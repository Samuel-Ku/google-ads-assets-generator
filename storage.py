"""Private SQLite metadata and bounded, application-owned media storage."""
import os
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApiError(Exception):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.message, self.status, self.details = message, status, details


class Storage:
    def __init__(self, root, quota_bytes, reserve_bytes, recover=True):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media, self.temp = self.root / "media", self.root / "tmp"
        self.media.mkdir(exist_ok=True, mode=0o700)
        self.temp.mkdir(exist_ok=True, mode=0o700)
        for directory in (self.root, self.media, self.temp):
            os.chmod(directory, 0o700)
        self.database = self.root / "studio.sqlite3"
        self.quota_bytes, self.reserve_bytes = quota_bytes, reserve_bytes
        self.lock, self.last_cleanup = threading.RLock(), 0.0
        self.reserved_bytes = 0
        self.initialize(recover)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.database, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self, recover):
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','editor')), active INTEGER NOT NULL DEFAULT 1,
 auth_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS brands (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL, secondary_color TEXT NOT NULL,
 text_color TEXT NOT NULL, font_family TEXT NOT NULL, tone TEXT NOT NULL, logo_asset_id TEXT,
 font_asset_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaigns (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, brand_id TEXT NOT NULL REFERENCES brands(id), brief TEXT NOT NULL,
 state TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id), updated_by INTEGER NOT NULL REFERENCES users(id));
CREATE TABLE IF NOT EXISTS versions (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE, version INTEGER NOT NULL,
 name TEXT NOT NULL, brand_id TEXT NOT NULL, brief TEXT NOT NULL, state TEXT NOT NULL,
 author_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, PRIMARY KEY(campaign_id,version));
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, mime TEXT NOT NULL,
 width INTEGER, height INTEGER, size INTEGER NOT NULL, campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
 brand_id TEXT REFERENCES brands(id), parent_id TEXT, created_at TEXT NOT NULL, expired INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS exports (
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
 path TEXT NOT NULL, filename TEXT NOT NULL, size INTEGER NOT NULL, file_count INTEGER NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, expired INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
 status TEXT NOT NULL, method TEXT NOT NULL DEFAULT 'smart', error TEXT, output_asset_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shared_templates (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, recipe TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)));
CREATE INDEX IF NOT EXISTS assets_campaign ON assets(campaign_id);
CREATE INDEX IF NOT EXISTS exports_campaign ON exports(campaign_id);
CREATE INDEX IF NOT EXISTS campaigns_expiry ON campaigns(expires_at);
""")
            if 'method' not in {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute("ALTER TABLE jobs ADD COLUMN method TEXT NOT NULL DEFAULT 'smart'")
            if recover:
                db.execute("UPDATE jobs SET status='error',error=?,updated_at=? WHERE status IN ('queued','running')",
                           ("Przetwarzanie przerwano podczas ponownego uruchomienia serwera. Spróbuj ponownie.", now_iso()))
        os.chmod(self.database, 0o600)
        if recover:
            for path in self.temp.iterdir():
                if path.is_file() and not path.is_symlink():
                    path.unlink()

    def secret(self):
        path = self.root / "session-secret"
        with self.lock:
            if not path.exists():
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w") as f:
                        f.write(secrets.token_hex(48))
                except FileExistsError:
                    pass
            return path.read_text().strip()

    def path(self, filename):
        candidate = self.media / filename
        if candidate.parent != self.media or candidate.is_symlink():
            raise ApiError("Nieprawidłowa ścieżka pliku.")
        return candidate

    def capacity(self):
        with self.lock:
            used = sum(p.stat().st_size for folder in (self.media,self.temp)
                       for p in folder.iterdir() if p.is_file() and not p.is_symlink())
            # History is intentionally persistent and must consume the same finite budget.
            for database_file in (self.database, Path(str(self.database)+'-wal'), Path(str(self.database)+'-shm')):
                try:
                    if not database_file.is_symlink():
                        used += database_file.stat().st_size
                except FileNotFoundError:
                    pass  # SQLite removes WAL/SHM when its final connection closes.
            free = shutil.disk_usage(self.root).free
            return dict(used_bytes=used, quota_bytes=self.quota_bytes, free_bytes=free,
                        reserve_bytes=self.reserve_bytes, reserved_bytes=self.reserved_bytes,
                        can_upload=used+self.reserved_bytes<self.quota_bytes and free>self.reserve_bytes+self.reserved_bytes,
                        retention_days=7)

    def ensure_capacity(self, amount):
        cap = self.capacity()
        if cap["used_bytes"]+self.reserved_bytes+amount > self.quota_bytes:
            raise ApiError("Brak miejsca w limicie aplikacji. Usuń niepotrzebną kampanię lub poczekaj na wygaśnięcie plików.",507)
        if cap["free_bytes"]-self.reserved_bytes-amount < self.reserve_bytes:
            raise ApiError("Za mało wolnego miejsca na serwerze. Nowe pliki są chwilowo zablokowane.",507)

    def write(self, filename, content):
        with self.lock:
            self.ensure_capacity(len(content))
            temporary = self.temp / secrets.token_hex(16)
            try:
                with temporary.open("xb") as f:
                    os.chmod(temporary,0o600)
                    f.write(content)
                os.replace(temporary,self.path(filename))
            finally:
                temporary.unlink(missing_ok=True)

    def cleanup(self, force=False):
        with self.lock:
            if not force and time.monotonic()-self.last_cleanup < 60:
                return
            cutoff=now_iso()
            with self.db() as db:
                files=db.execute("SELECT a.id,a.path FROM assets a JOIN campaigns c ON c.id=a.campaign_id WHERE c.expires_at<=? AND a.expired=0",(cutoff,)).fetchall()
                for row in files:
                    self.path(row["path"]).unlink(missing_ok=True)
                    db.execute("UPDATE assets SET expired=1 WHERE id=?",(row["id"],))
                for row in db.execute("SELECT id,path FROM exports WHERE expires_at<=? AND expired=0",(cutoff,)).fetchall():
                    self.path(row["path"]).unlink(missing_ok=True)
                    db.execute("UPDATE exports SET expired=1 WHERE id=?",(row["id"],))
            self.last_cleanup=time.monotonic()
