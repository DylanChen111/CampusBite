"""推荐策略重构测试：配置校验（CT1-CT6）。

T1 产出验证：backend/config/recommendation.py
后续 T8 将补充 TestFilters / TestScoring / TestReasons / TestDefaultStrategy 等。
"""

import os
import unittest
from decimal import Decimal

from backend.config.recommendation import (
    ConfigError,
    DEFAULT_WEIGHTS,
    get_weights,
)

_ENV_VARS = [
    "CAMPUSBITE_WEIGHT_T",
    "CAMPUSBITE_WEIGHT_P",
    "CAMPUSBITE_WEIGHT_D",
    "CAMPUSBITE_WEIGHT_R",
]


class TestConfig(unittest.TestCase):
    """CT1-CT6：配置校验测试。"""

    def setUp(self):
        self._saved = {v: os.environ.pop(v, None) for v in _ENV_VARS}

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved[v] is not None:
                os.environ[v] = self._saved[v]
            else:
                os.environ.pop(v, None)

    def test_ct1_legal_config(self):
        """CT1：合法配置正常加载。"""
        os.environ["CAMPUSBITE_WEIGHT_T"] = "0.30"
        os.environ["CAMPUSBITE_WEIGHT_P"] = "0.30"
        os.environ["CAMPUSBITE_WEIGHT_D"] = "0.20"
        os.environ["CAMPUSBITE_WEIGHT_R"] = "0.20"
        w = get_weights()
        self.assertEqual(w["T"], Decimal("0.30"))
        self.assertEqual(w["P"], Decimal("0.30"))
        self.assertEqual(w["D"], Decimal("0.20"))
        self.assertEqual(w["R"], Decimal("0.20"))
        self.assertEqual(sum(w.values()), Decimal("1.00"))

    def test_ct2_missing_config(self):
        """CT2：权重缺失使用默认值。"""
        w = get_weights()
        self.assertEqual(w, DEFAULT_WEIGHTS)
        self.assertEqual(w["T"], Decimal("0.35"))
        self.assertEqual(w["P"], Decimal("0.25"))
        self.assertEqual(w["D"], Decimal("0.20"))
        self.assertEqual(w["R"], Decimal("0.20"))

    def test_ct3_invalid_type(self):
        """CT3：权重类型非法抛 ConfigError。"""
        os.environ["CAMPUSBITE_WEIGHT_T"] = "abc"
        with self.assertRaises(ConfigError) as ctx:
            get_weights()
        self.assertIn("T", str(ctx.exception))
        self.assertIn("abc", str(ctx.exception))

    def test_ct4_negative_weight(self):
        """CT4：权重负值抛 ConfigError。"""
        os.environ["CAMPUSBITE_WEIGHT_T"] = "-0.1"
        with self.assertRaises(ConfigError) as ctx:
            get_weights()
        self.assertIn("T", str(ctx.exception))

    def test_ct5_invalid_sum(self):
        """CT5：权重总和不符抛 ConfigError。"""
        os.environ["CAMPUSBITE_WEIGHT_T"] = "0.10"
        os.environ["CAMPUSBITE_WEIGHT_P"] = "0.10"
        os.environ["CAMPUSBITE_WEIGHT_D"] = "0.10"
        os.environ["CAMPUSBITE_WEIGHT_R"] = "0.10"
        with self.assertRaises(ConfigError) as ctx:
            get_weights()
        self.assertIn("总和", str(ctx.exception))

    def test_ct6_error_message_contains_field_and_value(self):
        """CT6：错误信息包含字段名和非法值。"""
        os.environ["CAMPUSBITE_WEIGHT_P"] = "xyz"
        with self.assertRaises(ConfigError) as ctx:
            get_weights()
        msg = str(ctx.exception)
        self.assertIn("P", msg)
        self.assertIn("xyz", msg)

    def test_default_weights_sum_to_one(self):
        """默认权重总和为 1.0。"""
        self.assertEqual(sum(DEFAULT_WEIGHTS.values()), Decimal("1.00"))

    def test_get_weights_idempotent(self):
        """get_weights() 幂等：重复调用返回相同结果。"""
        w1 = get_weights()
        w2 = get_weights()
        self.assertEqual(w1, w2)


# ---------------------------------------------------------------------------
# T2: Strategy 接口与 Context 测试
# ---------------------------------------------------------------------------

from backend.recommendation.strategy import RecommendationStrategy, RecommendationContext
from backend.recommendation import PreferenceError
from backend.data.repository import FoodRepository
from backend.data.database import DEFAULT_DB


class TestStrategyInterface(unittest.TestCase):
    """Strategy 接口契约测试。"""

    def test_cannot_instantiate_abc(self):
        """RecommendationStrategy 是 ABC，不能直接实例化。"""
        with self.assertRaises(TypeError):
            RecommendationStrategy()

    def test_has_four_abstract_methods(self):
        """接口定义 4 个抽象方法。"""
        abstracts = RecommendationStrategy.__abstractmethods__
        self.assertIn("filter", abstracts)
        self.assertIn("score", abstracts)
        self.assertIn("reasons", abstracts)
        self.assertIn("weights", abstracts)

    def test_subclass_must_implement_all(self):
        """子类必须实现全部 4 个方法才能实例化。"""

        class _Incomplete(RecommendationStrategy):
            def filter(self, food, prefs):
                return True

        with self.assertRaises(TypeError):
            _Incomplete()


class _StubStrategy(RecommendationStrategy):
    """测试用桩策略：所有菜品通过，统一评分。"""

    def filter(self, food, prefs):
        return True

    def score(self, food, prefs):
        return {"T": Decimal("50"), "P": Decimal("50"),
                "D": Decimal("50"), "R": Decimal("50")}

    def reasons(self, food, prefs, dimensions):
        return ["测试理由"]

    def weights(self):
        return {"T": Decimal("0.25"), "P": Decimal("0.25"),
                "D": Decimal("0.25"), "R": Decimal("0.25")}


class _FilterAllStrategy(RecommendationStrategy):
    """测试用桩策略：过滤掉所有菜品。"""

    def filter(self, food, prefs):
        return False

    def score(self, food, prefs):
        return {"T": Decimal("50"), "P": Decimal("50"),
                "D": Decimal("50"), "R": Decimal("50")}

    def reasons(self, food, prefs, dimensions):
        return []

    def weights(self):
        return {"T": Decimal("0.25"), "P": Decimal("0.25"),
                "D": Decimal("0.25"), "R": Decimal("0.25")}


class _IdBasedStrategy(RecommendationStrategy):
    """测试用桩策略：按 food id 评分，用于验证排序。"""

    def filter(self, food, prefs):
        return True

    def score(self, food, prefs):
        fid = Decimal(str(food["id"]))
        return {"T": fid, "P": Decimal("0"), "D": Decimal("0"), "R": Decimal("0")}

    def reasons(self, food, prefs, dimensions):
        return [f"菜品 id={food['id']}"]

    def weights(self):
        return {"T": Decimal("1"), "P": Decimal("0"),
                "D": Decimal("0"), "R": Decimal("0")}


