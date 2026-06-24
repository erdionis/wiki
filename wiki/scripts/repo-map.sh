#!/usr/bin/env bash
# repo-map.sh — упрощённая карта репозитория (bash, без зависимостей)
#
# Использование:
#   bash scripts/repo-map.sh                  # автоопределение src/
#   bash scripts/repo-map.sh src/main/java    # явный путь
#
# Работает там, где нет Python. Менее точен — без парсинга AST.
# Для точного анализа используйте repo-map.py

set -euo pipefail

ROOT="${1:-}"
OUTPUT="wiki/architecture/repo-map.md"
TODAY=$(date +%Y-%m-%d)

# ─── Определение корня ───────────────────────────────────────────
if [[ -z "$ROOT" ]]; then
  for candidate in src app lib core pkg; do
    if [[ -d "$candidate" ]]; then
      ROOT="$candidate"
      break
    fi
  done
fi

if [[ -z "$ROOT" || ! -d "$ROOT" ]]; then
  echo "Ошибка: не найдена директория с исходниками."
  echo "Использование: bash scripts/repo-map.sh <путь>"
  exit 1
fi

# ─── Подсчёт файлов и выбор шестерни ────────────────────────────
FILE_COUNT=$(find "$ROOT" \
  -not -path '*/.git/*' -not -path '*/target/*' -not -path '*/build/*' \
  -not -path '*/__pycache__/*' -not -path '*/node_modules/*' \
  \( -name "*.java" -o -name "*.py" -o -name "*.go" -o -name "*.kt" -o -name "*.xml" \) \
  | wc -l | tr -d ' ')

if   [[ $FILE_COUNT -lt 30  ]]; then GEAR=1; GEAR_DESC="полные сигнатуры"
elif [[ $FILE_COUNT -lt 150 ]]; then GEAR=2; GEAR_DESC="ключевые методы"
else                                  GEAR=3; GEAR_DESC="структура папок"
fi

echo "Файлов: $FILE_COUNT → Gear $GEAR ($GEAR_DESC)"

# ─── Генерация карты ─────────────────────────────────────────────
mkdir -p "$(dirname "$OUTPUT")"

cat > "$OUTPUT" << HEADER
# Карта репозитория (repo-map)

**Краткое описание**: Автогенерируемый структурный скелет кодовой базы.

**Источники**: \`$ROOT/\`

**Последнее обновление**: $TODAY

**Шестерня**: Gear $GEAR из 3 — $GEAR_DESC
($FILE_COUNT файлов)

> ⚠️ Сгенерировано скриптом \`scripts/repo-map.sh\`. Не редактировать вручную.
> Для точного анализа используйте \`python scripts/repo-map.py\`

---

HEADER

# ─── Gear 3: только структура папок ─────────────────────────────
if [[ $GEAR -eq 3 ]]; then
  echo "## Структура директорий" >> "$OUTPUT"
  echo '```' >> "$OUTPUT"
  find "$ROOT" -type d \
    -not -path '*/.git*' -not -path '*/target*' -not -path '*/build*' \
    -not -path '*/__pycache__*' \
    | sort | head -60 >> "$OUTPUT"
  echo '```' >> "$OUTPUT"

  echo -e "\n## Точки входа" >> "$OUTPUT"
  grep -rl "public static void main\|def main\|func main(" "$ROOT" 2>/dev/null \
    | head -10 | while read -r f; do
    echo "- \`$f\`" >> "$OUTPUT"
  done
  echo "" >> "$OUTPUT"
  exit 0
fi

