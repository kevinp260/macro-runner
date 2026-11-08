"""Searchable local Help window, independent of workflow execution."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from macro_help import BY_ID, CATEGORIES, search_topics


class HelpDialog(QDialog):
    """Openable alongside the editor; never reads or changes workflow values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MacroRunner — Help and User Guide")
        self.setMinimumSize(720, 460)
        self.resize(940, 650)

        outer = QVBoxLayout(self)
        intro = QLabel("What would you like to do? Search a feature, button, "
                       "or problem — for example, breakpoint, debug gap, "
                       "image not found, or save a workflow.")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        self.search = QLineEdit()
        self.search.setObjectName("helpSearch")
        self.search.setPlaceholderText("Search the Help guide…")
        self.search.setClearButtonEnabled(True)
        outer.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.category = QComboBox()
        self.category.addItem("All topics")
        self.category.addItems(CATEGORIES)
        left_layout.addWidget(self.category)
        self.count = QLabel()
        left_layout.addWidget(self.count)
        self.results = QListWidget()
        self.results.setObjectName("helpResults")
        left_layout.addWidget(self.results, 1)
        splitter.addWidget(left)

        self.article = QTextBrowser()
        self.article.setObjectName("helpArticle")
        self.article.setOpenExternalLinks(False)
        self.article.setOpenLinks(False)
        self.article.setReadOnly(True)
        splitter.addWidget(self.article)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 650])
        outer.addWidget(splitter, 1)

        self.search.textChanged.connect(self.refresh)
        self.category.currentTextChanged.connect(self.refresh)
        self.results.currentItemChanged.connect(self._show_current)
        self.refresh()
        self.search.setFocus()

    def refresh(self, *_):
        """Rebuild only the small list, not any workflow or editor state."""
        selected = self.results.currentItem()
        previous_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        topics = search_topics(self.search.text(), self.category.currentText())
        self.results.blockSignals(True)
        try:
            self.results.clear()
            chosen = 0
            for index, topic in enumerate(topics):
                item = QListWidgetItem(topic.title)
                item.setData(Qt.ItemDataRole.UserRole, topic.id)
                item.setToolTip(topic.category)
                self.results.addItem(item)
                if topic.id == previous_id:
                    chosen = index
            if topics:
                self.results.setCurrentRow(chosen)
        finally:
            self.results.blockSignals(False)
        self.count.setText(f"{len(topics)} topic(s)")
        self._show_current()

    def _show_current(self, *_):
        item = self.results.currentItem()
        if item is None:
            self.article.setMarkdown(
                "# No matching help topics\n\n"
                "Try fewer words, another category, or a simpler phrase. "
                "For example: **click**, **pause**, **breakpoint**, or **save**.")
            return
        topic = BY_ID[item.data(Qt.ItemDataRole.UserRole)]
        self.article.setMarkdown(
            f"# {topic.title}\n\n*{topic.category}*\n\n{topic.body.strip()}")
        self.article.verticalScrollBar().setValue(0)

    def open_topic(self, topic_id="start"):
        """Show a topic by stable ID, also when a previous search is active."""
        topic_id = topic_id if topic_id in BY_ID else "start"
        self.category.setCurrentIndex(0)
        self.search.clear()
        for row in range(self.results.count()):
            if self.results.item(row).data(Qt.ItemDataRole.UserRole) == topic_id:
                self.results.setCurrentRow(row)
                break
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
