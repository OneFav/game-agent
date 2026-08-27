from __future__ import annotations

import csv
import textwrap
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

from game_agent.utils.fs import write_json

matplotlib.use("Agg", force=True)
from matplotlib import pyplot as plt  # noqa: E402


FIGURE_FILENAMES = {
    "training_design": "training_design.png",
    "training_process": "training_process.png",
    "training_effect": "training_effect.png",
}

_COLORS = {
    "navy": "#17324D",
    "blue": "#2F6B9A",
    "cyan": "#5AA6A6",
    "orange": "#D9822B",
    "green": "#2D7D46",
    "red": "#B33A3A",
    "gray": "#6B7280",
    "light": "#EEF3F7",
}


def generate_training_visualizations(
    *,
    exp_dir: Path,
    scenario_spec: dict[str, Any],
    policy_metadata: dict[str, Any],
    search_space: dict[str, Any],
    rows: list[dict[str, Any]],
    baseline_metrics: dict[str, float],
    baseline_per_seed_metrics: list[dict[str, Any]],
    best: dict[str, Any],
    seeds: list[int],
    baseline_identity: str = "policy.default_config",
) -> dict[str, Any]:
    """生成设计、过程和效果三类标准图，以及机器可读清单。"""

    figures_dir = Path(exp_dir) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    evaluation_metrics = scenario_spec.get("evaluation_metrics", {})

    design_path = figures_dir / FIGURE_FILENAMES["training_design"]
    process_path = figures_dir / FIGURE_FILENAMES["training_process"]
    effect_path = figures_dir / FIGURE_FILENAMES["training_effect"]

    render_training_design(
        design_path,
        scenario_spec=scenario_spec,
        policy_metadata=policy_metadata,
        search_space=search_space,
        seeds=seeds,
    )
    process_data_level, process_sources = render_training_process(
        process_path,
        exp_dir=Path(exp_dir),
        rows=rows,
        evaluation_metrics=evaluation_metrics,
        best_trial_id=str(best["trial_id"]),
    )
    comparison = render_training_effect(
        effect_path,
        baseline_metrics=baseline_metrics,
        best_metrics=best["metrics"],
        baseline_per_seed_metrics=baseline_per_seed_metrics,
        best_per_seed_metrics=best.get("per_seed_metrics", []),
        evaluation_metrics=evaluation_metrics,
        best_trial_id=str(best["trial_id"]),
        baseline_label=_baseline_label(baseline_identity),
    )

    disclosures = []
    if process_data_level == "trial_evaluation":
        disclosures.append(
            "No multi-step training curve was available; the process figure uses "
            "trial-level evaluation metrics and hard-constraint evidence."
        )

    manifest = {
        "schema_version": "1.0",
        "standard": "training_visualization/v1",
        "figures": [
            {
                "id": "training_design",
                "path": f"figures/{design_path.name}",
                "purpose": "Declare method, data contracts, optimization surface, and evidence budget.",
                "data_sources": [
                    "scenario/task_spec.yaml",
                    "policy/metadata.json",
                    "policy/search_space.yaml",
                ],
            },
            {
                "id": "training_process",
                "path": f"figures/{process_path.name}",
                "purpose": "Show optimization progress, best-so-far behavior, and constraint feasibility.",
                "data_level": process_data_level,
                "data_sources": process_sources,
            },
            {
                "id": "training_effect",
                "path": f"figures/{effect_path.name}",
                "purpose": (
                    f"Compare the declared baseline ({baseline_identity}) with the "
                    "promoted best trial on identical seeds."
                ),
                "data_sources": [
                    "baseline_metrics.json",
                    f"trials/{best['trial_id']}/metrics.json",
                    "best_config.yaml",
                ],
            },
        ],
        "comparison": {
            **comparison,
            "baseline": baseline_identity,
            "candidate": str(best["trial_id"]),
            "seeds": seeds,
        },
        "raw_data_tables": ["leaderboard.csv", "baseline_metrics.json"],
        "disclosures": disclosures,
    }
    write_json(figures_dir / "visualization_manifest.json", manifest)
    return manifest


