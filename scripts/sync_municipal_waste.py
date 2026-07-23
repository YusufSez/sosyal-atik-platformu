"""Belediye atık toplama noktalarını senkronize et.

Kullanım:
  python scripts/sync_municipal_waste.py konya
  python scripts/sync_municipal_waste.py konya --file "C:\\path\\konya.html"
  python scripts/sync_municipal_waste.py ibb
  python scripts/sync_municipal_waste.py all
  python scripts/sync_municipal_waste.py --list
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from factory import create_app
from services.municipal_waste import list_providers, sync_all, sync_source


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(description="Belediye atık merkezi senkronu")
    parser.add_argument(
        "source",
        nargs="?",
        help=f"Kaynak kodu ({', '.join(list_providers())}) veya 'all'",
    )
    parser.add_argument(
        "--file",
        dest="file_path",
        help="Dosya tabanlı kaynaklar için HTML/JS yolu (ör. Konya)",
    )
    parser.add_argument("--list", action="store_true", help="Kayıtlı kaynakları listele")
    parser.add_argument("--limit", type=int, default=500, help="İBB limit (varsayılan 500)")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout (sn)")
    args = parser.parse_args(argv)

    if args.list or not args.source:
        print("Kayıtlı belediye kaynakları:")
        for key in list_providers():
            print(f"  - {key}")
        print("  - all")
        if not args.source:
            return 0

    app = create_app()
    with app.app_context():
        kwargs = {"limit": args.limit, "timeout": args.timeout}
        if args.file_path:
            kwargs["file_path"] = args.file_path

        if args.source.strip().lower() == "all":
            stats = sync_all(**kwargs)
            for line in stats.log_lines():
                print(line)
            return 0 if stats.errors == 0 else 1

        stats = sync_source(args.source, **kwargs)
        for line in stats.log_lines():
            print(line)
        return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
