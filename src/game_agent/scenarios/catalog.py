from __future__ import annotations

from copy import deepcopy
from typing import Any


CAPABILITY_COLUMNS = (
    "continuous_3d",
    "multi_agent",
    "partial_observation",
    "communication",
    "stochasticity",
    "dynamic_lifecycle",
    "hybrid_action",
    "graph_observation",
    "image_observation",
    "external_adapter",
)


_TASKS: tuple[tuple[str, str, str, str, str], ...] = (
    ("S01", "二维静态航路点导航", "navigation", "single_agent_continuous_navigation", "route_completion_rate"),
    ("S02", "二维动态障碍导航", "navigation", "dynamic_obstacles", "goal_reach_rate"),
    ("S03", "三维 Slalom 穿门", "navigation", "continuous_3d_geometry", "ordered_gate_completion_rate"),
    ("S04", "三维移动目标交会", "navigation", "moving_objective", "rendezvous_success_rate"),
    ("S05", "拓扑航路网络导航", "navigation", "graph_world", "valid_route_success_rate"),
    ("S06", "二维单积分器能耗导航", "dynamics", "single_integrator_dynamics", "energy_adjusted_success"),
    ("S07", "三维双积分器制动着陆", "dynamics", "terminal_state_constraints", "safe_landing_rate"),
    ("S08", "阻尼动力学持续跟踪", "dynamics", "damped_dynamics", "trajectory_tracking_score"),
    ("S09", "异构快慢双机协同到达", "dynamics", "heterogeneous_dynamics", "synchronized_arrival_rate"),
    ("S10", "外部六自由度动力学接入", "dynamics", "external_dynamics_adapter", "flight_envelope_completion_rate"),
    ("S11", "完全观测 1v1 追逃", "pursuit_evasion", "two_sided_competition", "capture_rate"),
    ("S12", "局部观测 1v1 追逃", "pursuit_evasion", "partial_observability", "capture_rate_under_partial_observation"),
    ("S13", "三追一协同围捕", "pursuit_evasion", "many_to_one_coordination", "team_capture_rate"),
    ("S14", "一追多逃目标选择", "pursuit_evasion", "one_to_many_target_selection", "weighted_capture_score"),
    ("S15", "多安全区追逃", "pursuit_evasion", "stateful_regions", "side_specific_win_rate"),
    ("S16", "固定队形保持", "team_cooperation", "relational_team_objective", "formation_completion_rate"),
    ("S17", "动态队形切换", "team_cooperation", "dynamic_relation_graph", "formation_transition_success_rate"),
    ("S18", "分布式区域覆盖", "team_cooperation", "spatial_field_objective", "coverage_ratio_at_budget"),
    ("S19", "多目标任务分配", "team_cooperation", "hybrid_assignment_and_control", "feasible_task_value_ratio"),
    ("S20", "协同三维穿门竞速", "team_cooperation", "team_synchronized_progress", "team_ordered_gate_completion_rate"),
    ("S21", "单护航者保护移动目标", "escort_defense", "protected_entity", "escort_success_rate"),
    ("S22", "多护航者对单拦截者", "escort_defense", "multi_agent_protection", "protected_route_completion_rate"),
    ("S23", "多护航者对多拦截者", "escort_defense", "many_to_many_adversarial_coupling", "protected_asset_fraction"),
    ("S24", "非对称攻防角色", "escort_defense", "asymmetric_team_contracts", "breakthrough_fraction"),
    ("S25", "多阶段护航—突防", "escort_defense", "multi_phase_mission", "full_mission_completion_rate"),
    ("S26", "有限视场搜索与跟踪", "sensor_game", "directional_field_of_view", "target_track_fraction"),
    ("S27", "障碍遮挡探测", "sensor_game", "geometric_occlusion", "line_of_sight_tracking_rate"),
    ("S28", "带噪传感器状态估计", "sensor_game", "sensor_measurement_model", "safe_landing_rate_under_sensor_noise"),
    ("S29", "异构传感器协同定位", "sensor_game", "heterogeneous_observation_spaces", "joint_localization_success_rate"),
    ("S30", "CTDE 信息分离", "sensor_game", "ctde_information_contract", "decentralized_coverage_rate"),
    ("S31", "固定两步通信延迟", "communication_game", "fixed_message_delay", "delayed_coordination_success_rate"),
    ("S32", "随机丢包编队", "communication_game", "stochastic_packet_loss", "formation_success_under_packet_loss"),
    ("S33", "带宽受限协作", "communication_game", "bandwidth_constrained_messages", "detections_per_communication_budget"),
    ("S34", "动态通信拓扑覆盖", "communication_game", "dynamic_communication_graph", "coverage_with_connectivity_rate"),
    ("S35", "通信中继部署", "communication_game", "communication_infrastructure_role", "mission_completion_with_relay_rate"),
    ("S36", "随机出生追逃", "robustness", "broad_initial_state_randomization", "capture_rate_across_spawn_distribution"),
    ("S37", "随机障碍布局泛化", "robustness", "procedural_geometry_randomization", "unseen_map_success_rate"),
    ("S38", "动力学参数随机化", "robustness", "hidden_dynamics_randomization", "dynamics_robust_tracking_rate"),
    ("S39", "随机三维风场穿门", "robustness", "spatiotemporal_vector_field", "wind_robust_gate_completion_rate"),
    ("S40", "训练评估分布偏移", "robustness", "frozen_distribution_shift_protocol", "ood_success_rate"),
    ("S41", "智能体动态加入覆盖", "hybrid_mission", "dynamic_agent_spawn", "dynamic_team_coverage_rate"),
    ("S42", "失效退出编队恢复", "hybrid_mission", "agent_failure_and_exit", "post_failure_mission_completion_rate"),
    ("S43", "中途角色切换", "hybrid_mission", "runtime_role_transition", "role_reassignment_success_rate"),
    ("S44", "混合动作", "hybrid_mission", "hybrid_action_space", "valid_hybrid_mission_rate"),
    ("S45", "事件驱动救援", "hybrid_mission", "event_driven_task_graph", "event_chain_completion_rate"),
    ("S46", "十智能体局部集群", "scale_external", "medium_scale_swarm", "local_coordination_completion_rate"),
    ("S47", "五十智能体集群", "scale_external", "large_scale_runtime", "large_swarm_shape_success_rate"),
    ("S48", "动态图观测集群", "scale_external", "graph_observation_space", "graph_observation_passage_rate"),
    ("S49", "图像观测避障", "scale_external", "multimodal_image_observation", "vision_navigation_success_rate"),
    ("S50", "外部仿真端到端接入", "scale_external", "full_external_simulator_adapter", "external_adapter_reproducibility"),
)


