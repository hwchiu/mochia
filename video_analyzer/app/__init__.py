from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.routers import videos, analysis, batch


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

    # 靜態檔案
    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 頁面路由（HTML）
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    templates_dir = Path(__file__).parent.parent / "templates"

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        from fastapi.templating import Jinja2Templates
        tmpl = Jinja2Templates(directory=str(templates_dir))
        return tmpl.TemplateResponse("index.html", {"request": request})

    @app.get("/video/{video_id}", response_class=HTMLResponse)
    async def video_detail(request: Request, video_id: str):
        from fastapi.templating import Jinja2Templates
        tmpl = Jinja2Templates(directory=str(templates_dir))
        return tmpl.TemplateResponse("detail.html", {"request": request, "video_id": video_id})

    return app


app = create_app()