# ─── Gear 1 и 2: классы и методы ────────────────────────────────
process_java() {
  local file="$1"
  local rel="${file#$ROOT/}"
  local classes methods

  classes=$(grep -n '^\s*\(public\|protected\)\s*\(abstract\s*\|final\s*\)\?\(class\|interface\|enum\|record\)\s' "$file" 2>/dev/null || true)
  [[ -z "$classes" ]] && return

  echo -e "\n  **$rel**" >> "$OUTPUT"
  echo "$classes" | while read -r line; do
    lineno=$(echo "$line" | cut -d: -f1)
    name=$(echo "$line" | grep -oP '(class|interface|enum|record)\s+\K\w+' | head -1)
    kind=$(echo "$line" | grep -oP '(class|interface|enum|record)' | head -1)
    [[ -z "$name" ]] && continue
    echo "    📦 $kind \`$name\`" >> "$OUTPUT"

    if [[ $GEAR -eq 1 ]]; then
      # Gear 1: методы с сигнатурами
      awk -v start="$lineno" 'NR>start && /^\s*(public|protected)\s.*\(.*\)/ && !/^\s*(public|protected)\s+(class|interface)/ {
        gsub(/^\s+/, "      · ")
        sub(/\s*\{.*$/, "")
        print
        if (NR > start+100) exit
      }' "$file" 2>/dev/null | head -15 >> "$OUTPUT" || true
    else
      # Gear 2: только имена методов
      awk -v start="$lineno" 'NR>start && /^\s*(public|protected)\s.*\(/ && !/^\s*(public|protected)\s+(class|interface)/ {
        match($0, /\w+\s*\(/, arr)
        name=arr[0]; gsub(/\s*\(/, "", name); gsub(/^\s+/, "", name)
        if (name != "") print "      · " name "()"
        if (NR > start+100) exit
      }' "$file" 2>/dev/null | head -10 >> "$OUTPUT" || true
    fi
  done
}

process_python() {
  local file="$1"
  local rel="${file#$ROOT/}"

  local has_content
  has_content=$(grep -c '^\(class\|def\) ' "$file" 2>/dev/null || echo 0)
  [[ $has_content -eq 0 ]] && return

  echo -e "\n  **$rel**" >> "$OUTPUT"

  grep -n '^\(class\|def\) ' "$file" 2>/dev/null | while read -r line; do
    lineno=$(echo "$line" | cut -d: -f1)
    decl=$(echo "$line" | cut -d: -f2-)
    if echo "$decl" | grep -q '^class '; then
      name=$(echo "$decl" | grep -oP 'class\s+\K\w+')
      echo "    📦 class \`$name\`" >> "$OUTPUT"
    else
      name=$(echo "$decl" | grep -oP 'def\s+\K\w+')
      [[ "$name" == _* ]] && [[ "$name" != __init* ]] && continue
      if [[ $GEAR -eq 1 ]]; then
        sig=$(echo "$decl" | sed 's/def //' | sed 's/://')
        echo "      · $sig" >> "$OUTPUT"
      else
        echo "      · ${name}()" >> "$OUTPUT"
      fi
    fi
  done
}

process_go() {
  local file="$1"
  local rel="${file#$ROOT/}"

  local has_content
  has_content=$(grep -cE '^(type|func) ' "$file" 2>/dev/null || echo 0)
  [[ $has_content -eq 0 ]] && return

  echo -e "\n  **$rel**" >> "$OUTPUT"

  grep -nE '^(type .+ (struct|interface)|func )' "$file" 2>/dev/null | while read -r line; do
    decl=$(echo "$line" | cut -d: -f2-)
    if echo "$decl" | grep -qE 'struct|interface'; then
      name=$(echo "$decl" | grep -oP 'type\s+\K\w+')
      kind=$(echo "$decl" | grep -oP '(struct|interface)')
      echo "    📦 $kind \`$name\`" >> "$OUTPUT"
    else
      if [[ $GEAR -eq 1 ]]; then
        sig=$(echo "$decl" | sed 's/ {$//')
        echo "      · $sig" >> "$OUTPUT"
      else
        name=$(echo "$decl" | grep -oP 'func\s+(?:\(\w+[^)]*\)\s+)?\K\w+')
        echo "      · ${name}()" >> "$OUTPUT"
      fi
    fi
  done
}

# ─── Обход файлов ────────────────────────────────────────────────
# Группируем по папкам
prev_dir=""
find "$ROOT" \
  -not -path '*/.git/*' -not -path '*/target/*' -not -path '*/build/*' \
  -not -path '*/__pycache__/*' -not -path '*/node_modules/*' \
  \( -name "*.java" -o -name "*.py" -o -name "*.go" -o -name "*.kt" \) \
  | sort | while read -r file; do
    dir=$(dirname "$file")
    if [[ "$dir" != "$prev_dir" ]]; then
      rel_dir="${dir#$ROOT/}"
      echo -e "\n### $rel_dir/" >> "$OUTPUT"
      prev_dir="$dir"
    fi

    case "${file##*.}" in
      java|kt) process_java "$file" ;;
      py)      process_python "$file" ;;
      go)      process_go "$file" ;;
    esac
done

cat >> "$OUTPUT" << FOOTER

---

## Связанные страницы

- [[architecture/overview]]
- [[architecture/module-map]]
- [[architecture/data-flow]]
FOOTER

echo "✓ Карта сохранена: $OUTPUT"
