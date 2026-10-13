import re
import statistics
from dataclasses import asdict, dataclass
from functools import lru_cache

from app.quality.stamps import DEFAULT_STAMPS, LATIN_WHITELIST, TY_FORMS, VY_FORMS

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\.]*[A-Za-zА-Яа-яЁё]|[A-Za-zА-Яа-яЁё]")
URL_RE = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ0-9])")
NOT_X_BUT_Y_RE = re.compile(r"\bне\s+[^.,;:!?\n]{1,60},\s+а\s+", re.IGNORECASE)
NOT_JUST_RE = re.compile(r"\bне\s+просто\s+[^.!?\n]{1,60}?(?:,\s*а\b|\s+[—–]\s+(?:это|а)\b)", re.IGNORECASE)
TRIAD_RE = re.compile(r"\b([А-Яа-яЁё]{3,}),\s+([А-Яа-яЁё]{3,})\s+и\s+([А-Яа-яЁё]{3,})\b")
HEADING_RE = re.compile(r"^(как|почему|что|зачем|когда|где|кто|чем)\b[^\n]{0,60}[.:]$", re.IGNORECASE)
SYMBOL_RE = re.compile(r"(?<![:/\w])[A-Za-zА-Яа-яЁё0-9]+/[A-Za-zА-Яа-яЁё0-9]+(?![\w/])|~\s?\d|→|->|=>|::|`")
MORAL_START_RE = re.compile(r"^(главное\b|помни|помните|не забывай|не забывайте|запомни|запомните|вывод прост|мораль)", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")

TRIAD_POS = {"ADJF", "ADJS", "ADVB", "INFN", "VERB", "PRTF", "PRTS"}


@dataclass
class Issue:
    code: str
    message: str
    fragment: str = ""
    critical: bool = True
    suggestion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3

    return pymorphy3.MorphAnalyzer(lang="ru")


@lru_cache(maxsize=200_000)
def lemma(word: str) -> str:
    w = word.lower().replace("ё", "е")
    if not re.match(r"[а-я]", w):
        return w
    return _morph().parse(w)[0].normal_form.replace("ё", "е")


@lru_cache(maxsize=50_000)
def pos(word: str) -> str | None:
    w = word.lower()
    if not re.match(r"[а-яё]", w):
        return None
    return _morph().parse(w)[0].tag.POS


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in WORD_RE.finditer(text)]


@dataclass(frozen=True)
class Pattern:
    source: str
    exact: bool
    seq: tuple[str, ...]


@lru_cache(maxsize=64)
def compile_patterns(phrases: tuple[str, ...]) -> tuple[Pattern, ...]:
    out = []
    for raw in phrases:
        p = raw.strip()
        if not p:
            continue
        exact = p.startswith("=")
        body = p[1:] if exact else p
        words = [w for w, _, _ in _tokens(body)]
        if not words:
            continue
        seq = tuple(w.lower().replace("ё", "е") for w in words) if exact else tuple(lemma(w) for w in words)
        out.append(Pattern(source=body, exact=exact, seq=seq))
    return tuple(out)


def find_phrases(text: str, phrases: list[str]) -> list[tuple[str, str]]:
    patterns = compile_patterns(tuple(phrases))
    toks = _tokens(text)
    if not toks:
        return []
    lemmas = [lemma(w) for w, _, _ in toks]
    forms = [w.lower().replace("ё", "е") for w, _, _ in toks]
    hits: list[tuple[str, str]] = []
    seen: set[tuple[int, str]] = set()
    for pat in patterns:
        seq = pat.seq
        n = len(seq)
        source = forms if pat.exact else lemmas
        for i in range(len(toks) - n + 1):
            if tuple(source[i : i + n]) == seq:
                gap_ok = all(re.fullmatch(r"[\s,]*", text[toks[j][2] : toks[j + 1][1]]) for j in range(i, i + n - 1))
                if not gap_ok:
                    continue
                key = (i, pat.source)
                if key in seen:
                    continue
                seen.add(key)
                hits.append((pat.source, text[toks[i][1] : toks[i + n - 1][2]]))
    return hits


def sentences(text: str) -> list[str]:
    parts = []
    for para in re.split(r"\n+", text):
        para = para.strip()
        if para:
            parts.extend(s.strip() for s in SENT_SPLIT_RE.split(para) if s.strip())
    return parts


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]


def _without_urls(text: str) -> str:
    return URL_RE.sub(" ", text)


def check_stamps(text: str, extra: list[str] | None = None) -> list[Issue]:
    issues = []
    for source, fragment in find_phrases(text, DEFAULT_STAMPS + (extra or [])):
        issues.append(
            Issue(
                code="stamp",
                message=f"Оборот-штамп нейросети: «{source}»",
                fragment=fragment,
                suggestion="Убери оборот или скажи то же конкретнее, своими словами.",
            )
        )
    return issues


