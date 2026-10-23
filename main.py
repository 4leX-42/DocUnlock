"""DocUnlock entry point.

Double-click (or `python main.py`) launches the GUI. Passing paths on the
command line runs headless: `python main.py file1.pdf folder2 -o out -p pw`,
adding `-c ebook` (or screen/printer) to also shrink the cleaned files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _cli(args: argparse.Namespace) -> int:
    from core.options import Options
    from core.pipeline import Pipeline
    from core.result import Status

    # Redirected output on Windows uses the ANSI code page: never die on "→".
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    paths = [Path(p) for p in args.paths]
    out = Path(args.out) if args.out else paths[0].resolve().parent / "DocUnlock_out"

    # A redirected stdout on Windows is cp1252: never die on '→' or 'ñ'.
    sys.stdout.reconfigure(errors="replace")

    def show(result):
        print(f"[{result.status.value:>14}] {result.source.name} "
              f"[{result.size_text}] -> {result.message or result.actions_text}")

    options = Options(
        metadata=not args.keep_metadata,
        signatures=not args.keep_signatures,
        protection=not args.keep_protection,
        passwords=not args.keep_passwords,
        compress=args.compress,
    )
    if not options.anything:
        print("No hay nada que hacer: todo desactivado.")
        return 2
    results = Pipeline().run(
        paths, out, args.password, progress=show, options=options
    )
    bad = sum(1 for r in results if r.status is Status.ERROR)
    print(f"\n{len(results)} archivos, {bad} con error. Salida: {out}")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="DocUnlock")
    parser.add_argument("paths", nargs="*", help="archivos o carpetas")
    parser.add_argument("-o", "--out", help="carpeta de salida")
    parser.add_argument("-p", "--password", help="contraseña para cifrados")
    parser.add_argument("--keep-metadata", action="store_true", help="no borrar metadatos")
    parser.add_argument("--keep-signatures", action="store_true", help="no quitar firmas")
    parser.add_argument("--keep-protection", action="store_true",
                        help="no quitar la protección de edición de Office")
    parser.add_argument("--keep-passwords", action="store_true",
                        help="conservar contraseñas y permisos en la copia")
    parser.add_argument(
        "-c", "--compress", choices=("screen", "ebook", "printer"),
        help="reducir tamaño con este perfil",
    )
    args = parser.parse_args()

    if args.paths:
        return _cli(args)

    from install import ensure_installed
    if ensure_installed():
        return 0

    from gui.app import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
