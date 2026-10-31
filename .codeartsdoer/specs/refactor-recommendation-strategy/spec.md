# 规格：推荐策略 Strategy 模式重构

> 特性标识：`refactor-recommendation-strategy`
> 创建日期：2026-10-15
> 最后修订：2026-10-20（Rev C — 冻结 Q1/Q2/Q3 人工决策）
> 状态：待人工审查（Pending Review）
> 基线依据：`baseline.md`
> 重构方向：方向一（推荐引擎策略模式重构）

---

## 修订记录

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| A | 2026-10-15 | 初始版本 |
| B | 2026-10-20 | 对照真实基线代码补充行为保持精确清单；修订配置非法处理为启动失败而非静默回退；修订策略不存在为报错而非悄悄切换；明确接口职责约束；明确 Decorator 非核心验收 |
| C | 2026-10-20 | 冻结 Q1/Q2/Q3 人工决策：确认配置非法启动失败不回退不增加宽松选项；冻结距离优先理由语义与数据约束；明确显式策略注册表机制及扩展约束 |

---

## 1. 概述

将 `backend/recommendation.py` 的单体 `recommend()` 函数重构为 Strategy 模式。推荐流程拆分为可独立替换的策略组件，评分权重外置为配置。默认策略下行为与重构前完全一致。

### 1.1 重构边界

| 允许修改 | 禁止修改 |
|----------|----------|
| `backend/recommendation/`（新建包） | 数据库结构（`schema.sql`、`seed.py`、`storage/`） |
| `backend/service/`（新建包） | 前端任何文件（`frontend/`） |
| `backend/config/`（新建包） | API 输入输出协议（路径、请求体、响应体） |
| `backend/tests/`（新增测试文件） | `backend/data/`（数据访问层） |
| | `backend/app.py`（路由层，通过 re-export 保持兼容） |

### 1.2 不变量

重构前后以下必须完全一致（对照 `recommendation.py` 真实代码）：
- `POST /api/recommend` 的请求体 schema（`RecommendRequest`）
- 响应体结构（`items` / `total_candidates` / `message` / `metadata`）
- 每条 item 结构（`dish` / `score` / `dimensions` / `reasons`）
- 评分公式 `Score = 0.35T + 0.25P + 0.20D + 0.20R`（默认策略下）
- 硬约束过滤规则（7 项，详见第 2.3 节行为保持清单）
- 排序稳定性（`(-score, id)` 复合键，score 降序 id 升序）
- 去重逻辑（按 `food["id"]` 去重，保留首次出现）
- 错误响应（422 / 503 / 404）

---

## 2. Strategy 模式设计

### 2.1 Strategy 接口

```
文件：backend/recommendation/strategy.py

class RecommendationStrategy(ABC):
    """推荐策略抽象接口。"""
```

**方法输入输出契约**：

| 方法 | 输入 | 输出 | 职责约束 |
|------|------|------|---------|
| `filter(food, prefs)` | `food`: 单条菜品 dict（含嵌套 `restaurant`）；`prefs`: 偏好 dict | `bool`：`True` 通过硬约束，`False` 排除 | 仅判定硬约束，不计算评分、不生成理由 |
| `score(food, prefs)` | `food`: 单条菜品 dict；`prefs`: 偏好 dict | `dict[str, Decimal]`：各维度分值，键为 `"T"`/`"P"`/`"D"`/`"R"`，值域 0–100 | 仅计算维度分，不加权、不排序 |
| `reasons(food, prefs, dimensions)` | `food`: 菜品 dict；`prefs`: 偏好 dict；`dimensions`: `score()` 返回值 | `list[str]`：理由字符串列表 | 仅生成理由，每条理由 MUST 引用 `food` 或 `food["restaurant"]` 的真实字段值 |
| `weights()` | 无 | `dict[str, Decimal]`：权重字典，键为维度标识，值域 0–1，总和 = 1.0 | 返回当前策略的权重配置 |

**接口职责约束（Rev B 新增）**：

- **MUST**：每个方法职责单一，`filter` 不评分、`score` 不过滤、`reasons` 不改变评分。
- **MUST**：`reasons()` 返回的每条字符串 MUST 引用传入 `food` 的真实字段值，MUST NOT 生成无法从字段验证的描述。
- **MUST**：策略实现不得直接访问数据库或 Repository，仅基于传入的 `food` 和 `prefs` 计算。

### 2.2 Context 角色

```
文件：backend/recommendation/strategy.py

class RecommendationContext:
    """推荐上下文，持有一个策略实例并编排推荐流程。"""

    def __init__(self, strategy: RecommendationStrategy):
        self._strategy = strategy

    def execute(self, foods: list[dict], prefs: dict) -> dict:
        """执行推荐流程，返回 {items, total_candidates, message}。"""
```

**Context 职责约束（Rev B 新增）**：

- **MUST**：Context 仅负责流程编排（遍历→委托策略→去重→排序→截取→消息），不负责具体评分算法。
- **MUST NOT**：Context 中 MUST NOT 出现针对具体策略的 `if/else` 分支或 `isinstance` 判断。所有策略差异通过 `self._strategy` 的多态方法调用体现。
- **MUST NOT**：Context MUST NOT 重复执行 Repository 已完成的过滤规则。Context 接收的 `foods` 为全量菜品列表（由 `RecommendationService` 调用 `repo.dishes()` 无参数获取），所有过滤由 `strategy.filter()` 统一负责。
- **MUST**：Context 保留数据校验职责（`validate_record` + 关联一致性检查 + 去重），与基线 `recommend()` L41-48 行为一致。

