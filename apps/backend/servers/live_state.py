# Author: mertaygn, cglrgrkn
"""Canlı-durum (live-state) çekirdeği — B-2.2 shared-state modül ayrımı.

api_server.py'nin WS/MQTT/session yollarının paylaştığı TEK gerçeklik kaynağı. Bu state + fonksiyonlar
eskiden api_server.py içindeydi (2400+ satır tek dosya); buraya taşındı → api_server yalnız HTTP/WS
yönlendirmesine odaklanır, canlı-durum mantığı bağımsız olarak sahiplenilir + test edilir
(bkz. tests/test_live_state.py — refactor-ÖNCESİ davranış kilidi, sonrası AYNI yeşil).

DAVRANIŞ BİREBİR KORUNUR. api_server.py bu isimlere aynı-nesne alias'larıyla bağlanır (dict/list/lock
in-place mutasyon → çağrı yerleri değişmez). WS broadcast event-loop'a bağımlı: api_server lifespan
`set_event_loop()` çağırır; `_event_loop` None iken broadcast erken-return no-op (thread güvenli)."""

import json
import logging
import threading
from collections import deque
from datetime import datetime

from fastapi import WebSocket
from utils import estop_mandali
from utils.path_utils import HARDWARE_VERSION, get_app_version

_APP_VERSION = get_app_version()

# ── WebSocket istemci kaydı + gönderim serileştirme ────────────────────────────
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()
# asyncio.Lock (event-loop'ta lazy olusturulur) — TUM broadcast send-donguelerini serilestirir.
# Cok sayida thread (MQTT/STM/sim/AI/bildirim) bagimsiz _send_all() coroutine'i planliyor →
# ayni WebSocket'e es-zamanli send_text = Starlette "Concurrent call to send()" / bozuk framing.
_ws_send_lock = None
_event_loop = None  # api_server lifespan'de set_event_loop() ile atanir


def set_event_loop(loop) -> None:
    """api_server lifespan STARTUP'ta çağırır → thread'lerden gelen broadcast'ler bu loop'a planlanır."""
    global _event_loop
    _event_loop = loop


def _ws_send_lock_get():
    """Event-loop'ta çalışan coroutine'lerden çağrılır → asyncio.Lock lazy-init güvenli (tek-thread)."""
    global _ws_send_lock
    if _ws_send_lock is None:
        import asyncio as _a

        _ws_send_lock = _a.Lock()
    return _ws_send_lock


# DENETIM P2 (geri-basinc): her yayin icin AYRI bir _send_all() planlaniyordu ve hepsi TEK bir
# _ws_send_lock'ta sıraya giriyordu. Yavas/yari-acik tek bir istemci her turda 5 sn tuttugu icin
# arkada sinirsiz coroutine + JSON gövdesi birikiyordu (bellek + gecikme). Telemetri yayinlari
# PERIYODIK ANLIK GORUNTU oldugundan bekleyen is birikince ESKISINI dusurmek dogru davranistir:
# istemci bir sonraki turda zaten guncel durumu alir. Sinir normalde asla tetiklenmez.
# ⚠️ D1.71 (B-1.11): yorum "ESKISINI dusur" diyordu ama kod sinirda GELEN YENI iletiyi atiyordu — takilan bir istemci
# kuyrugu doldurunca saglikli istemciler de STM kopmasini, E-stop'u, seans bitisini HIC gormuyordu (11/11 kayip, durum
# kendiliginden duzelmez). Artik sinirda kuyruktaki EN ESKI PERIYODIK ileti dusurulur; TEK SEFERLIK gecis iletileri
# (asagidaki kume DISINDA kalan her tur: stm_status, session_update, emergency_stop, estop_*, notification…) ASLA
# dusmez — gerekirse sinir asilir (seyrek; bellek sinirli kalir).
_WS_MAX_PENDING_BROADCASTS = 64
#: Yenisi eskisinin YERINI TUTAN periyodik anlik goruntuler (her biri o anin TAM durumunu tasir). Bilinmeyen tur
#: DUSURULMEZ (yeni bir tek-seferlik tur sessizce dusmesin diye varsayilan guvenli taraftadir).
_WS_PERIYODIK_TURLER = frozenset(
    {"sensor_data", "coil_status", "stm_coil_update", "ai_vision", "snapshot", "gateway_status"}
)
_ws_pending = 0
_ws_pending_lock = threading.Lock()
_ws_dropped_total = 0
#: Henuz gonderilmeye BASLAMAMIS yayin kayitlari (FIFO; `_ws_pending_lock` altinda). Ucustaki ileti buradan cikar ve
#: artik dusurulemez. Kayit: {"periyodik": bool, "dusuruldu": bool}.
_ws_bekleyenler: deque = deque()


def _ws_dusurme_kaydi(neden: str) -> None:
    """`_ws_pending_lock` ALTINDA çağrılır: düşürme sayacı + seyrek uyarı (log seli olmasın)."""
    global _ws_dropped_total
    _ws_dropped_total += 1
    if _ws_dropped_total % 100 == 1:
        logging.getLogger(__name__).warning(
            "WS yayin kuyrugu dolu (%d bekleyen) → %s (toplam %d). Yavas/yari-acik istemci olabilir.",
            _ws_pending,
            neden,
            _ws_dropped_total,
        )


