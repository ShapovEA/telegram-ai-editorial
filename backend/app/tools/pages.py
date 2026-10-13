import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura

log = logging.getLogger(__name__)

MAX_BYTES = 4 * 1024 * 1024
MIN_TEXT = 200
USER_AGENT = "Mozilla/5.0 (compatible; AI-SMM-Department/1.0; +https://github.com/)"


class PageError(Exception):
    pass


@dataclass
class Page:
    url: str
    title: str
    text: str
    published: str | None = None


async def _is_public(host: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


async def fetch_html(url: str, *, timeout: float = 20.0) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PageError("неподдерживаемый адрес")
    if not await _is_public(parsed.hostname):
        raise PageError("адрес во внутренней сети запрещён")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"}) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise PageError(f"HTTP {resp.status_code}")
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype and "xml" not in ctype and "text" not in ctype:
                    raise PageError(f"не HTML ({ctype})")
                chunks = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                final_url = str(resp.url)
                encoding = resp.encoding or "utf-8"
    except PageError:
        raise
    except Exception as exc:
        raise PageError(str(exc)) from exc
    return b"".join(chunks).decode(encoding, errors="replace"), final_url


def extract(html: str, url: str) -> Page:
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_precision=True) or ""
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = (meta.title if meta and meta.title else "") or ""
    published = meta.date if meta and meta.date else None
    return Page(url=url, title=title, text=text.strip(), published=published)


async def read_page(url: str) -> Page:
    html, final_url = await fetch_html(url)
    page = await asyncio.to_thread(extract, html, final_url)
    if len(page.text) < MIN_TEXT:
        raise PageError("на странице не найден основной текст")
    return page