### 2.3 Concrete Strategy A — DefaultStrategy

```
文件：backend/recommendation/default_strategy.py

class DefaultStrategy(RecommendationStrategy):
    """默认推荐策略：四维加权评分。迁移自 recommendation.py recommend() 的现有逻辑。"""
```

**行为保持精确清单（对照 `recommendation.py` 真实代码）**：

> 以下每一项均引用基线代码行号，重构后 `DefaultStrategy` + `RecommendationContext` 必须逐条复现。

#### 2.3.1 硬约束过滤语义（基线 L50-64）

| 序号 | 约束 | 基线代码 | `filter()` 必须复现的语义 |
|------|------|---------|------------------------|
| F1 | 预算 | `if budget is not None and price > budget: continue` | `budget` 非空且 `food["price"] > budget` → 返回 `False`。**注意：使用 `>` 而非 `>=`，等于预算的菜品保留** |
| F2 | 距离 | `if maximum is not None and distance > maximum: continue` | `max_distance_m` 非空且 `restaurant["distance_m"] > max_distance_m` → 返回 `False` |
| F3 | 营业 | `if p.get("only_open") and restaurant["is_open"] != "TRUE": continue` | `only_open` 为 `True` 且 `restaurant["is_open"] != "TRUE"` → 返回 `False` |
| F4 | 忌口 | `if any(restriction_status(food, term) != "TRUE" for term in avoid): continue` | `avoid` 中任一 `restriction_status(food, term) != "TRUE"` → 返回 `False` |
| F5 | 时段 | `if p.get("meal_period") and p["meal_period"] not in restaurant["meal_periods"]: continue` | `meal_period` 非空且不在 `restaurant["meal_periods"]` 中 → 返回 `False` |
| F6 | 评分 | `if p.get("min_rating") is not None and rating < p["min_rating"]: continue` | `min_rating` 非空且 `restaurant["rating"] < min_rating` → 返回 `False` |
| F7 | 口味命中 | `matched = sorted(set(tastes) & set(food["taste_tags"])); if tastes and not matched: continue` | `tastes` 非空且与 `food["taste_tags"]` 交集为空 → 返回 `False` |

#### 2.3.2 四维评分公式（基线 L65-71）

| 维度 | 基线代码 | `score()` 必须复现的公式 |
|------|---------|------------------------|
| T（口味） | `Decimal(len(matched)) / Decimal(len(tastes)) * 100 if tastes else Decimal(50)` | 有口味：`命中数 / 口味总数 × 100`；无口味：`Decimal(50)` |
| P（价格） | `(1 - Decimal(str(price)) / Decimal(str(budget))) * 100 if budget is not None else Decimal(50)` | 有预算：`(1 - price / budget) × 100`；无预算：`Decimal(50)` |
| D（距离） | `(Decimal(100) if maximum == 0 else (1 - Decimal(distance) / Decimal(str(maximum))) * 100) if maximum is not None else Decimal(50)` | 有距离上限且为 0：`Decimal(100)`；有距离上限且 >0：`(1 - distance / max) × 100`；无距离上限：`Decimal(50)` |
| R（评分） | `Decimal(str(rating)) / 5 * 100` | `restaurant["rating"] / 5 × 100`（始终计算） |

- **MUST**：所有计算使用 `Decimal` 类型，`str()` 转换后再构造 `Decimal`（与基线一致，避免浮点精度问题）。
- **MUST**：综合分 `score = sum(dimensions[key] * weight for key, weight in weights.items())`，使用 `Decimal` 精确计算。
- **MUST**：输出时 `score` 转为 `float`，`dimensions` 各值转为 `float`（基线 L81-82）。

#### 2.3.3 默认权重（基线 L8）

```
WEIGHTS = {"T": Decimal("0.35"), "P": Decimal("0.25"), "D": Decimal("0.20"), "R": Decimal("0.20")}
```

- **MUST**：`DefaultStrategy.weights()` 返回的默认权重 MUST 为 `T=0.35, P=0.25, D=0.20, R=0.20`。
- **MUST**：默认权重从 `config.recommendation.DEFAULT_WEIGHTS` 读取，MUST NOT 在策略类中硬编码。

#### 2.3.4 推荐理由生成依据（基线 L72-80）

| 序号 | 条件 | 基线代码 | `reasons()` 必须复现的内容 |
|------|------|---------|------------------------|
| R1 | 始终 | `f"菜品价格为 {price:g} 元" + (f"，不超过你的 {budget:g} 元预算。" if budget is not None else "。")` | 价格理由，有预算时附预算说明 |
| R2 | 始终 | `f"所属场所模拟距离为 {distance} 米" + (f"，符合 {maximum:g} 米上限。" if maximum is not None else "。")` | 距离理由，有距离上限时附上限说明 |
| R3 | 始终 | `f"所属场所模拟评分为 {rating:g} 分（满分 5 分）。"` | 评分理由 |
| R4 | `if tastes` | `"口味匹配标签：" + "、".join(matched) + "。"` | 口味匹配理由，仅在有口味偏好时追加 |
| R5 | `if is_open != "UNKNOWN"` | `"所属场所在记录的模拟时刻标记为" + ("营业中。" if is_open == "TRUE" else "未营业。")` | 营业理由，UNKNOWN 时不生成 |
| R6 | `if avoid` | `"模拟配方声明符合严格排除条件：" + "、".join(avoid) + "；不代表现实过敏安全保证。"` | 忌口理由，仅在有忌口时追加 |

