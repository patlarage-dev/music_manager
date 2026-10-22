"""Music Manager: local inventory, reversible operations and OpenSubsonic bridge."""

from __future__ import annotations
import asyncio
import ctypes
import errno
import sys
import base64
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256, md5
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import random
import re
import secrets
import shutil
import sqlite3
import threading
import time
from urllib.parse import urlsplit
import uuid

import httpx
import mutagen
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

STATE = Path(os.getenv("STATE_DIR", "/data"))
MEDIA = Path(os.getenv("MEDIA_ROOT", "/media"))
ROOTS = {
    z: MEDIA / d
    for z, d in [
        ("Bibliothèque", "music"),
        ("Téléchargements", "incoming"),
        ("Quarantaine", "quarantine"),
    ]
}
NAV = os.getenv("NAVIDROME_URL", "http://navidrome:4533").rstrip("/")
PUBLIC_NAV = os.getenv("NAVIDROME_PUBLIC_URL", "http://100.120.247.35:4533")
AUDIO = {
    ".flac",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".aiff",
    ".aif",
    ".alac",
    ".wma",
}
MUTEX = threading.RLock()
SCAN_LOCK = threading.Lock()
MB_LOCK = threading.Lock()
SCAN = {"running": False, "processed": 0, "errors": [], "lastScan": None}
MB_LAST = 0.0
LOG = logging.getLogger("music-manager")


def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    connection = sqlite3.connect(STATE / "manager.db", timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init():
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "covers").mkdir(exist_ok=True)
    with db() as c:
        c.executescript(
            """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY, album_id TEXT, zone TEXT, rel TEXT, mtime REAL, size INTEGER, digest TEXT, payload TEXT);
        CREATE INDEX IF NOT EXISTS tracks_album ON tracks(album_id);
        CREATE TABLE IF NOT EXISTS track_identity(id TEXT PRIMARY KEY, album_id TEXT);
        CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, created TEXT, action TEXT, source TEXT, target TEXT, status TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, expires REAL, payload TEXT, used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, admin INTEGER, expires REAL, credentials TEXT);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, expires REAL, payload TEXT);
        CREATE TABLE IF NOT EXISTS release_refs(album_id TEXT PRIMARY KEY, payload TEXT);
        """
        )
        columns = {r[1] for r in c.execute("PRAGMA table_info(sessions)")}
        if "credentials" not in columns:
            c.execute("ALTER TABLE sessions ADD COLUMN credentials TEXT")
        # Journal recovery knows whether a move or an atomic tag replacement was interrupted.
        for op in c.execute(
            "SELECT * FROM operations WHERE status IN ('pending','restoring')"
        ).fetchall():
            source, target = Path(op["source"]), Path(op["target"])
            if op["action"] == "metadata":
                try:
                    recover_metadata(op["id"], target)
                    status = "restored"
                    error = "Copie originale restaurée après interruption"
                except Exception:
                    status = "needs_review"
                    error = "Interruption : copies conservées, vérification manuelle requise avant restauration"
            elif op["status"] == "restoring":
                status = (
                    "restored" if source.exists() and not target.exists() else "applied"
                )
                error = "Reprise de restauration après interruption"
            else:
                status = (
                    "applied" if target.exists() and not source.exists() else "failed"
                )
                error = "Reprise après interruption"
            c.execute(
                "UPDATE operations SET status=?,error=? WHERE id=?",
                (status, error, op["id"]),
            )
    os.chmod(STATE / "manager.db", 0o600)


def setting(key, default=None):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def save_setting(key, value):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value))
        )


def safe_path(zone: str, rel: str, exists=True):
    if zone not in ROOTS:
        raise HTTPException(400, "Espace inconnu.")
    if (
        not rel
        or rel.startswith("/")
        or "\\" in rel
        or any(p in ("..", ".", "") or p.startswith(".") for p in rel.split("/"))
    ):
        raise HTTPException(400, "Chemin non autorisé.")
    root = ROOTS[zone]
    if root.is_symlink():
        raise HTTPException(400, "Racine symbolique interdite.")
    target = root / rel
    for candidate in [target, *target.parents]:
        if candidate == root:
            break
        if candidate.is_symlink():
            raise HTTPException(400, "Les liens symboliques ne sont pas autorisés.")
    if not target.resolve().is_relative_to(root.resolve()):
        raise HTTPException(400, "Chemin hors bibliothèque.")
    if exists and not target.exists():
        raise HTTPException(404, "Cet élément n’existe plus. Relancez l’analyse.")
    return target


def rename_noreplace(source: Path, target: Path):
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
        if result:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
    else:
        if target.exists():
            raise FileExistsError(str(target))
        os.rename(source, target)


