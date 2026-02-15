"""
Serial port selection and configuration dialog.
"""

import sys
import os

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QDialogButtonBox, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from pemf_gui.serial_manager import SerialManager, ConnectionState
import time

class SerialPortDialog(QDialog):
    """Dialog for selecting and configuring a serial port."""
    
    # Signal emitted when connection is established
    connected = pyqtSignal()
    
    def __init__(self, parent=None, serial_manager=None):
        """Initialize the dialog.
        
        Args:
            parent: Parent widget
            serial_manager: Optional SerialManager instance
        """
        super().__init__(parent)
        self.serial_manager = serial_manager or SerialManager()
        self.setWindowTitle("Serial Port Configuration")
        self.setMinimumWidth(400)
        
        self.init_ui()
        self.refresh_ports()
        
        # Connect signals
        self.serial_manager.add_callback('on_state_change', self.on_connection_state_changed)
        self.serial_manager.add_callback('on_error', self.on_serial_error)
    
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()
        
        # Port selection
        port_group = QGroupBox("UDP Settings") # Changed title
        port_layout = QFormLayout()
        
        # IP Address
        self.ip_address_input = QLineEdit("127.0.0.1") # Input for IP Address
        port_layout.addRow("IP Address:", self.ip_address_input)
        
        # Port
        self.port_spin = QSpinBox() # SpinBox for Port
        self.port_spin.setRange(1024, 65535) # Typical port range
        self.port_spin.setValue(12345) # Default UDP port
        port_layout.addRow("Port:", self.port_spin)
        
        # port_layout.addRow(self.advanced_group)
        port_group.setLayout(port_layout)
        
        # Connection status
        self.status_label = QLabel("Status: Not connected")
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Disable OK button until connected
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        
        # Add widgets to layout
        layout.addWidget(port_group)
        
        # Status and connect button
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.connect_btn)
        layout.addLayout(status_layout)
        
        layout.addWidget(button_box)
        self.setLayout(layout)
        
        # Load saved settings
        self.load_settings()
    
    def load_settings(self):
        """Load saved settings."""
        # Load from config if available
        if hasattr(self.serial_manager, 'config'):
            ip_address = self.serial_manager.config.get('udp.ip_address', '127.0.0.1')
            port = self.serial_manager.config.get('udp.port', 12345)
            
            self.ip_address_input.setText(ip_address)
            self.port_spin.setValue(port)
    
    def save_settings(self):
        """Save current settings."""
        if hasattr(self.serial_manager, 'config'):
            self.serial_manager.config.set('udp.ip_address', self.ip_address_input.text())
            self.serial_manager.config.set('udp.port', self.port_spin.value())
    
    def refresh_ports(self):
        """Refresh the list of available serial ports. (Not applicable for UDP)"""
        # This method is no longer needed for UDP, but kept as a placeholder or can be removed.
        pass
    
    def toggle_advanced(self, checked):
        """Show/hide advanced options. (Not applicable for UDP)"""
        # This method is no longer needed for UDP, but kept as a placeholder or can be removed.
        pass
    
    def toggle_connection(self):
        """Connect to or disconnect from the selected port."""
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
        else:
            self.connect_to_port()
    
    def connect_to_port(self):
        """Attempt to connect to the selected port."""
        ip_address = self.ip_address_input.text()
        port = self.port_spin.value()
        
        if not ip_address or not port:
            QMessageBox.warning(self, "Error", "Please enter a valid IP address and port")
            return
        
        try:
            self.connect_btn.setEnabled(False)
            self.connect_btn.setText("Connecting...")
            
            # Save settings before connecting
            self.save_settings()
            
            # Try to connect using UDP
            if self.serial_manager.connect(ip_address, port):
                self.connected.emit()
            
        except ValueError as e:
            QMessageBox.critical(self, "Error", f"Invalid settings: {e}")
        finally:
            self.update_ui_state()
    
    def on_connection_state_changed(self, old_state, new_state):
        """Handle connection state changes."""
        self.update_ui_state()
        
        if new_state == ConnectionState.CONNECTED:
            self.ok_button.setEnabled(True)
        elif new_state == ConnectionState.DISCONNECTED:
            self.ok_button.setEnabled(False)
    
    def on_serial_error(self, message):
        """Handle serial errors."""
        QMessageBox.critical(self, "UDP Error", message) # Changed message
        self.update_ui_state()
    
    def update_ui_state(self):
        """Update the UI based on the current connection state."""
        if self.serial_manager.state == ConnectionState.CONNECTED:
            self.status_label.setText(f"Status: Connected to {self.serial_manager.config.get('udp.ip_address')}:{self.serial_manager.config.get('udp.port')}") # Updated status text
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setEnabled(True)
            
        elif self.serial_manager.state == ConnectionState.CONNECTING:
            self.status_label.setText("Status: Connecting...")
            self.connect_btn.setText("Connecting...")
            self.connect_btn.setEnabled(False)
            
        elif self.serial_manager.state == ConnectionState.ERROR:
            self.status_label.setText("Status: Error")
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            
        else:  # DISCONNECTED
            self.status_label.setText("Status: Not connected")
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
    
    def accept(self):
        """Handle dialog acceptance."""
        if not self.serial_manager.is_connected():
            QMessageBox.warning(self, "Not Connected", "You must be connected to a device to continue.")
            return
        
        self.save_settings()
        super().accept()
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Cleanup callbacks
        try:
            self.serial_manager.remove_callback('on_state_change', self.on_connection_state_changed)
            self.serial_manager.remove_callback('on_error', self.on_serial_error)
        except Exception as e:
            logger.warning(f"Error removing callbacks: {e}")
        
        # Disconnect when closing
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
        
        super().closeEvent(event)


# Logging configuration
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
