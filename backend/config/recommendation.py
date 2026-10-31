"""推荐评分权重配置：环境变量读取、合法性校验、启动时失败。"""

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


def get_weights():
    """读取并校验推荐权重配置。

    优先级：
    1. 环境变量 CAMPUSBITE_WEIGHT_T / _P / _D / _R（若存在且合法）
    2. DEFAULT_WEIGHTS 常量

    校验：
    - 每个权重须为有效 Decimal
    - 每个权重须在 [0, 1] 范围内
    - 四维权重之和须为 1.0

    异常：
    - ConfigError：配置非法时抛出，消息包含具体字段名和非法值
    """
    weights = {}
    for key, env_var in _ENV_MAP.items():
        raw = os.environ.get(env_var)
        if raw is None:
            weights[key] = DEFAULT_WEIGHTS[key]
        else:
            try:
                weights[key] = Decimal(raw)
            except Exception:
                raise ConfigError(
                    f"权重 {key} 环境变量 {env_var} 值 '{raw}' 无法解析为数值"
                )
    for key, value in weights.items():
        if value < 0 or value > 1:
            raise ConfigError(
                f"权重 {key} 值 {value} 超出合法范围 [0, 1]"
            )
    total = sum(weights.values())
    if total != Decimal("1.00"):
        raise ConfigError(
            f"权重总和 {total} 不等于 1.0"
            f"（T={weights['T']}, P={weights['P']},"
            f" D={weights['D']}, R={weights['R']}）"
        )
    return weights
