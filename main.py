"""DocUnlock entry point.

Double-click (or `python main.py`) launches the GUI. Passing paths on the
command line runs headless: `python main.py file1.pdf folder2 -o out -p pw`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _cli(args: argparse.Namespace) -> int:
    from core.pipeline import Pipeline
    from core.result import Status

    paths = [Path(p) for p in args.paths]
    out = Path(args.out) if args.out else paths[0].resolve().parent / "DocUnlock_out"

    def show(result):
        print(f"[{result.status.value:>14}] {result.source.name} "
              f"-> {result.message or result.actions_text}")

    results = Pipeline().run(paths, out, args.password, progress=show)
    bad = sum(1 for r in results if r.status is Status.ERROR)
    print(f"\n{len(results)} archivos, {bad} con error. Salida: {out}")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="DocUnlock")
    parser.add_argument("paths", nargs="*", help="archivos o carpetas")
    parser.add_argument("-o", "--out", help="carpeta de salida")
    parser.add_argument("-p", "--password", help="contrasena para cifrados")
    args = parser.parse_args()

    if args.paths:
        return _cli(args)

    from gui.app import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
