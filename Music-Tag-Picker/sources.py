# -*- coding: utf-8 -*-
"""搜索网易云、QQ 音乐、咪咕、酷狗，并按选中的条目再取歌词。"""
import base64
import json
import re
import urllib.parse

from app_http import fetch

PLATFORMS = (
    ("netease", "网易云"),
    ("qq", "QQ 音乐"),
    ("migu", "咪咕"),
    ("kugou", "酷狗"),
)
PLATFORM_LABELS = dict(PLATFORMS)


def artist_names(artists):
    names = []
    for item in artists or []:
        names.extend(part.strip() for part in re.split(r"[,/、;&]+", item) if part.strip())
    return names


def penalty(name):
    lowered = (name or "").lower()
    flags = ("live", "remix", "cover", "dj", "翻唱", "伴奏", "纯音乐")
    return any(flag in lowered or flag in (name or "") for flag in flags)


def decorate(song, title, artist):
    names = artist_names(song.get("artists"))
    score = 0
    if song.get("name") == title:
        score += 100
    elif title and title in (song.get("name") or ""):
        score += 40
    if artist and artist in names:
        score += 60
    if penalty(song.get("name")):
        score -= 35
    song["score"] = score
    song["preferred"] = song.get("name") == title and ((not artist) or artist in names) and not penalty(song.get("name"))
    song["label"] = PLATFORM_LABELS.get(song.get("platform"), song.get("platform"))
    return song


def search_netease(title):
    songs = []
    for page in range(10):
        body = urllib.parse.urlencode({"s": title, "type": 1, "offset": page * 30, "limit": 30}).encode()
        _, _, raw = fetch(
            "https://music.163.com/api/cloudsearch/pc",
            {"Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        batch = json.loads(raw.decode("utf-8")).get("result", {}).get("songs") or []
        if not batch:
            break
        for item in batch:
            album = item.get("al") or {}
            songs.append({
                "platform": "netease",
                "id": str(item.get("id") or ""),
                "name": item.get("name") or "",
                "artists": [a.get("name") or "" for a in item.get("ar") or []],
                "album": album.get("name") or "",
                "duration_ms": int(item.get("dt") or 0),
                "cover_url": album.get("picUrl") or "",
            })
    return songs


def search_qq(title, artist):
    query = title if not artist else "%s %s" % (title, artist)
    url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?" + urllib.parse.urlencode(
        {"w": query, "format": "json", "p": 1, "n": 30, "cr": 1, "new_json": 1}
    )
    _, _, raw = fetch(url, {"Referer": "https://y.qq.com/"})
    items = (((json.loads(raw.decode("utf-8")).get("data") or {}).get("song") or {}).get("list")) or []
    songs = []
    for item in items:
        album = item.get("album") or {}
        pmid = album.get("pmid") or album.get("mid") or ""
        songs.append({
            "platform": "qq",
            "id": item.get("mid") or "",
            "name": item.get("name") or item.get("title") or "",
            "artists": [x.get("name") or x.get("title") or "" for x in item.get("singer") or []],
            "album": album.get("name") or album.get("title") or "",
            "duration_ms": int(item.get("interval") or 0) * 1000,
            "cover_url": ("https://y.gtimg.cn/music/photo_new/T002R500x500M000%s.jpg" % pmid) if pmid else "",
        })
    return songs


def search_kugou(title, artist):
    query = title if not artist else "%s %s" % (title, artist)
    url = "https://songsearch.kugou.com/song_search_v2?" + urllib.parse.urlencode(
        {"keyword": query, "page": 1, "pagesize": 30, "platform": "WebFilter"}
    )
    _, _, raw = fetch(url, {"Referer": "https://www.kugou.com/"})
    items = ((json.loads(raw.decode("utf-8")).get("data") or {}).get("lists")) or []
    songs = []
    for item in items:
        image = (item.get("Image") or "").replace("{size}", "480")
        songs.append({
            "platform": "kugou",
            "id": item.get("FileHash") or "",
            "name": item.get("SongName") or "",
            "artists": [item.get("SingerName") or ""],
            "album": item.get("AlbumName") or "",
            "duration_ms": int(item.get("Duration") or 0) * 1000,
            "cover_url": image,
        })
    return songs


def search_migu(title, artist):
    query = title if not artist else "%s %s" % (artist, title)
    url = "https://app.c.nf.migu.cn/pc/resource/song/item/search/v1.0?" + urllib.parse.urlencode(
        {"text": query, "pageNo": 1, "pageSize": 30}
    )
    _, _, raw = fetch(url, {"Referer": "https://music.migu.cn/", "channel": "0146921", "uid": "0"})
    items = json.loads(raw.decode("utf-8"))
    if isinstance(items, dict):
        items = items.get("data") or []
    songs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        image = item.get("img1") or ""
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            image = "https://d.musicapp.migu.cn" + image
        duration = int(item.get("duration") or 0)
        songs.append({
            "platform": "migu",
            "id": str(item.get("copyrightId") or item.get("contentId") or ""),
            "name": item.get("songName") or "",
            "artists": [x.get("name") or "" for x in item.get("singerList") or []],
            "album": item.get("album") or "",
            "duration_ms": duration * 1000 if duration < 10000 else duration,
            "cover_url": image,
            "lrc_url": item.get("lrcUrl") or "",
        })
    return songs


SEARCHERS = {
    "netease": lambda title, artist: search_netease(title),
    "qq": search_qq,
    "migu": search_migu,
    "kugou": search_kugou,
}


def search(title, artist, platforms):
    songs = []
    errors = []
    for name in platforms:
        try:
            found = SEARCHERS[name](title, artist)
            songs.extend(decorate(song, title, artist) for song in found)
        except Exception as exc:
            errors.append({"platform": name, "label": PLATFORM_LABELS.get(name, name), "error": "%s: %s" % (type(exc).__name__, exc)})
    songs.sort(key=lambda song: (-song.get("score", 0), song.get("name") or ""))
    return {"songs": songs, "errors": errors}


def _lyric_payload(text):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    timed = sum(1 for line in lines if line.strip().startswith("["))
    return {"ok": bool(text), "lyric": text or "", "lines": len(lines), "timed_lines": timed}


def lyric_netease(song):
    _, _, raw = fetch(
        "https://music.163.com/api/song/lyric?id=%s&lv=1&kv=1&tv=-1" % song.get("id"),
        {"Referer": "https://music.163.com/"},
    )
    data = json.loads(raw.decode("utf-8"))
    return _lyric_payload(((data.get("lrc") or {}).get("lyric")) or "")


def lyric_qq(song):
    url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?" + urllib.parse.urlencode(
        {"songmid": song.get("id"), "format": "json", "nobase64": 1, "g_tk": 5381}
    )
    _, _, raw = fetch(url, {"Referer": "https://y.qq.com/"})
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("MusicJsonCallback"):
        text = text[text.find("(") + 1:text.rfind(")")]
    data = json.loads(text)
    return _lyric_payload(data.get("lyric") or "")


