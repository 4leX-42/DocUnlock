# DocUnlock — Estado y pendientes

Fecha: 2026-10-21

Este documento explica **qué es** la herramienta, **cómo** está construida, **qué
está probado** y **qué falta** por hacer. El código vive en la carpeta
`Azure_MS_entorno\DocUnlock\`. Proyecto **terminado** el 2026-10-21: limpieza,
modo compresión, GUI y `.exe` portable probados.

---

## 1. Qué es

Una herramienta local de escritorio para Windows que procesa documentos
**propios** y, desde una sola interfaz, les quita todo lo que impide editarlos o
reutilizarlos:

- Restricciones de edición.
- Permisos de PDF (no editar, no copiar, etc.).
- Firmas digitales.
- Metadatos (autor, empresa, fechas, revisiones).

Funciona por archivo o por lotes (una carpeta entera, mezclando formatos). Todo
el procesamiento es **local**: nada se sube a ningún servicio externo. Los
originales **no se tocan**; cada documento procesado se escribe en una carpeta de
salida aparte.

### Qué NO hace (decisión deliberada)

No incluye adivinación de contraseñas: ni fuerza bruta, ni diccionarios, ni
combinaciones a partir del nombre del archivo. Si un documento está cifrado con
contraseña de apertura, la contraseña **la aporta el usuario**; la herramienta la
usa para descifrar, pero nunca intenta averiguarla.

---

## 2. Cómo está construido

- **Lenguaje:** Python.
- **GUI:** PySide6 (Qt). Interfaz mínima: añadir archivos/carpeta, campo de
  contraseña opcional, botón Process, tabla de estado por archivo.
- **Empaquetado:** PyInstaller → `DocUnlock.exe` de un solo archivo, doble clic,
  sin consola (`build.bat`).
- **PDF:** `pikepdf` (motor QPDF).
- **Office cifrado:** `msoffcrypto-tool`.
- **Office sin cifrar:** manipulación directa del ZIP/XML (sin dependencias).

### Estructura

```
DocUnlock/
  main.py                     Entrada: GUI (doble clic) o CLI (si pasas rutas)
  core/
    detect.py                 Detección de formato por magic bytes + ZIP sniff
    pipeline.py               Orquestación, recorrido de carpetas, lotes
    result.py                 Modelo de resultado por archivo (estado, acciones)
  processors/
    base.py                   Contrato abstracto Processor
    pdf_proc.py               PDF (pikepdf)
    office_proc.py            docx/xlsx/pptx + descifrado OLE (msoffcrypto)
    compress.py               Modo compresión (pikepdf + Pillow para PDF, Pillow para Office)
    pdf_fonts.py              Recorte de fuentes TrueType incrustadas (fontTools)
  gui/app.py                  Interfaz PySide6 con hilo de trabajo (QThread)
  tests/test_pipeline.py      Banco de pruebas con ficheros sintéticos
  requirements.txt
  build.bat                   Compila el .exe (solo librerías Python)
  README.md
  docs/ESTADO-Y-PENDIENTE.md  Este documento
