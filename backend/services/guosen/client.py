# -*- coding: utf-8 -*-
"""
国信证券 xxskills 统一客户端。

设计原则：
1. 每个 skill 通过独立 Python 脚本调用，避免依赖冲突。
2. 自动设置对应的环境变量，调用方无需关心内部差异。
3. 统一解析 stdout 的 JSON 结果；ETF 筛选等落盘技能单独处理。
"""

import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class GuosenSkillError(Exception):
    """国信 skill 调用异常"""


def _sanitize_message(text: str) -> str:
    """清除异常/日志中的 apiKey/token 等敏感信息"""
    if not text:
        return text
    # 清除 URL 查询参数中的 apiKey
    text = re.sub(r"apiKey=[^\s&\"']+", "apiKey=***", text, flags=re.IGNORECASE)
    # 清除 V2V- 开头的 key
    text = re.sub(r"V2V-[A-Za-z0-9_-]{50,}", "V2V-***", text)
    return text


class GuosenClient:
    """国信证券 xxskills 统一客户端"""

    def __init__(self, skills_root: Optional[str] = None):
        if skills_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            skills_root = project_root / "tools" / "guosen-skills"
        self.skills_root = Path(skills_root)
        self._validate_skills()

    def _validate_skills(self) -> None:
        required = [
            "gs-stock-market-query",
            "gs-stock-financial-query",
            "gs-economy-query",
            "gs-smart-stock-picking",
            "gs-fund-compare",
            "gs-etf-filter",
        ]
        missing = [name for name in required if not (self.skills_root / name).exists()]
        if missing:
            raise GuosenSkillError(f"缺少 skill 目录: {missing}")

    @staticmethod
    def _env_for(skill_name: str) -> Dict[str, str]:
        """构造指定 skill 需要的环境变量副本"""
        env = os.environ.copy()
        if skill_name == "gs-etf-filter":
            key = os.environ.get("COZE_GUOSEN_API_KEY_7627056463827140634") or os.environ.get("GS_API_KEY")
            if key:
                env["COZE_GUOSEN_API_KEY_7627056463827140634"] = key
        else:
            key = os.environ.get("GS_API_KEY")
            if key:
                env["GS_API_KEY"] = key
        return env

    def _run_script(
        self,
        skill_name: str,
        script_name: str,
        args: List[str],
        timeout: int = 60,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Dict[str, Any]:
        script_path = self.skills_root / skill_name / "scripts" / script_name
        if not script_path.exists():
            raise GuosenSkillError(f"脚本不存在: {script_path}")

        cmd = [sys.executable, str(script_path), *args]
        env = self._env_for(skill_name)
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="ignore",
                )
            except subprocess.TimeoutExpired as e:
                last_error = GuosenSkillError(f"skill {skill_name} 调用超时")
            except Exception as e:
                last_error = GuosenSkillError(f"skill {skill_name} 调用失败: {e}")
            else:
                if result.returncode == 0:
                    text = result.stdout.strip()
                    if text:
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError as e:
                            safe_preview = _sanitize_message(text[:200])
                            raise GuosenSkillError(
                                f"skill {skill_name} 返回非 JSON 输出: {safe_preview}"
                            ) from e
                    last_error = GuosenSkillError(f"skill {skill_name} 返回空输出")
                else:
                    last_error = GuosenSkillError(
                        f"skill {skill_name} 返回非零退出码 {result.returncode}"
                    )

            # 非最后一次尝试则退避重试
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)

        raise last_error or GuosenSkillError(f"skill {skill_name} 调用失败，已重试 {max_retries} 次")

    # ───────────────────────────────────────────────
    # 行情数据
    # ───────────────────────────────────────────────

    def query_single_hq(self, code: str, set_code: int = 0, target: int = 0) -> Dict[str, Any]:
        """查询单个证券实时行情"""
        return self._run_script(
            "gs-stock-market-query",
            "get_data.py",
            ["single_hq", "--code", code, "--set_code", str(set_code), "--target", str(target)],
        )

    def query_comb_hq(self, codes: List[str], set_codes: List[int], target: int = 0) -> Dict[str, Any]:
        """查询多只股票实时行情"""
        if len(codes) != len(set_codes):
            raise GuosenSkillError("codes 与 set_codes 长度必须一致")
        return self._run_script(
            "gs-stock-market-query",
            "get_data.py",
            [
                "comb_hq",
                "--codes", ",".join(codes),
                "--set_codes", ",".join(str(s) for s in set_codes),
                "--target", str(target),
            ],
        )

    def query_fund_flow(self, code: str, set_code: int, period: int = 10) -> Dict[str, Any]:
        """查询个股资金流向"""
        return self._run_script(
            "gs-stock-market-query",
            "get_data.py",
            ["fund_flow", "--code", code, "--set_code", str(set_code), "--period", str(period)],
        )

    def query_multi_hq(self, set_domain: int, want_num: int = 10, sort_type: int = 1, target: int = 0) -> Dict[str, Any]:
        """查询涨幅/跌幅排名"""
        return self._run_script(
            "gs-stock-market-query",
            "get_data.py",
            [
                "multi_hq",
                "--set_domain", str(set_domain),
                "--want_num", str(want_num),
                "--sort_type", str(sort_type),
                "--target", str(target),
            ],
        )

    def query_related_comb_hq(self, code: str, set_code: int, target: int = 0) -> Dict[str, Any]:
        """查询个股关联板块"""
        return self._run_script(
            "gs-stock-market-query",
            "get_data.py",
            ["related_comb", "--code", code, "--set_code", str(set_code), "--target", str(target)],
        )

    def query_past_hq(self, code: str, set_code: int, want_nums: int = 20, mas: Optional[str] = None) -> Dict[str, Any]:
        """查询近 n 个交易日日行情"""
        args = ["past_hq", "--code", code, "--set_code", str(set_code), "--want_nums", str(want_nums)]
        if mas:
            args += ["--mas", mas]
        return self._run_script("gs-stock-market-query", "get_data.py", args)

    # ───────────────────────────────────────────────
    # 财务数据
    # ───────────────────────────────────────────────

    def query_financial(
        self,
        report_type: str,
        code: str,
        market: str = "SH",
        report_period: str = "Q0",
        report_year: Optional[str] = None,
        count: int = 1,
    ) -> Dict[str, Any]:
        """
        查询 A 股财务报表。
        report_type: a_balance / a_income / a_cashflow / hk_balance / hk_income / hk_cashflow
        """
        args = [
            report_type,
            "--code", code,
            "--market", market,
            "--report_type", report_period,
            "--count", str(count),
        ]
        if report_year:
            args += ["--report_year", report_year]
        return self._run_script("gs-stock-financial-query", "get_data.py", args)

    # ───────────────────────────────────────────────
    # 宏观经济
    # ───────────────────────────────────────────────

    def query_economy(self, query_text: str) -> Dict[str, Any]:
        """自然语言查询宏观经济数据"""
        return self._run_script("gs-economy-query", "get_data.py", [query_text])

    # ───────────────────────────────────────────────
    # 智能选股 / 基金对比 / ETF 筛选
    # ───────────────────────────────────────────────
    # TODO: 这三个 skill 的脚本支持参数较灵活，当前先不暴露开放 *args 透传接口，
    # 后续按具体业务场景补充显式、带校验的 typed 方法，避免命令注入与路径遍历。