def check_constructions(text: str, fmt: str = "text") -> list[Issue]:
    issues: list[Issue] = []
    clean = _without_urls(text)
    not_just = [m.group(0) for m in NOT_JUST_RE.finditer(clean)]
    if not_just:
        issues.append(
            Issue(
                code="contrast",
                message="Оборот «не просто X, а Y» — шаблон нейросети",
                fragment=not_just[0].strip(),
                suggestion="Скажи прямо, что это такое, без приёма «не просто».",
            )
        )
    contrasts = [m.group(0) for m in NOT_X_BUT_Y_RE.finditer(clean)]
    if len(contrasts) > 1:
        issues.append(
            Issue(
                code="contrast",
                message=f"Противопоставление «не X, а Y» встречается {len(contrasts)} раза",
                fragment=contrasts[1].strip(),
                critical=False,
                suggestion="Если противопоставления звучат как приём, одно перепиши прямым утверждением.",
            )
        )
    sents = sentences(clean)
    for s in sents:
        if s.count(" — ") + s.count(" – ") >= 3:
            issues.append(
                Issue(
                    code="dash_chain",
                    message="Три тире в одном предложении",
                    fragment=s[:160],
                    critical=False,
                    suggestion="Если тире заменяют точку или запятую, разбей предложение.",
                )
            )
            break
    triads = []
    for m in TRIAD_RE.finditer(clean):
        words = m.groups()
        tags = [pos(w) for w in words]
        if tags[0] in TRIAD_POS and len(set(tags)) == 1:
            triads.append(m.group(0))
    if len(triads) >= 2:
        issues.append(
            Issue(
                code="triad",
                message="Перечисления тройками подряд — характерный ритм нейросети",
                fragment=triads[1],
                suggestion="Оставь одно-два самых точных слова вместо тройки.",
            )
        )
    if fmt != "poll":
        for s in sents:
            if s.rstrip().endswith("?") and not s.lstrip().startswith(("«", '"', "—")):
                issues.append(
                    Issue(
                        code="rhetorical",
                        message="Риторический вопрос или вопрос к аудитории",
                        fragment=s[:160],
                        suggestion="Замени вопрос утверждением.",
                    )
                )
                break
    for p in paragraphs(clean):
        if len(p.split()) <= 7 and HEADING_RE.match(p):
            issues.append(
                Issue(
                    code="template_heading",
                    message="Подзаголовок-шаблон вида «Как это работает.»",
                    fragment=p,
                    suggestion="Убери подзаголовок, пусть абзац начинается с сути.",
                )
            )
            break
    paras = paragraphs(clean)
    if paras:
        last = re.sub(r"^источник:.*$", "", paras[-1], flags=re.IGNORECASE).strip() or (paras[-2] if len(paras) > 1 else "")
        if last and MORAL_START_RE.match(last):
            issues.append(
                Issue(
                    code="moral",
                    message="Нравоучительный вывод в конце",
                    fragment=last[:160],
                    suggestion="Закончи конкретным следствием для читателя, без морали.",
                )
            )
    for m in SYMBOL_RE.finditer(clean):
        frag = m.group(0)
        issues.append(
            Issue(
                code="symbols",
                message="Значки вместо слов",
                fragment=frag,
                suggestion="Пиши словами: «Rust и Go», «около 60 тысяч», без стрелок и косых черт.",
            )
        )
        break
    return issues


def check_jargon(text: str, whitelist: set[str] | None = None) -> list[Issue]:
    allowed = LATIN_WHITELIST | {w.lower() for w in (whitelist or set())}
    found: list[str] = []
    for w, _, _ in _tokens(_without_urls(text)):
        if not re.fullmatch(r"[A-Za-z][A-Za-z\-\.]*", w):
            continue
        lw = w.lower()
        if lw in allowed or len(w) < 3:
            continue
        if w[0].isupper() or any(ch.isupper() for ch in w[1:]) or "." in w:
            continue
        found.append(w)
    if not found:
        return []
    uniq = list(dict.fromkeys(found))
    return [
        Issue(
            code="jargon",
            message="Английские слова вместо русских: " + ", ".join(uniq[:5]),
            fragment=uniq[0],
            suggestion="Замени русскими словами; латиницей — только названия продуктов и компаний.",
        )
    ]


