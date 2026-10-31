"""推荐服务层：策略注册表与策略选择，对照 spec §4.4 / design §6。"""

from backend.recommendation.default_strategy import DefaultStrategy
from backend.recommendation.distance_priority_strategy import DistancePriorityStrategy
from backend.recommendation.strategy import RecommendationContext


STRATEGY_REGISTRY = {
    "default": DefaultStrategy,
    "distance_priority": DistancePriorityStrategy,
}


class RecommendationService:
    """推荐服务，根据策略标识选择对应策略并执行推荐。

    策略选择在 __init__ 阶段完成，未知名称立即抛出 ValueError，
    不延迟到 recommend 阶段，不静默回退到默认策略（spec §5.4）。
    """

    def __init__(self, strategy_name: str = "default"):
        if strategy_name is None:
            strategy_name = "default"
        if strategy_name not in STRATEGY_REGISTRY:
            raise ValueError(f"未知推荐策略: {strategy_name}")
        self._strategy = STRATEGY_REGISTRY[strategy_name]()

    def recommend(self, foods: list, prefs: dict) -> dict:
        context = RecommendationContext(self._strategy)
        return context.execute(foods, prefs)
