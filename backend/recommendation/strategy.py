"""推荐策略抽象接口与推荐上下文编排。"""

from abc import ABC, abstractmethod
from decimal import Decimal

from backend.data.validation import DataValidationError, validate_record
from backend.recommendation import validate_preferences


class RecommendationStrategy(ABC):
    """推荐策略抽象接口。

    每个具体策略定义四个维度：
    - filter: 硬约束判定（是否进入候选集）
    - score: 多维评分计算（返回各维度 Decimal 分值）
    - reasons: 推荐理由生成（返回字符串列表）
    - weights: 该策略使用的评分权重
    """

    @abstractmethod
    def filter(self, food, prefs):
        """硬约束过滤。返回 True 表示通过，False 表示排除。"""

    @abstractmethod
    def score(self, food, prefs):
        """评分计算。返回各维度分值字典，键 T/P/D/R，值域 0-100。"""

    @abstractmethod
    def reasons(self, food, prefs, dimensions):
        """推荐理由生成。返回理由字符串列表。"""

    @abstractmethod
    def weights(self):
        """返回当前策略的权重字典，值域 0-1，总和=1.0。"""


class RecommendationContext:
    """推荐上下文，持有一个策略实例并编排推荐流程。

    职责：
    1. 偏好验证（委托 validate_preferences）
    2. 遍历候选菜品，委托策略执行过滤→评分→理由
    3. 数据校验、关联一致性检查、去重
    4. 综合分计算（sum(dimension × weight)）
    5. 排序（-score, id）、截取 top_k
    6. 生成结果消息
    """

    def __init__(self, strategy):
        self._strategy = strategy

    def execute(self, foods, prefs):
        """执行推荐流程，返回 {items, total_candidates, message}。"""
        validate_preferences(prefs)
        tastes = prefs.get("tastes", [])
        scored, seen = [], set()

        for food in foods:
            validate_record(food, "dish")
            restaurant = food.get("restaurant")
            validate_record(restaurant, "restaurant")
            if food["restaurant_id"] != restaurant["id"]:
                raise DataValidationError("菜品与场所关联不一致")
            if food["id"] in seen:
                continue
            seen.add(food["id"])

            if not self._strategy.filter(food, prefs):
                continue
            dimensions = self._strategy.score(food, prefs)
            weights = self._strategy.weights()
            score = sum(dimensions[key] * weight for key, weight in weights.items())
            reason_list = self._strategy.reasons(food, prefs, dimensions)
            scored.append((score, food["id"], {
                "dish": food,
                "score": float(score),
                "dimensions": {key: float(value) for key, value in dimensions.items()},
                "reasons": reason_list,
            }))

        scored.sort(key=lambda entry: (-entry[0], entry[1]))
        top_k = prefs.get("top_k", 5)
        items = [entry[2] for entry in scored[:top_k]]
        message = self._build_message(items, scored, tastes, top_k)
        return {"items": items, "total_candidates": len(scored), "message": message}

    @staticmethod
    def _build_message(items, scored, tastes, top_k):
        if not items:
            if tastes:
                return (
                    "没有菜品同时满足所选口味及其他硬约束。"
                    "请检查口味、预算、距离、时段、最低评分和严格忌口；"
                    "系统未自动放宽条件。"
                )
            return (
                "没有菜品满足全部硬约束。"
                "请检查预算、距离、时段、最低评分和严格忌口；"
                "系统未自动放宽条件。"
            )
        if len(items) < top_k:
            return (
                f"仅有 {len(items)} 道菜品满足全部硬约束，"
                "已返回实际数量，未自动放宽条件。"
            )
        return "已按综合评分排序。"
