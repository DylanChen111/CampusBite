# 技术设计：推荐策略 Strategy 模式重构

> 特性标识：`refactor-recommendation-strategy`
> 创建日期：2026-10-21
> 状态：待人工审查（Pending Review）
> 依据规格：`spec.md`（Rev C 冻结）、`proposal.md`（Rev C 冻结）
> 基线依据：`baseline.md`

---

## 1. 当前架构与目标架构的差异

### 1.1 当前架构（基线 `backend/recommendation.py`）

```
recommendation.py（单文件，91 行）
├── WEIGHTS = {...}                    # 模块级硬编码常量（L8）
├── class PreferenceError(ValueError)  # 异常类（L11-12）
├── def validate_preferences(p)        # 偏好验证（L15-32）
└── def recommend(foods, p)            # 单体函数（L35-91）
      ├── validate_preferences(p)      # 偏好验证
      ├── for food in foods:           # 遍历菜品
      │     ├── validate_record()      # 数据校验（L41-45）
      │     ├── 去重（L46-48）
      │     ├── 7 × if...continue      # 硬约束过滤（L50-64）
      │     ├── dimensions = {T,P,D,R} # 评分计算（L65-71）
      │     ├── reasons = [...]        # 理由生成（L72-80）
      │     └── scored.append()        # 结果收集（L81-82）
      ├── scored.sort()               # 排序（L83）
      ├── items = scored[:top_k]      # 截取（L84）
      └── message = ...               # 消息（L85-90）
```

**问题**：六类职责耦合在一个函数内，权重硬编码，策略不可扩展，过滤/评分/理由无法独立测试。

### 1.2 目标架构

```
backend/
├── config/
│   ├── __init__.py
│   └── recommendation.py             # 权重配置 + ConfigError + get_weights()
├── recommendation/                    # 包（替代单文件）
│   ├── __init__.py                   # re-export recommend/validate_preferences/PreferenceError
│   ├── strategy.py                   # RecommendationStrategy(ABC) + RecommendationContext
│   ├── filters.py                    # 硬约束过滤函数集（7 项）
│   ├── scoring.py                    # 评分维度计算函数集（T/P/D/R）
│   ├── reasons.py                    # 推荐理由生成函数集
│   ├── default_strategy.py           # DefaultStrategy
│   └── distance_priority_strategy.py # DistancePriorityStrategy
├── service/
│   ├── __init__.py
│   └── recommendation_service.py     # RecommendationService + STRATEGY_REGISTRY
└── recommendation.py                 # 兼容入口（删除，由包替代）
```

### 1.3 差异总结

| 维度 | 当前 | 目标 |
|------|------|------|
| 文件结构 | 1 个 `.py` 文件 | 3 个包（config/recommendation/service）共 10 个 `.py` 文件 |
| 推荐逻辑 | `recommend()` 单体函数 | Strategy 接口 + Context 编排 + 2 个具体策略 |
| 权重来源 | 模块级常量 `WEIGHTS` | `config.recommendation.get_weights()` + 环境变量 |
| 策略扩展 | 修改函数内部 | 新建类 + 注册表映射 |
| 可测试性 | 仅整体验证 | filters/scoring/reasons/strategy 可独立单元测试 |
| 导入路径 | `from backend.recommendation import recommend` | 不变（包 `__init__.py` re-export） |

---

## 2. RecommendationStrategy 接口设计

### 2.1 接口定义

```python
# 文件：backend/recommendation/strategy.py

from abc import ABC, abstractmethod
from decimal import Decimal

class RecommendationStrategy(ABC):
    """推荐策略抽象接口。"""

    @abstractmethod
    def filter(self, food: dict, prefs: dict) -> bool:
        """硬约束过滤。True=通过，False=排除。"""

    @abstractmethod
    def score(self, food: dict, prefs: dict) -> dict[str, Decimal]:
        """评分计算。返回各维度分值（0-100），键 T/P/D/R。"""

    @abstractmethod
    def reasons(self, food: dict, prefs: dict, dimensions: dict) -> list[str]:
        """推荐理由生成。每条引用 food 真实字段值。"""

    @abstractmethod
    def weights(self) -> dict[str, Decimal]:
        """返回权重字典，值域 0-1，总和=1.0。"""
```

### 2.2 方法职责隔离

