# -*- coding: utf-8 -*-
"""
UX P0：修复股票列表中部分代码无中文名称的问题

根因：infoharbor_ex.code 未覆盖上海指数（000003/000015/000018 等），
      且 data.py 把上海指数代码开头为 0 的误判为深圳市场。
修复：
  1. mootdx_provider 解析 shs.tnf / szs.tnf / bjs.tnf 补全名称；
  2. data.py 保留 provider 返回的 market 字段并用于筛选。
"""

import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

from reports.rules import PROJECT_ROOT, Rule


class UXStockListNamesRule(Rule):
    name = "ux_stock_list_names"
    description = "修复股票列表中部分代码名称显示为代码数字的问题"
    keywords = [
        "stock-list",
        "股票名称显示为代码数字",
        "000003",
        "000015",
        "000018",
        "mootdx_provider",
        "backend/api/data.py",
    ]
    risk = "medium"
    priority = 0
    requires_restart = True

    _MOOTDX_FILE = PROJECT_ROOT / "utils" / "mootdx_provider.py"
    _DATA_FILE = PROJECT_ROOT / "backend" / "api" / "data.py"

    def detect(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/data/stock-list?limit=20000", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return False, f"无法获取股票列表: {e}"

        stocks = data.get("stocks", [])
        # 忽略债券/可转债代码（11/12/13 开头），聚焦股票与指数
        bad = [
            s for s in stocks
            if s.get("name") == s.get("code") and not str(s.get("code", "")).startswith(("11", "12", "13"))
        ]
        if not bad:
            return False, "股票列表名称正常"
        return True, f"股票列表中 {len(bad)} 条名称仍为代码，例如 {bad[0]['code']}"

    def apply(self) -> Tuple[bool, str]:
        ok1, msg1 = self._apply_mootdx()
        ok2, msg2 = self._apply_data_py()
        return ok1 and ok2, f"{msg1}; {msg2}"

    def _apply_mootdx(self) -> Tuple[bool, str]:
        path = self._MOOTDX_FILE
        text = path.read_text(encoding="utf-8")

        # 已修复则跳过
        if "_load_stock_names_from_tnf" in text:
            return True, "mootdx_provider 已包含 tnf 名称解析"

        self.backup("utils/mootdx_provider.py")

        old_scan = '''    def _scan_local_stocks(self) -> List[Dict]:
        """扫描本地通达信数据目录获取股票列表（带名称）"""
        stocks = []
        vipdoc_dir = os.path.join(self.tdxdir, "vipdoc")
        
        # 优先从 TDX 的 infoharbor_ex.code 读取代码→名称映射（本地、快速、准确）
        name_map = self._load_stock_names_from_infoharbor()
        
        # 兜底：base.dbf 或东方财富在线接口
        if not name_map:
            name_map = self._load_stock_names_from_base_dbf()
        if not name_map:
            name_map = self._load_stock_names_from_eastmoney()'''

        new_scan = '''    def _scan_local_stocks(self) -> List[Dict]:
        """扫描本地通达信数据目录获取股票列表（带名称）"""
        stocks = []
        vipdoc_dir = os.path.join(self.tdxdir, "vipdoc")
        
        # 优先从 TDX 的 shs.tnf / szs.tnf / bjs.tnf 读取代码→名称映射（覆盖指数、B股等 infoharbor 缺失的代码）
        name_map = self._load_stock_names_from_tnf()
        
        # infoharbor_ex.code 对普通股票名称更准确，用来覆盖 TNF 中的 XD/XR 前缀临时名称
        name_map.update(self._load_stock_names_from_infoharbor())
        
        # 兜底：base.dbf 或东方财富在线接口
        if not name_map:
            name_map = self._load_stock_names_from_base_dbf()
        if not name_map:
            name_map = self._load_stock_names_from_eastmoney()'''

        if old_scan not in text:
            return False, "未找到 _scan_local_stocks 旧代码块，无法自动修补"
        text = text.replace(old_scan, new_scan)

        tnf_method = '''
    def _load_stock_names_from_tnf(self) -> Dict[str, str]:
        """从 TDX shs.tnf / szs.tnf / bjs.tnf 读取代码→名称映射

        通达信的 tnf 文件是定长二进制文件，每条记录 300 字节，
        不同市场/板块的记录在文件中有多个起始偏移（0/60/120/180/240）。
        该方法遍历所有可能偏移，提取 code（0-8 字节）和 name（31-48 字节，GBK）。
        """
        name_map = {}
        tnf_files = [
            ("sh", "shs.tnf"),
            ("sz", "szs.tnf"),
            ("bj", "bjs.tnf"),
        ]

        for market, filename in tnf_files:
            tnf_path = os.path.join(self.tdxdir, "T0002", "hq_cache", filename)
            if not os.path.exists(tnf_path):
                continue
            try:
                with open(tnf_path, "rb") as f:
                    # 文件头 50 字节
                    f.seek(50)
                    data = f.read()
                record_size = 300
                for base in range(0, record_size, 60):
                    record_count = (len(data) - base) // record_size
                    for i in range(record_count):
                        offset = base + i * record_size
                        rec = data[offset:offset + record_size]
                        if len(rec) < record_size:
                            break
                        code = rec[0:9].split(b"\x00")[0].decode("ascii", errors="ignore").strip()
                        name = rec[31:49].split(b"\x00")[0].decode("gbk", errors="ignore").strip()
                        if code.isdigit() and len(code) == 6 and name:
                            name_map[code] = name
            except Exception as e:
                if self._obs:
                    self._obs.log("WARN", f"{filename} parse failed: {e}", "OfflineDataProvider")

        return name_map
'''

        # 插入到 _load_stock_names_from_base_dbf 之前
        anchor = '    def _load_stock_names_from_base_dbf(self) -> Dict[str, str]:'
        if anchor not in text:
            return False, "未找到 _load_stock_names_from_base_dbf 锚点"
        text = text.replace(anchor, tnf_method + anchor)

        path.write_text(text, encoding="utf-8")
        return True, "已扩展 mootdx_provider 的 TNF 名称解析"

    def _apply_data_py(self) -> Tuple[bool, str]:
        path = self._DATA_FILE
        text = path.read_text(encoding="utf-8")

        if "raw_market if raw_market in" in text:
            return True, "data.py 已保留 provider 市场字段"

        self.backup("backend/api/data.py")

        old_block = '''        # 筛选市场
        if market and "code" in df.columns:
            if market.lower() == "sh":
                df = df[df["code"].astype(str).str.startswith("6")]
            elif market.lower() == "sz":
                df = df[df["code"].astype(str).str.startswith(("0", "3"))]
            elif market.lower() == "bj":
                df = df[df["code"].astype(str).str.startswith(("4", "8"))]

        # 按代码排序，避免截断时丢失特定股票（如 300308 中际旭创）
        df = df.sort_values(by="code").reset_index(drop=True).head(limit)

        # 转换为标准格式
        records = []
        for _, row in df.iterrows():
            records.append({
                "code": str(row.get("code", "")),
                "name": str(row.get("name", "")),
                "market": _infer_market(str(row.get("code", ""))),
            })'''

        new_block = '''        # 筛选市场：优先使用 provider 返回的 market 字段，避免把上海指数代码误判为深圳
        if market and "market" in df.columns:
            df = df[df["market"].astype(str).str.lower() == market.lower()]
        elif market and "code" in df.columns:
            if market.lower() == "sh":
                df = df[df["code"].astype(str).str.startswith("6")]
            elif market.lower() == "sz":
                df = df[df["code"].astype(str).str.startswith(("0", "3"))]
            elif market.lower() == "bj":
                df = df[df["code"].astype(str).str.startswith(("4", "8"))]

        # 按代码排序，避免截断时丢失特定股票（如 300308 中际旭创）
        df = df.sort_values(by="code").reset_index(drop=True).head(limit)

        # 转换为标准格式，保留 provider 返回的市场字段
        records = []
        for _, row in df.iterrows():
            raw_market = str(row.get("market", "")).lower().strip()
            code = str(row.get("code", ""))
            records.append({
                "code": code,
                "name": str(row.get("name", "")),
                "market": raw_market if raw_market in ("sh", "sz", "bj") else _infer_market(code),
            })'''

        if old_block not in text:
            return False, "未找到 data.py get_stock_list 旧代码块"
        text = text.replace(old_block, new_block)

        old_search = '''            if (row_code.startswith(q) or row_code.startswith(code_6) or 
                q in row_name.lower()):
                matches.append({
                    "code": row_code,
                    "name": row_name,
                    "market": _infer_market(row_code),
                })'''

        new_search = '''            if (row_code.startswith(q) or row_code.startswith(code_6) or 
                q in row_name.lower()):
                row_market = str(row.get("market", "")).lower().strip()
                matches.append({
                    "code": row_code,
                    "name": row_name,
                    "market": row_market if row_market in ("sh", "sz", "bj") else _infer_market(row_code),
                })'''

        if old_search in text:
            text = text.replace(old_search, new_search)

        path.write_text(text, encoding="utf-8")
        return True, "已修复 data.py 市场字段保留逻辑"

    def verify(self) -> Tuple[bool, str]:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:5889/api/v1/data/stock-list?limit=20000", timeout=15
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return False, f"验证请求失败: {e}"

        stocks = data.get("stocks", [])
        for code in ("000003", "000015", "000018"):
            item = next((s for s in stocks if s.get("code") == code), None)
            if item is None:
                return False, f"验证时未找到 {code}"
            if item.get("name") == code:
                return False, f"{code} 名称仍为代码"
            if item.get("market") != "sh":
                return False, f"{code} 市场被误标为 {item.get('market')}"

        bad = [
            s for s in stocks
            if s.get("name") == s.get("code") and not str(s.get("code", "")).startswith(("11", "12", "13"))
        ]
        return True, f"股票列表名称修复完成，剩余 {len(bad)} 条无名称"
