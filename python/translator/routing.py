from __future__ import annotations

from dataclasses import dataclass
import os

from .models import RoutingDecision, TranslationCandidate


RISK_POLICY_VERSION = "v2.2"


@dataclass(frozen=True)
class RiskPolicy:
    """Versioned, explainable knobs for remote-review routing."""

    remote_threshold: float = 0.35
    context_degraded_weight: float = 0.35
    calibration_interval: int = 5

    def __post_init__(self) -> None:
        if not 0 <= self.remote_threshold <= 1:
            raise ValueError("remote_threshold must be between 0 and 1")
        if not 0 <= self.context_degraded_weight <= 1:
            raise ValueError("context_degraded_weight must be between 0 and 1")
        if self.calibration_interval < 1:
            raise ValueError("calibration_interval must be at least 1")

    @classmethod
    def from_environment(cls) -> "RiskPolicy":
        return cls(
            remote_threshold=float(os.getenv("V2_REMOTE_RISK_THRESHOLD", "0.35")),
            context_degraded_weight=float(os.getenv("V2_CONTEXT_DEGRADED_WEIGHT", "0.35")),
            calibration_interval=int(os.getenv("V2_CALIBRATION_INTERVAL", "5")),
        )


@dataclass(frozen=True)
class TranslationContext:
    source_text: str
    validation_errors: tuple[str, ...] = ()
    entity_conflict: bool = False
    glossary_conflict: bool = False
    context_degraded: bool = False
    retry_count: int = 0
    structural_flags: tuple[str, ...] = ()
    model_risk_label: str = "low"
    calibration_sample: bool = False


class QualityRouter:
    """Owns V2's deterministic, explainable decision to call the remote reviewer."""

    def __init__(self, remote_threshold: float | None = None, *, policy: RiskPolicy | None = None):
        if policy is not None and remote_threshold is not None:
            raise ValueError("provide policy or remote_threshold, not both")
        self.policy = policy or RiskPolicy(
            remote_threshold=0.35 if remote_threshold is None else remote_threshold
        )
        self.remote_threshold = self.policy.remote_threshold

    def decide(
        self, candidate: TranslationCandidate, context: TranslationContext
    ) -> RoutingDecision:
        signals: list[str] = list(context.validation_errors)
        validation_weights = {
            "empty_translation": 1.0,
            "unchanged_source": 1.0,
            "untranslated_latin": 0.8,
            "numbers_changed": 0.7,
            "malformed_json": 0.8,
            "missing_structure": 0.5,
        }
        score = min(sum(validation_weights.get(signal, 0.15) for signal in context.validation_errors), 1.0)
        if not candidate.text.strip():
            signals.append("empty_translation")
            score = 1.0
        if candidate.text.strip().casefold() == context.source_text.strip().casefold():
            signals.append("unchanged_source")
            score = 1.0
        if context.entity_conflict:
            signals.append("entity_conflict")
            score += 0.6
        if context.glossary_conflict:
            signals.append("glossary_conflict")
            score += 0.4
        if context.context_degraded:
            signals.append("context_degraded")
            score += self.policy.context_degraded_weight
        if context.retry_count:
            signals.append("retry_history")
            score += min(context.retry_count * 0.1, 0.3)
        if context.calibration_sample:
            signals.append("calibration_sample")
            score = max(score, self.remote_threshold)
        for flag in context.structural_flags:
            signals.append(f"structure:{flag}")
            score += 0.1
        label = context.model_risk_label.lower()
        label_weight = {"low": 0.0, "medium": 0.25, "high": 0.5}.get(label, 0.0)
        if label not in {"low", "medium", "high"}:
            signals.append("invalid_model_risk_label")
            label = "high"
            label_weight = 0.5
        if label != "low":
            signals.append(f"model_risk:{label}")
        score = min(score + label_weight, 1.0)
        route = "remote_review" if score >= self.remote_threshold else "local_only"
        return RoutingDecision(
            score=score,
            signals=sorted(set(signals)),
            risk_label=label,
            route=route,
            review_status="not_required" if route == "local_only" else "review_debt",
            selection_reason=(
                "Deterministic and model risk signals require remote review"
                if route == "remote_review"
                else "No remote-review threshold was reached"
            ),
        )