def file_hash(path: Path):
    result = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def atomic_copy(source: Path, target: Path):
    temporary = target.parent / (".music-manager-" + uuid.uuid4().hex)
    try:
        shutil.copy2(source, temporary)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_manifest(path: Path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def recover_metadata(oid: str, backup: Path, only_after=False):
    if backup.parent != STATE / "backups" or backup.name != oid or backup.is_symlink():
        raise ValueError("Invalid backup")
    manifest = json.loads((backup / "manifest.json").read_text())
    for item in manifest:
        path = Path(item["path"])
        copy = Path(item["backup"])
        if not copy.is_relative_to(backup) or not any(
            path.is_relative_to(root) for root in ROOTS.values()
        ):
            raise ValueError("Invalid path")
        if any(p.is_symlink() for p in [path, *path.parents]) or copy.is_symlink():
            raise ValueError("Symlink")
        allowed = (
            {item.get("after")} if only_after else {item["before"], item.get("after")}
        )
        if (
            file_hash(copy) != item["before"]
            or not path.is_file()
            or file_hash(path) not in allowed
        ):
            raise ValueError("Changed file")
    for item in manifest:
        atomic_copy(Path(item["backup"]), Path(item["path"]))


def identifier(value):
    return sha256(value.encode()).hexdigest()[:24]


def clean_name(value):
    value = value.strip()
    if (
        not value
        or len(value) > 180
        or value in (".", "..")
        or value.startswith(".")
        or any(ch in value for ch in "/\\\0\r\n")
    ):
        raise HTTPException(
            400, "Nom invalide. Utilisez un nom simple, sans barre oblique."
        )
    return value


def tag(tags, key, default=""):
    values = tags.get(key, []) if tags else []
    return str(values[0]) if values else default


def number(value):
    try:
        return int(str(value).split("/")[0])
    except (ValueError, TypeError):
        return 0


def picture(path: Path, album_id: str):
    cache = STATE / "covers" / f"{album_id}.jpg"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return True
    try:
        audio = mutagen.File(path)
        images = getattr(audio, "pictures", [])
        content = images[0].data if images else None
        if not content and audio and audio.tags:
            for key, value in audio.tags.items():
                if str(key).startswith("APIC"):
                    content = value.data
                    break
            if not content and "covr" in audio.tags:
                content = bytes(audio.tags["covr"][0])
            if not content and "metadata_block_picture" in audio.tags:
                from mutagen.flac import Picture

                content = Picture(
                    base64.b64decode(audio.tags["metadata_block_picture"][0])
                ).data
        if content is None:
            for name in (
                "cover.jpg",
                "folder.jpg",
                "front.jpg",
                "cover.png",
                "folder.png",
            ):
                candidate = path.parent / name
                if (
                    candidate.is_file()
                    and not candidate.is_symlink()
                    and candidate.stat().st_size < 20_000_000
                ):
                    content = candidate.read_bytes()
                    break
        if not content:
            return False
        with Image.open(BytesIO(content)) as image:
            image.thumbnail((600, 600))
            image.convert("RGB").save(cache, "JPEG", quality=85)
        return True
    except Exception:
        return False


def scan():
    if not SCAN_LOCK.acquire(blocking=False):
        return
    SCAN.update(running=True, processed=0, errors=[])
    try:
        with MUTEX:
            with db() as c:
                old = {r["id"]: dict(r) for r in c.execute("SELECT * FROM tracks")}
                identities = {
                    r["id"]: r["album_id"]
                    for r in c.execute("SELECT * FROM track_identity")
                }
            records = []
            grouped = defaultdict(list)
            for zone, root in ROOTS.items():
                if not root.is_dir() or root.is_symlink():
                    SCAN["errors"].append(f"{zone} : répertoire indisponible.")
                    continue
                for directory, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".")
                        and not (Path(directory) / d).is_symlink()
                    ]
                    for name in files:
                        if (
                            name.startswith(".")
                            or Path(name).suffix.lower() not in AUDIO
                        ):
                            continue
                        path = Path(directory) / name
                        try:
                            rel = path.relative_to(root).as_posix()
                            safe_path(zone, rel)
                            stat = path.stat()
                            tid = identifier(zone + "/" + rel)
                            previous = old.get(tid)
                            if (
                                previous
                                and previous["mtime"] == stat.st_mtime
                                and previous["size"] == stat.st_size
                            ):
                                item = json.loads(previous["payload"])
                                digest = previous["digest"]
                            else:
                                audio = mutagen.File(path, easy=True)
                                if audio is None:
                                    raise ValueError("format audio illisible")
                                artist = (
                                    tag(audio, "albumartist")
                                    or tag(audio, "artist")
                                    or (
                                        path.parent.parent.name
                                        if path.parent != root
                                        else "Artiste inconnu"
                                    )
                                )
                                title = tag(audio, "album") or path.parent.name
                                aid = identities.get(tid) or identifier(
                                    zone
                                    + "/"
                                    + path.parent.relative_to(root).as_posix()
                                    + "/"
                                    + artist
                                    + "/"
                                    + title
                                )
                                info = audio.info
                                total = tag(audio, "totaltracks") or tag(
                                    audio, "tracktotal"
                                )
                                if not total:
                                    raw = tag(audio, "tracknumber")
                                    total = raw.split("/")[-1] if "/" in raw else ""
                                item = {
                                    "id": tid,
                                    "albumId": aid,
                                    "zone": zone,
                                    "rel": rel,
                                    "title": tag(audio, "title") or path.stem,
                                    "artist": tag(audio, "artist") or artist,
                                    "albumArtist": artist,
                                    "album": title,
                                    "year": number(tag(audio, "date")[:4]),
                                    "genre": tag(audio, "genre") or "Non renseigné",
                                    "number": number(tag(audio, "tracknumber")),
                                    "disc": number(tag(audio, "discnumber")) or 1,
                                    "total": number(total),
                                    "duration": round(
                                        float(getattr(info, "length", 0)), 1
                                    ),
                                    "format": path.suffix[1:].upper(),
                                    "bitrate": round(
                                        getattr(info, "bitrate", 0) / 1000
                                    ),
                                    "sampleRate": getattr(info, "sample_rate", 0),
                                    "bitDepth": getattr(info, "bits_per_sample", 0),
                                    "size": stat.st_size,
                                    "mbid": tag(audio, "musicbrainz_albumid"),
                                    "artistMbid": tag(
                                        audio, "musicbrainz_albumartistid"
                                    )
                                    or tag(audio, "musicbrainz_artistid"),
                                }
                                fingerprint = sha256()
                                with path.open("rb") as stream:
                                    for chunk in iter(
                                        lambda: stream.read(1024 * 1024), b""
                                    ):
                                        fingerprint.update(chunk)
                                digest = fingerprint.hexdigest()
                            records.append(
                                (
                                    tid,
                                    item["albumId"],
                                    zone,
                                    rel,
                                    stat.st_mtime,
                                    stat.st_size,
                                    digest,
                                    json.dumps(item),
                                )
                            )
                            grouped[item["albumId"]].append(item)
                            SCAN["processed"] += 1
                        except Exception as error:
                            LOG.warning("Scan %s: %s", path, type(error).__name__)
                            if len(SCAN["errors"]) < 30:
                                SCAN["errors"].append(
                                    f"{name} : fichier illisible ou accès refusé."
                                )
            indexed = []
            with db() as c:
                refs = {
                    r["album_id"]: json.loads(r["payload"])
                    for r in c.execute("SELECT * FROM release_refs")
                }
            for aid, items in grouped.items():
                first = items[0]
                folder = str(Path(first["rel"]).parent)
                # Per-disc totals, never assume a single-disc edition.
                discs = defaultdict(list)
                for t in items:
                    discs[t["disc"]].append(t)
                expected = sum(max(t["total"] for t in ts) for ts in discs.values())
                positions = {(t["disc"], t["number"]) for t in items if t["number"]}
                ref = refs.get(aid)
                missing = []
                if ref:
                    expected = len(ref["tracks"])
                    missing = [
                        t
                        for t in ref["tracks"]
                        if (t["disc"], t["number"]) not in positions
                    ]
                else:
                    for disc, ts in discs.items():
                        for n in range(1, max(t["total"] for t in ts) + 1):
                            if (disc, n) not in positions:
                                missing.append(
                                    {
                                        "disc": disc,
                                        "number": n,
                                        "title": f"Piste {n} (titre non identifié)",
                                    }
                                )
                cover = picture(safe_path(first["zone"], first["rel"]), aid)
                value = {
                    "id": aid,
                    "artist": first["albumArtist"],
                    "title": first["album"],
                    "year": first["year"],
                    "genre": first["genre"],
                    "tracks": len(items),
                    "expected": expected or None,
                    "format": ", ".join(sorted({i["format"] for i in items})),
                    "zone": first["zone"],
                    "folder": folder,
                    "cover": f"/api/covers/{aid}" if cover else None,
                    "duration": round(sum(i["duration"] for i in items)),
                    "mbid": (ref or {}).get("id") or first["mbid"],
                    "artistMbid": first["artistMbid"],
                    "missing": missing,
                    "reference": ref,
                    "completeness": (
                        "incomplete"
                        if missing
                        else (
                            "complete"
                            if expected and len(positions) >= expected
                            else "unknown"
                        )
                    ),
                }
                indexed.append((aid, json.dumps(value)))
            with db() as c:
                c.execute("DELETE FROM tracks")
                c.executemany("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)", records)
                c.execute("DELETE FROM albums")
                c.executemany("INSERT INTO albums VALUES (?,?)", indexed)
                save_time = now()
                c.execute(
                    "INSERT OR REPLACE INTO settings VALUES (?,?)",
                    ("lastScan", json.dumps(save_time)),
                )
            SCAN["lastScan"] = save_time
    except Exception:
        LOG.exception("Scan failed")
        SCAN["errors"].append("Analyse interrompue. Le précédent index est conservé.")
    finally:
        SCAN["running"] = False
        SCAN_LOCK.release()


def start_scan():
    if not SCAN["running"]:
        threading.Thread(target=scan, daemon=True).start()


