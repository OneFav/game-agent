from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import policy


def test_policy_class_implements_policy_protocol() -> None:
    assert issubclass(policy.PolicyClass, policy.Policy)
