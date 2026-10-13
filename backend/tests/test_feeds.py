import pytest

from app.services import feeds
from app.tools import pages

ARTICLE = "Полный текст статьи. " * 40
FEED_CONTENT = "Текст из ленты целиком. " * 30


def fake_page(text: str | None):
    async def read_page(url: str) -> pages.Page:
        if text is None:
            raise pages.PageError("HTTP 403")
        return pages.Page(url=url, title="", text=text)

    return read_page


@pytest.mark.parametrize(
    ("page", "content", "expected"),
    [
        (ARTICLE, "", ARTICLE),
        (None, FEED_CONTENT, FEED_CONTENT),
        (ARTICLE, FEED_CONTENT, ARTICLE),
        (None, "Короткий анонс", ""),
        (None, "", ""),
    ],
)
async def test_article_text_takes_fullest_text(monkeypatch, page, content, expected):
    monkeypatch.setattr(pages, "read_page", fake_page(page))
    assert await feeds.article_text("https://example.com/a", content) == expected


async def test_full_text_available(monkeypatch):
    monkeypatch.setattr(pages, "read_page", fake_page(None))
    assert await feeds.full_text_available([{"url": "https://example.com/a", "full_text": False}]) is False
    assert await feeds.full_text_available([{"url": "https://example.com/a", "full_text": True}]) is True
    monkeypatch.setattr(pages, "read_page", fake_page(ARTICLE))
    assert await feeds.full_text_available([{"url": "https://example.com/a", "full_text": False}]) is True
