from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent

CORPUS = json.loads(
    (
        Path(__file__).resolve().parents[3] / "contract-fixtures/v1/shadow-parity.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("target", ["cycle", "outcome"])
def test_shared_valid_envelopes(target: str) -> None:
    model = ShadowCycle if target == "cycle" else ShadowOutcomeEvent
    model.model_validate_json(json.dumps(CORPUS[target]))


@pytest.mark.parametrize("case", CORPUS["mutations"], ids=lambda case: case["name"])
def test_shared_invalid_mutations(case: dict[str, object]) -> None:
    target = str(case["target"])
    payload = copy.deepcopy(CORPUS[target])
    path = case["path"]
    assert isinstance(path, list)
    parent = payload
    for key in path[:-1]:
        parent = parent[int(key)] if isinstance(parent, list) else parent[key]
    if case.get("remove"):
        if isinstance(parent, list):
            del parent[int(path[-1])]
        else:
            del parent[path[-1]]
    else:
        if isinstance(parent, list):
            parent[int(path[-1])] = case["value"]
        else:
            parent[path[-1]] = case["value"]
    model = ShadowCycle if target == "cycle" else ShadowOutcomeEvent
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(payload))