| 方法 | 可读取 | 可计算 | 不可做 |
|------|--------|--------|--------|
| `filter` | `food`, `prefs` | bool 判定 | 评分、理由、排序 |
| `score` | `food`, `prefs` | Decimal 维度分 | 过滤、理由、加权 |
| `reasons` | `food`, `prefs`, `dimensions` | str 列表 | 评分、过滤 |
| `weights` | 无 | Decimal 权重 | 依赖 food/prefs |

### 2.3 设计依据

- spec §2.1 方法输入输出契约表
- spec §5.1 接口约束（SHALL 提供 4 个抽象方法）
- 基线 `recommendation.py` L50-80：过滤、评分、理由三段逻辑可清晰分离

---

## 3. RecommendationContext 职责与调用流程

### 3.1 类定义

```python
# 文件：backend/recommendation/strategy.py

class RecommendationContext:
    def __init__(self, strategy: RecommendationStrategy):
        self._strategy = strategy

    def execute(self, foods: list[dict], prefs: dict) -> dict:
        validate_preferences(prefs)          # 偏好验证（保留基线 L36）
        budget = prefs.get("budget")
        tastes = prefs.get("tastes", [])
        scored, seen = [], set()

        for food in foods:
            # 数据校验（保留基线 L41-45）
            validate_record(food, "dish")
            restaurant = food.get("restaurant")
            validate_record(restaurant, "restaurant")
            if food["restaurant_id"] != restaurant["id"]:
                raise DataValidationError("菜品与场所关联不一致")
            # 去重（保留基线 L46-48）
            if food["id"] in seen:
                continue
            seen.add(food["id"])
            # 委托策略
            if not self._strategy.filter(food, prefs):
                continue
            dimensions = self._strategy.score(food, prefs)
            score = sum(dimensions[k] * w for k, w in self._strategy.weights().items())
            reason_list = self._strategy.reasons(food, prefs, dimensions)
            scored.append((score, food["id"], {
                "dish": food, "score": float(score),
                "dimensions": {k: float(v) for k, v in dimensions.items()},
                "reasons": reason_list
            }))

        # 排序截取（保留基线 L83-84）
        scored.sort(key=lambda e: (-e[0], e[1]))
        top_k = prefs.get("top_k", 5)
        items = [e[2] for e in scored[:top_k]]
        # 消息（保留基线 L85-90）
        message = self._build_message(items, scored, tastes, top_k)
        return {"items": items, "total_candidates": len(scored), "message": message}
```

### 3.2 Context 保留的职责（不委托策略）

| 职责 | 基线行号 | 说明 |
|------|---------|------|
| 偏好验证 | L36 | `validate_preferences(prefs)` |
| 数据校验 | L41-45 | `validate_record` + 关联一致性 |
| 去重 | L46-48 | 按 `food["id"]` 去重 |
| 综合分计算 | L71 | `sum(dimensions[k] * weights[k])` |
| 排序 | L83 | `(-score, id)` 复合键 |
| 截取 | L84 | `scored[:top_k]` |
| 消息生成 | L85-90 | 空结果/不足/正常三种文案 |

### 3.3 Context 不包含的逻辑

- 具体硬约束判定 → 委托 `strategy.filter()`
- 具体维度评分 → 委托 `strategy.score()`
- 具体理由文案 → 委托 `strategy.reasons()`
- 权重值 → 委托 `strategy.weights()`
- **无 `if/else` 或 `isinstance` 针对策略类型**（spec §5.1 AC20）

### 3.4 调用流程图

```
RecommendationService.recommend(foods, prefs)
  │
  ├── strategy = STRATEGY_REGISTRY[strategy_name]()
  ├── context = RecommendationContext(strategy)
  └── context.execute(foods, prefs)
        │
        ├── validate_preferences(prefs)
        ├── for food in foods:
        │     ├── validate_record(food)
        │     ├── 去重检查
        │     ├── strategy.filter(food, prefs)  →  False? skip
        │     ├── strategy.score(food, prefs)   →  dimensions
        │     ├── score = Σ(dimensions × strategy.weights())
        │     └── strategy.reasons(food, prefs, dimensions) → reasons
        ├── sort(scored, key=(-score, id))
        ├── items = scored[:top_k]
        └── message = build_message(...)
```

---

## 4. DefaultStrategy 迁移方案

### 4.1 类结构

