"""Shared pytest fixtures.

Environment variables are set **before** any application module is imported so
the settings singleton picks up the test configuration:

* the dedicated ``continuum_test`` PostgreSQL database;
* the development-only auth bypass (a static token), which is what lets the
  suite exercise authenticated endpoints locally.

The suite refuses to fall back to fake data: it talks to a real PostgreSQL
database with the real pgvector/uuid extensions.
"""

from __future__ import annotations

import io
import os
import tempfile
import uuid
import zipfile
from collections.abc import Iterator

# --------------------------------------------------------------------------
# Environment must be configured before importing the application.
# --------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://continuum:continuum@localhost:5433/continuum_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "development"
os.environ["ALLOW_DEV_AUTH"] = "true"
os.environ["DEV_AUTH_TOKEN"] = "test-dev-token"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="continuum-test-uploads-")
os.environ["MAX_UPLOAD_SIZE_BYTES"] = str(2 * 1024 * 1024)
os.environ["MAX_ZIP_EXPANSION_BYTES"] = str(8 * 1024 * 1024)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: F401,E402  (registers every table)
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workspace import Workspace, WorkspaceMember  # noqa: E402
from app.models.enums import WorkspaceRole  # noqa: E402

DEV_TOKEN = "test-dev-token"
AUTH_HEADERS = {"Authorization": f"Bearer {DEV_TOKEN}"}


# --------------------------------------------------------------------------
# Schema lifecycle
# --------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_schema: None) -> Iterator[None]:
    """Truncate every table so each test starts from a known state."""
    engine = get_engine()
    names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with engine.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE {names} CASCADE")
    yield


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return dict(AUTH_HEADERS)


@pytest.fixture
def db_session() -> Iterator:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------
# Domain fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def workspace(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/workspaces", json={"name": "Continuum Test Workspace"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def project(client: TestClient, workspace: dict) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": workspace["id"], "name": "Handover Project"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def foreign_workspace(db_session) -> dict:
    """A workspace owned by a *different* user, used to prove isolation."""
    other = User(email="intruder@example.com", full_name="Intruder", supabase_user_id=None)
    db_session.add(other)
    db_session.flush()

    other_workspace = Workspace(name="Someone Else's Workspace", owner_id=other.id)
    db_session.add(other_workspace)
    db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=other_workspace.id, user_id=other.id, role=WorkspaceRole.OWNER
        )
    )
    db_session.commit()
    return {"id": str(other_workspace.id), "name": other_workspace.name, "owner_id": str(other.id)}


# --------------------------------------------------------------------------
# Synthetic artefacts
# --------------------------------------------------------------------------
@pytest.fixture
def synthetic_pdf() -> bytes:
    """A real, two-page PDF generated with PyMuPDF."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Continuum handover note: the billing service owns invoices.")
    second = document.new_page()
    second.insert_text((72, 72), "Second page: rotate the signing key every 90 days.")
    payload = document.tobytes()
    document.close()
    return payload


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


@pytest.fixture
def zip_builder():
    return make_zip


def unique_text(prefix: str = "note") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"
