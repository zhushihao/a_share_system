"""
板块计算引擎 - 板块动量排名 + 生命周期判定 + 大小盘风格轮动
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from utils.data_fetcher import fetch_sector_list, fetch_sector_kline, fetch_sector_components, fetch_daily_kline


@dataclass
class SectorResult:
    sector_code: str
    sector_name: str
    score: float                    # 综合得分 0-100
    rank: int                       # 排名
    lifecycle: str                  # 萌芽期/发酵期/高潮期/衰退期
    style: str                      # 大盘价值/中小盘成长/题材概念/周期资源
    
    # 维度得分
    score_20d_return: float         # 20日涨幅 25%
    score_new_high_ratio: float     # 20日新高股占比 20%
    score_volume_change: float      # 成交额变化率 20%
    score_limit_up_quality: float   # 涨停板梯队质量 15%
    score_continuity: float         # 持续性 10%
    score_institutional: float      # 机构参与度 10%
    
    # 原始数据
    return_20d: float
    new_high_ratio: float
    volume_change: float
    limit_up_info: Dict
    continuity_days: int
    institutional_ratio: float
    
    # 3+2法则
    new_high_20d_count: int
    new_high_60d_count: int
    rule_3plus2: bool
    
    # 交易建议
    recommendation: str
    
    def to_dict(self) -> Dict:
        return {
            "sector_code": self.sector_code,
            "sector_name": self.sector_name,
            "score": round(self.score, 2),
            "rank": self.rank,
            "lifecycle": self.lifecycle,
            "style": self.style,
            "score_20d_return": round(self.score_20d_return, 2),
            "score_new_high_ratio": round(self.score_new_high_ratio, 2),
            "score_volume_change": round(self.score_volume_change, 2),
            "score_limit_up_quality": round(self.score_limit_up_quality, 2),
            "score_continuity": round(self.score_continuity, 2),
            "score_institutional": round(self.score_institutional, 2),
            "return_20d": round(self.return_20d, 4),
            "new_high_ratio": round(self.new_high_ratio, 4),
            "volume_change": round(self.volume_change, 4),
            "continuity_days": self.continuity_days,
            "institutional_ratio": round(self.institutional_ratio, 4),
            "new_high_20d_count": self.new_high_20d_count,
            "new_high_60d_count": self.new_high_60d_count,
            "rule_3plus2": self.rule_3plus2,
            "recommendation": self.recommendation,
        }


def _calculate_new_highs(df_daily: pd.DataFrame, window: int = 20) -> int:
    """计算个股创window日新高的次数"""
    if len(df_daily) < window + 1:
        return 0
    count = 0
    for i in range(window, len(df_daily)):
        if df_daily["high"].iloc[i] >= df_daily["high"].iloc[i-window:i].max():
            count += 1
    return count


def calculate_sector_metrics(sector_code: str, sector_name: str, 
                              end_date: str, days: int = 60,
                              stock_data_cache: Optional[Dict[str, pd.DataFrame]] = None,
                              max_components: int = 50) -> Optional[Dict]:
    """
    计算单个板块的所有指标
    end_date: YYYYMMDD
    stock_data_cache: 已加载的个股数据字典（优先复用，避免重复请求）
    max_components: 最多检查多少只成分股（默认50，可减少以提速）
    """
    try:
        # 获取板块K线
        start_date = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
        sector_kline = fetch_sector_kline(sector_code, start_date, end_date, period="daily")
        if len(sector_kline) < 30:
            return None
        
        # 20日涨幅
        if len(sector_kline) >= 20:
            return_20d = (sector_kline["close"].iloc[-1] - sector_kline["close"].iloc[-20]) / sector_kline["close"].iloc[-20]
        else:
            return_20d = 0
        
        # 成交额变化率
        if len(sector_kline) >= 25:
            vol_5d = sector_kline["amount"].iloc[-5:].mean()
            vol_20d = sector_kline["amount"].iloc[-20:].mean()
            volume_change = (vol_5d / vol_20d - 1) if vol_20d > 0 else 0
        else:
            volume_change = 0
        
        # 持续性
        continuity_days = 0
        for i in range(1, len(sector_kline)):
            if sector_kline["close"].iloc[-i] > sector_kline["close"].iloc[-i-1]:
                continuity_days += 1
            else:
                break
        
        # 获取成分股
        components = fetch_sector_components(sector_code)
        if len(components) == 0:
            return None
        
        total_components = len(components)
        
        # 统计创20日新高和60日新高的成分股
        new_high_20d = 0
        new_high_60d = 0
        checked = 0
        
        for _, row in components.iterrows():
            if checked >= max_components:
                break
            checked += 1
            code = row["code"]
            try:
                # 优先复用已缓存数据
                if stock_data_cache and code in stock_data_cache:
                    stock_df = stock_data_cache[code]
                else:
                    stock_df = fetch_daily_kline(code, start_date, end_date)
                
                if len(stock_df) >= 20:
                    if stock_df["high"].iloc[-1] >= stock_df["high"].iloc[-20:].max():
                        new_high_20d += 1
                if len(stock_df) >= 60:
                    if stock_df["high"].iloc[-1] >= stock_df["high"].iloc[-60:].max():
                        new_high_60d += 1
            except Exception:
                continue
        
        new_high_ratio = new_high_20d / total_components if total_components > 0 else 0
        
        # 3+2法则
        rule_3plus2 = (new_high_20d >= 3) and (new_high_60d >= 2)
        
        # 涨停板梯队质量（简化版）
        limit_up_info = {
            "limit_up_count": 0,
            "max_height": 0,
        }
        
        # 机构参与度（简化版）
        institutional_ratio = 0.0
        
        return {
            "sector_code": sector_code,
            "sector_name": sector_name,
            "return_20d": return_20d,
            "volume_change": volume_change,
            "continuity_days": continuity_days,
            "new_high_20d": new_high_20d,
            "new_high_60d": new_high_60d,
            "total_components": total_components,
            "new_high_ratio": new_high_ratio,
            "rule_3plus2": rule_3plus2,
            "limit_up_info": limit_up_info,
            "institutional_ratio": institutional_ratio,
            "sector_kline": sector_kline,
        }
    except Exception as e:
        return None


def calculate_sector_ranking(end_date: str, top_n: int = 50, 
                             max_sectors: Optional[int] = None,
                             stock_data_cache: Optional[Dict[str, pd.DataFrame]] = None,
                             max_components: int = 50) -> List[SectorResult]:
    """
    计算全市场板块排名
    max_sectors: 最多扫描多少个板块（None=全部）
    stock_data_cache: 已加载的个股数据（复用）
    max_components: 每个板块最多检查多少只成分股
    """
    sectors = fetch_sector_list()
    if len(sectors) == 0:
        return []
    
    # 限制扫描板块数量
    if max_sectors and len(sectors) > max_sectors:
        sectors = sectors.head(max_sectors)
    
    results = []
    for _, row in sectors.iterrows():
        sector_code = row["sector_code"]
        sector_name = row["sector_name"]
        
        metrics = calculate_sector_metrics(
            sector_code, sector_name, end_date,
            stock_data_cache=stock_data_cache,
            max_components=max_components
        )
        if metrics is None:
            continue
        
        # ... 后续不变
        score_20d_return = min(max(metrics["return_20d"] * 100, -20), 20) * 2.5 + 50
        score_new_high = min(metrics["new_high_ratio"] * 500, 100)
        score_volume = min(max(metrics["volume_change"] * 100, -50), 50) * 1 + 50
        score_continuity = min(metrics["continuity_days"] * 10, 100)
        score_limit_up = 0
        score_institutional = metrics["institutional_ratio"] * 100
        
        score = (
            score_20d_return * 0.25 +
            score_new_high * 0.20 +
            score_volume * 0.20 +
            score_limit_up * 0.15 +
            score_continuity * 0.10 +
            score_institutional * 0.10
        )
        
        lifecycle = "萌芽期"
        if score >= 60 and metrics["rule_3plus2"]:
            lifecycle = "发酵期"
        elif score >= 70 and metrics["continuity_days"] >= 3:
            lifecycle = "高潮期"
        elif score < 30 or metrics["volume_change"] < -0.3:
            lifecycle = "衰退期"
        
        if "银行" in sector_name or "保险" in sector_name or "证券" in sector_name or "白酒" in sector_name:
            style = "大盘价值"
        elif "科技" in sector_name or "电子" in sector_name or "软件" in sector_name or "通信" in sector_name:
            style = "中小盘成长"
        elif "有色" in sector_name or "煤炭" in sector_name or "化工" in sector_name or "钢铁" in sector_name:
            style = "周期资源"
        else:
            style = "题材概念"
        
        if lifecycle == "发酵期":
            recommendation = "趋势池候选"
        elif lifecycle == "高潮期":
            recommendation = "持仓窗口，不新开仓"
        elif lifecycle == "衰退期":
            recommendation = "风险池"
        else:
            recommendation = "观察池"
        
        results.append(SectorResult(
            sector_code=sector_code,
            sector_name=sector_name,
            score=score,
            rank=0,
            lifecycle=lifecycle,
            style=style,
            score_20d_return=score_20d_return,
            score_new_high_ratio=score_new_high,
            score_volume_change=score_volume,
            score_limit_up_quality=score_limit_up,
            score_continuity=score_continuity,
            score_institutional=score_institutional,
            return_20d=metrics["return_20d"],
            new_high_ratio=metrics["new_high_ratio"],
            volume_change=metrics["volume_change"],
            limit_up_info=metrics["limit_up_info"],
            continuity_days=metrics["continuity_days"],
            institutional_ratio=metrics["institutional_ratio"],
            new_high_20d_count=metrics["new_high_20d"],
            new_high_60d_count=metrics["new_high_60d"],
            rule_3plus2=metrics["rule_3plus2"],
            recommendation=recommendation,
        ))
    
    results.sort(key=lambda x: x.score, reverse=True)
    for i, r in enumerate(results):
        r.rank = i + 1
    
    return results[:top_n]


def calculate_style_rotation(index_data: Dict[str, pd.DataFrame]) -> Dict:
    """
    大小盘风格轮动判定
    index_data: {"中证1000": DataFrame, "沪深300": DataFrame}
    """
    if "中证1000" not in index_data or "沪深300" not in index_data:
        return {"style": "未知", "ratio": 0, "ratio_ma20_trend": "平"}
    
    zz1000 = index_data["中证1000"]
    hs300 = index_data["沪深300"]
    
    if len(zz1000) < 20 or len(hs300) < 20:
        return {"style": "未知", "ratio": 0, "ratio_ma20_trend": "平"}
    
    # 计算比值
    ratio = zz1000["close"] / hs300["close"]
    ratio_ma20 = ratio.rolling(20).mean()
    
    current_ratio = ratio.iloc[-1]
    current_ma20 = ratio_ma20.iloc[-1]
    prev_ma20 = ratio_ma20.iloc[-2] if len(ratio_ma20) >= 2 else current_ma20
    
    if current_ma20 > prev_ma20:
        trend = "上升"
        style = "小盘占优"
    elif current_ma20 < prev_ma20:
        trend = "下降"
        style = "大盘占优"
    else:
        trend = "平"
        style = "均衡"
    
    return {
        "style": style,
        "ratio": round(current_ratio, 4),
        "ratio_ma20_trend": trend,
        "ratio_ma20": round(current_ma20, 4),
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system")
    
    print("Testing sector calculation...")
    results = calculate_sector_ranking("20250619", top_n=10)
    print(f"\nTop 10 sectors:")
    for r in results[:10]:
        print(f"  {r.rank}. {r.sector_name}: score={r.score:.1f}, lifecycle={r.lifecycle}, "
              f"20d_return={r.return_20d*100:.1f}%, 3+2={r.rule_3plus2}")