def _base_runtime(index: int, family: str) -> dict[str, Any]:
    group_offset = (index - 1) % 5
    n_agents = {
        "navigation": 1,
        "dynamics": 1,
        "pursuit_evasion": 2,
        "team_cooperation": 4,
        "escort_defense": 3,
        "sensor_game": 1,
        "communication_game": 4,
        "robustness": 2,
        "hybrid_mission": 4,
        "scale_external": 10,
    }[family]
    task_mode = {
        "pursuit_evasion": "pursuit",
        "team_cooperation": "formation" if group_offset < 2 else "coverage",
        "escort_defense": "escort",
        "communication_game": "formation" if group_offset < 2 else "coverage",
        "hybrid_mission": "coverage",
        "scale_external": "formation",
    }.get(family, "navigation")
    return {
        "dimension": 2,
        "n_agents": n_agents,
        "max_steps": 48,
        "dt": 0.15,
        "task_mode": task_mode,
        "dynamics": "double_integrator",
        "observation_type": "vector",
        "action_type": "continuous",
        "stochasticity": "initial_jitter",
        "lifecycle": "fixed",
        "communication": {"mode": "perfect"},
        "external_reference": False,
        "vector_field": False,
    }


def _overrides() -> dict[str, dict[str, Any]]:
    return {
        "S02": {"stochasticity": "dynamic_obstacles"},
        "S03": {"dimension": 3},
        "S04": {"dimension": 3, "n_agents": 2},
        "S05": {"observation_type": "graph", "action_type": "hybrid"},
        "S06": {"dynamics": "single_integrator"},
        "S07": {"dimension": 3},
        "S08": {"dimension": 3, "dynamics": "damped"},
        "S09": {"dimension": 3, "n_agents": 2, "dynamics": "damped"},
        "S10": {"dimension": 3, "dynamics": "external_reference", "external_reference": True},
        "S12": {"stochasticity": "sensor_noise"},
        "S13": {"n_agents": 4, "pursuer_count": 3, "evader_count": 1},
        "S14": {
            "n_agents": 4,
            "pursuer_count": 1,
            "evader_count": 3,
            "action_type": "hybrid",
        },
        "S16": {"n_agents": 4},
        "S17": {"n_agents": 5, "lifecycle": "role_transition"},
        "S18": {"n_agents": 6, "task_mode": "coverage"},
        "S19": {"n_agents": 4, "task_mode": "coverage", "action_type": "hybrid"},
        "S20": {"dimension": 3, "n_agents": 3},
        "S22": {"dimension": 3, "n_agents": 5},
        "S23": {"dimension": 3, "n_agents": 8},
        "S24": {"dimension": 3, "n_agents": 8},
        "S25": {"dimension": 3, "n_agents": 6, "lifecycle": "role_transition"},
        "S26": {"stochasticity": "limited_fov"},
        "S27": {"stochasticity": "occlusion"},
        "S28": {"dimension": 3, "stochasticity": "sensor_noise"},
        "S29": {"dimension": 3, "n_agents": 2, "stochasticity": "heterogeneous_sensors"},
        "S30": {"n_agents": 4, "task_mode": "coverage", "stochasticity": "ctde_split"},
        "S31": {"n_agents": 2, "communication": {"mode": "delayed", "delay_steps": 2}},
        "S32": {"communication": {"mode": "lossy", "drop_probability": 0.2}},
        "S33": {"communication": {"mode": "bandwidth", "budget_per_step": 2}},
        "S34": {"n_agents": 6, "task_mode": "coverage", "communication": {"mode": "dynamic_topology"}},
        "S35": {"task_mode": "coverage", "communication": {"mode": "delayed", "delay_steps": 1}},
        "S36": {"task_mode": "pursuit", "stochasticity": "broad_initial_state"},
        "S37": {"n_agents": 1, "stochasticity": "procedural_geometry"},
        "S38": {"n_agents": 1, "dynamics": "damped", "stochasticity": "dynamics_parameters"},
        "S39": {"dimension": 3, "n_agents": 1, "vector_field": True, "stochasticity": "wind_field"},
        "S40": {"n_agents": 1, "stochasticity": "distribution_shift"},
        "S41": {"lifecycle": "dynamic_spawn"},
        "S42": {"n_agents": 5, "lifecycle": "failure_exit"},
        "S43": {"n_agents": 3, "lifecycle": "role_transition"},
        "S44": {"n_agents": 3, "action_type": "hybrid"},
        "S45": {"action_type": "hybrid", "lifecycle": "role_transition"},
        "S46": {"n_agents": 10},
        "S47": {"n_agents": 50, "max_steps": 40},
        "S48": {"n_agents": 12, "observation_type": "graph"},
        "S49": {"n_agents": 2, "observation_type": "image", "task_mode": "navigation"},
        "S50": {"dimension": 3, "n_agents": 4, "external_reference": True, "dynamics": "external_reference"},
    }


