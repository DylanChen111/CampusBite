"""Validate data at the import and read boundaries."""

import json
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

STATES = {"TRUE", "FALSE", "UNKNOWN"}
TASTES = {"清淡", "香辣", "麻辣", "微辣", "酸甜", "鲜香", "甜口"}
MEALS = {"早餐", "午餐", "晚餐", "夜宵"}
ALLERGENS = {"花生", "大豆", "小麦", "鸡蛋", "牛奶", "鱼", "虾", "芝麻", "坚果"}
DIETARY = {"素食"}


class DataValidationError(ValueError):
    """Invalid data; caller can translate this to an API error later."""


def require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{field}: 必须是非空文本")


def number(value, field, minimum=0, maximum=None, money=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DataValidationError(f"{field}: 必须是有限数值")
    if value < minimum or (maximum is not None and value > maximum):
        raise DataValidationError(f"{field}: 数值超出允许范围")
    if money:
        try:
            decimal = Decimal(str(value))
            if decimal != decimal.quantize(Decimal("0.01")) or value >= 1000000000:
                raise DataValidationError(f"{field}: 金额须小于十亿元且最多两位小数")
        except InvalidOperation as exc:
            raise DataValidationError(f"{field}: 非法金额") from exc


def timestamp(value, field, optional=False):
    if optional and value is None:
        return
    require_text(value, field)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise DataValidationError(f"{field}: 须使用带时区的 ISO 8601 时间") from exc


def tags(value, field, vocabulary=None, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, list) or any(not isinstance(t, str) or not t.strip() or t != t.strip() for t in value):
        raise DataValidationError(f"{field}: 须使用非空字符串数组；未知用 null")
    if len(value) != len(set(value)):
        raise DataValidationError(f"{field}: 标签不能重复")
    if vocabulary is not None and not set(value) <= vocabulary:
        raise DataValidationError(f"{field}: 含有不支持的标签")


def hours(value):
    if value is None:
        return
    if not isinstance(value, list) or not value:
        raise DataValidationError("business_hours: 须使用时段数组或 null")
    previous_end = "00:00"
    for interval in value:
        if not isinstance(interval, list) or len(interval) != 2:
            raise DataValidationError("business_hours: 每段须有开始和结束时间")
        if any(not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in interval):
            raise DataValidationError("business_hours: 时间须为 HH:MM")
        start, end = interval
        if start >= end or start < previous_end:
            raise DataValidationError("business_hours: 须按顺序排列、不重叠且不跨日")
        previous_end = end


def validate_record(record, kind):
    if kind not in {"restaurant", "dish"} or not isinstance(record, dict):
        raise DataValidationError("不支持的数据类型")
    required = {"id", "name", "description", "updated_at"}
    if kind == "restaurant":
        required |= {"type", "location", "avg_price", "business_hours", "meal_periods", "is_open",
                     "status_source", "status_at", "distance_m", "rating"}
    else:
        required |= {"restaurant_id", "price", "cuisine", "taste_tags", "dietary_tags",
                     "ingredients", "avoid_tags", "allergens", "possible_allergens"}
    missing = required - record.keys()
    if missing:
        raise DataValidationError(f"{kind}: 缺少字段 {', '.join(sorted(missing))}")
    for field in ("id", "restaurant_id") if kind == "dish" else ("id",):
        if type(record[field]) is not int or record[field] <= 0:
            raise DataValidationError(f"{field}: 须为正整数")
    require_text(record["name"], "name")
    if record["description"] is not None and not isinstance(record["description"], str):
        raise DataValidationError("description: 须为文本或 null")
    timestamp(record["updated_at"], "updated_at")
    if kind == "restaurant":
        if not isinstance(record["type"], str) or record["type"] not in {"restaurant", "window"}:
            raise DataValidationError("type: 非法场所类型")
        require_text(record["location"], "location")
        number(record["avg_price"], "avg_price", money=True)
        number(record["rating"], "rating", maximum=5)
        if type(record["distance_m"]) is not int or record["distance_m"] < 0:
            raise DataValidationError("distance_m: 须为非负整数")
        hours(record["business_hours"])
        tags(record["meal_periods"], "meal_periods", MEALS)
        if not isinstance(record["is_open"], str) or record["is_open"] not in STATES:
            raise DataValidationError("is_open: 须为 TRUE/FALSE/UNKNOWN")
        source = record["status_source"]
        if not isinstance(source, str) or source not in {"simulated_explicit", "simulated_schedule", "unknown"}:
            raise DataValidationError("status_source: 非法状态来源")
        if source == "unknown" and record["is_open"] != "UNKNOWN":
            raise DataValidationError("未知来源不能判定营业")
        if source == "simulated_schedule" and record["business_hours"] is None:
            raise DataValidationError("按时间判定须提供营业时段")
        timestamp(record["status_at"], "status_at", optional=record["is_open"] == "UNKNOWN")
    else:
        number(record["price"], "price", money=True)
        require_text(record["cuisine"], "cuisine")
        tags(record["taste_tags"], "taste_tags", TASTES)
        tags(record["dietary_tags"], "dietary_tags", DIETARY)
        for field in ("ingredients", "avoid_tags", "allergens", "possible_allergens"):
            tags(record[field], field, ALLERGENS if "allergens" in field else None, optional=True)


def decode_row(row, kind):
    result = dict(row)
    fields = ("business_hours", "meal_periods") if kind == "restaurant" else (
        "taste_tags", "dietary_tags", "ingredients", "avoid_tags", "allergens", "possible_allergens")
    for field in fields:
        if result[field] is not None:
            try:
                result[field] = json.loads(result[field])
            except (ValueError, TypeError) as exc:
                raise DataValidationError(f"{field}: 无法解析 JSON") from exc
    validate_record(result, kind)
    return result
