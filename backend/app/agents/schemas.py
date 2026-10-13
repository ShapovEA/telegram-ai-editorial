from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StoryScore(BaseModel):
    story: int = Field(description="Номер сюжета из списка")
    significance: int = Field(ge=1, le=5)
    significance_reason: str
    primary_source_url: str = Field(default="", description="Адрес первоисточника, если он есть среди материалов сюжета")


class ScoutAnswer(BaseModel):
    scores: list[StoryScore]


class ChiefAnswer(BaseModel):
    candidate: int = Field(description="Номер кандидата из списка")
    reason: str = Field(description="Почему выбран этот кандидат")
    reader_goal: str
    key_idea: str
    angle: str = Field(default="", description="Подача: новость с разбором, объяснение, практический совет или анализ тренда")


class ChiefFixAnswer(BaseModel):
    action: Literal["rephrase", "switch"]
    candidate: int = Field(description="Номер кандидата: текущий для rephrase, другой для switch")
    reader_goal: str
    key_idea: str
    change_note: str = Field("", description="Что изменено в задании и почему, одно-два предложения")


class Claim(BaseModel):
    claim: str
    status: Literal["confirmed", "unsupported", "contradicted"]
    quote: str = ""


class FactcheckAnswer(BaseModel):
    claims: list[Claim] = Field(max_length=8)
    key_idea_status: Literal["confirmed", "unsupported", "contradicted"]
    key_idea_quote: str = ""
    comment: str = ""


class GoalCheckAnswer(BaseModel):
    status: Literal["confirmed", "narrow", "unsupported"]
    adjusted_key_idea: str = ""
    comment: str = ""


class Fact(BaseModel):
    claim: str = Field(description="Факт по-русски простыми словами")
    quote: str = Field(description="Дословная цитата со страницы")
    source_url: str = Field(description="Адрес страницы, откуда цитата, или calculate")
    date: str = Field(default="", description="Дата или период, к которому относится факт")


class ResearchReport(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)

    @field_validator("facts")
    @classmethod
    def limit(cls, v: list[Fact]) -> list[Fact]:
        return v[:8]


class DraftBase(BaseModel):
    need_facts: bool = False
    questions: list[str] = Field(default_factory=list, max_length=3)
    key_idea: str = ""


class TextDraft(DraftBase):
    title: str = ""
    text: str = ""


class PollDraft(DraftBase):
    intro: str = ""
    question: str = Field(default="", max_length=300)
    options: list[str] = Field(default_factory=list, max_length=10)
    multiple: bool = False

    @field_validator("options")
    @classmethod
    def check_options(cls, v: list[str]) -> list[str]:
        for opt in v:
            if len(opt) > 100:
                raise ValueError("вариант ответа длиннее 100 символов")
        return v


class DigestItem(BaseModel):
    name: str
    description: str
    url: str = ""


class DigestDraft(DraftBase):
    title: str = ""
    intro: str = ""
    items: list[DigestItem] = Field(default_factory=list)
    outro: str = ""


DRAFT_SCHEMAS: dict[str, type[DraftBase]] = {"text": TextDraft, "poll": PollDraft, "digest": DigestDraft}


class Recommendation(BaseModel):
    issue: str
    suggestion: str
    fragment: str = ""
    critical: bool


class Review(BaseModel):
    main_idea: str = ""
    complete: bool = True
    recommendations: list[Recommendation] = Field(default_factory=list)


class ChartData(BaseModel):
    title: str
    kind: Literal["bar", "line"] = "bar"
    labels: list[str]
    values: list[float]
    unit: str = ""


class PublisherAnswer(BaseModel):
    body_html: str
    image_kind: Literal["none", "stock", "chart"] = "none"
    image_query: str = ""
    chart: ChartData | None = None


class Verdicts(BaseModel):
    class Item(BaseModel):
        post: int
        verdict: Literal["same", "development", "different"]

    items: list[Item]


class SameEvent(BaseModel):
    same_event: bool