def _ws_broadcast_sync(message: dict) -> None:
    """Thread-safe senkron broadcast (MQTT callback'lerinden çağrılır)."""
    import asyncio

    global _ws_pending
    if not _event_loop or not _ws_clients:
        return
    # D1.71 (B-1.27): serileştirme sayaçtan ÖNCE. Eskiden sayaç artırılıp `json.dumps` fırlatınca geri alınmıyordu: 64
    # serileştirilemeyen yayından sonra sınır kalıcı dolu kalıyor, bütün canlı akış ölüyordu (hata çağırana da —
    # ör. acil durdurma yoluna — sızıyordu). Serileştirilemeyen ileti günlüğe yazılıp ATLANIR.
    try:
        data = json.dumps(message, ensure_ascii=False)
    except Exception:
        logging.getLogger(__name__).exception(
            "WS yayini serilestirilemedi, atlandi (tur=%s)",
            (message or {}).get("type") if isinstance(message, dict) else "?",
        )
        return
    kayit = {"periyodik": message.get("type") in _WS_PERIYODIK_TURLER, "dusuruldu": False}
    with _ws_pending_lock:
        if _ws_pending >= _WS_MAX_PENDING_BROADCASTS:
            # D1.71 (B-1.11): sınırda GELEN ileti değil, kuyruktaki EN ESKİ periyodik ileti düşer.
            kurban = next((k for k in _ws_bekleyenler if k["periyodik"]), None)
            if kurban is not None:
                kurban["dusuruldu"] = True
                _ws_bekleyenler.remove(kurban)
                _ws_pending -= 1
                _ws_dusurme_kaydi("en eski periyodik anlik goruntu dusuruldu")
            elif kayit["periyodik"]:
                _ws_dusurme_kaydi("kuyrukta yalniz tek-seferlik ileti var, yeni periyodik ileti dusuruldu")
                return
            # Tek seferlik geçiş iletisi: sınır aşılsa da KABUL edilir (asla düşmez).
        _ws_pending += 1
        _ws_bekleyenler.append(kayit)
    with _ws_lock:
        clients = list(_ws_clients)

    async def _send_all():
        global _ws_pending
        try:
            dead = []
            async with _ws_send_lock_get():
                with _ws_pending_lock:
                    if kayit["dusuruldu"]:
                        return  # sınırda düşürüldü (sayaç düşürmede geri sayıldı)
                    try:
                        _ws_bekleyenler.remove(kayit)  # artık UÇUŞTA: düşürülemez
                    except ValueError:
                        pass
                for ws in clients:
                    try:
                        # P-2: per-send timeout — yavaş/yarı-açık istemci tüm broadcast'i (→ tüm filoyu)
                        # bloklamasın; 5sn'de yanıtlamayan istemci DÜŞÜRÜLÜR (except Exception TimeoutError'ı
                        # da yakalar → dead). Sağlıklı istemci ms'de gönderir → davranış aynı.
                        await asyncio.wait_for(ws.send_text(data), timeout=5.0)
                    except Exception:
                        dead.append(ws)
            if dead:
                with _ws_lock:
                    for d in dead:
                        try:
                            _ws_clients.remove(d)
                        except ValueError:
                            pass
                # DENETIM P2: soket KAPATILMIYORDU — istemci yayin listesinden cikarilsa da
                # TCP baglantisi acik kaliyor, istemci kendini "bagli" sanip DONMUS telemetri
                # gostermeye devam ediyordu (yeniden baglanma da tetiklenmez). Acikca kapat →
                # istemci kopmayi gorur ve reconnect merdivenini calistirir.
                for d in dead:
                    try:
                        await d.close(code=1011)  # 1011 = internal error / sunucu dusurdu
                    except Exception:
                        pass
        finally:
            with _ws_pending_lock:
                if not kayit["dusuruldu"]:
                    _ws_pending -= 1
                try:
                    _ws_bekleyenler.remove(kayit)  # iptal edilen (hiç başlamamış) gönderim kuyrukta kalmasın
                except ValueError:
                    pass

    try:
        _event_loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_send_all(), loop=_event_loop))
    except Exception:
        with _ws_pending_lock:
            if not kayit["dusuruldu"]:
                _ws_pending -= 1  # planlanamadi → sayaci geri al (sizinti olmasin)
            try:
                _ws_bekleyenler.remove(kayit)
            except ValueError:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# ESP ALT SİSTEMİ — AÇIK/KAPALI (sahip kararı 2026-09-11: "espleri sistemden söktüm")
# ══════════════════════════════════════════════════════════════════════════════
# Sahip: "ilerde tekrar hibrit esp+stm ya da sadece esp sistemine dönebilirim" → ESP kodu
# SİLİNMEZ, yalnız DEVRE DIŞI bırakılır. Tek kaldıraç bu bayraktır:
#
#     PEMF_ESP_ENABLED=1  → eski davranış (MQTT + ESP bobinleri + MQTT durum rozeti)
#     (ayarlanmamış/0)    → ESP yok sayılır: MQTT'ye bağlanılmaz, "Sistem" rozeti
#                           KIRMIZI/SARI göstermez, ESP bobin slotları sürülmez.
#
# ⚠️ NEDEN BAYRAK, NEDEN YORUM SATIRI DEĞİL: kodu yorumlamak onu derlenmez/test edilemez
# hâle getirir; geri dönüşte "hangi satırlar açılacaktı?" sorusu kalır ve o satırlar
# sessizce bayatlar. Bayrakla kod CANLI kalır, testler ONU KOŞMAYA devam eder
# (`PEMF_ESP_ENABLED=1` ile) ve geri dönüş TEK satırlık bir ayardır.
#
# ⚠️ ÇALIŞMA ZAMANINDA OKUNUR (sabitlenmez): testler ortamı değiştirip iki dünyayı da
# ölçebilsin. Sıcak yolda değil, yalnız durum/komut sınırlarında çağrılır.
def esp_etkin() -> bool:
    """ESP alt sistemi (MQTT + ESP bobinleri) açık mı? Varsayılan KAPALI."""
    import os

    return os.environ.get("PEMF_ESP_ENABLED", "0") == "1"


