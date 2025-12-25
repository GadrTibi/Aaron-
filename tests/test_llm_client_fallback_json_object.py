import json

from app.services import llm_client
from app.services.generation_report import GenerationReport


def test_fallback_to_json_object(monkeypatch):
    calls = {"count": 0}
    report = GenerationReport()

    def fake_post(url, headers, json=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            class Resp:
                status_code = 400

                def json(self):
                    return {"error": {"message": "response_format unsupported"}}

                text = "response_format unsupported"

            return Resp()

        class Resp:
            status_code = 200

            def json(self):
                payload = {
                    "quartier_intro": "intro",
                    "transports_metro_texte": "metro",
                    "transports_bus_texte": "bus",
                    "transports_taxi_texte": "taxi",
                }
                return {"output_text": __import__("json").dumps(payload)}

        return Resp()

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"post": staticmethod(fake_post)}))
    monkeypatch.setattr(llm_client, "_get_openai_api_key", lambda: "dummy")

    result = llm_client.invoke_llm_json("prompt", {"type": "object"}, report)

    assert calls["count"] == 2
    assert result["quartier_intro"] == "intro"
    assert any("structured outputs failed" in warn for warn in report.provider_warnings)
