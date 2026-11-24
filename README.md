<!--
[ES] DocUnlock: quita protecciones, permisos, firmas y metadatos de PDF y Office, y opcionalmente comprime. Todo local, sin admin.
[EN] DocUnlock: strips protections, permissions, signatures and metadata from PDF and Office files, and can compress. Local only, no admin.
Contexto: usuario
Instalar: $f="$env:TEMP\DocUnlock.exe"; [Net.ServicePointManager]::SecurityProtocol=3072; irm https://github.com/4leX-42/DocUnlock/releases/latest/download/DocUnlock.exe -OutFile $f; explorer.exe "$f"
-->
<div align="center">

# DocUnlock

Limpieza y compresión local de PDF y Office. Sin admin, sin red.

![Windows 11](https://img.shields.io/badge/Windows-11-1f1f1f?style=flat-square) ![Python](https://img.shields.io/badge/Python-PySide6-1f1f1f?style=flat-square&logo=python&logoColor=white) ![Local](https://img.shields.io/badge/100%25-local-c8102e?style=flat-square)

<img src="assets/screenshot.png" width="760" alt="DocUnlock">

<sub>Parte de <a href="https://github.com/4leX-42/GADGETS-SUPPORT_CX">GADGETS-SUPPORT_CX</a></sub>

</div>

## <img src="https://api.iconify.design/lucide/download.svg?color=%238b949e" width="18" align="top"> Instalar

```powershell
$f="$env:TEMP\DocUnlock.exe"; [Net.ServicePointManager]::SecurityProtocol=3072; irm https://github.com/4leX-42/DocUnlock/releases/latest/download/DocUnlock.exe -OutFile $f; explorer.exe "$f"
```

Se instala en `%LOCALAPPDATA%\Programs\DocUnlock` con acceso en Inicio. Abrir sin elevar: con integridad alta Windows bloquea el arrastrar y soltar.

## <img src="https://api.iconify.design/lucide/eraser.svg?color=%238b949e" width="18" align="top"> Qué hace

| Formato | Limpia |
|---|---|
| <img src="https://api.iconify.design/lucide/file-text.svg?color=%238b949e" width="18" align="top"> PDF | Permisos, cifrado de propietario, firmas (`/Sig`, `/Perms`), DocInfo y XMP |
| <img src="https://api.iconify.design/lucide/file-type.svg?color=%238b949e" width="18" align="top"> `.docx` `.xlsx` `.pptx` | Protección de edición y hoja, `docProps` |
| <img src="https://api.iconify.design/lucide/key-round.svg?color=%238b949e" width="18" align="top"> Office cifrado | Descifra con la contraseña indicada y limpia |
| <img src="https://api.iconify.design/lucide/file-clock.svg?color=%238b949e" width="18" align="top"> `.doc` `.xls` `.ppt` | Solo descifrado |

<img src="https://api.iconify.design/lucide/minimize-2.svg?color=%238b949e" width="18" align="top"> **Comprimir** (opcional, independiente): imágenes a 72 / 150 / 300 ppp, recorte de fuentes incrustadas, deduplicado. Solo se guarda si pesa menos.

<img src="https://api.iconify.design/lucide/shield-check.svg?color=%238b949e" width="18" align="top"> Los originales no se modifican: la salida va a `DocUnlock_out` sin sobrescribir.

> <img src="https://api.iconify.design/lucide/shield-off.svg?color=%238b949e" width="18" align="top"> Sin fuerza bruta: las contraseñas de apertura las aporta el usuario. Quitar una firma la invalida.

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%238b949e" width="18" align="top"> CLI

```
python main.py <archivos|carpetas> -o <salida> [-p <contraseña>] [-c screen|ebook|printer]
```

`--keep-metadata` `--keep-signatures` `--keep-protection` `--keep-passwords`

<details>
<summary><img src="https://api.iconify.design/lucide/code-xml.svg?color=%238b949e" width="18" align="top"> <b>Desarrollo</b></summary>

```bat
py -3 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python main.py                              REM GUI
python -m unittest -v tests.test_pipeline   REM pruebas
build.bat                                   REM dist\DocUnlock.exe
```

```
main.py                 entrada GUI / CLI
core/                   detección, pipeline, resultado
processors/             pdf_proc, office_proc, compress, pdf_fonts
gui/app.py              PySide6
tests/                  ficheros sintéticos
```

Formato nuevo: un `Processor` en `processors/` registrado en `Pipeline`. Bloqueos en equipos gestionados (SmartScreen, AppLocker, ASR): `docs/ESTADO-Y-PENDIENTE.md` §4.
</details>
