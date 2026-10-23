"""DocUnlock window: queue documents, pick what to remove and whether to
compress, run it on a worker thread and watch each file's result."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.detect import detect
from core.options import Options
from core.pipeline import SUPPORTED_EXT, Pipeline
from core.result import FileResult, Status, human_size
from gui import theme
from gui.widgets import (
    ChamferPanel, FlatButton, OptionRow, PrimaryButton, StatusMark, ThemeSwitch, Toggle, TrashButton,
    app_icon,
)
from processors.compress import DEFAULT_PROFILE, PROFILES

_KIND = {
    "pdf": "PDF",
    "docx": "Word",
    "xlsx": "Excel",
    "pptx": "PowerPoint",
    "ole": "Office binario",
    "unknown": "Desconocido",
}

_STATUS = {
    Status.OK: ("Listo", "WHITE"),
    Status.SKIPPED: ("Omitido", "MUTED"),
    Status.ERROR: ("Error", "RED"),
    Status.NEEDS_PASSWORD: ("Falta contraseña", "RED"),
}

_PROFILE_HELP = {
    "screen": "72 ppp · JPEG 50. Lectura en pantalla, envío por correo.",
    "ebook": "150 ppp · JPEG 60. Uso general y escaneos.",
    "printer": "300 ppp · JPEG 80. Calidad de impresión.",
}

_COLS = ("Documento", "Tipo", "Estado", "Tamaño", "Ahorro", "Detalle", "")
_NAME_COL, _KIND_COL, _STATUS_COL, _SIZE_COL, _SAVE_COL, _DETAIL_COL, _TRASH_COL = range(7)
_NUMERIC = (_SIZE_COL, _SAVE_COL)

# Past this width the window adds side margins instead of stretching rows
# of switches and fields across a 27" screen.
_CONTENT_MAX_WIDTH = 1360


class _Ink(QStyledItemDelegate):
    """Paints a column's text in a theme token (read at paint time, so a
    theme switch recolours rows already in the table)."""

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        self._token = token

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.palette.setColor(QPalette.ColorRole.Text, QColor(getattr(theme, self._token)))


class _ElideMiddle(_Ink):
    """File names keep their start and their extension: 'Anexo 7 … firmado.pdf'."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.textElideMode = Qt.TextElideMode.ElideMiddle


