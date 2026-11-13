from app.services.handover_intelligence import apply_human_edits, prioritize_knowledge


def test_role_changes_relevance_order_without_changing_evidence_records():
    rows = [
        {"id": "a", "category": "frontend", "title": "React components", "content": "UI", "confidence": 0.8},
        {"id": "b", "category": "database", "title": "Database migrations", "content": "Backend schema", "confidence": 0.8},
    ]
    frontend = prioritize_knowledge(rows, "frontend_developer")
    backend = prioritize_knowledge(rows, "backend_developer")
    assert frontend[0]["id"] == "a"
    assert backend[0]["id"] == "b"
    assert {item["id"] for item in frontend} == {item["id"] for item in backend}
    assert rows[0]["id"] == "a"  # input and its provenance remain untouched


def test_custom_role_prioritizes_its_explicit_focus_terms():
    rows = [
        {"id": "frontend", "title": "User interface", "category": "frontend", "confidence": 0.9},
        {"id": "database", "title": "Database migrations", "category": "operations", "confidence": 0.2},
    ]
    assert [item["id"] for item in prioritize_knowledge(rows, "database engineer")] == ["database", "frontend"]


def test_human_fact_edits_remove_old_evidence_and_keep_original_text():
    source = {
        "sections": [{"key": "architecture", "title": "Architecture", "items": [
            {"text": "Observed component", "evidence_level": "observed", "evidence": [{"file_path": "src/api.py"}]}
        ]}],
        "tasks": [{"id": "issue:4", "title": "Fix request validation", "description": "Investigate issue", "status": "suggested", "priority": "medium", "evidence": [{"label": "Issue #4"}]}],
    }
    updated = apply_human_edits(
        source,
        [{"key": "architecture", "title": "Architecture", "items": [{"text": "New claim", "evidence": [{"url": "https://fake.invalid"}]}]}],
        [{"id": "issue:4", "title": "New issue claim", "status": "accepted", "evidence": [{"label": "fake"}]}],
    )
    item = updated["sections"][0]["items"][0]
    task = updated["tasks"][0]
    assert item["evidence"] == [] and item["evidence_level"] == "reviewer_edited_unverified"
    assert task["evidence"] == [] and task["status"] == "accepted"
