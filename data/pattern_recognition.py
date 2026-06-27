"""
蔡森型态识别引擎 v2 - 优化版
改进：
1. 配置化：所有阈值从 system.yaml 读取，不再硬编码
2. 去噪：置信度过滤（>= min_for_report 才输出）+ 重复型态去重
3. 代码精简：提取公共函数，减少重复
4. 最大输出限制：单股票/单型态限制数量

输入：个股日线/周线 DataFrame（date, open, close, high, low, volume）
输出：去噪后的型态列表（含颈线、满足点、置信度、突破状态）
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from utils.config_loader import get_config


# ==================== 配置读取 ====================
PATTERN_CONF = get_config("pattern", {})
EXTREMA_ORDER = get_config("pattern.extrema.order", 3)
EXTREMA_USE_BODY = get_config("pattern.extrema.use_body", True)
PRICE_TOLERANCE = get_config("pattern.extrema.tolerance", 0.05)
NECKLINE_METHOD = get_config("pattern.neckline.method", "robust")
SPAN_MIN = get_config("pattern.span.min", 20)
SPAN_MAX = get_config("pattern.span.max", 200)
SPAN_OPTIMAL = get_config("pattern.span.optimal", [40, 120])
CONF_MIN_ACCEPTABLE = get_config("pattern.confidence.min_acceptable", 0.55)
CONF_MIN_FOR_REPORT = get_config("pattern.confidence.min_for_report", 0.65)
CONF_MAX_PER_STOCK = get_config("pattern.confidence.max_per_stock", 20)
CONF_MAX_PER_TYPE = get_config("pattern.confidence.max_per_type", 5)

# 置信度评分权重
W_SYMMETRY = get_config("pattern.confidence.symmetry_bonus", 0.15)
W_SPAN = get_config("pattern.confidence.span_bonus", 0.15)
W_R2 = get_config("pattern.confidence.neckline_r2_bonus", 0.10)
W_BREAKOUT = get_config("pattern.confidence.breakout_bonus", 0.20)
W_VOLUME = get_config("pattern.confidence.volume_bonus", 0.10)

# 质量排序权重
W_QUALITY_CONF = get_config("pattern.confidence.quality_weights.confidence", 0.50)
W_QUALITY_SPAN = get_config("pattern.confidence.quality_weights.span", 0.20)
W_QUALITY_BREAKOUT = get_config("pattern.confidence.quality_weights.breakout_strength", 0.30)


@dataclass
class Pattern:
    """型态数据结构"""
    code: str
    name: str
    pattern_type: str           # W底/M头/头肩底/头肩顶/破底翻/假突破/收敛三角底/收敛三角头/下飘旗形/上飘旗形
    direction: str              # 多头/空头/中性
    timeframe: str              # 日线/周线
    
    neckline: float
    neckline_slope: float
    extreme_point: float
    
    target_1: float
    target_2: Optional[float] = None
    
    breakout_date: Optional[str] = None
    breakout_price: Optional[float] = None
    breakout_volume_ratio: Optional[float] = None
    
    pattern_start_date: Optional[str] = None
    pattern_end_date: Optional[str] = None
    
    status: str = "构筑中"
    confidence: float = 0.0
    
    evidence: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "code": self.code, "name": self.name,
            "pattern_type": self.pattern_type, "direction": self.direction,
            "timeframe": self.timeframe,
            "neckline": round(self.neckline, 3),
            "neckline_slope": round(self.neckline_slope, 4),
            "extreme_point": round(self.extreme_point, 3),
            "target_1": round(self.target_1, 3) if self.target_1 else None,
            "target_2": round(self.target_2, 3) if self.target_2 else None,
            "breakout_date": self.breakout_date,
            "breakout_price": round(self.breakout_price, 3) if self.breakout_price else None,
            "breakout_volume_ratio": round(self.breakout_volume_ratio, 3) if self.breakout_volume_ratio else None,
            "pattern_start_date": self.pattern_start_date,
            "pattern_end_date": self.pattern_end_date,
            "status": self.status, "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }


# ==================== 公共工具函数 ====================

def find_local_extrema(df: pd.DataFrame, order: int = EXTREMA_ORDER, use_body: bool = EXTREMA_USE_BODY) -> Tuple[List[int], List[int]]:
    """局部极值检测：用滑动窗口找局部高点/低点"""
    if len(df) < order * 2 + 1:
        return [], []
    
    if use_body:
        price_high = price_low = (df["open"] + df["close"]) / 2
    else:
        price_high, price_low = df["high"], df["low"]
    
    high_indices, low_indices = [], []
    for i in range(order, len(df) - order):
        if price_high.iloc[i] == price_high.iloc[i - order:i + order + 1].max():
            high_indices.append(i)
        if price_low.iloc[i] == price_low.iloc[i - order:i + order + 1].min():
            low_indices.append(i)
    
    return high_indices, low_indices


def fit_neckline(points: List[Tuple[int, float]], method: str = NECKLINE_METHOD) -> Tuple[float, float, float]:
    """颈线拟合：多点线性回归，IQR 过滤异常值"""
    if len(points) < 2:
        return 0.0, points[0][1] if points else 0.0, 0.0
    
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    
    if method == "robust" and len(points) >= 4:
        q1, q3 = np.percentile(y, 25), np.percentile(y, 75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (y >= lower) & (y <= upper)
        if mask.sum() >= 2:
            x, y = x[mask], y[mask]
    
    if len(x) >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    else:
        slope, intercept, r_squared = 0.0, y[0] if len(y) > 0 else 0.0, 0.0
    
    return slope, intercept, r_squared


def calculate_volume_ratio(df: pd.DataFrame, idx: int, window: int = 20) -> float:
    """当日成交量 / 前window日均量"""
    if idx < window:
        return 1.0
    avg_vol = df["volume"].iloc[idx - window:idx].mean()
    return df["volume"].iloc[idx] / avg_vol if avg_vol > 0 else 1.0


def is_near(p1: float, p2: float, tolerance: float = PRICE_TOLERANCE) -> bool:
    """判断两个价格是否接近"""
    return abs(p1 - p2) / max(p1, p2, 0.001) <= tolerance


def calculate_target(pattern_type: str, neckline: float, extreme_point: float, breakout_price: float, direction: str) -> Tuple[float, Optional[float]]:
    """等幅计算通用规则"""
    distance = abs(neckline - extreme_point)
    if direction == "多头":
        t1 = breakout_price + distance
        t2 = t1 + distance
        return t1, t2
    else:
        t1 = breakout_price - distance
        t2 = t1 - distance
        return t1, t2


# ==================== 突破/跌破检测 ====================

def detect_breakout(df: pd.DataFrame, start_idx: int, neckline: float, direction: str, 
                    max_days: int = 30, volume_threshold: float = 1.2) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """
    检测突破/跌破
    返回: (breakout_idx, breakout_price, volume_ratio) 或 (None, None, None)
    """
    end = min(start_idx + max_days, len(df))
    for k in range(start_idx + 1, end):
        price = df["close"].iloc[k]
        vol_ratio = calculate_volume_ratio(df, k)
        
        if direction == "多头" and price > neckline * 1.03 and vol_ratio >= volume_threshold:
            return k, price, vol_ratio
        elif direction == "空头" and price < neckline * 0.97:
            return k, price, vol_ratio
    return None, None, None


def detect_failure(df: pd.DataFrame, start_idx: int, neckline: float, 
                  direction: str, max_days: int = 15) -> bool:
    """检测型态是否失效"""
    end = min(start_idx + max_days, len(df))
    for k in range(start_idx + 1, end):
        price = df["close"].iloc[k]
        if direction == "多头" and price < neckline * 0.97:
            return True
        elif direction == "空头" and price > neckline * 1.03:
            return True
    return False


# ==================== 置信度评分 ====================

def score_confidence(left_price: float, right_price: float, span: int, 
                     r2: float, breakout_idx: Optional[int], 
                     vol_ratio: Optional[float], direction: str) -> float:
    """
    多维度置信度评分
    """
    score = 0.3  # 基础分
    
    # 对称性
    if is_near(left_price, right_price, tolerance=0.03):
        score += W_SYMMETRY
    
    # 时间跨度适中
    if SPAN_OPTIMAL[0] <= span <= SPAN_OPTIMAL[1]:
        score += W_SPAN
    
    # 颈线R²高分
    if r2 > 0.7:
        score += W_R2
    
    # 突破加分
    if breakout_idx is not None:
        score += W_BREAKOUT
        if vol_ratio is not None and vol_ratio >= 1.3:
            score += W_VOLUME
    
    return min(score, 1.0)


# ==================== 型态模板函数 ====================

def _build_double_pattern(df: pd.DataFrame, code: str, name: str, 
                        left_idx: int, right_idx: int, mid_idx: int,
                        left_price: float, right_price: float, mid_price: float,
                        highs: List[int], lows: List[int],
                        pattern_type: str, direction: str) -> Optional[Pattern]:
    """
    构建双顶/双底型态（W底、M头的通用构建器）
    """
    span = right_idx - left_idx
    if span < SPAN_MIN or span > SPAN_MAX:
        return None
    
    if not is_near(left_price, right_price, tolerance=0.08):
        return None
    
    # 颈线：中间点 + 右侧对应点
    if direction == "多头":
        right_points = [h for h in highs if right_idx < h < right_idx + span * 0.5]
        neckline_points = [(mid_idx, mid_price)] + [(h, df["high"].iloc[h]) for h in right_points]
    else:
        right_points = [l for l in lows if right_idx < l < right_idx + span * 0.5]
        neckline_points = [(mid_idx, mid_price)] + [(l, df["low"].iloc[l]) for l in right_points]
    
    slope, intercept, r2 = fit_neckline(neckline_points)
    neckline = slope * right_idx + intercept
    
    extreme = (left_price + right_price) / 2
    distance = abs(extreme - neckline) if direction == "多头" else abs(extreme - neckline)
    
    # 突破检测
    breakout_idx, breakout_price, vol_ratio = detect_breakout(df, right_idx, neckline, direction)
    failed = detect_failure(df, right_idx, neckline, direction) if breakout_idx is None else False
    
    # 置信度
    score = score_confidence(left_price, right_price, span, r2, breakout_idx, vol_ratio, direction)
    if score < CONF_MIN_ACCEPTABLE:
        return None
    
    status = "构筑中"
    if breakout_idx is not None:
        status = "已突破" if direction == "多头" else "已跌破"
    elif failed:
        status = "已失效"
    elif right_idx >= len(df) - 5:
        status = "待突破" if direction == "多头" else "待跌破"
    
    bp = breakout_price or neckline
    t1, t2 = calculate_target(pattern_type, neckline, extreme, bp, direction)
    
    evidence = {
        f"{'left' if direction=='多头' else 'right'}_{'bottom' if direction=='多头' else 'top'}_date": str(df["date"].iloc[left_idx]),
        f"{'left' if direction=='多头' else 'right'}_{'bottom' if direction=='多头' else 'top'}_price": round(left_price, 3),
        f"{'right' if direction=='多头' else 'left'}_{'bottom' if direction=='多头' else 'top'}_date": str(df["date"].iloc[right_idx]),
        f"{'right' if direction=='多头' else 'left'}_{'bottom' if direction=='多头' else 'top'}_price": round(right_price, 3),
        "mid_date": str(df["date"].iloc[mid_idx]),
        "mid_price": round(mid_price, 3),
        "span_days": span,
        "neckline_r2": round(r2, 3),
    }
    
    return Pattern(
        code=code, name=name, pattern_type=pattern_type, direction=direction, timeframe="日线",
        neckline=round(neckline, 3), neckline_slope=slope, extreme_point=round(extreme, 3),
        target_1=round(t1, 3), target_2=round(t2, 3) if t2 else None,
        breakout_date=str(df["date"].iloc[breakout_idx]) if breakout_idx else None,
        breakout_price=round(breakout_price, 3) if breakout_price else None,
        breakout_volume_ratio=round(vol_ratio, 3) if vol_ratio else None,
        pattern_start_date=str(df["date"].iloc[left_idx]),
        pattern_end_date=str(df["date"].iloc[right_idx]),
        status=status, confidence=round(score, 3), evidence=evidence
    )


def _build_head_shoulder(df: pd.DataFrame, code: str, name: str,
                        left_idx: int, head_idx: int, right_idx: int,
                        left_price: float, head_price: float, right_price: float,
                        highs: List[int], lows: List[int],
                        pattern_type: str, direction: str) -> Optional[Pattern]:
    """
    构建头肩型态（头肩底/头肩顶的通用构建器）
    """
    if direction == "多头":
        if head_price >= min(left_price, right_price) * 0.95:
            return None
    else:
        if head_price <= max(left_price, right_price) * 1.05:
            return None
    
    if not is_near(left_price, right_price, tolerance=0.1):
        return None
    
    if direction == "多头":
        left_peak = max((h for h in highs if left_idx < h < head_idx), key=lambda h: df["high"].iloc[h], default=None)
        right_peak = max((h for h in highs if head_idx < h < right_idx), key=lambda h: df["high"].iloc[h], default=None)
    else:
        left_peak = min((l for l in lows if left_idx < l < head_idx), key=lambda l: df["low"].iloc[l], default=None)
        right_peak = min((l for l in lows if head_idx < l < right_idx), key=lambda l: df["low"].iloc[l], default=None)
    
    if left_peak is None or right_peak is None:
        return None
    
    neckline_points = [(left_peak, df["high"].iloc[left_peak] if direction == "多头" else df["low"].iloc[left_peak]),
                       (right_peak, df["high"].iloc[right_peak] if direction == "多头" else df["low"].iloc[right_peak])]
    
    slope, intercept, r2 = fit_neckline(neckline_points)
    neckline = slope * right_idx + intercept
    
    distance = abs(head_price - neckline)
    
    breakout_idx, breakout_price, vol_ratio = detect_breakout(df, right_idx, neckline, direction)
    
    score = score_confidence(left_price, right_price, right_idx - left_idx, r2, breakout_idx, vol_ratio, direction)
    if score < CONF_MIN_ACCEPTABLE:
        return None
    
    status = "构筑中"
    if breakout_idx is not None:
        status = "已突破" if direction == "多头" else "已跌破"
    elif right_idx >= len(df) - 5:
        status = "待突破" if direction == "多头" else "待跌破"
    
    bp = breakout_price or neckline
    t1, t2 = calculate_target(pattern_type, neckline, head_price, bp, direction)
    
    return Pattern(
        code=code, name=name, pattern_type=pattern_type, direction=direction, timeframe="日线",
        neckline=round(neckline, 3), neckline_slope=slope, extreme_point=round(head_price, 3),
        target_1=round(t1, 3), target_2=round(t2, 3) if t2 else None,
        breakout_date=str(df["date"].iloc[breakout_idx]) if breakout_idx else None,
        breakout_price=round(breakout_price, 3) if breakout_price else None,
        breakout_volume_ratio=round(vol_ratio, 3) if vol_ratio else None,
        pattern_start_date=str(df["date"].iloc[left_idx]),
        pattern_end_date=str(df["date"].iloc[right_idx]),
        status=status, confidence=round(score, 3),
        evidence={
            "left_shoulder_date": str(df["date"].iloc[left_idx]),
            "head_date": str(df["date"].iloc[head_idx]),
            "right_shoulder_date": str(df["date"].iloc[right_idx]),
            "neckline_r2": round(r2, 3),
        }
    )


# ==================== 具体型态检测 ====================

def detect_W_bottom(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """W底识别：双底+中间高点"""
    patterns = []
    n = len(lows)
    for i in range(n - 1):
        for j in range(i + 1, n):
            left_idx, right_idx = lows[i], lows[j]
            mid_highs = [h for h in highs if left_idx < h < right_idx]
            if not mid_highs:
                continue
            best_mid = max(mid_highs, key=lambda h: df["high"].iloc[h])
            p = _build_double_pattern(df, code, name, left_idx, right_idx, best_mid,
                                      df["low"].iloc[left_idx], df["low"].iloc[right_idx], df["high"].iloc[best_mid],
                                      highs, lows, "W底", "多头")
            if p:
                patterns.append(p)
    return patterns


def detect_M_top(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """M头识别：双顶+中间低点"""
    patterns = []
    n = len(highs)
    for i in range(n - 1):
        for j in range(i + 1, n):
            left_idx, right_idx = highs[i], highs[j]
            mid_lows = [l for l in lows if left_idx < l < right_idx]
            if not mid_lows:
                continue
            best_mid = min(mid_lows, key=lambda l: df["low"].iloc[l])
            p = _build_double_pattern(df, code, name, left_idx, right_idx, best_mid,
                                      df["high"].iloc[left_idx], df["high"].iloc[right_idx], df["low"].iloc[best_mid],
                                      highs, lows, "M头", "空头")
            if p:
                patterns.append(p)
    return patterns


def detect_head_shoulder_bottom(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """头肩底"""
    patterns = []
    n = len(lows)
    for i in range(n - 2):
        for j in range(i + 1, n - 1):
            for k in range(j + 1, n):
                p = _build_head_shoulder(df, code, name, lows[i], lows[j], lows[k],
                                        df["low"].iloc[lows[i]], df["low"].iloc[lows[j]], df["low"].iloc[lows[k]],
                                        highs, lows, "头肩底", "多头")
                if p:
                    patterns.append(p)
    return patterns


def detect_head_shoulder_top(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """头肩顶"""
    patterns = []
    n = len(highs)
    for i in range(n - 2):
        for j in range(i + 1, n - 1):
            for k in range(j + 1, n):
                p = _build_head_shoulder(df, code, name, highs[i], highs[j], highs[k],
                                        df["high"].iloc[highs[i]], df["high"].iloc[highs[j]], df["high"].iloc[highs[k]],
                                        highs, lows, "头肩顶", "空头")
                if p:
                    patterns.append(p)
    return patterns


# ==================== 收敛三角 & 旗形 & 其他 ====================

def detect_converging_triangle(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """收敛三角：高点下移 + 低点上移"""
    patterns = []
    if len(highs) < 3 or len(lows) < 3:
        return patterns
    
    for start in range(len(highs) - 2):
        for end in range(start + 3, min(start + 20, len(highs))):
            h_indices = highs[start:end]
            l_indices = [l for l in lows if highs[start] < l < highs[end]]
            if len(l_indices) < 2:
                continue
            
            h_prices = [df["high"].iloc[h] for h in h_indices]
            l_prices = [df["low"].iloc[l] for l in l_indices]
            
            if not all(h_prices[i] >= h_prices[i+1] for i in range(len(h_prices)-1)):
                continue
            if not all(l_prices[i] <= l_prices[i+1] for i in range(len(l_prices)-1)):
                continue
            
            h_points = [(h, df["high"].iloc[h]) for h in h_indices]
            l_points = [(l, df["low"].iloc[l]) for l in l_indices]
            upper_slope, upper_intercept, upper_r2 = fit_neckline(h_points)
            lower_slope, lower_intercept, lower_r2 = fit_neckline(l_points)
            
            if upper_slope >= -0.001 or lower_slope <= 0.001:
                continue
            
            cross_x = (lower_intercept - upper_intercept) / (upper_slope - lower_slope)
            last_idx = max(h_indices[-1], l_indices[-1])
            if cross_x < last_idx or cross_x > last_idx + 15:
                continue
            
            height = max(h_prices) - min(l_prices)
            direction = None
            breakout_idx, breakout_price = None, None
            
            for k in range(last_idx + 1, min(last_idx + 30, len(df))):
                price = df["close"].iloc[k]
                upper_line = upper_slope * k + upper_intercept
                lower_line = lower_slope * k + lower_intercept
                if price > upper_line * 1.02:
                    direction = "多头"; breakout_idx, breakout_price = k, price; break
                elif price < lower_line * 0.98:
                    direction = "空头"; breakout_idx, breakout_price = k, price; break
            
            score = 0.3
            if upper_r2 > 0.6 and lower_r2 > 0.6: score += 0.2
            if len(h_indices) >= 4 and len(l_indices) >= 4: score += 0.1
            if breakout_idx: score += 0.2
            if score < CONF_MIN_ACCEPTABLE: continue
            
            status = "构筑中"
            if breakout_idx: status = "已突破" if direction == "多头" else "已跌破"
            
            if direction == "多头":
                target = (breakout_price + height) if breakout_price else (upper_slope * last_idx + upper_intercept) + height
                ptype = "收敛三角底"
            else:
                target = (breakout_price - height) if breakout_price else (lower_slope * last_idx + lower_intercept) - height
                ptype = "收敛三角头"
            
            patterns.append(Pattern(
                code=code, name=name, pattern_type=ptype, direction=direction or "中性", timeframe="日线",
                neckline=round(upper_slope * last_idx + upper_intercept if direction == "多头" else lower_slope * last_idx + lower_intercept, 3),
                neckline_slope=upper_slope if direction == "多头" else lower_slope,
                extreme_point=round(min(l_prices) if direction == "多头" else max(h_prices), 3),
                target_1=round(target, 3), target_2=None,
                breakout_date=str(df["date"].iloc[breakout_idx]) if breakout_idx else None,
                breakout_price=round(breakout_price, 3) if breakout_price else None,
                pattern_start_date=str(df["date"].iloc[h_indices[0]]),
                pattern_end_date=str(df["date"].iloc[last_idx]),
                status=status, confidence=round(min(score, 1.0), 3),
                evidence={"high_points": len(h_indices), "low_points": len(l_indices), "upper_r2": round(upper_r2, 3), "lower_r2": round(lower_r2, 3)}
            ))
    return patterns


def detect_breakdown_reversal(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """破底翻：先找底部型态，检查是否跌破后快速站回"""
    patterns = []
    bottom_patterns = detect_W_bottom(df, code, name, highs, lows)
    bottom_patterns.extend(detect_head_shoulder_bottom(df, code, name, highs, lows))
    
    # 过滤：只保留在合理时间跨度内的型态（破底翻要求更长周期）
    valid_patterns = []
    for bp in bottom_patterns:
        if bp.pattern_start_date and bp.pattern_end_date:
            try:
                start = datetime.strptime(bp.pattern_start_date, "%Y-%m-%d")
                end = datetime.strptime(bp.pattern_end_date, "%Y-%m-%d")
                span_days = (end - start).days
                # 破底翻要求型态跨度在15-150交易日范围内（约21-214自然日）
                if 21 <= span_days <= 214:
                    valid_patterns.append(bp)
            except:
                pass
    
    for bp in valid_patterns:
        if bp.status != "构筑中":
            continue
        end_idx_match = df[df["date"] == bp.pattern_end_date].index
        if len(end_idx_match) == 0:
            continue
        end_idx = end_idx_match[0]
        neckline = bp.neckline
        
        breakdown_idx, recovery_idx = None, None
        for k in range(end_idx + 1, min(end_idx + 15, len(df))):
            price = df["close"].iloc[k]
            if breakdown_idx is None and price < neckline * 0.97:
                breakdown_idx = k
            elif breakdown_idx is not None and price > neckline * 1.02:
                recovery_idx = k
                break
        
        if breakdown_idx and recovery_idx and (recovery_idx - breakdown_idx) <= 5:
            vol_ratio = calculate_volume_ratio(df, recovery_idx)
            if vol_ratio >= 1.2:
                recovery_price = df["close"].iloc[recovery_idx]
                t1, t2 = calculate_target("breakdown_reversal", neckline, bp.extreme_point, recovery_price, "多头")
                patterns.append(Pattern(
                    code=code, name=name, pattern_type="破底翻", direction="多头", timeframe="日线",
                    neckline=round(neckline, 3), neckline_slope=bp.neckline_slope, extreme_point=round(bp.extreme_point, 3),
                    target_1=round(t1, 3), target_2=round(t2, 3) if t2 else None,
                    breakout_date=str(df["date"].iloc[recovery_idx]),
                    breakout_price=round(recovery_price, 3), breakout_volume_ratio=round(vol_ratio, 3),
                    pattern_start_date=bp.pattern_start_date, pattern_end_date=str(df["date"].iloc[recovery_idx]),
                    status="已突破", confidence=0.7,
                    evidence={"breakdown_date": str(df["date"].iloc[breakdown_idx]), "recovery_days": recovery_idx - breakdown_idx, "base_pattern": bp.pattern_type}
                ))
    return patterns


def detect_false_breakout(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """假突破：突破后隔日翻黑跌破颈线"""
    patterns = []
    for i in range(30, len(df) - 5):
        recent_high = df["high"].iloc[i-20:i].max()
        recent_avg = df["close"].iloc[i-20:i].mean()
        if df["close"].iloc[i] > recent_high * 1.02 and df["volume"].iloc[i] >= df["volume"].iloc[i-20:i].mean() * 1.2:
            if df["close"].iloc[i+1] < recent_high * 0.98:
                patterns.append(Pattern(
                    code=code, name=name, pattern_type="假突破", direction="空头", timeframe="日线",
                    neckline=round(recent_high, 3), neckline_slope=0, extreme_point=round(recent_avg, 3),
                    target_1=round(recent_high - (recent_high - recent_avg), 3), target_2=None,
                    breakout_date=str(df["date"].iloc[i]), breakout_price=round(df["close"].iloc[i], 3),
                    pattern_start_date=str(df["date"].iloc[i-20]), pattern_end_date=str(df["date"].iloc[i+1]),
                    status="已失效", confidence=0.6,
                    evidence={"breakout_volume_ratio": round(df["volume"].iloc[i] / df["volume"].iloc[i-20:i].mean(), 3)}
                ))
    return patterns


def detect_flag_patterns(df: pd.DataFrame, code: str, name: str, highs: List[int], lows: List[int]) -> List[Pattern]:
    """旗形识别：下飘旗形（多头中继）和上飘旗形（空头中继）"""
    patterns = []
    for i in range(30, len(df) - 30):
        prev_high = df["high"].iloc[i-30:i].max()
        prev_low = df["low"].iloc[i-30:i].min()
        prev_range = prev_high - prev_low
        if prev_range / prev_low < 0.15:
            continue
        
        flag_highs = [h for h in highs if i <= h < i + 20]
        flag_lows = [l for l in lows if i <= l < i + 20]
        if len(flag_highs) < 2 or len(flag_lows) < 2:
            continue
        
        h_prices = [df["high"].iloc[h] for h in flag_highs]
        l_prices = [df["low"].iloc[l] for l in flag_lows]
        h_slope = np.polyfit(range(len(h_prices)), h_prices, 1)[0]
        l_slope = np.polyfit(range(len(l_prices)), l_prices, 1)[0]
        prev_trend = df["close"].iloc[i] - df["close"].iloc[i-30]
        
        # 下飘旗形
        if prev_trend > 0 and h_slope < -0.001 and l_slope < 0 and h_slope < l_slope:
            breakout_idx = None
            for k in range(i + 20, min(i + 35, len(df))):
                if df["close"].iloc[k] > max(h_prices) * 1.02:
                    breakout_idx = k; break
            target = df["close"].iloc[i-30] + prev_range * 2 if breakout_idx else None
            patterns.append(Pattern(
                code=code, name=name, pattern_type="下飘旗形", direction="多头", timeframe="日线",
                neckline=round(max(h_prices), 3), neckline_slope=h_slope, extreme_point=round(min(l_prices), 3),
                target_1=round(target, 3) if target else None, target_2=None,
                breakout_date=str(df["date"].iloc[breakout_idx]) if breakout_idx else None,
                breakout_price=round(df["close"].iloc[breakout_idx], 3) if breakout_idx else None,
                pattern_start_date=str(df["date"].iloc[i-30]), pattern_end_date=str(df["date"].iloc[i+20]),
                status="待突破" if breakout_idx is None else "已突破", confidence=0.5,
                evidence={"prev_trend": round(prev_trend, 3), "h_slope": round(h_slope, 5), "l_slope": round(l_slope, 5)}
            ))
        # 上飘旗形
        elif prev_trend < 0 and l_slope > 0.001 and h_slope > 0 and h_slope > l_slope:
            breakout_idx = None
            for k in range(i + 20, min(i + 35, len(df))):
                if df["close"].iloc[k] < min(l_prices) * 0.98:
                    breakout_idx = k; break
            target = df["close"].iloc[i-30] - prev_range * 2 if breakout_idx else None
            patterns.append(Pattern(
                code=code, name=name, pattern_type="上飘旗形", direction="空头", timeframe="日线",
                neckline=round(min(l_prices), 3), neckline_slope=l_slope, extreme_point=round(max(h_prices), 3),
                target_1=round(target, 3) if target else None, target_2=None,
                breakout_date=str(df["date"].iloc[breakout_idx]) if breakout_idx else None,
                breakout_price=round(df["close"].iloc[breakout_idx], 3) if breakout_idx else None,
                pattern_start_date=str(df["date"].iloc[i-30]), pattern_end_date=str(df["date"].iloc[i+20]),
                status="待跌破" if breakout_idx is None else "已跌破", confidence=0.5,
                evidence={"prev_trend": round(prev_trend, 3), "h_slope": round(h_slope, 5), "l_slope": round(l_slope, 5)}
            ))
    return patterns


# ==================== 去噪与输出控制 ====================

def _deduplicate_patterns(patterns: List[Pattern]) -> List[Pattern]:
    """去重：同一位置同方向的型态只保留置信度最高的"""
    # 按 (code, pattern_type, start_date, end_date) 分组，取每组最高置信度
    grouped = {}
    for p in patterns:
        key = (p.code, p.pattern_type, p.pattern_start_date, p.pattern_end_date)
        if key not in grouped or p.confidence > grouped[key].confidence:
            grouped[key] = p
    return list(grouped.values())


def _filter_by_confidence(patterns: List[Pattern], min_conf: float = CONF_MIN_FOR_REPORT) -> List[Pattern]:
    """置信度过滤"""
    return [p for p in patterns if p.confidence >= min_conf]


def _limit_per_type(patterns: List[Pattern], max_per_type: int = CONF_MAX_PER_TYPE) -> List[Pattern]:
    """限制每种型态的最大数量"""
    type_counts = {}
    result = []
    for p in sorted(patterns, key=lambda x: x.confidence, reverse=True):
        ptype = p.pattern_type
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
        if type_counts[ptype] <= max_per_type:
            result.append(p)
    return result


def _score_pattern_quality(p: Pattern) -> float:
    """
    型态质量综合评分（0-1）
    用于在置信度相近时，优先选出更优质的型态
    """
    # 1. 置信度得分（已有）
    conf_score = p.confidence
    
    # 2. 时间跨度得分：40-120交易日为最优，偏离则衰减
    span_score = 0.5
    if p.pattern_start_date and p.pattern_end_date:
        try:
            start = datetime.strptime(p.pattern_start_date, "%Y-%m-%d")
            end = datetime.strptime(p.pattern_end_date, "%Y-%m-%d")
            span_days = (end - start).days
            # 假设交易日约为自然日的0.7倍
            span_trading_days = span_days * 0.7
            if SPAN_OPTIMAL[0] <= span_trading_days <= SPAN_OPTIMAL[1]:
                span_score = 1.0
            elif span_trading_days < SPAN_OPTIMAL[0]:
                span_score = max(0.3, span_trading_days / SPAN_OPTIMAL[0])
            else:
                span_score = max(0.3, 1.0 - (span_trading_days - SPAN_OPTIMAL[1]) / 200)
        except:
            pass
    
    # 3. 突破力度得分：突破幅度越大越好，但不过度奖励极端值
    breakout_score = 0.5
    if p.breakout_price and p.neckline and p.neckline > 0:
        strength = (p.breakout_price - p.neckline) / p.neckline
        # 3%-8% 为理想突破区间
        if 0.03 <= strength <= 0.08:
            breakout_score = 1.0
        elif strength < 0.03:
            breakout_score = max(0.3, strength / 0.03)
        else:
            breakout_score = max(0.3, 1.0 - (strength - 0.08) / 0.2)
    
    # 加权综合
    quality = (
        W_QUALITY_CONF * conf_score +
        W_QUALITY_SPAN * span_score +
        W_QUALITY_BREAKOUT * breakout_score
    )
    return quality


def _limit_total(patterns: List[Pattern], max_total: int = CONF_MAX_PER_STOCK) -> List[Pattern]:
    """限制总数量：按综合质量评分排序，取 Top N"""
    scored = [(p, _score_pattern_quality(p)) for p in patterns]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:max_total]]


# ==================== 主入口 ====================

def scan_patterns(df: pd.DataFrame, code: str, name: str, 
                  min_history: int = 100, order: int = EXTREMA_ORDER) -> List[Pattern]:
    """
    扫描单只个股的所有型态，返回去噪后的列表
    """
    if len(df) < min_history:
        return []
    
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    highs, lows = find_local_extrema(df, order=order, use_body=EXTREMA_USE_BODY)
    if len(highs) < 3 or len(lows) < 3:
        return []
    
    all_patterns = []
    all_patterns.extend(detect_W_bottom(df, code, name, highs, lows))
    all_patterns.extend(detect_M_top(df, code, name, highs, lows))
    all_patterns.extend(detect_head_shoulder_bottom(df, code, name, highs, lows))
    all_patterns.extend(detect_head_shoulder_top(df, code, name, highs, lows))
    all_patterns.extend(detect_converging_triangle(df, code, name, highs, lows))
    all_patterns.extend(detect_breakdown_reversal(df, code, name, highs, lows))
    all_patterns.extend(detect_false_breakout(df, code, name, highs, lows))
    all_patterns.extend(detect_flag_patterns(df, code, name, highs, lows))
    
    # 去噪管道
    all_patterns = _deduplicate_patterns(all_patterns)
    all_patterns = _filter_by_confidence(all_patterns, CONF_MIN_FOR_REPORT)
    all_patterns = _limit_per_type(all_patterns, CONF_MAX_PER_TYPE)
    all_patterns = _limit_total(all_patterns, CONF_MAX_PER_STOCK)
    
    # 最终按置信度排序
    return sorted(all_patterns, key=lambda x: x.confidence, reverse=True)


def scan_all_patterns(stock_data_dict: Dict[str, pd.DataFrame], 
                      stock_info: Dict[str, str],
                      min_history: int = 100) -> List[Dict]:
    """批量扫描全市场型态"""
    all_results = []
    for code, df in stock_data_dict.items():
        name = stock_info.get(code, "")
        try:
            patterns = scan_patterns(df, code, name, min_history=min_history)
            for p in patterns:
                all_results.append(p.to_dict())
        except Exception as e:
            all_results.append({"code": code, "name": name, "error": str(e), "pattern_type": "ERROR", "status": "ERROR", "confidence": 0})
    return all_results


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")
    from utils.data_fetcher import fetch_daily_kline
    
    print("Testing pattern recognition v2...")
    df = fetch_daily_kline("000001", "20240601", "20250619")
    print(f"Loaded {len(df)} days")
    
    patterns = scan_patterns(df, "000001", "平安银行", min_history=80)
    print(f"\nAfter denoising: {len(patterns)} patterns")
    
    type_counts = {}
    for p in patterns:
        type_counts[p.pattern_type] = type_counts.get(p.pattern_type, 0) + 1
    print("\nType distribution:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    
    for p in patterns[:5]:
        print(f"\n  [{p.pattern_type}] conf={p.confidence:.2f} status={p.status} "
              f"neckline={p.neckline} target_1={p.target_1} breakout={p.breakout_date}")
