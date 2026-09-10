"""Best-effort, bounded GPS result cache shared by separate Finder processes."""

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import time


LOCATION_TTL = 30 * 24 * 60 * 60
MAX_ENTRIES = 2048


def cache_directory():
    override = os.environ.get("WATERMARK_GPS_CACHE_DIR")
    shared = os.environ.get("WATERMARK_CACHE_DIR")
    if override == "off" or shared == "off":
        return None
    if override:
        return Path(override).expanduser()
    if shared:
        return Path(shared).expanduser() / "gps"
    base = (Path.home() / "Library/Caches" if sys.platform == "darwin" else
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")))
    return base / "watermark-tool" / "gps"


def cached_location(key, location=None):
    """Read a live success or store one; unavailable/corrupt caches never block export."""
    directory = cache_directory()
    if directory is None:
        return None
    digest = sha256(json.dumps(["nominatim-v1", *key]).encode()).hexdigest()
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        database = directory / "locations.sqlite3"
        with closing(sqlite3.connect(database, timeout=0.2)) as connection:
            database.chmod(0o600)
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS locations "
                    "(key TEXT PRIMARY KEY, location TEXT NOT NULL, expires REAL NOT NULL)"
                )
                now = time.time()
                if location is None:
                    row = connection.execute(
                        "SELECT location, expires FROM locations WHERE key = ? AND expires > ?",
                        (digest, now),
                    ).fetchone()
                    return row
                if location:
                    connection.execute("DELETE FROM locations WHERE expires <= ?", (now,))
                    connection.execute(
                        "INSERT OR REPLACE INTO locations VALUES (?, ?, ?)",
                        (digest, location, now + LOCATION_TTL),
                    )
                    connection.execute(
                        "DELETE FROM locations WHERE key NOT IN "
                        "(SELECT key FROM locations ORDER BY expires DESC LIMIT ?)",
                        (MAX_ENTRIES,),
                    )
    except (OSError, sqlite3.Error):
        pass
    return None