def periodic():
    while True:
        time.sleep(60)
        minutes = int(setting("scanMinutes", 0))
        last = setting("lastScan")
        if (
            minutes
            and last
            and time.time() - datetime.fromisoformat(last).timestamp() > minutes * 60
        ):
            start_scan()


@asynccontextmanager
async def lifespan(app):
    init()
    start_scan()
    threading.Thread(target=periodic, daemon=True).start()
    yield


app = FastAPI(title="Music Manager", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        if request.headers.get("x-music-manager") != "1" or (
            origin and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return Response("Origine de la requête non autorisée.", status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = (
        "no-store"
        if not request.url.path.startswith("/api/covers/")
        else "private, max-age=3600"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def user(request: Request, admin=False):
    token = request.cookies.get("mm_session", "")
    with db() as c:
        row = c.execute(
            "SELECT * FROM sessions WHERE token=? AND expires>?",
            (sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(
            401, "Connectez-vous à Navidrome dans Paramètres pour cette action."
        )
    if admin and not row["admin"]:
        raise HTTPException(
            403,
            "Un compte administrateur Navidrome est requis pour modifier les fichiers.",
        )
    return dict(row)


async def nav_call(endpoint, params=None, credentials=None):
    credentials = credentials or setting("navCredentials")
    if not credentials:
        raise HTTPException(409, "Connectez votre compte Navidrome dans Paramètres.")
    values = {
        **credentials,
        "v": "1.16.1",
        "c": "MusicManager",
        "f": "json",
        **(params or {}),
    }
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            result = await client.get(f"{NAV}/rest/{endpoint}", params=values)
            result.raise_for_status()
            payload = result.json().get("subsonic-response", {})
        if payload.get("status") != "ok":
            raise HTTPException(
                502,
                "Navidrome a refusé la demande. Vérifiez le compte et ses permissions.",
            )
        return payload
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Navidrome est indisponible. Réessayez plus tard.")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1000)


@app.post("/api/session")
async def login(body: Login, response: Response):
    salt = secrets.token_hex(16)
    credentials = {
        "u": body.username,
        "s": salt,
        "t": md5((body.password + salt).encode()).hexdigest(),
    }
    await nav_call("ping", credentials=credentials)
    account = (await nav_call("getUser", {"username": body.username}, credentials))[
        "user"
    ]
    # Equivalent Subsonic credentials remain server-side in the private state volume.
    save_setting("navCredentials", credentials)
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)",
            (
                sha256(token.encode()).hexdigest(),
                body.username,
                int(account.get("adminRole", False)),
                time.time() + 86400 * 7,
                json.dumps(credentials),
            ),
        )
    response.set_cookie(
        "mm_session", token, httponly=True, samesite="strict", max_age=86400 * 7
    )
    return {"username": body.username, "admin": account.get("adminRole", False)}


@app.delete("/api/session")
def logout(request: Request, response: Response):
    token = request.cookies.get("mm_session", "")
    with db() as c:
        c.execute(
            "DELETE FROM sessions WHERE token=?", (sha256(token.encode()).hexdigest(),)
        )
    response.delete_cookie("mm_session")
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok"}


def all_albums():
    with db() as c:
        return [json.loads(r[0]) for r in c.execute("SELECT payload FROM albums")]


def album(aid):
    with db() as c:
        row = c.execute("SELECT payload FROM albums WHERE id=?", (aid,)).fetchone()
    if not row:
        raise HTTPException(404, "Album absent de l’index. Relancez l’analyse.")
    return json.loads(row[0])


def album_tracks(aid):
    with db() as c:
        rows = c.execute(
            "SELECT payload FROM tracks WHERE album_id=?", (aid,)
        ).fetchall()
    return sorted(
        [json.loads(r[0]) for r in rows],
        key=lambda t: (t["disc"], t["number"], t["title"]),
    )


@app.get("/api/status")
async def status(request: Request):
    values = all_albums()
    library = [a for a in values if a["zone"] == "Bibliothèque"]
    try:
        session = user(request)
    except HTTPException:
        session = None
    credentials = setting("navCredentials")
    connected = False
    if credentials:
        try:
            await nav_call("ping")
            connected = True
        except HTTPException:
            pass
    disk = shutil.disk_usage(MEDIA) if MEDIA.exists() else None
    return {
        "scan": {**SCAN, "lastScan": setting("lastScan")},
        "stats": {
            "artists": len({a["artist"] for a in library}),
            "albums": len(library),
            "tracks": sum(a["tracks"] for a in library),
            "quarantine": sum(a["zone"] == "Quarantaine" for a in values),
            "incoming": sum(a["zone"] == "Téléchargements" for a in values),
            "incomplete": sum(a["completeness"] == "incomplete" for a in library),
        },
        "navidrome": {
            "configured": bool(credentials),
            "connected": connected,
            "username": credentials["u"] if credentials else None,
            "url": PUBLIC_NAV,
        },
        "session": (
            {"username": session["username"], "admin": bool(session["admin"])}
            if session
            else None
        ),
        "disk": {"free": disk.free, "total": disk.total} if disk else None,
        "scanMinutes": setting("scanMinutes", 0),
        "roots": {
            z: str(p).replace(str(MEDIA), "/mnt/media", 1) for z, p in ROOTS.items()
        },
    }


@app.post("/api/scan")
def rescan():
    start_scan()
    return {"started": True}


class Preferences(BaseModel):
    scanMinutes: int = Field(ge=0, le=10080)


@app.put("/api/preferences")
def preferences(body: Preferences, request: Request):
    user(request, admin=True)
    if body.scanMinutes not in (0, 60, 1440, 10080):
        raise HTTPException(400, "Fréquence non autorisée.")
    save_setting("scanMinutes", body.scanMinutes)
    return {"ok": True}


@app.get("/api/albums")
def list_albums(
    q: str = "",
    zone: str = "Bibliothèque",
    genre: str = "",
    offset: int = 0,
    limit: int = 60,
    sort: str = "artist",
    attention: bool = False,
    format: str = "",
    state: str = "",
):
    values = all_albums()
    values = [
        a
        for a in values
        if (not zone or a["zone"] == zone)
        and (not genre or a["genre"] == genre)
        and (not format or format.upper() in a["format"].split(", "))
        and (not state or a["completeness"] == state)
        and q.casefold() in f"{a['artist']} {a['title']}".casefold()
    ]
    if attention:
        values = [a for a in values if a["completeness"] != "complete"]
    values.sort(
        key=lambda a: (a["artist"].casefold(), a["year"], a["title"].casefold())
    )
    return {
        "items": values[max(0, offset) : max(0, offset) + min(max(limit, 1), 100)],
        "total": len(values),
        "genres": sorted({a["genre"] for a in all_albums()}),
        "formats": sorted({f for a in all_albums() for f in a["format"].split(", ")}),
    }


@app.get("/api/albums/{aid}")
def detail(aid: str):
    return {**album(aid), "songs": album_tracks(aid)}


@app.get("/api/covers/{aid}")
def cover(aid: str):
    if not re.fullmatch("[a-f0-9]{24}", aid):
        raise HTTPException(404)
    path = STATE / "covers" / f"{aid}.jpg"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/tracks/{tid}/stream")
def stream(tid: str):
    with db() as c:
        row = c.execute("SELECT zone,rel FROM tracks WHERE id=?", (tid,)).fetchone()
    if not row:
        raise HTTPException(404, "Piste introuvable.")
    return FileResponse(safe_path(row["zone"], row["rel"]))


@app.get("/api/explorer")
def explorer(zone: str = "Téléchargements", path: str = ""):
    if zone not in ROOTS:
        raise HTTPException(400, "Espace inconnu.")
    folder = safe_path(zone, path) if path else ROOTS[zone]
    if folder.is_symlink() or not folder.is_dir():
        raise HTTPException(404, "Dossier indisponible.")
    items = []
    for p in sorted(
        folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())
    ):
        if p.name.startswith(".") or p.is_symlink():
            continue
        rel = p.relative_to(ROOTS[zone]).as_posix()
        items.append(
            {
                "name": p.name,
                "path": rel,
                "directory": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else None,
                "trackId": (
                    identifier(zone + "/" + rel) if p.suffix.lower() in AUDIO else None
                ),
            }
        )
    return {"items": items, "path": path, "zone": zone}


@app.get("/api/duplicates")
def duplicates():
    with db() as c:
        rows = c.execute("SELECT digest,payload FROM tracks").fetchall()
    hashes = defaultdict(list)
    names = defaultdict(list)
    for row in rows:
        t = json.loads(row["payload"])
        hashes[row["digest"]].append(t)
        key = (t["artist"].casefold().strip(), t["title"].casefold().strip())
        names[key].append(t)
    exact = [{"type": "exact", "tracks": ts} for ts in hashes.values() if len(ts) > 1]
    ambiguous = [
        {"type": "ambiguous", "tracks": ts}
        for ts in names.values()
        if len(ts) > 1 and len({t["size"] for t in ts}) > 1
    ]
    return {"items": (exact + ambiguous)[:100], "total": len(exact) + len(ambiguous)}


class Operation(BaseModel):
    albumIds: list[str] = Field(min_length=1, max_length=20)
    action: str
    destinationZone: str = "Bibliothèque"
    newName: str = ""


def snapshot(path):
    if path.is_symlink():
        raise HTTPException(400, "Les liens symboliques ne sont pas autorisés.")
    if path.is_file():
        st = path.stat()
        return [[path.name, st.st_size, st.st_mtime_ns]]
    if not path.is_dir():
        raise HTTPException(400, "Fichier ou dossier indisponible.")
    result = []
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            child = Path(directory) / name
            if child.is_symlink():
                raise HTTPException(
                    400,
                    "Un lien symbolique est présent dans cet album. Opération refusée.",
                )
        for name in files:
            child = Path(directory) / name
            st = child.stat()
            result.append([str(child.relative_to(path)), st.st_size, st.st_mtime_ns])
    return sorted(result)


@app.post("/api/operations/preview")
def preview(body: Operation, request: Request):
    user(request, admin=True)
    if body.action not in ("trash", "move", "rename"):
        raise HTTPException(400, "Opération inconnue.")
    if body.action == "rename" and len(body.albumIds) != 1:
        raise HTTPException(400, "Renommez un seul album à la fois.")
    with MUTEX:
        plan = []
        sources = set()
        targets = set()
        with db() as c:
            compilation_folders = {
                Path(r["source"]).parent
                for r in c.execute(
                    "SELECT source FROM operations WHERE action='move_file'"
                )
            }
        for aid in dict.fromkeys(body.albumIds):
            a = album(aid)
            # A compilation/download playlist can contain several logical albums.
            # Move only the indexed files belonging to the selected album in that case.
            shared_folder = (
                a["folder"] == "."
                or ROOTS[a["zone"]] / a["folder"] in compilation_folders
                or any(
                    other["id"] != aid
                    and other["zone"] == a["zone"]
                    and (
                        other["folder"] == a["folder"]
                        or Path(other["folder"]).is_relative_to(Path(a["folder"]))
                    )
                    for other in all_albums()
                )
            )
            if body.action == "move" and shared_folder:
                if body.destinationZone not in ROOTS:
                    raise HTTPException(400, "Destination inconnue.")
                if body.destinationZone == a["zone"]:
                    raise HTTPException(
                        400, "Choisissez un autre espace pour déplacer ces fichiers."
                    )

                def component(value):
                    value = re.sub(r"[/\\\x00\r\n]", "_", value).strip()[:180]
                    return clean_name(
                        value
                        if value
                        and value not in (".", "..")
                        and not value.startswith(".")
                        else "_" + value.lstrip(".")
                    )

                songs = album_tracks(aid)
                if not songs:
                    raise HTTPException(
                        409, "Aucune piste indexée pour cet album. Relancez l’analyse."
                    )
                for song in songs:
                    source = safe_path(a["zone"], song["rel"])
                    if not source.is_file():
                        raise HTTPException(
                            409, "Une piste n’est plus un fichier. Relancez l’analyse."
                        )
                    target = safe_path(
                        body.destinationZone,
                        f"{component(a['artist'])}/{component(a['title'])}/{source.name}",
                        False,
                    )
                    if source in sources or target in targets or target.exists():
                        raise HTTPException(
                            409,
                            "La destination existe déjà. Aucun fichier ne sera écrasé.",
                        )
                    sources.add(source)
                    targets.add(target)
                    plan.append(
                        {
                            "source": str(source),
                            "target": str(target),
                            "snapshot": snapshot(source),
                            "album": a["title"],
                            "zone": a["zone"],
                            "folder": song["rel"],
                            "fileOnly": True,
                        }
                    )
                continue
            source = safe_path(a["zone"], a["folder"])
            if any(
                source == p or source.is_relative_to(p) or p.is_relative_to(source)
                for p in sources
            ):
                raise HTTPException(
                    400,
                    "Plusieurs albums partagent ce dossier. Traitez-le manuellement.",
                )
            shared = [
                other
                for other in all_albums()
                if other["id"] != aid
                and other["zone"] == a["zone"]
                and (
                    other["folder"] == a["folder"]
                    or Path(other["folder"]).is_relative_to(Path(a["folder"]))
                )
            ]
            if shared:
                raise HTTPException(
                    400,
                    "Ce dossier contient plusieurs albums. Opération automatique refusée.",
                )
            if body.action == "trash":
                target = (
                    ROOTS["Quarantaine"]
                    / ".music-manager-trash"
                    / str(uuid.uuid4())
                    / source.name
                )
            elif body.action == "rename":
                target = safe_path(
                    a["zone"],
                    str(Path(a["folder"]).parent / clean_name(body.newName)),
                    False,
                )
            else:
                if body.destinationZone not in ROOTS:
                    raise HTTPException(400, "Destination inconnue.")
                target = safe_path(
                    body.destinationZone,
                    f"{clean_name(a['artist'])}/{clean_name(source.name)}",
                    False,
                )
            if target.exists() or target in targets:
                raise HTTPException(
                    409, "La destination existe déjà. Aucun fichier ne sera écrasé."
                )
            if source == target or target.is_relative_to(source):
                raise HTTPException(400, "Destination invalide.")
            sources.add(source)
            targets.add(target)
            plan.append(
                {
                    "source": str(source),
                    "target": str(target),
                    "snapshot": snapshot(source),
                    "album": a["title"],
                    "zone": a["zone"],
                    "folder": a["folder"],
                }
            )
        token = secrets.token_urlsafe(24)
        with db() as c:
            c.execute(
                "INSERT INTO plans(id,expires,payload) VALUES (?,?,?)",
                (
                    token,
                    time.time() + 300,
                    json.dumps({"action": body.action, "items": plan}),
                ),
            )
    return {
        "token": token,
        "action": body.action,
        "items": [
            {
                "album": p["album"],
                "source": p["source"].replace(str(MEDIA), "/mnt/media", 1),
                "target": p["target"].replace(str(MEDIA), "/mnt/media", 1),
                "files": len(p["snapshot"]),
            }
            for p in plan
        ],
        "expiresIn": 300,
    }


class Apply(BaseModel):
    token: str


@app.post("/api/operations/apply")
def apply(body: Apply, request: Request):
    user(request, admin=True)
    with MUTEX:
        with db() as c:
            row = c.execute(
                "SELECT * FROM plans WHERE id=? AND used=0 AND expires>?",
                (body.token, time.time()),
            ).fetchone()
            if not row:
                raise HTTPException(
                    409, "Prévisualisation expirée ou déjà utilisée. Recommencez."
                )
            plan = json.loads(row["payload"])
            if "action" not in plan or "items" not in plan:
                raise HTTPException(400, "Prévisualisation de déplacement requise.")
            for item in plan["items"]:
                source = safe_path(item["zone"], item["folder"])
                if (
                    snapshot(source) != item["snapshot"]
                    or Path(item["target"]).exists()
                ):
                    raise HTTPException(
                        409, "Les fichiers ont changé. Recommencez la prévisualisation."
                    )
            c.execute("UPDATE plans SET used=1 WHERE id=?", (body.token,))
        completed = []
        try:
            for item in plan["items"]:
                source = Path(item["source"])
                target = Path(item["target"])
                if any(p.is_symlink() for p in [target, *target.parents]):
                    raise OSError("Lien symbolique")
                target.parent.mkdir(parents=True, exist_ok=True)
                oid = str(uuid.uuid4())
                with db() as c:
                    c.execute(
                        "INSERT INTO operations VALUES (?,?,?,?,?,?,?)",
                        (
                            oid,
                            now(),
                            "move_file" if item.get("fileOnly") else plan["action"],
                            str(source),
                            str(target),
                            "pending",
                            None,
                        ),
                    )
                # Same filesystem is required. EXDEV fails without removing the original.
                rename_noreplace(source, target)
                completed.append((oid, source, target))
                with db() as c:
                    c.execute(
                        "UPDATE operations SET status=? WHERE id=?", ("applied", oid)
                    )
        except OSError:
            for oid, source, target in reversed(completed):
                try:
                    if not source.exists():
                        rename_noreplace(target, source)
                    with db() as c:
                        c.execute(
                            "UPDATE operations SET status=? WHERE id=?",
                            ("rolled_back", oid),
                        )
                except OSError:
                    LOG.exception("Rollback requires review: %s", oid)
            with db() as c:
                c.execute(
                    "UPDATE operations SET status='failed',error='Transfert refusé ou interrompu' WHERE status='pending'"
                )
            raise HTTPException(
                409,
                "Opération interrompue. Consultez l’historique ; les fichiers déjà transférés ont fait l’objet d’une tentative de restauration.",
            )
    start_scan()
    return {"ok": True, "count": len(completed)}


@app.get("/api/history")
def history():
    with db() as c:
        rows = c.execute(
            "SELECT * FROM operations ORDER BY created DESC LIMIT 100"
        ).fetchall()
    return {
        "items": [
            {
                **dict(r),
                "source": r["source"].replace(str(MEDIA), "/mnt/media", 1),
                "target": r["target"].replace(str(MEDIA), "/mnt/media", 1),
            }
            for r in rows
        ]
    }


@app.post("/api/history/{oid}/restore")
def restore(oid: str, request: Request):
    user(request, admin=True)
    with MUTEX:
        with db() as c:
            row = c.execute(
                "SELECT * FROM operations WHERE id=? AND status='applied'", (oid,)
            ).fetchone()
            if not row:
                raise HTTPException(409, "Cette opération ne peut plus être restaurée.")
            source, target = Path(row["source"]), Path(row["target"])
            if row["action"] == "metadata":
                try:
                    # Validate before marking the journal as restoring.
                    manifest = json.loads((target / "manifest.json").read_text())
                    for item in manifest:
                        path = Path(item["path"])
                        if not path.is_file() or file_hash(path) != item.get("after"):
                            raise ValueError("Changed")
                    c.execute(
                        "UPDATE operations SET status='restoring' WHERE id=?", (oid,)
                    )
                    c.commit()
                    recover_metadata(oid, target)
                except Exception:
                    raise HTTPException(
                        409,
                        "Restauration refusée : un fichier a changé ou une copie est indisponible. Les copies sont conservées sur le serveur.",
                    )
                c.execute("UPDATE operations SET status='restored' WHERE id=?", (oid,))
                start_scan()
                return {"ok": True}
            # These paths are generated by the backend, but still revalidate after restart.
            for p in (source, target):
                if not any(p.is_relative_to(root) for root in ROOTS.values()):
                    raise HTTPException(400, "Chemin de restauration invalide.")
                if any(part.is_symlink() for part in [p, *p.parents]):
                    raise HTTPException(400, "Lien symbolique détecté.")
            if source.exists():
                raise HTTPException(
                    409, "Le chemin d’origine est occupé. Aucun fichier écrasé."
                )
            if not (target.is_dir() or target.is_file()):
                raise HTTPException(409, "L’élément à restaurer est introuvable.")
            source.parent.mkdir(parents=True, exist_ok=True)
            c.execute("UPDATE operations SET status='restoring' WHERE id=?", (oid,))
            c.commit()
            try:
                rename_noreplace(target, source)
            except OSError:
                raise HTTPException(
                    409, "Restauration impossible. Vérifiez les droits et les disques."
                )
            c.execute("UPDATE operations SET status='restored' WHERE id=?", (oid,))
    start_scan()
    return {"ok": True}


async def musicbrainz(path, params):
    key = path + json.dumps(params, sort_keys=True)
    with db() as c:
        row = c.execute(
            "SELECT payload FROM cache WHERE key=? AND expires>?", (key, time.time())
        ).fetchone()
    if row:
        return json.loads(row[0])

    def fetch():
        global MB_LAST
        with MB_LOCK:
            delay = 1.1 - (time.monotonic() - MB_LAST)
            if delay > 0:
                time.sleep(delay)
            MB_LAST = time.monotonic()
            with httpx.Client(
                timeout=25,
                headers={
                    "User-Agent": "MusicManager/0.2 (personal-library; https://github.com/patlarage-dev/music_manager)"
                },
            ) as client:
                result = client.get(
                    "https://musicbrainz.org/ws/2/" + path,
                    params={"fmt": "json", **params},
                )
                result.raise_for_status()
                return result.json()

    try:
        result = await asyncio.to_thread(fetch)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "MusicBrainz est indisponible. Réessayez plus tard.")
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (key, time.time() + 86400 * 7, json.dumps(result)),
        )
    return result


def lucene(value):
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r"\\\1", value)


