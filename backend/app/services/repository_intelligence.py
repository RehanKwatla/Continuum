"""Persisted, bounded repository ingestion using the GitProvider adapter."""
from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.enums import (
    ACTIVE_REPOSITORY_INGESTION_STATUSES, AccessLabel, ProcessingStatus,
    RepositoryIngestionStatus as Status, SourceType,
)
from app.models.project import Project
from app.models.repository_intelligence import (
    CommitRecord, IssueRecord, PullRequestRecord, RepositoryConnection,
    RepositoryFile, RepositorySnapshot,
)
from app.models.git_history import CommitFileChange
from app.models.source import Source
from app.models.workspace import Workspace
from app.services.ingestion_service import IngestionService
from app.services.public_github import (
    GitHubApiError, GitHubPublicConnector, GitProvider, ParsedRepositoryUrl, RepositoryUrlError,
    parse_repository_url,
)

logger = logging.getLogger("continuum.repository_intelligence")
_limits = get_settings()
MAX_FILES = _limits.repository_max_files
MAX_TREE_ENTRIES = _limits.repository_max_tree_entries
MAX_FILE_BYTES = _limits.repository_max_file_bytes
MAX_TOTAL_BYTES = _limits.repository_max_content_bytes
MAX_COMMITS = _limits.repository_max_commits
MAX_ISSUES = _limits.repository_max_issues
MAX_PRS = _limits.repository_max_pull_requests
MAX_DEPTH = _limits.repository_max_tree_depth
SUPPORTED_EXTENSIONS = set(_limits.repository_allowed_extensions)
SPECIAL_FILES = {
    "readme", "contributing", "license", "dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "package.json", "requirements.txt", "pyproject.toml",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "tsconfig.json",
}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "cargo.lock", "composer.lock", "gemfile.lock", "pipfile.lock"}
DENIED_PARTS = {".git", "node_modules", "dist", "build", "coverage", "vendor", ".venv"}
SECRET_NAME = re.compile(r"(^|/)(\.env($|\.)|.*\.(pem|key|p12|pfx|crt|cer|cert)$|id_rsa($|\.)|credentials$|secrets?\.)", re.I)
MINIFIED = re.compile(r"\.(min|bundle)\.(js|css)$", re.I)


def _dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def github_metadata(raw: dict, languages: dict) -> dict:
    return {
        "name": raw["name"], "owner": raw["owner"]["login"],
        "description": raw.get("description"), "canonical_url": raw["html_url"],
        "default_branch": raw["default_branch"], "visibility": "public" if not raw.get("private") else "private",
        "language": raw.get("language"), "languages": languages,
        "stars": raw.get("stargazers_count", 0), "forks": raw.get("forks_count", 0),
        "open_issues": raw.get("open_issues_count", 0),
        "created_at": _dt(raw.get("created_at")), "updated_at": _dt(raw.get("updated_at")),
        "pushed_at": _dt(raw.get("pushed_at")), "license": (raw.get("license") or {}).get("spdx_id") or (raw.get("license") or {}).get("name"),
    }


def file_skip_reason(path: str, size: int, files_considered: int, content_budget: int) -> str | None:
    """Return a visible reason when a tree entry must not be downloaded."""
    parts = {part.lower() for part in PurePosixPath(path).parts}
    name = PurePosixPath(path).name
    extension = PurePosixPath(path).suffix.lower()
    special = name.lower() in SPECIAL_FILES or (".github" in parts and extension in {".yml", ".yaml"})
    if any(part in DENIED_PARTS or part in {"generated", "__generated__"} for part in parts) or SECRET_NAME.search(path):
        return "Excluded by repository safety filter."
    if name.lower() in LOCKFILES:
        return "Dependency lockfile is retained as metadata and excluded from source content ingestion."
    if files_considered >= MAX_FILES:
        return f"Repository file content limit ({MAX_FILES}) reached; metadata retained."
    if not (extension in SUPPORTED_EXTENSIONS or special) or MINIFIED.search(name) or size == 0:
        return "Not a supported source/documentation file."
    if size > MAX_FILE_BYTES:
        return f"File exceeds the {MAX_FILE_BYTES}-byte per-file content limit."
    if size > content_budget:
        return "Repository content budget reached."
    return None


