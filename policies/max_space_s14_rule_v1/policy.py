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

from game_agent.policy_designer.max_space_policy import MaxSpaceRulePolicy, RedPolicy, BluePolicy


class PolicyClass(MaxSpaceRulePolicy):
    """Stable adapter for max_space_s14_rule_v1 (S14)."""

    PACKAGE_SPEC = {'policy_id': 'max_space_s14_rule_v1',
 'scenario_id': 'S14',
 'dimension': 2,
 'method_name': 'role_aware_pursuit_rule',
 'strategy': 'pursuit_role',
 'controller_family': 'red_blue_pursuit',
 'task_family': 'pursuit_evasion',
 'primary_metric': 'weighted_capture_score',
 'observation_type': 'vector',
 'action_type': 'hybrid',
 'agent_count': 4,
 'adversarial': True,
 'zero_policy': False,
 'default_config': {'strategy': 'pursuit_role',
                    'policy_id': 'max_space_s14_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.18},
 'checkpoint_binding': {'method': 'role_aware_pursuit_rule',
                        'observation_contract': 'scenario.observation_space:vector',
                        'action_contract': 'scenario.action_space:hybrid:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S14',
                        'agent_count': 4,
                        'parameter_sharing': 'side_specific_dispatch'}}


POLICY_SPEC = {'policy_id': 'max_space_s14_rule_v1',
 'scenario_id': 'S14',
 'dimension': 2,
 'method_name': 'role_aware_pursuit_rule',
 'strategy': 'pursuit_role',
 'controller_family': 'red_blue_pursuit',
 'task_family': 'pursuit_evasion',
 'primary_metric': 'weighted_capture_score',
 'observation_type': 'vector',
 'action_type': 'hybrid',
 'agent_count': 4,
 'adversarial': True,
 'zero_policy': False,
 'default_config': {'strategy': 'pursuit_role',
                    'policy_id': 'max_space_s14_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.18},
 'checkpoint_binding': {'method': 'role_aware_pursuit_rule',
                        'observation_contract': 'scenario.observation_space:vector',
                        'action_contract': 'scenario.action_space:hybrid:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S14',
                        'agent_count': 4,
                        'parameter_sharing': 'side_specific_dispatch'}}
