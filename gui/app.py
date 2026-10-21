"""Minimal PySide6 GUI: pick files/folder, run, watch progress."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.pipeline import Pipeline
from core.result import FileResult, Status

_STATUS_COLOR = {
    Status.OK: "#2e7d32",
    Status.SKIPPED: "#8a6d00",
    Status.ERROR: "#c62828",
    Status.NEEDS_PASSWORD: "#1565c0",
}


def _as_status(value: str) -> Status | None:
    try:
        return Status(value)
    except ValueError:
        return None


class Worker(QObject):
    progress = Signal(object)
    finished = Signal(list)

    def __init__(self, paths, out_dir, password):
        super().__init__()
        self._paths = paths
        self._out = out_dir
        self._pw = password

    def run(self):
        pipeline = Pipeline()
        results = pipeline.run(
            self._paths, self._out, self._pw, progress=self.progress.emit
        )
        self.finished.emit(results)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocUnlock")
        self.resize(820, 520)
        self._paths: list[Path] = []
        self._thread: QThread | None = None
        self._build()

    # -- layout ------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)

        pick = QHBoxLayout()
        self.btn_files = QPushButton("Add files")
        self.btn_folder = QPushButton("Add folder")
        self.btn_clear = QPushButton("Clear")
        self.btn_files.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._add_folder)
        self.btn_clear.clicked.connect(self._clear)
        pick.addWidget(self.btn_files)
        pick.addWidget(self.btn_folder)
        pick.addWidget(self.btn_clear)
        pick.addStretch()
        root.addLayout(pick)

        out = QHBoxLayout()
        out.addWidget(QLabel("Output:"))
        self.out_edit = QLineEdit()
        self.btn_out = QPushButton("...")
        self.btn_out.setFixedWidth(36)
        self.btn_out.clicked.connect(self._pick_out)
        out.addWidget(self.out_edit)
        out.addWidget(self.btn_out)
        root.addLayout(out)

        pw = QHBoxLayout()
        pw.addWidget(QLabel("Password (optional):"))
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("tu contrasena, para archivos cifrados")
        self.pw_show = QCheckBox("Show")
        self.pw_show.toggled.connect(
            lambda on: self.pw_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        pw.addWidget(self.pw_edit)
        pw.addWidget(self.pw_show)
        root.addLayout(pw)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Status", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.btn_run = QPushButton("Process")
        self.btn_run.clicked.connect(self._start)
        bottom.addWidget(self.bar, 1)
        bottom.addWidget(self.btn_run)
        root.addLayout(bottom)

    # -- actions -----------------------------------------------------------
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select documents", "",
            "Documents (*.pdf *.docx *.xlsx *.xlsm *.pptx *.doc *.xls *.ppt)",
        )
        self._add([Path(f) for f in files])

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            self._add([Path(folder)])

    def _add(self, paths: list[Path]):
        for p in paths:
            if p not in self._paths:
                self._paths.append(p)
        self._refresh_list()

    def _clear(self):
        self._paths.clear()
        self.table.setRowCount(0)

    def _refresh_list(self):
        self.table.setRowCount(0)
        for p in self._paths:
            self._row(p.name, "", "pending", str(p))

    def _pick_out(self):
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder:
            self.out_edit.setText(folder)

    def _default_out(self) -> Path:
        base = self._paths[0]
        anchor = base if base.is_dir() else base.parent
        return anchor / "DocUnlock_out"

    def _start(self):
        if not self._paths:
            return
        out = Path(self.out_edit.text()) if self.out_edit.text() else self._default_out()
        self.out_edit.setText(str(out))
        self.table.setRowCount(0)
        self.bar.setRange(0, 0)  # busy
        self.btn_run.setEnabled(False)

        thread = QThread()
        self._worker = Worker(list(self._paths), out, self.pw_edit.text() or None)
        self._worker.moveToThread(thread)
        thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread = thread
        thread.start()

    def _on_progress(self, result: FileResult):
        self._row(
            result.source.name, result.kind, result.status.value,
            result.message or result.actions_text,
        )

    def _on_finished(self, _results: list[FileResult]):
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.btn_run.setEnabled(True)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None

    def _row(self, name, kind, status, detail):
        r = self.table.rowCount()
        self.table.insertRow(r)
        items = [
            QTableWidgetItem(name),
            QTableWidgetItem(kind),
            QTableWidgetItem(status),
            QTableWidgetItem(detail),
        ]
        st = _as_status(status)
        if st is not None:
            items[2].setForeground(QColor(_STATUS_COLOR[st]))
        items[3].setToolTip(detail)
        for c, it in enumerate(items):
            self.table.setItem(r, c, it)


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