```

### Cómo detecta el formato

Por los primeros bytes (magic bytes), no por la extensión:

- `%PDF` → PDF.
- `PK\x03\x04` (ZIP) → se abre y se mira qué carpeta interna tiene: `word/`,
  `xl/`, `ppt/` → docx/xlsx/pptx.
- `\xd0\xcf\x11\xe0...` (CFB/OLE) → Office antiguo binario, o un OOXML cifrado
  con contraseña.

### Cómo procesa cada formato

- **PDF** (`pdf_proc.py`): abre con pikepdf; al reescribir sin `encrypt=` se
  pierden cifrado y permisos de propietario. Quita firmas (campos `/Sig` del
  `/AcroForm`, `/Perms` del root, `/SigFlags` a 0) y además barre las
  anotaciones de widget huérfanas de las páginas para que Acrobat no avise.
  Borra metadatos: `/Info` del trailer (DocInfo) y el stream XMP `/Metadata`.
- **Office OOXML** (`office_proc.py`): recorre el ZIP y reescribe las partes:
  - Quita por regex los elementos de protección: `w:documentProtection`,
    `w:writeProtection`, `sheetProtection`, `workbookProtection`,
    `fileSharing`, `p:modifyVerifier`.
  - Vacía el contenido de `docProps/core.xml`, `app.xml` y `custom.xml`
    dejando solo la raíz válida (borra autor, lastModifiedBy, etc.).
- **Office cifrado (OLE)**: con la contraseña del usuario, `msoffcrypto`
  descifra a un temporal y luego se limpia como OOXML normal. Si es `.doc/.xls`
  binario antiguo sin cifrar, se avisa y se recomienda convertir a formato
  moderno.

---
### Modo compresión (hecho 2026-10-21)

Es una **casilla que se combina con la limpieza** ("Compress" + perfil en la
GUI, `-c <perfil>` en CLI): primero se limpia, después se comprime la copia
limpia. El fichero comprimido solo sustituye al limpio si pesa menos.

| Perfil | PDF (resolución, calidad JPEG) | Imágenes Office (lado máx., calidad JPEG) |
|--------|--------------------------------|-------------------------------------------|
| `screen` | 72 ppp, 50 | 1280 px, 60 |
| `ebook` (por defecto) | 150 ppp, 60 | 1920 px, 75 |
| `printer` | 300 ppp, 80 | 3000 px, 85 |

- **PDF** (2026-10-22, sustituye a Ghostscript; motivo: AGPL y fallos de
  seguridad graves con explotación real, CVE-2024-29510, en un binario
  congelado dentro del `.exe` que nadie parchea, lo que no pasaría el control
  A.8.8 de ISO 27001). Todo dentro del proceso con pikepdf, Pillow y fontTools:
  - Mide a qué tamaño se **dibuja** cada imagen (contenido de página y Form
    XObjects, siguiendo `q/Q/cm`) y baja las que superen 1,5 × la resolución
    del perfil, como hace Ghostscript. Fotos y escaneos a JPEG; dibujos de
    256 colores o menos, sin pérdida. Se saltan máscaras, CMYK, 1 bit y
    JBIG2/CCITT/JPX.
  - Imagen Flate **dañada**: se rescata lo legible y el resto queda en blanco,
    como lo pintan los visores (la *Guía LinkedIn* tenía una de 13 MB).
  - **Fuentes** (`pdf_fonts.py`): Word incrusta TrueType enteras aunque las
    marque como subconjunto (`ABCDEE+Calibri`, ~200 KB). Se recortan con
    fontTools conservando los ids de glifo: TrueType simples, todo lo que
    alcanzan los 256 códigos; Type0 Identity, los glifos usados. Las fuentes
    del `/DR` de formularios no se tocan.
  - Imágenes idénticas repetidas se unen en un solo objeto.
  - Guarda con streams recomprimidos y object streams. No añade `Producer` ni
    XMP, así que no hace falta volver a borrar metadatos.
- **Office**: se recomprimen los JPEG/PNG de `word|xl|ppt/media/` con Pillow,
  mismo nombre y formato (no se tocan content types ni relaciones). EMF/WMF y
  otros formatos se dejan como están.
- La tabla muestra **tamaño antes → después (%)** por archivo.
- **Comparativa con Ghostscript 10.05.1** (2026-10-22, 9 PDF reales del equipo
  más un escaneo sintético, 46,5 MB en total; calidad = PSNR mínimo de todas
  las páginas a 72 ppp frente al original):

  | Perfil | Ghostscript | pikepdf | Tiempo GS / pikepdf |
  |--------|-------------|---------|---------------------|
  | `screen` | 9,5 MB | 9,5 MB | 9,0 s / 6,2 s |
  | `ebook` | 11,9 MB | 11,4 MB | 8,7 s / 6,4 s |
  | `printer` | 19,5 MB | 15,7 MB | 9,5 s / 7,2 s |

  Mismo peso o menos y más rápido, con mejor PSNR en casi todos (el texto y
  los vectores no se rasterizan ni se reescriben). Ghostscript gana algo en
  PDF de texto puro (Alcampo: 176 frente a 229 KB).

---

## 3. Qué está probado (2026-10-21)

- **Factura real firmada** (`14209724-FACTURA CCAA...pdf`, iText 7.1.5): sin
  cifrado, `SigFlags 0`, sin `/Perms`, 2 firmas quitadas, metadatos borrados,
  sin widgets huérfanos.
- **Banco de pruebas** `tests/test_pipeline.py` (8 casos, todos OK; genera los
  ficheros al vuelo, sin documentos reales en el repo):
  - docx protegido: protección y metadatos fuera, contenido intacto, original sin tocar.
  - **docx cifrado real** (cifrado con msoffcrypto): sin contraseña →
    `NEEDS_PASSWORD`; contraseña mala → `NEEDS_PASSWORD` "Contrasena incorrecta"
    (antes daba `ERROR`: msoffcrypto falla en `decrypt()`, no en `load_key()` —
    corregido); contraseña buena → descifrado y limpio, sin temporales.
  - **PDF con contraseña de apertura real**: sin contraseña → `NEEDS_PASSWORD` y
    no deja nada a medias; con ella → descifrado y sin metadatos.
  - PDF con permisos de propietario: sale sin cifrado.
  - Compresión PDF (2 páginas A4 a 300 ppp): ≥40 % menos, mismas páginas, sin
    `/Info` ni XMP. Compresión docx: imagen a ≤1920 px, sigue siendo JPEG.
  - Lote con `a\factura.docx` y `b\factura.docx` y salida **dentro** de la
    carpeta de entrada: respeta subcarpetas y la segunda pasada no reprocesa su
    propia salida.
- **GUI** conducida de punta a punta (Qt offscreen): añadir carpeta, Compress,
  Process, fila con tamaño y detalle, botón "Open output" habilitado.
- **`.exe` real** (`dist\DocUnlock.exe`, recompilado 2026-10-22 sin
  Ghostscript: 71 MB, antes 87): en modo CLI procesó 11 PDF con `-c ebook`,
  45,4 MB a 11 MB, y marcó como error el PDF dañado de prueba.
- **Cancelar** a mitad de lote (2 de 11 hechos, 9 marcados *Cancelado*) y
  **doble clic** en fila (abre la copia; en error muestra el detalle).

Ejecutar las pruebas: `.venv\Scripts\python -m unittest -v tests.test_pipeline`.

---

## 4. Requisito: cualquier Windows 11 sin permisos de administrador

Cumplido por diseño:

- `DocUnlock.exe` es portable: no se instala, no escribe en el registro ni en
  `Program Files`. PyInstaller lo descomprime en `%TEMP%\_MEI…` en cada arranque
  y lo borra al cerrar.
- Python, Qt, pikepdf, msoffcrypto, Pillow y fontTools van **dentro** del
  `.exe`. El equipo destino no necesita nada instalado.
- Compilar tampoco pide admin (`build.bat` usa un venv local).

Lo que puede estorbar en un equipo concreto (no depende del programa):

1. **SmartScreen**: un `.exe` sin firmar descargado de Internet/Teams/correo
   muestra "Windows protegió su PC". Se pasa con *Más información → Ejecutar
   de todas formas*, sin admin. Copiado por USB o carpeta de red no suele salir.
2. **Equipos gestionados (Intune)**: si hay AppLocker/WDAC o la regla ASR
   *"Bloquear ejecutables que no cumplan criterios de prevalencia, antigüedad o
   lista de confianza"*, el `.exe` se bloquea. Solución: firmar el
   `.exe` con un certificado de firma de código o que IT lo permita por hash.
3. **Antivirus**: los `.exe` de PyInstaller *onefile* a veces dan falso
   positivo heurístico. Mismo remedio: firma o exclusión.
4. **Licencias** (inventario ISO): pikepdf MPL-2.0, qpdf Apache-2.0, Pillow
   MIT-CMU, fontTools MIT, msoffcrypto-tool MIT, PySide6 LGPL-3.0. Ninguna
   obliga a publicar el código por uso interno. Versiones fijadas en
   `requirements.txt`: al salir un parche de seguridad, subir versión y
   recompilar.

---

## 5. Cómo retomar o recompilar

```bat
cd C:\Users\alexa\Documents\Testeo2.0\Azure_MS_entorno\DocUnlock
build.bat                 REM crea .venv si falta -> dist\DocUnlock.exe
.venv\Scripts\python main.py                  REM GUI desde código
.venv\Scripts\python main.py C:\docs -c ebook REM CLI, limpiar y comprimir
```

Añadir un formato = un `Processor` en `processors/` registrado en `Pipeline`
(`core/pipeline.py`). Mejoras opcionales, no pedidas: firmar el `.exe`, adelgazar
el empaquetado (Qt Quick/QML/Pdf se cuelan por los plugins de Qt, ~15 MB).

---

## 6. Interfaz (rehecha 2026-10-21)

La primera GUI (Qt por defecto, en inglés) se descartó. La actual:

- **Toda en castellano**, negro, blanco y rojo corporativo (`#E30613`), con
  Bahnschrift (viene con Windows). Tokens en `gui/theme.py`; formas con
  esquinas cortadas pintadas a mano en `gui/widgets.py`. El rojo solo marca lo
  activo: interruptor encendido, perfil elegido, botón Procesar, zona de
  arrastre bajo el cursor y errores. Barra de título negra en Windows 11.
- **Dos bloques independientes**:
  - *Limpiar*: metadatos, firmas digitales, protección de edición y
    contraseñas/permisos, cada uno con su interruptor (`core/options.py`).
  - *Comprimir*: reducir tamaño con perfil Máxima / Equilibrada / Ligera.
    Se puede usar sin limpiar nada.
- Con *Contraseñas y permisos* apagado la copia sigue protegida: el PDF se
  guarda con su cifrado original y el Office se vuelve a cifrar con la misma
  contraseña después de comprimir. Un PDF cuyo cifrado se conserva también se
  comprime y sale con el mismo cifrado (desde 2026-10-22).
- Cola visible al soltar archivos, barra de progreso real (n de N), resumen
  final con el ahorro total y aviso de los que piden contraseña.
- Icono propio (`assets/docunlock.ico`), también en el `.exe`.

Pruebas: 13 casos OK, incluidos conservar contraseña en PDF y en docx,
comprimir sin limpiar, recorte de fuente TrueType entera y PDF cifrado
comprimido con imágenes repetidas unidas.
