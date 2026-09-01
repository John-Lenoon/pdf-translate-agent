from types import SimpleNamespace

import httpx
from openai import APIConnectionError

from translator.models import TranslationResult
from translator.provider import OpenAIProvider


class Responses:
    def __init__(self):
        self.calls = 0

    def parse(self, **_kwargs):
        self.calls += 1
        if self.calls < 3:
            raise APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
        return SimpleNamespace(
            id="response-1",
            output_parsed=TranslationResult(translation="译文"),
            usage=None,
            _request_id="request-1",
        )


def test_provider_retries_transient_errors_three_times():
    responses = Responses()
    sleeps = []
    provider = OpenAIProvider(
        "test-model",
        client=SimpleNamespace(responses=responses),
        sleep=sleeps.append,
    )

    result = provider.translate("Source", {}, [], [])

    assert result.translation == "译文"
    assert responses.calls == 3
    assert sleeps == [1, 2]
    assert provider.last_metadata["request_id"] == "request-1"


def test_provider_retries_empty_structured_responses():
    class EmptyThenValidResponses:
        def __init__(self):
            self.calls = 0

        def parse(self, **_kwargs):
            self.calls += 1
            parsed = None if self.calls < 3 else TranslationResult(translation="译文")
            return SimpleNamespace(id=f"response-{self.calls}", output_parsed=parsed, usage=None)

    responses = EmptyThenValidResponses()
    sleeps = []
    provider = OpenAIProvider(
        "test-model",
        client=SimpleNamespace(responses=responses),
        sleep=sleeps.append,
    )

    assert provider.translate("Source", {}, [], []).translation == "译文"
    assert responses.calls == 3
    assert sleeps == [1, 2]


def test_compatible_chat_provider_validates_json_object(monkeypatch):
    class Completions:
        def __init__(self):
            self.request = None

        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                id="chat-1",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"translation":"译文","entity_observations":[],'
                            '"glossary_suggestions":[],"warnings":[]}'
                        )
                    )
                ],
                usage=None,
                _request_id="chat-request-1",
            )

    completions = Completions()
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    provider = OpenAIProvider(
        "deepseek-test",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    result = provider.translate("Source", {}, [], [])

    assert result.translation == "译文"
    assert completions.request["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in completions.request["messages"][0]["content"]
