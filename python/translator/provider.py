from __future__ import annotations

import json
import os
import time
from typing import Callable, Protocol

from .models import ChapterSummaryResult, TranslationResult

PROMPT_VERSION = "v1.1"
CONTEXT_VERSION = "v1.1"


class TranslationProvider(Protocol):
    model: str
    last_metadata: dict

    def translate(
        self,
        source: str,
        context: dict,
        entities: list[dict],
        glossary: list[dict],
    ) -> TranslationResult: ...

    def summarize_chapter(self, chapter_text: str) -> str: ...


class ProviderResponseError(RuntimeError):
    pass


class OpenAIProvider:
    def __init__(
        self,
        model: str | None = None,
        *,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ):
        self.model = model or os.getenv("TRANSLATION_MODEL", "")
        if not self.model:
            raise RuntimeError("TRANSLATION_MODEL is required")
        if client is None:
            from openai import OpenAI

            base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
            client = OpenAI(base_url=base_url)
        self.client = client
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.use_chat_completions = bool(self.base_url) and hasattr(client, "chat")
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.last_metadata: dict = {}

    def translate(
        self,
        source: str,
        context: dict,
        entities: list[dict],
        glossary: list[dict],
    ) -> TranslationResult:
        system = (
            "You are a quality-focused literary English-to-Chinese translator. "
            "Preserve meaning, voice, paragraph structure, and punctuation. Reuse every "
            "canonical person name supplied in entities. Apply only the user glossary; "
            "glossary suggestions are advisory and must not change this translation. "
            "Report only clearly identified people in entity_observations."
        )
        payload = json.dumps(
            {
                "source": source,
                "chapter_summary": context.get("chapter_summary", ""),
                "previous_paragraphs": context.get("previous_paragraphs", []),
                "next_paragraphs": context.get("next_paragraphs", []),
                "judge_feedback": context.get("judge_feedback"),
                "entities": entities,
                "user_glossary": glossary,
            },
            ensure_ascii=False,
        )

        def request():
            response, parsed = self._structured_request(
                system,
                payload,
                TranslationResult,
            )
            if parsed is None:
                raise ProviderResponseError("MODEL_RETURNED_NO_STRUCTURED_TRANSLATION")
            return response, parsed

        response, parsed = self._retry(request)
        self.last_metadata = self._metadata(response)
        return parsed

    def summarize_chapter(self, chapter_text: str) -> str:
        bounded_text = chapter_text[:12000]

        def request():
            response, parsed = self._structured_request(
                "Summarize this English novel chapter for a Chinese literary translator. "
                "Keep plot state, tone, relationships, and named people.",
                bounded_text,
                ChapterSummaryResult,
            )
            if parsed is None or not parsed.summary.strip():
                raise ProviderResponseError("MODEL_RETURNED_NO_CHAPTER_SUMMARY")
            return response, parsed

        response, parsed = self._retry(request)
        self.last_metadata = self._metadata(response)
        return parsed.summary.strip()

    def _structured_request(self, system: str, user: str, schema):
        if self.use_chat_completions:
            schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{system} Return only a JSON object that validates against "
                            f"this JSON Schema: {schema_json}"
                        ),
                    },
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise ProviderResponseError("MODEL_RETURNED_NO_STRUCTURED_OUTPUT")
            parsed = schema.model_validate_json(content)
            return response, parsed
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=schema,
        )
        return response, response.output_parsed

    def _retry(self, operation):
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
        from pydantic import ValidationError

        retryable = (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
            ProviderResponseError,
            ValidationError,
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except retryable:
                if attempt == self.max_attempts:
                    raise
                self.sleep(2 ** (attempt - 1))

    def _metadata(self, response) -> dict:
        usage = getattr(response, "usage", None)
        return {
            "response_id": getattr(response, "id", None),
            "request_id": getattr(response, "_request_id", None),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
        }
