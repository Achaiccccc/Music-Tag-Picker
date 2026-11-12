# Music Tag Picker

音乐标签挑选。部署在绿联 NAS 上的 Docker 应用：浏览本地音乐目录，从网易云、QQ 音乐、咪咕、酷狗列出搜索候选，由用户选定一条后再把标题、歌手、专辑、歌词和封面写入文件。

## 功能

- 左侧目录树最多展开 5 层，树下方可按歌名、歌手、文件名和路径模糊搜索本地文件。
- 点选文件后按「歌名 - 歌手」预填，可以直接修改。
- 可勾选一个或多个平台。候选不截成前 10 条，现场版和翻唱会保留。
- 确认后才写入。支持 `mp3`、`wav`、`flac`、`ogg`、`opus`、`m4a`、`mp4`、`aac`。

## 运行

在本目录执行：

```bash
docker compose up -d --build
```

把 `docker-compose.yml` 里冒号左侧换成 NAS 上的音乐目录，容器内固定为 `/music`。浏览器访问 `http://<NAS地址>:8090`。

## 许可

Copyright (C) 2026 Achaiccccc

本程序是自由软件。你可以按照 GNU General Public License 第 3 版（GPL-3.0）的条款重新分发和修改它。完整文本见同目录的 [LICENSE](LICENSE)。
