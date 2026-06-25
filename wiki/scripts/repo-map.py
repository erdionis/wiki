#!/usr/bin/env python3
"""
repo-map.py — структурная карта кодовой базы для wiki.

Извлекает классы, функции, методы из исходного кода и генерирует
wiki/architecture/repo-map.md с адаптивной детализацией (система шестерён).

Поддерживаемые языки:
  Tree-sitter (если установлен): TypeScript, TSX, JavaScript, Rust, C#, Swift,
    Ruby, C, C++, Scala, PHP, Dart, Kotlin, Go, Python, Java, Bash, SQL,
    JSON, Lua, Groovy, Astro, Vue, Svelte и другие (31+ язык).
  Regex-fallback (без зависимостей): Python, Java, Go, Kotlin, XML (Spring/Camel).

Установка tree-sitter (опционально):
  pip install tree-sitter tree-sitter-python tree-sitter-typescript \\
      tree-sitter-javascript tree-sitter-rust tree-sitter-c-sharp \\
      tree-sitter-go tree-sitter-java tree-sitter-kotlin tree-sitter-ruby \\
      tree-sitter-swift tree-sitter-c tree-sitter-cpp tree-sitter-scala \\
      tree-sitter-php tree-sitter-dart

Использование:
  python scripts/repo-map.py                        # автоопределение из sources.md
  python scripts/repo-map.py src/                   # явный путь
  python scripts/repo-map.py src/ --gear 2          # принудительная шестерня
  python scripts/repo-map.py src/ --incremental     # инкрементальный режим (по mtime)
  python scripts/repo-map.py src/ --no-ast          # принудительно regex (без tree-sitter)
  python scripts/repo-map.py src/ --output wiki/architecture/repo-map.md
"""

import os
import re
import sys
import argparse
import json
import time
from pathlib import Path
from datetime import date
from collections import defaultdict


# ─────────────────────────────────────────
# TREE-SITTER ПОДДЕРЖКА (опциональная)
# ─────────────────────────────────────────
# Проверяем наличие tree-sitter при импорте.
# Если пакеты не установлены — тихо переходим на regex-парсеры.
# Установка: pip install tree-sitter tree-sitter-python tree-sitter-typescript ...

def _try_import_treesitter() -> bool:
    """Возвращает True если tree-sitter доступен."""
    try:
        import tree_sitter  # noqa: F401
        return True
    except ImportError:
        return False

_TREESITTER_AVAILABLE = _try_import_treesitter()

# Маппинг расширений → название грамматики tree-sitter
# Порядок: сначала расширения, для которых нет regex-fallback
_TS_LANG_MAP: dict[str, str] = {
    '.ts':    'typescript',
    '.tsx':   'tsx',
    '.js':    'javascript',
    '.jsx':   'javascript',
    '.mjs':   'javascript',
    '.rs':    'rust',
    '.cs':    'c_sharp',
    '.swift': 'swift',
    '.rb':    'ruby',
    '.c':     'c',
    '.h':     'c',
    '.cpp':   'cpp',
    '.cc':    'cpp',
    '.cxx':   'cpp',
    '.scala': 'scala',
    '.php':   'php',
    '.dart':  'dart',
    '.lua':   'lua',
    # Языки, для которых есть и regex, и tree-sitter:
    '.py':    'python',
    '.java':  'java',
    '.kt':    'kotlin',
    '.go':    'go',
}

# Кэш загруженных грамматик (избегаем повторного импорта)
_TS_LANG_CACHE: dict[str, object] = {}


def _load_ts_language(lang_name: str):
    """Загружает Language из tree-sitter-<lang> пакета. Возвращает None если нет пакета."""
    if lang_name in _TS_LANG_CACHE:
        return _TS_LANG_CACHE[lang_name]
    try:
        import importlib
        # tree-sitter пакеты называются tree_sitter_<lang>
        pkg_name = f'tree_sitter_{lang_name}'
        mod = importlib.import_module(pkg_name)
        from tree_sitter import Language
        lang = Language(mod.language())
        _TS_LANG_CACHE[lang_name] = lang
        return lang
    except Exception:
        _TS_LANG_CACHE[lang_name] = None
        return None


