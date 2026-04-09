from __future__ import annotations

# Portions of this file are adapted from jiji262/douyin-downloader
# (MIT License, Copyright (c) 2026 jiji262).
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# Portions of the X-Bogus signing logic are adapted from Evil0ctal's
# Douyin_TikTok_Download_API project under the Apache License 2.0.

import asyncio
import base64
import hashlib
import json
import random
import re
import string
import subprocess
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import requests
from yt_dlp.cookies import extract_cookies_from_browser

try:
    from .douyin_abogus import ABogus, BrowserFingerprintGenerator
except ImportError:
    from douyin_abogus import ABogus, BrowserFingerprintGenerator


DOUYIN_BASE_URL = "https://www.douyin.com"
DOUYIN_REFERER = f"{DOUYIN_BASE_URL}/"
DOUYIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DETAIL_AID_CANDIDATES = ("6383", "1128")
USER_AGENT_POOL = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0"
    ),
]


class DouyinDownloadError(RuntimeError):
    """Raised when the dedicated Douyin provider cannot fetch a playable asset."""


class XBogus:
    def __init__(self, user_agent: str | None = None) -> None:
        self._array = [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, 10, 11, 12, 13, 14, 15,
        ]
        self._character = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
        self._ua_key = b"\x00\x01\x0c"
        self._user_agent = user_agent or DOUYIN_USER_AGENT

    def _md5_str_to_array(self, md5_str: str) -> list[int]:
        if isinstance(md5_str, str) and len(md5_str) > 32:
            return [ord(char) for char in md5_str]

        array: list[int] = []
        index = 0
        while index < len(md5_str):
            array.append(
                (self._array[ord(md5_str[index])] << 4)
                | self._array[ord(md5_str[index + 1])]
            )
            index += 2
        return array

    def _md5(self, input_data: str | list[int]) -> str:
        data = self._md5_str_to_array(input_data) if isinstance(input_data, str) else input_data
        md5_hash = hashlib.md5()
        md5_hash.update(bytes(data))
        return md5_hash.hexdigest()

    def _md5_encrypt(self, url_path: str) -> list[int]:
        hashed = self._md5(self._md5_str_to_array(self._md5(url_path)))
        return self._md5_str_to_array(hashed)

    def _encoding_conversion(
        self, a, b, c, e, d, t, f, r, n, o, i, _, x, u, s, l, v, h, p
    ) -> str:
        payload = [a]
        payload.append(int(i))
        payload.extend([b, _, c, x, e, u, d, s, t, l, f, v, r, h, n, p, o])
        return bytes(payload).decode("ISO-8859-1")

    @staticmethod
    def _encoding_conversion2(a: int, b: int, c: str) -> str:
        return chr(a) + chr(b) + c

    @staticmethod
    def _rc4_encrypt(key: bytes, data: bytes) -> bytearray:
        s = list(range(256))
        j = 0
        encrypted = bytearray()

        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) % 256
            s[i], s[j] = s[j], s[i]

        i = j = 0
        for byte in data:
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            encrypted.append(byte ^ s[(s[i] + s[j]) % 256])

        return encrypted

    def _calculation(self, a1: int, a2: int, a3: int) -> str:
        x3 = ((a1 & 255) << 16) | ((a2 & 255) << 8) | (a3 & 255)
        return (
            self._character[(x3 & 16515072) >> 18]
            + self._character[(x3 & 258048) >> 12]
            + self._character[(x3 & 4032) >> 6]
            + self._character[x3 & 63]
        )

    def build(self, url: str) -> tuple[str, str, str]:
        ua_md5_array = self._md5_str_to_array(
            self._md5(
                base64.b64encode(
                    self._rc4_encrypt(
                        self._ua_key, self._user_agent.encode("ISO-8859-1")
                    )
                ).decode("ISO-8859-1")
            )
        )
        empty_md5_array = self._md5_str_to_array(
            self._md5(self._md5_str_to_array("d41d8cd98f00b204e9800998ecf8427e"))
        )
        url_md5_array = self._md5_encrypt(url)

        timer = int(time.time())
        ct = 536919696
        new_array = [
            64,
            0.00390625,
            1,
            12,
            url_md5_array[14],
            url_md5_array[15],
            empty_md5_array[14],
            empty_md5_array[15],
            ua_md5_array[14],
            ua_md5_array[15],
            timer >> 24 & 255,
            timer >> 16 & 255,
            timer >> 8 & 255,
            timer & 255,
            ct >> 24 & 255,
            ct >> 16 & 255,
            ct >> 8 & 255,
            ct & 255,
        ]

        xor_result = new_array[0]
        for value in new_array[1:]:
            xor_result ^= int(value)
        new_array.append(xor_result)

        first_half: list[int] = []
        second_half: list[int] = []
        for index, value in enumerate(new_array):
            if index % 2 == 0:
                first_half.append(value)
            else:
                second_half.append(value)
        merged = first_half + second_half

        garbled = self._encoding_conversion2(
            2,
            255,
            self._rc4_encrypt(
                "ÿ".encode("ISO-8859-1"),
                self._encoding_conversion(*merged).encode("ISO-8859-1"),
            ).decode("ISO-8859-1"),
        )

        xb = ""
        index = 0
        while index < len(garbled):
            xb += self._calculation(
                ord(garbled[index]),
                ord(garbled[index + 1]),
                ord(garbled[index + 2]),
            )
            index += 3

        return f"{url}&X-Bogus={xb}", xb, self._user_agent


