from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.routers import videos, analysis, batch, labels


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="本地影片分析系統 - 支援批量分析與背景 Worker",
    )

    @app.on_event("startup")
    async def startup():
        init_db()

    # API Routers
    app.include_router(videos.router)
    app.include_router(analysis.router)
    app.include_router(batch.router)
    app.include_router(labels.router)

    # 靜態檔案
    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 頁面路由（HTML）
    templates_dir = Path(__file__).parent.parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/video/{video_id}", response_class=HTMLResponse)
    async def video_detail(request: Request, video_id: str):
        return templates.TemplateResponse("detail.html", {"request": request, "video_id": video_id})

    return app


app = create_app()