def render_training_design(
    path: Path,
    *,
    scenario_spec: dict[str, Any],
    policy_metadata: dict[str, Any],
    search_space: dict[str, Any],
    seeds: list[int],
) -> None:
    method = policy_metadata.get("method", {})
    hypothesis = policy_metadata.get("method_hypothesis", {})
    boundaries = policy_metadata.get("immutable_boundaries", {})
    evaluation = scenario_spec.get("evaluation_metrics", {})
    primary = evaluation.get("primary", {})
    constraints = evaluation.get("hard_constraints", [])
    reward_components = scenario_spec.get("reward_structure", {}).get("components", [])
    reward_design = policy_metadata.get("reward_design", {})
    budget = search_space.get("budget", {})

    fig = plt.figure(figsize=(15, 8.5), facecolor="white")
    fig.suptitle(
        f"Training Design | {policy_metadata.get('policy_id', 'policy')}",
        x=0.04,
        y=0.97,
        ha="left",
        fontsize=20,
        fontweight="bold",
        color=_COLORS["navy"],
    )
    fig.text(
        0.04,
        0.925,
        f"Scenario: {scenario_spec.get('task_id', 'unknown')}  •  "
        f"Formalism: {scenario_spec.get('formalism', 'unknown')}  •  "
        f"Evaluation seeds: {', '.join(map(str, seeds))}",
        fontsize=10,
        color=_COLORS["gray"],
    )

    panels = [
        (
            "1  Method & roles",
            [
                f"Method: {method.get('name', policy_metadata.get('policy_type', 'unspecified'))}",
                f"Family: {method.get('family', 'unspecified')}",
                f"Learning: {method.get('learning_paradigm', 'unspecified')}",
                f"Execution: {method.get('execution_mode', 'unspecified')}",
                f"Trained: {_format_list(method.get('trained_parties', []))}",
                f"Frozen: {_format_list(method.get('frozen_parties', []))}",
                f"Shared params: {method.get('parameter_sharing', 'unspecified')}",
                f"Opponent model: {method.get('explicit_opponent_model', 'unspecified')}",
            ],
            _COLORS["blue"],
        ),
        (
            "2  Data & safety contract",
            [
                f"Observation: {_shape_text(scenario_spec.get('observation_space', {}))}",
                f"Action: {_shape_text(scenario_spec.get('action_space', {}))}",
                f"Action semantics: {scenario_spec.get('action_space', {}).get('semantics', 'unspecified')}",
                f"Privileged train state: {method.get('training_privileged_state', False)}",
                _wrapped(
                    f"Environment reward: {_format_list([item.get('name') for item in reward_components])}",
                    width=55,
                ),
                _wrapped(
                    f"Training shaping: {_format_list(reward_design.get('training_only_shaping', []))}",
                    width=55,
                ),
                f"Primary metric: {primary.get('name', 'unspecified')} ({primary.get('direction', 'unspecified')})",
                "Hard constraints:",
                *[f"  • {_constraint_text(item)}" for item in constraints],
            ],
            _COLORS["cyan"],
        ),
        (
            "3  Optimization & evidence",
            [
                f"Max trials: {budget.get('max_trials', 'unspecified')}",
                f"Train steps / trial: {budget.get('max_train_steps', 'not applicable')}",
                f"Seeds / trial: {budget.get('seeds_per_trial', len(seeds))}",
                f"Baseline: {search_space.get('baseline', {}).get('identity', 'policy.default_config')}",
                f"Initial knobs: {_format_list(search_space.get('parameters', {}).keys())}",
                "Method hypothesis:",
                _wrapped(str(hypothesis.get("statement", "not declared")), width=38),
                "Optimization guidance:",
                *[
                    f"  • {_wrapped(str(item), width=34)}"
                    for item in hypothesis.get("optimization_guidance", [])
                ],
                f"Invariants: {len(boundaries.get('method_invariants', []))}",
            ],
            _COLORS["orange"],
        ),
    ]
    for index, (title, lines, color) in enumerate(panels):
        axis = fig.add_axes([0.04 + index * 0.32, 0.12, 0.29, 0.76])
        _render_text_panel(axis, title, lines, color)

    fig.text(
        0.04,
        0.045,
        "Promotion authority: scenario.evaluation_metrics  •  "
        "Reward is a training signal, never the ranking authority.",
        fontsize=10,
        color=_COLORS["navy"],
        fontweight="bold",
    )
    _save_figure(fig, path)


