"""Small operator CLI: `uv run python -m app.cli <command>`."""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import ROOT, get_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wakeful")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hash-password", help="print a bcrypt hash for ADMIN_PASSWORD_HASH")
    sub.add_parser("gen-keys", help="print fresh SECRET_KEY and TOKEN_ENCRYPTION_KEY values")
    sub.add_parser("seed", help="seed defaults (and mock data in mock mode)")
    b = sub.add_parser("backup", help="copy the SQLite database to backups/")
    b.add_argument("--dir", default=str(ROOT / "backups"))
    sub.add_parser("sync", help="run one Fanvue sync now")
    sub.add_parser("pause", help="emergency stop: pause all automation")
    a = p.parse_args(argv)

    if a.cmd == "hash-password":
        from app.security import hash_password

        pw = getpass.getpass("Password: ")
        if len(pw) < 10:
            print("Use at least 10 characters.", file=sys.stderr)
            return 1
        print(hash_password(pw))
    elif a.cmd == "gen-keys":
        import secrets

        print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
        print(f"TOKEN_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    elif a.cmd == "seed":
        from app.main import bootstrap

        bootstrap()
        print("seeded")
    elif a.cmd == "backup":
        s = get_settings()
        if not s.is_sqlite:
            print("For PostgreSQL use pg_dump (see docs/deployment.md).", file=sys.stderr)
            return 1
        src = Path(s.database_url.removeprefix("sqlite:///"))
        dest_dir = Path(a.dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        import sqlite3

        dest = dest_dir / f"wakeful-{datetime.now():%Y%m%d-%H%M%S}.db"
        with sqlite3.connect(src) as s_conn, sqlite3.connect(dest) as d_conn:
            s_conn.backup(d_conn)  # consistent online backup
        print(dest)
    elif a.cmd == "sync":
        from app.db import session_scope
        from app.services import sync

        with session_scope() as db:
            print(sync.sync(db).__dict__)
    elif a.cmd == "pause":
        from app.db import session_scope
        from app.settings_store import SafetySettings, load, save

        with session_scope() as db:
            s_doc = load(db, SafetySettings)
            s_doc.automation_paused = True
            save(db, s_doc)
        print("automation paused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
