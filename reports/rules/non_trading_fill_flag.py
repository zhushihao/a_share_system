# -*- coding: utf-8 -*-
"""
非交易日数据填充标记规则

当最新 K 线出现在周末/节假日，且 OHLC 与前一日完全相同时，在返回数据中标记 is_filled。
"""

import json
import sqlite3
import urllib.request
from datetime import datetime
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class NonTradingFillFlagRule(Rule):
    name = "non_trading_fill_flag"
    description = "对非交易日复制填充的 OHLCV 数据增加 is_filled 标记"
    keywords = ["非交易日", "复制填充", "forward fill", "is_filled", "填充数据"]
    risk = "medium"
    requires_restart = True

    def _clear_ohlcv_cache(self):
        """清除 OHLCV 缓存，强制下次请求走新代码"""
        for cache_dir in [
            PROJECT_ROOT / "backend" / "data" / "cache",
            PROJECT_ROOT / "data" / "cache",
        ]:
            if not cache_dir.exists():
                continue
            for pkl in cache_dir.glob("*.pkl"):
                try:
                    pkl.unlink()
                except Exception:
                    pass
            l3_db = cache_dir / "cache_l3.db"
            if l3_db.exists():
                try:
                    conn = sqlite3.connect(str(l3_db))
                    conn.execute("DELETE FROM cache_entries WHERE key LIKE 'ohlcv:%'")
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

    def detect(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/ohlcv?limit=5", timeout=10
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("data", [])
                if rows and "is_filled" not in rows[0]:
                    return True, "OHLCV 返回记录缺少 is_filled 字段"
                return False, "OHLCV 已包含 is_filled 字段"
        except Exception as e:
            return True, f"无法验证 OHLCV 字段: {e}"

    def apply(self) -> Tuple[bool, str]:
        dp_file = PROJECT_ROOT / "backend" / "services" / "data_provider.py"
        self.backup("backend/services/data_provider.py")
        text = dp_file.read_text(encoding="utf-8")

        helper = '''\n    def _detect_filled_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:\n        """\n        检测非交易日复制填充。\n        若最后一条数据的日期为周末，且 OHLC 与前一条完全相同，则标记 is_filled=True。\n        """\n        if df is None or len(df) < 2:\n            if df is not None:\n                df["is_filled"] = False\n            return df\n        df = df.copy()\n        df["is_filled"] = False\n        last = df.iloc[-1]\n        prev = df.iloc[-2]\n        try:\n            last_date = str(int(last.get("date", "")))\n            if len(last_date) == 8:\n                dt = datetime.strptime(last_date, "%Y%m%d")\n                if dt.weekday() >= 5:  # 周六/周日\n                    ohlc_same = (\n                        abs(float(last.get("open", 0)) - float(prev.get("open", 0))) < 1e-6\n                        and abs(float(last.get("high", 0)) - float(prev.get("high", 0))) < 1e-6\n                        and abs(float(last.get("low", 0)) - float(prev.get("low", 0))) < 1e-6\n                        and abs(float(last.get("close", 0)) - float(prev.get("close", 0))) < 1e-6\n                    )\n                    if ohlc_same:\n                        df.at[df.index[-1], "is_filled"] = True\n        except Exception:\n            pass\n        return df\n'''

        old_return = '''        # 选择标准列
        standard_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
        available_cols = [c for c in standard_cols if c in df.columns]
        return df[available_cols]'''

        new_return = '''        # 检测非交易日填充
        df = self._detect_filled_ohlcv(df)

        # 选择标准列
        standard_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "is_filled"]
        available_cols = [c for c in standard_cols if c in df.columns]
        return df[available_cols]'''

        # 幂等：已存在 helper 和新列顺序则直接清缓存
        if "def _detect_filled_ohlcv" in text and '"is_filled"' in text:
            self._clear_ohlcv_cache()
            return True, "is_filled 逻辑已存在，仅清除 OHLCV 缓存"

        if old_return not in text:
            return False, "未找到 _standardize_ohlcv 返回语句，可能源码已变化"

        if "def _detect_filled_ohlcv" not in text:
            anchor = "    def _aggregate_period"
            if anchor not in text:
                return False, "未找到插入 helper 的位置"
            text = text.replace(anchor, helper + anchor, 1)

        text = text.replace(old_return, new_return, 1)
        dp_file.write_text(text, encoding="utf-8")
        self._clear_ohlcv_cache()
        return True, "已在 data_provider.py 中添加 is_filled 检测逻辑并清除 OHLCV 缓存"

    def verify(self) -> Tuple[bool, str]:
        dp_file = PROJECT_ROOT / "backend" / "services" / "data_provider.py"
        text = dp_file.read_text(encoding="utf-8")
        if "def _detect_filled_ohlcv" not in text:
            return False, "未找到 _detect_filled_ohlcv 函数"
        if '"is_filled"' not in text:
            return False, "列顺序未包含 is_filled"
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/quote/000001/ohlcv?limit=5", timeout=10
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("data", [])
                if rows and "is_filled" not in rows[0]:
                    return False, "运行时 OHLCV 仍缺少 is_filled"
                return True, "运行时 OHLCV 已返回 is_filled"
        except Exception as e:
            return False, f"运行时验证失败: {e}"
