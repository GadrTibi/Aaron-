import pytest

from app.services import llm_client


def _fake_response(status_code=200, json_data=None, text=""):
    class Resp:
        def __init__(self):
            self.status_code = status_code
            self._json = json_data
            self.text = text

        def json(self):
            if self._json is None:
                raise ValueError("no json")
            return self._json

    return Resp()


def test_openai_error_message_surface(monkeypatch):
    def fake_post(*args, **kwargs):
        return _fake_response(
            status_code=400,
            json_data={"error": {"message": "quota exceeded"}},
            text='{"error":{"message":"quota exceeded"}}',
        )

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"post": staticmethod(fake_post)}))
    monkeypatch.setattr(llm_client, "_get_openai_api_key", lambda: "dummy")

    with pytest.raises(RuntimeError) as excinfo:
        llm_client.invoke_llm_json("test", {"type": "object"})

    assert "OpenAI error 400: quota exceeded" in str(excinfo.value)