def render_training_process(
    path: Path,
    *,
    exp_dir: Path,
    rows: list[dict[str, Any]],
    evaluation_metrics: dict[str, Any],
    best_trial_id: str,
) -> tuple[str, list[str]]:
    ordered = sorted(rows, key=lambda row: str(row["trial_id"]))
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    direction = str(primary.get("direction", "maximize"))
    trial_numbers = np.arange(1, len(ordered) + 1)
    values = np.asarray(
        [float(row["metrics"][primary_name]) for row in ordered],
        dtype=float,
    )
    best_so_far = (
        np.maximum.accumulate(values)
        if direction == "maximize"
        else np.minimum.accumulate(values)
    )
    feasible = np.asarray(
        [_constraints_pass(row["metrics"], evaluation_metrics) for row in ordered],
        dtype=bool,
    )
    standard_deviations = np.asarray(
        [
            _per_seed_metric_std(row.get("per_seed_metrics", []), primary_name)
            for row in ordered
        ],
        dtype=float,
    )
    curve = _load_meaningful_training_curve(exp_dir, best_trial_id)

    if curve is None:
        fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True)
        _plot_trial_progress(
            axes[0],
            trial_numbers,
            values,
            best_so_far,
            feasible,
            standard_deviations,
            primary_name,
            direction,
        )
        _plot_constraint_progress(
            axes[1],
            trial_numbers,
            ordered,
            evaluation_metrics,
        )
        axes[1].set_xlabel("Trial execution order")
        subtitle = (
            "Trial-level evidence (no multi-step learning curve was emitted by train.py)"
        )
        data_level = "trial_evaluation"
        sources = ["leaderboard.csv", "trials/*/metrics.json"]
    else:
        has_training_evaluation = "evaluation_primary" in curve
        panel_count = 4 if has_training_evaluation else 3
        fig, axes = plt.subplots(panel_count, 1, figsize=(14, 13 if has_training_evaluation else 11))
        _plot_trial_progress(
            axes[0],
            trial_numbers,
            values,
            best_so_far,
            feasible,
            standard_deviations,
            primary_name,
            direction,
        )
        next_axis = 1
        if has_training_evaluation:
            axes[1].plot(
                curve["evaluation_primary_step"],
                curve["evaluation_primary"],
                color=_COLORS["green"],
                marker="o",
                linewidth=2,
            )
            axes[1].set_ylabel(primary_name)
            axes[1].set_title(
                f"Training-time evaluation: {primary_name} ({direction})"
            )
            _style_axis(axes[1])
            next_axis = 2
        reward_axis = axes[next_axis]
        loss_axis = axes[next_axis + 1]
        reward_series = False
        if "episode_reward" in curve:
            reward_axis.plot(
                curve["episode_reward_step"],
                curve["episode_reward"],
                color=_COLORS["gray"],
                alpha=0.38,
                linewidth=1.0,
                label="Episode reward",
            )
            reward_series = True
        reward_key = curve.get("reward_key")
        if reward_key:
            reward_axis.plot(
                curve[f"{reward_key}_step"],
                curve[reward_key],
                color=_COLORS["blue"],
                linewidth=2.2,
                label="Rolling reward mean",
            )
            reward_series = True
        if reward_series:
            reward_axis.set_ylabel("Reward")
            reward_axis.set_title("Learning reward (training signal only)")
            reward_axis.legend(frameon=False, ncol=2)
            _style_axis(reward_axis)
        loss_keys = [
            key for key in ("actor_loss", "critic_loss", "loss") if key in curve
        ]
        for key in loss_keys:
            loss_axis.plot(
                curve[f"{key}_step"],
                curve[key],
                marker="o",
                markersize=3,
                linewidth=1.6,
                label=key,
            )
        loss_axis.set_title("Optimization losses")
        loss_axis.set_ylabel("Loss")
        loss_axis.set_xlabel("Training step")
        if loss_keys:
            loss_axis.legend(frameon=False, ncol=len(loss_keys))
        else:
            loss_axis.text(
                0.5,
                0.5,
                "No loss column was emitted.",
                transform=loss_axis.transAxes,
                ha="center",
                va="center",
            )
        _style_axis(loss_axis)
        subtitle = f"Training-step curve from {curve['source']}"
        data_level = "training_step"
        sources = [
            "leaderboard.csv",
            "trials/*/metrics.json",
            str(curve["source"]),
        ]

    fig.suptitle(
        "Training Process | optimization trajectory and feasibility",
        fontsize=18,
        fontweight="bold",
        color=_COLORS["navy"],
        y=0.98,
    )
    fig.text(0.5, 0.945, subtitle, ha="center", fontsize=10, color=_COLORS["gray"])
    fig.tight_layout(rect=[0.03, 0.03, 0.98, 0.93])
    _save_figure(fig, path)
    return data_level, sources


