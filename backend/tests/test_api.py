import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.data.database import connection, initialize
from backend.data.restrictions import RISK_FIELDS, restriction_status
from backend.data.seed import seed_data


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "api.sqlite3"
        initialize(self.path)
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def test_lists_use_database_records_and_metadata(self):
        places = self.client.get("/api/restaurants")
        foods = self.client.get("/api/dishes")
        self.assertEqual(places.status_code, 200)
        self.assertEqual(places.json()["total"], 6)
        self.assertEqual(foods.status_code, 200)
        self.assertEqual(foods.json()["total"], 30)
        self.assertEqual(foods.json()["items"][0]["name"], "宫保鸡丁饭")
        self.assertEqual(foods.json()["metadata"]["is_mock"], 1)
        self.assertIn("花生", foods.json()["options"]["avoid"])

    def test_search_empty_and_literal_sql_input(self):
        self.assertEqual(self.client.get("/api/dishes", params={"keyword": "  "}).json()["total"], 30)
        self.assertTrue(all("面" in f["name"] for f in self.client.get("/api/dishes", params={"keyword": "面"}).json()["items"]))
        self.assertEqual(self.client.get("/api/dishes", params={"keyword": "' OR 1=1 --"}).json()["total"], 0)

    def test_combined_filters_and_rating_sort(self):
        data = self.client.get("/api/dishes", params={"budget": 15, "taste": "清淡", "max_distance_m": 500, "only_open": True, "sort": "rating"}).json()
        self.assertEqual([f["id"] for f in data["items"]], [4, 7, 9])
        self.assertTrue(all(f["price"] <= 15 and f["restaurant"]["distance_m"] <= 500 for f in data["items"]))

    def test_cuisine_and_meal_filters(self):
        for params in ({"cuisine": "轻食"}, {"meal_period": "夜宵"}):
            self.assertEqual(self.client.get("/api/dishes", params=params).json()["total"], 5)

    def test_strict_avoidance_excludes_known_possible_and_unknown(self):
        data = self.client.get("/api/dishes", params={"avoid": "花生"}).json()
        ids = {item["id"] for item in data["items"]}
        self.assertFalse({1, 8, 29, 30} & ids)
        self.assertIn(4, ids)
        self.assertTrue(all(restriction_status(item, "花生") == "TRUE" for item in data["items"]))

    def test_multiple_constraints_and_unsupported_constraint(self):
        data = self.client.get("/api/dishes", params=[("avoid", "花生"), ("avoid", "大豆")]).json()
        self.assertTrue(data["items"])
        self.assertTrue(all(restriction_status(item, term) == "TRUE" for item in data["items"] for term in ("花生", "大豆")))
        self.assertEqual(self.client.get("/api/dishes", params={"avoid": "无法识别的食材"}).json()["total"], 0)

    def test_restriction_tristate_and_known_conflict_precedence(self):
        base = seed_data()[1][3]
        self.assertEqual(restriction_status(base, "花生"), "TRUE")
        self.assertEqual(restriction_status(seed_data()[1][0], "花生"), "FALSE")
        self.assertEqual(restriction_status(seed_data()[1][28], "花生"), "UNKNOWN")
        for field in RISK_FIELDS:
            item = copy.deepcopy(base)
            item[field] = None
            self.assertEqual(restriction_status(item, "花生"), "UNKNOWN")
        incomplete = copy.deepcopy(base)
        incomplete["ingredients"] = []
        self.assertEqual(restriction_status(incomplete, "花生"), "UNKNOWN")
        known = copy.deepcopy(seed_data()[1][0])
        known["possible_allergens"] = None
        self.assertEqual(restriction_status(known, "花生"), "FALSE")

    def test_unknown_partial_risk_fields_not_passed_by_api(self):
        original = seed_data()[1][3]
        for field in RISK_FIELDS:
            with self.subTest(field=field):
                with connection(self.path, create=True) as conn:
                    conn.execute(f"UPDATE dishes SET {field}=NULL WHERE id=4")
                    conn.commit()
                ids = {item["id"] for item in self.client.get("/api/dishes", params={"avoid": "花生"}).json()["items"]}
                self.assertNotIn(4, ids)
                with connection(self.path, create=True) as conn:
                    conn.execute(f"UPDATE dishes SET {field}=? WHERE id=4", (json.dumps(original[field], ensure_ascii=False),))
                    conn.commit()

    def test_only_open_excludes_false_and_unknown(self):
        data = self.client.get("/api/dishes", params={"only_open": True}).json()
        self.assertEqual(data["total"], 15)
        self.assertTrue(all(item["restaurant"]["is_open"] == "TRUE" for item in data["items"]))

    def test_invalid_query_parameters_are_friendly(self):
        for params in ({"budget": -1}, {"budget": 0}, {"budget": "abc"}, {"budget": "NaN"},
                       {"budget": "Infinity"}, {"budget": 1.234}, {"max_distance_m": -1},
                       {"min_rating": 6}, {"taste": "不支持"}, {"sort": "sql"}, {"only_open": "abc"}, {"avoid": ""}, {"cuisine": ""}):
            with self.subTest(params=params):
                response = self.client.get("/api/dishes", params=params)
                self.assertEqual(response.status_code, 422)
                self.assertIn("message", response.json()["error"])
                self.assertNotIn("Traceback", response.text)

    def test_detail_and_not_found(self):
        response = self.client.get("/api/dishes/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"], self.client.get("/api/dishes").json()["items"][0])
        self.assertEqual(self.client.get("/api/dishes/999").status_code, 404)
        self.assertEqual(self.client.get("/api/dishes/abc").status_code, 422)

    def test_missing_or_corrupt_database_is_friendly(self):
        missing = TestClient(create_app(Path(self.temp.name) / "missing.sqlite3"))
        self.addCleanup(missing.close)
        self.assertEqual(missing.get("/api/dishes").status_code, 503)
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE dishes SET taste_tags='[1]' WHERE id=1")
            conn.commit()
        response = self.client.get("/api/dishes")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.path), response.text)

    def test_no_plural_recommendation_alias(self):
        self.assertEqual(self.client.post("/api/recommendations", json={"budget": 20}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
