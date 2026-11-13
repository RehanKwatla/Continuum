"""Stage 3 — Codebase Intelligence persistence.

These tables store the structured output of static-analysis passes over an
ingested repository snapshot.  Each :class:`CodeAnalysisRun` is anchored to a
:class:`~app.models.repository_intelligence.RepositorySnapshot` and contains
language statistics, technology detections, code symbols, module and external
dependencies, architecture components, and entry points.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CodeAnalysisStatus
from app.models.types import (
    CreatedAt,
    JsonArray,
    JsonObject,
    UpdatedAt,
    UuidFK,
    UuidPK,
    sa_enum,
)


# ---------------------------------------------------------------------------
# CodeAnalysisRun
# ---------------------------------------------------------------------------
class CodeAnalysisRun(Base):
    """One analysis pass over a repository snapshot."""

    __tablename__ = "code_analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "parser_version",
            name="uq_code_analysis_runs_snapshot_parser",
        ),
    )

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[CodeAnalysisStatus] = mapped_column(
        sa_enum(CodeAnalysisStatus, "code_analysis_status", length=24),
        nullable=False,
        default=CodeAnalysisStatus.PENDING,
        server_default=CodeAnalysisStatus.PENDING.value,
    )
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    languages_summary: Mapped[JsonObject]
    technologies_summary: Mapped[JsonArray]
    entry_points_summary: Mapped[JsonArray]
    architecture_summary: Mapped[JsonObject]
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # --- relationships -------------------------------------------------------
    language_statistics: Mapped[list["LanguageStatistic"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    technology_detections: Mapped[list["TechnologyDetection"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    code_symbols: Mapped[list["CodeSymbol"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    module_dependencies: Mapped[list["ModuleDependency"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    external_dependencies: Mapped[list["ExternalDependency"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    architecture_components: Mapped[list["ArchitectureComponent"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    entry_points: Mapped[list["EntryPoint"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CodeAnalysisRun {self.id} {self.status}>"


# ---------------------------------------------------------------------------
# LanguageStatistic
# ---------------------------------------------------------------------------
class LanguageStatistic(Base):
    """Per-language byte/file breakdown for one analysis run."""

    __tablename__ = "language_statistics"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "language",
            "detection_source",
            name="uq_language_statistics_run_lang_source",
        ),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    detection_source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="language_statistics"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LanguageStatistic {self.language} ({self.detection_source})>"


# ---------------------------------------------------------------------------
# TechnologyDetection
# ---------------------------------------------------------------------------
class TechnologyDetection(Base):
    """A framework / tool / library detected in the codebase."""

    __tablename__ = "technology_detections"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "technology",
            name="uq_technology_detections_run_tech",
        ),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    technology: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_paths: Mapped[JsonArray]
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="technology_detections"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TechnologyDetection {self.technology} ({self.confidence})>"


# ---------------------------------------------------------------------------
# CodeSymbol
# ---------------------------------------------------------------------------
class CodeSymbol(Base):
    """A named symbol (function, class, route, …) extracted from source."""

    __tablename__ = "code_symbols"
    __table_args__ = (
        Index("ix_code_symbols_run_file", "analysis_run_id", "file_path"),
        Index("ix_code_symbols_run_type", "analysis_run_id", "symbol_type"),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    symbol_name: Mapped[str] = mapped_column(String(500), nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parameters: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extras: Mapped[JsonObject]
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="code_symbols"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CodeSymbol {self.symbol_type} {self.symbol_name}>"


# ---------------------------------------------------------------------------
# ModuleDependency
# ---------------------------------------------------------------------------
class ModuleDependency(Base):
    """An import / re-export / inheritance edge between two modules."""

    __tablename__ = "module_dependencies"
    __table_args__ = (
        Index("ix_module_dependencies_run_source", "analysis_run_id", "source_module"),
        Index("ix_module_dependencies_run_target", "analysis_run_id", "target_module"),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    source_module: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_module: Mapped[str] = mapped_column(String(1000), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_file: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_file: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_symbols: Mapped[JsonArray]
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="module_dependencies"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModuleDependency {self.source_module} → {self.target_module}>"


# ---------------------------------------------------------------------------
# ExternalDependency
# ---------------------------------------------------------------------------
class ExternalDependency(Base):
    """A third-party package declared in a manifest file."""

    __tablename__ = "external_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "package_name",
            "manifest_path",
            name="uq_external_dependencies_run_pkg_manifest",
        ),
    )

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    package_name: Mapped[str] = mapped_column(String(256), nullable=False)
    declared_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dep_category: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="external_dependencies"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExternalDependency {self.package_name} ({self.ecosystem})>"


# ---------------------------------------------------------------------------
# ArchitectureComponent
# ---------------------------------------------------------------------------
class ArchitectureComponent(Base):
    """A high-level architectural component inferred from the codebase."""

    __tablename__ = "architecture_components"

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    component_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    file_paths: Mapped[JsonArray]
    connected_components: Mapped[JsonArray]
    evidence: Mapped[JsonArray]
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    inference_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="architecture_components"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ArchitectureComponent {self.component_name} ({self.category})>"


# ---------------------------------------------------------------------------
# EntryPoint
# ---------------------------------------------------------------------------
class EntryPoint(Base):
    """A detected application entry point (main, server bootstrap, …)."""

    __tablename__ = "entry_points"

    id: Mapped[UuidPK]
    analysis_run_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("code_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    runtime_or_framework: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[JsonArray]
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[CreatedAt]

    analysis_run: Mapped[CodeAnalysisRun] = relationship(
        back_populates="entry_points"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EntryPoint {self.file_path}>"
