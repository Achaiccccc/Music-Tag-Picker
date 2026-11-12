# -*- coding: utf-8 -*-
"""把选中的标题、歌手、专辑、歌词和封面写回音频文件。"""
import urllib.parse

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, USLT
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from app_http import fetch

COVER_HOSTS = (
    "music.126.net",
    "y.gtimg.cn",
    "y.qq.com",
    "migu.cn",
    "kugou.com",
)


def _host_ok(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == item or host.endswith("." + item) for item in COVER_HOSTS)


def _image_mime(data, declared, url):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    declared = (declared or "").lower()
    if "png" in declared or url.lower().endswith(".png"):
        return "image/png"
    if "webp" in declared or url.lower().endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _id3_cover(tags):
    if tags is None:
        return b"", ""
    pictures = tags.getall("APIC")
    if not pictures:
        return b"", ""
    return bytes(pictures[0].data or b""), pictures[0].mime or ""


def _vorbis_cover(audio):
    pictures = getattr(audio, "pictures", None) or []
    if pictures:
        return bytes(pictures[0].data or b""), pictures[0].mime or ""
    encoded = audio.get("metadata_block_picture") or []
    if not encoded:
        return b"", ""
    import base64
    picture = Picture(base64.b64decode(encoded[0]))
    return bytes(picture.data or b""), picture.mime or ""


def read_cover(path):
    suffix = path.suffix.lower()
    data, mime = b"", ""
    try:
        if suffix == ".mp3":
            data, mime = _id3_cover(ID3(path))
        elif suffix == ".wav":
            audio = WAVE(path)
            data, mime = _id3_cover(audio.tags)
        elif suffix == ".flac":
            data, mime = _vorbis_cover(FLAC(path))
        elif suffix == ".ogg":
            data, mime = _vorbis_cover(OggVorbis(path))
        elif suffix == ".opus":
            data, mime = _vorbis_cover(OggOpus(path))
        elif suffix in (".m4a", ".mp4", ".aac"):
            audio = MP4(path)
            covers = audio.get("covr") or []
            if covers:
                mime = "image/png" if getattr(covers[0], "imageformat", None) == MP4Cover.FORMAT_PNG else "image/jpeg"
                data = bytes(covers[0])
    except Exception:
        return b"", ""
    if not data:
        return b"", ""
    sniffed = _image_mime(data, mime, "")
    if sniffed not in ("image/jpeg", "image/png", "image/webp"):
        return b"", ""
    return data, sniffed


def download_cover(url):
    if not url or not _host_ok(url):
        return b"", "", "没有可写入的封面"
    status, headers, data = fetch(url, {"Referer": url}, timeout=12)
    mime = _image_mime(data, headers.get("Content-Type"), url)
    if status != 200 or not mime.startswith("image/") or len(data) < 500:
        return b"", mime, "封面下载失败"
    return data, mime, ""


def _id3_write(tags, title, artist, album, lyric, cover, mime):
    for key in ("TIT2", "TPE1", "TALB", "USLT", "APIC"):
        tags.delall(key)
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    if lyric:
        tags.add(USLT(encoding=3, lang="chi", desc="", text=lyric))
    if cover and mime in ("image/jpeg", "image/png", "image/webp"):
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))


def _vorbis_write(audio, title, artist, album, lyric, cover, mime):
    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    if lyric:
        audio["lyrics"] = lyric
    if hasattr(audio, "clear_pictures"):
        audio.clear_pictures()
    if cover:
        picture = Picture()
        picture.type = 3
        picture.mime = mime
        picture.data = cover
        if hasattr(audio, "add_picture"):
            audio.add_picture(picture)
        else:
            import base64
            audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]


def write_tags(path, title, artist, album, lyric, cover, mime):
    suffix = path.suffix.lower()
    written = ["标题", "歌手", "专辑"]
    if lyric:
        written.append("歌词")
    cover_note = ""
    if suffix == ".mp3":
        try:
            tags = ID3(path)
        except Exception:
            tags = ID3()
        _id3_write(tags, title, artist, album, lyric, cover, mime)
        tags.save(path)
    elif suffix == ".wav":
        audio = WAVE(path)
        if audio.tags is None:
            audio.add_tags()
        _id3_write(audio.tags, title, artist, album, lyric, cover, mime)
        audio.save()
    elif suffix == ".flac":
        audio = FLAC(path)
        _vorbis_write(audio, title, artist, album, lyric, cover, mime)
        audio.save()
    elif suffix in (".ogg",):
        audio = OggVorbis(path)
        _vorbis_write(audio, title, artist, album, lyric, cover, mime)
        audio.save()
    elif suffix == ".opus":
        audio = OggOpus(path)
        _vorbis_write(audio, title, artist, album, lyric, cover, mime)
        audio.save()
    elif suffix in (".m4a", ".mp4", ".aac"):
        audio = MP4(path)
        audio["\xa9nam"] = [title]
        audio["\xa9ART"] = [artist]
        audio["\xa9alb"] = [album]
        if lyric:
            audio["\xa9lyr"] = [lyric]
        if cover and mime == "image/jpeg":
            audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        elif cover and mime == "image/png":
            audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_PNG)]
        elif cover:
            cover_note = "该格式不能嵌入这种封面"
            written = [item for item in written if item != "封面"]
        audio.save()
    else:
        raise ValueError("暂不支持写入 %s" % suffix)
    if cover and "封面" not in written and not cover_note:
        written.append("封面")
    elif cover and not cover_note and suffix not in (".m4a", ".mp4", ".aac"):
        if "封面" not in written:
            written.append("封面")
    return {"written": written, "cover_note": cover_note}