def _ts_node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def _collect_ts_items(node, source: bytes, gear: int, results: list, depth: int = 0):
    """Рекурсивный обход AST — универсальный для большинства языков."""
    # Типы узлов, которые нас интересуют как «контейнеры» (классы, интерфейсы и т.п.)
    CONTAINER_TYPES = {
        'class_declaration', 'class_definition', 'class_specifier',
        'interface_declaration', 'interface_body',
        'struct_item', 'struct_declaration', 'struct_specifier',
        'enum_declaration', 'enum_item',
        'trait_item', 'impl_item',
        'object_declaration',              # Scala object/companion
        'record_declaration',
    }
    # Типы узлов для функций/методов
    FUNCTION_TYPES = {
        'function_declaration', 'function_definition', 'function_item',
        'method_declaration', 'method_definition',
        'constructor_declaration',
        'arrow_function',                   # JS/TS — только верхний уровень
        'function_signature',
    }

    ntype = node.type

    if ntype in CONTAINER_TYPES and depth <= 2:
        # Найти имя
        name_node = node.child_by_field_name('name')
        name = _ts_node_text(name_node, source) if name_node else '?'
        container = {'kind': ntype.split('_')[0], 'name': name, 'methods': []}
        results.append(container)
        if gear <= 2:
            # Рекурсивно собираем методы внутри
            for child in node.children:
                _collect_ts_items(child, source, gear, container['methods'], depth + 1)
        return

    if ntype in FUNCTION_TYPES:
        name_node = node.child_by_field_name('name')
        params_node = node.child_by_field_name('parameters')
        name = _ts_node_text(name_node, source) if name_node else '?'
        params = _ts_node_text(params_node, source) if params_node else ''

        # Пропускаем приватные методы в gear 2
        if gear >= 2 and name.startswith('_') and not name.startswith('__'):
            return

        if gear == 1:
            sig = f'{name}{params}'
        else:
            sig = f'{name}()'
        if isinstance(results, list) and results and isinstance(results[-1], dict):
            # Мы внутри контейнера — results это container['methods']
            results.append(sig)
        else:
            # Верхнеуровневая функция
            results.append({'kind': 'function', 'name': name, 'methods': [sig] if gear == 1 else []})
        return

    # Рекурсия для всех остальных узлов
    for child in node.children:
        _collect_ts_items(child, source, gear, results, depth)


def parse_via_treesitter(file_path: Path, gear: int) -> list[dict] | None:
    """
    Парсит файл через tree-sitter. Возвращает список типов в том же формате,
    что и regex-парсеры, или None если язык/пакет недоступен.
    """
    if not _TREESITTER_AVAILABLE:
        return None

    lang_name = _TS_LANG_MAP.get(file_path.suffix)
    if not lang_name:
        return None

    language = _load_ts_language(lang_name)
    if language is None:
        return None

    try:
        from tree_sitter import Parser
        source = file_path.read_bytes()
        parser = Parser(language)
        tree = parser.parse(source)
        results: list[dict] = []
        _collect_ts_items(tree.root_node, source, gear, results, depth=0)
        return results if results else []
    except Exception:
        return None
# ШЕСТЕРНИ (gear system, идея из PocketCoder)
# ─────────────────────────────────────────
# Gear 1 (малый проект, < 30 файлов):
#   файл → все классы/интерфейсы → все публичные методы с сигнатурами
#
# Gear 2 (средний, 30–150 файлов):
#   файл → классы/интерфейсы → только публичные методы (без тела)
#
# Gear 3 (большой, > 150 файлов):
#   пакет/папка → список классов → точки входа (main, init, handler)
#
# Гибридный gear: если в папке >= HYBRID_THRESHOLD файлов,
# для неё принудительно включается Gear 1 (подробные сигнатуры),
# независимо от глобальной шестерни.
# ─────────────────────────────────────────

