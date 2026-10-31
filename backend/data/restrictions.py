"""Three-state constraint evaluation for the controlled mock ingredient vocabulary."""

from .validation import ALLERGENS, DataValidationError, require_text

AVOID_OPTIONS = sorted(ALLERGENS | {"香菜", "辣椒", "牛肉", "猪肉", "鸡肉"})
RISK_FIELDS = ("ingredients", "avoid_tags", "allergens", "possible_allergens")


def restriction_status(dish, restriction):
    """TRUE means the mock declarations satisfy this one constraint, not real safety."""
    require_text(restriction, "avoid")
    if restriction not in AVOID_OPTIONS:
        return "UNKNOWN"
    for field in RISK_FIELDS:
        value = dish.get(field)
        if value is not None and (not isinstance(value, list) or any(not isinstance(v, str) for v in value)):
            raise DataValidationError(f"{field}: 非法风险信息")
    if any(restriction in (dish.get(field) or []) for field in RISK_FIELDS[:-1]):
        return "FALSE"
    if any(dish.get(field) is None for field in RISK_FIELDS):
        return "UNKNOWN"
    if not dish["ingredients"] or restriction in dish["possible_allergens"]:
        return "UNKNOWN"
    return "TRUE"
