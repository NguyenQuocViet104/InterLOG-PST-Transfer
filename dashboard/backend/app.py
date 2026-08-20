from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "dashboard.db"
TEST_MODE = os.getenv("INTERLOG_TEST_MODE", "1") != "0"
FINAL_STATUSES = {"COMPLETE", "FAILED", "CANCELLED"}
TEST_PST_SIZE = 51_028_116_480
PURVIEW_FLOW = ["SCHEDULED", "EXPORTING", "PST_READY", "WAITING_TRANSFER", "TRANSFERRING", "VERIFYING", "COMPLETE"]
PROGRESS = {"SCHEDULED": 0, "WAITING_OPERATOR": 10, "EXPORTING": 25, "PST_READY": 50, "WAITING_TRANSFER": 55, "TRANSFERRING": 75, "VERIFYING": 95, "COMPLETE": 100}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime:
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
        db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, mailbox TEXT NOT NULL, scope TEXT NOT NULL,
          folder_name TEXT, export_engine TEXT NOT NULL, auth_mode TEXT NOT NULL,
          scheduled_at TEXT NOT NULL, destination TEXT NOT NULL, status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0, bytes_total INTEGER NOT NULL DEFAULT 0,
          bytes_done INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
          test_mode INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          level TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workers (
          id TEXT PRIMARY KEY, display_name TEXT NOT NULL, machine_name TEXT NOT NULL,
          role TEXT NOT NULL, status TEXT NOT NULL, version TEXT NOT NULL,
          last_seen_at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS artifacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0,
          sha256 TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_events_job_id ON events(job_id,id DESC);
        CREATE INDEX IF NOT EXISTS ix_artifacts_job_id ON artifacts(job_id,id DESC);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        for name, definition in {
            "ticket": "TEXT NOT NULL DEFAULT ''", "requested_by": "TEXT NOT NULL DEFAULT ''",
            "assigned_worker": "TEXT NOT NULL DEFAULT 'vm-worker-01'", "pst_path": "TEXT NOT NULL DEFAULT ''",
            "error": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        db.execute("""INSERT OR IGNORE INTO workers(id,display_name,machine_name,role,status,version,last_seen_at,detail)
          VALUES('vm-worker-01','VM Export Worker','TEST-VM','export','OFFLINE','0.2.0',?,'Chưa kết nối agent thật')""", (now(),))
        db.commit()


def row_dict(row: sqlite3.Row | None) -> dict:
    result = dict(row) if row else {}
    if "test_mode" in result:
        result["test_mode"] = bool(result["test_mode"])
    return result


def worker_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    try:
        age = (datetime.now(timezone.utc) - parse_timestamp(result["last_seen_at"])).total_seconds()
    except (ValueError, TypeError):
        age = 999999
    result["heartbeat_age_seconds"] = max(0, int(age))
    if age > 45:
        result["status"] = "OFFLINE"
    return result


def add_event(db: sqlite3.Connection, job_id: int, message: str, level: str = "INFO") -> None:
    db.execute("INSERT INTO events(job_id,level,message,created_at) VALUES(?,?,?,?)", (job_id, level, message, now()))


def require_job(db: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy job")
    return row


class JobCreate(BaseModel):
    mailbox: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    scope: Literal["primary", "online_archive", "folder"]
    folder_name: str | None = None
    export_engine: Literal["purview", "outlook_manual", "graph_local"] = "outlook_manual"
    auth_mode: Literal["app_only", "interactive_oauth"] = "interactive_oauth"
    scheduled_at: datetime
    destination: str = Field(min_length=2, max_length=500)
    ticket: str = Field(default="", max_length=100)
    requested_by: str = Field(default="", max_length=200)
    assigned_worker: str = Field(default="vm-worker-01", max_length=100)
    note: str = Field(default="", max_length=1000)


class OperatorReady(BaseModel):
    pst_path: str = Field(min_length=2, max_length=1000)
    size_bytes: int = Field(default=0, ge=0)


class LocalComplete(BaseModel):
    pst_path: str = Field(min_length=2, max_length=1000)
    manifest_path: str | None = Field(default=None, max_length=1000)


class UserCopyConfirm(BaseModel):
    destination_path: str = Field(min_length=2, max_length=1000)
    size_bytes: int = Field(default=0, ge=0)


class WorkerHeartbeat(BaseModel):
    id: str = Field(min_length=2, max_length=100)
    display_name: str = "VM Worker"
    machine_name: str = ""
    role: str = "export"
    status: Literal["ONLINE", "BUSY", "OFFLINE", "ERROR"] = "ONLINE"
    version: str = "0.2.0"
    detail: str = ""


class ReceiptPayload(BaseModel):
    status: str
    sourcePath: str | None = None
    destinationPath: str | None = None
    expectedBytes: int | None = None
    bytesTransferred: int | None = None
    bytesTotal: int | None = None
    sourceSha256: str | None = None
    destinationSha256: str | None = None
    errorDescription: str | None = None
    error: str | None = None


async def demo_worker() -> None:
    while True:
        await asyncio.sleep(4)
        if not TEST_MODE:
            continue
        with connect() as db:
            db.execute("UPDATE workers SET status='ONLINE',last_seen_at=?,detail='Dashboard demo worker' WHERE id='vm-worker-01'", (now(),))
            rows = db.execute("SELECT * FROM jobs WHERE status NOT IN ('COMPLETE','FAILED','CANCELLED') ORDER BY id").fetchall()
            for row in rows:
                if parse_timestamp(row["scheduled_at"]) > datetime.now(timezone.utc):
                    continue
                current = row["status"]
                if row["export_engine"] == "outlook_manual":
                    if current == "SCHEDULED":
                        db.execute("UPDATE jobs SET status='WAITING_OPERATOR',progress=10,updated_at=? WHERE id=?", (now(), row["id"]))
                        add_event(db, row["id"], "Chờ IT export đúng dữ liệu bằng Outlook Classic và xác nhận PST đã sẵn sàng", "WARNING")
                    continue
                if row["export_engine"] == "graph_local":
                    if current == "SCHEDULED":
                        db.execute("UPDATE jobs SET status='WAITING_GRAPH',progress=10,updated_at=? WHERE id=?", (now(), row["id"]))
                        add_event(db, row["id"], "Chờ Graph local worker đồng bộ mailbox và đóng PST", "WARNING")
                    continue
                index = PURVIEW_FLOW.index(current) if current in PURVIEW_FLOW else 0
                next_status = PURVIEW_FLOW[min(index + 1, len(PURVIEW_FLOW) - 1)]
                total = TEST_PST_SIZE if next_status in {"PST_READY", "WAITING_TRANSFER", "TRANSFERRING", "VERIFYING", "COMPLETE"} else row["bytes_total"]
                done = total if next_status in {"VERIFYING", "COMPLETE"} else (total * PROGRESS.get(next_status, 0) // 100 if total else 0)
                db.execute("UPDATE jobs SET status=?,progress=?,bytes_total=?,bytes_done=?,updated_at=? WHERE id=?", (next_status, PROGRESS.get(next_status, row["progress"]), total, done, now(), row["id"]))
                add_event(db, row["id"], f"TEST MODE: chuyển trạng thái sang {next_status}")
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(demo_worker())
    yield
    task.cancel()


app = FastAPI(title="InterLOG Mail Operations", version="0.3.2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.3.2", "testMode": TEST_MODE, "database": str(DB_PATH)}


@app.get("/api/dashboard")
def dashboard() -> dict:
    with connect() as db:
        jobs = [row_dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 100")]
        counts = {row["status"]: row["count"] for row in db.execute("SELECT status,COUNT(*) AS count FROM jobs GROUP BY status")}
        events = [dict(row) for row in db.execute("SELECT events.*,jobs.mailbox FROM events JOIN jobs ON jobs.id=events.job_id ORDER BY events.id DESC LIMIT 16")]
        workers = [worker_dict(row) for row in db.execute("SELECT * FROM workers ORDER BY id")]
    active = sum(value for key, value in counts.items() if key not in FINAL_STATUSES)
    return {"jobs": jobs, "events": events, "workers": workers, "summary": {"total": sum(counts.values()), "active": active, "complete": counts.get("COMPLETE", 0), "failed": counts.get("FAILED", 0)}, "testMode": TEST_MODE}


@app.get("/api/jobs")
def list_jobs(status: str | None = None, query: str = Query(default="", max_length=200)) -> list[dict]:
    clauses, params = [], []
    if status and status != "ALL":
        clauses.append("status=?"); params.append(status)
    if query:
        clauses.append("(mailbox LIKE ? OR ticket LIKE ? OR requested_by LIKE ?)")
        pattern = f"%{query}%"; params.extend([pattern, pattern, pattern])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as db:
        return [row_dict(row) for row in db.execute(f"SELECT * FROM jobs{where} ORDER BY id DESC LIMIT 200", params)]


@app.get("/api/events")
def list_events(level: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> list[dict]:
    where, params = "", []
    if level and level != "ALL":
        where = " WHERE events.level=?"
        params.append(level)
    params.append(limit)
    with connect() as db:
        return [dict(row) for row in db.execute(
            f"SELECT events.*,jobs.mailbox,jobs.ticket FROM events JOIN jobs ON jobs.id=events.job_id{where} ORDER BY events.id DESC LIMIT ?",
            params,
        )]


@app.get("/api/history.csv")
def export_history_csv() -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["job_id", "mailbox", "ticket", "scope", "status", "progress", "bytes_total", "scheduled_at", "updated_at", "error"])
    with connect() as db:
        for row in db.execute("SELECT id,mailbox,ticket,scope,status,progress,bytes_total,scheduled_at,updated_at,error FROM jobs ORDER BY id DESC"):
            writer.writerow(list(row))
    headers = {"Content-Disposition": "attachment; filename=interlog-mail-history.csv"}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)


@app.get("/api/system")
def system_status() -> dict:
    certificate = bool(os.getenv("INTERLOG_CERTIFICATE_THUMBPRINT"))
    tenant = bool(os.getenv("INTERLOG_TENANT_ID"))
    client = bool(os.getenv("INTERLOG_CLIENT_ID"))
    with connect() as db:
        db_ok = db.execute("SELECT 1").fetchone()[0] == 1
    return {
        "testMode": TEST_MODE,
        "database": {"ready": db_ok, "path": str(DB_PATH)},
        "purview": {
            "ready": (not TEST_MODE) and tenant and client and certificate,
            "tenantConfigured": tenant,
            "clientConfigured": client,
            "certificateConfigured": certificate,
            "productionLocked": TEST_MODE,
        },
        "outlook": {"mode": "manual", "ready": True, "note": "IT export bằng Outlook Classic trên VM"},
        "bits": {"ready": True, "receiptEndpoint": "/api/jobs/{job_id}/receipt"},
        "security": {"storesPasswords": False, "authentication": "Certificate/RBAC hoặc OAuth tương tác"},
    }


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreate) -> dict:
    if payload.scope == "folder" and not payload.folder_name:
        raise HTTPException(422, "Phải nhập tên thư mục khi chọn phạm vi folder")
    if payload.export_engine == "purview" and payload.auth_mode != "app_only":
        raise HTTPException(422, "Purview worker phải dùng app-only; không nhận mật khẩu user")
    if payload.export_engine == "graph_local" and payload.auth_mode != "app_only":
        raise HTTPException(422, "Graph local phải dùng app-only/RBAC")
    created = now()
    with connect() as db:
        cursor = db.execute("""INSERT INTO jobs(mailbox,scope,folder_name,export_engine,auth_mode,scheduled_at,destination,status,progress,note,test_mode,created_at,updated_at,ticket,requested_by,assigned_worker,pst_path,error)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (payload.mailbox.lower(), payload.scope, payload.folder_name, payload.export_engine, payload.auth_mode, payload.scheduled_at.astimezone(timezone.utc).isoformat(), payload.destination, "SCHEDULED", 0, payload.note, int(TEST_MODE), created, created, payload.ticket, payload.requested_by, payload.assigned_worker, "", ""))
        job_id = int(cursor.lastrowid)
        add_event(db, job_id, "Yêu cầu backup đã được tạo")
        if TEST_MODE:
            add_event(db, job_id, "TEST MODE: không truy cập mailbox thật", "WARNING")
        db.commit()
        return row_dict(require_job(db, job_id))


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int) -> dict:
    with connect() as db:
        job = row_dict(require_job(db, job_id))
        events = [dict(row) for row in db.execute("SELECT * FROM events WHERE job_id=? ORDER BY id DESC", (job_id,))]
        artifacts = [dict(row) for row in db.execute("SELECT * FROM artifacts WHERE job_id=? ORDER BY id DESC", (job_id,))]
    return {"job": job, "events": events, "artifacts": artifacts}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: int) -> list[dict]:
    return job_detail(job_id)["events"]


@app.post("/api/jobs/{job_id}/operator-ready")
def operator_ready(job_id: int, payload: OperatorReady) -> dict:
    with connect() as db:
        row = require_job(db, job_id)
        if row["status"] not in {"WAITING_OPERATOR", "SCHEDULED", "FAILED"}:
            raise HTTPException(409, "Job không ở trạng thái chờ xác nhận PST")
        timestamp = now()
        db.execute("UPDATE jobs SET status='PST_READY',progress=50,pst_path=?,bytes_total=?,bytes_done=0,error='',updated_at=? WHERE id=?", (payload.pst_path, payload.size_bytes, timestamp, job_id))
        db.execute("INSERT INTO artifacts(job_id,kind,path,size_bytes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (job_id, "PST_SOURCE", payload.pst_path, payload.size_bytes, "READY", timestamp, timestamp))
        add_event(db, job_id, f"IT xác nhận PST đã export xong: {payload.pst_path}")
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/complete-local")
def complete_local(job_id: int, payload: LocalComplete) -> dict:
    pst_path = Path(payload.pst_path).resolve()
    if not pst_path.is_file() or pst_path.suffix.lower() != ".pst":
        raise HTTPException(422, "Không tìm thấy file PST local hợp lệ")
    manifest_path = Path(payload.manifest_path).resolve() if payload.manifest_path else None
    if manifest_path and not manifest_path.is_file():
        raise HTTPException(422, "Không tìm thấy manifest PST")
    with connect() as db:
        row = require_job(db, job_id)
        if row["export_engine"] != "graph_local":
            raise HTTPException(409, "Chỉ job Graph local mới nhận PST local")
        timestamp = now()
        size = pst_path.stat().st_size
        db.execute("UPDATE jobs SET status='COMPLETE',progress=100,pst_path=?,bytes_total=?,bytes_done=?,error='',updated_at=? WHERE id=?", (str(pst_path), size, size, timestamp, job_id))
        db.execute("INSERT INTO artifacts(job_id,kind,path,size_bytes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (job_id, "PST_LOCAL", str(pst_path), size, "VERIFIED", timestamp, timestamp))
        if manifest_path:
            db.execute("INSERT INTO artifacts(job_id,kind,path,size_bytes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (job_id, "PST_MANIFEST", str(manifest_path), manifest_path.stat().st_size, "VERIFIED", timestamp, timestamp))
        add_event(db, job_id, f"Graph local backup hoàn tất và đã đăng ký PST: {pst_path}")
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/confirm-user-copy")
def confirm_user_copy(job_id: int, payload: UserCopyConfirm) -> dict:
    with connect() as db:
        row = require_job(db, job_id)
        if row["export_engine"] != "outlook_manual":
            raise HTTPException(409, "Xác nhận bàn giao thủ công chỉ dành cho job Outlook")
        if row["status"] not in {"PST_READY", "WAITING_TRANSFER", "TRANSFERRING"}:
            raise HTTPException(409, "Job chưa ở bước chuyển PST về máy user")
        timestamp = now()
        size = payload.size_bytes or row["bytes_total"]
        db.execute(
            "UPDATE jobs SET status='VERIFYING',progress=95,destination=?,bytes_done=?,updated_at=? WHERE id=?",
            (payload.destination_path, size, timestamp, job_id),
        )
        db.execute(
            "INSERT INTO artifacts(job_id,kind,path,size_bytes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (job_id, "PST_USER_COPY", payload.destination_path, size, "PENDING_OUTLOOK_CHECK", timestamp, timestamp),
        )
        add_event(db, job_id, f"IT xác nhận file đã được chuyển về máy user: {payload.destination_path}", "WARNING")
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/verify-user-copy")
def verify_user_copy(job_id: int) -> dict:
    with connect() as db:
        row = require_job(db, job_id)
        if row["export_engine"] != "outlook_manual" or row["status"] != "VERIFYING":
            raise HTTPException(409, "Job chưa chờ xác minh PST trên máy user")
        timestamp = now()
        db.execute("UPDATE jobs SET status='COMPLETE',progress=100,bytes_done=bytes_total,error='',updated_at=? WHERE id=?", (timestamp, job_id))
        db.execute("UPDATE artifacts SET status='VERIFIED',updated_at=? WHERE job_id=? AND kind='PST_USER_COPY'", (timestamp, job_id))
        add_event(db, job_id, "IT xác nhận PST đã mở được bằng Outlook trên máy user; bàn giao hoàn tất")
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/receipt")
def ingest_receipt(job_id: int, receipt: ReceiptPayload) -> dict:
    status = receipt.status.upper()
    mapped = {"QUEUED": "WAITING_TRANSFER", "TRANSFERRING_BACKGROUND": "TRANSFERRING", "CONNECTING": "TRANSFERRING", "TRANSFERRING": "TRANSFERRING", "TRANSIENTERROR": "TRANSFERRING", "SUSPENDED": "TRANSFERRING", "TRANSFERRED": "VERIFYING", "WAITING_SOURCE_VERIFICATION": "VERIFYING", "VERIFYING_SHA256": "VERIFYING", "COMPLETE": "COMPLETE", "COMPLETE_EXISTING": "COMPLETE", "ERROR": "FAILED", "SIZE_MISMATCH": "FAILED", "HASH_MISMATCH": "FAILED", "SOURCE_CHANGED_STOPPED": "FAILED", "SOURCE_UNAVAILABLE": "FAILED"}.get(status, "TRANSFERRING")
    total = receipt.bytesTotal or receipt.expectedBytes or 0
    done = receipt.bytesTransferred or (total if mapped == "COMPLETE" else 0)
    progress = 100 if mapped == "COMPLETE" else (min(99, int(done * 100 / total)) if total else PROGRESS.get(mapped, 0))
    error = receipt.errorDescription or receipt.error or ""
    path = receipt.destinationPath or receipt.sourcePath or ""
    with connect() as db:
        require_job(db, job_id)
        db.execute("UPDATE jobs SET status=?,progress=?,bytes_total=?,bytes_done=?,pst_path=CASE WHEN ?<>'' THEN ? ELSE pst_path END,error=?,updated_at=? WHERE id=?", (mapped, progress, total, done, path, path, error, now(), job_id))
        level = "ERROR" if mapped == "FAILED" else ("WARNING" if status in {"TRANSIENTERROR", "SUSPENDED"} else "INFO")
        add_event(db, job_id, f"BITS receipt: {status} ({done}/{total} bytes)" + (f" — {error}" if error else ""), level)
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int) -> dict:
    with connect() as db:
        row = require_job(db, job_id)
        if row["status"] == "COMPLETE":
            raise HTTPException(409, "Job đã hoàn tất")
        if row["export_engine"] == "graph_local":
            target = "WAITING_GRAPH"
        else:
            target = "WAITING_OPERATOR" if row["export_engine"] == "outlook_manual" and not row["pst_path"] else "WAITING_TRANSFER"
        db.execute("UPDATE jobs SET status=?,error='',updated_at=? WHERE id=?", (target, now(), job_id))
        add_event(db, job_id, "IT yêu cầu thử lại/tiếp tục job", "WARNING")
        db.commit()
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    with connect() as db:
        row = require_job(db, job_id)
        if row["status"] == "COMPLETE":
            raise HTTPException(409, "Job đã hoàn tất")
        db.execute("UPDATE jobs SET status='CANCELLED',updated_at=? WHERE id=?", (now(), job_id))
        add_event(db, job_id, "Job đã bị hủy bởi IT", "WARNING")
        db.commit()
    return job_detail(job_id)


@app.get("/api/workers")
def list_workers() -> list[dict]:
    with connect() as db:
        return [worker_dict(row) for row in db.execute("SELECT * FROM workers ORDER BY id")]


@app.post("/api/workers/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeat) -> dict:
    with connect() as db:
        db.execute("""INSERT INTO workers(id,display_name,machine_name,role,status,version,last_seen_at,detail) VALUES(?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,machine_name=excluded.machine_name,role=excluded.role,status=excluded.status,version=excluded.version,last_seen_at=excluded.last_seen_at,detail=excluded.detail""", (payload.id, payload.display_name, payload.machine_name, payload.role, payload.status, payload.version, now(), payload.detail))
        db.commit()
    return {"ok": True, "testMode": TEST_MODE}


FRONTEND = ROOT / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = FRONTEND / path
        return FileResponse(candidate if candidate.is_file() else FRONTEND / "index.html")