class TestContext(unittest.TestCase):
    """Context 编排逻辑测试。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self.prefs = {"budget": 20, "tastes": [], "avoid": [],
                      "top_k": 3, "only_open": False}

    def test_returns_correct_structure(self):
        """Context 返回 {items, total_candidates, message} 结构。"""
        ctx = RecommendationContext(_StubStrategy())
        result = ctx.execute(self.foods, self.prefs)
        self.assertIn("items", result)
        self.assertIn("total_candidates", result)
        self.assertIn("message", result)

    def test_delegates_filter(self):
        """filter 返回 False 的菜品不出现。"""
        ctx = RecommendationContext(_FilterAllStrategy())
        result = ctx.execute(self.foods, self.prefs)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_candidates"], 0)

    def test_top_k_truncation(self):
        """结果截取 top_k 条。"""
        ctx = RecommendationContext(_StubStrategy())
        result = ctx.execute(self.foods, self.prefs)
        self.assertLessEqual(len(result["items"]), 3)

    def test_sorts_by_score_desc_then_id_asc(self):
        """排序按 (-score, id)：score 降序，同分 id 升序。"""
        ctx = RecommendationContext(_IdBasedStrategy())
        result = ctx.execute(self.foods, {**self.prefs, "top_k": 5})
        items = result["items"]
        for i in range(len(items) - 1):
            s1, s2 = items[i]["score"], items[i + 1]["score"]
            if s1 == s2:
                self.assertLess(items[i]["dish"]["id"], items[i + 1]["dish"]["id"])
            else:
                self.assertGreaterEqual(s1, s2)

    def test_empty_result_message(self):
        """空结果消息含"未自动放宽条件"。"""
        ctx = RecommendationContext(_FilterAllStrategy())
        result = ctx.execute(self.foods, self.prefs)
        self.assertIn("未自动放宽条件", result["message"])

    def test_fewer_results_message(self):
        """候选不足 top_k 时消息含实际数量。"""
        ctx = RecommendationContext(_StubStrategy())
        prefs = {**self.prefs, "top_k": 5}
        result = ctx.execute(self.foods, prefs)
        if len(result["items"]) < 5:
            self.assertIn("道菜品", result["message"])

    def test_total_candidates_equals_filtered_count(self):
        """total_candidates 等于通过过滤的去重候选数。"""
        ctx = RecommendationContext(_StubStrategy())
        result = ctx.execute(self.foods, self.prefs)
        unique_ids = {f["id"] for f in self.foods}
        self.assertEqual(result["total_candidates"], len(unique_ids))

    def test_propagates_preference_error(self):
        """非法偏好抛出 PreferenceError。"""
        ctx = RecommendationContext(_StubStrategy())
        bad = {"budget": -1, "tastes": [], "avoid": [],
               "top_k": 3, "only_open": False}
        with self.assertRaises(PreferenceError):
            ctx.execute(self.foods, bad)

    def test_item_structure(self):
        """每条 item 含 dish/score/dimensions/reasons。"""
        ctx = RecommendationContext(_StubStrategy())
        result = ctx.execute(self.foods, self.prefs)
        for item in result["items"]:
            self.assertIn("dish", item)
            self.assertIn("score", item)
            self.assertIn("dimensions", item)
            self.assertIn("reasons", item)
            for dim in ("T", "P", "D", "R"):
                self.assertIn(dim, item["dimensions"])

    def test_context_no_strategy_type_branching(self):
        """Context 不因策略类型不同产生分支（行为一致性）。"""
        ctx1 = RecommendationContext(_StubStrategy())
        ctx2 = RecommendationContext(_FilterAllStrategy())
        r1 = ctx1.execute(self.foods, self.prefs)
        r2 = ctx2.execute(self.foods, self.prefs)
        self.assertEqual(set(r1.keys()), set(r2.keys()))


# ---------------------------------------------------------------------------
# T3: filters / scoring / reasons 函数集测试
# ---------------------------------------------------------------------------

from backend.recommendation.filters import hard_constraints_pass, matched_tastes
from backend.recommendation.scoring import compute_dimensions
from backend.recommendation.reasons import build_reasons


class TestFilters(unittest.TestCase):
    """硬约束过滤函数测试（对照基线 L50-64）。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self.food_by_id = {f["id"]: f for f in self.foods}

    def test_f1_budget_exceeds(self):
        """F1: price > budget → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": 10, "tastes": [], "avoid": [], "only_open": False}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f1_budget_equal_passes(self):
        """F1: price == budget → True（基线用 > 而非 >=）。"""
        food = self.food_by_id[1]
        prefs = {"budget": 18, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f1_no_budget_passes(self):
        """F1: budget 为 None → 通过。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f2_distance_exceeds(self):
        """F2: distance > max_distance_m → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "max_distance_m": 100, "tastes": [], "avoid": [], "only_open": False}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f2_distance_equal_passes(self):
        """F2: distance == max_distance_m → True。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "max_distance_m": 200, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f3_only_open_false_is_open(self):
        """F3: only_open=True 且 is_open != 'TRUE' → False。"""
        food = self.food_by_id[21]
        self.assertEqual(food["restaurant"]["is_open"], "FALSE")
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": True}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f3_only_open_true_is_open(self):
        """F3: only_open=True 且 is_open == 'TRUE' → 通过。"""
        food = self.food_by_id[1]
        self.assertEqual(food["restaurant"]["is_open"], "TRUE")
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": True}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f3_only_open_false_passes(self):
        """F3: only_open=False → 不检查营业状态。"""
        food = self.food_by_id[21]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f4_avoid_violation(self):
        """F4: avoid 含 restriction_status != 'TRUE' 的项 → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": ["花生"], "only_open": False}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f4_avoid_passes(self):
        """F4: avoid 项全部 restriction_status == 'TRUE' → 通过。"""
        food = self.food_by_id[4]
        prefs = {"budget": None, "tastes": [], "avoid": ["花生"], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f4_no_avoid_passes(self):
        """F4: avoid 为空 → 通过。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f5_meal_period_not_served(self):
        """F5: meal_period 不在 restaurant meal_periods 中 → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False, "meal_period": "早餐"}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f5_meal_period_served(self):
        """F5: meal_period 在 meal_periods 中 → 通过。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False, "meal_period": "午餐"}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f6_min_rating_below(self):
        """F6: rating < min_rating → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False, "min_rating": 4.7}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f6_min_rating_equal_passes(self):
        """F6: rating == min_rating → True（基线用 < 而非 <=）。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False, "min_rating": 4.6}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f7_tastes_no_match(self):
        """F7: tastes 非空且交集为空 → False。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": ["清淡"], "avoid": [], "only_open": False}
        self.assertFalse(hard_constraints_pass(food, prefs))

    def test_f7_tastes_match(self):
        """F7: tastes 非空且有匹配 → 通过。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": ["香辣"], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_f7_no_tastes_passes(self):
        """F7: tastes 为空 → 通过（不检查口味匹配）。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": [], "only_open": False}
        self.assertTrue(hard_constraints_pass(food, prefs))

    def test_matched_tastes_with_match(self):
        """matched_tastes 返回排序后的交集。"""
        food = self.food_by_id[1]
        prefs = {"tastes": ["香辣", "清淡"]}
        self.assertEqual(matched_tastes(food, prefs), ["香辣"])

    def test_matched_tastes_no_match(self):
        """matched_tastes 无匹配返回空列表。"""
        food = self.food_by_id[1]
        prefs = {"tastes": ["清淡", "甜口"]}
        self.assertEqual(matched_tastes(food, prefs), [])

    def test_matched_tastes_empty_prefs(self):
        """matched_tastes 空口味返回空列表。"""
        food = self.food_by_id[1]
        prefs = {"tastes": []}
        self.assertEqual(matched_tastes(food, prefs), [])

    def test_all_constraints_pass(self):
        """全部约束通过 → True。"""
        food = self.food_by_id[4]
        prefs = {"budget": 10, "max_distance_m": 200, "tastes": ["清淡"],
                 "avoid": ["花生"], "only_open": False, "meal_period": "午餐",
                 "min_rating": 4.0}
        self.assertTrue(hard_constraints_pass(food, prefs))


class TestScoring(unittest.TestCase):
    """评分维度计算测试（对照基线 L65-69）。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self.food_by_id = {f["id"]: f for f in self.foods}

    def test_returns_decimal_dict(self):
        """返回 dict[str, Decimal]，键 T/P/D/R。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": []}
        dims = compute_dimensions(food, prefs)
        self.assertIsInstance(dims, dict)
        for key in ("T", "P", "D", "R"):
            self.assertIn(key, dims)
            self.assertIsInstance(dims[key], Decimal)

    def test_t_with_match(self):
        """T: 命中数/口味总数×100。"""
        food = self.food_by_id[1]
        prefs = {"tastes": ["香辣", "清淡"]}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["T"], Decimal(1) / Decimal(2) * 100)

    def test_t_no_tastes(self):
        """T: 无口味时 Decimal(50)。"""
        food = self.food_by_id[1]
        prefs = {"tastes": []}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["T"], Decimal(50))

    def test_p_with_budget(self):
        """P: (1-price/budget)×100，使用 Decimal(str())。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "tastes": []}
        dims = compute_dimensions(food, prefs)
        expected = (1 - Decimal(str(18)) / Decimal(str(20))) * 100
        self.assertEqual(dims["P"], expected)

    def test_p_no_budget(self):
        """P: 无预算时 Decimal(50)。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": []}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["P"], Decimal(50))

    def test_d_with_max_zero(self):
        """D: maximum==0 时 Decimal(100)。"""
        food = self.food_by_id[1]
        prefs = {"max_distance_m": 0, "tastes": []}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["D"], Decimal(100))

    def test_d_with_max_positive(self):
        """D: (1-distance/max)×100，使用 Decimal(str(maximum))。"""
        food = self.food_by_id[1]
        prefs = {"max_distance_m": 400, "tastes": []}
        dims = compute_dimensions(food, prefs)
        expected = (1 - Decimal(200) / Decimal(str(400))) * 100
        self.assertEqual(dims["D"], expected)

    def test_d_no_max(self):
        """D: 无距离上限时 Decimal(50)。"""
        food = self.food_by_id[1]
        prefs = {"max_distance_m": None, "tastes": []}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["D"], Decimal(50))

    def test_r_rating(self):
        """R: rating/5×100，使用 Decimal(str(rating))。"""
        food = self.food_by_id[1]
        prefs = {"tastes": []}
        dims = compute_dimensions(food, prefs)
        expected = Decimal(str(4.6)) / 5 * 100
        self.assertEqual(dims["R"], expected)

    def test_decimal_precision_str_conversion(self):
        """Decimal 精度：price/budget 使用 Decimal(str()) 转换，非 Decimal(float)。"""
        food = {"price": 0.1, "taste_tags": [],
                "restaurant": {"distance_m": 100, "rating": 4.0,
                                "is_open": "TRUE", "meal_periods": ["午餐"]}}
        prefs = {"budget": 1.0, "tastes": []}
        dims = compute_dimensions(food, prefs)
        expected_p = (1 - Decimal(str(0.1)) / Decimal(str(1.0))) * 100
        self.assertEqual(dims["P"], expected_p)
        self.assertNotEqual(dims["P"], (1 - Decimal(0.1) / Decimal(1.0)) * 100)

    def test_all_dimensions_with_full_prefs(self):
        """全偏好下四维评分值与基线公式逐维度一致。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "max_distance_m": 400, "tastes": ["香辣", "清淡"]}
        dims = compute_dimensions(food, prefs)
        self.assertEqual(dims["T"], Decimal(1) / Decimal(2) * 100)
        self.assertEqual(dims["P"], (1 - Decimal(str(18)) / Decimal(str(20))) * 100)
        self.assertEqual(dims["D"], (1 - Decimal(200) / Decimal(str(400))) * 100)
        self.assertEqual(dims["R"], Decimal(str(4.6)) / 5 * 100)


