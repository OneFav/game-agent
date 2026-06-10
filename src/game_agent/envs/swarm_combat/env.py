"""
集群对抗主环境
PettingZoo 风格的并行多智能体接口：reset / step
"""
from typing import Dict, List
import numpy as np

from game_agent.envs.swarm_combat.config import EnvConfig
from game_agent.envs.swarm_combat.dynamics import build_dynamics
from game_agent.envs.swarm_combat.entities import Drone, Gate, Team, Role
from game_agent.envs.swarm_combat.constraints import build_default_constraints
from game_agent.envs.swarm_combat.rewards import build_default_rewards
from game_agent.envs.swarm_combat.terminations import build_default_terminations


class SwarmCombatEnv:
    def __init__(self, cfg: EnvConfig = None):
        self.cfg = cfg or EnvConfig()
        self.rng = np.random.default_rng(self.cfg.seed)

        # 实体
        self.drones: List[Drone] = []
        self.gates: List[Gate] = []

        # 模块
        self.constraints = build_default_constraints(self.cfg)
        self.reward_components = build_default_rewards(self.cfg)
        self.terminations = build_default_terminations(self.cfg)

        # 运行时
        self.step_count = 0
        self.team_scores: Dict[Team, float] = {Team.RED: 0.0, Team.BLUE: 0.0}
        self.team_pass_count: Dict[Team, int] = {Team.RED: 0, Team.BLUE: 0}
        self.history = []  # 记录每步位置，供可视化
        self.collision_events = []
        self.last_pass_events = []

        self._build_gates()

    # ---------- 公共接口 ----------
    @property
    def n_agents(self) -> int:
        return self.cfg.n_red + self.cfg.n_blue

    @property
    def action_dim(self) -> int:
        return 3  # 双积分器：3D 加速度

    def reset(self, seed: int | None = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.step_count = 0
        self.team_scores = {Team.RED: 0.0, Team.BLUE: 0.0}
        self.team_pass_count = {Team.RED: 0, Team.BLUE: 0}
        self.history = []
        self.collision_events = []
        self.last_pass_events = []

        # 重置门冷却
        for g in self.gates:
            g.cooldown_remaining = {Team.RED: 0, Team.BLUE: 0}

        self._spawn_drones()
        self._record_history()
        obs = self._get_observations()
        info: dict = {}
        return obs, info

    def step(self, actions: Dict[int, np.ndarray]):
        """
        actions: {drone_id: np.ndarray(3,)}
        返回: obs, rewards, terminated, truncated, info
        """
        # 1) 记录上一步位置
        prev_positions = {d.id: d.position.copy() for d in self.drones}

        # 2) 推进动力学
        for d in self.drones:
            a = actions.get(d.id, np.zeros(self.action_dim, dtype=np.float32))
            a = np.asarray(a, dtype=np.float32).reshape(-1)[:self.action_dim]
            d.step(a, self.cfg.dt)

        # 3) 检测穿门事件
        pass_events = self._detect_gate_passes(prev_positions)

        # 4) 检查约束
        collision_triggered = False
        collision_reason = None
        collision_details = []
        oob_ids = []
        for c in self.constraints:
            violated, info = c.check(self.drones, self.gates, self.cfg.field)
            if not violated:
                continue
            detail = {"step": self.step_count + 1, "type": c.name, **info}
            collision_details.append(detail)
            if c.name == "out_of_bounds":
                oob_ids.extend(info.get("outs", []))
                if self.cfg.rules.out_of_bounds_ends_episode:
                    collision_triggered = True
                    collision_reason = "out_of_bounds"
            else:
                if self.cfg.rules.collision_ends_episode:
                    collision_triggered = True
                    collision_reason = c.name
        if collision_details:
            self.collision_events.extend(collision_details)

        # 5) 更新门冷却
        for g in self.gates:
            g.tick_cooldown()

        # 6) 推进步数
        self.step_count += 1

        # 7) 构造奖励上下文
        ctx = {
            "drones": self.drones,
            "gates": self.gates,
            "dt": self.cfg.dt,
            "step": self.step_count,
            "pass_events": pass_events,
            "collision_triggered": collision_triggered,
            "collision_reason": collision_reason,
            "collision_details": collision_details,
            "oob_ids": oob_ids,
            "team_scores": self.team_scores,
        }

        # 8) 计算奖励（组件累加）
        rewards = {d.id: 0.0 for d in self.drones}
        for comp in self.reward_components:
            partial = comp.compute(ctx)
            for k, v in partial.items():
                rewards[k] += v

        # 9) 团队积分仅由穿门事件累加（唯一指标）
        for ev in pass_events:
            if ev["scored"]:
                team = next(d.team for d in self.drones if d.id == ev["drone_id"])
                self.team_scores[team] += self.cfg.rewards.gate_pass
                self.team_pass_count[team] += 1
        self.last_pass_events = pass_events

        # 10) 终止判定
        terminated = False
        term_info = {}
        for t in self.terminations:
            done, info = t.check(ctx)
            if done:
                terminated = True
                term_info = info
                break

        self._record_history()

        # 按智能体构建 terminated / truncated
        terminated_dict = {d.id: terminated for d in self.drones}
        truncated_dict = {d.id: False for d in self.drones}
        if self.step_count >= self.cfg.max_steps and not terminated:
            truncated_dict = {d.id: True for d in self.drones}

        info_dict = {
            "pass_events": pass_events,
            "collision_events": collision_details,
            "team_scores": dict(self.team_scores),
            "team_pass_count": dict(self.team_pass_count),
            "termination": term_info,
            "step": self.step_count,
        }
        return self._get_observations(), rewards, terminated_dict, truncated_dict, info_dict

    # ---------- 内部 ----------
    def _build_gates(self):
        self.gates = [
            Gate(i, gc.center, gc.normal, gc.width, gc.height, gc.cooldown_steps, gc.pass_direction)
            for i, gc in enumerate(self.cfg.gates)
        ]

    def _spawn_drones(self):
        """生成红蓝双方无人机，本体同构，仅 role 不同
        初始化模式由 cfg.spawn_red / cfg.spawn_blue 独立控制
        """
        self.drones = []
        drone_id = 0
        # 红方
        red_positions = self._generate_team_positions(
            team=Team.RED, n=self.cfg.n_red, spawn_cfg=self.cfg.spawn_red
        )
        for k in range(self.cfg.n_red):
            role = Role.RACER if k < self.cfg.n_red_racers else Role.DEFENDER
            pos = red_positions[k]
            init_state = np.array([pos[0], pos[1], pos[2], 0, 0, 0], dtype=np.float32)
            self.drones.append(Drone(
                drone_id, Team.RED, role, self._build_dynamics(role),
                init_state, self.cfg.drone.safety_radius
            ))
            drone_id += 1

        # 蓝方
        blue_positions = self._generate_team_positions(
            team=Team.BLUE, n=self.cfg.n_blue, spawn_cfg=self.cfg.spawn_blue
        )
        for k in range(self.cfg.n_blue):
            role = Role.RACER if k < self.cfg.n_blue_racers else Role.DEFENDER
            pos = blue_positions[k]
            init_state = np.array([pos[0], pos[1], pos[2], 0, 0, 0], dtype=np.float32)
            self.drones.append(Drone(
                drone_id, Team.BLUE, role, self._build_dynamics(role),
                init_state, self.cfg.drone.safety_radius
            ))
            drone_id += 1

    def _build_dynamics(self, role: Role):
        type_key = "racer" if role == Role.RACER else "defender"
        type_cfg = self.cfg.drone_types.get(type_key)
        if type_cfg is None:
            return build_dynamics(
                "double_integrator",
                self.cfg.drone.max_speed,
                self.cfg.drone.max_accel,
            )
        max_speed = type_cfg.max_speed if type_cfg.max_speed is not None else self.cfg.drone.max_speed
        max_accel = type_cfg.max_accel if type_cfg.max_accel is not None else self.cfg.drone.max_accel
        return build_dynamics(type_cfg.dynamics, max_speed, max_accel, type_cfg.drag)


    def _generate_team_positions(self, team, n: int, spawn_cfg):
        """根据 spawn_cfg 生成 n 个起飞位置"""
        if spawn_cfg.mode == "fixed":
            return self._generate_fixed_positions(team, n, spawn_cfg)
        elif spawn_cfg.mode == "random":
            return self._generate_random_positions(n, spawn_cfg)
        else:
            raise ValueError(f"未知 spawn mode: {spawn_cfg.mode}")


    def _generate_fixed_positions(self, team, n: int, spawn_cfg):
        """固定模式：优先用用户提供的列表，不足则用默认排布补齐"""
        positions = []
        user_list = spawn_cfg.fixed_positions or []

        # 用户指定的部分
        for i in range(min(n, len(user_list))):
            positions.append(np.array(user_list[i], dtype=np.float32))

        # 默认排布补齐（沿 y 轴均匀排开）
        if len(positions) < n:
            # 根据队伍决定默认 x 起飞线
            default_x = -20.0 if team == Team.RED else 20.0
            # 用 random_*_range 的中心作为默认 z（避免再加新字段）
            default_z = 0.5 * (spawn_cfg.random_z_range[0] + spawn_cfg.random_z_range[1])
            # y 在 random_y_range 内均匀排开
            y_lo, y_hi = spawn_cfg.random_y_range
            remaining = n - len(positions)
            if remaining == 1:
                ys = [0.5 * (y_lo + y_hi)]
            else:
                ys = np.linspace(y_lo, y_hi, n)[len(positions):]
            for y in ys:
                positions.append(np.array([default_x, y, default_z], dtype=np.float32))

        return positions[:n]


    def _generate_random_positions(self, n: int, spawn_cfg):
        """随机模式：在指定 box 内均匀采样，保证彼此间距 >= min_separation"""
        positions = []
        rng = self.rng
        tries = 0
        while len(positions) < n and tries < spawn_cfg.max_resample_tries * n:
            cand = np.array([
                rng.uniform(*spawn_cfg.random_x_range),
                rng.uniform(*spawn_cfg.random_y_range),
                rng.uniform(*spawn_cfg.random_z_range),
            ], dtype=np.float32)
            ok = all(np.linalg.norm(cand - p) >= spawn_cfg.min_separation for p in positions)
            if ok:
                positions.append(cand)
            tries += 1

        if len(positions) < n:
            # 兜底：松弛间距强制填满，避免死循环
            print(f"[spawn] 警告：随机采样未能满足最小间距，已松弛约束补齐 ({len(positions)}/{n})")
            while len(positions) < n:
                cand = np.array([
                    rng.uniform(*spawn_cfg.random_x_range),
                    rng.uniform(*spawn_cfg.random_y_range),
                    rng.uniform(*spawn_cfg.random_z_range),
                ], dtype=np.float32)
                positions.append(cand)

        return positions


    def _detect_gate_passes(self, prev_positions: Dict[int, np.ndarray]):
        """
        每架无人机 × 每个门 检查穿越
        冷却期内的门穿过不计分（但事件仍记录，便于调试）
        """
        events = []
        for d in self.drones:
            for g in self.gates:
                intersects, intersection = g.check_intersection(prev_positions[d.id], d.position)
                if not intersects:
                    continue
                passed, _ = g.check_pass(prev_positions[d.id], d.position, d.team)
                scored = not g.is_on_cooldown(d.team)
                if passed and scored:
                    g.trigger_cooldown(d.team)
                    d.gate_pass_count += 1
                events.append({
                    "drone_id": d.id,
                    "gate_id": g.id,
                    "valid_direction": passed,
                    "scored": bool(passed and scored),
                    "team": d.team.name,
                    "intersection": None if intersection is None else intersection.copy(),
                })
        return events

    def _get_observations(self) -> Dict[int, np.ndarray]:
        """
        全局可观测：每架无人机的观测包含全场所有无人机状态 + 所有门状态
        observation = concat([
            self_state(6),
            for each other drone: rel_pos(3) + rel_vel(3) + team_flag(1) + role_flag(1),
            for each gate: rel_center(3) + normal(3) + cooldown_red(1) + cooldown_blue(1)
        ])
        """
        obs = {}
        for d in self.drones:
            parts = [d.state]
            for o in self.drones:
                if o.id == d.id:
                    continue
                rel_p = o.position - d.position
                rel_v = o.velocity - d.velocity
                team_flag = 1.0 if o.team == d.team else -1.0
                role_flag = 1.0 if o.role == Role.RACER else -1.0
                parts.append(np.concatenate([rel_p, rel_v, [team_flag, role_flag]]))
            for g in self.gates:
                rel_c = g.center - d.position
                cd_r = g.cooldown_remaining[Team.RED] / max(g.cooldown_steps, 1)
                cd_b = g.cooldown_remaining[Team.BLUE] / max(g.cooldown_steps, 1)
                parts.append(np.concatenate([rel_c, g.normal, [cd_r, cd_b]]))
            obs[d.id] = np.concatenate(parts).astype(np.float32)
        return obs

    def _record_history(self):
        snapshot = {
            "step": self.step_count,
            "drones": [
                {
                    "id": d.id, "team": d.team.name, "role": d.role.name,
                    "pos": d.position.copy(), "vel": d.velocity.copy(),
                }
                for d in self.drones
            ],
            "gates": [
                {
                    "id": g.id,
                    "cd_red": g.cooldown_remaining[Team.RED],
                    "cd_blue": g.cooldown_remaining[Team.BLUE],
                    "cd_max": g.cooldown_steps,
                }
                for g in self.gates
            ],
            "scores": dict(self.team_scores),
            "pass_events": [
                {
                    **ev,
                    "intersection": None if ev.get("intersection") is None else ev["intersection"].copy(),
                }
                for ev in self.last_pass_events
            ],
            "collision_events": list(self.collision_events),
        }
        self.history.append(snapshot)