def check_address(text: str, address: str) -> list[Issue]:
    words = [w.lower() for w, _, _ in _tokens(_without_urls(text))]
    ty = [w for w in words if w in TY_FORMS]
    vy = [w for w in words if w in VY_FORMS]
    if address == "ty" and vy:
        return [Issue(code="address", message="Обращение на «вы», а стайлгайд требует «ты»", fragment=vy[0], suggestion="Обращайся к читателю на «ты».")]
    if address == "vy" and ty:
        return [Issue(code="address", message="Обращение на «ты», а стайлгайд требует «вы»", fragment=ty[0], suggestion="Обращайся к читателю на «вы».")]
    return []


def check_rhythm(text: str) -> list[Issue]:
    sents = sentences(_without_urls(text))
    lengths = [len(s.split()) for s in sents if len(s.split()) > 1]
    issues = []
    if len(lengths) >= 6:
        mean = statistics.mean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0
        if cv < 0.3:
            issues.append(
                Issue(
                    code="rhythm",
                    message=f"Однообразный ритм: предложения почти одной длины (в среднем {mean:.0f} слов)",
                    critical=False,
                    suggestion="Чередуй короткие и длинные предложения.",
                )
            )
    paras = [len(p) for p in paragraphs(text)]
    if len(paras) >= 5:
        mean = statistics.mean(paras)
        cv = statistics.pstdev(paras) / mean if mean else 0
        if cv < 0.15:
            issues.append(
                Issue(code="rhythm", message="Абзацы почти одинаковой длины", critical=False, suggestion="Сделай абзацы разной длины по смыслу.")
            )
    return issues


def check_title(title: str, text: str) -> list[Issue]:
    issues = []
    t = title.strip()
    if not t:
        return [Issue(code="title", message="Нет заголовка", suggestion="Добавь заголовок, который сообщает суть.")]
    words = t.split()
    if len(t) > 80:
        issues.append(Issue(code="title", message=f"Заголовок длиннее 80 символов ({len(t)})", fragment=t, suggestion="Сократи до 4–9 слов."))
    if len(words) < 3 or len(words) > 11:
        issues.append(Issue(code="title", message=f"Заголовок из {len(words)} слов, нужно 4–9", fragment=t, critical=len(words) > 12 or len(words) < 3))
    if t.endswith("."):
        issues.append(Issue(code="title", message="Точка в конце заголовка", fragment=t, suggestion="Убери точку."))
    if "!" in t or "?" in t:
        issues.append(Issue(code="title", message="Восклицание или вопрос в заголовке", fragment=t, suggestion="Заголовок — утверждение о сути."))
    if any(q in t for q in "«»\"“”"):
        issues.append(Issue(code="title", message="Кавычки в заголовке", fragment=t))
    if re.search(r":\s*(что|почему|как|зачем|главное|все|всё)\b", t, re.IGNORECASE):
        issues.append(Issue(code="title", message="Шаблон заголовка «X: что/почему/как…»", fragment=t, suggestion="Назови суть: кто, что сделал, какая цифра."))
    if EMOJI_RE.search(t):
        issues.append(Issue(code="title", message="Эмодзи в заголовке", fragment=t))
    if t.isupper() and len(t) > 5:
        issues.append(Issue(code="title", message="Заголовок капсом", fragment=t))
    first = sentences(text)[:1]
    if first:
        tl = {lemma(w) for w, _, _ in _tokens(t) if len(w) > 3}
        fl = {lemma(w) for w, _, _ in _tokens(first[0]) if len(w) > 3}
        if tl and len(tl & fl) / len(tl) >= 0.7:
            issues.append(Issue(code="title_repeat", message="Первая фраза повторяет заголовок", fragment=first[0][:160], suggestion="Первая фраза должна добавлять подробности, а не повторять заголовок."))
    return issues


def check_markup(text: str) -> list[Issue]:
    if re.search(r"<[a-z/][^>]*>|\*\*|__|^#+\s", text, re.IGNORECASE | re.MULTILINE):
        return [Issue(code="markup", message="Разметка в тексте Писателя", suggestion="Пиши обычным текстом, оформление сделает Издатель.")]
    if EMOJI_RE.search(text):
        return [Issue(code="markup", message="Эмодзи в тексте Писателя", suggestion="Эмодзи расставит Издатель.")]
    return []


def detect(
    text: str,
    *,
    title: str = "",
    fmt: str = "text",
    address: str | None = None,
    extra_stamps: list[str] | None = None,
    whitelist: set[str] | None = None,
) -> list[Issue]:
    full = f"{title}\n{text}" if title else text
    issues = check_stamps(full, extra_stamps)
    issues += check_constructions(text, fmt)
    issues += check_jargon(full, whitelist)
    if address:
        issues += check_address(full, address)
    issues += check_rhythm(text)
    issues += check_markup(text)
    if fmt in ("text", "digest"):
        issues += check_title(title, text)
    return issues


def stamp_score(text: str, title: str = "") -> int:
    return sum(1 for i in detect(text, title=title) if i.critical)