- **MUST**：理由顺序 MUST 为 R1→R2→R3→R4→R5→R6（条件满足时依次追加）。
- **MUST**：每条理由 MUST 引用 `food` 或 `restaurant` 的真实字段值（`price`、`distance_m`、`rating`、`taste_tags`、`is_open`、`avoid`）。

#### 2.3.5 排序与 Top K 截取（基线 L83-84）

- **排序**：`scored.sort(key=lambda entry: (-entry[0], entry[1]))` — 按 `(-score, dish_id)` 复合键排序，score 降序，同分时 id 升序。
- **截取**：`items = [entry[2] for entry in scored[:p.get("top_k", 5)]]` — 取前 `top_k` 条，默认 5。
- **MUST**：排序 MUST 在 `Decimal` 精度下进行（未舍入总分参与排序），输出时才转 `float`。

#### 2.3.6 无结果及消息处理（基线 L85-90）

| 条件 | 基线消息 | `Context` 必须复现的消息 |
|------|---------|------------------------|
| 空结果 + 有口味 | `"没有菜品同时满足所选口味及其他硬约束。请检查口味、预算、距离、时段、最低评分和严格忌口；系统未自动放宽条件。"` | 逐字一致 |
| 空结果 + 无口味 | `"没有菜品满足全部硬约束。请检查预算、距离、时段、最低评分和严格忌口；系统未自动放宽条件。"` | 逐字一致 |
| 不足 top_k | `f"仅有 {len(items)} 道菜品满足全部硬约束，已返回实际数量，未自动放宽条件。"` | 逐字一致 |
| 正常 | `"已按综合评分排序。"` | 逐字一致 |

#### 2.3.7 数据校验与去重（基线 L41-48）

- **校验**：每条 `food` 调用 `validate_record(food, "dish")` 和 `validate_record(restaurant, "restaurant")`。
- **关联一致性**：`food["restaurant_id"] != restaurant["id"]` → 抛 `DataValidationError`。
- **去重**：按 `food["id"]` 去重，已见过的 id 跳过（`continue`），保留首次出现。
- **MUST**：以上逻辑由 `RecommendationContext.execute()` 保留，不委托给策略。

#### 2.3.8 返回值结构（基线 L81-82, 91）

```python
# 每条 item
{"dish": food, "score": float(score),
 "dimensions": {key: float(value) for key, value in dimensions.items()},
 "reasons": reasons}

# 返回
{"items": items, "total_candidates": len(scored), "message": message}
```

- **MUST**：`total_candidates` 等于通过硬约束的去重后候选数（`len(scored)`），不是 `len(items)`。

### 2.4 Concrete Strategy B — DistancePriorityStrategy（新增）

```
文件：backend/recommendation/distance_priority_strategy.py

class DistancePriorityStrategy(RecommendationStrategy):
    """距离优先推荐策略。"""
```

**完整权重配置**：

| 维度 | 权重 | 说明 |
|------|------|------|
| T（口味） | `Decimal("0.20")` | 降低口味权重 |
| P（价格） | `Decimal("0.20")` | 降低价格权重 |
| D（距离） | `Decimal("0.40")` | **距离权重提升至 0.40** |
| R（评分） | `Decimal("0.20")` | 保持评分权重 |
| **总和** | **1.00** | ✅ 合法 |

**约束（Rev B 明确）**：

- **MUST**：所有权重均为合法数值（0 ≤ w ≤ 1 的 Decimal）。
- **MUST**：四维权重总和 MUST 为 `Decimal("1.00")`。
- **MUST**：距离权重 MUST 为 `Decimal("0.40")`。
- **MUST NOT**：`DistancePriorityStrategy` MUST NOT 修改 `DefaultStrategy` 的默认权重。
- **MUST**：`DistancePriorityStrategy.filter()` MUST 使用与 `DefaultStrategy.filter()` **完全相同的硬约束规则**（复用 `filters.py` 函数），不得因排序策略不同而改变预算、距离硬限制、忌口及营业状态的过滤语义。
- **MUST**：`DistancePriorityStrategy.score()` MUST 使用与 `DefaultStrategy.score()` **完全相同的四维计算公式**（复用 `scoring.py` 函数），仅权重不同。
- **MUST**：`DistancePriorityStrategy.reasons()` 在 `DefaultStrategy.reasons()` 基础上追加一条距离优先说明，不修改已有理由顺序。

#### 2.4.1 距离优先理由语义与数据约束（Rev C 冻结 — Q2）

> 不冻结整句文案，但冻结理由语义和数据约束。实现时文案可调整，以下约束不可违反。

- **SHALL**：追加的理由 SHALL 能够体现距离是该策略的优先排序依据。
- **MUST**：追加的理由 MUST 只使用真实候选数据中的距离信息（`food["restaurant"]["distance_m"]`）。
- **MUST NOT**：追加的理由 MUST NOT 声称该菜品或餐厅一定比其他候选更近，除非当前候选与其他候选的比较结果确实支持该结论。
- **MUST NOT**：追加的理由 MUST NOT 编造距离、用户偏好或营业信息。
- **MUST**：在自动化测试中 MUST 验证理由与策略及实际数据一致（见 AC30）。