def lyric_kugou(song):
    search_url = "http://lyrics.kugou.com/search?" + urllib.parse.urlencode({
        "ver": 1, "man": "yes", "client": "pc", "keyword": song.get("name") or "",
        "duration": int(song.get("duration_ms") or 0), "hash": song.get("id") or "",
    })
    _, _, raw = fetch(search_url, {"Referer": "https://www.kugou.com/"})
    candidates = json.loads(raw.decode("utf-8")).get("candidates") or []
    if not candidates:
        return _lyric_payload("")
    cand = candidates[0]
    download = "http://lyrics.kugou.com/download?" + urllib.parse.urlencode({
        "ver": 1, "client": "pc", "id": cand.get("id"), "accesskey": cand.get("accesskey"),
        "fmt": "lrc", "charset": "utf8",
    })
    _, _, raw = fetch(download, {"Referer": "https://www.kugou.com/"})
    content = json.loads(raw.decode("utf-8")).get("content") or ""
    try:
        text = base64.b64decode(content).decode("utf-8", "replace")
    except Exception:
        text = ""
    return _lyric_payload(text)


def lyric_migu(song):
    lrc_url = song.get("lrc_url") or ""
    host = (urllib.parse.urlparse(lrc_url).hostname or "").lower()
    if not lrc_url or not (host.endswith("migu.cn") or host.endswith("migu.com")):
        return _lyric_payload("")
    _, _, raw = fetch(lrc_url, {"Referer": "https://music.migu.cn/"})
    return _lyric_payload(raw.decode("utf-8", "replace"))


LYRICS = {
    "netease": lyric_netease,
    "qq": lyric_qq,
    "kugou": lyric_kugou,
    "migu": lyric_migu,
}


def load_lyric(song):
    platform = song.get("platform")
    if platform not in LYRICS:
        raise ValueError("未知平台")
    if not song.get("id"):
        raise ValueError("缺少歌曲编号")
    return LYRICS[platform](song)
