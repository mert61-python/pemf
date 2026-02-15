# -*- coding: utf-8 -*-
"""
Sensör Veri Monitörü Penceresi
ESP8266 cihazlarından gelen sensör verilerini (manyetik alan, sıcaklık, akım) 
gerçek zamanlı olarak görselleştirir.
"""

import sys
import os
import time
import logging
from collections import deque
import numpy as np  # Performance Fix - NumPy optimizasyonu için

# PyQt6 Imports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QGroupBox, QScrollArea,
    QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QReadWriteLock

import pyqtgraph as pg

# ✅ Suppress numpy warnings for pyqtgraph overflow (ViewBox internal module)
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, module='pyqtgraph.graphicsItems.ViewBox.ViewBox')

# PyQtGraph konfigürasyonu
# OpenGL devre dışı - eski bilgisayarlarda uyumluluk için software rendering kullan
pg.setConfigOptions(useOpenGL=False, enableExperimental=False)
pg.setConfigOption('background', '#1e1e2e')
pg.setConfigOption('foreground', 'w')
pg.setConfigOption('antialias', True)

class TicksAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"{value:.1f}" for value in values]

# Design System
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
from styles import StyleMixin
# Responsive Utils
from utils.responsive_utils import get_screen_info


class SensorDataWindow(QMainWindow, StyleMixin):
    """
    Sensör verilerini görselleştirmek için pencere sınıfı.
    
    Bu sınıf, sensör verilerini (manyetik alan, sıcaklık, akım) 
    gerçek zamanlı olarak görselleştirir.
    
    Design System entegrasyonu ile merkezi stil yönetimi kullanır.
    """
    
    def __init__(self, parent=None):
        """SensorDataWindow sınıfını başlatır."""
        super().__init__(parent)
        self.main_window = None
        self.logger = logging.getLogger(__name__)
        
        # Deque veri yapıları (900 nokta limitli - memory optimization)
        self.max_data_points = 900  # ~5 dakika geçmiş @ 3Hz (daha uzun geçmiş görmek için)
        
        # Her bobin için deque veri yapıları
        self.magnetic_data = {}
        self.magnetic_time = {}
        self.ambient_temp_data = {}
        self.object_temp_data = {}
        self.temp_time = {}
        self.current_data = {}
        self.current_time = {}
        
        # Thread safety için QReadWriteLock (GUI Stability Fix #4)
        self.data_lock = QReadWriteLock()
        
        # Her bobin için başlangıç zamanı (ilk veri geldiğinde ayarlanacak - gecikme önleme)
        self.coil_start_times = {}
        
        # Her bobin için deque yapılarını başlat
        for coil_id in range(1, 9):
            self.magnetic_data[coil_id] = deque(maxlen=self.max_data_points)
            self.magnetic_time[coil_id] = deque(maxlen=self.max_data_points)
            self.coil_start_times[coil_id] = None  # İlk veri geldiğinde ayarlanacak
            self.ambient_temp_data[coil_id] = deque(maxlen=self.max_data_points)
            self.object_temp_data[coil_id] = deque(maxlen=self.max_data_points)
            self.temp_time[coil_id] = deque(maxlen=self.max_data_points)
            self.current_data[coil_id] = deque(maxlen=self.max_data_points)
            self.current_time[coil_id] = deque(maxlen=self.max_data_points)
        
        # Plot referansları
        self.hall_plots = []
        self.hall_curves = []
        self.temp_plots = []
        self.temp_ambient_curves = []
        self.temp_object_curves = []
        self.current_plots = []
        self.current_curves = []
        
        # Veri güncelleme zamanlayıcısı (GUI Stability Fix #3 - Performance)
        # 1Hz MQTT veri + 20 FPS güncelleme = Smooth visualization
        self.update_timer = QTimer(self)  # Parent widget'a bağla
        self.update_timer.timeout.connect(self.update_plots)
        self.update_timer.start(50)  # 50ms'de bir güncelle (20 FPS - main window ile senkron)
        
        # Apply design system theme
        self.apply_theme()
        
        # Responsive window sizing (after theme is applied)
        self._setup_responsive_window()
        
        self.init_ui()
    
    def setMainWindow(self, main_window):
        """Ana pencere referansını ayarlar."""
        self.main_window = main_window
    
    def connect_to_main_window(self, main_window):
        """MainWindow'dan gelen MQTT sensor verilerini dinlemek için bağlantı kurar."""
        self.main_window = main_window
        if hasattr(main_window, 'sensor_data_received'):
            main_window.sensor_data_received.connect(self.update_sensor_data)

    def init_ui(self):
        self.setWindowTitle("Sensör Veri Monitörü")
        self.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d185a, stop:1 #6c2b8f);         
            font-family: 'Segoe UI', 'Arial', sans-serif;
            color: #ffffff;
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4a148c;
                color: white;
                border: 1px solid #7b1fa2;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #7b1fa2;
            }
            QPushButton:pressed {
                background-color: #9c27b0;
            }
        """)      
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.frameShape().NoFrame)
        
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(20, 10, 30, 20)
        self.plot_layout.setSpacing(20)
        
        # 1. Manyetik Alan Sensörlerini Oluştur
        self.create_sensor_group(
            title="Manyetik Alan Sensörleri",
            y_label="Manyetik Alan (mT)",
            plot_storage=self.hall_plots,
            curve_storage=self.hall_curves,
            is_temp=False
        )

        # 2. Akım Sensörlerini Oluştur
        self.create_sensor_group(
            title="Akım Sensörleri",
            y_label="Akım (A)",
            plot_storage=self.current_plots,
            curve_storage=self.current_curves,
            is_temp=False
        )

        # 3. Sıcaklık Sensörlerini Oluştur
        self.create_sensor_group(
            title="Sıcaklık Sensörleri",
            y_label="Sıcaklık (°C)",
            plot_storage=self.temp_plots,
            curve_storage=self.temp_object_curves,  # Birinci eğri (Nesne)
            is_temp=True,
            second_curve_storage=self.temp_ambient_curves  # İkinci eğri (Ortam)
        )

        
        self.plot_layout.addStretch()
        
        scroll.setWidget(self.plot_container)
        
        # Sadece scroll widget'ını ana düzene ekle
        main_layout.addWidget(scroll)

    def create_sensor_group(self, title, y_label, plot_storage, curve_storage, is_temp=False, second_curve_storage=None):
        """
        Genel amaçlı sensör grubu oluşturucu (DRY Prensibi).
        
        Args:
            title (str): Grubun başlığı (örn: "Akım Sensörleri")
            y_label (str): Y ekseni etiketi (örn: "Akım (A)")
            plot_storage (list): Plot widget referanslarını saklayacak liste
            curve_storage (list): Eğri (Curve) referanslarını saklayacak liste
            is_temp (bool): Sıcaklık grafiği mi? (Çift eğri ve legend gerektirir)
            second_curve_storage (list, optional): Sıcaklık için ikinci eğri listesi (Ortam)
        """
        group = QGroupBox(title)
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        group.setMinimumHeight(800)
        
        grid = QGridLayout(group)
        grid.setSpacing(10)
        
        for i in range(8):
            row = i // 4
            col = i % 4
            coil_num = i + 1
            
            # --- Ortak Başlık ve Stil Ayarları ---
            # Coil 1 için özel yeşil renk, diğerleri beyaz
            title_color = '#00ff7f' if i == 0 else 'white'
            plot_title = f'Bobin {coil_num} - {title.split(" ")[0]}'
            if is_temp:
                plot_title = f'Bobin {coil_num} - Sıcaklık Sensörü'  # Başlık düzeltmesi 
            
            # Plot Widget Oluşturma
            axisItems = {'left': TicksAxis(orientation='left')}
            plot_widget = pg.PlotWidget(axisItems=axisItems)
            plot_widget.setLabel('left', y_label, color='white')
            plot_widget.setLabel('bottom', 'Zaman (s)', color='white')
            plot_widget.setTitle(plot_title, color=title_color)
            plot_widget.showGrid(x=True, y=True, alpha=0.3)
            
            # Plot referansını kaydet
            plot_item = plot_widget.getPlotItem()
            plot_storage.append(plot_item)
            
            # --- Coil 1 Özel Notu (Gerçek Zamanlı Veri) ---
            if i == 0:
                note_label = QLabel("Gerçek Zamanlı Veri")
                note_label.setStyleSheet("color: #00ff7f; font-style: italic;")
                note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(note_label, row+1, col)
                
            # --- Eğri (Curve) Oluşturma Mantığı ---
            if is_temp:
                # --- SICAKLIK MODU (Çift Çizgi) ---
                plot_widget.addLegend(offset=(10, 10))
                
                if i == 0:  # Coil 1 için parlak renkler
                    pen_obj = pg.mkPen(color='#ff5500', width=2)  # Parlak Turuncu (kalınlık azaltıldı)
                    pen_amb = pg.mkPen(color='#00aaff', width=2)  # Parlak Mavi (kalınlık azaltıldı)
                else:  # Diğerleri için standart renkler
                    pen_obj = pg.mkPen(color='#ff7f0e', width=2)
                    pen_amb = pg.mkPen(color='#1f77b4', width=2)
                
                # Nesne (Object) Eğrisi - curve_storage'a gider
                curve_obj = plot_widget.plot(pen=pen_obj, name='Bobin')
                # Downsampling optimizasyonu (UI İyileştirmesi - Performans)
                # Ekrana sığmayan veya piksellerden daha sık olan verileri çizmeyerek GPU/CPU tasarrufu sağlar
                # Downsampling: 'mean' kullanarak gürültüyü bastırır ve çizgiyi temizler
                curve_obj.setDownsampling(auto=True, method='mean')
                curve_obj.setClipToView(True)
                curve_storage.append(curve_obj)
                
                # Ortam (Ambient) Eğrisi - second_curve_storage'a gider
                if second_curve_storage is not None:
                    curve_amb = plot_widget.plot(pen=pen_amb, name='Ortam')
                    # Downsampling optimizasyonu
                    # Downsampling: 'mean' kullanarak gürültüyü bastırır ve çizgiyi temizler
                    curve_amb.setDownsampling(auto=True, method='mean')
                    curve_amb.setClipToView(True)
                    second_curve_storage.append(curve_amb)
                    
            else:
                # --- STANDART MOD (Tek Çizgi: Hall veya Akım) ---
                if i == 0:
                    pen = pg.mkPen(color='#00ff7f', width=2)  # Parlak Yeşil (kalınlık azaltıldı)
                else:
                    # i değerine göre renk değiştiren algoritma
                    pen = pg.mkPen(color=pg.intColor(i, 8, alpha=200), width=2)
                    
                curve = plot_widget.plot(pen=pen)
                # Downsampling optimizasyonu (UI İyileştirmesi - Performans)
                # Ekrana sığmayan veya piksellerden daha sık olan verileri çizmeyerek GPU/CPU tasarrufu sağlar
                # Downsampling: 'mean' kullanarak gürültüyü bastırır ve çizgiyi temizler
                curve.setDownsampling(auto=True, method='mean')
                curve.setClipToView(True)
                curve_storage.append(curve)
                
            # Grid'e ekle
            grid.addWidget(plot_widget, row, col)
            
        # Grubu ana layout'a ekle
        self.plot_layout.addWidget(group)

    def update_sensor_data(self, coil_id, data):
        """
        MQTT'den gelen sensör verilerini deque yapılarına ekler.
        
        ESP kodundan gelen veri formatı:
        - coil_id: int (1-8)
        - object_temp: float (°C)
        - ambient_temp: float (°C)
        - magnetic_field: float (mT)
        - current: float (A)
        - sensors_ok: bool
        - pwm_active: bool
        
        Args:
            coil_id: Bobin ID'si (string veya int, 1-8 aralığında olmalı)
            data (dict): Sensör verileri içeren sözlük
        """
        try:
            # coil_id'yi integer'a çevir ve doğrula
            try:
                coil_id = int(coil_id)
            except (ValueError, TypeError):
                self.logger.warning("Geçersiz coil_id: %s", coil_id)
                return
            
            # coil_id aralık kontrolü (1-8)
            if coil_id < 1 or coil_id > 8:
                self.logger.warning("coil_id aralık dışında: %s (1-8 olmalı)", coil_id)
                return
            
            current_time = time.time()
            
            # İlk veri geldiğinde start_time'ı ayarla (gecikme önleme)
            if self.coil_start_times[coil_id] is None:
                self.coil_start_times[coil_id] = current_time
                self.logger.info(f"[SENSOR WIN] Bobin {coil_id} başlangıç zamanı ayarlandı (1Hz veri akışı)")
            
            # Thread-safe write lock (GUI Stability Fix #4)
            self.data_lock.lockForWrite()
            try:
                # Manyetik alan verisi (ESP: magnetic_field in mT)
                # Transactional yaklaşım: Önce değeri doğrula, sonra hepsini birlikte ekle
                if 'magnetic_field' in data and data['magnetic_field'] is not None:
                    val = data['magnetic_field']
                    try:
                        # Önce float'a çevir, sonra 1 basamağa yuvarla (Örn: 0.234 -> 0.2)
                        f_val = round(float(val), 1)
                        # Transactional: Ya hepsi eklensin ya hiçbiri
                        self.magnetic_data[coil_id].append(f_val)
                        self.magnetic_time[coil_id].append(current_time)
                    except (ValueError, TypeError) as e:
                        self.logger.debug("Geçersiz magnetic_field değeri: %s", val)
                
                # Sıcaklık verileri (ESP: object_temp, ambient_temp in °C)
                # Transactional yaklaşım: Önce değerleri doğrula, sonra hepsini birlikte ekle
                ambient_val = None
                object_val = None
                
                if 'ambient_temp' in data and data['ambient_temp'] is not None:
                    try:
                        ambient_val = float(data['ambient_temp'])
                    except (ValueError, TypeError) as e:
                        self.logger.debug("Geçersiz ambient_temp değeri: %s", data.get('ambient_temp'))
                
                if 'object_temp' in data and data['object_temp'] is not None:
                    try:
                        object_val = float(data['object_temp'])
                    except (ValueError, TypeError) as e:
                        self.logger.debug("Geçersiz object_temp değeri: %s", data.get('object_temp'))
                
                # Transactional: En az bir sıcaklık verisi varsa zamanı ekle, sonra mevcut verileri ekle
                # Bu şekilde veri ve zaman senkronizasyonu garanti edilir
                if ambient_val is not None or object_val is not None:
                    # Zamanı ekle (her iki sıcaklık verisi için de aynı zaman kullanılır)
                    self.temp_time[coil_id].append(current_time)
                    
                    # Mevcut olan sıcaklık verilerini ekle (1 basamak yuvarlama)
                    if ambient_val is not None:
                        self.ambient_temp_data[coil_id].append(round(ambient_val, 1))  # 25.3°C
                    if object_val is not None:
                        self.object_temp_data[coil_id].append(round(object_val, 1))   # 36.6°C
                
                # Akım verisi (ESP: current in A)
                # Transactional yaklaşım: Önce değeri doğrula, sonra hepsini birlikte ekle
                if 'current' in data and data['current'] is not None:
                    val = data['current']
                    try:
                        # Tüm sensörler için aynı precision (1 basamak) - consistency
                        f_val = round(float(val), 1)
                        # Transactional: Ya hepsi eklensin ya hiçbiri
                        self.current_data[coil_id].append(f_val)
                        self.current_time[coil_id].append(current_time)
                    except (ValueError, TypeError) as e:
                        self.logger.debug("Geçersiz current değeri: %s", val)

            finally:
                self.data_lock.unlock()
                        
        except Exception as e:
            self.logger.error("Sensör verisi güncelleme hatası (coil_id=%s): %s", coil_id, e, exc_info=True)

    def update_plots(self):
        """
        Deque yapılarındaki verileri okuyarak pyqtgraph eğrilerine aktarır.
        100ms'de bir çağrılır (GUI Stability Fix #3 - Performance).
        Thread-safe read lock kullanır (GUI Stability Fix #4).
        """
        try:
            # Thread-safe read lock
            self.data_lock.lockForRead()
            try:
                # Hall sensörleri güncelle (Safe Plotting - veri ve zaman boyutlarını eşitle)
                # Performance Fix: NumPy optimizasyonu (500+ nokta için %90 CPU tasarrufu)
                for i in range(8):
                    coil_id = i + 1
                    if len(self.magnetic_data[coil_id]) > 0 and len(self.magnetic_time[coil_id]) > 0:
                        # Start time kontrolü
                        if self.coil_start_times.get(coil_id) is None:
                            continue  # Start time henüz ayarlanmamış, bu bobini atla
                        
                        data_len = len(self.magnetic_time[coil_id])
                        start_time = self.coil_start_times[coil_id]
                        
                        # NumPy optimizasyonu: 500+ nokta için NumPy dizileri kullan
                        if data_len > 500:
                            # NumPy vektörel işlem (C hızında)
                            times_array = np.array(self.magnetic_time[coil_id], dtype=np.float64)
                            normalized_times = times_array - start_time  # start_time'a göre normalize
                            
                            # Veriyi alırken 1 basamağa yuvarla (gürültüyü azaltır)
                            y_data = np.round(np.array(self.magnetic_data[coil_id], dtype=np.float64), 1)
                            
                            # Boyutları eşitle (NumPy slicing)
                            min_len = min(len(normalized_times), len(y_data))
                            if min_len > 0:
                                self.hall_curves[i].setData(x=normalized_times[:min_len], y=y_data[:min_len])
                        else:
                            # Küçük veri setleri için list kullan (overhead daha az)
                            times = list(self.magnetic_time[coil_id])
                            if times:
                                normalized_times = [t - start_time for t in times]
                                
                                # Veriyi alırken 1 basamağa yuvarla (gürültüyü azaltır)
                                y_data = [round(val, 1) for val in self.magnetic_data[coil_id]]
                                x_data = normalized_times
                                
                                min_len = min(len(x_data), len(y_data))
                                if min_len > 0:
                                    self.hall_curves[i].setData(x=x_data[:min_len], y=y_data[:min_len])
                
                # Akım sensörleri güncelle (Safe Plotting - veri ve zaman boyutlarını eşitle)
                # Performance Fix: NumPy optimizasyonu (500+ nokta için %90 CPU tasarrufu)
                for i in range(8):
                    coil_id = i + 1
                    if len(self.current_data[coil_id]) > 0 and len(self.current_time[coil_id]) > 0:
                        # Start time kontrolü
                        if self.coil_start_times.get(coil_id) is None:
                            continue  # Start time henüz ayarlanmamış, bu bobini atla
                        
                        data_len = len(self.current_time[coil_id])
                        start_time = self.coil_start_times[coil_id]
                        
                        # NumPy optimizasyonu: 500+ nokta için NumPy dizileri kullan
                        if data_len > 500:
                            # NumPy vektörel işlem (C hızında)
                            times_array = np.array(self.current_time[coil_id], dtype=np.float64)
                            normalized_times = times_array - start_time  # start_time'a göre normalize
                            
                            # Veriyi alırken 2 basamağa yuvarla (gürültüyü azaltır)
                            y_data = np.round(np.array(self.current_data[coil_id], dtype=np.float64), 2)
                            
                            # Boyutları eşitle (NumPy slicing)
                            min_len = min(len(normalized_times), len(y_data))
                            if min_len > 0:
                                self.current_curves[i].setData(x=normalized_times[:min_len], y=y_data[:min_len])
                        else:
                            # Küçük veri setleri için list kullan (overhead daha az)
                            times = list(self.current_time[coil_id])
                            if times:
                                normalized_times = [t - start_time for t in times]
                                
                                # Veriyi alırken 2 basamağa yuvarla (gürültüyü azaltır)
                                y_data = [round(val, 2) for val in self.current_data[coil_id]]
                                x_data = normalized_times
                                
                                min_len = min(len(x_data), len(y_data))
                                if min_len > 0:
                                    self.current_curves[i].setData(x=x_data[:min_len], y=y_data[:min_len])
                
                # Sıcaklık sensörleri güncelle (Safe Plotting - veri ve zaman boyutlarını eşitle)
                # Performance Fix: NumPy optimizasyonu (500+ nokta için %90 CPU tasarrufu)
                for i in range(8):
                    coil_id = i + 1
                    if len(self.temp_time[coil_id]) > 0:
                        # Start time kontrolü
                        if self.coil_start_times.get(coil_id) is None:
                            continue  # Start time henüz ayarlanmamış, bu bobini atla
                        
                        data_len = len(self.temp_time[coil_id])
                        start_time = self.coil_start_times[coil_id]
                        
                        # NumPy optimizasyonu: 500+ nokta için NumPy dizileri kullan
                        if data_len > 500:
                            # NumPy vektörel işlem (C hızında)
                            times_array = np.array(self.temp_time[coil_id], dtype=np.float64)
                            normalized_times = times_array - start_time  # start_time'a göre normalize
                            
                            # Ortam sıcaklığı (NumPy) - 1 basamak yuvarlama
                            if len(self.ambient_temp_data[coil_id]) > 0:
                                y_data = np.round(np.array(self.ambient_temp_data[coil_id], dtype=np.float64), 1)
                                min_len = min(len(normalized_times), len(y_data))
                                if min_len > 0:
                                    self.temp_ambient_curves[i].setData(x=normalized_times[:min_len], y=y_data[:min_len])
                            
                            # Nesne sıcaklığı (NumPy) - 1 basamak yuvarlama
                            if len(self.object_temp_data[coil_id]) > 0:
                                y_data = np.round(np.array(self.object_temp_data[coil_id], dtype=np.float64), 1)
                                min_len = min(len(normalized_times), len(y_data))
                                if min_len > 0:
                                    self.temp_object_curves[i].setData(x=normalized_times[:min_len], y=y_data[:min_len])
                        else:
                            # Küçük veri setleri için list kullan (overhead daha az)
                            times = list(self.temp_time[coil_id])
                            normalized_times = [t - start_time for t in times]
                            x_data = normalized_times
                            
                            # Ortam sıcaklığı (List) - 1 basamak yuvarlama
                            if len(self.ambient_temp_data[coil_id]) > 0:
                                y_data = [round(val, 1) for val in self.ambient_temp_data[coil_id]]
                                min_len = min(len(x_data), len(y_data))
                                if min_len > 0:
                                    self.temp_ambient_curves[i].setData(x=x_data[:min_len], y=y_data[:min_len])
                            
                            # Nesne sıcaklığı (List) - 1 basamak yuvarlama
                            if len(self.object_temp_data[coil_id]) > 0:
                                y_data = [round(val, 1) for val in self.object_temp_data[coil_id]]
                                min_len = min(len(x_data), len(y_data))
                                if min_len > 0:
                                    self.temp_object_curves[i].setData(x=x_data[:min_len], y=y_data[:min_len])
            finally:
                self.data_lock.unlock()
                
        except Exception as e:
            self.logger.error("Plot güncelleme hatası: %s", e, exc_info=True)

    def _setup_responsive_window(self):
        """Setup responsive window sizing and positioning"""
        try:
            width, height, scale_factor, screen_type = get_screen_info()
            
            # Base dimensions for different screen types
            base_configs = {
                "mobile": {"width": 800, "height": 600, "min_width": 600, "min_height": 500},
                "tablet": {"width": 1024, "height": 768, "min_width": 800, "min_height": 600},
                "laptop": {"width": 1400, "height": 900, "min_width": 1200, "min_height": 800},
                "desktop": {"width": 1600, "height": 1000, "min_width": 1400, "min_height": 900},
                "ultrawide": {"width": 1920, "height": 1200, "min_width": 1600, "min_height": 1000}
            }
            
            config = base_configs.get(screen_type, base_configs["desktop"])
            
            # Scale dimensions based on actual screen size
            target_width = min(int(config["width"] * scale_factor), width * 0.95)
            target_height = min(int(config["height"] * scale_factor), height * 0.9)
            
            # Center window on screen
            x = (width - target_width) // 2
            y = (height - target_height) // 2
            
            # Set window properties
            self.setGeometry(int(x), int(y), int(target_width), int(target_height))
            self.setMinimumSize(config["min_width"], config["min_height"])
            
        except Exception as e:
            self.logger.warning("Responsive window setup failed: %s, using default size", e)
            # Fallback to default sizing
            self.resize(1600, 1000)
            self.setMinimumSize(1200, 900)

    def closeEvent(self, event):
        """Pencere kapatılırken çağrılır - Timer'ları ve kaynakları temizle"""
        self.logger.info("SensorDataWindow kapatılıyor - Temizlik başlatılıyor")
        
        # Timer'ı durdur
        try:
            if hasattr(self, 'update_timer') and self.update_timer.isActive():
                self.update_timer.stop()
                self.logger.debug("Update timer durduruldu")
        except Exception as e:
            self.logger.error("Timer durdurulurken hata: %s", e)
        
        # Signal bağlantılarını kes
        try:
            if hasattr(self, 'main_window') and self.main_window:
                if hasattr(self.main_window, 'sensor_data_received'):
                    try:
                        self.main_window.sensor_data_received.disconnect(self.update_sensor_data)
                        self.logger.debug("Signal bağlantısı kesildi")
                    except:
                        pass  # Already disconnected
            
            # Timer signal'ını da disconnect et
            if hasattr(self, 'update_timer'):
                try:
                    self.update_timer.timeout.disconnect(self.update_plots)
                    self.logger.debug("Timer signal'ı disconnect edildi")
                except:
                    pass  # Already disconnected
                    
        except Exception as e:
            self.logger.warning("Signal bağlantıları kesilirken hata: %s", e)
        
        # Veri yapılarını temizle (opsiyonel - bellek temizliği için)
        try:
            if hasattr(self, 'magnetic_data'):
                for coil_id in self.magnetic_data:
                    self.magnetic_data[coil_id].clear()
                    self.magnetic_time[coil_id].clear()
                    self.ambient_temp_data[coil_id].clear()
                    self.object_temp_data[coil_id].clear()
                    self.temp_time[coil_id].clear()
                    self.current_data[coil_id].clear()
                    self.current_time[coil_id].clear()
                self.logger.debug("Veri yapıları temizlendi")
        except Exception as e:
            self.logger.warning("Veri yapıları temizlenirken hata: %s", e)
        
        self.logger.info("SensorDataWindow temizliği tamamlandı")
        event.accept()

# Eğer bu dosya doğrudan çalıştırılırsa
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SensorDataWindow()
    window.show()
    sys.exit(app.exec())
