"""推荐理由生成函数集，对照基线 recommendation.py L72-80。"""

from backend.recommendation.filters import matched_tastes


def build_reasons(food, prefs, dimensions):
    """生成推荐理由列表，对照基线 L72-80。

    R1 价格理由（始终）
    R2 距离理由（始终）
    R3 评分理由（始终）
    R4 口味匹配理由（仅 tastes 非空时）
    R5 营业理由（仅 is_open != "UNKNOWN" 时）
    R6 忌口理由（仅 avoid 非空时）
    """
    budget = prefs.get("budget")
    maximum = prefs.get("max_distance_m")
    tastes = prefs.get("tastes", [])
    avoid = prefs.get("avoid", [])
    restaurant = food["restaurant"]
    price = food["price"]
    distance = restaurant["distance_m"]
    rating = restaurant["rating"]
    matched = matched_tastes(food, prefs)

    reasons = [
        f"菜品价格为 {price:g} 元" + (f"，不超过你的 {budget:g} 元预算。" if budget is not None else "。"),
        f"所属场所模拟距离为 {distance} 米" + (f"，符合 {maximum:g} 米上限。" if maximum is not None else "。"),
        f"所属场所模拟评分为 {rating:g} 分（满分 5 分）。",
    ]
    if tastes:
        reasons.append("口味匹配标签：" + "、".join(matched) + "。")
    if restaurant["is_open"] != "UNKNOWN":
        reasons.append("所属场所在记录的模拟时刻标记为" + ("营业中。" if restaurant["is_open"] == "TRUE" else "未营业。"))
    if avoid:
        reasons.append("模拟配方声明符合严格排除条件：" + "、".join(avoid) + "；不代表现实过敏安全保证。")
    return reasons
