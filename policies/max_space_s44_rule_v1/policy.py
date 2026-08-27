from __future__ import annotations

import sys
from pathlib import Path


def _add_source_root() -> None:
    for parent in Path(__file__).resolve().parents:
        source_root = parent / "src"
        if (source_root / "game_agent" / "policy_designer" / "max_space_policy.py").is_file():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


_add_source_root()

from game_agent.policy_designer.max_space_policy import MaxSpaceRulePolicy


class PolicyClass(MaxSpaceRulePolicy):
    """Stable adapter for max_space_s44_rule_v1 (S44)."""

    PACKAGE_SPEC = {'policy_id': 'max_space_s44_rule_v1',
 'scenario_id': 'S44',
 'dimension': 2,
 'method_name': 'lifecycle_role_rule',
 'strategy': 'lifecycle_role',
 'controller_family': 'lifecycle_role_control',
 'task_family': 'hybrid_mission',
 'primary_metric': 'valid_hybrid_mission_rate',
 'observation_type': 'vector',
 'action_type': 'hybrid',
 'agent_count': 3,
 'adversarial': False,
 'zero_policy': False,
 'default_config': {'strategy': 'lifecycle_role',
                    'policy_id': 'max_space_s44_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'lifecycle_role_rule',
                        'observation_contract': 'scenario.observation_space:vector',
                        'action_contract': 'scenario.action_space:hybrid:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S44',
                        'agent_count': 3,
                        'parameter_sharing': 'shared_by_all_agents'}}


POLICY_SPEC = {'policy_id': 'max_space_s44_rule_v1',
 'scenario_id': 'S44',
 'dimension': 2,
 'method_name': 'lifecycle_role_rule',
 'strategy': 'lifecycle_role',
 'controller_family': 'lifecycle_role_control',
 'task_family': 'hybrid_mission',
 'primary_metric': 'valid_hybrid_mission_rate',
 'observation_type': 'vector',
 'action_type': 'hybrid',
 'agent_count': 3,
 'adversarial': False,
 'zero_policy': False,
 'default_config': {'strategy': 'lifecycle_role',
                    'policy_id': 'max_space_s44_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'lifecycle_role_rule',
                        'observation_contract': 'scenario.observation_space:vector',
                        'action_contract': 'scenario.action_space:hybrid:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S44',
                        'agent_count': 3,
                        'parameter_sharing': 'shared_by_all_agents'}}
