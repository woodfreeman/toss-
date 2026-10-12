"""Toss 快抛 — WiFi 局域网互传小工具（文本 / 图片 / 小文件）。

双实例形态：每台电脑各放一份，谁开机谁就是服务器。
- 单文件 FastAPI 应用，SQLite 存记录，文件落本地 data/files/
- 访问口令（可选）：PBKDF2-HMAC-SHA256 存储 + HMAC 签名会话 Cookie
- 7 天自动清理：普通条目按创建时间过期；回收站条目按删除时间再留 7 天反悔期
- 打包：pyinstaller --onefile --noconsole --collect-submodules uvicorn --add-data "static;static" backend/main.py
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import List

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

VERSION = "0.1.7"
APP_NAME = "Toss 快抛"
PORT = int(os.environ.get("TOSS_PORT", "8400"))
RETENTION_DEFAULT = 30  # 记录保留天数（可在 ⚙️ 设置里改，范围 1~90）
RETENTION_MIN = 1
RETENTION_MAX = 90
SESSION_DAYS = 30
DB_TIMEOUT = 5

# ---------- 路径（exe 旁边即数据目录，绿色便携） ----------
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    STATIC_DIR = Path(getattr(sys, "_MEIPASS", ".")) / "static"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = BASE_DIR / "static"

DATA_DIR = BASE_DIR / "data"
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "toss.db"
KEY_PATH = DATA_DIR / ".secret.key"
LOG_PATH = DATA_DIR / "toss.log"

for p in (FILES_DIR,):
    p.mkdir(parents=True, exist_ok=True)


def load_key() -> bytes:
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(secrets.token_bytes(32))
    return KEY_PATH.read_bytes()


SECRET_KEY = load_key()

logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("toss")

# ---------- DB ----------
DDL = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,            -- text | file
  content TEXT,                  -- text 专用
  orig_name TEXT,
  stored_name TEXT,
  size INTEGER DEFAULT 0,
  mime TEXT,
  is_image INTEGER DEFAULT 0,
  created_at REAL NOT NULL,
  deleted_at REAL               -- 非空 = 已进回收站（软删除）
);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    return conn


with db() as _c:
    _c.executescript(DDL)
    # 旧库迁移
    cols = {r["name"] for r in _c.execute("PRAGMA table_info(items)").fetchall()}
    if "deleted_at" not in cols:
        # v0.1.2 及以前：items 表没有 deleted_at 列
        _c.execute("ALTER TABLE items ADD COLUMN deleted_at REAL")
    if "memo" not in cols:
        # v0.1.6：新增可编辑备注/重命名（图片/文件/文本通用）
        _c.execute("ALTER TABLE items ADD COLUMN memo TEXT")


def get_setting(key: str, default: str = "") -> str:
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_retention_days() -> int:
    """读取可配置的保留天数（默认 30，限制在 1~90）。"""
    try:
        val = int(get_setting("retention_days", ""))
    except ValueError:
        val = RETENTION_DEFAULT
    return max(RETENTION_MIN, min(RETENTION_MAX, val))


# ---------- 口令 ----------
def hash_pw(pw: str, salt: str = "") -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        salt = stored.split("$", 1)[0]
    except ValueError:
        return False
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def make_token() -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{exp:08x}"
    sig = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def check_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
        good = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return False
        return int(payload, 16) > time.time()
    except Exception:
        return False


def has_password() -> bool:
    return bool(get_setting("pw_hash"))


def require_auth(request: Request) -> None:
    if not has_password():
        return
    token = request.cookies.get("toss_session", "")
    if not token or not check_token(token):
        raise HTTPException(status_code=401, detail="未登录")


# ---------- 清理 ----------
def _purge_rows(c: sqlite3.Connection, rows) -> int:
    """物理删除条目及其文件（回收站过期 / 手动彻底删除共用）。"""
    n = 0
    for row in rows:
        if row["stored_name"]:
            try:
                (FILES_DIR / row["stored_name"]).unlink(missing_ok=True)
            except OSError:
                pass
        c.execute("DELETE FROM items WHERE id=?", (row["id"],))
        n += 1
    return n


def cleanup_expired() -> int:
    cutoff = time.time() - get_retention_days() * 86400
    with db() as c:
        # 未删除的按创建时间过期；已进回收站的按删除时间过期（再留 7 天反悔期）
        rows = c.execute(
            "SELECT id, stored_name FROM items WHERE "
            "(deleted_at IS NULL AND created_at < ?) OR "
            "(deleted_at IS NOT NULL AND deleted_at < ?)",
            (cutoff, cutoff),
        ).fetchall()
        removed = _purge_rows(c, rows)
    if removed:
        log.info("cleanup: removed %d expired items", removed)
    return removed


def cleanup_loop() -> None:
    while True:
        time.sleep(1800)
        try:
            cleanup_expired()
        except Exception:
            log.error("cleanup error:\n%s", traceback.format_exc())


threading.Thread(target=cleanup_loop, daemon=True).start()

# ---------- 应用 ----------
app = FastAPI(title=APP_NAME)


class TextIn(BaseModel):
    content: str


class LoginIn(BaseModel):
    password: str


class SetPwIn(BaseModel):
    old_password: str = ""
    new_password: str = ""


class MemoIn(BaseModel):
    memo: str = ""


def local_ips() -> list:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


@app.get("/api/health")
def api_health(request: Request):
    return {
        "name": APP_NAME,
        "version": VERSION,
        "need_password": has_password(),
        "authed": bool(request.cookies.get("toss_session", "")) and check_token(
            request.cookies.get("toss_session", "")
        ),
    }


@app.post("/api/login")
def api_login(data: LoginIn, response: Response):
    stored = get_setting("pw_hash")
    if not stored:
        raise HTTPException(status_code=400, detail="尚未设置口令")
    if not verify_pw(data.password, stored):
        raise HTTPException(status_code=401, detail="口令不对")
    response.set_cookie(
        "toss_session", make_token(),
        max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
    )
    return {"ok": True}


@app.post("/api/logout")
def api_logout(response: Response):
    response.delete_cookie("toss_session")
    return {"ok": True}


@app.post("/api/auth/setpw", dependencies=[Depends(require_auth)])
def api_setpw(data: SetPwIn):
    stored = get_setting("pw_hash")
    if stored:
        if not data.old_password or not verify_pw(data.old_password, stored):
            raise HTTPException(status_code=403, detail="旧口令不对")
    if not data.new_password or len(data.new_password) < 4:
        raise HTTPException(status_code=400, detail="新口令至少 4 位")
    set_setting("pw_hash", hash_pw(data.new_password))
    return {"ok": True}


@app.post("/api/auth/clearpw", dependencies=[Depends(require_auth)])
def api_clearpw():
    set_setting("pw_hash", "")
    return {"ok": True}


@app.get("/api/items", dependencies=[Depends(require_auth)])
def api_items(limit: int = 100):
    limit = max(1, min(limit, 500))
    with db() as c:
        rows = c.execute(
            "SELECT * FROM items WHERE deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/text", dependencies=[Depends(require_auth)])
def api_text(data: TextIn):
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容为空")
    item_id = uuid.uuid4().hex[:12]
    with db() as c:
        c.execute(
            "INSERT INTO items(id,kind,content,created_at) VALUES(?,?,?,?)",
            (item_id, "text", content, time.time()),
        )
    return {"ok": True, "id": item_id}


@app.post("/api/files", dependencies=[Depends(require_auth)])
def api_files(files: List[UploadFile] = File(...)):
    saved = []
    with db() as c:
        for f in files:
            suffix = Path(f.filename or "unnamed").suffix[:16]
            stored = f"{uuid.uuid4().hex}{suffix}"
            dest = FILES_DIR / stored
            size = 0
            with dest.open("wb") as out:
                while chunk := f.file.read(1024 * 1024):
                    out.write(chunk)
                    size += len(chunk)
            mime = f.content_type or "application/octet-stream"
            is_image = 1 if mime.startswith("image/") else 0
            item_id = uuid.uuid4().hex[:12]
            c.execute(
                "INSERT INTO items(id,kind,orig_name,stored_name,size,mime,is_image,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (item_id, "file", f.filename or stored, stored, size, mime, is_image, time.time()),
            )
            saved.append({"id": item_id, "name": f.filename, "size": size})
    return {"ok": True, "saved": saved}


def _get_item(item_id: str):
    with db() as c:
        row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="条目不存在或已过期")
    return row


@app.get("/api/items/{item_id}/raw", dependencies=[Depends(require_auth)])
def api_raw(item_id: str):
    row = _get_item(item_id)
    if row["kind"] == "text":
        return PlainTextResponse(row["content"] or "")
    path = FILES_DIR / row["stored_name"]
    return FileResponse(path, media_type=row["mime"] or "application/octet-stream")


@app.get("/api/items/{item_id}/download", dependencies=[Depends(require_auth)])
def api_download(item_id: str):
    row = _get_item(item_id)
    if row["kind"] == "text":
        return PlainTextResponse(
            row["content"] or "",
            headers={"Content-Disposition": f'attachment; filename="toss-{item_id}.txt"'},
        )
    path = FILES_DIR / row["stored_name"]
    return FileResponse(path, filename=row["orig_name"] or path.name)


@app.delete("/api/items/{item_id}", dependencies=[Depends(require_auth)])
def api_delete(item_id: str):
    """软删除：进回收站，文件保留，可还原。"""
    _get_item(item_id)
    with db() as c:
        c.execute(
            "UPDATE items SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
            (time.time(), item_id),
        )
    return {"ok": True}


@app.get("/api/trash", dependencies=[Depends(require_auth)])
def api_trash(limit: int = 100):
    limit = max(1, min(limit, 500))
    with db() as c:
        rows = c.execute(
            "SELECT * FROM items WHERE deleted_at IS NOT NULL "
            "ORDER BY deleted_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/items/{item_id}/restore", dependencies=[Depends(require_auth)])
def api_restore(item_id: str):
    _get_item(item_id)
    with db() as c:
        c.execute("UPDATE items SET deleted_at=NULL WHERE id=?", (item_id,))
    return {"ok": True}


@app.put("/api/items/{item_id}/memo", dependencies=[Depends(require_auth)])
def api_set_memo(item_id: str, data: MemoIn):
    """设置/清除备注（重命名）。列表里设置了备注优先显示备注名；空串=清除。"""
    _get_item(item_id)
    memo = (data.memo or "").strip()[:200]
    with db() as c:
        c.execute("UPDATE items SET memo=? WHERE id=?", (memo, item_id))
    return {"ok": True, "memo": memo}


@app.delete("/api/trash/{item_id}", dependencies=[Depends(require_auth)])
def api_purge(item_id: str):
    """彻底删除：文件 + 记录一起干掉，不可恢复。"""
    row = _get_item(item_id)
    if not row["deleted_at"]:
        raise HTTPException(status_code=400, detail="条目不在回收站")
    with db() as c:
        _purge_rows(c, [row])
    return {"ok": True}


@app.post("/api/trash/empty", dependencies=[Depends(require_auth)])
def api_trash_empty():
    with db() as c:
        rows = c.execute(
            "SELECT id, stored_name FROM items WHERE deleted_at IS NOT NULL"
        ).fetchall()
        removed = _purge_rows(c, rows)
    if removed:
        log.info("trash: purged %d items", removed)
    return {"ok": True, "removed": removed}


# ---------- 应用内自更新 ----------
# 约定：升级包经 /api/files 上传，文件名必须是 Toss-vX.Y.Z.exe
UPDATE_NAME_RE = re.compile(r"^Toss-v(\d+(?:\.\d+)+)\.exe$", re.IGNORECASE)


def _ver_tuple(v: str):
    return tuple(int(x) for x in v.split("."))


def _md5_file(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def find_update_item():
    """在未删除条目里找版本号大于当前的 Toss-vX.Y.Z.exe，返回最新一个。"""
    cur = _ver_tuple(VERSION)
    best = None
    with db() as c:
        rows = c.execute(
            "SELECT id, orig_name, stored_name, size FROM items "
            "WHERE deleted_at IS NULL AND kind='file' ORDER BY created_at DESC"
        ).fetchall()
    for r in rows:
        m = UPDATE_NAME_RE.match(r["orig_name"] or "")
        if not m:
            continue
        ver = m.group(1)
        if _ver_tuple(ver) <= cur:
            continue
        if best is None or _ver_tuple(ver) > _ver_tuple(best["version"]):
            best = {"id": r["id"], "name": r["orig_name"], "version": ver,
                    "stored_name": r["stored_name"], "size": r["size"]}
    return best


@app.get("/api/update/check", dependencies=[Depends(require_auth)])
def api_update_check():
    upd = find_update_item()
    return {
        "version": VERSION,
        "available": bool(upd),
        "update_version": upd["version"] if upd else None,
        "item_id": upd["id"] if upd else None,
    }


@app.post("/api/update/apply", dependencies=[Depends(require_auth)])
def api_update_apply():
    """一键更新：换包 + 重启。Windows 下运行中的 exe 不可覆盖但可重命名。"""
    if not getattr(sys, "frozen", False):
        raise HTTPException(status_code=400, detail="开发模式（非 exe）不支持自更新")
    upd = find_update_item()
    if not upd:
        raise HTTPException(status_code=404, detail="没有待更新的版本包")
    src = FILES_DIR / upd["stored_name"]
    if not src.exists():
        raise HTTPException(status_code=404, detail="更新包文件丢失，请重新推送")
    exe = Path(sys.executable).resolve()
    stage = exe.parent / "Toss-new.exe"
    old = exe.parent / "Toss-old.exe"
    try:
        shutil.copyfile(src, stage)
        if stage.stat().st_size != src.stat().st_size or _md5_file(stage) != _md5_file(src):
            raise HTTPException(status_code=500, detail="更新包复制校验失败，已中止")
        old.unlink(missing_ok=True)
        exe.rename(old)      # 运行中的 exe 可重命名
        stage.rename(exe)    # 磁盘上已是新版
    except HTTPException:
        raise
    except Exception:
        log.error("self-update failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="换包失败，详见 data/toss.log")
    # 直接拉起新 exe（带启动延迟，等旧进程释放端口）；新进程启动时负责清理 Toss-old.exe
    # PYINSTALLER_RESET_ENVIRONMENT=1（官方公开变量，专为应用重启场景）：
    # 清掉继承的 _PYI_* 私有变量，让新 exe 被当作全新顶层实例，
    # 否则 6.22 引导器会把"旧 Toss 进程 spawn 新 Toss.exe"误判为篡改而弹窗拒启
    child_env = dict(os.environ, TOSS_START_DELAY="3", PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(
        [str(exe)], cwd=str(exe.parent), env=child_env, close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    log.info("self-update: swapping to v%s (item %s)", upd["version"], upd["id"])
    threading.Timer(1.0, os._exit, args=(0,)).start()  # 先让响应发出去再退出
    return {"ok": True, "update_version": upd["version"]}


@app.post("/api/cleanup", dependencies=[Depends(require_auth)])
def api_cleanup():
    return {"ok": True, "removed": cleanup_expired()}


@app.get("/api/info", dependencies=[Depends(require_auth)])
def api_info():
    with db() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM items WHERE deleted_at IS NULL").fetchone()["n"]
        total = c.execute(
            "SELECT COALESCE(SUM(size),0) AS s FROM items WHERE deleted_at IS NULL"
        ).fetchone()["s"]
        trash_n = c.execute(
            "SELECT COUNT(*) AS n FROM items WHERE deleted_at IS NOT NULL"
        ).fetchone()["n"]
    return {
        "name": APP_NAME, "version": VERSION, "port": PORT,
        "ips": local_ips(), "retention_days": get_retention_days(),
        "item_count": n, "total_size": total, "trash_count": trash_n,
        "has_password": has_password(),
    }


class RetentionIn(BaseModel):
    days: int


@app.get("/api/settings/retention", dependencies=[Depends(require_auth)])
def api_get_retention():
    return {"days": get_retention_days(), "min": RETENTION_MIN, "max": RETENTION_MAX}


@app.put("/api/settings/retention", dependencies=[Depends(require_auth)])
def api_set_retention(data: RetentionIn):
    days = max(RETENTION_MIN, min(RETENTION_MAX, data.days))
    set_setting("retention_days", str(days))
    return {"ok": True, "days": get_retention_days()}


# 静态资源不强缓存：升级后普通刷新即新版，根治"升级了界面没变"的 Ctrl+F5 问题
@app.middleware("http")
async def _no_cache_static(request: Request, call_next):
    resp = await call_next(request)
    if not request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def _cleanup_old_exe():
    """自更新交接：旧进程退出后其映像解锁，负责删掉 Toss-old.exe。"""
    if not getattr(sys, "frozen", False):
        return
    old = Path(sys.executable).resolve().parent / "Toss-old.exe"
    for _ in range(20):
        try:
            if old.exists():
                old.unlink()
            return
        except OSError:
            time.sleep(0.5)


def main() -> None:
    _cleanup_old_exe()
    delay = int(os.environ.get("TOSS_START_DELAY", "0") or 0)
    if delay:
        time.sleep(delay)  # 自更新交接：等旧进程退出释放端口
    log.info("Toss v%s starting on 0.0.0.0:%s, data=%s", VERSION, PORT, DATA_DIR)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        raise