# ── Canlı Durum (Live State) ───────────────────────────────────────
_live_state = {
    "gateway": "offline",
    # ⚠️ ESP KAPALIYKEN "devre_disi": eskiden varsayılan "warning" idi ve broker hiç
    # çalışmadığı için ORADA KALIYORDU → Dashboard'daki "Sistem" rozeti, kurulu olmayan
    # bir alt sistem yüzünden KALICI SARI/KIRMIZI duruyordu (sahip: "kırmızı dolu bir
    # ekran var"). Kurulu olmayan bir şey arızalı değildir.
    "mqtt": ("warning" if esp_etkin() else "devre_disi"),
    # İNTERNET — CİHAZ AĞINDAN AYRI (sahip bildirimi 2026-09-11).
    # ⚠️ Bu ürün internetsiz ÇALIŞIR; internet yalnız UZAKTAN ERİŞİM içindir. Eskiden
    # internet yokluğu `gateway`i "offline" yapıyor ve "Bağlantı" rozeti kırmızı
    # yanıyordu — oysa hotspot açık, STM kablolu, tüm donanım kusursuz çalışıyor.
    # Ayrı alan: arayüz bunu NÖTR bilgi olarak gösterir, arıza olarak DEĞİL.
    "internet": "offline",
    "stm": "warning",
    "coils": {
        i: {
            "id": i + 1,
            "connected": False,
            "running": False,
            "frequencyHz": 0,
            "dutyCycle": 0,
            "magneticMt": 0.0,
            "objectTemp": 0.0,
            "ambientTemp": 0.0,
            "currentA": 0.0,
            # ⚠️ i < 7 → bobin 1-7 STM (faz 4, 2026-09-10). Slot 8 ESP (cihaz yok).
            # İstemci bu alanı sürüş yolunu seçmek için okur (CoilParameterPanel: STM bobini
            # `stmConnected`e kapılanır, ESP bobini `command_id` ACK'i bekler).
            "stm32Driven": i < 7,
            # GERÇEKTEN ölçülmüş alanların adları. Boş = bu bobinde o sensör YOK →
            # arayüz kısa çizgi (—) gösterir. ⚠️ 0.0 ile "ölçülmedi" ayırt edilebilsin
            # diye var: bobin 1-5 yalnız akım, bobin 6-7 yalnız sıcaklık/alan ölçer ve
            # ölçülmeyen alan 0.0 olarak DURUR (aşağı akış 0.0 bekliyor, None değil).
            "measuredFields": [],
            # SÜRÜŞ KİPİ — firmware'in ETKİN olarak uyguladığı kip (ACK `K=` alanı).
            # None = firmware bildirmedi (eski sürüm) → arayüz "—" gösterir.
            # ⚠️ İSTENEN değil ETKİN: bobin 6-7 sürücüsü tek yönlü, istek ne olursa olsun
            # True kalır. Düğmenin gerçekte ne yaptığını gösteren TEK alan budur.
            "unipolar": None,
            # Bu bobin bipolar sürülebilir mi (donanım yeteneği). Arayüz düğmeyi buna göre
            # kilitler; yeteneksiz bobinde düğme gösterilmez.
            "bipolarYetenek": i < 5,
        }
        for i in range(8)
    },
    "activeTreatment": {
        "mode": "Sistem Hazır",
        "frequencyHz": 0,
        # REÇETE yoğunluğu: operatörün yazdığı sayı. Cihaza GÖNDERİLMEZ (STM/ESP paketi mT
        # taşımaz), yalnız DB'ye kaydedilir → arayüzde "(kayıt)" etiketiyle gösterilir.
        "intensityMt": 0.0,
        # D1.89 (İNCELEME-2 §10 #5 · İG-6.47 sınıfı): duty GÜDÜMLÜ seansın (AI Pro) TEMSİL duty'si (%; bobin 1'in plan
        # duty'si). Eskiden `intensityMt`e yazılıyordu → arayüz "%37 duty"yi "37 mT" diye gösteriyordu. mT DEĞİLDİR;
        # None = bu seans duty temsil değeri taşımıyor (elle seans: reçete `intensityMt`).
        "dutyTemsilYuzde": None,
        # ÖLÇÜLEN yoğunluk: STM'e bağlı MLX90393'ün seans boyunca gördüğü TEPE |B| (mT).
        # ⚠️ None = HİÇ ÖLÇÜM YOK (sensör bağlı değil / seans yok). 0.0 KOYULMAZ: aşağı
        # akış 0.0'ı "ölçüldü" sayar — bu deponun tekrarlayan arızası. Arayüz None iken
        # reçete değerine düşer ve ETİKETİ de "(kayıt)" olarak gösterir.
        "measuredIntensityMt": None,
        # Ölçümün geldiği bobin (tek manyetik sensör bobin 6'ya eşlenik). None = ölçüm yok.
        "measuredIntensityCoil": None,
        # SEANS BOYU TEPE (mT) — `measuredIntensityMt` ANLIK (son saniyenin tepesi) iken
        # bu, seansın TAMAMINDA görülen en büyük |B|. ⚠️ İKİSİ AYRI SORUNUN CEVABI:
        # "şu an ne veriyoruz" (anlık, sahip isteği 2026-09-11) ve "bu seansta en fazla
        # ne verdik" (tepe, kayda/PDF'e giren). Tek sayı ikisini birden söyleyemez:
        # bobinler birlikte anahtarlandığı için anlık değer darbe fazına göre oynar,
        # tepe ise asla düşmez. None = hiç ölçüm gelmedi (0.0 DEĞİL).
        "measuredPeakMt": None,
        "remainingMin": 0,
        "elapsedSec": 0,
        "durationSec": 0,
        "isActive": False,
    },
    # D1.E04 (İG-6.7): son ACİL DURDUR'un TEYİT durumu — "durdu" (`running:false`) ile "teyit edildi" AYRI. None = süreç
    # açıldığından beri E-stop yok. {"teyitli": bool, "kaynak": "estop" | "stm_ack", "zaman": epoch}.
    "estopTeyit": None,
    # Dashboard 'Hasta Özeti' kartının okuduğu aktif-seans hastası. None → aktif hasta yok.
    # Seans başlat/durdur'da set_live_patient/update_live_session_state ile güncellenir.
    "patient": None,
    "notifications": [],
    "system": {
        "softwareVersion": _APP_VERSION,
        "hardwareVersion": HARDWARE_VERSION,
        "deviceId": "PEMF-001",
        "startTime": datetime.now().isoformat(),
        "totalSessions": 0,
    },
}
_live_state_lock = threading.Lock()
_notif_counter = 0
# ── BOBİN TOPOLOJİSİ ──────────────────────────────────────────────────────────
# FAZ 4 (sahip kararı 2026-09-10): bobin 6-7 ESP8266'dan STM32'ye TAŞINDI.
# Firmware `NUM_COILS = 7`, paket 120 bayt; bobin 6 → PE13, bobin 7 → PE15.
#
# ⚠️ SLOT 8 ESP'DE KALIYOR (sahip kararı "8. slot kalsın"): fiziksel bir bobin YOK, ama
# `_live_state["coils"]` 8 slotlu kalıyor → WS anlık-görüntü sözleşmesi ve `range(8)` geçen
# dokuz çağrı yeri DEĞİŞMİYOR. ESP yolu (MQTT/watchdog/E-stop aynası) böylece SİLİNMEDEN
# uykuda kalır; bir gün 8. bobin takılırsa tek satırla geri gelir.
#
# ⚠️ BU KÜMELER YÖNLENDİRMEYİ BELİRLER: `STM_COIL_IDS` seri porta, `ESP_COIL_IDS` MQTT'ye
# gider (`api_server` `/api/coil/{id}/control` ve batch yolları). Bir bobin YANLIŞ kümede
# olursa komut hiç ulaşmaz ve arayüz bunu göstermez — 2026-09-10'a kadar bobin 6-7 tam
# bu durumdaydı (kablo STM'e çekilmiş, komut MQTT'ye gidiyordu).
STM_COIL_IDS = set(range(1, 8))
ESP_COIL_IDS = {8}


