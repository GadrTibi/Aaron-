from app.services.token_audit import audit_template_tokens


def test_token_audit_marks_empty_values():
    template_tokens = {"A", "B"}
    mapping = {"A": "", "B": "x"}

    result = audit_template_tokens(template_tokens, mapping)

    assert result["empty_values"] == ["A"]
    assert result["missing_in_mapping"] == []
    assert result["ok"] == ["B"]


def test_token_audit_marks_missing_tokens():
    template_tokens = {"A", "B", "C"}
    mapping = {"A": "1", "B": "2"}

    result = audit_template_tokens(template_tokens, mapping)

    assert result["missing_in_mapping"] == ["C"]
    assert result["ok"] == ["A", "B"]
