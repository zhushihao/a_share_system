"""
配置加载模块 - 读取系统全局配置
"""
import os
import yaml
from typing import Dict, Any

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "system.yaml")
_CONFIG_PATH = os.path.abspath(_CONFIG_PATH)

_cached_config = None


def load_config() -> Dict[str, Any]:
    """加载全局配置文件"""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_config = yaml.safe_load(f)
    return _cached_config


def get_config(path: str, default: Any = None) -> Any:
    """
    按路径获取配置值
    path: 用点分隔，如 'pattern.confidence.min_acceptable'
    """
    cfg = load_config()
    keys = path.split(".")
    for key in keys:
        if isinstance(cfg, dict) and key in cfg:
            cfg = cfg[key]
        else:
            return default
    return cfg


# 预加载常用配置
CONF_PATTERN = load_config().get("pattern", {})
CONF_TRAFFIC = load_config().get("traffic_light", {})
CONF_SECTOR = load_config().get("sector", {})
CONF_RISK = load_config().get("risk_management", {})
CONF_MARKET = load_config().get("market_regime", {})
CONF_BUY = load_config().get("buy_points", {})
