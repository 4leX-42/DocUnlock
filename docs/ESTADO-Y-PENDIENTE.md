# DocUnlock — Estado y pendientes

Fecha: 2026-10-21

Este documento explica **qué es** la herramienta, **cómo** está construida, **qué
está probado** y **qué falta** por hacer. El código vive en la carpeta
`DocUnlock/` dentro de `Testeo2.0`. La construcción quedó pausada a petición del
usuario; se retoma más adelante.

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
  gui/app.py                  Interfaz PySide6 con hilo de trabajo (QThread)
  requirements.txt
  build.bat                   Compila el .exe
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

## 3. Qué está probado (2026-10-21)

Verificado headless por CLI (misma lógica que usa la GUI):

- **Factura real firmada** (`14209724-FACTURA CCAA...pdf`, iText 7.1.5): salida
  sin cifrado, `SigFlags 0`, sin `/Perms`, 2 firmas quitadas, metadatos
  borrados, sin widgets huérfanos. Queda editable sin el truco de "Imprimir →
  Guardar como PDF".
- **docx sintético protegido**: protección de edición fuera, metadatos borrados,
  contenido intacto, ZIP válido.
- `py_compile` OK en todos los módulos (incluida la GUI).

El venv de pruebas tiene solo `pikepdf` + `msoffcrypto-tool`. `PySide6` y
`PyInstaller` aún no se instalaron; los instala `build.bat` al compilar.

---

## 4. Qué falta

### 4.1. Modo de compresión / reducir tamaño (PEDIDO — pendiente)

Incorporar a la misma herramienta un modo para **reducir el peso** de ficheros
manteniendo legibilidad, igual que se hizo con el PDF "Anexo 7. Preacuerdos con
puntos de retorno".

**Referencia de aquel trabajo (2026-10-21):** el peso estaba en páginas
escaneadas a ~300 ppp. Se usó **Ghostscript** para rebajarlas:

- Binario: `C:\Program Files\gs\gs10.08.0\bin\gswin64c.exe`.
- Dispositivo: `pdfwrite`, `-dCompatibilityLevel=1.6`.
- Perfiles comparados: `-dPDFSETTINGS=/ebook` (≈150 ppp, el elegido) frente a
  `/printer` (≈300 ppp).
- Resultado: 29,7 MB de origen bajaron notablemente con `/ebook`, revisando la
  legibilidad página a página antes de dar por buena la compresión.

**Diseño propuesto para el modo** (a implementar, no hecho):

- Nuevo `Processor` de compresión (p. ej. `processors/compress_proc.py`) o una
  opción "Compress" seleccionable en la GUI junto a "Clean/Unlock".
- PDF: envolver Ghostscript con elección de perfil (`screen`/`ebook`/`printer`)
  y nivel de calidad configurable. Detectar la ruta de `gswin64c.exe` y avisar
  si no está instalado.
- Decidir si la compresión es un modo aparte o una casilla que se combina con la
  limpieza (p. ej. "limpiar y además comprimir").
- Posible extensión a imágenes dentro de Office (recompresión de medios en el
  ZIP) como fase posterior.
- Mostrar en la tabla el tamaño antes/después por archivo.

**Dependencia nueva:** Ghostscript (externo, no pip). Documentar su instalación
o empaquetar su localización.

### 4.2. Otros pendientes

- Compilar y probar el `.exe` real (`build.bat`) en la VM Intune-Lab.
- Probar la GUI de forma interactiva (hasta ahora solo lógica por CLI).
- Probar con un Office **cifrado real** (ruta `msoffcrypto`), no solo docx
  sintético.
- Probar un PDF con contraseña de apertura real (ruta `NEEDS_PASSWORD` +
  descifrado con contraseña correcta).
- Decidir carpeta de salida por defecto y comportamiento ante nombres
  repetidos (ya hay `_unique_dst`, revisar que convence).

---

## 5. Cómo retomar

```bat
cd C:\Users\alexa\Documents\Testeo2.0\DocUnlock
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py            REM GUI

REM compilar:
build.bat                 REM -> dist\DocUnlock.exe
```

Añadir un formato o un modo nuevo = un `Processor` en `processors/` registrado
en `Pipeline` (`core/pipeline.py`).