# ══════════════════════════════════════════════════════════════════════════════
# STM KOMUT REDDİ — "komut gitmiyor ama seans başlamış gibi görünüyor" (sahip, 2026-09-12)
# ══════════════════════════════════════════════════════════════════════════════
# SAHİP BİLDİRİMİ: "firmware sürüm uyumsuzluğundan dolayı bobinler komut almayacak bildirimi
# gelmesine ve gerçekten bobinlere komut gitmemesine rağmen seans başlatınca gerçekten
# başlıyormuş gibi her şey sorunsuz devam ediyor."
#
# ⚠️ NEDEN MEVCUT KAPILAR YAKALAMIYORDU (D1.52'den beri `HardwareController._stm_baslatma_engeli`
# bu kararı TÜM başlatma yollarında okur): `_stm_surus_hazir()` yalnız SERİ PORTUN AÇIK olup
# olmadığına bakar. Firmware uyuşmazlığında port AÇIKTIR, yazma BAŞARILIDIR — paketi reddeden
# KARTIN KENDİSİDİR ve bunu ASENKRON bir `STM_NACK: CRC` satırıyla söyler. Yani "yazabildim"
# ile "bobin çalıştı" arasındaki fark tam buraya düşüyordu: seans başlıyor, sayaç işliyor,
# geçmişe "Tamamlandı" yazılıyor — hiçbir bobin hiç enerjilenmemişken. Tıbbi kayıt YALAN oluyor.
#
# ⚠️ NEDEN "TEK NACK = RED" DEĞİL: tek bir NACK hat gürültüsü olabilir ve zaten yeniden
# gönderilir (`retry_last_payload`). SİSTEMATİK red, kartın HİÇBİR paketi ayrıştıramadığı
# durumdur. Ayırt edici ölçüt: ARADA KABUL (STM_OK) OLMADAN ard arda gelen NACK sayısı.
#: Ard arda bu kadar NACK "sistematik red" sayılır. Keep-alive 2 Hz → ~1,5 sn'de karar.
STM_RED_ESIGI = 3
#: Karar bu kadar süre tazelenmezse bayatlar (kalıcı kilitlenme olmasın).
#: ⚠️ Kart gerçekten reddediyorsa keep-alive her yarım saniyede yeni NACK üretir → karar taze kalır.
STM_RED_GECERLILIK_S = 10.0

