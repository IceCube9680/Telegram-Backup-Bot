"""Disk space health monitoring utility."""

import asyncio
from pathlib import Path
import shutil
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings


class DiskHealthStatus(BaseModel):
    """Disk space storage metrics and health evaluation."""

    storage_path: str = Field(..., description="Target storage filesystem directory")
    total_bytes: int = Field(..., description="Total storage capacity in bytes")
    used_bytes: int = Field(..., description="Used storage capacity in bytes")
    free_bytes: int = Field(..., description="Available free storage in bytes")
    usage_percent: float = Field(..., description="Current disk usage percentage")
    status: str = Field(..., description="Health status: healthy, warning, or critical")
    warning_threshold_pct: float = Field(..., description="Configured warning threshold")
    critical_threshold_pct: float = Field(..., description="Configured critical threshold")


async def get_disk_health(settings: Optional[Settings] = None) -> DiskHealthStatus:
    """Evaluate filesystem storage health on configured STORAGE_PATH."""

    cfg = settings or get_settings()
    path = Path(cfg.STORAGE_PATH).resolve()
    await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)

    total_b, used_b, free_b = await asyncio.to_thread(shutil.disk_usage, path)
    usage_pct = round((used_b / total_b) * 100.0, 2) if total_b > 0 else 0.0

    if usage_pct >= cfg.DISK_CRITICAL_THRESHOLD_PCT:
        health_state = "critical"
    elif usage_pct >= cfg.DISK_WARNING_THRESHOLD_PCT:
        health_state = "warning"
    else:
        health_state = "healthy"

    return DiskHealthStatus(
        storage_path=str(path),
        total_bytes=total_b,
        used_bytes=used_b,
        free_bytes=free_b,
        usage_percent=usage_pct,
        status=health_state,
        warning_threshold_pct=cfg.DISK_WARNING_THRESHOLD_PCT,
        critical_threshold_pct=cfg.DISK_CRITICAL_THRESHOLD_PCT,
    )
