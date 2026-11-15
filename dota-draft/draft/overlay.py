from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

ROWS = 6
ROWS_BOTH = 5
ITEM_KEYS = ["start", "mid", "late", "popular"]

OVERLAY_STYLE = """
#ov { background: #101318; border: 1px solid #2f6fed; border-radius: 6px; }
#ov QLabel { background: transparent; }
#ov QLabel#title { color: #8f98a8; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
#ov QLabel#sect { color: #8f98a8; font-size: 7pt; font-weight: 700; letter-spacing: 1px; }
#ov QLabel#state { color: #7c8594; font-size: 8pt; }
#ov QLabel#name { font-size: 9pt; }
#ov QLabel#pos { color: #8f98a8; font-size: 8pt; }
#ov QLabel#score { font-size: 9pt; font-weight: 600; }
#ov QPushButton { padding: 1px 6px; font-size: 8pt; min-height: 16px; border-radius: 3px; }
#ov QPushButton#x { border: none; background: transparent; color: #8f98a8; font-size: 10pt; padding: 0 4px; }
#ov QPushButton#x:hover { color: white; }
#ov QPushButton#secthead { border: none; background: transparent; color: #8f98a8; font-size: 7pt;
    font-weight: 700; letter-spacing: 1px; text-align: left; padding: 2px 0; min-height: 12px; }
#ov QPushButton#secthead:hover { color: white; }
"""


class _List(QWidget):

    def __init__(self, title: str):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName("sect")
        v.addWidget(self.title)
        self.rows = []
        for _ in range(ROWS):
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            icon = QLabel()
            icon.setFixedSize(44, 25)
            name = QLabel()
            name.setObjectName("name")
            pos = QLabel()
            pos.setObjectName("pos")
            score = QLabel()
            score.setObjectName("score")
            score.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            score.setFixedWidth(40)
            row.addWidget(icon)
            row.addWidget(name, 1)
            row.addWidget(pos)
            row.addWidget(score)
            v.addWidget(holder)
            self.rows.append((holder, icon, name, pos, score))

    def fill(self, rows: list[dict], icons: dict[int, QIcon], is_pick: bool, count: int, titled: bool):
        self.title.setVisible(titled)
        for i, (holder, icon, name, pos, score) in enumerate(self.rows):
            holder.setVisible(i < count)
            if i < len(rows) and i < count:
                r = rows[i]
                h = r["hero"]
                icon.setPixmap(icons.get(h["id"], QIcon()).pixmap(QSize(44, 25)))
                name.setText(h["name"])
                pos.setText(f"pos {r['pos']}")
                s = r["score"]
                score.setText(f"{s:+.1f}")
                if is_pick:
                    col = "#4cd07d" if s > 0.5 else "#e2665b" if s < -0.5 else "#dfe3ea"
                else:
                    col = "#e2665b" if s > 0.5 else "#dfe3ea"
                score.setStyleSheet(f"color: {col};")
            else:
                icon.clear()
                name.setText("")
                pos.setText("")
                score.setText("")