**理由语义示例（非冻结文案）**：

```
"本策略以距离为主要排序依据，当前菜品所属场所模拟距离为 {distance_m} 米。"
```

> 此示例仅为语义参考，实现时可用不同措辞，但须满足上述 5 条约束。

**新增策略示例说明**：

`DistancePriorityStrategy` 展示 Strategy 模式的扩展能力：
- **无须修改** `DefaultStrategy` 或 `RecommendationContext` 任何代码
- 仅需新建一个类，实现 4 个接口方法
- 复用 `filters.py` 和 `scoring.py` 中的公共函数，仅覆盖 `weights()` 和增强 `reasons()`
- 策略选择通过 `RecommendationService` 注入，不硬编码

---

## 3. 配置优化

### 3.1 配置模块

```
文件：backend/config/recommendation.py

DEFAULT_WEIGHTS = {
    "T": Decimal("0.35"),  # 口味匹配
    "P": Decimal("0.25"),  # 价格适配
    "D": Decimal("0.20"),  # 距离适配
    "R": Decimal("0.20"),  # 场所评分
}

def get_weights() -> dict[str, Decimal]:
    """读取并校验推荐权重配置。"""
```

### 3.2 配置位置与默认值（Rev B 明确）

| 项 | 值 |
|----|----|
| 配置文件位置 | `backend/config/recommendation.py` |
| 默认权重 | `T=0.35, P=0.25, D=0.20, R=0.20` |
| 环境变量名 | `CAMPUSBITE_WEIGHT_T` / `_P` / `_D` / `_R` |
| 环境变量可选 | 是，未设置时使用 `DEFAULT_WEIGHTS` |

### 3.3 合法范围与校验时机（Rev B 修订）

| 项 | 规则 |
|----|------|
| 单个权重合法范围 | `0 ≤ w ≤ 1`，须为有效 `Decimal` |
| 权重总和约束 | `T + P + D + R == Decimal("1.00")` |
| 校验时机 | 应用启动时（`get_weights()` 首次调用时），**不在每次请求中重复校验** |
| 权重缺失 | 环境变量未设置 → 使用 `DEFAULT_WEIGHTS` 对应项（合法） |
| 权重类型非法 | 环境变量无法解析为 `Decimal` → **抛出 `ConfigError`，应用启动失败** |
| 权重存在负值 | 任一权重 < 0 → **抛出 `ConfigError`，应用启动失败** |
| 权重总和不符合 | 总和 ≠ 1.0 → **抛出 `ConfigError`，应用启动失败** |

> **Rev B 关键修订**：权重配置非法时**不再静默回退默认值**，而是抛出 `ConfigError` 导致应用启动失败。理由：静默回退会生成用户无法解释的推荐结果，违反数据透明性原则（`baseline.md` 第 6 节 B3）。

### 3.3.1 配置错误处理决策（Rev C 冻结 — Q1）

- **MUST**：非法评分配置 MUST 导致 `ConfigError` 并阻止应用以非法配置启动。
- **MUST NOT**：系统 MUST NOT 提供 `--strict-config` 或 `--lenient-config` 启动选项。
- **MUST NOT**：系统 MUST NOT 允许非法配置静默回退到默认值。

**独立测试验证要求**：

| 编号 | 测试场景 | 期望结果 |
|------|---------|---------|
| CT1 | 合法配置正常加载 | `get_weights()` 返回 `DEFAULT_WEIGHTS` 或环境变量指定的合法权重 |
| CT2 | 权重缺失（环境变量未设置） | 使用 `DEFAULT_WEIGHTS`（合法行为，非异常） |
| CT3 | 权重类型非法（如 `CAMPUSBITE_WEIGHT_T=abc`） | 抛 `ConfigError`，应用启动失败 |
| CT4 | 权重存在负值（如 `CAMPUSBITE_WEIGHT_T=-0.1`） | 抛 `ConfigError`，应用启动失败 |
| CT5 | 权重总和不符合约定（如四维和 = 0.9） | 抛 `ConfigError`，应用启动失败 |
| CT6 | 错误信息定位配置问题 | `ConfigError` 消息 MUST 包含具体非法字段名和非法值 |

### 3.4 ConfigError 定义

```
class ConfigError(ValueError):
    """推荐配置非法，应用无法安全启动。"""
```

- **MUST**：`ConfigError` 消息 MUST 包含具体非法字段名和非法值。
- **MUST**：`ConfigError` 在应用启动时抛出，MUST NOT 在请求处理时抛出。

---

## 4. 输入输出契约

### 4.1 输入（不变）

```
POST /api/recommend
Content-Type: application/json

{
  "budget": number | null,          // 菜品预算上限
  "max_distance_m": number | null,  // 场所距离上限
  "min_rating": number | null,      // 最低场所评分 0-5
  "tastes": string[],               // 口味标签
  "avoid": string[],                // 严格忌口
  "meal_period": string | null,     // 用餐时段
  "only_open": boolean,             // 仅看营业中
  "top_k": integer                  // 3 | 4 | 5
}
```

### 4.2 输出（不变）