@app.get("/api/albums/{aid}/matches")
async def matches(aid: str):
    a = album(aid)
    result = await musicbrainz(
        "release",
        {
            "query": f'artist:"{lucene(a["artist"])}" AND release:"{lucene(a["title"])}"',
            "limit": 12,
        },
    )
    if not result.get("releases"):
        normalized = re.sub(
            r"\s*[\[(].*?(?:remaster|deluxe|edition).*?[\])]",
            "",
            a["title"],
            flags=re.I,
        ).strip()
        if normalized and normalized != a["title"]:
            result = await musicbrainz(
                "release",
                {
                    "query": f'artist:"{lucene(a["artist"])}" AND release:"{lucene(normalized)}"',
                    "limit": 12,
                },
            )
    return {
        "items": [
            {
                "id": r["id"],
                "title": r["title"],
                "date": r.get("date", ""),
                "country": r.get("country", ""),
                "tracks": sum(m.get("track-count", 0) for m in r.get("media", [])),
                "disambiguation": r.get("disambiguation", ""),
                "artist": "".join(
                    x.get("name", "") + x.get("joinphrase", "")
                    for x in r.get("artist-credit", [])
                ),
            }
            for r in result.get("releases", [])
        ]
    }


class Identify(BaseModel):
    mbid: str