class _Section(QWidget):
    toggled = Signal(str, bool)

    def __init__(self, key: str, title: str, collapsed: bool):
        super().__init__()
        self.key, self.title = key, title
        self.setStyleSheet("background: transparent;")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        self.head = QPushButton()
        self.head.setObjectName("secthead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.setToolTip("Click to collapse or expand")
        self.head.clicked.connect(self._click)
        v.addWidget(self.head)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        v.addWidget(self.content)
        self.collapsed = collapsed
        self._apply()

    def set_title(self, title: str):
        self.title = title
        self._apply()

    def _apply(self):
        self.head.setText(("▸ " if self.collapsed else "▾ ") + self.title)
        self.content.setVisible(not self.collapsed)

    def _click(self):
        self.collapsed = not self.collapsed
        self._apply()
        self.toggled.emit(self.key, self.collapsed)


class _Build(QWidget):
    changed = Signal()
    COLS = 6

    def __init__(self, collapsed: set[str]):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self.collapsed = set(collapsed)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.hero_icon = QLabel()
        self.hero_icon.setFixedSize(44, 25)
        self.hero_name = QLabel("")
        self.hero_name.setObjectName("name")
        head.addWidget(self.hero_icon)
        head.addWidget(self.hero_name, 1)
        v.addLayout(head)
        self.msg = QLabel("")
        self.msg.setObjectName("state")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)

        self.sections: dict[str, _Section] = {}
        self.item_cells: dict[str, list[QLabel]] = {}
        for key in ITEM_KEYS:
            sec = self._section(key, "")
            row = QHBoxLayout(sec.content)
            row.setContentsMargins(0, 0, 0, 2)
            row.setSpacing(3)
            cells = []
            for _ in range(self.COLS):
                c = QLabel()
                c.setFixedSize(36, 26)
                c.setScaledContents(True)
                row.addWidget(c)
                cells.append(c)
            row.addStretch(1)
            self.item_cells[key] = cells
            v.addWidget(sec)

        sec = self._section("skills", "MAX SKILLS IN THIS ORDER")
        srow = QHBoxLayout(sec.content)
        srow.setContentsMargins(0, 0, 0, 2)
        srow.setSpacing(4)
        self.skills = []
        for i in range(4):
            arrow = QLabel("›")
            arrow.setObjectName("pos")
            c = QLabel()
            c.setFixedSize(28, 28)
            c.setScaledContents(True)
            if i:
                srow.addWidget(arrow)
            srow.addWidget(c)
            self.skills.append((arrow, c))
        srow.addStretch(1)
        v.addWidget(sec)

        sec = self._section("talents", "TALENTS")
        tv = QVBoxLayout(sec.content)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(1)
        self.talents = []
        for _ in range(4):
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            lv = QLabel()
            lv.setObjectName("score")
            lv.setFixedWidth(18)
            name = QLabel()
            name.setObjectName("pos")
            share = QLabel()
            share.setObjectName("pos")
            share.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lv)
            row.addWidget(name, 1)
            row.addWidget(share)
            tv.addWidget(holder)
            self.talents.append((holder, lv, name, share))
        v.addWidget(sec)

    def _section(self, key: str, title: str) -> _Section:
        sec = _Section(key, title, key in self.collapsed)
        sec.toggled.connect(self._toggled)
        self.sections[key] = sec
        return sec

    def _toggled(self, key: str, collapsed: bool):
        (self.collapsed.add if collapsed else self.collapsed.discard)(key)
        self.changed.emit()

    def set_message(self, text: str):
        self.hero_icon.clear()
        self.hero_name.setText("")
        self.msg.setText(text)
        self.msg.setVisible(True)
        for sec in self.sections.values():
            sec.setVisible(False)

    def set_build(self, hero_name: str, hero_icon: QIcon, sections: list, skills=(), talents=(), note=""):
        self.hero_icon.setPixmap(hero_icon.pixmap(QSize(44, 25)))
        self.hero_name.setText(hero_name)
        self.msg.setText(note)
        self.msg.setVisible(bool(note))
        for i, key in enumerate(ITEM_KEYS):
            label, rows = sections[i] if i < len(sections) else ("", [])
            sec = self.sections[key]
            sec.setVisible(bool(rows))
            sec.set_title(label)
            for j, c in enumerate(self.item_cells[key]):
                if j < len(rows):
                    c.setPixmap(rows[j][0])
                    c.setToolTip(rows[j][1])
                    c.setVisible(True)
                else:
                    c.clear()
                    c.setVisible(False)
        self.sections["skills"].setVisible(bool(skills))
        for i, (arrow, c) in enumerate(self.skills):
            on = i < len(skills)
            arrow.setVisible(on)
            c.setVisible(on)
            if on:
                c.setPixmap(skills[i][0])
                c.setToolTip(skills[i][1])
        self.sections["talents"].setVisible(bool(talents))
        for i, (holder, lv, name, share) in enumerate(self.talents):
            on = i < len(talents)
            holder.setVisible(on)
            if on:
                level, text, pct = talents[i]
                lv.setText(str(level))
                name.setText(name.fontMetrics().elidedText(text, Qt.ElideRight, 165))
                name.setToolTip(text)
                share.setText(f"{pct:.0f}%" if pct is not None else "")


