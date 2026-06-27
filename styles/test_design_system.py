# -*- coding: utf-8 -*-
"""
Design System Test
Yeni tasarım sistemini test etmek için örnek pencere
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QSlider
)
from PyQt6.QtCore import Qt

# Import design system
from styles import StyleMixin, StyleBuilder


class TestWindow(QMainWindow, StyleMixin):
    """Test penceresi - Design system demo"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PEMF Design System Test")
        self.setMinimumSize(900, 700)
        
        # Apply theme using StyleMixin
        self.apply_theme()
        
        self._init_ui()
    
    def _init_ui(self):
        """UI oluştur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title = QLabel("PEMF Design System Test")
        title.setObjectName("titleLabel")
        main_layout.addWidget(title)
        
        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_buttons_tab(), "Buttons")
        tabs.addTab(self._create_inputs_tab(), "Inputs")
        tabs.addTab(self._create_tables_tab(), "Tables")
        tabs.addTab(self._create_cards_tab(), "Cards")
        main_layout.addWidget(tabs)
        
        # Status bar
        self.statusBar().showMessage("Design System v1.0.0")
    
    def _create_buttons_tab(self) -> QWidget:
        """Buttons tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Primary buttons
        group = QGroupBox("Primary Buttons")
        group_layout = QHBoxLayout(group)
        
        btn1 = QPushButton("Default Button")
        group_layout.addWidget(btn1)
        
        btn2 = QPushButton("Primary Button")
        btn2.setProperty("class", "primary")
        group_layout.addWidget(btn2)
        
        layout.addWidget(group)
        
        # Success/Danger buttons
        group2 = QGroupBox("Success & Danger Buttons")
        group2_layout = QHBoxLayout(group2)
        
        btn3 = QPushButton("Success Button")
        btn3.setProperty("class", "success")
        group2_layout.addWidget(btn3)
        
        btn4 = QPushButton("Danger Button")
        btn4.setProperty("class", "danger")
        group2_layout.addWidget(btn4)
        
        layout.addWidget(group2)
        
        # Secondary/Ghost buttons
        group3 = QGroupBox("Secondary & Ghost Buttons")
        group3_layout = QHBoxLayout(group3)
        
        btn5 = QPushButton("Secondary Button")
        btn5.setProperty("class", "secondary")
        group3_layout.addWidget(btn5)
        
        btn6 = QPushButton("Ghost Button")
        btn6.setProperty("class", "ghost")
        group3_layout.addWidget(btn6)
        
        layout.addWidget(group3)
        
        # Disabled button
        group4 = QGroupBox("Disabled Button")
        group4_layout = QHBoxLayout(group4)
        
        btn7 = QPushButton("Disabled Button")
        btn7.setEnabled(False)
        group4_layout.addWidget(btn7)
        
        layout.addWidget(group4)
        
        layout.addStretch()
        return widget
    
    def _create_inputs_tab(self) -> QWidget:
        """Inputs tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Line Edit
        group1 = QGroupBox("Line Edit")
        group1_layout = QVBoxLayout(group1)
        line_edit = QLineEdit()
        line_edit.setPlaceholderText("Enter text here...")
        group1_layout.addWidget(line_edit)
        layout.addWidget(group1)
        
        # Combo Box
        group2 = QGroupBox("Combo Box")
        group2_layout = QVBoxLayout(group2)
        combo = QComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3"])
        group2_layout.addWidget(combo)
        layout.addWidget(group2)
        
        # Spin Box
        group3 = QGroupBox("Spin Box")
        group3_layout = QVBoxLayout(group3)
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(50)
        group3_layout.addWidget(spin)
        layout.addWidget(group3)
        
        # Slider
        group4 = QGroupBox("Slider")
        group4_layout = QVBoxLayout(group4)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        group4_layout.addWidget(slider)
        layout.addWidget(group4)
        
        # Text Edit
        group5 = QGroupBox("Text Edit")
        group5_layout = QVBoxLayout(group5)
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Enter multiline text here...")
        text_edit.setMaximumHeight(100)
        group5_layout.addWidget(text_edit)
        layout.addWidget(group5)
        
        layout.addStretch()
        return widget
    
    def _create_tables_tab(self) -> QWidget:
        """Tables tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("Table Widget")
        group_layout = QVBoxLayout(group)
        
        table = QTableWidget(5, 3)
        table.setHorizontalHeaderLabels(["Column 1", "Column 2", "Column 3"])
        
        # Fill with sample data
        for row in range(5):
            for col in range(3):
                item = QTableWidgetItem(f"Row {row+1}, Col {col+1}")
                table.setItem(row, col, item)
        
        group_layout.addWidget(table)
        layout.addWidget(group)
        
        return widget
    
    def _create_cards_tab(self) -> QWidget:
        """Cards tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Card
        card1 = QWidget()
        card1.setProperty("class", "card")
        card1_layout = QVBoxLayout(card1)
        card1_layout.addWidget(QLabel("This is a basic card"))
        card1_layout.addWidget(QPushButton("Card Button"))
        layout.addWidget(card1)
        
        # Elevated Card
        card2 = QWidget()
        card2.setProperty("class", "card-elevated")
        card2_layout = QVBoxLayout(card2)
        card2_layout.addWidget(QLabel("This is an elevated card"))
        card2_layout.addWidget(QPushButton("Card Button"))
        layout.addWidget(card2)
        
        # Bordered Card
        card3 = QWidget()
        card3.setProperty("class", "card-bordered")
        card3_layout = QVBoxLayout(card3)
        card3_layout.addWidget(QLabel("This is a bordered card"))
        card3_layout.addWidget(QPushButton("Card Button"))
        layout.addWidget(card3)
        
        # Status Labels
        group = QGroupBox("Status Labels")
        group_layout = QVBoxLayout(group)
        
        label1 = QLabel("✓ Success Status")
        label1.setProperty("class", "status-success")
        group_layout.addWidget(label1)
        
        label2 = QLabel("⚠ Warning Status")
        label2.setProperty("class", "status-warning")
        group_layout.addWidget(label2)
        
        label3 = QLabel("✗ Error Status")
        label3.setProperty("class", "status-error")
        group_layout.addWidget(label3)
        
        label4 = QLabel("ℹ Info Status")
        label4.setProperty("class", "status-info")
        group_layout.addWidget(label4)
        
        layout.addWidget(group)
        
        layout.addStretch()
        return widget


def main():
    """Test uygulamasını çalıştır"""
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