@app.post("/api/albums/{aid}/identify")
async def identify(aid: str, body: Identify):
    album(aid)
    try:
        mbid = str(uuid.UUID(body.mbid))
    except ValueError:
        raise HTTPException(400, "Identifiant MusicBrainz invalide.")
    result = await musicbrainz("release/" + mbid, {"inc": "recordings"})
    tracks = []
    for medium in result.get("media", []):
        for t in medium.get("tracks", []):
            tracks.append(
                {
                    "disc": medium.get("position", 1),
                    "number": t.get("position", 0),
                    "title": t.get("title") or t.get("recording", {}).get("title", ""),
                }
            )
    if not tracks:
        raise HTTPException(
            400, "Cette édition ne contient aucune liste de pistes exploitable."
        )
    ref = {
        "id": mbid,
        "title": result["title"],
        "date": result.get("date", ""),
        "tracks": tracks,
    }
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO release_refs VALUES (?,?)", (aid, json.dumps(ref))
        )
    start_scan()
    return ref


@app.get("/api/discover")
async def discover(artist: str):
    own = all_albums()
    found = []
    source = "Collection locale : genres partagés"
    if setting("navCredentials"):
        try:
            artists = (
                (
                    await nav_call(
                        "search3",
                        {
                            "query": artist,
                            "artistCount": 20,
                            "albumCount": 0,
                            "songCount": 0,
                        },
                    )
                )
                .get("searchResult3", {})
                .get("artist", [])
            )
            match = next(
                (a for a in artists if a["name"].casefold() == artist.casefold()), None
            )
            if match:
                info = (
                    await nav_call(
                        "getArtistInfo2",
                        {"id": match["id"], "count": 15, "includeNotPresent": "true"},
                    )
                ).get("artistInfo2", {})
                for a in info.get("similarArtist", []):
                    found.append(
                        {
                            "name": a["name"],
                            "mbid": a.get("musicBrainzId"),
                            "present": any(
                                x["artist"].casefold() == a["name"].casefold()
                                for x in own
                            ),
                        }
                    )
                if found:
                    source = "Artistes similaires fournis par Navidrome"
        except HTTPException:
            pass
    if not found:
        genres = {
            a["genre"]
            for a in own
            if a["artist"] == artist and a["genre"] != "Non renseigné"
        }
        found = [
            {"name": name, "present": True}
            for name in sorted(
                {
                    a["artist"]
                    for a in own
                    if a["artist"] != artist and a["genre"] in genres
                }
            )
        ]
    return {"items": found, "source": source, "followed": setting("followed", [])}