GEAR_THRESHOLDS = (30, 150)  # (граница gear1→gear2, граница gear2→gear3)
HYBRID_THRESHOLD = 30        # файлов в папке для принудительного Gear 1

IGNORE_DIRS = {
    '.git', '.idea', '.vscode', '__pycache__', 'node_modules',
    'target', 'build', 'dist', '.gradle', 'venv', '.venv',
    'vendor', 'bin', 'obj', '.pytest_cache', 'wiki',
}

IGNORE_FILES = {'.DS_Store', 'Thumbs.db'}


# ─────────────────────────────────────────
# ПАРСЕРЫ ПО ЯЗЫКАМ (regex-based)
# ─────────────────────────────────────────

def parse_java(content: str, gear: int) -> list[dict]:
    """Извлекает типы и методы из Java/Kotlin файла."""
    results = []
    current_type = None

    for line in content.splitlines():
        stripped = line.strip()

        # Определение класса / интерфейса / enum / record
        m = re.match(
            r'(?:public\s+)?(?:abstract\s+|final\s+|sealed\s+)?'
            r'(class|interface|enum|record|@interface)\s+(\w+)'
            r'(?:<[^>]*>)?(?:\s+(?:extends|implements)[^{]*)?', stripped)
        if m:
            current_type = {'kind': m.group(1), 'name': m.group(2), 'methods': []}
            results.append(current_type)
            continue

        if current_type is None:
            continue

        # Публичный/protected метод
        if gear <= 2:
            m = re.match(
                r'(?:public|protected)\s+'
                r'(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?'
                r'(?:<[^>]*>\s+)?'
                r'([\w<>\[\],\s]+?)\s+(\w+)\s*\(([^)]*)\)', stripped)
            if m and not stripped.startswith('//'):
                return_type = m.group(1).strip()
                method_name = m.group(2)
                params = m.group(3).strip()

                if gear == 1:
                    sig = f'{method_name}({params}): {return_type}'
                else:
                    # gear 2: параметры без типов
                    param_names = ', '.join(
                        p.strip().split()[-1] for p in params.split(',') if p.strip()
                    ) if params else ''
                    sig = f'{method_name}({param_names})'

                current_type['methods'].append(sig)

    return results


def parse_python(content: str, gear: int) -> list[dict]:
    """Извлекает классы и функции из Python файла."""
    results = []
    current_class = None

    for line in content.splitlines():
        stripped = line.strip()

        # Класс
        m = re.match(r'class\s+(\w+)\s*(?:\([^)]*\))?:', stripped)
        if m and not line.startswith(' ') and not line.startswith('\t'):
            current_class = {'kind': 'class', 'name': m.group(1), 'methods': []}
            results.append(current_class)
            continue

        # Функция верхнего уровня
        if re.match(r'^def\s+', line):
            m = re.match(r'def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(.+))?:', stripped)
            if m:
                name, params, ret = m.group(1), m.group(2).strip(), m.group(3)
                if name.startswith('_') and not name.startswith('__'):
                    continue  # пропускаем приватные функции в gear 2/3
                sig = _python_sig(name, params, ret, gear)
                func = {'kind': 'function', 'name': name, 'methods': [sig] if gear == 1 else []}
                results.append(func)
            current_class = None
            continue

        # Метод внутри класса
        if current_class and re.match(r'    def\s+', line):
            m = re.match(r'def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(.+))?:', stripped)
            if m and gear <= 2:
                name, params, ret = m.group(1), m.group(2).strip(), m.group(3)
                if name.startswith('__') and name != '__init__':
                    continue
                if name.startswith('_') and not name.startswith('__') and gear == 2:
                    continue
                sig = _python_sig(name, params, ret, gear)
                current_class['methods'].append(sig)

    return results


