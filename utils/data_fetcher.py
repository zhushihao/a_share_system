"""
数据获取模块 v3 - 混合策略：ifind 为主 + stock_finance_data 备选 + 东方财富 为辅
ifind: 个股历史K线（通过脚本，批量高效）
stock_finance_data: 备选数据源（内置，稳定，指数代码正确）
东方财富: 板块数据、全市场列表、龙虎榜、涨跌停、北向资金（ifind未覆盖）
"""

import requests
import pandas as pd
import json
import time
import os
import sys
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------
IFIND_SCRIPT = r"C:\Users\江厉害\AppData\Roaming\kimi-desktop\daimon-share\daimon\plugin-packages\ifind\scripts\ifind_tool.py"
if not os.path.exists(IFIND_SCRIPT):
    IFIND_SCRIPT = r"C:\Users\江厉害\AppData\Roaming\kimi-desktop\daimon-share\daimon\runtime\kimi-code\home\plugins\managed\ifind\scripts\ifind_tool.py"

EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}
EM_SESSION = requests.Session()
EM_SESSION.headers.update(EM_HEADERS)


# ---------------------------------------------------------------------------
# stock_finance_data 封装（内置数据源，作为 ifind 备选）
# ---------------------------------------------------------------------------

def _sfd_get_price(ticker: str, start_date: str, end_date: str, 
                   interval: str = "D", adjust: str = "forward") -> Optional[pd.DataFrame]:
    """
    通过 stock_finance_data 获取历史价格数据
    ticker 格式: XXXXXX.SH/SZ/BJ, XXXXXX.HK, XXXXXX.US
    start_date/end_date: YYYY-MM-DD
    
    返回 DataFrame 或 None（失败时）
    """
    try:
        # 使用 kimi_datasource_call_v2 的 Python 绑定
        import importlib.util
        spec = importlib.util.find_spec("kimi_datasource_call_v2")
        if spec is None:
            # 降级：直接调用 data source（如果可用）
            return None
        
        # 通过 subprocess 调用内置脚本（更可靠）
        tmp_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "raw", "tmp", f"sfd_{ticker.replace('.', '_')}_{int(time.time())}.csv"
        )
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        
        params = {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "file_path": tmp_path,
            "interval": interval,
            "adjust": adjust,
            "format": "json",
        }
        
        # 使用 agent-gw 的 call_data_source_tool
        cmd = [
            sys.executable, "-c",
            f"""
import sys, json, os
sys.path.insert(0, r"C:\\Users\\江厉害\\AppData\\Roaming\\kimi-desktop\\daimon-share\\daimon\\runtime\\python\\.venv\\Lib\\site-packages")
from agent_gw import call_data_source_tool

result = call_data_source_tool({{
    "data_source_name": "stock_finance_data",
    "api_name": "stock_finance_data_get_price",
    "params": {json.dumps(params)}
}})
print(json.dumps({{
    "is_success": result.get("is_success", False),
    "has_files": len(result.get("files", [])) > 0
}}))
"""
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if proc.returncode != 0:
            return None
        
        result = json.loads(proc.stdout.strip())
        if not result.get("is_success"):
            return None
        
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            return None
        
        df = pd.read_csv(tmp_path)
        if len(df) == 0:
            return None
        
        # 标准化列名
        df = df.rename(columns={
            "time": "date",
            "thscode": "code",
        })
        df["date"] = pd.to_datetime(df["date"])
        
        # 确保有必要的列
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                return None
        
        return df.sort_values("date").reset_index(drop=True)
        
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _retry_get(url: str, max_retries: int = 3, timeout: int = 30, sleep: float = 1.0) -> requests.Response:
    """带重试的 GET 请求（东方财富）"""
    for i in range(max_retries):
        try:
            r = EM_SESSION.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception:
            if i < max_retries - 1:
                time.sleep(sleep * (i + 1))
    return EM_SESSION.get(url, timeout=timeout)


def _market_code(code: str) -> str:
    """获取东方财富市场前缀：上海=1, 深圳=0, 北京=0"""
    if code.startswith("6") or code.startswith("8") or code.startswith("9"):
        return f"1.{code}"
    elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
        return f"0.{code}"
    elif code.startswith("4") or code.startswith("8"):
        return f"0.{code}"
    return f"0.{code}"


def _to_ifind_ticker(code: str) -> str:
    """6位代码 → ifind ticker 格式 XXXXXX.SZ/SH/BJ
    
    注意：指数代码需要特殊处理（如000300是沪深300，在上海交易所）
    """
    # 上海交易所指数（0开头但属于SH）
    SH_INDEXES = {"000001", "000300", "000016", "000905", "000852", "000688", "000010"}
    # 深圳交易所指数
    SZ_INDEXES = {"399001", "399006", "399300", "399005", "399101"}
    
    if code in SH_INDEXES:
        return f"{code}.SH"
    if code in SZ_INDEXES:
        return f"{code}.SZ"
    
    # 个股/其他指数
    if code.startswith("6") or code.startswith("8") or code.startswith("9"):
        return f"{code}.SH"
    elif code.startswith("4") or code.startswith("8") or code.startswith("9"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def _call_ifind(api_name: str, params: dict) -> dict:
    """调用 ifind 插件脚本，返回解析后的结果"""
    # 使用临时文件保存 CSV，然后读取
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"ifind_{api_name}_{int(time.time())}.csv")
    params["file_path"] = tmp_path

    cmd = [
        sys.executable, IFIND_SCRIPT, "call",
        "--api-name", api_name,
        "--params-json", json.dumps(params)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=os.path.dirname(IFIND_SCRIPT))

    if proc.returncode != 0:
        raise RuntimeError(f"ifind call failed: {proc.stderr}")

    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
        # 可能没有文件返回，返回空
        return {"df": pd.DataFrame(), "stdout": proc.stdout}

    df = pd.read_csv(tmp_path)
    return {"df": df, "stdout": proc.stdout}


# ---------------------------------------------------------------------------
# ifind 数据源（稳定）
# ---------------------------------------------------------------------------

def ifind_daily_kline(code: str, start_date: str, end_date: str, adjust: str = "forward") -> pd.DataFrame:
    """
    使用 ifind 获取个股历史日线（首选）
    code: 6位代码如 "000001"
    start_date/end_date: "YYYY-MM-DD"
    adjust: forward=前复权, backward=后复权, none=不复权
    返回: DataFrame[date, open, high, low, close, volume, ...]
    """
    ticker = _to_ifind_ticker(code)
    result = _call_ifind("ifind_get_price", {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "interval": "D",
        "adjust": adjust,
    })
    df = result["df"]
    if df.empty:
        return pd.DataFrame()

    # 标准化列名
    rename_map = {
        "time": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "date" not in df.columns and "time" in df.columns:
        df["date"] = df["time"]

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def ifind_stock_info(code: str) -> dict:
    """获取股票基本信息（名称等）"""
    ticker = _to_ifind_ticker(code)
    result = _call_ifind("ifind_get_stock_info", {"ticker": ticker})
    df = result["df"]
    if df.empty:
        return {"name": code, "code": code}
    row = df.iloc[0].to_dict()
    return {
        "code": code,
        "name": row.get("thsname_cn", code),
        "ticker": ticker,
    }


def ifind_close_summary(code: str) -> dict:
    """获取个股收盘摘要（当日快照）"""
    ticker = _to_ifind_ticker(code)
    result = _call_ifind("ifind_get_stock_realtime_price", {
        "ticker": ticker,
        "type": "close_summary",
    })
    df = result["df"]
    if df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {
        "code": code,
        "close": row.get("close"),
        "pre_close": row.get("pre_close"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "change_pct": row.get("pct_chg"),
        "volume": row.get("volume"),
        "amount": row.get("amt"),
        "turnover": row.get("turn"),
    }


# ---------------------------------------------------------------------------
# 东方财富 数据源（ifind 未覆盖的板块/市场级数据）
# ---------------------------------------------------------------------------

def em_fetch_stock_list() -> pd.DataFrame:
    """获取全市场 A 股列表（含实时行情快照）"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=6000&po=1&np=1&fltt=2&invt=2&fid=f20"
        "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:204"
        "&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f20,f21,f22,f23,f24,f25,f26,f33,f34,f35,f36,f37,f38,f39,f40,f41,f42,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f57,f58,f60,f61,f62,f63,f64,f65,f66,f67,f68,f69,f70,f71,f72,f73,f74,f75,f76,f77,f78,f79,f80,f81,f82,f83,f84,f85,f86,f87,f88,f89,f90,f91,f92,f93,f94,f95,f96,f97,f98,f99,f100"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("data") is None or data["data"].get("diff") is None:
        return pd.DataFrame()

    raw = data["data"]["diff"]
    rows = []
    for item in raw:
        rows.append({
            "code": item.get("f12", ""),
            "name": item.get("f14", ""),
            "close": item.get("f2", 0) / 100 if item.get("f2") else 0,
            "change_pct": item.get("f3", 0) / 100 if item.get("f3") else 0,
            "change_amount": item.get("f4", 0) / 100 if item.get("f4") else 0,
            "volume": item.get("f5", 0),
            "amount": item.get("f6", 0) / 10000 if item.get("f6") else 0,
            "amplitude": item.get("f7", 0) / 100 if item.get("f7") else 0,
            "turnover": item.get("f8", 0) / 100 if item.get("f8") else 0,
            "pe_ttm": item.get("f9", 0),
            "volume_ratio": item.get("f10", 0) / 100 if item.get("f10") else 0,
            "high": item.get("f15", 0) / 100 if item.get("f15") else 0,
            "low": item.get("f16", 0) / 100 if item.get("f16") else 0,
            "open": item.get("f17", 0) / 100 if item.get("f17") else 0,
            "pre_close": item.get("f18", 0) / 100 if item.get("f18") else 0,
            "total_mv": item.get("f20", 0) / 100000000 if item.get("f20") else 0,
            "circ_mv": item.get("f21", 0) / 100000000 if item.get("f21") else 0,
            "pb": item.get("f23", 0),
            "pct_60d": item.get("f24", 0) / 100 if item.get("f24") else 0,
            "pct_ytd": item.get("f25", 0) / 100 if item.get("f25") else 0,
            "is_st": str(item.get("f58", "") or "").startswith("ST") or "ST" in str(item.get("f58", "") or ""),
            "list_date": item.get("f26", ""),
        })

    df = pd.DataFrame(rows)
    df = df[df["code"].str.len() == 6]
    return df


def em_fetch_daily_kline(code: str, start_date: str, end_date: str, period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
    """东方财富日线/周线（作为 ifind 降级备选）"""
    klt = "101" if period == "daily" else "102" if period == "weekly" else "103"
    # 东方财富 fqt: 0=不复权, 1=前复权, 2=后复权
    fqt = {"qfq": "1", "hfq": "2", "none": "0", "1": "1", "2": "2", "0": "0"}.get(adjust, "1")
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={_market_code(code)}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt={klt}&fqt={fqt}&beg={start_date}&end={end_date}&lmt=100000"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("data") is None or data["data"].get("klines") is None:
        return pd.DataFrame()

    klines = data["data"]["klines"]
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 9:
            continue
        rows.append({
            "date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": int(parts[5]),
            "amount": float(parts[6]),
            "amplitude": float(parts[7]),
            "pct_change": float(parts[8]),
            "turnover": float(parts[9]) if len(parts) > 9 else 0,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def em_fetch_minute_kline(code: str, period: str = "5") -> pd.DataFrame:
    """东方财富分钟级 K 线"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={_market_code(code)}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt={period}&fqt=1&lmt=1000"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("data") is None or data["data"].get("klines") is None:
        return pd.DataFrame()

    klines = data["data"]["klines"]
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        rows.append({
            "datetime": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": int(parts[5]),
            "amount": float(parts[6]) if len(parts) > 6 else 0,
        })

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def _clean_em_text(text: str) -> str:
    """清理东方财富接口返回的文本：强制 UTF-8 并处理 GBK 误解码产生的 surrogate"""
    if not isinstance(text, str):
        return str(text)
    # 若包含 surrogate pair，说明被错误解码，尝试按 latin1→gbk 重新解码
    if any(0xDC00 <= ord(c) <= 0xDFFF for c in text):
        try:
            return text.encode("latin1", "replace").decode("gbk", "ignore")
        except Exception:
            pass
    return text


def em_fetch_sector_list() -> pd.DataFrame:
    """同花顺概念板块列表（带异常降级）"""
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f20"
            "&fs=m:90+t:2"
            "&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,f21,f22,f23,f24,f25,f26,f27,f28,f29,f30,f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f41,f42,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65,f66,f67,f68,f69,f70,f71,f72,f73,f74,f75,f76,f77,f78,f79,f80,f81,f82,f83,f84,f85,f86,f87,f88,f89,f90,f91,f92,f93,f94,f95,f96,f97,f98,f99,f100"
        )
        r = _retry_get(url, max_retries=2, timeout=15)
        r.encoding = "utf-8"
        data = r.json()
        if data.get("data") is None or data["data"].get("diff") is None:
            return pd.DataFrame()
        raw = data["data"]["diff"]
        rows = []
        for item in raw:
            rows.append({
                "sector_code": item.get("f12", ""),
                "sector_name": _clean_em_text(item.get("f14", "")),
                "close": item.get("f2", 0) / 100 if item.get("f2") else 0,
                "change_pct": item.get("f3", 0) if item.get("f3") else 0,
                "volume": item.get("f5", 0),
                "amount": item.get("f6", 0) / 10000 if item.get("f6") else 0,
                "pct_20d": item.get("f24", 0) / 100 if item.get("f24") else 0,
                "pct_60d": item.get("f25", 0) / 100 if item.get("f25") else 0,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        # 降级：返回空DataFrame，让调用方使用内置列表
        return pd.DataFrame()


def _default_sector_list() -> pd.DataFrame:
    """内置默认板块列表（当东方财富接口失败时降级使用）"""
    default_sectors = [
        ("BK0477", "酿酒行业"), ("BK0478", "银行"), ("BK0479", "保险"), ("BK0480", "证券"),
        ("BK0481", "电力行业"), ("BK0482", "房地产"), ("BK0483", "化工行业"), ("BK0484", "钢铁"),
        ("BK0485", "有色金属"), ("BK0486", "煤炭行业"), ("BK0487", "医药制造"), ("BK0488", "医疗"),
        ("BK0489", "汽车整车"), ("BK0490", "电子元件"), ("BK0491", "软件服务"), ("BK0492", "通信设备"),
        ("BK0493", "半导体"), ("BK0494", "光伏设备"), ("BK0495", "电池"), ("BK0496", "电机"),
        ("BK0497", "专用设备"), ("BK0498", "通用机械"), ("BK0499", "农牧饲渔"), ("BK0500", "食品饮料"),
        ("BK0501", "家电行业"), ("BK0502", "纺织服装"), ("BK0503", "造纸印刷"), ("BK0504", "建材"),
        ("BK0505", "装修装饰"), ("BK0506", "交运设备"), ("BK0507", "交运物流"), ("BK0508", "旅游酒店"),
        ("BK0509", "文化传媒"), ("BK0510", "商业百货"), ("BK0511", "包装材料"), ("BK0512", "珠宝首饰"),
        ("BK0513", "工艺商品"), ("BK0514", "航天航空"), ("BK0515", "船舶制造"), ("BK0516", "工程机械"),
        ("BK0517", "环保工程"), ("BK0518", "燃气"), ("BK0519", "公用事业"), ("BK0520", "高速公路"),
        ("BK0521", "港口水运"), ("BK0522", "民航机场"), ("BK0523", "水泥建材"), ("BK0524", "化肥"),
        ("BK0525", "农药兽药"), ("BK0526", "化纤行业"), ("BK0527", "橡胶制品"), ("BK0528", "塑料制品"),
        ("BK0529", "玻璃陶瓷"), ("BK0530", "金属制品"), ("BK0531", "仪器仪表"), ("BK0532", "电力行业"),
    ]
    rows = []
    for code, name in default_sectors:
        rows.append({
            "sector_code": code, "sector_name": name,
            "close": 0, "change_pct": 0, "volume": 0, "amount": 0,
            "pct_20d": 0, "pct_60d": 0,
        })
    return pd.DataFrame(rows)


def em_fetch_sector_kline(sector_code: str, start_date: str, end_date: str, period: str = "daily") -> pd.DataFrame:
    """板块指数 K 线（带异常降级）"""
    try:
        klt = "101" if period == "daily" else "102"
        # 修复日期格式：确保为 YYYYMMDD
        start_date = start_date.replace("-", "")
        end_date = end_date.replace("-", "")
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid=90.{sector_code}"
            f"&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt={klt}&fqt=0&beg={start_date}&end={end_date}&lmt=100000"
        )
        r = _retry_get(url, max_retries=2, timeout=15)
        data = r.json()
        if data.get("data") is None or data["data"].get("klines") is None:
            return pd.DataFrame()
        klines = data["data"]["klines"]
        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 9:
                continue
            rows.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": int(parts[5]),
                "amount": float(parts[6]),
                "amplitude": float(parts[7]),
                "pct_change": float(parts[8]),
            })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()


def em_fetch_sector_components(sector_code: str) -> pd.DataFrame:
    """板块成分股列表（带异常降级）"""
    try:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz=200&po=1&np=1&fltt=2&invt=2&fid=f20"
            f"&fs=b:{sector_code}"
            f"&fields=f12,f13,f14,f2,f3,f20,f21"
        )
        r = _retry_get(url, max_retries=2, timeout=15)
        r.encoding = "utf-8"
        data = r.json()
        if data.get("data") is None or data["data"].get("diff") is None:
            return pd.DataFrame()
        raw = data["data"]["diff"]
        rows = []
        for item in raw:
            rows.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "close": item.get("f2", 0) / 100 if item.get("f2") else 0,
                "change_pct": item.get("f3", 0) / 100 if item.get("f3") else 0,
                "total_mv": item.get("f20", 0) / 100000000 if item.get("f20") else 0,
                "circ_mv": item.get("f21", 0) / 100000000 if item.get("f21") else 0,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame()

