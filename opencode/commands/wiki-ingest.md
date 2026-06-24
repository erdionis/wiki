---
description: "Проиндексировать источник с созданием SHA-256 хешей и проставлением lifecycle"
---

Выполни ingestion источника: $ARGUMENTS

Шаги:
0. Проверить `wiki/.ingest-progress.json` — есть ли незавершённый прогресс:
   - Если есть и не старше 24ч → спросить: «Продолжить прерванную индексацию?»
   - Если да → загрузить processed_files, current_label, phase; продолжить с прерванного места
   - Если нет или пользователь отказался → начать с чистого листа, создать новый прогресс

1. Прочитай wiki/sources.md — найди путь по указанной метке или пути
2. Определи тип источника:
   - Исходный код → WIKI-INGEST-MODULE
   - Конфигурация → WIKI-INGEST-CONFIG
   - Документ / ADR → WIKI-INGEST-DOC
   - План / задачи → WIKI-INGEST-PLAN
   - Тесты → WIKI-INGEST-TESTS
3. Прочитай SKILL.md и выполни нужный сценарий
4. Применяй дерево решений перед каждой страницей:
   существующая страница покрывает ту же суть → слить;
   новая суть → создать
5. **После создания/обновления КАЖДОЙ wiki-страницы:**
   - Проставить **Статус**: новым страницам → `draft`, слитым → `active`
   - Обновить `wiki/architecture/file-page-map.json`: добавить/обновить запись `исходный_файл → wiki/страница.md`
   - Добавить обработанный файл в `wiki/.ingest-progress.json` → `processed_files`
   - Сохранить прогресс (phase, current_label, last_file)
6. После основных страниц выполни каскадное обновление
7. Зафиксируй противоречия в секции ## Противоречия (не выбирай между источниками)
8. Обсуди находки с пользователем перед финальной записью
9. **В конце успешной индексации:**
   - Обновить колонку `Индексировано` в `wiki/sources.md` для текущей метки (текущая дата)
   - Создать `wiki/.source-hashes.json`: вычислить SHA-256 для каждого прочитанного файла
   - Очистить `wiki/.ingest-progress.json` (прогресс завершён)
   - Обновить `wiki/hot-context.md` — добавить информацию о новых страницах
   - Обновить `wiki/index.md` и `wiki/log.md`

Если $ARGUMENTS не указан — спроси какой источник индексировать.

---

Формат `wiki/.ingest-progress.json`:
```json
{
  "started_at": "2026-06-10T10:30:00Z",
  "last_update": "2026-06-10T10:45:00Z",
  "current_label": "src-main",
  "phase": "modules",
  "processed_files": [
    "src/main/java/com/example/PaymentService.java",
    "src/main/java/com/example/OrderRepository.java"
  ],
  "total_files": 42,
  "current_file_index": 2
}
```

Фазы: `modules` → `concepts` → `architecture` → `index`
