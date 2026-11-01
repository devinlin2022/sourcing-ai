import secrets
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import ADMIN_PASSWORD, ADMIN_USER, MARKET_REFRESH_HOUR
from app.db import db
from app.ingest.pipeline import datasets_overview
from app.market import store as market

security = HTTPBasic()


def require_auth(cred: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(cred.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(cred.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Basic"},
        )
    return cred.username


def _scheduled_refresh():
    try:
        market.refresh()
    except Exception as e:
        print(f"[market] scheduled refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(_scheduled_refresh, "cron", hour=MARKET_REFRESH_HOUR, minute=0)
        scheduler.start()
    except Exception as e:
        print(f"[scheduler] disabled: {e}")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Sourcing AI", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/datasets", dependencies=[Depends(require_auth)])
    def datasets():
        return datasets_overview()

    @app.get("/api/market/latest", dependencies=[Depends(require_auth)])
    def market_latest():
        return market.board().to_dict("records")

    from app.ui.app import CSS, build_blocks

    gr.mount_gradio_app(
        app,
        build_blocks(),
        path="/",
        auth=lambda u, p: secrets.compare_digest(u, ADMIN_USER)
        and secrets.compare_digest(p, ADMIN_PASSWORD),
        auth_message="Sourcing AI 登录（默认 admin / admin123，请尽快在 .env 修改）",
        theme=gr.themes.Soft(),
        css=CSS,
    )
    return app
