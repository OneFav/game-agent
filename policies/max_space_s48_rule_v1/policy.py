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
    """Stable adapter for max_space_s48_rule_v1 (S48)."""

    PACKAGE_SPEC = {'policy_id': 'max_space_s48_rule_v1',
 'scenario_id': 'S48',
 'dimension': 2,
 'method_name': 'scalable_modality_rule',
 'strategy': 'scalable_adapter',
 'controller_family': 'scalable_modality_adapter',
 'task_family': 'scale_external',
 'primary_metric': 'graph_observation_passage_rate',
 'observation_type': 'graph',
 'action_type': 'continuous',
 'agent_count': 12,
 'adversarial': False,
 'zero_policy': False,
 'default_config': {'strategy': 'scalable_adapter',
                    'policy_id': 'max_space_s48_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 0.92,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'scalable_modality_rule',
                        'observation_contract': 'scenario.observation_space:graph',
                        'action_contract': 'scenario.action_space:continuous:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S48',
                        'agent_count': 12,
                        'parameter_sharing': 'shared_by_all_agents'}}


POLICY_SPEC = {'policy_id': 'max_space_s48_rule_v1',
 'scenario_id': 'S48',
 'dimension': 2,
 'method_name': 'scalable_modality_rule',
 'strategy': 'scalable_adapter',
 'controller_family': 'scalable_modality_adapter',
 'task_family': 'scale_external',
 'primary_metric': 'graph_observation_passage_rate',
 'observation_type': 'graph',
 'action_type': 'continuous',
 'agent_count': 12,
 'adversarial': False,
 'zero_policy': False,
 'default_config': {'strategy': 'scalable_adapter',
                    'policy_id': 'max_space_s48_rule_v1',
                    'gain': 1.0,
                    'damping': 0.55,
                    'action_cap': 0.92,
                    'rate_limit': 2.0,
                    'communication_decay': 0.0,
                    'role_gain': 0.0},
 'checkpoint_binding': {'method': 'scalable_modality_rule',
                        'observation_contract': 'scenario.observation_space:graph',
                        'action_contract': 'scenario.action_space:continuous:2d',
                        'preprocessing': 'max_space_local_obs_v1',
                        'scenario_id': 'S48',
                        'agent_count': 12,
                        'parameter_sharing': 'shared_by_all_agents'}}
