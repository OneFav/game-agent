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
    """Stable adapter for max_space_zero_v1 (ALL)."""

    PACKAGE_SPEC = {'policy_id': 'max_space_zero_v1',
 'scenario_id': 'ALL',
 'dimension': 2,
 'method_name': 'explicit_zero_action_rule',
 'strategy': 'zero',
 'controller_family': 'explicit_zero_baseline',
 'task_family': 'max_space_50_v1',
 'primary_metric': 'scenario_declared_primary',
 'observation_type': 'scenario_declared',
 'action_type': 'continuous_control_projection',
 'agent_count': 0,
 'adversarial': False,
 'zero_policy': True,
 'default_config': {'strategy': 'zero',
                    'policy_id': 'max_space_zero_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'explicit_zero_action_rule',
                        'observation_contract': 'scenario.observation_space:scenario_declared',
                        'action_contract': 'scenario.action_space:runtime_dimension',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'ALL',
                        'agent_count': 0,
                        'parameter_sharing': 'shared_by_all_agents'}}


POLICY_SPEC = {'policy_id': 'max_space_zero_v1',
 'scenario_id': 'ALL',
 'dimension': 2,
 'method_name': 'explicit_zero_action_rule',
 'strategy': 'zero',
 'controller_family': 'explicit_zero_baseline',
 'task_family': 'max_space_50_v1',
 'primary_metric': 'scenario_declared_primary',
 'observation_type': 'scenario_declared',
 'action_type': 'continuous_control_projection',
 'agent_count': 0,
 'adversarial': False,
 'zero_policy': True,
 'default_config': {'strategy': 'zero',
                    'policy_id': 'max_space_zero_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 1.0,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'explicit_zero_action_rule',
                        'observation_contract': 'scenario.observation_space:scenario_declared',
                        'action_contract': 'scenario.action_space:runtime_dimension',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'ALL',
                        'agent_count': 0,
                        'parameter_sharing': 'shared_by_all_agents'}}
