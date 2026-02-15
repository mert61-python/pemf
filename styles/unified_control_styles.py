# -*- coding: utf-8 -*-
"""
Unified Control Window Stylesheet (DEPRECATED)

⚠️ DEPRECATED: Bu dosya artık kullanılmamaktadır.
Lütfen yeni design system'i kullanın:

    from styles import StyleMixin
    
    class MyWindow(QMainWindow, StyleMixin):
        def __init__(self):
            super().__init__()
            self.apply_theme()

Bu dosya backward compatibility için korunmaktadır.
"""

import warnings

def get_unified_control_stylesheet():
    """
    Unified Control Window için modern stylesheet döndürür
    
    ⚠️ DEPRECATED: Lütfen yeni design system'i kullanın (StyleMixin)
    
    Returns:
        str: QSS (Qt Style Sheet) string
    """
    warnings.warn(
        "get_unified_control_stylesheet() is deprecated. "
        "Use StyleMixin instead: class MyWindow(QMainWindow, StyleMixin)",
        DeprecationWarning,
        stacklevel=2
    )
    return """
        /* Ana tema ve renk sistemi */
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a2e, stop:1 #16213e);
        }
        QWidget {
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #f8fafc;
        }
        
        /* Kart bileşenleri */
        QWidget[class="card"] {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            margin: 8px;
            padding: 16px;
        }
        
        QWidget[class="card-elevated"] {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            margin: 8px;
            padding: 20px;
        }
        
        /* Status indicator'ları */
        QLabel[class="status-success"] {
            color: #22c55e;
            font-weight: 600;
        }
        QLabel[class="status-warning"] {
            color: #f59e0b;
            font-weight: 600;
        }
        QLabel[class="status-error"] {
            color: #ef4444;
            font-weight: 600;
        }
        QLabel[class="status-info"] {
            color: #3b82f6;
            font-weight: 600;
        }
        QTabWidget::pane {
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.2);
            margin-top: 8px;
        }
        QTabWidget::tab-bar {
            alignment: center;
        }
        QTabBar::tab {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 12px 24px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            color: rgba(255, 255, 255, 0.7);
            min-width: 120px;
        }
        QTabBar::tab:selected {
            background: rgba(99, 102, 241, 0.2);
            border-color: rgba(99, 102, 241, 0.5);
            color: #ffffff;
        }
        QTabBar::tab:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
        }
        QGroupBox {
            font-size: 14px;
            font-weight: 600;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 16px;
            margin: 12px 8px;
            padding-top: 16px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 rgba(255, 255, 255, 0.12), 
                stop:1 rgba(255, 255, 255, 0.06));
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 20px;
            padding: 8px 16px;
            color: rgba(255, 255, 255, 0.95);
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 rgba(99, 102, 241, 0.8), 
                stop:1 rgba(67, 56, 202, 0.8));
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-radius: 8px;
            font-weight: 700;
        }
        QLabel {
            color: rgba(255, 255, 255, 0.9);
            font-size: 13px;
        }
        QSpinBox, QDoubleSpinBox {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            color: #ffffff;
            min-height: 20px;
        }
        QSpinBox:focus, QDoubleSpinBox:focus {
            border: 2px solid rgba(99, 102, 241, 0.6);
            background: rgba(255, 255, 255, 0.12);
        }
        QComboBox {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            color: #ffffff;
            min-height: 20px;
        }
        QComboBox:focus {
            border: 2px solid rgba(99, 102, 241, 0.6);
            background: rgba(255, 255, 255, 0.12);
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid rgba(255, 255, 255, 0.7);
            margin-right: 5px;
        }
        QComboBox QAbstractItemView {
            background: rgba(26, 26, 46, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            selection-background-color: rgba(99, 102, 241, 0.3);
            color: #ffffff;
            padding: 4px;
        }
        /* Modern Button System */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 0.8), stop:1 rgba(67, 56, 202, 0.8));
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 10px;
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
            padding: 12px 24px;
            min-height: 20px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 1.0), stop:1 rgba(67, 56, 202, 1.0));
            border: 2px solid rgba(99, 102, 241, 0.6);
            padding: 11px 23px;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(67, 56, 202, 0.9), stop:1 rgba(55, 48, 163, 0.9));
            border: 2px solid rgba(67, 56, 202, 0.8);
            padding: 13px 25px;
        }
        QPushButton:disabled {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.1);
            color: rgba(255, 255, 255, 0.4);
        }
        
        /* Button Variants */
        QPushButton[class="primary"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 0.9), stop:1 rgba(67, 56, 202, 0.9));
            border-color: rgba(99, 102, 241, 0.5);
        }
        QPushButton[class="success"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 0.8), stop:1 rgba(21, 128, 61, 0.8));
            border-color: rgba(34, 197, 94, 0.3);
        }
        QPushButton[class="success"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 1.0), stop:1 rgba(21, 128, 61, 1.0));
            border-color: rgba(34, 197, 94, 0.6);
        }
        QPushButton[class="danger"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 0.8), stop:1 rgba(185, 28, 28, 0.8));
            border-color: rgba(239, 68, 68, 0.3);
        }
        QPushButton[class="danger"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 1.0), stop:1 rgba(185, 28, 28, 1.0));
            border-color: rgba(239, 68, 68, 0.6);
        }
        QPushButton[class="secondary"] {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: rgba(255, 255, 255, 0.9);
        }
        QPushButton[class="secondary"]:hover {
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.3);
        }
        QPushButton#startButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 0.8), stop:1 rgba(21, 128, 61, 0.8));
            border-color: rgba(34, 197, 94, 0.3);
        }
        QPushButton#startButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(34, 197, 94, 1.0), stop:1 rgba(21, 128, 61, 1.0));
        }
        QPushButton#stopButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 0.8), stop:1 rgba(185, 28, 28, 0.8));
            border-color: rgba(239, 68, 68, 0.3);
        }
        QPushButton#stopButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(239, 68, 68, 1.0), stop:1 rgba(185, 28, 28, 1.0));
        }
        QSlider::groove:horizontal {
            border: 1px solid rgba(255, 255, 255, 0.2);
            height: 6px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 0.9), stop:1 rgba(67, 56, 202, 0.9));
            border: 1px solid rgba(99, 102, 241, 0.5);
            width: 18px;
            margin: -6px 0;
            border-radius: 9px;
        }
        QSlider::handle:horizontal:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 1.0), stop:1 rgba(67, 56, 202, 1.0));
        }
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollBar:vertical {
            background: rgba(255, 255, 255, 0.05);
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        QStatusBar {
            background: rgba(0, 0, 0, 0.3);
            color: rgba(255, 255, 255, 0.8);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            padding: 8px;
        }
    """

