from __future__ import annotations

import re

from .models import EntityObservation

_FUNCTION_WORDS = {
    "i", "we", "you", "he", "she", "it", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "our", "their", "hers", "ours", "theirs", "the", "a", "an",
}
_RELATION_WORDS = {
    "father", "mother", "brother", "sister", "husband", "wife", "son", "daughter",
    "child", "man", "woman", "boy", "girl", "stranger", "friend", "teacher", "doctor",
}


def is_valid_person_observation(observation: EntityObservation) -> bool:
    source = " ".join(observation.source_name.split())
    target = observation.target_name.strip()
    if not source or not target or len(source) > 80:
        return False
    words = re.findall(r"[A-Za-z]+", source)
    lowered = {word.casefold() for word in words}
    if not words or lowered & _FUNCTION_WORDS or lowered & _RELATION_WORDS:
        return False
    if len(words) > 4 or not all(word[0].isupper() for word in words):
        return False
    return True


def valid_person_observations(observations: list[EntityObservation]) -> list[EntityObservation]:
    unique: dict[str, EntityObservation] = {}
    for observation in observations:
        if is_valid_person_observation(observation):
            key = " ".join(observation.source_name.split()).casefold()
            unique.setdefault(key, observation)
    return list(unique.values())