```
200 OK
{
  "items": [
    {
      "dish": { ... },              // 菜品完整记录（含嵌套 restaurant）
      "score": number,              // 综合分 0-100
      "dimensions": {               // 各维度分 0-100
        "T": number, "P": number, "D": number, "R": number
      },
      "reasons": string[]           // 推荐理由列表
    }
  ],
  "total_candidates": integer,      // 通过硬约束的候选总数
  "message": string,                // 结果说明
  "metadata": { ... }               // 数据来源信息
}
```

### 4.3 策略选择输入（新增，内部）

```
RecommendationService(strategy_name: str = "default")
  - "default"           → DefaultStrategy
  - "distance_priority" → DistancePriorityStrategy
```

> 策略选择为内部接口，不暴露到 HTTP API。当前 `app.py` 使用默认策略。

### 4.4 显式策略注册表（Rev C 冻结 — Q3）

```
文件：backend/service/recommendation_service.py

STRATEGY_REGISTRY: dict[str, RecommendationStrategy] = {
    "default": DefaultStrategy,
    "distance_priority": DistancePriorityStrategy,
}
```

**注册表约束**：

- **SHALL**：系统 SHALL 采用显式策略注册表，使用策略名称到策略类/实例的映射。
- **MUST**：默认策略和距离优先策略 MUST 均可通过注册表选择。
- **MUST NOT**：系统 MUST NOT 引入装饰器自动注册、动态插件发现或 Python 入口点机制。
- **MUST**：新增策略时，MUST 通过实现策略接口并添加注册表映射完成扩展，MUST NOT 修改 `RecommendationContext` 的核心编排逻辑。
- **MUST**：`RecommendationContext` MUST NOT 通过 `if/else` 编写具体策略的评分逻辑，所有策略差异通过多态方法调用体现。
- **MUST**：未知策略名称 MUST 按照现有规格抛出 `ValueError`，MUST NOT 静默切换到默认策略。

---

## 5. SHALL / MUST 约束（EARS 格式）

### 5.1 接口约束

- **SHALL**：系统 SHALL 提供 `RecommendationStrategy` 抽象基类，定义 `filter`、`score`、`reasons`、`weights` 四个抽象方法。
- **SHALL**：系统 SHALL 提供 `RecommendationContext` 类，接收一个 `RecommendationStrategy` 实例并编排推荐流程。
- **SHALL**：系统 SHALL 提供 `DefaultStrategy` 具体策略，迁移现有四维加权评分逻辑。
- **SHALL**：系统 SHALL 提供 `DistancePriorityStrategy` 具体策略，作为 Strategy 模式扩展验证。
- **MUST**：每个具体策略 MUST 实现全部四个抽象方法。
- **MUST**：`RecommendationContext.execute()` 的返回值结构 MUST 与重构前 `recommend()` 完全一致。
- **MUST**：`RecommendationContext` MUST 仅负责流程编排，MUST NOT 包含具体评分算法实现。
- **MUST NOT**：`RecommendationContext` 中 MUST NOT 出现针对具体策略类型的 `if/else` 或 `isinstance` 分支。
- **MUST NOT**：策略方法 MUST NOT 直接访问数据库或 Repository，仅基于传入参数计算。
- **MUST NOT**：`RecommendationContext` MUST NOT 重复执行 Repository 已完成的过滤规则。

### 5.2 行为不变约束

- **MUST**：WHEN 使用 `DefaultStrategy` 且权重为默认值时，THE 系统 MUST 对相同输入返回与重构前完全相同的 `items`、`total_candidates`、`message`（逐字段一致）。
- **MUST**：WHEN 硬约束过滤排除某菜品时，THE 策略 `filter()` MUST 返回 `False`，且该菜品 MUST NOT 出现在 `items` 中。
- **MUST**：WHEN 所有维度分值和权重确定后，THE 综合分 MUST 等于 `Σ(dimension[i] × weight[i])`，使用 `Decimal` 精确计算。
- **MUST**：THE 排序 MUST 按 `(-score, dish_id)` 复合键稳定排序，截取前 `top_k` 条。
- **MUST**：WHEN 候选数为零时，THE `message` MUST 逐字匹配基线 L85-86 对应文案且 `items` MUST 为空列表。
- **MUST**：WHEN 候选数小于 `top_k` 时，THE `message` MUST 逐字匹配基线 L88 文案且 `items` 长度 MUST 等于候选数。
- **MUST**：THE `total_candidates` MUST 等于通过硬约束的去重后候选总数，MUST NOT 等于 `len(items)`（当 `len(items) < top_k` 时）。
- **MUST**：THE 去重 MUST 按 `food["id"]` 去重，保留首次出现，与基线 L46-48 一致。

### 5.3 配置约束（Rev B 修订）

- **SHALL**：系统 SHALL 从 `backend.config.recommendation` 读取推荐权重。
- **MUST**：WHEN 环境变量未设置时，THE 系统 MUST 使用 `DEFAULT_WEIGHTS`（T=0.35, P=0.25, D=0.20, R=0.20）。
- **MUST**：WHEN 环境变量权重类型非法（无法解析为 Decimal）时，THE 系统 MUST 抛出 `ConfigError`，MUST NOT 静默回退。
- **MUST**：WHEN 任一权重为负值时，THE 系统 MUST 抛出 `ConfigError`，MUST NOT 静默回退。
- **MUST**：WHEN 权重总和不为 1.0 时，THE 系统 MUST 抛出 `ConfigError`，MUST NOT 静默回退。
- **MUST**：WHERE `DistancePriorityStrategy` 被使用时，THE 权重 MUST 为 T=0.20, P=0.20, D=0.40, R=0.20。
- **MUST NOT**：`DistancePriorityStrategy` MUST NOT 修改 `DefaultStrategy` 的默认权重。