```python
# 文件：backend/recommendation/default_strategy.py

from backend.config.recommendation import get_weights
from backend.recommendation.filters import hard_constraints_pass
from backend.recommendation.scoring import compute_dimensions
from backend.recommendation.reasons import build_reasons

class DefaultStrategy(RecommendationStrategy):
    def filter(self, food, prefs):
        return hard_constraints_pass(food, prefs)

    def score(self, food, prefs):
        return compute_dimensions(food, prefs)

    def reasons(self, food, prefs, dimensions):
        return build_reasons(food, prefs, dimensions)

    def weights(self):
        return get_weights()
```

### 4.2 迁移映射（基线代码 → 新模块）

| 基线代码 | 迁移目标 | 说明 |
|---------|---------|------|
| L50-64（7 个 `if...continue`） | `filters.py:hard_constraints_pass()` | 返回 bool，True=全通过 |
| L62-63（口味命中计算） | `filters.py` 内部 | `matched` 计算移入过滤函数 |
| L65-69（T/P/D/R 公式） | `scoring.py:compute_dimensions()` | 返回 `dict[str, Decimal]` |
| L72-80（理由拼接） | `reasons.py:build_reasons()` | 返回 `list[str]` |
| L8（`WEIGHTS`） | `config/recommendation.py:DEFAULT_WEIGHTS` | 通过 `get_weights()` 读取 |
| L71（综合分） | `RecommendationContext.execute()` | Context 保留加权求和 |
| L41-48（校验+去重） | `RecommendationContext.execute()` | Context 保留 |
| L83-90（排序+消息） | `RecommendationContext.execute()` | Context 保留 |

### 4.3 filters.py 详细设计

```python
# 文件：backend/recommendation/filters.py

from backend.data.restrictions import restriction_status

def hard_constraints_pass(food: dict, prefs: dict) -> bool:
    """检查 7 项硬约束，全部通过返回 True。"""
    budget = prefs.get("budget")
    maximum = prefs.get("max_distance_m")
    tastes = prefs.get("tastes", [])
    avoid = prefs.get("avoid", [])
    restaurant = food["restaurant"]
    price = food["price"]
    distance = restaurant["distance_m"]
    rating = restaurant["rating"]

    # F1 预算（基线 L50）
    if budget is not None and price > budget:
        return False
    # F2 距离（基线 L52）
    if maximum is not None and distance > maximum:
        return False
    # F3 营业（基线 L54）
    if prefs.get("only_open") and restaurant["is_open"] != "TRUE":
        return False
    # F4 忌口（基线 L56）
    if any(restriction_status(food, term) != "TRUE" for term in avoid):
        return False
    # F5 时段（基线 L58）
    if prefs.get("meal_period") and prefs["meal_period"] not in restaurant["meal_periods"]:
        return False
    # F6 评分（基线 L60）
    if prefs.get("min_rating") is not None and rating < prefs["min_rating"]:
        return False
    # F7 口味命中（基线 L62-63）
    matched = sorted(set(tastes) & set(food["taste_tags"]))
    if tastes and not matched:
        return False
    return True

def matched_tastes(food: dict, prefs: dict) -> list[str]:
    """返回口味匹配标签（供 scoring/reasons 复用）。"""
    tastes = prefs.get("tastes", [])
    return sorted(set(tastes) & set(food["taste_tags"]))
```

### 4.4 scoring.py 详细设计

```python
# 文件：backend/recommendation/scoring.py

from decimal import Decimal
from backend.recommendation.filters import matched_tastes

def compute_dimensions(food: dict, prefs: dict) -> dict[str, Decimal]:
    """计算四维评分（基线 L65-69）。"""
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
```

### 4.5 reasons.py 详细设计

```python
# 文件：backend/recommendation/reasons.py

from backend.recommendation.filters import matched_tastes

def build_reasons(food: dict, prefs: dict, dimensions: dict) -> list[str]:
    """生成推荐理由（基线 L72-80）。"""
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
```

---

## 5. DistancePriorityStrategy 实现方案

### 5.1 类结构

