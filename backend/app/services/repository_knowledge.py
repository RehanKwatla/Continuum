"""Bounded deterministic knowledge reconstruction from captured repository evidence.

Imported text is always treated as data. This service never executes repository
content, installs packages, makes network calls, or sends data to an LLM.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import session_scope
from app.models.code_intelligence import ArchitectureComponent, CodeAnalysisRun, EntryPoint, ExternalDependency, ModuleDependency, TechnologyDetection
from app.models.git_history import CommitInsight
from app.models.repository_knowledge import (
    KnowledgeAnalysisRun, KnowledgeConflict, KnowledgeEntity, KnowledgeEvidence,
    KnowledgeGap, KnowledgeRelationship, KnowledgeUnit, ProjectAssumption,
)
from app.models.evidence_span import EvidenceSpan
from app.models.repository_intelligence import (
    CommitRecord, IssueRecord, PullRequestRecord, RepositoryConnection,
    RepositoryFile, RepositorySnapshot,
)
from app.models.source import Source

logger = logging.getLogger(__name__)
ANALYSIS_VERSION = "knowledge-v1"
MAX_SOURCES = 2500
MAX_SOURCE_CHARS = 500_000
MAX_UNITS_PER_SOURCE = 50
MAX_EXTRACTED_UNITS = 5000
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc"}
CONFIG_NAMES = {"pyproject.toml", "package.json", "requirements.txt", "dockerfile", "docker-compose.yml", "docker-compose.yaml", "vite.config.ts", "tsconfig.json", ".env.example"}
RUNTIME_CONFIG_NAMES = {".env.example", "docker-compose.yml", "docker-compose.yaml", "settings.py", "config.py", "application.properties", "application.yml", "application.yaml", "database.yml"}
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cs", ".php", ".rb"}
TECH_TERMS = {"postgresql": "PostgreSQL", "postgres": "PostgreSQL", "sqlite": "SQLite", "mysql": "MySQL", "mongodb": "MongoDB", "redis": "Redis"}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, max(offset, 0)) + 1


def _category(source_type: str, path: str, text: str) -> str:
    value = f"{path} {text[:250]}".lower()
    if source_type.endswith("issue"):
        return "reported_problem" if any(word in value for word in ("bug", "error", "broken", "fail", "blocker")) else "unresolved_question" if "?" in text or "question" in value else "feature_description"
    if source_type.endswith("pull_request"):
        return "implementation_context"
    if source_type.endswith("commit"):
        return "historical_change"
    if "contribut" in value or "development" in value or "setup" in value or "install" in value:
        return "development_workflow"
    if any(term in value for term in ("deploy", "docker", "release", "production", "operations")):
        return "operational_procedure"
    if any(term in value for term in ("architecture", "design", "component", "service", "module")):
        return "architecture_description"
    if any(term in value for term in ("limitation", "not supported", "known issue", "workaround")):
        return "known_limitation"
    if any(term in value for term in ("decision", "chose", "selected", "trade-off", "tradeoff", "because")):
        return "technical_decision_context"
    if any(term in value for term in ("feature", "capability", "provides", "allows", "supports")):
        return "feature_description"
    return "project_context"


def extract_document_units(content: str, *, source_type: str, path: str) -> list[dict]:
    """Split text into bounded paragraphs and retain exact one-based line ranges."""
    if len(content) > MAX_SOURCE_CHARS:
        content = content[:MAX_SOURCE_CHARS]
    units = []
    for match in re.finditer(r"(?m)(?:^\s*#.*\n)?(?:[^\n].*(?:\n|$))+", content):
        block = match.group(0).strip()
        if len(block) < 30 or len(block) > 6000:
            continue
        clean = re.sub(r"(?m)^#{1,6}\s*", "", block).strip()
        if len(clean) < 30:
            continue
        first = re.split(r"(?<=[.!?])\s+|\n", clean, maxsplit=1)[0].strip(" -*#")
        if len(first) < 8:
            first = PureTitle(path)
        offset = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
        units.append({"category": _category(source_type, path, clean), "title": first[:480], "content": clean[:6000], "start": offset, "end": min(match.end(), offset + len(block)), "line_start": _line_number(content, offset), "line_end": _line_number(content, min(match.end(), offset + len(block))), "evidence_level": "observed", "confidence": 0.78, "method": "bounded_paragraph_extraction"})
        if len(units) >= MAX_UNITS_PER_SOURCE:
            break
    return units


def PureTitle(path: str) -> str:
    return path.rsplit("/", 1)[-1].replace("_", " ").replace("-", " ") or "Repository source"


def _source_path(row: RepositoryFile) -> str:
    return row.path


def _gather_sources(db, snapshot_id) -> tuple[list[dict], dict[str, int]]:
    docs: list[dict] = []
    counts = Counter()
    file_rows = db.scalars(select(RepositoryFile).where(RepositoryFile.snapshot_id == snapshot_id).order_by(RepositoryFile.path).limit(MAX_SOURCES)).all()
    for row in file_rows:
        path = _source_path(row)
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        is_code = suffix in CODE_SUFFIXES
        if not (is_code or path.lower().endswith(tuple(DOC_SUFFIXES)) or path.rsplit("/", 1)[-1].lower() in CONFIG_NAMES or "/.github/workflows/" in f"/{path.lower()}" or (suffix in {".yaml", ".yml", ".toml", ".ini", ".cfg", ".json"} and ("config" in path.lower() or suffix == ".toml"))):
            continue
        counts["discovered"] += 1
        source = db.get(Source, row.source_id) if row.source_id else None
        if not source or source.content is None:
            counts["unavailable"] += 1
            continue
        docs.append({"source": source, "source_type": source.source_type.value, "path": path, "content": source.content, "timestamp": source.created_at_source, "url": source.source_url, "is_code": is_code})
        counts["processed"] += 1
    record_models = ((IssueRecord, "issue"), (PullRequestRecord, "pull_request"), (CommitRecord, "commit"))
    for model, label in record_models:
        rows = db.scalars(select(model).where(model.snapshot_id == snapshot_id).limit(MAX_SOURCES)).all()
        counts[f"{label}_records"] = len(rows)
        counts["discovered"] += len(rows)
        for row in rows:
            if not row.source_id:
                counts["unavailable"] += 1
                continue
            source = db.get(Source, row.source_id)
            if not source or source.content is None:
                counts["unavailable"] += 1
                continue
            docs.append({"source": source, "source_type": source.source_type.value, "path": source.source_name, "content": source.content, "timestamp": source.created_at_source, "url": source.source_url, "record": row})
            counts["processed"] += 1
    return docs, dict(counts)


def _add_unit(db, run, repository_id, snapshot_id, item: dict, source_data: dict, entity_cache: dict) -> KnowledgeUnit:
    category, content = item["category"], item["content"]
    key = _digest(category, _normalise(content))
    unit = db.scalar(select(KnowledgeUnit).where(KnowledgeUnit.analysis_run_id == run.id, KnowledgeUnit.dedup_key == key))
    if unit is None:
        unit = KnowledgeUnit(analysis_run_id=run.id, repository_id=repository_id, snapshot_id=snapshot_id, category=category, title=item["title"], content=content, evidence_level=item["evidence_level"], confidence=item["confidence"], extraction_method=item["method"], extraction_version=ANALYSIS_VERSION, freshness_status="unverified", source_timestamp=source_data["timestamp"], dedup_key=key)
        db.add(unit)
        db.flush()
        unit_entity = _entity(db, run, repository_id, "knowledge_unit", str(unit.id), unit.title, entity_cache)
        project_entity = _entity(db, run, repository_id, "repository", str(repository_id), "Repository project", entity_cache)
        source_key = str(source_data["source"].id)
        source_entity = _entity(db, run, repository_id, "source", source_key, source_data["path"], entity_cache)
    else:
        unit_entity = _entity(db, run, repository_id, "knowledge_unit", str(unit.id), unit.title, entity_cache)
        project_entity = _entity(db, run, repository_id, "repository", str(repository_id), "Repository project", entity_cache)
        source_entity = _entity(db, run, repository_id, "source", str(source_data["source"].id), source_data["path"], entity_cache)
    evidence_quote = item.get("evidence_quote", content)[:6000]
    file_path = source_data["path"] if source_data["source_type"].endswith(("github_file", "github_readme")) or source_data["path"].lower().endswith(tuple(DOC_SUFFIXES)) or source_data["path"].rsplit("/", 1)[-1].lower() in CONFIG_NAMES else None
    is_file = file_path is not None
    evidence = db.scalar(select(KnowledgeEvidence).where(KnowledgeEvidence.knowledge_unit_id == unit.id, KnowledgeEvidence.source_id == source_data["source"].id, KnowledgeEvidence.file_path == file_path, KnowledgeEvidence.line_start == (item.get("line_start") if is_file else None), KnowledgeEvidence.quote == evidence_quote))
    if evidence is None:
        span = None
        if item.get("start") is not None:
            span = db.scalar(select(EvidenceSpan).where(EvidenceSpan.source_id == source_data["source"].id, EvidenceSpan.start_offset <= item["start"], EvidenceSpan.end_offset >= item.get("end", item["start"])).order_by(EvidenceSpan.span_index).limit(1))
        evidence = KnowledgeEvidence(knowledge_unit_id=unit.id, source_id=source_data["source"].id, evidence_span_id=span.id if span else None, source_type=source_data["source_type"], source_name=source_data["source"].source_name, file_path=file_path, line_start=item.get("line_start") if is_file else None, line_end=item.get("line_end") if is_file else None, source_location=(f"{file_path}#L{item['line_start']}-L{item['line_end']}" if is_file and item.get("line_start") else source_data.get("url")), source_url=source_data.get("url"), quote=evidence_quote, source_timestamp=source_data["timestamp"])
        db.add(evidence)
        db.flush()
        for source_entity_id, target_entity_id, relationship_type in ((unit_entity.id, source_entity.id, "DOCUMENTS"), (project_entity.id, unit_entity.id, "SUPPORTS")):
            exists = db.scalar(select(KnowledgeRelationship.id).where(KnowledgeRelationship.analysis_run_id == run.id, KnowledgeRelationship.source_entity_id == source_entity_id, KnowledgeRelationship.target_entity_id == target_entity_id, KnowledgeRelationship.relationship_type == relationship_type))
            if not exists:
                db.add(KnowledgeRelationship(analysis_run_id=run.id, source_entity_id=source_entity_id, target_entity_id=target_entity_id, relationship_type=relationship_type, evidence_id=evidence.id, confidence=item["confidence"], evidence_level=item["evidence_level"]))
    return unit


def _entity(db, run, repository_id, entity_type, ref, name, cache):
    key = (entity_type, ref)
    if key in cache:
        return cache[key]
    entity = db.scalar(select(KnowledgeEntity).where(KnowledgeEntity.analysis_run_id == run.id, KnowledgeEntity.entity_type == entity_type, KnowledgeEntity.canonical_reference == ref))
    if entity is None:
        entity = KnowledgeEntity(analysis_run_id=run.id, repository_id=repository_id, entity_type=entity_type, entity_name=name[:500], canonical_reference=ref[:1000], metadata_json={})
        db.add(entity)
        db.flush()
    cache[key] = entity
    return entity


def _create_gap(db, run, repository_id, title, category, description, component, why, question, severity, confidence, refs):
    key = _digest(category, _normalise(title), *(sorted(str(ref.get("id") or ref.get("source_id") or "") for ref in refs)))
    exists = db.scalar(select(KnowledgeGap).where(KnowledgeGap.analysis_run_id == run.id, KnowledgeGap.dedup_key == key))
    if exists:
        return
    db.add(KnowledgeGap(analysis_run_id=run.id, repository_id=repository_id, title=title[:500], category=category, description=description, affected_component=component, why_it_matters=why, recommended_question=question, severity=severity, confidence=confidence, status="open", evidence_references=refs, dedup_key=key))


def _reconcile_conflicts(db, run, repository_id, docs):
    docs_only = [doc for doc in docs if doc["path"].lower().endswith(tuple(DOC_SUFFIXES))]
    configs = [doc for doc in docs if doc["path"].rsplit("/", 1)[-1].lower() in RUNTIME_CONFIG_NAMES or doc["path"].lower().endswith(("/config/settings.py", "/config/database.yml"))]
    for document in docs_only:
        doc_text = document["content"].lower()
        doc_terms = {term: name for term, name in TECH_TERMS.items() if re.search(rf"\b{re.escape(term)}\b", doc_text)}
        for config in configs:
            if config["source"].id == document["source"].id:
                continue
            cfg_text = config["content"].lower()
            cfg_terms = {term: name for term, name in TECH_TERMS.items() if re.search(rf"\b{re.escape(term)}\b", cfg_text)}
            doc_values, cfg_values = set(doc_terms.values()), set(cfg_terms.values())
            if doc_values and cfg_values and doc_values.isdisjoint(cfg_values):
                term_a, name_a = next(iter(doc_terms.items()))
                term_b, name_b = next(iter(cfg_terms.items()))
                key = _digest("config_mismatch", str(document["source"].id), str(config["source"].id), name_a, name_b)
                if db.scalar(select(KnowledgeConflict).where(KnowledgeConflict.analysis_run_id == run.id, KnowledgeConflict.dedup_key == key)):
                    continue
                db.add(KnowledgeConflict(analysis_run_id=run.id, repository_id=repository_id, conflict_type="configuration_mismatch", claim_a=f"Documentation mentions {name_a}.", claim_b=f"Current configuration file {config['path']} mentions {name_b}.", evidence_a={"source_id": str(document["source"].id), "source": document["path"], "source_timestamp": document["timestamp"].isoformat() if document["timestamp"] else None, "term": term_a}, evidence_b={"source_id": str(config["source"].id), "source": config["path"], "source_timestamp": config["timestamp"].isoformat() if config["timestamp"] else None, "term": term_b}, confidence=0.66, status="open", possible_explanation="Documentation may be outdated, configuration may be transitional, or the sources may describe different environments.", dedup_key=key))


def _extract_assumptions(db, run, repository_id, docs):
    seen = set()
    for doc in docs:
        if not (doc.get("is_code") or doc["path"].lower().endswith(tuple(DOC_SUFFIXES)) or doc["path"].rsplit("/", 1)[-1].lower() in CONFIG_NAMES):
            continue
        pattern = re.compile(r"os\.environ(?:\.get)?\s*\(\s*['\"]([A-Z][A-Z0-9_]{2,})|os\.getenv\s*\(\s*['\"]([A-Z][A-Z0-9_]{2,})|process\.env\.([A-Z][A-Z0-9_]{2,})|\b([A-Z][A-Z0-9_]{2,})\s*=")
        for match in pattern.finditer(doc["content"]):
            context = doc["content"][max(0, match.start()-50):min(len(doc["content"]), match.end()+100)]
            name = next((group for group in match.groups() if group), None)
            if not name:
                continue
            if name in seen or name in {"TRUE", "FALSE", "NULL", "NONE", "HTTP", "HTTPS"}:
                continue
            seen.add(name)
            key = _digest("environment", name)
            if db.scalar(select(ProjectAssumption).where(ProjectAssumption.analysis_run_id == run.id, ProjectAssumption.dedup_key == key)):
                continue
            db.add(ProjectAssumption(analysis_run_id=run.id, repository_id=repository_id, description=f"Runtime or configuration behavior references environment variable {name}; an environment providing it may be required.", assumption_type="environment_requirement", evidence_level="observed", confidence=0.72, verification_status="unverified", supporting_evidence=[{"source_id": str(doc["source"].id), "path": doc["path"], "line": _line_number(doc["content"], match.start()), "quote": context.strip()[:400]}], verification_method=f"Check deployment configuration for {name} and confirm expected behavior when it is absent.", dedup_key=key))


def _extract_analysis_units(db, run, connection, snapshot, docs, entity_cache) -> int:
    """Connect Stage 3/4 persisted outputs to their original file/commit evidence."""
    file_rows = db.scalars(select(RepositoryFile).where(RepositoryFile.snapshot_id == snapshot.id)).all()
    doc_by_path = {doc["path"]: doc for doc in docs}
    file_by_path = {row.path: row for row in file_rows}
    generated = []
    code_run = db.scalar(select(CodeAnalysisRun).where(CodeAnalysisRun.snapshot_id == snapshot.id).order_by(CodeAnalysisRun.created_at.desc()).limit(1))
    if code_run:
        for component in db.scalars(select(ArchitectureComponent).where(ArchitectureComponent.analysis_run_id == code_run.id)).all():
            generated.append(("architecture_description", component.component_name, f"Stage 3 grouped {len(component.file_paths or [])} captured file(s) into component {component.component_name}. Evidence level: inferred from persisted static analysis; confidence: {component.confidence}.", component.file_paths or [], "inferred", 0.60 if component.confidence == "low" else 0.75, "stage3_architecture_analysis"))
        for dependency in db.scalars(select(ExternalDependency).where(ExternalDependency.analysis_run_id == code_run.id).limit(500)).all():
            generated.append(("dependency_requirement", dependency.package_name, f"A dependency manifest declares {dependency.package_name} ({dependency.declared_version or 'version unspecified'}) as {dependency.dep_category} dependency in {dependency.manifest_path}. A resolved version was {'recorded as ' + dependency.resolved_version if dependency.resolved_version else 'not established by the captured manifest data'}.", [dependency.manifest_path], "observed", 0.88, "stage3_manifest_analysis"))
        for technology in db.scalars(select(TechnologyDetection).where(TechnologyDetection.analysis_run_id == code_run.id).limit(300)).all():
            generated.append(("feature_description", technology.technology, f"Stage 3 detected {technology.technology} in category {technology.category} by {technology.detection_method}; confidence {technology.confidence}.", technology.evidence_paths or [], "observed", 0.82 if technology.confidence == "high" else 0.68, "stage3_manifest_analysis"))
        for entry in db.scalars(select(EntryPoint).where(EntryPoint.analysis_run_id == code_run.id).limit(100)).all():
            generated.append(("architecture_description", f"Entry point: {entry.file_path}", f"Stage 3 identified {entry.file_path} as a likely entry point using {entry.detection_method}; confidence {entry.confidence}.", [entry.file_path], "inferred", 0.65, "stage3_entry_point_analysis"))
        for edge in db.scalars(select(ModuleDependency).where(ModuleDependency.analysis_run_id == code_run.id, ModuleDependency.resolution_status == "resolved").limit(500)).all():
            generated.append(("architecture_description", f"Module relationship: {edge.source_file} → {edge.target_file}", f"Static analysis observed an import from {edge.source_file} to {edge.target_file} at line {edge.line_number or 'unknown'}.", [edge.source_file], "observed", 0.9, "stage3_parsed_import"))
    insights = db.scalars(select(CommitInsight).where(CommitInsight.snapshot_id == snapshot.id).limit(500)).all()
    commits = {item.commit_sha: item for item in db.scalars(select(CommitRecord).where(CommitRecord.snapshot_id == snapshot.id)).all()}
    for insight in insights:
        commit = commits.get(insight.commit_sha)
        if not commit or not commit.source_id:
            continue
        source = db.get(Source, commit.source_id)
        if source and source.content:
            doc_by_path[f"__commit__:{commit.commit_sha}"] = {"source": source, "source_type": source.source_type.value, "path": source.source_name, "content": source.content, "timestamp": commit.committed_at, "url": commit.url}
            generated.append(("historical_change", f"{insight.category.replace('_', ' ').title()}: {(commit.message or commit.commit_sha).splitlines()[0][:150]}", insight.summary, [f"__commit__:{commit.commit_sha}"], "inferred", 0.60 if insight.confidence == "low" else 0.72, "stage4_deterministic_commit_analysis"))
    added = 0
    for category, title, content, paths, evidence_level, confidence, method in generated:
        for path in paths[:8]:
            doc = doc_by_path.get(path)
            if not doc and path in file_by_path:
                row = file_by_path[path]
                source = db.get(Source, row.source_id) if row.source_id else None
                if source and source.content:
                    doc = {"source": source, "source_type": source.source_type.value, "path": path, "content": source.content, "timestamp": source.created_at_source, "url": source.source_url}
            if not doc:
                continue
            quote = doc["content"][:1500]
            item = {"category": category, "title": title, "content": content, "evidence_level": evidence_level, "confidence": confidence, "method": method, "start": 0, "end": min(len(doc["content"]), len(quote)), "line_start": 1, "line_end": min(30, doc["content"].count("\n") + 1), "evidence_quote": quote}
            _add_unit(db, run, connection.id, snapshot.id, item, doc, entity_cache)
            added += 1
    return added


def _run_analysis(run_id) -> None:
    with session_scope() as db:
        run = db.get(KnowledgeAnalysisRun, run_id)
        if not run:
            return
        snapshot = db.get(RepositorySnapshot, run.snapshot_id)
        connection = db.get(RepositoryConnection, snapshot.repository_connection_id) if snapshot else None
        if not snapshot or not connection:
            run.status, run.error_details = "failed", "The repository snapshot is no longer available."
            return
        run.status, run.progress, run.started_at = "running", 5, datetime.now(timezone.utc)
        db.commit()
        try:
            docs, counts = _gather_sources(db, snapshot.id)
            entity_cache = {}
            extracted = 0
            for doc in docs:
                if doc.get("is_code"):
                    continue
                content = doc["content"]
                if len(content) > MAX_SOURCE_CHARS:
                    content = content[:MAX_SOURCE_CHARS]
                    counts["truncated"] = counts.get("truncated", 0) + 1
                units = extract_document_units(content, source_type=doc["source_type"], path=doc["path"])
                if not units and doc["source_type"].endswith(("issue", "pull_request", "commit")) and content.strip():
                    units = [{"category": _category(doc["source_type"], doc["path"], content), "title": doc["source"].source_name[:480], "content": content[:6000], "line_start": 1, "line_end": min(content.count("\n") + 1, 100), "evidence_level": "observed", "confidence": 0.65, "method": "structured_source_record"}]
                for unit in units:
                    _add_unit(db, run, connection.id, snapshot.id, unit, doc, entity_cache)
                    extracted += 1
                    if extracted >= MAX_EXTRACTED_UNITS:
                        counts["unit_limit_reached"] = 1
                        break
                if extracted >= MAX_EXTRACTED_UNITS:
                    break
            if extracted < MAX_EXTRACTED_UNITS:
                extracted += _extract_analysis_units(db, run, connection, snapshot, docs, entity_cache)
            run.progress = 45
            db.commit()
            issue_rows = db.scalars(select(IssueRecord).where(IssueRecord.snapshot_id == snapshot.id, IssueRecord.state == "open")).all()
            for issue in issue_rows:
                labels = {str(label).lower() for label in (issue.labels or [])}
                if labels.intersection({"bug", "blocker", "blocked", "question", "help wanted"}):
                    _create_gap(db, run, connection.id, f"Open issue #{issue.issue_number}: {issue.title}", "unresolved_implementation_question" if "question" in labels else "incomplete_feature_requirements" if "feature" in labels else "unresolved_implementation_question", f"This issue is still open in the captured snapshot. Closure status is not used as proof of resolution.", None, "An unresolved issue may contain a blocker or needed technical context for a successor.", f"What is the current status and intended resolution for issue #{issue.issue_number}?", "high" if labels.intersection({"blocker", "blocked"}) else "medium", 0.78, [{"source_id": str(issue.source_id) if issue.source_id else None, "issue_number": issue.issue_number, "url": issue.url, "title": issue.title}])
            file_paths = {doc["path"] for doc in docs}
            config_docs = [doc for doc in docs if doc["path"].rsplit("/", 1)[-1].lower() in CONFIG_NAMES]
            env_pattern = re.compile(r"os\.environ(?:\.get)?\s*\(\s*['\"]([A-Z][A-Z0-9_]{2,})|os\.getenv\s*\(\s*['\"]([A-Z][A-Z0-9_]{2,})|process\.env\.([A-Z][A-Z0-9_]{2,})")
            env_names = sorted({group for doc in docs for match in env_pattern.finditer(doc["content"]) for group in match.groups() if group})
            deployment_docs = any(any(word in path.lower() for word in ("deploy", "runbook", "operations", "production")) for path in file_paths)
            if env_names and config_docs and not deployment_docs:
                refs = [{"source_id": str(doc["source"].id), "path": doc["path"]} for doc in config_docs[:5]]
                _create_gap(db, run, connection.id, "Operational setup for configured environment variables", "missing_operational_procedures", f"Captured configuration references {', '.join(env_names[:12])}, but the indexed snapshot contains no deployment or runbook document to explain their values or failure behavior.", None, "A successor may not know which values are required or how missing configuration affects startup.", f"Which deployment environment supplies {', '.join(env_names[:5])}, and what are the recovery steps when a value is missing?", "medium", 0.65, refs)
            _extract_assumptions(db, run, connection.id, docs)
            _reconcile_conflicts(db, run, connection.id, docs)
            run.progress = 80
            db.flush()
            run.coverage = {"sources_discovered": counts.get("discovered", 0), "sources_processed": counts.get("processed", 0), "sources_unavailable": counts.get("unavailable", 0), "sources_skipped": max(0, counts.get("discovered", 0) - counts.get("processed", 0) - counts.get("unavailable", 0)), "documents_truncated": counts.get("truncated", 0), "unit_limit_reached": bool(counts.get("unit_limit_reached")), "issues_in_snapshot": counts.get("issue_records", 0), "pull_requests_in_snapshot": counts.get("pull_request_records", 0), "commits_in_snapshot": counts.get("commit_records", 0), "knowledge_units_extracted": extracted, "analysis_version": ANALYSIS_VERSION, "last_indexed_at": datetime.now(timezone.utc).isoformat(), "comments_indexed": False, "review_comments_indexed": False, "known_limitations": ["The existing Stage 2 connector does not ingest issue or PR discussion comments.", "Embedding infrastructure is not configured; keyword retrieval is used.", "Decision statements are excerpts; no accepted decision records exist in Stages 1–4.", "Source selection is limited to files already ingested in this snapshot."], "method": "deterministic extraction; no LLM or repository code execution"}
            run.status, run.progress, run.completed_at = "completed", 100, datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            run = db.get(KnowledgeAnalysisRun, run_id)
            if run:
                run.status = "failed"
                run.error_details = f"Knowledge analysis failed ({type(exc).__name__})."
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
            logger.exception("Knowledge analysis failed id=%s type=%s", run_id, type(exc).__name__)


def run_knowledge_analysis(run_id) -> None:
    """Background task entry point with isolated session and failure status."""
    _run_analysis(run_id)


def run_payload(run: KnowledgeAnalysisRun) -> dict:
    return {"id": run.id, "snapshot_id": run.snapshot_id, "status": run.status, "progress": run.progress, "analysis_version": run.analysis_version, "coverage": run.coverage, "error_details": run.error_details, "started_at": run.started_at, "completed_at": run.completed_at}