_stm_red = {"ard_arda": 0, "son_an": 0.0, "son_mesaj": ""}
_stm_red_lock = threading.Lock()


def stm_komut_reddi_bildir(mesaj: str = "") -> bool:
    """Karttan bir NACK geldi. Eşiğe ULAŞILDIYSA True döner (bu çağrıyla sistematik red oldu)."""
    import time as _t

    with _stm_red_lock:
        simdi_an = _t.monotonic()
        # ⚠️ D1.51 (B-1.1): son NACK'ten bu yana karar geçerliliği dolduysa bu NACK YENİ bir dizi başlatır. Eskiden
        # sayaç yalnız KABUL'de sıfırlanıyordu: kart hiç kabul etmezse kenar (<3 → ≥3) SÜREÇ ÖMRÜNDE BİR KEZ
        # oluşuyor, karar bayatlayıp yeni seans başladıktan sonra gelen NACK'ler 4, 5, 6… sayılıp seansı HİÇ
        # durdurmuyordu (sahte "Tamamlandı"). Taze kararda yeni NACK yeni kenar ÜRETMEZ (bildirim/E-stop seli yok).
        if (simdi_an - _stm_red["son_an"]) > STM_RED_GECERLILIK_S:
            _stm_red["ard_arda"] = 0
        onceki = _stm_red["ard_arda"] >= STM_RED_ESIGI
        _stm_red["ard_arda"] += 1
        _stm_red["son_an"] = simdi_an
        _stm_red["son_mesaj"] = str(mesaj or "")[:200]
        simdi = _stm_red["ard_arda"] >= STM_RED_ESIGI
    return simdi and not onceki


def stm_komut_kabulu_bildir() -> None:
    """Karttan KABUL (STM_OK) geldi → sayaç sıfırlanır.

    ⚠️ SIFIRLAMA ŞART: aksi halde aylar önceki tek bir gürültü NACK'i sayacı sonsuza dek
    yukarıda tutar ve sağlam bir kartta seans başlatmayı engelleriz — düzelttiğimiz arızanın
    tam tersi, ama aynı ölçüde yanlış.
    """
    with _stm_red_lock:
        _stm_red["ard_arda"] = 0
        _stm_red["son_mesaj"] = ""


def stm_komutlari_reddediyor() -> bool:
    """Kart ŞU AN komutları sistematik olarak reddediyor mu (firmware/protokol uyuşmazlığı)?"""
    import time as _t

    with _stm_red_lock:
        if _stm_red["ard_arda"] < STM_RED_ESIGI:
            return False
        return (_t.monotonic() - _stm_red["son_an"]) <= STM_RED_GECERLILIK_S


def stm_red_ozeti() -> dict:
    """Teşhis/arayüz için: reddediyor mu, kaç ard arda, son ham mesaj.

    ⚠️ `stm_komutlari_reddediyor()` BURADAN ÇAĞRILMAZ: `_stm_red_lock` yeniden-girişli
    değildir (`threading.Lock`), kilit altında çağırmak süreci kilitlerdi. Karar burada
    aynı ölçütle yeniden hesaplanır.
    """
    import time as _t

    with _stm_red_lock:
        ard_arda = _stm_red["ard_arda"]
        taze = (_t.monotonic() - _stm_red["son_an"]) <= STM_RED_GECERLILIK_S
        return {
            "reddediyor": ard_arda >= STM_RED_ESIGI and taze,
            "ard_arda": ard_arda,
            "son_mesaj": _stm_red["son_mesaj"],
        }


def _sync_stm_coils_locked() -> list[dict]:
    """Bobin 1-7'yi canlı STM bağlantı durumundan türetir (faz 4: 5 → 7).

    ⚠️ Bu döngü `STM_COIL_IDS` ile AYNI kapsamda olmalı. Ayrışırsa bobin 6-7 `connected`
    alanını hiç güncellemez → STM çevrimdışıyken kart "Hazır"da asılı kalır (2026-09-10'da
    ESP tarafında ölçülen arızanın aynısı).
    """
    stm_online = _live_state["stm"] == "online"
    snapshots = []
    for idx in range(len(STM_COIL_IDS)):
        coil = _live_state["coils"][idx]
        coil["stm32Driven"] = True
        coil["connected"] = stm_online
        if not stm_online:
            coil["running"] = False
            # ⚠️ ETKİN SÜRÜŞ KİPİ DE UNUTULUR. Bu alan "kartın BANA BİLDİRDİĞİ kip"tir;
            # kart gittiğinde artık kimse doğrulamıyor demektir. Eski değeri tutmak,
            # yeniden bağlanan (belki YENİDEN PROGRAMLANMIŞ, belki BAŞKA) bir kart için
            # doğrulanmamış bir kipi doğrulanmış gibi göstermek olurdu. None → arayüz
            # kısa çizgi gösterir ve ilk ACK'te gerçek kip geri gelir.
            coil["unipolar"] = None
        snapshots.append(dict(coil))
    return snapshots


