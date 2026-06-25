#!/bin/sh
# install-hook.sh — устанавливает git post-commit хук для автообновления repo-map.
#
# Хук запускает только `repo-map.py --incremental` (чистый Python, без LLM).
# Завершается за секунды. /wiki-update (LLM-обновление) по-прежнему запускается вручную.
#
# Использование:
#   sh wiki/scripts/install-hook.sh
#
# Для удаления хука:
#   rm .git/hooks/post-commit

set -e

HOOK=".git/hooks/post-commit"

# Проверяем, что мы в корне git-репозитория
if [ ! -d ".git" ]; then
    echo "Ошибка: запускайте скрипт из корня репозитория (где находится папка .git)" >&2
    exit 1
fi

# Предупреждение если хук уже существует
if [ -f "$HOOK" ]; then
    echo "Внимание: $HOOK уже существует. Перезаписать? [y/N]"
    read -r answer
    case "$answer" in
        [yY]*) ;;
        *) echo "Отменено." ; exit 0 ;;
    esac
fi

mkdir -p "$(dirname "$HOOK")"

cat > "$HOOK" << 'EOF'
#!/bin/sh
# Автоматически обновляет repo-map после каждого коммита.
# Запускается в фоне (& на конце) — не блокирует git commit.
python wiki/scripts/repo-map.py --incremental 2>/dev/null &
EOF

chmod +x "$HOOK"

echo "✓ Хук установлен: $HOOK"
echo "  После каждого git commit будет автоматически обновляться repo-map.md"
echo "  (запускается в фоне, не замедляет коммит)"
