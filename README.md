<!--
[ES] DocUnlock: quita protecciones, permisos, firmas y metadatos de PDF y Office, y opcionalmente comprime. Todo local, sin admin.
[EN] DocUnlock: strips protections, permissions, signatures and metadata from PDF and Office files, and can compress. Local only, no admin.
Contexto: usuario
Instalar: $f="$env:TEMP\DocUnlock.exe"; [Net.ServicePointManager]::SecurityProtocol=3072; irm https://github.com/4leX-42/DocUnlock/releases/latest/download/DocUnlock.exe -OutFile $f; explorer.exe "$f"
-->
# DocUnlock

Herramienta local para limpiar documentos propios: quita restricciones de
edición, permisos, firmas digitales y metadatos de PDF y Office, por archivo
o por lotes. Todo el procesamiento es local; nada se sube a ningún servicio.

Parte de [GADGETS-SUPPORT_CX](https://github.com/4leX-42/GADGETS-SUPPORT_CX), el catálogo de herramientas.

Opcionalmente **reduce el tamaño** (bloque *Comprimir*, independiente de la
limpieza): PDF con pikepdf + Pillow + fontTools y las imágenes de Office con
Pillow. Sin Ghostscript ni ningún binario externo.

Los originales no se tocan: cada documento procesado se escribe en una
carpeta de salida aparte (por defecto `DocUnlock_out` junto al primer
archivo), respetando subcarpetas y sin sobrescribir nunca: si el nombre ya
existe, sale `doc (1).pdf`.

**Funciona en cualquier Windows 11 sin permisos de administrador**: el `.exe`
es portable y lleva todo dentro. Lo que sí puede
bloquearlo (SmartScreen, AppLocker/ASR en equipos gestionados) está en
`docs/ESTADO-Y-PENDIENTE.md`, sección 4.

**Ábrelo siempre sin elevar** (no "Ejecutar como administrador"): si la ventana
corre como admin (integridad alta), Windows bloquea el arrastrar y soltar desde
el Explorador (integridad media) y no podrás tirar documentos ni carpetas a la
app. Por eso el comando de instalación lo lanza con `explorer.exe`: arranca al
nivel del usuario aunque lo pegues en una PowerShell ya elevada.

## Qué hace por formato

| Formato | Operaciones |
|---------|-------------|
| PDF | Quita permisos/cifrado de propietario, firmas digitales (`/Sig`, `/Perms`, `/SigFlags`) y metadatos (DocInfo + XMP). Descifra si das la contraseña de apertura. |
| Word/Excel/PowerPoint (`.docx/.xlsx/.pptx`) | Quita protección de edición (`documentProtection`, `writeProtection`, `sheetProtection`, `workbookProtection`, `modifyVerifier`, `fileSharing`) y metadatos (`docProps`). |
| Office cifrado (contraseña de apertura) | Descifra con la contraseña que tú indicas y luego limpia. |
| `.doc/.xls/.ppt` binarios antiguos | Sin cifrar: se avisan (conviene convertirlos a formato moderno). Cifrados: se descifran con tu contraseña. |

## Compresión

| Perfil | PDF | Imágenes Office |
|--------|-----|-----------------|
| `screen` | ~72 ppp | 1280 px, JPEG 60 |
| `ebook` (defecto) | ~150 ppp | 1920 px, JPEG 75 |
| `printer` | ~300 ppp | 3000 px, JPEG 85 |

Se aplica después de limpiar, y solo se queda con el resultado si pesa menos.
En PDF: baja las imágenes a la resolución del perfil según el tamaño al que
se dibujan en la página, fotos y escaneos a JPEG (calidad 50/60/80) y dibujos
de pocos colores sin pérdida; recorta las fuentes TrueType incrustadas
enteras (Word mete Calibri completa, ~200 KB por estilo) a los glifos que
puede usar; une imágenes repetidas; y rehace la compresión interna. No toca
texto, vectores, formularios, enlaces ni metadatos, y un PDF que conserva su
contraseña se comprime y sale con el mismo cifrado.

## Límites reales (no del programa)

- Un documento con **contraseña de apertura** está cifrado. Sin esa
  contraseña no se puede leer el contenido. Debes aportarla tú.
- Quitar una firma digital **invalida** la firma. Si el documento vale como
  original firmado (p. ej. una factura oficial), la copia limpia ya no lo es.
- Este programa **no adivina contraseñas**. No incluye fuerza bruta ni
  diccionarios. Solo usa la contraseña que tú proporcionas.

## Uso

### GUI (doble clic)

Doble clic en `dist\DocUnlock.exe`. Arrastra documentos o carpetas a la
ventana y elige qué hacer, en dos bloques independientes:

- **Limpiar**: metadatos, firmas digitales, protección de edición y
  contraseñas/permisos, cada uno con su interruptor. Si desactivas
  *Contraseñas y permisos*, la copia conserva la contraseña: el PDF guarda su
  cifrado original y el Office se vuelve a cifrar con la misma contraseña.
- **Comprimir**: *Reducir tamaño* con perfil Máxima, Equilibrada o Ligera.
  Se puede usar sola, sin limpiar nada.

Pulsa **Procesar**. La tabla muestra estado, tamaño antes y después y qué se
ha hecho con cada documento. Durante el lote el botón pasa a **Cancelar**:
termina el documento en curso y deja el resto sin procesar. Doble clic en una
fila abre la copia limpia, o el detalle completo si dio error. La papelera de
cada fila la quita de la cola; *Abrir carpeta de salida* abre el resultado.

### Línea de comandos (sin GUI)

```
python main.py "C:\ruta\doc.pdf" "C:\carpeta" -o "C:\salida" -p micontrasena -c ebook
```

Por defecto limpia todo; `--keep-metadata`, `--keep-signatures`,
`--keep-protection` y `--keep-passwords` desactivan cada paso.

## Desarrollo

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py                              REM lanza la GUI
python -m unittest -v tests.test_pipeline   REM pruebas
```

## Compilar el .exe

```bat
build.bat
```

Genera `dist\DocUnlock.exe` (un solo archivo, sin consola). Solo librerías
Python con licencia permisiva o LGPL, versiones fijadas en `requirements.txt`.
No hace falta admin para compilar.

## Desplegar

Se reparte solo `dist\DocUnlock.exe`. Al abrirlo por primera vez desde
cualquier sitio (USB, Descargas, una carpeta compartida) se copia a
`%LOCALAPPDATA%\Programs\DocUnlock`, crea el acceso directo en Inicio (sale en
la búsqueda de Windows) y se vuelve a abrir desde allí; el original se puede
borrar. Una versión nueva abierta igual sustituye a la instalada. Por usuario
y sin admin; si algo falla, arranca sin instalar. Lógica en `install.py`.

## Arquitectura

```
main.py              Entrada: GUI o CLI
core/detect.py       Detección de formato por magic bytes
core/pipeline.py     Orquestación y lotes
core/result.py       Modelo de resultado por archivo
processors/pdf_proc.py      PDF (pikepdf)
processors/office_proc.py   OOXML + descifrado OLE (msoffcrypto)
processors/compress.py      Compresión (imágenes PDF y Office)
processors/pdf_fonts.py     Recorte de fuentes TrueType incrustadas (fontTools)
gui/app.py           Interfaz PySide6
tests/               Pruebas con ficheros sintéticos
```

Añadir un formato = un nuevo `Processor` en `processors/` registrado en
`Pipeline`.