def update_live_coil_kip(coil_id: int, unipolar: bool) -> None:
    """Bobinin ETKİN sürüş kipini canlı duruma yazar (ACK `K=` alanından)."""
    idx = coil_id - 1
    if not (0 <= idx < 8):
        return
    with _live_state_lock:
        if _live_state["coils"][idx].get("unipolar") == bool(unipolar):
            return  # değişmedi → boşuna yayın yapma
        _live_state["coils"][idx]["unipolar"] = bool(unipolar)
        snapshot = dict(_live_state["coils"][idx])
    _ws_broadcast_sync({"type": "coil_status", "coilId": coil_id, "data": snapshot})


def stm_surus_hazir() -> bool:
    """STM sürüş yolu komut KABUL EDEBİLİR durumda mı?

    ⚠️ NEDEN VAR (saha, 2026-09-11): STM kopukken `/api/coil/1/control`
    `{"status":"success","transport":"stm32"}` döndürüyordu. Donanım yokken, hiçbir şey
    çalışmayacakken "başarılı" — bu deponun tekrarlayan SESSİZ BAŞARISIZLIK sınıfı.
    `stm_is_connected` backend'in hiçbir yerinde kontrol edilmiyordu; tek kapı istemci
    tarafındaydı (`CoilParameterPanel`), yani mobil/AI/doğrudan-API çağrıları kapısızdı.

    ⚠️ NEDEN `core.stm_is_connected` DEĞİL, BU ALAN: aynı EXE sunucuda `PEMF_SIMULATE=1`
    ile demo koşuyor ve simülasyon döngüsü `core.stm_is_connected`i AYARLAMAZ — yalnız
    `_live_state["stm"]`i "online" yapar. Kapıyı core alanına bağlamak demo/sunucu
    dağıtımında HİÇBİR bobinin başlatılamamasına yol açardı. Bu alan ayrıca arayüzün
    okuduğu alandır → backend artık ekranda görünenle AYNI şeyi söyler.

    Kapı: tests/test_stm_kopukken_baslatma_reddi.py
    """
    with _live_state_lock:
        return _live_state["stm"] == "online"


def _push_notification(message: str, level: str = "info") -> None:
    global _notif_counter
    with _live_state_lock:
        # Audit P3: ID artışını KİLİT altına al — paho MQTT callback + STM seri-loop thread'leri
        # aynı anda okuyup yazarsa iki bildirim aynı id'yi paylaşır (ID'ye göre dedup eden React
        # istemci birini düşürür/yanlış render eder).
        _notif_counter += 1
        notif = {"id": _notif_counter, "message": message, "level": level, "timestamp": datetime.now().isoformat()}
        _live_state["notifications"].insert(0, notif)
        if len(_live_state["notifications"]) > 50:
            _live_state["notifications"].pop()
    _ws_broadcast_sync({"type": "notification", "data": notif})


def _efield_snapshot():
    """Canlı E-alanı önbelleğini oku. İçe aktarma HATA verirse (paket yok / model yok)
    snapshot BOZULMAZ — alan None kalır ve UI bar'ı hiç göstermez."""
    try:
        from servers import efield_live

        return efield_live.get_live()
    except Exception:
        return None


def _build_ws_snapshot() -> dict:
    """Anlık durum özeti (WebSocket'e ilk bağlanıldığında gönderilir)."""
    with _live_state_lock:
        _sync_stm_coils_locked()
        coils_list = [dict(_live_state["coils"][i]) for i in range(8)]
        return {
            "gateway": _live_state["gateway"],
            "mqtt": _live_state["mqtt"],
            "internet": _live_state["internet"],
            "stm": _live_state["stm"],
            "activeTreatment": _live_state["activeTreatment"],
            "coils": coils_list,
            "notifications": _live_state["notifications"][:10],
            "system": _live_state["system"],
            "patient": _live_state.get("patient"),
            # CANLI E-ALANI (2026-08-06): yalnız ÖNBELLEK okunur — ONNX bu istek yolunda
            # ÇALIŞMAZ (bkz. servers/efield_live.py). Bağlam/seans yoksa None → UI bar'ı gizler.
            "eField": _efield_snapshot(),
            # D1.81 · Y4 (yalnız-ek): acil durdurma mandalı — arayüz (Karşılama/Giriş dahil) "Sıfırla"yı gösterir.
            "estopMandali": estop_mandali.durum(),
            # D1.E04 (yalnız-ek): son E-stop teyitsizse arayüz kayan ACİL DURDUR'u "(teyitsiz)" ile ekranda tutar.
            "estopTeyit": _live_state.get("estopTeyit"),
        }


def estop_teyidi_yaz(teyitli: bool, kaynak: str = "estop") -> dict:
    """D1.E04 · İG-6.7: ACİL DURDUR'un TEYİT durumunu yaz ve yayınla (`estop_teyit`). Teyitten BAĞIMSIZ `running:false`
    yayını (canlı durum sıfırlaması) "durdu" kanıtı DEĞİLDİR; istemci görünür durdurmayı bu alana göre tutar.
    Yalnız RAPOR — STOP'u kapılamaz, gönderimi azaltmaz (Ö.4-Y8)."""
    import time as _t

    veri = {"teyitli": bool(teyitli), "kaynak": str(kaynak), "zaman": _t.time()}
    with _live_state_lock:
        _live_state["estopTeyit"] = veri
        _ws_broadcast_sync({"type": "estop_teyit", "data": dict(veri)})
    return veri