```python
# 文件：backend/recommendation/distance_priority_strategy.py

from decimal import Decimal
from backend.recommendation.strategy import RecommendationStrategy
from backend.recommendation.filters import hard_constraints_pass
from backend.recommendation.scoring import compute_dimensions
from backend.recommendation.reasons import build_reasons

DISTANCE_PRIORITY_WEIGHTS = {
    "T": Decimal("0.20"),
    "P": Decimal("0.20"),
    "D": Decimal("0.40"),
    "R": Decimal("0.20"),
}

class DistancePriorityStrategy(RecommendationStrategy):
    def filter(self, food, prefs):
        return hard_constraints_pass(food, prefs)  # 复用，与 DefaultStrategy 一致

    def score(self, food, prefs):
        return compute_dimensions(food, prefs)  # 复用，与 DefaultStrategy 一致

    def reasons(self, food, prefs, dimensions):
        base = build_reasons(food, prefs, dimensions)  # 基础理由
        distance = food["restaurant"]["distance_m"]
        base.append(f"本策略以距离为主要排序依据，当前菜品所属场所模拟距离为 {distance} 米。")
        return base

    def weights(self):
        return DISTANCE_PRIORITY_WEIGHTS
```

### 5.2 与 DefaultStrategy 的差异

| 方法 | DefaultStrategy | DistancePriorityStrategy |
|------|----------------|------------------------|
| `filter` | `hard_constraints_pass()` | **相同**（复用 `filters.py`） |
| `score` | `compute_dimensions()` | **相同**（复用 `scoring.py`） |
| `reasons` | `build_reasons()` | `build_reasons()` + **追加距离优先说明** |
| `weights` | `get_weights()`（默认 0.35/0.25/0.20/0.20） | **固定** 0.20/0.20/0.40/0.20 |

### 5.3 理由语义满足性

追加理由 `"本策略以距离为主要排序依据，当前菜品所属场所模拟距离为 {distance} 米。"` 满足 spec §2.4.1 约束：
1. ✅ 体现距离是优先排序依据
2. ✅ 使用 `food["restaurant"]["distance_m"]` 真实字段
3. ✅ 不声称比其他候选更近
4. ✅ 不编造数据
5. ✅ 可自动化测试验证（AC30）

---

## 6. STRATEGY_REGISTRY 注册与选择机制

### 6.1 注册表定义

```python
# 文件：backend/service/recommendation_service.py

from backend.recommendation.default_strategy import DefaultStrategy
from backend.recommendation.distance_priority_strategy import DistancePriorityStrategy
from backend.recommendation.strategy import RecommendationContext

STRATEGY_REGISTRY = {
    "default": DefaultStrategy,
    "distance_priority": DistancePriorityStrategy,
}
```

### 6.2 RecommendationService

```python
class RecommendationService:
    def __init__(self, strategy_name: str = "default"):
        if strategy_name not in STRATEGY_REGISTRY:
            raise ValueError(f"未知推荐策略: {strategy_name}")
        self._strategy = STRATEGY_REGISTRY[strategy_name]()

    def recommend(self, foods: list[dict], prefs: dict) -> dict:
        context = RecommendationContext(self._strategy)
        return context.execute(foods, prefs)
```

### 6.3 选择流程

```
strategy_name="default" → STRATEGY_REGISTRY["default"] → DefaultStrategy()
strategy_name="distance_priority" → STRATEGY_REGISTRY["distance_priority"] → DistancePriorityStrategy()
strategy_name="unknown" → ValueError（不悄悄切换）
strategy_name=None → 默认 "default"（合法默认值）
```

### 6.4 扩展方式

新增策略仅需：
1. 创建 `backend/recommendation/my_strategy.py`，实现 `RecommendationStrategy` 接口
2. 在 `STRATEGY_REGISTRY` 中添加 `"my_strategy": MyStrategy`
3. **不修改** `RecommendationContext`、`DefaultStrategy`、`app.py`

---

## 7. 评分权重配置

### 7.1 配置模块

