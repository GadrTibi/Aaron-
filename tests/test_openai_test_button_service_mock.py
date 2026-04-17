from app.services import llm_client


def test_openai_test_button_service_mock_success(monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {"data": []}

        text = ""

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"get": staticmethod(lambda *a, **k: Resp())}))

    ok, message = llm_client.test_openai_api_key("sk-test")

    assert ok is True
    assert message == "ok"


def test_openai_test_button_service_mock_error(monkeypatch):
    class Resp:
        status_code = 401

        def json(self):
            return {"error": {"message": "Invalid API key: sk-secret-value"}}

        text = "Invalid API key"

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"get": staticmethod(lambda *a, **k: Resp())}))

    ok, message = llm_client.test_openai_api_key("sk-secret-value")

    assert ok is False
    assert "401" in message
    assert "Invalid API key" in message
    assert "sk-secret-value" not in message
