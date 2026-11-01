############################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# http://flatcam.org                                       #
# MIT Licence                                              #
############################################################

"""
Cutting tool library: the end mills, V-bits and drill bits on hand, and
which of them is used for isolation routing, the board outline and drilling.

Shown in the "Tool" tab. Everything is stored in millimetres in
``app.defaults`` (and so in defaults.json) and converted to the units of
the object being processed when it is used.
"""

import copy
import math

from PyQt6 import QtCore, QtWidgets

ENDMILL = "endmill"
VBIT = "vbit"
DRILL = "drill"
TYPE_NAMES = {ENDMILL: "End mill", VBIT: "V-bit", DRILL: "Drill bit"}

# Starting library. Dimensions in mm, feeds in mm/min. "feed" is across the
# board, "plunge" down into it (and all a drill bit does).
DEFAULT_TOOLS = [
    {"id": 1, "name": "V-bit 30° 0.1mm", "type": VBIT, "dia": 0.1, "angle": 30.0,
     "feed": 100.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.1},
    {"id": 2, "name": "End mill 0.8mm", "type": ENDMILL, "dia": 0.8, "angle": 0.0,
     "feed": 200.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.5},
    {"id": 3, "name": "End mill 2.0mm", "type": ENDMILL, "dia": 2.0, "angle": 0.0,
     "feed": 300.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.6},
    {"id": 4, "name": "Drill 0.6mm", "type": DRILL, "dia": 0.6, "angle": 0.0,
     "feed": 60.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.0},
    {"id": 5, "name": "Drill 0.8mm", "type": DRILL, "dia": 0.8, "angle": 0.0,
     "feed": 60.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.0},
    {"id": 6, "name": "Drill 1.0mm", "type": DRILL, "dia": 1.0, "angle": 0.0,
     "feed": 60.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.0},
    {"id": 7, "name": "Drill 1.2mm", "type": DRILL, "dia": 1.2, "angle": 0.0,
     "feed": 60.0, "plunge": 60.0, "spindle": None, "depthperpass": 0.0},
]

# Operation -> tool assignment and cut depth (mm, negative).
# A "tool" of None means: use the settings on the object itself.
DEFAULT_OPERATIONS = {
    "isolation": {"tool": 1, "cutz": -0.1},
    "outline": {"tool": 3, "cutz": -1.8},
    "drilling": {"enabled": True, "cutz": -1.8},
}

# How every job ends: lift to z_end (mm above the work), then go to X0 Y0
# if return_to_origin. Also, how new Geometry objects start out: with their
# cutting moves split (if split) into pieces no longer than segment_length
# (mm), so a controller's height map (auto-leveling) corrects Z all along
# them, not just at their ends. Each object can change this.
DEFAULT_JOB_END = {"z_end": 15.0, "return_to_origin": True,
                   "split": True, "segment_length": 2.0}

# A hole and its drill bit may differ by this much (mm) without a warning.
DRILL_TOLERANCE = 0.1


def defaults():
    """Entries for App.defaults."""
    return {"cutting_tools": copy.deepcopy(DEFAULT_TOOLS),
            "cutting_operations": copy.deepcopy(DEFAULT_OPERATIONS),
            "cutting_job_end": copy.deepcopy(DEFAULT_JOB_END)}


def plunge_rate(tool):
    """A tool's plunge rate (mm/min). Tools saved before there was one plunge at their feed."""
    plunge = tool.get("plunge")
    return tool["feed"] if plunge is None else plunge


def from_mm(value, units):
    """Converts a length (or feed rate) in mm to ``units`` ("MM" or "IN")."""
    return value if units.upper() == "MM" else value / 25.4


def cut_width(tool, cutz):
    """
    Width of the cut made by ``tool`` at depth ``cutz`` (both mm). For a
    V-bit it grows with depth from the tip diameter.
    """
    if tool["type"] == VBIT:
        half_angle = math.radians(tool["angle"]) / 2
        return tool["dia"] + 2 * abs(cutz) * math.tan(half_angle)
    return tool["dia"]


