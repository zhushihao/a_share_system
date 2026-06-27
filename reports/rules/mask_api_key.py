# -*- coding: utf-8 -*-
"""
API Key 脱敏规则

GET /settings 返回前对 ai_api_key 做掩码处理，避免泄露。
"""

from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class MaskApiKeyRule(Rule):
    name = "mask_api_key"
    description = "GET /settings 返回前掩码 ai_api_key"
    keywords = ["api key", "api_key", "泄露", "ai_api_key", "凭证"]
    risk = "low"
    requires_restart = True

    def detect(self) -> Tuple[bool, str]:
        settings_file = PROJECT_ROOT / "backend" / "api" / "settings.py"
        text = settings_file.read_text(encoding="utf-8")

        # 如果已经存在脱敏函数，则认为已修复
        if "def _mask_api_key" in text:
            return False, "已存在 API Key 脱敏逻辑"

        # 只要设置项里包含 ai_api_key 且没有脱敏函数，就应用
        if '"ai_api_key"' in text:
            return True, "GET /settings 包含 ai_api_key 但缺少脱敏逻辑"
        return False, "未检测到 ai_api_key 设置项"

    def apply(self) -> Tuple[bool, str]:
        settings_file = PROJECT_ROOT / "backend" / "api" / "settings.py"
        self.backup("backend/api/settings.py")
        text = settings_file.read_text(encoding="utf-8")

        helper = '''\n\ndef _mask_api_key(value: str) -> str:\n    """对 API Key 做掩码，仅保留前 4 位和后 4 位"""\n    if not value or len(value) <= 8:\n        return ""\n    return value[:4] + "****" + value[-4:]\n\n'''

        # 在 _validate_setting_key 函数后插入 helper
        anchor = 'def _validate_setting_key(key: str) -> None:\n    """校验设置键名，拒绝与静态路由冲突的键名"""\n    if key in ("batch", "reset"):\n        raise HTTPException(status_code=404, detail=f"Setting key not found: {key}")\n'
        if helper.strip() not in text:
            text = text.replace(anchor, anchor + helper)

        # 在 return 前增加脱敏
        old_return = '''        return {
            "status": "ok",
            "settings": result,
            "default_keys": list(DEFAULT_SETTINGS.keys()),
        }'''
        new_return = '''        # 对敏感字段脱敏后再返回
        result["ai_api_key"] = _mask_api_key(result.get("ai_api_key", ""))

        return {
            "status": "ok",
            "settings": result,
            "default_keys": list(DEFAULT_SETTINGS.keys()),
        }'''
        text = text.replace(old_return, new_return)

        settings_file.write_text(text, encoding="utf-8")
        return True, "已在 GET /settings 中对 ai_api_key 做掩码"

    def verify(self) -> Tuple[bool, str]:
        settings_file = PROJECT_ROOT / "backend" / "api" / "settings.py"
        text = settings_file.read_text(encoding="utf-8")
        if "def _mask_api_key" not in text:
            return False, "未找到 _mask_api_key 函数"
        if 'result["ai_api_key"] = _mask_api_key' not in text:
            return False, "返回前未调用脱敏"
        return True, "API Key 脱敏逻辑已生效"
