import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import time
import wave
import pytest
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "manager", Path(__file__).parents[1] / "app.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
REAL_START_SCAN = m.start_scan


@pytest.fixture()
def client(tmp_path, monkeypatch):
    media = (tmp_path / "media").resolve()
    state = (tmp_path / "state").resolve()
    media.mkdir()
    state.mkdir()
    roots = {
        z: media / d
        for z, d in [
            ("Bibliothèque", "music"),
            ("Téléchargements", "incoming"),
            ("Quarantaine", "quarantine"),
        ]
    }
    for p in roots.values():
        p.mkdir()
    monkeypatch.setattr(m, "FILE_MANAGERS", {"patrick"})
    monkeypatch.setattr(m, "MEDIA", media)
    monkeypatch.setattr(m, "STATE", state)
    monkeypatch.setattr(m, "ROOTS", roots)
    monkeypatch.setattr(m, "start_scan", lambda *args, **kwargs: None)
    m.SCAN.update(running=False, processed=0, errors=[], lastScan=None)
    m.init()
    with m.db() as c:
        c.execute(
            "INSERT INTO sessions(token,username,admin,expires) VALUES (?,?,?,?)",
            (m.sha256(b"test-token").hexdigest(), "patrick", 1, time.time() + 1000),
        )
    c = TestClient(
        m.app, headers={"X-Music-Manager": "1", "Origin": "http://testserver"}
    )
    c.cookies.set("mm_session", "test-token")
    yield c
    c.close()


def seed(zone="Téléchargements", folder="Artist/Album", name="Song.wav"):
    path = m.ROOTS[zone] / folder
    path.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path / name), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(struct.pack("<h", 500) * 8000)
    m.scan()
    return m.all_albums()[0], path


def test_indexes_real_audio_and_reuses_hash(client):
    a, path = seed()
    assert a["tracks"] == 1
    assert a["duration"] == 1
    assert a["expected"] is None
    assert a["completeness"] == "unknown"
    original = m.album_tracks(a["id"])[0]
    m.scan()
    assert m.album_tracks(a["id"])[0]["id"] == original["id"]
    assert (
        client.get(
            "/api/tracks/" + original["id"] + "/stream", headers={"Range": "bytes=0-9"}
        ).status_code
        == 206
    )


@pytest.mark.parametrize(
    "rel",
    [
        "../outside",
        "/etc/passwd",
        "Artist/../../x",
        ".hidden/a",
        "Artist\\file",
        "Artist//Album",
    ],
)
def test_rejects_escaping_and_hidden_paths(client, rel):
    with pytest.raises(m.HTTPException):
        m.safe_path("Bibliothèque", rel)


def test_symlink_is_never_followed(client, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (m.ROOTS["Bibliothèque"] / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(m.HTTPException):
        m.safe_path("Bibliothèque", "link/file", False)
    assert client.get("/api/explorer?zone=Biblioth%C3%A8que").json()["items"] == []


def test_requires_same_origin_header_and_admin(client):
    a, _ = seed()
    payload = {"albumIds": [a["id"]], "action": "trash"}
    assert (
        client.post(
            "/api/operations/preview",
            json=payload,
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert client.post("/api/operations/preview", json=payload).status_code == 401


def test_move_then_restore_preserves_content(client):
    a, path = seed()
    before = (path / "Song.wav").read_bytes()
    plan = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    )
    assert plan.status_code == 200, plan.text
    token = plan.json()["token"]
    assert path.exists()
    applied = client.post("/api/operations/apply", json={"token": token})
    assert applied.status_code == 200, applied.text
    assert not path.exists()
    op = client.get("/api/history").json()["items"][0]
    assert (
        Path(op["target"].replace("/mnt/media", str(m.MEDIA)))
        .joinpath("Song.wav")
        .read_bytes()
        == before
    )
    assert (
        client.post("/api/operations/apply", json={"token": token}).status_code == 409
    )
    restored = client.post("/api/history/" + op["id"] + "/restore", json={})
    assert restored.status_code == 200, restored.text
    assert (path / "Song.wav").read_bytes() == before


def test_collision_and_changed_source_refuse_writes(client):
    a, path = seed()
    target = m.ROOTS["Bibliothèque"] / a["artist"] / path.name
    target.mkdir(parents=True)
    payload = {"albumIds": [a["id"]], "action": "move"}
    assert client.post("/api/operations/preview", json=payload).status_code == 409
    plan = client.post(
        "/api/operations/preview", json={**payload, "action": "trash"}
    ).json()
    (path / "cover.jpg").write_bytes(b"new download")
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 409
    )
    assert path.exists()


def test_trash_is_excluded_from_scans_and_restore_refuses_collision(client):
    a, path = seed()
    plan = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "trash"}
    ).json()
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 200
    )
    m.scan()
    assert not m.all_albums()
    op = client.get("/api/history").json()["items"][0]
    path.mkdir()
    assert (
        client.post("/api/history/" + op["id"] + "/restore", json={}).status_code == 409
    )


def test_destination_symlink_added_after_preview_is_refused(client, tmp_path):
    a, path = seed()
    plan = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    ).json()
    outside = tmp_path / "outside"
    outside.mkdir()
    (m.ROOTS["Bibliothèque"] / a["artist"]).symlink_to(
        outside, target_is_directory=True
    )
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 409
    )
    assert path.exists()
    assert not list(outside.iterdir())


def test_subsonic_login_never_stores_plain_password(client, monkeypatch):
    async def nav(endpoint, params=None, credentials=None):
        assert "secret-password" not in json.dumps(credentials)
        return (
            {"user": {"adminRole": True}} if endpoint == "getUser" else {"status": "ok"}
        )

    monkeypatch.setattr(m, "nav_call", nav)
    result = client.post(
        "/api/session", json={"username": "patrick", "password": "secret-password"}
    )
    assert result.status_code == 200
    assert "HttpOnly" in result.headers["set-cookie"]
    stored = m.setting("navCredentials")
    assert set(stored) == {"u", "t", "s"}
    assert stored["u"] == "patrick"
    assert b"secret-password" not in (m.STATE / "manager.db").read_bytes()