def _fetch_validation(parsed: ParsedRepositoryUrl, connector=None):
    connector = connector or GitHubPublicConnector()
    try:
        raw = connector.repository(parsed.owner, parsed.name)
        if raw.get("private"):
            raise RepositoryUrlError("Only public GitHub repositories can be analysed.")
        if not raw.get("default_branch"):
            raise RepositoryUrlError("Repository does not have a default branch.")
        metadata = github_metadata(raw, connector.languages(parsed.owner, parsed.name))
        refs = connector.branches(parsed.owner, parsed.name)
        branches = [{"name": b["name"], "commit_sha": b["commit"]["sha"], "protected": bool(b.get("protected")), "is_default": b["name"] == raw["default_branch"]} for b in refs]
        by_name = {b["name"] for b in branches}
        if parsed.branch and parsed.branch not in by_name:
            raise RepositoryUrlError("The branch in that URL is not available in this repository.")
        return metadata, branches, parsed.branch or raw["default_branch"]
    finally:
        if connector is not None:
            connector.close()


def validate_repository_url(value: str, connector=None):
    parsed = parse_repository_url(value)
    metadata, branches, selected = _fetch_validation(parsed, connector)
    return parsed, metadata, branches, selected


def _set_stage(db: Session, snapshot: RepositorySnapshot, stage: Status):
    snapshot.ingestion_status = stage
    db.commit()


def _upsert_source(db, project, source_type, name, content, external_id, author, when, url, metadata):
    result = IngestionService(db).ingest_text_artifact(
        project, source_type=source_type, source_name=name, content=content,
        external_id=external_id, author=author, created_at_source=when,
        metadata=metadata, access_label=AccessLabel.PUBLIC, source_url=url,
    )
    source = db.get(Source, result.source_id) if result.source_id else None
    # IngestionResult currently does not expose source id. Resolve by stable external metadata.
    if source is None:
        source = db.scalar(select(Source).where(Source.project_id == project.id, Source.source_type == source_type, Source.external_id == external_id).order_by(Source.created_at.desc()))
    return source