```python
# 文件：backend/config/recommendation.py

import os
from decimal import Decimal

class ConfigError(ValueError):
    """推荐配置非法，应用无法安全启动。"""

DEFAULT_WEIGHTS = {
    "T": Decimal("0.35"),
    "P": Decimal("0.25"),
    "D": Decimal("0.20"),
    "R": Decimal("0.20"),
}

_ENV_MAP = {
    "T": "CAMPUSBITE_WEIGHT_T",
    "P": "CAMPUSBITE_WEIGHT_P",
    "D": "CAMPUSBITE_WEIGHT_D",
    "R": "CAMPUSBITE_WEIGHT_R",
}

def get_weights() -> dict[str, Decimal]:
    """读取并校验推荐权重配置。"""
    weights = {}
    for key, env_var in _ENV_MAP.items():
        raw = os.environ.get(env_var)
        if raw is None:
            weights[key] = DEFAULT_WEIGHTS[key]
        else:
            try:
                weights[key] = Decimal(raw)
            except Exception:
                raise ConfigError(f"权重 {key} 环境变量 {env_var} 值 '{raw}' 无法解析为数值")
    # 校验范围
    for key, value in weights.items():
        if value < 0 or value > 1:
            raise ConfigError(f"权重 {key} 值 {value} 超出合法范围 [0, 1]")
    # 校验总和
    total = sum(weights.values())
    if total != Decimal("1.00"):
        raise ConfigError(f"权重总和 {total} 不等于 1.0（T={weights['T']}, P={weights['P']}, D={weights['D']}, R={weights['R']}）")
    return weights
```

### 7.2 配置位置与读取方式

| 项 | 值 |
|----|----|
| 配置文件 | `backend/config/recommendation.py` |
| 默认值 | `DEFAULT_WEIGHTS`（T=0.35, P=0.25, D=0.20, R=0.20） |
| 环境变量 | `CAMPUSBITE_WEIGHT_T/_P/_D/_R` |
| 读取方式 | `os.environ.get()` → `Decimal()` 解析 |
| 校验时机 | **应用启动时**（`recommendation/__init__.py` 模块级主动调用 `get_weights()`） |
| 缓存 | 模块级单例（启动时读取一次） |

### 7.3 启动阶段主动配置校验（实施约束确认新增）

> **问题**：`get_weights()` 仅在 `DefaultStrategy.weights()` 被调用时执行，而首次调用发生在第一次推荐请求时。如果不主动校验，非法配置将延迟到第一次请求才暴露，违反 spec §3.3.1 "阻止应用以非法配置启动"要求。

**启动校验机制**：

`app.py:11` 的 `from .recommendation import PreferenceError, recommend` 是**模块级导入**。因此 `app.py` 加载时必然执行 `recommendation/__init__.py`。在 `__init__.py` 模块级代码中主动调用 `get_weights()`，即可在应用启动时触发配置校验：

```python
# 文件：backend/recommendation/__init__.py

from backend.config.recommendation import get_weights  # T1 产出

# 模块级主动校验 — app.py 加载时触发，非法配置阻止启动
_weights = get_weights()

# ... 其余 re-export 代码 ...
```

**校验链路**：

```
应用启动 / 模块加载
  └── app.py 加载
        └── from .recommendation import ...（模块级导入，L11）
              └── recommendation/__init__.py 加载
                    └── get_weights() 调用（模块级）
                          ├── 合法 → 返回权重，应用正常启动
                          └── 非法 → ConfigError 向上传播
                                └── app.py 加载失败 → 应用无法启动
```

**保证**：
- **MUST**：`recommendation/__init__.py` MUST 在模块级调用 `get_weights()`，确保 `app.py` 加载时触发校验。
- **MUST NOT**：校验 MUST NOT 延迟到第一次推荐请求。
- **MUST NOT**：`app.py` MUST NOT 被修改（校验通过 `__init__.py` 模块级代码触发，不需要修改 `app.py`）。

---

## 8. ConfigError 和未知策略异常处理路径

### 8.1 ConfigError 处理路径

```
应用启动
  └── get_weights() 调用
        ├── 环境变量类型非法 → ConfigError("权重 T 环境变量 ... 值 'abc' 无法解析为数值")
        ├── 权重存在负值 → ConfigError("权重 T 值 -0.1 超出合法范围 [0, 1]")
        └── 权重总和 ≠ 1.0 → ConfigError("权重总和 0.9 不等于 1.0（...）")
              │
              └── 应用启动失败（异常向上传播，不捕获不回退）
```

### 8.2 未知策略异常处理路径

```
RecommendationService(strategy_name="unknown")
  └── "unknown" not in STRATEGY_REGISTRY
        └── raise ValueError("未知推荐策略: unknown")
              │
              └── app.py 异常处理器捕获 → 503 DATA_UNAVAILABLE
```

