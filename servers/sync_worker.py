"""
Supabase Background Sync Worker
================================
Bu modul, lokal SQLite veritabanlarındaki (patients, treatment_sessions)
değişiklikleri arka planda kontrol edip Supabase bulut veritabanı ile eşitler.
"""
import logging
import os
import threading
from typing import Optional

from database.patient_database import get_patient_database
from database.treatment_history_db import get_treatment_db

logger = logging.getLogger(__name__)

class CloudSyncWorker:
    def __init__(self, supabase_url: str, supabase_key: str, interval_sec: int = 60):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.interval_sec = interval_sec
        self.stop_event = threading.Event()
        self.client = None
        self.thread: Optional[threading.Thread] = None

        # GİZLİLİK (tıbbi cihaz): Hasta/seans PII'sinin buluta sync'i VARSAYILAN KAPALI.
        # Açmak için ortam değişkeni PEMF_CLOUD_PATIENT_SYNC=1. Açıkken bile tüm push/pull
        # sorguları device_id ile izole edilir → başka kliniğin verisi ne gönderilir ne çekilir.
        self.patient_sync_enabled = os.environ.get("PEMF_CLOUD_PATIENT_SYNC", "0") == "1"
        try:
            from utils.path_utils import get_unique_device_id
            self.device_id = get_unique_device_id()
        except Exception:
            self.device_id = "unknown-device"
        self._reg_secret = None  # Coverage-audit P1: bulut capability-token cache (_registry_secret)

        self.client = None
        if self.supabase_url and self.supabase_key:
            self._ensure_client()  # ilk deneme; başarısızsa _sync_loop HER TURDA tekrar dener (self-heal)
        else:
            logger.warning("Supabase URL veya Key belirtilmedigi icin Cloud Sync deaktif.")

    def _ensure_client(self) -> bool:
        """Supabase istemcisini (yeniden) kur. Self-heal: internetsiz/paket-hatalı boot'ta client None
        kalırsa döngü her turda tekrar dener → 'client YALNIZ __init__'te kurulur, patlarsa restart'a
        kadar sync ölür' boşluğunu kapatır (reconnect-audit)."""
        if self.client:
            return True
        if not (self.supabase_url and self.supabase_key):
            return False
        try:
            from supabase import create_client
            self.client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase istemcisi olusturuldu.")
            return True
        except ImportError:
            logger.error("Supabase paketi kurulu degil (pip install supabase).")
            return False
        except Exception as e:
            logger.debug(f"Supabase client kurulamadi (sonraki turda tekrar denenecek): {e}")
            return False

    def _registry_secret(self) -> str:
        """Coverage-audit P1: bulut capability-token (device_registry_secret) — Supabase RPC'lerinde
        device_id (gizli-değil) yerine YETKİ. İlk publish'te bulut secret_hash'e TOFU ile mühürlenir;
        sonra her RPC bunu p_secret olarak gönderir. Cache'li."""
        if self._reg_secret:
            return self._reg_secret
        try:
            from utils.secrets_manager import get_secret
            self._reg_secret = get_secret("device_registry_secret") or ""
        except Exception:
            self._reg_secret = ""
        return self._reg_secret

    def publish_now(self, _url=None):
        """Tünel URL'si DEĞİŞİR DEĞİŞMEZ (tunnel_manager callback'i) cihaz kaydını ANINDA yayınla →
        60sn döngü beklenmez; telefon rotasyon/cold-boot sonrası eski/null URL görmez (audit: yayın gecikmesi)."""
        try:
            self._publish_device_registry()
        except Exception as e:
            logger.debug(f"publish_now hatasi: {e}")

    def start(self):
        # client HENÜZ kurulamamış olsa da (internetsiz boot) döngüyü başlat → _ensure_client her turda
        # tekrar dener (self-heal). Yalnız yapılandırma yoksa (url/key) hiç başlatma.
        if not (self.supabase_url and self.supabase_key):
            return

        # Tünel URL'si bulunur/değişir bulunmaz ANINDA yayın (60sn döngü beklemeden) — Supabase'deki
        # eski/null URL penceresini kapatır. Callback module-global listede → tünel restart'larında kalıcı.
        try:
            from servers.tunnel_manager import register_url_callback
            register_url_callback(self.publish_now)
        except Exception:
            pass

        self.thread = threading.Thread(target=self._sync_loop, daemon=True, name="CloudSyncWorker")
        self.thread.start()
        logger.info("CloudSyncWorker arka planda baslatildi.")

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def _sync_loop(self):
        # SPLIT-BRAIN FIX: canonical app_data_dir (PEMF_DATA_DIR → ProgramData). Eskiden APPDATA
        # kullaniliyordu; servis LocalSystem'de APPDATA=...\systemprofile\... → API/DB'nin yazdigi
        # dosyadan FARKLI patients.db/treatment_history.db acilip BOS/eski DB Supabase'e sync ediliyordu.
        from utils.path_utils import get_app_data_directory
        app_data_dir = get_app_data_directory()
        patient_db = get_patient_database(app_data_dir)
        session_db = get_treatment_db(app_data_dir)

        if not self.patient_sync_enabled:
            logger.warning("Hasta/seans BULUT SYNC KAPALI (gizlilik korumasi). Acmak icin PEMF_CLOUD_PATIENT_SYNC=1. Cihaz kayit defteri/uzaktan erisim aktif kalir.")

        backoff = self.interval_sec
        while not self.stop_event.is_set():
            # Self-heal: client henüz kurulamadıysa (internetsiz boot / paket) tekrar KUR; olmuyorsa backoff.
            if not self._ensure_client():
                backoff = min(max(backoff, self.interval_sec) * 2, 300)
                self.stop_event.wait(backoff)
                continue
            # Cihaz erisim bilgisini (tunnel_url/local_ip) once yayinla -> mobil
            # temassiz uzaktan baglanti icin kritik; hasta/seans sync'ten bagimsiz.
            ok = True
            try:
                if not self._publish_device_registry():
                    ok = False
            except Exception as e:
                logger.debug(f"Device registry publish hatasi: {e}")
                ok = False
            if self.patient_sync_enabled:
                try:
                    self._sync_patients(patient_db)
                    self._sync_sessions(session_db)
                except Exception as e:
                    logger.error(f"Sync sirasinda beklenmeyen hata: {e}")
                    ok = False

            # BACKOFF (reconnect-audit): başarılı→interval_sec'e SIFIRLA; ağ-down→×2 (üst 300sn) → uzun
            # kesintide gereksiz RPC + log-gürültüsü azalır; geri gelince ilk başarıda hemen normale döner.
            backoff = self.interval_sec if ok else min(max(backoff, self.interval_sec) * 2, 300)
            self.stop_event.wait(backoff)

    def _sync_patients(self, patient_db):
        try:
            # Audit P2 #14: kilidi ağ-RPC boyunca TUTMA (PULL ile aynı desen). Unsynced satırları
            # kilit altında SNAPSHOT'la, kilidi BIRAK, upsert_patient RPC'lerini KİLİTSİZ yap, sonra
            # yalnız sync_status UPDATE için KISA yeniden-kilitle. Aksi halde Supabase yavaş/erişilmezse
            # add/get/search + KVKK unutulma-hakkı silme dahil TÜM hasta-DB işlemleri bloklanırdı.
            with patient_db.lock:
                with patient_db._get_connection() as conn:
                    conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}  # SQLCipher-uyumlu
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM patients WHERE sync_status = 0")
                    unsynced_patients = [dict(row) for row in cursor.fetchall()]

            for patient_data in unsynced_patients:
                # SQLite row'u supabase formatina donustur
                payload = {
                    "id": patient_data["id"],
                    "device_id": self.device_id,  # cross-tenant izolasyon
                    # PII alanları ŞİFRELİ (enc:) gönderilir → buluta düz-metin PII YAZILMAZ.
                    "name": patient_data["name"],
                    "species": patient_data["species"],
                    "breed": patient_data["breed"],
                    "age": patient_data["age"],
                    "weight": patient_data["weight"],
                    "owner": patient_data["owner"],
                    "vet_contact": patient_data["vet_contact"],
                    "created_at": patient_data["created_at"],
                    "updated_at": patient_data["updated_at"]
                }
                # P1 audit 2026-06-28: RLS+RPC — dogrudan tablo upsert (anon, RLS-yok) YERINE
                # SECURITY DEFINER upsert_patient RPC (device_id'yi SUNUCU-TARAFI zorlar). KİLİTSİZ.
                try:
                    self.client.rpc("upsert_patient", {"p_device_id": self.device_id, "p_patient": payload, "p_secret": self._registry_secret()}).execute()
                except Exception as _re:
                    logger.error(f"Hasta {patient_data['id']} PUSH RPC hatasi: {_re}")
                    continue
                # RPC istisna firlatmadiysa basarili → sync_status'u KISA kilitle güncelle.
                with patient_db.lock:
                    with patient_db._get_connection() as conn:
                        conn.execute("UPDATE patients SET sync_status = 1 WHERE id = ?", (patient_data["id"],))
                        conn.commit()
                logger.info(f"Hasta {patient_data['id']} Supabase'e senkronize edildi (RPC).")

        except Exception as e:
            logger.error(f"Patient PUSH hatasi: {e}")
            
        # PULL: Supabase'den lokal SQLite'a indir
        try:
            # Sadece BU cihazın kayıtları (cross-tenant izolasyon); decrypt-guard defense-in-depth.
            # P1 audit: RLS+RPC — dogrudan SELECT (anon kapali) YERINE resolve_patients RPC.
            # Audit P2: RPC'yi patient_db.lock DIŞINDA çağır — kilidi ağ-çağrısı boyunca tutmak tüm
            # hasta-DB işlemlerini (add/get/search + delete unutulma-hakkı) bloklardı. Sonucu al,
            # SONRA kısa DB-yazımı için kilitle.
            res = self.client.rpc("resolve_patients", {"p_device_id": self.device_id, "p_secret": self._registry_secret()}).execute()
            with patient_db.lock:
                with patient_db._get_connection() as conn:
                    cursor = conn.cursor()
                    if res.data:
                        skipped = 0
                        for rp in res.data:
                            name_val = rp.get("name", "") or ""
                            # CROSS-TENANT KORUMASI: Bulut 'patients' tablosu PAYLAŞIMLI; başka
                            # cihazların kayıtları da geliyor. Bu makinenin anahtarıyla ÇÖZÜLEMEYEN
                            # kayıt BAŞKA bir kliniğe aittir → lokale çekme (gizlilik ihlali +
                            # "bozuk/okunamayan kayıt" kirliliği önlenir). Kendi kayıtların çözülür → çekilir.
                            try:
                                dec = patient_db._decrypt_field(name_val) if name_val else ""
                            except Exception:
                                dec = "[okunamayan kayıt]"
                            if dec == "[okunamayan kayıt]":
                                skipped += 1
                                continue
                            # D-1: INSERT OR REPLACE YERİNE ON CONFLICT DO UPDATE. REPLACE = DELETE+INSERT →
                            # (a) sync'e-ait-OLMAYAN kolonları (owner_email/last_treatment_at/anonymized)
                            # varsayılana sıfırlıyordu; (b) FK-cascade patient_search_index'i siliyordu
                            # (hasta aranamaz olurdu). ON CONFLICT DO UPDATE yalnız sync-sahibi kolonları
                            # günceller → diğerleri + arama-indeksi KORUNUR.
                            cursor.execute(
                                """
                                INSERT INTO patients
                                (id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at, sync_status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                                ON CONFLICT(id) DO UPDATE SET
                                    name=excluded.name, species=excluded.species, breed=excluded.breed,
                                    age=excluded.age, weight=excluded.weight, owner=excluded.owner,
                                    vet_contact=excluded.vet_contact, updated_at=excluded.updated_at, sync_status=1
                                """,
                                (
                                    rp.get("id"), rp.get("name", ""), rp.get("species", ""), rp.get("breed", ""),
                                    rp.get("age", ""), rp.get("weight", ""), rp.get("owner", ""), rp.get("vet_contact", ""),
                                    rp.get("created_at"), rp.get("updated_at")
                                )
                            )
                        conn.commit()
                        if skipped:
                            logger.warning(f"Patient PULL: {skipped} yabanci/cozulemeyen kayit atlandi (cross-tenant korumasi).")
        except Exception as e:
            logger.error(f"Patient PULL hatasi: {e}")

    def _sync_sessions(self, session_db):
        # PUSH: Lokalden Supabase'e gönder
        try:
            with session_db._get_connection() as conn:
                conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}  # SQLCipher-uyumlu (sqlite3.Row, sqlcipher3 cursor'ı SARMAZ → at-rest-şifreli DB'de PUSH TypeError'la patlıyordu)
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM treatment_sessions WHERE sync_status = 0")
                unsynced_sessions = cursor.fetchall()
                
                for row in unsynced_sessions:
                    session_data = dict(row)
                    payload = {
                        "id": session_data["id"],
                        "device_id": self.device_id,  # cross-tenant izolasyon
                        "session_date": session_data["session_date"],
                        "start_time": session_data["start_time"],
                        "end_time": session_data["end_time"],
                        "duration_minutes": session_data["duration_minutes"],
                        "treatment_mode": session_data["treatment_mode"],
                        "target_condition": session_data["target_condition"],
                        "frequency_hz": session_data["frequency_hz"],
                        "intensity_mt": session_data["intensity_mt"],
                        "pulse_duration_ms": session_data["pulse_duration_ms"],
                        # GİZLİLİK: PII'yi paylaşımlı buluta DÜZ-METİN gönderme. Telemetri (parametre/
                        # tarih/durum) sync olur; hasta adı/notu/operatör LOKAL kalır (redacted).
                        "operator_name": None,
                        "patient_name": None,
                        "patient_notes": None,
                        "session_status": session_data["session_status"],
                        "created_at": session_data["created_at"]
                    }
                    
                    # P1 audit 2026-06-28: RLS+RPC — upsert_session RPC (device_id sunucu-tarafi).
                    self.client.rpc("upsert_session", {"p_device_id": self.device_id, "p_session": payload, "p_secret": self._registry_secret()}).execute()
                    cursor.execute("UPDATE treatment_sessions SET sync_status = 1 WHERE id = ?", (session_data["id"],))
                    conn.commit()
                    logger.info(f"Seans {session_data['id']} Supabase'e senkronize edildi (RPC).")
                        
        except Exception as e:
            logger.error(f"Session PUSH hatasi: {e}")
            
        # PULL: Supabase'den lokal SQLite'a indir
        try:
            with session_db._get_connection() as conn:
                cursor = conn.cursor()
                # P1 audit: RLS+RPC — resolve_sessions RPC.
                res = self.client.rpc("resolve_sessions", {"p_device_id": self.device_id, "p_secret": self._registry_secret()}).execute()
                if res.data:
                    for rs in res.data:
                        # D-1: INSERT OR REPLACE YERİNE ON CONFLICT DO UPDATE. REPLACE = DELETE+INSERT →
                        # (a) FK-cascade seansın TÜM child kayıtlarını (session_parameters/sensor_samples/
                        # session_events/session_coil_runs) SİLERDİ = seans-detayı kaybı; (b) PUSH PII'yi
                        # None redacte ettiğinden pull-back yerel patient_name/notes/operator'ı EZERDİ.
                        # DO UPDATE: child-cascade YOK + PII kolonları güncellenMEZ (yerel PII KORUNUR).
                        cursor.execute(
                            """
                            INSERT INTO treatment_sessions
                            (id, session_date, start_time, end_time, duration_minutes, treatment_mode, target_condition, frequency_hz, intensity_mt, pulse_duration_ms, operator_name, patient_name, patient_notes, session_status, created_at, sync_status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                            ON CONFLICT(id) DO UPDATE SET
                                session_date=excluded.session_date, start_time=excluded.start_time,
                                end_time=excluded.end_time, duration_minutes=excluded.duration_minutes,
                                treatment_mode=excluded.treatment_mode, target_condition=excluded.target_condition,
                                frequency_hz=excluded.frequency_hz, intensity_mt=excluded.intensity_mt,
                                pulse_duration_ms=excluded.pulse_duration_ms, session_status=excluded.session_status,
                                sync_status=1
                            """,
                            (
                                rs.get("id"), rs.get("session_date"), rs.get("start_time"), rs.get("end_time"), rs.get("duration_minutes"),
                                rs.get("treatment_mode"), rs.get("target_condition"), rs.get("frequency_hz"), rs.get("intensity_mt"), rs.get("pulse_duration_ms"),
                                rs.get("operator_name"), rs.get("patient_name"), rs.get("patient_notes"), rs.get("session_status"), rs.get("created_at")
                            )
                        )
                    conn.commit()
        except Exception as e:
            logger.error(f"Session PULL hatasi: {e}")

    def _publish_device_registry(self):
        """Bu cihazin guncel erisim bilgisini Supabase 'devices' tablosuna yazar.

        Mobil uygulama ayni WiFi'de cihazi (mDNS) bulamadiginda, device_id ile bu
        tablodan guncel tunnel_url'i cekip TEMASSIZ (QR'siz) uzaktan baglanir.
        'last_seen' bir heartbeat'tir (cihazin canli oldugunu gosterir).
        """
        if not self.client:
            return False
        try:
            from datetime import datetime, timezone

            from servers.auto_discovery import _get_local_ip
            from servers.tunnel_manager import get_tunnel_url
            from utils.path_utils import get_pairing_code, get_unique_device_id

            # Tünel anlık düşse de (URL boş) registry'yi NULL ile EZME → son bilinen URL korunur,
            # böylece app'in resolve'u boşa düşmez (watchdog tüneli toparlayınca yeni URL güncellenir).
            cur_url = get_tunnel_url() or None
            if cur_url:
                self._last_tunnel_url = cur_url
            payload = {
                "device_id": get_unique_device_id(),
                "name": os.environ.get("PEMF_DEVICE_NAME", "PEMF-Vet"),
                "tunnel_url": cur_url or getattr(self, "_last_tunnel_url", None),
                "local_ip": _get_local_ip(),
                "api_port": 8000,
                "pairing_code": get_pairing_code(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
            try:
                # GUVENLI YOL: SECURITY DEFINER 'upsert_device' RPC ile yaz. RLS'i guvenli
                # sekilde asar → anon'a DOGRUDAN tablo INSERT/UPDATE vermeye gerek yok
                # (cross-tenant dump + tunnel poisoning yuzeyi daralir). Kullanici RPC SQL'ini
                # calistirdiysa bu yol calisir; degilse asagidaki eski tablo-upsert'e duser.
                self.client.rpc("upsert_device", {
                    "p_device_id": payload["device_id"],
                    "p_name": payload["name"],
                    "p_tunnel_url": payload["tunnel_url"],
                    "p_local_ip": payload["local_ip"],
                    "p_api_port": payload["api_port"],
                    "p_pairing_code": payload["pairing_code"],
                    "p_secret": self._registry_secret(),   # Coverage-audit P1: capability-token (TOFU + doğrulama)
                }).execute()
            except Exception as _rpc_err:
                # DENETIM P2: BU except HER hatayi "RPC yok" sayiyordu (yetki, ag, secret-mismatch
                # hepsi ayni dala dusuyordu). En zararlisi TOFU muhru: cihaz yeniden kurulunca
                # device_secret degisir, RPC "secret mismatch" verir; kod bunu "RPC yok" sanip
                # anon tablo-upsert deniyor, v2 SQL'de anon INSERT/UPDATE politikalari kaldirildigi
                # icin O DA basarisiz oluyor → registry KALICI olarak guncellenmiyor ve operatore
                # yalnizca yaniltici "RPC yok" uyarisi gorunuyordu. Artik siniflandiriliyor.
                _msg = str(_rpc_err).lower()
                if "secret" in _msg and ("mismatch" in _msg or "match" in _msg):
                    # Kalici durum: fallback DENEME (zaten reddedilir) — GORUNUR hata yayinla.
                    self._registry_status = "secret_mismatch"
                    logger.error(
                        "Device registry: SIR UYUSMAZLIGI (TOFU muhru). Bu cihaz-id bulutta BASKA "
                        "bir sirla muhurlenmis — muhtemelen yeniden kurulum sonrasi device_secret "
                        "degisti. Uzaktan erisim GUNCELLENMEYECEK. Cozum: Supabase'de bu device_id "
                        "kaydini silin ya da eski siri geri yukleyin. Ayrinti: %s", _rpc_err)
                    return False
                if "pgrst202" in _msg or "does not exist" in _msg or "not found" in _msg:
                    # Audit P3: SECURITY DEFINER upsert_device RPC yok → eski anon tablo-upsert. pairing_code
                    # (auth-bearer sır) geniş-okunur tabloya ASLA yazılmaz (RLS yanlış-yapılandırılırsa
                    # okunur/tünel-zehirlenir) → pairing_code'u ÇIKAR + GÖRÜNÜR uyar (RPC deploy edilmeli).
                    logger.warning("Device registry: upsert_device RPC yok → anon tablo-upsert (pairing_code ATLANDI; uzaktan-pairing için RPC deploy edilmeli).")
                    self._registry_status = "rpc_missing"
                    fallback = {k: v for k, v in payload.items() if k != "pairing_code"}
                    self.client.table("devices").upsert(fallback, on_conflict="device_id").execute()
                else:
                    # Ag/gecici hata → fallback DENEME (yanlis-pozitif "RPC yok" uyarisi uretmesin);
                    # disaridaki except backoff'u ×2 yapsin.
                    self._registry_status = "error"
                    raise
            else:
                self._registry_status = "ok"
            return True   # publish OK → _sync_loop backoff'u interval_sec'e sıfırlar
        except Exception as e:
            # Yazilamadi (tablo yok / RLS / RPC yok). Sync'i bozma ama GORUNUR logla
            # (eskiden DEBUG'ta sessizce yutuluyordu → registry'nin neden bos kaldigi gizleniyordu).
            logger.warning(f"Device registry publish BASARISIZ: {e}")
            return False  # ağ/RPC hatası → _sync_loop backoff'u ×2 (üst 300sn) → uzun kesintide gürültü azalır


def get_registry_status() -> str:
    """Bulut cihaz-registry'sinin SON yayin durumu: ok | secret_mismatch | rpc_missing | error | unknown.

    DENETIM P2: 'secret_mismatch' (TOFU muhru — yeniden kurulum sonrasi device_secret degisti)
    KALICI bir durumdur ve yalnizca log'a dusuyordu; operator uzaktan erisimin neden sessizce
    guncellenmedigini goremiyordu. /api/health uzerinden gorunur kilinir.
    """
    w = _sync_worker
    return getattr(w, "_registry_status", "unknown") if w is not None else "unknown"


# Global instance for easy access
_sync_worker = None

def init_cloud_sync(supabase_url: str, supabase_key: str):
    global _sync_worker
    if _sync_worker is None:
        _sync_worker = CloudSyncWorker(supabase_url, supabase_key)
        _sync_worker.start()

def get_cloud_sync() -> Optional[CloudSyncWorker]:
    return _sync_worker
