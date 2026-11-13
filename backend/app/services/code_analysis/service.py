"""Persistence and orchestration for snapshot-scoped repository analysis."""
from __future__ import annotations

import json
import logging
import re
import tomllib
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.session import session_scope
from app.models.code_intelligence import (
    ArchitectureComponent, CodeAnalysisRun, CodeSymbol, EntryPoint,
    ExternalDependency, LanguageStatistic, ModuleDependency, TechnologyDetection,
)
from app.models.enums import CodeAnalysisStatus, ProcessingStatus, RepositoryIngestionStatus
from app.models.repository_intelligence import RepositoryConnection, RepositoryFile, RepositorySnapshot
from app.models.source import Source
from app.services.code_analysis.engine import analyze_files
from app.services.code_analysis.parser import PARSER_VERSION

logger = logging.getLogger(__name__)
MAX_ANALYSIS_FILES = 2000
MAX_ANALYSIS_BYTES = 64 * 1024 * 1024


def _external_dependencies(contents: dict[str, str]) -> list[dict]:
    found = []
    package_locks: dict[str, dict] = {}
    for path, text in contents.items():
        if path.rsplit("/", 1)[-1].lower() == "package-lock.json":
            try:
                lock = json.loads(text)
                package_locks[path.rsplit("/", 1)[0]] = {key.removeprefix("node_modules/"): value.get("version") for key, value in (lock.get("packages") or {}).items() if key.startswith("node_modules/") and isinstance(value, dict)}
            except (ValueError, TypeError):
                pass
    for path, text in contents.items():
        name = path.rsplit("/", 1)[-1].lower()
        try:
            if name == "package.json":
                data = json.loads(text)
                for group, category in (("dependencies", "runtime"), ("devDependencies", "development"), ("optionalDependencies", "optional"), ("peerDependencies", "peer")):
                    for package, version in (data.get(group) or {}).items():
                        found.append({"package_name": package, "declared_version": str(version), "resolved_version": package_locks.get(path.rsplit("/", 1)[0], {}).get(package), "dep_category": category, "manifest_path": path, "ecosystem": "npm"})
            elif name in {"requirements.txt", "pipfile"}:
                for line in text.splitlines():
                    line = line.split("#", 1)[0].strip()
                    match = re.match(r"([A-Za-z0-9_.-]+)\s*(?:\[.*?\])?\s*(===|==|~=|>=|<=|!=|>|<)?\s*([^;\s]+)?", line)
                    if match:
                        found.append({"package_name": match.group(1), "declared_version": ((match.group(2) or "") + (match.group(3) or "")) or None, "dep_category": "runtime", "manifest_path": path, "ecosystem": "python"})
            elif name == "pyproject.toml":
                data = tomllib.loads(text)
                groups = [(data.get("project", {}).get("dependencies", []), "runtime")]
                groups += [(items, "development") for items in data.get("project", {}).get("optional-dependencies", {}).values()]
                poetry = data.get("tool", {}).get("poetry", {})
                groups += [(poetry.get("dependencies", {}), "runtime"), (poetry.get("dev-dependencies", {}), "development")]
                for items, category in groups:
                    if isinstance(items, dict):
                        pairs = items.items()
                    else:
                        pairs = ((re.split(r"[<>=!~; ]", item, maxsplit=1)[0], item[len(re.split(r"[<>=!~; ]", item, maxsplit=1)[0]):].strip() or None) for item in items)
                    for package, version in pairs:
                        if package.lower() == "python":
                            continue
                        declared = version if isinstance(version, str) else version.get("version") if isinstance(version, dict) else None
                        found.append({"package_name": package, "declared_version": declared, "dep_category": category, "manifest_path": path, "ecosystem": "python"})
            elif name == "cargo.toml":
                data = tomllib.loads(text)
                for group, category in (("dependencies", "runtime"), ("dev-dependencies", "development"), ("build-dependencies", "build")):
                    for package, version in data.get(group, {}).items():
                        found.append({"package_name": package, "declared_version": version if isinstance(version, str) else version.get("version"), "dep_category": category, "manifest_path": path, "ecosystem": "cargo"})
            elif name == "go.mod":
                for line in text.splitlines():
                    m = re.match(r"\s*([^\s()]+)\s+(v\S+)", line)
                    if m and m.group(1) != "module":
                        found.append({"package_name": m.group(1), "declared_version": m.group(2), "dep_category": "runtime", "manifest_path": path, "ecosystem": "go"})
            elif name == "composer.json":
                data = json.loads(text)
                for group, category in (("require", "runtime"), ("require-dev", "development")):
                    for package, version in (data.get(group) or {}).items():
                        if package.lower() != "php":
                            found.append({"package_name": package, "declared_version": str(version), "dep_category": category, "manifest_path": path, "ecosystem": "composer"})
            elif name == "pom.xml":
                import xml.etree.ElementTree as ET
                root = ET.fromstring(text)
                ns = {"m": root.tag.split("}")[0].lstrip("{")} if "}" in root.tag else {}
                prefix = "m:" if ns else ""
                for dep in root.findall(f".//{prefix}dependency", ns):
                    group = dep.findtext(f"{prefix}groupId", default="", namespaces=ns)
                    artifact = dep.findtext(f"{prefix}artifactId", default="", namespaces=ns)
                    version = dep.findtext(f"{prefix}version", namespaces=ns)
                    scope = dep.findtext(f"{prefix}scope", default="compile", namespaces=ns)
                    if artifact:
                        found.append({"package_name": f"{group}:{artifact}".strip(":"), "declared_version": version, "dep_category": "development" if scope in {"test", "provided"} else "runtime", "manifest_path": path, "ecosystem": "maven"})
            elif name in {"build.gradle", "build.gradle.kts"}:
                for match in re.finditer(r"\b(implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly)\s*\(?\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]", text):
                    scope, group, artifact, version = match.groups()
                    found.append({"package_name": f"{group}:{artifact}", "declared_version": version, "dep_category": "development" if scope.startswith("test") else "runtime", "manifest_path": path, "ecosystem": "gradle"})
        except (ValueError, TypeError):
            continue
    return found