def _python_sig(name: str, params: str, ret, gear: int) -> str:
    # Убираем self/cls
    clean_params = ', '.join(
        p.strip() for p in params.split(',')
        if p.strip() not in ('self', 'cls') and p.strip()
    )
    if gear == 1 and ret:
        return f'{name}({clean_params}) -> {ret.strip()}'
    elif gear == 1:
        return f'{name}({clean_params})'
    else:
        # gear 2: только имена без аннотаций
        bare = ', '.join(p.split(':')[0].split('=')[0].strip() for p in clean_params.split(',') if p.strip())
        return f'{name}({bare})'


def parse_go(content: str, gear: int) -> list[dict]:
    """Извлекает struct, interface и func из Go файла."""
    results = []
    current_type = None

    for line in content.splitlines():
        stripped = line.strip()

        # struct / interface
        m = re.match(r'type\s+(\w+)\s+(struct|interface)\s*\{?', stripped)
        if m:
            current_type = {'kind': m.group(2), 'name': m.group(1), 'methods': []}
            results.append(current_type)
            continue

        # func (метод или функция)
        m = re.match(r'func\s+(?:\((\w+\s+\*?\w+)\)\s+)?(\w+)\s*\(([^)]*)\)(.*)', stripped)
        if m and gear <= 2:
            receiver, fname, params, ret = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
            if fname[0].islower() and gear == 2:
                continue  # пропускаем unexported в gear 2
            if receiver and current_type:
                sig = f'{fname}({params}){(" → " + ret.rstrip("{").strip()) if ret and gear == 1 else ""}'
                current_type['methods'].append(sig)
            else:
                sig = f'func {fname}({params}){(" → " + ret.rstrip("{").strip()) if ret and gear == 1 else ""}'
                results.append({'kind': 'func', 'name': fname, 'methods': [sig]})

    return results


def parse_xml_config(content: str, gear: int) -> list[dict]:
    """Извлекает bean/route/service определения из XML конфигураций (Spring, Camel)."""
    results = []

    # Spring beans
    for m in re.finditer(r'<bean[^>]+id\s*=\s*["\'](\w+)["\'][^>]+class\s*=\s*["\']([^"\']+)["\']', content):
        results.append({'kind': 'bean', 'name': m.group(1),
                        'methods': [f'class: {m.group(2).split(".")[-1]}'] if gear == 1 else []})

    # Camel routes
    for m in re.finditer(r'<route[^>]*id\s*=\s*["\']([^"\']+)["\']', content):
        results.append({'kind': 'route', 'name': m.group(1), 'methods': []})

    # Generic service/component tags
    for tag in ('service', 'component', 'endpoint', 'processor', 'handler'):
        for m in re.finditer(rf'<{tag}[^>]+(?:id|name)\s*=\s*["\']([^"\']+)["\']', content):
            results.append({'kind': tag, 'name': m.group(1), 'methods': []})

    return results


PARSERS = {
    '.java': parse_java,
    '.kt': parse_java,       # Kotlin — regex-fallback; tree-sitter предпочтительнее
    '.py': parse_python,
    '.go': parse_go,
    '.xml': parse_xml_config,
}

# Расширения, которые понимает tree-sitter (но нет regex-парсера).
# Используются в collect_files, чтобы собирать эти файлы даже без tree-sitter
# (при его наличии они распарсятся, при отсутствии — пропустятся в parse_file).
_TS_ONLY_EXTENSIONS = {
    '.ts', '.tsx', '.js', '.jsx', '.mjs',
    '.rs', '.cs', '.swift', '.rb',
    '.c', '.h', '.cpp', '.cc', '.cxx',
    '.scala', '.php', '.dart', '.lua',
}

# Все расширения, которые мы собираем (regex + tree-sitter-only)
_ALL_EXTENSIONS = set(PARSERS.keys()) | _TS_ONLY_EXTENSIONS


# ─────────────────────────────────────────
# СБОР ФАЙЛОВ (возвращает дерево папок)
# ─────────────────────────────────────────

