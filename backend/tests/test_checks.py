from app.quality.checks import check_numbers, check_publisher, numbers_in, safe_html


def test_numbers_with_scales():
    values = [v for _, v in numbers_in("Около 60 тысяч человек и 1,5 млн рублей, рост на 12,4%")]
    assert 60000 in values and 1_500_000 in values and 12.4 in values


def test_numbers_found_in_materials():
    materials = ["Выручка выросла до 60 000 рублей, доля составила 12,4%."]
    assert check_numbers("Выручка около 60 тысяч, доля 12,4%.", materials) == []
    issues = check_numbers("Выручка выросла на 37%.", materials)
    assert issues and "37" in issues[0].message


def test_publisher_preserves_text():
    writer = "Банк снизил ставку до 16%. Подробнее в прошлом посте https://t.me/channel/10"
    good = '📉 Банк снизил ставку до <b>16%</b>. Подробнее в прошлом посте <a href="https://t.me/channel/10">t.me</a>'
    assert check_publisher(good, writer, allowed_urls={"https://t.me/channel/10"}, emoji_max=2) == []
    bad = 'Банк понизил ставку до <b>16%</b>. Подробнее <a href="https://evil.com">тут</a>'
    errors = check_publisher(bad, writer, allowed_urls={"https://t.me/channel/10"}, emoji_max=2)
    assert any("изменён" in e for e in errors) and any("evil.com" in e for e in errors)


def test_safe_html_escapes():
    assert safe_html("A <b> & B") == "A &lt;b&gt; &amp; B"
