"""Isolated Douyin profile inspector used by the desktop channel importer."""

from __future__ import annotations

import json
import random
import re
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from haizflow.services.video_download import _load_yt_dlp, _youtube_dl_options
from haizflow.vendor.douyin_xbogus import XBogus


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def _cookie_header(auth: dict) -> str:
    yt_dlp = _load_yt_dlp()
    options = _youtube_dl_options(auth)
    with yt_dlp.YoutubeDL(options) as downloader:
        cookies = [
            f"{cookie.name}={cookie.value}"
            for cookie in downloader.cookiejar
            if "douyin.com" in str(cookie.domain or "")
        ]
    return "; ".join(cookies)


def _request(url: str, cookie_header: str, *, timeout: int = 25) -> tuple[bytes, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.douyin.com/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.geturl()


def _resolve_profile_url(url: str, cookie_header: str) -> str:
    if "/user/" in urllib.parse.urlparse(url).path:
        return url
    _body, resolved = _request(url, cookie_header)
    return resolved


def _extract_sec_uid(url: str) -> str:
    match = re.search(r"/user/([A-Za-z0-9_-]+)", urllib.parse.urlparse(url).path)
    if not match:
        raise ValueError("The Douyin link did not resolve to a public profile.")
    return match.group(1)


def _random_ms_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(182)) + "=="


def _query(sec_uid: str, cursor: int, count: int, ms_token: str) -> dict:
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "sec_user_id": sec_uid,
        "max_cursor": str(cursor),
        "count": str(count),
        "locate_query": "false",
        "show_live_replay_strategy": "1",
        "need_time_list": "1",
        "time_list_query": "0",
        "whale_cut_token": "",
        "cut_version": "1",
        "publish_video_strategy_type": "2",
        "from_user_page": "1",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "pc_libra_divert": "Windows",
        "support_h265": "1",
        "support_dash": "0",
        "version_code": "290100",
        "version_name": "29.1.0",
        "cookie_enabled": "true",
        "screen_width": "1536",
        "screen_height": "864",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "139.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "139.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "16",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "200",
        "msToken": ms_token,
    }


def _api_page(sec_uid: str, cursor: int, count: int, cookie_header: str, ms_token: str) -> dict:
    query = urllib.parse.urlencode(_query(sec_uid, cursor, count, ms_token))
    base = f"https://www.douyin.com/aweme/v1/web/aweme/post/?{query}"
    signed_url, _signature, _ua = XBogus(USER_AGENT).build(base)
    body, _resolved = _request(signed_url, cookie_header)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Douyin returned an invalid profile response.")
    status_code = int(payload.get("status_code") or 0)
    if status_code == 2483:
        raise PermissionError("Douyin requires a fresh Edge/Chrome session or cookies.txt.")
    if status_code:
        message = str(payload.get("status_msg") or payload.get("message") or "unknown error")
        raise RuntimeError(f"Douyin profile request failed ({status_code}): {message}")
    return payload


def _cover_url(video: dict) -> str:
    for key in ("cover", "origin_cover", "dynamic_cover"):
        value = video.get(key)
        if not isinstance(value, dict):
            continue
        urls = value.get("url_list") or []
        if urls:
            return str(urls[0])
    return ""


def _candidate(aweme: dict) -> dict | None:
    # Photo notes and slideshows are not valid inputs for the video pipeline.
    if aweme.get("images"):
        return None
    video = aweme.get("video")
    play_address = video.get("play_addr") if isinstance(video, dict) else None
    if not isinstance(play_address, dict):
        return None
    play_urls = play_address.get("url_list") or []
    if not any(isinstance(url, str) and url.startswith(("http://", "https://")) for url in play_urls):
        return None
    remote_id = str(aweme.get("aweme_id") or "").strip()
    if not remote_id:
        return None
    author = aweme.get("author") if isinstance(aweme.get("author"), dict) else {}
    statistics = aweme.get("statistics") if isinstance(aweme.get("statistics"), dict) else {}
    timestamp = aweme.get("create_time")
    try:
        published_at = datetime.fromtimestamp(float(timestamp), timezone.utc).strftime("%Y%m%d")
    except (TypeError, ValueError, OSError):
        published_at = ""
    duration = int(video.get("duration") or aweme.get("duration") or 0)
    if duration > 10_000:
        duration //= 1000
    raw_view_count = statistics.get("play_count")
    try:
        view_count = int(raw_view_count) if raw_view_count is not None else None
    except (TypeError, ValueError):
        view_count = None
    return {
        "remote_video_id": remote_id,
        "source_url": f"https://www.douyin.com/video/{remote_id}",
        "title": str(aweme.get("desc") or f"Video {remote_id}").strip(),
        "platform": "Douyin",
        "uploader": str(author.get("nickname") or "").strip(),
        "duration_seconds": max(0, duration),
        "published_at": published_at,
        "view_count": view_count,
        "thumbnail_url": _cover_url(video),
    }


def inspect_profile(payload: dict) -> dict:
    auth = {
        "cookie_browser": str(payload.get("cookie_browser") or ""),
        "cookie_file": str(payload.get("cookie_file") or ""),
    }
    cookie_header = _cookie_header(auth)
    profile_url = _resolve_profile_url(str(payload.get("url") or ""), cookie_header)
    sec_uid = _extract_sec_uid(profile_url)
    scan_scope = int(payload.get("scan_scope") or 0)
    limit = max(1, min(100, int(payload.get("limit") or 20)))
    ranking = str(payload.get("ranking") or "newest")
    target = (
        scan_scope
        if ranking == "popular" and scan_scope
        else None
        if ranking == "popular"
        else limit
    )
    cursor = 0
    candidates = []
    seen = set()
    channel_name = ""
    ms_token = _random_ms_token()
    while target is None or len(candidates) < target:
        page_size = 20 if target is None else min(20, target - len(candidates))
        page = _api_page(sec_uid, cursor, page_size, cookie_header, ms_token)
        items = page.get("aweme_list") or []
        if not items:
            break
        for aweme in items:
            item = _candidate(aweme) if isinstance(aweme, dict) else None
            if not item or item["remote_video_id"] in seen:
                continue
            seen.add(item["remote_video_id"])
            candidates.append(item)
            channel_name = channel_name or item["uploader"]
        if not page.get("has_more"):
            break
        next_cursor = int(page.get("max_cursor") or 0)
        if next_cursor == cursor:
            break
        cursor = next_cursor
    if not candidates:
        raise RuntimeError("Douyin returned no public videos. Try a fresh browser session.")
    return {"channel_name": channel_name, "candidates": candidates}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        response = inspect_profile(payload)
    except (OSError, ValueError, RuntimeError, PermissionError, urllib.error.URLError) as exc:
        response = {"error": str(exc)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
