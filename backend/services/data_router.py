# -*- coding: utf-8 -*-
"""
统一数据源路由。

目标：把 Guosen xxskills 作为首选数据源，mootdx/akshare/cache 作为降级，
集中处理 fallback、字段映射、缓存和错误统计。

当前阶段：骨架，待按 docs/GUOSEN_SKILLS_INTEGRATION.md 逐步填充。
"""

from typing import Any, Dict, List, Optional

import pandas as pd

from backend.services.guosen.client import GuosenClient
from backend.services.data_provider import get_data_provider_service


class DataSourceRouter:
    """
    数据源路由：Guosen > mootdx > akshare > cache
    """

    def __init__(self):
        self._guosen = GuosenClient()
        self._provider = get_data_provider_service()

    def get_quotes(self, symbols: List[str]) -> List[Any]:
        """
        获取多只股票实时行情。
        TODO: 先调 Guosen query_comb_hq，失败回退 mootdx realtime。
        """
        raise NotImplementedError

    def get_kline(
        self,
        symbol: str,
        period: str = "daily",
        days: int = 20,
    ) -> Optional[pd.DataFrame]:
        """
        获取 K 线数据。
        TODO: 近期数据用 Guosen query_past_hq，历史数据用 TDX 离线文件合并。
        """
        raise NotImplementedError

    def get_financial(self, symbol: str) -> Dict[str, Any]:
        """
        获取 F10 财务数据。
        TODO: 用 Guosen query_financial 获取最新 balance/income/cashflow。
        """
        raise NotImplementedError

    def get_sector_components(self, sector_code: str) -> List[str]:
        """
        获取板块成分股代码列表。
        TODO: 用 Guosen query_related_comb_hq 获取真实成分股。
        """
        raise NotImplementedError

    def get_market_sentiment(self) -> Dict[str, Any]:
        """
        获取市场情绪（涨跌家数等）。
        TODO: 用 Guosen query_multi_hq 涨跌排名计算。
        """
        raise NotImplementedError

    def get_hotspots(self, want_num: int = 10) -> List[Dict[str, Any]]:
        """
        获取热点板块。
        TODO: 用 Guosen query_multi_hq 行业/概念排名 + related_comb 成分股。
        """
        raise NotImplementedError
