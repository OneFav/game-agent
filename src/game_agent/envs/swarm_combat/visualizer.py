"""
简单的 matplotlib 3D 可视化
- 门的颜色和透明度反映冷却状态
- 门标签实时显示红/蓝双方剩余冷却步数
"""
import numpy as np
from game_agent.envs.swarm_combat.matplotlib_compat import patch_matplotlib_cbook

patch_matplotlib_cbook()
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection


TEAM_COLORS = {"RED": "#d62728", "BLUE": "#1f77b4"}
ROLE_MARKERS = {"RACER": "o", "DEFENDER": "^"}

# 门冷却配色
GATE_COLOR_IDLE = "#bdbdbd"      # 双方都不在冷却：灰色
GATE_COLOR_RED_CD = "#d62728"    # 仅红方冷却
GATE_COLOR_BLUE_CD = "#1f77b4"   # 仅蓝方冷却
GATE_COLOR_BOTH_CD = "#8e44ad"   # 双方都冷却：紫色


def _gate_corners(gate):
    """返回门的四个角点 (4,3)"""
    c = gate.center
    th = gate.tangent_h
    tv = gate.tangent_v
    w, h = gate.width / 2, gate.height / 2
    return np.array([
        c + th * w + tv * h,
        c - th * w + tv * h,
        c - th * w - tv * h,
        c + th * w - tv * h,
    ])


def _gate_style_from_cd(cd_red: int, cd_blue: int, cd_max: int):
    """
    根据冷却剩余步数返回 (edge_color, face_color, alpha, edge_width)
    冷却越深，alpha 越高（更"实心"），表示门处于"封锁"状态
    """
    r_active = cd_red > 0
    b_active = cd_blue > 0

    if r_active and b_active:
        edge = GATE_COLOR_BOTH_CD
    elif r_active:
        edge = GATE_COLOR_RED_CD
    elif b_active:
        edge = GATE_COLOR_BLUE_CD
    else:
        edge = "black"

    face = GATE_COLOR_IDLE if not (r_active or b_active) else edge

    # alpha：基础 0.15，随最大冷却比例线性增加到 0.6
    cd_ratio = max(cd_red, cd_blue) / max(cd_max, 1)
    alpha = 0.15 + 0.45 * cd_ratio

    edge_width = 1.0 + 2.0 * cd_ratio  # 冷却越深，边框越粗

    return edge, face, alpha, edge_width


def _make_gate_label(gate_id, cd_red, cd_blue):
    """门标签文本"""
    parts = [f"G{gate_id}"]
    if cd_red > 0:
        parts.append(f"R:{cd_red}")
    if cd_blue > 0:
        parts.append(f"B:{cd_blue}")
    return " ".join(parts)


def _marker_segments_3d(point, size: float = 0.35):
    p = np.asarray(point, dtype=np.float32)
    return [
        np.array([[p[0] - size, p[1], p[2]], [p[0] + size, p[1], p[2]]]),
        np.array([[p[0], p[1] - size, p[2]], [p[0], p[1] + size, p[2]]]),
        np.array([[p[0], p[1], p[2] - size], [p[0], p[1], p[2] + size]]),
    ]