class TestReasons(unittest.TestCase):
    """推荐理由生成测试（对照基线 L72-80）。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self.food_by_id = {f["id"]: f for f in self.foods}

    def test_returns_list_of_strings(self):
        """返回 list[str]。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertIsInstance(reasons, list)
        for r in reasons:
            self.assertIsInstance(r, str)

    def test_r1_price_reason_always_present(self):
        """R1: 价格理由始终存在，含价格值。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("18" in r and "元" in r for r in reasons))

    def test_r1_price_with_budget(self):
        """R1: 有预算时附预算说明。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("20" in r and "预算" in r for r in reasons))

    def test_r1_price_without_budget(self):
        """R1: 无预算时不附预算说明。"""
        food = self.food_by_id[1]
        prefs = {"budget": None, "tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertFalse(any("预算" in r for r in reasons))

    def test_r2_distance_reason_always_present(self):
        """R2: 距离理由始终存在，含距离值。"""
        food = self.food_by_id[1]
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("200" in r and "米" in r for r in reasons))

    def test_r2_distance_with_max(self):
        """R2: 有距离上限时附上限说明。"""
        food = self.food_by_id[1]
        prefs = {"max_distance_m": 500, "tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("500" in r and "上限" in r for r in reasons))

    def test_r3_rating_reason_always_present(self):
        """R3: 评分理由始终存在，含评分值。"""
        food = self.food_by_id[1]
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("4.6" in r and "分" in r for r in reasons))

    def test_r4_taste_reason_only_when_tastes(self):
        """R4: 仅 tastes 非空时追加口味匹配理由。"""
        food = self.food_by_id[1]
        reasons_with = build_reasons(food, {"tastes": ["香辣"], "avoid": []}, {})
        reasons_without = build_reasons(food, {"tastes": [], "avoid": []}, {})
        self.assertTrue(any("口味匹配" in r for r in reasons_with))
        self.assertFalse(any("口味匹配" in r for r in reasons_without))

    def test_r4_taste_reason_content(self):
        """R4: 口味理由含匹配标签。"""
        food = self.food_by_id[1]
        prefs = {"tastes": ["香辣"], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        taste_reason = [r for r in reasons if "口味匹配" in r]
        self.assertEqual(len(taste_reason), 1)
        self.assertIn("香辣", taste_reason[0])

    def test_r5_open_reason_not_unknown(self):
        """R5: is_open != 'UNKNOWN' 时追加营业理由。"""
        food = self.food_by_id[1]
        self.assertEqual(food["restaurant"]["is_open"], "TRUE")
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("营业中" in r for r in reasons))

    def test_r5_open_reason_unknown_skipped(self):
        """R5: is_open == 'UNKNOWN' 时不追加营业理由。"""
        food = self.food_by_id[16]
        self.assertEqual(food["restaurant"]["is_open"], "UNKNOWN")
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertFalse(any("营业" in r and "标记" in r for r in reasons))

    def test_r5_open_false(self):
        """R5: is_open == 'FALSE' 时追加未营业理由。"""
        food = self.food_by_id[21]
        self.assertEqual(food["restaurant"]["is_open"], "FALSE")
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertTrue(any("未营业" in r for r in reasons))

    def test_r6_avoid_reason_only_when_avoid(self):
        """R6: 仅 avoid 非空时追加忌口理由。"""
        food = self.food_by_id[1]
        reasons_with = build_reasons(food, {"tastes": [], "avoid": ["花生"]}, {})
        reasons_without = build_reasons(food, {"tastes": [], "avoid": []}, {})
        self.assertTrue(any("严格排除" in r for r in reasons_with))
        self.assertFalse(any("严格排除" in r for r in reasons_without))

    def test_r6_avoid_reason_content(self):
        """R6: 忌口理由含 avoid 标签。"""
        food = self.food_by_id[1]
        prefs = {"tastes": [], "avoid": ["花生", "大豆"]}
        reasons = build_reasons(food, prefs, {})
        avoid_reason = [r for r in reasons if "严格排除" in r]
        self.assertEqual(len(avoid_reason), 1)
        self.assertIn("花生", avoid_reason[0])
        self.assertIn("大豆", avoid_reason[0])

    def test_reason_order(self):
        """理由顺序: R1→R2→R3→R4→R5→R6。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"], "avoid": ["花生"]}
        reasons = build_reasons(food, prefs, {})
        self.assertEqual(len(reasons), 6)
        self.assertIn("价格", reasons[0])
        self.assertIn("距离", reasons[1])
        self.assertIn("评分", reasons[2])
        self.assertIn("口味匹配", reasons[3])
        self.assertIn("营业", reasons[4])
        self.assertIn("严格排除", reasons[5])

    def test_reason_order_minimal(self):
        """最小理由集: 仅 R1→R2→R3（无 tastes/avoid, is_open=UNKNOWN）。"""
        food = self.food_by_id[16]
        self.assertEqual(food["restaurant"]["is_open"], "UNKNOWN")
        prefs = {"tastes": [], "avoid": []}
        reasons = build_reasons(food, prefs, {})
        self.assertEqual(len(reasons), 3)

    def test_reasons_reference_real_data(self):
        """理由引用 food 真实字段值。"""
        food = self.food_by_id[1]
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"], "avoid": ["花生"]}
        reasons = build_reasons(food, prefs, {})
        full_text = " ".join(reasons)
        self.assertIn(f"{food['price']:g}", full_text)
        self.assertIn(str(food["restaurant"]["distance_m"]), full_text)
        self.assertIn(f"{food['restaurant']['rating']:g}", full_text)


# ---------------------------------------------------------------------------
# T4: DefaultStrategy 行为保持测试（三层验证，design.md §12.4）
# ---------------------------------------------------------------------------

from backend.recommendation.default_strategy import DefaultStrategy
from backend.recommendation import recommend as baseline_recommend


class TestDefaultStrategy(unittest.TestCase):
    """DefaultStrategy 三层行为保持验证。

    对比基线 recommend() 与 RecommendationContext(DefaultStrategy()).execute() 的输出，
    覆盖 AC2/AC9-AC14/AC18。
    """

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}
        self.strategy = DefaultStrategy()
        self.ctx = RecommendationContext(self.strategy)

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)

    def _run_both(self, prefs):
        """同时运行基线和新路径，返回 (baseline_result, new_result)。"""
        baseline = baseline_recommend(self.foods, prefs)
        new = self.ctx.execute(self.foods, prefs)
        return baseline, new

    # --- AC18: 不含内联逻辑 ---

    def test_no_inline_filter_logic(self):
        """AC18: filter 委托 hard_constraints_pass，不含内联逻辑。"""
        import inspect
        src = inspect.getsource(DefaultStrategy.filter)
        self.assertIn("hard_constraints_pass", src)
        self.assertNotIn("restriction_status", src)
        self.assertNotIn("budget", src)

    def test_no_inline_score_logic(self):
        """AC18: score 委托 compute_dimensions，不含内联逻辑。"""
        import inspect
        src = inspect.getsource(DefaultStrategy.score)
        self.assertIn("compute_dimensions", src)
        self.assertNotIn("Decimal", src)

    def test_no_inline_reasons_logic(self):
        """AC18: reasons 委托 build_reasons，不含内联逻辑。"""
        import inspect
        src = inspect.getsource(DefaultStrategy.reasons)
        self.assertIn("build_reasons", src)
        self.assertNotIn("口味匹配", src)

    def test_weights_from_config(self):
        """AC18: weights 委托 get_weights，不硬编码。"""
        import inspect
        src = inspect.getsource(DefaultStrategy.weights)
        self.assertIn("get_weights", src)
        self.assertNotIn("0.35", src)

    # --- AC9: 过滤一致性 ---

    def test_filter_consistency_no_budget(self):
        """AC9: 无预算时过滤结果一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_with_budget(self):
        """AC9: 有预算时过滤结果一致。"""
        prefs = {"budget": 15, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_with_tastes(self):
        """AC9: 有口味时过滤结果一致。"""
        prefs = {"budget": None, "tastes": ["香辣", "清淡"], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_with_avoid(self):
        """AC9: 有忌口时过滤结果一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": ["花生"],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_only_open(self):
        """AC9: only_open=True 时过滤结果一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": [],
                 "only_open": True, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_meal_period(self):
        """AC9: 有时段时过滤结果一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": [],
                 "only_open": False, "meal_period": "早餐", "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_min_rating(self):
        """AC9: 有最低评分时过滤结果一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": [],
                 "only_open": False, "min_rating": 4.5, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    def test_filter_consistency_all_constraints(self):
        """AC9: 全约束同时生效时过滤结果一致。"""
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"],
                 "avoid": ["花生"], "only_open": False,
                 "meal_period": "午餐", "min_rating": 4.0, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])

    # --- AC10: 逐维度评分 + 综合评分一致性 ---

    def test_score_dimensions_consistency(self):
        """AC10 第一层: 逐维度评分 float 值一致。"""
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"],
                 "avoid": [], "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            b_dims = baseline["items"][i]["dimensions"]
            n_dims = new["items"][i]["dimensions"]
            for key in ("T", "P", "D", "R"):
                self.assertEqual(b_dims[key], n_dims[key],
                                 f"维度 {key} 不一致: item {i}")

    def test_composite_score_consistency(self):
        """AC10 第二层: 综合评分 float 值一致。"""
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"],
                 "avoid": [], "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["score"],
                             new["items"][i]["score"],
                             f"综合评分不一致: item {i}")

    def test_score_decimal_precision(self):
        """AC10: DefaultStrategy.score() 返回 Decimal 类型。"""
        food = self.foods[0]
        prefs = {"budget": 20, "tastes": [], "avoid": []}
        dims = self.strategy.score(food, prefs)
        for key in ("T", "P", "D", "R"):
            self.assertIsInstance(dims[key], Decimal)

    def test_weights_match_baseline(self):
        """AC10: DefaultStrategy.weights() 与基线 WEIGHTS 一致。"""
        from backend.recommendation import WEIGHTS
        w = self.strategy.weights()
        for key in ("T", "P", "D", "R"):
            self.assertEqual(w[key], WEIGHTS[key])

    # --- AC12: 排序一致性 ---

    def test_sort_consistency_top_k_3(self):
        """AC12 第三层: top_k=3 排序结果一致。"""
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"],
                             f"排序位置 {i} dish_id 不一致")

    def test_sort_consistency_top_k_4(self):
        """AC12 第三层: top_k=4 排序结果一致。"""
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 4}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])

    def test_sort_consistency_top_k_5(self):
        """AC12 第三层: top_k=5 排序结果一致。"""
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])

    def test_sort_consistency_with_tastes(self):
        """AC12: 有口味时排序结果一致。"""
        prefs = {"budget": 15, "tastes": ["清淡", "鲜香"], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])

    def test_sort_consistency_all_constraints(self):
        """AC12: 全约束时排序结果一致。"""
        prefs = {"budget": 20, "max_distance_m": 800, "tastes": ["香辣", "清淡"],
                 "avoid": ["花生"], "only_open": False,
                 "meal_period": "午餐", "min_rating": 4.0, "top_k": 5}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])

    # --- AC11: 理由一致性 ---

    def test_reasons_consistency(self):
        """AC11: 理由列表逐条一致。"""
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"],
                 "avoid": ["花生"], "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["reasons"],
                             new["items"][i]["reasons"],
                             f"理由不一致: item {i}")

    def test_reasons_consistency_no_tastes_no_avoid(self):
        """AC11: 无口味无忌口时理由一致。"""
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["reasons"],
                             new["items"][i]["reasons"])

    # --- AC13: 消息一致性 ---

    def test_message_normal(self):
        """AC13: 正常结果消息逐字一致。"""
        prefs = {"budget": 50, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        if len(baseline["items"]) == 3:
            self.assertEqual(baseline["message"], new["message"])
            self.assertEqual(baseline["message"], "已按综合评分排序。")

    def test_message_insufficient(self):
        """AC13: 候选不足 top_k 时消息逐字一致。"""
        prefs = {"budget": 5, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["message"], new["message"])
        if 0 < len(baseline["items"]) < 5:
            self.assertIn("道菜品", baseline["message"])

    def test_message_empty_with_tastes(self):
        """AC13: 空结果+有口味时消息逐字一致。"""
        prefs = {"budget": 1, "tastes": ["甜口"], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["items"], [])
        self.assertEqual(new["items"], [])
        self.assertEqual(baseline["message"], new["message"])

    def test_message_empty_no_tastes(self):
        """AC13: 空结果+无口味时消息逐字一致。"""
        prefs = {"budget": 1, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        self.assertEqual(baseline["items"], [])
        self.assertEqual(new["items"], [])
        self.assertEqual(baseline["message"], new["message"])

    # --- AC14: total_candidates 一致性 ---

    def test_total_candidates_consistency(self):
        """AC14: total_candidates 值一致。"""
        for prefs in [
            {"budget": 20, "tastes": [], "avoid": [], "only_open": False, "top_k": 5},
            {"budget": 10, "tastes": ["清淡"], "avoid": [], "only_open": False, "top_k": 3},
            {"budget": 50, "tastes": [], "avoid": ["花生"], "only_open": True, "top_k": 4},
            {"budget": 1, "tastes": ["甜口"], "avoid": [], "only_open": False, "top_k": 3},
        ]:
            baseline, new = self._run_both(prefs)
            self.assertEqual(baseline["total_candidates"], new["total_candidates"],
                             f"total_candidates 不一致: prefs={prefs}")

    # --- AC2: 完整输出逐字段一致 ---

    def test_full_output_consistency(self):
        """AC2: 完整输出 items/total_candidates/message 逐字段一致。"""
        prefs = {"budget": 20, "max_distance_m": 800, "tastes": ["香辣", "清淡"],
                 "avoid": ["花生"], "only_open": False,
                 "meal_period": "午餐", "min_rating": 4.0, "top_k": 5}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])
            self.assertEqual(baseline["items"][i]["score"],
                             new["items"][i]["score"])
            self.assertEqual(baseline["items"][i]["dimensions"],
                             new["items"][i]["dimensions"])
            self.assertEqual(baseline["items"][i]["reasons"],
                             new["items"][i]["reasons"])
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])
        self.assertEqual(baseline["message"], new["message"])

    def test_full_output_no_budget_no_tastes(self):
        """AC2: 无预算无口味时完整输出一致。"""
        prefs = {"budget": None, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        baseline, new = self._run_both(prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])
            self.assertEqual(baseline["items"][i]["score"],
                             new["items"][i]["score"])
            self.assertEqual(baseline["items"][i]["dimensions"],
                             new["items"][i]["dimensions"])
            self.assertEqual(baseline["items"][i]["reasons"],
                             new["items"][i]["reasons"])
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])
        self.assertEqual(baseline["message"], new["message"])