class Follow(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@app.post("/api/follow")
def follow(body: Follow):
    names = setting("followed", [])
    if body.name in names:
        names.remove(body.name)
    else:
        names.append(body.name)
    save_setting("followed", names[:500])
    return {"items": names}


@app.get("/api/radio")
def radio(artist: str):
    values = [a for a in all_albums() if a["zone"] == "Bibliothèque"]
    genres = {
        a["genre"]
        for a in values
        if a["artist"] == artist and a["genre"] != "Non renseigné"
    }
    candidates = [a for a in values if a["artist"] == artist or a["genre"] in genres]
    tracks = [t for a in candidates for t in album_tracks(a["id"])]
    random.shuffle(tracks)
    return {
        "items": tracks[:30],
        "source": "Artiste et genres de votre bibliothèque uniquement",
    }


PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls"}
PLAYLIST_LIMIT = 2000


def playlist_sources():
    result = {}
    for zone in ("Téléchargements", "Bibliothèque"):
        root = ROOTS[zone]
        if not root.is_dir() or root.is_symlink():
            continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and not (Path(directory) / d).is_symlink()
            ]
            for name in files:
                if (
                    name.startswith(".")
                    or Path(name).suffix.lower() not in PLAYLIST_EXTENSIONS
                ):
                    continue
                path = Path(directory) / name
                rel = path.relative_to(root).as_posix()
                try:
                    safe_path(zone, rel)
                    if not path.is_file():
                        continue
                except HTTPException:
                    continue
                pid = identifier(zone + "/" + rel)
                result[pid] = {
                    "id": pid,
                    "name": (
                        path.parent.name
                        if path.stem.casefold() == "playlist" and path.parent != root
                        else path.stem
                    ),
                    "zone": zone,
                    "rel": rel,
                    "path": path,
                }
    return result


def read_playlist(path):
    if path.stat().st_size > 2_000_000:
        raise HTTPException(400, "Playlist trop volumineuse (2 Mo maximum).")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if path.suffix.lower() == ".m3u8":
            raise HTTPException(400, "Ce fichier M3U8 n’est pas encodé en UTF-8.")
        text = raw.decode("cp1252")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if path.suffix.lower() == ".pls":
        numbered = []
        for line in lines:
            match = re.match(r"File(\d+)=(.*)", line, re.I)
            if match:
                numbered.append((int(match[1]), match[2].strip()))
        entries = [value for _, value in sorted(numbered)]
    else:
        entries = [line for line in lines if not line.startswith("#")]
    if not entries or len(entries) > PLAYLIST_LIMIT:
        raise HTTPException(
            400, f"Une playlist doit contenir entre 1 et {PLAYLIST_LIMIT} pistes."
        )
    return entries


def resolve_playlist(pid):
    source = playlist_sources().get(pid)
    if not source:
        raise HTTPException(
            404, "Fichier de playlist introuvable. Actualisez la liste."
        )
    entries = read_playlist(source["path"])
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM tracks")]
        moves = [
            dict(r)
            for r in c.execute(
                "SELECT source,target FROM operations WHERE status='applied' AND action IN ('move','move_file','rename') ORDER BY created DESC"
            )
        ]
    by_path = {ROOTS[r["zone"]] / r["rel"]: r for r in rows}
    library_hashes = defaultdict(list)
    for r in rows:
        if r["zone"] == "Bibliothèque":
            library_hashes[r["digest"]].append(r)

    def allowed(path):
        return any(path.is_relative_to(root) for root in ROOTS.values()) and not any(
            p.is_symlink() for p in [path, *path.parents]
        )

    def current(row):
        path = ROOTS[row["zone"]] / row["rel"]
        if not allowed(path) or not path.is_file():
            return False
        st = path.stat()
        return st.st_size == row["size"] and st.st_mtime == row["mtime"]

    items = []
    for entry in entries:
        normalized = entry.replace("\\", "/")
        # Never open network addresses or arbitrary host paths from a playlist.
        if "://" in normalized or re.match(r"^[A-Za-z]:", normalized):
            items.append({"entry": entry, "status": "unsupported", "track": None})
            continue
        candidates = []
        if normalized.startswith("/music/"):
            candidates.append(ROOTS["Bibliothèque"] / normalized[len("/music/") :])
        elif normalized.startswith("/mnt/media/"):
            candidates.append(MEDIA / normalized[len("/mnt/media/") :])
        else:
            candidates.append(
                Path(normalized)
                if normalized.startswith("/")
                else source["path"].parent / normalized
            )
        path = Path(os.path.abspath(candidates[0]))
        row = None
        visited = set()
        for _ in range(32):
            if not allowed(path) or path in visited:
                break
            visited.add(path)
            if path in by_path and current(by_path[path]):
                row = by_path[path]
                break
            # An existing, unindexed file must be analysed before matching it.
            if path.exists():
                break
            move = next(
                (
                    m
                    for m in moves
                    if path == Path(m["source"])
                    or path.is_relative_to(Path(m["source"]))
                ),
                None,
            )
            if not move:
                break
            path = Path(move["target"]) / path.relative_to(Path(move["source"]))
        if row:
            if row["zone"] != "Bibliothèque":
                row = next(
                    (r for r in library_hashes[row["digest"]] if current(r)), row
                )
            status = "ready" if row["zone"] == "Bibliothèque" else "incoming"
            track = json.loads(row["payload"])
        else:
            status, track = "missing", None
        items.append({"entry": entry, "status": status, "track": track})
    return {k: v for k, v in source.items() if k != "path"} | {
        "items": items,
        "total": len(items),
        "ready": sum(i["status"] == "ready" for i in items),
    }


