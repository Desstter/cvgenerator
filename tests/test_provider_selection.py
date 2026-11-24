"""Provider-specific request formats and explicit model selection, without external calls."""
from types import SimpleNamespace

from app.services import ai_adapter


def test_openai_uses_responses_api_json_without_storing(monkeypatch):
    calls = []
    provider = object.__new__(ai_adapter.OpenAIProvider)
    provider.model = "gpt-6.2-sol"
    provider.config = SimpleNamespace(openai_max_tokens=2000, openai_service_tier="fast")
    provider.client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: calls.append(kw) or SimpleNamespace(output_text='{"ok": true}')))
    assert provider.chat_json("Return JSON", "test") == {"ok": True}
    assert calls[0]["model"] == "gpt-6.2-sol"
    assert calls[0]["store"] is False
    assert calls[0]["service_tier"] == "fast"
    assert calls[0]["text"] == {"format": {"type": "json_object"}}
    assert "max_tokens" not in calls[0]


def test_default_openai_model_is_sol():
    from app.config import Settings
    assert Settings.model_fields["openai_model"].default == "gpt-6.2-sol"
    assert Settings.model_fields["openai_service_tier"].default == ""


def test_openai_omits_service_tier_when_empty():
    calls = []
    provider = object.__new__(ai_adapter.OpenAIProvider)
    provider.model = "gpt-6.2-sol"
    provider.config = SimpleNamespace(openai_max_tokens=2000, openai_service_tier="")
    provider.client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: calls.append(kw) or SimpleNamespace(output_text='{"ok": true}')))
    assert provider.chat_json("Return JSON", "test") == {"ok": True}
    assert calls[0]["model"] == "gpt-6.2-sol"
    assert "service_tier" not in calls[0]


def test_deepseek_uses_chat_json_and_exact_model():
    calls = []
    provider = object.__new__(ai_adapter.DeepSeekProvider)
    provider.model = "deepseek-v4-pro"
    provider.config = SimpleNamespace(deepseek_max_tokens=2000)
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw) or response)))
    assert provider.chat_json("Return JSON", "test") == {"ok": True}
    assert calls[0]["model"] == "deepseek-v4-pro"
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_cli_accepts_explicit_model_and_deepseek():
    from app.cli import parser
    args = parser().parse_args(["--workspace", "work", "generate", "--job", "job.txt", "--provider", "deepseek", "--model", "deepseek-v4-pro"])
    assert (args.provider, args.model) == ("deepseek", "deepseek-v4-pro")
