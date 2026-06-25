# Wiki-скилл для проектов

Лёгкая замена RAG — накопительная база знаний прямо в репозитории.

## Файлы пакета

```
SKILL.md                        ← глобальный навык (установить один раз)
AGENTS.md                       ← шаблон для каждого проекта
TUTORIAL.md                     ← полное руководство разработчика
CHANGELOG.md                    ← история изменений скилла

wiki/scripts/
  repo-map.py                   ← структурная карта + file-page-map.json
  repo-map.sh                   ← bash-версия без зависимостей
  install-hook.sh               ← git post-commit хук (автообновление repo-map)

opencode/commands/              ← 8 slash-команд
  wiki-start.md                 ← старт сессии / запуск задачи с wiki-first
  wiki-ingest.md                ← проиндексировать источник (с чекпоинтами)
  wiki-ask.md                   ← вопрос только через wiki, никогда из памяти
  wiki-update.md                ← авто-обнаружение изменений, точечное обновление
  wiki-repomap.md               ← регенерация структурного скелета
  wiki-lint.md                  ← аудит с тремя уровнями 🔴🟡🔵
  wiki-stats.md                 ← состояние вики: покрытие, связность, здоровье
  wiki-plan.md                  ← обновление статуса задач

wiki/
  sources.md                    ← шаблон манифеста источников (с колонкой Индексировано)
  index.md                      ← пустое оглавление
  log.md                        ← пустой журнал
  hot-context.md                ← L1 кэш: краткая выжимка
  architecture/
    repo-map.md                 ← автогенерируемый скелет классов/методов
    .repo-map-cache.json        ← инкрементальный кэш mtime + parsed-типы
    file-page-map.json          ← маппинг: исходный файл → wiki-страница
  .source-hashes.json           ← SHA-256 хеши источников (создаётся при ingestion)
  .ingest-progress.json         ← чекпоинты для возобновления ingestion
```

## Быстрый старт

### 1. Установить скилл глобально (один раз)

```bash
mkdir -p ~/.opencode/skills/wiki
cp SKILL.md ~/.opencode/skills/wiki/SKILL.md
```

### 2. Добавить в проект

```bash
cp AGENTS.md ./AGENTS.md                                 # отредактировать
mkdir -p wiki/scripts opencode/commands
cp wiki/sources.md      wiki/sources.md                  # прописать пути проекта
cp wiki/index.md        wiki/index.md
cp wiki/log.md          wiki/log.md
cp wiki/hot-context.md  wiki/hot-context.md
cp opencode/commands/*.md    opencode/commands/
cp wiki/scripts/repo-map.py  wiki/scripts/
cp wiki/scripts/repo-map.sh  wiki/scripts/
cp wiki/scripts/install-hook.sh wiki/scripts/
```

### 3. Установить git-хук (один раз, в корне проекта)

```bash
sh wiki/scripts/install-hook.sh
```

После этого `repo-map.md` обновляется автоматически после каждого `git commit`. `/wiki-update` (LLM) по-прежнему запускается вручную.

### 4. Установить tree-sitter (опционально)

Если в проекте есть TypeScript, Rust, C#, Swift и другие языки без regex-парсера:

```bash
pip install tree-sitter \
    tree-sitter-typescript tree-sitter-javascript \
    tree-sitter-rust tree-sitter-c-sharp \
    tree-sitter-go tree-sitter-java tree-sitter-python \
    tree-sitter-kotlin tree-sitter-ruby tree-sitter-swift \
    tree-sitter-c tree-sitter-cpp tree-sitter-scala \
    tree-sitter-php tree-sitter-dart
```

Без установки — автоматический fallback на regex. Поведение не меняется.

### 5. Первичная индексация

```bash
python wiki/scripts/repo-map.py    # генерирует repo-map.md + file-page-map.json (шаблон)
/wiki-ingest src-main              # заполняет file-page-map.json, создаёт wiki-страницы
/wiki-lint
```

### 6. Начало каждой сессии

```
/wiki-start                                           ← L1 hot cache + контекст
/wiki-start добавить рефанд в платёжный модуль       ← контекст + wiki-first для задачи
```

### 7. Ежедневная работа после изменений кода