def test_duplicates_are_real_checksums(client):
    _, path = seed()
    other = m.ROOTS["Bibliothèque"] / "Copy"
    other.mkdir()
    (other / "Song.wav").write_bytes((path / "Song.wav").read_bytes())
    m.scan()
    groups = client.get("/api/duplicates").json()["items"]
    assert groups[0]["type"] == "exact"
    assert len(groups[0]["tracks"]) == 2


def test_radio_contains_only_music_not_incoming(client):
    seed()
    assert client.get("/api/radio?artist=Artist").json()["items"] == []
    seed("Bibliothèque", "Artist/Library")
    songs = client.get("/api/radio?artist=Artist").json()["items"]
    assert songs
    assert all(t["zone"] == "Bibliothèque" for t in songs)


def test_corrupt_stream_path_cannot_escape_root(client):
    a, path = seed()
    t = m.album_tracks(a["id"])[0]
    with m.db() as c:
        c.execute("UPDATE tracks SET rel=? WHERE id=?", ("../../etc/passwd", t["id"]))
    assert client.get("/api/tracks/" + t["id"] + "/stream").status_code == 400


def test_nested_album_folder_is_not_moved_implicitly(client):
    a, path = seed(folder="Artist/Album")
    seed(folder="Artist/Album/Bonus")
    response = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "trash"}
    )
    assert response.status_code == 400
    assert path.exists()


def test_metadata_crash_recovery_restores_only_known_versions(client):
    a, path = seed()
    original = path / "Song.wav"
    before = original.read_bytes()
    oid = "interrupted-tags"
    backup = m.STATE / "backups" / oid
    backup.mkdir(parents=True)
    copy = backup / "original"
    copy.write_bytes(before)
    original.write_bytes(before + b"updated-tags")
    manifest = [
        {
            "path": str(original),
            "backup": str(copy),
            "before": m.file_hash(copy),
            "after": m.file_hash(original),
        }
    ]
    m.atomic_manifest(backup / "manifest.json", manifest)
    with m.db() as c:
        c.execute(
            "INSERT INTO operations VALUES (?,?,?,?,?,?,?)",
            (oid, m.now(), "metadata", str(path), str(backup), "pending", None),
        )
    m.init()
    assert original.read_bytes() == before
    op = client.get("/api/history").json()["items"][0]
    assert op["status"] == "restored"


def test_metadata_crash_recovery_preserves_external_edits(client):
    a, path = seed()
    original = path / "Song.wav"
    oid = "interrupted-external"
    backup = m.STATE / "backups" / oid
    backup.mkdir(parents=True)
    copy = backup / "original"
    copy.write_bytes(original.read_bytes())
    original.write_bytes(b"external edit")
    manifest = [
        {
            "path": str(original),
            "backup": str(copy),
            "before": m.file_hash(copy),
            "after": "not-the-current-hash",
        }
    ]
    m.atomic_manifest(backup / "manifest.json", manifest)
    with m.db() as c:
        c.execute(
            "INSERT INTO operations VALUES (?,?,?,?,?,?,?)",
            (oid, m.now(), "metadata", str(path), str(backup), "pending", None),
        )
    m.init()
    assert original.read_bytes() == b"external edit"
    assert copy.exists()
    assert client.get("/api/history").json()["items"][0]["status"] == "needs_review"


def test_navidrome_actions_use_the_current_session_identity(client, monkeypatch):
    credentials = {"u": "patrick", "s": "abc", "t": "def"}
    with m.db() as c:
        c.execute("UPDATE sessions SET credentials=?", (json.dumps(credentials),))
    m.save_setting("navCredentials", {"u": "another-user", "s": "x", "t": "y"})
    calls = []

    async def nav(endpoint, params=None, credentials=None):
        calls.append(credentials)
        return {"status": "ok"}

    monkeypatch.setattr(m, "nav_call", nav)
    result = client.post("/api/navidrome/scan", json={})
    assert result.status_code == 200
    assert calls[0]["u"] == "patrick"


def test_metadata_write_round_trip_on_flac_tags(client):
    folder = m.ROOTS["Bibliothèque"] / "Artist" / "Tagged"
    folder.mkdir(parents=True)
    # Small synthetic FLAC streaminfo fixture; tests tag serialization, not decoding.
    info = (
        struct.pack(">HH", 4096, 4096)
        + b"\0" * 6
        + (((8000 << 44) | (15 << 36) | 8000).to_bytes(8, "big"))
        + b"\0" * 16
    )
    path = folder / "track.flac"
    path.write_bytes(b"fLaC" + b"\x80\x00\x00\x22" + info)
    from mutagen.flac import FLAC

    tags = FLAC(path)
    tags["artist"] = "Artist"
    tags["albumartist"] = "Artist"
    tags["album"] = "Tagged"
    tags["tracknumber"] = "1"
    tags["tracktotal"] = "1"
    tags.save()
    original = path.read_bytes()
    m.scan()
    a = m.all_albums()[0]
    plan = client.post(
        "/api/albums/" + a["id"] + "/metadata/preview",
        json={"artist": "Artist", "album": "Renamed", "year": "2001", "genre": "Rock"},
    )
    assert plan.status_code == 200, plan.text
    result = client.post("/api/metadata/apply", json={"token": plan.json()["token"]})
    assert result.status_code == 200, result.text
    m.scan()
    assert m.all_albums()[0]["id"] == a["id"]
    assert m.all_albums()[0]["title"] == "Renamed"
    assert FLAC(path)["date"] == ["2001"]
    assert FLAC(path)["genre"] == ["Rock"]
    op = client.get("/api/history").json()["items"][0]
    result = client.post("/api/history/" + op["id"] + "/restore", json={})
    assert result.status_code == 200, result.text
    assert path.read_bytes() == original


