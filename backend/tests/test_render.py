from app.domain.schemas import Styleguide, StyleStructured
from app.graphs.common import main_source_url
from app.graphs.post.render import compose_html
from app.quality.checks import check_tail

SG = Styleguide(structured=StyleStructured(signature="— Пьяный бухгалтер", hashtags=["#учет", "#налоги"]))
URL = "https://www.consultant.ru/document/cons_doc_LAW_122855/"


def test_tail_is_composed_by_code_in_order():
    out = compose_html("Заголовок", "Текст поста.", SG, URL)
    assert out == (
        "<b>Заголовок</b>\n\nТекст поста.\n\n"
        f'Источник: <a href="{URL}">consultant.ru</a>\n\n— Пьяный бухгалтер\n\n#учет #налоги'
    )


def test_no_source_line_without_source():
    assert "Источник" not in compose_html("", "Текст.", SG)


def test_writer_tail_lines_are_flagged():
    assert check_tail(f"Текст.\n\nИсточник: {URL}", SG)
    assert check_tail("Текст.\n\n— Пьяный бухгалтер", SG)
    assert check_tail("Текст.\n\n#учет #налоги", SG)
    assert check_tail("Про #учет в середине строки.", SG) == []


def test_main_source_prefers_news_source_then_most_cited_fact():
    facts = [{"source_url": URL}, {"source_url": URL}, {"source_url": "https://other.ru"}, {"source_url": "calculate"}]
    assert main_source_url({"brief": {"mode": "news", "source": {"url": "https://news.ru/1"}}, "facts": facts}) == "https://news.ru/1"
    assert main_source_url({"brief": {"mode": "news", "source": None}, "facts": facts}) == URL
    assert main_source_url({"brief": {"mode": "news", "source": None}, "facts": []}) is None
    assert main_source_url({"brief": {"mode": "smm"}, "facts": facts}) is None
