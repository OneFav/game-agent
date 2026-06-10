"""
终止条件模块
- 正常终止：达到 max_steps，比较累计积分定胜负
- 异常终止：碰撞 / 出界 → 双败，立即结束
"""
from abc import ABC, abstractmethod
from typing import Dict
from game_agent.envs.swarm_combat.entities import Team


class TerminationCondition(ABC):
    @abstractmethod
    def check(self, ctx: Dict):
        """返回 (terminated: bool, info: dict)"""
        ...


class MaxStepsTermination(TerminationCondition):
    def __init__(self, max_steps: int):
        self.max_steps = max_steps

    def check(self, ctx):
        if ctx["step"] >= self.max_steps:
            scores = ctx["team_scores"]
            if scores[Team.RED] > scores[Team.BLUE]:
                winner = "RED"
            elif scores[Team.BLUE] > scores[Team.RED]:
                winner = "BLUE"
            else:
                winner = "DRAW"
            return True, {"reason": "max_steps", "winner": winner, "scores": scores}
        return False, {}


class TargetScoreTermination(TerminationCondition):
    """任一队达到目标分时提前结束。"""

    def __init__(self, target_score, draw_tolerance: float = 1e-6):
        self.target_score = target_score
        self.draw_tolerance = draw_tolerance

    def check(self, ctx):
        if self.target_score is None:
            return False, {}
        scores = ctx["team_scores"]
        red = scores[Team.RED]
        blue = scores[Team.BLUE]
        if max(red, blue) < self.target_score:
            return False, {}
        if abs(red - blue) <= self.draw_tolerance:
            winner = "DRAW"
        else:
            winner = "RED" if red > blue else "BLUE"
        return True, {"reason": "target_score", "winner": winner, "scores": scores}


class CollisionTermination(TerminationCondition):
    """任何碰撞类事件 → 双败"""
    def check(self, ctx):
        if ctx.get("collision_triggered", False):
            return True, {
                "reason": ctx.get("collision_reason", "collision"),
                "winner": "DOUBLE_LOSS",
                "scores": ctx["team_scores"],
                "details": ctx.get("collision_details", []),
            }
        return False, {}


def build_default_terminations(cfg):
    return [
        CollisionTermination(),
        TargetScoreTermination(cfg.rules.target_score, cfg.rules.draw_tolerance),
        MaxStepsTermination(cfg.max_steps),
    ]