@app.get("/api/playlist-files")
def playlist_files():
    return {
        "items": [
            {k: v for k, v in source.items() if k != "path"}
            for source in playlist_sources().values()
        ]
    }


@app.get("/api/playlist-files/{pid}")
def playlist_file(pid: str):
    with MUTEX:
        return resolve_playlist(pid)


class ImportPlaylist(BaseModel):
    sourceId: str
    name: str = Field(min_length=1, max_length=120)


def session_credentials(request):
    account = user(request)
    if not account.get("credentials"):
        raise HTTPException(401, "Reconnectez votre compte Navidrome.")
    return json.loads(account["credentials"])


@app.post("/api/playlist-files/import")
async def import_playlist(body: ImportPlaylist, request: Request):
    credentials = session_credentials(request)
    with MUTEX:
        resolved = resolve_playlist(body.sourceId)
    if resolved["ready"] != resolved["total"]:
        raise HTTPException(
            409,
            "Certaines pistes sont absentes de Bibliothèque. Déplacez-les depuis l’Explorateur puis relancez l’analyse. Aucun import partiel n’a été effectué.",
        )
    key = identifier(credentials["u"] + "/" + body.sourceId)
    imported = setting("playlistImports", {})
    previous = imported.get(key)
    result = await create_navidrome_playlist(
        Playlist(
            name=body.name, trackIds=[i["track"]["id"] for i in resolved["items"]]
        ),
        credentials,
        playlist_id=previous,
    )
    with MUTEX:
        imported = setting("playlistImports", {})
        imported[key] = result["playlist"]["id"]
        save_setting("playlistImports", imported)
    return result


@app.get("/api/navidrome/playlists")
async def nav_playlists(request: Request):
    credentials = session_credentials(request)
    response = await nav_call("getPlaylists", credentials=credentials)
    return {
        "items": response.get("playlists", {}).get("playlist", []),
        "username": credentials["u"],
        "url": PUBLIC_NAV,
    }


