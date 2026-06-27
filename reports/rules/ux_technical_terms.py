# -*- coding: utf-8 -*-
"""
UX P1：修复技术指标、技术形态、信号类型/策略英文未本地化的问题

涉及：
  - backend/api/quote.py 增加指标 labels 与形态 display_name
  - backend/services/patterns.py 将三角形描述中的英文子类型中文化
  - frontend StockDetail.tsx / Signals.tsx 使用后端返回的中文标签
"""

import json
import urllib.request
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class UXTechnicalTermsRule(Rule):
    name = "ux_technical_terms"
    description = "中文化技术指标、形态、信号类型与策略的展示"
    keywords = [
        "技术指标",
        "技术形态",
        "ma5",
        "macd_dif",
        "kdj_k",
        "v_reversal",
        "head_shoulder_top",
        "convergent",
        "bai_da_right_side",
        "signal_type",
        "strategy",
    ]
    risk = "medium"
    priority = 1
    requires_restart = True

    _QUOTE_FILE = PROJECT_ROOT / "backend" / "api" / "quote.py"
    _PATTERNS_FILE = PROJECT_ROOT / "backend" / "services" / "patterns.py"
    _STOCK_DETAIL_FILE = PROJECT_ROOT / "frontend_react" / "src" / "pages" / "StockDetail.tsx"
    _SIGNALS_FILE = PROJECT_ROOT / "frontend_react" / "src" / "pages" / "Signals.tsx"

    def detect(self) -> Tuple[bool, str]:
        issues = []

        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/indicators?period=daily&limit=5", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "labels" not in data:
                issues.append("indicators API 未返回 labels 映射")
        except Exception as e:
            issues.append(f"indicators API 异常: {e}")

        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/patterns?period=daily", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            patterns = data.get("patterns", [])
            for p in patterns:
                if "display_name" not in p:
                    issues.append("patterns API 未返回 display_name")
                    break
                desc = p.get("reason", "")
                if isinstance(desc, str) and "convergent" in desc:
                    issues.append("patterns description 仍含英文 subtype")
                    break
        except Exception as e:
            issues.append(f"patterns API 异常: {e}")

        if issues:
            return True, "; ".join(issues[:3])
        return False, "技术指标与形态中文映射正常"

    def apply(self) -> Tuple[bool, str]:
        results = []
        ok, msg = self._apply_quote_py()
        results.append(msg)
        if not ok:
            return False, "; ".join(results)

        ok, msg = self._apply_patterns_py()
        results.append(msg)
        if not ok:
            return False, "; ".join(results)

        ok, msg = self._apply_frontend()
        results.append(msg)
        if not ok:
            return False, "; ".join(results)

        return True, "; ".join(results)

    def _apply_quote_py(self) -> Tuple[bool, str]:
        path = self._QUOTE_FILE
        text = path.read_text(encoding="utf-8")

        if "INDICATOR_LABELS" in text and "PATTERN_DISPLAY_NAMES" in text:
            return True, "quote.py 已包含指标/形态中文映射"

        self.backup("backend/api/quote.py")

        old_router = '''router = APIRouter()


def _get_platform():'''
        new_router = '''router = APIRouter()


# 技术指标中文标签
INDICATOR_LABELS = {
    "ma5": "5日均线",
    "ma10": "10日均线",
    "ma20": "20日均线",
    "ma60": "60日均线",
    "macd_dif": "MACD差离值",
    "macd_dea": "MACD信号线",
    "macd_bar": "MACD柱状线",
    "macd": "MACD",
    "kdj_k": "KDJ-K线",
    "kdj_d": "KDJ-D线",
    "kdj_j": "KDJ-J线",
    "rsi6": "RSI(6)",
    "rsi12": "RSI(12)",
    "rsi24": "RSI(24)",
    "boll_up": "布林上轨",
    "boll_mid": "布林中轨",
    "boll_down": "布林下轨",
    "obv": "OBV能量潮",
    "dmi_pdi": "DMI+DI",
    "dmi_mdi": "DMI-DI",
    "dmi_adx": "DMI-ADX",
}

# 技术形态中文显示名称与描述词映射
PATTERN_DISPLAY_NAMES = {
    "v_reversal": "V型反转",
    "head_shoulder_top": "头肩顶",
    "head_shoulder_bottom": "头肩底",
    "double_top": "双顶",
    "double_bottom": "双底",
    "triangle": "三角形",
    "fibonacci_retracement": "斐波那契回调",
}

PATTERN_SUBTYPE_LABELS = {
    "convergent": "收敛",
    "ascending": "上升",
    "descending": "下降",
    "bottom": "底部",
    "top": "顶部",
    "breakout": "突破",
}


def _get_platform():'''
        if old_router not in text:
            return False, "未找到 quote.py router 锚点"
        text = text.replace(old_router, new_router)

        old_indicators = '''    records = df.to_dict("records")
    
    return {
        "symbol": symbol,
        "period": period,
        "adjust": adjust,
        "count": len(records),
        "indicators": latest_indicators or {},
        "data": records,
    }'''
        new_indicators = '''    records = df.to_dict("records")
    indicator_keys = list(latest_indicators.keys()) if latest_indicators else []
    labels = {k: INDICATOR_LABELS.get(k, k) for k in indicator_keys}
    
    return {
        "symbol": symbol,
        "period": period,
        "adjust": adjust,
        "count": len(records),
        "indicators": latest_indicators or {},
        "labels": labels,
        "data": records,
    }'''
        if old_indicators not in text:
            return False, "未找到 get_indicators 返回代码块"
        text = text.replace(old_indicators, new_indicators)

        old_patterns = '''        np["pattern"] = ptype
        np["pattern_type"] = ptype
        np["name"] = ptype
        # position 映射：从 subtype 推断，若为空则根据形态类型推断
        subtype = np.get("subtype", "")
        if not subtype or not str(subtype).strip():
            ptype = np.get("pattern", "") or np.get("pattern_type", "") or np.get("type", "")
            if "top" in ptype.lower():
                subtype = "top"
            elif "bottom" in ptype.lower():
                subtype = "bottom"
            elif "breakout" in ptype.lower() or "breakdown" in ptype.lower():
                subtype = "breakout"
        np["position"] = subtype
        np["accuracy"] = np.get("confidence", 0)
        np["reason"] = np.get("description", "")
        normalized_patterns.append(np)'''
        new_patterns = '''        np["pattern"] = ptype
        np["pattern_type"] = ptype
        np["name"] = ptype
        # 中文显示名称
        np["display_name"] = PATTERN_DISPLAY_NAMES.get(ptype, ptype)
        # position 映射：从 subtype 推断，若为空则根据形态类型推断
        subtype = np.get("subtype", "")
        if not subtype or not str(subtype).strip():
            ptype = np.get("pattern", "") or np.get("pattern_type", "") or np.get("type", "")
            if "top" in ptype.lower():
                subtype = "top"
            elif "bottom" in ptype.lower():
                subtype = "bottom"
            elif "breakout" in ptype.lower() or "breakdown" in ptype.lower():
                subtype = "breakout"
        np["position"] = subtype
        np["accuracy"] = np.get("confidence", 0)
        # 将 description 中的英文子类型翻译为中文，提升可读性
        reason = str(np.get("description", "") or "")
        for en, cn in PATTERN_SUBTYPE_LABELS.items():
            reason = reason.replace(en, cn)
        np["reason"] = reason
        normalized_patterns.append(np)'''
        if old_patterns not in text:
            return False, "未找到 get_patterns 规范化代码块"
        text = text.replace(old_patterns, new_patterns)

        path.write_text(text, encoding="utf-8")
        return True, "已扩展 quote.py 指标/形态中文映射"

    def _apply_patterns_py(self) -> Tuple[bool, str]:
        path = self._PATTERNS_FILE
        text = path.read_text(encoding="utf-8")

        if "subtype_cn = {" in text:
            return True, "patterns.py 三角形描述已中文化"

        self.backup("backend/services/patterns.py")

        old_block = '''    results.append({
        "type": "triangle",
        "subtype": subtype,
        "start_date": str(recent_peaks.iloc[0]["date"]),
        "end_date": str(latest["date"]),
        "upper_bound": round(float(upper), 3),
        "lower_bound": round(float(lower), 3),
        "confidence": confidence,
        "description": (
            f"{subtype}三角形：上边界 {upper:.2f}，下边界 {lower:.2f}，"
            f"等待突破方向"
        ),
    })'''
        new_block = '''    subtype_cn = {"convergent": "收敛", "ascending": "上升", "descending": "下降"}.get(subtype, subtype)
    results.append({
        "type": "triangle",
        "subtype": subtype,
        "start_date": str(recent_peaks.iloc[0]["date"]),
        "end_date": str(latest["date"]),
        "upper_bound": round(float(upper), 3),
        "lower_bound": round(float(lower), 3),
        "confidence": confidence,
        "description": (
            f"{subtype_cn}三角形：上边界 {upper:.2f}，下边界 {lower:.2f}，等待突破方向"
        ),
    })'''
        if old_block not in text:
            return False, "未找到 detect_triangle 描述代码块"
        text = text.replace(old_block, new_block)

        path.write_text(text, encoding="utf-8")
        return True, "已修复 patterns.py 三角形描述中文"

    def _apply_frontend(self) -> Tuple[bool, str]:
        detail_path = self._STOCK_DETAIL_FILE
        detail_text = detail_path.read_text(encoding="utf-8")
        if "p.display_name || p.pattern" not in detail_text:
            self.backup("frontend_react/src/pages/StockDetail.tsx")
            old = '<div className="font-medium text-sm text-slate-800">{p.pattern}</div>'
            new = '<div className="font-medium text-sm text-slate-800">{p.display_name || p.pattern}</div>'
            if old in detail_text:
                detail_text = detail_text.replace(old, new)
                detail_path.write_text(detail_text, encoding="utf-8")
            else:
                return False, "未找到 StockDetail.tsx 形态显示代码"

        signals_path = self._SIGNALS_FILE
        signals_text = signals_path.read_text(encoding="utf-8")
        if "signal.strategy_label || signal.strategy" not in signals_text:
            self.backup("frontend_react/src/pages/Signals.tsx")
            old = '<span className="text-xs text-slate-500">{signal.strategy}</span>'
            new = '<span className="text-xs text-slate-500">{signal.strategy_label || signal.strategy}</span>'
            if old in signals_text:
                signals_text = signals_text.replace(old, new)
                signals_path.write_text(signals_text, encoding="utf-8")
            else:
                return False, "未找到 Signals.tsx 策略显示代码"

        return True, "前端已使用中文标签"

    def verify(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/indicators?period=daily&limit=5", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "labels" not in data:
                return False, "indicators API 仍未返回 labels"
        except Exception as e:
            return False, f"indicators 验证失败: {e}"

        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/patterns?period=daily", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            patterns = data.get("patterns", [])
            for p in patterns:
                if "display_name" not in p:
                    return False, "patterns API 仍未返回 display_name"
                desc = p.get("reason", "")
                if isinstance(desc, str) and "convergent" in desc:
                    return False, "patterns description 仍含 convergent"
        except Exception as e:
            return False, f"patterns 验证失败: {e}"

        return True, "技术指标与形态中文映射验证通过"
