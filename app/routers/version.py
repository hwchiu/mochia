import json
from datetime import datetime

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["version"])


@router.get("/api/version")
def get_version() -> dict:
    """回傳目前執行中的 image 版本資訊。
    APP_VERSION 與 BUILD_DATE 由 Docker build-arg (GIT_SHA / BUILD_DATE) 注入，
    每次 CI 發佈新 image 時自動更新。
    """
    return {
        "version": settings.APP_VERSION,
        "build_date": settings.BUILD_DATE,
        "app_name": settings.APP_NAME,
    }


@router.get("/api/version/worker-health")
def get_worker_health() -> dict:
    """檢查 Worker 是否存活（透過心跳檔案）"""
    heartbeat_path = settings.DATA_DIR / "worker_heartbeat.json"

    if not heartbeat_path.exists():
        return {
            "alive": False,
            "reason": "心跳檔案不存在（Worker 可能未啟動）",
            "last_heartbeat": None,
            "elapsed_seconds": None,
        }

    try:
        data = json.loads(heartbeat_path.read_text())
        last_ts = datetime.fromisoformat(data["timestamp"])
        elapsed = (datetime.utcnow() - last_ts).total_seconds()
        stale_threshold = settings.WORKER_POLL_INTERVAL * 3  # 3 個 poll 間隔視為失效
        alive = elapsed < stale_threshold
        return {
            "alive": alive,
            "reason": None
            if alive
            else f"心跳已超過 {int(elapsed)}s 無更新（閾值 {stale_threshold}s）",
            "last_heartbeat": data["timestamp"],
            "elapsed_seconds": round(elapsed, 1),
            "pid": data.get("pid"),
        }
    except Exception as e:
        return {
            "alive": False,
            "reason": f"無法讀取心跳檔案: {e}",
            "last_heartbeat": None,
            "elapsed_seconds": None,
        }
