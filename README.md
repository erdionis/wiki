# Wiki-скилл для проектов

Лёгкая замена RAG — накопительная база знаний прямо в репозитории.

## Файлы пакета

```
SKILL.md                        ← глобальный навык (установить один раз)
AGENTS.md                       ← шаблон для каждого проекта
TUTORIAL.md                     ← полное руководство разработчика

wiki/scripts/
  repo-map.py                   ← структурная карта + file-page-map.json
  repo-map.sh                   ← bash-версия без зависимостей

.opencode/commands/             ← 8 slash-команд
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

wiki/ (создаётся в проекте)
  hot-context.md                ← L1 кэш: краткая выжимка (< 24ч)
  .source-hashes.json           ← SHA-256 хеши источников
  .ingest-progress.json         ← чекпоинты для возобновления ingestion
  architecture/
    repo-map.md                 ← автогенерируемый скелет классов/методов
    .repo-map-cache.json        ← инкрементальный кэш mtime + parsed-типы
    file-page-map.json          ← маппинг: исходный файл → wiki-страница
```

## Быстрый старт

### 1. Установить скилл глобально (один раз)

```bash
mkdir -p ~/.opencode/skills/wiki
cp SKILL.md ~/.opencode/skills/wiki/SKILL.md
```

### 2. Добавить в проект

```bash
cp AGENTS.md ./AGENTS.md                          # отредактировать
mkdir -p wiki .opencode/commands scripts
cp wiki/sources.md      wiki/sources.md      # прописать пути проекта (с колонкой Индексировано)
cp wiki/index.md        wiki/index.md
cp wiki/log.md          wiki/log.md
cp wiki/hot-context.md  wiki/hot-context.md
cp .opencode/commands/*.md     .opencode/commands/
cp wiki/scripts/repo-map.*        wiki/scripts/
```

### 3. Первичная индексация

```bash
python wiki/scripts/repo-map.py    # генерирует repo-map.md + file-page-map.json (шаблон)
/wiki-ingest src-main         # заполняет file-page-map.json, создаёт .ingest-progress.json при необходимости
/wiki-lint
```

### 4. Начало каждой сессии

```
/wiki-start                              ← L1 hot cache + контекст
/wiki-start добавить рефанд в платёжный модуль   ← контекст + wiki-first для задачи
```

### 5. Ежедневная работа после изменений кода

```
/wiki-update          # авто-детекция через git (или SHA-256 / mtime), точечное обновление
                      # через file-page-map.json. НЕ помечает все страницы [устарело]
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

## Ключевые механизмы (новые в v2/v3)

| Механизм | Файл | Назначение |
|---|---|---|
| **File → Page Map** | `wiki/architecture/file-page-map.json` | Точный lookup: исходный файл → wiki-страница. Создаётся как пустой шаблон скриптом repo-map, заполняется при `/wiki-ingest`. Используется `/wiki-update` для точечных обновлений. |
| **Ingest Checkpoints** | `wiki/.ingest-progress.json` | Чекпоинты для возобновления прерванной индексации. Фазы: `modules → concepts → architecture → index`. Автоочищается при завершении. |
| **Индексировано** | Колонка в `wiki/sources.md` | Дата последней успешной индексации метки. Fallback для `/wiki-update` когда git недоступен. |
| **L1 Hot Cache** | `wiki/hot-context.md` | Краткая выжимка контекста (до 10 строк). Читается при `/wiki-start` вместо полного index.md. |
| **Page Lifecycle** | Поле **Статус** на каждой странице | Состояния: `draft → active → stale → archived`. |
| **SHA-256 Hashes** | `wiki/.source-hashes.json` | Криптографическая верификация источников. Создаётся при `/wiki-ingest`, обновляется при `/wiki-update`. |

## Три фундаментальных правила

```
1. Wiki first    — перед задачей читай wiki, не код
2. Code → Wiki   — нашёл в коде → сразу записал в wiki
3. Never from memory — Agents отвечает только из wiki
```

## Подробнее

`TUTORIAL.md` — полное руководство с примерами для Python, Go, XML-проектов.