class TestDefaultStrategyPrecision(unittest.TestCase):
    """T4 精度补强：DefaultStrategy 返回值的 Decimal 精度直接验证。

    现有 TestDefaultStrategy 中 test_score_dimensions_consistency 和
    test_composite_score_consistency 比较的是输出 dict 中的 float 值，
    test_score_decimal_precision 仅检查 isinstance 而不比较实际值。

    本测试类直接比较 DefaultStrategy.score() 和 weights() 返回的 Decimal 值，
    预期值独立按基线公式计算（基线 L65-71, L8），不复制新实现输出。
    """

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}
        self.strategy = DefaultStrategy()

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)

    def _find_food(self, food_id):
        for food in self.foods:
            if food["id"] == food_id:
                return food
        raise ValueError(f"food id={food_id} not found")

    # --- 权重 Decimal 直接比较 ---

    def test_weights_decimal_values(self):
        """默认权重 Decimal 值与基线 WEIGHTS 逐键精确一致。"""
        w = self.strategy.weights()
        self.assertEqual(w["T"], Decimal("0.35"))
        self.assertEqual(w["P"], Decimal("0.25"))
        self.assertEqual(w["D"], Decimal("0.20"))
        self.assertEqual(w["R"], Decimal("0.20"))

    def test_weights_sum_decimal(self):
        """权重之和为 Decimal("1.00")，非 float 1.0。"""
        w = self.strategy.weights()
        total = sum(w.values())
        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal("1.00"))

    # --- 四维评分 Decimal 直接比较 ---

    def test_score_dimensions_dish1_with_budget_and_distance(self):
        """菜品1（price=18, distance=200, rating=4.6）四维 Decimal 值精确比较。

        prefs: budget=20, max_distance_m=500, tastes=["香辣"]
        基线公式（L65-69）:
          T = Decimal(1)/Decimal(1)*100
          P = (1 - Decimal("18")/Decimal("20")) * 100
          D = (1 - Decimal(200)/Decimal("500")) * 100
          R = Decimal("4.6")/5 * 100
        """
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)

        expected_T = Decimal(1) / Decimal(1) * 100
        expected_P = (1 - Decimal(str(18)) / Decimal(str(20))) * 100
        expected_D = (1 - Decimal(200) / Decimal(str(500))) * 100
        expected_R = Decimal(str(4.6)) / 5 * 100

        self.assertEqual(dims["T"], expected_T)
        self.assertEqual(dims["P"], expected_P)
        self.assertEqual(dims["D"], expected_D)
        self.assertEqual(dims["R"], expected_R)

    def test_score_dimensions_dish4_different_price(self):
        """菜品4（price=9, distance=200, rating=4.6）验证不同价格的 P 维度。

        prefs: budget=15, max_distance_m=800, tastes=["清淡"]
        """
        food = self._find_food(4)
        prefs = {"budget": 15, "max_distance_m": 800, "tastes": ["清淡"], "avoid": []}
        dims = self.strategy.score(food, prefs)

        expected_T = Decimal(1) / Decimal(1) * 100
        expected_P = (1 - Decimal(str(9)) / Decimal(str(15))) * 100
        expected_D = (1 - Decimal(200) / Decimal(str(800))) * 100
        expected_R = Decimal(str(4.6)) / 5 * 100

        self.assertEqual(dims["T"], expected_T)
        self.assertEqual(dims["P"], expected_P)
        self.assertEqual(dims["D"], expected_D)
        self.assertEqual(dims["R"], expected_R)

    def test_score_dimensions_dish21_decimal_price(self):
        """菜品21（price=3.5, distance=100, rating=3.8）验证小数价格的 Decimal 转换。

        prefs: budget=7, max_distance_m=200, tastes=["清淡"]
        关键：price=3.5 必须通过 Decimal(str(3.5)) 转换，不能直接 Decimal(3.5)。
        """
        food = self._find_food(21)
        prefs = {"budget": 7, "max_distance_m": 200, "tastes": ["清淡"], "avoid": []}
        dims = self.strategy.score(food, prefs)

        expected_T = Decimal(1) / Decimal(1) * 100
        expected_P = (1 - Decimal(str(3.5)) / Decimal(str(7))) * 100
        expected_D = (1 - Decimal(100) / Decimal(str(200))) * 100
        expected_R = Decimal(str(3.8)) / 5 * 100

        self.assertEqual(dims["T"], expected_T)
        self.assertEqual(dims["P"], expected_P)
        self.assertEqual(dims["D"], expected_D)
        self.assertEqual(dims["R"], expected_R)

    # --- 无偏好时的默认值 Decimal 直接比较 ---

    def test_score_no_budget_defaults_to_decimal_50(self):
        """无预算时 P=Decimal(50)，非 float 50。"""
        food = self._find_food(1)
        prefs = {"budget": None, "tastes": [], "avoid": []}
        dims = self.strategy.score(food, prefs)
        self.assertEqual(dims["P"], Decimal(50))

    def test_score_no_max_distance_defaults_to_decimal_50(self):
        """无距离上限时 D=Decimal(50)，非 float 50。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": None, "tastes": [], "avoid": []}
        dims = self.strategy.score(food, prefs)
        self.assertEqual(dims["D"], Decimal(50))

    def test_score_no_tastes_defaults_to_decimal_50(self):
        """无口味时 T=Decimal(50)，非 float 50。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": [], "avoid": []}
        dims = self.strategy.score(food, prefs)
        self.assertEqual(dims["T"], Decimal(50))

    # --- 零距离边界值 ---

    def test_score_zero_max_distance_returns_decimal_100(self):
        """max_distance_m=0 时 D=Decimal(100)。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": 0, "tastes": [], "avoid": []}
        dims = self.strategy.score(food, prefs)
        self.assertEqual(dims["D"], Decimal(100))

    # --- 多口味匹配的 T 维度 ---

    def test_score_partial_taste_match(self):
        """部分口味匹配时 T 维度 Decimal 值精确比较。

        菜品1 taste_tags=["香辣"], prefs tastes=["香辣", "清淡"]
        matched=["香辣"], len=1, len(tastes)=2
        T = Decimal(1)/Decimal(2)*100
        """
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": ["香辣", "清淡"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        expected_T = Decimal(1) / Decimal(2) * 100
        self.assertEqual(dims["T"], expected_T)

    # --- 综合评分 Decimal 直接计算 ---

    def test_composite_score_decimal_computation(self):
        """综合评分 Decimal 精确计算：sum(d × w) 使用 Decimal 运算。

        菜品1, prefs: budget=20, max_distance_m=500, tastes=["香辣"]
        综合评分 = T×0.35 + P×0.25 + D×0.20 + R×0.20
        """
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        weights = self.strategy.weights()

        composite = sum(dims[key] * weights[key] for key in ("T", "P", "D", "R"))
        self.assertIsInstance(composite, Decimal)

        expected_T = Decimal(1) / Decimal(1) * 100
        expected_P = (1 - Decimal(str(18)) / Decimal(str(20))) * 100
        expected_D = (1 - Decimal(200) / Decimal(str(500))) * 100
        expected_R = Decimal(str(4.6)) / 5 * 100
        expected_composite = (
            expected_T * Decimal("0.35")
            + expected_P * Decimal("0.25")
            + expected_D * Decimal("0.20")
            + expected_R * Decimal("0.20")
        )
        self.assertEqual(composite, expected_composite)

    def test_composite_score_decimal_with_decimal_price(self):
        """小数价格的综合评分 Decimal 精确计算。

        菜品21 (price=3.5), prefs: budget=7, max_distance_m=200, tastes=["清淡"]
        """
        food = self._find_food(21)
        prefs = {"budget": 7, "max_distance_m": 200, "tastes": ["清淡"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        weights = self.strategy.weights()

        composite = sum(dims[key] * weights[key] for key in ("T", "P", "D", "R"))
        self.assertIsInstance(composite, Decimal)

        expected_T = Decimal(1) / Decimal(1) * 100
        expected_P = (1 - Decimal(str(3.5)) / Decimal(str(7))) * 100
        expected_D = (1 - Decimal(100) / Decimal(str(200))) * 100
        expected_R = Decimal(str(3.8)) / 5 * 100
        expected_composite = (
            expected_T * Decimal("0.35")
            + expected_P * Decimal("0.25")
            + expected_D * Decimal("0.20")
            + expected_R * Decimal("0.20")
        )
        self.assertEqual(composite, expected_composite)

    # --- 环境变量覆盖权重的 Decimal 精度 ---

    def test_env_override_weights_decimal(self):
        """环境变量覆盖权重后仍为 Decimal 类型且值精确。"""
        os.environ["CAMPUSBITE_WEIGHT_T"] = "0.30"
        os.environ["CAMPUSBITE_WEIGHT_P"] = "0.30"
        os.environ["CAMPUSBITE_WEIGHT_D"] = "0.20"
        os.environ["CAMPUSBITE_WEIGHT_R"] = "0.20"
        w = self.strategy.weights()
        self.assertEqual(w["T"], Decimal("0.30"))
        self.assertEqual(w["P"], Decimal("0.30"))
        self.assertEqual(w["D"], Decimal("0.20"))
        self.assertEqual(w["R"], Decimal("0.20"))


from backend.service.recommendation_service import RecommendationService, STRATEGY_REGISTRY


class TestRegistry(unittest.TestCase):
    """AC33/AC34：显式策略注册表验证。"""

    def test_registry_exists_and_is_dict(self):
        """AC33: STRATEGY_REGISTRY 存在且为 dict。"""
        self.assertIsInstance(STRATEGY_REGISTRY, dict)

    def test_registry_has_default(self):
        """AC33: 注册表包含 "default" 映射。"""
        self.assertIn("default", STRATEGY_REGISTRY)

    def test_registry_default_is_default_strategy(self):
        """AC33: "default" 映射指向 DefaultStrategy 类。"""
        self.assertIs(STRATEGY_REGISTRY["default"], DefaultStrategy)

    def test_registry_no_dynamic_discovery(self):
        """AC34: 注册表不使用动态发现机制。"""
        import inspect
        import backend.service.recommendation_service as svc_module
        src = inspect.getsource(svc_module)
        self.assertNotIn("importlib", src)
        self.assertNotIn("entry_points", src)
        self.assertNotIn("iter_modules", src)
        self.assertNotIn("walk_packages", src)
        self.assertNotIn("pkgutil", src)


class TestRecommendationService(unittest.TestCase):
    """AC17/AC26：RecommendationService 策略选择与推荐执行验证。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)

    def test_service_default_strategy(self):
        """AC17: 默认构造使用 DefaultStrategy。"""
        service = RecommendationService()
        self.assertIsInstance(service._strategy, DefaultStrategy)

    def test_service_explicit_default(self):
        """AC17: 显式 "default" 使用 DefaultStrategy。"""
        service = RecommendationService("default")
        self.assertIsInstance(service._strategy, DefaultStrategy)

    def test_service_none_strategy(self):
        """spec §5.4: strategy_name=None 使用 DefaultStrategy（合法默认值）。"""
        service = RecommendationService(None)
        self.assertIsInstance(service._strategy, DefaultStrategy)

    def test_service_unknown_strategy_raises_valueerror(self):
        """AC26: 未知 strategy_name 抛 ValueError。"""
        with self.assertRaises(ValueError) as cm:
            RecommendationService("unknown")
        self.assertIn("unknown", str(cm.exception))

    def test_service_unknown_raises_at_init_not_recommend(self):
        """design §8.2: ValueError 在 __init__ 阶段抛出，非 recommend 阶段。"""
        with self.assertRaises(ValueError):
            RecommendationService("nonexistent")
        service = RecommendationService("default")
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        result = service.recommend(self.foods, prefs)
        self.assertIn("items", result)

    def test_service_unknown_no_silent_fallback(self):
        """AC26: 未知策略不静默回退到默认策略。"""
        try:
            service = RecommendationService("unknown")
            self.fail("应抛出 ValueError，不应静默回退")
        except ValueError:
            pass
        service = RecommendationService("default")
        self.assertIsInstance(service._strategy, DefaultStrategy)

    def test_service_recommend_delegates_to_context(self):
        """Service.recommend 委托 RecommendationContext.execute。"""
        service = RecommendationService("default")
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": [],
                 "only_open": False, "top_k": 5}
        context = RecommendationContext(DefaultStrategy())
        service_result = service.recommend(self.foods, prefs)
        context_result = context.execute(self.foods, prefs)
        self.assertEqual(len(service_result["items"]), len(context_result["items"]))
        for i in range(len(service_result["items"])):
            self.assertEqual(service_result["items"][i]["dish"]["id"],
                             context_result["items"][i]["dish"]["id"])

    def test_service_recommend_matches_baseline(self):
        """Service 默认策略输出与基线 recommend() 一致。"""
        service = RecommendationService("default")
        prefs = {"budget": 20, "max_distance_m": 800, "tastes": ["香辣", "清淡"],
                 "avoid": ["花生"], "only_open": False,
                 "meal_period": "午餐", "min_rating": 4.0, "top_k": 5}
        baseline = baseline_recommend(self.foods, prefs)
        new = service.recommend(self.foods, prefs)
        self.assertEqual(len(baseline["items"]), len(new["items"]))
        for i in range(len(baseline["items"])):
            self.assertEqual(baseline["items"][i]["dish"]["id"],
                             new["items"][i]["dish"]["id"])
            self.assertEqual(baseline["items"][i]["score"],
                             new["items"][i]["score"])
            self.assertEqual(baseline["items"][i]["dimensions"],
                             new["items"][i]["dimensions"])
            self.assertEqual(baseline["items"][i]["reasons"],
                             new["items"][i]["reasons"])
        self.assertEqual(baseline["total_candidates"], new["total_candidates"])
        self.assertEqual(baseline["message"], new["message"])

    def test_service_default_weights_unchanged(self):
        """Service 默认策略权重未被修改。"""
        service = RecommendationService("default")
        w = service._strategy.weights()
        self.assertEqual(w["T"], Decimal("0.35"))
        self.assertEqual(w["P"], Decimal("0.25"))
        self.assertEqual(w["D"], Decimal("0.20"))
        self.assertEqual(w["R"], Decimal("0.20"))


