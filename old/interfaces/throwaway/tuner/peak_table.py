"""Top FFT peaks placeholder table."""

from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from interfaces.throwaway.shared.cards import Card


class PeakTable(Card):
    """Mock spectrum peak table for detector diagnostics.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Top FFT peaks", "Static rows showing the intended table shape", parent=parent)
        table = QTableWidget(5, 4)
        table.setHorizontalHeaderLabels(["Rank", "Frequency", "Note", "Relative"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        rows = [
            ("1", "110.00 Hz", "A2", "1.00"),
            ("2", "220.00 Hz", "A3", "0.56"),
            ("3", "329.63 Hz", "E4", "0.34"),
            ("4", "440.00 Hz", "A4", "0.22"),
            ("5", "146.83 Hz", "D3", "0.18"),
        ]
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem(value))

        self.layout.addWidget(table)