def render_animation(env, save_path: str = None, interval_ms: int = 50):
    """根据 env.history 生成动画（含门冷却动态显示）"""
    patch_matplotlib_cbook()
    if not env.history:
        print("[viz] history 为空，请先 reset/step")
        return
    if "gates" not in env.history[0]:
        print("[viz] 警告：history 中缺少 gates 快照，门冷却将无法显示。"
              "请确保 env._record_history 已记录门状态。")

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    fc = env.cfg.field
    ax.set_xlim(fc.x_range); ax.set_ylim(fc.y_range); ax.set_zlim(fc.z_range)
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")

    # ---- 门：每个门一个 Poly3DCollection + 一个 text ----
    gate_polys = {}
    gate_texts = {}
    for g in env.gates:
        corners = _gate_corners(g)
        poly = Poly3DCollection([corners], alpha=0.2,
                                facecolor=GATE_COLOR_IDLE,
                                edgecolor="black", linewidths=1.0)
        ax.add_collection3d(poly)
        gate_polys[g.id] = poly

        c = g.center
        h = g.height / 2
        txt = ax.text(c[0], c[1], c[2] + h + 0.4, f"G{g.id}",
                      color="black", fontsize=8, ha="center")
        gate_texts[g.id] = txt

    # ---- 无人机位置标记 + 轨迹 ----
    markers = {}
    for snap_drone in env.history[0]["drones"]:
        team = snap_drone["team"]; role = snap_drone["role"]
        p0 = snap_drone["pos"]
        marker = Line3DCollection(_marker_segments_3d(p0), colors=[TEAM_COLORS[team]], linewidths=1.8,
                                  label=f"D{snap_drone['id']}-{team[0]}-{role[0]}")
        ax.add_collection3d(marker)
        markers[snap_drone["id"]] = marker

    trails = {}
    for d in env.history[0]["drones"]:
        p0 = d["pos"]
        trail = Line3DCollection([np.array([p0, p0])], colors=[TEAM_COLORS[d["team"]]], linewidths=1.0, alpha=0.4)
        ax.add_collection3d(trail)
        trails[d["id"]] = trail

    title = ax.set_title("")

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, loc="upper right", fontsize=7, ncol=2)

    # 门冷却图例（手工加几条说明）
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=GATE_COLOR_IDLE, edgecolor="black", label="Gate idle"),
        Patch(facecolor=GATE_COLOR_RED_CD, edgecolor=GATE_COLOR_RED_CD, label="RED cooling"),
        Patch(facecolor=GATE_COLOR_BLUE_CD, edgecolor=GATE_COLOR_BLUE_CD, label="BLUE cooling"),
        Patch(facecolor=GATE_COLOR_BOTH_CD, edgecolor=GATE_COLOR_BOTH_CD, label="BOTH cooling"),
    ]
    leg2 = ax.legend(handles=legend_elements, loc="upper left", fontsize=7, title="Gate state")
    ax.add_artist(leg2)

    # 把无人机图例重新加回去（add_artist 之后会被替换）
    if handles:
        ax.legend(handles, labels, loc="upper right", fontsize=7, ncol=2)

    def update(frame_idx):
        snap = env.history[frame_idx]

        # 更新无人机
        for d in snap["drones"]:
            p = d["pos"]
            markers[d["id"]].set_segments(_marker_segments_3d(p, size=0.35))
            past = np.array([s["drones"][d["id"]]["pos"]
                             for s in env.history[:frame_idx + 1]])
            if len(past) == 1:
                past = np.array([past[0], past[0]])
            trails[d["id"]].set_segments([past])

        # 更新门
        gate_snaps = snap.get("gates", [])
        for gs in gate_snaps:
            gid = gs["id"]
            cd_r = gs["cd_red"]; cd_b = gs["cd_blue"]; cd_max = gs["cd_max"]
            edge, face, alpha, lw = _gate_style_from_cd(cd_r, cd_b, cd_max)
            poly = gate_polys[gid]
            poly.set_facecolor(face)
            poly.set_edgecolor(edge)
            poly.set_alpha(alpha)
            poly.set_linewidth(lw)
            gate_texts[gid].set_text(_make_gate_label(gid, cd_r, cd_b))
            # 标签颜色跟边框走，方便一眼识别
            gate_texts[gid].set_color(edge if (cd_r > 0 or cd_b > 0) else "black")

        # 标题：分数 + 步数
        scores = snap["scores"]
        red = _score_of(scores, "RED")
        blue = _score_of(scores, "BLUE")
        title.set_text(f"Step {snap['step']}  |  RED {red:.0f}  vs  BLUE {blue:.0f}")

        return (list(markers.values()) + list(trails.values())
                + list(gate_polys.values()) + list(gate_texts.values()) + [title])

    anim = FuncAnimation(fig, update, frames=len(env.history),
                         interval=interval_ms, blit=False, repeat=False)
    fig._swarm_combat_animation = anim

    if save_path:
        try:
            anim.save(save_path, fps=int(1000 / interval_ms))
            print(f"[viz] 动画保存到 {save_path}")
        except Exception as e:
            print(f"[viz] 保存失败：{e}，改为直接显示")
            plt.show()
    else:
        plt.show()
    return anim


