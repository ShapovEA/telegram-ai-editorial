import html

from app.domain.schemas import Styleguide
from app.quality.checks import domain_label, safe_html, urls_in

FORMAT_NAMES = {"text": "пост", "poll": "опрос", "digest": "подборка"}


def urls(text: str) -> list[str]:
    return urls_in(text)


def digest_text(d: dict) -> str:
    parts = [d.get("intro", "").strip()]
    for item in d.get("items") or []:
        parts.append(f"{item['name']} — {item['description']}".strip())
    if d.get("outro"):
        parts.append(d["outro"].strip())
    return "\n\n".join(p for p in parts if p)


def poll_text(d: dict) -> str:
    opts = "\n".join(f"- {o}" for o in d.get("options") or [])
    return f"{d.get('intro', '')}\n\nВопрос: {d.get('question', '')}\nВарианты:\n{opts}".strip()


def draft_title_text(d: dict, fmt: str) -> tuple[str, str]:
    if fmt == "poll":
        return "", poll_text(d)
    if fmt == "digest":
        return d.get("title", ""), digest_text(d)
    return d.get("title", ""), d.get("text", "")


def draft_text(d: dict, fmt: str) -> str:
    title, text = draft_title_text(d, fmt)
    return f"Заголовок: {title}\n\n{text}" if title else text


def _tail(sg: Styleguide, source_url: str | None) -> str:
    parts = []
    if source_url:
        parts.append(f'Источник: <a href="{html.escape(source_url, quote=True)}">{html.escape(domain_label(source_url))}</a>')
    if sg.structured.signature:
        parts.append(html.escape(sg.structured.signature))
    if sg.structured.hashtags:
        parts.append(" ".join(html.escape(h if h.startswith("#") else f"#{h}") for h in sg.structured.hashtags))
    return "\n\n".join(parts)


def compose_html(title: str, body_html: str, sg: Styleguide, source_url: str | None = None) -> str:
    head = f"<b>{html.escape(title.strip())}</b>\n\n" if title.strip() else ""
    tail = _tail(sg, source_url)
    return head + body_html.strip() + (f"\n\n{tail}" if tail else "")


def format_non_text(d: dict, fmt: str, sg: Styleguide) -> dict:
    if fmt == "poll":
        intro = safe_html(d.get("intro", "")) if d.get("intro") else ""
        return {
            "html": compose_html("", intro, sg) if intro else "",
            "body_html": intro,
            "poll": {"question": d.get("question", ""), "options": d.get("options") or [], "multiple": bool(d.get("multiple"))},
            "image_kind": "none",
            "fallback": False,
        }
    lines = [html.escape(d.get("intro", "").strip())] if d.get("intro") else []
    for item in d.get("items") or []:
        name = html.escape(item["name"])
        if item.get("url"):
            name = f'<a href="{html.escape(item["url"], quote=True)}">{name}</a>'
        lines.append(f"• <b>{name}</b> — {html.escape(item['description'])}")
    if d.get("outro"):
        lines.append(html.escape(d["outro"].strip()))
    body = "\n\n".join(lines)
    return {"html": compose_html(d.get("title", ""), body, sg), "body_html": body, "image_kind": "none", "fallback": False}


def plain_text(d: dict, fmt: str) -> str:
    title, text = draft_title_text(d, fmt)
    return text
