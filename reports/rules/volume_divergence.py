# -*- coding: utf-8 -*-
"""
量价底背离计算修正规则

原逻辑把当前成交量与“前期高点对应的成交量”比较，导致底背离判断错误。
应改为与“前期低点对应的成交量”比较。
"""

from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class VolumeDivergenceRule(Rule):
    name = "volume_divergence"
    description = "修正 signal_composer 底背离成交量的比较对象"
    keywords = ["底背离", "成交量", "max_close_vol", "量价", "divergence"]
    risk = "medium"
    requires_restart = True

    def detect(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        text = composer_file.read_text(encoding="utf-8")

        # 定位 _score_volume 函数
        start = text.find("def _score_volume")
        end = text.find("def _score_support_resistance", start)
        func_text = text[start:end]

        # 如果已经使用 min_close_vol 或 min_close_idx，则认为已修复
        if "min_close_vol" in func_text or "min_close_idx" in func_text:
            return False, "底背离已使用低点成交量比较"

        if "curr_vol > max_close_vol * 1.5" in func_text:
            return True, "底背离仍错误使用 max_close_vol 作为比较基准"
        return False, "未检测到相关底背离逻辑"

    def apply(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        self.backup("backend/services/signal_composer.py")
        text = composer_file.read_text(encoding="utf-8")

        old_block = '''            max_close_idx = prev_window["close"].idxmax()
            max_close_price = prev_window.loc[max_close_idx, "close"]
            max_close_vol = prev_window.loc[max_close_idx, "volume"]
            curr_close = recent.iloc[-1]["close"]
            curr_vol = recent.iloc[-1]["volume"]
            
            if curr_close > max_close_price * 1.01 and curr_vol < max_close_vol * 0.8:
                score -= 0.3
                details["divergence"] = "顶背离：价格创新高但成交量萎缩"
            # 底背离：当前收盘价创前19日新低，但成交量放大（>前低量的1.5倍）
            elif curr_close < prev_window["close"].min() * 1.01 and curr_vol > max_close_vol * 1.5:
                score += 0.2
                details["divergence"] = "潜在底背离：价格创新低但成交量放大"'''

        new_block = '''            max_close_idx = prev_window["close"].idxmax()
            max_close_price = prev_window.loc[max_close_idx, "close"]
            max_close_vol = prev_window.loc[max_close_idx, "volume"]
            min_close_idx = prev_window["close"].idxmin()
            min_close_vol = prev_window.loc[min_close_idx, "volume"]
            curr_close = recent.iloc[-1]["close"]
            curr_vol = recent.iloc[-1]["volume"]
            
            if curr_close > max_close_price * 1.01 and curr_vol < max_close_vol * 0.8:
                score -= 0.3
                details["divergence"] = "顶背离：价格创新高但成交量萎缩"
            # 底背离：当前收盘价创前19日新低，但成交量放大（>前低量的1.5倍）
            elif curr_close < prev_window["close"].min() * 0.99 and curr_vol > min_close_vol * 1.5:
                score += 0.2
                details["divergence"] = "潜在底背离：价格创新低但成交量放大"'''

        if old_block not in text:
            return False, "未找到需要替换的底背离代码块，可能源码已变化"

        text = text.replace(old_block, new_block)
        composer_file.write_text(text, encoding="utf-8")
        return True, "已修正底背离成交量比较对象为前期低点成交量"

    def verify(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        text = composer_file.read_text(encoding="utf-8")
        start = text.find("def _score_volume")
        end = text.find("def _score_support_resistance", start)
        func_text = text[start:end]

        if "min_close_vol" not in func_text:
            return False, "底背离逻辑未使用 min_close_vol"
        if "curr_vol > max_close_vol * 1.5" in func_text:
            return False, "底背离仍错误使用 max_close_vol"
        return True, "底背离成交量比较对象已修正"