class Overlay(QWidget):
    pos_clicked = Signal(int)
    sections_changed = Signal(bool, bool)
    build_toggled = Signal(bool)
    collapsed_changed = Signal(list)
    hidden = Signal()
    moved = Signal(QPoint)

    def __init__(self, show_picks: bool = True, show_bans: bool = False, collapsed: set[str] | None = None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Dota Draft Helper — Overlay")
        self.setObjectName("ov")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(OVERLAY_STYLE)
        self.setWindowOpacity(0.92)
        self.setFixedWidth(250)
        self._drag: QPoint | None = None
        if not show_picks and not show_bans:
            show_picks = True

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(3)
        self.title = QLabel("DRAFT")
        self.title.setObjectName("title")
        self.title.setToolTip("Drag to move")
        head.addWidget(self.title)
        head.addStretch(1)
        self.btn_picks = self._toggle("Picks", show_picks, "Show suggested picks")
        self.btn_bans = self._toggle("Bans", show_bans, "Show suggested bans")
        self.btn_build = QPushButton("Build")
        self.btn_build.setToolTip("Switch between the draft and the build for your hero\n"
                                  "(switches to the build by itself when the draft is over)")
        self.btn_build.clicked.connect(self._build_clicked)
        head.addWidget(self.btn_picks)
        head.addWidget(self.btn_bans)
        head.addWidget(self.btn_build)
        head.addWidget(self._x("–", "Collapse / expand", self._toggle_fold))
        head.addWidget(self._x("×", "Hide overlay", self._hide))
        v.addLayout(head)

        self.body = QWidget()
        self.body.setObjectName("body")
        self.body.setStyleSheet("#body { background: transparent; }")
        bv = QVBoxLayout(self.body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(4)

        self.pos_row = QWidget()
        self.pos_row.setStyleSheet("background: transparent;")
        prow = QHBoxLayout(self.pos_row)
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(2)
        self.pos_group = QButtonGroup(self)
        for i, name in enumerate(["All", "1", "2", "3", "4", "5"]):
            b = QPushButton(name)
            b.setCheckable(True)
            self.pos_group.addButton(b, i)
            prow.addWidget(b)
        self.pos_group.idClicked.connect(self.pos_clicked.emit)
        bv.addWidget(self.pos_row)

        self.picks = _List("PICKS")
        self.bans = _List("BANS")
        bv.addWidget(self.picks)
        bv.addWidget(self.bans)
        self.build = _Build(collapsed or set())
        self.build.set_message("Your hero is not known yet.")
        self.build.changed.connect(self._build_changed)
        bv.addWidget(self.build)

        self.state = QLabel("")
        self.state.setObjectName("state")
        bv.addWidget(self.state)
        v.addWidget(self.body)
        self._last = None
        self._build_on = False
        self._apply_sections()

    def _toggle(self, text, on, tip):
        b = QPushButton(text)
        b.setCheckable(True)
        b.setChecked(on)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False, btn=b: self._section_clicked(btn))
        return b

    def _x(self, text, tip, slot):
        b = QPushButton(text)
        b.setObjectName("x")
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _section_clicked(self, btn):
        if not self.btn_picks.isChecked() and not self.btn_bans.isChecked():
            btn.setChecked(True)
            return
        self._apply_sections()
        self.sections_changed.emit(self.btn_picks.isChecked(), self.btn_bans.isChecked())


    def _build_clicked(self):
        self._build_on = not self._build_on
        self._apply_sections()
        self.build_toggled.emit(self._build_on)

    def set_build_mode(self, on: bool):
        if self._build_on != on:
            self._build_on = on
            self._apply_sections()

    def build_mode(self) -> bool:
        return self._build_on

    def set_build(self, hero_name, hero_icon, sections, skills=(), talents=(), note=""):
        self.build.set_build(hero_name, hero_icon, sections, skills, talents, note)
        self._fit()

    def set_build_message(self, text: str):
        self.build.set_message(text)
        self._fit()

    def _build_changed(self):
        self._fit()
        self.collapsed_changed.emit(sorted(self.build.collapsed))

    def _apply_sections(self):
        b = self._build_on
        self.title.setText("BUILD" if b else "DRAFT")
        self.btn_build.setText("‹ Draft" if b else "Build ›")
        self.btn_picks.setVisible(not b)
        self.btn_bans.setVisible(not b)
        self.build.setVisible(b)
        self.state.setVisible(not b)
        self.picks.setVisible(self.btn_picks.isChecked() and not b)
        self.pos_row.setVisible(self.btn_picks.isChecked() and not b)
        self.bans.setVisible(self.btn_bans.isChecked() and not b)
        if self._last:
            self.show_rows(*self._last)
        self._fit()

    def _fit(self):
        self.build.adjustSize()
        self.body.adjustSize()
        self.adjustSize()

    def _toggle_fold(self):
        self.body.setVisible(not self.body.isVisible())
        self._fit()

    def _hide(self):
        self.hide()
        self.hidden.emit()


    def show_rows(self, picks: list[dict], bans: list[dict], icons: dict[int, QIcon], state: str,
                  pos_checked: int, pos_taken: set[int]):
        self._last = (picks, bans, icons, state, pos_checked, pos_taken)
        both = self.btn_picks.isChecked() and self.btn_bans.isChecked()
        count = ROWS_BOTH if both else ROWS
        for i in range(6):
            b = self.pos_group.button(i)
            b.setEnabled(i not in pos_taken)
            b.setChecked(i == pos_checked)
        self.picks.fill(picks, icons, True, count, both)
        self.bans.fill(bans, icons, False, count, both)
        self.state.setText(state)
        self._fit()


    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.frameGeometry().topLeft())
