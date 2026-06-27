"""
每日数据下载脚本 - 盘后 19:00 运行
下载全市场日线、板块数据、北向资金、涨跌停数据
输出到 data/raw/YYYYMMDD/ 目录
"""
import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_fetcher import (
    fetch_stock_list, fetch_daily_kline, fetch_sector_list,
    fetch_sector_kline, fetch_northbound_money, fetch_limit_up_down,
    fetch_dragon_tiger
)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def download_daily(date_str: str = None, output_base: str = None):
    """
    下载每日数据
    date_str: YYYYMMDD, 默认今天
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    
    if output_base is None:
        output_base = os.path.join(os.path.dirname(__file__), "..", "data", "raw", date_str)
    output_base = os.path.abspath(output_base)
    ensure_dir(output_base)
    
    print(f"[{datetime.now()}] Starting daily download for {date_str}")
    print(f"Output directory: {output_base}")
    
    log_lines = []
    
    # 1. 下载全市场股票列表
    try:
        print("Downloading stock list...")
        stock_list = fetch_stock_list()
        stock_list.to_csv(os.path.join(output_base, "stock_list.csv"), index=False, encoding="utf-8-sig")
        log_lines.append(f"Stock list: {len(stock_list)} rows")
        print(f"  -> {len(stock_list)} stocks")
    except Exception as e:
        log_lines.append(f"Stock list ERROR: {e}")
        print(f"  -> ERROR: {e}")
    
    # 2. 下载板块列表
    try:
        print("Downloading sector list...")
        sector_list = fetch_sector_list()
        sector_list.to_csv(os.path.join(output_base, "sector_list.csv"), index=False, encoding="utf-8-sig")
        log_lines.append(f"Sector list: {len(sector_list)} rows")
        print(f"  -> {len(sector_list)} sectors")
    except Exception as e:
        log_lines.append(f"Sector list ERROR: {e}")
        print(f"  -> ERROR: {e}")
    
    # 3. 下载北向资金
    try:
        print("Downloading northbound money...")
        start_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
        north = fetch_northbound_money(start_date, end_date)
        north.to_csv(os.path.join(output_base, "northbound.csv"), index=False, encoding="utf-8-sig")
        log_lines.append(f"Northbound: {len(north)} rows")
        print(f"  -> {len(north)} rows")
    except Exception as e:
        log_lines.append(f"Northbound ERROR: {e}")
        print(f"  -> ERROR: {e}")
    
    # 4. 下载涨跌停数据
    try:
        print("Downloading limit up/down data...")
        limit_data = fetch_limit_up_down(end_date)
        limit_data.to_csv(os.path.join(output_base, "limit_up_down.csv"), index=False, encoding="utf-8-sig")
        log_lines.append(f"Limit up/down: {len(limit_data)} rows")
        print(f"  -> {len(limit_data)} rows")
    except Exception as e:
        log_lines.append(f"Limit up/down ERROR: {e}")
        print(f"  -> ERROR: {e}")
    
    # 5. 下载龙虎榜数据
    try:
        print("Downloading dragon tiger data...")
        lhb = fetch_dragon_tiger(end_date)
        lhb.to_csv(os.path.join(output_base, "dragon_tiger.csv"), index=False, encoding="utf-8-sig")
        log_lines.append(f"Dragon tiger: {len(lhb)} rows")
        print(f"  -> {len(lhb)} rows")
    except Exception as e:
        log_lines.append(f"Dragon tiger ERROR: {e}")
        print(f"  -> ERROR: {e}")
    
    # 保存日志
    log_path = os.path.join(output_base, "download.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Download log for {date_str}\n")
        f.write(f"Time: {datetime.now()}\n")
        for line in log_lines:
            f.write(line + "\n")
    
    print(f"\n[{datetime.now()}] Download complete. Log: {log_path}")
    return output_base


def download_stock_history(
    codes: list,
    start_date: str,
    end_date: str,
    output_dir: str = None
):
    """
    批量下载个股历史K线
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "history")
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)
    
    print(f"Downloading history for {len(codes)} stocks...")
    
    for i, code in enumerate(codes):
        try:
            df = fetch_daily_kline(code, start_date, end_date)
            if len(df) > 0:
                df.to_csv(os.path.join(output_dir, f"{code}.csv"), index=False, encoding="utf-8-sig")
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{len(codes)}")
        except Exception as e:
            print(f"  {code} ERROR: {e}")
    
    print(f"History download complete. Saved to {output_dir}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Daily data download")
    parser.add_argument("--date", type=str, default=None, help="YYYYMMDD")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("--history", action="store_true", help="Download history mode")
    parser.add_argument("--codes", type=str, default=None, help="Comma-separated stock codes")
    parser.add_argument("--start", type=str, default="20240101", help="History start date")
    parser.add_argument("--end", type=str, default="20251231", help="History end date")
    
    args = parser.parse_args()
    
    if args.history:
        codes = args.codes.split(",") if args.codes else ["000001", "300750", "600519"]
        download_stock_history(codes, args.start, args.end, args.output)
    else:
        download_daily(args.date, args.output)
