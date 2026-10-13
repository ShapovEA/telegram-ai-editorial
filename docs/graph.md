# Графы и State

## Состав

Работа отдела разбита на несколько графов LangGraph по видам задач. Каждый запуск — отдельный поток (`thread_id = run_id`) с checkpointer на Postgres: запуск переживает перезапуск воркера и продолжается с последнего успешного узла.

| Граф | Когда запускается | Агенты |
|---|---|---|
| `onboarding` | Создание канала, правка брифа | Аккаунт-менеджер, Стратег |
| `planning` | SMM: раз в неделю, «Перепланировать», «Заменить тему», «+ слот» | Стратег |
| `post` | Каждый слот публикации | Скаут, Шеф, Фактчекер, Исследователь, Писатель, Редактор, Издатель |
| `analytics` | SMM: раз в месяц | Аналитик, Стратег |

Работа без LLM идёт фоновыми задачами вне графов: сбор RSS, склейка сюжетов, синхронизация каталога моделей, сбор реакций, планировщик слотов, публикация в назначенное время.

Стоимость и события запусков не хранятся в State. Их пишет callback в `llm_calls` и `run_events`, поэтому State остаётся компактным.

Тип канала задаётся при создании и не меняется, поэтому ветки по типу решаются при сборке графа, а не роутером во время запуска. `post` и `onboarding` компилируются отдельно для новостного и SMM-канала (`graph_for(kind, channel_type)`): узлов другого типа в графе нет. Страница запуска берёт схему из `GET /runs/{id}/graph` и показывает ровно тот граф, который исполняется.

Подпись узла задаётся в `@node(name, label, news=..., smm=...)`: если для типа канала есть своя подпись, она идёт в события, текущий шаг запуска и схему. Имена узлов уникальны во всех графах, реестр подписей падает при повторе.

## Граф `post`

Главный граф проекта: циклический, с двумя «головами» и общим производством в виде подграфов. В сборку попадает одна голова — по типу канала.

```
START
  → load_context                       загрузка канала, брифа, стратегии, моделей ролей
  → [news_head] | [smm_head]           по типу канала, выбирается при сборке
  → (PostBrief готов? нет → finalize: skipped)
  → [production]
  → deliver
      ├─ автопилот → schedule → END
      └─ одобрение → request_approval → interrupt ──► approve        → schedule → END
                                                 ├──► revise(comment) → [production] с комментарием владельца
                                                 └──► expire          → finalize: skipped / not_approved
```

### Подграф `news_head`

```
pick_stories        код: свежие сюжеты из пула, приоритетные первыми, без отброшенных
  ├─ пусто → fallback: банк идей или пропуск слота (настройка канала)
  → scout           LLM: значимость 1–5 с обоснованием по каждому сюжету
  → chief           LLM: выбор сюжета, reader_goal, key_idea, формат
  → load_sources    код: тексты источников сюжета, первоисточник отдельно
  → factcheck       LLM: утверждения и ключевая мысль против источников
  → verify_quotes   код: цитаты фактчекера есть в источниках дословно
  ├─ ключевая мысль подтверждена → build_brief → END
  ├─ не подтверждена, попыток < 2 → chief_fix (rephrase / switch) → load_sources → …
  └─ попытки исчерпаны → сюжет отброшен с причиной → fallback
```

### Подграф `smm_head`

```
load_slot     код: слот плана (тема, рубрика, формат, задача, позиция канала)
  → build_brief → END
```

Тему и задачу уже придумал Стратег при планировании, поэтому голова SMM короткая. Проверка того, что факты подтверждают задачу, — в производстве (`goal_check`).

### Контракт `PostBrief`

Обе головы отдают одну структуру; производство не знает, откуда пришла задача.

```python
class PostBrief(BaseModel):
    mode: Literal["news", "smm"]
    format: Literal["text", "poll", "digest"]
    rubric: str | None
    topic: str
    reader_goal: str
    key_idea: str
    needs_research: bool
    source: SourceRef | None
    unconfirmed_claims: list[str]
    related_post: PostRef | None
    channel_position: str | None
```

Времени выхода нет ни в брифе, ни в снимке слота в State: смена часового пояса канала переносит слот, пока пост в работе. `save_post` и `schedule` читают время из слота в БД.

### Подграф `production`

```
START
  ├─ needs_research и фактов нет → researcher → (smm) goal_check   узел есть только в SMM-сборке
  │       goal_check: не подтверждено → либо писать то, что подтверждается,
  │                                     либо slot_return (тема возвращается Стратегу) → END
  └─ → writer
writer
  ├─ need_facts, раундов < 2 → researcher → writer
  └─ → auto_checks          код: стоп-обороты, длина, заголовок, ссылки, числа из calculate
  → editor
  ├─ critical, попыток < 3 → writer (с замечаниями)
  ├─ critical, попытки исчерпаны → finalize: needs_attention
  └─ → publisher
  → publisher_checks        код: текст не изменён, ссылки только из текста
  ├─ провал → publisher (1 повтор) → иначе безопасное оформление кодом
  → media                   график в песочнице Python или картинка со стока
  → END
```

### Агенты-исполнители с инструментами

