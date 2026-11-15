from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QProgressBar, QPushButton, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import data, gsi, recommend, vision, winutil
from .overlay import Overlay

if getattr(sys, "frozen", False):
    DEBUG_DIR = Path(sys.executable).resolve().parent / "debug"
else:
    DEBUG_DIR = Path(__file__).resolve().parent.parent / "debug"

STYLE = """
* { font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog, QWidget { background: #14171c; color: #dfe3ea; }
QLabel#h { color: #8f98a8; font-size: 9pt; font-weight: 600; letter-spacing: 1px; }
QLabel#hint { color: #7c8594; font-size: 9pt; }
QLabel#ok { color: #4cd07d; font-size: 9pt; font-weight: 600; }
QLabel#err { color: #e2665b; font-size: 9pt; }
QLabel#info { color: #aab2c0; background: #181c22; border: 1px solid #2c333e; border-radius: 4px; padding: 10px; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background: #1e232b; border: 1px solid #2c333e;
  border-radius: 4px; padding: 4px 8px; min-height: 20px; }
QComboBox:disabled { color: #5a6270; border-color: #20252d; }
QComboBox#pos {font-size: 8pt; padding: 1px 4px; min-height: 16px; }
QComboBox#pos:disabled { color: #3a424f; border-color: #20252d; }
QComboBox QAbstractItemView { background: #1e232b; selection-background-color: #2f6fed; }
QPushButton { background: #232a34; border: 1px solid #323a47; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { background: #2c3541; }
QPushButton:checked { background: #2f6fed; border-color: #2f6fed; color: white; }
QPushButton:disabled { color: #3f4753; background: #191d23; border-color: #232932; }
QPushButton#slot {background: #1a1e25; border: 1px dashed #333b48; padding: 0; }
QPushButton#slot:hover { border-color: #c0392b; }
QPushButton#seg { padding: 4px 10px; }
QListWidget#pool::item { border: 2px solid transparent; border-radius: 3px; padding: 2px; }
QListWidget#pool::item:selected { border-color: #4cd07d; background: #1f3a2b; }
QListWidget { background: #181c22; border: 1px solid #2c333e; border-radius: 4px; }
QTableWidget { background: #181c22; border: 1px solid #2c333e; gridline-color: #232932;
  alternate-background-color: #1b2027; }
QHeaderView::section { background: #1e232b; color: #8f98a8; border: none; padding: 5px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #1e232b; padding: 7px 16px; margin-right: 2px; border-radius: 4px 4px 0 0; }
QTabBar::tab:selected { background: #2f6fed; color: white; }
QProgressBar { background: #1e232b; border: none; height: 6px; border-radius: 3px; }
QProgressBar::chunk { background: #2f6fed; border-radius: 3px; }
QCheckBox { spacing: 6px; }
"""

POS_SHORT = ["Role", "1 · Carry", "2 · Mid", "3 · Off", "4 · Soft", "5 · Hard"]
SLOT = QSize(88, 50)
BAN_SLOT = QSize(50, 28)


class _Sig(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)


class Task(QRunnable):
    def __init__(self, fn, with_progress=False):
        super().__init__()
        self.fn, self.sig, self.with_progress = fn, _Sig(), with_progress

    def run(self):
        try:
            res = self.fn(self.sig.progress.emit) if self.with_progress else self.fn()
            self.sig.done.emit(res)
        except data.DataError as e:
            self.sig.error.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.sig.error.emit(f"Error: {e}")


class NumItem(QTableWidgetItem):
    def __lt__(self, other):
        return (self.data(Qt.UserRole) or 0) < (other.data(Qt.UserRole) or 0)


class TeamRow(QWidget):
    removed = Signal(int)
    pos_changed = Signal(int, int)

    def __init__(self, n: int, size: QSize, per_row: int = 5, with_pos: bool = False):
        super().__init__()
        self.buttons, self.combos = [], []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = None
        for i in range(n):
            if i % per_row == 0:
                if row is not None:
                    row.addStretch(1)
                row = QHBoxLayout()
                row.setSpacing(4)
                lay.addLayout(row)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            b = QPushButton()
            b.setObjectName("slot")
            b.setFixedSize(size)
            b.setIconSize(size - QSize(4, 4))
            b.clicked.connect(lambda _=False, idx=i: self.removed.emit(idx))
            cell.addWidget(b)
            self.buttons.append(b)
            if with_pos:
                c = QComboBox()
                c.setObjectName("pos")
                c.addItems(POS_SHORT)
                c.setFixedWidth(size.width())
                c.setEnabled(False)
                c.setToolTip("Position of this hero (optional)")
                c.currentIndexChanged.connect(lambda p, idx=i: self.pos_changed.emit(idx, p))
                cell.addWidget(c)
                self.combos.append(c)
            row.addLayout(cell)
        if row is not None:
            row.addStretch(1)

    def set(self, ids: list[int], icons: dict, names: dict, pos: dict | None = None):
        for i, b in enumerate(self.buttons):
            filled = i < len(ids)
            b.setIcon(icons.get(ids[i], QIcon()) if filled else QIcon())
            b.setToolTip(f"{names.get(ids[i], '?')} — click to remove" if filled else "")
            if self.combos:
                c = self.combos[i]
                c.blockSignals(True)
                c.setCurrentIndex((pos or {}).get(ids[i], 0) if filled else 0)
                c.setEnabled(filled)
                c.blockSignals(False)


class TokenDialog(QDialog):

    def __init__(self, parent, token: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Connect Stratz")
        self.setMinimumWidth(440)
        v = QVBoxLayout(self)
        v.setSpacing(10)
        info = QLabel(
            "Stratz statistics need your personal API token (free):<br><br>"
            "1. Open <a style='color:#6ea0ff' href='https://stratz.com/api'>stratz.com/api</a> "
            "and sign in with Steam.<br>"
            "2. Copy the token shown under <b>My Tokens</b>.<br>"
            "3. Paste it below and press OK.")
        info.setObjectName("info")
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        v.addWidget(info)
        self.edit = QLineEdit(token)
        self.edit.setPlaceholderText("Paste token here")
        self.edit.setEchoMode(QLineEdit.Password)
        v.addWidget(self.edit)
        self.msg = QLabel("")
        self.msg.setObjectName("err")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._check)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _check(self):
        self.msg.setText("Checking…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            ok, text = data.check_stratz_token(self.edit.text())
        finally:
            QApplication.restoreOverrideCursor()
        if ok:
            self.accept()
        else:
            self.msg.setText(text)

    def token(self) -> str:
        return self.edit.text().strip()


class PoolDialog(QDialog):

    def __init__(self, parent, heroes: list[dict], icons: dict, pool: set[int]):
        super().__init__(parent)
        self.setWindowTitle("My hero pool")
        self.resize(640, 560)
        v = QVBoxLayout(self)
        hint = QLabel("Click the heroes you play. With “My pool only” on, picks are suggested only from them.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search hero…")
        self.search.textChanged.connect(self._filter)
        v.addWidget(self.search)
        self.grid = QListWidget()
        self.grid.setObjectName("pool")
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setSelectionMode(QListWidget.MultiSelection)
        self.grid.setIconSize(QSize(64, 36))
        self.grid.setSpacing(3)
        self.grid.setUniformItemSizes(True)
        for h in heroes:
            it = QListWidgetItem(icons.get(h["id"], QIcon()), "")
            it.setToolTip(h["name"])
            it.setData(Qt.UserRole, h["id"])
            it.setSizeHint(QSize(72, 44))
            self.grid.addItem(it)
            it.setSelected(h["id"] in pool)
        self.grid.itemSelectionChanged.connect(self._count)
        v.addWidget(self.grid, 1)
        row = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("hint")
        row.addWidget(self.count, 1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.grid.clearSelection)
        row.addWidget(clear)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)
        self._count()

    def _filter(self, text):
        t = text.strip().lower()
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            it.setHidden(bool(t) and t not in it.toolTip().lower())

    def _count(self):
        n = len(self.grid.selectedItems())
        self.count.setText(f"{n} hero{'es' if n != 1 else ''} in pool")

    def pool(self) -> list[int]:
        return sorted(it.data(Qt.UserRole) for it in self.grid.selectedItems())


