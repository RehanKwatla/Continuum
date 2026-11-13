from app.services.git_history_intelligence import UNCLEAR_INTENT, classify_commit


def test_classifies_revert_and_documentation_from_explicit_signals():
    assert classify_commit("Revert \"Add cache\"", ["src/cache.py"])["category"] == "revert"
    docs = classify_commit("Update setup guide", ["README.md", "docs/setup.md"])
    assert docs["category"] == "documentation"
    assert docs["confidence"] == "high"


def test_security_word_alone_does_not_claim_a_security_fix():
    result = classify_commit("Discuss security review", ["docs/security-review.md"])
    assert result["category"] != "security"
    assert result["confidence"] in {"low", "high"}


def test_generic_commit_has_low_confidence_and_no_claim_of_intent():
    result = classify_commit("Update code", ["src/service.py"])
    assert result["confidence"] == "low"
    assert result["signals"]
    assert UNCLEAR_INTENT == "Change intent could not be reliably determined from the available history."
