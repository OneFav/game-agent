from __future__ import annotations

from pathlib import Path

from game_agent.autoresearch.visualization import render_training_process


EVALUATION_METRICS = {
    "primary": {"name": "success_rate", "direction": "maximize"},
    "hard_constraints": [
        {"name": "collision_rate", "direction": "minimize", "max": 0.1},
    ],
}


def test_process_visualization_prefers_meaningful_training_curve(
    tmp_path: Path,
) -> None:
    trial_dir = tmp_path / "trials" / "trial_0002"
    trial_dir.mkdir(parents=True)
    (trial_dir / "training_curves.csv").write_text(
        "event,step,episode,reward_mean,actor_loss,critic_loss,evaluation_primary,episode_reward\n"
        "evaluation,0,0,,,,0.1,\n"
        "episode,40,1,-1.0,,,,-1.2\n"
        "optimizer_update,80,2,,0.8,1.2,,\n"
        "episode,100,3,0.2,,,,0.5\n"
        "evaluation,100,3,,,,0.5,\n"
        "optimizer_update,160,5,,0.4,0.7,,\n"
        "episode,200,8,1.1,,,,1.4\n"
        "evaluation,200,8,,,,0.8,\n",
        encoding="utf-8",
    )
    rows = [
        {
            "trial_id": "trial_0001",
            "metrics": {"success_rate": 0.4, "collision_rate": 0.2},
            "per_seed_metrics": [
                {"success_rate": 0.2},
                {"success_rate": 0.4},
                {"success_rate": 0.6},
            ],
        },
        {
            "trial_id": "trial_0002",
            "metrics": {"success_rate": 0.8, "collision_rate": 0.05},
            "per_seed_metrics": [
                {"success_rate": 0.7},
                {"success_rate": 0.8},
                {"success_rate": 0.9},
            ],
        },
    ]
    output = tmp_path / "training_process.png"

    data_level, sources = render_training_process(
        output,
        exp_dir=tmp_path,
        rows=rows,
        evaluation_metrics=EVALUATION_METRICS,
        best_trial_id="trial_0002",
    )

    assert data_level == "training_step"
    assert "trials/trial_0002/training_curves.csv" in sources
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert output.stat().st_size > 1_000


def test_process_visualization_discloses_trial_level_fallback(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "trial_id": "trial_0001",
            "metrics": {"success_rate": 0.4, "collision_rate": 0.2},
        },
        {
            "trial_id": "trial_0002",
            "metrics": {"success_rate": 0.8, "collision_rate": 0.05},
        },
    ]
    output = tmp_path / "training_process.png"

    data_level, sources = render_training_process(
        output,
        exp_dir=tmp_path,
        rows=rows,
        evaluation_metrics=EVALUATION_METRICS,
        best_trial_id="trial_0002",
    )

    assert data_level == "trial_evaluation"
    assert sources == ["leaderboard.csv", "trials/*/metrics.json"]
    assert output.stat().st_size > 1_000