def _run_code_analysis(analysis_id) -> None:
    with session_scope() as db:
        run = db.get(CodeAnalysisRun, analysis_id)
        if not run:
            return
        run.status = CodeAnalysisStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        db.commit()
        snapshot = db.get(RepositorySnapshot, run.snapshot_id)
        connection = db.get(RepositoryConnection, snapshot.repository_connection_id) if snapshot else None
        rows = db.scalars(select(RepositoryFile).where(RepositoryFile.snapshot_id == run.snapshot_id).order_by(RepositoryFile.path).limit(MAX_ANALYSIS_FILES)).all()
        contents: dict[str, str] = {}
        total = 0
        for row in rows:
            if not row.source_id or row.analysis_status != ProcessingStatus.COMPLETED:
                continue
            source = db.get(Source, row.source_id)
            if not source or source.content is None:
                continue
            encoded = source.content.encode("utf-8", errors="replace")
            if len(encoded) > 512_000 or total + len(encoded) > MAX_ANALYSIS_BYTES:
                continue
            contents[row.path] = source.content
            total += len(encoded)
        files = [{"path": r.path, "extension": r.extension, "size": r.size, "analysis_status": r.analysis_status.value} for r in rows]
        result = analyze_files(files, contents, connection.languages if connection else None)
        run.languages_summary = {"local": result["languages"].get("extension", []), "github": result["languages"].get("github", []), "unknown_file_count": result["unknown_file_count"]}
        run.technologies_summary = result["technologies"]
        run.entry_points_summary = result["entry_points"]
        run.architecture_summary = {"tree": result["tree"], "directories": result["directories"], "files": result["files"], "analysed_files": result["analysed_files"], "skipped_files": result["skipped_files"], "category_counts": result["category_counts"], "routes": result["routes"], "components": result["components"], "errors": result["errors"], "truncated": len(rows) >= MAX_ANALYSIS_FILES, "symbol_count": len(result["symbols"]), "dependency_count": len(result["imports"])}
        for lang in (result["languages"].get("extension", []) + result["languages"].get("github", [])):
            db.add(LanguageStatistic(analysis_run_id=run.id, language=lang["language"], file_count=lang["file_count"], total_bytes=lang["total_bytes"], percentage=lang["percentage"], detection_source=lang["detection_source"]))
        for tech in result["technologies"]:
            db.add(TechnologyDetection(analysis_run_id=run.id, technology=tech["technology"], category=tech["category"], version=tech.get("version"), confidence=tech.get("confidence", "medium"), detection_method=tech.get("detection_method", "manifest"), evidence_paths=tech.get("evidence_paths", [])))
        for item in result["symbols"]:
            db.add(CodeSymbol(analysis_run_id=run.id, file_path=item["file_path"], symbol_name=item["name"], symbol_type=item["type"], language=item["language"], start_line=item["start"], end_line=item["end"], parameters=item.get("parameters"), visibility=item.get("visibility"), extras=item.get("extras", {})))
        for edge in result["imports"]:
            db.add(ModuleDependency(analysis_run_id=run.id, source_module=edge["source_module"], target_module=edge["target_module"], relationship_type=edge["relationship_type"], source_file=edge["source_file"], target_file=edge["target_file"], line_number=edge["line_number"], imported_symbols=edge["imported_symbols"], resolution_status=edge["resolution_status"]))
        for entry in result["entry_points"]:
            db.add(EntryPoint(analysis_run_id=run.id, file_path=entry["file_path"], runtime_or_framework=entry["runtime_or_framework"], detection_method=entry["detection_method"], confidence=entry["confidence"], evidence=entry["evidence"]))
        for component in result["components"]:
            db.add(ArchitectureComponent(analysis_run_id=run.id, **component))
        for dep in _external_dependencies(contents):
            db.add(ExternalDependency(analysis_run_id=run.id, resolved_version=dep.pop("resolved_version", None), **dep))
        run.status = CodeAnalysisStatus.PARTIALLY_COMPLETED if result["errors"] or run.architecture_summary["truncated"] else CodeAnalysisStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def run_code_analysis(analysis_id) -> None:
    """Execute in the background and persist an observable failure state."""
    try:
        _run_code_analysis(analysis_id)
    except Exception as exc:
        logger.exception("Code analysis failed id=%s error=%s", analysis_id, type(exc).__name__)
        with session_scope() as db:
            run = db.get(CodeAnalysisRun, analysis_id)
            if run:
                run.status = CodeAnalysisStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
                run.architecture_summary = {**(run.architecture_summary or {}), "error": "Static analysis failed; inspect server logs using the analysis run id."}


def run_payload(run: CodeAnalysisRun) -> dict:
    return {"id": run.id, "snapshot_id": run.snapshot_id, "status": run.status.value, "parser_version": run.parser_version, "started_at": run.started_at, "completed_at": run.completed_at, "languages": run.languages_summary, "technologies": run.technologies_summary, "entry_points": run.entry_points_summary, "architecture": run.architecture_summary}
