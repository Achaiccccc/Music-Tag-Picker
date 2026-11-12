# -*- coding: utf-8 -*-
"""选择 NAS 音乐目录中的文件，搜索平台候选，确认后写入标签。"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import library
import sources
from tags import download_cover, read_cover, write_tags

PORT = int(os.environ.get("PORT", "8080"))
BASE = Path(__file__).resolve().parent
INDEX = (BASE / "index.html").read_text(encoding="utf-8")


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def selected_platforms(raw):
    names = [item.strip() for item in (raw or "").split(",") if item.strip()]
    unknown = [item for item in names if item not in sources.PLATFORM_LABELS]
    if unknown:
        raise ValueError("未知平台")
    if not names:
        raise ValueError("至少选择一个平台")
    return names


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX.encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
            return
        if parsed.path == "/api/health":
            self._send(200, "application/json; charset=utf-8", json_bytes({"ok": True}))
            return
        if parsed.path == "/api/browse":
            self._browse(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-search":
            self._local_search(parse_qs(parsed.query))
            return
        if parsed.path == "/api/search":
            self._search(parse_qs(parsed.query))
            return
        if parsed.path == "/api/cover":
            self._cover(parse_qs(parsed.query))
            return
        self._send(404, "text/plain; charset=utf-8", "未找到".encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1000000:
            self._send(413, "application/json; charset=utf-8", json_bytes({"ok": False, "error": "请求过大"}))
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, "application/json; charset=utf-8", json_bytes({"ok": False, "error": "请求不是 JSON"}))
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/lyric":
            self._lyric(payload)
            return
        if parsed.path == "/api/write":
            self._write(payload)
            return
        self._send(404, "text/plain; charset=utf-8", "未找到".encode("utf-8"))

    def _browse(self, query):
        try:
            data = library.browse(
                (query.get("path") or [""])[0],
                (query.get("base") or [""])[0],
                (query.get("picking") or ["0"])[0] == "1",
            )
            self._send(200, "application/json; charset=utf-8", json_bytes(data))
        except (ValueError, FileNotFoundError) as exc:
            self._send(400, "application/json; charset=utf-8", json_bytes({"ok": False, "error": str(exc)}))

    def _local_search(self, query):
        data = library.search_files((query.get("q") or [""])[0])
        status = 200 if data.get("ok") else 400
        self._send(status, "application/json; charset=utf-8", json_bytes(data))

    def _cover(self, query):
        try:
            path = library.resolve_file((query.get("path") or [""])[0])
            data, mime = read_cover(path)
            if not data:
                self._send(404, "text/plain; charset=utf-8", b"")
                return
            self._send(200, mime, data)
        except (ValueError, FileNotFoundError):
            self._send(404, "text/plain; charset=utf-8", b"")

    def _search(self, query):
        title = ((query.get("title") or [""])[0] or "").strip()
        artist = ((query.get("artist") or [""])[0] or "").strip()
        if not title:
            self._send(400, "application/json; charset=utf-8", json_bytes({"ok": False, "error": "请填写歌名"}))
            return
        try:
            platforms = selected_platforms((query.get("platforms") or [""])[0])
        except ValueError as exc:
            self._send(400, "application/json; charset=utf-8", json_bytes({"ok": False, "error": str(exc)}))
            return
        data = sources.search(title, artist, platforms)
        data["ok"] = True
        self._send(200, "application/json; charset=utf-8", json_bytes(data))

    def _lyric(self, payload):
        song = payload.get("song") or {}
        try:
            data = sources.load_lyric(song)
            data["ok"] = bool(data.get("lyric"))
            self._send(200, "application/json; charset=utf-8", json_bytes(data))
        except Exception as exc:
            self._send(200, "application/json; charset=utf-8", json_bytes({
                "ok": False, "lyric": "", "lines": 0, "timed_lines": 0,
                "error": "%s: %s" % (type(exc).__name__, exc),
            }))

    def _write(self, payload):
        song = payload.get("song") or {}
        try:
            path = library.resolve_file(payload.get("path") or "")
            title = (song.get("name") or "").strip()
            artist = " / ".join(item for item in (song.get("artists") or []) if item)
            album = (song.get("album") or "").strip()
            if not title:
                raise ValueError("候选缺少歌名")
            lyric = sources.load_lyric(song).get("lyric") or ""
            cover, mime, cover_error = download_cover(song.get("cover_url") or "")
            result = write_tags(path, title, artist, album, lyric, cover, mime)
            if cover_error and "封面" not in result["written"]:
                result["cover_note"] = cover_error
            result["ok"] = True
            result["file"] = path.name
            self._send(200, "application/json; charset=utf-8", json_bytes(result))
        except Exception as exc:
            self._send(400, "application/json; charset=utf-8", json_bytes({
                "ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
            }))

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        message = fmt % args
        message = re.sub(r"lyric=.*", "lyric=<hidden>", message)
        print("[%s] %s" % (self.log_date_time_string(), message))


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("music tagger listening on 0.0.0.0:%s root=%s" % (PORT, library.music_root()))
    server.serve_forever()


if __name__ == "__main__":
    main()