def run_snapshot(snapshot_id: uuid.UUID):
    """Background-task entrypoint; opens its own DB session and persists stages."""
    factory = get_session_factory()
    db = factory()
    started = datetime.now(timezone.utc)
    connector = GitHubPublicConnector()
    try:
        snap = db.get(RepositorySnapshot, snapshot_id)
        if not snap:
            return
        snap.started_at = started
        connection = db.get(RepositoryConnection, snap.repository_connection_id)
        project = db.get(Project, connection.project_id)
        provider: GitProvider = connector
        deadline = time.monotonic() + _limits.repository_max_duration_seconds
        _set_stage(db, snap, Status.VALIDATING)
        raw = provider.get_repository(connection.owner, connection.repository_name)
        if raw.get("private"):
            raise ValueError("Repository became private and cannot be analysed.")
        _set_stage(db, snap, Status.FETCHING_METADATA)
        meta = github_metadata(raw, provider.get_languages(connection.owner, connection.repository_name))
        for attr, field in (("description", "description"), ("language", "language"), ("stars", "stars"), ("forks", "forks"), ("open_issues", "open_issues"), ("license_name", "license"), ("repository_created_at", "created_at"), ("repository_updated_at", "updated_at"), ("repository_pushed_at", "pushed_at")):
            setattr(connection, attr, meta[field])
        connection.languages = meta["languages"]
        connection.external_id = str(raw["id"])
        _set_stage(db, snap, Status.FETCHING_BRANCHES)
        connection.branches = [{"name": b["name"], "commit_sha": b["commit"]["sha"], "protected": bool(b.get("protected")), "is_default": b["name"] == connection.default_branch} for b in provider.list_branches(connection.owner, connection.repository_name)]
        branch = next((b for b in connection.branches if b["name"] == snap.branch), None)
        if branch is None:
            raise ValueError("Selected branch is no longer available.")
        sha = branch["commit_sha"]
        if time.monotonic() >= deadline:
            raise TimeoutError("Repository analysis reached its configured processing time limit.")
        _set_stage(db, snap, Status.FETCHING_TREE)
        if time.monotonic() >= deadline:
            raise TimeoutError("Repository analysis reached its configured processing time limit.")
        tree = provider.get_repository_tree(connection.owner, connection.repository_name, sha)
        entries = tree.get("tree", [])
        tree_complete = not bool(tree.get("truncated"))
        warnings = []
        if not tree_complete:
            warnings.append("GitHub marked the recursive tree as truncated; snapshot file inventory is partial.")
            # Bounded depth-first fallback on directories; preserves explicit partial warning on limits.
            pending = [(item["path"], 1) for item in entries if item.get("type") == "tree"]
            seen = {item.get("path") for item in entries}
            fallback_request_budget = min(40, _limits.repository_max_api_requests // 4)
            while pending and len(entries) < MAX_TREE_ENTRIES and provider.request_count < fallback_request_budget:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Repository analysis reached its configured processing time limit.")
                path, depth = pending.pop(0)
                if depth > MAX_DEPTH:
                    continue
                listing = provider.list_directory(connection.owner, connection.repository_name, path, snap.branch)
                if not isinstance(listing, list):
                    continue
                for item in listing:
                    if item.get("path") not in seen:
                        entries.append({"path": item.get("path"), "type": "tree" if item.get("type") == "dir" else "blob", "sha": item.get("sha"), "size": item.get("size", 0), "url": item.get("url")})
                        seen.add(item.get("path"))
                        if item.get("type") == "dir": pending.append((item["path"], depth + 1))
            if pending:
                warnings.append("Tree traversal reached the bounded traversal depth/request limit.")
        snap.commit_sha, snap.tree_complete = sha, tree_complete
        blobs = [entry for entry in entries if entry.get("type") == "blob" and entry.get("path")]
        snap.files_discovered = len(blobs)
        if len(blobs) > MAX_TREE_ENTRIES:
            snap.tree_complete = False
            warnings.append(f"Tree metadata persistence capped at {MAX_TREE_ENTRIES} file entries; {len(blobs) - MAX_TREE_ENTRIES} entries were not stored.")
        _set_stage(db, snap, Status.FETCHING_FILES)
        budget, considered = MAX_TOTAL_BYTES, 0
        for entry in blobs[:MAX_TREE_ENTRIES]:
            if time.monotonic() >= deadline:
                warnings.append("Repository analysis reached its configured processing time limit.")
                break
            path = entry["path"]
            p = PurePosixPath(path)
            fname, extension = p.name, p.suffix.lower()
            if len(path) > 1000 or len(fname) > 255:
                snap.files_skipped += 1
                warnings.append("A repository path exceeded the supported metadata path length and was skipped.")
                continue
            file_size = int(entry.get("size") or 0)
            row = RepositoryFile(snapshot_id=snap.id, path=path, file_name=fname, directory_path=str(p.parent) if str(p.parent) != "." else "", extension=extension, size=file_size, blob_sha=entry.get("sha"), analysis_status=ProcessingStatus.PENDING)
            reason = file_skip_reason(path, file_size, considered, budget)
            if reason:
                row.analysis_status, row.skip_reason = ProcessingStatus.SKIPPED, reason
            else:
                try:
                    content = provider.get_file_content(connection.owner, connection.repository_name, entry["sha"], MAX_FILE_BYTES)
                    if "\x00" in content:
                        raise ValueError("Binary content is not analysed")
                    content = content[: MAX_FILE_BYTES].replace("\r\n", "\n")
                    path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]
                    src = _upsert_source(db, project, SourceType.GITHUB_FILE, path, content, f"repo:{connection.owner}/{connection.repository_name}:{path_id}", None, None, f"https://github.com/{connection.owner}/{connection.repository_name}/blob/{quote(path, safe='/')}", {"repository": connection.repository_url, "file_path": path, "branch": snap.branch, "snapshot_id": str(snap.id), "blob_sha": entry.get("sha")})
                    row.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if src and src.processing_status in {ProcessingStatus.COMPLETED, ProcessingStatus.DUPLICATE}:
                        row.source_id = src.id
                        row.content_storage_reference = f"source:{src.id}"
                        row.analysis_status = ProcessingStatus.COMPLETED
                        budget -= len(content.encode("utf-8"))
                        snap.files_processed += 1
                    else:
                        row.analysis_status, row.skip_reason = ProcessingStatus.FAILED, "Source content was not accepted by Continuum's ingestion scanner."
                        snap.files_skipped += 1
                except (UnicodeDecodeError, ValueError, OverflowError) as exc:
                    row.analysis_status, row.skip_reason = ProcessingStatus.SKIPPED, str(exc)[:300]
            if row.analysis_status == ProcessingStatus.SKIPPED:
                snap.files_skipped += 1
            db.add(row)
            considered += 1
            if considered % 25 == 0:
                db.commit()
        if len(blobs) > MAX_FILES:
            warnings.append(f"File content ingestion capped at {MAX_FILES}; remaining file metadata was retained as skipped rows.")
        db.commit()
        _set_stage(db, snap, Status.FETCHING_COMMITS)
        commits = provider.list_commits(connection.owner, connection.repository_name, snap.branch, MAX_COMMITS)
        for commit in commits:
            if time.monotonic() >= deadline:
                raise TimeoutError("Repository analysis reached its configured processing time limit.")
            sha_value = commit["sha"]
            detail = provider.get_commit_details(connection.owner, connection.repository_name, sha_value)
            inner, author_obj, committer_obj = detail.get("commit", {}), detail.get("commit", {}).get("author") or {}, detail.get("commit", {}).get("committer") or {}
            gh_author = detail.get("author") or {}
            files = detail.get("files") or []
            record = db.scalar(select(CommitRecord).where(CommitRecord.repository_connection_id == connection.id, CommitRecord.commit_sha == sha_value))
            if record is None:
                record = CommitRecord(repository_connection_id=connection.id, commit_sha=sha_value)
            record.snapshot_id = snap.id
            record.parent_shas = [p.get("sha") for p in detail.get("parents", [])]
            record.author_name, record.author_email = author_obj.get("name"), author_obj.get("email")
            record.github_author = gh_author.get("login")
            record.committer_name, record.committer_email = committer_obj.get("name"), committer_obj.get("email")
            record.committer_at = _dt(committer_obj.get("date"))
            record.message, record.committed_at, record.url = (inner.get("message") or "")[:100_000], _dt(author_obj.get("date")), detail.get("html_url")
            record.changed_files = [f.get("filename") for f in files if f.get("filename")]
            record.additions, record.deletions = detail.get("stats", {}).get("additions"), detail.get("stats", {}).get("deletions")
            record.total_changes = detail.get("stats", {}).get("total")
            for changed_file in files:
                filename = changed_file.get("filename")
                if not filename:
                    continue
                file_change = db.scalar(select(CommitFileChange).where(
                    CommitFileChange.snapshot_id == snap.id,
                    CommitFileChange.commit_sha == sha_value,
                    CommitFileChange.file_path == filename,
                )) or CommitFileChange(snapshot_id=snap.id, commit_sha=sha_value, file_path=filename)
                file_change.status = (changed_file.get("status") or "unknown")[:24]
                file_change.previous_filename = changed_file.get("previous_filename")
                file_change.additions = changed_file.get("additions")
                file_change.deletions = changed_file.get("deletions")
                file_change.changes = changed_file.get("changes")
                file_change.statistics_available = all(changed_file.get(key) is not None for key in ("additions", "deletions", "changes"))
                file_change.patch_available = isinstance(changed_file.get("patch"), str)
                db.add(file_change)
            if record.source_id is None:
                src = _upsert_source(db, project, SourceType.GITHUB_COMMIT, (record.message or f"Commit {sha_value[:7]}").splitlines()[0][:500], f"Commit {sha_value}\nAuthor: {record.author_name or 'unknown'}\nCommitter: {record.committer_name or 'unknown'}\n\n{record.message or ''}\n\nChanged files:\n" + "\n".join(record.changed_files[:100]), sha_value, record.author_name, record.committed_at, record.url, {"repository": connection.repository_url, "commit_sha": sha_value, "snapshot_id": str(snap.id)})
                record.source_id = src.id if src else None
            db.add(record)
            snap.commits_processed += 1
        db.commit()
        _set_stage(db, snap, Status.FETCHING_ISSUES)
        for item in provider.list_issues(connection.owner, connection.repository_name, MAX_ISSUES):
            if time.monotonic() >= deadline:
                raise TimeoutError("Repository analysis reached its configured processing time limit.")
            if "pull_request" in item:
                continue
            number = int(item["number"])
            record = db.scalar(select(IssueRecord).where(IssueRecord.repository_connection_id == connection.id, IssueRecord.issue_number == number)) or IssueRecord(repository_connection_id=connection.id, issue_number=number, title=item.get("title") or "(untitled)")
            record.snapshot_id, record.title, record.description = snap.id, (item.get("title") or "(untitled)")[:500], (item.get("body") or "")[:100_000]
            record.state, record.labels = item.get("state", "unknown"), [l.get("name") for l in item.get("labels", [])]
            record.assignees, record.author = [a.get("login") for a in item.get("assignees", [])], (item.get("user") or {}).get("login")
            record.created_at_source, record.updated_at_source, record.closed_at, record.url = _dt(item.get("created_at")), _dt(item.get("updated_at")), _dt(item.get("closed_at")), item.get("html_url")
            src = _upsert_source(db, project, SourceType.GITHUB_ISSUE, f"#{number} {record.title}"[:500], f"Issue #{number}: {record.title}\nState: {record.state}\nLabels: {', '.join(record.labels)}\n\n{record.description or '(no description)'}", f"issue#{number}", record.author, record.created_at_source, record.url, {"repository": connection.repository_url, "issue_number": number, "snapshot_id": str(snap.id)})
            record.source_id = src.id if src else record.source_id
            db.add(record)
            snap.issues_processed += 1
        db.commit()
        _set_stage(db, snap, Status.FETCHING_PULL_REQUESTS)
        for item in provider.list_pull_requests(connection.owner, connection.repository_name, MAX_PRS):
            if time.monotonic() >= deadline:
                raise TimeoutError("Repository analysis reached its configured processing time limit.")
            number = int(item["number"])
            record = db.scalar(select(PullRequestRecord).where(PullRequestRecord.repository_connection_id == connection.id, PullRequestRecord.pr_number == number)) or PullRequestRecord(repository_connection_id=connection.id, pr_number=number, title=item.get("title") or "(untitled)")
            record.snapshot_id, record.title, record.description = snap.id, (item.get("title") or "(untitled)")[:500], (item.get("body") or "")[:100_000]
            record.state, record.author = item.get("state", "unknown"), (item.get("user") or {}).get("login")
            record.base_branch, record.head_branch = (item.get("base") or {}).get("ref"), (item.get("head") or {}).get("ref")
            record.merged_at, record.closed_at, record.created_at_source, record.updated_at_source, record.url = _dt(item.get("merged_at")), _dt(item.get("closed_at")), _dt(item.get("created_at")), _dt(item.get("updated_at")), item.get("html_url")
            try:
                changed_files = provider.list_pull_request_files(connection.owner, connection.repository_name, number)
                record.changed_files = [f.get("filename") for f in changed_files if f.get("filename")]
                record.changed_file_count = len(changed_files)
                record.additions = sum(f.get("additions", 0) for f in changed_files) if all(f.get("additions") is not None for f in changed_files) else None
                record.deletions = sum(f.get("deletions", 0) for f in changed_files) if all(f.get("deletions") is not None for f in changed_files) else None
                review_data = provider.list_pull_request_reviews(connection.owner, connection.repository_name, number)
                record.reviews = [{"state": review.get("state"), "submitted_at": review.get("submitted_at"), "author": (review.get("user") or {}).get("login")} for review in review_data]
                record.reviews_available = True
            except GitHubApiError as exc:
                record.changed_files, record.reviews, record.reviews_available = [], [], False
                record.changed_file_count, record.additions, record.deletions = None, None, None
                warnings.append(f"PR #{number} changed-file or review details unavailable (GitHub HTTP {exc.status}).")
            src = _upsert_source(db, project, SourceType.GITHUB_PULL_REQUEST, f"PR #{number} {record.title}"[:500], f"Pull request #{number}: {record.title}\nState: {record.state}\nBase: {record.base_branch}\nHead: {record.head_branch}\n\n{record.description or '(no description)'}\n\nChanged files:\n" + "\n".join(record.changed_files[:100]) + "\n\nReviews:\n" + "\n".join(f"{r.get('author') or 'unknown'}: {r.get('state') or 'unknown'}" for r in record.reviews[:100]), f"pr#{number}", record.author, record.created_at_source, record.url, {"repository": connection.repository_url, "pull_request_number": number, "snapshot_id": str(snap.id), "changed_files_available": bool(record.changed_files), "reviews_available": record.reviews_available})
            record.source_id = src.id if src else record.source_id
            db.add(record)
            snap.pull_requests_processed += 1
        db.commit()
        _set_stage(db, snap, Status.SAVING_SNAPSHOT)
        snap.warnings = warnings
        snap.ingestion_status = Status.PARTIALLY_COMPLETED if warnings or snap.files_skipped else Status.COMPLETED
        snap.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        snap = db.get(RepositorySnapshot, snapshot_id)
        if snap:
            has_results = bool(snap.files_processed or snap.commits_processed or snap.issues_processed or snap.pull_requests_processed)
            snap.ingestion_status = Status.PARTIALLY_COMPLETED if has_results else Status.FAILED
            snap.error_summary = str(exc)[:500] if isinstance(exc, (ValueError, GitHubApiError)) else "Repository analysis failed. Retry the analysis later."
            if has_results:
                snap.warnings = [*(snap.warnings or []), "Analysis stopped after a partial result was saved."]
            snap.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.warning("Repository snapshot failed id=%s error=%s", snapshot_id, type(exc).__name__)
    finally:
        connector.close()
        db.close()