- **Исследователь** — подграф ReAct: `web_search`, `read_page`, `search_past_posts`, `calculate`, итог через `report`. Не больше 8 вызовов инструментов за раунд. Любой текст страницы проходит проверку на инъекции до того, как попадёт к агенту. Цитаты в фактах сверяются кодом с прочитанными страницами; факты без подтверждённой цитаты отбрасываются.
- **Писатель** — `calculate` для производных чисел, итог через `answer` со схемой под формат.
- **Шеф, Скаут, Фактчекер, Редактор, Издатель** — один вызов со структурированным ответом через `answer`.

### `PostState`

```python
class PostState(TypedDict):
    run_id: str
    channel_id: str
    slot_id: str
    mode: Literal["news", "smm"]
    ctx: ChannelContext

    stories: list[Story]
    scout_scores: list[StoryScore]
    chosen_story_id: str | None
    sources: list[SourceDoc]
    factcheck: FactcheckReport | None
    chief_attempts: int
    rejected_story_ids: Annotated[list[str], operator.add]

    brief: PostBrief | None

    facts: Annotated[list[Fact], operator.add]
    not_found: Annotated[list[str], operator.add]
    calculations: Annotated[list[Calculation], operator.add]
    research_questions: list[str]
    research_rounds: int

    draft: Draft | None
    write_attempts: int
    auto_issues: list[Issue]
    review: Review | None
    review_history: Annotated[list[Review], operator.add]
    owner_feedback: str | None

    formatted: Formatted | None
    media: Media | None

    outcome: Outcome | None
    errors: Annotated[list[RunError], operator.add]
```

`Draft` — объединение схем по форматам: `TextDraft` (title, text, key_idea), `PollDraft` (question, options, intro), `DigestDraft` (title, intro, items со своими ссылками).

## Граф `planning` (SMM)

```
collect_context    код: стратегия, посты за 2 месяца с результатами, идеи с 👍,
                   комментарии клиента, закреплённые слоты, тренды ниши (SearXNG, по желанию)
  → strategist_plan
  → plan_checks    код: доли рубрик, окна публикации, количество слотов
  → novelty_check  код: bge-m3 против прошлых постов; серая зона — один пакетный вызов LLM
  ├─ есть проблемы, попыток < 2 → strategist_fix (только проблемные слоты) → plan_checks
  → save_draft
  ├─ автопилот → approve_all → END
  └─ одобрение → interrupt
         ├─ approve                → approve_all → END
         ├─ replan(comment)        → strategist_plan (закреплённые и утверждённые не трогает)
         └─ auto_approve_deadline  → approve_all → END
```

Сетка плана в State хранит местное время канала, а не момент в UTC. `save_draft` переводит его в момент по поясу канала на момент сохранения, поэтому смена пояса, пока Стратег составляет план, не сдвигает слоты.

Режимы того же графа:
- `replace_slot` — новая тема для одного слота в той же рубрике;
- `suggest_topics` — 3–5 вариантов темы для слота «+ слот».

## Граф `onboarding`

```
read_samples           код: образцы текстов из брифа, сайт
  → designer_styleguide  LLM: стайлгайд
  → (SMM) strategist_strategy  LLM: стратегия; в новостной сборке узла нет
  → await_documents      interrupt
       ├─ regenerate(comment) → designer_styleguide
       └─ approve → save_documents → seed_ideas → END
```

Осмысленность брифа проверяет отдельный граф `brief_check` из формы брифа.

## Граф `analytics` (SMM)

```
collect_stats      код: реакции, опросы, оценки клиента по постам месяца
  → analyst        ReAct: python_sandbox (расчёты, графики), итог через report
  → strategist_proposal
  → interrupt → approve / reject → (approve) обновление стратегии → END
```

## Лимиты циклов

| Цикл | Лимит | После лимита |
|---|---|---|
| Фактчекер → Шеф | 2 исправления | Сюжет отброшен, следующий или запасной вариант |
| Писатель → Исследователь | 2 раунда | Писатель работает с тем, что есть |
| Редактор → Писатель | 3 попытки | `needs_attention`, пост ждёт решения клиента в кабинете |
| Издатель → проверка | 1 повтор | Безопасное оформление кодом |
| План → проверки | 2 исправления | Черновик с предупреждениями на карточках |
| Доработка по комментарию владельца | 3 раза | Только ручная правка |

Дополнительно `recursion_limit` на запуск как предохранитель.

## Ошибки и fallback

| Ошибка | Где обрабатывается | Действие |
|---|---|---|
| Сеть, 429, 5xx OpenRouter | `RetryPolicy` узла | Повтор с экспоненциальной паузой |
| Модель недоступна | OpenRouter | Следующая модель из цепочки `models` |
| Ответ не по схеме | Обёртка вызова | Повтор с текстом ошибки валидации, затем следующая модель |
| Поиск не ответил | Инструмент | SearXNG → DuckDuckGo → пустой результат с пометкой |
| Страница не открылась или инъекция | Инструмент | Агент получает сообщение об ошибке или вердикт, а не текст |
| OpenRouter недоступен целиком | Запуск | Статус «отложен», повтор через 15 / 30 / 60 минут с последнего узла |
| Бюджет исчерпан | Перед каждым узлом с LLM | Остановка, статус `budget_exceeded` |
| Неожиданное исключение | Запуск | Статус `failed`, ошибка в таймлайне, слот помечен |

## Прозрачность

Узлы и инструменты публикуют события через `get_stream_writer()`: начало и конец узла, вызов инструмента и его результат, проверки кодом, переходы по циклам с номером итерации. Вместе с потоком `messages` (токены модели) они сохраняются в `run_events` и транслируются на страницу запуска.
