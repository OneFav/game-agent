from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


FIG_DPI = 300
COLORS = {
    "red": "#B22222",
    "blue": "#1F77B4",
    "neutral": "#4D4D4D",
    "pass": "#2CA02C",
    "fail": "#D62728",
    "not_executed": "#8C8C8C",
}


def set_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "figure.dpi": FIG_DPI,
            "savefig.dpi": FIG_DPI,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "grid.linewidth": 0.6,
        }
    )


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_round_history(game_dir: Path) -> pd.DataFrame:
    with (game_dir / "round_history.json").open("r", encoding="utf-8") as handle:
        rows = json.load(handle)
    df = pd.DataFrame(rows)
    return df[df["status"].isin(["PASS", "FAIL_STOP"])].copy()


def load_trial_rows(root: Path, rounds: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, row in rounds.iterrows():
        exp_dir = root / row["exp_dir"]
        leaderboard = exp_dir / "leaderboard.csv"
        if not leaderboard.exists():
            continue
        trial_df = pd.read_csv(leaderboard)
        trial_df["round_id"] = int(row["round_id"])
        trial_df["round_status"] = row["status"]
        trial_df["round_target_side"] = row["target_side"]
        frames.append(trial_df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def save_both(fig: plt.Figure, out_dir: Path, stem: str) -> None:
    fig.savefig(out_dir / f"{stem}.pdf")
    fig.savefig(out_dir / f"{stem}.png")


def plot_round_dashboard(rounds: pd.DataFrame, out_dir: Path) -> None:
    rounds = rounds.sort_values("round_id")
    x = rounds["round_id"].astype(int).to_list()
    target_colors = [COLORS.get(side, COLORS["neutral"]) for side in rounds["target_side"]]

    fig, axes = plt.subplots(2, 2, figsize=(8.2, 5.6))
    ax = axes[0, 0]
    ax.plot(x, rounds["red_utility"], marker="o", color=COLORS["red"], label="Red utility")
    ax.plot(x, rounds["blue_utility"], marker="s", color=COLORS["blue"], label="Blue utility")
    for _, row in rounds.iterrows():
        if row["status"] == "FAIL_STOP":
            ax.axvline(row["round_id"], color=COLORS["fail"], linestyle="--", linewidth=1)
    ax.set_xlabel("Round")
    ax.set_ylabel("Utility")
    ax.set_xticks(x)
    ax.legend(frameon=False, loc="best")

    ax = axes[0, 1]
    bars = ax.bar(x, rounds["target_margin"], color=target_colors, alpha=0.88)
    ax.axhline(0, color="black", linewidth=0.8)
    for bar, status, val in zip(bars, rounds["status"], rounds["target_margin"]):
        label = "PASS" if status == "PASS" else "FAIL"
        va = "bottom" if val >= 0 else "top"
        y = val + (0.12 if val >= 0 else -0.12)
        ax.text(bar.get_x() + bar.get_width() / 2, y, label, ha="center", va=va, fontsize=8)
    ymin = min(-0.8, float(rounds["target_margin"].min()) - 0.8)
    ymax = max(0.8, float(rounds["target_margin"].max()) + 0.8)
    ax.set_ylim(ymin, ymax)
    ax.set_xlabel("Round")
    ax.set_ylabel("Target-side margin")
    ax.set_xticks(x)

    ax = axes[1, 0]
    width = 0.34
    left = [v - width / 2 for v in x]
    right = [v + width / 2 for v in x]
    ax.bar(left, rounds["coupling_delta"], width=width, color="#9467BD", label="Coupling delta")
    ax.bar(right, rounds["best_response_gain_side"], width=width, color="#FF7F0E", label="BR gain")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Round")
    ax.set_ylabel("Metric value")
    ax.set_xticks(x)
    ax.legend(frameon=False, loc="best")

    ax = axes[1, 1]
    metrics = ["collision_rate", "out_of_bounds_rate", "action_violation_rate"]
    offsets = [-0.24, 0.0, 0.24]
    palette = ["#7F7F7F", "#17BECF", "#BCBD22"]
    for metric, offset, color in zip(metrics, offsets, palette):
        ax.bar([v + offset for v in x], rounds[metric], width=0.22, label=metric.replace("_", " "), color=color)
    ax.axhline(0.05, color="#7F7F7F", linestyle="--", linewidth=0.8, label="collision threshold")
    ax.axhline(0.01, color="#17BECF", linestyle=":", linewidth=0.9, label="OOB threshold")
    ax.set_ylim(0, 0.06)
    ax.set_xlabel("Round")
    ax.set_ylabel("Rate")
    ax.set_xticks(x)
    ax.legend(frameon=False, loc="upper left", ncol=2, columnspacing=0.9, handlelength=1.8)

    fig.tight_layout()
    save_both(fig, out_dir, "current_round_dashboard")
    plt.close(fig)


def plot_trial_advantage(trials: pd.DataFrame, out_dir: Path) -> None:
    if trials.empty:
        return

    rounds = sorted(trials["round_id"].unique())
    data = [trials.loc[trials["round_id"] == rid, "advantage_score"].dropna().to_numpy() for rid in rounds]

    fig, ax = plt.subplots(1, 1, figsize=(6.8, 3.2))
    box = ax.boxplot(data, positions=rounds, widths=0.5, patch_artist=True, showfliers=False)
    for patch, rid in zip(box["boxes"], rounds):
        side = trials.loc[trials["round_id"] == rid, "round_target_side"].iloc[0]
        patch.set_facecolor(COLORS.get(side, COLORS["neutral"]))
        patch.set_alpha(0.26)
        patch.set_edgecolor(COLORS.get(side, COLORS["neutral"]))

    for rid in rounds:
        subset = trials[trials["round_id"] == rid].copy()
        color = COLORS.get(subset["round_target_side"].iloc[0], COLORS["neutral"])
        x_positions = [rid + ((i % 5) - 2) * 0.035 for i in range(len(subset))]
        ax.scatter(
            x_positions,
            subset["advantage_score"],
            s=18,
            color=color,
            edgecolor="white",
            linewidth=0.35,
            alpha=0.78,
        )
        promoted = subset[subset["decision"].astype(str).str.contains("promotion|promote", case=False, na=False)]
        ax.scatter(
            [rid] * len(promoted),
            promoted["advantage_score"],
            s=42,
            facecolor="none",
            edgecolor="black",
            linewidth=1.0,
            label="promotion gate" if rid == rounds[0] else None,
        )

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Round")
    ax.set_ylabel("Trial advantage score")
    ax.set_xticks(rounds)
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    save_both(fig, out_dir, "trial_advantage_distribution")
    plt.close(fig)


def write_metrics_csv(rounds: pd.DataFrame, out_dir: Path) -> None:
    cols = [
        "round_id",
        "target_side",
        "status",
        "red_utility",
        "blue_utility",
        "target_margin",
        "coupling_delta",
        "best_response_gain_side",
        "collision_rate",
        "out_of_bounds_rate",
        "action_violation_rate",
        "trial_count",
        "policy_code_edits",
    ]
    rounds[cols].sort_values("round_id").to_csv(out_dir / "current_round_metrics.csv", index=False)


def main() -> None:
    set_style()
    root = repo_root()
    game_dir = root / "game" / "vertical_wave_3v3"
    out_dir = game_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    rounds = load_round_history(game_dir)
    trials = load_trial_rows(root, rounds)
    write_metrics_csv(rounds, out_dir)
    plot_round_dashboard(rounds, out_dir)
    plot_trial_advantage(trials, out_dir)

    print(f"Saved figures and metrics to {out_dir}")


if __name__ == "__main__":
    main()
