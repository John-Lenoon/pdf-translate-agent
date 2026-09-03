from __future__ import annotations

from dataclasses import dataclass

from .models import RoutingDecision, TranslationCandidate, TranslationResult
from .provider import CONTEXT_VERSION, PROMPT_VERSION, TranslationProvider
from .routing import QualityRouter, TranslationContext


@dataclass(frozen=True)
class CoordinatedTranslation:
    result: TranslationResult
    selected: TranslationCandidate
    candidates: list[TranslationCandidate]
    decision: RoutingDecision
    provider_events: list[tuple[str, dict]]


class TranslationCoordinator:
    """Runs local first-pass translation and bounded remote review for one segment."""

    def __init__(
        self,
        local_provider: TranslationProvider,
        router: QualityRouter,
        remote_provider: TranslationProvider | None = None,
    ):
        self.local_provider = local_provider
        self.router = router
        self.remote_provider = remote_provider

    def translate(
        self,
        source: str,
        context: dict,
        entities: list[dict],
        glossary: list[dict],
        *,
        retry_count: int = 0,
        structural_flags: tuple[str, ...] = (),
    ) -> CoordinatedTranslation:
        local_result = self.local_provider.translate(source, context, entities, glossary)
        local_candidate = self._candidate("local", local_result, self.local_provider)
        validation_errors = self._quality_signals(source, local_result.translation)
        decision = self.router.decide(
            local_candidate,
            TranslationContext(
                source_text=source,
                validation_errors=tuple(validation_errors),
                # An intentionally disabled chapter summary is not a failure.
                context_degraded=bool(context.get("context_degraded", False)),
                retry_count=retry_count,
                structural_flags=structural_flags,
                model_risk_label=local_result.risk_label,
                calibration_sample=bool(context.get("calibration_sample")),
            ),
        )
        if decision.route == "local_only":
            return CoordinatedTranslation(local_result, local_candidate, [local_candidate], decision, [])

        if self.remote_provider is None:
            return CoordinatedTranslation(
                local_result,
                local_candidate,
                [local_candidate],
                decision,
                [("remote_review_unavailable", {"reason": "remote_provider_not_configured"})],
            )
        try:
            review_context = {**context, "local_candidate": local_result.translation}
            started_event = ("remote_review_started", {"model": self.remote_provider.model})
            remote_result = self.remote_provider.translate(source, review_context, entities, glossary)
            remote_candidate = self._candidate("remote", remote_result, self.remote_provider)
            if self._quality_signals(source, remote_candidate.text) or not remote_candidate.text.strip():
                raise ValueError("remote candidate failed deterministic quality checks")
            changed = remote_candidate.text != local_candidate.text
            reviewed = decision.model_copy(
                update={
                    "review_status": "revised" if changed else "kept",
                    "selection_reason": "Remote review returned a validated candidate",
                }
            )
            return CoordinatedTranslation(
                remote_result,
                remote_candidate,
                [local_candidate, remote_candidate],
                reviewed,
                [started_event, ("remote_review_completed", {"selected": "remote", "changed": changed})],
            )
        except Exception as exc:
            return CoordinatedTranslation(
                local_result,
                local_candidate,
                [local_candidate],
                decision,
                [("remote_review_started", {"model": self.remote_provider.model}), ("remote_review_failed", {"error_type": type(exc).__name__, "message": str(exc)})],
            )

    @staticmethod
    def _quality_signals(source: str, translation: str) -> list[str]:
        import re
        signals: list[str] = []
        if not translation.strip():
            return ["empty_translation"]
        source_numbers = re.findall(r"\d+(?:[.,]\d+)?", source)
        target_numbers = re.findall(r"\d+(?:[.,]\d+)?", translation)
        if sorted(source_numbers) != sorted(target_numbers):
            signals.append("numbers_changed")
        latin = len(re.findall(r"[A-Za-z]", translation))
        han = len(re.findall(r"[\u3400-\u9fff]", translation))
        if re.search(r"[A-Za-z]", source) and han == 0 and latin > 0:
            signals.append("untranslated_latin")
        if translation.casefold() == source.strip().casefold():
            signals.append("unchanged_source")
        return signals

    @staticmethod
    def _candidate(
        source: str, result: TranslationResult, provider: TranslationProvider
    ) -> TranslationCandidate:
        return TranslationCandidate(
            source=source,
            text=result.translation.strip(),
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            context_version=CONTEXT_VERSION,
            metadata=dict(getattr(provider, "last_metadata", {})),
        )