class DouyinAPIClient:
    BASE_URL = DOUYIN_BASE_URL

    def __init__(self, cookies: dict[str, str]):
        self.cookies = dict(cookies or {})
        self._session: aiohttp.ClientSession | None = None
        selected_ua = random.choice(USER_AGENT_POOL)
        self.headers = {
            "User-Agent": selected_ua,
            "Referer": DOUYIN_REFERER,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }
        self._signer = XBogus(self.headers["User-Agent"])
        self._ms_token = (self.cookies.get("msToken") or "").strip()
        self._abogus_enabled = True

    async def __aenter__(self) -> "DouyinAPIClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _ensure_session(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                cookies=self.cookies,
                timeout=aiohttp.ClientTimeout(total=30),
                raise_for_status=False,
            )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _default_query(self) -> dict[str, str]:
        ms_token = self._ms_token or self.cookies.get("msToken") or _generate_false_ms_token()
        self._ms_token = ms_token
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "130.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "130.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "12",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "100",
            "msToken": ms_token,
        }

    def sign_url(self, url: str) -> tuple[str, str]:
        signed_url, _, ua = self._signer.build(url)
        return signed_url, ua

    def build_signed_path(self, path: str, params: dict[str, str]) -> tuple[str, str]:
        query = urlencode(params)
        base_url = f"{self.BASE_URL}{path}"
        ab_signed = self._build_abogus_url(base_url, query)
        if ab_signed:
            return ab_signed
        return self.sign_url(f"{base_url}?{query}")

    def _build_abogus_url(self, base_url: str, query: str) -> tuple[str, str] | None:
        if not self._abogus_enabled:
            return None

        try:
            browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Edge")
            signer = ABogus(fp=browser_fp, user_agent=self.headers["User-Agent"])
            params_with_ab, _, user_agent, _ = signer.generate_abogus(query, "")
            return f"{base_url}?{params_with_ab}", user_agent
        except Exception:
            return None

    async def _request_json(
        self,
        path: str,
        params: dict[str, str],
        *,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        await self._ensure_session()
        if self._session is None:
            return {}

        delays = [1, 2, 5]
        last_error = "抖音详情接口没有返回可用视频信息。"

        for attempt in range(max_retries):
            signed_url, user_agent = self.build_signed_path(path, params)
            try:
                async with self._session.get(
                    signed_url,
                    headers={**self.headers, "User-Agent": user_agent},
                ) as response:
                    if response.status != 200:
                        last_error = f"抖音详情接口返回 HTTP {response.status}。"
                    else:
                        raw_text = await response.text()
                        if not raw_text.strip():
                            last_error = "抖音详情接口返回了空响应，通常说明当前链路被平台静默拦截。"
                        else:
                            try:
                                payload = json.loads(raw_text)
                            except json.JSONDecodeError:
                                if "verify" in raw_text.lower() or "captcha" in raw_text.lower():
                                    last_error = "抖音详情接口返回了验证页，当前登录态需要重新验证。"
                                else:
                                    last_error = "抖音详情接口返回的不是 JSON，通常说明平台临时触发了风控。"
                            else:
                                if isinstance(payload, dict):
                                    return payload
                                last_error = "抖音详情接口返回了非字典响应。"
            except aiohttp.ClientError as exc:
                last_error = f"抖音详情接口请求失败：{exc}"

            if attempt < max_retries - 1:
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])

        raise DouyinDownloadError(last_error)

    async def get_video_detail(self, aweme_id: str) -> dict[str, Any]:
        last_error = "抖音详情接口没有返回可用视频信息。"

        for aid in DETAIL_AID_CANDIDATES:
            params = await self._default_query()
            params.update({"aweme_id": aweme_id, "aid": aid})
            payload = await self._request_json("/aweme/v1/web/aweme/detail/", params)

            detail = payload.get("aweme_detail")
            if isinstance(detail, dict) and detail.get("aweme_id"):
                return detail

            filter_detail = payload.get("filter_detail") or {}
            if isinstance(filter_detail, dict) and filter_detail.get("filter_reason"):
                last_error = f"抖音详情接口过滤了这条内容：{filter_detail['filter_reason']}"
                continue

            not_login_module = payload.get("not_login_module") or {}
            if isinstance(not_login_module, dict) and not_login_module.get("guide_login_tip_exist"):
                last_error = "抖音要求补充登录验证，请重新登录浏览器中的抖音后再试。"
                continue

            if payload.get("verify_ticket"):
                last_error = "抖音当前触发了验证页，请在浏览器里完成验证后重试。"
                continue

            status_code = payload.get("status_code")
            if status_code not in (None, 0):
                last_error = f"抖音详情接口返回 status_code={status_code}。"

        raise DouyinDownloadError(last_error)


