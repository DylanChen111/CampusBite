"""Read records for later APIs; no recommendation scoring."""

from .database import DEFAULT_DB, connection
from .restrictions import restriction_status
from .validation import MEALS, TASTES, DataValidationError, decode_row, number


class FoodRepository:
    def __init__(self, path=DEFAULT_DB):
        self.path = path

    def metadata(self):
        with connection(self.path) as conn:
            row = conn.execute("SELECT * FROM dataset_info WHERE id = 1").fetchone()
            if row is None:
                raise DataValidationError("缺少数据来源说明")
            return dict(row)

    def restaurants(self):
        with connection(self.path) as conn:
            return [decode_row(r, "restaurant") for r in conn.execute("SELECT * FROM restaurants ORDER BY id")]

    def dishes(self, *, keyword="", budget=None, max_distance_m=None, min_rating=None,
               taste=None, meal_period=None, only_open=False, sort="id", cuisine=None, avoid=None):
        if not isinstance(keyword, str):
            raise DataValidationError("keyword: 须为文本")
        if type(only_open) is not bool:
            raise DataValidationError("only_open: 须为布尔值")
        if cuisine is not None and (not isinstance(cuisine, str) or not cuisine.strip()):
            raise DataValidationError("cuisine: 须为非空文本")
        if avoid is None:
            avoid = []
        if not isinstance(avoid, list) or any(not isinstance(t, str) or not t.strip() for t in avoid):
            raise DataValidationError("avoid: 须为非空文本组成的数组")
        if budget is not None:
            number(budget, "budget", money=True)
            if budget <= 0:
                raise DataValidationError("budget: 必须大于零")
        if max_distance_m is not None:
            number(max_distance_m, "max_distance_m")
        if min_rating is not None:
            number(min_rating, "min_rating", maximum=5)
        if taste is not None and (not isinstance(taste, str) or taste not in TASTES):
            raise DataValidationError("taste: 不支持的口味")
        if meal_period is not None and (not isinstance(meal_period, str) or meal_period not in MEALS):
            raise DataValidationError("meal_period: 不支持的时段")
        if not isinstance(sort, str) or sort not in {"id", "price", "distance", "rating"}:
            raise DataValidationError("sort: 不支持的排序")
        with connection(self.path) as conn:
            restaurants = {r["id"]: decode_row(r, "restaurant") for r in conn.execute("SELECT * FROM restaurants")}
            foods = []
            for row in conn.execute("SELECT * FROM dishes ORDER BY id"):
                dish = decode_row(row, "dish")
                restaurant = restaurants.get(dish["restaurant_id"])
                if restaurant is None:
                    raise DataValidationError("菜品关联场所不存在")
                text = " ".join([dish["name"], restaurant["name"], restaurant["location"], dish["cuisine"],
                                 dish["description"] or "", *dish["taste_tags"], *dish["dietary_tags"]])
                if keyword.strip().casefold() not in text.casefold():
                    continue
                if budget is not None and dish["price"] > budget:
                    continue
                if max_distance_m is not None and restaurant["distance_m"] > max_distance_m:
                    continue
                if min_rating is not None and restaurant["rating"] < min_rating:
                    continue
                if taste is not None and taste not in dish["taste_tags"]:
                    continue
                if meal_period is not None and meal_period not in restaurant["meal_periods"]:
                    continue
                if only_open and restaurant["is_open"] != "TRUE":
                    continue
                if cuisine is not None and dish["cuisine"] != cuisine:
                    continue
                if any(restriction_status(dish, restriction) != "TRUE" for restriction in avoid):
                    continue
                foods.append({**dish, "restaurant": restaurant})
        keys = {"id": lambda f: (f["id"],), "price": lambda f: (f["price"], f["id"]),
                "distance": lambda f: (f["restaurant"]["distance_m"], f["id"]),
                "rating": lambda f: (-f["restaurant"]["rating"], f["id"])}
        return sorted(foods, key=keys[sort])

    def dish(self, dish_id):
        if type(dish_id) is not int or dish_id <= 0:
            raise DataValidationError("dish_id: 须为正整数")
        return next((food for food in self.dishes() if food["id"] == dish_id), None)
