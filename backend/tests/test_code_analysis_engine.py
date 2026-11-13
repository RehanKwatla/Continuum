"""Synthetic source fixtures for the Stage 3 static analysis engine."""
from app.services.code_analysis.engine import analyze_files
from app.services.code_analysis.parser import parse_source
from app.services.code_analysis.service import _external_dependencies


def test_python_symbols_imports_routes_and_exact_lines():
    result = parse_source("app/main.py", "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'ok': True}\n")
    assert any(item["name"] == "health" and item["start"] == 4 for item in result["symbols"])
    assert result["imports"][0]["module"] == "fastapi"
    assert result["routes"] == [{"method": "GET", "route": "/health", "handler": "health", "line": 3}]


def test_structure_languages_and_manifest_evidence_are_from_available_files():
    files = [
        {"path": "src/main.py", "extension": ".py", "size": 80, "analysis_status": "completed"},
        {"path": "package.json", "extension": ".json", "size": 20, "analysis_status": "completed"},
        {"path": "README.md", "extension": ".md", "size": 30, "analysis_status": "skipped"},
    ]
    result = analyze_files(files, {"src/main.py": "def main():\n    pass\n", "package.json": '{"dependencies":{"react":"^18.2.0"}}'})
    assert any(node["path"] == "src" and node["node_type"] == "directory" for node in result["tree"])
    assert result["analysed_files"] == 2
    assert result["skipped_files"] == 1
    assert result["languages"]["extension"][0]["language"] == "Python"
    react = next(item for item in result["technologies"] if item["technology"] == "React")
    assert react["evidence_paths"] == ["package.json"]


def test_parse_errors_are_per_file_not_fatal():
    files = [{"path": "broken.py", "extension": ".py", "size": 10}]
    result = analyze_files(files, {"broken.py": "def broken(:\n"})
    assert result["errors"] and result["errors"][0]["path"] == "broken.py"
    assert result["symbols"] == []


def test_typescript_tree_sitter_adapter_when_dependency_is_installed():
    import pytest
    pytest.importorskip("tree_sitter_language_pack")
    result = parse_source("src/index.ts", "import { helper } from './helper';\nexport function run(value: string) { return helper(value); }\n")
    assert result["imports"][0]["module"] == "./helper"
    assert any(item["name"] == "run" and item["type"] == "function" for item in result["symbols"])
    assert any(item["name"] == "run" for item in result["exports"])


def test_external_dependency_versions_are_declared_constraints():
    results = _external_dependencies({"package.json": '{"dependencies":{"react":"^18.2.0"},"devDependencies":{"vitest":"~2.0.0"}}'})
    assert {item["package_name"]: item["declared_version"] for item in results} == {"react": "^18.2.0", "vitest": "~2.0.0"}
    assert all(item.get("resolved_version") is None for item in results)
