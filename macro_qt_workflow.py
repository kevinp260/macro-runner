"""PySide6 structured workflow tree with validated group drag-and-drop.

Tree items represent executable Action objects or complete control blocks.
The legacy flat marker layout exists only at the import/export boundary.
"""
from copy import deepcopy
from dataclasses import asdict
import json

from PySide6.QtCore import Qt, QByteArray, QMimeData, QSignalBlocker, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView, QListWidget, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QFileDialog
)

from macro_model import Action
from macro_workflow import WorkflowNode, default_node, from_actions, to_actions
from macro_flow import OPENERS

NODE_ROLE = int(Qt.ItemDataRole.UserRole)
BREAKPOINT_ROLE = NODE_ROLE + 1  # Editor-only; never included in macro JSON.


def pack_node(node):
    """Store JSON text so native Qt drag/drop can serialize the item safely."""
    return json.dumps({
        "action": asdict(node.action),
        "else_marker": asdict(node.else_marker) if node.else_marker else None,
        "end_marker": asdict(node.end_marker) if node.end_marker else None,
    })


def unpack_node(item):
    payload = item.data(0, NODE_ROLE)
    if payload == "else_branch":
        return None
    if not isinstance(payload, str):
        raise ValueError("Unrecognized action item in workflow.")
    try:
        values = json.loads(payload)
        return WorkflowNode(
            Action(**values["action"]),
            else_marker=Action(**values["else_marker"]) if values["else_marker"] else None,
            end_marker=Action(**values["end_marker"]) if values["end_marker"] else None,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Cannot restore dropped workflow item.") from exc


PALETTE_MIME = "application/x-macrorunner-action-kind"
KINDS = [
    ("Click", "click"), ("Click image", "click_image"),
    ("Wait", "wait"), ("Wait until", "wait_until"),
    ("Press / Type", "key"), ("Hold key", "key_down"),
    ("Release key", "key_up"), ("Move mouse", "move"),
    ("Scroll", "scroll"), ("Drag", "drag"),
    ("Set clipboard text", "clipboard_set"), ("Paste clipboard / text", "clipboard_paste"),
    ("Read clipboard to variable", "clipboard_read"),
    ("Open application / file / URL", "launch"),
    ("Wait for window", "wait_window"),
    ("File exists", "file_check"), ("Wait for file", "file_wait"),
    ("Copy file", "file_copy"), ("Move file", "file_move"),
    ("Create folder", "folder_create"),
    ("Repeat block", "loop_start"),
    ("If / Else", "if_start"), ("Repeat until", "until_start"),
    ("Watch region changes", "watch_start"),
]

TITLES = {
    "click": "Mouse click", "click_image": "Click image",
    "wait": "Wait", "wait_until": "Wait until",
    "key": "Keyboard", "key_down": "Hold key", "key_up": "Release key",
    "move": "Move", "scroll": "Scroll", "drag": "Drag",
    "clipboard_set": "Set clipboard text", "clipboard_paste": "Paste clipboard / text",
    "clipboard_read": "Read clipboard to variable",
    "launch": "Open application / file / URL",
    "wait_window": "Wait for window",
    "file_check": "File exists", "file_wait": "Wait for file",
    "file_copy": "Copy file", "file_move": "Move file",
    "folder_create": "Create folder",
    "loop_start": "Repeat block", "if_start": "Condition",
    "until_start": "Repeat until", "watch_start": "Watch region changes"
}


def description(action):
    kind = action.kind
    if kind == "click":
        detail = f"{action.button} at ({action.x}, {action.y})"
    elif kind == "click_image":
        detail = action.image_path or "Choose reference image"
        if action.result_variable:
            detail += f" → {action.result_variable}"
    elif kind in ("wait",):
        detail = f"{action.seconds:g} seconds"
    elif kind in ("wait_until", "if_start", "until_start"):
        target = action.image_path if action.condition_source == "image" else (
            f"pixel ({action.pixel_x}, {action.pixel_y}) {action.pixel_color}")
        detail = f"{action.match_mode.replace('_', ' ')} · {target}"
    elif kind in ("key", "key_down", "key_up"):
        detail = action.keys
    elif kind == "clipboard_read":
        detail = f"text → {action.result_variable or 'Choose text variable'}"
    elif kind == "clipboard_set":
        detail = "clipboard text (hidden)"
    elif kind == "clipboard_paste":
        detail = ("existing clipboard" if action.clipboard_text is None
                  else "temporary text (hidden)" if action.clipboard_restore
                  else "text (leave on clipboard)")
    elif kind in ("file_check", "file_wait", "file_copy",
                  "file_move", "folder_create"):
        from pathlib import Path
        source = Path(action.file_path).name if action.file_path else "Choose path"
        if kind in ("file_copy", "file_move"):
            target = (Path(action.file_destination).name
                      if action.file_destination else "Choose destination")
            detail = f"{source} → {target}" + (
                " · overwrite" if action.file_overwrite else " · no overwrite")
        elif kind == "file_wait":
            detail = f"{source} · {action.timeout:g}s timeout"
        else:
            detail = source
    elif kind == "wait_window":
        source = ("workflow target" if action.window_wait_source == "workflow"
                  else action.window_wait_title or "Choose window")
        detail = f"{action.window_wait_state} · {source}"
    elif kind == "launch":
        from pathlib import Path
        from urllib.parse import urlsplit
        detail = (urlsplit(action.launch_target).hostname or "Configure URL"
                  if action.launch_mode == "url" and action.launch_target
                  else Path(action.launch_target).name or "Configure target")
        detail = f"{action.launch_mode} · {detail}"
    elif kind == "watch_start":
        detail = (f"({action.region_x}, {action.region_y}) "
                  f"{action.region_w}×{action.region_h} · "
                  f"every {action.poll_interval:g}s · "
                  f"{action.watch_change_percent:g}% changed")
    elif kind == "loop_start":
        detail = f"{action.repeats} cycles"
    elif kind == "scroll":
        detail = f"{action.scroll_amount:+} steps"
    elif kind == "move":
        detail = f"({action.x}, {action.y})"
    elif kind == "drag":
        detail = f"({action.x}, {action.y}) → ({action.to_x}, {action.to_y})"
    else:
        detail = ""
    base = action.name.strip() or TITLES.get(kind, kind)
    repeats = f" · ×{action.repeats}" if (kind not in OPENERS and action.repeats > 1) else ""
    policy = (
        f" · retry {action.retry_count}×" if action.failure_policy == "retry"
        else " · skip on error" if action.failure_policy == "skip" else "")
    return f"{base}  ·  {detail}{repeats}{policy}" + (
        "" if action.enabled else "  [disabled]")


class ActionPalette(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        for title, kind in KINDS:
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, kind)
            self.addItem(item)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(PALETTE_MIME,
                     QByteArray(item.data(Qt.ItemDataRole.UserRole).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class WorkflowTree(QTreeWidget):
    actions_changed = Signal(list)
    invalid_change = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setIndentation(22)
        self._snapshot = []
        self.setAlternatingRowColors(False)
        self.itemChanged.connect(self._check_state_changed)

    @staticmethod
    def _set_action_label(item, action):
        marker = "●  " if item.data(0, BREAKPOINT_ROLE) else ""
        item.setText(0, marker + description(action))

    @staticmethod
    def _decorate_leaf(item, action):
        """Show disabled commands without making them unselectable/editable."""
        font = item.font(0)
        font.setStrikeOut(not action.enabled)
        font.setItalic(not action.enabled)
        item.setFont(0, font)
        state = ("Enabled — uncheck to skip this action."
                 if action.enabled else
                 "Disabled — check to include this action.")
        if item.data(0, BREAKPOINT_ROLE):
            state += (" Breakpoint: pauses before execution."
                      if action.enabled else
                      " Breakpoint is inactive while disabled.")
        item.setToolTip(0, state + " F9 toggles a breakpoint.")

    def _check_state_changed(self, item, column):
        """Persist a checkbox change through the normal history/change path."""
        if column != 0 or item.data(0, NODE_ROLE) == "else_branch":
            return
        node = unpack_node(item)
        if node.is_group:
            return
        enabled = item.checkState(0) == Qt.CheckState.Checked
        if node.action.enabled == enabled:
            return
        previous = deepcopy(self._snapshot)
        node.action.enabled = enabled
        with QSignalBlocker(self):
            item.setData(0, NODE_ROLE, pack_node(node))
            self._set_action_label(item, node.action)
            self._decorate_leaf(item, node.action)
        self._commit(previous)

    def _insert_node(self, parent, node):
        item = QTreeWidgetItem()
        item.setData(0, NODE_ROLE, pack_node(node))
        self._set_action_label(item, node.action)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled |
                      Qt.ItemFlag.ItemIsDropEnabled)
        if node.is_group:
            # Control blocks cannot be disabled; their child actions can.
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, (Qt.CheckState.Checked if node.action.enabled
                                   else Qt.CheckState.Unchecked))
            self._decorate_leaf(item, node.action)
        if parent is None:
            self.addTopLevelItem(item)
        elif (parent.childCount() and
              parent.child(parent.childCount() - 1).data(0, NODE_ROLE) == "else_branch"):
            parent.insertChild(parent.childCount() - 1, item)
        else:
            parent.addChild(item)
        for child in node.children:
            self._insert_node(item, child)
        if node.action.kind == "if_start" and node.otherwise is not None:
            branch = QTreeWidgetItem()
            branch.setText(0, "ELSE  ·  alternate branch")
            branch.setData(0, NODE_ROLE, "else_branch")
            branch.setFlags((branch.flags() | Qt.ItemFlag.ItemIsDropEnabled) &
                            ~(Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsUserCheckable))
            item.addChild(branch)
            for child in node.otherwise:
                self._insert_node(branch, child)
        item.setExpanded(True)
        return item

    def set_actions(self, actions):
        # Programmatic population must not generate individual checkbox edits.
        nodes = from_actions(actions)
        with QSignalBlocker(self):
            self._snapshot = deepcopy(actions)
            self.clear()
            for node in nodes:
                self._insert_node(None, node)

    def _read_children(self, parent):
        count = parent.childCount() if parent is not None else self.topLevelItemCount()
        return [self._read_node(parent.child(i) if parent is not None
                                else self.topLevelItem(i)) for i in range(count)]

    def _read_node(self, item):
        result = unpack_node(item)
        if result is None:
            raise ValueError("An Else branch cannot be moved outside an If group.")
        result.children = []
        result.otherwise = None
        if result.is_group:
            for index in range(item.childCount()):
                child = item.child(index)
                if child.data(0, NODE_ROLE) == "else_branch":
                    if result.action.kind != "if_start" or result.otherwise is not None:
                        raise ValueError("Else can only appear once inside an If block.")
                    result.otherwise = self._read_children(child)
                else:
                    if result.otherwise is not None:
                        raise ValueError("Move actions into the Else branch, not after it.")
                    result.children.append(self._read_node(child))
        elif item.childCount():
            raise ValueError("Only workflow blocks can contain actions.")
        return result

    def actions(self):
        return to_actions(self._read_children(None))

    def _commit(self, previous):
        try:
            after = self.actions()
        except ValueError as exc:
            self.set_actions(previous)
            self.invalid_change.emit(str(exc))
            return False
        if previous != after:
            self._snapshot = deepcopy(after)
            self.actions_changed.emit(after)
        return True

    def _prepare_node(self, kind):
        node = default_node(kind)
        if kind == "click_image":
            filename, _ = QFileDialog.getOpenFileName(
                self, "Choose reference image for Click Image", "",
                "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)"
            )
            if not filename:
                return None
            node.action.image_path = filename
        return node

    def insert_kind(self, kind):
        try:
            node = self._prepare_node(kind)
            if node is None:
                return
            current = self.currentItem()
            if current is None:
                self._insert_node(None, node)
            elif (unpack_node(current) is not None and
                  unpack_node(current).is_group):
                self._insert_node(current, node)
                current.setExpanded(True)
            else:
                parent = current.parent()
                item = self._insert_node(parent, node)
                if parent is None:
                    self.takeTopLevelItem(self.indexOfTopLevelItem(item))
                    self.insertTopLevelItem(self.indexOfTopLevelItem(current) + 1, item)
                else:
                    parent.removeChild(item)
                    parent.insertChild(parent.indexOfChild(current) + 1, item)
            self._commit(self._snapshot)
        except ValueError as exc:
            self.set_actions(self._snapshot)
            self.invalid_change.emit(str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PALETTE_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PALETTE_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        previous = deepcopy(self._snapshot)
        if event.mimeData().hasFormat(PALETTE_MIME):
            try:
                kind = bytes(event.mimeData().data(PALETTE_MIME)).decode("utf-8")
                node = self._prepare_node(kind)
                if node is None:
                    event.ignore()
                    return
                target = self.itemAt(event.position().toPoint())
                if target is None:
                    self._insert_node(None, node)
                else:
                    indicator = self.dropIndicatorPosition()
                    if indicator == QAbstractItemView.DropIndicatorPosition.OnItem:
                        # Dropping onto leaf items inserts after them.
                        data = unpack_node(target)
                        if data is None or data.is_group:
                            self._insert_node(target, node)
                        else:
                            parent = target.parent()
                            item = self._insert_node(parent, node)
                            if parent is None:
                                self.takeTopLevelItem(self.indexOfTopLevelItem(item))
                                self.insertTopLevelItem(self.indexOfTopLevelItem(target) + 1, item)
                            else:
                                parent.removeChild(item)
                                parent.insertChild(parent.indexOfChild(target) + 1, item)
                    else:
                        parent = target.parent()
                        item = self._insert_node(parent, node)
                        offset = int(indicator == QAbstractItemView.DropIndicatorPosition.BelowItem)
                        if parent is None:
                            self.takeTopLevelItem(self.indexOfTopLevelItem(item))
                            self.insertTopLevelItem(self.indexOfTopLevelItem(target) + offset, item)
                        else:
                            parent.removeChild(item)
                            parent.insertChild(parent.indexOfChild(target) + offset, item)
                if self._commit(previous):
                    event.acceptProposedAction()
                else:
                    event.ignore()
            except ValueError as exc:
                self.set_actions(previous)
                self.invalid_change.emit(str(exc))
                event.ignore()
            return
        # Internal moves use native Qt drag-and-drop; validate before persisting.
        super().dropEvent(event)
        self._commit(previous)

    def selected_nodes(self):
        return [item for item in self.selectedItems()
                if item.data(0, NODE_ROLE) != "else_branch"]

    def toggle_breakpoints(self):
        """Toggle transient breakpoints on selected executable tree actions."""
        chosen = self.selected_nodes()
        if not chosen:
            return
        nodes = [unpack_node(item) for item in chosen]
        if any(node.is_group for node in nodes):
            self.invalid_change.emit(
                "Breakpoints can be placed on executable actions, not control blocks.")
            return
        with QSignalBlocker(self):
            for item, node in zip(chosen, nodes):
                item.setData(0, BREAKPOINT_ROLE,
                             not bool(item.data(0, BREAKPOINT_ROLE)))
                self._set_action_label(item, node.action)
                self._decorate_leaf(item, node.action)

    def breakpoint_indices(self):
        """Return flat enabled action indices for an execution snapshot."""
        return {
            index for index, item in self.index_map().items()
            if index < len(self._snapshot)
            and self._snapshot[index].enabled
            and self._snapshot[index].kind not in
                ("loop_start", "loop_end", "if_start", "if_end", "else",
                 "until_start", "until_end", "watch_start", "watch_end")
            and bool(item.data(0, BREAKPOINT_ROLE))
        }

    def clear_breakpoints(self):
        """Reset debugging-only marks when opening another document."""
        with QSignalBlocker(self):
            for item in set(self.index_map().values()):
                if item.data(0, BREAKPOINT_ROLE):
                    item.setData(0, BREAKPOINT_ROLE, False)
                    node = unpack_node(item)
                    if node is not None:
                        self._set_action_label(item, node.action)
                        if not node.is_group:
                            self._decorate_leaf(item, node.action)

    def selected_action(self):
        items = self.selected_nodes()
        return unpack_node(items[0]).action if len(items) == 1 else None

    def update_selected_action(self, action):
        items = self.selected_nodes()
        if len(items) != 1:
            raise ValueError("Select one action to edit its properties.")
        old = deepcopy(self._snapshot)
        node = unpack_node(items[0])
        if node.action.kind != action.kind:
            raise ValueError("Change action type using the action palette.")
        node.action = deepcopy(action)
        with QSignalBlocker(self):
            items[0].setData(0, NODE_ROLE, pack_node(node))
            self._set_action_label(items[0], action)
            if not node.is_group:
                items[0].setCheckState(
                    0, Qt.CheckState.Checked if action.enabled
                    else Qt.CheckState.Unchecked)
                self._decorate_leaf(items[0], action)
        self._commit(old)

    def delete_selection(self):
        chosen = self.selected_nodes()
        if not chosen:
            return
        chosen = [item for item in chosen if not any(
            ancestor in chosen for ancestor in self._ancestors(item))]
        previous = deepcopy(self._snapshot)
        for item in chosen:
            parent = item.parent()
            if parent is None:
                self.takeTopLevelItem(self.indexOfTopLevelItem(item))
            else:
                parent.removeChild(item)
        self._commit(previous)

    @staticmethod
    def _ancestors(item):
        parents = []
        parent = item.parent()
        while parent is not None:
            parents.append(parent)
            parent = parent.parent()
        return parents

    def toggle_enabled_selection(self):
        chosen = self.selected_nodes()
        if not chosen:
            return
        nodes = [unpack_node(item) for item in chosen]
        if any(node.is_group for node in nodes):
            self.invalid_change.emit("Select executable actions only; workflow groups cannot be disabled.")
            return
        previous = deepcopy(self._snapshot)
        with QSignalBlocker(self):
            for item, node in zip(chosen, nodes):
                node.action.enabled = not node.action.enabled
                item.setData(0, NODE_ROLE, pack_node(node))
                self._set_action_label(item, node.action)
                item.setCheckState(
                    0, Qt.CheckState.Checked if node.action.enabled
                    else Qt.CheckState.Unchecked)
                self._decorate_leaf(item, node.action)
        self._commit(previous)

    def duplicate_selection(self):
        chosen = self.selected_nodes()
        chosen = [item for item in chosen if not any(
            ancestor in chosen for ancestor in self._ancestors(item))]
        previous = deepcopy(self._snapshot)
        for item in reversed(chosen):
            node = self._read_node(item)
            parent = item.parent()
            new_item = self._insert_node(parent, node)
            if parent is None:
                self.takeTopLevelItem(self.indexOfTopLevelItem(new_item))
                self.insertTopLevelItem(self.indexOfTopLevelItem(item) + 1, new_item)
            else:
                parent.removeChild(new_item)
                parent.insertChild(parent.indexOfChild(item) + 1, new_item)
        self._commit(previous)

    def index_map(self):
        """Map every legacy flat action index to its visible tree item."""
        mapping = {}
        position = 0

        def walk(parent):
            nonlocal position
            count = parent.childCount() if parent is not None else self.topLevelItemCount()
            for i in range(count):
                item = parent.child(i) if parent is not None else self.topLevelItem(i)
                value = item.data(0, NODE_ROLE)
                if value == "else_branch":
                    # A default empty Else drop target is only visual; it does
                    # not create an Else marker in the flattened action list.
                    if item.childCount():
                        mapping[position] = item
                        position += 1
                    walk(item)
                    continue
                mapping[position] = item
                position += 1
                if unpack_node(item).is_group:
                    walk(item)
                    mapping[position] = item  # loop/if end marker
                    position += 1
        walk(None)
        return mapping

    def selected_flat_index(self):
        mapping = self.index_map()
        chosen = self.selectedItems()
        if not chosen:
            return 0
        for index, item in mapping.items():
            if item is chosen[0]:
                return index
        return 0