class Worker(QObject):
    progress = Signal(int, object)
    failed = Signal(str)
    finished = Signal(list)

    def __init__(self, files, out_dir, password, options):
        super().__init__()
        self._files = files
        self._out = out_dir
        self._pw = password
        self._options = options
        self._index = 0
        self._stop = False

    def cancel(self):
        """Called from the GUI thread; the pipeline reads it between files."""
        self._stop = True

    def _emit(self, result):
        self.progress.emit(self._index, result)
        self._index += 1

    def run(self):
        try:
            results = Pipeline().run(
                [], self._out, self._pw, progress=self._emit,
                options=self._options, files=self._files,
                cancelled=lambda: self._stop,
            )
        except Exception as exc:  # e.g. output folder not writable
            self.failed.emit(str(exc))
            results = []
        self.finished.emit(results)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocUnlock")
        self.setWindowIcon(app_icon())
        self.resize(1180, 880)
        self.setMinimumSize(960, 700)
        self.setAcceptDrops(True)
        self._paths: list[Path] = []
        self._queue: list[tuple[Path, Path]] = []
        self._removed: set[Path] = set()  # files taken out of a dropped folder
        self._results: dict[str, FileResult] = {}  # source path -> last result
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._busy = False
        self._cancelling = False
        self._build()
        self._update_state()

    # -- layout ------------------------------------------------------------
    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 20)
        outer.setSpacing(0)
        content = QWidget()
        content.setMaximumWidth(_CONTENT_MAX_WIDTH)
        outer.addStretch(1)
        outer.addWidget(content, 100)
        outer.addStretch(1)

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        root.addLayout(self._build_header())
        root.addWidget(self._build_drop())

        panels = QHBoxLayout()
        panels.setSpacing(18)
        panels.addWidget(self._build_clean(), 3)
        panels.addWidget(self._build_compress(), 2)
        root.addLayout(panels)

        root.addLayout(self._build_fields())
        root.addWidget(self._build_table(), 1)
        root.addLayout(self._build_footer())

    def _build_header(self):
        title = QLabel("DocUnlock")
        title.setObjectName("title")
        tagline = QLabel("Limpia y comprime documentos en este equipo. Nada sale de él.")
        tagline.setObjectName("tagline")
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(30, 30))
        mark.setFixedSize(30, 30)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(10)
        row.addWidget(tagline, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        self.theme_switch = ThemeSwitch()
        self.theme_switch.changed.connect(self._set_theme)
        row.addWidget(self.theme_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _set_theme(self, mode: str) -> None:
        theme.apply(mode)
        QApplication.instance().setStyleSheet(theme.qss())
        _title_bar(self)
        for w in self.findChildren(QWidget):
            w.update()

    def _build_drop(self):
        self.drop = ChamferPanel(fill="BLACK")
        self.drop.set_look("BLACK", "LINE", dashed=True)
        self.drop.setMinimumHeight(120)

        self.drop_main = QLabel()
        self.drop_main.setObjectName("dropMain")
        self.drop_sub = QLabel()
        self.drop_sub.setObjectName("dropSub")

        self.btn_files = FlatButton("Añadir archivos")
        self.btn_folder = FlatButton("Añadir carpeta")
        self.btn_clear = FlatButton("Vaciar")
        self.btn_files.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._add_folder)
        self.btn_clear.clicked.connect(self._clear)

        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(self.drop_main)
        text.addWidget(self.drop_sub)

        lay = QHBoxLayout(self.drop)
        lay.setContentsMargins(28, 18, 28, 18)
        lay.setSpacing(10)
        lay.addLayout(text, 1)
        for b in (self.btn_files, self.btn_folder, self.btn_clear):
            b.setStyleSheet("background: transparent;")
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return self.drop

    def _panel(self, title: str, note: str = "", extra: QWidget | None = None):
        panel = ChamferPanel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("panelTitle")
        head.addWidget(t)
        head.addStretch()
        if note:
            n = QLabel(note)
            n.setObjectName("panelNote")
            head.addWidget(n)
        if extra is not None:
            head.addWidget(extra, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)
        return panel, lay

    def _master_switch(self) -> QWidget:
        """'Todo' switch in the Limpiar header: one click turns the four
        cleaning steps on or off; it follows them when they change one by one."""
        box = QWidget()
        box.setObjectName("masterSwitch")
        box.setStyleSheet("#masterSwitch, #masterSwitch QLabel { background: transparent; }")
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        label = QLabel("Todo")
        label.setObjectName("fieldLabel")
        self.clean_all = Toggle(True)
        self.clean_all.setToolTip("Activar o desactivar las cuatro opciones de limpieza")
        # clicked, not toggled: only a user click fans out; syncing from
        # _update_state uses setChecked and must not loop back.
        self.clean_all.clicked.connect(self._set_all_clean)
        row.addWidget(label)
        row.addWidget(self.clean_all)
        return box

    def _set_all_clean(self, on: bool) -> None:
        for o in self._clean_opts:
            o.setChecked(on)
        self._update_state()

    def _build_clean(self):
        panel, lay = self._panel("Limpiar", extra=self._master_switch())
        self.opt_meta = OptionRow("Metadatos", "Autor, empresa, fechas, revisiones.")
        self.opt_sign = OptionRow("Firmas digitales", "PDF. La copia pierde la firma.")
        self.opt_prot = OptionRow("Protección de edición", "Solo lectura, hojas y libros (Office).")
        self.opt_pass = OptionRow("Contraseñas y permisos", "Apertura y permisos PDF.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(4)
        top = Qt.AlignmentFlag.AlignTop  # a wrapped description must not shift its neighbour
        grid.addWidget(self.opt_meta, 0, 0, top)
        grid.addWidget(self.opt_sign, 0, 1, top)
        grid.addWidget(self.opt_prot, 1, 0, top)
        grid.addWidget(self.opt_pass, 1, 1, top)
        self._clean_opts = (self.opt_meta, self.opt_sign, self.opt_prot, self.opt_pass)
        for o in self._clean_opts:
            o.toggled.connect(self._update_state)
        lay.addLayout(grid)
        lay.addStretch()
        return panel

    def _build_compress(self):
        panel, lay = self._panel("Comprimir")
        self.opt_comp = OptionRow(
            "Reducir tamaño",
            "Imágenes y fuentes incrustadas. Tras limpiar.",
            checked=False,
        )
        self.opt_comp.toggled.connect(self._update_state)
        lay.addWidget(self.opt_comp)

        seg = QHBoxLayout()
        seg.setSpacing(0)
        seg.setContentsMargins(50, 4, 0, 0)
        self.seg_group = QButtonGroup(self)
        self.seg_group.setExclusive(True)
        self.seg_buttons: dict[str, QPushButton] = {}
        for key, prof in PROFILES.items():
            b = FlatButton(prof.label.capitalize())
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(key == DEFAULT_PROFILE)
            self.seg_group.addButton(b)
            self.seg_buttons[key] = b
            b.toggled.connect(self._update_state)
            seg.addWidget(b)
        seg.addStretch()
        lay.addLayout(seg)

        self.profile_help = QLabel()
        self.profile_help.setObjectName("optDesc")
        self.profile_help.setContentsMargins(50, 4, 0, 0)
        self.profile_help.setWordWrap(True)
        lay.addWidget(self.profile_help)

        lay.addStretch()
        return panel

    def _build_fields(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)

        l1 = QLabel("Contraseña de los documentos cifrados")
        l1.setObjectName("fieldLabel")
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("Solo si alguno pide contraseña para abrirse")
        self.pw_show = QCheckBox("Ver")
        self.pw_show.setObjectName("pwShow")
        self.pw_show.toggled.connect(
            lambda on: self.pw_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        pw = QHBoxLayout()
        pw.setSpacing(10)
        pw.addWidget(self.pw_edit, 1)
        pw.addWidget(self.pw_show)

        l2 = QLabel("Guardar en")
        l2.setObjectName("fieldLabel")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Carpeta DocUnlock_out junto al primer documento")
        self.btn_out = FlatButton("Elegir…")
        self.btn_out.clicked.connect(self._pick_out)
        out = QHBoxLayout()
        out.setSpacing(10)
        out.addWidget(self.out_edit, 1)
        out.addWidget(self.btn_out)

        grid.addWidget(l1, 0, 0)
        grid.addWidget(l2, 0, 1)
        grid.addLayout(pw, 1, 0)
        grid.addLayout(out, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return grid

    def _build_table(self):
        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(list(_COLS))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setItemDelegateForColumn(_NAME_COL, _ElideMiddle("WHITE", self.table))
        for col in (_KIND_COL, _DETAIL_COL):
            self.table.setItemDelegateForColumn(col, _Ink("MUTED", self.table))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.cellDoubleClicked.connect(self._open_row)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setMinimumSectionSize(40)
        widths = {_KIND_COL: 104, _STATUS_COL: 150, _SIZE_COL: 180, _SAVE_COL: 84, _TRASH_COL: 44}
        for col in range(len(_COLS)):
            if col in widths:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, widths[col])
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for col in _NUMERIC:
            self.table.horizontalHeaderItem(col).setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

        empty = QLabel("Cola vacía. Arrastra documentos o carpetas a la zona de arriba.")
        empty.setObjectName("emptyQueue")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(empty)
        self.table_stack.addWidget(self.table)
        return self.table_stack

    def _build_footer(self):
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)

        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.btn_open = FlatButton("Abrir carpeta de salida")
        self.btn_open.clicked.connect(self._open_out)
        self.btn_run = PrimaryButton("Procesar")
        self.btn_run.clicked.connect(self._run_or_cancel)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self.summary, 1)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_run)

        col = QVBoxLayout()
        col.setSpacing(14)
        col.addWidget(self.bar)
        col.addLayout(row)
        return col

    # -- state -------------------------------------------------------------
    def _options(self) -> Options:
        profile = None
        if self.opt_comp.isChecked():
            profile = next(
                (k for k, b in self.seg_buttons.items() if b.isChecked()), DEFAULT_PROFILE
            )
        return Options(
            metadata=self.opt_meta.isChecked(),
            signatures=self.opt_sign.isChecked(),
            protection=self.opt_prot.isChecked(),
            passwords=self.opt_pass.isChecked(),
            compress=profile,
        )

    def _update_state(self, *_):
        comp_on = self.opt_comp.isChecked()
        for b in self.seg_buttons.values():
            b.setEnabled(comp_on and not self._busy)
        key = next((k for k, b in self.seg_buttons.items() if b.isChecked()), DEFAULT_PROFILE)
        self.profile_help.setText(_PROFILE_HELP[key] if comp_on else "")

        n = len(self._queue)
        if n:
            size = sum(f.stat().st_size for f, _ in self._queue if f.exists())
            self.drop_main.setText(
                f"{n} documento{'s' if n != 1 else ''} en cola, {human_size(size)}"
            )
            self.drop_sub.setText("Suelta más para añadir.")
        else:
            self.drop_main.setText("Arrastra aquí documentos o carpetas")
            self.drop_sub.setText("PDF, Word, Excel y PowerPoint. Los originales no se modifican.")
        self.btn_clear.setVisible(bool(n))
        self.btn_open.setEnabled(bool(self._paths) and self._out_dir().is_dir())

        opts = self._options()
        # While a batch runs the main button turns into Cancelar.
        self.btn_run.setText("Cancelar" if self._busy else "Procesar")
        if self._busy:
            self.btn_run.setEnabled(not self._cancelling)
        else:
            self.btn_run.setEnabled(bool(n) and opts.anything)
        for w in (self.btn_files, self.btn_folder, self.btn_clear, self.opt_meta,
                  self.opt_sign, self.opt_prot, self.opt_pass, self.opt_comp,
                  self.clean_all):
            w.setEnabled(not self._busy)
        for r in range(self.table.rowCount()):
            cell = self.table.cellWidget(r, _TRASH_COL)
            if cell is not None:
                cell.setVisible(not self._busy)
        self.table_stack.setCurrentIndex(1 if self.table.rowCount() else 0)
        self.clean_all.setChecked(all(o.isChecked() for o in self._clean_opts))

        if self._busy:
            return
        if not n:
            self.summary.setText("Cola vacía.")
        elif not opts.anything:
            self.summary.setText("Sin operaciones: activa Limpiar o Comprimir.")
        elif self.summary.property("done") is not True:
            self.summary.setText(self._plan_text(opts))

    @staticmethod
    def _plan_text(opts: Options) -> str:
        parts = [
            name for on, name in (
                (opts.metadata, "metadatos"),
                (opts.signatures, "firmas"),
                (opts.protection, "protección"),
                (opts.passwords, "contraseñas"),
            ) if on
        ]
        text = "Limpiar: " + (" · ".join(parts) if parts else "—")
        if opts.compress:
            prof = PROFILES[opts.compress]
            text += f"   |   Comprimir: {prof.label}, {prof.pdf_dpi} ppp, JPEG {prof.pdf_quality}"
        return text

    # -- drag & drop -------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self._busy:
            event.acceptProposedAction()
            self.drop.set_look("RED_DEEP", "RED")

    def dragLeaveEvent(self, _event):
        self.drop.set_look("BLACK", "LINE", dashed=True)

    def dropEvent(self, event):
        self.drop.set_look("BLACK", "LINE", dashed=True)
        dropped = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        self._add([p for p in dropped if p.is_dir() or p.suffix.lower() in SUPPORTED_EXT])

    # -- queue -------------------------------------------------------------
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Elegir documentos", "",
            "Documentos (*.pdf *.docx *.xlsx *.xlsm *.pptx *.doc *.xls *.ppt)",
        )
        self._add([Path(f) for f in files])

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta")
        if folder:
            self._add([Path(folder)])

    def _add(self, paths: list[Path]):
        for p in paths:
            self._removed.discard(p)  # adding it again brings it back
            if p not in self._paths:
                self._paths.append(p)
        self._queue = self._gather()
        self.summary.setProperty("done", False)
        self._fill_queue()
        self._update_state()

    def _gather(self, exclude: Path | None = None) -> list[tuple[Path, Path]]:
        files = Pipeline().gather(self._paths, exclude=exclude)
        return [(f, rel) for f, rel in files if f not in self._removed]

    def _remove(self, path: Path):
        """Trash button on a row: drop that file from the queue. A file
        added on its own leaves the list; one found inside an added folder
        is remembered as excluded so the next gather skips it."""
        if self._busy:
            return
        if path in self._paths:
            self._paths.remove(path)
        else:
            self._removed.add(path)
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == str(path):
                self.table.removeRow(r)
                break
        self._queue = [(f, rel) for f, rel in self._queue if f != path]
        if not self._queue:
            self._paths.clear()
            self._removed.clear()
        self._update_state()

    def _clear(self):
        self._paths.clear()
        self._removed.clear()
        self._queue.clear()
        self.table.setRowCount(0)
        self.bar.setValue(0)
        self.summary.setProperty("done", False)
        self._update_state()

    def _fill_queue(self):
        self.table.setRowCount(0)
        self._results.clear()
        for f, rel in self._queue:
            r = self.table.rowCount()
            self.table.insertRow(r)
            folder = str(rel.parent) if str(rel.parent) != "." else ""
            self._set_row(r, f.name, _KIND.get(detect(f), ""), ("En cola", "MUTED"),
                          human_size(f.stat().st_size), "", folder)
            name = self.table.item(r, _NAME_COL)
            name.setData(Qt.ItemDataRole.UserRole, str(f))
            name.setToolTip(str(f))
            trash = TrashButton()
            trash.clicked.connect(lambda _=False, p=f: self._remove(p))
            cell = QWidget()
            lay = QHBoxLayout(cell)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(trash, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(r, _TRASH_COL, cell)

    def _pick_out(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de salida")
        if folder:
            self.out_edit.setText(folder)

    def _default_out(self) -> Path:
        base = self._paths[0]
        anchor = base if base.is_dir() else base.parent
        return anchor / "DocUnlock_out"

    def _out_dir(self) -> Path:
        text = self.out_edit.text().strip()
        return Path(text) if text else self._default_out()

    def _open_out(self):
        out = self._out_dir() if self._paths else None
        if out is not None and out.is_dir():
            os.startfile(out)  # Windows Explorer

    def _open_row(self, r: int, _col: int):
        """Double click: open the cleaned copy, or show the full error."""
        item = self.table.item(r, _NAME_COL)
        result = self._results.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        if result is None:
            return
        if result.status is Status.OK and result.output and result.output.exists():
            os.startfile(result.output)
            return
        box = QMessageBox(self)
        box.setWindowTitle(_STATUS[result.status][0])
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(result.source.name)
        box.setInformativeText(result.message or result.actions_text or "Sin detalle")
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()

    # -- run ---------------------------------------------------------------
    def _run_or_cancel(self):
        if self._busy:
            self._cancel()
        else:
            self._start()

    def _cancel(self):
        if self._worker is None or self._cancelling:
            return
        self._cancelling = True
        self._worker.cancel()
        self.summary.setText("Cancelando: termina el documento en curso…")
        self._update_state()

    def _start(self):
        if not self._queue or self._busy:
            return
        out = self._out_dir()
        self.out_edit.setText(str(out))
        files = self._gather(exclude=out)
        self._queue = files
        self._fill_queue()

        self._busy = True
        self._mark_running(0)
        self._update_state()
        self.bar.setRange(0, max(len(files), 1))
        self.bar.setValue(0)
        self.summary.setText(f"Procesando 0/{len(files)}…")

        thread = QThread()
        self._worker = Worker(files, out, self.pw_edit.text() or None, self._options())
        self._worker.moveToThread(thread)
        thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)
        self._thread = thread
        thread.start()

    def _on_progress(self, index: int, result: FileResult):
        label = _STATUS[result.status]
        before, after = result.size_before, result.size_after
        size, saving = human_size(before) if before else "", ""
        if result.status is Status.OK and after:
            size = f"{human_size(before)} → {human_size(after)}"
            pct = round(100 * (before - after) / before) if before else 0
            saving = f"-{pct} %" if pct >= 1 else "—"
        self._set_row(
            index, result.source.name, _KIND.get(result.kind, result.kind), label,
            size, saving, result.message or result.actions_text,
        )
        self._results[str(result.source)] = result
        name = self.table.item(index, _NAME_COL)
        if name is not None:
            hint = "abrir la copia" if result.status is Status.OK else "ver el detalle"
            name.setToolTip(f"{result.source}\nDoble clic: {hint}")
        self.bar.setValue(index + 1)
        if self._cancelling:
            return
        self._mark_running(index + 1)
        self.summary.setText(f"Procesando {index + 1}/{len(self._queue)}…")

    def _mark_running(self, r: int):
        if r < self.table.rowCount():
            self.table.setCellWidget(
                r, _STATUS_COL, StatusMark("WHITE", "Procesando", dot="RED")
            )
            self.table.scrollToItem(self.table.item(r, _NAME_COL))

    def _on_failed(self, message: str):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_row(r, "—", "", ("Error", "RED"), "", "", message)

    def _on_finished(self, results: list[FileResult]):
        self._busy = False
        cancelled, self._cancelling = self._cancelling, False
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None
        pending = len(self._queue) - len(results)
        if cancelled:
            for r in range(len(results), len(self._queue)):
                self.table.setCellWidget(r, _STATUS_COL, StatusMark("MUTED", "Cancelado"))

        ok = [r for r in results if r.status is Status.OK]
        need_pw = sum(1 for r in results if r.status is Status.NEEDS_PASSWORD)
        errors = sum(1 for r in results if r.status is Status.ERROR)
        before = sum(r.size_before for r in ok)
        after = sum(r.size_after for r in ok)
        parts = [f"OK {len(ok)}/{len(results)}"]
        if before and after and after < before:
            pct = round(100 * (before - after) / before)
            parts.append(f"{human_size(before)} → {human_size(after)} (-{pct} %)")
        if need_pw:
            parts.append(f"{need_pw} sin contraseña")
        if errors:
            parts.append(f"{errors} error{'es' if errors != 1 else ''}")
        if cancelled and pending > 0:
            parts.append(f"cancelado, {pending} sin procesar")
        self.summary.setText(" · ".join(parts))
        self.summary.setProperty("done", True)
        self._update_state()

    # -- table -------------------------------------------------------------
    def _set_row(self, r, name, kind, status, size, saving, detail):
        text, color = status
        cells = {_NAME_COL: name, _KIND_COL: kind, _STATUS_COL: "",
                 _SIZE_COL: size, _SAVE_COL: saving, _DETAIL_COL: detail}
        old = self.table.item(r, _NAME_COL)
        key = old.data(Qt.ItemDataRole.UserRole) if old is not None else None
        for c, value in cells.items():
            item = QTableWidgetItem(value)
            if c == _NAME_COL:
                if key is not None:
                    item.setData(Qt.ItemDataRole.UserRole, key)  # keep the row's file
                    item.setToolTip(key)
            elif c in (_KIND_COL, _DETAIL_COL):
                item.setToolTip(value)
            if c in _NUMERIC:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, c, item)
        self.table.setCellWidget(r, _STATUS_COL, StatusMark(color, text))


def _title_bar(win: QWidget) -> None:
    """Windows 11 title bar in the theme's background colour (DWM).
    Cosmetic: ignored where unsupported."""
    try:
        import ctypes

        hwnd = int(win.winId())
        dark = ctypes.c_int(1 if theme.MODE == "dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        r, g, b = (int(theme.BLACK[i:i + 2], 16) for i in (1, 3, 5))
        caption = ctypes.c_int(r | g << 8 | b << 16)  # COLORREF is 0x00BBGGRR
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def main():
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(theme.qss())
    app.setWindowIcon(app_icon())
    win = MainWindow()
    _title_bar(win)
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
