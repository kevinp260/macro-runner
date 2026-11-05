"""PySide6 structured workflow tree with validated group drag-and-drop.

Tree items represent executable Action objects or complete control blocks.
The legacy flat marker layout exists only at the import/export boundary.
"""
from copy import deepcopy
from dataclasses import asdict
import json

from PySide6.QtCore import Qt, QByteArray, QMimeData, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView, QListWidget, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QFileDialog
)

from macro_model import Action
from macro_workflow import WorkflowNode, default_node, from_actions, to_actions
from macro_flow import OPENERS

NODE_ROLE = int(Qt.ItemDataRole.UserRole)


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
    ("Repeat block", "loop_start"),
    ("If / Else", "if_start"), ("Repeat until", "until_start"),
]

TITLES = {
    "click": "Mouse click", "click_image": "Click image",
    "wait": "Wait", "wait_until": "Wait until",
    "key": "Keyboard", "key_down": "Hold key", "key_up": "Release key",
    "move": "Move", "scroll": "Scroll", "drag": "Drag",
    "loop_start": "Repeat block", "if_start": "Condition",
    "until_start": "Repeat until"
}


def description(action):
    kind = action.kind
    if kind == "click":
        detail = f"{action.button} at ({action.x}, {action.y})"
    elif kind == "click_image":
        detail = action.image_path or "Choose reference image"
    elif kind in ("wait",):
        detail = f"{action.seconds:g} seconds"
    elif kind in ("wait_until", "if_start", "until_start"):
        target = action.image_path if action.condition_source == "image" else (
            f"pixel ({action.pixel_x}, {action.pixel_y}) {action.pixel_color}")
        detail = f"{action.match_mode.replace('_', ' ')} · {target}"
    elif kind in ("key", "key_down", "key_up"):
        detail = action.keys
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
    return f"{base}  ·  {detail}{repeats}" + ("" if action.enabled else "  [disabled]")


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

    def _insert_node(self, parent, node):
        item = QTreeWidgetItem()
        item.setData(0, NODE_ROLE, pack_node(node))
        item.setText(0, description(node.action))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled |
                      Qt.ItemFlag.ItemIsDropEnabled)
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
                            ~Qt.ItemFlag.ItemIsDragEnabled)
            item.addChild(branch)
            for child in node.otherwise:
                self._insert_node(branch, child)
        item.setExpanded(True)
        return item

    def set_actions(self, actions):
        self._snapshot = deepcopy(actions)
        self.clear()
        for node in from_actions(actions):
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
        items[0].setData(0, NODE_ROLE, pack_node(node))
        items[0].setText(0, description(action))
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
        for item, node in zip(chosen, nodes):
            node.action.enabled = not node.action.enabled
            item.setData(0, NODE_ROLE, pack_node(node))
            item.setText(0, description(node.action))
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