> **注意**：`ValueError` 在 `app.py` 中由通用异常处理器捕获（基线 L44-47 已有 `sqlite3.Error` 处理器覆盖 503）。由于 `app.py` 不修改，`ValueError` 会由 FastAPI 默认 500 处理器处理。如需 503，须在 `RecommendationService` 层捕获并转为已有异常类型。但 spec 约束 `app.py` 不修改，因此策略选择在 `recommend()` 函数内部完成（通过 `__init__.py` 薄封装），`ValueError` 在 `recommend()` 内抛出，由 `app.py` 的 `recommendations` 端点已有的 `try/except` 捕获。

### 8.3 异常处理与现有 app.py 的兼容

基线 `app.py:52-61` 的 `recommendations` 端点：
```python
@app.post("/api/recommend")
def recommendations(preferences: RecommendRequest):
    from .recommendation import validate_preferences
    values = preferences.model_dump()
    try:
        validate_preferences(values)
    except PreferenceError as exc:
        return JSONResponse(status_code=422, ...)
    repo = repository()
    return {**recommend(repo.dishes(), values), "metadata": repo.metadata()}
```

重构后 `recommend()` 内部抛出的 `ValueError`（未知策略）和 `DataValidationError`（数据校验）不被 `try/except PreferenceError` 捕获，会向上传播至 FastAPI 异常处理器。基线 `app.py:39-47` 已注册 `DataValidationError` → 503 和 `FileNotFoundError`/`sqlite3.Error` → 503 处理器。`ValueError` 无专门处理器，将返回 500。

**设计决策（实施约束确认修订）**：

1. **ValueError 抛出边界**：未知策略名称 MUST 在策略选择边界（`RecommendationService.__init__`）抛出 `ValueError`，MUST NOT 延迟到推荐计算阶段，MUST NOT 静默回退到默认策略。
2. **默认 API 调用不受影响**：`recommend()` 薄封装内部使用固定策略名 `"default"`，不暴露策略选择参数。因此 `app.py` 调用路径（`POST /api/recommend`）不会触发未知策略异常，请求和响应协议不变。
3. **内部接口异常**：未知策略异常仅在直接使用 `RecommendationService(strategy_name=...)` 传入非法名称时触发，用于测试和未来扩展。
4. **测试要求**：T8 中 MUST 包含 `TestUnknownStrategy` 测试类，验证传入未知名称时在 `__init__` 阶段抛出 `ValueError`，而非在 `recommend()` 调用时抛出。

---

## 9. 推荐理由生成与真实数据的对应关系

### 9.1 DefaultStrategy 理由数据来源

| 理由序号 | 文案模板 | 数据来源字段 | 基线行号 |
|---------|---------|-------------|---------|
| R1 | `"菜品价格为 {price:g} 元..."` | `food["price"]` | L72 |
| R2 | `"所属场所模拟距离为 {distance} 米..."` | `food["restaurant"]["distance_m"]` | L73 |
| R3 | `"所属场所模拟评分为 {rating:g} 分..."` | `food["restaurant"]["rating"]` | L74 |
| R4 | `"口味匹配标签：{matched}..."` | `set(tastes) & set(food["taste_tags"])` | L76 |
| R5 | `"所属场所...标记为营业中/未营业。"` | `food["restaurant"]["is_open"]` | L78 |
| R6 | `"模拟配方声明符合严格排除条件：{avoid}..."` | `prefs["avoid"]` | L80 |

### 9.2 DistancePriorityStrategy 追加理由

| 理由 | 文案模板 | 数据来源字段 | 约束 |
|------|---------|-------------|------|
| R7 | `"本策略以距离为主要排序依据，当前菜品所属场所模拟距离为 {distance} 米。"` | `food["restaurant"]["distance_m"]` | spec §2.4.1 五条约束 |

### 9.3 真实数据保证

- `food` 和 `food["restaurant"]` 由 `FoodRepository.dishes()` 从 SQLite 读取，经 `validate_record()` 校验字段完整性
- `price`、`distance_m`、`rating` 为数据库字段，由 `schema.sql` CHECK 约束保证合法
- `taste_tags`、`is_open`、`meal_periods` 由 `validation.py` 验证
- 理由中所有 `{variable}` 插值均来自上述已验证字段，不编造数据

---

## 10. 与 Repository、API 和现有测试的依赖关系

### 10.1 与 Repository 的关系