class SettingsDialog(QDialog):
    def __init__(self, parent, s: dict, connected: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self.new_token: str | None = None
        self._token = s.get("stratz_token", "")
        form = QFormLayout(self)
        row = QHBoxLayout()
        self.tok_state = QLabel()
        row.addWidget(self.tok_state, 1)
        ch = QPushButton("Change token…")
        ch.clicked.connect(self._change_token)
        row.addWidget(ch)
        form.addRow("Stratz token", row)
        self._show_token_state(bool(self._token) and s.get("stratz_ok", False))
        grow = QHBoxLayout()
        self.gsi_state = QLabel()
        grow.addWidget(self.gsi_state, 1)
        self.gsi_btn = QPushButton("Install")
        self.gsi_btn.clicked.connect(self._install_gsi)
        grow.addWidget(self.gsi_btn)
        form.addRow("Game link", grow)
        ghint = QLabel(
            "The game link (Valve's official Game State Integration) lets Dota tell this app when "
            "a match is in the pick stage. Install it, then in Steam open Dota 2 → Properties → "
            f"Launch Options, add  {gsi.LAUNCH_OPTION}  and restart Dota. "
            "Dota sends nothing while you are in the main menu.")
        ghint.setObjectName("hint")
        ghint.setWordWrap(True)
        ghint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(ghint)
        self.cfg_dir = gsi.find_cfg_dir()
        self._link = connected if callable(connected) else (lambda: "off")
        self._show_gsi_state()
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._show_gsi_state)
        self._poll.start(1000)
        self.thr = QSpinBox()
        self.thr.setRange(50, 95)
        self.thr.setSuffix(" %")
        self.thr.setValue(s.get("thr2", 70))
        form.addRow("Match threshold", self.thr)
        self.debug = QCheckBox("Save game screenshots while reading (for tuning detection)")
        self.debug.setChecked(s.get("debug_shots", False))
        self.debug.setToolTip(f"Keeps the last 12 screenshots of the Dota window in:\n{DEBUG_DIR}")
        form.addRow(self.debug)
        hint = QLabel("A lower threshold finds more heroes but makes more mistakes.\n"
                      "The token is stored only on this computer.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _show_token_state(self, ok: bool):
        self.tok_state.setObjectName("ok" if ok else "hint")
        self.tok_state.setText("● Connected" if ok else "Not connected")
        self.tok_state.style().unpolish(self.tok_state)
        self.tok_state.style().polish(self.tok_state)

    def _change_token(self):
        d = TokenDialog(self, self._token)
        if d.exec():
            self._token = self.new_token = d.token()
            self._show_token_state(True)

    def _show_gsi_state(self):
        installed = gsi.is_installed(self.cfg_dir)
        link = self._link()
        if link == "live":
            text, ok = "● Connected — match in progress", True
        elif link == "ready":
            text, ok = "● Ready — Dota reports only during a match", True
        elif installed:
            text, ok = "Installed — turns green when a match starts", False
        else:
            text, ok = "Not installed", False
        if text == self.gsi_state.text():
            return
        self.gsi_btn.setText("Reinstall" if installed else "Install")
        self.gsi_state.setObjectName("ok" if ok else "hint")
        self.gsi_state.setText(text)
        self.gsi_state.style().unpolish(self.gsi_state)
        self.gsi_state.style().polish(self.gsi_state)

    def _install_gsi(self):
        cfg = self.cfg_dir
        if cfg is None:
            picked = QFileDialog.getExistingDirectory(
                self, "Select the Dota 2 folder “dota 2 beta\\game\\dota\\cfg”")
            if not picked:
                return
            cfg = Path(picked)
        try:
            gsi.install(cfg)
        except Exception as e:
            self.gsi_state.setObjectName("err")
            self.gsi_state.setText(f"Could not write the file: {e}")
            self.gsi_state.style().unpolish(self.gsi_state)
            self.gsi_state.style().polish(self.gsi_state)
            return
        self.cfg_dir = cfg
        self._show_gsi_state()

    def values(self) -> dict:
        v = {"thr2": self.thr.value(), "debug_shots": self.debug.isChecked()}
        if self.new_token is not None:
            v.update(stratz_token=self.new_token, stratz_ok=True)
        return v


class SetupDialog(QDialog):

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Setup")
        self.setMinimumWidth(620)
        self.cfg_dir = gsi.find_cfg_dir()
        self.auto_note = ""
        if self.cfg_dir and not gsi.is_installed(self.cfg_dir):
            try:
                gsi.install(self.cfg_dir)
                self.auto_note = " (installed just now)"
            except Exception:
                pass
        self.launch_opt = gsi.launch_option_set()
        self._ticks = 0

        v = QVBoxLayout(self)
        v.setSpacing(10)
        intro = QLabel("Everything the program needs to read your drafts. Green items are done; "
                       "the others say what to do. You can reopen this window with the Setup button.")
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.rows = {}
        for key, title in [("stats", "Hero statistics and images"),
                           ("link", "Game link file in the Dota 2 folder"),
                           ("option", "Dota 2 launch option"),
                           ("signal", "Signal from the game"),
                           ("window", "Game window"),
                           ("stratz", "Stratz statistics (optional)")]:
            self.rows[key] = self._row(v, title)
        self.rows["link"][2].setText("Install")
        self.rows["link"][2].clicked.connect(self._install_link)
        self.rows["option"][2].setText("Copy option")
        self.rows["option"][2].clicked.connect(self._copy_option)
        self.rows["stratz"][2].setText("Connect…")
        self.rows["stratz"][2].clicked.connect(self._stratz)
        for key in ("stats", "signal", "window"):
            self.rows[key][2].hide()
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        v.addWidget(bb)
        self._refresh()
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh)
        self._poll.start(1000)

    def _row(self, layout, title):
        box = QWidget()
        box.setObjectName("card")
        box.setStyleSheet("#card { background: #181c22; border: 1px solid #2c333e; border-radius: 4px; }"
                          "#card QLabel { background: transparent; }")
        h = QHBoxLayout(box)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        mark = QLabel("•")
        mark.setFixedWidth(18)
        mark.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        mark.setStyleSheet("font-size: 12pt; font-weight: 700;")
        tv = QVBoxLayout()
        tv.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 600;")
        text = QLabel("")
        text.setObjectName("hint")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tv.addWidget(t)
        tv.addWidget(text)
        btn = QPushButton("")
        h.addWidget(mark)
        h.addLayout(tv, 1)
        h.addWidget(btn, alignment=Qt.AlignVCenter)
        layout.addWidget(box)
        return mark, text, btn

    def _set(self, key, state, text):
        mark, label, _ = self.rows[key]
        mark.setText("✓" if state else "!" if state is False else "•")
        mark.setStyleSheet("font-size: 12pt; font-weight: 700; color: %s;"
                           % ("#4cd07d" if state else "#e2a03b" if state is False else "#8f98a8"))
        if label.text() != text:
            label.setText(text)

    def _refresh(self):
        w = self.win
        self._ticks += 1
        if self._ticks % 5 == 0:
            self.launch_opt = gsi.launch_option_set()
        link = w._link_status()

        if not w.matchups or w.preloading:
            self._set("stats", None, "Downloading in the background — you can keep using the program. "
                                     + w.status.text().lstrip("⚠ "))
        else:
            self._set("stats", True, "Downloaded. They refresh by themselves every few days.")

        installed = gsi.is_installed(self.cfg_dir)
        self.rows["link"][2].setText("Reinstall" if installed else "Install")
        if installed:
            self._set("link", True, "Installed" + self.auto_note + ". Dota reads it when it starts.")
        elif self.cfg_dir:
            self._set("link", False, "Not installed. Press Install — the program writes one small file "
                                     "into Dota's cfg folder.")
        else:
            self._set("link", False, "Dota 2 was not found through Steam. Press Install and choose the folder "
                                     "“dota 2 beta\\game\\dota\\cfg” yourself.")

        steps = (f"In Steam: right-click Dota 2 → Properties → General → Launch Options, add  "
                 f"{gsi.LAUNCH_OPTION}  and restart Dota.")
        if link != "off":
            self._set("option", True, "Working — the game has already sent data to this program.")
        elif self.launch_opt:
            self._set("option", True, "Set in Steam. If Dota was already running, restart it once.")
        elif self.launch_opt is False:
            self._set("option", False, "Not set yet. " + steps + " Only you can do this step — "
                                       "Steam does not let other programs change it safely.")
        else:
            self._set("option", None, "Could not read Steam's settings. " + steps)

        if link == "live":
            self._set("signal", True, "Connected — a match is in progress.")
        elif link == "ready":
            self._set("signal", True, "Received earlier in this session. Dota sends nothing in the main menu.")
        elif w.gsi.error:
            self._set("signal", False, f"The program cannot listen for the game: {w.gsi.error}. "
                                       "Close other copies of this program.")
        else:
            self._set("signal", None, "No signal yet — it appears when a match starts (Dota sends nothing in "
                                      "the main menu). To test, start any bot match after the steps above.")

        ok, text = w.window_status()
        self._set("window", True if ok else None,
                  text + ". Set Dota's display mode to Borderless Window (Settings → Video); "
                         "exclusive fullscreen cannot be read.")

        if w._stratz_ready():
            using = w.source.currentIndex() == 1
            self.rows["stratz"][2].setText("Change token…" if using else "Use Stratz")
            self._set("stratz", True, "Connected" + (" and in use." if using else ", but OpenDota is selected."))
        else:
            self.rows["stratz"][2].setText("Connect…")
            self._set("stratz", None, "Adds statistics by rank and position, hero synergy, skill order and "
                                      "talents. Needs a free personal token from stratz.com/api. Without it "
                                      "the program uses OpenDota.")

    def _install_link(self):
        cfg = self.cfg_dir
        if cfg is None:
            picked = QFileDialog.getExistingDirectory(
                self, "Select the Dota 2 folder “dota 2 beta\\game\\dota\\cfg”")
            if not picked:
                return
            cfg = Path(picked)
        try:
            gsi.install(cfg)
            self.cfg_dir, self.auto_note = cfg, ""
        except Exception as e:
            self._set("link", False, f"Could not write the file: {e}")
            return
        self._refresh()

    def _copy_option(self):
        QApplication.clipboard().setText(gsi.LAUNCH_OPTION)
        self.rows["option"][2].setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.rows["option"][2].setText("Copy option"))

    def _stratz(self):
        w = self.win
        if w._stratz_ready() and w.source.currentIndex() == 1:
            d = TokenDialog(self, w.s.get("stratz_token", ""))
            if d.exec():
                w.s.update(stratz_token=d.token(), stratz_ok=True)
                data.save_settings(w.s)
                w._load_matchups(force=True)
        else:
            w.connect_stratz()
        self._refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dota Draft Helper")
        self.resize(1320, 780)
        self.s = data.load_settings()
        self.pool = QThreadPool.globalInstance()
        self.heroes: list[dict] = []
        self.icons: dict[int, QIcon] = {}
        self.names: dict[int, str] = {}
        self.matchups: dict | None = None
        self.detector: vision.Detector | None = None
        self.allies: list[int] = []
        self.enemies: list[int] = []
        self.bans: list[int] = []
        self.ally_pos: dict[int, int] = {}
        self.enemy_pos: dict[int, int] = {}
        self.ignored: set[int] = set()
        self.scan_busy = False
        self.last_seen: tuple | None = None
        self.load_gen = 0
        self.preloading = False
        self.note = ""
        self.my_hero: int | None = None
        self.build_cache: dict[tuple, tuple] = {}
        self.build_loading: set[tuple] = set()
        self.hero_locked = False
        self.last_window: tuple[int, int] | None = None
        self.tick = 0
        self._tasks = set()
        self.overlay: Overlay | None = None
        self.slot_seen: list[tuple] = [(None, 0)] * 10
        self.slot_hero: list[int | None] = [None] * 10
        self.gsi_state: str | None = None
        self.gsi_match: str | None = None
        self.last_shot = 0.0
        self.shot_idx = 0
        self._auto_last = ""
        self.gsi = gsi.GsiServer()
        self.gsi.updated.connect(self._on_gsi)
        self.gsi.start()
        self.last_picks: list[dict] = []
        self.last_bans: list[dict] = []
        if self.s.get("source", 0) == 1 and not self._stratz_ready():
            self.s["source"] = 0
        self._build()
        self._apply_mode()
        self._apply_input()
        self._update_conn()
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self._scan_tick)
        self.timer.start()
        self._run(Task(self._load_base, True), self._base_loaded)
        if self.s.get("overlay_on", False):
            self.ov_btn.setChecked(True)
        if not self.s.get("setup_seen", False):
            QTimer.singleShot(400, self._setup)


    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(12, 10, 12, 8)
        v.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.mode = self._combo(["All Pick", "Captains Mode"], "mode", top, "Game mode")
        self.rank = self._combo([b[0] for b in data.BRACKETS], "rank", top, "Rank")
        self.conn = QLabel("")
        self.source = self._combo(["OpenDota", "Stratz"], "source", top, "Statistics", self.conn)
        self.side = self._combo(["Radiant (left)", "Dire (right)"], "side", top, "My side")
        top.addStretch(1)

        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(self._h("DRAFT INPUT"))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.input = QButtonGroup(self)
        for i, t in enumerate(["Auto-detect", "Manual"]):
            b = QPushButton(t)
            b.setObjectName("seg")
            b.setCheckable(True)
            self.input.addButton(b, i)
            seg.addWidget(b)
        self.input.button(0 if self.s.get("auto", True) else 1).setChecked(True)
        self.input.idClicked.connect(self._input_changed)
        box.addLayout(seg)
        top.addLayout(box)

        self.ov_btn = QPushButton("Overlay")
        self.ov_btn.setCheckable(True)
        self.ov_btn.setToolTip("Small always-on-top panel with the top suggestions, to keep over the game")
        self.ov_btn.toggled.connect(self._toggle_overlay)
        top.addWidget(self.ov_btn, alignment=Qt.AlignBottom)
        sb = QPushButton("Setup")
        sb.setToolTip("Checklist of everything the program needs to work with your game")
        sb.clicked.connect(self._setup)
        top.addWidget(sb, alignment=Qt.AlignBottom)
        b = QPushButton("Settings")
        b.clicked.connect(self._settings)
        top.addWidget(b, alignment=Qt.AlignBottom)
        v.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        v.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(self._h("MY TEAM"))
        head.addStretch(1)
        nb = QPushButton("New draft")
        nb.clicked.connect(self._reset)
        head.addWidget(nb)
        lv.addLayout(head)
        self.row_ally = TeamRow(5, SLOT, with_pos=True)
        self.row_ally.removed.connect(lambda i: self._remove(self.allies, i))
        self.row_ally.pos_changed.connect(lambda i, p: self._set_pos(self.allies, self.ally_pos, i, p))
        lv.addWidget(self.row_ally)
        lv.addWidget(self._h("ENEMY TEAM"))
        self.row_enemy = TeamRow(5, SLOT, with_pos=True)
        self.row_enemy.removed.connect(lambda i: self._remove(self.enemies, i))
        self.row_enemy.pos_changed.connect(lambda i, p: self._set_pos(self.enemies, self.enemy_pos, i, p))
        lv.addWidget(self.row_enemy)

        self.auto_panel = QLabel()
        self.auto_panel.setObjectName("info")
        self.auto_panel.setWordWrap(True)
        self.auto_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lv.addWidget(self.auto_panel)

        self.manual_panel = QWidget()
        mv = QVBoxLayout(self.manual_panel)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(6)
        self.ban_head = self._h("BANS")
        mv.addWidget(self.ban_head)
        self.row_ban = TeamRow(16, BAN_SLOT, per_row=8)
        self.row_ban.removed.connect(lambda i: self._remove(self.bans, i))
        mv.addWidget(self.row_ban)
        addrow = QHBoxLayout()
        addrow.setSpacing(4)
        addrow.addWidget(self._h("ADD TO:"))
        self.target = QButtonGroup(self)
        for i, t in enumerate(["Enemy", "My team", "Bans"]):
            tbn = QPushButton(t)
            tbn.setCheckable(True)
            tbn.setChecked(i == 0)
            self.target.addButton(tbn, i)
            addrow.addWidget(tbn)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search hero…")
        self.search.textChanged.connect(self._filter)
        addrow.addWidget(self.search, 1)
        mv.addLayout(addrow)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setIconSize(QSize(64, 36))
        self.grid.setSpacing(3)
        self.grid.setUniformItemSizes(True)
        self.grid.itemClicked.connect(self._grid_click)
        mv.addWidget(self.grid, 1)
        lv.addWidget(self.manual_panel, 1)
        self.left_stretch = QWidget()
        lv.addWidget(self.left_stretch, 1)
        split.addWidget(left)

        self.tabs = QTabWidget()
        pick_tab = QWidget()
        pv = QVBoxLayout(pick_tab)
        pv.setContentsMargins(0, 6, 0, 0)
        pv.setSpacing(6)
        frow = QHBoxLayout()
        frow.setSpacing(4)
        frow.addWidget(self._h("SHOW POSITION:"))
        self.pos_filter = QButtonGroup(self)
        for i, t in enumerate(["All", "1", "2", "3", "4", "5"]):
            fb = QPushButton(t)
            fb.setObjectName("seg")
            fb.setCheckable(True)
            fb.setChecked(i == 0)
            if i:
                fb.setToolTip(data.POS_NAMES[i])
            self.pos_filter.addButton(fb, i)
            frow.addWidget(fb)
        self.pos_filter.idClicked.connect(lambda _: self._refresh())
        frow.addStretch(1)
        self.pool_only = QCheckBox("My pool only")
        self.pool_only.setChecked(self.s.get("pool_only", False))
        self.pool_only.toggled.connect(self._pool_toggled)
        frow.addWidget(self.pool_only)
        self.pool_btn = QPushButton()
        self.pool_btn.setObjectName("seg")
        self.pool_btn.clicked.connect(self._edit_pool)
        frow.addWidget(self.pool_btn)
        self._pool_label()
        pv.addLayout(frow)
        self.tbl_pick = self._table(["Hero", "Score", "Best position", "Win rate",
                                     "Good against", "Weak against", "Synergy"])
        pv.addWidget(self.tbl_pick)
        self.tbl_ban = self._table(["Hero", "Threat", "Likely position", "Win rate",
                                    "Counters on my team", "", ""])
        self.tbl_pick.cellDoubleClicked.connect(lambda r, c: self._table_add(self.tbl_pick, r, self.allies, 5, True))
        self.tbl_ban.cellDoubleClicked.connect(lambda r, c: self._table_add(self.tbl_ban, r, self.bans, 16, False))
        self.tabs.addTab(pick_tab, "Suggested picks")
        self.tabs.addTab(self.tbl_ban, "Suggested bans")
        split.addWidget(self.tabs)
        split.setSizes([500, 820])

        bot = QHBoxLayout()
        self.status = QLabel("Loading…")
        self.status.setObjectName("hint")
        bot.addWidget(self.status, 1)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(220)
        self.bar.hide()
        bot.addWidget(self.bar)
        v.addLayout(bot)

    def _h(self, text):
        lab = QLabel(text)
        lab.setObjectName("h")
        return lab

    def _combo(self, items, key, layout, title, extra: QLabel | None = None):
        box = QVBoxLayout()
        box.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self._h(title.upper()))
        if extra is not None:
            head.addWidget(extra)
        head.addStretch(1)
        box.addLayout(head)
        c = QComboBox()
        c.addItems(items)
        c.setCurrentIndex(min(self.s.get(key, 0), len(items) - 1))
        c.currentIndexChanged.connect(lambda i, k=key: self._combo_changed(k, i))
        box.addWidget(c)
        layout.addLayout(box)
        return c

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(34)
        t.setIconSize(QSize(52, 29))
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.setSortingEnabled(True)
        t.setWordWrap(False)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate([165, 65, 150, 75, 230, 190]):
            t.setColumnWidth(i, w)
        t.setToolTip("Double-click a row to add the hero to the draft")
        return t


    def _set(self, key, val):
        self.s[key] = val
        data.save_settings(self.s)

    def _stratz_ready(self) -> bool:
        return bool(self.s.get("stratz_token")) and self.s.get("stratz_ok", False)

    def _update_conn(self):
        on = self.source.currentIndex() == 1 and self._stratz_ready()
        self.conn.setObjectName("ok")
        self.conn.setText("● Connected" if on else "")
        self.conn.style().unpolish(self.conn)
        self.conn.style().polish(self.conn)
        self._apply_rank_lock()

    def _apply_rank_lock(self):
        od = self.source.currentIndex() == 0
        self.rank.blockSignals(True)
        self.rank.setCurrentIndex(0 if od else min(self.s.get("rank", 0), self.rank.count() - 1))
        self.rank.blockSignals(False)
        self.rank.setEnabled(not od)
        self.rank.setToolTip("Rank brackets are available with Stratz statistics only" if od else "")

    def _set_source(self, idx):
        self.source.blockSignals(True)
        self.source.setCurrentIndex(idx)
        self.source.blockSignals(False)
        self._set("source", idx)
        self._update_conn()

    def _combo_changed(self, key, idx):
        if key == "source":
            if idx == 1 and not self._stratz_ready():
                d = TokenDialog(self, self.s.get("stratz_token", ""))
                if not d.exec():
                    self._set_source(0)
                    return
                self.s.update(stratz_token=d.token(), stratz_ok=True)
            self._set_source(idx)
            self._load_matchups()
            return
        self._set(key, idx)
        if key == "mode":
            self._apply_mode()
            self._refresh()
        elif key == "rank":
            self._load_matchups()
        elif key == "side":
            self.allies, self.enemies = self.enemies, self.allies
            self.ally_pos, self.enemy_pos = self.enemy_pos, self.ally_pos
            self._refresh()

    def _apply_mode(self):
        cm = self.mode.currentIndex() == 1
        self.ban_head.setText("BANS" if cm else "BANS (optional)")

    def _input_changed(self, idx):
        self._set("auto", idx == 0)
        self._apply_input()

    def _is_auto(self) -> bool:
        return self.input.checkedId() == 0

    def _apply_input(self):
        auto = self._is_auto()
        self.auto_panel.setVisible(auto)
        self.left_stretch.setVisible(auto)
        self.manual_panel.setVisible(not auto)
        if auto:
            self._auto_text("waiting for the pick screen…")

    def _auto_text(self, state: str):
        if self.gsi.error:
            link = f"<span style='color:#e2665b'>Game link failed: {self.gsi.error}.</span>"
        elif self._link_status() == "live":
            link = ("<span style='color:#4cd07d'>● Game link connected</span> — the draft resets "
                    "and your side is set automatically.")
        elif self._link_status() == "ready":
            link = ("<span style='color:#4cd07d'>● Game link ready</span> — Dota reports only during "
                    "a match; reading starts with the next hero selection.")
        else:
            link = ("Game link: no signal yet. Dota reports only during a match, so this turns green "
                    "when your first match starts. If it does not, set the link up in <b>Settings</b>. "
                    "Until then press <b>New draft</b> before each game.")
        text = (f"<b>Auto-detect is on</b> — {state}<br><br>{link}<br><br>"
                "Heroes are read from the portrait slots at the top of the hero selection screen "
                "(Dota in Borderless Window mode).<br>"
                "• Set a position under any portrait to refine the suggestions (optional).<br>"
                "• Click a portrait to remove a wrong detection.")
        if text != self._auto_last:
            self._auto_last = text
            self.auto_panel.setText(text)


    def _toggle_overlay(self, on):
        self._set("overlay_on", on)
        if not on:
            if self.overlay:
                self.overlay.hide()
            return
        if self.overlay is None:
            ov = Overlay(self.s.get("overlay_picks", True), self.s.get("overlay_bans", False),
                         set(self.s.get("build_collapsed", [])))
            ov.collapsed_changed.connect(lambda keys: self._set("build_collapsed", sorted(keys)))
            ov.pos_clicked.connect(lambda i: self.pos_filter.button(i).click())
            ov.sections_changed.connect(self._overlay_sections)
            ov.build_toggled.connect(lambda on: self._show_build() if on else None)
            ov.hidden.connect(lambda: self.ov_btn.setChecked(False))
            ov.moved.connect(lambda p: self._set("overlay_xy", [p.x(), p.y()]))
            self.overlay = ov
        screens = QApplication.screens()
        xy = self.s.get("overlay_xy")
        if xy and any(sc.geometry().contains(xy[0] + 20, xy[1] + 10) for sc in screens):
            self.overlay.move(xy[0], xy[1])
        else:
            g = QApplication.primaryScreen().geometry()
            self.overlay.move(g.right() - self.overlay.width() - 20, g.top() + int(g.height() * 0.28))
        self._update_overlay()
        if self.hero_locked:
            self.overlay.set_build_mode(True)
            self._show_build()
        self.overlay.show()

    def _show_build(self):
        ov, hid = self.overlay, self.my_hero
        if ov is None:
            return
        if not hid or hid not in self.names:
            ov.set_build_message("Your hero is not known yet. It comes from the game link "
                                 "as soon as you pick in a match.")
            return
        key = self._build_key()
        if key in self.build_cache:
            ov.set_build(self.names[hid], self.icons.get(hid, QIcon()), *self.build_cache[key])
            return
        if key in self.build_loading:
            return
        self.build_loading.add(key)
        ov.set_build_message(f"Loading the build for {self.names[hid]}…")
        _, src, bracket, pos = key
        token = self.s.get("stratz_token", "")

        def work():
            if src == "stratz":
                try:
                    return data.load_stratz_build(hid, bracket, pos or None, token), True
                except data.DataError:
                    pass
            return {"items": data.load_build(hid), "skills": [], "talents": []}, False

        def done(res):
            b, from_stratz = res
            self.build_loading.discard(key)
            sections = []
            for label, rows in b["items"]:
                cells = []
                for r in rows:
                    pm = QPixmap(r["icon"])
                    if not pm.isNull():
                        cells.append((pm, f"{r['name']} — {r['count']} games"))
                sections.append((label, cells))
            skills = [(pm, s["name"]) for s in b["skills"] if not (pm := QPixmap(s["icon"])).isNull()]
            if from_stratz:
                note = f"{data.BRACKETS[bracket][0]} · {'pos ' + str(pos) if pos else 'all positions'} · Stratz"
                ib, ip = b.get("items_scope", (bracket, pos or None))
                if (ib, ip) != (bracket, pos or None):
                    note += (f"\nItems: {data.BRACKETS[ib][0].lower()}, "
                             f"{'pos ' + str(ip) if ip else 'all positions'} (too few games in this filter)")
            else:
                note = "OpenDota · all ranks and positions"
            self.build_cache[key] = (sections, skills, b["talents"], note)
            if self.my_hero == hid and self._build_key() == key:
                self._show_build()

        def err(msg):
            self.build_loading.discard(key)
            if self.my_hero == hid and self.overlay:
                self.overlay.set_build_message("⚠ " + msg)

        self._run(Task(work), done, err)

    def _build_key(self) -> tuple:
        hid = self.my_hero
        if not (self.source.currentIndex() == 1 and self._stratz_ready()):
            return hid, "opendota", 0, 0
        pos = self.ally_pos.get(hid)
        if not pos and self.matchups and self.matchups.get("pos_real"):
            table = self.matchups["pos"].get(hid) or {}
            if table:
                pos = max(table, key=lambda p: table[p][0])
        return hid, "stratz", self.rank.currentIndex(), pos or 0

    def _overlay_sections(self, picks: bool, bans: bool):
        self.s["overlay_picks"] = picks
        self._set("overlay_bans", bans)

    def _update_overlay(self):
        ov = self.overlay
        if ov is None:
            return
        if not self.matchups:
            state = "Loading statistics…"
        else:
            state = (f"{'Auto' if self._is_auto() else 'Manual'} · my team {len(self.allies)}/5 · "
                     f"enemy {len(self.enemies)}/5")
        ov.show_rows(self.last_picks, self.last_bans, self.icons, state,
                     self.pos_filter.checkedId(), set(self.ally_pos.values()))

    def _pool_label(self):
        self.pool_btn.setText(f"Edit pool ({len(self.s.get('pool', []))})…")

    def _pool_toggled(self, on):
        self._set("pool_only", on)
        if on and not self.s.get("pool") and self.heroes:
            if not self._edit_pool():
                self.pool_only.setChecked(False)
                return
        self._refresh()

    def _edit_pool(self) -> bool:
        if not self.heroes:
            return False
        d = PoolDialog(self, self.heroes, self.icons, set(self.s.get("pool", [])))
        if not d.exec():
            return False
        self._set("pool", d.pool())
        self._pool_label()
        if not self.s["pool"] and self.pool_only.isChecked():
            self.pool_only.setChecked(False)
        else:
            self._refresh()
        return bool(self.s["pool"])

    def _setup(self):
        d = SetupDialog(self)
        d.exec()
        self._set("setup_seen", True)
        self._update_conn()

    def connect_stratz(self) -> bool:
        if not self._stratz_ready():
            d = TokenDialog(self, self.s.get("stratz_token", ""))
            if not d.exec():
                return False
            self.s.update(stratz_token=d.token(), stratz_ok=True)
        self._set_source(1)
        self._load_matchups()
        return True

    def _settings(self):
        d = SettingsDialog(self, self.s, self._link_status)
        if d.exec():
            vals = d.values()
            self.s.update(vals)
            data.save_settings(self.s)
            self._update_conn()
            if "stratz_token" in vals and self.source.currentIndex() == 1:
                self._load_matchups(force=True)


    def _run(self, task: Task, on_done, on_error=None):
        self._tasks.add(task)
        task.setAutoDelete(False)

        def fin(*_):
            self._tasks.discard(task)

        task.sig.done.connect(on_done)
        task.sig.done.connect(fin)
        task.sig.error.connect(on_error or self._error)
        task.sig.error.connect(fin)
        task.sig.progress.connect(self._progress)
        self.pool.start(task)

    def _progress(self, i, n, text):
        self.bar.show()
        self.bar.setMaximum(n)
        self.bar.setValue(i)
        self.status.setText(f"{text}: {i}/{n}")

    def _error(self, msg):
        self.bar.hide()
        self.status.setText("⚠ " + msg)

    def _load_base(self, progress):
        heroes = data.load_heroes()
        data.download_images(heroes, progress)
        det = vision.Detector(heroes, data.img_path)
        det.warm()
        return heroes, det

    def _base_loaded(self, res):
        self.heroes, self.detector = res
        self.names = {h["id"]: h["name"] for h in self.heroes}
        for h in self.heroes:
            pm = QPixmap(str(data.img_path(h)))
            self.icons[h["id"]] = QIcon(pm) if not pm.isNull() else QIcon()
            it = QListWidgetItem(self.icons[h["id"]], "")
            it.setToolTip(h["name"])
            it.setData(Qt.UserRole, h["id"])
            it.setSizeHint(QSize(68, 40))
            self.grid.addItem(it)
        self.bar.hide()
        QTimer.singleShot(0, self.grid.scrollToTop)
        self._load_matchups()

    def _load_matchups(self, force=False):
        if not self.heroes:
            return
        self.load_gen += 1
        gen = self.load_gen
        src = "stratz" if self.source.currentIndex() == 1 else "opendota"
        br = self.rank.currentIndex()
        token = self.s.get("stratz_token", "")
        heroes = self.heroes
        self.status.setText("Loading statistics…")

        def done(m):
            if gen != self.load_gen:
                return
            self.matchups = m
            self.bar.hide()
            if m["source"] == "stratz":
                note = "Statistics: Stratz."
                if not m["pos_real"]:
                    note += " Position stats were unavailable — positions are estimated."
            else:
                note = ("Statistics: OpenDota — no per-rank data (rank is locked) and positions are "
                        "estimated. Stratz gives both.")
            self.note = note
            self.status.setText(note)
            self._refresh()
            self._start_preload()

        def err(msg):
            if gen != self.load_gen:
                return
            self._error(msg)
            if src == "stratz":
                if "rejected" in msg:
                    self.s["stratz_ok"] = False
                self._set_source(0)
                if self.matchups is None or self.matchups["source"] != "opendota":
                    QTimer.singleShot(0, self._load_fallback)

        self._run(Task(lambda p: data.load_matchups(src, br, heroes, token, p, force), True), done, err)

    def _start_preload(self):
        if self.preloading or not self.heroes:
            return
        jobs = data.preload_jobs(self._stratz_ready(), self.heroes)
        if not jobs:
            return
        self.preloading = True
        heroes, token = self.heroes, self.s.get("stratz_token", "")

        def work(progress):
            failed = []
            for k, (src, idx) in enumerate(jobs):
                if src == "builds":
                    label = f"Preloading item builds (set {k + 1} of {len(jobs)})"
                    try:
                        data.preload_builds(heroes, lambda i, n, _t: progress(i, n, label))
                    except data.DataError as e:
                        failed.append(str(e))
                    continue
                label = "Preloading " + (f"Stratz · {data.BRACKETS[idx][0]}" if src == "stratz" else "OpenDota")
                label += f" (set {k + 1} of {len(jobs)})"
                try:
                    data.load_matchups(src, idx, heroes, token, lambda i, n, _t: progress(i, n, label))
                except data.DataError as e:
                    failed.append(str(e))
            return failed

        def done(failed):
            self.preloading = False
            self.bar.hide()
            tail = (f"  ⚠ Some data could not be preloaded: {failed[0]}" if failed
                    else "  All statistics are downloaded.")
            self.status.setText(self.note + tail)

        self._run(Task(work, True), done)

    def _load_fallback(self):
        keep = self.status.text()
        self._load_matchups()
        self.status.setText(keep + "  Using OpenDota instead.")


    def _reset(self):
        self.allies.clear()
        self.enemies.clear()
        self.bans.clear()
        self.ally_pos.clear()
        self.enemy_pos.clear()
        self.ignored.clear()
        self.slot_seen = [(None, 0)] * 10
        self.slot_hero = [None] * 10
        self.my_hero = None
        self.hero_locked = False
        if self.overlay:
            self.overlay.set_build_mode(False)
            self._show_build()
        self._refresh()

    def _remove(self, lst, idx):
        if idx < len(lst):
            hid = lst.pop(idx)
            self.ally_pos.pop(hid, None)
            self.enemy_pos.pop(hid, None)
            if self._is_auto():
                self.ignored.add(hid)
            self._refresh()

    def _set_pos(self, lst, posmap, idx, p):
        if idx >= len(lst):
            return
        hid = lst[idx]
        if p == 0:
            posmap.pop(hid, None)
        else:
            for other in [h for h, v in posmap.items() if v == p and h != hid]:
                del posmap[other]
            posmap[hid] = p
        self._refresh()

    def _add(self, hid, lst, limit) -> bool:
        if hid in self.allies or hid in self.enemies or hid in self.bans or len(lst) >= limit:
            return False
        lst.append(hid)
        return True

    def _grid_click(self, item):
        hid = item.data(Qt.UserRole)
        lst, lim = [(self.enemies, 5), (self.allies, 5), (self.bans, 16)][self.target.checkedId()]
        if self._add(hid, lst, lim):
            self._refresh()

    def _table_add(self, tbl, row, lst, limit, with_pos):
        it = tbl.item(row, 0)
        if not it:
            return
        hid = it.data(Qt.UserRole + 1)
        p = tbl.item(row, 2).data(Qt.UserRole + 1)
        if self._add(hid, lst, limit):
            self.ignored.discard(hid)
            if with_pos and p and p not in self.ally_pos.values():
                self.ally_pos[hid] = p
            self._refresh()

    def _filter(self, text):
        t = text.strip().lower()
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            it.setHidden(bool(t) and t not in it.toolTip().lower())


    def _refresh(self):
        self.row_ally.set(self.allies, self.icons, self.names, self.ally_pos)
        self.row_enemy.set(self.enemies, self.icons, self.names, self.enemy_pos)
        self.row_ban.set(self.bans, self.icons, self.names)
        taken = set(self.allies) | set(self.enemies) | set(self.bans)
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            it.setFlags(Qt.NoItemFlags if it.data(Qt.UserRole) in taken else Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        used = set(self.ally_pos.values())
        for i in range(1, 6):
            self.pos_filter.button(i).setEnabled(i not in used)
        if self.pos_filter.checkedId() in used:
            self.pos_filter.button(0).setChecked(True)
        if not self.matchups:
            return
        cm = self.mode.currentIndex() == 1
        ranks = data.BRACKETS[self.rank.currentIndex()][3]
        only = self.pos_filter.checkedId() or None
        mine = set(self.s.get("pool", []))
        pool = mine if self.pool_only.isChecked() and mine else None
        picks = recommend.recommend(self.heroes, self.matchups, self.allies, self.enemies, self.bans,
                                    self.ally_pos, self.enemy_pos, cm, only, pool)
        bans = recommend.recommend_bans(self.heroes, self.matchups, self.allies, self.enemies, self.bans,
                                        self.ally_pos, self.enemy_pos, cm)
        self._fill(self.tbl_pick, picks, ranks, True)
        self._fill(self.tbl_ban, bans, ranks, False)
        self.last_picks, self.last_bans = picks, bans
        self._update_overlay()
        if self.overlay and self.overlay.build_mode():
            self._show_build()

    def _fmt(self, parts, best=True, n=2):
        parts = [p for p in parts if (p[1] > 0.05 if best else p[1] < -0.05)]
        parts.sort(key=lambda p: -p[1] if best else p[1])
        return ", ".join(f"{self.names.get(h, '?')} {v:+.1f}" for h, v in parts[:n])

    def _fill(self, tbl, rows, ranks, is_pick):
        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(rows))
        real = self.matchups["pos_real"]
        for r, row in enumerate(rows):
            h = row["hero"]
            in_pool = is_pick and h["id"] in self.s.get("pool", [])
            it = QTableWidgetItem(self.icons.get(h["id"], QIcon()), h["name"] + ("  ★" if in_pool else ""))
            it.setData(Qt.UserRole + 1, h["id"])
            it.setToolTip(", ".join(h["roles"]) + ("\nIn my pool" if in_pool else ""))
            tbl.setItem(r, 0, it)
            sc = NumItem(f"{row['score']:+.1f}")
            sc.setData(Qt.UserRole, row["score"])
            sc.setTextAlignment(Qt.AlignCenter)
            good, bad = row["score"] > 0.5, row["score"] < -0.5
            if is_pick:
                sc.setForeground(QColor("#4cd07d" if good else "#e2665b" if bad else "#dfe3ea"))
            else:
                sc.setForeground(QColor("#e2665b" if good else "#dfe3ea"))
            tbl.setItem(r, 1, sc)
            p = row["pos"]
            txt = f"{p} · {data.POS_NAMES[p]}"
            if row["pos_wr"] is not None:
                txt += f"  {row['pos_wr']:.1f}%"
            ps = NumItem(txt)
            ps.setData(Qt.UserRole, p)
            ps.setData(Qt.UserRole + 1, p)
            ps.setToolTip("Position where this hero scores best in this draft"
                          + ("" if real else " (estimated from hero roles)"))
            tbl.setItem(r, 2, ps)
            wr = data.hero_winrate(h, ranks)
            w = NumItem(f"{wr:.1f}%" if wr is not None else "—")
            w.setData(Qt.UserRole, wr or 0)
            w.setTextAlignment(Qt.AlignCenter)
            tbl.setItem(r, 3, w)
            tbl.setItem(r, 4, QTableWidgetItem(self._fmt(row["vs"], True)))
            tbl.setItem(r, 5, QTableWidgetItem(self._fmt(row["vs"], False) if is_pick else ""))
            tbl.setItem(r, 6, QTableWidgetItem(self._fmt(row["with"], True) if is_pick else ""))
        tbl.setSortingEnabled(True)
        tbl.sortItems(1, Qt.DescendingOrder)
        tbl.scrollToTop()


    def _link_status(self) -> str:
        if time.time() - self.gsi.last_time < 15:
            return "live"
        return "ready" if self.gsi.last_time else "off"

    def _own_rects(self):
        out = []
        if self.isVisible() and not self.isMinimized():
            out.append(winutil.window_rect(self.winId()))
        if self.overlay and self.overlay.isVisible():
            out.append(winutil.window_rect(self.overlay.winId()))
        return out

    def _scan_gate(self):
        hwnd = winutil.find_dota()
        if not hwnd:
            return None, "Dota 2 is not running."
        rect = winutil.client_rect(hwnd)
        if not rect:
            return None, "Dota 2 is minimized."
        link = self._link_status()
        if link == "live":
            info = self.gsi.info or {}
            if not info.get("in_game"):
                return None, "in the menu — waiting for a match."
            if info.get("state") not in gsi.PICK_STATES:
                return None, (f"{gsi.STATE_NAMES.get(info.get('state'), 'waiting')} — "
                              "heroes are read only during hero selection.")
        elif link == "ready":
            return None, "waiting for a match to start."
        elif not winutil.is_active(hwnd):
            return None, "Dota 2 is not the active window."
        x, y, w, h = rect
        strip = (x, y, w, max(20, int(h * vision.STRIP_H)))
        if any(winutil.intersects(strip, r) for r in self._own_rects()):
            return None, "this app's window covers the top of the game — move it away."
        return (rect, strip), ""

    def _scan_tick(self):
        if not self._is_auto() or self.scan_busy or not self.detector:
            return
        if len(self.allies) >= 5 and len(self.enemies) >= 5:
            self._auto_text("draft complete.")
            return
        gate, reason = self._scan_gate()
        if gate is None:
            self.slot_seen = [(None, 0)] * 10
            self._auto_text(reason)
            return
        rect, strip = gate
        win_h = rect[3]
        frame = winutil.capture(*strip)
        if frame is None:
            return
        if int(frame.max()) < 12:
            self._auto_text("the game image is black — switch Dota to Borderless Window mode.")
            return
        self._debug_shot(rect)
        self.scan_busy = True
        thr = self.s.get("thr2", 70) / 100
        det = self.detector
        self.last_window = (rect[2], rect[3])
        key = f"{rect[2]}x{rect[3]}"
        k = self._hud_scale(rect[2], rect[3])

        def err(msg):
            self.scan_busy = False

        if k is not None:
            def done(res):
                self.scan_busy = False
                self._on_detect(res)

            self._run(Task(lambda: det.detect(frame, win_h, thr, k)), done, err)
            return

        def calibrated(found):
            self.scan_busy = False
            if not found:
                self._auto_text(f"calibrating for a {key} window — waiting for the first picked hero.")
                return
            calib = dict(self.s.get("calib", {}))
            calib[key] = found[0]
            self._set("calib", calib)
            self._on_detect(found[1])

        self._run(Task(lambda: det.calibrate(frame, win_h, thr)), calibrated, err)

    def _hud_scale(self, w: int, h: int) -> float | None:
        k = self.s.get("calib", {}).get(f"{w}x{h}")
        if k is not None:
            return float(k)
        return 1.0 if vision.is_standard(w, h) else None

    def window_status(self) -> tuple[bool, str]:
        hwnd = winutil.find_dota()
        rect = winutil.client_rect(hwnd) if hwnd else None
        size = (rect[2], rect[3]) if rect else self.last_window
        if not size:
            return True, "Detected automatically when Dota 2 is running"
        w, h = size
        if f"{w}x{h}" in self.s.get("calib", {}):
            return True, f"{w}×{h} — calibrated"
        if vision.is_standard(w, h):
            return True, f"{w}×{h} (16:9) — supported"
        return False, f"{w}×{h} — will calibrate itself at the first pick"

    def _debug_shot(self, rect):
        if not self.s.get("debug_shots", False) or time.time() - self.last_shot < 6:
            return
        self.last_shot = time.time()
        img = winutil.capture(*rect)
        if img is None:
            return
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            self.shot_idx = self.shot_idx % 12 + 1
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                buf.tofile(str(DEBUG_DIR / f"shot_{self.shot_idx:02d}.jpg"))
        except Exception:
            pass

    def _on_detect(self, res):
        if not self._is_auto():
            return
        slots = res["slots"]
        n = sum(1 for s in slots if s)
        self._auto_text(f"reading hero selection — {n} picked hero{'es' if n != 1 else ''} visible." if n
                        else "reading hero selection — no picked heroes yet.")
        mine_left = self.side.currentIndex() == 0
        changed = False
        for i, hid in enumerate(slots):
            prev, cnt = self.slot_seen[i]
            cnt = cnt + 1 if hid == prev else 1
            self.slot_seen[i] = (hid, cnt)
            if not hid or cnt < 2 or self.slot_hero[i] == hid or hid in self.ignored:
                continue
            old = self.slot_hero[i]
            if old:
                for lst, posmap in ((self.allies, self.ally_pos), (self.enemies, self.enemy_pos)):
                    if old in lst:
                        lst.remove(old)
                        posmap.pop(old, None)
                changed = True
            target = self.allies if (i < 5) == mine_left else self.enemies
            if hid in target:
                self.slot_hero[i] = hid
            elif self._add(hid, target, 5):
                self.slot_hero[i] = hid
                changed = True
        if changed:
            self._refresh()


    def _on_gsi(self, info: dict):
        state, prev = info.get("state"), self.gsi_state
        entered_pick = state == "DOTA_GAMERULES_STATE_HERO_SELECTION" and prev != state
        self.gsi_state = state
        if entered_pick:
            if self._is_auto():
                self._reset()
            else:
                self.my_hero, self.hero_locked = None, False
                if self.overlay:
                    self.overlay.set_build_mode(False)
        mine = info.get("hero_id")
        if mine and mine in self.names and not self.hero_locked:
            if self.my_hero != mine:
                self.my_hero = mine
                if self.overlay and self.overlay.build_mode():
                    self._show_build()
            if state in gsi.BUILD_STATES:
                self.hero_locked = True
                if self.overlay:
                    self.overlay.set_build_mode(True)
                    self._show_build()
        if not self._is_auto():
            return
        team = info.get("team")
        if team and state in gsi.PICK_STATES:
            idx = 0 if team == "radiant" else 1
            if self.side.currentIndex() != idx:
                self.side.setCurrentIndex(idx)

    def closeEvent(self, e):
        self.timer.stop()
        self.gsi.stop()
        if self.overlay:
            self.overlay.close()
        self.pool.waitForDone(1500)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if (base / "icon.ico").exists():
        app.setWindowIcon(QIcon(str(base / "icon.ico")))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
