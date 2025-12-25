from app.services import llm_client


def test_payload_uses_structured_outputs_schema(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["payload"] = json

        class Resp:
            status_code = 200

            def json(self):
                return {"output_text": '{"quartier_intro":"","transports_metro_texte":"","transports_bus_texte":"","transports_taxi_texte":""}'}

        return Resp()

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"post": staticmethod(fake_post)}))
    monkeypatch.setattr(llm_client, "_get_openai_api_key", lambda: "dummy")

    schema = {"type": "object", "properties": {"foo": {"type": "string"}}}

    llm_client.invoke_llm_json("hello", schema)

    assert captured["url"] == llm_client.RESPONSES_URL
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"
    assert captured["payload"]["text"]["format"]["schema"] == schema
