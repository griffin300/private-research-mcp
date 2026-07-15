from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from app import PROJECT_NAME, __version__
from app.dashboard.routes import create_dashboard_router
from app.logging_config import configure_logging
from app.mcp_server import create_mcp_server
from app.runtime import create_runtime

runtime = create_runtime()
configure_logging(runtime.settings.log_level)
mcp = create_mcp_server(runtime)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=PROJECT_NAME, version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None
)
app.include_router(create_dashboard_router(runtime))
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health() -> dict[str, object]:
    return (await runtime.pipeline.status()).model_dump(mode="json")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": PROJECT_NAME, "dashboard": "/dashboard", "mcp": "/mcp"}


def run() -> None:
    uvicorn.run(app, host=runtime.settings.admin_host, port=runtime.settings.admin_port)


if __name__ == "__main__":
    run()