def download_douyin_media(
    *,
    url: str,
    preset_name: str,
    output_dir: Path,
    cookie_options: dict[str, Any],
    ffmpeg_bin: str,
    audio_bitrate: str,
) -> dict[str, Any]:
    cookies = _load_cookies(cookie_options)
    if not cookies:
        raise DouyinDownloadError(
            "抖音专用下载链路没有拿到可用 Cookies。请重新登录抖音，并启用浏览器登录态或更新 cookies.txt。"
        )
    cookies.setdefault("msToken", _generate_false_ms_token())

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DOUYIN_USER_AGENT,
            "Referer": DOUYIN_REFERER,
            "Origin": DOUYIN_BASE_URL,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }
    )
    session.trust_env = False
    session.cookies.update(cookies)

    resolved_url = _resolve_douyin_url(session, url)
    aweme_id = _extract_aweme_id(resolved_url) or _extract_aweme_id(url)
    if not aweme_id:
        raise DouyinDownloadError("没有从这条抖音链接里解析出视频 ID，请换成网页链接或分享短链后重试。")

    detail, detail_user_agent = _fetch_video_detail(cookies, aweme_id)
    title = _coerce_title(detail, aweme_id)
    stem = _sanitize_output_component(f"{title} [{aweme_id}]")
    artifact_dir = output_dir / stem
    artifact_dir.mkdir(parents=True, exist_ok=True)

    video_path = artifact_dir / f"{stem}.mp4"
    media_url, headers = _select_video_download(detail, detail_user_agent)
    _download_file(session, media_url, video_path, headers=headers)

    final_path = video_path
    if preset_name == "Best Audio (MP3)":
        audio_path = artifact_dir / f"{stem}.mp3"
        _convert_to_mp3(
            input_path=video_path,
            output_path=audio_path,
            ffmpeg_bin=ffmpeg_bin,
            bitrate=audio_bitrate,
        )
        video_path.unlink(missing_ok=True)
        final_path = audio_path

    return {
        "title": title,
        "download_path": final_path,
        "artifact_dir": artifact_dir,
        "aweme_id": aweme_id,
        "resolved_url": resolved_url,
    }


def _fetch_video_detail(cookies: dict[str, str], aweme_id: str) -> tuple[dict[str, Any], str]:
    return asyncio.run(_fetch_video_detail_async(cookies, aweme_id))


async def _fetch_video_detail_async(
    cookies: dict[str, str],
    aweme_id: str,
) -> tuple[dict[str, Any], str]:
    async with DouyinAPIClient(cookies) as client:
        detail = await client.get_video_detail(aweme_id)
        return detail, client.headers["User-Agent"]


