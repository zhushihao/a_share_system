# -*- coding: utf-8 -*-
"""
Data Platform API - 数据中台管理接口

功能：
1. 数据质量自检报告
2. 缓存统计
3. 强制刷新数据
4. 数据平台健康状态
"""

from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter

from backend.services.data_platform import get_data_platform_service

router = APIRouter()


@router.get("/data-platform/status")
async def data_platform_status():
    """数据中台状态总览"""
    platform = get_data_platform_service()
    stats = platform.get_stats()
    return {
        "status": "ok",
        **stats,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/data-platform/self-check")
async def data_platform_self_check():
    """运行数据质量自检并返回报告"""
    platform = get_data_platform_service()
    report = platform.run_self_check()
    return report


@router.get("/data-platform/cache/stats")
async def data_platform_cache_stats():
    """缓存统计"""
    platform = get_data_platform_service()
    stats = platform.get_stats()
    return {
        "cache_stats": stats.get("cache_stats", {}),
        "hit_rate": stats.get("hit_rate", 0),
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/data-platform/refresh")
async def data_platform_refresh():
    """强制刷新所有核心数据缓存"""
    platform = get_data_platform_service()
    platform.refresh_all()
    return {
        "status": "refreshed",
        "message": "所有核心数据已强制刷新",
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/data-platform/clear-cache")
async def data_platform_clear_cache():
    """清空所有缓存"""
    platform = get_data_platform_service()
    platform.clear_cache()
    return {
        "status": "cleared",
        "message": "所有缓存已清空",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/data-platform/health")
async def data_platform_health():
    """数据平台健康检查"""
    platform = get_data_platform_service()
    report = platform.run_self_check()
    quality = report.get("quality_checks", {})
    total_passed = sum(v.get("passed", 0) for v in quality.values())
    total_failed = sum(v.get("failed", 0) for v in quality.values())
    total = total_passed + total_failed
    health_score = total_passed / max(total, 1)
    
    return {
        "status": "healthy" if health_score >= 0.95 else "degraded" if health_score >= 0.80 else "unhealthy",
        "health_score": round(health_score, 4),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "data_sources": report.get("data_sources", {}),
        "timestamp": datetime.now().isoformat(),
    }
