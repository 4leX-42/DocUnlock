# DocUnlock

Herramienta local para limpiar documentos propios: quita restricciones de
edición, permisos, firmas digitales y metadatos de PDF y Office, por archivo
o por lotes. Todo el procesamiento es local; nada se sube a ningún servicio.

Los originales no se tocan: cada documento procesado se escribe en una
carpeta de salida aparte.

## Qué hace por formato

| Formato | Operaciones |
|---------|-------------|
| PDF | Quita permisos/cifrado de propietario, firmas digitales (`/Sig`, `/Perms`, `/SigFlags`) y metadatos (DocInfo + XMP). Descifra si das la contraseña de apertura. |
| Word/Excel/PowerPoint (`.docx/.xlsx/.pptx`) | Quita protección de edición (`documentProtection`, `writeProtection`, `sheetProtection`, `workbookProtection`, `modifyVerifier`, `fileSharing`) y metadatos (`docProps`). |
| Office cifrado (contraseña de apertura) | Descifra con la contraseña que tú indicas y luego limpia. |
| `.doc/.xls/.ppt` binarios antiguos | Se detectan y se avisan; conviene convertirlos a formato moderno primero. |

## Límites reales (no del programa)

- Un documento con **contraseña de apertura** está cifrado. Sin esa
  contraseña no se puede leer el contenido. Debes aportarla tú.
- Quitar una firma digital **invalida** la firma. Si el documento vale como
  original firmado (p. ej. una factura oficial), la copia limpia ya no lo es.
- Este programa **no adivina contraseñas**. No incluye fuerza bruta ni
  diccionarios. Solo usa la contraseña que tú proporcionas.

## Uso

### GUI (doble clic)

Tras compilar (`build.bat`), doble clic en `dist\DocUnlock.exe`. Añade
archivos o una carpeta, elige salida, pon la contraseña si hace falta y pulsa
**Process**.

### Línea de comandos (sin GUI)

```
python main.py "C:\ruta\doc.pdf" "C:\carpeta" -o "C:\salida" -p micontrasena
```

## Desarrollo

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py            REM lanza la GUI
```

## Compilar el .exe

```bat
build.bat
```

Genera `dist\DocUnlock.exe` (un solo archivo, sin consola).

## Arquitectura

```
main.py              Entrada: GUI o CLI
core/detect.py       Detección de formato por magic bytes
core/pipeline.py     Orquestación y lotes
core/result.py       Modelo de resultado por archivo
processors/pdf_proc.py      PDF (pikepdf)
processors/office_proc.py   OOXML + descifrado OLE (msoffcrypto)
gui/app.py           Interfaz PySide6
```

Añadir un formato = un nuevo `Processor` en `processors/` registrado en
`Pipeline`.