def collect_files(root: Path) -> dict[str, list[Path]]:
    """Возвращает {относительный_путь_папки: [файлы]}.
    Ключ '.' для корня, 'sub/dir' для вложенных.
    Файлы внутри каждой группы отсортированы."""
    tree: dict[str, list[Path]] = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            if fname in IGNORE_FILES:
                continue
            p = Path(dirpath) / fname
            if p.suffix in _ALL_EXTENSIONS:
                rel = p.relative_to(root)
                parent = str(rel.parent) if rel.parent != Path('.') else '.'
                tree[parent].append(p)
    for group in tree:
        tree[group].sort()
    return dict(sorted(tree.items()))


def count_files_per_folder(tree: dict[str, list[Path]]) -> dict[str, int]:
    """Считает общее количество файлов в каждой папке (включая подпапки).
    Возвращает {папка: количество_файлов}."""
    result = {}
    for folder in tree:
        total = len(tree[folder])
        # Добавляем файлы из подпапок
        for other_folder, files in tree.items():
            if other_folder.startswith(folder + '/'):
                total += len(files)
        result[folder] = total
    return result


def detect_gear(file_count: int) -> int:
    if file_count < GEAR_THRESHOLDS[0]:
        return 1
    elif file_count < GEAR_THRESHOLDS[1]:
        return 2
    return 3


# ─────────────────────────────────────────
# КЭШ ДЛЯ ИНКРЕМЕНТАЛЬНОГО РЕЖИМА
# ─────────────────────────────────────────

CACHE_FILENAME = '.repo-map-cache.json'


def load_cache(cache_path: Path) -> dict | None:
    """Загружает кэш parsed-данных. Возвращает None если нет или битый."""
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:
        return None