def render_training_effect(
    path: Path,
    *,
    baseline_metrics: dict[str, float],
    best_metrics: dict[str, float],
    evaluation_metrics: dict[str, Any],
    best_trial_id: str,
    baseline_per_seed_metrics: list[dict[str, Any]] | None = None,
    best_per_seed_metrics: list[dict[str, Any]] | None = None,
    baseline_label: str = "Default baseline",
) -> dict[str, Any]:
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    direction = str(primary.get("direction", "maximize"))
    baseline_value = float(baseline_metrics[primary_name])
    best_value = float(best_metrics[primary_name])
    baseline_std = _per_seed_metric_std(
        baseline_per_seed_metrics or [],
        primary_name,
    )
    best_std = _per_seed_metric_std(
        best_per_seed_metrics or [],
        primary_name,
    )
    signed_delta = (
        best_value - baseline_value
        if direction == "maximize"
        else baseline_value - best_value
    )
    relative_delta = (
        signed_delta / abs(baseline_value) * 100.0
        if baseline_value != 0.0
        else None
    )

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.8))
    bars = axes[0].bar(
        [baseline_label, f"Best ({best_trial_id})"],
        [baseline_value, best_value],
        yerr=[baseline_std, best_std],
        capsize=6,
        color=[_COLORS["gray"], _COLORS["green"]],
        width=0.58,
    )
    axes[0].bar_label(
        bars,
        labels=[
            f"{baseline_value:.4g}\n± {baseline_std:.3g}",
            f"{best_value:.4g}\n± {best_std:.3g}",
        ],
        padding=4,
        fontsize=10,
    )
    axes[0].set_title(f"Primary metric: {primary_name} ({direction})")
    axes[0].set_ylabel(primary_name)
    _style_axis(axes[0])
    delta_text = f"direction-aware Δ = {signed_delta:+.4g}"
    if relative_delta is not None:
        delta_text += f"  ({relative_delta:+.1f}%)"
    axes[0].text(
        0.5,
        0.02,
        delta_text,
        transform=axes[0].transAxes,
        ha="center",
        va="bottom",
        color=_COLORS["navy"],
        fontweight="bold",
    )

    constraints = evaluation_metrics.get("hard_constraints", [])
    if constraints:
        positions = np.arange(len(constraints))
        width = 0.36
        baseline_ratios = [
            _constraint_ratio(baseline_metrics, item) for item in constraints
        ]
        best_ratios = [_constraint_ratio(best_metrics, item) for item in constraints]
        baseline_bars = axes[1].bar(
            positions - width / 2,
            baseline_ratios,
            width,
            label=baseline_label,
            color=_COLORS["gray"],
        )
        best_bars = axes[1].bar(
            positions + width / 2,
            best_ratios,
            width,
            label="Best",
            color=_COLORS["green"],
        )
        axes[1].bar_label(
            baseline_bars,
            labels=[f"{value:.3g}" for value in baseline_ratios],
            padding=3,
            fontsize=9,
            color=_COLORS["gray"],
        )
        axes[1].bar_label(
            best_bars,
            labels=[f"{value:.3g}" for value in best_ratios],
            padding=3,
            fontsize=9,
            color=_COLORS["green"],
        )
        axes[1].axhline(
            1.0,
            color=_COLORS["red"],
            linestyle="--",
            linewidth=1.5,
            label="Constraint boundary",
        )
        axes[1].set_xticks(
            positions,
            [str(item.get("name", "constraint")) for item in constraints],
            rotation=18,
            ha="right",
        )
        axes[1].set_ylabel("Constraint ratio (≤ 1 is feasible)")
        axes[1].set_title("Hard-constraint status")
        axes[1].legend(frameon=False, fontsize=9)
        _style_axis(axes[1])
    else:
        axes[1].axis("off")
        axes[1].text(
            0.5,
            0.5,
            "No hard constraints declared.",
            ha="center",
            va="center",
            fontsize=13,
            color=_COLORS["gray"],
        )

    fig.suptitle(
        "Training Effect | same-seed baseline comparison",
        fontsize=18,
        fontweight="bold",
        color=_COLORS["navy"],
    )
    fig.tight_layout(rect=[0.02, 0.03, 0.98, 0.92])
    _save_figure(fig, path)
    return {
        "primary_metric": primary_name,
        "direction": direction,
        "baseline_value": baseline_value,
        "baseline_std": baseline_std,
        "candidate_value": best_value,
        "candidate_std": best_std,
        "n_seeds": max(
            len(baseline_per_seed_metrics or []),
            len(best_per_seed_metrics or []),
        ),
        "direction_aware_delta": signed_delta,
        "relative_improvement_percent": relative_delta,
        "baseline_constraints_passed": _constraints_pass(
            baseline_metrics,
            evaluation_metrics,
        ),
        "candidate_constraints_passed": _constraints_pass(
            best_metrics,
            evaluation_metrics,
        ),
    }


