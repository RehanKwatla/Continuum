"""Ingestion service: validate → store → scan → parse → normalise → persist.

Security posture:
  * uploaded bytes are stored, never executed;
  * file types are validated by *content*, not only by extension;
  * archives are inspected with zip-slip, entry-count, per-entry and total
    expansion limits; nested archives are never opened;
  * sensitive files are refused and secrets are redacted before persistence.
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import Sequence
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AccessLabel, ProcessingStatus, SourceType
from app.models.project import Project
from app.models.source import Source
from app.schemas.source import IngestionResult, UploadResponse
from app.services.file_parser import (
    ParsedDocument,
    ParsedSegment,
    ParseError,
    decode_text_bytes,
    parse_markdown,
    parse_pdf,
    parse_text,
)
from app.services.normalizer import NormalizedSource, build_normalized_source
from app.services.security_scanner import ScanResult, scan_text
from app.utils.files import (
    ALLOWED_ARCHIVE_EXTENSIONS,
    ALLOWED_UPLOAD_EXTENSIONS,
    DENIED_EXTENSIONS,
    detect_actual_format,
    extension_of,
    is_denied_filename,
    is_denied_path,
    normalize_archive_path,
    read_limited,
    safe_storage_key,
    sanitize_filename,
)
from app.utils.hashing import compute_content_hash  # noqa: F401  (re-exported for tests)

logger = logging.getLogger("continuum.ingestion")

_EXTENSION_TO_FORMAT = {".pdf": "pdf", ".zip": "zip", ".md": "markdown", ".markdown": "markdown"}
_MAX_COMPRESSION_RATIO = 1000


class IngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def ingest_uploads(
        self, project: Project, uploads: Sequence[UploadFile]
    ) -> UploadResponse:
        results: list[IngestionResult] = []
        for upload in uploads:
            results.extend(self._handle_upload(project, upload))

        return UploadResponse(
            results=results,
            accepted=sum(1 for r in results if r.status is ProcessingStatus.COMPLETED),
            duplicates=sum(1 for r in results if r.status is ProcessingStatus.DUPLICATE),
            failed=sum(
                1 for r in results if r.status in {ProcessingStatus.FAILED, ProcessingStatus.SKIPPED}
            ),
        )

    def ingest_text_artifact(
        self,
        project: Project,
        *,
        source_type: SourceType,
        source_name: str,
        content: str,
        external_id: str | None = None,
        author: str | None = None,
        created_at_source=None,
        metadata: dict | None = None,
        access_label: AccessLabel = AccessLabel.WORKSPACE,
        source_url: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
    ) -> IngestionResult:
        """Persist a non-upload artefact (used by the GitHub connector)."""
        scan = scan_text(content)
        warnings = list(scan.warnings)
        meta = dict(metadata or {})
        meta["security_scan"] = scan.summary
        meta["character_count"] = len(scan.redacted_content)

        normalized = build_normalized_source(
            source_type=source_type,
            source_name=source_name,
            content=scan.redacted_content,
            external_id=external_id,
            author=author,
            created_at_source=created_at_source,
            metadata=meta,
            access_label=access_label,
            warnings=warnings,
            source_url=source_url,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        return self._persist(project, normalized, display_name=source_name)

    # ------------------------------------------------------------------
    # Upload handling
    # ------------------------------------------------------------------
    def _handle_upload(self, project: Project, upload: UploadFile) -> list[IngestionResult]:
        display_name = sanitize_filename(upload.filename or "unnamed")
        extension = extension_of(display_name)

        if is_denied_filename(display_name):
            return [
                self._failure(
                    display_name,
                    "This file name is on the sensitive-file deny list and was not ingested.",
                )
            ]
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            return [
                self._failure(
                    display_name,
                    f"Unsupported file type '{extension or 'unknown'}'. Allowed types: {allowed}.",
                )
            ]

        payload = read_limited(upload.file, settings.max_upload_size_bytes)
        if len(payload) > settings.max_upload_size_bytes:
            return [
                self._failure(
                    display_name,
                    f"File exceeds the {settings.max_upload_size_bytes} byte upload limit.",
                )
            ]
        if not payload:
            return [self._failure(display_name, "File is empty.")]

        actual = detect_actual_format(payload[:8192], display_name)
        if actual == "unknown":
            return [
                self._failure(
                    display_name,
                    "Content type could not be determined; the file is not a supported "
                    "PDF, ZIP, Markdown or text document.",
                )
            ]
        expected = _EXTENSION_TO_FORMAT.get(extension)
        if expected and expected != actual:
            text_like = {expected, actual} <= {"markdown", "text"}
            if not text_like:
                return [
                    self._failure(
                        display_name,
                        f"Declared type '{extension}' does not match detected content type "
                        f"'{actual}'. File was rejected.",
                    )
                ]

        if actual == "zip":
            return self._ingest_archive(project, display_name, payload)
        return [self._ingest_document(project, display_name, payload, actual)]

    def _ingest_document(
        self,
        project: Project,
        filename: str,
        payload: bytes,
        actual_format: str,
        *,
        source_type: SourceType | None = None,
        external_id: str | None = None,
        member_path: str | None = None,
        storage_key: str | None = None,
    ) -> IngestionResult:
        try:
            parsed = self._parse(payload, filename, actual_format)
        except ParseError as exc:
            return self._failure(filename, f"Parsing failed: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Parser error for %s: %s", filename, type(exc).__name__)
            return self._failure(filename, f"Parsing failed unexpectedly ({type(exc).__name__}).")

        redacted_doc, scan = self._redact(parsed)
        warnings = list(redacted_doc.warnings) + scan.warnings

        metadata = dict(redacted_doc.metadata)
        metadata["security_scan"] = scan.summary
        metadata["character_count"] = len(redacted_doc.text)
        metadata["segment_count"] = len(redacted_doc.segments)
        if member_path:
            metadata["archive_entry"] = member_path
        if scan.has_secrets:
            metadata["redacted"] = True

        resolved_type = source_type or _FORMAT_TO_SOURCE_TYPE[actual_format]
        resolved_external_id = external_id or (member_path if member_path else None)

        normalized = build_normalized_source(
            source_type=resolved_type,
            source_name=filename,
            content=redacted_doc.text,
            external_id=resolved_external_id,
            author=None,
            metadata=metadata,
            access_label=AccessLabel.WORKSPACE,
            warnings=warnings,
            storage_key=storage_key,
            mime_type=_MIME_TYPES.get(actual_format),
            size_bytes=len(payload),
        )
        return self._persist(project, normalized, display_name=filename)

    # ------------------------------------------------------------------
    # Archives
    # ------------------------------------------------------------------
    def _ingest_archive(
        self, project: Project, archive_name: str, payload: bytes
    ) -> list[IngestionResult]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile:
            return [self._failure(archive_name, "Not a valid ZIP archive.")]

        with archive:
            infos = archive.infolist()
            if len(infos) > settings.max_zip_entries:
                return [
                    self._failure(
                        archive_name,
                        f"Archive contains {len(infos)} entries which exceeds the "
                        f"{settings.max_zip_entries} entry limit.",
                    )
                ]

            archive_storage_key = self._store_bytes(project, archive_name, payload)
            results: list[IngestionResult] = []
            total_expanded = 0

            for info in infos:
                member = self._inspect_member(info)
                if isinstance(member, IngestionResult):
                    results.append(member)
                    continue

                member_path = member
                if info.file_size > settings.max_zip_entry_bytes:
                    results.append(
                        self._skip(
                            member_path,
                            f"Archive entry exceeds the {settings.max_zip_entry_bytes} byte limit.",
                        )
                    )
                    continue

                total_expanded += info.file_size
                if total_expanded > settings.max_zip_expansion_bytes:
                    results.append(
                        self._failure(
                            archive_name,
                            "Archive expansion exceeded the configured limit; processing stopped.",
                        )
                    )
                    return results

                if (
                    info.compress_size
                    and info.file_size / max(info.compress_size, 1) > _MAX_COMPRESSION_RATIO
                ):
                    results.append(
                        self._skip(
                            member_path, "Archive entry has a suspicious compression ratio."
                        )
                    )
                    continue

                try:
                    with archive.open(info) as handle:
                        entry_payload = read_limited(handle, settings.max_zip_entry_bytes)
                except (RuntimeError, zipfile.BadZipFile):
                    results.append(self._failure(member_path, "Archive entry could not be read."))
                    continue

                actual = detect_actual_format(entry_payload[:8192], member_path)
                if actual == "zip":
                    results.append(
                        self._skip(
                            member_path,
                            "Nested archives are not processed (nesting depth limit is 1).",
                        )
                    )
                    continue
                if actual == "unknown":
                    results.append(
                        self._skip(member_path, "Archive entry content type could not be determined.")
                    )
                    continue

                result = self._ingest_document(
                    project,
                    member_path.rsplit("/", 1)[-1],
                    entry_payload,
                    actual,
                    source_type=SourceType.UPLOADED_ZIP_ENTRY,
                    external_id=f"{archive_name}!{member_path}",
                    member_path=member_path,
                    storage_key=archive_storage_key,
                )
                if result.source_id is not None:
                    source = self.db.get(Source, result.source_id)
                    if source is not None:
                        source.meta = {
                            **(source.meta or {}),
                            "archive_name": archive_name,
                            "archive_entry": member_path,
                            "archive_storage_key": archive_storage_key,
                        }
                results.append(result)

            return results

    def _inspect_member(self, info: zipfile.ZipInfo) -> str | IngestionResult:
        """Return a safe member path, or a skip/failure result explaining why not."""
        raw = info.filename
        if raw.endswith("/") or raw.endswith("\\"):
            return self._skip(raw, "Directory entry skipped.")

        safe = normalize_archive_path(raw)
        if safe is None:
            return self._failure(
                raw, "Unsafe archive path rejected (path traversal / absolute path)."
            )
        if is_denied_path(safe):
            return self._skip(safe, "Path is on the deny list (.git, node_modules, ...).")

        basename = safe.rsplit("/", 1)[-1]
        if is_denied_filename(basename):
            return self._skip(safe, "Sensitive file name; archive entry was not ingested.")

        extension = extension_of(safe)
        if extension in DENIED_EXTENSIONS:
            reason = (
                "Nested archives are not processed."
                if extension in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
                else "File type is on the deny list."
            )
            return self._skip(safe, reason)
        if extension not in ALLOWED_ARCHIVE_EXTENSIONS:
            return self._skip(
                safe, f"File type '{extension or 'unknown'}' is not permitted inside archives."
            )
        return safe

    # ------------------------------------------------------------------
    # Parsing & redaction
    # ------------------------------------------------------------------
    def _parse(self, payload: bytes, filename: str, actual_format: str) -> ParsedDocument:
        limit = settings.max_content_chars
        if actual_format == "pdf":
            return parse_pdf(payload, filename, limit=limit)
        text = decode_text_bytes(payload)
        if actual_format == "markdown":
            return parse_markdown(text, filename, limit=limit)
        return parse_text(text, filename, limit=limit)

    def _redact(self, parsed: ParsedDocument) -> tuple[ParsedDocument, ScanResult]:
        """Redact secrets segment-by-segment, preserving exact offsets."""
        if not parsed.segments:
            scan = scan_text(parsed.text)
            if not scan.has_secrets:
                return parsed, scan
            metadata = dict(parsed.metadata)
            metadata["parse_warnings"] = list(parsed.metadata.get("parse_warnings") or [])
            return ParsedDocument(scan.redacted_content, [], metadata), scan

        overall = ScanResult(redacted_content="")
        pieces: list[str] = []
        new_segments: list[ParsedSegment] = []
        original = parsed.text
        cursor = 0
        offset = 0

        for segment in parsed.segments:
            gap = original[cursor : segment.start_offset]
            pieces.append(gap)
            offset += len(gap)

            segment_scan = scan_text(segment.text)
            overall.findings.extend(segment_scan.findings)
            overall.mentions_sensitive_keyword |= segment_scan.mentions_sensitive_keyword
            redacted_text = segment_scan.redacted_content

            new_segments.append(
                ParsedSegment(
                    location=segment.location,
                    text=redacted_text,
                    start_offset=offset,
                    end_offset=offset + len(redacted_text),
                    metadata=dict(segment.metadata),
                )
            )
            pieces.append(redacted_text)
            offset += len(redacted_text)
            cursor = segment.end_offset

        pieces.append(original[cursor:])
        overall.redacted_content = "".join(pieces)

        metadata = dict(parsed.metadata)
        metadata["parse_warnings"] = list(parsed.metadata.get("parse_warnings") or [])
        return (
            ParsedDocument(
                text=overall.redacted_content,
                segments=new_segments,
                metadata=metadata,
                page_count=parsed.page_count,
            ),
            overall,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist(
        self, project: Project, normalized: NormalizedSource, *, display_name: str
    ) -> IngestionResult:
        content_hash = normalized.content_hash

        existing = self.db.execute(
            select(Source.id).where(
                Source.project_id == project.id,
                Source.content_hash == content_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return IngestionResult(
                filename=display_name,
                source_id=existing,
                source_type=normalized.source_type,
                status=ProcessingStatus.DUPLICATE,
                message="Identical content already exists in this project.",
                warnings=list(normalized.warnings),
                duplicate_of=existing,
            )

        source = Source(
            project_id=project.id,
            source_type=normalized.source_type,
            source_name=normalized.source_name,
            external_id=normalized.external_id,
            content=normalized.content,
            meta=normalized.metadata,
            author=normalized.author,
            created_at_source=normalized.created_at_source,
            access_label=normalized.access_label,
            processing_status=ProcessingStatus.COMPLETED,
            content_hash=content_hash,
            storage_key=normalized.storage_key,
            mime_type=normalized.mime_type,
            size_bytes=normalized.size_bytes,
            source_url=normalized.source_url,
            warnings=normalized.warnings,
        )
        self.db.add(source)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = self.db.execute(
                select(Source.id).where(
                    Source.project_id == project.id,
                    Source.content_hash == content_hash,
                )
            ).scalar_one_or_none()
            return IngestionResult(
                filename=display_name,
                source_id=duplicate,
                source_type=normalized.source_type,
                status=ProcessingStatus.DUPLICATE,
                message="Identical content already exists in this project.",
                duplicate_of=duplicate,
            )

        self.db.refresh(source)
        return IngestionResult(
            filename=display_name,
            source_id=source.id,
            source_type=source.source_type,
            status=ProcessingStatus.COMPLETED,
            message=_completion_message(normalized),
            warnings=list(normalized.warnings),
        )

    def _store_bytes(self, project: Project, filename: str, payload: bytes) -> str | None:
        """Persist raw bytes under the project's storage directory."""
        storage_key = safe_storage_key(filename)
        root = Path(settings.upload_dir).resolve()
        target_dir = (root / str(project.id)).resolve()
        if not str(target_dir).startswith(str(root)):
            logger.error("Refusing to write outside the upload root.")
            return None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / storage_key).write_bytes(payload)
        except OSError:
            logger.warning("Could not persist upload for project %s", project.id)
            return None
        return storage_key

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _failure(filename: str, message: str) -> IngestionResult:
        return IngestionResult(filename=filename, status=ProcessingStatus.FAILED, message=message)

    @staticmethod
    def _skip(filename: str, message: str) -> IngestionResult:
        return IngestionResult(filename=filename, status=ProcessingStatus.SKIPPED, message=message)


_FORMAT_TO_SOURCE_TYPE: dict[str, SourceType] = {
    "pdf": SourceType.UPLOADED_PDF,
    "markdown": SourceType.UPLOADED_MARKDOWN,
    "text": SourceType.UPLOADED_TEXT,
}

_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "markdown": "text/markdown",
    "text": "text/plain",
    "zip": "application/zip",
}


def _completion_message(normalized: NormalizedSource) -> str:
    if normalized.warnings:
        return "Ingested with warnings."
    return "Ingested successfully."