def estop_teyidi_stm_ack() -> bool:
    """Kart GERÇEK bir ACK'le TÜM çıkışlarını sıfır bildirdi: bekleyen (teyitsiz) E-stop STM tarafından teyit edilir.
    Yalnız ESP kapalıyken (A-63: teyit STM'e göre) — ESP açıkken STM ACK'i ESP'yi teyit etmez. @return teyit verildi mi."""
    with _live_state_lock:
        mevcut = _live_state.get("estopTeyit")
        if not mevcut or mevcut.get("teyitli") or esp_etkin():
            return False
    estop_teyidi_yaz(True, "stm_ack")
    return True


def update_live_stm_status(connected: bool) -> None:
    """STM32 bağlantı durumunu günceller."""
    with _live_state_lock:
        _live_state["stm"] = "online" if connected else "warning"
        stm_state = _live_state["stm"]
        coil_snapshots = _sync_stm_coils_locked()
    _ws_broadcast_sync({"type": "stm_status", "data": {"stm": stm_state, "connected": connected}})
    for coil in coil_snapshots:
        _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil["id"], "data": coil})


def update_live_coil_from_stm(
    coil_id: int, duty: float, freq: float, phase: float, duration_min: int, running: bool
) -> None:
    """STM32 USB verisiyle bobin durumunu günceller.

    ⚠️ D1.74 (B-1.19): STM BAĞLANTI DURUMUNA DOKUNMAZ. Eskiden her `coil_update` `_live_state["stm"] = "online"`
    yazıp `stm_status{online}` yayınlıyordu; firmware watchdog satırının SENTETİK sıfırlama yayını da `coil_update`
    olduğundan STM koptuktan sonra (ya da başarısız bir el sıkışmada) okunan bir satır başlatma kapısını
    (`stm_surus_hazir`) yeniden açıyordu — kart yokken START kabul ediliyordu (ölçüldü). "online" yalnız
    `update_live_stm_status(True)`'dan gelir (gerçek `STM_READY`/`STM_OK` → `hardware.stm.connected`). Bobinin
    `connected` alanı da canlı STM durumundan türer (`_sync_stm_coils_locked` ile aynı ölçüt)."""
    coil_index = coil_id - 1
    if not (0 <= coil_index < 8):
        return
    with _live_state_lock:
        coil = _live_state["coils"][coil_index]
        coil.update(
            {
                "connected": _live_state["stm"] == "online",
                "running": running,
                "frequencyHz": int(freq),
                "dutyCycle": float(duty),
                "phase": float(phase),
                "durationMin": int(duration_min),
                "stm32Driven": True,
            }
        )
        snapshot = dict(coil)
    _ws_broadcast_sync({"type": "stm_coil_update", "coilId": coil_id, "data": snapshot})


def update_live_session_state(
    is_active: bool,
    mode: str = "Sistem Hazır",
    freq: float = 0,
    intensity: float = 0,
    remaining_min: int = 0,
    elapsed_sec: int = 0,
    duration_sec: int = 0,
    surus_nesli: int | None = None,
    duty_temsil: float | None = None,
) -> bool:
    """React/WebSocket tarafındaki aktif tedavi özetini günceller. @return yazıldı mı (False = "aktif" yazımı ATLANDI).

    D1.81 (İG-5.36) — iki kural, durum kilidi altında (acil durdurmanın yazımıyla sıralı):
      * Mandal kuruluyken ya da çağıranın `surus_nesli` bayatken "AKTİF" yazımı YAPILMAZ: ölçüldü, uçuştaki AI turu
        acil durdurmadan SONRA `isActive:true` yayınlıyordu (8'de 3) ve etiketi eziyordu.
      * Mandal kuruluyken "Sistem Hazır" yazılmaz → "Acil Durdurma" kalır (döngü sonu / AI durdurma / seans durdurma
        etiketi eziyordu, 8'de 7). Mandal operatörün "Sıfırla"sıyla kalkınca normal etiket döner.
    1-C inceleme i2-F3: dönüş değeri, "aktif" yazımının kilit ALTINDA reddedildiğini çağırana söyler — seans başlatma
    buna göre CSV açmaz ve "success" demez (denetim ile yazım arasındaki durdurma da tek karar noktasında görülür)."""
    with _live_state_lock:
        if is_active and estop_mandali.baslatma_engeli(surus_nesli):
            logging.getLogger(__name__).info(
                "Canli durum 'aktif' yazimi ATLANDI (acil durdurma mandali / bayat surus nesli): %s", mode
            )
            return False
        if not is_active and mode == "Sistem Hazır" and estop_mandali.mandalli_mi():
            mode = "Acil Durdurma"
        _live_state["activeTreatment"].update(
            {
                "isActive": bool(is_active),
                "mode": mode,
                "frequencyHz": freq,
                "intensityMt": intensity,
                "dutyTemsilYuzde": duty_temsil,  # D1.89: duty mT alanına YAZILMAZ (bkz. ilk durum)
                "remainingMin": remaining_min,
                "elapsedSec": elapsed_sec,
                "durationSec": duration_sec,
            }
        )
        # ⚠️ ÖLÇÜM SEANSA AİTTİR — BAŞLARKEN DE BİTERKEN DE SIFIRLANIR. Yalnız bitişte
        # temizlemek yetmez: yeni seansın ilk telemetrisi gelene kadar arayüz ÖNCEKİ
        # seansın tepe değerini "bu seansın ölçülen yoğunluğu" diye gösterirdi.
        _live_state["activeTreatment"]["measuredIntensityMt"] = None
        _live_state["activeTreatment"]["measuredIntensityCoil"] = None
        _live_state["activeTreatment"]["measuredPeakMt"] = None
        if not is_active:
            # Seans bitti (durdur/watchdog/acil) → Hasta Özeti "Aktif hasta yok"a dönsün. TÜM stop
            # yolları buradan geçtiği için hasta temizliği tek noktada garanti (kilit içinde, hafif).
            _live_state["patient"] = None
        snapshot = dict(_live_state["activeTreatment"])
        # ⚠️ 1-C inceleme i2-F4: yayın YAZIMLA AYNI kilit altında PLANLANIR (`call_soon_threadsafe` FIFO + gönderim kilidi
        # FIFO → istemci yazım sırasını görür). Eskiden kilit bırakıldıktan SONRA planlanıyordu: E-stop'tan ÖNCE denetimi
        # geçen bir "aktif" yazımının yayını E-stop'un "Acil Durdurma" yayınından SONRAYA kalabiliyor, istemcinin aldığı
        # son ileti `isActive:true` oluyordu (ölçüldü 30/30, zorlanmış zamanlama). Kilit sırası güvenli: `_ws_broadcast_sync`
        # yalnız `_ws_pending_lock` / `_ws_lock` alır, onları tutup `_live_state_lock` alan yol yok.
        _ws_broadcast_sync({"type": "session_update", "data": snapshot})
    if not is_active:
        # patient session_update ile TAŞINMAZ → tam snapshot yayınla ki kart canlı temizlensin.
        _ws_broadcast_sync({"type": "snapshot", "data": _build_ws_snapshot()})
    return True