def _capabilities(index: int, runtime: dict[str, Any]) -> dict[str, bool]:
    return {
        "continuous_3d": runtime["dimension"] == 3,
        "multi_agent": runtime["n_agents"] > 1,
        "partial_observation": 26 <= index <= 30 or index in {12, 49},
        "communication": 31 <= index <= 35,
        "stochasticity": 36 <= index <= 40 or runtime["stochasticity"] != "initial_jitter",
        "dynamic_lifecycle": 41 <= index <= 45 or runtime["lifecycle"] != "fixed",
        "hybrid_action": runtime["action_type"] == "hybrid",
        "graph_observation": runtime["observation_type"] == "graph",
        "image_observation": runtime["observation_type"] == "image",
        "external_adapter": runtime["external_reference"],
    }


def build_max_space_50_catalog() -> tuple[dict[str, Any], ...]:
    """Build the frozen, explicit 50-scenario conformance catalog."""

    overrides = _overrides()
    result: list[dict[str, Any]] = []
    for index, (scenario_id, name, family, distinction, primary_metric) in enumerate(_TASKS, 1):
        runtime = _base_runtime(index, family)
        runtime.update(deepcopy(overrides.get(scenario_id, {})))
        result.append(
            {
                "schema_version": "representative_scenario/v1",
                "scenario_id": scenario_id,
                "name": name,
                "task_family": family,
                "representative_distinction": distinction,
                "primary_metric": primary_metric,
                "metric_direction": "maximize",
                "baseline_policy_id": "max_space_zero_v1",
                "candidate_policy_id": f"max_space_{scenario_id.lower()}_rule_v1",
                "capabilities": _capabilities(index, runtime),
                "runtime_config": runtime,
                "disclosures": [
                    "本套件使用确定性点质量参考运行时验证接口与研究编排，不代表高保真飞行动力学。",
                    "候选策略是能力感知参考策略，不是经强化学习训练所得的策略。",
                ],
            }
        )
    return tuple(result)


def catalog_by_id() -> dict[str, dict[str, Any]]:
    return {item["scenario_id"]: deepcopy(item) for item in build_max_space_50_catalog()}
