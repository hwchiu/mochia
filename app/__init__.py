from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.routers import analysis, batch, labels, notes, review, search, stats, videos


def create_app() -> FastAPI:
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="本地影片分析系統 - 支援批量分析與背景 Worker",
        lifespan=lifespan,
    )

    # API Routers
    app.include_router(videos.router)
    app.include_router(analysis.router)
    app.include_router(batch.router)
    app.include_router(labels.router)
    app.include_router(search.router)
    app.include_router(review.router)
    app.include_router(notes.router)
    app.include_router(stats.router)

    # 靜態檔案
    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 頁面路由（HTML）
    templates_dir = Path(__file__).parent.parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {})

    @app.get("/video/{video_id}", response_class=HTMLResponse)
    async def video_detail(request: Request, video_id: str):
        return templates.TemplateResponse(request, "detail.html", {"video_id": video_id})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
