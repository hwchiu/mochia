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