def _render_text_panel(
    axis: plt.Axes,
    title: str,
    lines: list[str],
    color: str,
) -> None:
    axis.set_facecolor("#F8FAFC")
    for spine in axis.spines.values():
        spine.set_color("#D7E0E8")
        spine.set_linewidth(1.2)
    axis.set_xticks([])
    axis.set_yticks([])
    axis.text(
        0.06,
        0.94,
        title,
        transform=axis.transAxes,
        fontsize=13,
        fontweight="bold",
        color="white",
        va="top",
        bbox={"boxstyle": "round,pad=0.55", "facecolor": color, "edgecolor": color},
    )
    expanded_lines = [
        wrapped_line
        for line in lines
        for wrapped_line in (str(line).splitlines() or [""])
    ]
    layout_units = len(expanded_lines) + 0.16 * len(lines)
    line_step = min(0.052, 0.74 / max(layout_units, 1.0))
    font_size = max(7.2, min(9.2, 12.5 - 0.2 * len(expanded_lines)))
    y = 0.84
    for line in lines:
        wrapped_lines = str(line).splitlines() or [""]
        for wrapped_line in wrapped_lines:
            axis.text(
                0.06,
                y,
                wrapped_line,
                transform=axis.transAxes,
                fontsize=font_size,
                color=_COLORS["navy"],
                va="top",
            )
            y -= line_step
        y -= min(0.008, line_step * 0.16)


def _plot_trial_progress(
    axis: plt.Axes,
    trials: np.ndarray,
    values: np.ndarray,
    best_so_far: np.ndarray,
    feasible: np.ndarray,
    standard_deviations: np.ndarray,
    primary_name: str,
    direction: str,
) -> None:
    axis.plot(
        trials,
        values,
        color=_COLORS["gray"],
        alpha=0.7,
        linewidth=1.2,
        label="Trial metric",
    )
    axis.errorbar(
        trials,
        values,
        yerr=standard_deviations,
        fmt="none",
        ecolor=_COLORS["gray"],
        elinewidth=1.0,
        capsize=3,
        alpha=0.6,
        label="±1 SD across seeds",
    )
    axis.scatter(
        trials[feasible],
        values[feasible],
        color=_COLORS["green"],
        s=42,
        label="Feasible",
        zorder=3,
    )
    axis.scatter(
        trials[~feasible],
        values[~feasible],
        color=_COLORS["red"],
        marker="x",
        s=48,
        label="Infeasible",
        zorder=3,
    )
    axis.plot(
        trials,
        best_so_far,
        color=_COLORS["blue"],
        linewidth=2.5,
        label="Best so far",
    )
    axis.set_title(f"Evaluation progress: {primary_name} ({direction})")
    axis.set_ylabel(primary_name)
    axis.legend(frameon=False, ncol=3)
    _style_axis(axis)


def _plot_constraint_progress(
    axis: plt.Axes,
    trials: np.ndarray,
    rows: list[dict[str, Any]],
    evaluation_metrics: dict[str, Any],
) -> None:
    constraints = evaluation_metrics.get("hard_constraints", [])
    for constraint in constraints:
        ratios = [
            _constraint_ratio(row["metrics"], constraint) for row in rows
        ]
        axis.plot(
            trials,
            ratios,
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=str(constraint.get("name", "constraint")),
        )
    axis.axhline(
        1.0,
        color=_COLORS["red"],
        linestyle="--",
        linewidth=1.5,
        label="Constraint boundary",
    )
    axis.set_title("Hard-constraint trajectory")
    axis.set_ylabel("Constraint ratio (≤ 1 is feasible)")
    if constraints:
        axis.legend(frameon=False, ncol=min(4, len(constraints) + 1))
    _style_axis(axis)


