"""评分维度计算函数集，对照基线 recommendation.py L65-69。"""

from decimal import Decimal

from backend.recommendation.filters import matched_tastes


def compute_dimensions(food, prefs):
    """计算四维评分（T/P/D/R），返回 dict[str, Decimal]，对照基线 L65-69。

    T 口味: 命中数/口味总数×100（无口味时 Decimal(50)）
    P 价格: (1-price/budget)×100（无预算时 Decimal(50)）
    D 距离: maximum==0 时 Decimal(100)，否则 (1-distance/max)×100（无上限时 Decimal(50)）
    R 评分: rating/5×100
    """
    budget = prefs.get("budget")
    maximum = prefs.get("max_distance_m")
    tastes = prefs.get("tastes", [])
    restaurant = food["restaurant"]
    price = food["price"]
    distance = restaurant["distance_m"]
    rating = restaurant["rating"]
    matched = matched_tastes(food, prefs)

    return {
        "T": Decimal(len(matched)) / Decimal(len(tastes)) * 100 if tastes else Decimal(50),
        "P": (1 - Decimal(str(price)) / Decimal(str(budget))) * 100 if budget is not None else Decimal(50),
        "D": (Decimal(100) if maximum == 0 else (1 - Decimal(distance) / Decimal(str(maximum))) * 100) if maximum is not None else Decimal(50),
        "R": Decimal(str(rating)) / 5 * 100,
    }