```
app.py recommendations 端点
  └── repo = FoodRepository(db_path)       # 不修改
  └── foods = repo.dishes()                # 无参数，全量数据
  └── recommend(foods, values)             # 薄封装 → RecommendationService
        └── context.execute(foods, prefs)
              └── strategy.filter(food, prefs)  # 过滤由策略负责
```

- **不修改** `data/repository.py`、`data/database.py`、`data/validation.py`、`data/restrictions.py`
- `filters.py` 依赖 `data/restrictions.py` 的 `restriction_status()`（已有模块，不修改）
- `RecommendationService` 调用 `repo.dishes()` **无参数**，不与 Repository 的过滤参数重叠

### 10.2 与 API 的关系

- `app.py` **不修改**（spec §5.5 AC8）
- `POST /api/recommend` 请求/响应结构不变（spec §4.1-4.2）
- `recommend()` 函数签名不变（spec §5.5）
- 导入路径 `from backend.recommendation import recommend` 通过包 `__init__.py` re-export 保持不变

### 10.3 与现有测试的关系

| 测试文件 | 方法数 | 重构影响 | 处理方式 |
|---------|--------|---------|---------|
| `test_recommendation.py` | 19 | 无（行为不变） | 不修改，须全部通过（AC2） |
| `test_api.py` | 14 | 无（API 不变） | 不修改，须全部通过（AC1） |
| `test_data.py` | 22 | 无（数据层不变） | 不修改，须全部通过（AC1） |
| `test_strategy.py`（新增） | — | 新增 | 覆盖策略接口、配置、新策略（T8） |

### 10.4 recommendation/__init__.py re-export 设计

```python
# 文件：backend/recommendation/__init__.py

from backend.config.recommendation import get_weights
from backend.recommendation.strategy import RecommendationContext
from backend.recommendation.default_strategy import DefaultStrategy
from backend.data.validation import DataValidationError, validate_record
from backend.data.restrictions import restriction_status

# 模块级主动配置校验 — app.py 加载时触发，非法配置阻止启动
_weights = get_weights()

class PreferenceError(ValueError):
    pass

def validate_preferences(p):
    # 从基线 recommendation.py L15-32 原样迁移
    ...

def recommend(foods, p):
    # 薄封装（≤10 行）
    service = RecommendationService("default")
    return service.recommend(foods, p)
```

> `validate_preferences` 和 `PreferenceError` 从基线 `recommendation.py` 原样迁移至 `__init__.py`，保证 `app.py` 的 `from .recommendation import validate_preferences, PreferenceError, recommend` 不变。
>
> **启动校验**：模块级 `_weights = get_weights()` 在 `app.py` 加载 `from .recommendation import ...` 时执行，非法配置抛 `ConfigError` 阻止应用启动（见 §7.3）。

---

## 11. 兼容性、风险和回滚方案

### 11.1 兼容性保证

| 维度 | 保证方式 |
|------|---------|
| 导入兼容 | `recommendation/__init__.py` re-export `recommend`/`validate_preferences`/`PreferenceError` |
| API 协议 | `app.py` 不修改，请求/响应结构不变 |
| 数据库 | 不修改 `schema.sql`/`seed.py`/`storage/` |
| 前端 | 不修改 `frontend/` |
| 测试 | 现有 55 个测试不修改，须全部通过 |

### 11.2 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Decimal 精度差异 | 中 | `scoring.py` 严格复现基线 `Decimal(str(...))` 转换；AC10 逐维度验证值一致（见 §12） |
| 排序稳定性差异 | 低 | Context 保留 `(-score, id)` 复合键排序；AC12 验证 |
| 理由文案差异 | 低 | `reasons.py` 逐字复现基线 L72-80；AC11 验证 |
| 包导入路径冲突 | 低 | `recommendation.py` 文件删除后由 `recommendation/` 包替代，Python 自动解析 |
| 环境变量未设置 | 无 | 回退 `DEFAULT_WEIGHTS`（合法行为） |
| 配置校验延迟 | 中→已解决 | `__init__.py` 模块级调用 `get_weights()`，启动时校验（见 §7.3） |

### 11.3 回滚方案

| 步骤 | 操作 |
|------|------|
| 1 | 恢复 `backend/recommendation.py` 单文件版本（git revert） |
| 2 | 删除 `backend/recommendation/`、`backend/service/`、`backend/config/` 包 |
| 3 | 删除 `backend/tests/test_strategy.py` |
| 4 | 运行 `python -m unittest discover -s backend/tests -v` 确认 55 个测试通过 |