def test_playlist_virtual_paths_are_matched_by_original_bytes(client, monkeypatch):
    import asyncio

    a, path = seed("Bibliothèque", "Artist/Album")
    track = m.album_tracks(a["id"])[0]
    with m.db() as c:
        digest = c.execute(
            "SELECT digest FROM tracks WHERE id=?", (track["id"],)
        ).fetchone()[0]
    created = []

    async def nav(endpoint, params=None, credentials=None):
        if endpoint == "getAlbumList2":
            return {
                "albumList2": {"album": [{"id": "nav-album", "name": track["album"]}]}
            }
        if endpoint == "getAlbum":
            return {
                "album": {
                    "song": [
                        {
                            "id": "nav-song",
                            "path": "virtual/path.mp3",
                            "title": track["title"],
                            "artist": track["artist"],
                            "duration": track["duration"],
                            "size": track["size"],
                        }
                    ]
                }
            }
        if endpoint == "createPlaylist":
            created.extend(params["songId"])
            return {"playlist": {"id": "playlist", "songCount": 1}}
        if endpoint == "getPlaylist":
            return {
                "playlist": {
                    "id": "playlist",
                    "songCount": 1,
                    "entry": [{"id": "nav-song"}],
                }
            }
        if endpoint == "getPlaylists":
            return {"playlists": {"playlist": [{"id": "playlist"}]}}
        raise AssertionError(endpoint)

    async def download(song_id, credentials):
        assert song_id == "nav-song"
        return digest

    monkeypatch.setattr(m, "nav_call", nav)
    monkeypatch.setattr(m, "nav_download_digest", download)
    result = asyncio.run(
        m.create_navidrome_playlist(
            m.Playlist(name="Local", trackIds=[track["id"]]), {"u": "patrick"}
        )
    )
    assert result["playlist"]["songCount"] == 1
    assert created == ["nav-song"]


def test_playlist_never_substitutes_same_title_with_other_audio(client, monkeypatch):
    import asyncio

    a, _ = seed("Bibliothèque", "Artist/Album")
    track = m.album_tracks(a["id"])[0]

    async def nav(endpoint, params=None, credentials=None):
        if endpoint == "getAlbumList2":
            return {"albumList2": {"album": [{"id": "album", "name": track["album"]}]}}
        if endpoint == "getAlbum":
            return {
                "album": {
                    "song": [
                        {
                            "id": "other-recording",
                            "path": "virtual/path.mp3",
                            "title": track["title"],
                            "artist": track["artist"],
                            "duration": track["duration"],
                            "size": track["size"],
                        }
                    ]
                }
            }
        raise AssertionError("No playlist should be created")

    async def download(*args):
        return "different-original-bytes"

    monkeypatch.setattr(m, "nav_call", nav)
    monkeypatch.setattr(m, "nav_download_digest", download)
    with pytest.raises(m.HTTPException) as exc:
        asyncio.run(
            m.create_navidrome_playlist(
                m.Playlist(name="Local", trackIds=[track["id"]]), {"u": "patrick"}
            )
        )
    assert exc.value.status_code == 409


