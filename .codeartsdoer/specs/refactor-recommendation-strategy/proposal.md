# 变更提案：推荐策略 Strategy 模式重构

> 提案编号：002
> 特性标识：`refactor-recommendation-strategy`
> 提案日期：2026-10-15
> 最后修订：2026-10-20（Rev C — 冻结 Q1/Q2/Q3 人工决策）
> 状态：待人工审查（Pending Review）
> 类型：结构重构（行为不变）
> 前置提案：`001-initial-restructure.md`
> 基线依据：`baseline.md` 第 4.1 节

---

## 修订记录

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| A | 2026-10-15 | 初始版本 |
| B | 2026-10-20 | 配置非法处理从"静默回退"改为"启动失败抛 ConfigError"；策略不存在从"悄悄切换"改为"抛 ValueError"；补充行为保持精确清单；明确接口职责约束；Decorator 标注为非核心验收 |
| C | 2026-10-20 | 冻结 Q1/Q2/Q3 人工决策：确认配置非法启动失败不回退不增加宽松选项；冻结距离优先理由语义与数据约束；明确显式策略注册表机制及扩展约束 |

---

## 1. 变更摘要

将 `backend/recommendation.py` 中 `recommend()` 函数承担的六类耦合职责（数据校验、硬约束过滤、评分计算、推荐理由生成、排序截取、消息生成）拆分为 Strategy 模式的可插拔组件，并将评分权重从代码常量抽离为配置。重构为纯结构性变更，**不改变 API 输入输出协议、不改变前端页面流程、不改变数据库结构**。

## 2. 动机

`baseline.md` 第 4.1–4.3 节确认以下问题：

1. **高耦合**：`recommend()` 单体函数 57 行，六类职责交织在一个 `for` 循环内
2. **策略不可扩展**：评分维度 T/P/D/R 和权重 `WEIGHTS` 硬编码在函数体/模块级常量中，新增维度或策略须修改函数内部
3. **难以测试**：过滤、评分、理由生成无法独立调用，测试只能通过 `recommend()` 整体验证

Strategy 模式将推荐算法封装为可独立替换的策略对象，通过统一接口与 Context 编排，使新增策略无须修改现有代码（开闭原则）。

## 3. 变更内容（Delta）

### 3.1 新增（Added）

| 路径 | 职责 |
|------|------|
| `backend/config/__init__.py` | 配置包初始化 |
| `backend/config/recommendation.py` | 推荐权重配置：`DEFAULT_WEIGHTS`、`get_weights()`、`ConfigError`、环境变量读取 + 启动时校验 |
| `backend/recommendation/__init__.py` | 包入口，re-export `recommend`、`validate_preferences`、`PreferenceError`（保持 `app.py` 导入不变） |
| `backend/recommendation/strategy.py` | `RecommendationStrategy` 抽象接口 + `RecommendationContext` 编排者 |
| `backend/recommendation/default_strategy.py` | `DefaultStrategy`：迁移现有四维加权评分逻辑 |
| `backend/recommendation/distance_priority_strategy.py` | `DistancePriorityStrategy`：新增策略示例，距离优先权重 |
| `backend/recommendation/filters.py` | 硬约束过滤函数集（从 `recommend()` 循环中抽取） |
| `backend/recommendation/scoring.py` | 评分维度计算函数集（T/P/D/R） |
| `backend/recommendation/reasons.py` | 推荐理由生成函数集 |
| `backend/service/__init__.py` | 服务包初始化 |
| `backend/service/recommendation_service.py` | `RecommendationService`：编排数据获取→策略推荐→结果组装 + 策略注册 |

### 3.2 修改（Modified）

| 路径 | 变更说明 |
|------|---------|
| `backend/recommendation.py` → `backend/recommendation/` | 文件转为包；`recommend()` 函数体改为委托 `RecommendationContext` + 策略，签名不变 |
| `backend/app.py` | **不修改**。`from .recommendation import recommend, validate_preferences, PreferenceError` 通过包 `__init__.py` re-export 保持不变 |
| `backend/tests/test_recommendation.py` | 现有 19 个测试方法保持不变；新增策略接口、默认策略、距离优先策略、配置注入的单元测试 |

### 3.3 删除（Removed）

