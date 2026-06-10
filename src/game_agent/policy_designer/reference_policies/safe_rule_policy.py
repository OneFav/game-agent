"""规则策略：正常直奔目标，出现碰撞风险时全力刹车。"""
from typing import Dict

import numpy as np

from game_agent.envs.swarm_combat.entities import Role, Team


class SafeRulePolicy:
    def __init__(
        self,
        desired_speed: float = 4.0,
        position_gain: float = 1.2,
        velocity_gain: float = 2.2,
        risk_margin: float = 0.6,
        boundary_margin: float = 1.2,
        turn_steps: int = 12,
        turn_lookahead: float = 5.0,
        risk_lookahead_steps: int = 18,
        brake_release_speed: float = 0.35,
        lane_spacing: float = 1.2,
        gate_approach_offset: float = 4.0,
        gate_exit_offset: float = 3.0,
        separation_gain: float = 4.0,
        defender_mode: str = "escort",
    ):
        self.desired_speed = desired_speed
        self.position_gain = position_gain
        self.velocity_gain = velocity_gain
        self.risk_margin = risk_margin
        self.boundary_margin = boundary_margin
        self.turn_steps = turn_steps
        self.turn_lookahead = turn_lookahead
        self.risk_lookahead_steps = risk_lookahead_steps
        self.brake_release_speed = brake_release_speed
        self.lane_spacing = lane_spacing
        self.gate_approach_offset = gate_approach_offset
        self.gate_exit_offset = gate_exit_offset
        self.separation_gain = separation_gain
        self.defender_mode = defender_mode
        self.gate_indices = {}
        self.gate_steps = {}
        self.pass_counts = {}
        self.turn_remaining = {}
        self.braking = {}

    def reset(self, env) -> None:
        """每局 reset 后调用，初始化赛车机的目标环序。"""
        self.gate_indices = {}
        self.gate_steps = {}
        self.pass_counts = {}
        self.turn_remaining = {}
        self.braking = {}
        for drone in env.drones:
            self.pass_counts[drone.id] = drone.gate_pass_count
            self.turn_remaining[drone.id] = 0
            self.braking[drone.id] = False
            if drone.role != Role.RACER or not env.gates:
                continue
            self.gate_indices[drone.id] = 0 if drone.team == Team.RED else len(env.gates) - 1
            self.gate_steps[drone.id] = self._team_gate_step(drone.team)

    def compute_actions(self, env) -> Dict[int, np.ndarray]:
        if set(self.pass_counts) != {d.id for d in env.drones}:
            self.reset(env)

        self._update_racer_plans(env)
        actions = {d.id: self._nominal_action(env, d) for d in env.drones}
        predicted = {
            d.id: d.dynamics.get_position(d.dynamics.step(d.state, actions[d.id], env.cfg.dt))
            for d in env.drones
        }

        for d in env.drones:
            has_risk = self._has_collision_risk(env, d, actions[d.id], predicted[d.id], predicted)
            speed = np.linalg.norm(d.velocity)
            if self.braking.get(d.id, False):
                has_risk = has_risk or speed > self.brake_release_speed or self._too_close_to_any_drone(env, d)

            self.braking[d.id] = has_risk
            if has_risk:
                actions[d.id] = self._full_brake_action(env, d)
            else:
                actions[d.id] = self._limit_norm(actions[d.id], self._max_accel(d)).astype(np.float32)

        return actions

    def _nominal_action(self, env, drone) -> np.ndarray:
        target = self._select_target(env, drone)
        to_target = target - drone.position
        desired_velocity = self._limit_norm(
            to_target * self.position_gain,
            min(self.desired_speed, self._max_speed(drone)),
        )
        accel = (desired_velocity - drone.velocity) * self.velocity_gain
        accel += self._separation_action(env, drone)
        accel += self._boundary_action(env, drone)
        return self._limit_norm(accel, self._max_accel(drone)).astype(np.float32)

    def _select_target(self, env, drone) -> np.ndarray:
        if drone.role == Role.RACER:
            return self._racer_target(env, drone)
        return self._defender_target(env, drone)

    def _racer_target(self, env, drone) -> np.ndarray:
        if not env.gates:
            return drone.position

        gate = env.gates[self.gate_indices.get(drone.id, 0) % len(env.gates)]
        crossing_dir = self._team_crossing_dir(drone.team, gate)
        lane = self._racer_lane_offset(env, drone, gate)
        signed_dist = float(np.dot(drone.position - gate.center, crossing_dir))
        local_to_lane = drone.position - (gate.center + lane)
        lateral_error = max(abs(float(np.dot(local_to_lane, gate.tangent_h))),
                            abs(float(np.dot(local_to_lane, gate.tangent_v))))
        align_threshold = max(min(gate.width, gate.height) / 2 - env.cfg.drone.safety_radius - 0.25, 0.5)
        needs_alignment = lateral_error > align_threshold and signed_dist < -1.0
        if signed_dist > -0.25 or needs_alignment:
            center_target = gate.center + lane - crossing_dir * self.gate_approach_offset
        else:
            center_target = gate.center + lane + crossing_dir * self.gate_exit_offset
        if self.turn_remaining.get(drone.id, 0) <= 0:
            return center_target

        to_gate = center_target - drone.position
        gate_dir = self._unit(to_gate)
        velocity_dir = self._unit(drone.velocity)
        if np.linalg.norm(velocity_dir) < 1e-6:
            velocity_dir = gate_dir

        turn_dir = self._unit(0.5 * velocity_dir + 0.5 * gate_dir)
        if np.linalg.norm(turn_dir) < 1e-6:
            return center_target
        return drone.position + turn_dir * self.turn_lookahead

    def _racer_lane_offset(self, env, drone, gate) -> np.ndarray:
        racers = [d for d in env.drones if d.team == drone.team and d.role == Role.RACER]
        racers.sort(key=lambda d: d.id)
        if len(racers) <= 1 or drone not in racers:
            return np.zeros(3, dtype=np.float32)

        idx = racers.index(drone)
        centered_idx = idx - (len(racers) - 1) / 2
        max_offset = max(gate.width / 2 - env.cfg.drone.safety_radius - 0.05, 0.0)
        offset = float(np.clip(centered_idx * self.lane_spacing, -max_offset, max_offset))
        return (gate.tangent_h * offset).astype(np.float32)

    def _defender_target(self, env, drone) -> np.ndarray:
        if self.defender_mode == "intercept":
            opponents = [d for d in env.drones if d.team != drone.team and d.role == Role.RACER]
            if opponents:
                target = min(opponents, key=lambda other: np.linalg.norm(other.position - drone.position))
                return target.position

        mates = [d for d in env.drones if d.team == drone.team and d.role == Role.RACER]
        if not mates:
            return drone.position
        target = min(mates, key=lambda other: np.linalg.norm(other.position - drone.position))
        team_dir = np.array([1.0, 0.0, 0.0], dtype=np.float32) if drone.team == Team.RED else np.array([-1.0, 0.0, 0.0], dtype=np.float32)
        return target.position - team_dir * 2.5 + np.array([0.0, 0.0, 1.0], dtype=np.float32)

    def _update_racer_plans(self, env) -> None:
        for drone in env.drones:
            if drone.role != Role.RACER or not env.gates:
                self.pass_counts[drone.id] = drone.gate_pass_count
                continue

            previous_count = self.pass_counts.get(drone.id, drone.gate_pass_count)
            if drone.gate_pass_count > previous_count:
                step = self.gate_steps.get(drone.id, 1)
                self.gate_indices[drone.id] = (self.gate_indices.get(drone.id, 0) + step) % len(env.gates)
                self.turn_remaining[drone.id] = self.turn_steps
            elif self.turn_remaining.get(drone.id, 0) > 0:
                self.turn_remaining[drone.id] -= 1

            self.pass_counts[drone.id] = drone.gate_pass_count

    def _initial_gate_index(self, env, drone) -> int:
        return int(np.argmin([np.linalg.norm(g.center - drone.position) for g in env.gates]))

    def _full_brake_action(self, env, drone) -> np.ndarray:
        if np.linalg.norm(drone.velocity) < 1e-6:
            return np.zeros(3, dtype=np.float32)
        return (-self._unit(drone.velocity) * self._max_accel(drone)).astype(np.float32)

    def _has_collision_risk(self, env, drone, action, next_pos, predicted) -> bool:
        for other in env.drones:
            if other.id == drone.id:
                continue

            safe_dist = (
                env.cfg.drone.intra_team_safe_dist
                if other.team == drone.team
                else env.cfg.drone.inter_team_safe_dist
            )
            risk_dist = safe_dist + self.risk_margin
            if np.linalg.norm(drone.position - other.position) < risk_dist:
                return True
            if np.linalg.norm(next_pos - predicted[other.id]) < risk_dist:
                return True

        if self._is_boundary_risk(env, next_pos):
            return True

        if self._segment_hits_gate_frame(env, drone.position, next_pos):
            return True

        return self._lookahead_has_risk(env, drone, action)

    def _too_close_to_any_drone(self, env, drone) -> bool:
        for other in env.drones:
            if other.id == drone.id:
                continue
            safe_dist = (
                env.cfg.drone.intra_team_safe_dist
                if other.team == drone.team
                else env.cfg.drone.inter_team_safe_dist
            )
            if np.linalg.norm(drone.position - other.position) < safe_dist + self.risk_margin:
                return True
        return False

    def _lookahead_has_risk(self, env, drone, action) -> bool:
        state = drone.state.copy()
        prev_pos = drone.position.copy()
        other_states = {other.id: other.state.copy() for other in env.drones if other.id != drone.id}
        speed = np.linalg.norm(drone.velocity)
        stop_time = speed / max(self._max_accel(drone), 1e-6)
        lookahead_steps = min(
            self.risk_lookahead_steps,
            max(2, int(np.ceil((stop_time + 0.3) / env.cfg.dt))),
        )

        for _ in range(lookahead_steps):
            state = drone.dynamics.step(state, action, env.cfg.dt)
            pos = drone.dynamics.get_position(state)

            if self._is_boundary_risk(env, pos):
                return True
            if self._segment_hits_gate_frame(env, prev_pos, pos):
                return True

            for other in env.drones:
                if other.id == drone.id:
                    continue
                other_states[other.id] = other.dynamics.step(
                    other_states[other.id],
                    np.zeros(env.action_dim, dtype=np.float32),
                    env.cfg.dt,
                )
                other_pos = other.dynamics.get_position(other_states[other.id])
                safe_dist = (
                    env.cfg.drone.intra_team_safe_dist
                    if other.team == drone.team
                    else env.cfg.drone.inter_team_safe_dist
                )
                if np.linalg.norm(pos - other_pos) < safe_dist + self.risk_margin:
                    return True

            prev_pos = pos

        return False

    def _position_in_field(self, env, pos) -> bool:
        x, y, z = pos
        return (
            env.cfg.field.x_range[0] <= x <= env.cfg.field.x_range[1]
            and env.cfg.field.y_range[0] <= y <= env.cfg.field.y_range[1]
            and env.cfg.field.z_range[0] <= z <= env.cfg.field.z_range[1]
        )

    def _is_boundary_risk(self, env, pos) -> bool:
        if not self._position_in_field(env, pos):
            return True

        ranges = [env.cfg.field.x_range, env.cfg.field.y_range, env.cfg.field.z_range]
        for axis, (lo, hi) in enumerate(ranges):
            if pos[axis] - lo < self.boundary_margin or hi - pos[axis] < self.boundary_margin:
                return True
        return False

    def _segment_hits_gate_frame(self, env, start, end) -> bool:
        return self._position_hits_gate_frame(env, end) or any(
            self._line_hits_gate_frame(gate, start, end, env.cfg.drone.safety_radius)
            for gate in env.gates
        )

    def _position_hits_gate_frame(self, env, pos) -> bool:
        radius = env.cfg.drone.safety_radius
        for gate in env.gates:
            plane_dist = abs(np.dot(pos - gate.center, gate.normal))
            if plane_dist > radius:
                continue

            local = pos - gate.center
            u = np.dot(local, gate.tangent_h)
            v = np.dot(local, gate.tangent_v)
            near_frame_u = abs(u) > gate.width / 2 - radius and abs(u) < gate.width / 2 + radius
            near_frame_v = abs(v) > gate.height / 2 - radius and abs(v) < gate.height / 2 + radius
            outside_box = abs(u) > gate.width / 2 or abs(v) > gate.height / 2
            if outside_box and (near_frame_u or near_frame_v):
                return True
        return False

    @staticmethod
    def _line_hits_gate_frame(gate, start, end, radius: float) -> bool:
        d_start = np.dot(start - gate.center, gate.normal)
        d_end = np.dot(end - gate.center, gate.normal)
        if d_start * d_end > 0 or abs(d_end - d_start) < 1e-9:
            return False

        t = d_start / (d_start - d_end)
        if t < 0.0 or t > 1.0:
            return False

        intersection = start + t * (end - start)
        local = intersection - gate.center
        u = np.dot(local, gate.tangent_h)
        v = np.dot(local, gate.tangent_v)
        safe_width = max(gate.width / 2 - radius, 0.0)
        safe_height = max(gate.height / 2 - radius, 0.0)
        return abs(u) > safe_width or abs(v) > safe_height

    def _separation_action(self, env, drone) -> np.ndarray:
        accel = np.zeros(3, dtype=np.float32)
        for other in env.drones:
            if other.id == drone.id:
                continue
            delta = drone.position - other.position
            dist = np.linalg.norm(delta)
            if dist < 1e-6:
                continue
            safe_dist = (
                env.cfg.drone.intra_team_safe_dist
                if other.team == drone.team
                else env.cfg.drone.inter_team_safe_dist
            )
            threshold = safe_dist + self.risk_margin + 0.8
            if dist < threshold:
                accel += self._unit(delta) * self.separation_gain * (threshold - dist) / threshold
        return accel.astype(np.float32)

    def _boundary_action(self, env, drone) -> np.ndarray:
        accel = np.zeros(3, dtype=np.float32)
        ranges = [env.cfg.field.x_range, env.cfg.field.y_range, env.cfg.field.z_range]
        for axis, (lo, hi) in enumerate(ranges):
            low_gap = drone.position[axis] - lo
            high_gap = hi - drone.position[axis]
            if low_gap < self.boundary_margin:
                accel[axis] += self.separation_gain * (self.boundary_margin - low_gap) / self.boundary_margin
            if high_gap < self.boundary_margin:
                accel[axis] -= self.separation_gain * (self.boundary_margin - high_gap) / self.boundary_margin
        return accel.astype(np.float32)

    @staticmethod
    def _team_gate_step(team) -> int:
        return 1 if team == Team.RED else -1

    @staticmethod
    def _team_crossing_dir(team, gate) -> np.ndarray:
        return gate.normal if team == Team.RED else -gate.normal

    @staticmethod
    def _max_accel(drone) -> float:
        return float(getattr(drone.dynamics, "max_accel", 10.0))

    @staticmethod
    def _max_speed(drone) -> float:
        return float(getattr(drone.dynamics, "max_speed", 8.0))

    @staticmethod
    def _limit_norm(vec, max_norm: float) -> np.ndarray:
        vec = np.asarray(vec, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm <= max_norm or norm < 1e-6:
            return vec
        return vec / norm * max_norm

    @staticmethod
    def _unit(vec) -> np.ndarray:
        vec = np.asarray(vec, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm < 1e-6:
            return np.zeros(3, dtype=np.float32)
        return vec / norm
