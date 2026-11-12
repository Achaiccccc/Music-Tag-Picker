# -*- coding: utf-8 -*-
"""浏览容器内挂载的音乐目录。路径不允许跳出 MUSIC_ROOT。"""
import os
import re
from pathlib import Path

def parse_filename(name):
    stem = Path(name).stem.strip()
    stem = re.sub(r"^\s*\d{1,3}\s*[\.、]\s*", "", stem)
    stem = re.sub(r"^\s*\d{1,3}\s*-\s*", "", stem)
    for sep in (" - ", " – ", " — ", "－"):
        if sep in stem:
            title, artist = stem.split(sep, 1)
            return {"title": title.strip(), "artist": artist.strip()}
    return {"title": stem.strip(), "artist": ""}


AUDIO_EXT = {
    ".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".opus",
    ".wav", ".wma", ".ape", ".aiff", ".aif", ".wv",
}
PICK_MAX_DEPTH = 8
LIBRARY_MAX_DEPTH = 5


def music_root():
    return Path(os.environ.get("MUSIC_ROOT", "/music")).resolve()


def _parts(rel):
    rel = (rel or "").replace("\\", "/").strip("/")
    if not rel:
        return ()
    parts = Path(rel).parts
    if ".." in parts:
        raise ValueError("路径不能包含 ..")
    return parts


def resolve_dir(rel):
    root = music_root()
    parts = _parts(rel)
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径超出音乐根目录")
    if not root.exists():
        raise FileNotFoundError("音乐根目录不存在：%s" % root)
    if not target.is_dir():
        raise FileNotFoundError("目录不存在")
    return root, target, "/".join(parts)


def resolve_file(rel):
    root = music_root()
    parts = _parts(rel)
    if not parts:
        raise ValueError("未选择文件")
    target = root.joinpath(*parts).resolve()
    if root not in target.parents:
        raise ValueError("路径超出音乐根目录")
    if not target.is_file():
        raise FileNotFoundError("文件不存在")
    if target.suffix.lower() not in AUDIO_EXT:
        raise ValueError("不是支持的音频文件")
    return target


def browse(path, base="", picking=False):
    root = music_root()
    if not root.exists():
        return {
            "ok": False,
            "root": str(root),
            "error": "容器内还没有音乐目录。请把 NAS 上的音乐文件夹挂载到 /music 后重新启动容器。",
            "path": "",
            "depth": 0,
            "dirs": [],
            "files": [],
            "can_descend": False,
        }
    base_parts = _parts(base)
    path_parts = _parts(path)
    if base_parts and path_parts[:len(base_parts)] != base_parts:
        raise ValueError("只能浏览已选择的目录")
    if picking:
        depth = len(path_parts)
        limit = PICK_MAX_DEPTH
    else:
        depth = len(path_parts) - len(base_parts)
        limit = LIBRARY_MAX_DEPTH
    if depth > limit:
        raise ValueError("最多向下进入 %s 层目录" % limit)
    _, target, rel = resolve_dir(path)
    can_descend = depth < limit
    dirs = []
    files = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        if entry.name.startswith("."):
            continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        if is_dir and can_descend:
            dirs.append(entry.name)
        elif entry.is_file() and entry.suffix.lower() in AUDIO_EXT and not picking:
            item = {"name": entry.name, "size": entry.stat().st_size}
            item.update(parse_filename(entry.name))
            files.append(item)
    return {
        "ok": True,
        "root": str(root),
        "path": rel,
        "base": "/".join(base_parts),
        "depth": depth,
        "limit": limit,
        "dirs": dirs,
        "files": files,
        "can_descend": can_descend,
        "error": "",
    }


def search_files(query, limit=40):
    text = (query or "").strip().lower()
    tokens = [part for part in re.split(r"\s+", text) if part]
    if not tokens:
        return {"ok": True, "files": [], "error": ""}
    root = music_root()
    if not root.exists():
        return {"ok": False, "files": [], "error": "音乐根目录不存在：%s" % root}
    found = []

    def walk(directory, depth):
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                if depth < LIBRARY_MAX_DEPTH:
                    walk(entry, depth + 1)
                continue
            if entry.suffix.lower() not in AUDIO_EXT:
                continue
            rel = entry.relative_to(root).as_posix()
            parsed = parse_filename(entry.name)
            haystack = " ".join([rel, entry.name, parsed["title"], parsed["artist"]]).lower()
            if all(token in haystack for token in tokens):
                found.append({
                    "path": rel,
                    "name": entry.name,
                    "title": parsed["title"],
                    "artist": parsed["artist"],
                    "size": entry.stat().st_size,
                })

    walk(root, 0)
    found.sort(key=lambda item: (
        0 if text in item["title"].lower() or text in item["name"].lower() else 1,
        item["path"].lower(),
    ))
    return {"ok": True, "files": found[:limit], "total": len(found), "error": ""}