### 5.4 策略选择约束（Rev B 新增，Rev C 冻结）

- **MUST**：WHEN 传入未知 `strategy_name` 时，THE `RecommendationService` MUST 抛出 `ValueError`，MUST NOT 悄悄切换为 `DefaultStrategy` 或其他策略。
- **MUST**：WHEN `strategy_name` 为 `None` 或未提供时，THE `RecommendationService` MUST 使用 `DefaultStrategy`（合法默认值，非悄悄切换）。
- **SHALL**：系统 SHALL 维护显式策略注册表（`STRATEGY_REGISTRY`），映射策略名称到策略类/实例。
- **MUST**：默认策略和距离优先策略 MUST 均在注册表中注册。
- **MUST NOT**：系统 MUST NOT 引入装饰器自动注册、动态插件发现或 Python 入口点机制。
- **MUST**：WHERE 新增策略时，THE 扩展 MUST 通过实现策略接口并添加注册表映射完成，MUST NOT 修改 `RecommendationContext` 核心编排逻辑。

### 5.5 兼容性约束

- **MUST**：`from backend.recommendation import recommend` MUST 保持有效。
- **MUST**：`from backend.recommendation import validate_preferences` MUST 保持有效。
- **MUST**：`from backend.recommendation import PreferenceError` MUST 保持有效。
- **MUST**：`recommend(foods, prefs)` 函数签名 MUST NOT 改变。
- **MUST**：`app.py` MUST NOT 被修改（通过包 `__init__.py` re-export 保持兼容）。

### 5.6 禁止约束

- **MUST NOT**：THE 重构 MUST NOT 修改 `backend/data/` 目录下任何文件。
- **MUST NOT**：THE 重构 MUST NOT 修改 `frontend/` 目录下任何文件。
- **MUST NOT**：THE 重构 MUST NOT 修改 `backend/app.py`。
- **MUST NOT**：THE 重构 MUST NOT 改变 `schema.sql` 或 `seed.py`。
- **MUST NOT**：THE 重构 MUST NOT 引入新的第三方依赖。

### 5.7 策略间硬约束共享约束（Rev B 新增）

- **MUST**：`DefaultStrategy.filter()` 与 `DistancePriorityStrategy.filter()` MUST 调用相同的 `filters.py` 函数，产生完全相同的过滤结果。
- **MUST NOT**：策略间的差异 MUST NOT 体现在硬约束过滤语义上，仅体现在权重和评分排序上。

### 5.8 距离优先理由语义约束（Rev C 冻结 — Q2）

- **SHALL**：`DistancePriorityStrategy.reasons()` 追加的理由 SHALL 体现距离是该策略的优先排序依据。
- **MUST**：追加的理由 MUST 只使用 `food["restaurant"]["distance_m"]` 真实字段值。
- **MUST NOT**：追加的理由 MUST NOT 声称该菜品或餐厅一定比其他候选更近，除非比较结果确实支持该结论。
- **MUST NOT**：追加的理由 MUST NOT 编造距离、用户偏好或营业信息。
- **MUST**：在自动化测试中 MUST 验证理由与策略及实际数据一致。

---

## 6. 异常场景（Rev B 修订）

| 场景 | 触发条件 | 系统行为 | 约束 |
|------|---------|---------|------|
| 非法偏好 | budget ≤ 0 / tastes 含未知标签 / top_k ∉ {3,4,5} 等 | `validate_preferences` 抛 `PreferenceError` → API 返回 422 | MUST 保持与重构前一致 |
| 数据校验失败 | 菜品记录缺字段 / 关联不一致 | `validate_record` 抛 `DataValidationError` → API 返回 503 | MUST 保持与重构前一致 |
| 数据库不可用 | SQLite 文件缺失 / 损坏 | `FileNotFoundError` / `sqlite3.Error` → API 返回 503 | MUST 保持与重构前一致 |
| 空候选集 | 所有菜品被硬约束排除 | `items=[]`, `message` 逐字匹配基线 L85-86 | MUST 保持与重构前一致 |
| 候选不足 | 通过约束的菜品 < top_k | 返回实际数量, `message` 逐字匹配基线 L88 | MUST 保持与重构前一致 |
| 权重类型非法 | 环境变量无法解析为 Decimal | **抛出 `ConfigError`，应用启动失败** | MUST NOT 静默回退；MUST NOT 导致请求返回不可解释结果 |
| 权重存在负值 | 任一权重 < 0 | **抛出 `ConfigError`，应用启动失败** | MUST NOT 静默回退 |
| 权重总和不符 | T+P+D+R ≠ 1.0 | **抛出 `ConfigError`，应用启动失败** | MUST NOT 静默回退 |
| 策略名称不存在 | 传入未知 strategy_name | **抛出 `ValueError`** → 由异常处理器转为 503 | MUST NOT 悄悄切换为其他策略 |

> **Rev B 关键修订**：
> - 权重配置非法：从"回退默认值"改为"抛出 `ConfigError` 启动失败"。理由：静默回退生成不可解释的推荐结果。
> - 策略不存在：从"回退 `DefaultStrategy`"改为"抛出 `ValueError`"。理由：悄悄切换违反显式错误原则。

---

## 7. 可选：Decorator 模式（推荐理由增强）

