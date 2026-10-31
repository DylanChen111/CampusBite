import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.data.database import connection, initialize, insert_record, validate_database
from backend.data.repository import FoodRepository
from backend.data.seed import VERSION, seed_data
from backend.data.validation import DataValidationError, hours, validate_record


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"
        initialize(self.path)
        self.repo = FoodRepository(self.path)

    def test_schema_counts_and_primary_keys(self):
        with connection(self.path) as conn:
            self.assertEqual(validate_database(conn), {"restaurants": 6, "dishes": 30})
            for table in ("restaurants", "dishes"):
                total, unique = conn.execute(f"SELECT count(*), count(DISTINCT id) FROM {table}").fetchone()
                self.assertEqual(total, unique)
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_init_is_idempotent_and_preserves_records(self):
        before = self.repo.dishes()
        for _ in range(3):
            self.assertEqual(initialize(self.path), {"restaurants": 6, "dishes": 30})
        self.assertEqual(before, self.repo.dishes())

    def test_database_rejects_invalid_values(self):
        statements = [
            "UPDATE dishes SET price=-1 WHERE id=1",
            "UPDATE dishes SET price=1.234 WHERE id=1",
            "UPDATE dishes SET restaurant_id=999 WHERE id=1",
            "UPDATE dishes SET restaurant_id=NULL WHERE id=1",
            "UPDATE dishes SET id=-1 WHERE id=1",
            "UPDATE dishes SET name='' WHERE id=1",
            "UPDATE dishes SET taste_tags='broken' WHERE id=1",
            "UPDATE dishes SET taste_tags='{}' WHERE id=1",
            "UPDATE restaurants SET avg_price=-1 WHERE id=1",
            "UPDATE restaurants SET distance_m=-1 WHERE id=1",
            "UPDATE restaurants SET distance_m=1.5 WHERE id=1",
            "UPDATE restaurants SET rating=5.1 WHERE id=1",
            "UPDATE restaurants SET rating=-1 WHERE id=1",
            "UPDATE restaurants SET is_open='yes' WHERE id=1",
            "UPDATE restaurants SET is_open='TRUE' WHERE id=4",
            "UPDATE dishes SET id=2 WHERE id=1",
            "DELETE FROM restaurants WHERE id=1",
        ]
        with connection(self.path, create=True) as conn:
            for statement in statements:
                with self.subTest(sql=statement):
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(statement)
                    conn.rollback()

    def test_validation_rejects_missing_required_fields(self):
        restaurants, dishes = seed_data()
        for record, kind in ((restaurants[0], "restaurant"), (dishes[0], "dish")):
            for field in record:
                with self.subTest(kind=kind, field=field):
                    broken = copy.deepcopy(record)
                    del broken[field]
                    with self.assertRaises(DataValidationError):
                        validate_record(broken, kind)

    def test_validation_numeric_edges(self):
        restaurants, dishes = seed_data()
        for original, kind, field, values in [
            (dishes[0], "dish", "price", [-1, 1.234, float("nan"), float("inf"), True, "12"]),
            (restaurants[0], "restaurant", "rating", [-1, 5.01, float("nan"), "4"]),
            (restaurants[0], "restaurant", "distance_m", [-1, 1.1, True]),
            (restaurants[0], "restaurant", "is_open", [True, [], "open"]),
        ]:
            for value in values:
                with self.subTest(field=field, value=value):
                    broken = copy.deepcopy(original)
                    broken[field] = value
                    with self.assertRaises(DataValidationError):
                        validate_record(broken, kind)

    def test_hours_and_tag_validation(self):
        for value in [[], "07:00-10:00", [["7:00", "10:00"]], [["24:00", "25:00"]],
                      [["23:00", "01:00"]], [["12:00", "12:00"]],
                      [["10:00", "12:00"], ["11:00", "13:00"]]]:
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                hours(value)
        hours([["07:00", "09:00"], ["09:00", "12:00"]])
        original = seed_data()[1][0]
        for field, value in [("taste_tags", "香辣"), ("taste_tags", ["香辣", "香辣"]),
                             ("taste_tags", ["不存在"]), ("allergens", ["不存在"]),
                             ("ingredients", [""]), ("dietary_tags", {})]:
            broken = copy.deepcopy(original)
            broken[field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                validate_record(broken, "dish")

    def test_unknown_and_optional_fields_remain_explicit(self):
        food = self.repo.dish(30)
        self.assertIsNone(food["ingredients"])
        self.assertIsNone(food["allergens"])
        self.assertIsNone(food["possible_allergens"])
        self.assertEqual(self.repo.dish(16)["restaurant"]["is_open"], "UNKNOWN")
        record = seed_data()[1][0]
        record["description"] = None
        validate_record(record, "dish")

    def test_each_unknown_risk_field_round_trips_independently(self):
        for index, field in enumerate(("ingredients", "avoid_tags", "allergens", "possible_allergens")):
            with self.subTest(field=field):
                record = copy.deepcopy(seed_data()[1][0])
                record.update(id=31 + index, name=f"独立测试未知{field}")
                record[field] = None
                with connection(self.path, create=True) as conn:
                    insert_record(conn, "dishes", record)
                    conn.commit()
                food = self.repo.dish(record["id"])
                for risk_field in ("ingredients", "avoid_tags", "allergens", "possible_allergens"):
                    self.assertEqual(food[risk_field], record[risk_field])
                self.assertIsNone(food[field])

    def test_declared_empty_risk_arrays_are_distinct_from_unknown(self):
        fields = ("ingredients", "avoid_tags", "allergens", "possible_allergens")
        record = copy.deepcopy(seed_data()[1][0])
        record.update(id=31, name="独立测试明确空数组")
        record.update({field: [] for field in fields})
        with connection(self.path, create=True) as conn:
            insert_record(conn, "dishes", record)
            conn.commit()
        declared_empty = self.repo.dish(31)
        unknown = self.repo.dish(30)
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(declared_empty[field], [])
                self.assertIsNone(unknown[field])
                self.assertNotEqual(declared_empty[field], unknown[field])

    def test_known_and_possible_allergens_remain_separate(self):
        known = self.repo.dish(1)
        possible = self.repo.dish(29)
        self.assertIn("花生", known["ingredients"])
        self.assertIn("花生", known["avoid_tags"])
        self.assertIn("花生", known["allergens"])
        self.assertEqual(known["possible_allergens"], [])
        self.assertNotIn("花生", possible["ingredients"])
        self.assertEqual(possible["allergens"], [])
        self.assertEqual(possible["possible_allergens"], ["花生"])

    def test_unknown_risk_uses_sql_null_not_json_null_or_state_string(self):
        fields = ("ingredients", "avoid_tags", "allergens", "possible_allergens")
        with connection(self.path, create=True) as conn:
            for field in fields:
                with self.subTest(field=field):
                    for invalid in ("null", '"UNKNOWN"', '"FALSE"'):
                        with self.assertRaises(sqlite3.IntegrityError):
                            conn.execute(f"UPDATE dishes SET {field}=? WHERE id=1", (invalid,))
                        conn.rollback()
                    conn.execute(f"UPDATE dishes SET {field}=? WHERE id=1", (None,))
                    conn.commit()
                    self.assertIsNone(self.repo.dish(1)[field])

    def test_all_business_states_round_trip_and_only_true_passes_open_filter(self):
        for state in ("TRUE", "FALSE", "UNKNOWN"):
            with self.subTest(state=state):
                with connection(self.path, create=True) as conn:
                    conn.execute("UPDATE restaurants SET is_open=? WHERE id=1", (state,))
                    conn.commit()
                self.assertEqual(self.repo.dish(1)["restaurant"]["is_open"], state)
                open_ids = {food["id"] for food in self.repo.dishes(only_open=True)}
                for dish_id in range(1, 6):
                    self.assertEqual(dish_id in open_ids, state == "TRUE")

    def test_unknown_business_hours_remain_unknown_on_read(self):
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE restaurants SET business_hours=NULL WHERE id=4")
            conn.commit()
        restaurant = self.repo.dish(16)["restaurant"]
        self.assertIsNone(restaurant["business_hours"])
        self.assertIsNone(restaurant["status_at"])
        self.assertEqual(restaurant["is_open"], "UNKNOWN")
        self.assertEqual(restaurant["status_source"], "unknown")
        self.assertNotIn(16, {food["id"] for food in self.repo.dishes(only_open=True)})

    def test_read_boundary_rejects_corrupt_tags_and_hours(self):
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE dishes SET taste_tags='[1]' WHERE id=1")
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.repo.dishes()
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE dishes SET taste_tags=? WHERE id=1", (json.dumps(["香辣"]),))
            conn.execute("UPDATE restaurants SET business_hours=? WHERE id=1", ('[["25:00","26:00"]]',))
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.repo.restaurants()

    def test_foreign_key_failure_rolls_back_seed(self):
        broken_path = Path(self.temp.name) / "broken.sqlite3"
        restaurants, dishes = seed_data()
        dishes[0]["restaurant_id"] = 999
        with self.assertRaises(sqlite3.IntegrityError):
            initialize(broken_path, records=(restaurants, dishes))
        with connection(broken_path) as conn:
            for table in ("restaurants", "dishes", "dataset_info"):
                self.assertEqual(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_duplicate_input_and_existing_id_conflict(self):
        restaurants, dishes = seed_data()
        with self.assertRaises(DataValidationError):
            initialize(self.path, records=(restaurants, dishes + [dishes[0]]))
        dishes[0]["name"] = "改名冲突"
        with self.assertRaises(DataValidationError):
            initialize(self.path, records=(restaurants, dishes))
        self.assertEqual(self.repo.dish(1)["name"], "宫保鸡丁饭")

    def test_no_overwrite_incompatible_version(self):
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE dataset_info SET data_version='other'")
            conn.commit()
        with self.assertRaises(DataValidationError):
            initialize(self.path)
        self.assertEqual(self.repo.metadata()["data_version"], "other")

    def test_unknown_business_excluded_when_only_open(self):
        foods = self.repo.dishes(only_open=True)
        self.assertEqual(len(foods), 15)
        self.assertTrue(all(f["restaurant"]["is_open"] == "TRUE" for f in foods))

    def test_budget_uses_dish_price_not_restaurant_avg(self):
        foods = self.repo.dishes(budget=10)
        self.assertTrue(foods)
        self.assertTrue(all(f["price"] <= 10 for f in foods))
        self.assertIn(4, [f["id"] for f in foods])
        self.assertGreater(self.repo.dish(4)["restaurant"]["avg_price"], 10)
        self.assertNotIn(6, [f["id"] for f in self.repo.dishes(budget=12)])
        self.assertIn(6, [f["id"] for f in self.repo.dishes(budget=16)])

    def test_four_filters_actually_change_results(self):
        base = self.repo.dishes()
        for params, predicate in [
            ({"budget": 10}, lambda f: f["price"] <= 10),
            ({"taste": "清淡"}, lambda f: "清淡" in f["taste_tags"]),
            ({"max_distance_m": 200}, lambda f: f["restaurant"]["distance_m"] <= 200),
            ({"min_rating": 4.5}, lambda f: f["restaurant"]["rating"] >= 4.5),
            ({"meal_period": "早餐"}, lambda f: "早餐" in f["restaurant"]["meal_periods"]),
        ]:
            with self.subTest(params=params):
                foods = self.repo.dishes(**params)
                self.assertTrue(0 < len(foods) < len(base))
                self.assertTrue(all(predicate(f) for f in foods))

    def test_search_empty_no_match_and_sql_literal(self):
        self.assertEqual(len(self.repo.dishes(keyword="  ")), 30)
        self.assertEqual(self.repo.dishes(keyword="不存在的食物"), [])
        self.assertEqual(self.repo.dishes(keyword="' OR 1=1 --"), [])
        self.assertEqual(self.repo.dishes(keyword="%"), [])
        for keyword in ("面食", "清淡", "虚构校园 A", "配方"):
            self.assertTrue(self.repo.dishes(keyword=keyword))

    def test_sort_and_detail_consistency(self):
        for sort, key in (("price", lambda f: f["price"]), ("distance", lambda f: f["restaurant"]["distance_m"]),
                          ("rating", lambda f: -f["restaurant"]["rating"])):
            values = [key(f) for f in self.repo.dishes(sort=sort)]
            self.assertEqual(values, sorted(values))
        for food in self.repo.dishes():
            self.assertEqual(self.repo.dish(food["id"]), food)
        self.assertIsNone(self.repo.dish(999))

    def test_query_invalid_input(self):
        for params in ({"budget": 0}, {"budget": -1}, {"budget": "10"}, {"budget": float("inf")},
                       {"budget": True}, {"max_distance_m": -1}, {"min_rating": 6},
                       {"sort": []}, {"taste": []}, {"only_open": "TRUE"}, {"keyword": None}):
            with self.subTest(params=params), self.assertRaises(DataValidationError):
                self.repo.dishes(**params)

    def test_mock_notice_and_diversity(self):
        info = self.repo.metadata()
        self.assertEqual(info["is_mock"], 1)
        self.assertEqual(info["data_version"], VERSION)
        self.assertIn("模拟", info["notice"])
        foods = self.repo.dishes()
        self.assertTrue({"川菜", "面食", "米饭", "轻食"} <= {f["cuisine"] for f in foods})
        self.assertTrue(any("素食" in f["dietary_tags"] for f in foods))
        self.assertEqual(min(f["price"] for f in foods), 3.5)
        self.assertEqual(max(f["price"] for f in foods), 32)

    def test_read_does_not_create_missing_database(self):
        path = Path(self.temp.name) / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            FoodRepository(path).dishes()
        self.assertFalse(path.exists())

    def test_write_helper_rejects_table_injection(self):
        with connection(self.path, create=True) as conn:
            with self.assertRaises(DataValidationError):
                insert_record(conn, "dishes); DROP TABLE dishes; --", seed_data()[1][0])
        self.assertEqual(len(self.repo.dishes()), 30)


if __name__ == "__main__":
    unittest.main()
