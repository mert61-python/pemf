from PyQt6.QtCore import QThread, pyqtSignal, QMutex
import numpy as np

class GraphDataWorker(QThread):
    """
    Background thread for processing graph data.
    Offloads NumPy array creation, filtering, and rounding from the main UI thread.
    """
    # Returns dict: {coil_id: (x_array, mag_y_array, temp_y_array)}
    data_processed = pyqtSignal(dict) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mutex = QMutex()
        self._data_snapshot = None
        self._running = True
        self._request_process = False
        
    def process_data(self, time_data, mag_data_dict, temp_data_dict, active_coils, window_seconds=5.0):
        """
        Queue data for processing.
        This method is called from the Main Thread.
        Performance Fix: window_seconds 10.0 -> 5.0 (deque maxlen ile eşleşir)
        Snapshot creation (O(N) but fast for N=1000, ~0.5ms)
        """
        self.mutex.lock()
        try:
            # Snapshot creation (O(N) but fast for N=1000)
            self._data_snapshot = {
                'time': list(time_data),
                'mag': {k: list(v) for k, v in mag_data_dict.items() if k in active_coils},
                'temp': {k: list(v) for k, v in temp_data_dict.items() if k in active_coils},
                'active_coils': list(active_coils),
                'window': window_seconds
            }
            self._request_process = True
        finally:
            self.mutex.unlock()

    def run(self):
        while self._running:
            process_now = False
            snapshot = None
            
            self.mutex.lock()
            if self._request_process:
                snapshot = self._data_snapshot
                self._request_process = False
                process_now = True
            self.mutex.unlock()
            
            if process_now and snapshot:
                results = {}
                try:
                    # Performance Fix: NumPy array conversion optimized
                    # 1. Convert time to numpy array (dtype=float32 daha hızlı, yeterli hassasiyet)
                    full_time = np.array(snapshot['time'], dtype=np.float32)
                    
                    if len(full_time) > 0:
                        last_time = full_time[-1]
                        start_time = last_time - snapshot['window']
                        
                        # 2. Filter active coils (vectorized operations)
                        for coil_id in snapshot['active_coils']:
                            # Get raw data lists
                            mag_list = snapshot['mag'].get(coil_id, [])
                            temp_list = snapshot['temp'].get(coil_id, [])
                            
                            # Basic length check
                            min_len = min(len(full_time), len(mag_list), len(temp_list))
                            
                            if min_len > 0:
                                # Performance Fix: Direct slicing + dtype=float32
                                t_slice = full_time[:min_len]
                                m_slice = np.array(mag_list[:min_len], dtype=np.float32)
                                tmp_slice = np.array(temp_list[:min_len], dtype=np.float32)
                                
                                # 3. Apply time window mask (vectorized boolean indexing)
                                mask = t_slice >= start_time
                                
                                if np.any(mask):
                                    final_x = t_slice[mask]
                                    # 4. Rounding optimization (in-place where possible)
                                    final_mag = np.round(m_slice[mask], 1)
                                    final_temp = np.round(tmp_slice[mask], 1)
                                    
                                    results[coil_id] = (final_x, final_mag, final_temp)
                    
                    # Emit prepared data back to Main Thread
                    self.data_processed.emit(results)
                    
                except Exception as e:
                    print(f"GraphWorker Error: {e}")
            
            # Performance Fix: Sleep 20ms -> 10ms (daha responsive, CPU kullanımı minimal)
            self.msleep(10) 
            
    def stop(self):
        self._running = False
        # Sonsuz bloklamayi engellemek icin sinirli bekleme kullan.
        self.wait(1000)