def save_cache(cache_path: Path, cache: dict) -> None:
    """Сохраняет кэш parsed-данных."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')


def parse_file(file_path: Path, gear: int, use_ast: bool = True) -> list[dict] | None:
    """Парсит один файл, возвращает список типов или None если неподдерживается.

    Стратегия (приоритет):
      1. Tree-sitter (если use_ast=True и пакеты установлены) — покрывает 31+ язык.
      2. Regex-fallback — Python, Java, Go, Kotlin, XML (без зависимостей).
      3. None — файл не поддерживается ни одним методом.
    """
    # Шаг 1: попытка через tree-sitter
    if use_ast:
        ts_result = parse_via_treesitter(file_path, gear)
        if ts_result is not None:
            return ts_result

    # Шаг 2: regex-fallback (только для языков с парсером)
    regex_parser = PARSERS.get(file_path.suffix)
    if not regex_parser:
        return None
    content = _safe_read(file_path)
    if not content:
        return None
    return regex_parser(content, gear)


def render_file_types(file_name: str, types: list[dict], gear: int) -> list[str]:
    """Рендерит один файл в строки markdown."""
    if gear == 3:
        # Для gear 3 — только факт наличия файла
        for t in types:
            if t['kind'] in ('class', 'struct', 'interface') and any(
                m in ['__init__', '__init__()', '__init__(self)'] or
                m.startswith('main(') or m == 'main'
                for m in t.get('methods', [])
            ):
                return [f'  {file_name}  ← точка входа']
        return [f'  {file_name}']
    lines = [f'  **{file_name}**']
    for t in types:
        icon = {'class': '📦', 'interface': '🔌', 'enum': '🏷',
                'record': '📋', 'struct': '📦', 'bean': '🫘',
                'route': '🔀', 'function': 'ƒ', 'func': 'ƒ'
                }.get(t['kind'], '·')
        lines.append(f'    {icon} {t["kind"]} `{t["name"]}`')
        for method in t.get('methods', []):
            lines.append(f'      · {method}')
    return lines


# ─────────────────────────────────────────
# РЕНДЕР В MARKDOWN (с поддержкой гибридного gear)
# ─────────────────────────────────────────

def render_map(root: Path, tree: dict[str, list[Path]],
               all_types: dict[str, list[dict]],
               global_gear: int, local_gears: dict[str, int]) -> str:
    """Рендерит полную карту из кэшированных типов.

    Параметры:
      root — корень анализируемой папки
      tree — {папка: [файлы]} от collect_files()
      all_types — {относительный_путь: [типы]} для всех файлов
      global_gear — глобальная шестерня
      local_gears — {папка: локальная_шестерня} от гибридного gear
    """
    lines = []

    # Группируем all_types по папкам
    grouped: dict[str, list[str]] = defaultdict(list)
    for rel_path_str, types in all_types.items():
        rel = Path(rel_path_str)
        parent = str(rel.parent) if rel.parent != Path('.') else '.'
        grouped[parent].append((rel_path_str, types))

    # Сортируем папки по имени
    for group in sorted(grouped):
        gear = local_gears.get(group, global_gear)

        if gear == 3:
            # Gear 3: только папки и точки входа
            lines.append(f'\n### {group}/')
            entry_files = []
            for rel_path_str, types in grouped[group]:
                fname = Path(rel_path_str).name
                rendered = render_file_types(fname, types, gear)
                if rendered and 'точка входа' in rendered[0]:
                    entry_files.append(rendered[0])
            if entry_files:
                lines.extend(entry_files)
            else:
                lines.append(f'  {len(grouped[group])} файлов')
        else:
            # Gear 1 или 2
            label = ''
            if gear == 1 and global_gear != 1:
                count = local_gears.get(group, 0)
                label = f'  (подробно, {count} файлов)'
            lines.append(f'\n### {group}/{label}')
            for rel_path_str, types in grouped[group]:
                fname = Path(rel_path_str).name
                if types:
                    lines.extend(render_file_types(fname, types, gear))

    return '\n'.join(lines)


def _safe_read(path: Path) -> str:
    for enc in ('utf-8', 'latin-1'):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ''


# ─────────────────────────────────────────
# ЧТЕНИЕ sources.md
# ─────────────────────────────────────────

def build_file_page_map(files_by_root: list[tuple[Path, Path]]) -> dict:
    """Строит пустой шаблон маппинга файл -> wiki-страница.
    Заполняется Claude во время ingestion (wiki-ingest).
    Ключ: относительный путь от root. Значение: путь к wiki-странице.
    
    Args:
        files_by_root: список кортежей (root_path, relative_file_path)
    """
    mapping = {}
    for root, rel_path in files_by_root:
        # rel_path уже относительный от root
        mapping[str(rel_path)] = ""  # заполняется при ingestion
    return mapping


def save_file_page_map(mapping: dict, output_path: Path) -> None:
    """Сохраняет маппинг рядом с repo-map.md."""
    map_path = output_path.with_name('file-page-map.json')
    map_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')


def read_sources(sources_path: Path) -> list[tuple[str, Path]]:
    """Возвращает список (метка, путь) из wiki/sources.md."""
    if not sources_path.exists():
        return []
    content = sources_path.read_text(encoding='utf-8')
    results = []
    for m in re.finditer(r'`([^`]+)`\s*\|\s*`([^`]+)`', content):
        label, path_str = m.group(1), m.group(2)
        p = Path(path_str)
        if p.exists() and p.is_dir():
            results.append((label, p))
    return results


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Генерация repo-map для wiki')
    parser.add_argument('path', nargs='?', help='Путь к исходникам (или автоопределение из sources.md)')
    parser.add_argument('--gear', type=int, choices=[1, 2, 3], help='Принудительная шестерня')
    parser.add_argument('--output', default='wiki/architecture/repo-map.md', help='Путь к выходному файлу')
    parser.add_argument('--max-files', type=int, default=500, help='Максимум файлов для анализа')
    parser.add_argument('--incremental', action='store_true',
                        help='Инкрементальный режим: перепарсить только изменённые файлы по mtime')
    parser.add_argument('--no-ast', action='store_true',
                        help='Отключить tree-sitter, использовать только regex-парсеры')
    args = parser.parse_args()

    # Определяем, использовать ли tree-sitter
    use_ast = not args.no_ast
    if use_ast and not _TREESITTER_AVAILABLE:
        use_ast = False  # tree-sitter не установлен — тихий fallback на regex

    # Сообщение о режиме парсинга
    if use_ast:
        print('Парсер: tree-sitter (с regex-fallback для неподдерживаемых языков)')
    else:
        print('Парсер: regex (tree-sitter недоступен или отключён через --no-ast)')

    # Определяем пути для анализа
    roots: list[tuple[str, Path]] = []

    if args.path:
        p = Path(args.path)
        if p.exists():
            roots = [('src', p)]
        else:
            print(f'Путь не найден: {args.path}', file=sys.stderr)
            sys.exit(1)
    else:
        sources_path = Path('wiki/sources.md')
        roots = read_sources(sources_path)
        if not roots:
            # Fallback: ищем src/ или app/ рядом
            for candidate in ('src', 'app', 'lib', 'core', 'pkg'):
                if Path(candidate).exists():
                    roots = [(candidate, Path(candidate))]
                    break
        if not roots:
            print('Не найдены исходники. Укажите путь или заполните wiki/sources.md', file=sys.stderr)
            sys.exit(1)

    # Определяем путь к кэшу (рядом с выходным файлом)
    output_path = Path(args.output)
    cache_path = output_path.with_name(CACHE_FILENAME)

    # Собираем дерево файлов для каждого root
    all_trees: dict[str, tuple[str, dict[str, list[Path]]]] = {}  # root_str -> (label, tree)
    for label, root in roots:
        tree = collect_files(root)
        if tree:
            all_trees[str(root)] = (label, tree)

    if not all_trees:
        print('Нет файлов для анализа', file=sys.stderr)
        sys.exit(1)

    # Считаем общее количество и определяем глобальный gear
    total_files = sum(len(files) for _, tree_data in all_trees.values() for files in tree_data.values())
    if total_files > args.max_files:
        print(f'Слишком много файлов ({total_files}). Используйте --max-files или укажите конкретный путь.')
        total_files = args.max_files

    global_gear = args.gear or detect_gear(total_files)
    gear_desc = {1: 'полные сигнатуры', 2: 'ключевые методы', 3: 'структура папок'}
    print(f'Файлов: {total_files} -> Gear {global_gear} ({gear_desc[global_gear]})')

    # Определяем локальные gear для каждой папки индивидуально
    all_folder_counts: dict[str, int] = {}
    all_local_gears: dict[str, int] = {}
    for root_str, (label, tree) in all_trees.items():
        folder_counts = count_files_per_folder(tree)
        all_folder_counts.update(folder_counts)
        for folder, count in folder_counts.items():
            if args.gear:
                # Если gear задан явно — используем его для всех папок
                all_local_gears[folder] = args.gear
            else:
                # Иначе вычисляем gear на основе количества файлов в папке
                all_local_gears[folder] = detect_gear(count)

    # Статистика по gear
    gear_counts = {1: 0, 2: 0, 3: 0}
    for g in all_local_gears.values():
        gear_counts[g] = gear_counts.get(g, 0) + 1
    print(f'  Распределение по папкам: Gear 1: {gear_counts[1]}, Gear 2: {gear_counts[2]}, Gear 3: {gear_counts[3]}')

    # Парсим все файлы (или загружаем из кэша при --incremental)
    all_types: dict[str, list[dict]] = {}
    changed_count = 0
    cached_count = 0

    cache = load_cache(cache_path) if args.incremental else None
    fresh_cache = {}

    for root_str, (label, tree) in all_trees.items():
        root = Path(root_str)
        for parent, files in tree.items():
            for file_path in files:
                rel = str(file_path.relative_to(root))

                if cache and rel in cache:
                    # Инкрементальная проверка: сверить mtime
                    try:
                        current_mtime = file_path.stat().st_mtime
                    except OSError:
                        current_mtime = 0

                    cached_entry = cache[rel]
                    if abs(cached_entry.get('mtime', 0) - current_mtime) < 0.001:
                        # Файл не изменился — берём из кэша
                        all_types[rel] = cached_entry['types']
                        fresh_cache[rel] = cached_entry
                        cached_count += 1
                        continue

                # Файл новый или изменился — перепарсить с локальным gear
                local_gear = all_local_gears.get(parent, global_gear)
                types = parse_file(file_path, local_gear, use_ast=use_ast) or []
                all_types[rel] = types
                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    mtime = 0
                fresh_cache[rel] = {'mtime': mtime, 'types': types}
                changed_count += 1

    # Если не было кэша (первый запуск), сохраняем все как fresh
    if not args.incremental:
        for root_str, (label, tree) in all_trees.items():
            root = Path(root_str)
            for parent, files in tree.items():
                for file_path in files:
                    rel = str(file_path.relative_to(root))
                    if rel not in fresh_cache:
                        types = all_types.get(rel, [])
                        try:
                            mtime = file_path.stat().st_mtime
                        except OSError:
                            mtime = 0
                        fresh_cache[rel] = {'mtime': mtime, 'types': types}

    if args.incremental:
        print(f'  Инкрементально: {changed_count} изменено, {cached_count} из кэша')

    # Строим итоговый markdown
    sections = []
    for root_str, (label, tree) in all_trees.items():
        root = Path(root_str)
        section = render_map(root, tree, all_types, global_gear, all_local_gears)
        if section.strip():
            sections.append(f'## {label} (`{root}/`)\n{section}')

    output_path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()

    content = f"""# Карта репозитория (repo-map)