def em_fetch_sector_component_count(sector_code: str) -> int:
    """获取板块成分股数量（轻量接口，仅取 total）"""
    try:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz=1&po=1&np=1&fltt=2&invt=2&fid=f20"
            f"&fs=b:{sector_code}"
            f"&fields=f12"
        )
        r = _retry_get(url, max_retries=1, timeout=10)
        r.encoding = "utf-8"
        data = r.json()
        if data.get("data") is None:
            return 0
        return int(data["data"].get("total", 0) or 0)
    except Exception:
        return 0



def em_fetch_northbound_money(start_date: str, end_date: str) -> pd.DataFrame:
    """北向资金历史"""
    url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get"
        "?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=500&pageNumber=1"
        "&reportName=RPT_MUTUAL_DEAL_HISTORY&columns=ALL&source=WEB&client=WEB"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("result") is None or data["result"].get("data") is None:
        return pd.DataFrame()

    raw = data["result"]["data"]
    rows = []
    for item in raw:
        rows.append({
            "date": item.get("TRADE_DATE", ""),
            "north_net": item.get("NORTH_NET_INFLOW", 0) / 100000000,
            "south_net": item.get("SOUTH_NET_INFLOW", 0) / 100000000,
            "sh_net": item.get("SH_NET_INFLOW", 0) / 100000000,
            "sz_net": item.get("SZ_NET_INFLOW", 0) / 100000000,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
    return df.sort_values("date").reset_index(drop=True)


def em_fetch_dragon_tiger(date_str: str) -> pd.DataFrame:
    """龙虎榜"""
    url = (
        f"https://datacenter-web.eastmoney.com/api/data/v1/get"
        f"?sortColumns=NET_BUY_AMT&sortTypes=-1&pageSize=500&pageNumber=1"
        f"&reportName=RPT_DAILYBILLBOARD_DETAILS&columns=ALL&source=WEB&client=WEB"
        f"&filter=(TRADE_DATE%3D%27{date_str}%27)"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("result") is None or data["result"].get("data") is None:
        return pd.DataFrame()

    raw = data["result"]["data"]
    rows = []
    for item in raw:
        rows.append({
            "code": item.get("SECURITY_CODE", ""),
            "name": item.get("SECURITY_NAME_ABBR", ""),
            "trade_date": item.get("TRADE_DATE", ""),
            "close": item.get("CLOSE_PRICE", 0),
            "change_pct": item.get("CHANGE_RATE", 0),
            "net_buy": item.get("NET_BUY_AMT", 0) / 10000,
            "buy_amt": item.get("BUY_AMT", 0) / 10000,
            "sell_amt": item.get("SELL_AMT", 0) / 10000,
            "turnover": item.get("TURNOVERRATE", 0),
            "deal_amount": item.get("DEAL_AMOUNT", 0),
            "free_mv": item.get("FREE_MARKET_CAP", 0),
        })
    return pd.DataFrame(rows)


def em_fetch_limit_up_down(date_str: str) -> pd.DataFrame:
    """涨跌停"""
    url = (
        f"https://datacenter-web.eastmoney.com/api/data/v1/get"
        f"?sortColumns=UD_RATE&sortTypes=-1&pageSize=500&pageNumber=1"
        f"&reportName=RPT_DAILYBILLBOARD_ZTGC&columns=ALL&source=WEB&client=WEB"
        f"&filter=(TRADE_DATE%3D%27{date_str}%27)"
    )
    r = _retry_get(url)
    data = r.json()
    if data.get("result") is None or data["result"].get("data") is None:
        return pd.DataFrame()

    raw = data["result"]["data"]
    rows = []
    for item in raw:
        rows.append({
            "code": item.get("SECURITY_CODE", ""),
            "name": item.get("SECURITY_NAME_ABBR", ""),
            "trade_date": item.get("TRADE_DATE", ""),
            "close": item.get("CLOSE_PRICE", 0),
            "limit_type": item.get("LIMIT_UP_DOWN_TYPE", ""),
            "first_time": item.get("FIRST_TIME", ""),
            "last_time": item.get("LAST_TIME", ""),
            "open_times": item.get("OPEN_TIMES", 0),
            "board_amount": item.get("BOARD_AMOUNT", 0) / 10000,
            "board_ratio": item.get("BOARD_RATIO", 0),
            "ud_rate": item.get("UD_RATE", 0),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 统一接口（优先 ifind，降级到东方财富）
# ---------------------------------------------------------------------------

def fetch_daily_kline(code: str, start_date: str, end_date: str, period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
    """
    获取个股日线（统一接口，带智能降级）
    
    降级链: ifind → stock_finance_data → 东方财富 → Cache → Empty
    
    参数:
        code: 6位代码如 "000001"
        start_date/end_date: "YYYYMMDD" 或 "YYYY-MM-DD"
        period: daily/weekly/monthly
        adjust: qfq=前复权, 0=none, 2=后复权
    返回:
        DataFrame[date, open, high, low, close, volume, ...] 或空DataFrame
    """
    from core.resilience import get_resilience
    
    # 统一日期格式为 YYYY-MM-DD（resilience 层期望的格式）
    if len(start_date) == 8 and start_date.isdigit():
        start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
    if len(end_date) == 8 and end_date.isdigit():
        end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
    
    resilience = get_resilience()
    result = resilience.fetch_kline(code, start_date, end_date, period, adjust)
    
    if result.success and result.data is not None:
        df = result.data
        # 确保返回 DataFrame
        if isinstance(df, pd.DataFrame):
            return df
        elif isinstance(df, list):
            return pd.DataFrame(df)
    
    return pd.DataFrame()


def fetch_stock_list() -> pd.DataFrame:
    """全市场列表（仅东方财富）"""
    return em_fetch_stock_list()


def fetch_minute_kline(code: str, period: str = "5") -> pd.DataFrame:
    """分钟级 K 线（仅东方财富）"""
    return em_fetch_minute_kline(code, period)


def fetch_sector_list() -> pd.DataFrame:
    """板块列表（优先东方财富，失败降级到内置默认列表）"""
    df = em_fetch_sector_list()
    if len(df) > 0:
        return df
    # 降级：使用内置默认板块列表
    return _default_sector_list()


def fetch_sector_kline(sector_code: str, start_date: str, end_date: str, period: str = "daily") -> pd.DataFrame:
    """板块 K 线（仅东方财富）"""
    return em_fetch_sector_kline(sector_code, start_date, end_date, period)


def fetch_sector_components(sector_code: str) -> pd.DataFrame:
    """板块成分股（仅东方财富）"""
    return em_fetch_sector_components(sector_code)


def fetch_northbound_money(start_date: str, end_date: str) -> pd.DataFrame:
    """北向资金（仅东方财富）"""
    return em_fetch_northbound_money(start_date, end_date)


def fetch_dragon_tiger(date_str: str) -> pd.DataFrame:
    """龙虎榜（仅东方财富）"""
    return em_fetch_dragon_tiger(date_str)


def fetch_limit_up_down(date_str: str) -> pd.DataFrame:
    """涨跌停（仅东方财富）"""
    return em_fetch_limit_up_down(date_str)


# 保持向后兼容的旧函数名
fetch_stock_info = ifind_stock_info
fetch_close_summary = ifind_close_summary


if __name__ == "__main__":
    # 快速测试
    print("Testing data_fetcher v2...")

    # Test ifind
    print("\n--- ifind daily kline (000001) ---")
    df = ifind_daily_kline("000001", "2025-06-01", "2025-06-19")
    print(f"Rows: {len(df)}, Columns: {list(df.columns)}")
    if len(df) > 0:
        print(df.tail(3))

    # Test unified interface
    print("\n--- unified fetch_daily_kline (000001) ---")
    df2 = fetch_daily_kline("000001", "20250601", "20250619")
    print(f"Rows: {len(df2)}")
    if len(df2) > 0:
        print(df2.tail(3))
