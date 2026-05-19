import hashlib
import json
from datetime import datetime, timezone, timedelta

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.config import Settings, get_settings

router = APIRouter()

SCHEMA_VERSION = 1


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                user         TEXT    NOT NULL,
                tool         TEXT    NOT NULL,
                args_hash    TEXT    NOT NULL,
                result_ok    INTEGER NOT NULL,
                ip           TEXT    NOT NULL,
                duration_ms  INTEGER NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON audit_events(ts)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tool ON audit_events(tool)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user ON audit_events(user)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_result_ok ON audit_events(result_ok)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute(
            "INSERT OR REPLACE INTO audit_meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        await db.commit()


async def log_call(
    db_path: str,
    user: str,
    tool: str,
    arguments: dict,
    result_ok: bool,
    ip: str,
    duration_ms: int,
) -> None:
    args_hash = hashlib.sha256(
        json.dumps(arguments, sort_keys=True).encode()
    ).hexdigest()[:16]
    ts = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO audit_events (ts, user, tool, args_hash, result_ok, ip, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, user, tool, args_hash, int(result_ok), ip, duration_ms),
        )
        await db.commit()


async def cleanup_old_events(db_path: str, retention_days: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM audit_events WHERE ts < ?", (cutoff,))
        await db.commit()


async def audit_health(settings: Settings) -> dict:
    if settings.audit_backend != "sqlite":
        return {
            "ok": False,
            "backend": settings.audit_backend,
            "error": "Unsupported audit backend",
        }

    try:
        async with aiosqlite.connect(settings.audit_db_path) as db:
            await db.execute("SELECT 1")
            async with db.execute("SELECT COUNT(*) FROM audit_events") as cursor:
                total = (await cursor.fetchone())[0]
            async with db.execute("SELECT value FROM audit_meta WHERE key = ?", ("schema_version",)) as cursor:
                row = await cursor.fetchone()
        return {
            "ok": True,
            "backend": settings.audit_backend,
            "sqlite_persistence": settings.audit_sqlite_persistence,
            "path": settings.audit_db_path,
            "schema_version": row[0] if row else None,
            "events_total": total,
            "retention_days": settings.audit_retention_days,
        }
    except Exception as exc:
        return {
            "ok": False,
            "backend": settings.audit_backend,
            "path": settings.audit_db_path,
            "error": type(exc).__name__,
        }


@router.get("/api/audit/health")
async def get_audit_health(settings: Settings = Depends(get_settings)):
    return await audit_health(settings)


@router.get("/api/audit")
async def get_audit(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    tool: str = Query(""),
    user: str = Query(""),
    settings: Settings = Depends(get_settings),
):
    clauses: list[str] = []
    params: list = []
    if tool:
        clauses.append("tool LIKE ?")
        params.append(f"%{tool}%")
    if user:
        clauses.append("user LIKE ?")
        params.append(f"%{user}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    count_params = list(params)
    params += [limit, offset]

    async with aiosqlite.connect(settings.audit_db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT * FROM audit_events {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        async with db.execute(
            f"SELECT COUNT(*) FROM audit_events {where}", count_params
        ) as c:
            total = (await c.fetchone())[0]

    return {"total": total, "events": [dict(r) for r in rows]}
