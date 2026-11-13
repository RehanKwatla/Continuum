"""Deterministic, evidence-linked analysis of captured Git commit history."""
from __future__ import annotations

from collections import Counter, defaultdict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.code_intelligence import ArchitectureComponent, CodeAnalysisRun
from app.models.git_history import CommitFileChange, CommitInsight, HistoryAnalysisRun
from app.models.repository_intelligence import CommitRecord, PullRequestRecord, RepositoryConnection, RepositorySnapshot

ANALYSIS_VERSION = "history-v1"
UNCLEAR_INTENT = "Change intent could not be reliably determined from the available history."


def classify_commit(message: str | None, paths: list[str]) -> dict:
    msg = (message or "").strip().lower()
    names = [path.lower() for path in paths]
    signals: list[str] = []
    category, confidence = "other", "low"
    if not msg and not paths:
        return {"category": "unknown", "confidence": "low", "signals": ["No commit message or changed paths were captured."]}
    if msg.startswith("revert ") or "this reverts commit " in msg:
        category, confidence = "revert", "high"
        signals.append("Commit message uses an explicit revert marker.")
    elif any("cve-" in msg or phrase in msg for phrase in ("security vulnerability fix", "fix security vulnerability", "vulnerability remediation")):
        category, confidence = "security", "medium"
        signals.append("Commit message explicitly describes vulnerability remediation.")
    elif any(any(token in p for token in ("package-lock", "pnpm-lock", "yarn.lock", "requirements", "pyproject", "cargo.lock", "go.sum")) for p in names) and any(token in msg for token in ("bump", "update", "upgrade", "dependency", "deps")):
        category, confidence = "dependency_update", "high"
        signals.append("Dependency manifest or lockfile changed with an update signal in the message.")
    elif any(token in msg for token in ("performance", "optimiz", "faster", "reduce latency")):
        category, confidence = "performance", "medium"
        signals.append("Commit message describes performance work.")
    elif any(p.endswith((".md", ".rst", ".adoc")) or "/docs/" in p or p.startswith("docs/") for p in names) and all(p.endswith((".md", ".rst", ".adoc")) or "/docs/" in p or p.startswith("docs/") for p in names):
        category, confidence = "documentation", "high"
        signals.append("All captured changed paths are documentation files.")
    elif any("test" in p or p.endswith((".spec.js", ".spec.ts", ".test.js", ".test.ts")) for p in names) and all("test" in p or p.endswith((".spec.js", ".spec.ts", ".test.js", ".test.ts")) for p in names):
        category, confidence = "testing", "high"
        signals.append("All captured changed paths are test files.")
    elif any(name in p for p in names for name in ("dockerfile", "docker-compose", ".github/workflows/", "webpack", "vite.config", "pyproject.toml", "setup.cfg", "Makefile")):
        category, confidence = "build_configuration", "medium"
        signals.append("Changed paths include build or CI configuration.")
    elif any(token in msg for token in ("refactor", "restructure", "cleanup", "clean up")):
        category, confidence = "refactoring", "medium"
        signals.append("Commit message describes refactoring or cleanup.")
    elif any(token in msg for token in ("fix", "bug", "regression", "patch")):
        category, confidence = "bug_fix", "medium"
        signals.append("Commit message describes a fix or regression.")
    elif any(token in msg for token in ("feat", "feature", "add ", "introduce", "implement")):
        category, confidence = "feature", "medium"
        signals.append("Commit message describes adding or implementing behavior.")
    elif msg or paths:
        signals.append("No category had sufficiently specific supporting signals.")
    return {"category": category, "confidence": confidence, "signals": signals}


def _summary(commit: CommitRecord, paths: list[str], components: dict[str, str]) -> tuple[str, list[str]]:
    affected = sorted({components.get(path) for path in paths if components.get(path)})
    if paths:
        visible = ", ".join(paths[:5]) + (f" and {len(paths) - 5} more" if len(paths) > 5 else "")
        what = f"Changed {len(paths)} file(s): {visible}."
    else:
        what = "Changed-file details are unavailable for this commit."
    component_text = f" Affected analyzed component(s): {', '.join(affected)}." if affected else " No matching Stage 3 component evidence was available."
    summary = f"{what}{component_text} {UNCLEAR_INTENT}"
    return summary, affected


