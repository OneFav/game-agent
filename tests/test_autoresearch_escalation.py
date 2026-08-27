from __future__ import annotations

from game_agent.autoresearch import ResearchStage, ResearchState


def test_stage_capabilities_are_cumulative() -> None:
    state = ResearchState()
    assert state.enabled_capabilities == ("existing_parameter_search",)

    state.record_stage_result(succeeded=False, reason="parameter plateau")
    assert state.stage is ResearchStage.RECIPE
    assert state.enabled_capabilities == (
        "existing_parameter_search",
        "training_recipe_change",
        "search_space_extension",
    )

    state.record_stage_result(succeeded=False, reason="recipe plateau")
    assert state.stage is ResearchStage.POLICY_CODE
    assert state.enabled_capabilities[-1] == "policy_local_code_change"
    assert set(ResearchState(ResearchStage.RECIPE).enabled_capabilities) < set(
        state.enabled_capabilities
    )


def test_failure_escalates_and_success_downgrades_with_bounds() -> None:
    state = ResearchState()
    assert state.record_stage_result(succeeded=False, reason="failed").current == 2
    assert state.record_stage_result(succeeded=False, reason="failed").current == 3
    assert state.record_stage_result(succeeded=False, reason="failed").current == 3

    transition = state.record_stage_result(succeeded=True, reason="promoted")
    assert (transition.previous, transition.current) == (3, 2)
    assert state.record_stage_result(succeeded=True, reason="promoted").current == 1
    assert state.record_stage_result(succeeded=True, reason="promoted").current == 1


def test_research_state_round_trip_preserves_history() -> None:
    state = ResearchState()
    state.record_stage_result(succeeded=False, reason="stage 1 plateau")
    state.record_stage_result(succeeded=True, reason="stage 2 promotion")

    restored = ResearchState.from_dict(state.to_dict())

    assert restored.stage is ResearchStage.PARAMETERS
    assert restored.history == state.history
    assert restored.to_dict()["enabled_capabilities"] == ["existing_parameter_search"]
