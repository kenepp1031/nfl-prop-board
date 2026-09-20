"""Shared plumbing: a disk-cached HTTP fetch. No third-party HTTP stack --
plain urllib, same as the rest of the pipeline."""
from __future__ import annotations

import gzip
import io
import json
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).parent
CACHE_DIR = APP_DIR / "cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


def cached_fetch(name: str, url: str, max_age_hours: float,
                 gzipped: bool = False, headers: dict | None = None) -> str:
    """Return the body of `url`, reusing cache/<name> when it is younger than
    `max_age_hours`. On a network failure any existing cached copy is served
    rather than letting the whole board go down for one stale file."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / name

    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
        return path.read_text(encoding="utf-8")

    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
        if gzipped:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        text = raw.decode("utf-8", "replace")
    except Exception:
        if path.exists():
            return path.read_text(encoding="utf-8")
        raise

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return text


def cached_json(name: str, max_age_hours: float, build):
    """Disk memo for something we assemble ourselves rather than download in
    one piece -- the prop offers, which take dozens of API calls to collect.

    Same contract as cached_fetch: a fresh copy on disk short-circuits the
    work, and if `build` raises we serve a stale copy rather than take the
    whole board down. A restart, or a second viewer, costs a file read
    instead of a minute of paging.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / name

    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass                                  # truncated write; rebuild it

    try:
        data = build()
    except Exception:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data