def analyze_history(db: Session, snapshot: RepositorySnapshot, connection: RepositoryConnection) -> HistoryAnalysisRun:
    existing = db.scalar(select(HistoryAnalysisRun).where(HistoryAnalysisRun.snapshot_id == snapshot.id, HistoryAnalysisRun.analysis_version == ANALYSIS_VERSION))
    if existing:
        return existing
    commits = db.scalars(select(CommitRecord).where(CommitRecord.snapshot_id == snapshot.id).order_by(CommitRecord.committed_at)).all()
    changes = db.scalars(select(CommitFileChange).where(CommitFileChange.snapshot_id == snapshot.id)).all()
    changes_by_sha: dict[str, list[CommitFileChange]] = defaultdict(list)
    for change in changes:
        changes_by_sha[change.commit_sha].append(change)
    code_run = db.scalar(select(CodeAnalysisRun).where(CodeAnalysisRun.snapshot_id == snapshot.id).order_by(CodeAnalysisRun.created_at.desc()).limit(1))
    components: dict[str, str] = {}
    component_edges: dict[str, set[str]] = defaultdict(set)
    if code_run:
        for component in db.scalars(select(ArchitectureComponent).where(ArchitectureComponent.analysis_run_id == code_run.id)).all():
            for path in component.file_paths or []:
                components[path] = component.component_name
        from app.models.code_intelligence import ModuleDependency
        for edge in db.scalars(select(ModuleDependency).where(ModuleDependency.analysis_run_id == code_run.id, ModuleDependency.target_file.is_not(None))).all():
            source_component, target_component = components.get(edge.source_file), components.get(edge.target_file)
            if source_component and target_component and source_component != target_component:
                component_edges[source_component].add(target_component)
    contributors: dict[str, dict] = {}
    file_frequency, pair_frequency, category_counts = Counter(), Counter(), Counter()
    insights = []
    timestamps = []
    for commit in commits:
        file_rows = changes_by_sha.get(commit.commit_sha, [])
        paths = [item.file_path for item in file_rows] or list(commit.changed_files or [])
        classification = classify_commit(commit.message, paths)
        summary, affected = _summary(commit, paths, components)
        downstream = sorted({target for component in affected for target in component_edges.get(component, set())})
        if downstream:
            summary += f" Parsed imports also connect these components to: {', '.join(downstream)}; this is a structural observation, not an impact prediction."
        signals = classification["signals"]
        insights.append(CommitInsight(snapshot_id=snapshot.id, commit_sha=commit.commit_sha, analysis_version=ANALYSIS_VERSION, category=classification["category"], confidence=classification["confidence"], classification_method="deterministic_message_and_path_rules", signals=signals, summary=summary, affected_components=affected, source_references=[{"type": "commit", "sha": commit.commit_sha, "url": commit.url}, *[{"type": "changed_file", "path": path, "sha": commit.commit_sha} for path in paths[:100]]]))
        category_counts[classification["category"]] += 1
        for path in set(paths):
            file_frequency[path] += 1
        unique_paths = sorted(set(paths))[:60]
        for i, first in enumerate(unique_paths):
            for second in unique_paths[i + 1:]:
                pair_frequency[(first, second)] += 1
        # Never collapse records by display name. Email is a Git identity
        # signal, while the GitHub login remains a separately reported field.
        if commit.author_email:
            actor_key = f"git-email:{commit.author_email.strip().lower()}"
        else:
            actor_key = f"unattributed:{commit.commit_sha}"
        actor = contributors.setdefault(actor_key, {"identity_key": actor_key, "author_name": commit.author_name, "author_email": commit.author_email, "github_login": None, "commits": 0, "known_additions": 0, "known_deletions": 0, "line_stats_complete": True, "files": set(), "modules": set(), "observed_first_at": None, "observed_last_at": None})
        if commit.github_author:
            actor["github_login"] = commit.github_author if not actor["github_login"] else actor["github_login"]
        actor["commits"] += 1
        if commit.additions is None or commit.deletions is None:
            actor["line_stats_complete"] = False
        else:
            actor["known_additions"] += commit.additions
            actor["known_deletions"] += commit.deletions
        actor["files"].update(paths)
        actor["modules"].update(components[p] for p in paths if p in components)
        if commit.committed_at:
            timestamps.append(commit.committed_at)
            actor["observed_first_at"] = min(actor["observed_first_at"], commit.committed_at) if actor["observed_first_at"] else commit.committed_at
            actor["observed_last_at"] = max(actor["observed_last_at"], commit.committed_at) if actor["observed_last_at"] else commit.committed_at
    total_author_commits = sum(item["commits"] for item in contributors.values()) or 1
    contributors_list = []
    for actor in contributors.values():
        actor["files_modified"] = len(actor.pop("files"))
        actor["modules_touched"] = sorted(actor.pop("modules"))
        actor["additions"] = actor.pop("known_additions") if actor["line_stats_complete"] else None
        actor["deletions"] = actor.pop("known_deletions") if actor["line_stats_complete"] else None
        actor["commit_share_percent"] = round(actor["commits"] * 100 / total_author_commits, 1)
        contributors_list.append(actor)
    contributors_list.sort(key=lambda item: (-item["commits"], item["identity_key"]))
    hotspots = []
    for path, count in file_frequency.most_common(50):
        rows = [item for item in changes if item.file_path == path]
        dates = [commit.committed_at for commit in commits if commit.committed_at and path in (commit.changed_files or [])]
        stats_known = bool(rows) and len(rows) == count and all(item.statistics_available for item in rows)
        hotspots.append({"file_path": path, "change_count": count, "known_additions": sum(item.additions or 0 for item in rows) if stats_known else None, "known_deletions": sum(item.deletions or 0 for item in rows) if stats_known else None, "observed_first_change": min(dates) if dates else None, "observed_last_change": max(dates) if dates else None, "evidence": "Counted from captured commit file records; activity outside the ingested history is unknown."})
    co_changes = [{"files": [a, b], "co_change_count": count, "evidence": "Both paths occur in the same captured commit(s)."} for (a, b), count in pair_frequency.most_common(50) if count > 1]
    available_stats = all(commit.additions is not None and commit.deletions is not None for commit in commits) if commits else False
    configured_limit = (snapshot.limits or {}).get("commits")
    coverage = {"snapshot_id": str(snapshot.id), "branch": snapshot.branch, "commit_sha": snapshot.commit_sha, "commits_retrieved": len(commits), "configured_commit_limit": configured_limit, "coverage_limited_by_configured_limit": bool(configured_limit and len(commits) >= int(configured_limit)), "earliest_available_commit": min(timestamps).isoformat() if timestamps else None, "latest_available_commit": max(timestamps).isoformat() if timestamps else None, "changed_files_observed": len(file_frequency), "file_statistics_complete": available_stats, "file_change_rows": len(changes), "pull_requests_retrieved": snapshot.pull_requests_processed, "branches_observed": (connection.branches or []), "co_change_file_cap_per_commit": 60, "coverage_note": "Coverage is limited to the commits captured for this repository snapshot; it is not a complete-history guarantee. Commit-to-PR links and provider-wide commit counts are not available from the existing ingested records."}
    for actor in contributors_list:
        for key in ("observed_first_at", "observed_last_at"):
            if actor[key]:
                actor[key] = actor[key].isoformat()
    pull_requests = db.scalars(select(PullRequestRecord).where(PullRequestRecord.snapshot_id == snapshot.id)).all()
    pr_status = {"open": 0, "merged": 0, "closed_without_merge": 0}
    for pr in pull_requests:
        if pr.merged_at:
            pr_status["merged"] += 1
        elif pr.state == "open":
            pr_status["open"] += 1
        else:
            pr_status["closed_without_merge"] += 1
    summary = {"classified_commits": len(insights), "category_counts": dict(category_counts), "contributors_observed": len(contributors_list), "files_changed": len(file_frequency), "co_change_pairs": len(co_changes), "pull_request_outcomes": pr_status, "author_identity_note": "Contributors are grouped by exact Git author email. Commits with no email remain individually unattributed; GitHub login is shown separately and is not merged into Git identity."}
    run = HistoryAnalysisRun(snapshot_id=snapshot.id, analysis_version=ANALYSIS_VERSION, status="completed", coverage=coverage, contributors=contributors_list, hotspots=hotspots, co_changes=co_changes, summary=summary)
    db.add(run)
    db.flush()
    for insight in insights:
        db.add(insight)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(HistoryAnalysisRun).where(HistoryAnalysisRun.snapshot_id == snapshot.id, HistoryAnalysisRun.analysis_version == ANALYSIS_VERSION))
        if existing:
            return existing
        raise
    db.refresh(run)
    return run


def history_payload(run: HistoryAnalysisRun) -> dict:
    return {"id": run.id, "snapshot_id": run.snapshot_id, "status": run.status, "analysis_version": run.analysis_version, "coverage": run.coverage, "summary": run.summary, "contributors": run.contributors, "hotspots": run.hotspots, "co_changes": run.co_changes}