class DistanceEntry(QtWidgets.QLineEdit):
    """
    Typed entry for a distance in mm, greater than zero. Either sign may be
    typed; it shows and returns the size.
    """

    def value(self):
        """
        :raises ValueError: If the text is not a number other than zero.
        """
        distance = abs(float(self.text().strip()))
        if distance == 0:
            raise ValueError("must be greater than zero")
        return distance

    def setValue(self, value):
        self.setText("%g" % abs(value))


class CutDepthEntry(DistanceEntry):
    """
    A DistanceEntry for a cut depth: value() returns it as a (negative) Cut Z.
    """

    def value(self):
        return -DistanceEntry.value(self)


class ToolLibrary(QtWidgets.QWidget):
    """
    The cutting tool library and its editor in the "Tool" tab.
    """

    # Emitted whenever a tool or an operation assignment changes.
    changed = QtCore.pyqtSignal()

    COLUMNS = ["Name", "Type", "Dia.\n(mm)", "Angle\n(°)", "Feed\n(mm/min)",
               "Plunge\n(mm/min)", "Spindle\n(RPM)", "Depth/pass\n(mm)"]
    FIELDS = ["name", "type", "dia", "angle", "feed", "plunge", "spindle", "depthperpass"]
    # Fields that don't apply to some types of tool
    NOT_FOR = {"angle": (ENDMILL, DRILL), "feed": (DRILL,), "depthperpass": (DRILL,)}

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._updating = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        ## Tools
        layout.addWidget(QtWidgets.QLabel("<b>Cutting Tools</b>"))
        hint = QtWidgets.QLabel(
            "Tools available for milling the board. For a V-bit, Dia. is the "
            "tip diameter; the cut gets wider with depth. Feed is the speed "
            "across the board, Plunge the speed down into it.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(220)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        # Scroll sideways rather than widen the whole side panel
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.table.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.table)

        buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add Tool")
        self.add_button.clicked.connect(self.on_add_tool)
        self.remove_button = QtWidgets.QPushButton("Remove Tool")
        self.remove_button.clicked.connect(self.on_remove_tool)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        ## Operations
        layout.addWidget(QtWidgets.QLabel("<b>Operations</b>"))
        grid = QtWidgets.QGridLayout()
        layout.addLayout(grid)
        grid.addWidget(QtWidgets.QLabel("Tool"), 0, 1)
        depth_label = QtWidgets.QLabel("Depth (mm)")
        depth_label.setToolTip("How deep to cut below the copper surface.\n"
                               "Type a number and press Enter.")
        grid.addWidget(depth_label, 0, 2)

        self.isolation_combo = QtWidgets.QComboBox()
        self.isolation_cutz = self._depth_entry()
        self.isolation_width = QtWidgets.QLabel()
        grid.addWidget(QtWidgets.QLabel("Isolation routing:"), 1, 0)
        grid.addWidget(self.isolation_combo, 1, 1)
        grid.addWidget(self.isolation_cutz, 1, 2)
        grid.addWidget(self.isolation_width, 2, 1, 1, 2)

        self.outline_combo = QtWidgets.QComboBox()
        self.outline_cutz = self._depth_entry()
        grid.addWidget(QtWidgets.QLabel("Board outline:"), 3, 0)
        grid.addWidget(self.outline_combo, 3, 1)
        grid.addWidget(self.outline_cutz, 3, 2)

        self.drilling_cb = QtWidgets.QCheckBox("Drill bits above")
        self.drilling_cb.setToolTip(
            "Drill each hole with the drill bit closest\n"
            "to its size, changing bits as needed.")
        self.drilling_cutz = self._depth_entry()
        grid.addWidget(QtWidgets.QLabel("Drilling:"), 4, 0)
        grid.addWidget(self.drilling_cb, 4, 1)
        grid.addWidget(self.drilling_cutz, 4, 2)

        note = QtWidgets.QLabel(
            "These replace the tool settings of Gerber and Excellon objects. "
            "Choose \"(object settings)\" to set an operation up on the object instead.")
        note.setWordWrap(True)
        layout.addWidget(note)

        ## Job end
        layout.addWidget(QtWidgets.QLabel("<b>End of every job</b>"))
        end_grid = QtWidgets.QGridLayout()
        layout.addLayout(end_grid)
        end_label = QtWidgets.QLabel("Lift to height (mm):")
        end_label.setToolTip("Height above the work to raise the tool to when a job\n"
                             "ends, before the spindle stops and any move back to\n"
                             "X0 Y0. Never lower than the job's travel height.")
        self.end_height = DistanceEntry()
        self.end_height.setMaximumWidth(80)
        self.return_cb = QtWidgets.QCheckBox("Then return to X0 Y0")
        end_grid.addWidget(end_label, 0, 0)
        end_grid.addWidget(self.end_height, 0, 1)
        end_grid.addWidget(self.return_cb, 1, 0, 1, 2)
        end_grid.setColumnStretch(2, 1)

        ## Auto-leveling
        layout.addWidget(QtWidgets.QLabel("<b>Auto-leveling</b>"))
        level_grid = QtWidgets.QGridLayout()
        layout.addLayout(level_grid)
        self.split_cb = QtWidgets.QCheckBox("Split cuts longer than (mm):")
        self.split_cb.setToolTip(
            "Cutting moves are broken into pieces no longer than this.\n"
            "A controller applying a height map only corrects Z at the\n"
            "points in the G-code, so long straight cuts drift off the\n"
            "surface between their ends. Use no more than the height\n"
            "map's probe spacing. Shorter pieces run slower.")
        self.segment_length_entry = DistanceEntry()
        self.segment_length_entry.setMaximumWidth(80)
        level_grid.addWidget(self.split_cb, 0, 0)
        level_grid.addWidget(self.segment_length_entry, 0, 1)
        level_grid.setColumnStretch(2, 1)
        level_note = QtWidgets.QLabel(
            "For new isolation, outline and other geometry. Change it for one "
            "object on its Selected tab.")
        level_note.setWordWrap(True)
        layout.addWidget(level_note)
        layout.addStretch()

        self.isolation_combo.activated.connect(self.on_operations_changed)
        self.outline_combo.activated.connect(self.on_operations_changed)
        self.drilling_cb.toggled.connect(self.on_operations_changed)
        for entry in (self.isolation_cutz, self.outline_cutz, self.drilling_cutz, self.end_height,
                      self.segment_length_entry):
            # Only when done typing, so a half-typed number is never used
            entry.editingFinished.connect(self.on_operations_changed)
        self.return_cb.toggled.connect(self.on_operations_changed)
        self.split_cb.toggled.connect(self.on_operations_changed)

        for tool in self.tools():
            tool.setdefault("plunge", plunge_rate(tool))

        self.refresh()

    @staticmethod
    def _depth_entry():
        entry = CutDepthEntry()
        entry.setMaximumWidth(80)
        return entry

    ####################
    ### Data access  ###
    ####################

    def tools(self):
        return self.app.defaults["cutting_tools"]

    def operations(self):
        return self.app.defaults["cutting_operations"]

    def job_end(self):
        return self.app.defaults["cutting_job_end"]

    def end_settings(self, units):
        """
        How every job ends, in ``units``. Keys: z_end (height to lift to),
        return_to_origin, segment_length (longest cutting move).
        """
        end = self.job_end()
        return {"z_end": from_mm(end["z_end"], units),
                "return_to_origin": end["return_to_origin"]}

    def split_settings(self, units):
        """
        How new Geometry objects split their cutting moves, in ``units``.
        Keys: split (bool), segment_length (longest move).
        """
        return {"split": self.split(), "segment_length": from_mm(self.segment_length(), units)}

    def split(self):
        """Whether to split. Settings saved before there was a choice get the default."""
        return self.job_end().setdefault("split", DEFAULT_JOB_END["split"])

    def segment_length(self):
        """Longest cutting move (mm). Settings saved before there was one get the default."""
        return self.job_end().setdefault("segment_length", DEFAULT_JOB_END["segment_length"])

    def get_tool(self, tool_id):
        for tool in self.tools():
            if tool["id"] == tool_id:
                return tool
        return None

    def _milling_settings(self, operation, units):
        op = self.operations()[operation]
        tool = self.get_tool(op["tool"])
        if tool is None:
            return None
        cutz = op["cutz"]
        depthperpass = tool["depthperpass"]
        return {
            "name": tool["name"],
            "dia": from_mm(cut_width(tool, cutz), units),
            "cutz": from_mm(cutz, units),
            "feedrate": from_mm(tool["feed"], units),
            "feedrate_z": from_mm(plunge_rate(tool), units),
            "spindlespeed": tool["spindle"],
            "multidepth": 0 < depthperpass < abs(cutz),
            "depthperpass": from_mm(depthperpass, units),
        }

    def isolation_settings(self, units):
        """
        Tool settings for isolation routing in ``units``, or None to use the
        object's own settings. Keys: name, dia (cut width), cutz, feedrate,
        feedrate_z (plunge rate), spindlespeed, multidepth, depthperpass.
        """
        return self._milling_settings("isolation", units)

    def outline_settings(self, units):
        """Like isolation_settings(), for cutting out the board outline."""
        return self._milling_settings("outline", units)

    def drill_bits(self):
        return sorted((t for t in self.tools() if t["type"] == DRILL), key=lambda t: t["dia"])

    def drilling_settings(self, units):
        """
        Drilling settings in ``units``, or None to use the object's own
        settings. Keys: cutz, and bits: a list (by diameter) of dicts with
        id, name, dia, feedrate (the bit's plunge rate) and spindlespeed.
        """
        op = self.operations()["drilling"]
        bits = self.drill_bits()
        if not op["enabled"] or not bits:
            return None
        return {
            "cutz": from_mm(op["cutz"], units),
            "bits": [{"id": b["id"], "name": b["name"], "dia": from_mm(b["dia"], units),
                      "feedrate": from_mm(plunge_rate(b), units), "spindlespeed": b["spindle"]}
                     for b in bits],
        }

    @staticmethod
    def match_drill_bit(hole_dia, bits):
        """The bit from ``bits`` (see drilling_settings()) closest in size to the hole."""
        return min(bits, key=lambda b: abs(b["dia"] - hole_dia))

    ####################
    ### Editor       ###
    ####################

    def refresh(self):
        """
        Rebuilds the editor from app.defaults, keeping the table's current
        cell and scroll position.
        """
        table = self.table
        row, col = table.currentRow(), table.currentColumn()
        vscroll = table.verticalScrollBar().value()
        hscroll = table.horizontalScrollBar().value()

        self._updating = True
        try:
            table.setRowCount(0)
            for tool in self.tools():
                self._append_row(tool)
            table.resizeRowsToContents()
            if row >= 0 and table.rowCount():
                table.setCurrentCell(min(row, table.rowCount() - 1), max(col, 0))
            table.verticalScrollBar().setValue(vscroll)
            table.horizontalScrollBar().setValue(hscroll)
            self._refresh_operations()
        finally:
            self._updating = False

    def _append_row(self, tool):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, field in enumerate(self.FIELDS):
            if field == "type":
                combo = QtWidgets.QComboBox()
                for key, label in TYPE_NAMES.items():
                    combo.addItem(label, key)
                combo.setCurrentIndex(combo.findData(tool["type"]))
                combo.currentIndexChanged.connect(
                    lambda _, c=combo: self.on_type_changed(c))
                self.table.setCellWidget(row, col, combo)
                continue
            value = tool[field]
            item = QtWidgets.QTableWidgetItem("" if value is None else str(value))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, tool["id"])
            if tool["type"] in self.NOT_FOR.get(field, ()):
                item.setText("")
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

    def _refresh_operations(self):
        ops = self.operations()

        def fill(combo, types, selected):
            combo.clear()
            combo.addItem("(object settings)", None)
            for tool in self.tools():
                if tool["type"] in types:
                    combo.addItem(tool["name"], tool["id"])
            index = combo.findData(selected)
            combo.setCurrentIndex(index if index >= 0 else 0)

        fill(self.isolation_combo, (ENDMILL, VBIT), ops["isolation"]["tool"])
        fill(self.outline_combo, (ENDMILL,), ops["outline"]["tool"])
        self.isolation_cutz.setValue(ops["isolation"]["cutz"])
        self.outline_cutz.setValue(ops["outline"]["cutz"])
        self.drilling_cb.setChecked(ops["drilling"]["enabled"])
        self.drilling_cutz.setValue(ops["drilling"]["cutz"])
        self.end_height.setValue(self.job_end()["z_end"])
        self.return_cb.setChecked(self.job_end()["return_to_origin"])
        self.split_cb.setChecked(self.split())
        self.segment_length_entry.setValue(self.segment_length())
        self.segment_length_entry.setEnabled(self.split())

        # Keep assignments to tools that were removed or changed type from lingering
        ops["isolation"]["tool"] = self.isolation_combo.currentData()
        ops["outline"]["tool"] = self.outline_combo.currentData()

        iso = self.isolation_settings("MM")
        self.isolation_width.setText("" if iso is None else "Cut width: %.3f mm" % iso["dia"])

    def _row_tool(self, row):
        return self.tools()[row]

    def on_item_changed(self, item):
        if self._updating:
            return
        tool = self._row_tool(item.row())
        field = self.FIELDS[item.column()]
        text = item.text().strip()
        try:
            if field == "name":
                if not text:
                    raise ValueError("A tool needs a name.")
                tool["name"] = text
            elif field == "spindle":
                tool["spindle"] = int(text) if text else None
            else:
                value = abs(float(text))
                if field in ("dia", "feed", "plunge") and value == 0:
                    raise ValueError("must be greater than zero.")
                tool[field] = value
        except ValueError as e:
            self.app.inform.emit("[warning] Invalid value for %s: %s" % (field, e))
        QtCore.QTimer.singleShot(0, self.refresh)
        self.changed.emit()

    def on_type_changed(self, combo):
        if self._updating:
            return
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 1) is combo:
                tool = self._row_tool(row)
                tool["type"] = combo.currentData()
                if tool["type"] == VBIT and not tool["angle"]:
                    tool["angle"] = 30.0
                break
        QtCore.QTimer.singleShot(0, self.refresh)
        self.changed.emit()

    def on_add_tool(self):
        new_id = max([t["id"] for t in self.tools()], default=0) + 1
        self.tools().append({"id": new_id, "name": "New tool %d" % new_id, "type": ENDMILL,
                             "dia": 1.0, "angle": 0.0, "feed": 200.0, "plunge": 60.0,
                             "spindle": None, "depthperpass": 0.5})
        self.refresh()
        self.table.editItem(self.table.item(self.table.rowCount() - 1, 0))
        self.changed.emit()

    def on_remove_tool(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            self.app.inform.emit("Select the tools to remove first.")
            return
        for row in rows:
            del self.tools()[row]
        self.refresh()
        self.changed.emit()

    def on_operations_changed(self, *args):
        if self._updating:
            return
        ops = self.operations()
        ops["isolation"]["tool"] = self.isolation_combo.currentData()
        ops["outline"]["tool"] = self.outline_combo.currentData()
        ops["drilling"]["enabled"] = self.drilling_cb.isChecked()
        for name, entry in (("isolation", self.isolation_cutz), ("outline", self.outline_cutz),
                            ("drilling", self.drilling_cutz)):
            try:
                ops[name]["cutz"] = entry.value()
            except ValueError:
                self.app.inform.emit("[warning] Invalid %s depth: %r. Enter a number greater than zero."
                                     % (name, entry.text()))
        try:
            self.job_end()["z_end"] = self.end_height.value()
        except ValueError:
            self.app.inform.emit("[warning] Invalid end height: %r. Enter a number greater than zero."
                                 % self.end_height.text())
        self.job_end()["return_to_origin"] = self.return_cb.isChecked()
        self.job_end()["split"] = self.split_cb.isChecked()
        try:
            self.job_end()["segment_length"] = self.segment_length_entry.value()
        except ValueError:
            self.app.inform.emit("[warning] Invalid cut length: %r. Enter a number greater than zero."
                                 % self.segment_length_entry.text())
        # Shows the stored values again, which also undoes an invalid entry
        QtCore.QTimer.singleShot(0, self.refresh)
        self.changed.emit()
