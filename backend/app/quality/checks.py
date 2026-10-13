import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.domain.schemas import Styleguide
from app.quality.detector import EMOJI_RE, URL_RE, Issue, detect, find_phrases

NUM_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](\d+))?(\s*(?:тыс|млн|млрд|трлн)\.?)?", re.IGNORECASE)
SCALE = {"тыс": 1e3, "млн": 1e6, "млрд": 1e9, "трлн": 1e12}
TG_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "blockquote", "code", "pre", "tg-spoiler", "br"}


def _num(int_part: str, frac: str | None) -> float:
    digits = re.sub(r"[   ]", "", int_part)
    return float(f"{digits}.{frac}") if frac else float(digits)


def numbers_in(text: str) -> list[tuple[str, float]]:
    out = []
    for m in NUM_RE.finditer(URL_RE.sub(" ", text)):
        value = _num(m.group(1), m.group(2))
        scale = m.group(3)
        if scale:
            key = scale.strip().rstrip(".").lower()
            value *= SCALE.get(key, 1)
        out.append((m.group(0).strip(), value))
    return out


def _variants(value: float) -> set[float]:
    vs = {round(value, 4), round(value), round(value, 1), round(value, 2)}
    for div in (1e3, 1e6, 1e9):
        if value >= div:
            vs |= {round(value / div, 1), round(value / div), round(value / div, 2)}
            vs.add(round(value / div) * div)
    return vs


def material_numbers(materials: list[str]) -> set[float]:
    found: set[float] = set()
    for text in materials:
        for _, v in numbers_in(text):
            found |= _variants(v)
            if v >= 1000:
                found.add(v)
    return found


def check_numbers(text: str, materials: list[str]) -> list[Issue]:
    known = material_numbers(materials)
    issues = []
    bad = []
    for raw, value in numbers_in(text):
        if value < 11 and float(value).is_integer():
            continue
        if value in known or _variants(value) & known:
            continue
        bad.append(raw)
    if bad:
        uniq = list(dict.fromkeys(bad))
        issues.append(
            Issue(
                code="number",
                message="Числа, которых нет в фактах и вычислениях: " + ", ".join(uniq[:5]),
                fragment=uniq[0],
                suggestion="Используй только числа из фактов; производные числа посчитай инструментом calculate.",
            )
        )
    return issues


def urls_in(text: str) -> list[str]:
    return [u.rstrip(").,;»\"") for u in URL_RE.findall(text)]


def check_tail(text: str, sg: Styleguide) -> list[Issue]:
    signature = sg.structured.signature.strip()
    for line in (ln.strip() for ln in text.splitlines()):
        if line.startswith("Источник:") or (signature and line == signature) or (line and all(t.startswith("#") for t in line.split())):
            return [
                Issue(
                    code="tail",
                    message="В тексте строка, которую добавляет система: источник, подпись или хештеги",
                    fragment=line[:160],
                    suggestion="Убери эту строку: источник, подпись и хештеги система добавит сама.",
                )
            ]
    return []


def check_links(text: str, *, mode: str, fmt: str, allowed: set[str], links_policy: str) -> list[Issue]:
    issues = []
    found = urls_in(text)
    extra = [u for u in found if u not in allowed]
    if links_policy != "free" and extra:
        issues.append(Issue(code="links", message="Ссылки, которых нет в материалах: " + ", ".join(extra[:3]), fragment=extra[0], suggestion="Убери посторонние ссылки."))
    if mode == "smm" and fmt == "text" and links_policy == "none":
        own = [u for u in found if u in allowed]
        if own and not any("t.me/" in u for u in own):
            issues.append(Issue(code="links", message="В SMM-посте не должно быть ссылок", fragment=own[0], critical=False))
    return issues


def check_length(text: str, sg: Styleguide) -> list[Issue]:
    n = len(text.strip())
    s = sg.structured
    if n < s.length_min * 0.85:
        return [Issue(code="length", message=f"Текст короче стайлгайда: {n} символов при минимуме {s.length_min}", suggestion="Добавь конкретики из фактов, а не воды.")]
    if n > s.length_max * 1.1:
        return [Issue(code="length", message=f"Текст длиннее стайлгайда: {n} символов при максимуме {s.length_max}", suggestion="Убери факты, которые не работают на ключевую мысль.")]
    return []


def check_banned(text: str, sg: Styleguide) -> list[Issue]:
    phrases = list(sg.structured.banned_phrases)
    if not phrases:
        return []
    return [
        Issue(code="banned", message=f"Запрещено стайлгайдом канала: «{src}»", fragment=frag, suggestion="Убери или замени по правилу канала.")
        for src, frag in find_phrases(text, phrases)
    ]


def auto_checks(
    *,
    title: str,
    text: str,
    fmt: str,
    mode: str,
    styleguide: Styleguide,
    materials: list[str],
    allowed_urls: set[str],
    extra_stamps: list[str] | None = None,
    whitelist: set[str] | None = None,
) -> list[Issue]:
    issues = detect(text, title=title, fmt=fmt, address=styleguide.structured.address, extra_stamps=extra_stamps, whitelist=whitelist)
    issues += check_banned(f"{title}\n{text}", styleguide)
    if fmt == "text":
        issues += check_length(text, styleguide)
        issues += check_tail(text, styleguide)
    issues += check_numbers(f"{title}\n{text}", materials)
    issues += check_links(text, mode=mode, fmt=fmt, allowed=allowed_urls, links_policy=styleguide.structured.links_policy)
    return issues


class _TagValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.hrefs: list[str] = []
        self.text_parts: list[str] = []
        self._in_a = 0

    def handle_starttag(self, tag, attrs):
        if tag not in TG_TAGS:
            self.errors.append(f"тег <{tag}> не поддерживается Telegram")
            return
        if tag == "br":
            self.text_parts.append("\n")
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if not href:
                self.errors.append("ссылка без href")
            else:
                self.hrefs.append(href)
            self._in_a += 1
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "br":
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"незакрытый или лишний тег </{tag}>")
            return
        self.stack.pop()
        if tag == "a":
            self._in_a -= 1

    def handle_data(self, data):
        if self._in_a:
            self.text_parts.append(" ")
            return
        self.text_parts.append(data)


def _words(text: str) -> list[str]:
    text = EMOJI_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = text.replace("‍", "").replace("️", "")
    return re.findall(r"[\wёЁ]+|[^\w\s]", text)


def check_publisher(body_html: str, writer_text: str, *, allowed_urls: set[str], emoji_max: int) -> list[str]:
    v = _TagValidator()
    try:
        v.feed(body_html)
        v.close()
    except Exception as exc:
        return [f"HTML не разбирается: {exc}"]
    errors = list(v.errors)
    if v.stack:
        errors.append("незакрытые теги: " + ", ".join(v.stack))
    for href in v.hrefs:
        if href not in allowed_urls:
            errors.append(f"ссылка {href} не из текста")
    rendered = "".join(v.text_parts)
    a, b = _words(writer_text), _words(rendered)
    if a != b:
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            if x != y:
                ctx_a = " ".join(a[max(0, i - 4) : i + 4])
                ctx_b = " ".join(b[max(0, i - 4) : i + 4])
                errors.append(f"текст изменён: «{ctx_a}» → «{ctx_b}»")
                break
        else:
            errors.append("текст изменён: разная длина")
    emojis = len(EMOJI_RE.findall(body_html))
    if emojis > emoji_max:
        errors.append(f"эмодзи {emojis}, по стайлгайду не больше {emoji_max}")
    return errors


def domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or url


def safe_html(text: str) -> str:
    return html.escape(text.strip())
