"""
Serial port management for the PEMF GUI application.
Handles communication with the PEMF device.
"""

import socket  # Import socket module for UDP
import threading
from typing import Callable
from enum import Enum, auto
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# Add the handlers to the logger
if not logger.handlers:  # Avoid adding handlers multiple times
    logger.addHandler(ch)

class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


class SerialManager:
    """Manages serial port communication with the PEMF device (HIGH FIX: buffer limit + reconnect)."""
    
    # HIGH FIX: Buffer size limit to prevent memory leak
    MAX_BUFFER_SIZE = 64 * 1024  # 64KB
    
    def __init__(self, config=None):
        """Initialize the serial manager.
        
        Args:
            config: Optional ConfigManager instance. If not provided, a new one will be created.
        """
        from .config import get_config
        self.config = config or get_config()
        self.udp_socket = None # Change from serial_port to udp_socket
        self.state = ConnectionState.DISCONNECTED
        self.callbacks = {
            'on_connect': [],
            'on_disconnect': [],
            'on_data': [],
            'on_error': [],
            'on_state_change': []
        }
        self._read_thread = None
        self._stop_event = threading.Event()
        self.remote_address = None # To store the address of the remote device
        
        # HIGH FIX: Reconnection logic
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._last_connection_params = None
        
        # HIGH FIX: Packet loss tracking
        self._packets_received = 0
        self._packets_lost = 0
    
    def add_callback(self, event: str, callback: Callable) -> None:
        """Add a callback for a specific event.
        
        Args:
            event: One of 'on_connect', 'on_disconnect', 'on_data', 'on_error', 'on_state_change'
            callback: Callback function
        """
        if event in self.callbacks:
            self.callbacks[event].append(callback)
    
    def remove_callback(self, event: str, callback: Callable) -> None:
        """Remove a callback."""
        if event in self.callbacks and callback in self.callbacks[event]:
            self.callbacks[event].remove(callback)
    
    def _notify(self, event: str, *args, **kwargs) -> None:
        """Notify all callbacks for an event."""
        for callback in self.callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")
    
    def set_state(self, new_state: ConnectionState) -> None:
        """Update the connection state and notify listeners."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self._notify('on_state_change', old_state, new_state)
    
    def connect(self, ip_address: str = None, port: int = None) -> bool:
        """Connect to the specified UDP port.
        
        Args:
            ip_address: IP address to bind to. If None, uses the value from config.
            port: Port to bind to. If None, uses the value from config.
            
        Returns:
            bool: True if connection was successful, False otherwise.
        """
        if self.state == ConnectionState.CONNECTED:
            self.disconnect()
        
        ip_address = ip_address or self.config.get('udp.ip_address', '127.0.0.1')
        port = port or self.config.get('udp.port', 12345)
        
        self.set_state(ConnectionState.CONNECTING)
        
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind((ip_address, port))
            self.udp_socket.settimeout(1.0) # Set a timeout for receiving data
            
            # Save the successful connection details
            self.config.set('udp.ip_address', ip_address)
            self.config.set('udp.port', port)
            
            # HIGH FIX: Save connection params for reconnection
            self._last_connection_params = (ip_address, port)
            self._reconnect_attempts = 0
            
            # Start the read thread
            self._stop_event.clear()
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            
            self.set_state(ConnectionState.CONNECTED)
            self._notify('on_connect', f"{ip_address}:{port}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to connect to UDP {ip_address}:{port}: {e}"
            logger.error(error_msg)
            self._notify('on_error', error_msg)
            self.set_state(ConnectionState.ERROR)
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the UDP socket."""
        if self.state == ConnectionState.DISCONNECTED:
            return
        
        self._stop_event.set()
        
        # Wait for read thread to finish
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
            if self._read_thread.is_alive():
                logger.warning("Read thread did not terminate within timeout")
        
        # Close UDP socket
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception as e:
                logger.error(f"Error closing UDP socket: {e}")
            finally:
                self.udp_socket = None
        
        self._read_thread = None
        self.remote_address = None
        
        if self.state != ConnectionState.DISCONNECTED:
            self.set_state(ConnectionState.DISCONNECTED)
            self._notify('on_disconnect')
    
    def _read_loop(self) -> None:
        """Background thread for receiving data from the UDP socket (HIGH FIX: buffer limit)."""
        buffer = bytearray()
        
        while not self._stop_event.is_set() and self.udp_socket:
            try:
                data, addr = self.udp_socket.recvfrom(1024) # Buffer size 1024 bytes
                self.remote_address = addr # Store the address of the sender
                self._packets_received += 1
                
                # HIGH FIX: Check buffer size before extending
                if len(buffer) + len(data) > self.MAX_BUFFER_SIZE:
                    logger.warning(f"Buffer overflow prevented: {len(buffer)} bytes, dropping oldest data")
                    # Keep only the last half of buffer
                    buffer = buffer[len(buffer)//2:]
                
                buffer.extend(data)
                
                # Process complete messages (assuming newline-terminated)
                while b'\n' in buffer:
                    line, _, buffer = buffer.partition(b'\n')
                    try:
                        line = line.decode('utf-8').strip()
                        if line:
                            self._notify('on_data', line)
                    except UnicodeDecodeError:
                        logger.warning(f"Failed to decode line: {line}")
                        
            except socket.timeout:
                # Timeout is normal, continue
                continue
            except Exception as e:
                logger.error(f"Error in read loop: {e}")
                # HIGH FIX: Try to reconnect on error
                if not self._stop_event.is_set():
                    self._attempt_reconnect()
                break
    
    def _attempt_reconnect(self) -> None:
        """
        HIGH FIX: Attempt to reconnect after connection loss.
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"Max reconnection attempts ({self._max_reconnect_attempts}) reached")
            self.set_state(ConnectionState.ERROR)
            self._notify('on_error', 'Connection lost - max reconnect attempts reached')
            return
        
        if self._last_connection_params is None:
            logger.error("No connection params to reconnect")
            return
        
        self._reconnect_attempts += 1
        logger.info(f"Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts}...")
        
        # Wait before reconnecting (exponential backoff, stop-aware)
        wait_seconds = min(2 ** self._reconnect_attempts, 30)
        if self._stop_event.wait(wait_seconds):
            logger.debug("Reconnect cancelled due to stop event")
            return
        
        # Try to reconnect
        ip_address, port = self._last_connection_params
        if self.connect(ip_address, port):
            logger.info("Reconnection successful")
        else:
            logger.warning(f"Reconnection attempt {self._reconnect_attempts} failed")
            
    def write(self, data: str) -> bool:
        """Write data to the UDP socket.
        
        Args:
            data: String data to write (will be encoded to bytes)
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        if self.state != ConnectionState.CONNECTED or not self.udp_socket or not self.remote_address:
            logger.warning("Cannot write: not connected or no remote address")
            return False
        
        try:
            if not data.endswith('\n'):
                data += '\n'
            self.udp_socket.sendto(data.encode('utf-8'), self.remote_address)
            return True
            
        except Exception as e:
            logger.error(f"Error writing to UDP socket: {e}")
            self._notify('on_error', f"Write error: {e}")
            self.disconnect()
            return False
    
    def is_connected(self) -> bool:
        """Check if the UDP socket is connected."""
        return (self.state == ConnectionState.CONNECTED and 
                self.udp_socket is not None and 
                self.remote_address is not None) # Check for remote address as well
