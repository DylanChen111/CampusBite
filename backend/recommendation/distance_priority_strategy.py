"""距离优先推荐策略：复用默认策略的过滤/评分/理由，提升距离权重并追加距离优先理由。

对照 spec §2.4 / §2.4.1 / §5.7-5.8 / design §5。
"""

from decimal import Decimal

from backend.recommendation.filters import hard_constraints_pass
from backend.recommendation.scoring import compute_dimensions
from backend.recommendation.reasons import build_reasons
from backend.recommendation.strategy import RecommendationStrategy


DISTANCE_PRIORITY_WEIGHTS = {
    "T": Decimal("0.20"),
    "P": Decimal("0.20"),
    "D": Decimal("0.40"),
    "R": Decimal("0.20"),
}


class DistancePriorityStrategy(RecommendationStrategy):
    """距离优先推荐策略。

    与 DefaultStrategy 的差异仅体现在权重和追加理由：
    - filter: 复用 hard_constraints_pass（AC24，spec §5.7）
    - score: 复用 compute_dimensions（spec §2.4）
    - reasons: build_reasons + 追加距离优先说明（spec §2.4.1）
    - weights: 固定 DISTANCE_PRIORITY_WEIGHTS（AC25，spec §2.4）
    """

    def filter(self, food, prefs):
        return hard_constraints_pass(food, prefs)

    def score(self, food, prefs):
        return compute_dimensions(food, prefs)

    def reasons(self, food, prefs, dimensions):
        base = build_reasons(food, prefs, dimensions)
        distance = food["restaurant"]["distance_m"]
        base.append(f"本策略以距离为主要排序依据，当前菜品所属场所模拟距离为 {distance} 米。")
        return base

    def weights(self):
        return DISTANCE_PRIORITY_WEIGHTS