def update_measured_intensity(mt: float | None, coil_id: int | None, tepe: float | None = None) -> bool:
    """Aktif seansın ÖLÇÜLEN yoğunluğunu yazar ve değiştiyse yayınlar.

    SAHİP KARARI 2026-09-11: "aktif seans ... ordaki yoğunluk değeri stm e bağlı olan
    SENSÖRDEN GELSİN" + "ANLIK yazdırmalı". Reçete alanı (`intensityMt`) DEĞİŞTİRİLMEZ —
    ikisi farklı şeydir (bkz. servers/seans_alan_kaydi.py başlığı).

    @param mt    ANLIK değer: SON SANİYENİN tepesi (`SeansAlanKaydi.son_deger`).
                 ⚠️ Gerçek "o mikrosaniyedeki" örnek DEĞİL ve olamaz: bobinler ~425 Hz
                 örneklenirken darbe fazına göre 0 ile tam alan arasında zıplar. Saniyelik
                 tepe, "şu an ne veriyoruz" sorusunun ölçülebilir en dürüst cevabıdır.
    @param tepe  SEANS BOYU en büyük |B| (`SeansAlanKaydi.zirve`). Kayda/PDF'e giren budur.

    ⚠️ SEANS YOKKEN YAZMAZ: ölçüm seansa aittir; boştaki cihazın okuduğu alan (dünyanın
    manyetik alanı dahil) "uygulanan doz" değildir ve arayüzde öyle görünmemelidir.
    ⚠️ DEĞİŞMEDİYSE YAYINLAMAZ: telemetri saniyede bir gelir; hiçbir şey değişmemişken
    `session_update` basmak WS'i ve istemci render'ını boşuna meşgul eder.

    @return yayın yapıldıysa True.
    """
    with _live_state_lock:
        at = _live_state["activeTreatment"]
        if not at.get("isActive"):
            return False
        yeni = None if mt is None else round(float(mt), 3)
        yeni_tepe = None if tepe is None else round(float(tepe), 3)
        if (
            (at.get("measuredIntensityMt") == yeni)
            and (at.get("measuredIntensityCoil") == coil_id)
            and (at.get("measuredPeakMt") == yeni_tepe)
        ):
            return False
        at["measuredIntensityMt"] = yeni
        at["measuredIntensityCoil"] = None if yeni is None else coil_id
        at["measuredPeakMt"] = yeni_tepe
        snapshot = dict(at)
    _ws_broadcast_sync({"type": "session_update", "data": snapshot})
    return True


def set_live_patient(patient) -> None:
    """Aktif seansın hastasını canlı-duruma yazar (Dashboard 'Hasta Özeti' kartı okur).
    patient=dict {name,species,breed,owner} veya None (aktif hasta yok). Yazımdan sonra TAM snapshot
    yayınlar → kart canlı güncellenir (session_update patient taşımadığı için full snapshot şart).
    Not: _build_ws_snapshot() kilidi kendisi alır → burada kilit BIRAKILDIKTAN sonra çağrılır (deadlock yok)."""
    with _live_state_lock:
        _live_state["patient"] = dict(patient) if isinstance(patient, dict) else None
    _ws_broadcast_sync({"type": "snapshot", "data": _build_ws_snapshot()})
