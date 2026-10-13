from app.domain.schemas import Brief
from app.services.samples import classify


def test_news_brief_requires_only_about_and_audience():
    brief = Brief(about="Новости бухгалтерского учёта в РФ")
    assert brief.required_missing("news") == ["audience"]
    assert Brief(about="a", audience="b").required_missing("news") == []


def test_smm_brief_requires_voice_and_goal():
    brief = Brief(about="a", audience="b")
    assert brief.required_missing("smm") == ["goal", "voice", "avoid"]


def test_render_uses_only_fields_of_channel_type():
    brief = Brief(about="Налоги", audience="Бухгалтеры", goal="Продажи курсов", voice="На «вы»")
    news = brief.render("news")
    assert "Налоги" in news and "Бухгалтеры" in news
    assert "Продажи курсов" not in news and "На «вы»" not in news
    assert "Продажи курсов" in brief.render("smm")


def test_classify_samples():
    assert classify("@buhnews") == ("channel", "buhnews")
    assert classify("https://t.me/buhnews") == ("channel", "buhnews")
    assert classify("t.me/buhnews/1234") == ("post", "buhnews/1234")
    assert classify("https://example.com/article") == ("page", "https://example.com/article")
    assert classify("ФНС разъяснила порядок уплаты налога")[0] == "text"


def test_schedule_rejects_unknown_timezone():
    import pytest
    from pydantic import ValidationError

    from app.domain.schemas import NewsSchedule

    assert NewsSchedule(timezone="America/Argentina/Buenos_Aires").timezone == "America/Argentina/Buenos_Aires"
    with pytest.raises(ValidationError):
        NewsSchedule(timezone="Europe/Moskva")
