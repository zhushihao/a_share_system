# -*- coding: utf-8 -*-
"""
UX P0/P1：修复信号列表名称缺失，并补充 signal_type / strategy 中文标签
"""

import json
import urllib.request
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class UXSignalNamesLabelsRule(Rule):
    name = "ux_signal_names_labels"
    description = "修复信号列表股票名称显示为代码，并中文化信号类型与策略"
    keywords = [
        "signals API",
        "股票名称显示为代码数字",
        "signal_type",
        "strategy",
        "BUY",
        "SELL",
        "bai_da_right_side",
        "vol_price_breakout",
        "ma_death_cross",
    ]
    risk = "medium"
    priority = 0
    requires_restart = True

    _SIGNALS_FILE = PROJECT_ROOT / "backend" / "api" / "signals.py"

    def detect(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/signals?limit=100", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return False, f"无法获取信号列表: {e}"

        signals = data.get("signals", [])
        if not signals:
            return False, "信号列表为空，无需修复"

        name_missing = [s for s in signals if s.get("name") == s.get("symbol")]
        label_missing = [s for s in signals if "signal_type_label" not in s or "strategy_label" not in s]
        issues = []
        if name_missing:
            issues.append(f"{len(name_missing)} 条信号名称仍为代码")
        if label_missing:
            issues.append(f"{len(label_missing)} 条信号缺少中文标签")
        if issues:
            return True, "; ".join(issues)
        return False, "信号列表名称与标签正常"

    def apply(self) -> Tuple[bool, str]:
        path = self._SIGNALS_FILE
        text = path.read_text(encoding="utf-8")

        if "SIGNAL_TYPE_LABELS" in text and "signal_type_label" in text:
            return True, "signals.py 已包含名称补全与中文标签"

        self.backup("backend/api/signals.py")

        # 1. 插入映射常量
        old_router = '''router = APIRouter()


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────'''
        new_router = '''router = APIRouter()


# 信号类型 / 策略中文映射
SIGNAL_TYPE_LABELS = {
    "BUY": "买入",
    "SELL": "卖出",
    "WATCH": "关注",
    "ALERT": "预警",
    "HOLD": "观望",
}

STRATEGY_LABELS = {
    "ma_golden_cross": "均线金叉",
    "ma_death_cross": "均线死叉",
    "vol_price_breakout": "放量突破",
    "vol_price_collapse": "放量下跌",
    "cai_sen_w_bottom": "蔡森 W 底",
    "cai_sen_head_shoulder": "蔡森头肩底",
    "bai_da_right_side": "右侧买入",
    "signal_composer": "多因子合成",
    "vwap_break": "突破均价",
    "vol_surge_stagnation": "放量滞涨",
    "opening_eight": "开盘八法",
}


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────'''
        if old_router not in text:
            return False, "未找到 signals.py 中 router 锚点"
        text = text.replace(old_router, new_router)

        # 2. 修改 _signal_result_to_dict
        old_to_dict = '''def _signal_result_to_dict(s: SignalResult) -> Dict[str, Any]:
    """将 SignalResult 转换为字典"""
    return {
        "symbol": s.symbol,
        "name": s.name,
        "timestamp": s.timestamp.isoformat() if isinstance(s.timestamp, datetime) else str(s.timestamp),
        "signal_type": s.signal_type.value,
        "strategy": s.strategy.value,
        "category": s.category.value,
        "description": s.description,
        "confidence": s.confidence,
        "price": s.price,
        "target_price": s.target_price,
        "stop_loss": s.stop_loss,
        "extra_data": s.extra_data,
    }'''
        new_to_dict = '''def _signal_result_to_dict(s: SignalResult) -> Dict[str, Any]:
    """将 SignalResult 转换为字典"""
    st = s.signal_type.value
    stg = s.strategy.value
    return {
        "symbol": s.symbol,
        "name": s.name,
        "timestamp": s.timestamp.isoformat() if isinstance(s.timestamp, datetime) else str(s.timestamp),
        "signal_type": st,
        "signal_type_label": SIGNAL_TYPE_LABELS.get(st, st),
        "strategy": stg,
        "strategy_label": STRATEGY_LABELS.get(stg, stg),
        "category": s.category.value,
        "description": s.description,
        "confidence": s.confidence,
        "price": s.price,
        "target_price": s.target_price,
        "stop_loss": s.stop_loss,
        "extra_data": s.extra_data,
    }'''
        if old_to_dict not in text:
            return False, "未找到 _signal_result_to_dict 旧代码块"
        text = text.replace(old_to_dict, new_to_dict)

        # 3. 在 list_signals 返回前补充名称和标签
        old_return = '''        for item in items:
            item['category'] = strategy_to_category.get(item.get('strategy', ''), 'daily')
        
        return {
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "signals": items,
        }'''
        new_return = '''        for item in items:
            item['category'] = strategy_to_category.get(item.get('strategy', ''), 'daily')
        
        # 从 stock-list 补充缺失的中文名称，并附加中文标签
        name_map = {}
        try:
            stock_df = _get_data_provider().fetch_stock_list()
            if stock_df is not None and len(stock_df) > 0 and "code" in stock_df.columns and "name" in stock_df.columns:
                for _, row in stock_df.iterrows():
                    code = str(row.get("code", "")).zfill(6)
                    name = str(row.get("name", "")).strip()
                    if code and name and name != code:
                        name_map[code] = name
        except Exception:
            pass
        
        for item in items:
            symbol = str(item.get("symbol", "")).zfill(6)
            name = item.get("name", "")
            if not name or name == symbol:
                item["name"] = name_map.get(symbol, symbol)
            
            st = item.get("signal_type", "")
            item["signal_type_label"] = SIGNAL_TYPE_LABELS.get(st, st)
            stg = item.get("strategy", "")
            item["strategy_label"] = STRATEGY_LABELS.get(stg, stg)
        
        return {
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "signals": items,
        }'''
        if old_return not in text:
            return False, "未找到 list_signals 返回代码块"
        text = text.replace(old_return, new_return)

        path.write_text(text, encoding="utf-8")
        return True, "已修复 signals.py 名称补全与中文标签"

    def verify(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/signals?limit=100", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return False, f"验证请求失败: {e}"

        signals = data.get("signals", [])
        if not signals:
            return True, "信号列表为空"

        for s in signals:
            if s.get("name") == s.get("symbol"):
                return False, f"信号 {s.get('symbol')} 名称仍为代码"
            if "signal_type_label" not in s:
                return False, "信号缺少 signal_type_label"
            if "strategy_label" not in s:
                return False, "信号缺少 strategy_label"
        return True, f"信号列表名称与标签正常（{len(signals)} 条）"
