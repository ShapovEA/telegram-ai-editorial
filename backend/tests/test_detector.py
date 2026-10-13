from app.quality.detector import detect, find_phrases

AI_TEXT = """Итак, давайте разберёмся, почему это важно.

В современном мире финансовая подушка играет ключевую роль — это не просто запас денег — это свобода.

Как это работает.

Подушка — это быстро, удобно и надёжно. Она защищает, поддерживает и успокаивает. Это не роскошь, а необходимость.

А вы уже откладываете?"""

HUMAN_TEXT = """Финансовая подушка нужна, чтобы потеря работы не превратилась в долги. Обычно советуют держать запас на три–шесть месяцев расходов.

Если тратишь 60 тысяч рублей в месяц, ориентир — от 180 до 360 тысяч. Начать можно с малого: автоперевод 10% зарплаты в день её получения.

Деньги держи там, откуда их можно снять за день без потерь, — на накопительном счёте или вкладе с частичным снятием."""


def test_ai_text_flags_many_issues():
    issues = detect(AI_TEXT, title="Финансовая подушка: что нужно знать", address="ty")
    codes = {i.code for i in issues}
    assert "stamp" in codes
    assert "contrast" in codes
    assert "template_heading" in codes
    assert "rhetorical" in codes
    assert "address" in codes
    assert "title" in codes
    assert "triad" in codes


def test_human_text_is_clean():
    issues = [i for i in detect(HUMAN_TEXT, title="Подушка безопасности на полгода расходов", address="ty") if i.critical]
    assert issues == [], [i.message for i in issues]


def test_lemma_match_word_forms():
    hits = find_phrases("Эти решения играли важную роль в истории.", ["играть важную роль"])
    assert hits and hits[0][1] == "играли важную роль"


def test_exact_forms_do_not_overmatch():
    assert find_phrases("Он представил отчёт.", ["=представь"]) == []
    assert find_phrases("Представь, что ты уволился.", ["=представь"])


def test_jargon_detected_but_products_allowed():
    issues = detect("У Node.js низкая latency, а Rust помогает с deadline.", title="Node.js стал быстрее на треть в тестах")
    jargon = [i for i in issues if i.code == "jargon"]
    assert jargon and "latency" in jargon[0].message and "Node" not in jargon[0].message


def test_russian_dashes_and_single_contrasts_are_not_critical():
    text = (
        "Первичка — это кирпич, регистр — стена, которую из кирпичей складывают. "
        "Смотри не на форму, а на суть. Сдать отчёт вовремя не просто, но реально.\n\n"
        "Срок перенесли, но расслабляться рано: декларацию ждут не в пятницу, а в понедельник."
    )
    critical = [i for i in detect(text, title="Первичка складывается в регистр за месяц", address="ty") if i.critical]
    assert critical == [], [i.message for i in critical]


def test_not_just_x_but_y_is_critical():
    issues = detect("Подушка — это не просто запас денег, а свобода.", title="Подушка на полгода расходов")
    assert any(i.code == "contrast" and i.critical for i in issues)