def test_album_filters_are_applied_before_pagination(client):
    values = [
        ("a", "Rock", "FLAC, MP3", "incomplete"),
        ("b", "Jazz", "FLAC", "unknown"),
        ("c", "Rock", "MP3", "complete"),
    ]
    with m.db() as c:
        for aid, genre, format, state in values:
            album = {
                "id": aid,
                "artist": "Artist",
                "title": aid,
                "year": 2000,
                "genre": genre,
                "format": format,
                "completeness": state,
                "zone": "Bibliothèque",
            }
            c.execute("INSERT INTO albums VALUES (?,?)", (aid, json.dumps(album)))
    response = client.get(
        "/api/albums",
        params={"genre": "Rock", "format": "MP3", "state": "incomplete", "limit": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [a["id"] for a in payload["items"]] == ["a"]
    assert payload["formats"] == ["FLAC", "MP3"]
    assert client.get("/api/albums", params={"format": "AAC"}).json()["total"] == 0


def compilation_fixture(folder="My compilation"):
    from mutagen.flac import FLAC

    root = m.ROOTS["Téléchargements"] / folder if folder else m.ROOTS["Téléchargements"]
    root.mkdir(parents=True, exist_ok=True)
    info = (
        struct.pack(">HH", 4096, 4096)
        + b"\0" * 6
        + (((8000 << 44) | (15 << 36) | 8000).to_bytes(8, "big"))
        + b"\0" * 16
    )
    for name, artist, album in [
        ("a.flac", "Artist A", "Album A"),
        ("b.flac", "Artist B", "Album B"),
    ]:
        path = root / name
        path.write_bytes(b"fLaC" + b"\x80\x00\x00\x22" + info)
        audio = FLAC(path)
        audio["artist"] = artist
        audio["albumartist"] = artist
        audio["album"] = album
        audio["title"] = name
        audio["tracknumber"] = "1"
        audio.save()
    (root / "cover.jpg").write_bytes(b"shared cover")
    m.scan()
    return root, {a["title"]: a for a in m.all_albums()}


def test_compilation_moves_only_selected_album_files_and_restores(client):
    root, albums = compilation_fixture()
    original = (root / "a.flac").read_bytes()
    response = client.post(
        "/api/operations/preview",
        json={"albumIds": [albums["Album A"]["id"]], "action": "move"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["files"] == 1
    target = m.ROOTS["Bibliothèque"] / "Artist A" / "Album A" / "a.flac"
    assert response.json()["items"][0]["target"].endswith("/Artist A/Album A/a.flac")
    assert (
        client.post(
            "/api/operations/apply", json={"token": response.json()["token"]}
        ).status_code
        == 200
    )
    assert target.read_bytes() == original
    assert (root / "b.flac").exists()
    assert (root / "cover.jpg").exists()
    assert not (root / "a.flac").exists()
    op = client.get("/api/history").json()["items"][0]
    assert op["action"] == "move_file"
    assert (
        client.post("/api/history/" + op["id"] + "/restore", json={}).status_code == 200
    )
    assert (root / "a.flac").read_bytes() == original
    assert not target.exists()


def test_last_album_in_a_compilation_keeps_file_level_destination(client):
    root, albums = compilation_fixture()
    plan = client.post(
        "/api/operations/preview",
        json={"albumIds": [albums["Album A"]["id"]], "action": "move"},
    ).json()
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 200
    )
    m.scan()
    remaining = next(a for a in m.all_albums() if a["title"] == "Album B")
    plan = client.post(
        "/api/operations/preview",
        json={"albumIds": [remaining["id"]], "action": "move"},
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["items"][0]["target"].endswith("/Artist B/Album B/b.flac")


def test_loose_downloaded_tracks_can_be_moved(client):
    root, albums = compilation_fixture("")
    plan = client.post(
        "/api/operations/preview",
        json={"albumIds": [albums["Album A"]["id"]], "action": "move"},
    )
    assert plan.status_code == 200, plan.text
    assert (
        client.post(
            "/api/operations/apply", json={"token": plan.json()["token"]}
        ).status_code
        == 200
    )
    assert (root / "b.flac").exists()
    assert not (root / "a.flac").exists()


def test_compilation_refuses_collision_but_can_complete_an_existing_album_folder(
    client,
):
    root, albums = compilation_fixture()
    target = m.ROOTS["Bibliothèque"] / "Artist A" / "Album A"
    target.mkdir(parents=True)
    (target / "another.flac").write_bytes(b"keep existing")
    body = {"albumIds": [albums["Album A"]["id"]], "action": "move"}
    assert client.post("/api/operations/preview", json=body).status_code == 200
    (target / "a.flac").write_bytes(b"keep collision")
    assert client.post("/api/operations/preview", json=body).status_code == 409
    assert (root / "a.flac").exists()
    assert (target / "a.flac").read_bytes() == b"keep collision"


def test_compilation_batch_rolls_back_files_after_failure(client, monkeypatch):
    root, albums = compilation_fixture()
    before = {name: (root / name).read_bytes() for name in ("a.flac", "b.flac")}
    plan = client.post(
        "/api/operations/preview",
        json={"albumIds": [a["id"] for a in albums.values()], "action": "move"},
    ).json()
    original = m.rename_noreplace

    def fail_second(source, target):
        if source == root / "b.flac":
            raise OSError("test interruption")
        return original(source, target)

    monkeypatch.setattr(m, "rename_noreplace", fail_second)
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 409
    )
    for name, data in before.items():
        assert (root / name).read_bytes() == data


def playlist_source(path, text):
    path.write_text(text, encoding="utf-8-sig")
    return next(
        pid for pid, source in m.playlist_sources().items() if source["path"] == path
    )


def test_download_playlist_keeps_order_duplicates_and_reports_pending(client):
    root, albums = compilation_fixture()
    pid = playlist_source(
        root / "Mix.m3u8", "#EXTM3U\n#EXTINF:1,Artist\nb.flac\na.flac\nb.flac\n"
    )
    result = client.get("/api/playlist-files/" + pid).json()
    assert result["ready"] == 0
    assert result["total"] == 3
    assert [i["track"]["album"] for i in result["items"]] == [
        "Album B",
        "Album A",
        "Album B",
    ]
    assert all(i["status"] == "incoming" for i in result["items"])


def test_download_playlist_follows_file_moves_after_scan_and_restore(client):
    root, albums = compilation_fixture()
    pid = playlist_source(root / "Mix.m3u8", "b.flac\na.flac\n")
    plan = client.post(
        "/api/operations/preview",
        json={
            "albumIds": [a["id"] for a in albums.values()],
            "action": "move",
            "destinationZone": "Bibliothèque",
        },
    ).json()
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 200
    )
    m.scan()
    result = client.get("/api/playlist-files/" + pid).json()
    assert result["ready"] == 2
    assert [i["track"]["album"] for i in result["items"]] == ["Album B", "Album A"]
    op = client.get("/api/history").json()["items"][0]
    assert (
        client.post("/api/history/" + op["id"] + "/restore", json={}).status_code == 200
    )
    m.scan()
    assert client.get("/api/playlist-files/" + pid).json()["ready"] == 1


def test_download_playlist_follows_directory_move(client):
    a, root = seed()
    playlist_root = m.ROOTS["Téléchargements"] / "Playlists"
    playlist_root.mkdir()
    pid = playlist_source(playlist_root / "Mix.m3u", "../Artist/Album/Song.wav\n")
    plan = client.post(
        "/api/operations/preview",
        json={
            "albumIds": [a["id"]],
            "action": "move",
            "destinationZone": "Bibliothèque",
        },
    ).json()
    assert (
        client.post("/api/operations/apply", json={"token": plan["token"]}).status_code
        == 200
    )
    m.scan()
    assert client.get("/api/playlist-files/" + pid).json()["ready"] == 1


def test_playlist_never_opens_remote_outside_or_symlink_entries(client):
    root, _ = compilation_fixture()
    outside = root.parent.parent.parent / "outside.wav"
    outside.write_text("private")
    (root / "link.flac").symlink_to(outside)
    pid = playlist_source(
        root / "Mix.m3u8",
        "https://example.com/private\n../../../../outside.wav\nlink.flac\nC:\\Music\\song.flac\n",
    )
    result = client.get("/api/playlist-files/" + pid).json()
    assert result["ready"] == 0
    assert [i["status"] for i in result["items"]] == [
        "unsupported",
        "missing",
        "missing",
        "unsupported",
    ]
    assert all(i["track"] is None for i in result["items"])
    (root / "secret.m3u8").symlink_to(outside)
    assert len(client.get("/api/playlist-files").json()["items"]) == 1


def test_playlist_import_refuses_partial_and_requires_session(client, monkeypatch):
    root, _ = compilation_fixture()
    pid = playlist_source(root / "Mix.m3u8", "a.flac\nmissing.flac\n")
    with m.db() as c:
        c.execute("UPDATE sessions SET credentials=?", (json.dumps({"u": "patrick"}),))

    async def create(*args, **kwargs):
        raise AssertionError("Must not send partial playlist")

    monkeypatch.setattr(m, "create_navidrome_playlist", create)
    assert (
        client.post(
            "/api/playlist-files/import", json={"sourceId": pid, "name": "Mix"}
        ).status_code
        == 409
    )
    client.cookies.clear()
    assert (
        client.post(
            "/api/playlist-files/import", json={"sourceId": pid, "name": "Mix"}
        ).status_code
        == 401
    )
    assert client.get("/api/navidrome/playlists").status_code == 401


def test_pls_entries_use_numeric_order_and_utf8(client):
    root, _ = compilation_fixture()
    pid = playlist_source(
        root / "Été.pls",
        "[playlist]\nFile10=b.flac\nTitle10=Song\nFile2=a.flac\nNumberOfEntries=2\nVersion=2\n",
    )
    result = client.get("/api/playlist-files/" + pid).json()
    assert result["name"] == "Été"
    assert [i["entry"] for i in result["items"]] == ["a.flac", "b.flac"]


def test_playlist_import_updates_previous_import_and_preserves_duplicates(
    client, monkeypatch
):
    _, root = seed("Bibliothèque")
    pid = playlist_source(root / "Mix.m3u8", "Song.wav\nSong.wav\n")
    with m.db() as c:
        c.execute("UPDATE sessions SET credentials=?", (json.dumps({"u": "patrick"}),))
    calls = []

    async def create(body, credentials, playlist_id=None):
        calls.append((body.trackIds, playlist_id, credentials["u"]))
        return {"playlist": {"id": "created", "songCount": 2}, "verified": True}

    monkeypatch.setattr(m, "create_navidrome_playlist", create)
    for _ in range(2):
        result = client.post(
            "/api/playlist-files/import", json={"sourceId": pid, "name": "Mix"}
        )
        assert result.status_code == 200, result.text
    assert calls[0][0][0] == calls[0][0][1]
    assert calls[0][1] is None and calls[1][1] == "created"


def test_playlist_verification_rejects_unreadable_result(client, monkeypatch):
    import asyncio

    a, _ = seed("Bibliothèque")
    track = m.album_tracks(a["id"])[0]

    async def nav(endpoint, params=None, credentials=None):
        if endpoint == "getAlbumList2":
            return {"albumList2": {"album": [{"id": "a", "name": track["album"]}]}}
        if endpoint == "getAlbum":
            return {"album": {"song": [{"id": "song", "path": track["rel"]}]}}
        if endpoint == "createPlaylist":
            return {"playlist": {"id": "created"}}
        if endpoint == "getPlaylist":
            return {"playlist": {"id": "created", "entry": []}}
        if endpoint == "getPlaylists":
            return {"playlists": {"playlist": []}}
        raise AssertionError(endpoint)

    async def digest(*args):
        with m.db() as c:
            return c.execute(
                "SELECT digest FROM tracks WHERE id=?", (track["id"],)
            ).fetchone()[0]

    monkeypatch.setattr(m, "nav_call", nav)
    monkeypatch.setattr(m, "nav_download_digest", digest)
    with pytest.raises(m.HTTPException) as exc:
        asyncio.run(
            m.create_navidrome_playlist(
                m.Playlist(name="Test", trackIds=[track["id"]]), {"u": "patrick"}
            )
        )
    assert exc.value.status_code == 502


def radio_inventory():
    albums, tracks = [], []
    for artist_index in range(15):
        artist = "Seed" if artist_index == 0 else f"Artist {artist_index}"
        for album_index in range(4):
            aid = f"{artist_index}-{album_index}"
            albums.append(
                {
                    "id": aid,
                    "artist": artist,
                    "genre": (
                        "Rock alternatif; Pop"
                        if artist_index == 0
                        else "Alternative Rock / Pop"
                    ),
                    "zone": "Bibliothèque",
                }
            )
            for number in range(3):
                tid = f"{aid}-{number}"
                tracks.append(
                    {
                        "payload": json.dumps(
                            {"id": tid, "albumId": aid, "artist": artist, "title": tid}
                        ),
                        "digest": tid,
                    }
                )
    return albums, tracks


def test_radio_balances_artists_albums_and_guarantees_seed(client):
    albums, tracks = radio_inventory()
    songs = m.select_radio("seed", 50, albums, tracks, [], set())
    from collections import Counter

    assert len(songs) == 30
    assert sum(t["artist"] == "Seed" for t in songs) == 3
    assert max(Counter(t["artist"] for t in songs).values()) <= 3
    assert max(Counter(t["albumId"] for t in songs).values()) <= 2
    assert len({t["id"] for t in songs}) == 30


def test_radio_avoids_recent_and_byte_duplicates(client):
    albums, tracks = radio_inventory()
    first = m.select_radio("Seed", 50, albums, tracks, [], set())
    recent = {t["id"] for t in first}
    second = m.select_radio("Seed", 50, albums, tracks, [], recent)
    assert len(second) == 30
    assert not recent.intersection(t["id"] for t in second)
    for row in tracks:
        row["digest"] = "identical-bytes"
    assert len(m.select_radio("Seed", 50, albums, tracks, [], set())) == 1


def test_radio_similar_artists_can_cross_genres_but_never_include_unrelated(client):
    albums, tracks = radio_inventory()
    for a in albums:
        if a["artist"] != "Seed":
            a["genre"] = "Classical"
    songs = m.select_radio("Seed", 100, albums, tracks, ["Artist 1"], set())
    assert {t["artist"] for t in songs} == {"Seed", "Artist 1"}
    assert len(songs) == 6
    assert m.radio_genres("Rock alternatif; HIP-HOP / Pop") == {
        "alternative rock",
        "hip hop",
        "pop",
    }
    assert m.radio_affinity({"alternative rock"}, {"hard rock"}) > 0
    assert m.radio_affinity({"jazz"}, {"metal"}) == 0


def test_radio_small_collection_preserves_caps(client):
    albums, tracks = radio_inventory()
    albums = albums[:1]
    songs = m.select_radio("Seed", 0, albums, tracks, [], set())
    assert len(songs) == 2
    assert all(t["artist"] == "Seed" for t in songs)


def test_radio_endpoint_remembers_last_three_generations_by_account(
    client, monkeypatch
):
    albums, tracks = radio_inventory()
    with m.db() as c:
        for a in albums:
            c.execute("INSERT INTO albums VALUES (?,?)", (a["id"], json.dumps(a)))
        for r in tracks:
            t = json.loads(r["payload"])
            c.execute(
                "INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)",
                (
                    t["id"],
                    t["albumId"],
                    "Bibliothèque",
                    t["id"],
                    0,
                    0,
                    r["digest"],
                    r["payload"],
                ),
            )

    async def similar(*args):
        return []

    monkeypatch.setattr(m, "radio_similar", similar)
    for _ in range(4):
        result = client.post("/api/radio", json={"artist": "Seed", "discovery": 50})
        assert result.status_code == 200, result.text
        assert len(result.json()["items"]) == 30
    key = "radio-history:" + m.identifier("patrick/seed")
    assert len(m.setting(key)) == 3
    assert m.setting("radio-history:" + m.identifier("other/seed")) is None
    assert (
        client.post("/api/radio", json={"artist": "Seed", "discovery": 101}).status_code
        == 422
    )
    assert client.post("/api/radio", json={"artist": "Missing"}).status_code == 404


def test_radio_navidrome_recommendations_are_cached_and_failure_falls_back(
    client, monkeypatch
):
    import asyncio

    calls = []

    async def nav(endpoint, params=None, credentials=None):
        calls.append(endpoint)
        if endpoint == "search3":
            return {"searchResult3": {"artist": [{"id": "seed", "name": "Seed"}]}}
        return {"artistInfo2": {"similarArtist": [{"name": "Related"}]}}

    monkeypatch.setattr(m, "nav_call", nav)
    assert asyncio.run(m.radio_similar("Seed")) == ["Related"]
    assert asyncio.run(m.radio_similar("seed")) == ["Related"]
    assert len(calls) == 2

    async def unavailable(*args, **kwargs):
        raise m.HTTPException(502, "Unavailable")

    monkeypatch.setattr(m, "nav_call", unavailable)
    assert asyncio.run(m.radio_similar("Other")) == []


def test_radio_popularity_personal_and_collective_weights_are_distinct(client):
    scores = {
        "hit": {"top": 1},
        "favorite": {"personal": 1, "played": True},
        "community": {"collective": 1},
    }
    assert m.radio_track_weight("hit", scores, 0) > m.radio_track_weight(
        "unknown", scores, 0
    )
    assert m.radio_track_weight("favorite", scores, 0) > m.radio_track_weight(
        "favorite", scores, 100
    )
    assert m.radio_track_weight("community", scores, 50) > 1
    assert m.radio_track_weight("unknown", scores, 100) == 1


def test_radio_from_song_guarantees_exact_seed_even_when_recent(client):
    albums, tracks = radio_inventory()
    seed = json.loads(tracks[5]["payload"])
    songs = m.select_radio(
        "Seed", 100, albums, tracks, [], {r["digest"] for r in tracks}, {}, seed
    )
    assert songs[0]["id"] == seed["id"]
    from collections import Counter

    assert max(Counter(t["artist"] for t in songs).values()) <= 3
    assert max(Counter(t["albumId"] for t in songs).values()) <= 2


def test_radio_song_endpoint_rejects_incoming_and_search_only_lists_library(
    client, monkeypatch
):
    a, _ = seed()
    incoming = m.album_tracks(a["id"])[0]

    async def signals(*args):
        return (
            {},
            set(),
            {
                "popular": False,
                "personal": False,
                "collective": False,
                "songSimilarity": False,
            },
        )

    async def similar(*args):
        return []

    monkeypatch.setattr(m, "radio_signals", signals)
    monkeypatch.setattr(m, "radio_similar", similar)
    assert (
        client.post("/api/radio", json={"trackId": incoming["id"]}).status_code == 404
    )
    a, _ = seed("Bibliothèque")
    with m.db() as c:
        own = json.loads(
            c.execute(
                "SELECT payload FROM tracks WHERE zone='Bibliothèque'"
            ).fetchone()[0]
        )
    result = client.get("/api/radio/tracks", params={"q": own["title"]}).json()
    assert result["total"] == 1 and result["items"][0]["zone"] == "Bibliothèque"
    result = client.post("/api/radio", json={"trackId": own["id"], "discovery": 80})
    assert result.status_code == 200, result.text
    assert any(t["id"] == own["id"] for t in result.json()["items"])
    assert result.json()["signals"]["popular"] is False


def test_radio_catalog_cache_is_scoped_by_account(client, monkeypatch):
    import asyncio

    async def nav(endpoint, params=None, credentials=None):
        return {
            "searchResult3": {
                "song": [
                    {
                        "id": "song",
                        "playCount": (
                            5 if credentials and credentials["u"] == "one" else 0
                        ),
                    }
                ]
            }
        }

    monkeypatch.setattr(m, "nav_call", nav)
    one = asyncio.run(m.radio_catalog({"u": "one"}))
    two = asyncio.run(m.radio_catalog({"u": "two"}))
    anonymous = asyncio.run(m.radio_catalog())
    assert one[0]["playCount"] == 5
    assert two[0]["playCount"] == 0
    assert "playCount" not in anonymous[0]


def test_radio_match_refuses_ambiguous_recordings(client):
    local = {
        "id": "local",
        "rel": "Artist/Album/a.flac",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "size": 100,
        "duration": 20,
    }
    song = {**local, "id": "nav", "path": "virtual/path"}
    assert m.radio_match(local, [song])["id"] == "nav"
    assert m.radio_match(local, [song, {**song, "id": "another"}]) is None
    assert m.radio_match(local, [{**song, "size": 101}]) is None


def test_collective_export_is_anonymous_normalized_and_read_only(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "collective", Path(__file__).parents[1] / "collective.py"
    )
    collective = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collective)
    database = tmp_path / "nav.db"
    c = sqlite3.connect(database)
    c.execute(
        "CREATE TABLE annotation(user_id TEXT,item_id TEXT,item_type TEXT,play_count INTEGER)"
    )
    c.executemany(
        "INSERT INTO annotation VALUES (?,?,?,?)",
        [
            ("user-one", "song-a", "media_file", 10000),
            ("user-two", "song-b", "media_file", 1),
        ],
    )
    c.commit()
    c.close()
    original = database.read_bytes()
    output = tmp_path / "radio" / "collective.json"
    collective.export_scores(database, output)
    payload = json.loads(output.read_text())
    assert payload["scores"] == {"song-a": 0.5, "song-b": 0.5}
    assert payload["listeners"] == 2
    assert "user-one" not in output.read_text() and "user-two" not in output.read_text()
    assert database.read_bytes() == original


def test_collective_signal_expires_and_requires_multiple_listeners(client):
    directory = m.STATE / "radio"
    directory.mkdir()
    path = directory / "collective.json"
    path.write_text(
        json.dumps({"created": time.time(), "listeners": 1, "scores": {"song": 1}})
    )
    assert m.collective_scores() == {}
    path.write_text(
        json.dumps({"created": time.time(), "listeners": 2, "scores": {"song": 0.5}})
    )
    assert m.collective_scores() == {"song": 0.5}
    path.write_text(
        json.dumps(
            {"created": time.time() - 3600, "listeners": 2, "scores": {"song": 0.5}}
        )
    )
    assert m.collective_scores() == {}


def test_radio_signals_combine_available_sources_without_cross_account_leak(
    client, monkeypatch
):
    import asyncio

    local = {
        "id": "local",
        "rel": "Artist/Album/song.flac",
        "artist": "Artist",
        "album": "Album",
        "title": "Song",
        "size": 100,
        "duration": 10,
    }
    song = {
        **local,
        "id": "nav-song",
        "path": "virtual/path",
        "playCount": 4,
        "starred": "2026-01-01",
    }

    async def catalog(credentials):
        assert credentials["u"] == "patrick"
        return [song]

    async def nav(endpoint, params=None, credentials=None):
        assert credentials["u"] == "patrick"
        if endpoint == "getTopSongs":
            return {"topSongs": {"song": [song]}}
        if endpoint == "getSimilarSongs":
            return {"similarSongs": {"song": [song]}}
        raise AssertionError(endpoint)

    monkeypatch.setattr(m, "radio_catalog", catalog)
    monkeypatch.setattr(m, "nav_call", nav)
    monkeypatch.setattr(m, "collective_scores", lambda: {"nav-song": 0.4})
    scores, related, signals = asyncio.run(
        m.radio_signals(
            "Artist", [], [{"payload": json.dumps(local)}], {"u": "patrick"}, local
        )
    )
    assert scores["local"]["top"] == 1
    assert scores["local"]["personal"] == 1
    assert scores["local"]["collective"] == 0.4
    assert related == set()
    assert signals["popular"] and signals["personal"] and signals["collective"]
    assert not signals["songSimilarity"]
    with m.db() as c:
        cached = c.execute(
            "SELECT payload FROM cache WHERE key LIKE 'radio-top:%'"
        ).fetchone()[0]
    assert json.loads(cached) == ["nav-song"]
    assert "playCount" not in cached and "patrick" not in cached


def test_multidisc_moves_preserve_album_hierarchy_and_restore(client):
    seed(folder="Linkin Park/Album One/CD1", name="one.wav")
    seed(folder="Linkin Park/Album Two/CD1", name="two.wav")
    original = {a["id"]: a for a in m.all_albums()}
    # An old flattened destination must not block either correctly nested album.
    old = m.ROOTS["Bibliothèque"] / "Linkin Park" / "CD1"
    old.mkdir(parents=True)
    (old / "existing.txt").write_text("untouched")
    plan = client.post(
        "/api/operations/preview", json={"albumIds": list(original), "action": "move"}
    )
    assert plan.status_code == 200, plan.text
    assert {
        p["target"].removeprefix("/mnt/media/music/") for p in plan.json()["items"]
    } == {"Linkin Park/Album One/CD1", "Linkin Park/Album Two/CD1"}
    assert (
        client.post(
            "/api/operations/apply", json={"token": plan.json()["token"]}
        ).status_code
        == 200
    )
    assert (m.ROOTS["Bibliothèque"] / "Linkin Park/Album One/CD1/one.wav").is_file()
    assert (m.ROOTS["Bibliothèque"] / "Linkin Park/Album Two/CD1/two.wav").is_file()
    assert (old / "existing.txt").read_text() == "untouched"
    for op in client.get("/api/history").json()["items"]:
        assert (
            client.post("/api/history/" + op["id"] + "/restore", json={}).status_code
            == 200
        )
    for a in original.values():
        assert (m.ROOTS["Téléchargements"] / a["folder"]).is_dir()


def test_multidisc_existing_exact_destination_still_refuses_overwrite(client):
    a, _ = seed(folder="Linkin Park/Album/CD1")
    target = m.ROOTS["Bibliothèque"] / a["folder"]
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("original")
    response = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    )
    assert response.status_code == 409
    assert (target / "keep.txt").read_text() == "original"


