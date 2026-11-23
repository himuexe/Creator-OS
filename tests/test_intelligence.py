import json

import pytest

from app.intelligence import AnalysisError, recommend


def candidate(first, last):
    return {"first": first, "last": last, "quality": 4, "title": "What changes exposure?",
            "hook": "Look at the moving subject.", "topic": "Exposure", "description": "The speaker compares shutters.",
            "reason": "The excerpt contains both the setup and its explanation."}


class ScriptedProvider:
    name, model = "test", "fixture"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def analyze(self, rows, avoid, correction):
        self.prompts.append((rows, avoid, correction))
        return next(self.responses)


def response(*clips):
    return json.dumps({"topics": ["Exposure"], "clips": clips})


rows = [{"start": 0.2, "end": 2.6, "text": "Shorter exposures freeze motion."},
        {"start": 3.0, "end": 5.5, "text": "Longer exposures blur moving subjects."},
        {"start": 5.6, "end": 9.2, "text": "Aperture controls light at the lens."}]


def test_invalid_model_boundaries_are_corrected_and_grounded():
    provider = ScriptedProvider([response(candidate(1, 5)), response(candidate(0, 1))])
    plan = recommend(rows, duration=10, provider=provider)
    assert provider.prompts[1][2]
    assert (plan.provider, plan.model, plan.topics) == ("test", "fixture", ["Exposure"])
    assert [(clip.first, clip.last) for clip in plan.clips] == [(0, 1)]


def test_alternatives_exclude_previous_spans_and_deduplicate():
    provider = ScriptedProvider([response(candidate(0, 1), candidate(2, 2), candidate(2, 2))])
    plan = recommend(rows, duration=10, exclude=[(0.2, 5.5)], provider=provider)
    assert provider.prompts[0][1] == [[0, 1]]
    assert [(clip.first, clip.last) for clip in plan.clips] == [(2, 2)]


def test_invalid_json_fails_after_bounded_retry():
    with pytest.raises(AnalysisError, match="twice"):
        recommend(rows, duration=10, provider=ScriptedProvider(["invalid", "null"]))


def test_invalid_source_time_never_reaches_model():
    with pytest.raises(AnalysisError, match="boundary"):
        recommend(rows, duration=3.0, provider=ScriptedProvider([]))
