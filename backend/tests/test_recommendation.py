import copy
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.data.database import connection, initialize
from backend.data.repository import FoodRepository
from backend.data.restrictions import RISK_FIELDS, restriction_status
from backend.data.validation import DataValidationError
from backend.recommendation import recommend


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'food.sqlite3'
        initialize(self.path)
        self.foods = FoodRepository(self.path).dishes()
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def post(self, **p):
        response = self.client.post('/api/recommend', json=p)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_weights_formula_and_actual_rating(self):
        food = self.foods[0]
        result = recommend([food], {'budget': 20, 'max_distance_m': 1000, 'tastes': [food['taste_tags'][0]]})['items'][0]
        expected = {'T': 100, 'P': 100 * (1 - food['price'] / 20), 'D': 100 * (1 - food['restaurant']['distance_m'] / 1000), 'R': food['restaurant']['rating'] / 5 * 100}
        for key, value in expected.items():
            self.assertAlmostEqual(result['dimensions'][key], value)
        self.assertAlmostEqual(result['score'], .35 * expected['T'] + .25 * expected['P'] + .20 * expected['D'] + .20 * expected['R'])

    def test_price_direction_and_budget_boundary(self):
        a = copy.deepcopy(self.foods[0]); b = copy.deepcopy(a)
        b['id'] = 100; a['price'] = 10; b['price'] = 20
        result = recommend([b, a], {'budget': 20})['items']
        self.assertEqual([r['dish']['id'] for r in result], [a['id'], b['id']])
        self.assertEqual([r['dimensions']['P'] for r in result], [50, 0])
        self.assertTrue(all(r['dish']['price'] <= 10 for r in self.post(budget=10)['items']))

    def test_distance_filter_and_zero_boundary(self):
        self.assertTrue(all(r['dish']['restaurant']['distance_m'] <= 200 for r in self.post(max_distance_m=200)['items']))
        self.assertEqual(self.post(max_distance_m=0)['items'], [])
        food = copy.deepcopy(self.foods[0]); food['restaurant']['distance_m'] = 0
        self.assertEqual(recommend([food], {'max_distance_m': 0})['items'][0]['dimensions']['D'], 100)

    def test_neutral_unspecified_and_no_unselected_claims(self):
        for result in self.post()['items']:
            self.assertEqual({k: result['dimensions'][k] for k in ['T', 'P', 'D']}, {'T': 50, 'P': 50, 'D': 50})
            self.assertNotIn('你的', ''.join(result['reasons']))
            self.assertNotIn('口味匹配', ''.join(result['reasons']))

    def test_taste_changes_order_and_requires_actual_match(self):
        a = self.post(tastes=['清淡']); b = self.post(tastes=['麻辣'])
        self.assertNotEqual([r['dish']['id'] for r in a['items']], [r['dish']['id'] for r in b['items']])
        for result, taste in [(a, '清淡'), (b, '麻辣')]:
            self.assertEqual(result['total_candidates'], sum(taste in food['taste_tags'] for food in self.foods))
            self.assertTrue(all(taste in item['dish']['taste_tags'] for item in result['items']))

    def test_multi_taste_match_fraction(self):
        food = self.foods[0]
        food = copy.deepcopy(food); food['taste_tags'] = ['清淡']
        result = recommend([food], {'tastes': ['清淡', '麻辣']})['items'][0]
        self.assertEqual(result['dimensions']['T'], 50)
        self.assertIn('口味匹配标签：清淡。', result['reasons'])

    def test_open_strict_and_no_open_score(self):
        result = self.post(only_open=True)
        self.assertEqual(result['total_candidates'], 15)
        self.assertTrue(all(r['dish']['restaurant']['is_open'] == 'TRUE' for r in result['items']))
        a = copy.deepcopy(self.foods[0]); b = copy.deepcopy(a)
        b['id'] = 99; b['restaurant']['is_open'] = 'UNKNOWN'
        items = recommend([a, b], {})['items']
        self.assertEqual(items[0]['score'], items[1]['score'])
        self.assertEqual(len(items), 2)

    def test_strict_avoid_known_possible_unknown_and_unsupported(self):
        result = self.post(avoid=['花生'])
        self.assertEqual(result['total_candidates'], 26)
        self.assertTrue(all(restriction_status(r['dish'], '花生') == 'TRUE' for r in result['items']))
        self.assertEqual(recommend([self.foods[i-1] for i in [1, 8, 29, 30]], {'avoid': ['花生']})['items'], [])
        self.assertEqual(self.post(avoid=['不识别的忌口'])['items'], [])
        for field in RISK_FIELDS:
            food = copy.deepcopy(self.foods[3]); food[field] = None
            self.assertEqual(recommend([food], {'avoid': ['花生']})['items'], [])

    def test_top_k_stability_uniqueness_and_fewer_results(self):
        for k in [3, 4, 5]:
            self.assertEqual(len(self.post(top_k=k)['items']), k)
        food = self.foods[0]
        self.assertEqual(len(recommend([food, food], {})['items']), 1)
        forward = recommend(self.foods, {}); reverse = recommend(list(reversed(self.foods)), {})
        self.assertEqual(forward, reverse)
        tied = recommend(self.foods[:5], {})['items']
        self.assertEqual([r['dish']['id'] for r in tied], [1, 2, 3, 4, 5])
        self.assertEqual(len(self.post(budget=4)['items']), 2)

    def test_reasons_match_database_and_constraints(self):
        result = self.post(budget=20, max_distance_m=1000, only_open=True, avoid=['花生'], tastes=['清淡'])
        for r in result['items']:
            f = r['dish']; original = self.foods[f['id']-1]
            self.assertEqual(f, original)
            text = ''.join(r['reasons'])
            self.assertIn(f"菜品价格为 {f['price']:g} 元", text)
            self.assertIn(f"所属场所模拟评分为 {f['restaurant']['rating']:g} 分", text)
            self.assertIn(f"模拟距离为 {f['restaurant']['distance_m']} 米", text)
            self.assertIn('模拟时刻', text)
            self.assertNotIn('菜品评分', text)
            self.assertIn('不代表现实过敏安全保证', text)

    def test_all_scores_bounded_and_no_input_mutation(self):
        original = copy.deepcopy(self.foods)
        for p in [{}, {'budget': 100, 'max_distance_m': 2000}, {'tastes': ['清淡', '鲜香']}]:
            for item in recommend(self.foods, p)['items']:
                self.assertTrue(0 <= item['score'] <= 100)
                self.assertTrue(all(0 <= v <= 100 for v in item['dimensions'].values()))
        self.assertEqual(self.foods, original)

    def test_invalid_requests_are_rejected(self):
        for p in [{'budget': 0}, {'budget': -1}, {'budget': '20'}, {'budget': True}, {'budget': 1.234}, {'budget': float('inf')}, {'max_distance_m': -1}, {'tastes': ['未知']}, {'tastes': ['清淡', '清淡']}, {'avoid': ['']}, {'top_k': 2}, {'top_k': True}, {'only_open': 'TRUE'}, {'min_rating': 6}, {'meal_period': '未知'}, {'extra': 1}]:
            with self.subTest(p=p):
                if p.get('budget') == float('inf'):
                    response = self.client.post('/api/recommend', content='{"budget":Infinity}', headers={'Content-Type': 'application/json'})
                else:
                    response = self.client.post('/api/recommend', json=p)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.post('/api/recommend', content='{').status_code, 422)

    def test_missing_invalid_rating_distance_and_link_rejected(self):
        for field, values in {'rating': [None, -1, 6], 'distance_m': [None, -1]}.items():
            for value in values:
                food = copy.deepcopy(self.foods[0]); food['restaurant'][field] = value
                with self.assertRaises(DataValidationError): recommend([food], {})
        food = copy.deepcopy(self.foods[0]); food['restaurant']['id'] = 99
        with self.assertRaises(DataValidationError): recommend([food], {})

    def test_empty_result_and_storage_failure(self):
        result = self.post(budget=1)
        self.assertEqual(result['items'], [])
        self.assertIn('未自动放宽', result['message'])
        self.client.app.state.db_path = Path(self.temp.name) / 'missing.sqlite3'
        response = self.client.post('/api/recommend', json={})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.path), response.text)

    def test_meal_and_rating_hard_filters(self):
        result = self.post(meal_period='早餐', min_rating=4)
        self.assertTrue(result['items'])
        self.assertTrue(all('早餐' in r['dish']['restaurant']['meal_periods'] and r['dish']['restaurant']['rating'] >= 4 for r in result['items']))

    def test_corrupt_stored_tags_return_friendly_503(self):
        with connection(self.path, create=True) as conn:
            conn.execute("UPDATE dishes SET taste_tags='[1]' WHERE id=1")
            conn.commit()
        response = self.client.post('/api/recommend', json={})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('Traceback', response.text)

    def test_screenshot_mild_spicy_budget10_night_has_no_match(self):
        result = self.post(budget=10, tastes=['微辣'], meal_period='夜宵')
        self.assertEqual(result['items'], [])
        self.assertEqual(result['total_candidates'], 0)
        self.assertIn('口味', result['message'])

    def test_selected_tastes_never_return_unrelated_food(self):
        for tastes in [['微辣'], ['清淡', '麻辣']]:
            result = self.post(tastes=tastes)
            self.assertTrue(result['items'])
            for item in result['items']:
                self.assertTrue(set(tastes) & set(item['dish']['taste_tags']))
                self.assertGreater(item['dimensions']['T'], 0)
