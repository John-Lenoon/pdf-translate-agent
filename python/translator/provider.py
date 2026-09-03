from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import threading
from typing import Callable, Protocol

from .models import ChapterSummaryResult, EntityDiscoveryResult, FormatReviewResult, StructureReviewResult, TranslationResult

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

    def discover_entities(self, source: str, context: dict) -> EntityDiscoveryResult: ...

    def classify_reflow_structure(self, source: str, hints: dict) -> StructureReviewResult: ...

    def review_reflow_page(self, payload: dict) -> FormatReviewResult: ...


class ProviderResponseError(RuntimeError):
    pass


class LocalModelUnavailableError(RuntimeError):
    error_code = "local_model_unavailable"


class LocalModelNotFoundError(RuntimeError):
    error_code = "local_model_not_found"


class LocalModelContractError(RuntimeError):
    error_code = "local_model_contract_unsupported"


class LocalModelGpuUnavailableError(RuntimeError):
    error_code = "local_model_gpu_unavailable"


class OllamaAdapter:
    """Minimal Ollama adapter with a testable request seam and schema-validated output."""

    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:11434",
        *,
        request: Callable[[str, str, dict], dict] | None = None,
        timeout: float = 120,
        num_ctx: int = 4096,
        num_predict: int = 512,
        think: bool = False,
    ):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.think = think
        self._request = request or self._http_request
        self.last_metadata: dict = {}
        self._active_response = None
        self._active_response_lock = threading.Lock()

    def cancel_active_request(self) -> None:
        """Close the in-flight Ollama response so cancellation reaches the model."""
        with self._active_response_lock:
            response = self._active_response
        if response is not None:
            response.close()

    def probe(self) -> None:
        try:
            models = self._request("GET", "/api/tags", {})
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise LocalModelUnavailableError("Ollama is not reachable") from exc
        available = {item.get("name") for item in models.get("models", [])}
        if self.model not in available:
            raise LocalModelNotFoundError(f"Ollama model is not installed: {self.model}")
        try:
            result = self._chat("Return a valid translation object", TranslationResult)
            if not result.translation.strip():
                raise ValueError("empty translation")
        except (ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
            raise LocalModelContractError("Ollama model failed structured-output probe") from exc
        self._assert_gpu_loaded()

    def _assert_gpu_loaded(self) -> None:
        try:
            processes = self._request("GET", "/api/ps", {})
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise LocalModelGpuUnavailableError("Unable to verify Ollama GPU placement") from exc
        loaded = next(
            (item for item in processes.get("models", []) if item.get("name") == self.model),
            None,
        )
        if not loaded or int(loaded.get("size_vram") or 0) <= 0:
            raise LocalModelGpuUnavailableError(
                f"Ollama model is not loaded in GPU memory: {self.model}"
            )

    def translate(self, source: str, context: dict, entities: list[dict], glossary: list[dict]) -> TranslationResult:
        payload = json.dumps(
            {
                "task": "Translate the source text from English to Simplified Chinese.",
                "target_language": "zh-CN",
                "source": source,
                "chapter_summary": context.get("chapter_summary", ""),
                "previous_paragraphs": context.get("previous_paragraphs", []),
                "next_paragraphs": context.get("next_paragraphs", []),
                "entities": entities,
                "user_glossary": glossary,
            },
            ensure_ascii=False,
        )
        return self._chat(
            payload,
            TranslationResult,
            "Translate English into natural, faithful Simplified Chinese. "
            "The translation field must contain Chinese prose, not the English source. "
            "Preserve paragraph meaning, tone, punctuation, and names.",
        )

    def discover_entities(self, source: str, context: dict) -> EntityDiscoveryResult:
        return self._chat(
            json.dumps({"source": source, "context": context}, ensure_ascii=False),
            EntityDiscoveryResult,
            "Extract clearly identified human person names from the English source. "
            "Return an empty list when there are none. For each name provide a natural "
            "Simplified Chinese translation and the exact evidence text.",
        )

    def summarize_chapter(self, chapter_text: str) -> str:
        result = self._chat(
            chapter_text[:12000],
            ChapterSummaryResult,
            "Summarize the English chapter in Simplified Chinese for a translator.",
        )
        if not result.summary.strip():
            raise ProviderResponseError("MODEL_RETURNED_NO_CHAPTER_SUMMARY")
        return result.summary.strip()

    def classify_reflow_structure(self, source: str, hints: dict) -> StructureReviewResult:
        return self._chat(
            json.dumps({"source": source, "hints": hints}, ensure_ascii=False),
            StructureReviewResult,
            "Classify this PDF text block for Chinese book layout. Use heading only for true headings; otherwise paragraph. Return confidence and a short reason.",
        )

    def review_reflow_page(self, payload: dict) -> FormatReviewResult:
        screenshot = payload.get("screenshot_png_base64", "")
        review_payload = {key: value for key, value in payload.items() if key != "screenshot_png_base64"}
        return self._chat(
            json.dumps(review_payload, ensure_ascii=False),
            FormatReviewResult,
            "Review the provided Chinese PDF page image and metrics for layout defects. Fail only for visible hierarchy, whitespace, clipping, collision, or readability problems. Return concise issue records.",
            images=[screenshot] if screenshot else None,
        )

    def _chat(self, prompt: str, schema, instruction: str = "Return only JSON matching the supplied schema.", images: list[str] | None = None):
        user_message = {"role": "user", "content": prompt}
        if images:
            user_message["images"] = images
        response = self._request(
            "POST",
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": schema.model_json_schema(),
                "think": self.think,
                "options": {
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                    "temperature": 0.2,
                },
                "messages": [
                    {"role": "system", "content": f"{instruction} Return only JSON matching the supplied schema."},
                    user_message,
                ],
            },
        )
        content = response.get("message", {}).get("content")
        if not content:
            raise ProviderResponseError("MODEL_RETURNED_NO_STRUCTURED_OUTPUT")
        parsed = schema.model_validate_json(content)
        self.last_metadata = {
            "usage": {
                "input_tokens": response.get("prompt_eval_count"),
                "output_tokens": response.get("eval_count"),
            },
            "endpoint": self.endpoint,
        }
        return parsed

    def _http_request(self, method: str, path: str, payload: dict) -> dict:
        data = None if method == "GET" else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
            with self._active_response_lock:
                self._active_response = response
            try:
                return json.loads(response.read().decode("utf-8"))
            finally:
                with self._active_response_lock:
                    self._active_response = None
                response.close()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and path == "/api/tags":
                raise LocalModelUnavailableError("Ollama endpoint does not support model listing") from exc
            raise LocalModelUnavailableError("Ollama request failed") from exc


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

    def classify_reflow_structure(self, source: str, hints: dict) -> StructureReviewResult:
        response, parsed = self._retry(
            lambda: self._structured_request(
                "Classify this PDF text block for Chinese book layout. Use heading only for true headings; otherwise paragraph. Return confidence and a short reason.",
                json.dumps({"source": source, "hints": hints}, ensure_ascii=False),
                StructureReviewResult,
            )
        )
        self.last_metadata = self._metadata(response)
        return parsed

    def review_reflow_page(self, payload: dict) -> FormatReviewResult:
        screenshot = payload.get("screenshot_png_base64", "")
        review_payload = {key: value for key, value in payload.items() if key != "screenshot_png_base64"}
        response, parsed = self._retry(
            lambda: self._structured_request(
                "Review the supplied Chinese PDF page image and deterministic metrics for layout defects. Fail only for visible hierarchy, whitespace, clipping, collision, or readability problems.",
                json.dumps(review_payload, ensure_ascii=False),
                FormatReviewResult,
                image_data_uri=f"data:image/png;base64,{screenshot}" if screenshot else None,
            )
        )
        self.last_metadata = self._metadata(response)
        return parsed

    def _structured_request(self, system: str, user: str, schema, image_data_uri: str | None = None):
        if self.use_chat_completions:
            schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            user_content = user if not image_data_uri else [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ]
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
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise ProviderResponseError("MODEL_RETURNED_NO_STRUCTURED_OUTPUT")
            parsed = schema.model_validate_json(content)
            return response, parsed
        user_content = user if not image_data_uri else [
            {"type": "input_text", "text": user},
            {"type": "input_image", "image_url": image_data_uri},
        ]
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
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