class TestThinWrapper(unittest.TestCase):
    """AC7/AC19：recommend() 薄封装与兼容导出验证。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)

    def test_public_imports_compatible(self):
        """AC7: from backend.recommendation import recommend/validate_preferences/PreferenceError 有效。"""
        from backend.recommendation import recommend, validate_preferences, PreferenceError
        self.assertTrue(callable(recommend))
        self.assertTrue(callable(validate_preferences))
        self.assertTrue(issubclass(PreferenceError, ValueError))

    def test_recommend_function_body_under_10_lines(self):
        """AC19: recommend() 函数体不超过 10 行。"""
        import inspect
        from backend.recommendation import recommend
        src = inspect.getsource(recommend)
        body_lines = [l for l in src.splitlines() if l.strip() and not l.strip().startswith(('#', '"""', "'''"))]
        body_lines = [l for l in body_lines if not l.startswith('def ')]
        self.assertLessEqual(len(body_lines), 10,
                             f"recommend() 函数体 {len(body_lines)} 行，超过 10 行上限")

    def test_recommend_delegates_to_service(self):
        """recommend() 委托 RecommendationService("default")。"""
        import inspect
        from backend.recommendation import recommend
        src = inspect.getsource(recommend)
        self.assertIn("RecommendationService", src)
        self.assertIn('"default"', src)

    def test_recommend_output_matches_service(self):
        """recommend() 输出与 RecommendationService("default").recommend() 一致。"""
        prefs = {"budget": 20, "max_distance_m": 800, "tastes": ["香辣", "清淡"],
                 "avoid": ["花生"], "only_open": False,
                 "meal_period": "午餐", "min_rating": 4.0, "top_k": 5}
        from backend.recommendation import recommend
        wrapper_result = recommend(self.foods, prefs)
        service_result = RecommendationService("default").recommend(self.foods, prefs)
        self.assertEqual(len(wrapper_result["items"]), len(service_result["items"]))
        for i in range(len(wrapper_result["items"])):
            self.assertEqual(wrapper_result["items"][i]["dish"]["id"],
                             service_result["items"][i]["dish"]["id"])
            self.assertEqual(wrapper_result["items"][i]["score"],
                             service_result["items"][i]["score"])
        self.assertEqual(wrapper_result["total_candidates"], service_result["total_candidates"])
        self.assertEqual(wrapper_result["message"], service_result["message"])

    def test_recommend_returns_correct_structure(self):
        """recommend() 返回 {items, total_candidates, message} 结构。"""
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        from backend.recommendation import recommend
        result = recommend(self.foods, prefs)
        self.assertIn("items", result)
        self.assertIn("total_candidates", result)
        self.assertIn("message", result)
        self.assertIsInstance(result["items"], list)
        self.assertIsInstance(result["total_candidates"], int)
        self.assertIsInstance(result["message"], str)

    def test_recommend_raises_preference_error(self):
        """recommend() 对非法偏好抛 PreferenceError。"""
        from backend.recommendation import recommend, PreferenceError
        prefs = {"budget": -10, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        with self.assertRaises(PreferenceError):
            recommend(self.foods, prefs)

    def test_weights_still_available(self):
        """WEIGHTS 仍可从 backend.recommendation 导入且值正确。"""
        from backend.recommendation import WEIGHTS
        self.assertEqual(WEIGHTS["T"], Decimal("0.35"))
        self.assertEqual(WEIGHTS["P"], Decimal("0.25"))
        self.assertEqual(WEIGHTS["D"], Decimal("0.20"))
        self.assertEqual(WEIGHTS["R"], Decimal("0.20"))

    def test_no_circular_import(self):
        """导入 backend.recommendation 不产生循环导入错误。"""
        import importlib
        import backend.recommendation
        importlib.reload(backend.recommendation)


class TestStartupValidation(unittest.TestCase):
    """模块级配置启动校验：使用独立进程验证 5 类启动场景。"""

    def _run_subprocess(self, env_vars):
        """在独立子进程中导入 backend.recommendation，返回 (returncode, stdout, stderr)。"""
        import subprocess
        env = dict(os.environ)
        for v in _ENV_VARS:
            env.pop(v, None)
        for k, val in env_vars.items():
            if val is not None:
                env[k] = val
            else:
                env.pop(k, None)
        result = subprocess.run(
            [".venv/Scripts/python.exe", "-c",
             "from backend.recommendation import recommend; print('IMPORT_OK')"],
            capture_output=True, text=True, env=env, cwd="E:\\校园美食推荐助手",
            timeout=15,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def test_startup_legal_default(self):
        """合法默认配置：导入成功。"""
        rc, out, err = self._run_subprocess({})
        self.assertEqual(rc, 0, f"默认配置导入失败: {err}")
        self.assertIn("IMPORT_OK", out)

    def test_startup_legal_override(self):
        """合法环境变量覆盖：导入成功。"""
        rc, out, err = self._run_subprocess({
            "CAMPUSBITE_WEIGHT_T": "0.30",
            "CAMPUSBITE_WEIGHT_P": "0.30",
            "CAMPUSBITE_WEIGHT_D": "0.20",
            "CAMPUSBITE_WEIGHT_R": "0.20",
        })
        self.assertEqual(rc, 0, f"合法覆盖导入失败: {err}")
        self.assertIn("IMPORT_OK", out)

    def test_startup_invalid_type(self):
        """非法权重类型：导入失败并出现 ConfigError。"""
        rc, out, err = self._run_subprocess({
            "CAMPUSBITE_WEIGHT_T": "abc",
        })
        self.assertNotEqual(rc, 0, "非法类型应导入失败")
        self.assertIn("ConfigError", err)

    def test_startup_negative_weight(self):
        """权重为负值：导入失败并出现 ConfigError。"""
        rc, out, err = self._run_subprocess({
            "CAMPUSBITE_WEIGHT_T": "-0.35",
        })
        self.assertNotEqual(rc, 0, "负值权重应导入失败")
        self.assertIn("ConfigError", err)

    def test_startup_invalid_sum(self):
        """权重总和不为 1：导入失败并出现 ConfigError。"""
        rc, out, err = self._run_subprocess({
            "CAMPUSBITE_WEIGHT_T": "0.50",
            "CAMPUSBITE_WEIGHT_P": "0.25",
            "CAMPUSBITE_WEIGHT_D": "0.20",
            "CAMPUSBITE_WEIGHT_R": "0.20",
        })
        self.assertNotEqual(rc, 0, "总和不符应导入失败")
        self.assertIn("ConfigError", err)


from backend.recommendation.distance_priority_strategy import DistancePriorityStrategy, DISTANCE_PRIORITY_WEIGHTS


class TestDistancePriority(unittest.TestCase):
    """AC3/AC24/AC25/AC30-AC32：DistancePriorityStrategy 验证。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}
        self.strategy = DistancePriorityStrategy()
        self.default_strategy = DefaultStrategy()

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)

    def _find_food(self, food_id):
        for food in self.foods:
            if food["id"] == food_id:
                return food
        raise ValueError(f"food id={food_id} not found")

    # --- AC3: 接口实现 ---

    def test_implements_all_abstract_methods(self):
        """AC3: DistancePriorityStrategy 实现全部 4 个抽象方法。"""
        self.assertTrue(callable(self.strategy.filter))
        self.assertTrue(callable(self.strategy.score))
        self.assertTrue(callable(self.strategy.reasons))
        self.assertTrue(callable(self.strategy.weights))

    def test_is_recommendation_strategy_subclass(self):
        """AC3: DistancePriorityStrategy 是 RecommendationStrategy 子类。"""
        self.assertIsInstance(self.strategy, RecommendationStrategy)

    # --- AC25: 权重 ---

    def test_weights_values(self):
        """AC25: 权重为 T=0.20, P=0.20, D=0.40, R=0.20。"""
        w = self.strategy.weights()
        self.assertEqual(w["T"], Decimal("0.20"))
        self.assertEqual(w["P"], Decimal("0.20"))
        self.assertEqual(w["D"], Decimal("0.40"))
        self.assertEqual(w["R"], Decimal("0.20"))

    def test_weights_sum_is_one(self):
        """AC25: 权重总和精确等于 Decimal("1.00")。"""
        w = self.strategy.weights()
        total = sum(w.values())
        self.assertIsInstance(total, Decimal)
        self.assertEqual(total, Decimal("1.00"))

    def test_weights_are_decimal(self):
        """AC25: 权重值为 Decimal 类型。"""
        w = self.strategy.weights()
        for key in ("T", "P", "D", "R"):
            self.assertIsInstance(w[key], Decimal)

    def test_default_weights_unchanged(self):
        """spec §2.4: DistancePriorityStrategy 不修改 DefaultStrategy 的默认权重。"""
        dw = self.default_strategy.weights()
        self.assertEqual(dw["T"], Decimal("0.35"))
        self.assertEqual(dw["P"], Decimal("0.25"))
        self.assertEqual(dw["D"], Decimal("0.20"))
        self.assertEqual(dw["R"], Decimal("0.20"))

    # --- AC24: 过滤一致性 ---

    def test_filter_same_as_default(self):
        """AC24: filter() 与 DefaultStrategy.filter() 对相同输入返回相同结果。"""
        prefs_list = [
            {"budget": 20, "tastes": [], "avoid": [], "only_open": False, "top_k": 5},
            {"budget": 10, "tastes": ["香辣"], "avoid": [], "only_open": False, "top_k": 3},
            {"budget": 50, "tastes": [], "avoid": ["花生"], "only_open": True, "top_k": 4},
            {"budget": 15, "max_distance_m": 500, "tastes": ["清淡"], "avoid": [],
             "only_open": False, "meal_period": "午餐", "min_rating": 4.0, "top_k": 5},
        ]
        for prefs in prefs_list:
            for food in self.foods:
                d_result = self.default_strategy.filter(food, prefs)
                dp_result = self.strategy.filter(food, prefs)
                self.assertEqual(d_result, dp_result,
                                 f"filter 不一致: food={food['id']}, prefs={prefs}")

    def test_filter_uses_hard_constraints_pass(self):
        """AC24: filter 委托 hard_constraints_pass。"""
        import inspect
        src = inspect.getsource(DistancePriorityStrategy.filter)
        self.assertIn("hard_constraints_pass", src)

    # --- 评分一致性 ---

    def test_score_same_as_default(self):
        """spec §2.4: score() 与 DefaultStrategy.score() 对相同输入返回相同结果。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"], "avoid": []}
        d_dims = self.default_strategy.score(food, prefs)
        dp_dims = self.strategy.score(food, prefs)
        for key in ("T", "P", "D", "R"):
            self.assertEqual(d_dims[key], dp_dims[key], f"维度 {key} 不一致")

    def test_score_uses_compute_dimensions(self):
        """spec §2.4: score 委托 compute_dimensions。"""
        import inspect
        src = inspect.getsource(DistancePriorityStrategy.score)
        self.assertIn("compute_dimensions", src)

    # --- AC30: 理由数据一致性 ---

    def test_reasons_appends_distance_priority(self):
        """AC30: reasons() 在 build_reasons 基础上追加距离优先说明。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        base_reasons = build_reasons(food, prefs, dims)
        full_reasons = self.strategy.reasons(food, prefs, dims)
        self.assertEqual(len(full_reasons), len(base_reasons) + 1)
        for i in range(len(base_reasons)):
            self.assertEqual(full_reasons[i], base_reasons[i])

    def test_reasons_appended_uses_real_distance(self):
        """AC30: 追加理由使用 food["restaurant"]["distance_m"] 真实字段值。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        reasons = self.strategy.reasons(food, prefs, dims)
        distance = food["restaurant"]["distance_m"]
        appended = reasons[-1]
        self.assertIn(str(distance), appended)

    def test_reasons_does_not_fabricate_data(self):
        """AC30: 追加理由不编造距离、用户偏好或营业信息。"""
        food = self._find_food(4)
        prefs = {"budget": 20, "tastes": ["清淡"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        reasons = self.strategy.reasons(food, prefs, dims)
        appended = reasons[-1]
        distance = food["restaurant"]["distance_m"]
        self.assertIn(str(distance), appended)
        self.assertNotIn("营业", appended)
        self.assertNotIn("预算", appended)

    # --- AC31: 理由体现距离优先语义 ---

    def test_reasons_reflects_distance_priority(self):
        """AC31: 追加理由包含距离排序依据说明。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        reasons = self.strategy.reasons(food, prefs, dims)
        appended = reasons[-1]
        self.assertIn("距离", appended)
        self.assertIn("排序", appended)

    # --- AC32: 理由不声称绝对更近 ---

    def test_reasons_no_absolute_closeness_claim(self):
        """AC32: 追加理由不包含"最近""比其他更近"等绝对比较措辞。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "tastes": ["香辣"], "avoid": []}
        dims = self.strategy.score(food, prefs)
        reasons = self.strategy.reasons(food, prefs, dims)
        appended = reasons[-1]
        self.assertNotIn("最近", appended)
        self.assertNotIn("更近", appended)
        self.assertNotIn("比其他", appended)

    # --- 理由顺序 ---

    def test_reasons_order_preserved(self):
        """spec §2.4: 追加理由在最后，不修改已有理由顺序。"""
        food = self._find_food(1)
        prefs = {"budget": 20, "max_distance_m": 500, "tastes": ["香辣"],
                 "avoid": ["花生"], "only_open": False, "top_k": 5}
        dims = self.strategy.score(food, prefs)
        base_reasons = build_reasons(food, prefs, dims)
        full_reasons = self.strategy.reasons(food, prefs, dims)
        for i in range(len(base_reasons)):
            self.assertEqual(full_reasons[i], base_reasons[i])

    # --- 注册表 ---

    def test_registry_has_distance_priority(self):
        """AC33: 注册表包含 "distance_priority" 映射。"""
        self.assertIn("distance_priority", STRATEGY_REGISTRY)

    def test_registry_distance_priority_is_correct_class(self):
        """AC33: "distance_priority" 映射指向 DistancePriorityStrategy 类。"""
        self.assertIs(STRATEGY_REGISTRY["distance_priority"], DistancePriorityStrategy)

    def test_service_can_select_distance_priority(self):
        """RecommendationService 可通过名称选择距离优先策略。"""
        service = RecommendationService("distance_priority")
        self.assertIsInstance(service._strategy, DistancePriorityStrategy)

    def test_service_distance_priority_produces_results(self):
        """RecommendationService 距离优先策略产生有效推荐结果。"""
        service = RecommendationService("distance_priority")
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 5}
        result = service.recommend(self.foods, prefs)
        self.assertIn("items", result)
        self.assertIn("total_candidates", result)
        self.assertIn("message", result)
        self.assertGreater(len(result["items"]), 0)

    def test_service_distance_priority_reasons_have_appendix(self):
        """距离优先策略推荐结果中理由包含距离优先追加说明。"""
        service = RecommendationService("distance_priority")
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        result = service.recommend(self.foods, prefs)
        for item in result["items"]:
            last_reason = item["reasons"][-1]
            self.assertIn("距离", last_reason)
            self.assertIn("排序", last_reason)

    def test_distance_priority_different_sorting_than_default(self):
        """距离优先策略与默认策略排序不同（验证权重确实影响排序）。"""
        service_default = RecommendationService("default")
        service_dp = RecommendationService("distance_priority")
        prefs = {"budget": 30, "max_distance_m": 2000, "tastes": [],
                 "avoid": [], "only_open": False, "top_k": 5}
        default_result = service_default.recommend(self.foods, prefs)
        dp_result = service_dp.recommend(self.foods, prefs)
        default_ids = [item["dish"]["id"] for item in default_result["items"]]
        dp_ids = [item["dish"]["id"] for item in dp_result["items"]]
        self.assertEqual(len(default_ids), len(dp_ids))
        self.assertNotEqual(default_ids, dp_ids,
                            "距离优先策略应产生与默认策略不同的排序")

    def test_unknown_strategy_still_raises_valueerror(self):
        """AC26: 未知策略仍抛 ValueError。"""
        with self.assertRaises(ValueError):
            RecommendationService("nonexistent")


class TestExtension(unittest.TestCase):
    """AC21-AC23, AC35：扩展性验证 — 新增策略无须修改现有代码。"""

    def setUp(self):
        repo = FoodRepository(DEFAULT_DB)
        self.foods = repo.dishes()
        self._saved_env = {v: os.environ.pop(v, None) for v in _ENV_VARS}
        self._saved_registry = dict(STRATEGY_REGISTRY)

    def tearDown(self):
        for v in _ENV_VARS:
            if self._saved_env[v] is not None:
                os.environ[v] = self._saved_env[v]
            else:
                os.environ.pop(v, None)
        STRATEGY_REGISTRY.clear()
        STRATEGY_REGISTRY.update(self._saved_registry)

    # --- AC23: 新增策略仅须创建类 + 注册 ---

    def test_create_and_register(self):
        """AC23: 创建策略类 + 注册到 STRATEGY_REGISTRY 即可使用，无须其他改动。"""

        class PricePriorityStrategy(RecommendationStrategy):
            """测试用：价格优先策略，仅验证扩展流程。"""

            def filter(self, food, prefs):
                return hard_constraints_pass(food, prefs)

            def score(self, food, prefs):
                return compute_dimensions(food, prefs)

            def reasons(self, food, prefs, dimensions):
                return build_reasons(food, prefs, dimensions)

            def weights(self):
                return {
                    "T": Decimal("0.10"),
                    "P": Decimal("0.50"),
                    "D": Decimal("0.20"),
                    "R": Decimal("0.20"),
                }

        STRATEGY_REGISTRY["price_priority"] = PricePriorityStrategy
        service = RecommendationService("price_priority")
        prefs = {"budget": 20, "tastes": [], "avoid": [],
                 "only_open": False, "top_k": 3}
        result = service.recommend(self.foods, prefs)
        self.assertIn("items", result)
        self.assertIn("total_candidates", result)
        self.assertIn("message", result)
        self.assertIsInstance(service._strategy, PricePriorityStrategy)

    def test_create_and_register_weights_effective(self):
        """AC23: 新注册策略的权重确实生效（与默认策略排序不同）。"""

        class RatingPriorityStrategy(RecommendationStrategy):
            """测试用：评分优先策略。"""

            def filter(self, food, prefs):
                return hard_constraints_pass(food, prefs)

            def score(self, food, prefs):
                return compute_dimensions(food, prefs)

            def reasons(self, food, prefs, dimensions):
                return build_reasons(food, prefs, dimensions)

            def weights(self):
                return {
                    "T": Decimal("0.10"),
                    "P": Decimal("0.10"),
                    "D": Decimal("0.10"),
                    "R": Decimal("0.70"),
                }

        STRATEGY_REGISTRY["rating_priority"] = RatingPriorityStrategy
        service_new = RecommendationService("rating_priority")
        service_default = RecommendationService("default")
        prefs = {"budget": 30, "max_distance_m": 2000, "tastes": [],
                 "avoid": [], "only_open": False, "top_k": 5}
        new_ids = [item["dish"]["id"] for item in service_new.recommend(self.foods, prefs)["items"]]
        default_ids = [item["dish"]["id"] for item in service_default.recommend(self.foods, prefs)["items"]]
        self.assertNotEqual(new_ids, default_ids,
                            "评分优先策略应产生与默认策略不同的排序")

    # --- AC21: 无须修改 DefaultStrategy 或 RecommendationContext ---

    def test_no_modification_needed_for_default_strategy(self):
        """AC21: DefaultStrategy 源码不含对新策略的引用。"""
        import inspect
        source = inspect.getsource(DefaultStrategy)
        self.assertNotIn("price_priority", source)
        self.assertNotIn("rating_priority", source)
        self.assertNotIn("DistancePriority", source)

    def test_no_modification_needed_for_context(self):
        """AC21: RecommendationContext 源码不含对具体策略类型的引用。"""
        import inspect
        source = inspect.getsource(RecommendationContext)
        self.assertNotIn("DefaultStrategy", source)
        self.assertNotIn("DistancePriority", source)
        self.assertNotIn("isinstance", source)

    # --- AC35: 新增策略不修改 Context（Context 无策略类型分支）---

    def test_context_no_strategy_type_branches(self):
        """AC35: RecommendationContext 中无 if/else 或 isinstance 针对策略类型。"""
        import inspect
        source = inspect.getsource(RecommendationContext)
        self.assertNotIn("isinstance", source,
                         "Context 不应使用 isinstance 检查策略类型")
        for strategy_name in ("Default", "DistancePriority", "PricePriority"):
            self.assertNotIn(strategy_name, source,
                             f"Context 不应引用具体策略类 {strategy_name}")

    def test_context_only_calls_strategy_methods(self):
        """AC35: Context 仅通过 self._strategy 调用 4 个接口方法。"""
        import inspect
        source = inspect.getsource(RecommendationContext)
        self.assertIn("self._strategy.filter", source)
        self.assertIn("self._strategy.score", source)
        self.assertIn("self._strategy.weights", source)
        self.assertIn("self._strategy.reasons", source)

    # --- AC22: 无须修改 app.py ---

    def test_app_py_no_strategy_references(self):
        """AC22: app.py 不引用任何具体策略名称。"""
        import inspect
        from backend import app as app_module
        source = inspect.getsource(app_module)
        self.assertNotIn("distance_priority", source)
        self.assertNotIn("DistancePriority", source)
        self.assertNotIn("DefaultStrategy", source)
        self.assertNotIn("STRATEGY_REGISTRY", source)
        self.assertNotIn("RecommendationService", source)

    def test_app_py_uses_recommend_function(self):
        """AC22: app.py 通过 recommend() 函数调用推荐，与策略解耦。"""
        import inspect
        from backend import app as app_module
        source = inspect.getsource(app_module)
        self.assertIn("recommend", source,
                      "app.py 应通过 recommend() 调用推荐")

    # --- 扩展流程完整性 ---

    def test_extension_full_flow(self):
        """AC21+AC22+AC23+AC35: 完整扩展流程 — 创建类→注册→使用，无须改现有代码。"""

        class TastePriorityStrategy(RecommendationStrategy):
            """测试用：口味优先策略。"""

            def filter(self, food, prefs):
                return hard_constraints_pass(food, prefs)

            def score(self, food, prefs):
                return compute_dimensions(food, prefs)

            def reasons(self, food, prefs, dimensions):
                return build_reasons(food, prefs, dimensions)

            def weights(self):
                return {
                    "T": Decimal("0.60"),
                    "P": Decimal("0.15"),
                    "D": Decimal("0.15"),
                    "R": Decimal("0.10"),
                }

        STRATEGY_REGISTRY["taste_priority"] = TastePriorityStrategy

        service = RecommendationService("taste_priority")
        prefs = {"budget": 25, "tastes": ["香辣"], "avoid": [],
                 "only_open": False, "top_k": 3}
        result = service.recommend(self.foods, prefs)
        self.assertGreater(len(result["items"]), 0,
                           "口味优先策略应返回结果")
        for item in result["items"]:
            self.assertIn("score", item)
            self.assertIn("dimensions", item)
            self.assertIn("reasons", item)
            self.assertIn("dish", item)
        self.assertIsInstance(service._strategy, TastePriorityStrategy)
        self.assertIsInstance(service._strategy, RecommendationStrategy)


if __name__ == "__main__":
    unittest.main()
