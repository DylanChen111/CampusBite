"""默认推荐策略：四维加权评分，迁移自基线 recommend() 逻辑。"""

from backend.config.recommendation import get_weights
from backend.recommendation.filters import hard_constraints_pass
from backend.recommendation.scoring import compute_dimensions
from backend.recommendation.reasons import build_reasons
from backend.recommendation.strategy import RecommendationStrategy


class DefaultStrategy(RecommendationStrategy):
    """默认推荐策略。

    将基线 recommend() 的过滤/评分/理由逻辑委托给 T3 抽取的函数集，
    权重从 config.recommendation.get_weights() 读取。
    不包含任何内联过滤/评分/理由逻辑（AC18）。
    """

    def filter(self, food, prefs):
        return hard_constraints_pass(food, prefs)

    def score(self, food, prefs):
        return compute_dimensions(food, prefs)

    def reasons(self, food, prefs, dimensions):
        return build_reasons(food, prefs, dimensions)

    def weights(self):
        return get_weights()
