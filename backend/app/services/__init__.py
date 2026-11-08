"""Service layer: business logic, authorisation-aware and framework-agnostic."""

from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.github_service import GitHubClient, GitHubOAuth, GitHubService, TokenCipher
from app.services.ingestion_service import IngestionService
from app.services.normalizer import NormalizedSource, build_normalized_source
from app.services.project_service import ProjectService
from app.services.security_scanner import ScanResult, SecretFinding, scan_bytes, scan_text
from app.services.workspace_service import WorkspaceService

__all__ = [
    "AuthService",
    "GitHubClient",
    "GitHubOAuth",
    "GitHubService",
    "IngestionService",
    "NormalizedSource",
    "ProjectService",
    "ScanResult",
    "SecretFinding",
    "TokenCipher",
    "WorkspaceService",
    "audit_service",
    "build_normalized_source",
    "scan_bytes",
    "scan_text",
]