def _resolve_douyin_url(session: requests.Session, url: str) -> str:
    if _extract_aweme_id(url):
        return url

    try:
        response = session.get(
            url,
            headers={"User-Agent": session.headers["User-Agent"], "Referer": DOUYIN_REFERER},
            allow_redirects=True,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise DouyinDownloadError(f"抖音分享链接跳转失败：{exc}") from exc

    resolved_url = response.url or url
    if _extract_aweme_id(resolved_url):
        return resolved_url

    match = re.search(r"https?://www\.douyin\.com/video/\d+", response.text)
    if match:
        return match.group(0)

    raise DouyinDownloadError("抖音分享短链跳转后没有拿到可识别的视频地址。")


def _select_video_download(detail: dict[str, Any], user_agent: str) -> tuple[str, dict[str, str]]:
    video = detail.get("video") or {}
    play_addr = video.get("play_addr") or {}
    candidates = [candidate for candidate in play_addr.get("url_list") or [] if candidate]
    candidates.sort(key=lambda candidate: 0 if "watermark=0" in candidate else 1)

    for candidate in candidates:
        parsed = urlparse(candidate)
        headers = _download_headers(user_agent)
        if parsed.netloc.endswith("douyin.com"):
            signed_url, _, signed_ua = XBogus(user_agent).build(candidate)
            return signed_url, _download_headers(signed_ua)
        return candidate, headers

    uri = play_addr.get("uri") or video.get("vid") or (video.get("download_addr") or {}).get("uri")
    if not uri:
        raise DouyinDownloadError("抖音详情里没有找到可播放的视频地址。")

    signer = XBogus(user_agent)
    params = {
        "video_id": uri,
        "ratio": "1080p",
        "line": "0",
        "is_play_url": "1",
        "watermark": "0",
        "source": "PackSourceEnum_PUBLISH",
    }
    signed_url, _, signed_ua = signer.build(
        f"{DOUYIN_BASE_URL}/aweme/v1/play/?{urlencode(params)}"
    )
    return signed_url, _download_headers(signed_ua)


def _download_file(
    session: requests.Session,
    url: str,
    target_path: Path,
    *,
    headers: dict[str, str],
) -> None:
    temp_path = target_path.with_suffix(f"{target_path.suffix}.part")
    try:
        with session.get(url, headers=headers, stream=True, timeout=60) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temp_path.replace(target_path)
    except requests.RequestException as exc:
        temp_path.unlink(missing_ok=True)
        raise DouyinDownloadError(f"抖音视频下载失败：{exc}") from exc


def _convert_to_mp3(
    *,
    input_path: Path,
    output_path: Path,
    ffmpeg_bin: str,
    bitrate: str,
) -> None:
    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        output_path.unlink(missing_ok=True)
        raise DouyinDownloadError("抖音视频已拿到，但转换 MP3 失败，请检查 ffmpeg 是否可用。") from exc


def _coerce_title(detail: dict[str, Any], aweme_id: str) -> str:
    for key in ("desc", "preview_title"):
        candidate = (detail.get(key) or "").strip()
        if candidate:
            return candidate
    author = detail.get("author") or {}
    nickname = (author.get("nickname") or "").strip()
    return nickname or f"Douyin {aweme_id}"


def _download_headers(user_agent: str) -> dict[str, str]:
    return {
        "Referer": DOUYIN_REFERER,
        "Origin": DOUYIN_BASE_URL,
        "Accept": "*/*",
        "User-Agent": user_agent,
    }


def _default_query(ms_token: str) -> dict[str, str]:
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "version_code": "290100",
        "version_name": "29.1.0",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "130.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "130.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "12",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "100",
        "msToken": ms_token,
    }


def _extract_aweme_id(url: str) -> str | None:
    patterns = (
        r"/video/(\d+)",
        r"/share/video/(\d+)",
        r"modal_id=(\d+)",
        r"aweme_id=(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    parsed = urlparse(url)
    query_values = parse_qs(parsed.query)
    for key in ("modal_id", "aweme_id"):
        values = query_values.get(key) or []
        if values and values[0].isdigit():
            return values[0]
    return None


def _sanitize_output_component(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    return sanitized or "untitled"


def _generate_false_ms_token() -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(182)) + "=="


def _load_cookies(cookie_options: dict[str, Any]) -> dict[str, str]:
    cookiefile = cookie_options.get("cookiefile")
    if cookiefile:
        return _load_cookies_from_file(str(cookiefile))

    browser_spec = cookie_options.get("cookiesfrombrowser")
    if browser_spec:
        browser_name, profile, keyring, container = browser_spec
        return _load_cookies_from_browser(
            browser_name=str(browser_name),
            profile=profile,
            keyring=keyring,
            container=container,
        )

    return {}


def _load_cookies_from_file(cookiefile: str) -> dict[str, str]:
    cookie_path = Path(cookiefile).expanduser().resolve()
    if not cookie_path.exists():
        return {}

    jar = MozillaCookieJar(str(cookie_path))
    jar.load(ignore_discard=True, ignore_expires=True)
    return _cookiejar_to_dict(jar)


def _load_cookies_from_browser(
    *,
    browser_name: str,
    profile: str | None,
    keyring: str | None,
    container: str | None,
) -> dict[str, str]:
    jar = extract_cookies_from_browser(
        browser_name,
        profile=profile,
        keyring=keyring,
        container=container,
    )
    return _cookiejar_to_dict(jar)


def _cookiejar_to_dict(cookie_jar: Any) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for cookie in cookie_jar:
        if not _is_douyin_cookie_domain(getattr(cookie, "domain", "")):
            continue
        name = str(getattr(cookie, "name", "")).strip()
        if not name or not _is_valid_cookie_name(name):
            continue
        cookies[name] = str(getattr(cookie, "value", "")).strip()
    return cookies


def _is_douyin_cookie_domain(domain: str) -> bool:
    lowered = (domain or "").lower()
    return "douyin.com" in lowered or "iesdouyin.com" in lowered


def _is_valid_cookie_name(name: str) -> bool:
    invalid = set('()<>@,;:\\"/[]?={} \t\r\n')
    if not name:
        return False
    if any(ord(char) < 33 or ord(char) > 126 for char in name):
        return False
    return not any(char in invalid for char in name)
