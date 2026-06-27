# -*- coding: utf-8 -*-
"""
CORS 收紧规则

将 allow_origins=["*"] + allow_credentials=True 改为仅允许本地前端地址。
"""

from pathlib import Path
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class CORSRule(Rule):
    name = "cors_lockdown"
    description = "将 CORS 通配符改为本地前端地址"
    keywords = ["cors", "allow_origins", "allow_credentials", "跨站"]
    risk = "low"
    requires_restart = True

    def detect(self) -> Tuple[bool, str]:
        main_file = PROJECT_ROOT / "backend" / "main.py"
        config_file = PROJECT_ROOT / "backend" / "config.py"
        main_text = main_file.read_text(encoding="utf-8")
        config_text = config_file.read_text(encoding="utf-8")

        has_wildcard_main = 'allow_origins=["*"]' in main_text or "allow_origins=['*']" in main_text
        has_wildcard_config = 'CORS_ORIGINS: list = ["*"]' in config_text or "CORS_ORIGINS: list = ['*']" in config_text

        if has_wildcard_main or has_wildcard_config:
            return True, "检测到 CORS 通配符配置"
        return False, "CORS 已收紧"

    def apply(self) -> Tuple[bool, str]:
        config_file = PROJECT_ROOT / "backend" / "config.py"
        main_file = PROJECT_ROOT / "backend" / "main.py"

        self.backup("backend/config.py")
        self.backup("backend/main.py")

        # 1. 修改 config.py
        config_text = config_file.read_text(encoding="utf-8")
        new_origins = '["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5889"]'
        config_text = config_text.replace(
            'CORS_ORIGINS: list = ["*"]',
            f'CORS_ORIGINS: list = {new_origins}',
        )
        config_text = config_text.replace(
            "CORS_ORIGINS: list = ['*']",
            f'CORS_ORIGINS: list = {new_origins}',
        )
        config_file.write_text(config_text, encoding="utf-8")

        # 2. 修改 main.py 使用 settings.CORS_ORIGINS
        main_text = main_file.read_text(encoding="utf-8")
        main_text = main_text.replace(
            'allow_origins=["*"]',
            'allow_origins=settings.CORS_ORIGINS',
        )
        main_text = main_text.replace(
            "allow_origins=['*']",
            'allow_origins=settings.CORS_ORIGINS',
        )
        main_file.write_text(main_text, encoding="utf-8")

        return True, "CORS 已改为本地前端地址并接入 settings.CORS_ORIGINS"

    def verify(self) -> Tuple[bool, str]:
        config_file = PROJECT_ROOT / "backend" / "config.py"
        main_file = PROJECT_ROOT / "backend" / "main.py"
        config_text = config_file.read_text(encoding="utf-8")
        main_text = main_file.read_text(encoding="utf-8")

        if 'CORS_ORIGINS: list = ["*"]' in config_text or "CORS_ORIGINS: list = ['*']" in config_text:
            return False, "config.py 仍包含通配符"
        if 'allow_origins=["*"]' in main_text or "allow_origins=['*']" in main_text:
            return False, "main.py 仍包含硬编码通配符"
        if 'allow_origins=settings.CORS_ORIGINS' not in main_text:
            return False, "main.py 未接入 settings.CORS_ORIGINS"
        return True, "CORS 配置检查通过"
