from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "dashboard.db"
TEST_MODE = os.getenv("INTERLOG_TEST_MODE", "1") != "0"

STATUSES = [
    "SCHEDULED", "WAITING_AUTH", "EXPORTING", "PST_READY",
    "TRANSFERRING", "VERIFYING", "COMPLETE",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime:
    # PowerShell/.NET can emit seven fractional digits while Python accepts six.
    normalized = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    result = datetime.fromisoformat(normalized)
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              mailbox TEXT NOT NULL,
              scope TEXT NOT NULL,
              folder_name TEXT,
              export_engine TEXT NOT NULL,
              auth_mode TEXT NOT NULL,
              scheduled_at TEXT NOT NULL,
              destination TEXT NOT NULL,
              status TEXT NOT NULL,
              progress INTEGER NOT NULL DEFAULT 0,
              bytes_total INTEGER NOT NULL DEFAULT 0,
              bytes_done INTEGER NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT '',
              test_mode INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
              level TEXT NOT NULL,
              message TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_events_job_id ON events(job_id, id DESC);
            """
        )


def row_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["test_mode"] = bool(result["test_mode"])
    return result


def add_event(db: sqlite3.Connection, job_id: int, message: str, level: str = "INFO") -> None:
    db.execute(
        "INSERT INTO events(job_id, level, message, created_at) VALUES(?,?,?,?)",
        (job_id, level, message, now()),
    )


class JobCreate(BaseModel):
    mailbox: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    scope: Literal["primary", "online_archive", "folder"]
    folder_name: str | None = None
    export_engine: Literal["purview", "outlook_manual"] = "purview"
    auth_mode: Literal["app_only", "interactive_oauth"] = "app_only"
    scheduled_at: datetime
    destination: str = Field(min_length=2, max_length=500)
    note: str = Field(default="", max_length=1000)


async def demo_worker() -> None:
    while True:
        await asyncio.sleep(4)
        if not TEST_MODE:
            continue
        with connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE status NOT IN ('COMPLETE','FAILED','CANCELLED') ORDER BY id"
            ).fetchall()
            for row in rows:
                scheduled = parse_timestamp(row["scheduled_at"])
                if scheduled > datetime.now(timezone.utc):
                    continue
                current = row["status"]
                index = STATUSES.index(current) if current in STATUSES else 0
                next_status = STATUSES[min(index + 1, len(STATUSES) - 1)]
                progress_map = {
                    "WAITING_AUTH": 5, "EXPORTING": 28, "PST_READY": 55,
                    "TRANSFERRING": 78, "VERIFYING": 94, "COMPLETE": 100,
                }
                progress = progress_map.get(next_status, row["progress"])
                db.execute(
                    "UPDATE jobs SET status=?, progress=?, updated_at=? WHERE id=?",
                    (next_status, progress, now(), row["id"]),
                )
                add_event(db, row["id"], f"TEST MODE: chuyển trạng thái sang {next_status}")
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(demo_worker())
    yield
    task.cancel()


app = FastAPI(title="InterLOG Mail Operations", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "testMode": TEST_MODE, "database": str(DB_PATH)}


@app.get("/api/dashboard")
def dashboard() -> dict:
    with connect() as db:
        jobs = [row_dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 50")]
        counts = {row["status"]: row["count"] for row in db.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
        )}
        events = [dict(row) for row in db.execute(
            "SELECT events.*, jobs.mailbox FROM events JOIN jobs ON jobs.id=events.job_id ORDER BY events.id DESC LIMIT 12"
        )]
    active = sum(value for key, value in counts.items() if key not in {"COMPLETE", "FAILED", "CANCELLED"})
    return {
        "jobs": jobs,
        "events": events,
        "summary": {
            "total": sum(counts.values()),
            "active": active,
            "complete": counts.get("COMPLETE", 0),
            "failed": counts.get("FAILED", 0),
        },
        "testMode": TEST_MODE,
    }


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreate) -> dict:
    if payload.scope == "folder" and not payload.folder_name:
        raise HTTPException(422, "Phải nhập tên thư mục khi chọn phạm vi folder")
    if payload.auth_mode == "interactive_oauth" and payload.export_engine == "purview":
        raise HTTPException(422, "Purview worker phải dùng app-only; không nhận mật khẩu user")
    created = now()
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO jobs(mailbox,scope,folder_name,export_engine,auth_mode,scheduled_at,
               destination,status,progress,note,test_mode,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                payload.mailbox.lower(), payload.scope, payload.folder_name,
                payload.export_engine, payload.auth_mode,
                payload.scheduled_at.astimezone(timezone.utc).isoformat(),
                payload.destination, "SCHEDULED", 0, payload.note,
                int(TEST_MODE), created, created,
            ),
        )
        job_id = cursor.lastrowid
        add_event(db, job_id, "Yêu cầu backup đã được tạo")
        add_event(db, job_id, "Đang chạy chế độ TEST - chưa truy cập mailbox thật", "WARNING")
        db.commit()
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row_dict(row)


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: int) -> list[dict]:
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(404, "Không tìm thấy job")
        return [dict(row) for row in db.execute(
            "SELECT * FROM events WHERE job_id=? ORDER BY id DESC", (job_id,)
        )]


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy job")
        if row["status"] == "COMPLETE":
            raise HTTPException(409, "Job đã hoàn tất")
        db.execute("UPDATE jobs SET status='CANCELLED', updated_at=? WHERE id=?", (now(), job_id))
        add_event(db, job_id, "Job đã bị hủy bởi IT", "WARNING")
        db.commit()
    return {"ok": True}


FRONTEND = ROOT / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = FRONTEND / path
        return FileResponse(candidate if candidate.is_file() else FRONTEND / "index.html")