| 路径 | 说明 |
|------|------|
| `backend/recommendation.py` 中的内联逻辑 | `recommend()` 函数内的硬约束过滤（L50-64）、评分计算（L65-71）、理由生成（L72-80）被抽取至独立模块，函数体不再包含这些逻辑 |
| 模块级常量 `WEIGHTS` | 从 `recommendation.py` 代码常量迁移至 `config/recommendation.py` 配置 |

> **注意**：`recommendation.py` 文件本身不删除，而是转换为 `recommendation/` 包。Python 导入路径 `backend.recommendation` 保持不变。

### 3.4 Rev B 修订内容

| 修订项 | Rev A（原方案） | Rev B（修订后） | 修订原因 |
|--------|----------------|----------------|---------|
| 权重配置非法处理 | 静默回退 `DEFAULT_WEIGHTS`，记录警告 | 抛 `ConfigError`，应用启动失败 | 静默回退生成用户无法解释的推荐结果，违反数据透明性 |
| 策略名称不存在 | 回退 `DefaultStrategy`，记录警告 | 抛 `ValueError` → 503 | 悄悄切换违反显式错误原则 |
| 行为保持要求 | 概述性描述 | 精确清单对照基线代码行号（L50-90） | 人工审查要求不得仅凭设计文档推测原有行为 |
| 接口职责约束 | 未明确 | 明确 Context 不评分、不硬编码、不重复过滤 | 人工审查要求审查接口职责清晰度 |
| Decorator 验收地位 | 可选但未明确排除 | 明确不作为核心验收 AC1-AC26 必要条件 | 不为模式数量引入无业务价值抽象 |

### 3.5 Rev C 修订内容（冻结 Q1/Q2/Q3 人工决策）

| 决策项 | 决策内容 | 修订原因 |
|--------|---------|---------|
| Q1：配置错误处理 | 维持 Rev B 规格：非法配置抛 `ConfigError` 启动失败；不增加 `--strict-config`/`--lenient-config` 选项；不允许静默回退；增加独立测试验证（CT1-CT6） | 人工确认静默回退不可接受 |
| Q2：距离优先理由 | 不冻结整句文案，冻结理由语义和数据约束（5 条 SHALL/MUST）；增加验收 AC30-AC32 | 人工要求语义可验证但不限制实现措辞 |
| Q3：策略注册机制 | 采用显式策略注册表（`STRATEGY_REGISTRY`）；不引入动态插件发现/入口点；新增策略仅注册映射不改 Context；增加验收 AC33-AC35 | 人工要求显式可审计的注册方式 |

## 4. Strategy 模式角色映射

### 4.1 重构前

```
recommend(foods, p)
  ├── validate_preferences(p)          # 偏好验证
  ├── for food in foods:
  │     ├── validate_record(food)      # 数据校验
  │     ├── 7 × if ... continue        # 硬约束过滤（内联）
  │     ├── dimensions = {T, P, D, R}  # 评分计算（内联）
  │     ├── reasons = [...]            # 理由生成（内联）
  │     └── scored.append(...)         # 结果收集
  ├── scored.sort(...)                 # 排序
  └── items = scored[:top_k]           # 截取 + 消息
```

### 4.2 重构后

```
recommend(foods, p)                    # 薄封装，签名不变
  └── RecommendationService
        ├── validate_preferences(p)    # 偏好验证（不变）
        ├── RecommendationContext(strategy)
        │     ├── for food in foods:
        │     │     ├── validate_record(food)           # 数据校验（Context 保留）
        │     │     ├── strategy.filter(food, p) → bool  # 策略：硬约束
        │     │     ├── strategy.score(food, p)  → dims  # 策略：评分
        │     │     └── strategy.reasons(food, p) → list # 策略：理由
        │     ├── 去重 (by food id)                       # Context 保留
        │     ├── rank(scored, top_k)                     # 排序截取
        │     └── message(items, top_k)                   # 消息生成
        └── return {items, total_candidates, message}
```

### 4.3 角色对照

| Strategy 模式角色 | 本项目实现 | 位置 |
|------------------|-----------|------|
| **Strategy 接口** | `RecommendationStrategy`（ABC） | `recommendation/strategy.py` |
| **Context** | `RecommendationContext` | `recommendation/strategy.py` |
| **Concrete Strategy A** | `DefaultStrategy` | `recommendation/default_strategy.py` |
| **Concrete Strategy B**（新增） | `DistancePriorityStrategy` | `recommendation/distance_priority_strategy.py` |
| **配置** | `DEFAULT_WEIGHTS` + `get_weights()` + `ConfigError` | `config/recommendation.py` |
| **服务编排** | `RecommendationService` | `service/recommendation_service.py` |