def test_move_path_retains_deeper_hierarchy_and_root_album_fallback(client):
    assert (
        m.album_move_path(
            {"folder": "Artist/Album/Disc 2/FLAC", "artist": "Tag Artist"}
        )
        == "Artist/Album/Disc 2/FLAC"
    )
    assert m.album_move_path({"folder": "Album", "artist": "Artist"}) == "Artist/Album"


def test_move_plan_created_before_path_fix_must_be_previewed_again(client):
    a, path = seed(folder="Artist/Album/CD1")
    response = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    )
    token = response.json()["token"]
    with m.db() as c:
        payload = json.loads(
            c.execute("SELECT payload FROM plans WHERE id=?", (token,)).fetchone()[0]
        )
        payload.pop("moveLayout")
        c.execute("UPDATE plans SET payload=? WHERE id=?", (json.dumps(payload), token))
    result = client.post("/api/operations/apply", json={"token": token})
    assert result.status_code == 409
    assert path.is_dir()


def test_apply_returns_index_baseline_and_queues_a_fresh_scan(client, monkeypatch):
    a, _ = seed()
    baseline = m.setting("lastScan")
    calls = []
    monkeypatch.setattr(m, "start_scan", lambda **kwargs: calls.append(kwargs))
    plan = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    ).json()
    result = client.post("/api/operations/apply", json={"token": plan["token"]})
    assert result.status_code == 200, result.text
    assert result.json()["scanAfter"] == baseline
    assert calls == [{"force": True}]
    status = client.get("/api/scan/status")
    assert status.status_code == 200 and status.json()["lastScan"] == baseline