class Playlist(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trackIds: list[str] = Field(min_length=1, max_length=PLAYLIST_LIMIT)


@app.post("/api/navidrome/playlist")
async def playlist(body: Playlist, request: Request):
    account = user(request)
    credentials = (
        json.loads(account["credentials"]) if account.get("credentials") else None
    )
    if not credentials:
        raise HTTPException(401, "Reconnectez votre compte Navidrome.")
    return await create_navidrome_playlist(body, credentials)


async def nav_download_digest(song_id: str, credentials):
    parameters = {
        **credentials,
        "id": song_id,
        "v": "1.16.1",
        "c": "MusicManager",
        "f": "json",
    }
    digest = sha256()
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            async with client.stream(
                "GET", NAV + "/rest/download", params=parameters
            ) as result:
                result.raise_for_status()
                async for chunk in result.aiter_bytes():
                    digest.update(chunk)
    except httpx.HTTPError:
        raise HTTPException(
            502,
            "Vérification audio Navidrome impossible. Vérifiez la connexion et le droit de téléchargement du compte.",
        )
    return digest.hexdigest()


async def create_navidrome_playlist(body: Playlist, credentials, playlist_id=None):
    async def call(endpoint, params=None):
        return await nav_call(endpoint, params, credentials)

    with db() as c:
        rows = c.execute(
            "SELECT id,digest,mtime,size,payload FROM tracks WHERE zone=?",
            ("Bibliothèque",),
        ).fetchall()
    requested = set(body.trackIds)
    rows = [r for r in rows if r["id"] in requested]
    own = {r["id"]: json.loads(r["payload"]) for r in rows}
    if any(tid not in own for tid in body.trackIds):
        raise HTTPException(
            409, "La sélection contient une piste absente de la bibliothèque."
        )
    fingerprints = {r["id"]: r["digest"] for r in rows}
    for row in rows:
        if row["id"] in body.trackIds:
            t = own[row["id"]]
            stat = safe_path(t["zone"], t["rel"]).stat()
            if stat.st_size != row["size"] or stat.st_mtime != row["mtime"]:
                raise HTTPException(
                    409,
                    "Un fichier a changé. Relancez l’analyse avant de créer la playlist.",
                )
    # Navidrome may expose virtual paths. When paths differ, compare original audio bytes.
    desired = {own[tid]["rel"]: tid for tid in body.trackIds}
    mapping = {}
    offset = 0
    while offset < 100000:
        values = (
            (
                await call(
                    "getAlbumList2",
                    {"type": "alphabeticalByName", "size": 500, "offset": offset},
                )
            )
            .get("albumList2", {})
            .get("album", [])
        )
        if not values:
            break
        for a in values:
            if not any(
                t["album"] == a.get("name")
                for t in own.values()
                if t["id"] in body.trackIds
            ):
                continue
            songs = (
                (await call("getAlbum", {"id": a["id"]}))
                .get("album", {})
                .get("song", [])
            )
            for song in songs:
                path = song.get("path", "").lstrip("/")
                for rel, tid in desired.items():
                    if tid in mapping:
                        continue
                    t = own[tid]
                    exact_path = path == rel or path == "music/" + rel
                    same_metadata = (
                        song.get("title", "").casefold() == t["title"].casefold()
                        and song.get("artist", "").casefold() == t["artist"].casefold()
                        and abs(float(song.get("duration", -999)) - t["duration"]) <= 2
                        and int(song.get("size", -1)) == t["size"]
                    )
                    if not exact_path and not same_metadata:
                        continue
                    key = "nav-file:" + NAV + ":" + song["id"] + ":" + fingerprints[tid]
                    with db() as c:
                        cached = c.execute(
                            "SELECT payload FROM cache WHERE key=? AND expires>?",
                            (key, time.time()),
                        ).fetchone()
                    matches = bool(cached)
                    if not matches:
                        matches = (
                            await nav_download_digest(song["id"], credentials)
                        ) == fingerprints[tid]
                        if matches:
                            with db() as c:
                                c.execute(
                                    "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                                    (key, time.time() + 86400 * 7, "true"),
                                )
                    if matches:
                        mapping[tid] = song["id"]
        if len(mapping) == len(set(body.trackIds)) or len(values) < 500:
            break
        offset += 500
    if any(tid not in mapping for tid in body.trackIds):
        raise HTTPException(
            409,
            "Certaines pistes ne correspondent pas aux fichiers indexés par Navidrome. Lancez son analyse puis réessayez. Aucun autre enregistrement n’a été substitué.",
        )
    song_ids = [mapping[tid] for tid in body.trackIds]
    params = {"name": body.name, "songId": song_ids}
    if playlist_id:
        params["playlistId"] = playlist_id
    result = await call("createPlaylist", params)
    created = result.get("playlist", {})
    if not created.get("id"):
        raise HTTPException(
            502, "Navidrome n’a pas confirmé la création de la playlist."
        )
    if playlist_id:
        await call("updatePlaylist", {"playlistId": created["id"], "name": body.name})
    verified = (await call("getPlaylist", {"id": created["id"]})).get("playlist", {})
    visible = (await call("getPlaylists")).get("playlists", {}).get("playlist", [])
    if [song.get("id") for song in verified.get("entry", [])] != song_ids or not any(
        p.get("id") == created["id"] for p in visible
    ):
        raise HTTPException(
            502,
            "La playlist a été envoyée, mais sa lecture dans Navidrome n’est pas confirmée. Actualisez Playlists avant de réessayer.",
        )
    return {
        "playlist": verified,
        "url": PUBLIC_NAV,
        "username": credentials["u"],
        "verified": True,
    }


@app.post("/api/navidrome/scan")
async def nav_scan(request: Request):
    account = user(request, admin=True)
    if not account.get("credentials"):
        raise HTTPException(401, "Reconnectez votre compte Navidrome.")
    return await nav_call("startScan", credentials=json.loads(account["credentials"]))


class Metadata(BaseModel):
    artist: str = Field(min_length=1, max_length=200)
    album: str = Field(min_length=1, max_length=200)
    year: str = Field(max_length=10)
    genre: str = Field(max_length=150)


@app.post("/api/albums/{aid}/metadata/preview")
def metadata_preview(aid: str, body: Metadata, request: Request):
    user(request, admin=True)
    a = album(aid)
    songs = album_tracks(aid)
    if body.year and not re.fullmatch(r"\d{4}", body.year):
        raise HTTPException(400, "L’année doit contenir quatre chiffres.")
    if any(t["format"] not in ("FLAC", "MP3", "M4A", "OGG", "OPUS") for t in songs):
        raise HTTPException(
            400,
            "Un format de cet album ne permet pas encore une écriture sûre des tags.",
        )
    changes = {}
    for key, old in [
        ("artist", a["artist"]),
        ("album", a["title"]),
        ("year", str(a["year"] or "")),
        ("genre", a["genre"] if a["genre"] != "Non renseigné" else ""),
    ]:
        value = getattr(body, key).strip()
        if value != old:
            changes[key] = {"before": [old], "after": value}
    if not changes:
        raise HTTPException(400, "Aucune modification à enregistrer.")
    folder = safe_path(a["zone"], a["folder"])
    token = secrets.token_urlsafe(24)
    payload = {
        "aid": aid,
        "zone": a["zone"],
        "folder": a["folder"],
        "songs": songs,
        "changes": changes,
        "snapshot": snapshot(folder),
    }
    with db() as c:
        c.execute(
            "INSERT INTO plans(id,expires,payload) VALUES (?,?,?)",
            (token, time.time() + 300, json.dumps(payload)),
        )
    return {"token": token, "changes": changes}


@app.post("/api/metadata/apply")
def metadata_apply(body: Apply, request: Request):
    user(request, admin=True)
    with MUTEX:
        with db() as c:
            row = c.execute(
                "SELECT * FROM plans WHERE id=? AND used=0 AND expires>?",
                (body.token, time.time()),
            ).fetchone()
            if not row:
                raise HTTPException(409, "Prévisualisation expirée. Recommencez.")
            plan = json.loads(row["payload"])
            if "changes" not in plan:
                raise HTTPException(400, "Prévisualisation de tags requise.")
            folder = safe_path(plan["zone"], plan["folder"])
            if snapshot(folder) != plan["snapshot"]:
                raise HTTPException(409, "Les fichiers ont changé. Recommencez.")
            needed = sum(t["size"] for t in plan["songs"])
            if shutil.disk_usage(STATE).free < needed * 2 + 100_000_000:
                raise HTTPException(
                    409, "Espace insuffisant pour une copie de sécurité complète."
                )
            c.execute("UPDATE plans SET used=1 WHERE id=?", (body.token,))
        oid = str(uuid.uuid4())
        backup = STATE / "backups" / oid
        backup.mkdir(parents=True)
        manifest = []
        try:
            staging = backup / "staged"
            staging.mkdir()
            for t in plan["songs"]:
                path = safe_path(t["zone"], t["rel"])
                copy = backup / t["id"]
                shutil.copy2(path, copy)
                manifest.append(
                    {
                        "path": str(path),
                        "backup": str(copy),
                        "before": file_hash(copy),
                        "staged": str(staging / (t["id"] + path.suffix)),
                    }
                )
            atomic_manifest(backup / "manifest.json", manifest)
            with db() as c:
                c.execute(
                    "INSERT INTO operations VALUES (?,?,?,?,?,?,?)",
                    (oid, now(), "metadata", str(folder), str(backup), "pending", None),
                )
            # Prepare every new file before replacing any original; journal all expected digests.
            for item in manifest:
                staged = Path(item["staged"])
                shutil.copy2(item["backup"], staged)
                audio = mutagen.File(staged, easy=True)
                if audio is None:
                    raise ValueError("Fichier illisible")
                for key, change in plan["changes"].items():
                    tag_key = {
                        "artist": "albumartist",
                        "album": "album",
                        "year": "date",
                        "genre": "genre",
                    }[key]
                    if change["after"]:
                        audio[tag_key] = [change["after"]]
                    elif tag_key in audio:
                        del audio[tag_key]
                audio.save()
                item["after"] = file_hash(staged)
            atomic_manifest(backup / "manifest.json", manifest)
            if snapshot(folder) != plan["snapshot"]:
                raise ValueError("Files changed during preparation")
            for item in manifest:
                path = Path(item["path"])
                if file_hash(path) != item["before"]:
                    raise ValueError("Concurrent file change")
                atomic_copy(Path(item["staged"]), path)
            with db() as c:
                c.execute("UPDATE operations SET status='applied' WHERE id=?", (oid,))
                c.executemany(
                    "INSERT OR REPLACE INTO track_identity VALUES (?,?)",
                    [(t["id"], plan["aid"]) for t in plan["songs"]],
                )
            shutil.rmtree(staging)
        except Exception:
            try:
                recover_metadata(oid, backup)
                status = "rolled_back"
                error = "Écriture interrompue, copie restaurée"
            except Exception:
                status = "needs_review"
                error = "Fichier modifié extérieurement : copie conservée, contrôle manuel requis"
            with db() as c:
                c.execute(
                    "UPDATE operations SET status=?,error=? WHERE id=?",
                    (status, error, oid),
                )
            LOG.exception("Metadata write failed")
            raise HTTPException(
                409,
                "Écriture interrompue. Consultez l’historique et les copies de sécurité avant de réessayer.",
            )
    start_scan()
    return {"ok": True}


@app.get("/api/artists")
def artists():
    return {
        "items": sorted(
            {a["artist"] for a in all_albums() if a["zone"] == "Bibliothèque"},
            key=str.casefold,
        )
    }