## 5. 影响评估

| 维度 | 影响 |
|------|------|
| **API 协议** | 无影响。`POST /api/recommend` 请求/响应结构不变 |
| **前端** | 无影响。不修改任何前端文件 |
| **数据库** | 无影响。不修改 schema、种子数据、存储层 |
| **现有测试** | 55 个后端测试方法须全部保持通过（行为不变验证） |
| **导入兼容** | `from backend.recommendation import recommend` 保持有效（包 `__init__.py` re-export） |
| **运行时行为** | 默认策略下输出与重构前完全一致 |
| **配置错误处理** | Rev B 变更：权重非法时应用启动失败（而非静默回退） |

## 6. 实施顺序

| 步骤 | 任务 | 依赖 | 产出 |
|------|------|------|------|
| T1 | 抽取推荐策略接口 `RecommendationStrategy` + `RecommendationContext` | — | `strategy.py` |
| T2 | 迁移当前综合评分逻辑为 `DefaultStrategy` | T1 | `default_strategy.py` + `filters.py` + `scoring.py` + `reasons.py` |
| T2.1 | 抽离权重至 `config/recommendation.py` + `ConfigError` + 启动校验 | T2 | `config/recommendation.py` |
| T3 | 新增 `DistancePriorityStrategy` 作为扩展验证 | T1, T2 | `distance_priority_strategy.py` |
| T4 | 补充测试：策略接口、默认策略一致性、新策略、配置注入、配置非法、策略不存在 | T1-T3 | `test_strategy.py`（新增） |
| T5 | 全量回归验证 | T1-T4 | 55 + 新增测试全部通过 |

## 7. 验证方式

```bash
# 后端全量测试（现有 55 + 新增）
python -m unittest discover -s backend/tests -v

# 确认 API 行为不变
python -c "
from fastapi.testclient import TestClient
from backend.app import create_app
c = TestClient(create_app())
r = c.post('/api/recommend', json={'budget': 20, 'tastes': ['清淡'], 'top_k': 3})
print(r.status_code, len(r.json()['items']))
# 期望: 200, 3
"

# 确认配置非法时启动失败（Rev B）
CAMPUSBITE_WEIGHT_T=abc python -c "from backend.config.recommendation import get_weights; get_weights()"
# 期望: 抛出 ConfigError
```

## 8. 待人工审查事项

| 编号 | 事项 | 状态 |
|------|------|------|
| 1 | `DistancePriorityStrategy` 权重方案 T=0.20, P=0.20, D=0.40, R=0.20 | ✅ 已明确，见 spec.md 第 2.4 节 |
| 2 | Decorator 模式是否引入 | ✅ 已明确为可选，非核心验收，见 spec.md 第 7 节 |
| 3 | 配置来源：仅环境变量 | ✅ 已明确，见 spec.md 第 @3.2 节 |
| 4 | 权重非法处理方式 | ✅ Rev B 修订为启动失败，见 spec.md 第 3.3 节 |
| 5 | 策略不存在处理方式 | ✅ Rev B 修订为抛 ValueError，见 spec.md 第 5.4 节 |
| 6 | 行为保持精确清单 | ✅ 已对照基线代码逐条列出，见 spec.md 第 2.3 节 |
| 7 | 接口职责约束 | ✅ 已明确，见 spec.md 第 2.1-2.2 节 |
| 8 | Q1：配置错误处理 | ✅ Rev C 冻结：维持启动失败，不增加宽松选项，增加独立测试 CT1-CT6，见 spec.md 第 3.3.1 节 |
| 9 | Q2：距离优先理由 | ✅ Rev C 冻结：冻结语义和数据约束（5 条），不冻结文案，见 spec.md 第 2.4.1 节 + 第 5.8 节 |
| 10 | Q3：策略注册机制 | ✅ Rev C 冻结：显式注册表，不引入动态发现，见 spec.md 第 4.4 节 + 第 5.4 节 |

> **所有待审查事项已冻结。** Rev C 完成后，规格可进入冻结状态，等待人工最终确认后拆解 `tasks.md`。