> **状态**：**可选扩展，不作为本次核心验收条件（AC1–AC17）的必要条件。**
>
> Strategy 是本次必须落地的设计模式。Decorator 仅在确认有实际业务价值时引入，不为满足模式数量而引入没有实际业务价值的抽象。

### 7.1 引入前提

引入 `NutritionHintDecorator` 须同时满足以下条件：

1. T3（`DistancePriorityStrategy`）已完成并通过测试
2. 现有数据确实支持可靠的营养提示（`seed.py` 中 `dietary_tags` 含 `"素食"` 标签，该标签由数据验证保证）
3. 确认追加理由对用户有实际价值，而非仅为展示模式

### 7.2 设计（若引入）

```
文件：backend/recommendation/decorators.py（若引入）

class ReasonDecorator:
    """推荐理由装饰器基类。包装策略的 reasons() 方法。"""

    def __init__(self, strategy: RecommendationStrategy):
        self._strategy = strategy

    def filter(self, food, prefs):
        return self._strategy.filter(food, prefs)

    def score(self, food, prefs):
        return self._strategy.score(food, prefs)

    def weights(self):
        return self._strategy.weights()

    def reasons(self, food, prefs, dimensions):
        base = self._strategy.reasons(food, prefs, dimensions)
        return self._enhance(base, food, prefs, dimensions)

    def _enhance(self, base_reasons, food, prefs, dimensions) -> list[str]:
        return base_reasons  # 子类覆盖


class NutritionHintDecorator(ReasonDecorator):
    """追加素食标注提示。

    实际代码位置：backend/recommendation/decorators.py
    使用位置：RecommendationService 中包装策略
    数据依据：food["dietary_tags"] 中的 "素食" 标签（由 validation.py 保证合法性）
    """

    def _enhance(self, base_reasons, food, prefs, dimensions):
        if "素食" in food.get("dietary_tags", []):
            return base_reasons + ["本品标注为素食选项（模拟标签，允许蛋奶）。"]
        return base_reasons
```

### 7.3 引入约束

- 引入时须在 `decorators.py` 中实现实际代码，MUST NOT 只写文档
- 须在 `test_strategy.py` 中补充对应测试
- 不改变 `reasons` 列表已有内容的顺序，仅追加
- **MUST NOT**：Decorator MUST NOT 修改评分或过滤逻辑，仅增强 `reasons()`

---

## 8. 验收条件

### 8.1 功能验收

| 编号 | 验收项 | 验证方式 |
|------|--------|---------|
| AC1 | 现有 55 个后端测试全部通过 | `python -m unittest discover -s backend/tests -v` → exit 0 |
| AC2 | 默认策略输出与重构前逐字段一致 | `test_recommendation.py` 19 个方法全部通过（无修改），覆盖公式/权重/过滤/排序/理由/边界 |
| AC3 | `RecommendationStrategy` 接口可被独立实现 | `DistancePriorityStrategy` 通过全部测试 |
| AC4 | 权重可从配置读取 | 环境变量设置合法值后策略使用自定义权重 |
| AC5 | 权重类型非法时启动失败 | 设置 `CAMPUSBITE_WEIGHT_T=abc` → `get_weights()` 抛 `ConfigError` |
| AC6 | 权重总和不符时启动失败 | 设置权重和 ≠ 1.0 → `get_weights()` 抛 `ConfigError` |
| AC7 | 导入兼容性 | `from backend.recommendation import recommend` 有效 |
| AC8 | `app.py` 未被修改 | `git diff backend/app.py` 无变化 |

### 8.2 行为保持验收（Rev B 新增 — 可比较、可验证）

| 编号 | 验收项 | 验证方式 |
|------|--------|---------|
| AC9 | 硬约束过滤语义不变 | 对相同 `foods` + `prefs`，`DefaultStrategy.filter()` 返回 `False` 的菜品集合 == 基线 `recommend()` 中被 `continue` 排除的菜品集合 |
| AC10 | 四维评分公式不变 | 对相同 `food` + `prefs`，`DefaultStrategy.score()` 返回的各维度 `Decimal` 值 == 基线 L65-69 计算值 |
| AC11 | 推荐理由内容不变 | 对相同 `food` + `prefs`，`DefaultStrategy.reasons()` 返回列表 == 基线 L72-80 生成的列表（逐条字符串一致） |
| AC12 | 排序结果不变 | 对相同候选集，`RecommendationContext` 排序后的 `items` 顺序 == 基线 `(-score, id)` 排序结果 |
| AC13 | 消息文案逐字一致 | 空结果/不足/正常三种场景的 `message` 字符串 == 基线 L85-90 对应文案 |
| AC14 | `total_candidates` 语义不变 | `total_candidates` == 通过硬约束的去重后候选数（`len(scored)`），非 `len(items)` |

### 8.3 结构验收

| 编号 | 验收项 |
|------|--------|
| AC15 | `backend/recommendation/` 为 Python 包（含 `__init__.py`） |
| AC16 | `backend/config/recommendation.py` 存在且定义 `DEFAULT_WEIGHTS` + `ConfigError` |
| AC17 | `backend/service/recommendation_service.py` 存在且定义 `RecommendationService` |
| AC18 | `DefaultStrategy` 不包含内联过滤/评分/理由逻辑（委托 `filters.py`/`scoring.py`/`reasons.py`） |
| AC19 | `recommend()` 函数体不超过 10 行（薄封装委托） |
| AC20 | `RecommendationContext` 中无 `if/else` 或 `isinstance` 针对具体策略类型的分支 |