def test_forced_scan_waits_for_previous_scan_to_finish(client, monkeypatch):
    import threading

    finished = threading.Event()
    actual_scan = m.scan

    def tracked_scan(*args, **kwargs):
        actual_scan(*args, **kwargs)
        finished.set()

    monkeypatch.setattr(m, "scan", tracked_scan)
    m.SCAN["running"] = True
    m.SCAN_LOCK.acquire()
    try:
        REAL_START_SCAN(force=True)
        assert not finished.wait(0.05)
    finally:
        m.SCAN_LOCK.release()
    assert finished.wait(2)


def test_file_manager_can_move_restore_and_set_preferences_without_navidrome_admin(
    client,
):
    with m.db() as c:
        c.execute("UPDATE sessions SET admin=0")
    a, path = seed()
    plan = client.post(
        "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
    )
    assert plan.status_code == 200, plan.text
    result = client.post("/api/operations/apply", json={"token": plan.json()["token"]})
    assert result.status_code == 200, result.text
    op = client.get("/api/history").json()["items"][0]
    assert (
        client.post("/api/history/" + op["id"] + "/restore", json={}).status_code == 200
    )
    assert path.is_dir()
    assert client.put("/api/preferences", json={"scanMinutes": 60}).status_code == 200
    status = client.get("/api/status").json()["session"]
    assert status == {"username": "patrick", "admin": False, "canManageFiles": True}
    assert client.post("/api/navidrome/scan", json={}).status_code == 403


