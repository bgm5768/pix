from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.routes.api import router as api_router
from app.services.comfy_client import ComfyClient
from app.services.comfy_launcher import ComfyLauncher
from app.services.errors import PixelForgeError
from app.services.job_manager import JobManager
from app.services.model_downloads import ModelDownloadManager
from app.services.translator import Translator

logger = logging.getLogger("pixelforge")


def _configure_logging() -> None:
    settings = get_settings()
    settings.ensure_directories()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(stream)
    log_path = settings.logs_dir / "backend.log"
    already = any(
        isinstance(handler, logging.FileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_path
        for handler in root.handlers
    )
    if not already:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(file_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    _configure_logging()

    comfy = ComfyClient(settings.comfyui)
    launcher = ComfyLauncher(settings)
    translator = Translator(settings.translation, settings.translation_model_dir)
    jobs = JobManager(settings, comfy, launcher, translator)
    downloads = ModelDownloadManager(settings, comfy)

    app.state.settings = settings
    app.state.comfy = comfy
    app.state.launcher = launcher
    app.state.translator = translator
    app.state.jobs = jobs
    app.state.downloads = downloads

    await jobs.start()
    logger.info("PixelForge Local backend starting (ComfyUI: %s)", settings.comfyui.normalized_url)

    async def bootstrap_comfyui() -> None:
        try:
            await launcher.ensure_running(comfy)
            logger.info("ComfyUI is ready at %s", settings.comfyui.normalized_url)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = getattr(exc, "message", str(exc))
            logger.warning("ComfyUI auto-start did not complete: %s", message)

    async def open_browser_later() -> None:
        if not settings.app.open_browser or os.environ.get("PIXELFORGE_NO_BROWSER") == "1":
            return
        await asyncio.sleep(1.8)
        try:
            # 0.0.0.0 is a bind address, not a browsable host.
            host = settings.app.host
            if host in {"0.0.0.0", "::", ""}:
                host = "127.0.0.1"
            webbrowser.open(f"http://{host}:{settings.app.port}")
        except Exception:
            logger.debug("Could not open the browser automatically", exc_info=True)

    bootstrap_task = asyncio.create_task(bootstrap_comfyui(), name="comfyui-bootstrap")
    browser_task = asyncio.create_task(open_browser_later(), name="open-browser")
    try:
        yield
    finally:
        for task in (bootstrap_task, browser_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await jobs.stop()
        await downloads.close()
        await comfy.close()
        launcher.shutdown()
        logger.info("PixelForge Local backend stopped")


app = FastAPI(
    title="PixelForge Local",
    description="로컬 ComfyUI 기반 AI 픽셀아트 생성기",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().app.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def private_network_access(request: Request, call_next):
    """Allow Chrome/Edge Private Network Access from the HTTPS Pages UI.

    A public HTTPS page calling http://127.0.0.1 is a private-network request.
    The browser sends a CORS preflight with Access-Control-Request-Private-Network
    and expects this header on the response.
    """
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


app.include_router(api_router)

outputs_root = PROJECT_ROOT / "outputs"
outputs_root.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(outputs_root)), name="files")

frontend_dist = PROJECT_ROOT / "frontend" / "dist"
assets_dir = frontend_dist / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")


@app.exception_handler(PixelForgeError)
async def pixelforge_error_handler(request: Request, exc: PixelForgeError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "extra": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = jsonable_encoder(exc.errors())
    first = errors[0] if errors else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part not in {"body", "query"})
    message = first.get("msg", "입력값이 올바르지 않습니다.")
    detail = f"{location}: {message}" if location else message
    return JSONResponse(
        status_code=422,
        content={"detail": f"입력값을 확인해 주세요. ({detail})", "code": "VALIDATION_ERROR", "errors": errors},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "서버 내부 오류가 발생했습니다. logs/backend.log를 확인해 주세요.",
            "code": "INTERNAL_ERROR",
        },
    )


@app.get("/", include_in_schema=False)
async def index():
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "detail": "프론트엔드 빌드가 없습니다. scripts/start.bat을 실행하면 자동으로 빌드됩니다.",
            "api_docs": "/docs",
        }
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "files/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found")
    dist = frontend_dist.resolve()
    candidate = (frontend_dist / full_path).resolve()
    if dist == candidate or dist in candidate.parents:
        if candidate.is_file():
            return FileResponse(candidate)
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build not found")
