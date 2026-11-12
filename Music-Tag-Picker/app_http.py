# -*- coding: utf-8 -*-
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 20


def fetch(url, headers=None, data=None, timeout=TIMEOUT):
    merged = {"User-Agent": UA}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=data, headers=merged)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers), response.read()