def test_navidrome_admin_does_not_implicitly_grant_local_file_rights(client):
    a, _ = seed()
    with m.db() as c:
        c.execute("UPDATE sessions SET username='other-admin', admin=1")
    requests = [
        ("/api/operations/preview", {"albumIds": [a["id"]], "action": "move"}),
        ("/api/operations/apply", {"token": "missing"}),
        ("/api/history/missing/restore", {}),
        (
            "/api/albums/" + a["id"] + "/metadata/preview",
            {"artist": "A", "album": "B", "year": "2026", "genre": "Rock"},
        ),
        ("/api/metadata/apply", {"token": "missing"}),
    ]
    for url, body in requests:
        result = client.post(url, json=body)
        assert result.status_code == 403, (url, result.text)
    assert client.put("/api/preferences", json={"scanMinutes": 60}).status_code == 403
    assert client.get("/api/status").json()["session"]["canManageFiles"] is False


def test_file_rights_deny_by_default_and_still_require_login(client, monkeypatch):
    a, _ = seed()
    monkeypatch.setattr(m, "FILE_MANAGERS", set())
    assert (
        client.post(
            "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
        ).status_code
        == 403
    )
    monkeypatch.setattr(m, "FILE_MANAGERS", {"patrick"})
    with m.db() as c:
        c.execute("UPDATE sessions SET username='patrick-other'")
    assert (
        client.post(
            "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert (
        client.post(
            "/api/operations/preview", json={"albumIds": [a["id"]], "action": "move"}
        ).status_code
        == 401
    )


def test_file_manager_uses_own_navidrome_identity_for_playlists(client, monkeypatch):
    with m.db() as c:
        c.execute(
            "UPDATE sessions SET admin=0,credentials=?", (json.dumps({"u": "patrick"}),)
        )

    async def nav(endpoint, params=None, credentials=None):
        assert endpoint == "getPlaylists"
        assert credentials == {"u": "patrick"}
        return {"playlists": {"playlist": []}}

    monkeypatch.setattr(m, "nav_call", nav)
    result = client.get("/api/navidrome/playlists")
    assert result.status_code == 200 and result.json()["username"] == "patrick"


def test_album_genre_filter_expands_semicolon_lists(client, monkeypatch):
    base = {
        "artist": "Artist",
        "year": 2026,
        "format": "FLAC",
        "completeness": "complete",
    }
    albums = [
        {
            **base,
            "id": "mixed",
            "title": "Mixed",
            "genre": " rock ; hard;; ",
            "zone": "Bibliothèque",
        },
        {
            **base,
            "id": "rock",
            "title": "Rock",
            "genre": "Rock",
            "zone": "Bibliothèque",
        },
        {
            **base,
            "id": "hardrock",
            "title": "Hard Rock",
            "genre": "Hard Rock",
            "zone": "Bibliothèque",
        },
        {
            **base,
            "id": "incoming",
            "title": "Incoming",
            "genre": "hard;Pop",
            "zone": "Téléchargements",
        },
    ]
    monkeypatch.setattr(m, "all_albums", lambda: albums)
    result = client.get("/api/albums").json()
    assert {g.casefold() for g in result["genres"]} == {
        "rock",
        "hard",
        "hard rock",
        "pop",
    }
    assert len(result["genres"]) == 4
    for genre, expected in [
        ("rock", {"mixed", "rock"}),
        ("HARD", {"mixed"}),
        ("Hard Rock", {"hardrock"}),
    ]:
        result = client.get("/api/albums", params={"genre": genre}).json()
        assert {a["id"] for a in result["items"]} == expected
        assert result["total"] == len(expected)
    result = client.get(
        "/api/albums", params={"genre": "hard", "zone": "Téléchargements"}
    ).json()
    assert [a["id"] for a in result["items"]] == ["incoming"]
    assert albums[0]["genre"] == " rock ; hard;; "