> 回滚不涉及数据库或前端变更，可快速执行。

### 11.4 渐进式实施保护

- **T1-T2 完成后**：接口和配置就位，但 `recommend()` 仍可使用旧逻辑（未切换）
- **T4 完成后**：`DefaultStrategy` 行为验证通过（AC9-AC14），此时切换 `recommend()` 至新路径
- **T9 回归验证**：55 个现有测试全部通过后，确认行为不变
- 任一阶段测试失败 → 停止，不继续后续任务

---

## 12. Decimal 精度与行为保持验证要求（实施约束确认新增）

### 12.1 Decimal 转换方式

- **MUST**：`scoring.py` 中所有 `Decimal` 构造 MUST 使用 `Decimal(str(value))` 转换方式，与基线 `recommendation.py` L65-69 完全一致。
- **MUST NOT**：MUST NOT 直接使用 `Decimal(value)`（浮点数直接构造会引入精度差异）。
- **MUST**：`price`、`budget`、`distance`、`maximum`、`rating` 均须先 `str()` 再 `Decimal()`。

**基线对照**：
```python
# 基线 L67（正确方式）
"P": (1 - Decimal(str(price)) / Decimal(str(budget))) * 100

# 禁止方式（精度差异）
"P": (1 - Decimal(price) / Decimal(budget)) * 100
```

### 12.2 评分计算顺序与舍入规则

- **MUST**：维度评分计算顺序 MUST 为 T → P → D → R（与基线 L66-69 字典构造顺序一致）。
- **MUST**：综合分计算 MUST 为 `sum(dimensions[key] * weight for key, weight in weights.items())`（与基线 L71 一致）。
- **MUST**：MUST NOT 在计算过程中引入额外舍入（`quantize`/`round`），保持 `Decimal` 全精度。
- **MUST**：仅在输出时转为 `float`（基线 L81-82），排序使用 `Decimal` 原值。

### 12.3 排序规则

- **MUST**：排序 MUST 使用 `key=lambda entry: (-entry[0], entry[1])`（基线 L83），即 `(-score, dish_id)` 复合键。
- **MUST**：`score` 降序（`-score` 升序），同分时 `dish_id` 升序。
- **MUST**：排序在 `Decimal` 精度下进行，MUST NOT 先转 `float` 再排序（可能引入同分误判）。

### 12.4 行为保持验证要求

> **不得仅使用少量最终推荐结果相同作为行为保持的充分证据。**

行为保持验证 MUST 分三个层级逐级对比：

| 层级 | 验证内容 | 对应 AC | 验证方法 |
|------|---------|---------|---------|
| **第一层：逐维度评分** | 对相同 `food` + `prefs`，`DefaultStrategy.score()` 返回的 T/P/D/R 各维度 `Decimal` 值 == 基线 L65-69 计算值 | AC10 | 逐维度断言 `assert new_dims["T"] == baseline_dims["T"]`（四维各一条） |
| **第二层：综合评分** | 对相同维度值和权重，综合分 `sum(d × w)` 的 `Decimal` 值 == 基线 L71 计算值 | AC10 | 断言 `assert new_score == baseline_score`（Decimal 精度对比） |
| **第三层：最终排序** | 对相同候选集，排序后的 `items` 顺序（含同分 tie-breaking）== 基线 L83-84 排序结果 | AC12 | 逐位置断言 `assert new_items[i]["dish"]["id"] == baseline_items[i]["dish"]["id"]` |

**补充验证**：
- AC9：逐条菜品验证 `filter()` 返回值 == 基线 `continue` 排除逻辑
- AC11：逐条理由字符串断言 `assert new_reasons == baseline_reasons`（列表逐元素对比）
- AC13：三种消息场景（空结果/不足/正常）逐字断言
- AC14：`total_candidates` 值断言

**测试数据要求**：
- MUST 使用 `seed.py` 中的真实种子数据（6 餐厅 + 30 菜品）构造测试用例
- MUST 覆盖边界场景：无口味/无预算/无距离/零距离/空候选/候选不足/top_k=3/4/5
- MUST 包含同分场景（验证 tie-breaking 排序规则）