def connection_payload(db: Session, connection: RepositoryConnection):
    latest = db.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_connection_id == connection.id).order_by(RepositorySnapshot.created_at.desc()).limit(1))
    return {"id": connection.id, "project_id": connection.project_id, "provider": connection.provider, "owner": connection.owner, "repository_name": connection.repository_name, "repository_url": connection.repository_url, "default_branch": connection.default_branch, "selected_branch": connection.selected_branch, "visibility": connection.visibility.value, "description": connection.description, "language": connection.language, "languages": connection.languages or {}, "stars": connection.stars, "forks": connection.forks, "open_issues": connection.open_issues, "license_name": connection.license_name, "repository_created_at": connection.repository_created_at, "repository_updated_at": connection.repository_updated_at, "repository_pushed_at": connection.repository_pushed_at, "branches": connection.branches or [], "latest_snapshot": snapshot_payload(latest) if latest else None}


def snapshot_payload(snap: RepositorySnapshot):
    return {"id": snap.id, "repository_id": snap.repository_connection_id, "branch": snap.branch, "commit_sha": snap.commit_sha, "status": snap.ingestion_status.value, "stage": snap.ingestion_status.value, "tree_complete": snap.tree_complete, "files_discovered": snap.files_discovered, "files_processed": snap.files_processed, "files_skipped": snap.files_skipped, "commits_processed": snap.commits_processed, "issues_processed": snap.issues_processed, "pull_requests_processed": snap.pull_requests_processed, "warnings": snap.warnings or [], "error_summary": snap.error_summary, "started_at": snap.started_at, "completed_at": snap.completed_at}


def paged_records(db: Session, model, repository_id: uuid.UUID, page: int, page_size: int):
    stmt = select(model).where(model.repository_connection_id == repository_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(model.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = [column.key for column in model.__table__.columns]
    items = [{name: getattr(row, name) for name in names} for row in rows]
    if model is CommitRecord:
        for item in items:
            item["author_email"] = None
            item["committer_email"] = None
    return {"items": items, "page": page, "page_size": page_size, "total": total}
