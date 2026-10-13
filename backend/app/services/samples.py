import html
import logging
import re
from dataclasses import dataclass

import httpx

from app.security import injection
from app.tools import pages

log = logging.getLogger(__name__)

MSG_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
POST_RE = re.compile(r"^(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]{4,64})/(\d+)/?(?:\?.*)?$")
CHANNEL_RE = re.compile(r"^(?:(?:https?://)?t\.me/(?:s/)?|@)([A-Za-z0-9_]{4,64})/?$")
URL_RE = re.compile(r"^https?://\S+$")

MIN_TEXT = 80
MAX_SAMPLES = 8


@dataclass
class Sample:
    source: str
    text: str


def classify(item: str) -> tuple[str, str]:
    item = item.strip()
    if m := POST_RE.match(item):
        return "post", f"{m.group(1)}/{m.group(2)}"
    if m := CHANNEL_RE.match(item):
        return "channel", m.group(1)
    if URL_RE.match(item):
        return "page", item
    return "text", item


def _clean(fragment: str) -> str:
    fragment = fragment.replace("<br/>", "\n").replace("<br>", "\n")
    return html.unescape(TAG_RE.sub("", fragment)).strip()


async def _telegram_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": pages.USER_AGENT}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def channel_posts(name: str, limit: int = 6) -> list[str]:
    try:
        body = await _telegram_html(f"https://t.me/s/{name}")
    except Exception as exc:
        log.warning("sample channel %s failed: %s", name, exc)
        return []
    posts = [_clean(m) for m in MSG_RE.findall(body)]
    return [p for p in posts if len(p) >= MIN_TEXT][-limit:]


async def single_post(path: str) -> str:
    try:
        body = await _telegram_html(f"https://t.me/{path}?embed=1&mode=tme")
    except Exception as exc:
        log.warning("sample post %s failed: %s", path, exc)
        return ""
    found = MSG_RE.findall(body)
    return _clean(found[0]) if found else ""


async def _fetch(kind: str, value: str) -> list[Sample]:
    if kind == "channel":
        return [Sample(f"t.me/{value}", t) for t in await channel_posts(value)]
    if kind == "post":
        text = await single_post(value)
        return [Sample(f"t.me/{value}", text)] if text else []
    if kind == "page":
        try:
            page = await pages.read_page(value)
        except pages.PageError as exc:
            log.warning("sample page %s failed: %s", value, exc)
            return []
        return [Sample(value, page.text[:3000])]
    return [Sample("вставлен владельцем", value)] if len(value) >= MIN_TEXT else []


async def collect(samples: list[str], site_url: str = "") -> dict:
    out: dict = {"samples": [], "site": "", "rejected": []}
    for item in samples:
        if len(out["samples"]) >= MAX_SAMPLES:
            break
        kind, value = classify(item)
        for sample in await _fetch(kind, value):
            if kind != "text":
                verdict = await injection.check(sample.text, source=sample.source)
                if verdict.injection:
                    out["rejected"].append(sample.source)
                    continue
            out["samples"].append({"source": sample.source, "text": sample.text[:1500]})
    if site_url:
        try:
            page = await pages.read_page(site_url)
            verdict = await injection.check(page.text[:6000], source=site_url)
            if verdict.injection:
                out["rejected"].append(site_url)
            else:
                out["site"] = page.text[:3000]
        except pages.PageError as exc:
            log.warning("site read failed: %s", exc)
    return out
