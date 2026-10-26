#!/usr/bin/env python3
"""
Universal HTTP URL nuller for binaries.
Заменяет все http/https адреса на нулевые байты (пустые строки той же длины).

Особенности:
  - Работает с несколькими файлами
  - Автоматически создаёт бэкапы (.bak)
  - Список исключений (не трогать определённые домены/URL)
  - Можно добавлять свои исключения через --exclude и --exclude-file

Примеры:
  python null_urls.py file1.exe file2.dll
  python null_urls.py *.exe --exclude "a11.gdl.easebar.com" --exclude "cdn.example.com"
  python null_urls.py *.exe --exclude-file excludes.txt
  python null_urls.py MuMuNxMain.exe -o patched.exe --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

# ============================================================
# ВСТРОЕННЫЙ СПИСОК ИСКЛЮЧЕНИЙ
# Можно дописывать сюда домены / части URL, которые НЕ нужно нулить
# ============================================================
DEFAULT_EXCLUDES = [
    # Локальные
    "127.0.0.1",
    "localhost",

    # Сертификаты
    "digicert.com",
    "ocsp.",
    "crl3.",
    "crl4.",
    "cacerts.",

    # Пример того, что ты просил (CDN / загрузки) # если нужно — раскомментируй
    #"a11.gdl.easebar.com",
    #"gdl.easebar.com",
    # "cdn.",        
    # "download.",
]

KEEP_PATTERNS: list[re.Pattern] = []


def build_keep_patterns(extra_excludes: list[str]):
    """Собирает итоговый список паттернов исключений."""
    global KEEP_PATTERNS
    KEEP_PATTERNS = []

    all_excludes = DEFAULT_EXCLUDES + extra_excludes

    for item in all_excludes:
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        pat = re.compile(re.escape(item.encode('utf-8')), re.I)
        KEEP_PATTERNS.append(pat)


URL_RE = re.compile(rb'https?://[^\x00\s"\'<>]+')


def should_keep(url: bytes, aggressive: bool) -> bool:
    if aggressive:
        return False
    for pat in KEEP_PATTERNS:
        if pat.search(url):
            return True
    return False


def null_urls(data: bytearray, aggressive: bool = False) -> list[tuple[int, bytes]]:
    results = []
    for m in URL_RE.finditer(data):
        url = m.group()
        if should_keep(url, aggressive):
            continue
        offset = m.start()
        length = len(url)
        results.append((offset, url))
        data[offset:offset + length] = b'\x00' * length
    return results


def process_file(src: Path, dst: Path | None, aggressive: bool, dry_run: bool, make_backup: bool):
    print(f"\n{'='*60}")
    print(f"[*] File: {src}")
    print(f"[*] Size: {src.stat().st_size:,} bytes")

    data = bytearray(src.read_bytes())
    results = null_urls(data, aggressive=aggressive)

    if not results:
        print("[*] No remote HTTP URLs found (or all excluded) — skipping.")
        return

    print(f"[*] Found {len(results)} URL(s) to null:")
    for offset, url in results:
        try:
            s = url.decode('ascii')
        except Exception:
            s = repr(url)
        print(f"    0x{offset:08X}  ({len(url):3d})  {s}")

    if dry_run:
        print("[*] Dry-run — nothing written.")
        return

    out = dst if dst is not None else src

    if make_backup and out.resolve() == src.resolve():
        bak = src.with_suffix(src.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(src.read_bytes())
            print(f"[+] Backup created → {bak}")
        else:
            print(f"[!] Backup already exists → {bak} (не перезаписываю)")

    out.write_bytes(data)
    print(f"[+] Patched → {out}")


def main():
    parser = argparse.ArgumentParser(
        description="Null all remote HTTP(S) URLs in binary files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("inputs", nargs="+", help="Input file(s) or masks")
    parser.add_argument("-o", "--output", help="Output file (только если один входной файл)")
    parser.add_argument("--aggressive", action="store_true",
                        help="Игнорировать все исключения (нулить вообще всё)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать, что будет занулено")
    parser.add_argument("--no-backup", action="store_true",
                        help="Не создавать .bak файлы")
    parser.add_argument("--exclude", action="append", default=[],
                        help="Добавить исключение (можно указывать несколько раз)")
    parser.add_argument("--exclude-file", type=Path,
                        help="Файл со списком исключений (по одному на строку)")
    args = parser.parse_args()

    extra = list(args.exclude)

    if args.exclude_file:
        if not args.exclude_file.is_file():
            print(f"[!] Exclude file not found: {args.exclude_file}")
            sys.exit(1)
        with open(args.exclude_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    extra.append(line)

    build_keep_patterns(extra)

    if not args.aggressive and KEEP_PATTERNS:
        print("[*] Active exclusions:")
        for p in KEEP_PATTERNS:
            print(f"    - {p.pattern.decode('utf-8', errors='replace')}")

    files: list[Path] = []
    for pattern in args.inputs:
        p = Path(pattern)
        if p.is_file():
            files.append(p)
        else:
            matched = list(Path().glob(pattern))
            if matched:
                files.extend(matched)
            else:
                print(f"[!] Not found: {pattern}")

    if not files:
        print("[!] No files to process.")
        sys.exit(1)

    if args.output and len(files) > 1:
        print("[!] -o/--output можно использовать только с одним входным файлом")
        sys.exit(1)

    for src in files:
        dst = Path(args.output) if args.output else None
        process_file(
            src=src,
            dst=dst,
            aggressive=args.aggressive,
            dry_run=args.dry_run,
            make_backup=not args.no_backup
        )

    print(f"\n{'='*60}")
    print(f"[*] Done. Processed {len(files)} file(s).")


if __name__ == "__main__":
    main()