### 8.4 扩展性验收

| 编号 | 验收项 |
|------|--------|
| AC21 | 新增策略无须修改 `DefaultStrategy` 或 `RecommendationContext` |
| AC22 | 新增策略无须修改 `app.py` |
| AC23 | 新增策略仅须创建一个类文件 + 注册到 `RecommendationService` |

### 8.5 策略间一致性验收（Rev B 新增）

| 编号 | 验收项 |
|------|--------|
| AC24 | `DistancePriorityStrategy.filter()` 与 `DefaultStrategy.filter()` 对相同输入返回相同结果 |
| AC25 | `DistancePriorityStrategy` 权重为 T=0.20, P=0.20, D=0.40, R=0.20，总和 = 1.0 |
| AC26 | 未知 `strategy_name` 抛 `ValueError`，不悄悄切换 |

### 8.6 配置错误处理验收（Rev C 新增 — Q1）

| 编号 | 验收项 | 验证方式 |
|------|--------|---------|
| AC27 | 合法配置正常加载 | 环境变量设置合法权重 → `get_weights()` 返回对应值 |
| AC28 | 非法配置（类型/负值/总和不符）启动失败 | 设置非法环境变量 → `get_weights()` 抛 `ConfigError` |
| AC29 | 错误信息定位配置问题 | `ConfigError` 消息包含具体非法字段名和非法值 |

### 8.7 距离优先理由验收（Rev C 新增 — Q2）

| 编号 | 验收项 | 验证方式 |
|------|--------|---------|
| AC30 | 理由与策略及实际数据一致 | 自动化测试验证追加理由引用 `distance_m` 真实值，不编造数据 |
| AC31 | 理由体现距离优先语义 | 追加理由包含距离排序依据说明 |
| AC32 | 理由不声称绝对更近 | 追加理由不包含"最近""比其他更近"等绝对比较措辞（除非比较结果支持） |

### 8.8 注册表验收（Rev C 新增 — Q3）

| 编号 | 验收项 | 验证方式 |
|------|--------|---------|
| AC33 | 显式注册表存在 | `STRATEGY_REGISTRY` 包含 `"default"` 和 `"distance_priority"` 映射 |
| AC34 | 注册表无动态发现 | 不使用装饰器自动注册、插件发现或入口点机制 |
| AC35 | 新增策略不修改 Context | 新增策略仅创建类文件 + 注册表添加映射，`RecommendationContext` 代码无变化 |

> **验收条件与基线不变行为的一致性检查**：AC9-AC14 逐条对照 `baseline.md` 第 6 节 B1-B10，无冲突。AC2 保证现有 19 个推荐测试通过，覆盖 B1-B9 全部行为契约。AC27-AC35 为 Rev C 新增，不与基线行为冲突（均为新增约束，不改变现有行为）。

---

## 9. 模块依赖关系（重构后）

```
app.py
  └──→ recommendation/__init__.py (re-export)
         └──→ service/recommendation_service.py
                ├──→ recommendation/strategy.py (Context + Interface)
                ├──→ recommendation/default_strategy.py
                │      ├──→ recommendation/filters.py
                │      ├──→ recommendation/scoring.py
                │      ├──→ recommendation/reasons.py
                │      └──→ config/recommendation.py
                └──→ recommendation/distance_priority_strategy.py
                       ├──→ recommendation/filters.py
                       ├──→ recommendation/scoring.py
                       ├──→ recommendation/reasons.py
                       └──→ config/recommendation.py

recommendation/filters.py ──→ data/restrictions.py (restriction_status)
recommendation/scoring.py   (无外部依赖，纯计算)
recommendation/reasons.py   (无外部依赖，纯字符串)
config/recommendation.py    (无外部依赖，纯配置)
```

> **关键**：`scoring.py` 和 `reasons.py` 无外部依赖，可完全独立单元测试。`filters.py` 仅依赖 `data/restrictions.py`（已有模块）。`RecommendationService` 调用 `repo.dishes()` **无参数**获取全量数据，过滤由策略统一负责，不与 Repository 过滤重复。

---

## 10. 任务拆解（待 spec 冻结后填充至 tasks.md）

| 任务 | 内容 | 产出文件 | 依赖 |
|------|------|---------|------|
| T1 | 抽取 `RecommendationStrategy` 接口 + `RecommendationContext` | `strategy.py` | — |
| T2 | 迁移现有逻辑为 `DefaultStrategy` + 抽取 `filters`/`scoring`/`reasons` | `default_strategy.py`, `filters.py`, `scoring.py`, `reasons.py` | T1 |
| T2.1 | 权重配置抽离 + `ConfigError` + 启动时校验 | `config/recommendation.py` | T2 |
| T2.2 | `RecommendationService` 编排 + 策略注册 | `service/recommendation_service.py` | T1, T2 |
| T2.3 | `recommendation/__init__.py` re-export + `recommend()` 薄封装 | `__init__.py` | T2.2 |
| T3 | 新增 `DistancePriorityStrategy` | `distance_priority_strategy.py` | T1, T2 |
| T4 | 补充测试 | `tests/test_strategy.py` | T1-T3 |
| T5 | 全量回归验证 | 55 + 新增测试通过 | T1-T4 |
