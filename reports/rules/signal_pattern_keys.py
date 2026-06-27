# -*- coding: utf-8 -*-
"""
SignalComposer 形态键名对齐规则

patterns.py 对 V 型反转返回 type="v_reversal" + subtype="bottom/top"，
signal_composer 原有逻辑只匹配 v_reversal_bottom/v_reversal_top，导致 V 转信号丢失。
本规则补齐对 v_reversal subtype 的处理。
"""

from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class SignalPatternKeysRule(Rule):
    name = "signal_pattern_keys"
    description = "修复 signal_composer 对 V 型反转形态键名的匹配"
    keywords = ["形态键名不匹配", "v_reversal", "signal_composer", "V 型", "形态评分"]
    risk = "medium"
    requires_restart = True

    def detect(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        text = composer_file.read_text(encoding="utf-8")

        # 如果已经存在 v_reversal subtype 处理，则跳过
        if 'ptype == "v_reversal"' in text:
            return False, "signal_composer 已处理 v_reversal subtype"

        if "v_reversal_bottom" in text or "v_reversal_top" in text:
            return True, "signal_composer 仍使用旧的 v_reversal_* 键名"
        return False, "未检测到相关形态键名问题"

    def apply(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        self.backup("backend/services/signal_composer.py")
        text = composer_file.read_text(encoding="utf-8")

        old_block = '''        # 三角形特殊处理：type="triangle"，subtype 区分方向
        if ptype == "triangle":
            if subtype == "ascending":
                score += conf * 0.4
                details["detected"].append(f"+ascending_triangle({conf:.2f})")
            elif subtype == "descending":
                score -= conf * 0.4
                details["detected"].append(f"-descending_triangle({conf:.2f})")
            elif subtype == "convergent":
                # 收敛三角形方向中性，轻微加分（等待突破）
                score += conf * 0.1
                details["detected"].append(f"~convergent_triangle({conf:.2f})")
        elif ptype in bullish_types:'''

        new_block = '''        # V 型反转特殊处理：type="v_reversal"，subtype 区分顶/底
        if ptype == "v_reversal":
            if subtype == "bottom":
                score += conf * 0.5
                details["detected"].append(f"+v_reversal_bottom({conf:.2f})")
            elif subtype == "top":
                score -= conf * 0.5
                details["detected"].append(f"-v_reversal_top({conf:.2f})")
        # 三角形特殊处理：type="triangle"，subtype 区分方向
        elif ptype == "triangle":
            if subtype == "ascending":
                score += conf * 0.4
                details["detected"].append(f"+ascending_triangle({conf:.2f})")
            elif subtype == "descending":
                score -= conf * 0.4
                details["detected"].append(f"-descending_triangle({conf:.2f})")
            elif subtype == "convergent":
                # 收敛三角形方向中性，轻微加分（等待突破）
                score += conf * 0.1
                details["detected"].append(f"~convergent_triangle({conf:.2f})")
        elif ptype in bullish_types:'''

        if old_block not in text:
            return False, "未找到需要替换的代码块，可能源码已变化"

        text = text.replace(old_block, new_block)
        composer_file.write_text(text, encoding="utf-8")
        return True, "已补齐 signal_composer 对 v_reversal subtype 的处理"

    def verify(self) -> Tuple[bool, str]:
        composer_file = PROJECT_ROOT / "backend" / "services" / "signal_composer.py"
        text = composer_file.read_text(encoding="utf-8")
        if 'ptype == "v_reversal"' not in text:
            return False, "未找到 v_reversal 处理逻辑"
        if "+v_reversal_bottom" not in text or "-v_reversal_top" not in text:
            return False, "v_reversal 顶底处理不完整"
        return True, "signal_composer 形态键名已对齐"