```
/wiki-update    # авто-детекция через git или SHA-256, точечное обновление
```

## Таблица команд

| Команда | Когда использовать |
|---|---|
| `/wiki-start` | Начало сессии. С аргументом — сразу в задачу через wiki-first |
| `/wiki-ingest <метка>` | Проиндексировать источник с созданием SHA-256 хешей и проставлением lifecycle |
| `/wiki-ask <вопрос>` | Вопрос о проекте — только через wiki, с учётом lifecycle страниц |
| `/wiki-update` | Изменения в коде — авто-обнаружение через git/SHA-256 + точечный lookup через `file-page-map.json` + обновление lifecycle |
| `/wiki-repomap` | Обновить структурный скелет (`repo-map.md` + `file-page-map.json` шаблон) |
| `/wiki-lint` | Аудит: 🔴 критично / 🟡 внимание / 🔵 информация + lifecycle проверки + hot-context |
| `/wiki-stats` | Сводка: страниц, lifecycle, покрытие, осиротевшие, инфраструктура |
| `/wiki-plan` | Обновить статус задач в плане |

## Ключевые механизмы

| Механизм | Файл | Назначение |
|---|---|---|
| **Tree-sitter парсер** | `wiki/scripts/repo-map.py` | Приоритетный парсер: 31+ язык (TS, Rust, C#, Swift, Ruby, Dart и др.). Fallback на regex если не установлен. Отключить: `--no-ast`. |
| **Git post-commit хук** | `.git/hooks/post-commit` | Автообновление `repo-map.md --incremental` после каждого коммита. Устанавливается через `install-hook.sh`. |
| **Теги уверенности** | Поле `**Уверенность**` на каждой странице | `extracted` — из кода напрямую; `inferred` — предположение агента; `ambiguous` — требует проверки человеком. |
| **Q&A-archive** | Поле `**Тип**: q&a-archive` | Страницы, созданные из `/wiki-ask`, а не из `/wiki-ingest`. Агент не доверяет им как первичным источникам. |
| **Hub-stubs + orphan clusters** | `/wiki-lint` | Структурные проблемы графа: узловые страницы без контента (>5 ссылок, <300 символов) и изолированные кластеры. |
| **File → Page Map** | `wiki/architecture/file-page-map.json` | Точный lookup: исходный файл → wiki-страница. Создаётся скриптом, заполняется при `/wiki-ingest`. |
| **Ingest Checkpoints** | `wiki/.ingest-progress.json` | Чекпоинты для возобновления прерванной индексации. Фазы: `modules → concepts → architecture → index`. |
| **Индексировано** | Колонка в `wiki/sources.md` | Дата последней успешной индексации метки. Fallback для `/wiki-update` когда git недоступен. |
| **L1 Hot Cache** | `wiki/hot-context.md` | Краткая выжимка контекста (до 10 строк). Читается при `/wiki-start` вместо полного index.md. |
| **Page Lifecycle** | Поле `**Статус**` на каждой странице | Состояния: `draft → active → stale → archived`. |
| **SHA-256 Hashes** | `wiki/.source-hashes.json` | Криптографическая верификация источников. Приоритетный метод в `/wiki-update`. |

## Три фундаментальных правила

```
1. Wiki first    — перед задачей читай wiki, не код
2. Code → Wiki   — нашёл в коде → сразу записал в wiki
3. Never from memory — Agents отвечает только из wiki
```

## Обновление скилла в существующем проекте

Чтобы перенести новую версию скилла в уже работающий проект:

```bash
# 1. Скопировать изменённые файлы
cp SKILL.md               your-project/SKILL.md
cp opencode/commands/wiki-lint.md  your-project/opencode/commands/wiki-lint.md
cp wiki/scripts/repo-map.py        your-project/wiki/scripts/repo-map.py
cp wiki/scripts/install-hook.sh    your-project/wiki/scripts/install-hook.sh

# 2. Переустановить хук (если это первый раз)
cd your-project
sh wiki/scripts/install-hook.sh

# 3. Страницы wiki/*.md не трогать — они принадлежат проекту
```

Подробнее об изменениях: `CHANGELOG.md`.

## Подробнее

`TUTORIAL.md` — полное руководство с примерами для Python, Go, XML-проектов.
