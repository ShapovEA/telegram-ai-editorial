from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, Field

from app.domain.enums import Role

Address = Literal["ty", "vy"]
ReasoningLevel = Literal["none", "minimal", "low", "medium", "high"]


BRIEF_TEXT_FIELDS = {
    "about": "О чём канал",
    "audience": "Для кого",
    "goal": "Цель канала",
    "voice": "Как говорить",
    "avoid": "Чего избегать",
    "positions": "Позиции канала",
}

BRIEF_SPEC: dict[str, dict[str, tuple[str, ...]]] = {
    "news": {"fields": ("about", "audience"), "required": ("about", "audience")},
    "smm": {"fields": ("about", "audience", "goal", "voice", "avoid", "positions"), "required": ("about", "audience", "goal", "voice", "avoid")},
}


class Brief(BaseModel):
    about: str = ""
    audience: str = ""
    goal: str = ""
    voice: str = ""
    avoid: str = ""
    positions: str = ""
    samples: list[str] = Field(default_factory=list)
    site_url: str = ""

    @staticmethod
    def fields_for(channel_type: str) -> tuple[str, ...]:
        return BRIEF_SPEC[channel_type]["fields"]

    @staticmethod
    def is_required(channel_type: str, name: str) -> bool:
        return name in BRIEF_SPEC[channel_type]["required"]

    def required_missing(self, channel_type: str) -> list[str]:
        return [name for name in BRIEF_SPEC[channel_type]["required"] if not getattr(self, name).strip()]

    def render(self, channel_type: str) -> str:
        lines = [f"{BRIEF_TEXT_FIELDS[name]}: {getattr(self, name).strip()}" for name in self.fields_for(channel_type) if getattr(self, name).strip()]
        return "\n".join(lines)


class StyleRule(BaseModel):
    id: str
    text: str
    origin: Literal["edits", "user"] = "user"


class StyleStructured(BaseModel):
    address: Address = "ty"
    length_min: int = 500
    length_max: int = 1400
    emoji_max: int = 2
    banned_phrases: list[str] = Field(default_factory=list)
    signature: str = ""
    hashtags: list[str] = Field(default_factory=list)
    links_policy: Literal["source_only", "none", "free"] = "source_only"


class Styleguide(BaseModel):
    structured: StyleStructured = Field(default_factory=StyleStructured)
    text: str = ""
    rules: list[StyleRule] = Field(default_factory=list)

    def render(self) -> str:
        s = self.structured
        address = "на «ты»" if s.address == "ty" else "на «вы»"
        lines = [
            f"Обращение к читателю: {address}.",
            f"Длина текста поста: {s.length_min}–{s.length_max} символов.",
            f"Эмодзи: не больше {s.emoji_max} на пост.",
        ]
        if s.banned_phrases:
            lines.append("Запрещённые слова и обороты канала: " + "; ".join(s.banned_phrases) + ".")
        tail = [f"подпись «{s.signature}»"] if s.signature else []
        if s.hashtags:
            tail.append("хештеги " + " ".join(s.hashtags))
        if tail:
            lines.append(f"В конец поста система сама добавит {' и '.join(tail)}. В текст поста их не пиши.")
        parts = ["\n".join(lines)]
        if self.text.strip():
            parts.append(self.text.strip())
        if self.rules:
            parts.append("Правила канала:\n" + "\n".join(f"- {r.text}" for r in self.rules))
        return "\n\n".join(parts)


class Rubric(BaseModel):
    name: str
    format: Literal["text", "poll", "digest"] = "text"
    share: int = Field(ge=0, le=100)
    description: str = ""
    needs_research: bool = True
    opinion: bool = False


class AudienceSegment(BaseModel):
    name: str
    pains: list[str] = Field(default_factory=list)


class Strategy(BaseModel):
    audience: list[AudienceSegment] = Field(default_factory=list)
    goal: str = ""
    rubrics: list[Rubric] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    notes: str = ""

    def render(self) -> str:
        out = [f"Цель канала: {self.goal}"]
        if self.audience:
            out.append("Аудитория:")
            for seg in self.audience:
                out.append(f"- {seg.name}: " + "; ".join(seg.pains))
        if self.rubrics:
            out.append("Рубрики:")
            for r in self.rubrics:
                out.append(f"- {r.name} ({r.format}, {r.share}%): {r.description}")
        if self.forbidden:
            out.append("Запрещено: " + "; ".join(self.forbidden))
        if self.notes:
            out.append(self.notes)
        return "\n".join(out)


class RoleModel(BaseModel):
    model: str
    fallbacks: list[str] = Field(default_factory=list)
    reasoning: ReasoningLevel = "none"
    temperature: float | None = None


STRONG = "anthropic/claude-sonnet-5"
STRONG_FALLBACK = "openai/gpt-5.6-sol"
LIGHT = "anthropic/claude-haiku-5.5"
LIGHT_FALLBACK = "openai/gpt-5.6-luna"

DEFAULT_ROLE_MODELS: dict[str, RoleModel] = {
    Role.account_manager: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK]),
    Role.designer: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK]),
    Role.strategist: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK]),
    Role.chief: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK]),
    Role.writer: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK], temperature=0.8),
    Role.editor: RoleModel(model=STRONG, fallbacks=[STRONG_FALLBACK], temperature=0.2),
    Role.scout: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.2),
    Role.factchecker: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.0),
    Role.researcher: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.2),
    Role.publisher: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.2),
    Role.analyst: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.2),
    Role.guard: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.0),
    Role.novelty: RoleModel(model=LIGHT, fallbacks=[LIGHT_FALLBACK], temperature=0.0),
}

JUDGE_MODEL = "openai/gpt-5.6-sol"


def _known_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Неизвестный часовой пояс: {value}") from exc
    return value


TimeZoneName = Annotated[str, AfterValidator(_known_zone)]


class NewsSchedule(BaseModel):
    times: list[str] = Field(default_factory=lambda: ["09:00", "14:00", "19:00"])
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    timezone: TimeZoneName = "Europe/Moscow"


class TimeWindow(BaseModel):
    start: str = "09:00"
    end: str = "21:00"


class SmmSchedule(BaseModel):
    posts_per_week: int = 5
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    windows: list[TimeWindow] = Field(default_factory=lambda: [TimeWindow()])
    timezone: TimeZoneName = "Europe/Moscow"


def channel_schedule(channel_type: str, data: dict | None) -> NewsSchedule | SmmSchedule:
    return (NewsSchedule if channel_type == "news" else SmmSchedule).model_validate(data or {})


class ChannelOptions(BaseModel):
    empty_slot_policy: Literal["skip", "evergreen"] = "evergreen"
    smm_approval_lead_hours: int = 24
    smm_autopilot_lead_hours: int = 2
    news_lead_minutes: int = 40
    news_approval_window_minutes: int = 120
    plan_auto_approve_hours: int = 12
    max_review_attempts: int = 3
    max_owner_revisions: int = 3
    story_ttl_hours: int = 72
    novelty_window_days: int = 60
    images: bool = True