**Краткое описание**: Автогенерируемый структурный скелет кодовой базы.

**Источники**: {', '.join(f'`{r}/`' for _, r in roots)}

**Последнее обновление**: {today}

**Шестерня**: индивидуальная для каждой папки
({total_files} файлов; порог gear 1/2/3: <{GEAR_THRESHOLDS[0]} / {GEAR_THRESHOLDS[0]}–{GEAR_THRESHOLDS[1]} / >{GEAR_THRESHOLDS[1]})
- Gear 1 (полные сигнатуры): {gear_counts[1]} папок
- Gear 2 (ключевые методы): {gear_counts[2]} папок  
- Gear 3 (структура): {gear_counts[3]} папок

**Парсер**: {'tree-sitter (с regex-fallback)' if use_ast else 'regex'}

> ⚠️ Этот файл генерируется автоматически скриптом `scripts/repo-map.py`.
> Не редактировать вручную — изменения будут перезаписаны.
> Для обновления: `python scripts/repo-map.py` или `python scripts/repo-map.py --incremental`

---

{''.join(chr(10) + s for s in sections)}

---

## Связанные страницы

- [[architecture/overview]]
- [[architecture/module-map]]
- [[architecture/data-flow]]
"""

    # Построить и сохранить file-page-map.json
    # Собираем файлы с сохранением информации о их root для правильного relative path
    files_by_root: list[tuple[Path, Path]] = []
    for root_str, (label, tree) in all_trees.items():
        root = Path(root_str)
        for parent, files in tree.items():
            for f in files:
                # f уже относительный от root, просто используем его как есть
                files_by_root.append((root, f))

    file_page_map = build_file_page_map(files_by_root)
    save_file_page_map(file_page_map, output_path)

    output_path.write_text(content, encoding='utf-8')
    save_cache(cache_path, fresh_cache)

    print(f'ok Карта сохранена: {output_path}')
    print(f'  Разделов: {len(sections)}')
    if args.incremental:
        print(f'  Кэш: {cache_path}')


if __name__ == '__main__':
    main()
