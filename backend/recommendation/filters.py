"""硬约束过滤函数集，对照基线 recommendation.py L50-64。"""

from backend.data.restrictions import restriction_status


def matched_tastes(food, prefs):
    """返回口味匹配标签（供 scoring/reasons 复用，对照基线 L62）。"""
    tastes = prefs.get("tastes", [])
    return sorted(set(tastes) & set(food["taste_tags"]))


def hard_constraints_pass(food, prefs):
    """检查 7 项硬约束，全部通过返回 True，对照基线 L50-64。

    F1 预算: budget 非空且 price > budget → False（基线 L50）
    F2 距离: maximum 非空且 distance > maximum → False（基线 L52）
    F3 营业: only_open 且 is_open != "TRUE" → False（基线 L54）
    F4 忌口: avoid 中任一 restriction_status != "TRUE" → False（基线 L56）
    F5 时段: meal_period 非空且不在 meal_periods 中 → False（基线 L58）
    F6 评分: min_rating 非空且 rating < min_rating → False（基线 L60）
    F7 口味: tastes 非空且交集为空 → False（基线 L62-63）
    """
    budget = prefs.get("budget")
    maximum = prefs.get("max_distance_m")
    tastes = prefs.get("tastes", [])
    avoid = prefs.get("avoid", [])
    restaurant = food["restaurant"]
    price = food["price"]
    distance = restaurant["distance_m"]
    rating = restaurant["rating"]

    if budget is not None and price > budget:
        return False
    if maximum is not None and distance > maximum:
        return False
    if prefs.get("only_open") and restaurant["is_open"] != "TRUE":
        return False
    if any(restriction_status(food, term) != "TRUE" for term in avoid):
        return False
    if prefs.get("meal_period") and prefs["meal_period"] not in restaurant["meal_periods"]:
        return False
    if prefs.get("min_rating") is not None and rating < prefs["min_rating"]:
        return False
    matched = matched_tastes(food, prefs)
    if tastes and not matched:
        return False
    return True
