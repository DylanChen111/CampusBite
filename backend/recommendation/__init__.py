"""Deterministic scoring of validated SQLite dishes; no real safety claims."""

from backend.config.recommendation import get_weights
from backend.data.validation import MEALS, TASTES, DataValidationError, number, tags

_weights = get_weights()
WEIGHTS = _weights


class PreferenceError(ValueError):
    pass


def validate_preferences(p):
    try:
        for field in ("budget", "max_distance_m", "min_rating"):
            value = p.get(field)
            if value is not None:
                number(value, field, maximum=5 if field == "min_rating" else None, money=field == "budget")
                if field == "budget" and value <= 0:
                    raise DataValidationError("预算必须大于零")
        tags(p.get("tastes", []), "tastes", TASTES)
        tags(p.get("avoid", []), "avoid")
        if p.get("meal_period") is not None and p["meal_period"] not in MEALS:
            raise DataValidationError("不支持的用餐时段")
        if type(p.get("only_open", False)) is not bool:
            raise DataValidationError("营业条件须为布尔值")
        if type(p.get("top_k", 5)) is not int or p.get("top_k", 5) not in (3, 4, 5):
            raise DataValidationError("推荐数量只能为 3、4 或 5")
    except DataValidationError as exc:
        raise PreferenceError(str(exc)) from exc


from backend.service.recommendation_service import RecommendationService


def recommend(foods, p):
    service = RecommendationService("default")
    return service.recommend(foods, p)