def _score_of(scores: dict, team_name: str):
    for k, v in scores.items():
        ks = k.name if hasattr(k, "name") else str(k)
        if ks == team_name:
            return v
    return 0


def render_snapshot(env, step_idx: int = -1):
    """单帧静态图（也展示门冷却）"""
    patch_matplotlib_cbook()
    snap = env.history[step_idx]
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    fc = env.cfg.field
    ax.set_xlim(fc.x_range); ax.set_ylim(fc.y_range); ax.set_zlim(fc.z_range)

    gate_snaps = {gs["id"]: gs for gs in snap.get("gates", [])}
    for g in env.gates:
        corners = _gate_corners(g)
        gs = gate_snaps.get(g.id, {"cd_red": 0, "cd_blue": 0, "cd_max": g.cooldown_steps})
        edge, face, alpha, lw = _gate_style_from_cd(gs["cd_red"], gs["cd_blue"], gs["cd_max"])
        poly = Poly3DCollection([corners], alpha=alpha, facecolor=face,
                                edgecolor=edge, linewidths=lw)
        ax.add_collection3d(poly)
        c = g.center; h = g.height / 2
        ax.text(c[0], c[1], c[2] + h + 0.4,
                _make_gate_label(g.id, gs["cd_red"], gs["cd_blue"]),
                color=edge if (gs["cd_red"] > 0 or gs["cd_blue"] > 0) else "black",
                fontsize=8, ha="center")

    for d in snap["drones"]:
        p = d["pos"]
        ax.add_collection3d(Line3DCollection(
            _marker_segments_3d(p, size=0.4),
            colors=[TEAM_COLORS[d["team"]]],
            linewidths=1.8,
        ))
    ax.set_title(f"Snapshot @ step {snap['step']}  scores={snap['scores']}")
    plt.show()


def save_trajectory_figure(env, save_path: str, title: str = "Trajectory Overview"):
    """保存适合论文插图的多子图轨迹图：3D、俯视、比分、穿门次数。"""
    patch_matplotlib_cbook()
    if not env.history:
        raise ValueError("env.history 为空，请先运行一局仿真")

    fig = plt.figure(figsize=(13, 9))
    ax3d = fig.add_subplot(2, 2, 1, projection="3d")
    ax_top = fig.add_subplot(2, 2, 2)
    ax_score = fig.add_subplot(2, 2, 3)
    ax_pass = fig.add_subplot(2, 2, 4)

    _draw_3d_scene(env, ax3d)
    _draw_top_down(env, ax_top)
    _draw_score_panel(env, ax_score)
    _draw_pass_panel(env, ax_pass)

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(save_path, dpi=220)
    plt.close(fig)


def save_topdown_figure(env, save_path: str, title: str = "Top-down Trajectory"):
    """保存俯视轨迹图，标注有效穿门和无效穿门事件。"""
    patch_matplotlib_cbook()
    if not env.history:
        raise ValueError("env.history 为空，请先运行一局仿真")
    fig, ax = plt.subplots(figsize=(9, 8))
    _draw_top_down(env, ax)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(save_path, dpi=220)
    plt.close(fig)


def _draw_3d_scene(env, ax):
    fc = env.cfg.field
    ax.set_xlim(fc.x_range); ax.set_ylim(fc.y_range); ax.set_zlim(fc.z_range)
    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
    for g in env.gates:
        corners = _gate_corners(g)
        poly = Poly3DCollection([corners], alpha=0.12,
                                facecolor=GATE_COLOR_IDLE,
                                edgecolor="black", linewidths=1.0)
        ax.add_collection3d(poly)
        ax.text(g.center[0], g.center[1], g.center[2] + g.height / 2 + 0.4,
                f"G{g.id}", fontsize=8, ha="center")

    for drone in env.history[0]["drones"]:
        did = drone["id"]
        team = drone["team"]
        role = drone["role"]
        points = np.array([snap["drones"][did]["pos"] for snap in env.history])
        line = Line3DCollection([points], colors=[TEAM_COLORS[team]], linewidths=1.2, alpha=0.75)
        line.set_label(f"D{did}-{team[0]}-{role[0]}")
        ax.add_collection3d(line)
        p = points[-1]
        marker_size = 0.35
        marker_segments = [
            np.array([[p[0] - marker_size, p[1], p[2]], [p[0] + marker_size, p[1], p[2]]]),
            np.array([[p[0], p[1] - marker_size, p[2]], [p[0], p[1] + marker_size, p[2]]]),
            np.array([[p[0], p[1], p[2] - marker_size], [p[0], p[1], p[2] + marker_size]]),
        ]
        ax.add_collection3d(Line3DCollection(marker_segments, colors=[TEAM_COLORS[team]], linewidths=1.6))
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title("3D trajectory")


