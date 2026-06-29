"""
国信证券 xxskills 统一调用封装。

环境变量（按 skill 区分）：
- 行情 / 财务 / 宏观经济 / 智能选股 / 基金对比：GS_API_KEY
- ETF 筛选：COZE_GUOSEN_API_KEY_7627056463827140634

用法：
    from backend.services.guosen import GuosenClient
    client = GuosenClient()
    hq = client.query_single_hq("000001", set_code=0)
"""

from .client import GuosenClient, GuosenSkillError

__all__ = ["GuosenClient", "GuosenSkillError"]