def _load_meaningful_training_curve(
    exp_dir: Path,
    best_trial_id: str,
) -> dict[str, Any] | None:
    candidates = [
        exp_dir / "trials" / best_trial_id / "training_curves.csv",
        *sorted((exp_dir / "trials").glob("*/training_curves.csv")),
    ]
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
        if len(rows) < 2:
            continue
        steps = [_float_or_none(row.get("step")) for row in rows]
        if any(step is None for step in steps) or len(set(steps)) < 2:
            continue
        curve: dict[str, Any] = {"source": path.relative_to(exp_dir).as_posix()}
        for key in (
            "reward_mean",
            "episode_reward_mean",
            "reward",
            "episode_reward",
            "episode_length",
            "episode_success",
            "actor_loss",
            "critic_loss",
            "loss",
            "kl_divergence",
            "evaluation_primary",
        ):
            values = [_float_or_none(row.get(key)) for row in rows]
            points = [
                (float(step), float(value))
                for step, value in zip(steps, values, strict=True)
                if step is not None and value is not None
            ]
            if points:
                curve[f"{key}_step"] = np.asarray(
                    [point[0] for point in points],
                    dtype=float,
                )
                curve[key] = np.asarray(
                    [point[1] for point in points],
                    dtype=float,
                )
        for reward_key in ("reward_mean", "episode_reward_mean", "reward"):
            if reward_key in curve:
                curve["reward_key"] = reward_key
                break
        return curve
    return None


def _constraints_pass(
    metrics: dict[str, float],
    evaluation_metrics: dict[str, Any],
) -> bool:
    for constraint in evaluation_metrics.get("hard_constraints", []):
        name = str(constraint.get("name", ""))
        if name not in metrics:
            return False
        value = float(metrics[name])
        if "max" in constraint and value > float(constraint["max"]):
            return False
        if "min" in constraint and value < float(constraint["min"]):
            return False
    return True


def _constraint_ratio(
    metrics: dict[str, float],
    constraint: dict[str, Any],
) -> float:
    value = float(metrics[str(constraint["name"])])
    if "max" in constraint:
        limit = float(constraint["max"])
        if limit == 0.0:
            return 0.0 if value <= 0.0 else 1.0 + abs(value)
        return value / limit
    limit = float(constraint["min"])
    if limit == 0.0:
        return 0.0 if value >= 0.0 else 1.0 + abs(value)
    if value <= 0.0:
        return 2.0
    return limit / value


def _style_axis(axis: plt.Axes) -> None:
    axis.grid(axis="y", color="#D7E0E8", linewidth=0.8, alpha=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color("#AAB7C4")
    axis.spines["bottom"].set_color("#AAB7C4")


def _save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _constraint_text(constraint: dict[str, Any]) -> str:
    if "max" in constraint:
        return f"{constraint.get('name')} ≤ {constraint['max']}"
    if "min" in constraint:
        return f"{constraint.get('name')} ≥ {constraint['min']}"
    return str(constraint.get("name", "unnamed"))


def _shape_text(space: dict[str, Any]) -> str:
    return f"{space.get('type', 'unknown')} {space.get('shape', 'unknown')}"


def _format_list(values: Any) -> str:
    items = [str(item) for item in values if item not in (None, "")]
    return ", ".join(items) if items else "none"


def _baseline_label(identity: str) -> str:
    if identity == "policy.untrained_initialization":
        return "Untrained initialization"
    if identity == "policy.default_config_trained":
        return "Trained default config"
    return "Default baseline"


def _wrapped(value: str, *, width: int) -> str:
    return textwrap.fill(value, width=width)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _per_seed_metric_std(
    per_seed_metrics: list[dict[str, Any]],
    output_name: str,
) -> float:
    source_name = "episode_length" if output_name == "avg_episode_length" else output_name
    values = [
        float(item[source_name])
        for item in per_seed_metrics
        if source_name in item
    ]
    return float(np.std(values, ddof=0)) if values else 0.0
