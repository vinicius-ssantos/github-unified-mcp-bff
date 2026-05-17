from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit import cleanup_old_events, init_db, router as audit_router
from app.auth import router as auth_router
from app.config import get_settings
from app.middleware import SecurityHeadersMiddleware
from app.proxy import router as proxy_router

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(_settings.audit_db_path)
    await cleanup_old_events(_settings.audit_db_path, _settings.audit_retention_days)
    yield


app = FastAPI(title="github-unified-mcp-bff", version="0.2.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(proxy_router)
app.include_router(auth_router)
app.include_router(audit_router)
