# -*- coding: utf-8 -*-
"""
Settings API - 系统设置接口

功能：
1. 获取所有设置
2. 获取单个设置
3. 更新设置
4. 删除设置
5. 重置为默认值
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from backend.models.database import (
    DATABASE_PATH,
    init_db,
    set_setting,
    get_setting,
    get_all_settings,
    delete_setting,
)

router = APIRouter()


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────

class SettingUpdateRequest(BaseModel):
    """设置更新请求"""
    value: Any = Field(..., description="设置值")


class SettingsBatchRequest(BaseModel):
    """批量设置请求"""
    settings: Dict[str, Any] = Field(..., description="设置键值对")


# 默认设置
DEFAULT_SETTINGS = {
    "tdx_dir": "D:/TDX",
    "theme": "light",
    "default_adjust": "qfq",
    "default_period": "daily",
    "default_initial_cash": 100000.0,
    "default_commission_rate": 0.0003,
    "default_slippage": 0.001,
    "ai_api_key": "",
    "ai_model": "kimi",
    "ai_enabled": False,
    "offline_mode": False,
    "language": "zh-CN",
}


# ───────────────────────────────────────────────
# Helper
# ───────────────────────────────────────────────

async def _get_db_conn():
    """获取数据库连接"""
    return await init_db(DATABASE_PATH)


def _validate_setting_key(key: str) -> None:
    """校验设置键名，拒绝与静态路由冲突的键名"""
    if key in ("batch", "reset"):
        raise HTTPException(status_code=404, detail=f"Setting key not found: {key}")


def _mask_api_key(value: str) -> str:
    """对 API Key 做掩码，仅保留前 4 位和后 4 位"""
    if not value or len(value) <= 8:
        return ""
    return value[:4] + "****" + value[-4:]



# ───────────────────────────────────────────────
# API Routes
# ───────────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    """
    获取所有系统设置

    返回已保存的设置，未设置的返回默认值。
    """
    conn = await _get_db_conn()
    try:
        saved = await get_all_settings(conn)
        
        # 合并默认值和已保存值
        result = DEFAULT_SETTINGS.copy()
        result.update(saved)
        
        # 对敏感字段脱敏后再返回
        result["ai_api_key"] = _mask_api_key(result.get("ai_api_key", ""))

        return {
            "status": "ok",
            "settings": result,
            "default_keys": list(DEFAULT_SETTINGS.keys()),
        }
    finally:
        await conn.close()


@router.post("/settings/batch")
async def update_settings_batch(request: SettingsBatchRequest):
    """
    批量更新设置
    """
    conn = await _get_db_conn()
    try:
        for key, value in request.settings.items():
            await set_setting(conn, key, value)
        return {
            "status": "ok",
            "updated": list(request.settings.keys()),
        }
    finally:
        await conn.close()


@router.post("/settings/reset")
async def reset_settings():
    """
    重置所有设置为默认值
    """
    conn = await _get_db_conn()
    try:
        # 删除所有设置
        for key in DEFAULT_SETTINGS.keys():
            await delete_setting(conn, key)
        
        return {
            "status": "ok",
            "message": "All settings reset to defaults",
            "defaults": DEFAULT_SETTINGS,
        }
    finally:
        await conn.close()


@router.get("/settings/{key}")
async def get_single_setting(key: str):
    """
    获取单个设置值
    """
    _validate_setting_key(key)

    conn = await _get_db_conn()
    try:
        value = await get_setting(conn, key, default=DEFAULT_SETTINGS.get(key))
        return {
            "status": "ok",
            "key": key,
            "value": value,
        }
    finally:
        await conn.close()


@router.put("/settings/{key}")
async def update_setting(key: str, request: SettingUpdateRequest):
    """
    更新单个设置
    """
    _validate_setting_key(key)

    conn = await _get_db_conn()
    try:
        await set_setting(conn, key, request.value)
        return {
            "status": "ok",
            "key": key,
            "value": request.value,
        }
    finally:
        await conn.close()


@router.delete("/settings/{key}")
async def remove_setting(key: str):
    """
    删除设置（恢复为默认值）
    """
    _validate_setting_key(key)

    conn = await _get_db_conn()
    try:
        ok = await delete_setting(conn, key)
        if not ok:
            return {
                "status": "ok",
                "key": key,
                "message": "Setting not found, nothing to delete",
            }
        return {
            "status": "ok",
            "key": key,
            "message": "Setting deleted, will use default on next read",
        }
    finally:
        await conn.close()