def _draw_top_down(env, ax):
    fc = env.cfg.field
    ax.set_xlim(fc.x_range); ax.set_ylim(fc.y_range)
    ax.set_xlabel("X"); ax.set_ylabel("Y")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25)

    for g in env.gates:
        corners = _gate_corners(g)
        closed = np.vstack([corners, corners[0]])
        ax.plot(closed[:, 0], closed[:, 1], color="black", linewidth=1.0)
        ax.text(g.center[0], g.center[1], f"G{g.id}", fontsize=8, ha="center", va="center")

    for drone in env.history[0]["drones"]:
        did = drone["id"]
        team = drone["team"]
        role = drone["role"]
        points = np.array([snap["drones"][did]["pos"] for snap in env.history])
        ax.plot(points[:, 0], points[:, 1], color=TEAM_COLORS[team],
                linewidth=1.5 if role == "RACER" else 1.0,
                alpha=0.8, label=f"D{did}-{team[0]}-{role[0]}")
        ax.scatter(points[0, 0], points[0, 1], c=TEAM_COLORS[team], marker="x", s=45)
        ax.scatter(points[-1, 0], points[-1, 1], c=TEAM_COLORS[team],
                   marker=ROLE_MARKERS[role], s=45, edgecolors="black", linewidths=0.5)

    for snap in env.history:
        for ev in snap.get("pass_events", []):
            p = ev.get("intersection")
            if p is None:
                continue
            color = TEAM_COLORS.get(ev["team"], "black")
            marker = "*" if ev.get("scored") else "o"
            alpha = 0.9 if ev.get("scored") else 0.25
            ax.scatter(p[0], p[1], c=color, marker=marker, s=80, alpha=alpha,
                       edgecolors="black", linewidths=0.4)
            if ev.get("scored"):
                ax.text(p[0], p[1], f"G{ev['gate_id']}", fontsize=7, color=color)

    ax.legend(fontsize=7, loc="upper right", ncol=2)
    ax.set_title("Top-down view")


def _draw_score_panel(env, ax):
    steps = [snap["step"] for snap in env.history]
    red_scores = [_score_of(snap["scores"], "RED") for snap in env.history]
    blue_scores = [_score_of(snap["scores"], "BLUE") for snap in env.history]
    ax.plot(steps, red_scores, color=TEAM_COLORS["RED"], label="RED")
    ax.plot(steps, blue_scores, color=TEAM_COLORS["BLUE"], label="BLUE")
    ax.set_xlabel("Step"); ax.set_ylabel("Score")
    ax.grid(True, alpha=0.25)
    ax.legend()
    ax.set_title("Real-time score panel")


def _draw_pass_panel(env, ax):
    steps = [snap["step"] for snap in env.history]
    red_passes, blue_passes = [], []
    r = b = 0
    for snap in env.history:
        for ev in snap.get("pass_events", []):
            if not ev.get("scored"):
                continue
            if ev["team"] == "RED":
                r += 1
            elif ev["team"] == "BLUE":
                b += 1
        red_passes.append(r)
        blue_passes.append(b)
    ax.step(steps, red_passes, where="post", color=TEAM_COLORS["RED"], label="RED passes")
    ax.step(steps, blue_passes, where="post", color=TEAM_COLORS["BLUE"], label="BLUE passes")
    ax.set_xlabel("Step"); ax.set_ylabel("Pass count")
    ax.grid(True, alpha=0.25)
    ax.legend()
    ax.set_title("Gate pass events")
