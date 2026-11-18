# Author: mertaygn, cglrgrkn
import asyncio  # P0 audit 2026-06-28: senkron MQTT publish'i event-loop'tan cikar (to_thread)
import itertools as _itertools  # MQTT yayinci client_id sayaci (bkz. _mqtt_client_id)
import json
import logging
import os
import re
import threading
import time
import uuid as _uuid
from contextlib import asynccontextmanager  # audit B-2.2: on_event yerine lifespan
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.gzip import GZipMiddleware
from utils import (
    ceviri,
    estop_mandali,  # D1.81 · Y4: acil durdurma mandalı + sürüş nesli
)
from utils import stm32_kimlik as _stm32_kimlik  # TD1: operatör metinleri (K1 / K2) tek kaynak
from utils.path_utils import get_app_version, get_build_id  # audit B-8.1: tek versiyon kaynağı

from servers import (
    coil_run_tracker,  # audit B-2.2: coil-run (treatment-DB) tracker ayrı modülde
    live_state,  # audit B-2.2: canlı-durum (WS/live-state) çekirdeği ayrı modülde
    session_state,  # audit B-2.2 (son kademe): aktif-seans state ayrı modülde
)
from servers import sensor_kaydedici as _sensor_kaydedici  # yerel telemetri kaydi (CSV)
from servers.ai_router import ai_router
from servers.history_router import router as history_router
from servers.settings_router import router as settings_router

_APP_VERSION = get_app_version()
_BUILD_ID = get_build_id()  # launcher'ın kurduğu paketin sha'sı (yoksa "")

# ── B-2.2: canlı-durum çekirdeği servers/live_state.py'ye taşındı ──────────────────────────────
# Aşağıdaki alias'lar AYNI nesnelere işaret eder (dict/list/lock in-place mutasyon → api_server'ın
# WS/MQTT/session gövdesi DEĞİŞMEDEN çalışır; davranış birebir — tests/test_live_state.py kanıtlar).
# Reassign edilen globaller (_event_loop lifespan'de) live_state.set_event_loop() ile atanır.
_live_state = live_state._live_state
_live_state_lock = live_state._live_state_lock
_ws_clients = live_state._ws_clients
_ws_lock = live_state._ws_lock
STM_COIL_IDS = live_state.STM_COIL_IDS
ESP_COIL_IDS = live_state.ESP_COIL_IDS
_ws_broadcast_sync = live_state._ws_broadcast_sync
_sync_stm_coils_locked = live_state._sync_stm_coils_locked
_push_notification = live_state._push_notification


def _bildir(uret, level: str = "info") -> None:
    """İKİ DİLLİ bildirim (`live_state._bildir`); gönderim bu modülün `_push_notification` takma adıyla (testler onu yakalar)."""
    live_state._bildir(uret, level, _push_notification)


_build_ws_snapshot = live_state._build_ws_snapshot


# ── GA (istem 53) CANLI 3B ALAN — Kontrol sekmesi "Alan haritası" + dijital ikiz (`servers/canli_alan.py`) ─────────────────────
# YALNIZ GÖSTERİM; ACİL DURDUR / sürüşle ortak kilit YOK (bobin durumu anlık görüntü, hesap kendi iş parçacığında, yalnız abone varken).
def _canli_alan_bobinleri() -> dict:
    hw = state.hardware
    return hw.calisan_bobin_durumu() if hw is not None else {}


def _canli_alan_gonder(ileti: dict, alicilar: list) -> None:
    _ws_broadcast_sync(ileti, alicilar=alicilar)


from servers import canli_alan as _canli_alan_modulu  # noqa: E402

_canli_alan = _canli_alan_modulu.CanliAlan(_canli_alan_bobinleri, _canli_alan_gonder)
update_live_stm_status = live_state.update_live_stm_status
update_live_coil_from_stm = live_state.update_live_coil_from_stm
update_live_coil_kip = live_state.update_live_coil_kip
update_live_coil_kip_istegi = live_state.update_live_coil_kip_istegi
update_measured_intensity = live_state.update_measured_intensity
set_live_patient = live_state.set_live_patient

# ── SEANS ALAN KAYDI (masaüstü CSV, sahip kararı 2026-09-11) ──────────────────────────
# ⚠️ `sensor_kaydedici` İLE KARIŞTIRMA: o, HER ZAMAN açık, günlük dönen, veri kökündeki
# araştırma günlüğüdür. Bu ise SEANSA ÖZEL, masaüstüne konan, operatörün elle açıp
# hastaya ilişkilendireceği tek dosyadır ("MASAÜSTÜNE KOYSUN. SEANS ÖZELİNDE OLCAK BU.").
from servers.seans_alan_kaydi import seans_alan_kaydi as _seans_alan  # noqa: E402


def update_live_session_state(*args, e_baglam_nesli: int | None = None, **kwargs):
    """`live_state.update_live_session_state` + seans alan kaydının kapanışı.

    `e_baglam_nesli` (O-A2-K.1): verilirse canlı E bağlamı yalnız o nesilden beri DEĞİŞMEDİYSE temizlenir — biten AI Pro
    döngüsünün GEÇ kapanışı, döngü çıktıktan sonra kurulan (yeni analizin) bağlamını silmez. Verilmezse (bütün durdurma
    yolları) bugünkü gibi koşulsuz temizlenir.

    ⚠️ NEDEN SARMALAYICI, NEDEN HER STOP YOLUNA AYRI ÇAĞRI DEĞİL: seansı bitiren DÖRT yol
    var (kullanıcı durdurma, süre-watchdog'u, STM watchdog'u, acil durdurma) ve hepsi
    zaten buradan geçiyor — dosyadaki hasta temizliği de tam olarak bu değişmeze dayanıyor
    ("TÜM stop yolları buradan geçtiği için ... tek noktada garanti"). Dört yere elle
    çağrı koymak, yarın eklenecek BEŞİNCİ yolun CSV'yi açık bırakmasını garanti ederdi:
    dosya diskte yarım kalır, özet satırı hiç yazılmaz.
    """
    _aktif = bool(args[0]) if args else bool(kwargs.get("is_active"))
    if not _aktif:
        try:
            _yol = _seans_alan.seans_bitti("seans kapandı")
            if _yol is not None:
                _bildir(lambda d: ceviri.t("bildirim.alanKaydiYazildi", dil=d, name=_yol.name), "info")
        except Exception:
            logging.exception("seans alan kaydı kapatılamadı (seans akışı etkilenmez)")
        # D1.61 (B-5.7 · B-1.25): canlı E bağlamı seansa aittir — aynı tek noktada temizlenir (durdurma, süre bekçisi,
        # STM watchdog'u, acil durdurma); sonraki seansta başka hedefin E'si "● canlı" görünmez.
        try:
            from servers import efield_live as _ef_bitis

            if e_baglam_nesli is None:
                _ef_bitis.seans_bitti()
            else:
                _ef_bitis.temizle_degismediyse(e_baglam_nesli)
        except Exception:
            logging.exception("canlı E bağlamı temizlenemedi (seans akışı etkilenmez)")
    return live_state.update_live_session_state(*args, **kwargs)


# Headless Core State referansı (Singleton Bridge)
# Bu obje main.py'den enjekte edilebilir veya burada global import edilebilir
try:
    from controllers.hardware_controller import HardwareController
    from database.patient_database import get_patient_database
    from headless_core import HeadlessCore
except ImportError:
    HeadlessCore = None
    HardwareController = None

    def get_patient_database(app_data_dir=None):
        return None


def _app_data_dir():
    """Kanonik app_data dizini — history/settings router'larıyla AYNI kök (split-brain önler).
    Eskiden os.environ APPDATA boş/yokken 'C:/PEMF_GUI'ye düşüp yazıcı/okuyucu ayrışıyordu."""
    try:
        from utils.path_utils import get_app_data_directory

        return get_app_data_directory()
    except Exception:
        from pathlib import Path as _PP

        return _PP(os.environ.get("APPDATA") or (_PP.home() / "AppData" / "Roaming")) / "PEMF_GUI"


# Swagger/OpenAPI görünürlüğü (audit B-1.7): ÜRETİMDE (auth zorunlu VEYA tünel açık = internet'e
# açık yüzey) /docs + /redoc + /openapi.json KAPALI → API şeması tünelden sızmasın. YEREL/dev
# (auth kapalı + tünel kapalı) AÇIK → geliştirici kolaylığı. PEMF_ENABLE_DOCS ile açıkça geçersiz kıl
# (1=aç, 0=kapat). Not: auth.py _EXEMPT_PREFIXES docs'u zaten muaf tutar → açıkken yerelde token'sız açılır.
_docs_env = os.getenv("PEMF_ENABLE_DOCS", "").strip()
if _docs_env in ("0", "1"):
    _docs_enabled = _docs_env == "1"
else:
    _docs_enabled = os.getenv("PEMF_REQUIRE_AUTH", "0") != "1" and os.getenv("PEMF_ENABLE_TUNNEL", "0") != "1"


@asynccontextmanager
def _scratch_isit_baslat() -> None:
    """Yara-kapanma (CPN, 872 MB) modelini AÇILIŞTA arka planda ısıt — saha bildirimi 2026-08-27.

    ÖLÇÜLEN ARIZA: ısıtma YALNIZ GPU mikroserviste (ai_service) vardı; klinik kurulumda model
    ilk "Analiz Et" anında yükleniyordu. Ölçüm (bu makinede, boşta): İLK istek 32,8 sn, ikinci
    22,4 sn — yani ilk analizin ~10 sn'si saf model yüklemesi ve o süre boyunca predictor kilidi
    tutuluyor. Yük altındaki bir klinik makinesinde bu fark büyür; kullanıcı ilk denemeyi
    "çalışmıyor" sanıp ikinci kez basıyor (sahadan bildirilen davranış tam buydu).

    ⚠️ CI DERSİ (ai_service, exit 134): cell/ teslim edilmemişken daemon thread isit() içinde
    hemen bitip kısa ömürlü interpreter kapanışıyla yarışıyor ve SIGABRT üretebiliyordu →
    thread YALNIZ alt-modül (cell.cpn) gerçekten varsa başlatılır; ucuz senkron ön-kontrol.
    ⚠️ Ayrı thread ŞART: default executor'da yapılırsa 872 MB yükleme boyunca E-stop dahil
    to_thread çağrıları kuyruğa girerdi (ölçülmüş executor-tükenmesi bulgusu).
    Kapatma: PEMF_SCRATCH_WARMUP=0 (araştırma profili kurulu olmayan makinede RAM'i boşa yemesin).
    """
    if os.environ.get("PEMF_SCRATCH_WARMUP", "1") != "1":
        return
    try:
        import importlib.util

        if importlib.util.find_spec("ai_hub.inference_paper_dilek_hoca.cell.cpn") is None:
            return
        from ai_hub.inference_paper_dilek_hoca import inference_paper_dilek_hoca as _ipd

        threading.Thread(target=_ipd.isit, daemon=True, name="scratch-warmup").start()
        logging.info("Yara-kapanma modeli arka planda ısıtılıyor (ilk analiz beklemesin).")
    except Exception as e:  # ısıtma bir KOLAYLIK — hiçbir hatası servisi düşürmez
        # 🔴 A9 dersi: bu satır `info` + zincirsizdi ve 2026-09-20'de YANILTICI teşhis
        # üretti ("model/cell hazır değil" derken gerçek sebep zehirlenmiş torch'tu).
        # Kolaylık düşebilir; ama NEDEN düştüğü okunabilir olmalı.
        logging.warning(
            "Yara-kapanma ısıtması BAŞARISIZ (%s) — ilk analiz ~33 sn sürebilir; tam zincir aşağıda",
            type(e).__name__,
            exc_info=True,
        )


async def lifespan(app: FastAPI):
    """Uygulama yaşam-döngüsü (audit B-2.2: deprecated @app.on_event yerine + import-zamanı
    thread yan-etkisini kaldırır). Arka-plan thread'leri (safety süre-watchdog dahil) YALNIZ sunucu
    BAŞLARKEN başlatılır — modül import'unda DEĞİL. Fonksiyonlar dosyada sonra tanımlı; runtime'da çözülür."""
    # ── STARTUP ──
    # B-2.2: canlı-durum modülüne event-loop'u ver → thread'lerden (MQTT/STM/sim) gelen WS
    # broadcast'leri bu loop'a planlar (eskiden modül-global _event_loop; davranış aynı).
    live_state.set_event_loop(asyncio.get_event_loop())
    logging.info("FastAPI Bridge: Başlıyor...")
    _register_event_bus_handlers()
    # MQTT canlı veri dinleyicisi + mDNS (aynı Wi-Fi'deki telefonlar keşfetsin)
    threading.Thread(target=_start_mqtt_for_api, daemon=True, name="FastAPIMQTTListener").start()
    threading.Thread(target=_start_mdns_service, daemon=True, name="PEMFmDNSService").start()
    # Arka-plan daemon'ları (süre-watchdog + sensör-persist + günlük-bakım + opsiyonel sim).
    _start_background_threads()
    # ⚠️ A9 — SIRA ÖNEMLİ: torch, ısıtma thread'i başlamadan ve `yield` ile istek kabulü
    # açılmadan ÖNCE, SENKRON kurulur (ölçüm 1,92 sn). Aksi halde `scratch-warmup` thread'i
    # ile ilk AI isteği aynı yarı-kurulu torch'u paylaşıyordu → 38 kez `NameError: _C`.
    # Bu satırı `_scratch_isit_baslat()`ın ALTINA almak arızayı geri getirir.
    _torch_isit()
    _scratch_isit_baslat()
    try:
        yield
    finally:
        # ── SHUTDOWN ──
        logging.info("FastAPI Bridge: Kapanıyor...")
        if _mqtt_client_api:
            try:
                _mqtt_client_api.loop_stop()
                _mqtt_client_api.disconnect()
            except Exception:
                pass
        try:
            from servers.auto_discovery import stop_mdns

            stop_mdns()
        except Exception:
            pass


# ⚠️ Multipart form-alanı limitini FastAPI app'i oluşturmadan ÖNCE yükselt (saha bulgusu
# 2026-08-30: scratch/base64 uçlarında "Part exceeded maximum size of 1024KB"). Bkz.
# utils/multipart_limit — Starlette varsayılanı 1MB, base64 görüntüler bunu aşıyordu.
from utils.agir_import import torch_isit as _torch_isit  # noqa: E402  (A9)
from utils.akim_olcumu import akim_olcumu_acik, akimsiz  # noqa: E402  (CH4 · Y154: akım sensörü tek bayrak)
from utils.dongu_guvenligi import dongu_hatasini_bildir as _dongu_hatasini_bildir  # noqa: E402
from utils.multipart_limit import buyuk_form_alani_limitini_uygula as _buyuk_form_limiti

_buyuk_form_limiti()

app = FastAPI(
    title="PEMF React Native API Bridge",
    description="PyQt6 arayüzüne gerek duymayan Headless Donanım API'si",
    version=_APP_VERSION,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)

# CORS configurable: üretimde PEMF_CORS_ORIGINS="https://app1,https://app2" ile daraltın.
# Native uygulamada Origin yok (CORS uygulanmaz); web paneli için anlamlıdır.
# DENETIM P0: VARSAYILAN "*" idi. deploy/device.env bunu daraltiyor ama backend .env dosyalarini
# OTOMATIK YUKLEMEZ (load_dotenv yok) → env yalniz NSSM servis kaydinda uygulanir. Tauri launcher
# ("PEMF Vet Client", canli dagitim yolu) exe'yi DOGRUDAN spawn edip yalniz 2 env verdiginden
# ACAO:* etkin kaliyordu: operatorun actigi HERHANGI bir web sayfasi cihaza fetch atip
# /api/auth/token (kalici cihaz anahtari) ve /api/patients (tum hasta PII) YANITLARINI OKUYABILIYORDU.
# Varsayilan artik loopback + RFC1918 + *.local kokenleriyle sinirli; internetteki bir sayfa
# yanitlari okuyamaz. Acik "*" hala MUMKUN ama artik bilincli bir tercih (PEMF_CORS_ORIGINS=*).
_LAN_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"169\.254\.\d{1,3}\.\d{1,3}|"
    r"[A-Za-z0-9-]+\.local"
    r")(:\d+)?$"
)
_cors_env = os.getenv("PEMF_CORS_ORIGINS", "").strip()
if _cors_env == "*":
    _cors_kwargs = {"allow_origins": ["*"]}  # acik opt-in (geriye uyumlu)
elif _cors_env:
    _cors_kwargs = {"allow_origins": [o.strip() for o in _cors_env.split(",") if o.strip()]}
else:
    _cors_kwargs = {"allow_origins": [], "allow_origin_regex": _LAN_ORIGIN_REGEX}
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,  # API stateless (cookie yok)
    allow_methods=["*"],
    allow_headers=["*"],
    # Jeton 402'sinin ret sebebi (servers/jeton.py `JETON_SEBEP_BASLIGI`): tarayıcı yalnız açıkça izin verilen yanıt başlığını okur.
    expose_headers=["X-PEMF-Jeton-Sebep"],
    **_cors_kwargs,
)

#: Bu boyutun altındaki yanıt SIKIŞTIRILMAZ.
#: ⚠️ Küçük yanıtta gzip SAF KAYIP: gzip başlığı ~20 bayt, sıkıştırma CPU'su bedava değil ve
#: canlı durum anlık görüntüsü (`/api/status`) saniyede birkaç kez çekiliyor. Kazanç AI
#: yanıtlarında (yüzlerce KB base64 görsel); küçük JSON'da yok.
GZIP_ASGARI_BAYT = 1024

# ⚠️ GZIP (AI Hub planı, ADIM 5). NEDEN İŞE YARIYOR: 7 panelli fantom/petri yanıtı base64 JPEG
# taşıyor ve base64 ikili veriyi %33 ŞİŞİRİR — gzip o şişmeyi büyük ölçüde geri alır.
# ⚠️ BU MAKİNEDE ÖLÇÜLDÜ (2026-09-12, `test_gzip_sikistirma.py` çıktısı, 7 panelli gerçek petri
# yanıtı): 5.917,7 KB → 4.472,6 KB, **oran 0,756**. Plan 0,73-0,75 öngörmüştü; bağımsız ölçüm
# doğruladı. (Test panelleri saf gürültü, yani JPEG için EN KÖTÜ durum; saha fotoğrafında kazanç
# bundan daha iyi olur.)
#
# ⚠️ KAZANÇ YALNIZ TAURI / DOĞRUDAN :8000 YOLUNDA. docker/web dağıtımında nginx zaten
# sıkıştırıyor (`docker/Dockerfile.frontend`), yani orada bu satır ikinci bir sıkıştırma
# DEĞİL — nginx upstream'den gelen `Content-Encoding: gzip`i olduğu gibi geçirir.
#
# ⚠️ WEBSOCKET ETKİLENMEZ: Starlette'in GZipMiddleware'i `scope["type"] != "http"` olan her şeyi
# dokunmadan geçirir. Canlı telemetri WS'i bu yüzden bozulmaz (kapı: test_gzip_sikistirma.py).
app.add_middleware(GZipMiddleware, minimum_size=GZIP_ASGARI_BAYT)

# Audit P2 + eksik-taraması P2 (2026-08-22): DNS-rebinding'e karşı Host koruması.
#
# TARİHÇE: TrustedHost altyapısı 2026-08-04'ten beri vardı ama varsayılan "*" ve HİÇBİR dağıtım
# profili/launcher ayarlamadığı için koruma hiçbir kurulumda AKTİF DEĞİLDİ. Statik liste de
# çözüm olamıyordu: meşru istemciler kliniğin O ANKİ LAN IP'siyle bağlanır (telefon →
# http://192.168.1.35:8000) ve TrustedHost joker-IP bilmez — liste ya mobili kırar ya "*" kalır.
#
# "auto" MODU: rebinding saldırısının Host başlığı HER ZAMAN saldırganın ALAN ADIdır (tarayıcı
# Host'a çözdüğü adı yazar). Meşru Host'lar sayılabilir bir sınıftır: IP-literal (v4/v6),
# localhost, *.local (mDNS), makinenin kendi adı, tünel alanları. "auto" bu sınıfı serbest
# bırakır, YABANCI DNS ADLARINI 400 ile reddeder. "auto,klinik.sirket.com" ek ad tanımlar
# (kurumsal intranet FQDN'li klinik için çıkış kapısı).
#
# Değer sözlüğü:  "*" (VARSAYILAN) = koruma kapalı (dev/test — sessiz davranış değişikliği yok;
# korumayı deploy/*.env + launcher backend_env "auto" ile açar) · "auto[,ek...]" = yukarıdaki
# sınıflandırma · açık liste = eski TrustedHost davranışı aynen.
# Kilit: tests/test_allowed_hosts_rebinding.py
import ipaddress as _ipaddress
import socket as _socket


def _allowed_hosts_secimi(deger: str):
    """Env değerini (mod, ekstra/liste) çiftine çözer — test edilebilir saf fonksiyon."""
    d = (deger or "*").strip()
    if d == "*" or not d:
        return ("kapali", ())
    parcalar = [p.strip() for p in d.split(",") if p.strip()]
    if parcalar and parcalar[0].lower() == "auto":
        return ("auto", tuple(p.lower() for p in parcalar[1:]))
    return ("liste", tuple(parcalar))


def _host_izinli(host: str, ekstra: tuple) -> bool:
    """'auto' modunun sınıflandırması. Boş Host = izinli (HTTP/1.0 fail-open; rebinding boş
    Host ile YAPILAMAZ — tarayıcı her zaman Host yazar)."""
    h = (host or "").strip().lower()
    if not h:
        return True
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]  # IPv6 literal köşeli parantezi
    try:
        _ipaddress.ip_address(h)
        return True  # IP-literal: telefonun LAN erişimi, hotspot, loopback...
    except ValueError:
        pass
    if h == "localhost" or h.endswith(".localhost"):
        return True
    if h.endswith(".local"):
        return True  # mDNS (pemf.local)
    if h == _socket.gethostname().strip().lower():
        return True  # tarayıcıda makine adıyla erişim (http://KLINIK-PC:8000)
    if h.endswith(".trycloudflare.com"):
        return True  # quick tunnel
    if h in ekstra:
        return True
    # Named tunnel hostname'i sırlardan (best-effort; sır altyapısı yoksa sessizce geç).
    try:
        from utils.secrets_manager import get_secret

        tunel = (get_secret("tunnel_hostname", default="", generate=False) or "").strip().lower()
        if tunel and h == tunel:
            return True
    except Exception:
        pass
    return False


class _RebindKorumaMiddleware:
    """Saf ASGI: http+websocket kapsamında Host'u sınıflandırır; yabancı DNS adı → 400.
    Reddedilen host'lar tekrar-log seli üretmesin diye süreç başına bir kez loglanır."""

    def __init__(self, app, ekstra: tuple = ()):
        self.app = app
        self.ekstra = tuple(ekstra)
        self._loglanan: set = set()

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        host = ""
        for ad, deger in scope.get("headers") or []:
            if ad == b"host":
                host = deger.decode("latin-1")
                break
        # Port'u at ([::1]:8000 dahil): son ':' yalnız rakam taşıyorsa porttur.
        if ":" in host:
            govde, _, kuyruk = host.rpartition(":")
            if kuyruk.isdigit():
                host = govde
        if _host_izinli(host, self.ekstra):
            return await self.app(scope, receive, send)
        if host not in self._loglanan:
            self._loglanan.add(host)
            logging.getLogger(__name__).warning(
                "Host reddedildi (DNS-rebinding korumasi): %r — mesru bir adsa PEMF_ALLOWED_HOSTS='auto,%s' ekleyin",
                host,
                host,
            )
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4400})
            return
        await send(
            {"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"text/plain; charset=utf-8")]}
        )
        await send({"type": "http.response.body", "body": "Gecersiz Host basligi.".encode("utf-8")})


_ah_mod, _ah_liste = _allowed_hosts_secimi(os.getenv("PEMF_ALLOWED_HOSTS", "*"))
if _ah_mod == "auto":
    app.add_middleware(_RebindKorumaMiddleware, ekstra=_ah_liste)
elif _ah_mod == "liste":
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(_ah_liste))


def _json_detay(metin: str) -> str:
    """Ara katman hata gövdesi (JSON) — TR (ASCII) gövde bayt bayt eskisiyle aynı."""
    return json.dumps({"detail": metin}, separators=(",", ":"))


# ── Global exception handler'ları (audit B-4.1) ────────────────────────────────
# Eskiden yakalanmayan istisna → Starlette varsayılan 500 (korelasyon-id'siz, merkezî log'suz);
# doğrulama hataları da tutarsız formattaydı. Artık TEK, tutarlı zarf: yakalanmayan istisnalar
# SUNUCU-TARAFI korelasyon-id ile loglanır ve istemciye ham traceback/str(e) SIZMAZ (bilgi ifşası).
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    err_id = _uuid.uuid4().hex[:12]
    logging.getLogger("api_server").exception(
        "Yakalanmayan istisna [error_id=%s] %s %s", err_id, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": ceviri.t("hata.beklenmeyen", dil=ceviri.istekten_dil(request)), "error_id": err_id},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    # 'input' alanı PII taşıyabilir → istemciye YALNIZ loc/msg/type; ham girdi değeri sızmaz.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": ceviri.t("hata.gecersizIstek", dil=ceviri.istekten_dil(request)), "errors": errors},
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Expo Web üzerinde SQLite (wa-sqlite) kullanabilmek için 'SharedArrayBuffer' nesnesine ihtiyaç vardır.
    Bu nesnenin tarayıcıda tanımlı olabilmesi için COOP ve COEP header'larının 'same-origin' / 'require-corp' olarak ayarlanması ZORUNLUDUR.
    Aksi halde uygulama beyaz ekranda kalır ve 'SharedArrayBuffer is not defined' hatası fırlatır.
    """
    # O-1: request-correlation-id — istemci X-Request-ID'sini (güvenli-karakter SÜZ → header/log-injection'a
    # karşı) kullan ya da üret; JSON-log + yanıt header'ında izlenir (7/24 saha debug).
    _rid = (
        "".join(c for c in (request.headers.get("X-Request-ID") or "") if c.isalnum() or c in "._-")[:64]
        or _uuid.uuid4().hex[:12]
    )
    from utils.request_context import request_id_var

    request_id_var.set(_rid)
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["X-API-Version"] = _APP_VERSION  # istemci/monitoring sürüm görünürlüğü
    # Paket kimliği: aynı sürüm numarası farklı ikiliyi çalıştırabilir (yeniden yayın, yarım
    # güncelleme). Olay kaydında "hangi paket" sorusunu tek başına cevaplar. Launcher'sız
    # çalıştırmada boş → header hiç eklenmez (uydurma değer basmaktansa sessiz kal).
    if _BUILD_ID:
        response.headers["X-Build-Id"] = _BUILD_ID
    # Klasik güvenlik header'ları (audit S-1): MIME-sniff / clickjacking / referrer-sızıntı önle.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    # HSTS YALNIZ TLS-proxy/tünel arkasından (LAN düz-HTTP'de anlamsız; tarayıcı HTTP'de yok sayar).
    _h = request.headers
    if _h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    # CSP (audit P2 #62/#63/#64) — YALNIZ sunulan web (HTML) yanıtlarına. Kilit koruma connect-src:
    # bir XSS/tedarik-zinciri script'i çalışsa bile localStorage'daki X-API-Key + Supabase token'ını
    # DIŞ sunucuya sızdıramaz (self + Supabase + aynı-origin ws dışına ağ isteği bloklanır). script/
    # style/asset yönergeleri Expo-web'i kırmayacak kadar geniş; object/base/frame-ancestors kilitli.
    _ctype = response.headers.get("content-type", "")
    if _ctype.startswith("text/html"):
        _host = _h.get("host", "")
        # SAHA 2026-09-08 (masaüstü, WebView2): connect-src'de `blob:`/`data:` YOKTU. Arayüz seçilen
        # görseli/sesi `fetch(blob:…)` / `fetch(data:…)` ile okuyup form-data'ya koyar (AiHub: imageFile
        # yokken 7 yerde, scratch `dosya.file` yokken, ses kaydı). Tarayıcı bunu CSP ile kesince fetch
        # `TypeError: Failed to fetch` fırlatır → arayüz "Ağ veya sunucu hatası." der, backend'e istek
        # HİÇ ulaşmaz, günlükte iz yoktur (CDP `securitypolicyviolation` ile ÖLÇÜLDÜ: connect-src->blob,
        # connect-src->data, media-src->blob). `blob:`/`data:` DIŞA veri sızdıramaz (aynı belgenin kendi
        # nesneleri) → connect-src'nin sızıntı-önleme amacı korunur. `media-src` de eklendi: yoksa
        # default-src 'self' devreye girip kayıt/yükleme (blob:) sesinin ÇALINMASINI engelliyordu.
        # Kapı: tests/test_csp_blob_baglanti.py (mutasyonla kırmızı kanıtlı).
        _connect = "'self' blob: data: https://*.supabase.co"
        if _host:
            _connect += f" ws://{_host} wss://{_host}"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "worker-src 'self' blob:; "
            f"connect-src {_connect}; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'"
        )
    response.headers["X-Request-ID"] = _rid
    return response


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """P0 #1: PEMF_REQUIRE_AUTH=1 iken donanım/hasta/seans endpoint'lerine token zorunlu kılar.
    İstemci: X-API-Key header veya ?token= query. OPTIONS(preflight) + muaf yollar serbesttir
    (emergency_stop/health/discovery/simulator). Auth KAPALIYKEN hiçbir şey değişmez (geriye uyumlu)."""
    # API versiyonlama (audit B-8.1): /api/v1/* yolları /api/* handler'larına yönlendirilir → hem
    # ESKİ istemciler (/api) hem YENİ istemciler (/api/v1) çalışır; route çoğaltmadan.
    # DENETIM P3: bu yeniden-yazim eskiden add_security_headers icindeydi; Starlette'te en SON
    # eklenen middleware EN DISTA calistigindan (kayit sirasi: headers, auth, rate-limit) o
    # middleware auth'tan SONRA kosuyordu → auth, yeniden-YAZILMAMIS yolu goruyordu ve
    # is_exempt("/api/v1/hardware/emergency_stop") tutmuyordu: fail-safe ACIL DURDURMA ucu
    # /api/v1 alias'inda 401 veriyordu. Yeniden-yazim artik auth'tan ONCE.
    # D3.06 (B-2.8): yeniden yazım artık EN DIŞ katmanlardan birinde (`_ApiV1TakmaAdi`, rate-limit'ten de ÖNCE) — burada
    # yalnız savunma: bir katman sırası değişikliği onu atlatırsa auth yine yeniden-yazılmış yolu görsün (idempotent).
    _p = request.scope.get("path", "")
    if _p.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + _p[len("/api/v1/") :]
    if request.method == "OPTIONS":
        return await call_next(request)
    # P1 audit 2026-06-28: FAIL-CLOSED. Eskiden auth yolundaki HERHANGI istisna (servers.auth
    # import hatasi, check_token bug) except'e dusup KOSULSUZ call_next ediyordu → TUM enforcement
    # bypass (sessiz fail-open). Artik: auth-katmani yuklenemezse guvenlik-muaf yollar (emergency_stop/
    # health/discovery/simulator) gecer, GERISI 503; token kontrolu patlarsa 401.
    try:
        from servers.auth import check_token, is_exempt, is_local_request, require_auth

        required = bool(require_auth())
        exempt = is_exempt(request.url.path)
        # YEREL/LAN MUAF: masaüstü kısayolu (localhost:8000) + aynı-WiFi istekleri token İSTEMEZ;
        # token YALNIZ tünel/uzak (Cloudflare header'lı) erişimde gerekir → web arayüzü yerelde sorunsuz açılır.
        if not exempt:
            _h = request.headers
            _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
            if is_local_request(request.client.host if request.client else "", _via_proxy):
                exempt = True
    except Exception:
        logging.exception("auth katmani yuklenemedi (FAIL-CLOSED)")
        p = request.url.path
        if any(s in p for s in ("emergency_stop", "/health", "/discovery", "/simulator")):
            return await call_next(request)
        return Response(
            status_code=503,
            content=_json_detay(ceviri.t("hata.authKatmani", dil=ceviri.istekten_dil(request))),
            media_type="application/json",
        )
    if required and not exempt:
        try:
            ok = check_token(request.headers.get("X-API-Key") or request.query_params.get("token") or "")
        except Exception:
            logging.exception("token kontrol hatasi (FAIL-CLOSED)")
            ok = False
        if not ok:
            return Response(
                status_code=401,
                content=_json_detay(ceviri.t("hata.apiAnahtari", dil=ceviri.istekten_dil(request))),
                media_type="application/json",
            )
    return await call_next(request)


# ── Rate limiting (in-process, per-UZAK-IP) — DoS/tarama azaltma (audit B-1.6) ──────────
# YEREL/LAN trafiği (web UI + 8 mobil, güvenli ağ) SINIRLANMAZ — yüksek-frekanslı meşru polling
# (AI Pro capture ~400ms, reconcile 2s) kırılmasın. Yalnız UZAK (Cloudflare tünel / reverse-proxy)
# istekler internet yüzeyi olduğundan pencere-başı sınırlıdır. Token 192-bit → brute-force zaten
# imkânsız; buradaki fayda DoS/otomatik-tarama azaltma. Env: PEMF_RATELIMIT_REMOTE_PER_MIN (vars. 600,
# 0=kapalı). ACİL-DURDURMA + health + discovery DAİMA muaf (fail-safe). _rl_hits yalnız bu async
# middleware'den (event-loop, tek-thread) erişilir → kilit gerekmez.
_RL_WINDOW_SEC = 60.0
try:
    _RL_REMOTE_MAX = int(os.getenv("PEMF_RATELIMIT_REMOTE_PER_MIN", "600"))
except ValueError:
    _RL_REMOTE_MAX = 600
_rl_hits: dict = {}  # client_ip -> [window_start_epoch, count]
_rl_last_purge = [0.0]


def _rl_client_ip(request: Request) -> str:
    """Gerçek istemci IP'si (per-istemci rate-limit anahtarı). GÜVENLİK (audit P3 #5): ham
    X-Forwarded-For SPOOF-EDİLEBİLİR (istemci keyfi XFF gönderip her istekte anahtar-değiştirerek
    rate-limit'i atlar) → ANAHTAR olarak KULLANMA. Yalnız Cloudflare'in DOĞRULADIĞI cf-connecting-ip
    (cloudflared client-supplied değeri ezer) veya doğrudan SOKET IP'si."""
    # DENETIM P3: cf-connecting-ip KOSULSUZ kullaniliyordu — soket-IP'nin gercekten guvenilir bir
    # proxy olup olmadigi hic sorulmuyordu. Cloudflare'siz kurulumda (dogrudan LAN/port-forward)
    # saldirgan her istekte farkli bir cf-connecting-ip uydurup rate-limit anahtarini degistirerek
    # siniri TAMAMEN atlayabiliyordu. Baslik artik YALNIZCA istek beyan edilmis bir ters-proxy'den
    # geliyorsa kullanilir (PEMF_TRUSTED_PROXIES); aksi halde SOKET IP'si esas alinir.
    # D3.34: kural TEK yerde (`servers.auth.istemci_adresi`) — takas / sifirlama kovalari ve denetim izi de onu kullanir.
    # cf-connecting-ip yalniz tunel acikken LOOPBACK'ten (cihazdaki cloudflared); B-2.20: beyanli proxy arkasinda XFF'in
    # SON atlamasi (sunucu profilinde tek kova kalmasin); IG-9.51: beyanli proxy'nin (nginx) aynen ilettigi uydurma
    # cf-connecting-ip artik anahtar DEGIL. Diger her durumda (dogrudan LAN/port-forward) SOKET IP'si esas alinir.
    from servers.auth import istemci_adresi

    return istemci_adresi(request)


@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    if _RL_REMOTE_MAX <= 0 or request.method == "OPTIONS":
        return await call_next(request)
    p = request.url.path
    # Fail-safe: acil-durdurma + sağlık/keşif ASLA sınırlanmaz.
    if "emergency_stop" in p or p.startswith("/api/health") or p.startswith("/api/discovery"):
        return await call_next(request)
    _h = request.headers
    _via_proxy = bool(_h.get("cf-connecting-ip") or _h.get("cf-ray") or _h.get("x-forwarded-for"))
    try:
        from servers.auth import is_local_request

        _local = is_local_request(request.client.host if request.client else "", _via_proxy)
    except Exception:
        _local = not _via_proxy
    if _local:
        return await call_next(request)  # LAN/localhost sınırsız (güvenli ağ)
    now = time.time()
    ip = _rl_client_ip(request)
    win = _rl_hits.get(ip)
    if win is None or (now - win[0]) >= _RL_WINDOW_SEC:
        _rl_hits[ip] = [now, 1]
    else:
        win[1] += 1
        if win[1] > _RL_REMOTE_MAX:
            retry = max(1, int(_RL_WINDOW_SEC - (now - win[0])))
            logging.getLogger(__name__).warning("Rate limit: uzak IP %s %s istek/dk aştı (%s)", ip, _RL_REMOTE_MAX, p)
            return Response(
                status_code=429,
                content=_json_detay(ceviri.t("hata.cokIstek", dil=ceviri.istekten_dil(request))),
                media_type="application/json",
                headers={"Retry-After": str(retry)},
            )
    # Bellek: 5 dk'da bir süresi geçmiş pencereleri temizle (uzak IP birikimi olmasın).
    if now - _rl_last_purge[0] > 300:
        _rl_last_purge[0] = now
        for _k in [k for k, v in _rl_hits.items() if now - v[0] >= _RL_WINDOW_SEC]:
            _rl_hits.pop(_k, None)
    return await call_next(request)


class _SurusNiyetiVarisDamgasi:
    """D1.81 · Y4 (1-C inceleme i1-F2 + F1 notu): bir HTTP isteğinin START NİYETİ, isteğin VARIŞ anındaki sürüş
    neslini taşır — gövde (landmark görüntüsü, JSON) OKUNMADAN ve handler'a girmeden ÖNCE.

    ⚠️ NEDEN: nesil handler GİRİŞİNDE alınınca iki açık kalıyordu (ölçüldü): (1) `/api/coil/batch` niyet nesli
    taşımıyordu — ESP yayını (saniyeler) sürerken gelen E-stop + Sıfırla'dan sonra kalan STM bobinleri E-stop ÖNCESİ
    niyetle sürülüyordu (30/30); (2) FastAPI gövdeyi handler'dan önce okur — mandallıyken gönderilmiş bir START'ın
    gövdesi Sıfırla'dan SONRA biterse handler yeni nesli alıp sürerdi (Y4: mandal kuruluyken hiçbir START). Damga
    `estop_mandali.surus_baglami` bağlamına yazılır; `HardwareController` ve `_esp_start_yayinla` (`asyncio.to_thread`
    bağlamı kopyalar) onu kilit altında denetler. Handler'lar `estop_mandali.niyet_nesli()` ile aynı damgayı okur.

    ⚠️ En DIŞTAKİ ara katmandır (en son eklenir). YALNIZ START'ı etkiler; STOP / acil durdurma nesle bakmaz (Ö.4-Y8).
    Saf ASGI: isteğin kendi görevinde koşar (bağlam alt katmanlara kesin geçer). WebSocket'e dokunmaz."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        with estop_mandali.surus_baglami(estop_mandali.nesil()):
            await self.app(scope, receive, send)


class _IstekDiliBaglami:
    """I18N (Y157–Y161 · T5/T6): isteğin DİLİ — `X-PEMF-Dil: tr|en` başlığı > `?dil=` (URL ile açılan PDF / görsel / iframe) > `tr`.

    ⚠️ `Accept-Language` OKUNMAZ (bilinçli): WebView2 / tarayıcı onu işletim sisteminin dilinden kendisi doldurur; İngilizce Windows'ta
    Türkçe seçili arayüze İngilizce ileti dönerdi. Başlık göndermeyen eski istemci (yayındaki APK) = tr. Dil `utils.ceviri.istek_dili_var`
    bağlamına yazılır; işleyiciler `ceviri.t()` ile o dilde metin üretir. Saf ASGI (bağlam alt katmanlara kesin geçer); bütün
    `@app.middleware("http")` katmanlarının DIŞINDA (kimlik / hız sınırı iletileri de istek dilinde), sürüş damgasının hemen İÇİNDE
    (damga en dışta kalır). WebSocket'e dokunmaz (WS olayları `kod` + `parametreler` taşır, arayüz çevirir). Güvenlik kapısı DEĞİL."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        from urllib.parse import parse_qs

        from utils import ceviri

        baslik = None
        for ad, deger in scope.get("headers") or ():
            if ad == b"x-pemf-dil":
                baslik = deger.decode("latin-1")
                break
        sorgu = (parse_qs((scope.get("query_string") or b"").decode("latin-1")).get(ceviri.DIL_PARAMETRESI) or [None])[
            0
        ]
        jeton = ceviri.istek_dili_var.set(ceviri.dil_coz(baslik, sorgu))
        try:
            await self.app(scope, receive, send)
        finally:
            ceviri.istek_dili_var.reset(jeton)


class _ApiV1TakmaAdi:
    """D3.06 (B-2.8): `/api/v1/*` → `/api/*` yeniden yazımı EN DIŞ katmanlarda — `@app.middleware("http")` katmanlarının HEPSİNDEN
    (rate-limit dahil) ÖNCE. Eskiden yalnız auth katmanının içindeydi; rate-limit auth'tan SONRA eklendiği için (Starlette'te son
    eklenen en dışta koşar) yeniden-yazılMAMIŞ yolu görüyor, sağlık / keşif muafiyeti takma adda tutmuyordu: uzak `/api/v1/health`
    sınır aşımında 429 (ölçüldü: [200, 200, 200, 429, 429]). ACİL DURDUR muafiyeti etkilenmez (alt dize denetimi; Ö.4-Y8).
    Saf ASGI, yalnız HTTP; WebSocket'e dokunmaz. Sıra: sürüş damgası > dil bağlamı > bu > http katmanları."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            yol = scope.get("path", "")
            if yol.startswith("/api/v1/"):
                scope = dict(scope)
                scope["path"] = "/api/" + yol[len("/api/v1/") :]
        await self.app(scope, receive, send)


app.add_middleware(_ApiV1TakmaAdi)
app.add_middleware(_IstekDiliBaglami)
app.add_middleware(_SurusNiyetiVarisDamgasi)


app.include_router(ai_router)
app.include_router(history_router)
app.include_router(settings_router)
# audit B-2.2: cohesive uç grupları ayrı modüler router'lara çıkarıldı (api_server.py küçültüldü).
from servers.auth_router import router as auth_router
from servers.patient_router import router as patient_router
from servers.session_router import router as session_router
from servers.system_router import router as system_router
from servers.update_router import router as update_router

app.include_router(update_router)
app.include_router(patient_router)
app.include_router(system_router)
app.include_router(session_router)
app.include_router(auth_router)


# (audit B-2.2) /api/update/* uçları servers/update_router.py'ye taşındı (modüler ayrım).

# DEMA Simülatörü host etme
import os

from utils.path_utils import packaged_resource_path

# ═══════════════════════════════════════════════════════════════════
# WebSocket + MQTT Canlı Veri Sistemi (port 8000 üzerinden)
# Tek portlu headless backend: REST API + WebSocket canlı veri sistemi.
# ═══════════════════════════════════════════════════════════════════

# ── WebSocket bağlantı havuzu ──────────────────────────────────────
# B-2.2: WS istemci kaydı + gönderim serileştirme + broadcast → servers/live_state.py (üstte alias'landı).


# B-2.2: _live_state + _sync_stm_coils_locked + _push_notification → servers/live_state.py (üstte alias'landı).


# ── MQTT Callbacks ─────────────────────────────────────────────────
_mqtt_client_api = None


def _on_mqtt_connect_api(client, userdata, flags, rc):
    if rc == 0:
        with _live_state_lock:
            _live_state["mqtt"] = "online"
        client.subscribe("pemf/coil/+/sensors")
        client.subscribe("pemf/coil/+/status")
        client.subscribe("pemf/coil/+/events")
        client.subscribe("pemf/coil/+/alarm")
        client.subscribe("pemf/coil/+/ack")  # HG-4 (2026-08-19): ESP komut onayı — E-stop teslimi doğrulanabilsin
        client.subscribe("pemf/gateway/status")
        client.subscribe("pemf/bridge/status")
        _bildir(lambda d: ceviri.t("bildirim.sistemBaglandi", dil=d), "success")
    else:
        with _live_state_lock:
            _live_state["mqtt"] = "error"


def _on_mqtt_disconnect_api(client, userdata, rc):
    with _live_state_lock:
        _live_state["mqtt"] = "error"
    _bildir(lambda d: ceviri.t("bildirim.sistemKesildi", dil=d), "warning")


# ── ESP telemetri STALENESS watchdog (reconnect-audit self-heal) ──────────────
# Gap: ESP güç kaybıyla LWT yaymadan (ungraceful) ölürse coil `connected:True` + BAYAT sensör değerleri
# kalıyordu → UI'da "canlı" görünüyordu. ESP bobinleri sıcaklık izleme için PERİYODİK sensör yayınlar;
# GENİŞ eşik (30sn) boyunca HİÇ mesaj gelmezse coil'i disconnected işaretle. Geniş eşik → normal yayın
# aralığında yanlış-alarm yok; sonraki ESP mesajı gelince connected=True'ya KENDİ düzelir. Yalnız ESP
# bobinlerine dokunur (STM 1-5 zaten _sync_stm_coils'ten türer). Timestamp yalnız gerçek MQTT mesajında
# yazılır → PEMF_SIMULATE modda sözlük boş kalır, watchdog no-op (sim coil'lerini bozmaz).
_coil_last_telemetry: dict = {}

#: bobin indeksi → {GERCEKTEN olculmus `_live_state` alan adi: son gelis ani (monotonic)}.
#: ⚠️ NEDEN ALAN BAZINDA: bobin bazinda "telemetri geldi mi" bilgisi 2026-09-10'da YETERSIZ
#: kaldi. Bobin 1-5 yalniz AKIM gonderiyor (ACS712), bobin 6-7 yalniz SICAKLIK/ALAN
#: gonderecek. Bobin bazinda damgayla yetinmek, gonderilmeyen alanin 0.0 baslangic degerini
#: "olculdu" sayip DB'ye yazdirir (PDF'te "0.0 °C olculdu" arizasinin ta kendisi).
#: ⚠️ D1.67 (B-1.3) — NEDEN DAMGA: eskiden bir KUMEYDI ve yalniz `add` ile buyuyordu. Sensor
#: susunca (kablo/I2C/MLX arizasi) son deger `_live_state`te DONUYOR, alan "olculuyor" kaliyor,
#: arayuz donmus sayiyi CANLI gosteriyor ve dakika akumulatoru onu her turda DB'ye yaziyordu.
#: Artik "olculuyor" = son `ALAN_TAZELIK_S` icinde GELDI (`_taze_alanlar_locked`).
_coil_olculen_alanlar: dict = {}

#: D1.67 — firmware'in `STM_TELE` basma periyodu (sn): `pemf_sensor.c` `SENSOR_ZIRVE_PENCERE_MS`
#: (1000 ms; sicaklik da ayni pencerede okunur, ayri periyodu yok). Kapi ikisini ESLER:
#: tests/test_telemetri_TAZELIGI_bayat_alan_OLCULMUS_SAYILMAZ.py.
STM_TELE_PERIYOT_S = 1.0
#: Bir alan bu sure icinde yeniden gelmezse "olculuyor" SAYILMAZ: `measuredFields`ten duser (arayuz
#: '—' gosterir, Y6) ve akumulatore/dakika satirina/run ozetine girmez. 5 periyot: firmware UART
#: mesgulken turu ATLAR — iki-uc atlanan satir '—' titresimi uretmesin.
#: ⚠️ YALNIZ GOSTERIM VE KAYIT (A-47, Y2): bayat/olculmeyen alan HICBIR durdurma ya da engelleme
#: tetiklemez — termal kesme hicbir katmanda YOK.
ALAN_TAZELIK_S = 5 * STM_TELE_PERIYOT_S


def _taze_alanlar_locked(idx: int, simdi: float) -> set:
    """Bobin `idx`in son `ALAN_TAZELIK_S` icinde GERCEKTEN gelen alanlari. Cagiran `_live_state_lock` tutar."""
    damga = _coil_olculen_alanlar.get(idx) or {}
    return {alan for alan, t in damga.items() if simdi - t <= ALAN_TAZELIK_S}


def _olculen_alanlari_tazele() -> None:
    """D1.67: susan sensorun alanini `measuredFields`ten DUSURUR ve istemciye `coil_status` ile bildirir.

    Yalniz yeni telemetride hesaplanan tazelik, sensor TAMAMEN sustugunda (hic satir yok) isimez:
    liste guncellenmez, arayuz son listeyle donmus degeri canli gosterir. Bu yuzden sensor dongusu
    (`_sensor_persistence_loop`) her turda bunu cagirir. Durdurma/engelleme YOK (A-47)."""
    simdi = time.monotonic()
    degisen = []
    alani_dusen = []
    with _live_state_lock:
        for idx in list(_coil_olculen_alanlar):
            if not (0 <= idx < 8):
                continue
            coil = _live_state["coils"][idx]
            eski = list(coil.get("measuredFields") or [])
            taze = sorted(_taze_alanlar_locked(idx, simdi))
            if taze != eski:
                coil["measuredFields"] = taze
                degisen.append((idx + 1, dict(coil)))
                if "magneticMt" in eski and "magneticMt" not in taze:
                    alani_dusen.append(idx + 1)
        _anlik_bobin = _live_state["activeTreatment"].get("measuredIntensityCoil")
    for cid, snap in degisen:
        _ws_broadcast_sync({"type": "coil_status", "coilId": cid, "data": snap})
    # D1.76 (D1.67 açık-2): seans kartının ANLIK ölçülen yoğunluğu o bobinin alan sensöründen gelir — sensör susunca
    # son değer "anlık" kalmaz ('—'); seans TEPESİ ölçülmüş bir kayıttır, korunur.
    if _anlik_bobin in alani_dusen:
        try:
            update_measured_intensity(None, None, _seans_alan.zirve())
        except Exception:
            logging.exception("susan alan sensörünün anlık yoğunluğu temizlenemedi")


#: TD5: "akım güvenilmez" bildirimi BASILMIŞ bobin indeksleri — STM bağlantısı boyunca bobin başına TEK birleşik uyarı (tezgâh:
#: her 0→1 geçişinde basılan doygunluk bildirimi yüzen girişte 46 kez geldi). Yeniden bağlanınca (yeni kart / yakma) sıfırlanır.
_akim_guvenilmez_bildirildi: set = set()

#: TD5: ACS712-30A ölçüm aralığı (A) — `headless_core.ACS712_AZAMI_A` ile AYNI (eşlik: tests/test_TD5_akim_GUVENILMEZ_…).
_ACS712_AZAMI_A = 30.0


def _akim_guvenilmez_mi(data: dict) -> bool:
    """TD5: telemetri akımı güvenilmez mi — ADC tavanı (`current_saturated`), aralık dışı ya da sayı değil."""
    if data.get("current_saturated"):
        return True
    try:
        return not (0.0 <= float(data["current"]) <= _ACS712_AZAMI_A)
    except (TypeError, ValueError):
        return True


#: STM_NACK bildirim kısıtlayıcısı: {ozet: son_bildirim_ani}. Bkz. `_stm_nack_bastir`.
_stm_nack_son: dict = {}
_stm_nack_lock = threading.Lock()

#: Aynı NACK sebebi için iki bildirim arası ASGARİ süre (sn).
#
# ⚠️ NEDEN (saha 2026-09-11): firmware/backend paket biçimi uyuşmazsa HER paket NACK'lenir.
# Keep-alive 2 Hz → operatöre saniyede iki özdeş "→ STM_NACK: CRC" düşer; sahada 89+ bildirim
# ölçüldü. Liste tıkanınca termal kesme / watchdog / doygunluk gibi GERÇEK olaylar görünmez
# olur. Bu bir alarm-yorgunluğu arızasıdır; bastırma SEBEP BAZINDA yapılır ki farklı bir NACK
# (ör. parametre reddi) CRC seline gömülmesin.
_STM_NACK_BILDIRIM_ARALIGI_S = 30.0


def _stm_nack_bastir(mesaj: str) -> bool:
    """Bu NACK bildirimi BASTIRILMALI mı? (True = gösterme)

    İlk olay HEMEN gösterilir; aynı sebep `_STM_NACK_BILDIRIM_ARALIGI_S` boyunca susturulur.
    ⚠️ Sebep bazında: "CRC" bastırılırken farklı bir NACK metni kendi hakkını korur.
    """
    ozet = "".join(ch for ch in mesaj.upper() if ch.isalpha())[:40]
    simdi = time.monotonic()
    with _stm_nack_lock:
        son = _stm_nack_son.get(ozet)
        if son is not None and (simdi - son) < _STM_NACK_BILDIRIM_ARALIGI_S:
            return True
        _stm_nack_son[ozet] = simdi
    return False


#: Firmware uyuşmazlığında operatöre gösterilen EYLEM METNİ — tek kaynak.
#: ⚠️ Aynı cümle hem bildirime hem `/session/start` reddine gider; iki yerde iki farklı
#: açıklama, operatörün "hangisi doğru?" diye durmasına yol açardı.
#: ⚠️ TD1 · K1 (tezgâh 2026-10-14, sahip: "o bir veteriner, yazılımcı değil"): eski metin CubeIDE talimatı ve "Açılış
#: satırı '7-ch' demeli" diyordu — uyumsuz (120 baytlık) kart da "7-ch" basar (YANLIŞ YÖN), CubeIDE klinik personeline
#: göre değil (JARGON). Geliştirici / servis talimatı yalnız destek ayrıntısında (`/api/health` `stmUyumsuzlukSebebi`,
#: `docs/SAHA-ISLERI-REHBERI.md` B-2). Kod (FW-PAKET) arayüz bandıyla AYNI (`utils.stm32_kimlik.OPERATOR_METNI`).
STM_RED_MESAJI = _stm32_kimlik.KOMUT_RED_METNI


def stm_red_mesaji(dil: str | None = None) -> str:
    """`STM_RED_MESAJI`nin İSTEK dilindeki karşılığı (409 / bildirim). ⚠️ ACİL DURDUR mandal EYLEMİ sabit Türkçe `STM_RED_MESAJI`yi kullanır."""
    return _stm32_kimlik.komut_red_metni(dil)


def _donanim_baslatma_reddi(donanim) -> str:
    """Donanım nesnesinin son START reddi sebebi (`HardwareController.son_baslatma_reddi`); bildirmeyen nesnede ""."""
    oku = getattr(donanim, "son_baslatma_reddi", None)
    return str(oku() or "") if callable(oku) else ""


def _seans_red_nedeni(sebepler: list) -> str:
    """D6.02 (S-1.7): HİÇBİR STM bobini kabul etmediğinde 503'ün NEDENİ.

    ⚠️ Eskiden HER durumda `stm_red_mesaji()` ("kartın yazılımı uyumsuz … FW-PAKET") veriliyordu; en sık sebep ise kablonun
    takılı olmamasıydı (kopuk STM) — veteriner sağlam kart için teknik destek arıyordu. Sıra: (1) donanımın KENDİ red sebebi
    (kopuk → "USB (ST-Link) kablosunu takın", gönderici ölü, parametre, mandal); (2) sebep bildirmeyen donanım nesnesinde STM
    kopuksa bağlantı eylemi; (3) yalnız o da yoksa eski kart-reddi metni. Firmware KESİN uyumsuz / kart komutları reddediyor
    kolları bu noktadan ÖNCE kendi 409'unu verir (metinleri DEĞİŞMEDİ)."""
    for sebep in sebepler or ():
        if sebep:
            return str(sebep)
    if not live_state.stm_surus_hazir():
        return ceviri.t("donanim.hata.stmBagliDegil")
    return stm_red_mesaji()


def _duty_seans_durdu_metni(ham: str, dil: str) -> str:
    sonuc = ceviri.t("bildirim.sonuc.seansDurduruldu", dil=dil)
    return live_state.stm_duty_reddi_metni(ham, sonuc, sifirla=True, dil=dil)


def _duty_cikislar_metni(ham: str, dil: str, durdu: bool) -> str:
    sonuc = ceviri.t("bildirim.sonuc.cikislarDurduruldu", dil=dil) if durdu else ""
    return live_state.stm_duty_reddi_metni(ham, sonuc, dil=dil)


#: D1.53 (A-05): 0 Hz seans isteğinin nedeni — tek kaynak (mandallı ve mandalsız yol AYNI metni verir; 1-C i3-F-4).
def sifir_hz_seans_mesaji() -> str:
    return ceviri.t("seans.hata.sifirHz")


#: Y65 (sahip, 1-F inceleme S-İF1): tedavi kaydının DB satırı açılamazsa seans BAŞLAMAZ — elle seans ve AI Pro AYNI metin.
def kayit_acilamadi_mesaji() -> str:
    return ceviri.t("seans.hata.kayitAcilamadi")


class KayitAcilamadi(RuntimeError):
    """Y65: yeni seansın tedavi kaydı (DB satırı) açılamadı — seans aktif BIRAKILMADI, bobin sürülmedi."""


def _seansi_geri_al(sebep: str, seans_kimligi=None) -> None:
    """Başlatılmış ama HİÇ SÜRÜLEMEMİŞ seansı geri al (kayıt YALAN olmasın).

    ⚠️ NEDEN GEREKLİ: `_active_session` ve DB satırı, bobinler sürülmeden ÖNCE oluşur
    (sıra bilinçlidir — backend seans ortasında çökerse bile kayıt kalsın diye). Bobinlerin
    hiçbiri komutu kabul etmezse o kayıt, hiç uygulanmamış bir tedaviyi belgeler hâle gelir.
    Burada seans kapatılır ve `donanim-reddi` sebebiyle mühürlenir → geçmişte "Donanım
    Reddetti" görünür, "Tamamlandı" DEĞİL.

    ⚠️ BOBİNLERE DOKUNULMAZ: hiçbiri enerjilenmedi (kabul listesi boş). Buradan bir STOP
    göndermek, aynı anda başlamış BAŞKA bir seansın bobinlerini düşürme riski taşırdı.

    ⚠️ YALNIZ KENDİ SEANSI (1-C inceleme i1-F3 / i2-F1): `seans_kimligi` verilirse geri alma YALNIZ o kimlikli seans
    HÂLÂ aktifse yapılır. Ölçüldü: bayat bir başlatma (DB yazımı sürerken Durdur — ya da E-stop + Sıfırla — ve YENİ
    seans) sürüşte nesille doğru reddediliyor ama bu geri alma O AN AKTİF olan YENİ seansı pasife çekip "Sistem
    Hazır" yazıyordu (30/30) — yeni seansın bobini enerjiliyken, süre bekçisinin göremeyeceği biçimde.
    """
    try:
        with _session_lock:
            if seans_kimligi is not None and not (
                _active_session.get("is_active") and _active_session.get("session_id") == seans_kimligi
            ):
                logging.getLogger(__name__).warning(
                    "Seans geri alma ATLANDI (%s): aktif seans artik bu baslatmanin degil.", sebep
                )
                return
            db_session_id = _active_session.get("db_session_id")
            started_epoch = _active_session.get("started_epoch") or _active_session.get("start_time")
            start_mono = _active_session.get("start_mono")
            coil_ids = _active_session.get("coil_ids") or []
            _active_session["is_active"] = False
        try:
            update_live_session_state(is_active=False, mode="Sistem Hazır")
        except Exception:
            logging.getLogger(__name__).debug("geri-al: canli durum guncellenemedi", exc_info=True)
        if db_session_id:
            _finalize_session_db(db_session_id, started_epoch, coil_ids=coil_ids, reason=sebep, start_mono=start_mono)
        logging.getLogger(__name__).error("Seans GERI ALINDI (%s): hicbir bobin surulmedi.", sebep)
    except Exception:
        logging.getLogger(__name__).exception("Seans geri alma basarisiz (%s)", sebep)


def _iptal_seans_satirini_kapat(db_session_id) -> None:
    """Enerjilemeden ÖNCE durdurulan (iptal edilen) başlatmanın KENDİ DB satırını `cancelled` ("İptal Edildi") kapat.

    ⚠️ 1-C inceleme i2-F7 (ölçüldü 30/30): başlatmanın DB yazımı sürerken gelen durdurma/acil durdurma seansı
    "cancelled" bitiriyor ama açtığı satır 'active' kalıyordu — uygulanmamış bir tedavi geçmişte "sürüyor" görünür.
    ⚠️ `_finalize_session_db` KULLANILMAZ: o KÜRESEL dakika/sensör tamponlarını boşaltır; arada açılmış YENİ seansın
    telemetrisi bu satıra yazılırdı. Satır sürmemiş bir başlatmaya aittir: süre 0, koşu kaydı yok. SENKRON (thread)."""
    if not db_session_id:
        return
    try:
        db = _get_treatment_db()
        if db is None:
            return
        db.end_session(db_session_id, duration_minutes=0, session_status="cancelled")
        db.set_session_meta(db_session_id, ended_epoch=time.time())
    except Exception:
        logging.getLogger(__name__).warning(
            "Iptal edilen seansin DB satiri kapatilamadi (db_id=%s).", db_session_id, exc_info=True
        )


def _ai_pro_plandan_cikar(bobinler) -> None:
    """Y54 (sahip): AI Pro sürerken operatörün bobin-başı STOP'u o bobini seans sonuna dek AI Pro PLANINDAN çıkarır ve
    ekranda söylenir. STOP gönderiminden ÖNCE çağrılır; STOP'u kapılamaz, geciktirmez (Ö.4-Y8); istisna atmaz."""
    try:
        from servers import ai_router as _air

        for b in _air.ai_pro_bobinlerini_plandan_cikar(bobinler):
            _bildir(lambda d, b=b: ceviri.t("bildirim.aiProPlandanCikti", dil=d, coil=b), "warning")
    except Exception:
        logging.getLogger(__name__).exception("Y54: AI Pro plan disi kaydi yapilamadi (STOP suruyor)")


def _ucustaki_baslatmayi_gecersiz_kil(bobinler) -> bool:
    """Bobin-başı STOP UÇUŞTAKİ seans başlatmasını iptal ettirir. STOP gönderiminden ÖNCE çağrılır; istisna atmaz.

    ⚠️ 1-C inceleme i1-F5 (ölçüldü 3/3): `/session/start` DB yazımındayken (await) ya da bobinleri sürerken gelen bobin
    STOP'u (tekil / batch / legacy `stop_coil`; 0 Hz "parkla" dahil) henüz sürülmemiş bobinde no-op'tu — başlatma
    ardından o bobini ENERJİLİYOR ve "success" dönüyordu (arayüzde bobin kartının "⏹ Durdur"u başlatma sürerken
    basılabilir). Nesil yalnız seans / acil durdurma / `stop_all_coils` durdurmasında artıyordu.
    Başlatma uçuştaysa (`baslatma_ucusta`: seans kuruldu, sürüş sonrası denetim bitmedi) ve STOP o seansın bobinlerinden
    birini kapsıyorsa nesil artar → başlatma bobin sürmeden iptal edilir ya da kalan sürüşü `HardwareController`da
    kilit altında reddedilir ve seans durdurulur.
    ⚠️ Başlatma BİTTİKTEN sonra ve AI (Auto) / AI Pro seansında nesle DOKUNMAZ: bobin STOP'u yalnız o bobini durdurur
    (nesil artsaydı tek bobin STOP'u seansın / AI Pro'nun bütün sürüş yetkisini keserdi).
    ⚠️ Bayrak denetimi ve artırım `_session_lock` ALTINDA; başlatma bayrağı aynı kilit altında indirir → STOP ya bayrak
    inmeden nesli artırır (başlatma iptal) ya da bayrak indikten sonra yalnız o bobini durdurur.
    Ö.4-Y8: STOP'u kapılamaz, geciktirmez; yalnız START'ı reddettirir. @return nesil artırıldı mı."""
    try:
        hedef = {int(b) for b in bobinler}
        with _session_lock:
            if not (_active_session.get("is_active") and _active_session.get("baslatma_ucusta")):
                return False
            if not hedef & set(_active_session.get("coil_ids") or ()):
                return False
            estop_mandali.nesil_artir()
        logging.getLogger(__name__).warning(
            "Seans baslatma surerken bobin STOP'u %s → ucustaki baslatma iptal (nesil artirildi).", sorted(hedef)
        )
        return True
    except Exception:
        logging.getLogger(__name__).exception("Ucustaki baslatma iptali basarisiz (STOP yine gonderilir).")
        return False


def _stm_red_aktif_seansi_durdur(ham: str) -> bool:
    """Kart komutları sistematik reddetmeye başladı → AKTİF SEANSI durdur. @return seans durduruldu (bildirim basıldı) mı.

    ═══════════════════════════════════════════════════════════════════════════
    ⚠️ SAHİP BİLDİRİMİ (2026-09-12) — SAHTE "BAŞARILI" SEANS
    ═══════════════════════════════════════════════════════════════════════════
    "bobinler komut almicak bildirimi gelmesine ve gerçekten bobinlere komut gitmemesine
    rağmen seans başlatınca gerçekten başlıyormuş gibi her şey sorunsuz devam ediyor."

    Eskiden bu dal YALNIZCA bildirim basıp `return` ediyordu. Seans aktif kalıyor, sayaç
    işliyor, bobin-çalışma satırları TAM SÜREYLE yazılıyor ve geçmişe "Tamamlandı" düşüyordu
    — hiçbir bobin hiç enerjilenmemişken. Tıbbi kayıt YALAN oluyordu: "bu hastaya 20 dk
    100 Hz uygulandı" diyen bir satır, hiç uygulanmamış bir tedaviyi belgeliyordu.

    ⚠️ `watchdog_timeout` DALI BUNU ZATEN DOĞRU YAPIYORDU (seansı durduruyor). CRC reddi
    aynı sınıftan bir olaydır — "donanım komuta uymuyor" — ve aynı tepkiyi hak eder.
    Aradaki tek fark, watchdog'da bobinler ÇALIŞIYOR olabilir, burada HİÇ çalışmamıştır;
    o yüzden durdurma fiziksel olarak zararsızdır ama KAYIT açısından şarttır.

    ⚠️ ACİL-DURDURMA YOLU KULLANILIR ÇÜNKÜ seansı "tamamlandı" DEĞİL, kesintiye uğramış
    olarak mühürler (`EMERGENCY_STOPPED` → geçmişte "Acil Durduruldu"). Operatör geçmişe
    baktığında bu seansın gerçekleşmediğini GÖREBİLİR. Sessizce "completed" yazmak, arızayı
    veritabanına kalıcılaştırmak olurdu.

    ⚠️ D1.101 · Y20: duty TAVANI reddi (`kip=`) firmware uyuşmazlığı DEĞİLDİR — bildirim nedeni ve eylemi söyler
    ("kartı yeniden programlayın" DEĞİL); kayıt aynı yoldan mühürlenir.
    """
    try:
        with _session_lock:
            _aktif = bool(_active_session.get("is_active"))
            _bobinler = _active_session.get("coil_ids") or list(range(1, 9))
        if not _aktif or not any(c in STM_COIL_IDS for c in _bobinler):
            return False
        logging.getLogger(__name__).error(
            "STM komut REDDI sistematik (%s) → aktif seans durduruluyor (sahte 'tamamlandi' yazilmasin).",
            str(ham)[:120],
        )
        # Y74 (sahip): seansta red ACİL DURDUR yolundan durdurur ve mandal KURULU KALIR → metin "sonra 'Sıfırla'ya basın" der.
        _duty_var = live_state.stm_duty_reddi_coz(ham) is not None
        # TD6 · K12: mandal bandı nedene göre EYLEM söylesin — duty reddinde K3 metni, aksi kart uyumsuzluğu metni. Yalnız
        # METİN (mandal aşağıdaki E-stop yolunda kurulur; imza ve sıra DEĞİŞMEDİ).
        try:
            _duty_eylem = live_state.stm_duty_reddi_metni(ham, sifirla=True, dil="tr")  # mandal EYLEMİ: yazı DEĞİŞMEZ
            # I18N-P1: duty reddi metni "Sıfırla"ya basın der (Y74) → makine-okur bayrak; kart uyumsuzluğu metni demez.
            # I18NI-A1.1: EN arayüz için dil karşılıkları (WS yükü tek; `eylem` TR bayt bayt aynı kalır).
            _eylemler = {
                d: (live_state.stm_duty_reddi_metni(ham, sifirla=True, dil=d) if _duty_eylem else stm_red_mesaji(d))
                for d in ceviri.DILLER
            }
            _eylemler["tr"] = _duty_eylem or STM_RED_MESAJI
            estop_mandali.eylem_birak(
                "stm_komut_reddi", _duty_eylem or STM_RED_MESAJI, sifirla_soyler=bool(_duty_eylem), metinler=_eylemler
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "K12: mandal eylem metni bırakılamadı (durdurma SÜRÜYOR)", exc_info=True
            )
        _bildir(
            lambda d: (
                "⛔ " + _duty_seans_durdu_metni(ham, d)
                if _duty_var
                else ceviri.t("bildirim.stmRedSeansDurdu", dil=d, neden=stm_red_mesaji(d))
            ),
            "error",
        )
        _emergency_stop_async(reason="stm_komut_reddi", mode="Duty Reddedildi" if _duty_var else "Firmware Uyuşmazlığı")
        return True
    except Exception:
        logging.getLogger(__name__).exception("STM red sonrasi seans durdurma basarisiz")
        return False


def _stm_duty_reddini_isle(ham: str, ilk_kez: bool) -> None:
    """D1.101 · Y20 (sahip) — kart bir bobinin duty'sini TAVAN üstü diye reddetti (`STM_NACK: RANGE … kip=`).

    Kenarda (`stm_komut_reddi_bildir` duty reddini TEK NACK'te sistematik sayar — içerik reddi gürültü değildir):
      * STM bobinli aktif seans → seans DURDURULUR (Y20: "sistematik NACK seansı durdurur"; acil durdurma yolu,
        kayıt "Acil Durduruldu") — `_stm_red_aktif_seansi_durdur`, bildirim nedeni ve eylemi söyler.
      * seans yoksa → STM sürüş durumu sıfırlanır (`stop_all_coils`). ⚠️ NEDEN: firmware paketi BÜTÜN olarak reddeder;
        reddedilen istek `HardwareController` durumunda kaldıkça keep-alive onu her turda yeniden gönderir → aynı
        paketlerdeki BAŞKA bobinlerin komutları — STOP dahil — kartta UYGULANMAZ, çalışan bobin ancak firmware
        ölü-adamıyla (1,5 sn) durur (Ö.4-Y8: STOP geciktirilmez). Ölü-adamın ZATEN yapacağı şey ilk NACK'te yapılır.
        ⚠️ Kıskaç DEĞİL (Ö.4-Y9): duty düzeltilmez, istek düşürülür — operatör geçerli değerle yeniden başlatır.
    Kenarda bildirim HER ZAMAN basılır (sistem bir şey durdurduysa operatör nedenini görmeli); NACK seli bastırması
    (`_stm_nack_bastir`) yalnız kenar DIŞI tekrarlara (yeniden deneme, keep-alive) uygulanır."""
    try:
        if not ilk_kez:
            if not _stm_nack_bastir(ham):
                _mandalli = estop_mandali.mandalli_mi()
                _bildir(lambda d: "⛔ " + live_state.stm_duty_reddi_metni(ham, sifirla=_mandalli, dil=d), "error")
            return
        if not _stm_red_aktif_seansi_durdur(ham):
            _durdu = False
            if state.hardware:
                try:
                    _durdu = bool(state.hardware.stop_all_coils())
                except Exception:
                    logging.getLogger(__name__).exception("D1.101: duty reddi sonrasi STM surus durumu sifirlanamadi")
            _bildir(lambda d: "⛔ " + _duty_cikislar_metni(ham, d, _durdu), "error")
        _stm_nack_bastir(ham)  # kenarın ardından gelen aynı sebepli NACK'ler bildirimi yinelemesin
    except Exception:
        logging.getLogger(__name__).exception("D1.101: duty reddi islenemedi")


#: bobin indeksi → son bilinen MANYETIK doygunluk durumu (ayni "yalniz gecis" kurali).
#: ⚠️ AKIMDAN AYRI SOZLUK: ikisini tek sozlukte tutmak, akim doygunlugu 1'ken gelen bir
#: manyetik doygunlugu "degismedi" sanip operatore HIC soylememek demekti.
_mag_doygun_son: dict = {}

ESP_STALE_SEC = 30.0
ESP_WATCHDOG_INTERVAL_SEC = 5.0


def _esp_telemetry_watchdog():
    while True:
        try:
            now = time.monotonic()
            changed = []
            with _live_state_lock:
                for cid in ESP_COIL_IDS:
                    idx = cid - 1
                    if not (0 <= idx < 8):
                        continue
                    last = _coil_last_telemetry.get(idx)
                    coil = _live_state["coils"][idx]
                    # Yalnız: telemetri ALMIŞ (last var) + hâlâ connected + GENİŞ eşik sustu → demote.
                    if last is not None and coil.get("connected") and (now - last) > ESP_STALE_SEC:
                        coil["connected"] = False
                        coil["running"] = False
                        changed.append((cid, dict(coil)))
            # DENETIM P2: bobin YALNIZCA "durdu" ISARETLENIYORDU; gercek bir STOP komutu
            # GONDERILMIYORDU. ESP guc kaybiyla degil de WiFi/broker kopmasiyla sessizlestiyse
            # kendisi hala son `start` komutuyla SURUYOR olabilir (kendi duration'i bitene dek).
            # Bu durumda UI "durdu" gosterirken bobin fiziksel olarak enerjili kalirdi — tam da
            # operatore yanlis guvence veren desen. Broker'a ulasilabiliyorsa STOP yayinla:
            # ESP geri geldiginde retained/yeniden-baglanma ile komutu alir.
            # 2. tur [5.8] (sahip onayi 2026-08-20): publish SONUCU okunur — probe False doner,
            # istisna ATMAZ; eski bildirim broker cokukken de "STOP gonderildi" diyordu (yanlis
            # guvence, 1. turun sahte-"durduruldu" sinifi) ve "log'a dusulur" vaadi bos kaliyordu.
            for cid, snap in changed:
                stop_gitti = False
                try:
                    stop_gitti = bool(
                        _mqtt_publish(
                            f"pemf/coil/{cid}/control",
                            {
                                "command": "stop",
                                "command_id": f"stale_{cid}_{int(time.time() * 1000)}",
                                "reason": "telemetry_stale",
                            },
                        )
                    )
                except Exception:
                    logging.getLogger(__name__).warning(
                        "esp watchdog: bobin %s STOP publish edilemedi", cid, exc_info=True
                    )
                _ws_broadcast_sync({"type": "coil_status", "coilId": cid, "data": snap})
                if stop_gitti:
                    _bildir(lambda d, cid=cid: ceviri.t("bildirim.telemetriYanitYokStop", dil=d, coil=cid), "warning")
                else:
                    logging.getLogger(__name__).warning(
                        "esp watchdog: bobin %s STOP publish DOĞRULANAMADI (broker erişilemez olabilir)", cid
                    )
                    _bildir(lambda d, cid=cid: ceviri.t("bildirim.telemetriYanitYokStopYok", dil=d, coil=cid), "error")
        except Exception:
            _dongu_hatasini_bildir("esp telemetry watchdog error")
        time.sleep(ESP_WATCHDOG_INTERVAL_SEC)


#: Y53 — YALNIZ aşırı sıcaklık adları (overtemp / over_temperature / aşırı sıcaklık / sıcaklık aşımı). ⚠️ 1-E incelemesi
#: (i-11.1): eskiden "temp" ALT DİZESİ yetiyordu → "attempt_failed", "overcurrent_temp", "temp_sensor_fault" TAM acil durdurma
#: yerine yalnız kendi bobinini durduruyordu (ölçüldü). Şüphede durdurma DARALMAZ (Ö.4-Y8): tanınmayan tür TAM acil durdurma.
_Y53_ASIRI_SICAKLIK = re.compile(
    r"(?<![a-z])(over[_\- ]?temp(erature)?|a[sş][iı]r[iı][_\- ]?s[iı]cak(l[iı]k)?|s[iı]cakl[iı]k[_\- ]?a[sş][iı]m[iı])(?![a-z])"
)
#: Başka bir alarm sınıfının izini taşıyan tür (birleşik alarm) → TAM acil durdurma.
_Y53_DIGER_ALARM = ("current", "akim", "akım", "safety", "violation", "guvenlik", "güvenlik", "ihlal")


def _esp_asiri_sicaklik_alarmi_mi(atype) -> bool:
    """Y53: ESP alarm türü YALNIZ aşırı sıcaklık mı (overtemp / over_temperature / aşırı sıcaklık)?"""
    t = str(atype or "").lower()
    if any(k in t for k in _Y53_DIGER_ALARM):
        return False
    return bool(_Y53_ASIRI_SICAKLIK.search(t))


def _y53_yalniz_kendi_bobinini_durdur(coil_id: int, atype: str) -> None:
    """Y53: aşırı sıcaklık alarmı veren ESP kartının YALNIZ kendi bobinine STOP (kapısız, Ö.4-Y8) + görsel uyarı.
    Genel ACİL DURDUR, mandal ve STM bobinlerine dokunulmaz. Bugün ölü yol (alarm yayınlayan firmware yok, ESP kapalı)."""
    logging.getLogger(__name__).error("ESP ALARM bobin %s: %s -> YALNIZ bu bobin durduruluyor (Y53)", coil_id, atype)
    try:
        _teyitsiz = _stop_session_coils([coil_id])
    except Exception:
        logging.getLogger(__name__).exception("Y53: bobin %s STOP basarisiz", coil_id)
        _teyitsiz = [coil_id]
    idx = coil_id - 1
    if 0 <= idx < 8:
        with _live_state_lock:
            _live_state["coils"][idx]["running"] = False
            _snap = dict(_live_state["coils"][idx])
        _ws_broadcast_sync({"type": "coil_status", "coilId": coil_id, "data": _snap})
    _bildir(
        lambda d: (
            ceviri.t("bildirim.asiriSicaklik", dil=d, coil=coil_id, atype=atype)
            + (ceviri.t("bildirim.stopDogrulanamadiEk", dil=d) if _teyitsiz else "")
        ),
        "warning",
    )


def _on_mqtt_message_api(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        is_retained = getattr(msg, "retain", False)

        if msg.topic == "pemf/bridge/status":
            connected = msg.payload.decode("utf-8", errors="ignore").strip() in ("1", "true", "connected")
            with _live_state_lock:
                _live_state["gateway"] = "online" if connected else "offline"
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        if len(topic_parts) >= 3 and topic_parts[1] == "gateway":
            payload = json.loads(msg.payload.decode("utf-8"))
            with _live_state_lock:
                _live_state["gateway"] = payload.get("status", "offline")
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": _live_state["gateway"]}})
            return

        payload = json.loads(msg.payload.decode("utf-8"))

        if len(topic_parts) >= 4 and topic_parts[1] == "coil":
            coil_id_str = topic_parts[2]
            msg_type = topic_parts[3]
            if not coil_id_str.isdigit():
                return
            coil_index = int(coil_id_str) - 1
            if not (0 <= coil_index < 8):
                return
            # ESP watchdog: bu bobinden HERHANGİ gerçek mesaj = canlı → staleness timestamp'ını tazele.
            # (Explicit wifi_disconnected/offline zaten connected=False yapar → watchdog onu atlar.)
            # ⚠️ `not is_retained` ŞART (2026-08-19, HG-4 denetimi): firmware bazı konuları retain=true
            # yayınlıyor (8266 status:235 + iki ESP'nin ack'i). Broker'da kalmış RETAINED bir mesaj,
            # backend her reconnect'inde teslim edilir; onu "canlı telemetri" sayıp damgayı tazelemek,
            # OFFLINE bir bobinin stale-STOP tespitini ESP_STALE_SEC (30 sn) geciktirir. Yalnız CANLI
            # (retain=0) mesaj bobinin gerçekten yayın yaptığını kanıtlar.
            if not is_retained:
                _coil_last_telemetry[coil_index] = time.monotonic()

            # CH4 · Y154: akım sensörü (ESP'de de ACS712) KAPALIYKEN ölçüm yükünün (sensors / status) akım alanları canlı duruma,
            # WS'ye ve sensör CSV'sine GİRMEZ. Alarm / ACK yükleri SÜZÜLMEZ (Ö.4-Y8: "overcurrent" alarmı TAM acil durdurmaya gider).
            if msg_type in ("sensors", "status"):
                payload = akimsiz(payload)

            # YEREL SENSOR KAYDI (sahip karari 2026-09-09: "bilgisayar tarafi" + "her zaman
            # acik"). Buraya takiliyor cunku backend BU KONULARA ZATEN ABONE — yeni abonelik,
            # ekstra ag yuku ve cihaz tarafinda degisiklik GEREKMEZ.
            # ⚠️ `status` DA kaydedilir: S3 hic `sensors` yayinlamaz (UYUMSUZ-6) ve sensor
            # degerlerini `status` icine koyar (telde olculdu) — yalniz `sensors` dinleyen bir
            # kaydedici S3 bobinleri icin BOS dosya uretirdi.
            # ⚠️ RETAINED mesaj kaydedilmez: broker'da kalmis bayat bir yuk, her reconnect'te
            # yeniden teslim edilir ve gecmise SAHTE tekrar satirlari yazardi.
            if not is_retained:
                _sensor_kaydedici.kaydet(coil_id_str, msg_type, payload)

            if msg_type == "sensors" and not is_retained:
                # ⚠️ D1.62 (B-8.12): 8266 ölçüm YOKKEN (sensör takılı değil / hiç sağlıklı okuma yok) alanı `null`
                # yayınlar — eskiden yapıcı sabitini "ölçüldü" diye ya da GEÇERSİZ `nan` yazıyordu. `float(None)` burada
                # iletinin geri kalanını düşürüyordu (bağlantı ve yayın atlanırdı). status dalıyla AYNI kural: okunamayan
                # alan yalnız KENDİNİ düşürür; 0 nöbetçisi yazılmaz (0 "ölçüldü, serin" okunur).
                def _olcum(anahtar):
                    import math as _math

                    try:
                        deger = float(payload[anahtar])
                    except (KeyError, TypeError, ValueError):
                        return None
                    return deger if _math.isfinite(deger) else None

                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    for _anahtar, _alan, _basamak in (
                        ("object_temp", "objectTemp", 1),
                        ("ambient_temp", "ambientTemp", 1),
                        ("current", "currentA", 3),
                        ("magnetic_field", "magneticMt", 2),
                    ):
                        _deger = _olcum(_anahtar)
                        if _deger is not None:
                            coil[_alan] = round(_deger, _basamak)
                    coil["connected"] = True
                    snapshot = dict(coil)
                _ws_broadcast_sync(
                    {"type": "sensor_data", "coilId": int(coil_id_str), "data": snapshot, "timestamp": time.time()}
                )

            elif msg_type == "status" and not is_retained:
                with _live_state_lock:
                    coil = _live_state["coils"][coil_index]
                    # DENETIM 2. TUR [1.2] (2026-08-20): `connected` ESKIDEN yalniz
                    # `payload["status"]` DIZESINDEN turetiliyordu — ama depodaki iki firmware'in
                    # publishStatus'u da `status` alani YAYINLAMAZ (S3 NetworkManager.cpp:604-672,
                    # 8266 :210-226; parite kapisi tests/test_esp_status_sozlesmesi.py bunu
                    # kaynakta kilitler). Sonuc: her CANLI status mesaji connected=False yaziyordu;
                    # S3 hic `sensors` yayinlamadigi icin (UYUMSUZ-6) bobin 6-7 KALICI "baglanti
                    # yok" gorunuyor, panel kontrolleri kilitleniyor ve asagidaki
                    # `_esp_telemetry_watchdog` (yalniz connected=True bobini stale-STOP'lar)
                    # S3 icin HIC calismiyordu. CANLI (retain=0; dal kosulu yukarida) status
                    # mesajinin kendisi cihazin yasadiginin kanitidir → varsayilan connected=True.
                    # ESKI firmware'in ACIK dize sinyali ise korunur ve varsayilani EZER
                    # ("offline" diyen cihaza inat canli denmez — karsit-kanit testiyle kilitli).
                    status = payload.get("status")
                    if status is not None:
                        coil["connected"] = status in ("online", "ready", "running")
                        coil["running"] = status == "running"
                    else:
                        coil["connected"] = True
                    if "frequency" in payload:
                        coil["frequencyHz"] = payload["frequency"]
                    # DENETIM 2. TUR [1.2]: duty uc ayri anahtarla geliyor — eski firmware
                    # `duty_cycle`, 8266 `pwm_duty_cycle`, S3 `pwm_duty`. Yalniz ilki okunuyordu →
                    # firmware'in DURUST efektif duty raporu (D-2) live-state'e ve oradan
                    # dakika-akumulatoru uzerinden DOZ KAYDINA (`pwm_duty_percent`) hic ulasmiyor,
                    # ESP bobinlerinin doz satirlarina duty=0 yaziliyordu.
                    # Oncelik EFEKTIF degerlerde (adversaryal review, 2026-08-20): pwm_* anahtarlari
                    # firmware'in D-2 "durust rapor"udur (kirpma/yuvarlama SONRASI gercek cikis);
                    # `duty_cycle` eski filonun/komutlananin adi. Ikisi birden gelirse efektif kazanir.
                    for _duty_anahtari in ("pwm_duty", "pwm_duty_cycle", "duty_cycle"):
                        if _duty_anahtari in payload:
                            coil["dutyCycle"] = payload[_duty_anahtari]
                            break
                    if "pwm_active" in payload:
                        coil["running"] = bool(payload["pwm_active"])
                    if "pwm_frequency" in payload:
                        coil["frequencyHz"] = payload["pwm_frequency"]

                    # TOLERANSLI sayi donusumu (adversaryal review #3): S3 sicaklik sensoru
                    # arizasinda readObjectTempC NaN doner ve ArduinoJson NaN'i `null` yazar —
                    # dogrudan float(None) TypeError'i TUM mesaj islemeyi yarida kesiyordu
                    # (connected/duty uygulanmis, current/ambient + WS + reconcile ATLANMIS).
                    # Bozuk tek alan yalniz KENDINI dusurur; 0-nobetcisi yazilmaz (bkz.
                    # CoilThermalHonesty: 0 "serin" okunur, null bir olcum DEGILDIR).
                    def _sayi(anahtar):
                        try:
                            return float(payload[anahtar])
                        except (KeyError, TypeError, ValueError):
                            return None

                    _ot = _sayi("object_temp")
                    if _ot is not None:
                        coil["objectTemp"] = round(_ot, 1)
                    _mf = _sayi("magnetic_field")
                    if _mf is not None:
                        coil["magneticMt"] = round(_mf, 2)
                    # DENETIM 2. TUR [1.2](c): S3 sensors mesajini kaldirdi ("UYUMSUZ-6") —
                    # current/ambient S3'te YALNIZ status icinde gelir; okunmazsa doz/KPI 0 gorur.
                    # (sensors dalindaki yuvarlama hassasiyetleriyle birebir ayni.)
                    _cur = _sayi("current")
                    if _cur is not None:
                        coil["currentA"] = round(_cur, 3)
                    _amb = _sayi("ambient_temp")
                    if _amb is not None:
                        coil["ambientTemp"] = round(_amb, 1)
                    snapshot = dict(coil)
                _ws_broadcast_sync({"type": "coil_status", "coilId": int(coil_id_str), "data": snapshot})
                # HG-6 (Plan A-3): hedefli reconcile — ESP "çalışıyor" diyor ama backend niyeti/
                # aktif seans kapsamıyor ise arka planda hedefli STOP (NVS/EEPROM resume + kayıp
                # offline-STOP senaryosu). RETAINED status'a asla tepki verme (8266 status'u
                # retain=true yayınlar; bayat "running" sahte reconcile tetiklemesin).
                if not is_retained:
                    _reconcile_esp_calisiyor(int(coil_id_str), snapshot)

            elif msg_type == "ack":
                # HG-4 (2026-08-19): ESP komut onayı → command_id ile bekleyen E-stop'u çöz.
                # ⚠️ RETAINED FİLTRESİ YOK — bilerek. Firmware ack'i retain=true yayınlar (8266:767 /
                # S3:782). MQTT-3.3.1-9: broker, KURULU bir aboneliğe canlı teslimde retain'i 0'lar →
                # yani canlı ack backend'e retain=0 gelir; retain=1 yalnız reconnect'te broker'ın
                # sakladığı BAYAT ack'te görülür. Bayat ack'e karşı koruma is_retained DEĞİL,
                # command_id BENZERSİZLİĞİdir: her E-stop yeni `estop_{coil}_{ms}` üretir; bayat ack
                # eski id taşır → _resolve_ack onu pending'de BULAMAZ → no-op. (Bu dal telemetri
                # damgasını tazelemez — o koruma yukarıda; ack yalnız pending çözer.)
                _cid = payload.get("command_id")
                if _cid:
                    # A-04 · D1.104: teyit yalnız komutun yayınlandığı bobinin konusundan sayılır (`_resolve_ack`).
                    _resolve_ack(str(_cid), bool(payload.get("success", False)), bobin=int(coil_id_str))

            elif msg_type == "events":
                # D-4 (2026-08-19): RETAINED events YOK SAY. ESP LWT'si (last-will) retain=true
                # yayınlanıyor (S3 + artık 8266). Bobin ANİ koparsa broker LWT'yi CANLI (retain=0,
                # MQTT-3.3.1-9) yayınlar → işlenir; ama backend RECONNECT'inde broker'ın sakladığı
                # BAYAT offline/online retained gelir ve o an online olan bobini "koptu" sanabilir.
                # Canlı durum yalnız retain=0 events'tir (sensor/status telemetrisi zaten connected=True yapar).
                if is_retained:
                    return
                event_type = payload.get("type") or payload.get("event_type", "unknown")
                # D-1 tamamlayıcısı (review, 2026-08-19 akşam): firmware selftest_ok/fail/skipped
                # event'leri yayınlıyor ama backend İŞLEMİYORDU → selftest endpoint'i koşulsuz
                # "success" döndüğünden ARIZALI bobin operatöre YEŞİL görünüyordu (yanlış tanısal
                # güvence — D-1'in düzelttiği şeyin zincirin öbür ucunda devamı).
                if event_type in ("selftest_ok", "selftest_fail", "selftest_skipped"):
                    _st_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    if event_type == "selftest_fail":
                        logging.error("SELFTEST BAŞARISIZ bobin %s: %s", coil_id_str, _st_msg)
                        _bildir(
                            lambda d: ceviri.t("bildirim.selfTestBasarisiz", dil=d, coil=coil_id_str, ayrinti=_st_msg),
                            "error",
                        )
                    else:
                        logging.info("selftest bobin %s: %s (%s)", coil_id_str, event_type, _st_msg)
                        _bildir(
                            lambda d: (
                                ceviri.t("bildirim.selfTestGecti", dil=d, coil=coil_id_str)
                                if event_type == "selftest_ok"
                                else ceviri.t("bildirim.selfTestAtlandi", dil=d, coil=coil_id_str)
                            ),
                            "success" if event_type == "selftest_ok" else "info",
                        )
                    _ws_broadcast_sync(
                        {
                            "type": "selftest_result",
                            "coilId": int(coil_id_str),
                            "data": {"result": event_type, "message": _st_msg},
                        }
                    )
                    return
                # DENETIM 2. TUR [4.2] (2026-08-20): iki firmware de yerel TERMAL korumada event
                # yayinliyor (S3 .ino:80 thermal_stop; 8266 .ino:361/368/493 stop+unlock+lock) ama
                # backend bunlari ISLEMIYORDU → cihazin en onemli yerel guvenlik eylemi operatore
                # gorunmuyordu: bobin "sebepsiz durdu" sanilir, termal kilit surerken start redleri
                # aciklamasiz kalirdi (D-1 selftest duzeltmesinin zincirin obur ucundaki ikizi).
                # RETAINED filtresi yukarida (bayat termal olay reconnect'te alarm uretmez).
                # Ad paritesi firmware kaynagiyla kilitli: tests/test_termal_olay_gorunurlugu.py
                if event_type in ("thermal_stop", "thermal_lock", "thermal_unlock"):
                    _termal_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    _ayr = f" ({_termal_msg})" if _termal_msg else ""
                    if event_type == "thermal_stop":
                        logging.error("YEREL TERMAL KESME bobin %s: %s", coil_id_str, _termal_msg)
                        _bildir(
                            lambda d: ceviri.t("bildirim.termalKesme", dil=d, coil=coil_id_str, ayrinti=_ayr), "error"
                        )
                    elif event_type == "thermal_lock":
                        _bildir(
                            lambda d: ceviri.t("bildirim.termalKilit", dil=d, coil=coil_id_str, ayrinti=_ayr), "warning"
                        )
                    else:
                        _bildir(lambda d: ceviri.t("bildirim.termalSogudu", dil=d, coil=coil_id_str), "success")
                    _ws_broadcast_sync(
                        {
                            "type": "thermal_event",
                            "coilId": int(coil_id_str),
                            "data": {"event": event_type, "message": _termal_msg},
                        }
                    )
                    return
                # [4.5] NACK YARISI (2026-08-22): iki firmware de komut reddinde `command_error`
                # eventi yayinliyor (8266 .ino:458 rate-limit / :527 validation / :605 unknown;
                # her red ayrica ack success=false gonderir) ama backend bu tipi HIC islemiyordu →
                # ESP'nin acik reddi ve SEBEBI operatore gorunmuyordu. Kosu-kaydi duzeltmesi ack
                # bekcisinde ( _start_ack_watch ) — bu dal yalniz GORUNURLUK: bildirim + WS.
                # RETAINED filtresi yukarida (bayat red reconnect'te alarm uretmez).
                if event_type == "command_error":
                    _ce_msg = str(payload.get("message") or payload.get("detail") or "")[:160]
                    logging.error("Bobin %s KOMUTU REDDETTI (NACK): %s", coil_id_str, _ce_msg)

                    def _ce_sebep(d):
                        return _ce_msg or ceviri.t("bildirim.sebepYok", dil=d)

                    _bildir(
                        lambda d: ceviri.t("bildirim.komutReddetti", dil=d, coil=coil_id_str, sebep=_ce_sebep(d)),
                        "error",
                    )
                    _ws_broadcast_sync(
                        {
                            "type": "command_error",
                            "coilId": int(coil_id_str),
                            "data": {"message": _ce_msg},
                        }
                    )
                    return
                if event_type in ("wifi_disconnected", "offline"):
                    # SAHA ARIZASI 2026-09-10 (sahip bildirimi): "Bobin N baglantisi kesildi"
                    # bildirimi DUSUYOR ama bobin karti "Hazır" kaliyordu. Kok neden: bu dal
                    # sunucu durumunu guncelliyor ve bildirim atiyor ama `coil_status` WS
                    # YAYINI YAPMIYORDU. Istemci `connected` alanini yalnizca WS anlik
                    # goruntusunden ya da `coil_status` olayindan ogrenir; "Hazır" etiketi
                    # dogrudan o alandan gelir (apps/ui/src/components/domain/CoilParameterPanel.tsx
                    # ve CoilCard.tsx: running ? "Aktif" : connected ? "Hazır" : "Offline").
                    # ⚠️ `_esp_telemetry_watchdog` bunu KURTARAMAZ: onun kosulu
                    # `coil.get("connected")` ve bu dal onu ZATEN False yapmis oluyor →
                    # bekci bobini atliyor, dolayisiyla yayin HIC gitmiyordu. Arayuz ancak
                    # tam yeniden baglanmada (yeni snapshot) kendini duzeltiyordu.
                    # Anlik goruntu KILIT ICINDE alinir, yayin kilit DISINDA yapilir
                    # (bekci deseninin aynisi).
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = False
                        _live_state["coils"][coil_index]["running"] = False
                        _snap = dict(_live_state["coils"][coil_index])
                    _ws_broadcast_sync({"type": "coil_status", "coilId": int(coil_id_str), "data": _snap})
                    _bildir(lambda d: ceviri.t("bildirim.bobinKesildi", dil=d, coil=coil_id_str), "warning")
                elif event_type == "wifi_connected":
                    # AYNI ARIZANIN AYNASI: yayin olmadan istemci "Offline" da asili kalirdi
                    # (bobin geri geldiginde kart guncellenmiyordu).
                    with _live_state_lock:
                        _live_state["coils"][coil_index]["connected"] = True
                        _snap = dict(_live_state["coils"][coil_index])
                    _ws_broadcast_sync({"type": "coil_status", "coilId": int(coil_id_str), "data": _snap})
                    _bildir(lambda d: ceviri.t("bildirim.bobinBaglandi", dil=d, coil=coil_id_str), "success")

            elif msg_type == "alarm":
                # ESP firmware'inin KENDİ güvenlik alarmı (overtemp / safety_violation / overcurrent).
                # Backend eşik dayatmaz; donanım "tehlikedeyim" dediğinde TÜM bobinleri durdurur.
                #
                # DENETIM P3: RETAINED filtresi yoktu. Broker'da kalmis ESKI bir retained alarm,
                # her MQTT yeniden-baglanmasinda (broker restart / ag dalgalanmasi) yeniden teslim
                # edilip acil-durdurma tetikliyordu → suren tedavi durdurulur, operator sebebi
                # goremez ("hayalet alarm"). Sensor dalinda (yukarida) `not is_retained` kosulu
                # ZATEN vardi; alarm dali unutulmustu. Retained mesaj GECMISTEKI bir durumdur,
                # CANLI bir tehlike bildirimi degil → yok say ama GORUNUR logla (fail-safe yon
                # kaybi yok: gercek/canli alarm retain'siz gelir).
                if is_retained:
                    logging.warning(
                        "ESP bobin %s icin RETAINED alarm alindi → acil-durdurma TETIKLENMEDI "
                        "(broker'da kalmis eski mesaj; canli alarm retain'siz gelir).",
                        coil_id_str,
                    )
                    return
                atype = payload.get("type") or payload.get("alarm") or payload.get("reason") or "alarm"
                # ⚠️ Y53 (sahip): ESP'nin "aşırı sıcaklık" alarmı YALNIZ kendi kartının bobinini durdurur ve uyarır; bobin
                # 1–7 SÜRER, genel ACİL DURDUR ve mandal KURULMAZ (A-47: bobin 1–7'de termal durdurma yok; Y40: kartın kendi
                # 100 °C kesmesi kalır). Diğer alarm türleri (overcurrent / safety_violation) aşağıda TAM acil durdurma.
                if _esp_asiri_sicaklik_alarmi_mi(atype):
                    _y53_yalniz_kendi_bobinini_durdur(int(coil_id_str), str(atype))
                    return
                logging.error("ESP ALARM bobin %s: %s -> tum bobinler durduruluyor", coil_id_str, atype)
                _bildir(lambda d: ceviri.t("bildirim.bobinAlarm", dil=d, coil=coil_id_str, atype=atype), "error")
                try:
                    _emergency_stop_async(reason=f"esp_alarm_{coil_id_str}_{atype}", mode="ESP Güvenlik Alarmı")
                except Exception:
                    logging.exception("ESP alarm STOP failed")

    except Exception as _e:
        # Audit #23: eskiden 'except: pass' ile sessizce yutuluyordu → bozuk/beklenmedik MQTT
        # mesajları (örn. coil status güncellenememesi) görünmezdi. Artık WARN'la (özet, traceback'siz).
        logging.getLogger(__name__).warning("MQTT on_message islenemedi (topic=%s): %s", getattr(msg, "topic", "?"), _e)


# ── MQTT istemci kimligi ─────────────────────────────────────────────────────
# MQTT sozlesmesi geregi AYNI client_id ile yeni bir baglanti gelirse broker ONCEKI oturumu
# DUSURUR. Sabit kimlikler ("api_server_ws_listener" / "api_server_pub") iki gercek arizaya
# yol aciyordu:
#
#   1) DINLEYICI — yeniden baslatma/OTA penceresinde eski surecin oturumu brokerde bir sure
#      yasar: yeni surec baglanir → eski dusurulur → eski otomatik yeniden baglanir → yeni
#      dusurulur... Sonuc: bitmeyen "Sistem baglantisi kesildi/kuruldu" bildirimi ve o sure
#      boyunca ESP telemetrisinde bosluk. (E2E 2026-08-06'da iki backend ile gozlendi.)
#
#   2) YAYINCI — _mqtt_publish HER cagride yeni istemci acar ve _emergency_stop_all, ESP
#      bobinlerine ThreadPoolExecutor ile PARALEL yayin yapar (bobin basina 2 publish).
#      Ucu de ayni kimligi kullandigindan broker sonuncu disindakileri DUSURUR → acil-durdurma
#      STOP komutu KAYBOLABILIR. Bu bir HASTA GUVENLIGI yolu: kimlik cagri basina benzersiz olmali.
#
# Kimlik <=23 karakterde tutulur (MQTT 3.1 doneminden kalma brokerlarin client_id siniri).
_MQTT_PUB_SEQ = _itertools.count(1)


def _mqtt_client_id(role: str) -> str:
    """Surece ozgu (yayinci ve bulut-aynasi icin cagriya da ozgu) MQTT client_id."""
    if role == "pub":
        return f"pemf_pub_{os.getpid()}_{next(_MQTT_PUB_SEQ) % 100000}"
    if role == "estop-cloud":
        # ── [3.3] 2. tur denetimi (duzeltme 2026-08-22) ──────────────────────────────
        # Bu rol eskiden asagidaki genel `pemf_{role}_{pid}` kalibina dusuyordu. Iki ariza:
        #   1) SUREC-SABIT: E-stop cifte tetiginde (panik aninda gercekci) iki ayna oturumu
        #      HiveMQ'ya AYNI kimlikle baglanir → broker ILKINI DUSURUR → ucustaki STOP
        #      publish'leri kaybolabilir. 'pub' rolunde cozulen arizanin birebir aynisi,
        #      yalniz BULUT yolunda.
        #   2) UZUNLUK: "pemf_estop-cloud_" = 17 karakter; Linux pid_max=4194304 (7 hane)
        #      ile kimlik 24'e tasar → eski brokerlarin 23-karakter siniri asilir,
        #      baglanti REDDEDILIR ve ayna SESSIZCE hic calismaz.
        # Kisa rol adi ("esc") + pid%100000 + cagri sayaci: en kotu durumda
        # 9 + 5 + 1 + 5 = 20 <= 23. Sayac 'pub' ile paylasilir — amac benzersizlik,
        # kaynak farki degil. Kilit: tests/test_mqtt_client_id.py [3.3] bolumu.
        return f"pemf_esc_{os.getpid() % 100000}_{next(_MQTT_PUB_SEQ) % 100000}"
    return f"pemf_{role}_{os.getpid()}"


#: O-3.1: yerel broker adresi — dinleyici istemci ve kimlik sondası AYNI broker'a bakar.
_YEREL_BROKER = ("127.0.0.1", 1883)
#: O-3.1: broker MosquittoSupervisor'la GEÇ açılabilir → sonda ölçülene dek dener (arka planda; açılışı bekletmez).
_SONDA_DENEME = 15
_SONDA_ARALIK_S = 2.0
#: Sondayı kesen olay (süreç kapanışı / test yıkımı): kurulunca bekleme biter ve sonuç GÜNLÜĞE YAZILMAZ.
_sonda_dur = threading.Event()


def _broker_kimlik_sondasi() -> bool | None:
    """A-04 · D1.104 · O-3.1: "broker KİMLİKSİZ" uyarısı DOSYAYA (`hazirlandi_mi`) değil ÇALIŞAN broker'ın gerçek
    yapılandırmasına bağlı — kullanıcı adı olmayan CONNECT'in CONNACK'i (`mqtt_kimlik.broker_anonim_kabul_ediyor_mu`).
    Anonim kabul ediliyorsa LAN'daki bir istemci sahte ack ile E-stop onayını taklit edebilir (D-2.1). Bağlantı KESİLMEZ
    (STOP yolu korunur); yalnız açıkça günlüğe yazılır. Dosya kontrolü iki hâli kaçırıyordu: hazırladıktan sonra broker
    yeniden başlayana dek ve çalışma kopyası yazılamayınca broker anonimdi, uyarı YOKTU; hazırlanmamış sistemde broker
    kimlik isterse de "anonim" diyordu (asıl sorun: backend BAĞLANAMAZ)."""
    from utils import mqtt_kimlik as _mk

    host, port = _YEREL_BROKER
    sonuc = None
    for _ in range(max(1, int(_SONDA_DENEME))):
        sonuc = _mk.broker_anonim_kabul_ediyor_mu(host, port)
        if sonuc is not None or _sonda_dur.wait(_SONDA_ARALIK_S):
            break
    if _sonda_dur.is_set():
        return sonuc
    hazir = _mk.hazirlandi_mi()
    if sonuc is True:
        logging.warning(
            "A-04: ESP etkin ama yerel MQTT broker KIMLIKSIZ (anonim baglanti KABUL EDILDI - olculdu) - sahte ack E-stop "
            "onayini taklit edebilir. "
            + (
                "Kimlik HAZIRLANMIS ama calisan broker onu kullanmiyor: PEMF uygulamasini bobinler durmusken kapatip "
                "acin (servis kurulumu: Restart-Service mosquitto)."
                if hazir
                else "ESP donus listesi: 'PEMF_Backend.exe --mqtt-kimlik hazirla' + broker yeniden baslatma + ESP yakma."
            )
        )
    elif sonuc is False and not hazir:
        # H-8.2 (1-H incelemesi): backend kimliği `_mqtt_credentials` önceliğiyle seçilir — A-04 kimliği yoksa operatörün
        # `mqtt_user/mqtt_pass` sırrı. Sonda yalnız broker'ın kimlik İSTEDİĞİNİ ölçer; operatör kimliği varken
        # "BAGLANAMAZ" ölçülmemiş bir sonuçtu (bağlantının sonucu paho istemcisinin günlüğündedir).
        _op_kullanici, _op_parola = _mqtt_credentials()
        if _op_kullanici and _op_parola:
            logging.warning(
                "A-04: yerel MQTT broker KIMLIK istiyor; A-04 kimligi HAZIRLANMAMIS - backend OPERATOR kimligiyle "
                "(mqtt_user) baglanmayi dener; broker reddederse ESP telemetrisi ve ESP STOP yolu KAPALI (sonuc MQTT "
                "baglanti gunlugunde). 'PEMF_Backend.exe --mqtt-kimlik hazirla' (ESP donus listesi)."
            )
        else:
            logging.warning(
                "A-04: yerel MQTT broker KIMLIK istiyor ama backend kimligi HAZIRLANMAMIS - backend broker'a BAGLANAMAZ "
                "(ESP telemetrisi ve ESP STOP yolu kapali). 'PEMF_Backend.exe --mqtt-kimlik hazirla' (ESP donus listesi)."
            )
    elif sonuc is None:
        logging.warning(
            "A-04: yerel MQTT broker'in kimlik durumu OLCULEMEDI (%s:%s yanit vermedi) - KIMLIKSIZ olup olmadigi bilinmiyor.",
            host,
            port,
        )
    return sonuc


def _start_mqtt_for_api() -> None:
    global _mqtt_client_api
    # ⚠️ ESP SÖKÜLÜ → MQTT'YE HİÇ BAĞLANMA (sahip kararı 2026-09-11).
    # Broker yokken `connect_async` + `loop_start` sonsuza dek yeniden dener; her deneme
    # log'a satır basar, "Sistem" rozetini sarıya çeker ve kurulu OLMAYAN bir alt sistem
    # için kalıcı alarm üretir. Kod SİLİNMEDİ: `PEMF_ESP_ENABLED=1` ile tamamı geri gelir
    # (bkz. live_state.esp_etkin notu — hibrit/ESP-only kuruluma dönüş tek satırlık ayardır).
    if not live_state.esp_etkin():
        logging.info("MQTT dinleyicisi ATLANDI — ESP alt sistemi kapalı (PEMF_ESP_ENABLED=1 ile açılır).")
        return
    # A-04 · D1.104 · O-3.1: kimlik durumu ÇALIŞAN broker'dan ölçülür (arka planda; bkz. _broker_kimlik_sondasi).
    threading.Thread(target=_broker_kimlik_sondasi, name="BrokerKimlikSondasi", daemon=True).start()
    try:
        import paho.mqtt.client as _mqtt

        # ⚠️ BİLEREK VERSION1 (2026-08-15) — yayıncı istemci V2'ye geçti, bu GEÇMEDİ.
        # Sebep: bu istemcinin ÜÇ geri çağrısı var (`on_connect`/`on_disconnect`/`on_message`) ve
        # V2 imzaları değiştirir (`rc` → `reason_code` + `properties`). Bu geri çağrılar ESP
        # telemetrisi ve ACİL DURDURMA yolundadır ve HİÇBİR TESTLE KAPSANMIYOR. Test kapsamı
        # olmayan bir güvenlik yolunda imza değiştirmek, doğrulanmamış risktir; sessizce
        # bozulursa bunu ancak sahada fark ederiz.
        # Sürümü AÇIKÇA vermek uyarıyı susturur ve davranışı DEĞİŞTİRMEZ.
        # ⚠️ KALICI ÇÖZÜM DEĞİLDİR: paho V1'i eninde sonunda kaldıracak. Geçiş için önce bu üç
        # geri çağrıya test yazılmalı (özellikle `_on_mqtt_message_api` → bobin telemetrisi),
        # sonra imzalar V2'ye çevrilmeli.
        _mqtt_client_api = _mqtt.Client(
            _mqtt.CallbackAPIVersion.VERSION1, client_id=_mqtt_client_id("ws"), clean_session=True
        )
        _u, _pw = _mqtt_credentials()
        if _u:
            _mqtt_client_api.username_pw_set(_u, _pw)  # broker auth açıksa kimlik gönder
        _mqtt_client_api.on_connect = _on_mqtt_connect_api
        _mqtt_client_api.on_disconnect = _on_mqtt_disconnect_api
        _mqtt_client_api.on_message = _on_mqtt_message_api
        # Async connect + loop: broker GEÇ açılırsa da otomatik yeniden dener. Eskiden ilk connect
        # başarısız olunca listener kalıcı ölüydü → ESP telemetrisi WS'e hiç ulaşmazdı.
        _mqtt_client_api.reconnect_delay_set(min_delay=2, max_delay=30)
        _mqtt_client_api.connect_async(_YEREL_BROKER[0], _YEREL_BROKER[1], 60)
        _mqtt_client_api.loop_start()
    except Exception as e:
        logging.warning(f"MQTT dinleyici başlatılamadı: {e}")


# B-2.2: _build_ws_snapshot + update_live_stm_status/coil_from_stm/session_state → servers/live_state.py (üstte alias'landı).


_event_bus_registered = False


def _stm_cevrimici_iyilestir() -> None:
    """D1.74: gerçek bir STM ACK'i geldiğinde canlı durum, ÇEKİRDEĞİN bağlantı gerçeğinden iyileşir.

    `update_live_coil_from_stm` artık STM'i "online" yazmıyor (sentetik yayınlar başlatma kapısını açıyordu). Ama
    açılışta çekirdek kartla `hardware.stm.connected` olayı api işleyicileri kaydolmadan el sıkışırsa olay kaçar; eskiden
    bunu her STM_OK örtüyordu. Ölçüt `core.stm_is_connected`dır (yalnız gerçek STM_READY/STM_OK ve kopuş yazar) ve
    çekirdeğin durum kilidi ALTINDA okunur: bağlantı geçişleri aynı kilitte yayınlandığından araya giren bir kopuş
    "online" ile ezilemez. Çekirdek bağlı değilse hiçbir şey yazılmaz."""
    core = getattr(state, "core", None)
    kilit = getattr(core, "_stm_state_lock", None)
    if core is None or kilit is None:
        return
    with kilit:
        if not getattr(core, "stm_is_connected", False):
            return
        with _live_state_lock:
            zaten = _live_state["stm"] == "online"
        if not zaten:
            logging.warning("STM canli durumu cekirdekle esitlendi (kacirilan baglanti olayi): online")
            update_live_stm_status(True)


def _herhangi_bobin_calisiyor() -> bool:
    """Y45: kopma / watchdog ANINDA herhangi bir bobin çalışıyor mu (seans olsun olmasın, elle başlatılmış dahil)?

    Ölçüt: HardwareController'ın KOMUT durumu (STM bobinleri; ACK gelmeden önce de "sürülüyor") VEYA canlı durum (ACK /
    telemetri; ESP slotu dahil). Durum SIFIRLANMADAN önce okunmalı (`on_disconnect` / `stop_all_coils` / kopuşun canlı
    durumu `running:false` yapması). ⚠️ Okunamazsa ÇALIŞIYOR sayılır (fail-safe: yanlış mandal yalnız bir Sıfırla
    maliyeti; kaçan mandal Y4'ü deler)."""
    try:
        _hc_durum = getattr(state.hardware, "coils_state", None) or {}
        if any(bool((v or {}).get("is_running")) for v in _hc_durum.values()):
            return True
        with _live_state_lock:
            return any(bool(c.get("running")) for c in _live_state["coils"].values())
    except Exception:
        logging.getLogger(__name__).exception("Y45: calisan bobin durumu okunamadi -> CALISIYOR sayildi (mandal)")
        return True


def _durdurma_aninda_calisiyor_mu(seans_aktifti: bool):
    """Y227 (BE 2b): durdurma ANINDA bobin / seans var mıydı — True / False / None (okunamadı). Teyit iletisine ve yanıta yazılır;
    istemci "ACİL DURDUR (teyitsiz)" düğmesini yalnız False DEĞİLKEN tutar. ⚠️ HİÇBİR ŞEY BEKLEMEZ (Ö.4-Y8): `_emergency_stop_all`
    STOP'tan ÖNCE çağırır — canlı durum kilidi o an meşgulse beklemek yerine None (bilinmiyor → düğme kalır, güvenli taraf).
    Ölçüt `_herhangi_bobin_calisiyor` ile aynı (HardwareController komut durumu VEYA canlı durum)."""
    if seans_aktifti:
        return True
    try:
        _hc_durum = getattr(state.hardware, "coils_state", None) or {}
        if any(bool((v or {}).get("is_running")) for v in _hc_durum.values()):
            return True
        if not _live_state_lock.acquire(blocking=False):
            return None
        try:
            return any(bool(c.get("running")) for c in _live_state["coils"].values())
        finally:
            _live_state_lock.release()
    except Exception:
        logging.getLogger(__name__).warning(
            "Y227: durdurma anindaki bobin durumu okunamadi -> bilinmiyor", exc_info=True
        )
        return None


def _y45_mandal_kur(neden: str) -> bool:
    """Y45 (sahip, 1-C §9 S1): kopma / watchdog anında bobin çalışıyorsa ACİL DURDUR MANDALI — STOP'tan ÖNCE, kapısız.
    Aktif STM seansında `_emergency_stop_all` zaten kurar; bu yol SEANSSIZ (elle) sürüşü kapsar. Boştayken KURULMAZ
    (kartın çıkıp takılması). Kurmak bir bayrak + sayaç: hiçbir STOP'u bekletmez; hata olsa da STOP yolu sürer (Ö.4-Y8).
    @return mandal bu çağrıyla kuruldu mu."""
    try:
        if not _herhangi_bobin_calisiyor():
            return False
        estop_mandali.mandalla(neden)
        return True
    except Exception:
        logging.getLogger(__name__).exception("Y45: mandal kurulamadi (durdurma SURUYOR)")
        return False


def _y45_mandal_sonrasi(neden: str) -> None:
    """STOP'lar gönderildikten SONRA: diske yaz (Y46, arka planda), arayüze yayınla, operatöre söyle."""
    try:
        estop_mandali.diske_yaz_arka_planda()
        _ws_broadcast_sync({"type": "estop_mandali", "data": estop_mandali.durum()})
        _bildir(
            lambda d: (
                ceviri.t("bildirim.mandalStmKopma", dil=d)
                if neden == "stm_disconnected"
                else ceviri.t("bildirim.mandalStmWatchdog", dil=d)
            ),
            "error",
        )
    except Exception:
        logging.getLogger(__name__).exception("Y45: mandal bildirimi yapilamadi")


def _handle_backend_event(event) -> None:
    """Route core EventBus events into FastAPI live-state/WebSocket."""
    data = event.data or {}
    if event.event_type == "hardware.stm.connected":
        _akim_guvenilmez_bildirildi.clear()  # TD5: yeni bağlantı (kart değişmiş / yakılmış olabilir) → uyarı yeniden hak eder
        update_live_stm_status(True)
        return
    if event.event_type == "hardware.stm.disconnected":
        # ⚠️ Y45: çalışan bobin bilgisi canlı durum ve HC SIFIRLANMADAN önce okunur; mandal STOP'tan ÖNCE kurulur.
        _y45_mandal = _y45_mandal_kur("stm_disconnected")
        update_live_stm_status(False)
        # GÜVENLİK: STM koptu → bobin durumunu sıfırla (reconnect'te eski freq/duty ile RE-FIRE
        # etmesin) + STM kullanan aktif seansı durdur (kontrolsüz bobin kalmasın).
        try:
            if state.hardware:
                state.hardware.on_disconnect()
        except Exception:
            logging.exception("STM on_disconnect failed")
        if _y45_mandal:
            _y45_mandal_sonrasi("stm_disconnected")
        with _session_lock:
            _sess_active = bool(_active_session.get("is_active"))
            _sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
        if _sess_active and any(c in STM_COIL_IDS for c in _sess_coils):
            logging.error("STM baglanti kaybi: STM kullanan aktif seans durduruluyor (guvenlik).")
            _bildir(lambda d: ceviri.t("bildirim.stmKoptuSeansDurdu", dil=d), "error")
            try:
                _emergency_stop_async(reason="stm_disconnected", mode="STM Bağlantı Kaybı")
            except Exception:
                logging.exception("STM disconnect STOP failed")
        return
    if event.event_type == "hardware.stm.coil_update":
        _sentetik = bool(data.get("sentetik"))
        if not _sentetik:
            # ⚠️ KART KOMUTU KABUL ETTİ: `STM_OK` ayrıştırıldı → "sistematik red" sayacı sıfırlanır.
            # Sıfırlama olmadan, eski bir gürültü NACK'i seans başlatmayı sonsuza dek engellerdi.
            # ⚠️ D1.74: firmware watchdog'unun SENTETİK sıfırlama yayını kabul DEĞİLDİR (kararı silmez).
            live_state.stm_komut_kabulu_bildir()
            _stm_cevrimici_iyilestir()
        update_live_coil_from_stm(
            coil_id=int(data.get("coil_id", 0)),
            duty=float(data.get("duty", data.get("duty_cycle", 0.0))),
            freq=float(data.get("freq", data.get("frequency", 0.0))),
            phase=float(data.get("phase", 0.0)),
            duration_min=int(data.get("duration_min", data.get("duration", 0))),
            running=bool(data.get("running", data.get("pwm_active", False))),
        )
        # SÜRÜŞ KİPİ — yalnız firmware bildirdiyse (`K=` alanı) yazılır. Anahtar YOKSA
        # (eski firmware) alana DOKUNULMAZ: False yazmak "bipolar doğrulandı" yalanı olur.
        if "unipolar" in data:
            update_live_coil_kip(int(data.get("coil_id", 0)), bool(data["unipolar"]))
        # Y69: ETKİN duty — aynı kural: yalnız kart bildirdiyse (`E=`) yazılır; anahtar YOKSA dokunulmaz (0 yazmak
        # "sürülmüyor" yalanı olur).
        if "duty_etkin" in data:
            live_state.update_live_coil_etkin_duty(int(data.get("coil_id", 0)), float(data["duty_etkin"]))
        return
    if event.event_type == "hardware.stm.telemetry":
        # FAZ 3 (2026-09-10): bobin 6-7 sensorleri ESP'den STM'e tasindi. ESP yolundaki
        # `sensor_data` SOZLESMESI BIREBIR KORUNUR → istemci ve DB verinin nereden geldigini
        # BILMEZ (CoilParameterPanel/sensor kaydedici degismedi).
        #
        # ⚠️ `_coil_last_telemetry` DAMGASI ZORUNLU: dakika-ortalamasi dongusu
        # (bkz. ~satir 3291) damgasi olmayan bobin icin DB satiri URETMEZ. Damga olmadan
        # sicaklik arayuzde gorunur ama gecmis/PDF/KPI'de HIC yer almaz.
        #
        # ⚠️ EKSIK ALAN YAZILMAZ: `object_temp` gelmediyse alana DOKUNULMAZ (0.0 yazmak
        # "olculdu" gibi kaydedilir — gecmiste PDF'e "0.0 °C olculdu" yazdiran desen).
        try:
            _t_coil_id = int(data.get("coil_id", 0))
        except (TypeError, ValueError):
            return
        _t_idx = _t_coil_id - 1
        if not (0 <= _t_idx < 8):
            return
        # CH4 · Y154: akım sensörü KAPALIYKEN (varsayılan) ayrıştırıcıyı atlayan üreticinin (eski olay biçimi / simülatör) akım
        # alanları da burada atılır → canlı durum / WS / sensör kaydı / bildirim akım görmez. Açıkken TD5 kuralı aşağıda aynen.
        data = akimsiz(data)
        # TD5: ayrıştırıcıyı atlayan üretici (ör. eski olay biçimi) için de AYNI kural — güvenilmez akım YAZILMAZ.
        if "current" in data and _akim_guvenilmez_mi(data):
            data = {k: v for k, v in data.items() if k != "current"}
            data["akim_guvenilmez"] = True
        # ⚠️ ALAN BAZINDA KAYIT — SAHTE OLCUM SINIFININ IKINCI DALGASI.
        #
        # 2026-09-10'da bobin 1-5'e ACS712 eklendi ve o bobinler ARTIK telemetri
        # gonderiyor (yalniz akim). Bobin bazinda `_coil_last_telemetry` damgasi tek
        # basina YETMEZ: damga atilinca dakika-ortalamasi dongusu o bobinin
        # `objectTemp`/`magneticMt` alanlarini da biriktirmeye baslar ve baslangic
        # degeri 0.0 oldugu icin DB'ye "0.0 °C olculdu, sample_count=30" yazar —
        # tam olarak PDF'e "0.0 °C olculdu" yazdiran eski ariza.
        #
        # Cozum: HANGI ALANIN gercekten olculdugunu kaydet. Akumulator yalniz bu
        # kumedeki alanlari biriktirir; arayuz de olculmeyeni kisa cizgi (—) gosterir.
        _t_alanlar = {
            "object_temp": ("objectTemp", 1),
            "ambient_temp": ("ambientTemp", 1),
            "magnetic_field": ("magneticMt", 3),
            "current": ("currentA", 3),
        }
        _t_yazildi = False
        _t_simdi = time.monotonic()
        with _live_state_lock:
            _t_coil = _live_state["coils"][_t_idx]
            _t_damga = _coil_olculen_alanlar.setdefault(_t_idx, {})
            for _kaynak, (_hedef, _basamak) in _t_alanlar.items():
                if _kaynak not in data:
                    continue
                _t_coil[_hedef] = round(float(data[_kaynak]), _basamak)
                _t_damga[_hedef] = _t_simdi
                _t_yazildi = True
            # TD2 (tezgâh · K6): alan ayarı doğrulanmamış firmware'in `B=`'si ayrıştırıcıda atıldı → değer YAZILMADI; arayüz
            # "Alan sensörü doğrulanamadı — ölçülen değer gösterilmiyor" der. Doğrulanmış alan gelince bayrak iner.
            _t_alan_onceki = bool(_t_coil.get("alanDogrulanamadi"))
            if data.get("alan_dogrulanamadi"):
                _t_coil["alanDogrulanamadi"] = True
                # Önceki (doğrulanmış) alanın damgası da düşer → `measuredFields` / dakika ortalaması onu taze SAYMAZ.
                if _t_damga.pop("magneticMt", None) is not None:
                    _t_coil["measuredFields"] = sorted(_taze_alanlar_locked(_t_idx, _t_simdi))
            elif "magnetic_field" in data:
                _t_coil["alanDogrulanamadi"] = False
            _t_alan_degisti = _t_alan_onceki != bool(_t_coil.get("alanDogrulanamadi"))
            # TD5: güvenilmez akım YAZILMADI (ayrıştırıcı attı); önceki güvenilir değerin tazelik damgası da düşer → `measuredFields`
            # / dakika ortalaması (doz kaydı) onu taze saymaz. Güvenilir akım gelince bayrak iner.
            _t_akim_onceki = bool(_t_coil.get("akimGuvenilmez"))
            if data.get("akim_guvenilmez"):
                _t_coil["akimGuvenilmez"] = True
                if _t_damga.pop("currentA", None) is not None:
                    _t_coil["measuredFields"] = sorted(_taze_alanlar_locked(_t_idx, _t_simdi))
            elif "current" in data:
                _t_coil["akimGuvenilmez"] = False
            _t_akim_degisti = _t_akim_onceki != bool(_t_coil.get("akimGuvenilmez"))
            # Y285: MLX bekçisi (headless_core `_mlx_bekci_tikla`) — `B=` eşik süresince gelmedi → sensör DÜŞTÜ; `B=` (doğrulanmamışı
            # da) gelince bayrak iner ve "yeniden bağlandı" bildirilir. Bildirim yalnız GEÇİŞTE (tekrar eden olay yeniden uyarmaz).
            _t_kayip_onceki = bool(_t_coil.get("alanKayip"))
            if data.get("alan_kayip"):
                _t_coil["alanKayip"] = True
            elif "magnetic_field" in data or data.get("alan_dogrulanamadi"):
                _t_coil["alanKayip"] = False
            _t_kayip_degisti = _t_kayip_onceki != bool(_t_coil.get("alanKayip"))
            if _t_yazildi:
                # D1.67: liste = TAZE alanlar (bu satirda gelmeyen ama pencere icindekiler dahil).
                _t_coil["measuredFields"] = sorted(_taze_alanlar_locked(_t_idx, _t_simdi))
            _t_snap = dict(_t_coil)
        if _t_alan_degisti or _t_akim_degisti or _t_kayip_degisti:
            _ws_broadcast_sync({"type": "coil_status", "coilId": _t_coil_id, "data": _t_snap})
        if _t_kayip_degisti:
            if _t_snap.get("alanKayip"):
                _bildir(lambda d: ceviri.t("bildirim.mlxDustu", dil=d, coil=_t_coil_id), "warning")
            else:
                _bildir(lambda d: ceviri.t("bildirim.mlxGeriGeldi", dil=d, coil=_t_coil_id), "info")
        if data.get("akim_guvenilmez") and _t_idx not in _akim_guvenilmez_bildirildi:
            _akim_guvenilmez_bildirildi.add(_t_idx)
            _bildir(lambda d: ceviri.t("bildirim.akimGuvenilmez", dil=d, coil=_t_coil_id), "warning")
        if _t_alan_degisti:
            if _t_snap.get("alanDogrulanamadi"):
                _bildir(lambda d: ceviri.t("bildirim.alanDogrulanamadi", dil=d, coil=_t_coil_id), "warning")
        if not _t_yazildi:
            return
        _coil_last_telemetry[_t_idx] = time.monotonic()
        # ⚠️ D2.39 (B-1.12 · Y31): "sensör kaydı HER ZAMAN açık" STM telemetrisini de kapsar. Kaydedicinin tek çağıranı MQTT (ESP)
        # işleyicisiydi ve o yol `PEMF_ESP_ENABLED` arkasında → varsayılan sahada bobin 1-7 telemetrisi diske HİÇ yazılmıyordu. Yük
        # olduğu gibi verilir (yalnız GELEN alanlar → ölçülmeyen sütun boş, Y6). Kaydedici ASLA canlı akışı bozmaz (kendisi yutar;
        # burada da sarılı). Kapı: tests/test_stm_telemetrisi_SENSOR_KAYDINA_yazilir_D239.py
        # F2-3.1: KUYRUĞA — bu satır STM okuyucu iş parçacığında koşar; dosya G/Ç'si okuyucuyu (ACİL DURDUR teyidi, NACK) bekletmez.
        try:
            _sensor_kaydedici.kaydet_arka_planda(_t_coil_id, "sensors", data)
        except Exception:
            logging.getLogger(__name__).debug("STM telemetrisi sensor kaydina yazilamadi", exc_info=True)
        # ⚠️ DOYGUNLUK (`X=1`): TD5'ten beri ayrıştırıcı akımı ATAR (`akim_guvenilmez`) — sayı ekrana / doz kaydına girmez;
        # operatör bobin başına TEK birleşik uyarı alır (yukarıda). Eskiden her 0→1 geçişinde "ölçüm aralığını AŞTI (ADC tavanı
        # ~12 A)" basılıyor, yüzen girişte 46 kez geliyordu.
        # ⚠️ MANYETIK DOYGUNLUK: ham eksen tam ölçeğe DAYANDI → |B| GÜVENİLMEZ ve seansın
        # "ölçülen yoğunluk"una öyle giriyor. RES_16'da taşma KIRPILMAZ, SARAR: gerçek alan
        # KÜÇÜK görünür — yani doygunluk bayrağı, sayının düşük çıkabileceğinin de habercisi.
        # Yalnız 0→1 geçişinde bildir (her saniye basmak alarm yorgunluğu üretir).
        _t_mag_doygun = bool(data.get("magnetic_saturated"))
        if _t_mag_doygun != bool(_mag_doygun_son.get(_t_idx)):
            _mag_doygun_son[_t_idx] = _t_mag_doygun
            if _t_mag_doygun:
                _bildir(lambda d: ceviri.t("bildirim.alanDoygun", dil=d, coil=_t_coil_id), "warning")
        # ── SEANS YOĞUNLUĞU: ölçüm CSV'ye ve aktif seans kartına ─────────────────────
        # Sahip kararı 2026-09-11: "ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN
        # GELSİN VE AYNI ZAMANDA CSV YE KAYDEDİP MASAÜSTÜNE KOYSUN".
        # ⚠️ Reçete alanı (`intensityMt`) DEĞİŞTİRİLMEZ — ikisi farklı büyüklüktür.
        if "magnetic_field" in data:
            try:
                _seans_alan.olcum(
                    _t_coil_id,
                    float(data["magnetic_field"]),
                    data.get("magnetic_samples"),
                    _t_mag_doygun,
                    # ⚠️ İŞARETLİ UÇLAR: `magnetic_field` BÜYÜKLÜKTÜR ve unipolar ile
                    # bipolari AYNI gösterir. Sürüş kipi/faz kazancı yalnız burada görünür.
                    uclar={
                        k: data[k]
                        for k in (
                            "mag_x_min",
                            "mag_x_max",
                            "mag_y_min",
                            "mag_y_max",
                            "mag_z_min",
                            "mag_z_max",
                        )
                        if k in data
                    },
                )
                # ⚠️ İKİ SAYI BİRDEN (sahip isteği 2026-09-11: "ANLIK yazdırmalı").
                # `son_deger()` = SON SANİYENİN tepesi → kartta canlı görünen sayı.
                # `zirve()`     = SEANS BOYU tepe → kayda/PDF'e giren, asla düşmeyen sayı.
                # Eskiden yalnız seans tepesi gönderiliyordu: operatör alanı değiştirip
                # (frekans/duty/kip) etkisini ANINDA göremiyordu, çünkü tepe düşmez.
                update_measured_intensity(_seans_alan.son_deger(), _t_coil_id, _seans_alan.zirve())
            except Exception:
                logging.exception("seans alan kaydı/ölçülen yoğunluk güncellenemedi")
        _ws_broadcast_sync({"type": "coil_status", "coilId": _t_coil_id, "data": _t_snap})
        _ws_broadcast_sync(
            {
                "type": "sensor_data",
                "coilId": _t_coil_id,
                "timestamp": time.time(),
                "data": {
                    "magneticMt": _t_snap.get("magneticMt"),
                    "objectTemp": _t_snap.get("objectTemp"),
                    "ambientTemp": _t_snap.get("ambientTemp"),
                    "currentA": _t_snap.get("currentA"),
                    "measuredFields": _t_snap.get("measuredFields"),
                },
            }
        )
        return
    if event.event_type == "hardware.stm.stop_onayi":
        # D1.E04: kart GERÇEK ACK'le tüm çıkışları sıfır bildirdi → bekleyen teyitsiz E-stop STM'ce teyit edilir (A-63).
        live_state.estop_teyidi_stm_ack()
        return
    if event.event_type == "hardware.stm.uyum":
        # TD1 (K1 / K2): kart ↔ uygulama paket uyumu kararı → canlı durum + WS `stm_uyum` (arayüz kalıcı bandı). Eskiden
        # `hardware.stm.uyumsuz` yayınlanıyor ama hiçbir abonesi yoktu (tezgâh ölçtü: arayüzde iz yok).
        live_state.stm_uyum_yaz(data)
        return
    if event.event_type == "hardware.stm.watchdog_timeout":
        # STM firmware watchdog'u ateşledi → STM PWM'i BİLİNMEYEN/durmuş durumda (komuta uymuyor). Bu bir
        # donanım-fault EVENT'i (backend EŞİK DAYATMAZ; donanımın kararına tepki verir) → STM kullanan aktif
        # seansı güvenli durdur + state'i eşitle. Aksi halde UI 'çalışıyor' gösterir ama STM durmuştur (desync).
        with _session_lock:
            _sess_active = bool(_active_session.get("is_active"))
            _sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
        _seans_durduruluyor = _sess_active and any(c in STM_COIL_IDS for c in _sess_coils)
        # ⚠️ Y45: bobin çalışırken (seans olsun olmasın) mandal — STOP'tan ÖNCE, HC sıfırlanmadan okunarak.
        _y45_mandal = _y45_mandal_kur("stm_watchdog_timeout")
        # ⚠️ D1.73 (B-1.18): firmware watchdog'u çıkışları SIFIRLADI ama HardwareController durumu "çalışıyor" kalıyordu →
        # keep-alive bir sonraki turda ESKİ duty ile bobini YENİDEN ENERJİLİYORDU (seanssız sürüşte host 1,5 sn takılınca;
        # operatöre "durdu" denirken). Durum `stop_all_coils` ile sıfırlanır (STOP da gider — Ö.4-Y8 yalnız artırır).
        # YALNIZ watchdog dalı: termal (`STM_EVT`) dalın davranışı A-47 gereği DEĞİŞMEZ (termal kesme YOK).
        if state.hardware:
            try:
                state.hardware.stop_all_coils()
            except Exception:
                logging.exception("STM watchdog sonrasi HC sifirlama basarisiz")
        if _y45_mandal:
            _y45_mandal_sonrasi("stm_watchdog_timeout")
        _bildir(
            lambda d: (
                ceviri.t("bildirim.stmWatchdogSeansDurdu", dil=d)
                if _seans_durduruluyor
                else ceviri.t("bildirim.stmWatchdogSeanssiz", dil=d)
            ),
            "error",
        )
        if _seans_durduruluyor:
            try:
                _emergency_stop_async(reason="stm_watchdog_timeout", mode="STM Watchdog")
            except Exception:
                logging.exception("STM watchdog STOP failed")
        return
    if event.event_type in {"hardware.stm.error", "hardware.stm.nack"}:
        _ham = str(data.get("message", event.event_type))
        # ⚠️ BİLDİRİM SELİ KAPISI (saha 2026-09-11): firmware/backend protokolü uyuşmazsa
        # HER paket NACK'lenir → keep-alive 2 Hz olduğu için operatöre saniyede iki özdeş
        # "→ STM_NACK: CRC" düşer. Sahada 89+ bildirim ölçüldü: liste tıkanır, gerçek olaylar
        # (termal, watchdog, doygunluk) görünmez olur — klasik alarm yorgunluğu.
        #
        # ⚠️ VE MESAJ EYLEM SÖYLEMİYORDU: "CRC" ham firmware metnidir; operatör ondan ne
        # yapacağını çıkaramaz. CRC reddi pratikte TEK bir şeyi gösterir: karttaki firmware
        # ile bu sürümün paket biçimi UYUŞMUYOR (paket 5 bobinde 88, 7 bobinde 120 bayt).
        # ⚠️ SAYAÇ BASTIRMADAN ÖNCE ARTAR. `_stm_nack_bastir` yalnız BİLDİRİM selini keser;
        # kararı da bastırsaydı 30 sn'de bir tek olay sayılır ve "sistematik red" hiç
        # oluşmazdı — susturma, körlüğe dönüşürdü.
        _ilk_kez_sistematik = live_state.stm_komut_reddi_bildir(_ham)
        if live_state.stm_duty_reddi_coz(_ham) is not None:  # D1.101 · Y20: duty tavanı reddi (firmware tek sınır)
            _stm_duty_reddini_isle(_ham, _ilk_kez_sistematik)
            return
        if _ilk_kez_sistematik:
            _stm_red_aktif_seansi_durdur(_ham)
        if _stm_nack_bastir(_ham):
            return
        if "CRC" in _ham.upper():
            _bildir(lambda d: "⚠️ " + stm_red_mesaji(d), "error")  # TD1 · K1: sade metin + kod; teknik ayrıntı destekte
            return
        _push_notification(_ham, "error")
        return
    if event.event_type == "mqtt.broker.status":
        # ⚠️ ESP KAPALIYKEN BROKER DURUMU ARIZA DEĞİLDİR: ESP kartları sistemden söküldü
        # (sahip, 2026-09-11) → mosquitto çalışmıyor olabilir ve bu BEKLENEN durumdur.
        # "warning" basmak, kurulu olmayan bir alt sistem için kalıcı sarı rozet üretirdi.
        if not live_state.esp_etkin():
            mqtt_state = "devre_disi"
        else:
            mqtt_state = "online" if data.get("port_open") or data.get("running") else "warning"
        with _live_state_lock:
            _live_state["mqtt"] = mqtt_state
            gateway_state = _live_state["gateway"]
        _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": gateway_state, "mqtt": mqtt_state}})
        return
    if event.event_type == "network.status":
        # ══════════════════════════════════════════════════════════════════════════
        # ⚠️ İNTERNET ≠ CİHAZ AĞI (sahip bildirimi 2026-09-11)
        # ══════════════════════════════════════════════════════════════════════════
        # ESKİ HÂLİ: `gateway_state = "online" if mode in ("online","hybrid") else "offline"`.
        # `_determine_gateway_mode` hotspot AÇIK + internet YOK durumunu "offline" döndürür
        # → "Bağlantı" rozeti KIRMIZI yanıyordu. Oysa o an hotspot çalışıyor, STM kablolu,
        # bütün donanım kusursuz sürülüyor. Sahip: "internete bağlı olmasa bile hotspot
        # açabiliyor ve bütün donanım kusursuz çalışıyor ama kırmızı dolu bir ekran var."
        #
        # BU ÜRÜN İNTERNETSİZ ÇALIŞIR. İnternet YALNIZ uzaktan erişim içindir. Bu yüzden:
        #   · `gateway` = CİHAZ AĞI kullanılabilir mi (hotspot açık YA DA internet var)
        #   · `internet` = ayrı, NÖTR bilgi (arayüz bunu arıza rengiyle göstermez)
        # Böylece kırmızı yalnız GERÇEKTEN bozuk bir şey için kalır ve uyarı körlüğü olmaz.
        mode = data.get("gateway_mode", "unknown")
        internet_var = bool(data.get("internet_connected")) or mode in ("online", "hybrid")
        # Hotspot açıksa cihaz ağı ÇALIŞIYOR demektir (mobil istemciler bağlanabilir).
        cihaz_agi_var = bool(data.get("hotspot_active")) or mode in ("online", "offline", "hybrid")
        gateway_state = "online" if cihaz_agi_var else "offline"
        with _live_state_lock:
            _live_state["gateway"] = gateway_state
            _live_state["internet"] = "online" if internet_var else "offline"
            # Y230 (BE 3): ESP KAPALIYKEN yerel broker erişilebilirliği (mosquitto ESP'den bağımsız koşar) ESP / MQTT durumu DEĞİLDİR —
            # eskiden burada kapısız "online" yazılıyor, Ana Ekran "ESP / MQTT" rozeti yeşil yanıyordu (`mqtt.broker.status` işleyicisiyle çelişki).
            if not live_state.esp_etkin():
                _live_state["mqtt"] = "devre_disi"
            elif data.get("mqtt_broker_reachable"):
                _live_state["mqtt"] = "online"
            mqtt_state = _live_state["mqtt"]
            internet_state = _live_state["internet"]
        # ⚠️ `internet` YAYININ İÇİNDE GİTMEK ZORUNDA (sahip bildirimi 2026-09-12).
        # Eskiden yalnız `_live_state`e yazılıyor, yayına KONMUYORDU → arayüz onu SADECE
        # ilk snapshot'ta görüyordu. `network.status` olayı da yalnız DEĞİŞİMDE yayınlandığı
        # için rozet başlangıç değerinde ("offline") sonsuza dek donuyordu: backend
        # `"internet":"online"` derken ekranda "İnternet yok — uzaktan erişim kapalı" yazıyordu.
        _ws_broadcast_sync(
            {
                "type": "gateway_status",
                "data": {
                    "gateway": gateway_state,
                    "mqtt": mqtt_state,
                    "internet": internet_state,
                    "network": data,
                },
            }
        )
        return
    if event.event_type in {"mqtt.broker.error", "discovery.error"}:
        # Y230 (BE 3): ESP kapalıyken broker hatası operatöre gösterilmez (kurulu olmayan alt sistem) — günlükte kalır.
        if event.event_type == "mqtt.broker.error" and not live_state.esp_etkin():
            logging.getLogger(__name__).info(
                "MQTT broker hatasi (ESP kapali, bildirim yok): %s", data.get("message", "")
            )
            return
        _push_notification(str(data.get("message", event.event_type)), "warning")


def _register_event_bus_handlers() -> None:
    global _event_bus_registered
    if _event_bus_registered:
        return
    try:
        from event_bus import subscribe

        subscribe("hardware.stm.*", _handle_backend_event, "api_server.hardware_stm")
        subscribe("mqtt.broker.*", _handle_backend_event, "api_server.mqtt_broker")
        subscribe("network.status", _handle_backend_event, "api_server.network_status")
        subscribe("discovery.*", _handle_backend_event, "api_server.discovery")
        _event_bus_registered = True
    except Exception as exc:
        logging.warning("EventBus handler registration failed: %s", exc)


# Global State Container
class APIState:
    def __init__(self):
        self.core: HeadlessCore = None
        self.hardware: HardwareController = None


state = APIState()

# NOT (audit B-2.2): startup/shutdown mantığı yukarıdaki `lifespan` context-manager'ına taşındı
# (deprecated @app.on_event kaldırıldı). Arka-plan thread'leri artık import anında DEĞİL, lifespan
# startup'ta başlar (state.core/hardware backend_service._wire_api_server ile SET EDİLDİKTEN sonra).


def _start_mdns_service() -> None:
    """mDNS (Zeroconf) servisini ayrı thread'de başlatır."""
    try:
        from servers.auto_discovery import get_api_port, start_mdns

        # ⚠️ SABİT 8000 DEĞİL (denetim 2026-08-17): launcher boş port arıyor, staging 8010
        # kullanıyor. 8000 meşgulken mDNS yanlış portu yayınlıyor ve telefon oraya bağlanıyor.
        start_mdns(port=get_api_port(), device_name="PEMF-Vet")
    except Exception as e:
        logging.warning("mDNS başlatılamadı: %s", e)


# ── WebSocket Endpoint (/ws) ───────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Tek port (8000) üzerinden canlı sensör verisi WebSocket bağlantısı."""
    # P1 audit 2026-06-28: FAIL-CLOSED. Eskiden auth istisnasi except'e dusup KOSULSUZ accept()
    # ediyordu (kimliksiz WS kabul). Artik istisnada baglanti KAPATILIR (sessiz bypass YOK).
    try:
        from servers.auth import check_token, is_local_request, require_auth

        required = bool(require_auth())
    except Exception:
        logging.exception("WS auth katmani yuklenemedi (FAIL-CLOSED)")
        await websocket.close(code=1011)  # internal error
        return
    # YEREL/LAN WS de auth MUAF (token yalniz tunel/uzak — Cloudflare header'li)
    _wh = websocket.headers
    _ws_via_proxy = bool(_wh.get("cf-connecting-ip") or _wh.get("cf-ray") or _wh.get("x-forwarded-for"))
    # Cross-origin CSRF (audit P2 #1): tarayıcı WS'inde Origin GELİR. DOĞRUDAN (proxy'siz) LAN'da
    # Origin host'u Host ile eşleşmezse, başka-origin bir kötücül web sayfası cihaza WS açıyordur →
    # reddet. Native mobil Origin GÖNDERMEZ → serbest. Proxy/tünelde Host/Origin güvenilmez +
    # token-auth zaten zorunlu → orada uygulanmaz (yanlış-pozitif tünel erişimini kırmasın).
    _ws_origin = _wh.get("origin")
    if _ws_origin and not _ws_via_proxy:
        try:
            from urllib.parse import urlparse as _urlparse

            _o_host = (_urlparse(_ws_origin).hostname or "").lower()
            _h_host = (_wh.get("host") or "").rsplit(":", 1)[0].lower()
            if _o_host and _h_host and _o_host != _h_host:
                await websocket.close(code=1008)  # policy violation (cross-origin)
                return
        except Exception:
            pass
    if required and is_local_request(websocket.client.host if websocket.client else "", _ws_via_proxy):
        required = False
    if required:
        try:
            tok = websocket.query_params.get("token") or websocket.headers.get("X-API-Key") or ""
            ok = check_token(tok)
        except Exception:
            logging.exception("WS token kontrol hatasi (FAIL-CLOSED)")
            ok = False
        if not ok:
            # accept() ÖNCE → close(1008) SONRA: aksi halde client handshake hatası (1006) görür ve
            # 1008'i (auth) ağ-kopmasından AYIRAMAZ → wsClient hot-loop'a girerdi (audit P0).
            try:
                await websocket.accept()
            except Exception:
                pass
            await websocket.close(code=1008)  # policy violation (auth)
            return
    await websocket.accept()
    with _ws_lock:
        _ws_clients.append(websocket)
    # DENETIM P3: ilk snapshot gonderimi try/finally'nin DISINDA idi. Istemci accept ile ilk
    # send_text arasinda koparsa (mobilde ekran-kilidi/ag gecisi siradan) send_text firlatir,
    # `finally: _ws_clients.remove(...)` HIC calismaz ve OLU soket yayin listesinde KALIR →
    # her broadcast onun icin 5 sn timeout bekler (tum filoyu yavaslatir) ve ancak o zaman
    # dusurulur. try bloguna ALINDI: hata olsa da temizlik garanti.
    try:
        # Bağlantı açıldığında anlık durumu gönder
        await websocket.send_text(json.dumps({"type": "snapshot", "data": _build_ws_snapshot()}, ensure_ascii=False))
        while True:
            data = await websocket.receive_text()
            # İstemciden gelen komutları işle (şimdilik ping/pong)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg.get("type") == "alan_abone":
                    # GA (istem 53): canlı alan haritası aboneliği (kart açıkken) — hesap yalnız abone varken koşar.
                    _canli_alan.abone(websocket, bool(msg.get("acik")))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        with _ws_lock:
            try:
                _ws_clients.remove(websocket)
            except ValueError:
                pass
        _canli_alan.abone(websocket, False)


# --- REACT NATIVE (EXPO) ENDPOINT'LERİ ---


@app.get("/metrics")
async def metrics():
    """Prometheus-uyumlu metrikler (audit B-5.2) — sayısal zaman-serisi gözlemlenebilirliği.
    Harici bağımlılık YOK (elle text format → frozen EXE'yi şişirmez). YEREL/LAN scrape auth-muaf
    (Prometheus localhost'tan çeker), uzak scrape token ister (auth middleware). Ölçütler in-memory
    canlı durumdan türetilir (ek sayaç enstrümantasyonu gerektirmez)."""
    with _live_state_lock:
        coils = _live_state["coils"]
        connected = sum(1 for i in range(8) if coils[i].get("connected"))
        running = sum(1 for i in range(8) if coils[i].get("running"))
        mqtt_up = 1 if _live_state.get("mqtt") == "online" else 0
        stm_up = 1 if _live_state.get("stm") == "online" else 0
        gateway_up = 1 if _live_state.get("gateway") == "online" else 0
        notif = len(_live_state.get("notifications", []))
    with _session_lock:
        active = 1 if _active_session.get("is_active") else 0
    with _ws_lock:
        ws_clients = len(_ws_clients)
    m = [
        ("pemf_ws_clients", "Bagli WebSocket istemci sayisi", ws_clients),
        ("pemf_active_session", "Aktif seans (1/0)", active),
        ("pemf_coils_connected", "Bagli bobin sayisi", connected),
        ("pemf_coils_running", "Calisan bobin sayisi", running),
        ("pemf_mqtt_up", "MQTT broker baglantisi (1/0)", mqtt_up),
        ("pemf_stm_up", "STM32 baglantisi (1/0)", stm_up),
        ("pemf_gateway_up", "Gateway/ag baglantisi (1/0)", gateway_up),
        ("pemf_notifications", "Bekleyen bildirim sayisi", notif),
    ]
    lines = []
    for name, help_text, val in m:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {val}")
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


class CommandPayload(BaseModel):
    command: str
    params: dict = {}


# (audit B-2.2) PatientInput modeli servers/patient_router.py'ye taşındı (hasta uçlarıyla birlikte).


class AutoPresetPayload(BaseModel):
    target_condition: str


class SessionStartPayload(BaseModel):
    # D1.99 (S-1.6): NaN/Infinity 422 — eskiden koşu kaydına inf yazıp detay ucunu kalıcı 500 yapıyor, NaN WS'i bozuyordu.
    model_config = ConfigDict(allow_inf_nan=False)

    patient_id: str = ""
    patient_name: str = ""
    operator_name: str = ""  # denetim izi — seansı başlatan operatör (audit P1)
    operator_email: str = ""  # klinik-içi sahiplik — seansı başlatan hekim e-postası ("Benim/Tüm Klinik")
    mode: str = "Manuel"  # Manuel | Otomatik | AI
    target_condition: str = ""
    frequency: float = 50.0
    duty: float = 25.0
    # ⚠️ T-d (Tezgâh-2 #9): REÇETE yoğunluğu (mT; cihaza GÖNDERİLMEZ, yalnız kayda yazılır). Varsayılan 25.0 idi → yoğunluk
    # göndermeyen istemcinin seansı "Ayarlanan 25 mT" diye kaydediliyordu (kimsenin girmediği değer; Y6: girilmeyen NULL).
    # 0 → `intensity_mt` NULL (`payload.intensity or None`); arayüz elle seansta zaten 0 gönderir.
    intensity: float = 0.0
    phase: float = 0.0
    # ge=1: süre 0/negatif olursa auto-end mantığı (total>0) hiç tetiklenmez → seans SONSUZ sürerdi.
    # Bu bir SÜRE (seans-uzunluğu) doğrulaması; frekans/duty/intensity TEDAVİ parametrelerine DOKUNULMADI.
    duration_minutes: int = Field(default=20, ge=1)
    # DENETIM P1 (thread-bombasi): tip `list` idi (eleman tipi/uzunluk kisiti YOK) →
    # {"coil_ids": [6]*20000} ESP bobin basina AYRI daemon-thread aciyordu (her biri socket
    # connect + paho connect) → 'can't start new thread' / handle tukenmesi; ayni anda suren
    # gercek tedavide sure-watchdog aclik cekip bobinler planlanandan uzun enerjili kalabilirdi.
    # /api/coil/batch zaten `_seen[:8]` ile sertlestirilmisti, start yolu unutulmustu.
    # Cihazda toplam 8 bobin var → 8'den uzun liste MESRU DEGIL, sinirda 422 ile reddedilir.
    # list[int]: tip-disi eleman artik sessizce "tedavi yok"a dusmek yerine 422 verir.
    coil_ids: list[int] = Field(default_factory=list, max_length=8)  # empty = all coils


# ⚠️ `duration` NEGATIF OLAMAZ (kampanya bulgusu S03, 2026-08-14). Eskiden dogrulama YOKTU:
# `duration=-60` sessizce kabul ediliyor, `_duration_seconds_to_stm_minutes(-60)` 0 donduruyor ve
# komut "sure verilmemis" gibi davraniyordu → bir YAZIM HATASI bobini gozetimsiz varsayilan sure
# boyunca enerjili birakiyordu. `0` GECERLIDIR ("sure belirtme") ve reddedilmez; negatif deger
# anlamsizdir ve 422 ile geri cevrilir. (Seans modeli zaten `Field(ge=1)` ile dogruluyordu; bobin
# yolu bu korumadan yoksundu.)
class CoilControlPayload(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)  # D1.99 (S-1.6): NaN/Infinity 422

    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = Field(default=0, ge=0)  # seconds for ESP/MQTT payloads
    start: bool = True


class SurusKipiPayload(BaseModel):
    """Bobin başına sürüş kipi İSTEĞİ.

    `unipolar[i] = True` → bobin i+1 tek yönlü sürülsün (yalnız IN_A darbelenir, IN_B kapalı).
    `False` → çift yönlü (IN_A / IN_B dönüşümlü) istenir.

    ⚠️ İSTEK ≠ ETKİN KİP. Bobin 6-7 sürücüsü donanımsal olarak tek yönlü; firmware
    `etkin = yetenek || istek` uygular, yani onlara `False` göndermek bir şey değiştirmez.
    Gerçekte uygulanan kip ACK'in `K=` alanından gelir ve canlı durumdaki `unipolar`
    alanına yazılır — arayüz DAİMA o alanı gösterir, bu isteği değil.
    """

    unipolar: list[bool]


class BatchCoilPayload(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)  # D1.99 (S-1.6): NaN/Infinity 422

    coil_ids: list[int]  # e.g. [1,2,3]
    freq: float = 50.0
    duty: float = 25.0
    phase: float = 0.0
    duration: int = Field(default=0, ge=0)  # seconds for ESP/MQTT payloads
    start: bool = True


_seans_muhru_kilit = threading.Lock()
_seans_muhru_sayac = 0


def _yeni_seans_muhru() -> str:
    """API seans mührü — `react_<epoch_ms>_<sayac>`.

    ⚠️ ESKİDEN `react_<epoch SANİYE>` idi ve AYNI SANİYEDE başlatılan iki farklı seans AYNI
    mührü alıyordu (kampanya bulgusu S11, ölçüldü). `session_events` kayıtlarındaki
    `payload.ref` bu mühürdür; çakışınca "bu denetim kaydı hangi seansa ait?" sorusu CEVAPSIZ
    kalır — bir istismar incelemesinde atfedilebilirlik yoksa iz işe yaramaz.

    Milisaniye TEK BAŞINA yetmez (hızlı durdur/başlat aynı ms'e düşebilir) → süreç-içi artan
    sayaç eklenir. Mühür artandır: denetimde olaylar kronolojik sıralanabilir.

    ⚠️ `react_` ÖN-EKİ KORUNUR — mevcut testler ve tüketiciler `startswith` ile bakar.
    """
    global _seans_muhru_sayac
    with _seans_muhru_kilit:
        _seans_muhru_sayac += 1
        return f"react_{int(time.time() * 1000)}_{_seans_muhru_sayac}"


def _surus_parametrelerini_dogrula_422(freq, duty, phase, duration_dk, duration_s=None) -> dict:
    """D1.95 (B-1.13 · B-1.16): donanım paketine SIĞMAYAN START parametresi → 422; bobin durumu ve deadline DEĞİŞMEZ.

    ⚠️ Eskiden taşan süre (`duration` ~10**309 sn) ve duty (≥ 3,4e40 %) durum YAZILDIKTAN SONRA patlıyordu: biri
    bobini deadline'sız (süresiz) enerjili bırakıp 500 dönüyor, öteki sonraki HER paketi (STOP dahil) düşürüyordu.
    `HardwareController` da aynı yardımcıyla reddeder (False); uçta 422 verilir ki çağıran "donanım reddetti"
    (503) ile "girdi geçersiz"i ayırt edebilsin. Duty/frekans ÜST sınırı EKLENMEZ (Ö.4-Y9).

    D1.99 (B-1.9 · S-1.2): dönüş = donanıma GİDECEK (normalize) değerler. `HardwareController.update_coil` AYNI saf
    fonksiyonu uygular; koşu kaydı ve seans kartı bu değeri yazar (30000 Hz istenip 25000 sürülürken kayıt 30000
    diyordu). `update_coil`'in bool sözleşmesi bilerek DEĞİŞTİRİLMEDİ (plan C1-20: truthiness bekleyen çağıranlar
    ve sahte donanımlar)."""
    from controllers.hardware_controller import ParametreGecersiz, surus_parametrelerini_hazirla

    try:
        return surus_parametrelerini_hazirla(freq, duty, phase, duration_dk, duration_s)
    except ParametreGecersiz as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _duration_seconds_to_stm_minutes(duration_seconds: int) -> int:
    """Convert web/API ESP duration seconds to STM firmware duration minutes."""
    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(1, (seconds + 59) // 60)


def _esp_duration_seconds(duration_seconds: int) -> int:
    """ESP (bobin 6-8) MQTT `duration` alanini SANIYE olarak cozer; gozetimsiz kapagi uygular.

    ⚠️ DENETIM BULGUSU 2026-08-17 — KISMI DUZELTME TAMAMLANDI. `duration = 0` bu projenin KENDI
    protokol sozlesmesinde **SURESIZ** demektir (`firmware/stm32_pemf/Core/Src/main.c`: "Süre (dakika): 0 = süresiz";
    `controllers/hardware_controller` ayni notu tasir). STM yolu bu nobetciyi 1.9.14'ten beri
    `GOZETIMSIZ_VARSAYILAN_DAKIKA`ya cevirir — ama ESP yolu onu HAM iletiyordu. Sonuc: 1.9.14'te
    BILINCLI eklenen klinik kapak 8 bobinin yalniz 5'ini kapsiyordu.

    ESP tarafinda sunucu-yanli hicbir son-tarih YOKTUR: `_coil_deadline` yalniz `range(1, 6)`,
    seans acilmadigi icin `_session_duration_watchdog` kapsam disi, `_esp_telemetry_watchdog`
    (bkz. asagi) yalniz telemetri SUSARSA devreye girer — saglikli yayin yapan bir ESP bobini
    kapaksiz kalirdi. Ustelik arayuz operatore "bobin donanim ust-sinirina kadar calisir" diye
    guvence veriyordu; ESP firmware'i o tarihte bu depoda DEGILDI, yani o guvencenin dayanagi
    yoktu. GUNCELLEME 2026-08-19: firmware artik depoda (firmware/esps3_pemf_coil +
    esp8266_pemf_coil) VE Plan A-1 ile cihazin KENDISI de suresiz modda 7200 sn KUMULATIF
    tavan uygular (SURESIZ_TAVAN_SEC — ayni 120 dk'dan turer). Bu fonksiyon backend-yanli
    ILK katman olarak DURUR (derinlemesine savunma; kaldirma).

    ⚠️ Sabit BURADA TANIMLANMAZ. Klinik sinir TEK KAYNAKTAN (`hardware_controller`) okunur ki iki
    transport bir gun ayrisamasin — bu bulgunun kok nedeni tam olarak o ayrisma idi.
    ⚠️ Yeni bir UST-SINIR DEGILDIR: acikca verilen sureye DOKUNULMAZ. `duration=0` de REDDEDILMEZ
    (Kontrol Paneli'ni bozardi); yalnizca sonsuz surmez.
    ⚠️ freq/duty/48°C safety-limit'leriyle ILGISI YOKTUR; onlar sahip karariyla kaldirildi ve GERI
    EKLENMEZ. Buradaki sinir yalniz SUREdir.

    Kilit: `tests/test_esp_gozetimsiz_sure_kapagi.py` (karsit-kanit testleri dahil).
    """
    from controllers.hardware_controller import GOZETIMSIZ_VARSAYILAN_DAKIKA

    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        seconds = 0
    if seconds > 0:
        return seconds
    return GOZETIMSIZ_VARSAYILAN_DAKIKA * 60


# ── MQTT publish helper (used by headless and GUI-less mode) ─────────────────
import json as _json


def _mqtt_credentials():
    """Yerel broker'a gönderilecek (kullanıcı, şifre).

    A-04 · D1.104: broker kimliği HAZIRLANMIŞSA (`utils.mqtt_kimlik hazirla`) makine deposundaki backend kimliği — broker'ın
    parola/yetki dosyaları onunla AYNI adımda üretildi, yani backend'in STOP yayınları kimlikli broker'da da geçer
    (Ö.4-Y8). Hazırlanmamışsa operatörün `mqtt_user/mqtt_pass` sırrı; o da yoksa (None, None) → anonim (hazırlanmamış
    broker bugünkü gibi anonim kabul eder — hiçbir STOP yolu değişmez)."""
    try:
        from utils import mqtt_kimlik

        _ku, _kp = mqtt_kimlik.backend_kimligi()
        if _ku and _kp:
            return _ku, _kp
    except Exception:
        logging.getLogger(__name__).warning("MQTT kimlik deposu okunamadi - operator kimligine dusuldu", exc_info=True)
    try:
        from utils.secrets_manager import get_secret

        u = get_secret("mqtt_user")
        p = get_secret("mqtt_pass")
    except Exception:
        u = os.environ.get("PEMF_MQTT_USER", "").strip()
        p = os.environ.get("PEMF_MQTT_PASS", "")
    return (u or None, p or None)


def _esp_yanit_durumu(ok: bool) -> str:
    """D1.98 (B-6.9): ESP bobin ucunun yanıt durumu — "ESP BİLEREK kapalı" ile "broker ölü" AYRILIR.

    Eskiden ikisi de `mqtt_unavailable`dı: `PEMF_ESP_ENABLED` ayarsızken (HEAD varsayılanı) Kontrol ekranının her
    "⏹ Durdur"u slot 8 yanıtı yüzünden sahte "bobinler HÂLÂ ÇALIŞIYOR olabilir" alarmı veriyordu (alarm körlüğü, K4).
    `devre_disi` = ESP alt sistemi kurulu/etkin değil, komut YAYINLANMADI (yine de `_mqtt_publish` denendi — gönderim
    azaltılmaz, Ö.4-Y8). ⚠️ "success" DEĞİLDİR: hiçbir yüklem bunu teyit saymaz; teyit A-63 gereği STM'e göre verilir.
    ESP açıkken başarısız yayın `mqtt_unavailable` KALIR (gerçek arıza alarmı)."""
    if ok:
        return "success"
    return "mqtt_unavailable" if live_state.esp_etkin() else "devre_disi"


def _mqtt_publish(topic: str, payload: dict) -> bool:
    """Publish a JSON payload to the local MQTT broker. Returns success.

    Broker kapalıyken paho.connect Windows'ta ~2sn bloke oluyordu (3 ESP bobin →
    seans başlatma ~8sn kilitleniyordu). Önce 0.3sn'lik hızlı socket probe ile
    broker erişilebilir mi bak; değilse anında çık (seansı kilitleme)."""
    # ⚠️ ESP SÖKÜLÜ → HİÇ YAYINLAMA (sahip kararı 2026-09-11, bkz. live_state.esp_etkin).
    # TEK BOĞAZ NOKTASI: bütün ESP komutları (manuel, seans, AI, E-stop, reconcile, selftest)
    # buradan geçer → kapı burada olunca çağrı yerlerini tek tek gezmeye gerek kalmaz ve
    # yeni bir çağrı yeri eklendiğinde de kendiliğinden kapanır.
    #
    # ⚠️ NİYET DE KAYDEDİLMEZ: `_kaydet_esp_komut_niyeti` reconcile içindir (ESP yeniden
    # görününce geri al). ESP yokken biriken niyet, ileride `PEMF_ESP_ENABLED=1` ile geri
    # dönüldüğünde BAYAT komutlarla reconcile tetikler — yani kapının altında kalmalı.
    #
    # Dönüş False: "yayınlanmadı" DOĞRUDUR. True demek, gönderilmemiş bir komutu
    # gönderilmiş saymak olurdu (bu deponun tekrarlayan sahte-teyit sınıfı).
    if not live_state.esp_etkin():
        logging.getLogger(__name__).debug("ESP kapali -> MQTT publish ATLANDI: %s", topic)
        return False
    # ⚠️ D1.81 · Y4 — SON SAVUNMA HATTI (tek boğaz noktası): acil durdurma MANDALLIYKEN hiçbir ESP START yayını
    # gitmez — bir çağrı yeri `_esp_start_yayinla`yı unutsa bile. YALNIZ "start": STOP / selftest / status bu kapıdan
    # GEÇMEZ (Ö.4-Y8: durdurma hiçbir şeye kapılanmaz).
    if str((payload or {}).get("command", "")).strip().lower() == "start" and estop_mandali.mandalli_mi():
        logging.getLogger(__name__).warning("ESP START yayini REDDEDILDI (acil durdurma mandalli): %s", topic)
        return False
    # HG-6 (Plan A-3): backend'in ESP'ye komutladığı NİYET tek boğaz noktasında kaydedilir.
    # ASİMETRİK (review F4): STOP burada HEMEN (başarısız STOP'ta bile niyet False olmalı ki
    # ESP görününce reconcile denesin); START ise yalnız publish DOĞRULANINCA (aşağıda) —
    # başarısız start niyeti True bıraksaydı NVS-resume hayaleti reconcile'dan süresiz muaf
    # kalırdı. Tüm çağıranlar (manuel, AI, seans, E-stop, reset) buradan geçer.
    _kaydet_esp_komut_niyeti(topic, payload, basarili=False)
    try:
        import socket as _socket

        try:
            _probe = _socket.create_connection(("127.0.0.1", 1883), timeout=0.3)
            _probe.close()
        except OSError:
            return False  # broker erişilemez → hızlı başarısız
        import paho.mqtt.client as _mqtt

        # Cagri basina BENZERSIZ kimlik — acil-durdurma ESP bobinlerine paralel yayin yapar;
        # sabit kimlikte broker es-zamanli baglantilardan yalniz birini tutar (bkz. _mqtt_client_id).
        # ⚠️ CALLBACK API SÜRÜMÜ AÇIKÇA VERİLİR (2026-08-15). paho 2.x, sürüm verilmeyen her
        # istemci için "Callback API version 1 is deprecated" uyarısı basıyordu ve bu tek satır
        # test çıktısında ~156 uyarı üretiyordu. Gürültü zararsız değildir: bugün tam bu yüzden
        # sklearn'ün "geçersiz sonuç üretebilir" uyarısı 171 satırlık tekrarın içinde
        # kayboluyordu. Bu istemcinin HİÇ geri çağrısı yok (yalnız connect/publish) → V2'ye
        # geçmek davranışı değiştirmez.
        c = _mqtt.Client(_mqtt.CallbackAPIVersion.VERSION2, client_id=_mqtt_client_id("pub"), clean_session=True)
        _u, _pw = _mqtt_credentials()
        if _u:
            c.username_pw_set(_u, _pw)  # broker auth açıksa (allow_anonymous false) kimlik gönder
        c.connect("127.0.0.1", 1883, 5)
        info = c.publish(topic, _json.dumps(payload), qos=1)
        # wait_for_publish: qos=1 mesajı disconnect'ten ÖNCE broker'a teslim edilsin (audit #4).
        # Eskiden publish hemen disconnect ediliyordu → ağ döngüsü çalışmadan mesaj ara sıra
        # gönderilmeden düşebiliyordu (bobin komutu kaybı).
        c.loop_start()
        try:
            # ⚠️ DENETİM 2026-08-09 (ENGEL) — SONUÇ ARTIK GERÇEKTEN OKUNUYOR.
            # Eski hâli `wait_for_publish(timeout=2.0)` çağırıp SONUCU YOK SAYARAK koşulsuz True
            # dönüyordu. Broker TCP'yi kabul edip QoS-1 PUBACK'i hiç göndermezse (broker asılı,
            # disk dolu, yetki reddi) zaman aşımı dolar ve mesaj TESLİM EDİLMEMİŞTİR — ama
            # `_estop_one` bunu "success" sayar, `_esp_ok` True olur, arayüz "bobinler durdu" der.
            # Yani acil durdurmanın ESP ayağı sessizce başarısız olurken operatöre BAŞARILI görünür.
            # `wait_for_publish` zaman aşımında (paho ≥2.0) WouldBlockError atar → yakala.
            try:
                info.wait_for_publish(timeout=2.0)
            except (ValueError, RuntimeError, OSError):
                pass  # aşağıdaki is_published() kesin cevabı verir
            except Exception:
                pass
            yayinlandi = bool(info.is_published())
        finally:
            c.loop_stop()
        c.disconnect()
        if not yayinlandi:
            logging.getLogger(__name__).error(
                "MQTT yayin DOGRULANAMADI (PUBACK yok) — konu=%s. Bobin komutu TESLIM EDILMEMIS olabilir.", topic
            )
        else:
            # F4: START niyeti yalnız DOĞRULANMIŞ publish'te kaydedilir (yukarıdaki asimetri notu).
            _kaydet_esp_komut_niyeti(topic, payload, basarili=True)
        return yayinlandi
    except Exception:
        return False


# ── ESP KOMUT ONAYI (ACK ROUND-TRIP) — donanım-uyum denetimi HG-4 (2026-08-19) ────────────────
# SORUN: ESP bobinleri (6-8) her komuta `pemf/coil/{id}/ack` konusuna {command_id, success}
# yayınlar (firmware sendCommandAck), ama backend bu konuyu HİÇ dinlemiyordu. `_mqtt_publish`
# yalnız broker QoS-1 PUBACK'ini okur → "broker mesajı kabul etti" demek, "ESP mesajı ALDI"
# demek DEĞİL. WiFi'siz bir ESP'ye E-stop yayınlanınca broker PUBACK döner, çağıran "success"
# sayar, operatöre "durduruldu" gösterir — ama ESP mesajı hiç almaz (STOP retain=False). Bobin
# fiziksel enerjili kalırken UI "durdu" der.
#
# ÇÖZÜM: kalıcı dinleyici client `.../ack`e abone olur; komut ONAYINI command_id ile eşler.
# ⚠️ E-stop'u BLOKLAMAZ: publish hemen gider (hız kritik), onay ARKA PLANDA izlenir; gelmezse
# operatöre AÇIK uyarı gider. Onay yokluğu artık SESSİZ değil.
_pending_acks: dict = {}
_pending_acks_lock = threading.Lock()
# 1-C inceleme i6-F-2/F-3: bobin başına GERÇEKTEN yayınlanan SON START'ın kimliği (`_esp_start_yayinla`, yayından ÖNCE;
# `_pending_acks_lock` ile). Geciken bir NACK bobinin GÜNCEL START'ına ait değilse (sonraki START devraldı) koşu
# kapatılmaz ve "bobin ÇALIŞMIYOR" denmez — o NACK bobinin ŞİMDİKİ durumunu söylemez.
_son_start_kimligi: dict = {}

# DENETIM 2. TUR [3.2] (2026-08-20): command_id YALNIZ ms çözünürlüklüydü — aynı bobine aynı
# milisaniyede iki E-stop tetiği (manuel buton + ESP alarmı; alarm dalında debounce yok) AYNI
# id'yi üretiyordu. _register_ack üzerine yazar + _wait_ack pop'lar → ikinci bekçi ack GELMİŞKEN
# timeout görüp acil-durdurma anında SAHTE "ONAYI GELMEDİ" kırmızı alarmı basıyordu (ölçüldü,
# iki advers interleaving). Süreç-ömürlü sıra numarası aynı ms'de bile benzersizlik verir.
# (itertools.count C-uygulamalıdır; next() GIL altında atomiktir — ayrıca kilit gerekmez.)
# ⚠️ id UZUNLUĞU (17. parti düzeltmesi — adversaryal inceleme): S3 firmware ≥36 karakterlik
# command_id'yi KIRPMAZ, TÜMDEN REDDEDER (esps3 NetworkManager.cpp: strlen<36 değilse id boş
# bırakılır → HİÇ ACK GİTMEZ). Yani id biçimi büyürse arıza modu "kırpılmış eşleşme" değil
# "onay hiç gelmez" olur. Biçim `estop_{coil}_{13 haneli ms}_{sıra}` ~25 karakterdir ve testle kilitlidir.
import itertools as _itertools

_estop_sira = _itertools.count(1)

# D1.E10 (DUZELTME-D1B §4 · NACK-D2 kökü): manuel/batch/seans kimlikleri de aynı türden sıra eki taşır.
# Windows saati 64 Hz'e yuvarlanınca aynı bobine iki hızlı start aynı ms'yi alıyordu → _register_ack
# ikinci kaydı EZİYOR, start#1'in geciken NACK'i start#2'nin bekçisini uyandırıp KABUL edilmiş koşuyu
# "REDDEDİLDİ" diye kapatıyordu (ölçüldü: 64 Hz saatte 40 denemede 36). Aynı kimlik ESP8266 tekrar
# önbelleğinde de ikinci start'ı SESSİZCE düşürür (STOP dışı tekrar ACK'siz yutulur).
# Ek mod 10^6: en uzun `react_batch_{bobin}_{13 haneli ms}_{≤6 hane}` = 34 karakter (S3 sınırı ≤35, üstte).
_komut_sira = _itertools.count(1)


def _komut_kimligi(on_ek: str, coil_id: int) -> str:
    """ESP komut kimliği `{on_ek}_{bobin}_{ms}_{sıra}` — aynı ms'de bile benzersiz, ≤35 karakter."""
    return f"{on_ek}_{coil_id}_{int(time.time() * 1000)}_{next(_komut_sira) % 1_000_000}"


#: 1-C inceleme i1-F4: telafi STOP'u deneme sayısı ve denemeler arası bekleme (geçici broker hatasını aşmak için).
_TELAFI_STOP_DENEME = 3
_TELAFI_STOP_ARA_S = 0.2


def _esp_start_yayinla(coil_id: int, payload: dict, nesil: int | None = None) -> bool:
    """ESP START yayını — acil durdurma MANDALI ve sürüş NESLİ kapılı (D1.81 · B-5.3 · Y4).

    ⚠️ STM'deki gibi kilit TUTULAMAZ: yayın saniyeler sürebilir ve STOP'u bekletmek Ö.4-Y8'e aykırıdır. Bu yüzden
    (1) yayından ÖNCE denetlenir (mandal ya da bayat niyet → yayın YOK), (2) yayın SIRASINDA durdurma / acil durdurma
    geldiyse (nesil değişti ya da mandal kuruldu) bu START o STOP'tan SONRA ulaşmış olabilir → ardından TELAFİ STOP'u
    gönderilir. STOP gönderimi yalnız ARTAR. `nesil`: START niyetinin nesli; verilmezse bağlamdaki (HTTP isteğinin
    VARIŞ damgası — `asyncio.to_thread` bağlamı kopyalar; i1-F2) nesil, o da yoksa yalnız mandal denetlenir.
    @return START yayını doğrulandı VE geçerli kaldı."""
    if nesil is None:
        nesil = estop_mandali.baglam_nesli()
    _nesil_once = estop_mandali.nesil() if nesil is None else nesil
    _engel = estop_mandali.baslatma_engeli(nesil)
    if _engel:
        logging.getLogger(__name__).warning("ESP bobin %s START YAYINLANMADI: %s", coil_id, _engel)
        return False
    _kimlik = str(payload.get("command_id") or "")
    if _kimlik:
        with _pending_acks_lock:
            _son_start_kimligi[coil_id] = _kimlik  # i6-F-3: bobinin GÜNCEL START'ı (yayından ÖNCE — hızlı NACK yarışı)
    ok = _mqtt_publish(f"pemf/coil/{coil_id}/control", payload)
    if estop_mandali.mandalli_mi() or estop_mandali.nesil() != _nesil_once:
        logging.getLogger(__name__).warning(
            "ESP bobin %s: START yayını sürerken durdurma/acil durdurma geldi → TELAFİ STOP'u gönderiliyor.", coil_id
        )
        # ⚠️ 1-C inceleme i1-F4: telafi STOP'unun sonucu OKUNUR. Eskiden dönüş yok sayılıyordu — düşerse (geçici broker
        # hatası) telde son başarılı komut START kalıyor, operatöre hiçbir şey söylenmiyordu (ölçüldü). En çok
        # `_TELAFI_STOP_DENEME` kez denenir (her deneme YENİ kimlikle — 8266 tekrar önbelleği yutmasın); hepsi düşerse
        # "STOP doğrulanamadı" bildirimi. Bu işlev iş parçacığında koşar (bekleme olay döngüsünü bloklamaz). Ö.4-Y8.
        for _deneme in range(_TELAFI_STOP_DENEME):
            if _deneme:
                time.sleep(_TELAFI_STOP_ARA_S)
            if _mqtt_publish(
                f"pemf/coil/{coil_id}/control", {"command": "stop", "command_id": _komut_kimligi("telafi", coil_id)}
            ):
                break
        else:
            _bildir_teyitsiz_stop([coil_id], lambda d: ceviri.t("bildirim.kaynak.telafiStop", dil=d))
        return False
    return ok


def _register_ack(command_id: str, bobin: int | None = None) -> None:
    """Publish'ten ÖNCE çağrılır (ack yarışı kaybolmasın): command_id için bekleme kaydı aç.

    A-04 · D1.104: `bobin` = komutun YAYINLANDIĞI bobin — teyit yalnız o bobinin ack konusundan sayılır."""
    with _pending_acks_lock:
        _pending_acks[command_id] = {"success": None, "event": threading.Event(), "bobin": bobin}


def _resolve_ack(command_id: str, success: bool, bobin: int | None = None) -> None:
    """ESP ack'i gelince: kayıtlıysa sonucu yaz + bekleyeni uyandır. Bilinmeyen id → no-op
    (retained/bayat ack veya STM seri yolu; zararsız).

    A-04 · D1.104 (ack teyidinin KAYNAĞI): komut bir bobine yayınlandıysa ack yalnız O bobinin konusundan
    (`pemf/coil/<bobin>/ack`) teyit sayılır; başka konudan gelen aynı kimlikli ack YOK SAYILIR ve günlüğe yazılır.
    Kimlikli broker'da (utils.mqtt_kimlik) ack konusuna yalnız ESP kimliği yazabilir."""
    with _pending_acks_lock:
        entry = _pending_acks.get(command_id)
    if entry is None:
        return
    beklenen = entry.get("bobin")
    if beklenen is not None and bobin is not None and int(bobin) != int(beklenen):
        logging.getLogger(__name__).warning(
            "ack YANLIS bobin konusundan geldi (komut bobin %s, konu bobin %s) - teyit SAYILMADI: %s",
            beklenen,
            bobin,
            command_id,
        )
        return
    entry["success"] = bool(success)
    entry["event"].set()


def _wait_ack(command_id: str, timeout: float):
    """True=ESP onayladı, False=ESP başarısız bildirdi, None=onay GELMEDİ (timeout)."""
    with _pending_acks_lock:
        entry = _pending_acks.get(command_id)
    if entry is None:
        return None
    got = entry["event"].wait(timeout)
    with _pending_acks_lock:
        _pending_acks.pop(command_id, None)
    return entry["success"] if got else None


# ── [4.5] NACK yarisi (2026-08-22): manuel ESP start'i da ack-mimarisine baglanir ────────────
# "Dogrulanmis publish" yalniz BROKER kabuludur; ESP komutu ayrica REDDEDEBILIR (rate-limit /
# validation / unknown → sendCommandAck(id, false)). Eskiden bu NACK yalniz E-stop bekcisinde
# okunuyordu → manuel start reddedilse bile tedavi gecmisindeki kosu kaydi "kostu" olarak acik
# kaliyordu (hayalet kayit). Bekci E-stop deseninin aynisi: publish BLOKLANMAZ, onay arka planda.
#
# ⚠️ ASIMETRI KASITLI:
#   · NACK (success=false) → kosu kaydi KAPANIR (bobin hic baslamadi — kesin bilgi) + error.
#   · TIMEOUT (onay yok)   → kayit KALIR + yalniz uyari. Ack QoS-0'dir ve kaybolabilir;
#     onaysizlikta kaydi kapatmak, GERCEKTEN calisan bobinin dozunu kayittan silmek olurdu
#     (yanlis yonde hata). Fiziksel-calismiyor-olabilir uyarisi [1.1]'in isidir.
# ⚠️ Bu is GUVENLIK LIMITI isi DEGILDIR: backend'e freq/duty clamp'i EKLENMEZ (sahip karari,
# pemf-production-readiness). Kilit: tests/test_nack_gorunurlugu.py
_START_ACK_TIMEOUT = 2.0  # sn — E-stop bekcisiyle ayni sozlesme (testle kilitli)


def _start_ack_watch(coil_id: int, command_id: str, run_id=None) -> None:
    """Manuel ESP start onayini ARKA PLANDA izle (bkz. ustteki blok yorumu).

    ⚠️ run_id (denetim 2026-08-24, D2): bekci baslatildigi andaki kosu kaydinin id'si. NACK'te
    kosu YALNIZ hala BU run ise kapatilir — ayni bobine hizli ikinci bir start (KABUL edilmis) run'i
    devraldiysa, bu (bayat) NACK araya giren CALISAN kosuyu DUSURMEMELI."""
    _t0 = time.monotonic()
    confirmed = _wait_ack(command_id, timeout=_START_ACK_TIMEOUT)
    _gecikme_ms = int((time.monotonic() - _t0) * 1000)

    # SAHA 2026-09-08 (sahip): "PWM basladi mi anlamiyorum, sadece butona dokunuyorum." ESP8266 ack'i
    # ms icinde geliyor ve BASARI halinde yalniz debug-log'a dusuyordu; arayuz 'Aktif' rozetini 3 sn'lik
    # status telemetrisinden ogreniyordu. Uc sonuc da (onay / NACK / zaman asimi) tek `coil_ack` WS
    # olayi olarak yayinlanir -> panel "cihaz onayladi (NN ms)" / "REDDETTI" / "onay gelmedi" der.
    # HTTP yaniti degismez (PUBACK'ta doner; bekci arka planda). Kapi: tests/test_esp_ack_basari_gorunurlugu.py
    def _ack_yayinla(ok, neden: str) -> None:
        try:
            _ws_broadcast_sync(
                {
                    "type": "coil_ack",
                    "coilId": coil_id,
                    "data": {
                        "ok": ok,
                        "reason": neden,
                        "commandId": command_id,
                        "latencyMs": _gecikme_ms,
                        "ts": int(time.time() * 1000),
                    },
                }
            )
        except Exception:
            logging.getLogger(__name__).debug("coil_ack yayini basarisiz (bobin %s)", coil_id, exc_info=True)

    if confirmed is True:
        logging.getLogger(__name__).debug("start bobin %s: ESP onayladi (ack, %d ms)", coil_id, _gecikme_ms)
        _ack_yayinla(True, "ack")
        return
    if confirmed is False:
        _ack_yayinla(False, "nack")
        # ⚠️ 1-C inceleme i6-F-3: NACK'lenen komut bobinin GÜNCEL START'ı değilse (sonraki START devraldı — çalışıyor
        # olabilir) bobinin şimdiki durumunu SÖYLEMEZ: koşu kapatılmaz, "ÇALIŞMIYOR" denmez (ölçüldü: kabul edilmiş start#2
        # sürerken geciken NACK#1 `error` bildirimi üretiyordu). Kayıt yoksa (eski yol / doğrudan çağrı) GÜNCEL sayılır.
        with _pending_acks_lock:
            _guncel = _son_start_kimligi.get(coil_id, command_id) == command_id
        if not _guncel:
            logging.getLogger(__name__).warning(
                "start bobin %s: ONCEKI start %s reddedildi (NACK); sonraki komut gecerli — kosu kapatilmadi",
                coil_id,
                command_id,
            )
            try:
                _bildir(lambda d: ceviri.t("bildirim.startReddedildiSonraki", dil=d, coil=coil_id), "warning")
            except Exception:
                pass
            return
        # Kesin red: kosu kaydi hayalet — kapat. Sebep metni command_error eventiyle ayrica gelir.
        logging.getLogger(__name__).error(
            "start bobin %s: ESP komutu REDDETTI (NACK) — kosu kaydi kapatiliyor (hic kosmamis bobin)",
            coil_id,
        )
        try:
            # D2: yalniz BU start'in run'ini kapat (araya giren yeni start run'i devraldiysa dokunma).
            # ⚠️ 1-C inceleme i6-F-2: bu START koşu AÇMADIYSA (`run_id` None — seanssız tekil START, DB hıçkırığı)
            # kapatacağı koşu YOKTUR; `only_run_id=None` KOŞULSUZ kapat demekti → o an açık olan BAŞKA START'ın (ör.
            # arada açılan seansın) koşusu kapanıyordu (ölçüldü).
            if run_id is not None:
                _finish_coil_run(coil_id, only_run_id=run_id)
        except Exception:
            logging.getLogger(__name__).debug("NACK sonrasi run kapatma hatasi", exc_info=True)
        try:
            _bildir(
                lambda d: (
                    ceviri.t("bildirim.startReddedildi", dil=d, coil=coil_id)
                    + (ceviri.t("bildirim.kosuKaydiDuzeltildi", dil=d) if run_id is not None else "")
                ),
                "error",
            )
        except Exception:
            pass
        return
    logging.getLogger(__name__).warning(
        "start bobin %s: ESP onayi %.1f sn'de GELMEDI — bobin komutu almamis olabilir (kayit korunuyor)",
        coil_id,
        _START_ACK_TIMEOUT,
    )
    _ack_yayinla(None, "timeout")
    try:
        _bildir(lambda d: ceviri.t("bildirim.startOnayYok", dil=d, coil=coil_id), "warning")
    except Exception:
        pass


def _start_ack_izle_arka_planda(coil_id: int, command_id: str, publish_ok: bool, run_id=None) -> None:
    """Publish sonucu belliyken bekciyi baglar. Kayit publish'ten ONCE acilmis olmali (hizli ESP
    ack yarisi kaybolmasin — HG-4 deseni); publish dusmusse bekleyecek sey yok → kaydi temizle.

    run_id (D2): bekciye bu start'in kosu kaydi id'sini gecir → NACK yalniz KENDI run'ini kapatir."""
    if not publish_ok:
        with _pending_acks_lock:
            _pending_acks.pop(command_id, None)
        return
    try:
        threading.Thread(
            target=_start_ack_watch, args=(coil_id, command_id, run_id), daemon=True, name=f"start-ack-{coil_id}"
        ).start()
    except Exception:
        # Thread acilamazsa (kaynak tukenmesi) start akisi BOZULMAZ — yalniz izleme kaybolur.
        logging.getLogger(__name__).warning("start-ack bekcisi baslatilamadi (bobin %s)", coil_id, exc_info=True)
        with _pending_acks_lock:
            _pending_acks.pop(command_id, None)


def _esp_control_broadcast(command: str, id_prefix: str, extra: dict | None = None) -> None:
    """ESP bobinlerine (6-8) `pemf/coil/{id}/control`'e komut yayınlar.

    ⚠️ D-1 (donanım-uyum denetimi, 2026-08-19): selftest + reset_pwm eskiden ÖLÜ bir topiğe
    (`pemf/esp32_{id}/command`) yayınlıyordu — S3/8266 firmware'i `pemf/coil/{id}/control`'e abone,
    o topiğe DEĞİL. Sonuç: selftest ESP 6-8'de HİÇ çalışmıyor (arızalı ESP sessizce geçer = yanlış
    tanısal güvence); reset sonrası seans-dışı ESP bobini enerjili kalıyordu. STM (1-5) MQTT
    dinlemez (seri protokol) → kapsam yalnız ESP_COIL_IDS. E-stop yolu ayrıdır (kendi çift-yayını)."""
    for i in sorted(ESP_COIL_IDS):
        payload = {"command": command, "command_id": f"{id_prefix}_{i}_{int(time.time() * 1000)}"}
        if extra:
            payload.update(extra)
        try:
            _mqtt_publish(f"pemf/coil/{i}/control", payload)
        except Exception:
            logging.getLogger(__name__).debug("%s publish %d hatasi", id_prefix, i, exc_info=True)


def _estop_ack_watch(coil_id: int, command_id: str) -> None:
    """E-stop onayını ARKA PLANDA izle (publish'i bloklamadan). Onay 2 sn'de gelmezse operatörü
    AÇIKÇA uyar — bobin fiziksel durmamış olabilir (WiFi partition / cloud-failover senaryosu)."""
    confirmed = _wait_ack(command_id, timeout=2.0)
    if confirmed is True:
        logging.getLogger(__name__).info("E-stop bobin %s: ESP ONAYLADI (ack)", coil_id)
        return
    if confirmed is False:
        # [3.2]: ESP komutu AÇIKÇA REDDETTİ (success=false NACK) — eskiden bu dal da "(2s) ONAYI
        # GELMEDİ" diyordu: hem teşhis hem süre ibaresi yanlıştı (NACK anında döner). Operatör
        # doğru şeye bakmalı: sorun ağ/teslim değil, cihazın reddi.
        logging.getLogger(__name__).error(
            "E-stop bobin %s: ESP komutu REDDETTİ (NACK) — bobin fiziksel DURMAMIS olabilir, MANUEL KONTROL et.",
            coil_id,
        )
        try:
            _bildir(lambda d: ceviri.t("bildirim.estopEspReddetti", dil=d, coil=coil_id), "error")
        except Exception:
            pass
        return
    logging.getLogger(__name__).error(
        "E-stop bobin %s: ESP ONAYI GELMEDI (2s) — bobin fiziksel DURMAMIS olabilir, MANUEL KONTROL et.",
        coil_id,
    )
    try:
        _bildir(lambda d: ceviri.t("bildirim.estopEspOnayYok", dil=d, coil=coil_id), "error")
    except Exception:
        pass


# ── ESP KOMUT NİYETİ + HEDEFLİ RECONCILE (HG-6, Plan A-3, 2026-08-19) ─────────────────────────
# SORUN: ESP reboot'ta NVS/EEPROM'dan OTONOM devam eder; backend'in offline pencerede yayınladığı
# STOP retained olmadığından KAYBOLUR ve backend yalnız "bağlandı" der → bobin, backend'in haberi
# olmadan enerjili. ÇÖZÜM: backend'in her ESP'ye KOMUTLADIĞI son durum tek boğaz noktasında
# (_mqtt_publish) kaydedilir; ESP status'unda "çalışıyor" görülüp backend niyeti "çalışmıyor" ise
# (ve aktif seans o bobini kapsamıyorsa) HEDEFLİ STOP gönderilir. Retained-STOP YERİNE bu tercih
# edildi: retained STOP, yeniden bağlanan ESP'nin MEŞRU seansını da öldürürdü.
# Backend restart'ında kayıt boş (=hiçbirine start komutlanmadı) → NVS'den devam eden bobin
# yakalanır; backend_service açılış-reconcile'ı ile çift katman.
_esp_commanded_running: dict = {}
_esp_intent_lock = threading.Lock()
_reconcile_last_stop: dict = {}
_reconcile_last_notify: dict = {}  # coil_id -> monotonic (bildirim katlama: 5 dk'da bir)
_esp_stop_zamani: dict = {}  # coil_id -> monotonic (son STOP niyeti anı; F5 grace penceresi)
_RECONCILE_MIN_ARALIK_SN = 30.0
_RECONCILE_STOP_GRACE_SN = 10.0  # STOP sonrası uçuştaki 'running' status'ları sahte tetik sayma


def _kaydet_esp_komut_niyeti(topic: str, payload: dict, basarili: bool = False) -> None:
    """`pemf/coil/{id}/control`e giden start/stop = backend NİYETİ. ASİMETRİK kayıt (review F4):
    · STOP: publish SONUCUNDAN BAĞIMSIZ, HEMEN kaydedilir (basarili=False çağrısında) — başarısız
      STOP'ta niyet False kalmalı ki ESP yeniden görününce reconcile DENESİN. Anı damgalanır
      (F5 grace penceresi: stop'tan hemen sonra gelen uçuştaki 'running' status sahte tetiklemesin).
    · START: yalnız publish DOĞRULANINCA (basarili=True çağrısında) kaydedilir — başarısız start
      niyeti True bırakırsa, o bobinin NVS-resume hayaleti reconcile'dan süresiz muaf kalırdı
      (güvenlik ağının kendisini delen delik)."""
    try:
        parts = topic.split("/")
        if len(parts) != 4 or parts[0] != "pemf" or parts[1] != "coil" or parts[3] != "control":
            return
        cmd = str(payload.get("command", "")).lower()
        cid = int(parts[2])
        if cmd == "stop" and not basarili:
            with _esp_intent_lock:
                _esp_commanded_running[cid] = False
                _esp_stop_zamani[cid] = time.monotonic()
        elif cmd == "start" and basarili:
            with _esp_intent_lock:
                _esp_commanded_running[cid] = True
    except Exception:
        pass


def _reconcile_esp_calisiyor(coil_id: int, snapshot: dict) -> None:
    """ESP status'u 'çalışıyor' dedi; backend niyeti/seansı bunu KAPSAMIYORSA hedefli STOP.
    MQTT callback'inden çağrılır → publish ARKA PLANDA (callback'i ~7sn bloklamasın)."""
    if coil_id not in ESP_COIL_IDS or not snapshot.get("running"):
        return
    simdi = time.monotonic()
    with _esp_intent_lock:
        if _esp_commanded_running.get(coil_id, False):
            return  # backend zaten start komutladı — meşru çalışma
        # F5 (review): normal STOP'tan hemen sonra broker sırasında bekleyen 'running' status'lar
        # işlenir — bunlar hayalet değil, uçuştaki bayat rapor. Grace penceresinde tetikleme
        # (sahte "güvenlik durdurması" bildirimi = tıbbi cihazda alarm yorgunluğu).
        if simdi - _esp_stop_zamani.get(coil_id, -1e9) < _RECONCILE_STOP_GRACE_SN:
            return
    with _session_lock:
        sess_aktif = bool(_active_session.get("is_active"))
        sess_coils = _active_session.get("coil_ids") or list(range(1, 9))
    if sess_aktif and coil_id in sess_coils:
        return  # aktif seans kapsıyor (niyet kaydı seans yolunda da dolar ama çifte emniyet)
    with _esp_intent_lock:
        if simdi - _reconcile_last_stop.get(coil_id, 0.0) < _RECONCILE_MIN_ARALIK_SN:
            return  # hız sınırı: aynı bobine 30 sn'de en çok bir reconcile-STOP
        _reconcile_last_stop[coil_id] = simdi

    def _stop_gonder():
        # F3 (review): karar ile publish arası pencerede meşru bir start gelmiş olabilir —
        # publish'ten HEMEN önce niyeti ve seans kapsamını YENİDEN doğrula; yoksa reconcile-STOP
        # yeni başlamış meşru tedaviyi sessizce durdururdu (üstelik stop niyeti start'ı ezerdi).
        with _esp_intent_lock:
            if _esp_commanded_running.get(coil_id, False):
                return
        with _session_lock:
            s_aktif = bool(_active_session.get("is_active"))
            s_coils = _active_session.get("coil_ids") or list(range(1, 9))
        if s_aktif and coil_id in s_coils:
            return
        cid = f"reconcile_{coil_id}_{int(time.time() * 1000)}"
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {"command": "stop", "command_id": cid, "timestamp": time.time()},
        )
        logging.getLogger(__name__).warning(
            "RECONCILE: bobin %s beklenmedik 'calisiyor' raporladi (backend niyeti: durmus) -> hedefli STOP %s.",
            coil_id,
            "gonderildi" if ok else "GONDERILEMEDI (broker?)",
        )
        # Bildirim katlama (review 'sonraya' maddesi — alarm yorgunluğu): STOP'a rağmen ısrarla
        # "çalışıyor" diyen kalıcı hayalet 30 sn'de bir DEĞİL, 5 dk'da bir bildirilir (log hep yazar).
        simdi_n = time.monotonic()
        with _esp_intent_lock:
            bildir = simdi_n - _reconcile_last_notify.get(coil_id, -1e9) >= 300.0
            if bildir:
                _reconcile_last_notify[coil_id] = simdi_n
        if bildir:
            try:
                _bildir(lambda d: ceviri.t("bildirim.beklenmedikCalisiyordu", dil=d, coil=coil_id), "warning")
            except Exception:
                pass

    threading.Thread(target=_stop_gonder, name=f"reconcile-stop-{coil_id}", daemon=True).start()


def _estop_cloud_mirror(coil_ids, reason: str) -> None:
    """HG-5 (Plan A-2, 2026-08-19): E-stop'u BULUT broker'ına AYNALA — best-effort, arka plan.

    ESP'ler yerel broker 3 kez başarısız olunca HiveMQ cloud'a failover eder; backend ise yalnız
    127.0.0.1'e yayınlıyordu → buluta göçmüş ESP'ye E-stop HİÇ ulaşmıyordu. Bu ayna, aynı STOP'u
    buluta da yayınlar. Kimlik bilgileri SecretsManager'dan (mqtt_cloud_host/port/user/pass;
    generate=False — yoksa dosyaya rastgele değer YAZILMAZ, ayna sessizce devre dışı kalır ve
    bir kez loglanır). ESP davranışına dokunmaz; yerel E-stop yolunu BLOKLAMAZ (ayrı thread)."""
    try:
        from utils.secrets_manager import get_secret

        host = (get_secret("mqtt_cloud_host", default="", generate=False) or "").strip()
        user = (get_secret("mqtt_cloud_user", default="", generate=False) or "").strip()
        parola = get_secret("mqtt_cloud_pass", default="", generate=False)
        port_s = (get_secret("mqtt_cloud_port", default="8883", generate=False) or "8883").strip()
        if not host or not user or not parola:
            logging.getLogger(__name__).info(
                "E-stop bulut aynasi ATLANDI: mqtt_cloud_* sirlari tanimli degil (yalniz yerel yol)."
            )
            return
        import paho.mqtt.client as _pm

        c = _pm.Client(
            _pm.CallbackAPIVersion.VERSION2,
            client_id=_mqtt_client_id("estop-cloud"),
            clean_session=True,
        )
        c.username_pw_set(user, parola)
        c.tls_set()  # sistem CA deposu (HiveMQ cloud sertifikası genel CA'lıdır)
        c.connect(host, int(port_s), keepalive=10)
        c.loop_start()
        try:
            infolar = []
            for cid in coil_ids:
                komut_id = f"estopcloud_{cid}_{int(time.time() * 1000)}"
                for topic in (f"pemf/coil/{cid}/control", f"pemf/esp32_{cid}/command"):
                    infolar.append(
                        c.publish(
                            topic,
                            _json.dumps(
                                {"command": "stop", "command_id": komut_id, "emergency": True, "timestamp": time.time()}
                            ),
                            qos=1,
                        )
                    )
            # Toplam süre bütçesi (review 'sonraya' maddesi): 6 yayın × 3sn ayrı ayrı beklemek
            # ~20sn'e uzayabilirdi. Tek 8sn'lik bütçe — dolunca kalanlar beklenmeden sayılır.
            teslim = 0
            son_tarih = time.monotonic() + 8.0
            for info in infolar:
                kalan = son_tarih - time.monotonic()
                if kalan > 0:
                    try:
                        info.wait_for_publish(timeout=min(3.0, kalan))
                    except Exception:
                        pass
                if info.is_published():
                    teslim += 1
            logging.getLogger(__name__).warning(
                "E-stop BULUT aynasi (%s): %d/%d yayin teslim edildi (butce 8sn).", reason, teslim, len(infolar)
            )
        finally:
            c.loop_stop()
            c.disconnect()
    except Exception as e:
        logging.getLogger(__name__).warning("E-stop bulut aynasi basarisiz (yerel yol etkilenmez): %s", e)


def _broker_reachable(timeout: float = 0.3) -> bool:
    """MQTT broker (127.0.0.1:1883) hızlı erişilebilirlik sağlaması — ESP bobin yolunun
    broker kapalıyken sessizce 'success' dönmesini önlemek için (audit #4)."""
    import socket as _socket

    try:
        _c = _socket.create_connection(("127.0.0.1", 1883), timeout=timeout)
        _c.close()
        return True
    except Exception:
        return False


# ── Active session state (in-memory, shared) ─────────────────────────────────
import threading as _threading

# B-2.2 (son kademe): session state → servers/session_state.py. Alias'lar AYNI nesnelere işaret eder
# (dict/lock in-place; rebind normalize edildiğinden endpoint/watchdog/emergency gövdesi değişmedi).
_session_lock = session_state._session_lock
_active_session = session_state._active_session
# Sensör örnekleri aktif seans boyunca burada toplanır; /api/session/notes ve /api/session/stop ile
# gerçek session_id'ye (db_session_id) flush edilir.
_sensor_sample_buffer: list = []
_sensor_sample_buffer_lock = _threading.Lock()

# ── Asama-2: per-bobin run logging + dakika-ortalama aggregator state ──────────
# B-2.2: coil-run state + _begin/_finish_coil_run → servers/coil_run_tracker.py. Alias'lar AYNI
# nesnelere işaret eder (yalnız in-place mutasyon: start_session `.clear()` + sensör-loop akümülasyon).
_active_coil_runs = coil_run_tracker._active_coil_runs
_active_coil_runs_lock = coil_run_tracker._active_coil_runs_lock
_coil_run_stats = coil_run_tracker._coil_run_stats
_coil_run_stats_lock = coil_run_tracker._coil_run_stats_lock
# Per-coil dakika-akumulatoru (dakika-ortalama aggregator). Modul-duzeyi → /api/session/stop
# bekleyen kismi dakikayi flush'tan ONCE emit edebilsin. {coil_id: {t_sum,t_min,t_max,i_sum,b_sum,amb_sum,n,freq,duty,phase}}
_minute_acc: dict = {}
_minute_acc_lock = _threading.Lock()


def _get_treatment_db():
    """Asama-2 yardimci: kanonik app_data ile TreatmentHistoryDB singleton'ini getir.
    Hata halinde None (cagiranlar try/except ile sarmali; DB hatasi seansi/donanimi DURDURMAZ)."""
    try:
        from database.treatment_history_db import get_treatment_db

        return get_treatment_db(_app_data_dir())
    except Exception:
        logging.getLogger(__name__).debug("Treatment DB erisilemedi", exc_info=True)
        return None


def _kayit_db_hazir():
    """Tıbbi kayıt DB'si yazmaya hazır mı → (hazir: bool, sebep: str). ASLA istisna atmaz.

    ⚠️ DENETİM 2026-08-09 (ENGEL) — bu, `/api/health`'in `dbReady` alanının ve seans-başlatma
    kapısının TEK KAYNAĞIDIR. İkisinin ayrı hesaplaması, "sağlık yeşil ama seans reddediliyor"
    (ya da tersi) gibi teşhis edilemez bir tutarsızlık üretirdi.

    ⚠️ D1.37 (B-3.8): backend açılışında hasta YA DA tedavi DB'si açılamadıysa (göç bekliyor /
    fail-closed / bozuk) backend DB'siz açılır ve burası O NEDENLE `False` döner — HASTA DB'si tek
    başına açılamasa da. Launcher güncelleme onayında yalnız `dbReady`e bakar (`main.rs`
    `db_hazir_mi`); hasta DB'si göç beklerken `true` kalsaydı güncellemeyi onaylayıp `runtime.old`u
    silerdi (plan D1.37 orkestratör notu).
    """
    try:
        acilis = _db_acilis_hatasi()
        if acilis:
            return False, acilis
        db = _get_treatment_db()
        if db is None:
            return False, "veritabani acilamadi"
        return db.is_ready()
    except Exception as e:
        logging.getLogger(__name__).error("DB hazirlik kontrolu basarisiz: %s", e, exc_info=True)
        return False, str(e)[:200]


def _disk_kritik_sebebi_mi(sebep) -> bool:
    """`_kayit_db_hazir` nedeni disk-kritik mi (ön ek HER dilde; bkz. `treatment_history_db.disk_kritik_sebebi_mi`)."""
    from database.treatment_history_db import disk_kritik_sebebi_mi

    return disk_kritik_sebebi_mi(sebep)


def _db_acilis_hatasi() -> str:
    """Backend açılışında açılamayan DB'lerin operatöre gösterilecek nedeni ('' = yok). D1.37.

    Kaynak `HeadlessCore.db_acilis_hatalari` (yol / istisna ayrıntısı İÇERMEZ — `/api/health`
    auth-muaftır ve tünelden erişilebilir)."""
    hatalar = getattr(state.core, "db_acilis_hatalari", None)
    if not isinstance(hatalar, dict):  # çekirdek yok / sahte çekirdek (ör. MagicMock) → açılış hatası YOK
        return ""
    ayrintilar = getattr(state.core, "db_acilis_ayrintilari", None)
    parcalar = []
    for k in ("hasta", "tedavi"):
        s = hatalar.get(k)
        if not (isinstance(s, str) and s):
            continue
        a = ayrintilar.get(k) if isinstance(ayrintilar, dict) else None
        if a:  # yapılandırılmış ayrıntı varsa metin İSTEK dilinde (Türkçe: durum alanıyla bayt bayt aynı)
            from headless_core import db_acilis_metni

            s = db_acilis_metni(a[0], k, a[1])
        if s not in parcalar:  # #22: "erişim yok" iki DB için AYNI cümle — bir kez söylenir
            parcalar.append(s)
    return " ".join(parcalar)


def _lookup_owner_email(patient_uuid: str) -> str:
    """Hasta sahibinin e-postasini PatientDatabase'ten (UUID ile) getir. Bulunamazsa ''.
    Best-effort: hata seansi DURDURMAZ. ('raporu sahibe e-posta gonder' icin owner_email zinciri.)"""
    if not patient_uuid:
        return ""
    try:
        pdb = get_patient_database()
        if not pdb:
            return ""
        p = pdb.get_patient(patient_uuid)
        if not p:
            return ""
        return (p.get("owner_email") or "").strip()
    except Exception:
        logging.getLogger(__name__).debug("_lookup_owner_email hatasi", exc_info=True)
        return ""


# ── B-2.2: coil-run tracker (servers/coil_run_tracker.py) — bağımlılık injection + fonksiyon alias ──
# coil_run_tracker'a aktif-seans DB-id getter'ını enjekte et (session_state sahibi; kilitli okuma).
coil_run_tracker.set_db_session_id_getter(session_state.current_db_session_id)
# lambda (fonksiyon-referansı DEĞİL) → _get_treatment_db monkeypatch'i/yeniden-bağlaması çağrı-anında görülür.
coil_run_tracker.set_treatment_db_getter(lambda: _get_treatment_db())
_begin_coil_run = coil_run_tracker._begin_coil_run
_finish_coil_run = coil_run_tracker._finish_coil_run


def _bobin_suresi_doldu(bobinler) -> None:
    """D1.68 (B-1.6): HC yazılım süre kapağı bobini durdurdu → koşu kaydı da kapanır (kaydedilen = uygulanan).

    Keep-alive iş parçacığından çağrılır: yalnız o anki koşu kimliklerini alır (bellek), DB yazımı AYRI iş parçacığında
    (yavaş DB keep-alive'ı bekletirse firmware ölü-adamı seansın diğer bobinlerini keser). Yalnız O koşu kapanır
    (`only_run_id`): araya aynı bobine yeni bir START girmişse yeni koşuya dokunulmaz."""
    with _active_coil_runs_lock:
        hedef = [(int(c), _active_coil_runs.get(int(c))) for c in bobinler]
    hedef = [(c, r) for c, r in hedef if r is not None]
    if not hedef:
        return

    def _kapat():
        for c, r in hedef:
            try:
                _finish_coil_run(c, only_run_id=r)
            except Exception:
                logging.getLogger(__name__).warning("sure kapagi: kosu kaydi kapatilamadi (bobin %s)", c, exc_info=True)

    try:
        threading.Thread(target=_kapat, name="sure-kapagi-kayit", daemon=True).start()
    except Exception:
        logging.getLogger(__name__).error("sure kapagi: kayit is parcacigi acilamadi (kosu kaydi acik kalabilir)")


try:
    from controllers import hardware_controller as _hc_modul

    _hc_modul.sure_doldu_kancasi_bagla(_bobin_suresi_doldu)
except Exception:
    logging.getLogger(__name__).warning("D1.68: sure kapagi kancasi baglanamadi", exc_info=True)


@app.post("/api/hardware/auto_preset")
async def auto_preset(payload: AutoPresetPayload):
    """
    Yapay Zeka skoruna göre (veya literatür hedefine göre)
    donanım parametrelerini otomatik ayarlar.
    """
    if not state.core:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.cekirdekHazirDegil"))

    try:
        from pathlib import Path

        from ai.hybrid_recommender import get_literature_recommendation

        app_data = Path.home() / ".pemf_gui"
        rec = get_literature_recommendation(payload.target_condition, app_data_dir=app_data)

        freq = float(rec.get("freq", 10.0))
        duty = float(rec.get("duty", 25.0))
        duration = float(rec.get("duration", 20.0))

        # GÜVENLİK: auto_preset SADECE parametre ÖNERİSİ döndürür — donanımı BAŞLATMAZ.
        # Fiziksel başlatma yalnız /api/session/start üzerinden (seans + kayıt + E-stop mandalı / STM başlatma kapıları;
        # tedavi clamp'i YOK — Y9 · termal interlock YOK — A-47).
        # (Eskiden burada start_all_coils yan-etkisi vardı → chip'e dokununca bobinler ateşleniyordu.)
        return {
            "status": "success",
            "parameters": {"freq": freq, "duty": duty, "duration": duration, "source": rec.get("source", "unknown")},
        }
    except ImportError:
        raise HTTPException(status_code=501, detail=ceviri.t("ai.hata.onericiYok"))
    except Exception:
        # B3 güvenlik-fix: ham str(e) istemciye SIZMAZ (bilgi ifşası) — sunucuda logla, generic dön.
        logging.getLogger(__name__).exception("AI öneri hesaplanamadı")
        raise HTTPException(status_code=500, detail=ceviri.t("ai.hata.oneriHatasi"))


def _eski_komut_baslatma_parametreleri(p: dict, varsayilan_sure_dk: int) -> dict:
    """D1.96 (B-1.33 · S-1.5): eski `/api/hardware/command` START parametrelerini TİPLİ doğrular → 422 (yanıtta ham
    değer yok, B-10.148). Eskiden ham `params` sözlüğü doğrudan `update_coil`'e gidiyordu: 0,5 dk `int()` ile 0'a
    kesilip HC'nin 120 dk'lık GÖZETİMSİZ kapağına düşüyordu (30 sn istenip 120 dk), sayı olmayan frekans sessizce
    100 Hz oluyordu, kesirli bobin kimliği 500 veriyordu.
    Süre: TAM dakika [0, protokol üstü] (0 = gözetimsiz varsayılan — eski sözleşme). Bobin: STM aralığında tam sayı.
    Frekans/duty/faz: sonlu sayı; donanıma gidecek değerler TEK kaynaktan (`_surus_parametrelerini_dogrula_422`).
    ⚠️ YALNIZ START: STOP yolları (stop_coil, stop_all_coils, 0 Hz = STOP) bu doğrulamadan GEÇMEZ (Ö.4-Y8)."""
    import math as _m

    from utils.stm32_protocol_limits import DURATION_MAX_MINUTES

    def _sayi(ad, varsayilan):
        v = p.get(ad, varsayilan)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not _m.isfinite(float(v)):
            raise HTTPException(status_code=422, detail=ceviri.t("donanim.hata.sayiGecersiz", ad=ad))
        return float(v)

    def _tam(ad, varsayilan, alt, ust):
        f = _sayi(ad, varsayilan)
        if f != int(f) or not (alt <= f <= ust):
            raise HTTPException(
                status_code=422, detail=ceviri.t("donanim.hata.tamSayiGecersiz", ad=ad, alt=alt, ust=ust)
            )
        return int(f)

    v = {
        "coil_id": _tam("coil_id", 1, 1, max(STM_COIL_IDS)),
        "freq": _sayi("freq", 100.0),
        "duty": _sayi("duty", 25.0),
        "phase": _sayi("phase", 0.0),
        "sure_dk": _tam("duration", varsayilan_sure_dk, 0, DURATION_MAX_MINUTES),
    }
    v["uyg"] = _surus_parametrelerini_dogrula_422(v["freq"], v["duty"], v["phase"], v["sure_dk"])
    return v


@app.post("/api/hardware/command")
async def hardware_command(payload: CommandPayload):
    """
    Eskiden bir PyQt6 butonuna tıklandığında yapılan işlemi buraya aktarır.
    Örn: MainWindow.start_treatment() -> /api/hardware/command {command: 'start_treatment'}
    """
    if not state.core or not state.hardware:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.cekirdekDonanimHazirDegil"))
    # D1.81 · Y4: START komutları mandallıyken 409 (try'ın DIŞINDA — aşağıdaki geniş except onu 500'e çevirirdi).
    # Asıl kapı `HardwareController`dadır; stop_coil / stop_all_coils buraya ASLA takılmaz (Ö.4-Y8).
    # 1-C inceleme i3-F-4 (A-05): 0 Hz BAŞLATMA = STOP — mandal 409'u ona UYGULANMAZ (HC onu STOP olarak işler; eskiden
    # mandallıyken 0 Hz start_coil/start_all_coils 409 ile STOP'suz dönüyordu).
    from controllers.hardware_controller import sifir_hz_durdurma_mi

    if str(payload.command or "").lower() in ("start_coil", "start_all_coils") and not sifir_hz_durdurma_mi(
        (payload.params or {}).get("freq", 100.0)
    ):
        _engel = estop_mandali.baslatma_engeli(estop_mandali.niyet_nesli())  # varış damgası (i1-F2)
        if _engel:
            raise HTTPException(status_code=409, detail=_engel)

    try:
        cmd = payload.command.lower()
        p = payload.params

        if cmd == "start_coil":
            coil_id = p.get("coil_id", 1)
            freq = p.get("freq", 100.0)
            if sifir_hz_durdurma_mi(freq):  # A-05: 0 Hz = STOP — tipli doğrulamaya TAKILMAZ (Ö.4-Y8); eski yol aynen
                success = state.hardware.update_coil(coil_id, freq, 0, 0, 0, start=True)
                return {"status": "success" if success else "error", "command": cmd, "coil_id": coil_id}
            # D1.96 (B-1.33): tipli parametre (422) + kabul edilen başlatma KOŞU KAYDI açar (aktif seansta; tekil uçla aynı).
            v = _eski_komut_baslatma_parametreleri(p, 0)
            coil_id = v["coil_id"]
            success = state.hardware.update_coil(coil_id, v["freq"], v["duty"], v["phase"], v["sure_dk"], start=True)
            if success:
                _begin_coil_run(coil_id, v["uyg"]["freq"], v["uyg"]["duty_yuzde"], v["uyg"]["faz"], None, "stm")
            return {"status": "success" if success else "error", "command": cmd, "coil_id": coil_id}

        elif cmd == "stop_coil":
            coil_id = p.get("coil_id", 1)
            _ai_pro_plandan_cikar([coil_id])  # Y54 (STOP'tan ÖNCE; istisna atmaz)
            _ucustaki_baslatmayi_gecersiz_kil([coil_id])  # 1-C inceleme i1-F5 (STOP'tan ÖNCE; istisna atmaz)
            success = state.hardware.update_coil(coil_id, 0, 0, 0, 0, start=False)
            return {"status": "success" if success else "error", "command": cmd, "coil_id": coil_id}

        elif cmd == "stop_all_coils":
            _isaret, _sira_once = _stm_yazim_isareti_al(), _stm_son_stop_sirasi_al()
            success = state.hardware.stop_all_coils()
            # 1-C §9 #2 (A-63): teyit = STOP porta YAZILDI (E-stop'la aynı ölçüt). Kuyruğa verildi ama yazılamadıysa
            # (kablo çıkık / ölü gönderici) "success" DENMEZ — "partial" + `stmStopped:false`. Yalnız RAPOR.
            # O-1.1: teyit beklemesi KENDİ iş parçacığında — ortak havuz doluyken yanıt (ve istemcinin yedek adımı) takılmaz.
            _yazildi = bool(success) and await _durdurma_is_parcaciginda(
                _stm_stop_porta_yazildi_mi, _isaret, _sira_once, ad="stop-all-teyit"
            )
            return {
                "status": ("success" if _yazildi else "partial") if success else "error",
                "command": cmd,
                "stmStopped": _yazildi,
            }

        elif cmd == "start_all_coils":
            freq = p.get("freq", 100.0)
            if sifir_hz_durdurma_mi(freq):  # A-05: 0 Hz = TÜM bobinler için STOP — doğrulamaya TAKILMAZ (Ö.4-Y8)
                success = state.hardware.start_all_coils(freq, 0, 0, 0)
                return {"status": "success" if success else "error", "command": cmd}
            v = _eski_komut_baslatma_parametreleri({**p, "coil_id": 1}, 30)  # D1.96: tipli (bobin kimliği yok)
            success = state.hardware.start_all_coils(v["freq"], v["duty"], v["phase"], v["sure_dk"])
            if success:  # D1.96: aktif seansta TÜM STM bobinlerinin koşusu kaydedilir (eskiden 7 bobin kayıtsız)
                for _cid in sorted(STM_COIL_IDS):
                    _begin_coil_run(_cid, v["uyg"]["freq"], v["uyg"]["duty_yuzde"], v["uyg"]["faz"], None, "stm")
            return {"status": "success" if success else "error", "command": cmd}

        else:
            return {"status": "error", "message": ceviri.t("donanim.hata.bilinmeyenKomut", cmd=cmd)}

    except HTTPException:
        raise  # D1.96: 422 geçersiz parametre — aşağıdaki genel 500'e çevrilmesin
    except Exception:
        # B3 güvenlik-fix: ham str(e) SIZMAZ — sunucuda logla, generic dön.
        logging.getLogger(__name__).exception("Donanım komutu başarısız")
        raise HTTPException(status_code=500, detail=ceviri.t("donanim.hata.komutBasarisiz"))


@app.post("/api/hardware/selftest")
async def trigger_hardware_selftest():
    """Tüm bobinlere SELFTEST komutu gönderir (fire-and-forget)."""
    import threading

    if not state.hardware:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.hazirDegil"))

    # 8× _mqtt_publish (her biri connect-publish-disconnect) SANİYELER sürebilir → HTTP yanıtını
    # BEKLETME (eskiden await → istemci timeout'u "gönderilemedi" gösteriyordu, HTTP 000). Arka-plan
    # daemon thread'de best-effort gönder, yanıtı hemen dön ("komut gönderildi" semantiği).
    # D-1 (2026-08-19): ESP'nin GERÇEKTEN dinlediği topiğe (`pemf/coil/{id}/control`) yayınla.
    # STM (1-5) MQTT selftest'i dinlemez → kapsam ESP_COIL_IDS. (8266'da SELFTEST handler'ı ayrı
    # bir eksik — tezgah maddesi; backend artık en azından doğru kapıya çalıyor.)
    threading.Thread(
        target=lambda: _esp_control_broadcast("SELFTEST", "selftest"),
        name="hw-selftest",
        daemon=True,
    ).start()
    return {"status": "success", "message": "Self-test commands sent."}


@app.post("/api/hardware/reset_pwm")
async def reset_all_pwms():
    """Tüm bobinleri durdurur ve duty 0 olarak reset atar (fire-and-forget)."""
    if not state.hardware:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.hazirDegil"))
    import threading

    # stop_all_coils (STM seri I/O; STM yoksa retry→saniyeler) + 8× _mqtt_publish (connect-publish) →
    # HTTP yanıtını BEKLETME (eskiden await → timeout / HTTP 000). Arka-plan thread'de yürüt, hemen dön.
    # Birincil güvenlik yolu /hardware/emergency_stop'tur; bu yalnız bakım-reset'idir.
    def _reset_all():
        try:
            state.hardware.stop_all_coils()  # STM 1-5 (seri)
        except Exception:
            logging.getLogger(__name__).debug("reset_pwm stop_all_coils hatasi", exc_info=True)
        # D-1 (2026-08-19): ESP 6-8'e ESP'nin dinlediği topiğe AÇIK "stop" (eskiden ölü esp32_
        # topiğine "start duty:0" gidiyordu → seans-dışı ESP bobini enerjili kalıyordu).
        _esp_control_broadcast("stop", "reset")

    threading.Thread(target=_reset_all, name="hw-reset-pwm", daemon=True).start()
    return {"status": "success", "message": "All PWM signals reset."}


@app.post("/api/hardware/cleanup_esp")
async def cleanup_stale_esp():
    """Zaman aşımına uğramış ESP cihazlarını temizler."""
    with _live_state_lock:
        for idx in range(5, 8):
            coil = _live_state["coils"][idx]
            if not coil.get("connected"):
                coil["running"] = False
    return {"status": "success", "message": "Stale ESP state cleaned."}


# ── Per-coil MQTT control (direct ESP command via MQTT) ───────────────────────
#: TD6 · K3: tekil bobin BAŞLATMASINDA kartın yanıtı en çok bu kadar beklenir (121 B @115200 ≈ 10,5 ms + kartın satırı).
_STM_BASLATMA_YANIT_BEKLEME_S = 0.5


def _stm_yanit_tabani():
    """TD6 · K3: kart yanıtı sayacı (komuttan ÖNCE) — izi bildirmeyen çekirdekte None (bekleme yapılmaz)."""
    _f = getattr(getattr(state.hardware, "core", None), "stm_yanit_sayaci", None)
    if not callable(_f):
        return None
    try:
        return int(_f())
    except Exception:
        return None


async def _stm_baslatma_kart_yaniti(coil_id: int, duty_yuzde: float, taban) -> str:
    """TD6 · K3 (tezgâh Oturum 13): tekil bobin başlatmasına kartın yanıtı — bu bobinin duty TAVANI reddi gelirse operatörün
    EYLEM metni (`live_state.stm_duty_reddi_metni`), aksi "".

    ÖLÇÜLEN: kart %80'i (çift yönlü) reddettiği hâlde API `success` dönüyordu; bobin başlamıyor, sebep görünmüyordu. Yanıt
    İÇERİKLE eşlenir (önceki canlı tutma paketinin yanıtı karışmasın): bu bobinin duty reddi → ret; bu bobini istenen duty ile
    ÇALIŞIR gösteren `STM_OK` → kabul (beklemeyi erken bitirir); süre dolarsa bugünkü anlam DEĞİŞMEZ. Kıskaç YOK (Ö.4-Y9)."""
    if taban is None:
        return ""
    core = getattr(state.hardware, "core", None)
    _sonra = getattr(core, "stm_yanitlari_sonra", None)
    _ack_coz = getattr(core, "_parse_stm_ok", None)
    if not callable(_sonra):
        return ""
    bitis = time.monotonic() + _STM_BASLATMA_YANIT_BEKLEME_S
    while True:
        try:
            yanitlar = _sonra(taban)
        except Exception:
            return ""
        for tur, satir in yanitlar:
            if tur == "nack":
                r = live_state.stm_duty_reddi_coz(satir)
                if r is not None and r["bobin"] == int(coil_id):
                    return live_state.stm_duty_reddi_metni(satir)
            elif callable(_ack_coz):
                try:
                    for u in _ack_coz(satir):
                        if (
                            int(u.get("coil_id", 0)) == int(coil_id)
                            and u.get("running")
                            and abs(float(u.get("duty", 0.0)) - float(duty_yuzde)) <= 1.0
                        ):
                            return ""
                except Exception:
                    pass
        if time.monotonic() >= bitis:
            return ""
        await asyncio.sleep(0.02)


@app.post("/api/coil/{coil_id}/control")
async def control_single_coil(coil_id: int, payload: CoilControlPayload):
    """Send a start/stop command to a coil.

    Duration convention:
    - API/MQTT payload duration is seconds (ESP-compatible).
    - STM32 firmware duration is minutes, converted only for HardwareController.
    """
    if coil_id < 1 or coil_id > 8:
        raise HTTPException(status_code=400, detail=ceviri.t("donanim.hata.bobinKimligi"))

    # ⚠️ D1.53 (B-1.10 · A-05): 0 Hz BAŞLATMA = bu bobin için STOP (arayüzün "parkla" isteği) — STM ve ESP
    # dallarının İKİSİNDE de, protokol sınırına (`normalize_*_frequency_hz`, Ö.4-Y9 — KALDIRILMAZ) ULAŞMADAN.
    # Eskiden 1 Hz'e çekilip istenen duty ile SÜRÜLÜYOR ve koşu kaydı "0 Hz" açılıyordu.
    from controllers.hardware_controller import sifir_hz_durdurma_mi

    _sifir_hz = bool(payload.start) and sifir_hz_durdurma_mi(payload.freq)
    if _sifir_hz:
        payload.start = False
    if not payload.start:  # 1-C inceleme i1-F5: bobin STOP'u uçuştaki seans başlatmasını iptal ettirir (STOP'tan ÖNCE)
        _ai_pro_plandan_cikar([coil_id])  # Y54: AI Pro bu bobini sonraki karede yeniden sürmesin
        _ucustaki_baslatmayi_gecersiz_kil([coil_id])
    # D1.81 · Y4: acil durdurma MANDALLIYKEN ya da isteğin VARIŞINDAN sonra durdurma geldiyse START 409 + neden.
    # Asıl kapı donanım düzeyindedir (`HardwareController`, `_esp_start_yayinla` — varış damgasıyla, kilit altında);
    # bu yalnız operatöre nedeni söyler. STOP buraya ASLA takılmaz.
    if payload.start:
        _engel = estop_mandali.baslatma_engeli(estop_mandali.niyet_nesli())
        if _engel:
            raise HTTPException(status_code=409, detail=_engel)
    _uyg: dict = {}
    if payload.start:  # D1.95: taşan girdi durum yazılmadan 422 · D1.99: kayıt GİDEN değeri yazar
        _uyg = _surus_parametrelerini_dogrula_422(
            payload.freq,
            payload.duty,
            payload.phase,
            _duration_seconds_to_stm_minutes(payload.duration),
            payload.duration,
        )

    command_id = _komut_kimligi("react", coil_id)  # D1.E10: ms tek başına çakışır

    if coil_id in STM_COIL_IDS:
        if not state.hardware:
            raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.stmHazirDegil"))
        stm_duration_min = _duration_seconds_to_stm_minutes(payload.duration)
        _yanit_tabani = _stm_yanit_tabani() if payload.start else None  # TD6 · K3: komuttan ÖNCE
        _stm_sonuc = state.hardware.update_coil(
            coil_id,
            payload.freq,
            payload.duty,
            payload.phase,
            stm_duration_min,
            start=payload.start,
            # DENETIM P3: STM firmware suresi DAKIKA granulerliginde oldugundan saniye→dakika
            # donusumu YUKARI yuvarlanir (30 sn → 1 dk = 2x fazla tedavi). Firmware icin bu dogru
            # (yarida kesmez); ama yazilim deadline'i monotonik SANIYE tuttugundan gercek sureyi
            # tam uygulayabilir → hassas saniyeyi de gecir. Firmware 1 dk'lik yedek kapak kalir.
            duration_seconds=payload.duration,
        )
        # DENETIM 2. TUR [4.5] (2026-08-20): update_coil'in donusu ESKIDEN yok sayiliyordu —
        # parametre reddinde (state DEGISMEDI, bobin surulmedi) hem tedavi gecmisine "kostu"
        # yaziliyor hem istemciye "success" donuyordu. Kosu kaydi yalniz KABUL edilen start'ta;
        # STOP'ta finish HER halde calisir (acik kaydi kapatmak guvenli taraftir).
        _stm_kabul = bool(_stm_sonuc)
        # TD6 · K3 (tezgâh Oturum 13): kart bu bobinin duty'sini REDDETTİYSE "success" DÖNÜLMEZ ve koşu kaydı açılmaz; operatör
        # nedeni ve eylemi görür. Yalnız START bekler (≤ 0,5 sn); STOP ASLA beklemez (Ö.4-Y8).
        _kart_red_metni = ""
        if payload.start and _stm_kabul:
            _kart_red_metni = await _stm_baslatma_kart_yaniti(coil_id, payload.duty, _yanit_tabani)
            if _kart_red_metni:
                _stm_kabul = False
        if payload.start:
            if _stm_kabul:
                _begin_coil_run(coil_id, _uyg["freq"], _uyg["duty_yuzde"], _uyg["faz"], None, "stm")  # D1.99
        else:
            _finish_coil_run(coil_id)
        _stm_yanit = {
            "status": "success" if _stm_kabul else "error",
            "command_id": command_id,
            "transport": "stm32",
        }
        if _sifir_hz:
            _stm_yanit["sifirHzDurdurma"] = True  # D1.53: istek DURDURMA olarak uygulandı
        if _kart_red_metni:
            _stm_yanit["kartReddetti"] = True
            _stm_yanit["mesaj"] = _kart_red_metni
        return _stm_yanit

    if payload.start:
        # D-3 (2026-08-19): ESP DDS 1000 Hz üstünü süremez (firmware constrain) → önden normalize.
        # STM yolu (yukarıda) update_coil içinde normalize_frequency_hz uygular; ESP yolu HAM
        # gönderiyordu → >1000 komut ESP'de SESSİZCE kırpılıp komut≠telemetri sapması yaratıyordu.
        from utils.stm32_protocol_limits import normalize_esp_frequency_hz

        esp_freq = normalize_esp_frequency_hz(payload.freq)
        # HG-3 üçüncü katman (2026-08-19): STM referans bobini (1) çalışırken frekansı, istenen
        # ESP frekansının ≳50 katıysa PB1 senkron darbeleri ESP periyot-başı penceresine düşer →
        # DC-yapışma rejimi (S3 latch'i ~8 darbede keser ama o pencerede DC akar; firmware PB1
        # artık duty=0'da susturuldu — bu uyarı ÇALIŞAN coil1 senaryosunu kapatır). REDDETMEZ
        # (operatör bilinçli olabilir), operatörü AÇIKÇA uyarır + yanıtında taşır.
        _sync_uyari = None
        try:
            with _live_state_lock:
                _c1 = dict(_live_state["coils"][0])
            if _c1.get("running") and float(_c1.get("frequencyHz") or 0) >= 50.0 * max(esp_freq, 1.0):
                _sync_args = {"hz": _c1.get("frequencyHz"), "coil": coil_id, "esp_freq": esp_freq}
                _sync_uyari = ceviri.t("donanim.uyari.fazSenkron", **_sync_args)
                _bildir(lambda d: "⚠️ " + ceviri.t("donanim.uyari.fazSenkron", dil=d, **_sync_args), "warning")
        except Exception:
            _sync_uyari = None
        mqtt_payload = {
            "command": "start",
            "command_id": command_id,
            "freq": esp_freq,
            "duty": payload.duty,
            "phase": payload.phase,
            # Gozetimsiz kapak (bkz. _esp_duration_seconds): `0` = "sure belirtilmedi" nobetcisi
            # SURESIZ demektir ve ESP tarafinda hicbir sunucu-yanli watchdog yok.
            "duration": _esp_duration_seconds(payload.duration),
        }
    else:
        esp_freq = payload.freq
        _sync_uyari = None
        mqtt_payload = {"command": "stop", "command_id": command_id}

    # [4.5] NACK yarisi (2026-08-22): onay kaydi publish'ten ONCE acilir (hizli ESP ack yarisi
    # kaybolmasin — HG-4 deseni). Bekci publish sonucuna gore asagida baglanir.
    if payload.start:
        _register_ack(command_id, bobin=coil_id)
    # P0 audit 2026-06-28: senkron _mqtt_publish (~7sn worst-case) event-loop'u bloklamasin → to_thread.
    # D1.81 · Y4: START mandal/nesil kapılı yayından geçer (telafi STOP'u dahil); STOP doğrudan.
    if payload.start:
        ok = await asyncio.to_thread(_esp_start_yayinla, coil_id, mqtt_payload)
    else:  # O-1.1: STOP yayını KENDİ iş parçacığında (ortak havuz doluyken sıra beklemez)
        ok = await _durdurma_is_parcaciginda(
            _mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload, ad=f"esp-stop-{coil_id}"
        )
    # Asama-2: per-bobin run logging (ESP/MQTT dali). Loglanan freq = ESP'ye GİDEN (normalize) değer.
    # [4.5]: kosu kaydi yalniz DOGRULANMIS publish'te — broker oluyken komut KESIN gitmedi;
    # "kostu" yazmak hic kosmamis bobini tedavi gecmisine sokar. STOP'ta finish her halde.
    if payload.start:
        _esp_run_id = None
        if ok:
            _begin_coil_run(coil_id, esp_freq, payload.duty, payload.phase, None, "esp")
            _esp_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
        # NACK gelirse bekci bu kaydi kapatir; timeout'ta kayit korunur (bkz. _start_ack_watch).
        _start_ack_izle_arka_planda(coil_id, command_id, ok, _esp_run_id)
    else:
        _finish_coil_run(coil_id)
    _yanit = {"status": _esp_yanit_durumu(ok), "command_id": command_id, "transport": "mqtt"}
    if _sync_uyari:
        _yanit["sync_warning"] = _sync_uyari
    if _sifir_hz:
        _yanit["sifirHzDurdurma"] = True  # D1.53: istek DURDURMA olarak uygulandı
    return _yanit


@app.post("/api/coil/surus_kipi")
async def set_surus_kipi(payload: SurusKipiPayload):
    """STM bobinlerinin bipolar/unipolar sürüş kipini ayarlar.

    ⚠️ ATOMİK SEVK: kip alanı pakete 2026-09-11'de eklendi (120 → 121 bayt). Kart ESKİ
    firmware ile koşuyorsa TÜM paketler CRC'den düşer — bu uç değil, tüm sürüş durur.
    Bu yüzden firmware ve backend birlikte sevk edilir.

    ⚠️ Kip yalnız SÜRÜŞ anında karta gider: hiç bobin çalışmıyorsa keep-alive paket
    göndermez (kasıtlı — boşta UART sessiz). Yanıttaki `etkin` bu yüzden "kaydedildi"
    demektir, "karta ulaştı" değil; gerçekleşen kip ACK `K=` → canlı durum `unipolar`.
    """
    if not state.hardware:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.stmYok"))
    n = len(STM_COIL_IDS)
    if len(payload.unipolar) != n:
        _uni = {"n": n, "ilk": min(STM_COIL_IDS), "son": max(STM_COIL_IDS), "gelen": len(payload.unipolar)}
        raise HTTPException(
            status_code=400,
            detail=ceviri.t("donanim.hata.unipolarDizisi", **_uni),
        )
    maske = 0
    for i, u in enumerate(payload.unipolar):
        if u:
            maske |= 1 << i
    uygulanan = state.hardware.surus_kipi_ayarla(maske)
    # YETENEK TAVANI: bobin 6-7 bipolar sürülemez → istek ne olursa olsun etkin kip unipolar.
    # Bunu burada da hesaplayıp döndürüyoruz ki arayüz, kart hiç paket almadan da (boşta)
    # düğmenin GERÇEKTE ne yapacağını gösterebilsin. Kart konuşunca ACK `K=` bunun üstüne yazar.
    yetenek = 0
    with _live_state_lock:
        for idx in range(n):
            if not _live_state["coils"][idx].get("bipolarYetenek", True):
                yetenek |= 1 << idx
    etkin = uygulanan | yetenek
    # T-c (Tezgâh-2 #6): kayıtlı istek canlı duruma — yeniden açılan / başka istemcideki Sürüş Kipi kutuları bundan başlar.
    update_live_coil_kip_istegi(etkin, n)
    return {
        "status": "success",
        "istek": [bool((uygulanan >> i) & 1) for i in range(n)],
        "etkin": [bool((etkin >> i) & 1) for i in range(n)],
        "maske": etkin,
    }


@app.post("/api/coil/batch")
async def control_batch_coils(payload: BatchCoilPayload):
    """Send the same command to multiple coils at once.

    Duration convention:
    - API/MQTT payload duration is seconds (ESP-compatible).
    - STM32 firmware duration is minutes, converted only for HardwareController.
    """
    # D1.53 (A-05): 0 Hz BAŞLATMA = seçili bobinler için STOP (tekil uçla AYNI kural ve gerekçe).
    from controllers.hardware_controller import sifir_hz_durdurma_mi

    _sifir_hz = bool(payload.start) and sifir_hz_durdurma_mi(payload.freq)
    if _sifir_hz:
        payload.start = False
    if not payload.start:  # 1-C inceleme i1-F5 — tekil uçla aynı
        _ai_pro_plandan_cikar(payload.coil_ids)  # Y54 — tekil uçla aynı
        _ucustaki_baslatmayi_gecersiz_kil(payload.coil_ids)
    if payload.start:  # D1.81 · Y4 — gerekçe tekil uçta (varış damgası); STOP asla takılmaz
        _engel = estop_mandali.baslatma_engeli(estop_mandali.niyet_nesli())
        if _engel:
            raise HTTPException(status_code=409, detail=_engel)
    _b_uyg: dict = {}
    if payload.start:  # D1.95: taşan girdi HİÇBİR bobin sürülmeden 422 · D1.99: kayıt GİDEN değeri yazar
        _b_uyg = _surus_parametrelerini_dogrula_422(
            payload.freq,
            payload.duty,
            payload.phase,
            _duration_seconds_to_stm_minutes(payload.duration),
            payload.duration,
        )

    results = []
    # Audit P3: coil_ids'i max 8 BENZERSİZE sınırla — {coil_ids:[6]*5000} her ID için sıralı
    # to_thread(_mqtt_publish ~2sn) + DB yazımıyla broker/threadpool'u bombalayıp gerçek coil-kontrolünü
    # geciktiriyordu (uzunluk/dedup kısıtı yoktu).
    _seen = []
    for _c in payload.coil_ids:
        if _c not in _seen:
            _seen.append(_c)
    for coil_id in _seen[:8]:
        if coil_id < 1 or coil_id > 8:
            results.append({"coilId": coil_id, "status": "invalid"})
            continue
        command_id = _komut_kimligi("react_batch", coil_id)  # D1.E10
        if coil_id in STM_COIL_IDS:
            if not state.hardware:
                results.append({"coilId": coil_id, "status": "stm_unavailable"})
                continue
            stm_duration_min = _duration_seconds_to_stm_minutes(payload.duration)
            _b_stm_sonuc = state.hardware.update_coil(
                coil_id,
                payload.freq,
                payload.duty,
                payload.phase,
                stm_duration_min,
                start=payload.start,
                # DENETIM P3: STM firmware suresi DAKIKA granulerliginde oldugundan saniye→dakika
                # donusumu YUKARI yuvarlanir (30 sn → 1 dk = 2x fazla tedavi). Firmware icin bu dogru
                # (yarida kesmez); ama yazilim deadline'i monotonik SANIYE tuttugundan gercek sureyi
                # tam uygulayabilir → hassas saniyeyi de gecir. Firmware 1 dk'lik yedek kapak kalir.
                duration_seconds=payload.duration,
            )
            # Asama-2: per-bobin run logging.
            # [4.5]: kosu kaydi + satir durumu update_coil'in donusune bagli (tekil yolla ayni) —
            # reddedilen start batch satirinda "success" gorunmesin, gecmise "kostu" yazilmasin.
            _b_stm_kabul = bool(_b_stm_sonuc)
            if payload.start:
                if _b_stm_kabul:
                    _begin_coil_run(coil_id, _b_uyg["freq"], _b_uyg["duty_yuzde"], _b_uyg["faz"], None, "stm")  # D1.99
            else:
                _finish_coil_run(coil_id)
            results.append(
                {"coilId": coil_id, "status": "success" if _b_stm_kabul else "invalid", "transport": "stm32"}
            )
            continue
        if payload.start:
            # D-3 batch tamamlayıcısı (review, 2026-08-19 akşam): tek-bobin yolu normalize
            # ederken batch HAM freq gönderiyordu — "kısmi düzeltme" deseninin ta kendisi.
            # Tek-bobin yoluyla AYNI normalize + AYNI ≳50× sync uyarısı.
            from utils.stm32_protocol_limits import normalize_esp_frequency_hz as _nesp

            _b_esp_freq = _nesp(payload.freq)
            _b_uyari = None
            try:
                with _live_state_lock:
                    _bc1 = dict(_live_state["coils"][0])
                if _bc1.get("running") and float(_bc1.get("frequencyHz") or 0) >= 50.0 * max(_b_esp_freq, 1.0):
                    _b_args = {"hz": _bc1.get("frequencyHz"), "coil": coil_id, "esp_freq": _b_esp_freq}
                    _b_uyari = ceviri.t("donanim.uyari.fazSenkronKisa", **_b_args)
                    _bildir(lambda d: "⚠️ " + ceviri.t("donanim.uyari.fazSenkronKisa", dil=d, **_b_args), "warning")
            except Exception:
                _b_uyari = None
            mqtt_payload = {
                "command": "start",
                "command_id": command_id,
                "freq": _b_esp_freq,
                "duty": payload.duty,
                "phase": payload.phase,
                # Tek-bobin yoluyla AYNI kapak (bkz. _esp_duration_seconds). Batch'i atlamak, bu
                # deponun bir kez yandigi "kismi duzeltme" desenini tekrarlamak olurdu.
                "duration": _esp_duration_seconds(payload.duration),
            }
        else:
            _b_esp_freq = payload.freq
            _b_uyari = None
            mqtt_payload = {"command": "stop", "command_id": command_id}
        # [4.5] NACK yarisi: tekil yolla AYNI bekci — batch'i atlamak deponun bir kez yandigi
        # "kismi duzeltme" desenini tekrarlamak olurdu.
        if payload.start:
            _register_ack(command_id, bobin=coil_id)
        # P0 audit 2026-06-28: senkron _mqtt_publish event-loop'u bloklamasin → to_thread.
        # D1.81 · Y4: START mandal/nesil kapılı yayından geçer (telafi STOP'u dahil); STOP doğrudan.
        if payload.start:
            ok = await asyncio.to_thread(_esp_start_yayinla, coil_id, mqtt_payload)
        else:  # O-1.1: STOP yayını KENDİ iş parçacığında (ortak havuz doluyken sıra beklemez)
            ok = await _durdurma_is_parcaciginda(
                _mqtt_publish, f"pemf/coil/{coil_id}/control", mqtt_payload, ad=f"esp-stop-{coil_id}"
            )
        # Asama-2: per-bobin run logging (ESP/MQTT dali) — loglanan freq = ESP'ye GIDEN (normalize).
        # [4.5]: kosu kaydi yalniz DOGRULANMIS publish'te (tekil yolla ayni gerekce).
        if payload.start:
            _b_run_id = None
            if ok:
                _begin_coil_run(coil_id, _b_esp_freq, payload.duty, payload.phase, None, "esp")
                _b_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
            _start_ack_izle_arka_planda(coil_id, command_id, ok, _b_run_id)
        else:
            _finish_coil_run(coil_id)
        _satir = {"coilId": coil_id, "status": _esp_yanit_durumu(ok), "transport": "mqtt"}
        if _b_uyari:
            _satir["sync_warning"] = _b_uyari
        results.append(_satir)
    if _sifir_hz:
        return {"status": "success", "results": results, "sifirHzDurdurma": True}
    return {"status": "success", "results": results}


# ── Session management ────────────────────────────────────────────────────────
async def _baslatma_hatasinda_kapat(benim_seans, neden: str, teyitli_ek: str) -> None:
    """`/session/start` beklenmeyen istisnasında seansı TUTARLI kapat ve 503 FIRLAT (İNC-2 §10 #2 + 1-E açık #9).

    KENDİ seansı hâlâ aktifse NORMAL durdurma yolu (`stop_session`: uçuştaki başlatma → TÜM seans bobinlerine STOP, satır
    `cancelled` / "İptal Edildi"); Ö.4-Y8: STOP yalnız artar, kapılanmaz. ⚠️ 1-E incelemesi (i-18.1): `stop_session` teyitsiz
    STOP'ta FIRLATMAZ, 409 yanıtı DÖNDÜRÜR — eskiden yok sayılıp "durduruldu" deniyordu (ölçüldü) → teyitsizse yanıt ACİL
    DURDUR'u söyler."""
    with _session_lock:
        _hala_benim = bool(_active_session.get("is_active")) and _active_session.get("session_id") == benim_seans
    _teyitsiz = False
    if _hala_benim:
        _durdurma = await stop_session()
        _teyitsiz = getattr(_durdurma, "status_code", 200) == 409
    with _session_lock:
        if _active_session.get("session_id") == benim_seans:
            _active_session["baslatma_ucusta"] = False  # başlatma bitti (başarısız) — bayrak da TUTARLI iner
    raise HTTPException(
        status_code=503,
        detail=(
            ceviri.t("seans.hata.stopDogrulanamadi", neden=neden)
            if _teyitsiz
            else ceviri.t("seans.hata.nedenVe", neden=neden, ek=teyitli_ek)
        ),
    )


@app.post("/api/session/start")
async def start_session(payload: SessionStartPayload, request: Request):
    """Start a new treatment session."""
    import time

    # ⚠️ D1.81 (B-5.3 · Y4): START NİYETİ isteğin VARIŞ anındaki nesli taşır (`_SurusNiyetiVarisDamgasi`; gövde
    # okunmadan önce — i1-F2). Aşağıdaki DB yazımı (await) sırasında gelen bir durdurma ya da acil durdurma nesli
    # artırır → bobin START'ları `HardwareController`da DURUM KİLİDİ ALTINDA reddedilir (mevcut `_still_active`
    # denetimi bunu yalnız denetim ANINA kadar kapatıyordu: denetle-sonra-yap).
    _niyet_nesli = estop_mandali.niyet_nesli()
    _giris_engeli = estop_mandali.baslatma_engeli(_niyet_nesli)
    if _giris_engeli:
        # ⚠️ 1-C inceleme i3-F-4 (A-05 · Y4): 0 Hz isteği bir DURDURMADIR — mandal yalnız START'ı engeller. Eskiden
        # mandallıyken 0 Hz seans isteği 409 ile STOP'SUZ dönüyordu (ölçüldü: mandal öncesi 2 STOP paketi → 0). İstenen
        # bobinlere STOP gönderilir (STOP gönderimi yalnız ARTAR, Ö.4-Y8); seans AÇILMAZ, DB satırı yazılmaz.
        from controllers.hardware_controller import sifir_hz_durdurma_mi

        if sifir_hz_durdurma_mi(payload.frequency):
            _durdur = [c for c in dict.fromkeys(payload.coil_ids or []) if 1 <= c <= 8] or list(range(1, 9))
            if not live_state.esp_etkin():  # seans yoluyla aynı: ESP kapalıyken hayalet bobin 8'e STOP/alarm yok
                _durdur = [c for c in _durdur if c not in ESP_COIL_IDS]
            _bildir_teyitsiz_stop(
                await _durdurma_is_parcaciginda(_stop_session_coils, _durdur, ad="sifir-hz-durdur"),  # O-1.1
                lambda d: ceviri.t("bildirim.kaynak.sifirHz", dil=d),
            )
            raise HTTPException(status_code=503, detail=sifir_hz_seans_mesaji())
        raise HTTPException(status_code=409, detail=_giris_engeli)

    # ⚠️ 2026-08-09 (Tier 1): kaydın SAHİBİNE sunucu karar verir (bkz. auth.cozumlenmis_operator).
    # Beyanı doğrudan yazmak, cihaza erişen herkesin başka bir hekim adına seans açmasına izin
    # veriyordu; seansın denetim izi (`session_started` olayı) de o adla imzalanıyordu.
    from servers.auth import cozumlenmis_operator, cozumlenmis_operator_adi

    _operator_kimligi = cozumlenmis_operator(request, payload.operator_email)
    from utils.profil import istek_profili

    _profil_istek = istek_profili(request)  # SG.G1
    # ⚠️ D2.41 (B-2.19): ADI da aynı kurala bağlı — e-posta sahipsiz düşerken `operator_name` beyanı seans satırına ve
    # `session_started` izine kayıtlı bir hekimin adını yazıyordu (ölçüldü). Jetonluda kayıtlı görünen ad; Kural 2'de beyan.
    _operator_adi = cozumlenmis_operator_adi(_operator_kimligi, payload.operator_name)
    # D1.95 (B-1.13 · B-1.16): taşan parametre seans KURULMADAN 422 (eskiden bobin başına patlayıp seansı yarım bırakırdı).
    _s_uyg = _surus_parametrelerini_dogrula_422(
        payload.frequency, payload.duty, payload.phase, payload.duration_minutes
    )
    # Derinlemesine savunma (Pydantic max_length=8 sinirda zaten reddeder): tekrarlari at ve
    # gecerli bobin araligina (1-8) filtrele → /api/coil/batch'teki `_seen[:8]` deseniyle ayni.
    _seen_coils = []
    for _c in payload.coil_ids or []:
        if 1 <= _c <= 8 and _c not in _seen_coils:
            _seen_coils.append(_c)
    coil_ids = _seen_coils or list(range(1, 9))
    stm_coils = [coil_id for coil_id in coil_ids if coil_id in STM_COIL_IDS]
    esp_coils = [coil_id for coil_id in coil_ids if coil_id in ESP_COIL_IDS]

    # ⚠️ HAYALET BOBİN KAYDI (sahip bildirimi 2026-09-12) ──────────────────────────────
    # "seans detayında donanım eps kalmış ve bobin 8 de görünüyor ama aslında çalışmıyor,
    # 7 bobinli sistem."
    #
    # ÖLÇÜLEN KÖK NEDEN: `_mqtt_publish` ESP kapalıyken HİÇ yayınlamıyor (doğru), ama aşağıdaki
    # ESP döngüsü `_begin_coil_run(...)`ı KOŞULSUZ çağırıyordu. Sonuç: bobin 8 için tedavi
    # geçmişine "46 sn · 100 Hz · %50 · ESP" satırı yazılıyordu — ortada o donanım YOKKEN.
    # Üstelik bobin kimliği verilmeyen seans `list(range(1, 9))`e düştüğü için bu, VARSAYILAN
    # yoldu: her seans bir hayalet bobin-8 kaydı üretiyordu.
    #
    # ⚠️ ESP KODU SİLİNMİYOR, YALNIZ KAPILANIYOR: `PEMF_ESP_ENABLED=1` ile eski davranış
    # bütünüyle geri gelir (sahip kararı 2026-09-11: "ilerde tekrar hibrit esp+stm'e dönebilirim").
    if esp_coils and not live_state.esp_etkin():
        logging.getLogger(__name__).info(
            "ESP bobinleri %s seans kapsamindan CIKARILDI (ESP alt sistemi kapali) — hayalet kosu kaydi yazilmaz.",
            esp_coils,
        )
        esp_coils = []
        coil_ids = [c for c in coil_ids if c not in ESP_COIL_IDS]
    if stm_coils and not state.hardware:
        raise HTTPException(status_code=503, detail=ceviri.t("donanim.hata.stmHazirDegil"))

    # ⚠️ SAHTE "BAŞARILI" SEANS KAPISI (sahip bildirimi 2026-09-12) ────────────────────
    # "bobinler komut almicak bildirimi gelmesine ... rağmen seans başlatınca gerçekten
    # başlıyormuş gibi her şey sorunsuz devam ediyor."
    #
    # ⚠️ NEDEN ÜSTTEKİ KONTROLLER YETMİYORDU: `state.hardware` VAR ve seri port AÇIK, yazma
    # BAŞARILI. Paketi reddeden kartın KENDİSİDİR ve bunu asenkron `STM_NACK: CRC` ile söyler.
    # "Yazabildim" ile "bobin çalıştı" arasındaki boşluk tam buraya düşüyordu: seans başlıyor,
    # sayaç işliyor, geçmişe "Tamamlandı" yazılıyordu — hiçbir bobin enerjilenmemişken.
    # D1.52 (B-1.4): aynı iki kapı (red + uyumsuz firmware) artık `HardwareController`ın başlatma
    # kapısında da var (tekil/batch/hardware-command/AI yolları); burada önden 409 + neden verilir.
    #
    # ⚠️ YALNIZ STM BOBİNİ İSTENDİĞİNDE KAPILANIR: ESP bobini (varsa) ayrı bir yoldan gider
    # ve bu reddin konusu değildir. Ayrıca kapı SADECE BAŞLATMADADIR — durdurma/E-stop
    # yolları bundan geçmez (kopuk/uyuşmaz kartta tedaviyi durduramamak asıl tehlike olurdu).
    if stm_coils and live_state.stm_komutlari_reddediyor():
        logging.getLogger(__name__).error(
            "Seans REDDEDILDI — STM kart komutlari reddediyor (son red: %s).",
            live_state.stm_red_ozeti().get("son_mesaj", "")[:80],
        )
        # Y74 / 1-G §8 #2: son red DUTY reddiyse eylem duty'dir (mandal kuruluysa + 'Sıfırla'), firmware uyuşmazlığı DEĞİL.
        raise HTTPException(
            status_code=409,
            detail=live_state.stm_red_duty_metni(ceviri.t("seans.sonuc.baslatilmadi")) or stm_red_mesaji(),
        )

    # ⚠️ FIRMWARE UYUM KAPISI (2026-09-18) — YUKARIDAKININ ONLEYICI IKIZI ────────────────
    # Ustteki kapi TEPKISELDIR: kart komutlari reddetmeye BASLADIKTAN sonra (NACK gorulunce)
    # devreye girer. Bu kapi ONLEYICIDIR: kart acilista KIM OLDUGUNU zaten soyluyor
    # (`-> STM_READY: DDS v2.3 (7-ch ...)`) ve o satir bugune kadar OKUNMUYORDU. Kanal sayisi
    # bizim paket genisligimizle tutmuyorsa bobinlerin calismayacagi ONCEDEN bellidir —
    # operatoru seansi baslatip NACK beklemeye zorlamanin anlami yok.
    #
    # ⚠️ YALNIZ KESIN UYUMSUZLUKTA (`is False`) reddedilir. Banner taninmadiysa deger `None`
    # kalir ve seans ENGELLENMEZ: ileride banner bicimi degisen UYUMLU bir firmware de
    # taninmayabilir ve calisan bir kligini durdurmak cozdugumuz sorundan buyuk zarar olurdu.
    #
    # ⚠️ SADECE BASLATMADA: durdurma ve acil-durdurma yollari buradan GECMEZ (uyumsuz kartta
    # tedaviyi durduramamak asil tehlike olurdu).
    if stm_coils and getattr(state.core, "stm_uyumlu", None) is False:
        _sebep = getattr(state.core, "stm_uyumsuzluk_sebebi", "") or "Firmware kanal sayisi uyusmuyor."
        logging.getLogger(__name__).error("Seans REDDEDILDI — firmware kimligi uyumsuz: %s", _sebep)
        # TD1 · K1: operatöre SADE metin + kod (teknik sebep günlükte ve `/api/health` `stmUyumsuzlukSebebi`nde — destek).
        raise HTTPException(status_code=409, detail=ceviri.t("seans.hata.baslatilmadiNeden", neden=stm_red_mesaji()))

    # ⚠️ DENETİM 2026-08-09 (ENGEL) — KAYITSIZ TEDAVİ ARTIK BAŞLAMAZ.
    # Aşağıdaki DB yazımları bilinçli olarak "best-effort"tur (DB hatası bobinleri durdurmasın).
    # Ama BAŞLANGIÇTA bunun sonucu şuydu: DB hiç açılamıyorken bile seans başlıyor, bobinler
    # enerjileniyor, tedavi uygulanıyor ve db_session_id=None kaldığı için seans satırı,
    # coil-run'lar ve sensör telemetrisinin HİÇBİRİ yazılmıyordu — operatöre tek bir uyarı
    # bile çıkmadan. Hastanın aldığı doz geriye dönük OLARAK BİLİNEMEZ hâle geliyordu.
    # Kapı YALNIZ BAŞLATMADADIR: /session/stop, /hardware/emergency_stop ve bobin durdurma
    # yolları BU KONTROLDEN GEÇMEZ — DB çökükken tedaviyi durduramamak asıl tehlike olurdu.
    # Ayrıca seans ORTASINDA DB düşerse tedavi kesilmez (eski best-effort davranışı korunur).
    _db_ok, _db_sebep = _kayit_db_hazir()
    if not _db_ok:
        logging.getLogger(__name__).error("Seans REDDEDILDI — tibbi kayit DB'si hazir degil: %s", _db_sebep)
        _acilis_sebebi = _db_acilis_hatasi()  # D1.37: göç bekliyorsa operatör NEDENİ görür
        _detay = ceviri.t("seans.hata.kayitDbAcilamadi")
        if _acilis_sebebi:
            _detay += ceviri.t("seans.hata.kayitDbNeden", sebep=_acilis_sebebi)
        elif _disk_kritik_sebebi_mi(_db_sebep):
            # D1.77 (B-3.9): disk doluyken "yeniden başlatın" YANLIŞ eylemdir — operatöre gerçek nedeni ve eylemi söyle.
            _detay = ceviri.t("seans.hata.baslatilamazNeden", sebep=_db_sebep)
        raise HTTPException(status_code=503, detail=_detay)

    # Güncelleme uygulanıyorken YENİ seans başlatma: installer servisi durdurup EXE'yi
    # değiştirebilir → başlayan tedavi bobinleri kontrolcüsüz bırakabilir. (update_manager
    # TOCTOU guard'ının TERS yönü — apply, başlamış tedaviyi zaten _has_active_treatment ile
    # reddeder; bu da apply penceresinde yeni tedaviyi reddeder.)
    try:
        from servers import update_manager as _um

        if _um.is_update_in_progress():
            raise HTTPException(status_code=409, detail=ceviri.t("seans.hata.guncellemeSuruyor"))
    except HTTPException:
        raise
    except Exception:
        pass

    with _session_lock:
        # D2-4.1: geri yükleme sürerken açılan seansın satırı içe aktarmanın silme adımında gider
        if _VERI_TASIMA_KILIDI.locked():
            raise HTTPException(status_code=409, detail=geri_yukleme_surerken_seans())
        if _active_session.get("is_active"):
            raise HTTPException(status_code=409, detail=ceviri.t("seans.hata.zatenAktif"))

        # B-2.2: REBIND (`_active_session = {...}`) yerine IN-PLACE (clear+update) → dict kimliği
        # sabit kalır (session_state alias'lanabilir); davranış aynı (kilit altında atomik).
        _active_session.clear()
        _active_session.update(
            {
                "is_active": True,
                "session_id": _yeni_seans_muhru(),
                "patient_id": payload.patient_id,
                "patient_name": payload.patient_name,
                "operator_name": _operator_adi,
                "mode": payload.mode,
                "target_condition": payload.target_condition,
                "frequency": payload.frequency,
                "duty": payload.duty,
                "intensity": payload.intensity,
                "phase": payload.phase,
                "duration_minutes": payload.duration_minutes,
                "start_time": time.time(),
                # DENETIM P2: sure-watchdog DUVAR SAATI farkiyla calisiyordu. NTP duzeltmesi/DST/
                # elle saat degisimi ILERI giderse seans ERKEN kesilir, GERI giderse planlanandan
                # UZUN surer (maruziyet artar). start_time istemciye/gosterime gittigi icin epoch
                # olarak KORUNDU; guvenlik karari icin AYRI monotonic isaret kullanilir.
                "start_mono": time.monotonic(),
                "started_epoch": time.time(),
                "coil_ids": coil_ids,
                "db_session_id": None,  # Asama-2: seans BASINDA olusan gercek int DB session_id
                "db_patient_id": None,
                # D1.80 (B-5.1): seansın TÜRÜ — `mode` serbest metindir ve YETKİ VERMEZ ("AI…" önekli elle seans
                # `/frame`'i AÇMAZ). D1.81: niyet nesli (bu seansın sürüşleri ona bağlı).
                "tur": "manuel",
                "surus_nesli": _niyet_nesli,
                # 1-C inceleme i1-F5: başlatma UÇUŞTA — bu seansın bobinine gelen STOP nesli artırır; sürüş sonrası
                # denetimde `_session_lock` altında iner (bkz. `_ucustaki_baslatmayi_gecersiz_kil`).
                "baslatma_ucusta": True,
            }
        )
        # ⚠️ 1-C inceleme i1-F3 / i2-F1: bu başlatmanın MÜHRÜ. Aşağıdaki DB await'i sırasında Durdur (ya da E-stop +
        # Sıfırla) ve YENİ bir seans gelebilir; await sonrasındaki HER adım (DB damgası, tampon temizliği, iptal, geri
        # alma) yalnız `_active_session` hâlâ BU mühürse koşar — başka seansın durumuna dokunmaz.
        _benim_seans = _active_session["session_id"]
    # ⚠️ 1-E açık #9 (İNCELEME-2 §10 #2 devamı): başlatma bayrağı kurulduktan SONRA, bobin sürüşünden ÖNCEKİ bölgede
    # (denetim izi, sahip e-postası, DB satırı, artık koşular, ESP döngüsü) beklenmeyen istisna uçtan 500'le kaçıyor,
    # seans `is_active` + `baslatma_ucusta` KALIYORDU (sonraki seans 409, açılmış DB satırı `active`). Sürüş hatasıyla
    # AYNI kapanış: KENDİ seansı hâlâ aktifse normal durdurma yolu (TÜM seans bobinlerine STOP, satır `cancelled`), 503.
    # Bilinçli HTTPException'lar (409 vb.) ve `return`ler etkilenmez.
    try:
        # Denetim izi (audit P1) — seansı HEMEN kalıcılaştır: kim (operatör) + ne zaman + hangi
        # parametreler. Eskiden seans yalnız SONDA DB'ye yazılıyordu → backend seans ortasında
        # çökerse hiçbir kayıt kalmıyordu ve operatör kimliği hiç tutulmuyordu. session_events
        # append-only olduğundan bu, ana seans satırı sonradan yazılsa da bağımsız kanıt sağlar.
        try:
            # P1 audit 2026-06-28: get_treatment_db() ARGUMANSIZ cagriliyordu (imza app_data_dir
            # zorunlu) → TypeError → except yutuyordu → session_started AUDIT IZI HIC yazilmazdi.
            # _get_treatment_db() sarmalayicisi app_data_dir gecer (dosyadaki diger cagrilarla tutarli).
            # ⚠️ C2-4.1 (2-C incelemesi · Ö.4-Y8): bu yazım OLAY DÖNGÜSÜNDE koşuyordu; tedavi DB'si kilitliyken döngü
            # `busy_timeout` kadar donuyor, ACİL DURDUR bekliyordu (ölçüldü: 4,4 sn). Döngüde FIFO işçide, en çok 0,25 sn
            # beklenerek (kayıt kaybolmaz; yeni `await` noktası YOK — başlatma akışının atomikliği değişmez).
            from utils import dongu_disi_yazim as _dongu_disi

            _dongu_disi.calistir(
                _get_treatment_db().record_session_event,
                None,
                "session_started",
                payload={
                    "ref": _active_session["session_id"],
                    "operator_name": _operator_adi,
                    "operator_email": _operator_kimligi,
                    "patient_id": payload.patient_id,
                    "mode": payload.mode,
                    "frequency": payload.frequency,
                    "duty": payload.duty,
                    "intensity": payload.intensity,
                    "phase": payload.phase,
                    "duration_minutes": payload.duration_minutes,
                    "coil_ids": coil_ids,
                },
                severity="info",
                ad="session_started izi",
            )
        except Exception:
            logging.getLogger(__name__).warning("Seans başlangıç audit kaydı yapılamadı.", exc_info=True)

        # Best-effort: DB hatasi seansi/donanimi DURDURMASIN → db_session_id=None kalir (eski davranis).
        # P-1 fix: senkron SQLCipher yazimlari (upsert_patient/start_session/set_meta/set_param) event-loop'u
        # BLOKLAMASIN → tumu tek to_thread'de; hizli lock-update (db_session_id) async'te sonrasinda yapilir.
        _started_epoch_snap = _active_session.get("started_epoch")
        # C2-2.9: Hasta Özeti kartının hasta kaydı da bu iş parçacığında okunur (sürüşten sonra döngüde okunuyordu).
        _hasta_kaydi: dict = {}

        def _persist_session_start():
            # ⚠️ C2-2.9 (2-C inceleme · Ö.4-Y8): hasta DB işleri (sahip e-postası, son tedavi damgası, Hasta Özeti kaydı) OLAY
            # DÖNGÜSÜNDE senkron koşuyordu — hasta DB'si kilitliyken (`busy_timeout` 5 sn; toplu silme `PatientDatabase.lock`'u
            # tutarken 10 sn) uçuştaki başlatma ACİL DURDUR'u ve donanım STOP'unu 5–10 sn bekletiyordu (ölçüldü). Artık bu iş
            # parçacığında; yeni `await` noktası EKLENMEZ (mühür denetimleri ve sürüş sonrası atomik bölge değişmez).
            # Asama-2 (1a): seans BASINDA gercek DB satirini ac (coil-run + sensor ona baglanir).
            # Sahip e-postasini hasta kayittan (patient_id=UUID) cek — "raporu sahibe e-posta gonder"
            # icin history'de session.owner_email dolu gelsin. Best-effort (yoksa bos string).
            owner_email = _lookup_owner_email(payload.patient_id)
            # KVKK retention (2026-06-28): bu tedavi icin hastanin last_treatment_at'ini guncelle
            # (inaktiflik sayaci → 5 yil sonra anonimlestirme bunu baz alir).
            if payload.patient_id:
                try:
                    _pdb = get_patient_database()
                    if _pdb is not None:
                        _pdb.touch_last_treatment(payload.patient_id)
                except Exception:
                    logging.getLogger(__name__).debug("touch_last_treatment hatasi", exc_info=True)
                try:
                    _pdb = get_patient_database()
                    _hasta_kaydi["kayit"] = _pdb.get_patient(payload.patient_id) if _pdb else None
                except Exception:
                    logging.getLogger(__name__).debug("Hasta Özeti snapshot lookup hatasi", exc_info=True)
            db = _get_treatment_db()
            if db is None:
                return None, None
            _pid = None
            if payload.patient_name:
                try:
                    _pid = db.upsert_patient(
                        {
                            "name": payload.patient_name,
                            "patient_uuid": (payload.patient_id or None),
                            "owner_email": (owner_email or None),
                        }
                    )
                except Exception:
                    logging.getLogger(__name__).debug("upsert_patient hatasi", exc_info=True)
            _sid = db.start_session(
                treatment_mode=payload.mode,
                target_condition=payload.target_condition or None,
                operator_name=_operator_adi or None,
                patient_name=payload.patient_name or None,
                # ⚠️ 2026-08-09 (Tier 1): e-posta İSTEMCİ BEYANINDAN değil, doğrulanmış operatör
                # jetonundan gelir. Beyan yalnız cihazda kayıtlı operatör YOKKEN kabul edilir.
                operator_email=_operator_kimligi or None,
                # SG.G1: seansın açıldığı arayüz profili (görünüm ayrımı; erişim kapısı DEĞİL). Bildirilmezse boş → türetilir.
                profil=_profil_istek,
            )
            # Yeni kolonlar (start_session bunlari yazmaz): gercek baslangic epoch + patient_id FK.
            # ⚠️ Y116: seansın REÇETESİ (frekans / şiddet) de BURADA, sunucunun bildiği değerle yazılır — doz kaydı seansın
            # kendi kaydıdır; `/api/session/notes` artık hiçbir dalda doz yazmaz (eskiden reçete satıra yalnız oradan,
            # istemcinin gövdesinden giriyordu — bitmiş seansta kimliksiz LAN isteği 50 → 999 Hz yapabiliyordu).
            try:
                db.set_session_meta(
                    _sid,
                    started_epoch=_started_epoch_snap,
                    patient_id=_pid,
                    frequency_hz=(payload.frequency or None),
                    intensity_mt=(payload.intensity or None),
                )
            except Exception:
                logging.getLogger(__name__).debug("set_session_meta(start) hatasi", exc_info=True)
            # Sahip e-postasini seans-parametresi olarak yaz (history JOIN'i bunu okur).
            if owner_email:
                try:
                    db.set_session_parameter(_sid, "patient_owner_email", owner_email, "")
                except Exception:
                    logging.getLogger(__name__).debug("set_session_parameter(owner_email) hatasi", exc_info=True)
            # ⚠️ DENETİM İZİNİ SEANSA BAĞLA (kampanya bulgusu S11, 2026-08-15).
            # `session_started` olaylarında `session_events.session_id` NULL'dur ve bu KASITLIDIR:
            # olay, DB seans satırı OLUŞMADAN ÖNCE yazılır (önce-iz-sonra-satır). Ama bağlantı
            # hiçbir yerde kurulmuyordu → "bu denetim kaydı hangi seansa ait?" cevapsız kalıyordu.
            #
            # ⚠️ BAĞLANTI TERS YÖNDE KURULUR: `session_events`e SONRADAN UPDATE ATILMAZ — o tablo
            # append-only'dir ve sıralama bilinçlidir. Bunun yerine mühür seans satırına yazılır.
            # Böylece yeni DB metodu, denetim tablosuna UPDATE ve `delete_session` semantiğinde
            # değişiklik GEREKMEZ. Join: session_parameters.parameter_value ==
            # json_extract(session_events.payload,'$.ref').
            #
            # ⚠️ DÜRÜST SINIR: bu, silinen bir seansın `session_events` payload'unda kalan
            # patient_id/operator_email artığını (KVKK) ÇÖZMEZ — "iz seansla birlikte silinsin mi?"
            # ayrı bir sahip kararıdır ve bu düzeltme onu cevaplamadan uygulanabilir.
            try:
                _ref = (_active_session or {}).get("session_id")
                if _ref:
                    db.set_session_parameter(_sid, "audit_ref", str(_ref), "")
            except Exception:
                logging.getLogger(__name__).debug("set_session_parameter(audit_ref) hatasi", exc_info=True)
            return _sid, _pid

        sid = None
        try:
            sid, patient_id = await asyncio.to_thread(_persist_session_start)
            if sid is not None:
                with _session_lock:
                    # Yalniz hala BU seans aktifse yaz (arada /stop — ya da Durdur/E-stop + Sifirla + YENI seans — gelmis
                    # olabilir; i1-F3: kimlik bakilmadan yeni seansin db_session_id'si bu satirla EZILIYORDU).
                    if _active_session.get("is_active") and _active_session.get("session_id") == _benim_seans:
                        _active_session["db_session_id"] = sid
                        _active_session["db_patient_id"] = patient_id
        except Exception:
            logging.getLogger(__name__).warning("Seans DB satiri olusturulamadi (db_session_id=None).", exc_info=True)
        # ⚠️ Y65 (sahip, 1-F inceleme S-İF1): tedavi kaydının DB satırı AÇILAMADIYSA seans BAŞLAMAZ — bobin sürülmeden 503.
        # Eskiden (önceden var) yalnız günlüğe yazılıp seans `db_session_id=None` ile SÜRÜLÜYORDU: seans/koşu/sensör kaydı
        # hiç oluşmuyordu (kaydedilen ≠ uygulanan; D1.77 "kayıtsız tedavi başlamaz"). Neden: DB > 5 sn meşgul (seans
        # bitiminde koşan ertelenmiş KVKK VACUUM'u, Y62) ya da başka bir DB hatası. Seans aktif BIRAKILMAZ (yeniden deneme
        # 409 almaz). STOP ve ACİL DURDUR bu kapıdan GEÇMEZ (Ö.4-Y8).
        if sid is None:
            with _session_lock:
                if _active_session.get("session_id") == _benim_seans:
                    _active_session["is_active"] = False
                    _active_session["baslatma_ucusta"] = False
            logging.getLogger(__name__).error("Seans REDDEDILDI — tedavi kaydi (DB satiri) acilamadi (Y65).")
            raise HTTPException(status_code=503, detail=kayit_acilamadi_mesaji())

        # Audit P1 (TOCTOU): DB-persist await'i sırasında eşzamanlı /stop is_active=False yapmış olabilir.
        # Bobinleri ENERJİLEMEDEN ÖNCE yeniden doğrula — aksi halde bobinler fiziksel açılır ama
        # _active_session.is_active=False kalır → süre-watchdog ASLA durdurmaz (gözetimsiz sürüş; setin en
        # zararlısı). Henüz hiç bobin enerjilenmediği için burada iptal güvenli (yarım-açık kalmaz).
        # ⚠️ 1-C inceleme i1-F3 / i2-F1: denetim KİMLİKLİDİR ve tampon temizliğinden ÖNCE yapılır — arada açılmış YENİ
        # seans "aktif" göründüğü için eski denetim bu bayat isteği sürdürüyor, YENİ seansın koşu kaydını ve
        # sensör/dakika tamponlarını siliyordu. İptalde bu başlatmanın KENDİ DB satırı "İptal Edildi" kapatılır (i2-F7).
        with _session_lock:
            _still_active = bool(_active_session.get("is_active")) and _active_session.get("session_id") == _benim_seans
            # ⚠️ 1-C inceleme i1-F5: seansı BİTİRMEYEN bir durdurma (bu seansın bobinine STOP, `stop_all_coils`) DB yazımı
            # sırasında nesli artırdıysa başlatma burada — bobin sürülmeden, tampon temizlenmeden — iptal edilir; kendi
            # satırı "İptal Edildi" kapanır (sürüş yolundaki "Donanım Reddetti" DEĞİL — donanım reddetmedi).
            _erken_engel = estop_mandali.baslatma_engeli(_niyet_nesli) if _still_active else ""
            if _erken_engel:
                _active_session["is_active"] = False
        if not _still_active:
            logging.getLogger(__name__).warning(
                "Seans başlatma İPTAL: enerjilemeden önce durdurma algılandı (bobinler açılmadı)."
            )
            await asyncio.to_thread(_iptal_seans_satirini_kapat, sid)
            return {"status": "cancelled", "message": ceviri.t("seans.mesaj.baslatmaDurduruldu")}
        if _erken_engel:
            logging.getLogger(__name__).warning(
                "Seans başlatma İPTAL: DB yazımı sırasında bobin durdurması geldi (nesil) — bobinler açılmadı."
            )
            await asyncio.to_thread(_iptal_seans_satirini_kapat, sid)
            raise HTTPException(status_code=409, detail=_erken_engel)

        # Yeni seans → önceki (kaydedilmemiş) sensör buffer'ını temizle.
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer.clear()
        # Asama-2: onceki seanstan artmis acik coil-run / istatistik kalmasin.
        # ⚠️ D1.68 (B-1.6): artık koşu haritadan SESSİZCE SİLİNMEZ, KAPATILIR (`end_coil_run` + özet). Eskiden `.clear()`
        # önceki seansın açık koşusunu (ör. seans sırasında tekil başlatılmış, seans durdurmasının kapsamı dışındaki bobin)
        # `ended_epoch=NULL` kalıcı bırakıyordu. Bitiş bilinmiyor → bu başlatma anı (üst sınır); bobin hâlâ sürülüyorsa günlüğe.
        with _active_coil_runs_lock:
            _artik_kosular = list(_active_coil_runs.keys())
        if _artik_kosular:
            logging.getLogger(__name__).warning(
                "Seans başlatma: önceki seanstan AÇIK koşu kaydı kapatılıyor (bobin %s; bobin hâlâ çalışıyor olabilir).",
                _artik_kosular,
            )

            def _artiklari_kapat():
                for _cid in _artik_kosular:
                    try:
                        _finish_coil_run(_cid)
                    except Exception:
                        logging.getLogger(__name__).warning("artik kosu kapatilamadi (bobin %s)", _cid, exc_info=True)

            await asyncio.to_thread(_artiklari_kapat)
        with _active_coil_runs_lock:
            _active_coil_runs.clear()
        with _coil_run_stats_lock:
            _coil_run_stats.clear()
        # DENETIM P2 (hasta-verisi karismasi): _minute_acc bu temizlikte YOKTU. Tek temizleme
        # noktasi _emit_minute_averages'ti; onu ise SADECE dakika-loop'u ve /api/session/stop
        # cagiriyor. Sure-watchdog otomatik bitisi ve acil-durdurma is_active=False yaptigindan
        # /stop "Aktif seans yok" ile erken doner → birikmis kismi dakika HIC bosaltilmaz ve
        # SONRAKI hastanin ilk dakika-ortalamasina karisirdi (tibbi kayit kirlenmesi).
        with _minute_acc_lock:
            _minute_acc.clear()

        # Session API accepts minutes; ESP/MQTT duration remains seconds.

        # DENETIM 2. TUR [4.4] (2026-08-20): D-3 duzeltmesi (ffd4406) uc ham yayin sitesinden yalniz
        # IKISINI (tek-bobin + batch) kapatmisti; SEANS yolu ESP'ye HAM freq gondermeye devam ediyordu
        # → >1000 Hz'lik seansta STM bobinleri istenen frekansta, ESP'ler sessizce 1000'de: karma
        # dizide tutarsiz doz ("kismi duzeltme, duzeltilmemis demektir"). Tek-bobin/batch ile AYNI
        # normalize; run-log da ESP'ye GIDEN degeri yazar (o iki yolun kuraliyla birebir).
        from utils.stm32_protocol_limits import normalize_esp_frequency_hz as _sess_nesp

        _esp_sess_freq = _sess_nesp(payload.frequency)
        mqtt_duration_seconds = payload.duration_minutes * 60
        # [E1] (denetim 2026-08-24): NACK bekcisi yalniz broker CANLIYKEN baglanir. Broker oluyken NACK
        # gelemez (publish gitmedi) ve `esp_unreachable` (asagida) zaten uyarir; bekci timeout'u cift
        # uyari uretmesin (8. parti bilincli karari: broker-olu yarisi snappy-start + esp_unreachable).
        _esp_broker_ok = bool(esp_coils) and _broker_reachable()
        for coil_id in esp_coils:
            command_id = _komut_kimligi("sess", coil_id)  # D1.E10
            mqtt_payload = {
                "command": "start",
                "command_id": command_id,
                "freq": _esp_sess_freq,
                "duty": payload.duty,
                "phase": payload.phase,
                "duration": mqtt_duration_seconds,
            }
            # [E1]: 18. parti ack-mimarisi tekil+batch yollarina baglandi ama SEANS yolu DISARIDA
            # kalmisti — termal-kilitli 8266 seans-start'i NACK'lerse (command_error) hayalet kosu kaydi
            # seans boyu acik kalir, kapanista TAM SURELI muhurlenir. Onay kaydi publish'ten ONCE acilir
            # (hizli ack yarisi kaybolmasin — HG-4 deseni; bekci publish sonucundan BAGIMSIZ, NACK ESP'nin
            # command_error event'iyle gelir). Tekil/batch yoluyla ayni sozlesme.
            if _esp_broker_ok:
                _register_ack(command_id, bobin=coil_id)
            # ESP publish arka planda → broker yavaş/erişilemezse seans başlatmayı bekletme (snappy start).
            # D1.81 · Y4: mandal/nesil kapılı START yayını (niyet nesli istek girişinden; telafi STOP'u dahil).
            _threading.Thread(
                target=_esp_start_yayinla, args=(coil_id, mqtt_payload, _niyet_nesli), daemon=True
            ).start()
            # Asama-2: seans-baslangic bobini icin per-bobin run kaydi. /session/start bobinleri
            # KENDI dongusuyle baslattigindan control_single/batch hook'u buraya ULASMAZ → burada ac.
            # ⚠️ KOSULSUZ (8. parti bilincli karari: fire-and-forget publish → sonuc bilinemez; broker-olu
            # seans zaten esp_unreachable tasir). [4.4]: loglanan freq = ESP'ye GIDEN (normalize) deger.
            _begin_coil_run(coil_id, _esp_sess_freq, payload.duty, payload.phase, payload.intensity, "esp")
            _sess_run_id = _active_coil_runs.get(coil_id)  # D2: bekçiye BU start'ın run'ını taşı
            # NACK gelirse bekci bu kaydi kapatir (hayalet kayit) + operatore bildirir; ack TIMEOUT'unda
            # kayit KORUNUR (ack QoS-0, kayip ack gercek kosunun dozunu silmemeli). Tekil yolla ayni.
            if _esp_broker_ok:
                _start_ack_izle_arka_planda(coil_id, command_id, True, _sess_run_id)
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Seans baslatma: surus ONCESI bolgede HATA → seans iptal ediliyor.")
        await _baslatma_hatasinda_kapat(
            _benim_seans,
            ceviri.t("seans.hata.hazirlikNeden"),
            ceviri.t("seans.hata.hazirlikEk"),
        )

    # event-loop-blok fix: update_coil = STM32'ye SENKRON seri-port yazımı (bobin başına ~onlarca ms) →
    # async-uçta doğrudan çalışınca event-loop'u bloklar; STM bobin döngüsünü thread'e offload et.
    def _start_stm_coils():
        """Bobinleri sür ve KABUL EDİLENLERİ döndür.

        ═══════════════════════════════════════════════════════════════════════
        ⚠️ SAHTE "BAŞARILI" SEANSIN İKİNCİ (ve daha genel) KÖKÜ — 2026-09-12
        ═══════════════════════════════════════════════════════════════════════
        `update_coil` REDDİ False ile bildirir (kart kopuk · firmware/CRC uyuşmaz ·
        parametre normalizasyonu patladı). Bu dönüş burada HİÇ OKUNMUYORDU: hiçbir bobin
        sürülmese bile seans "başladı" sayılıyor, sayaç işliyor, coil-run satırları TAM
        SÜREYLE yazılıyor ve geçmişe "Tamamlandı" düşüyordu.

        ⚠️ Tekil bobin yolu (`control_single_coil`) bunu 2026-08-20'de ZATEN düzeltmişti
        ("koşu kaydı yalnız KABUL edilen start'ta"); SEANS yolu dışarıda kalmıştı — bu
        deponun tekrar eden "kısmi düzeltme, düzeltilmemiş demektir" sınıfı.
        """
        kabul = []
        for coil_id in stm_coils:
            if state.hardware.update_coil(
                coil_id, payload.frequency, payload.duty, payload.phase, payload.duration_minutes, start=True
            ):
                kabul.append(coil_id)
                # ⚠️ KOŞU KAYDI YALNIZ KABULDE: reddedilen bobin için satır açmak, hiç
                # uygulanmamış bir dozu tıbbi kayda yazmak olurdu.
                # D1.99 (S-1.2): GİDEN (normalize) değer — update_coil aynı `surus_parametrelerini_hazirla`yı uygular.
                _begin_coil_run(coil_id, _s_uyg["freq"], _s_uyg["duty_yuzde"], _s_uyg["faz"], payload.intensity, "stm")
            else:
                # D6.02 (S-1.7): reddin GERÇEK sebebi (aynı işçi iş parçacığında, `update_coil`'den hemen sonra okunur).
                _sebep = _donanim_baslatma_reddi(state.hardware)
                if _sebep:
                    _stm_red_sebepleri.append(_sebep)
                logging.getLogger(__name__).error("Seans: bobin %s komutu REDDEDILDI (surulmedi): %s", coil_id, _sebep)
        return kabul

    _stm_red_sebepleri: list = []

    _stm_kabul: list = []
    if stm_coils:
        # D1.81: niyet nesli bağlamı `to_thread` iş parçacığına kopyalanır → `update_coil` onu kilit altında denetler.
        try:
            with estop_mandali.surus_baglami(_niyet_nesli):
                _stm_kabul = await asyncio.to_thread(_start_stm_coils) or []
        except Exception:
            # ⚠️ İNCELEME-2 §10 #2 (i3-F-10 genişlemesi): sürüş İSTİSNA atarsa (ör. bobin 1 kabul edildi, bobin 2'de
            # `update_coil` fırladı) uç 500'le çıkıyor, seans `is_active` + `baslatma_ucusta` kalıyor, kabul edilen bobin
            # TELDE kalıyordu; sonraki normal Durdur satırı "İptal Edildi" yazıyordu. Başlatma bayrağı ve seans TUTARLI
            # kapanır: KENDİ seansı hâlâ aktifse normal durdurma yolu (uçuştaki başlatma → TÜM seans bobinlerine STOP,
            # satır "İptal Edildi"); Ö.4-Y8: STOP yalnız artar, kapılanmaz.
            logging.getLogger(__name__).exception("Seans baslatma: bobin surusu HATA verdi → seans iptal ediliyor.")
            await _baslatma_hatasinda_kapat(
                _benim_seans,
                ceviri.t("seans.hata.surusNeden"),
                ceviri.t("seans.hata.surusEk"),
            )

    # ⚠️ HİÇBİR BOBİN SÜRÜLMEDİYSE SEANS YOKTUR — geri al ve DÜRÜSTÇE söyle.
    # Sahip bildirimi: "bobinlere komut gitmemesine rağmen seans başlatınca gerçekten
    # başlıyormuş gibi her şey sorunsuz devam ediyor."
    # ⚠️ ESP bobinleri hesaba katılır: karma dizide STM reddedilse de ESP sürülmüş olabilir,
    # o seans GERÇEKTİR ve iptal edilmemelidir.
    # ⚠️ `stm_coils` KOŞULU YOK: ESP kapalıyken yalnız bobin 8 istenen bir seansta
    # `stm_coils` boştur ve eski koşul HİÇ tetiklenmezdi — seans yine sahte başarılı olurdu.
    if not _stm_kabul and not esp_coils:
        from controllers.hardware_controller import sifir_hz_durdurma_mi

        _surus_engeli = estop_mandali.baslatma_engeli(_niyet_nesli)
        # ⚠️ `to_thread`: `_finalize_session_db` SENKRONDUR ve kendi sözleşmesinde "yalnız
        # thread'lerden çağrılır, event-loop'tan DEĞİL" der (SQLite yazımları event-loop'u
        # bloklar). Bu uç `async` olduğu için geri alma thread'e taşınır.
        # ⚠️ 1-C §9 #5: sürüş penceresinde, İLK bobinden önce gelen durdurma (bobin STOP'u / acil durdurma) nesli artırır
        # ve TÜM bobinler reddedilir — donanım REDDETMEDİ, başlatma İPTAL edildi → satır "İptal Edildi" (eskiden
        # "Donanım Reddetti"; yanıt zaten 409'du). Engel yoksa gerçek donanım reddidir.
        await asyncio.to_thread(
            _seansi_geri_al,
            "iptal:surus-oncesi-durdurma" if _surus_engeli else "donanim-reddi:hicbir-bobin-surulmedi",
            _benim_seans,
        )
        if _surus_engeli:
            # D1.81: neden firmware DEĞİL — başlatma sürerken durdurma / acil durdurma geldi.
            raise HTTPException(status_code=409, detail=_surus_engeli)
        if sifir_hz_durdurma_mi(payload.frequency):
            # D1.53 (A-05): 0 Hz = DURDURMA — bobinler durduruldu; neden firmware DEĞİL, girilen frekans.
            raise HTTPException(status_code=503, detail=sifir_hz_seans_mesaji())
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("seans.hata.komutKabulEdilmedi", neden=_seans_red_nedeni(_stm_red_sebepleri)),
        )

    # ⚠️ 1-C inceleme i2-F3: STM sürüşü (to_thread) SIRASINDA durdurma gelmiş olabilir — bobin 1 kabul edildikten SONRA,
    # bobin 2'den ÖNCE. Ölçüldü (30/30): bobin 2 nesille doğru reddediliyor ama `_stm_kabul=[1]` boş olmadığı için akış
    # canlı durumu "AKTİF" yazıyor, seans CSV'sini AÇIYOR ve "success" dönüyordu — seans da bobin de yokken; operatörün
    # sonraki Durdur'u (seanssız dal) göstergeyi temizlemiyordu. "Aktif" yazımından, CSV'den, hasta kartından ve
    # yanıttan ÖNCE: bu başlatma hâlâ KENDİ seansı mı ve sürüş yetkisi geçerli mi?
    async def _baslatma_sirasinda_durduruldu(engel: str):
        with _session_lock:
            _hala = bool(_active_session.get("is_active")) and _active_session.get("session_id") == _benim_seans
        if _hala:
            # Kendi seansı aktif ama başlatma sürerken seansı BİTİRMEYEN bir durdurma (ör. `stop_all_coils`) geldi:
            # kabul edilen bobinler o durdurmayla durdu → seans normal durdurma yoluyla kapatılır (STOP'lar yalnız artar).
            logging.getLogger(__name__).warning("Seans başlatma sürerken durdurma geldi → seans durduruluyor.")
            await stop_session()
        raise HTTPException(status_code=409, detail=engel or ceviri.t("seans.hata.baslatmaSurerkenDurduruldu"))

    with _session_lock:
        _hala_benim = bool(_active_session.get("is_active")) and _active_session.get("session_id") == _benim_seans
        _sonra_engel = estop_mandali.baslatma_engeli(_niyet_nesli)
        if _hala_benim and not _sonra_engel:
            # i1-F5: başlatma uçuşu BİTTİ — bundan sonra bobin STOP'u yalnız o bobini durdurur (nesle dokunmaz).
            _active_session["baslatma_ucusta"] = False
    if not _hala_benim or _sonra_engel:
        await _baslatma_sirasinda_durduruldu(_sonra_engel)

    # D1.61 (B-5.7): elle seansta fantom/petri analizinin canlı E bağlamı (başka bir hedef) GÖSTERİLMEZ.
    try:
        from servers import efield_live as _ef_bas

        _ef_bas.seans_basladi("manuel")
    except Exception:
        logging.exception("canlı E bağlamı temizlenemedi (seans akışı etkilenmez)")

    # D1.99 (B-1.9): kart donanıma GİDEN frekansı gösterir (STM kabul ettiyse STM'in, yoksa ESP'nin normalize değeri).
    from utils.stm32_protocol_limits import normalize_esp_frequency_hz as _kart_esp_hz

    _kart_freq = _s_uyg["freq"] if _stm_kabul else _kart_esp_hz(payload.frequency)
    # i2-F3: yazım nesli KİLİT ALTINDA denetler; denetim ile yazım arasında gelen durdurmada yazım atlanır (False) →
    # CSV açılmaz, "success" denmez (tek karar noktası). `is False`: dönüşsüz eski sahte uygulamalar "yazıldı" sayılır.
    if (
        update_live_session_state(
            is_active=True,
            mode=payload.mode,
            freq=_kart_freq,
            intensity=payload.intensity,
            remaining_min=payload.duration_minutes,
            duration_sec=payload.duration_minutes * 60,
            surus_nesli=_niyet_nesli,
        )
        is False
    ):
        await _baslatma_sirasinda_durduruldu(estop_mandali.baslatma_engeli(_niyet_nesli))

    # ── SEANSA ÖZEL ALAN KAYDI (masaüstü CSV) ────────────────────────────────────────
    # ⚠️ `update_live_session_state`ten SONRA: o çağrı `isActive`i true yapar ve ölçülen
    # yoğunluğu sıfırlar; kayıt ondan önce açılsaydı ilk telemetri satırı hâlâ kapalı
    # görünen bir seansa yazılırdı. ⚠️ HATA SEANSI ENGELLEMEZ: CSV bir kolaylıktır,
    # dolu disk ya da yazma izni yüzünden tedavi başlamaması kabul edilemez.
    try:
        _csv_yolu = _seans_alan.seans_basladi(
            str(_active_session.get("session_id") or ""),
            {
                "patient_name": payload.patient_name,
                "operator_name": _operator_adi,
                "mode": payload.mode,
                "frequency": payload.frequency,
                "duty": payload.duty,
                "duration_minutes": payload.duration_minutes,
                "intensity": payload.intensity,
            },
        )
        if _csv_yolu is not None:
            _bildir(lambda d: ceviri.t("bildirim.alanKaydiBasladi", dil=d, yol=_csv_yolu), "info")
        else:
            _bildir(lambda d: ceviri.t("bildirim.alanKaydiAcilamadi", dil=d), "warning")
    except Exception:
        logging.exception("seans alan kaydı açılamadı (seans akışı etkilenmez)")

    # Dashboard 'Hasta Özeti' kartı için aktif hastayı canlı-duruma yaz (aktif seansın GERÇEK hastası).
    # İsim in-memory payload'dan (maskesiz); tür/ırk/sahip patient_id ile hasta-DB'den (düz-metin, maskesiz)
    # zenginleştirilir. Hasta yoksa None → kart "Aktif hasta yok" gösterir. set_live_patient tam snapshot yayınlar.
    _patient_snap = None
    _pname = (payload.patient_name or "").strip()
    if _pname or payload.patient_id:
        _patient_snap = {"name": _pname or "İsimsiz", "species": "", "breed": "", "owner": ""}
        if payload.patient_id:
            try:
                # C2-2.9: kayıt başlatmadaki iş parçacığında okundu (olay döngüsünde hasta DB G/Ç'si yok).
                _rec = _hasta_kaydi.get("kayit")
                if _rec:
                    _patient_snap = {
                        "name": (_rec.get("name") or _pname or "İsimsiz"),
                        "species": _rec.get("species") or "",
                        "breed": _rec.get("breed") or "",
                        "owner": _rec.get("owner") or "",
                    }
            except Exception:
                logging.getLogger(__name__).debug("Hasta Özeti snapshot lookup hatasi", exc_info=True)
    set_live_patient(_patient_snap)

    # ESP fail-safe (audit #4): broker erişilemezse ESP bobinleri (6-8) sessizce başlamaz →
    # operatöre WARN dön. Eskiden seans her hâlükârda 'success' dönüp ESP'ler ölü kalıyordu
    # ve kimse fark etmiyordu (STM bobinleri çalışsa da ESP yolu sessizce başarısızdı).
    # DENETIM P3: canli global `_active_session` REFERANSLA donuyordu. FastAPI yaniti bu
    # fonksiyon dondukten SONRA serilestirir; arada bir arka-plan thread'i (sure-watchdog,
    # AI loop, /stop) sozlugu mutate ederse serilestirme sirasinda "dictionary changed size
    # during iteration" → 500, ya da yanit yari-eski/yari-yeni alanlar tasir. Kilit altinda
    # SNAPSHOT dondur (istemci sozlesmesi ayni; yalniz yasam suresi guvenli).
    with _session_lock:
        _sess_snapshot = dict(_active_session)
    resp = {"status": "success", "session": _sess_snapshot}
    # `_esp_broker_ok` yukarida bir kez olculdu (esp_coils VE broker canli); ayni degeri kullan.
    if esp_coils and not _esp_broker_ok:
        msg = ceviri.t("seans.uyari.espErisilemez", esp_coils=esp_coils)
        logging.getLogger(__name__).warning(
            "Seans başladı ama %s", ceviri.t("seans.uyari.espErisilemez", dil="tr", esp_coils=esp_coils)
        )
        resp["warning"] = msg
        resp["esp_unreachable"] = True
    return resp


def _stop_session_coils(coil_ids, yetkiyi_kes: bool = False):
    """Verilen bobinlere donanım STOP gönderir (önce STM→update_coil start=False, sonra ESP→MQTT).
    is_running=False yapar → HWKeepAlive tazelemeyi keser → bobinler fiziksel olarak durur.

    `yetkiyi_kes` (D1.81 · B-5.3): SEANSI BİTİREN durdurmalar (`/api/session/stop`, `/api/ai/pro/stop`, süre bekçisi)
    STOP'tan ÖNCE sürüş neslini artırır → uçuştaki START niyetleri (tahmin/lokalizasyondaki `/frame`, döngü turu)
    bu STOP'tan sonra bobini YENİDEN enerjileyemez. Seansın KENDİ ara durdurması (AI Pro hedef kaybı) bunu yapmaz:
    hedef yeniden bulununca sürüş sürmelidir.

    DENETIM 2. TUR [1.1] (2026-08-20): DOĞRULANAMAYAN bobinlerin listesini DÖNER.
    Eskiden publish/update_coil sonuçları YOK SAYILIYORDU → broker ölüyken /api/session/stop
    koşulsuz "success" dönüyor, istemcinin "Durdurma onaylanamadı — ACİL DURDUR'a basın"
    uyarısı hiç tetiklenmiyordu (STOP hiçbir bobine ulaşmamışken UI "durdu" der).
    "Teyitsiz" üç durumu kapsar: ESP publish PUBACK'siz düştü · STM update_coil False döndü ·
    STM kontrolcüsü hiç yok (STOP denen(e)medi — sessiz atlama da teyitsizliktir).
    Dönüş listesi bilgidir; durdurma denemeleri her hâlükârda yapılır (best-effort korunur)."""
    import time as _t

    if yetkiyi_kes:
        estop_mandali.nesil_artir()

    teyitsiz: list = []
    _esp_acik = live_state.esp_etkin()
    _stm_hedef = [cid for cid in coil_ids if cid in STM_COIL_IDS]
    # ⚠️ 1-G inceleme G-3.2 (Ö.4-Y8): STM STOP'ları ESP yayınlarından ÖNCE kuyruğa verilir. `_mqtt_publish` sağlıklı
    # broker'da bile ~1 sn, yerel broker kimliği uyuşmazken (D1.104 `--yenile` penceresi) ~2 sn sürüyor; ESP önce
    # yayınlandığında STM STOP'u onu BEKLİYORDU (ölçüldü: "Seansı Durdur" bobin [1, 8] → ilk STM STOP 1,04 sn /
    # uyuşmazlıkta 3,09 sn). Port teyidi (yalnız RAPOR) ESP yayınlarından SONRA beklenir → ESP STOP'u da onu beklemez.
    _isaret = _sira_once = None
    _kuyrukta: list = []
    if state.hardware:
        _isaret, _sira_once = _stm_yazim_isareti_al(), _stm_son_stop_sirasi_al()
        for coil_id in _stm_hedef:
            try:
                ok = bool(state.hardware.update_coil(coil_id, 0.0, 0.0, 0.0, 0, start=False))
            except Exception:
                logging.getLogger(__name__).warning(
                    "_stop_session_coils: STM stop hatasi (bobin %s)", coil_id, exc_info=True
                )
                ok = False
            if not ok:
                teyitsiz.append(coil_id)
            else:
                _kuyrukta.append(coil_id)
    else:
        teyitsiz.extend(_stm_hedef)
    for coil_id in [cid for cid in coil_ids if cid in ESP_COIL_IDS]:
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {
                "command": "stop",
                "command_id": f"stop_{coil_id}_{int(_t.time() * 1000)}",
            },
        )
        # ⚠️ A-63 (İG-5.10): ESP BİLEREK kapalıyken STOP yine DENENİR ama teyit STM'e göre verilir — ESP slotu "teyitsiz"
        # sayılmaz (eskiden bobin 8'li her seans durdurması 409 "HÂLÂ ÇALIŞIYOR olabilirler" diyordu).
        if not ok and _esp_acik:
            teyitsiz.append(coil_id)
    # ⚠️ 1-C §9 #2 (A-63): teyit "kuyruğa verildi" DEĞİL, STOP PORTA YAZILDI (E-stop'la aynı ölçüt, D1.55). Eskiden
    # kablo çıkıkken (porta 0 bayt) seans / AI Pro / süre bekçisi durdurması "teyitli" sayılıyordu. Yalnız RAPOR.
    if _kuyrukta and not _stm_stop_porta_yazildi_mi(_isaret, _sira_once):
        teyitsiz.extend(_kuyrukta)
    # Asama-2: durdurulan tum bobinlerin acik run'larini kapat (acik kalmasin).
    for coil_id in coil_ids:
        try:
            _finish_coil_run(coil_id)
        except Exception:
            logging.getLogger(__name__).debug("_stop_session_coils _finish_coil_run hatasi", exc_info=True)
    if teyitsiz:
        logging.getLogger(__name__).warning(
            "_stop_session_coils: donanim STOP'u DOGRULANAMAYAN bobinler: %s (broker/STM erisilemez olabilir)",
            sorted(teyitsiz),
        )
    return sorted(teyitsiz)


def _seanssiz_durdur() -> list:
    """`/api/session/stop` AKTİF SEANS YOKKEN (D1.81 · İG-5.3): yetkiyi kes + TÜM STM bobinlerine tek STOP paketi
    (`stop_all_coils`), ESP açıksa ESP bobinlerine STOP; seanssız (tekil/batch) açılmış koşu kayıtları kapanır.
    Dönen: STOP'u DOĞRULANAMAYAN bobinler (STM kontrolcüsü yoksa STM tarafında durdurulacak bir şey de yoktur)."""
    estop_mandali.nesil_artir()
    teyitsiz: list = []
    if state.hardware:
        _isaret, _sira_once = _stm_yazim_isareti_al(), _stm_son_stop_sirasi_al()
        try:
            ok = bool(state.hardware.stop_all_coils())
        except Exception:
            logging.getLogger(__name__).warning("seanssiz stop: STM stop_all hatasi", exc_info=True)
            ok = False
        # 1-C §9 #2 (A-63): kuyruğa verildi ≠ porta yazıldı (kablo çıkık → teyitsiz). Yalnız RAPOR; STOP gitti.
        if not ok or not _stm_stop_porta_yazildi_mi(_isaret, _sira_once):
            teyitsiz.extend(sorted(STM_COIL_IDS))
    if live_state.esp_etkin():
        for coil_id in sorted(ESP_COIL_IDS):
            if not _mqtt_publish(
                f"pemf/coil/{coil_id}/control", {"command": "stop", "command_id": _komut_kimligi("stop", coil_id)}
            ):
                teyitsiz.append(coil_id)
    for coil_id in range(1, 9):
        try:
            _finish_coil_run(coil_id)
        except Exception:
            logging.getLogger(__name__).debug("seanssiz stop: _finish_coil_run hatasi", exc_info=True)
    return teyitsiz


def _seans_disi_calisan_bobinler(seans_bobinleri) -> list:
    """Y63 (sahip, 1-F S-F3): "Seansı Durdur" anında seansın bobin listesi DIŞINDA çalıştığı BİLİNEN bobinler — seans
    sürerken tekil kontrol / toplu uç / eski `/hardware/command` ile ayrıca başlatılanlar (STM 1-7, 6-7 dahil; ESP 8).
    Kaynaklar: HC durumu (`is_running` — STM'in kaynağı), açık koşu kaydı (seans satırına bağlanan tekil başlatma), ESP
    canlı durumu (`running`). Çalıştığı bilinmeyen bobine STOP GÖNDERİLMEZ: ESP açık + broker ölüyken hiç sürülmemiş bobin 8
    için sahte "STOP DOĞRULANAMADI" (409) alarmı üretilmesin (alarm körlüğü). Bir kaynak okunamazsa atlanır — seans
    durdurmayı engellemez."""
    seans = {int(c) for c in (seans_bobinleri or [])}
    calisan: set = set()
    try:
        for _cid, _d in list((getattr(state.hardware, "coils_state", None) or {}).items()):
            if (_d or {}).get("is_running"):
                calisan.add(int(_cid))
    except Exception:
        logging.getLogger(__name__).warning("Y63: HC bobin durumu okunamadi (o kaynak atlandi)", exc_info=True)
    with _active_coil_runs_lock:
        calisan.update(int(c) for c in _active_coil_runs)
    with _live_state_lock:
        for _c in _live_state["coils"].values():
            if _c.get("running") and int(_c.get("id") or 0) in ESP_COIL_IDS:
                calisan.add(int(_c["id"]))
    return sorted(c for c in calisan - seans if 1 <= c <= 8)


def _bildir_teyitsiz_stop(teyitsiz, kaynak) -> None:
    """DENETIM 2. TUR [1.1] tamamlamasi (adversaryal review #2): /session/stop yaniti teyitsizligi
    tasirken sure-watchdog / AI durdurma / sahipsiz-bobin yollari onu YUTUYORDU — broker oluyken
    seans "sure doldu" ile bitince operatore hicbir uyari gitmiyordu (bobinler ESP'de kendi suresi
    bitene dek enerjili kalabilir). Bu yardimci, HTTP yaniti OLMAYAN durdurma yollarinin ortak
    uyari kanali. Bos listede SESSIZ (alarm yorgunlugu uretme); bildirim hatasi durdurmayi bozmaz."""
    if not teyitsiz:
        return

    def _kaynak_metni(d):
        return kaynak(d) if callable(kaynak) else kaynak

    _bobinler = sorted(teyitsiz)
    try:
        _bildir(
            lambda d: ceviri.t("bildirim.teyitsizStop", dil=d, kaynak=_kaynak_metni(d), bobinler=_bobinler),
            "error",
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "teyitsiz-stop bildirimi gonderilemedi (%s)", kaynak("tr") if callable(kaynak) else kaynak, exc_info=True
        )


def start_ai_session(
    freq,
    duty,
    duration_minutes,
    coil_ids,
    mode="AI",
    operator_email: str = "",
    tur: str = "ai_auto",
    onay_kimligi: str = "",
    surus_nesli: int | None = None,
    model: str = "",
    onay_hedefi: int | None = None,
    hasta: dict | None = None,
    kayit: dict | None = None,
):
    """AI biofeedback donanım sürerken seansı _active_session'a YAZAR → süre-watchdog onu da
    izler ve süresi dolunca DURDURUR; emergency_stop/STM-disconnect de AI'yı kapsar. Parametre
    CLAMP'i YOK (sadece seans takibi). Tekrarlı AI çağrılarında ilk start_time/session_id korunur.

    D1.80 (B-5.1 · B-5.10): seans MÜHRÜ — `tur` ("ai_auto" | "ai_pro"), `onay_kimligi` (AI Pro: tüketilen hekim
    onayı), `surus_nesli` (D1.81: niyet nesli), `model` (AI Pro: onaylanan sağlayıcı). `/frame` YALNIZ
    `tur == "ai_pro"` + onay + nesil taşıyan seansta sürer; `mode` metni yetki VERMEZ. Varsayılan tür en az
    yetkili olandır ("ai_auto": `/frame` sürmez).
    D1.60 (A-16): `onay_hedefi` = hekimin ONAYLADIĞI hedef (organ) kimliği. Seans sürerken başka hedefe geçiş
    yeni onay ister (`/ai/pro/organ` 409) ve sürüş yalnız bu hedefi sürer."""
    import time as _t

    def _devam_mi(onceki: dict) -> bool:
        # Devam (aynı seans satırı/başlangıcı) YALNIZ AI (Auto)'nun KENDİ tekrarlı çağrısında (D1.88'e kadar landmark her
        # istekte çağırıyordu; bugün tek çağıran AI Pro — `tur="ai_pro"`, bu dal ürün kodundan ERİŞİLMEZ). AI Pro her
        # başlatmada YENİ mühürlü seanstır: önceki AI (Auto) seansının başlangıcını/satırını
        # devralsaydı mühürdeki süre (başlangıç + onaylanan dk) yanlış hesaplanırdı. Türü olmayan eski kayıt AI
        # (Auto) sayılır (yalnız kayıt sürekliliği — yetki değil).
        return (
            bool(onceki.get("is_active"))
            and str(onceki.get("mode", "")).startswith("AI")
            and tur == "ai_auto"
            and onceki.get("tur", "ai_auto") == "ai_auto"
        )

    # ⚠️ Y65 (sahip, 1-F inceleme S-İF1): YENİ seansın tedavi satırı devralmanın HİÇBİR yan etkisinden (oturumun
    # değişmesi, sahipsiz bobin STOP'u, önceki seansın kapatılması) ÖNCE açılır. Açılamazsa hiçbir şeye dokunulmadan
    # `KayitAcilamadi` → önceki seans (ör. manuel) AYNEN sürer; çağıran (`/ai/pro/start`) döngüyü başlatmaz, onayı GERİ
    # VERİR (D1.E06) ve 503 döner. 1-G ilk taslağı satırı devralmadan SONRA açıyordu: manuel seans sürerken AI Pro'nun
    # satırı açılamayınca manuel seans kapatılmış, oturum silinmiş, bobinleri ise keep-alive ile SÜRMEYE devam ediyordu
    # (sahipsiz, kayıtsız sürüş). Eskiden (önceden var) satır "best-effort" idi ("tedavi surer").
    with _session_lock:
        _on_cont = _devam_mi(dict(_active_session))
    _ai_sid = None
    _ai_pid = None
    # ⚠️ D2.E15 (İG-5.14): AI Pro seansı HASTAYA bağlanır — elle seans yoluyla AYNI bağ (`upsert_patient` ayna satırı + satırda
    # ad + `set_session_meta(patient_id)` + sahip e-postası). Hasta ONAY MÜHRÜNDEN gelir (`/ai/pro/start`). Hasta yoksa
    # bugünkü gibi sahipsiz.
    _hasta_adi = str((hasta or {}).get("name") or "").strip()
    _hasta_kimligi = str((hasta or {}).get("id") or "").strip()
    _sahip_epostasi = ""
    if not _on_cont:
        if _VERI_TASIMA_KILIDI.locked():  # D2-4.1: Y65 yolu — bobin sürülmez, onay yanmaz (çağıran `geri_ver`)
            raise KayitAcilamadi(geri_yukleme_surerken_seans())
        try:
            _db = _get_treatment_db()
            if _db is not None and _hasta_adi:
                try:
                    _sahip_epostasi = _lookup_owner_email(_hasta_kimligi) if _hasta_kimligi else ""
                    _ai_pid = _db.upsert_patient(
                        {
                            "name": _hasta_adi,
                            "patient_uuid": (_hasta_kimligi or None),
                            "owner_email": (_sahip_epostasi or None),
                        }
                    )
                except Exception:
                    logging.getLogger(__name__).warning(
                        "AI seansi: hasta ayna satiri yazilamadi (seans sahipsiz)", exc_info=True
                    )
            if _db is not None:
                # ⚠️ SAHİPLİK (sahip bildirimi 2026-09-12: "klinik ve benim ayrımı düzgün
                # çalışıyor mu incele... herkes kendi maili ile kayıt oluyor ya").
                # ÖLÇÜLDÜ: bu satır `operator_email` YAZMIYORDU → her AI seansı SAHİPSİZ
                # kaydediliyordu. Arayüzün kuralı "sahipsiz = benim" olduğu için otonom
                # seanslar kliniğin HER hekimine "Benim Seanslarım"da görünüyordu; yani
                # "Benim / Tüm Klinik" ayrımı AI tarafında fiilen YOKTU.
                # ODD B-4 (ODK-B keşfi 18-11): AI Pro satırı hedefini taşır (petri: plaka etiketi "Kuyu C6", kedi: organ) — geçmiş
                # kartı "Hedef -" gösteriyordu. Değer VERİ (Türkçe etiket; DB değerleri çevrilmez).
                _ai_sid = _db.start_session(
                    treatment_mode=mode,
                    target_condition=(str((kayit or {}).get("hedef") or "").strip() or None),
                    patient_name=(_hasta_adi or None),
                    operator_email=(str(operator_email or "").strip().lower() or None),
                )
        except Exception:
            logging.getLogger(__name__).exception("AI seansi DB satiri acilamadi (Y65: seans BASLATILMAYACAK).")
            _ai_sid = None
        if _ai_sid is None:
            raise KayitAcilamadi(kayit_acilamadi_mesaji())

    with _session_lock:
        prev = dict(_active_session)  # devralma kararı için ESKİ seansın snapshot'ı (clear'dan ÖNCE)
        cont = _devam_mi(prev)
        if not cont and _ai_sid is None:
            # Yarış: anlık görüntüde AI (Auto) devamıydı, kilitte YENİ seans — satır yok → oturuma DOKUNMADAN reddet.
            raise KayitAcilamadi(kayit_acilamadi_mesaji())
        # B-2.2: REBIND yerine IN-PLACE (clear+update) → dict kimliği sabit; davranış aynı.
        _active_session.clear()
        # 1-C inceleme i1-F3: kimlik BENZERSİZ olmalı (eskiden `ai_<epoch SANİYE>`: aynı saniyedeki iki AI seansı aynı
        # kimliği alıyor, kimlik denetimli geri alma / DB damgası yanlış seansı "kendi" sanabiliyordu). Elle seans
        # mührüyle aynı üretici (ms + süreç-içi sayaç), `ai_` öneki korunur.
        _new_session_id = prev.get("session_id") if cont else "ai_" + _yeni_seans_muhru().split("_", 1)[1]
        _active_session.update(
            {
                "is_active": True,
                "session_id": _new_session_id,
                "mode": mode,
                "frequency": freq,
                "duty": duty,
                "phase": 0.0,
                "duration_minutes": int(duration_minutes),
                "start_time": prev.get("start_time") if cont else _t.time(),
                "start_mono": prev.get("start_mono") if cont else _t.monotonic(),
                "coil_ids": list(coil_ids),
                # DENETIM P1: bu iki alan HIC kurulmuyordu → _flush_sensor_buffer_if_active
                # `if not _db_sid: return` ile TUM dakika-ortalamalarini atiyordu ve otonom
                # tedavinin DB'de seans satiri OLUSMUYORDU (doz/sicaklik kaydi kalici kayip).
                # cont=True (ayni AI seansinin tekrarli cagrisi; D1.88'e kadar landmark auto_adjust her
                # istekte cagiriyordu — bugun erisilmez) → MEVCUT satiri koru, YENI satir acma. Y65: yeni satır YUKARIDA açıldı.
                "db_session_id": prev.get("db_session_id") if cont else _ai_sid,
                "db_patient_id": prev.get("db_patient_id") if cont else _ai_pid,
                "started_epoch": prev.get("started_epoch") if cont else _t.time(),
                "tur": tur,
                "onay_kimligi": str(onay_kimligi or ""),
                "surus_nesli": surus_nesli,
                "model": str(model or ""),
                "onay_hedefi": onay_hedefi,
            }
        )
        _started_epoch_ai = _active_session["started_epoch"]
        # DENETIM (2026-08-05, dogrulama turunda bulundu): yukarida `coil_ids` KOSULSUZ
        # yeniden yaziliyor (satir "coil_ids": list(coil_ids)). Yeni seans ONCEKINDEN DAR bir
        # kume sahiplenirse aradaki bobinler SESSIZCE sahipsiz kalir — donanima STOP gitmez.
        #   Somut yol (D1.88'e kadar): `AI (Auto)` landmark surusu bobin 1-8'i 30 dk enerjilerdi → operator
        #   `AI Pro` baslatir (yalniz 1-7). Bobin 8'i artik ne AI Pro dongusunun hedef-kayip
        #   STOP'u (range(1,8)) ne sure-watchdog (sess["coil_ids"]=1-7) ne de teardown kapsar;
        #   ESP kendi 30 dk suresi dolana kadar CANLI HAYVAN uzerinde surer.
        # Hem cont=True (AI→AI devam) hem cont=False (devralma) yolunda gecerli → kilit
        # BLOGUNUN DISINDA, tek yerde hesapla. STOP kilit birakildiktan SONRA gonderilir.
        _orphan_coils = [
            int(c)
            for c in (prev.get("coil_ids") or [])
            if prev.get("is_active") and int(c) not in set(int(x) for x in coil_ids)
        ]
    # D1.61 (B-5.7): AI (Auto) / kedi AI Pro seansında fantom/petri analizinin canlı E bağlamı (başka hedef) GÖSTERİLMEZ;
    # yalnız AYNI modelin araştırma AI Pro seansı bağlamı korur (`efield_live.seans_basladi`). AI (Auto)'nun kendi tekrarı
    # (`cont`) yeni seans değildir.
    if not cont:
        try:
            from servers import efield_live as _ef_ai

            _ef_ai.seans_basladi(tur, model)
        except Exception:
            logging.getLogger(__name__).exception("canlı E bağlamı temizlenemedi (seans akışı etkilenmez)")
    if _orphan_coils:
        try:
            _bildir_teyitsiz_stop(
                _stop_session_coils(_orphan_coils), lambda d: ceviri.t("bildirim.kaynak.sahipsiz", dil=d)
            )
            logging.getLogger(__name__).warning(
                "AI seansi daha DAR bir bobin kumesi sahiplendi → sahipsiz kalan bobinler "
                "durduruldu %s (aksi halde enerjili kalirlardi).",
                _orphan_coils,
            )
        except Exception:  # pragma: no cover — SAVUNMA: alt işlevler STOP hatasını içeride yakalar
            logging.getLogger(__name__).exception("Sahipsiz bobin STOP hatasi: %s", _orphan_coils)
    # P1 audit 2026-06-28: AKTIF MANUEL (non-AI) seans varken AI baslayinca _active_session KOSULSUZ
    # eziliyordu → manuel db_session_id/coil_ids kayboluyor, acik coil-run'lar kapanmiyor, DB satiri
    # kalici 'active' kaliyor (KPI/history sisiyor + STM keep-alive surer ama UI 'AI' gosterir).
    # Yeni AI seansini kurduktan SONRA eski manuel seansi DUZGUN kapat (orphan onle). Hizli: coil-run
    # in-memory + ~ms DB write; AI coil komutlari start_ai_session DONDUKTEN sonra → race yok.
    if not cont and prev.get("is_active"):
        try:
            # DENETIM 2026-08-17: burada coil-run kapatma + end_session ELLE yapiliyordu; iki eksigi
            # vardi. (1) `_emit_minute_averages()` CAGRILMIYORDU → devralinan seansin birikmis KISMI
            # dakikasi `_minute_acc`te KALIYOR ve bir sonraki dakika-loop turunda YENI (AI) seansin
            # db_session_id'si ile yaziliyordu: onceki hastanin sicaklik/akim ornekleri BASKA bir
            # seansin tibbi kaydina karisiyordu. (2) `ended_epoch` yazilmiyordu. Ikisi de
            # `_finalize_session_db`de zaten dogru: coil-run'lari kapatir, kismi dakikayi DOGRU
            # (eski) db_session_id'ye doker, buffer'i flush eder, end_session + ended_epoch yazar.
            # ⚠️ SENKRON DB isi: `start_ai_session`in cagricisi event-loop DISINDA (senkron
            # `def start_ai_pro` → FastAPI threadpool'u; D1.88'e kadar AI (Auto) landmark yolu da
            # `to_thread` ile cagiriyordu) → `_finalize_session_db`in "yalniz thread'lerden" sozlesmesi korunur.
            # ⚠️ Coil-run kapatma BURADA kalir, `_finalize_session_db`e devredilmez: finalize
            # `if not db_session_id: return 0` ile ilk satirda doner, yani DB satiri hic acilmamis
            # bir seansta acik coil-run'lar kapatilmadan kalirdi (eski davranis kapatiyordu).
            for _cid in prev.get("coil_ids") or []:
                try:
                    _finish_coil_run(_cid)
                except Exception:
                    pass
            _finalize_session_db(
                prev.get("db_session_id"),
                prev.get("started_epoch") or prev.get("start_time"),
                reason="ai-devralma",
                start_mono=prev.get("start_mono"),
            )
            logging.getLogger(__name__).warning(
                "AI seansi (%s) aktif MANUEL seansi devraldi → eski seans (db_id=%s) duzgun kapatildi (orphan onlendi).",
                mode,
                prev.get("db_session_id"),
            )
        except Exception:  # pragma: no cover — SAVUNMA: _finalize_session_db hatayı içeride yakalar
            logging.getLogger(__name__).exception("AI gecisinde eski manuel seans kapatma hatasi")

    # DENETIM 2026-08-17 (hasta-verisi karismasi, `/api/session/start` ile SIMETRI): manuel yol
    # yeni seansta `_minute_acc` + `_sensor_sample_buffer`i temizliyordu (bkz. `start_session`),
    # AI yolu TEMIZLEMIYORDU. Sonuc: onceki seanstan kalan kismi-dakika ve flush edilmemis sensor
    # ornekleri, `_flush_sensor_buffer_if_active` GUNCEL `db_session_id`yi kullandigi icin YENI AI
    # seansinin satirina yaziliyordu → yanlis seansa/hastaya ait tibbi kayit.
    # ⚠️ Yukaridaki finalize onceki seansin verisini KENDI satirina zaten dokuyor; buradaki temizlik
    # (a) DB satiri hic acilmamis seans (finalize ilk satirda doner) ve (b) hic aktif seans olmayan
    # ama buffer'da artik kalan durum icin. Finalize yazimi basarisiz olup ornekleri buffer'a GERI
    # koyduysa da temizlenirler: veri kaybi, YANLIS HASTAYA yazmaktan iyidir (manuel yolun karari).
    # ⚠️ `cont=True` (ayni AI seansinin tekrarli cagrisi — D1.88'e kadar landmark auto_adjust her istekte cagiriyordu)
    # yolunda TEMIZLENMEZ; aksi halde suren seansin kendi telemetrisi her istekte silinirdi.
    if not cont:
        with _minute_acc_lock:
            _minute_acc.clear()
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer.clear()

    # DENETIM P1: otonom (AI Pro / AI Auto) tedavinin DB seans satirini AC. Eskiden hic
    # acilmadigi icin canli hayvana uygulanan dozun, dakika-ortalamali sensor/sicaklik
    # telemetrisinin ve seansin kendisinin KALICI KAYDI YOKTU (buffer 20k tavaninda kirpilip
    # atiliyordu). Yalniz YENI seansta (cont=False) acilir; tekrarli AI cagrilari mevcut
    # satiri kullanir. Y65: satır fonksiyonun BAŞINDA (devralmadan önce) açıldı; burada yalnız başlangıç damgası yazılır.
    if _ai_sid is not None:
        try:
            _db = _get_treatment_db()
            if cont and _db is not None:
                # Yarış (anlık görüntüde yeni seans, kilitte AI (Auto) devamı): açılan satır KULLANILMADI → "İptal Edildi"
                # (`_finalize_session_db` DEĞİL: o, süren seansın kısmi dakikasını bu satıra dökerdi).
                _db.end_session(_ai_sid, duration_minutes=0, session_status="cancelled")
            elif _db is not None:
                # ODD B-4: seansın sürüş frekansı (mühür) ve ODAK dozu (mT) — geçmiş kartı "0 Hz" / "Yoğunluk —" gösteriyordu.
                _db.set_session_meta(
                    _ai_sid,
                    started_epoch=_started_epoch_ai,
                    patient_id=_ai_pid,
                    frequency_hz=(kayit or {}).get("frek_hz"),
                    intensity_mt=(kayit or {}).get("doz_mT"),
                )
                if _sahip_epostasi:
                    _db.set_session_parameter(_ai_sid, "patient_owner_email", _sahip_epostasi, "")
        except Exception:
            logging.getLogger(__name__).debug("AI set_session_meta hatasi", exc_info=True)
    # 1-C inceleme i1-F3: çağıran geri almayı bu kimliğe bağlar (`_seansi_geri_al(..., kimlik)`; bugün AI Pro `/start`,
    # D1.88'e kadar AI (Auto) landmark).
    return _new_session_id


def _kayit_suresi_dk(start_mono, started_epoch):
    """Seans KAYIT süresini (dakika) hesapla — MONOTONIC öncelikli, wall-clock geri-çekilmeli.

    ⚠️ DST/SAAT-DEĞİŞİMİ (denetim 2026-08-30): kayıt süresi `time.time()` farkından hesaplanıyordu.
    Duvar saati ileri/geri giderse (NTP/DST/manuel) RAPORLANAN süre gerçekten sapıyordu (max(0,…)
    negatifi engelliyordu ama değeri yanlış). Gerçek tedavi zaten monotonic watchdog'la
    güvencedeydi (bkz. start_mono, hardware_controller deadline) — bu yalnız KAYDI düzeltir.
    `start_mono` varsa ondan (saat-değişiminden bağımsız); yoksa eski wall-clock yolu (geriye
    uyumlu: recovery gibi monotonic snapshot'ı olmayan yollar). Negatif clamp korunur."""
    if start_mono is not None:
        try:
            return max(0, int((time.monotonic() - float(start_mono)) / 60))
        except (TypeError, ValueError):
            pass
    if started_epoch:
        try:
            return max(0, int((time.time() - float(started_epoch)) / 60))
        except (TypeError, ValueError):
            return None
    return None


#: D5 (D3 devri, sağlamlık · 2-C inc. §9 #5): kapanış yazımı (`end_session` + bitiş damgası) başka bir yazıcının UZUN işleminde
#: `busy_timeout` (5 sn) sonunda `database is locked` ile düşüyordu; kimse yeniden denemiyordu → operatörün durdurduğu seans `active`
#: kalıyor, sonraki açılışta "Elektrik Kesintisi" mühürleniyordu [ÖLÇTÜM]. Kilit hatasında bu süre boyunca yeniden denenir.
#: `_finalize_session_db` YALNIZ iş parçacıklarından çağrılır (olay döngüsü / ACİL DURDUR beklemez; STOP kapanıştan ÖNCE gider).
#: Kapı: tests/test_seans_KAPANISI_uzun_kilitte_DUSMEZ_D5.py
KAPANIS_KILIT_SURESI_SN = 20.0
_KAPANIS_DENEME_ARASI_SN = 0.5


def _kilit_hatasi_mi(e: BaseException) -> bool:
    m = str(e).lower()
    return "locked" in m or "busy" in m


def _finalize_session_db(db_session_id, started_epoch, coil_ids=None, reason: str = "auto", start_mono=None) -> int:
    """Seansi DB'de KAPAT: kismi dakika-ortalamasi + sensor buffer flush + end_session/ended_epoch.

    DENETIM P2: /api/session/stop DISINDAKI bitis yollari DB'ye HIC dokunmuyordu:
      - sure-watchdog otomatik tamamlanmasi (frontend timer bitiminde /stop CAGIRMAZ → NORMAL
        tam-sure bitisi de bu yoldan gecer),
      - acil durdurma (_emergency_stop_all).
    Sonuc: treatment_sessions satiri kalici 'active' kalir (KPI/gecmis sisir), son dakikanin
    sensor/sicaklik verisi ve acik coil-run'lar KAYBOLUR — acil durdurmada guvenlik olayinin
    telemetri kaniti da yok olur. SENKRONDUR: yalniz thread'lerden cagrilir (watchdog / e-stop
    thread'i), event-loop'tan DEGIL.
    """
    if not db_session_id:
        return 0
    # Acik coil-run'lari kapat (watchdog yolunda _stop_session_coils zaten yapar; e-stop yapmaz).
    for _cid in coil_ids or []:
        try:
            _finish_coil_run(_cid)
        except Exception:
            logging.getLogger(__name__).debug("finalize: _finish_coil_run(%s) hatasi", _cid, exc_info=True)
    flushed = 0
    try:
        _emit_minute_averages()  # birikmis KISMI dakikayi da buffer'a dok (yoksa kaybolur)
    except Exception:
        logging.exception("finalize: dakika-ortalamasi hatasi")
    try:
        with _sensor_sample_buffer_lock:
            pending = list(_sensor_sample_buffer)
            _sensor_sample_buffer.clear()
        db = _get_treatment_db()
        if db is not None:
            if pending:
                try:
                    flushed = db.add_sensor_samples_batch(db_session_id, pending)
                except Exception:
                    logging.exception("finalize: sensor flush hatasi")
                # DENETIM P2: yazim BASARISIZSA (istisna ya da sessiz 0) ornekleri KAYBETME —
                # buffer'a geri koy ki bir sonraki flush (dakika-loop / sonraki finalize)
                # yeniden denesin. Buffer'in kendi 20k tavani sinirsiz buyumeyi zaten onler.
                if not flushed:
                    with _sensor_sample_buffer_lock:
                        _sensor_sample_buffer[:0] = pending
                    logging.warning("finalize: %d sensor ornegi yazilamadi → buffer'a geri konuldu.", len(pending))
            try:
                _now = time.time()
                dur_min = _kayit_suresi_dk(start_mono, started_epoch)
                # ⚠️ SEBEP ARTIK KAYDA DA GECER (kampanya bulgusu S09). `reason` buraya zaten
                # tasiniyordu ama YALNIZ loglaniyordu → acil durdurma ile biten seans gecmiste
                # normal bitenden ayirt EDILEMIYORDU ("bu hastada e-stop yasandi mi?" cevapsiz).
                from database.treatment_history_db import (
                    SEANS_DURUMU_ACIL_DURDURMA,
                    SEANS_DURUMU_DONANIM_REDDI,
                )

                _sebep = str(reason or "")
                if _sebep.startswith("acil-durdurma"):
                    _durum = SEANS_DURUMU_ACIL_DURDURMA
                elif _sebep.startswith("donanim-reddi"):
                    # ⚠️ Donanım komutu reddetti → seans HİÇ başlamadı. "completed" yazmak,
                    # uygulanmamış bir tedaviyi uygulanmış olarak belgelemek olurdu.
                    _durum = SEANS_DURUMU_DONANIM_REDDI
                elif _sebep.startswith("iptal"):
                    # 1-C §9 #5: başlatma bobin sürülmeden İPTAL edildi (durdurma geldi) → "İptal Edildi".
                    _durum = "cancelled"
                elif _sebep.startswith("ai-pro-durdurma"):
                    # ODD B-4 (ODK-B keşfi 18-11): operatör AI Pro'yu ELLE durdurdu → "Durduruldu" (`stopped`; KPI "Dur./Hata"da
                    # sayılır). Eskiden "completed" → Raporlar "Tamamlanma %100", planlanan süre verilmemişken tamamlanmış görünüyordu.
                    _durum = "stopped"
                elif _sebep.startswith("ai-pro-kesinti"):
                    # D2.E07 (YA-1): AI Pro döngüsü KENDİ kesildi (hedef kaybı / doz modeli hatası / kamera) → "Kesintiye Uğradı".
                    _durum = "interrupted"
                elif _sebep.startswith("ai-devralma"):
                    # D2.E06 (YA-2) · sahip kararı Y90: AI seansının DEVRALDIĞI (planlanan süresi dolmadan kapatılan) elle
                    # seans → "Kesintiye Uğradı" (D1.75 ile aynı ilke; "completed" verilmemiş süreyi tamamlanmış gösterirdi).
                    _durum = "interrupted"
                elif _sebep.startswith("kapanis"):
                    # D1.75 (B-1.22): backend seans ortasında KAPANDI (servis durdurma / Ctrl+C) → "Kesintiye Uğradı".
                    # "completed" planlanan süre dolmamışken yanlış; satırı açık bırakmak ise sonraki açılışta
                    # "Elektrik Kesintisi" (ABORTED_DUE_TO_POWER) mühürlüyordu — olmamış bir güç kaybı.
                    _durum = "interrupted"
                else:
                    _durum = "completed"
                _son = time.monotonic() + KAPANIS_KILIT_SURESI_SN  # D5: kilitte sınırlı yeniden deneme (yukarıdaki not)
                # Sınırlı döngü (sonsuz `while True` DEĞİL — daemon döngüsü kapısı `test_dongu_hata_bildirimi_OLDURMEZ`).
                _kapandi = False
                while not _kapandi:
                    try:
                        db.end_session(db_session_id, duration_minutes=dur_min, session_status=_durum)
                        db.set_session_meta(db_session_id, ended_epoch=_now)
                        _kapandi = True
                    except Exception as _e:
                        if not _kilit_hatasi_mi(_e) or time.monotonic() >= _son:
                            raise
                        logging.warning(
                            "finalize: tedavi DB'si kilitli — seans kapanisi yeniden deneniyor (db_id=%s)",
                            db_session_id,
                        )
                        time.sleep(_KAPANIS_DENEME_ARASI_SN)
            except Exception:
                logging.exception("finalize: end_session hatasi")
        # notes ucu cift-kayit yapmasin (bkz. session_router db_finalized kontrolu).
        with _session_lock:
            if _active_session.get("db_session_id") == db_session_id:
                _active_session["db_finalized"] = True
        logging.info("Seans DB'de kapatildi (%s): db_id=%s, %d sensor satiri", reason, db_session_id, flushed)
    except Exception:
        logging.exception("finalize: kalici kayit hatasi")
    _bekleyen_vacuumu_arka_planda()  # D1.58: ertelenmiş KVKK VACUUM'u (seans bitti)
    return flushed


def _bekleyen_vacuumu_arka_planda() -> None:
    """D1.58 (B-3.88): seans bittiğinde ertelenmiş KVKK VACUUM'u AYRI iş parçacığında koş (durdurma yanıtını bekletmez);
    o arada yeni seans başladıysa YAPILMAZ (bir sonraki seans sonunda / bakımda)."""

    def _kos():
        try:
            with _session_lock:
                if _active_session.get("is_active"):
                    return
            db = _get_treatment_db()
            if db is not None and hasattr(db, "bekleyen_vacuum_calistir"):
                db.bekleyen_vacuum_calistir()
        except Exception:
            logging.getLogger(__name__).warning("Ertelenmis KVKK VACUUM'u calistirilamadi", exc_info=True)

    try:
        threading.Thread(target=_kos, name="kvkk-vacuum", daemon=True).start()
    except Exception:
        logging.getLogger(__name__).warning("KVKK VACUUM is parcacigi acilamadi (bakimda denenecek)")


def kapanis_seansi_pasife_al() -> dict | None:
    """D1.75 (B-1.22): backend KAPANIRKEN aktif seansı bellekte kapat — donanım STOP'undan ÖNCE, yalnız bellek (beklemez).

    Çağıran (`backend_service._shutdown`) önce `estop_mandali.kapanis_kur()` ile START'ı reddeder, sonra bunu çağırır,
    sonra STOP'u gönderir, EN SON `kapanis_seans_kaydini_kapat` ile DB satırını kapatır (DB yazımı STOP'u geciktirmez).
    AI Pro döngüsü pasif seansı ve kapanışı görüp çıkar; teardown'ı kapanışta da STOP gönderir (`mandalli_mi`).
    @return DB kapanışı için anlık görüntü; seans yoksa None."""
    with _session_lock:
        if not _active_session.get("is_active"):
            return None
        anlik = {
            "db_session_id": _active_session.get("db_session_id"),
            "started_epoch": _active_session.get("started_epoch") or _active_session.get("start_time"),
            "start_mono": _active_session.get("start_mono"),
            "coil_ids": list(_active_session.get("coil_ids") or list(range(1, 9))),
            "mode": _active_session.get("mode"),
        }
        _active_session["is_active"] = False
    return anlik


def kapanis_seans_kaydini_kapat(anlik) -> None:
    """D1.75: `kapanis_seansi_pasife_al`ın görüntüsüyle DB satırını "Kesintiye Uğradı" kapatır (STOP'tan SONRA)."""
    if not anlik or not anlik.get("db_session_id"):
        return
    _db_sid = anlik["db_session_id"]
    try:
        _get_treatment_db().record_session_event(
            _db_sid, "service_shutdown", payload={"mode": anlik.get("mode"), "coil_ids": anlik.get("coil_ids")}
        )
    except Exception:
        logging.getLogger(__name__).warning("kapanis: session_event yazilamadi", exc_info=True)
    _finalize_session_db(
        _db_sid,
        anlik.get("started_epoch"),
        coil_ids=anlik.get("coil_ids"),
        reason="kapanis",
        start_mono=anlik.get("start_mono"),
    )


def _session_duration_watchdog():
    """KRİTİK GÜVENLİK: seans süresi dolunca bobinleri DONANIM düzeyinde durdurur.
    Firmware keep-alive süreyi her sn tazelediğinden tek başına auto-stop OLMAZ; bu watchdog
    süre dolunca açık STOP üretir (planlanandan uzun PEMF maruziyetini önler)."""
    import time as _t

    while True:
        try:
            with _session_lock:
                sess = dict(_active_session)
            if sess.get("is_active"):
                total = int(sess.get("duration_minutes", 0)) * 60
                _sm = sess.get("start_mono")
                _elapsed = (
                    (_t.monotonic() - _sm) if _sm is not None else (_t.time() - sess.get("start_time", _t.time()))
                )
                # ⚠️ D1.70 (B-1.8 · sahip kararı Y5): seans ORTASINDA girilen süre KALAN süredir —
                # `parametre_guncelle` kesin bitiş anını (`bitis_mono`) yazar; varsa o esastır (yoksa planlanan toplam).
                _bm = sess.get("bitis_mono")
                _doldu = (_t.monotonic() >= float(_bm)) if _bm is not None else (total > 0 and _elapsed >= total)
                if _doldu:
                    # Audit P2 (TOCTOU seal): fiziksel STOP'tan HEMEN önce seansın HÂLÂ aynı olduğunu
                    # doğrula — aksi halde operatör A'yı durdurup B'yi aynı bobinlerde başlattıysa bayat
                    # snapshot B'nin TAZE bobinlerini durdurur + coil-run'larını bozar (pencere ~µs'e iner).
                    with _session_lock:
                        _still_same = bool(_active_session.get("is_active")) and _active_session.get(
                            "session_id"
                        ) == sess.get("session_id")
                    if not _still_same:
                        continue  # seans devralındı/durduruldu → bayat watchdog turu dokunmasın
                    _bildir_teyitsiz_stop(
                        _stop_session_coils(sess.get("coil_ids", list(range(1, 9))), yetkiyi_kes=True),  # D1.81
                        lambda d: ceviri.t("bildirim.kaynak.sureDoldu", dil=d),
                    )
                    with _session_lock:
                        if _active_session.get("session_id") == sess.get("session_id"):
                            _active_session["is_active"] = False
                    # DENETIM P2: seansi DB'de de KAPAT. Frontend timer bitiminde /stop
                    # cagirmadigindan NORMAL tam-sure bitisi buradan gecer; eskiden satir
                    # kalici 'active' kaliyor ve son dakikanin sensor verisi kayboluyordu.
                    _finalize_session_db(
                        sess.get("db_session_id"),
                        sess.get("started_epoch"),
                        reason="sure-doldu",
                        start_mono=sess.get("start_mono"),
                    )
                    try:
                        update_live_session_state(is_active=False, mode="Sistem Hazır")
                        _ws_broadcast_sync(
                            {"type": "session_completed", "data": {"session_id": sess.get("session_id")}}
                        )
                    except Exception:
                        pass
                    logging.info("Süre doldu → seans otomatik durduruldu (watchdog): %s", sess.get("session_id"))
        except Exception:
            _dongu_hatasini_bildir("session_duration_watchdog hata")
        _t.sleep(1)


# (audit B-2.2) session-watchdog başlatma _start_background_threads()'e taşındı (lifespan startup).


def _hardware_simulation_loop():
    """PEMF_SIMULATE=1: gerçek donanım yokken sanal bobin + sensör verisi üretip WS ile
    yayınlar (Dashboard/Sensör/Kontrol/KPI testleri için). Seans aktifken bobinler seansın
    freq/duty'siyle 'çalışıyor' görünür; aksi halde boşta.

    ⚠️ BAYATLIK DÜZELTİLDİ (2026-09-20, sahip bildirimi). Bu döngü üç yerde GERÇEĞİ
    AŞIYORDU ve üçü de simülasyonu ürüne göre FAZLA İYİMSER yapıyordu:

      1. `for idx in range(8)` ELLE yazılmıştı. Topoloji tek kaynak `live_state`'te
         (`STM_COIL_IDS` / `ESP_COIL_IDS`); 2026-09-10'da bobin 6-7 ESP'den STM'e taşındı
         ve bu döngü onu hiç görmedi. Aynı kural iki yerde = sessiz ayrışma.
      2. **HER bobine `objectTemp` uyduruyordu.** STM protokolünde SICAKLIK ALANI YOK
         (`tools/stm32_simulator.py`: 121 baytlık pakette sıcaklık yok); backend'de
         `objectTemp` YALNIZ MQTT yükünden gelir (`payload.get("object_temp")`). Yani
         STM'deki bobinler gerçekte HİÇ sıcaklık bildirmez. Sim onları bildiriyor gibi
         gösterince arayüzdeki "bu bobinde sıcaklık ölçümü yok — otomatik termal durdurma
         uygulanmaz" uyarısı SİMÜLASYONDA KAYBOLUYOR ve termal kesme testi var olmayan bir
         korumayı doğrulamış gibi yeşil veriyordu. Artık sıcaklık YALNIZ ölçebilen bobine
         (ESP/MQTT yolu) verilir; ötekiler `None` kalır ve arayüz doğruyu söyler.
      3. `mqtt`/`gateway` KOŞULSUZ "online" yazıyordu. ESP kapalıyken (`PEMF_ESP_ENABLED=0`)
         MQTT yok; durum `live_state.esp_etkin()`e bağlandı.
    """
    import math
    import random
    import time as _t

    # Topoloji TEK KAYNAKTAN. Elle sayı yazmak bu döngünün bayatlama sebebiydi.
    _stm = set(live_state.STM_COIL_IDS)
    _esp = set(live_state.ESP_COIL_IDS)
    _bobin_idleri = sorted(_stm | _esp)

    t0 = _t.time()
    while True:
        try:
            now = _t.time()
            el = now - t0
            with _session_lock:
                sess = dict(_active_session)
            active = bool(sess.get("is_active"))
            sfreq = float(sess.get("frequency") or 0)
            sduty = float(sess.get("duty") or 0)
            scoils = set(sess.get("coil_ids") or [])
            snaps = []
            esp_acik = live_state.esp_etkin()
            # CH4 · Y154: akım sensörü KAPALIYKEN sim de akım UYDURMAZ (0.0 = canlı durumun "ölçülmedi" varsayılanı).
            _akim = akim_olcumu_acik()
            with _live_state_lock:
                # ESP kapalıyken MQTT/gateway "online" DEĞİLDİR — sim gerçeği aşmasın.
                _live_state["gateway"] = "online" if esp_acik else "devre_disi"
                _live_state["mqtt"] = "online" if esp_acik else "devre_disi"
                _live_state["stm"] = "online"
                for cid in _bobin_idleri:
                    idx = cid - 1
                    coil = _live_state["coils"][idx]
                    # ESP bobini ancak ESP açıkken bağlıdır; STM bobinleri simde hep bağlı.
                    coil["connected"] = True if cid in _stm else esp_acik
                    # Sıcaklığı YALNIZ ölçebilen bobin bildirir (MQTT/ESP yolu).
                    sicaklik_olculur = (cid in _esp) and esp_acik
                    running = active and ((cid in scoils) if scoils else True)
                    coil["running"] = running
                    if running:
                        d = sduty or 25.0
                        coil["frequencyHz"] = round(sfreq or 50.0, 1)
                        coil["dutyCycle"] = round(d, 1)
                        coil["magneticMt"] = round(
                            d / 25.0 * 2.0 + 0.25 * math.sin(el * 2 + idx) + random.uniform(-0.04, 0.04), 3
                        )
                        coil["currentA"] = (
                            round(0.35 + d / 100.0 * 0.6 + random.uniform(-0.02, 0.02), 3) if _akim else 0.0
                        )
                        coil["objectTemp"] = (
                            round(
                                26.0
                                + min(el / 25.0, 14.0)
                                + 0.4 * math.sin(el * 0.5 + idx)
                                + random.uniform(-0.2, 0.2),
                                1,
                            )
                            if sicaklik_olculur
                            else None
                        )
                    else:
                        coil["frequencyHz"] = 0
                        coil["dutyCycle"] = 0
                        coil["magneticMt"] = round(abs(random.uniform(0, 0.05)), 3)
                        coil["currentA"] = round(abs(random.uniform(0, 0.02)), 3) if _akim else 0.0
                        coil["objectTemp"] = (
                            round(24.0 + 0.3 * math.sin(el * 0.3 + idx) + random.uniform(-0.2, 0.2), 1)
                            if sicaklik_olculur
                            else None
                        )
                    # Ortam sıcaklığı da aynı telemetriden gelir → ölçüm yoksa YOK.
                    coil["ambientTemp"] = round(23.0 + random.uniform(-0.3, 0.3), 1) if sicaklik_olculur else None
                    snaps.append(dict(coil))
            _kapi_durum = "online" if esp_acik else "devre_disi"
            _ws_broadcast_sync({"type": "gateway_status", "data": {"gateway": _kapi_durum, "mqtt": _kapi_durum}})
            _ws_broadcast_sync({"type": "stm_status", "data": {"stm": "online"}})
            for coil in snaps:
                _ws_broadcast_sync({"type": "coil_status", "coilId": coil["id"], "data": coil})
                _ws_broadcast_sync(
                    {
                        "type": "sensor_data",
                        "coilId": coil["id"],
                        "timestamp": now,
                        "data": {
                            "magneticMt": coil["magneticMt"],
                            "objectTemp": coil["objectTemp"],
                            "ambientTemp": coil["ambientTemp"],
                            "currentA": coil["currentA"],
                        },
                    }
                )
        except Exception:
            _dongu_hatasini_bildir("hardware sim loop error")
        _t.sleep(0.5)


def _emit_minute_averages(now=None):
    """Modul-duzeyi _minute_acc icindeki n>0 her bobin icin DAKIKA-ortalamasi satirini
    _sensor_sample_buffer'a ekler ve akumulatoru SIFIRLAR. Ayrica per-RUN istatistigini
    (_coil_run_stats) gunceller. Ham veri YERINE dakika-ortalamasi → 20dk seans ≈ bobin basina ~20 satir.
    Hem dakika-loop hem /api/session/stop (kismi dakika) cagirir; thread-safe."""
    if now is None:
        now = time.time()
    rows = []
    with _minute_acc_lock:
        snapshot = list(_minute_acc.items())
        _minute_acc.clear()
    for coil_id, acc in snapshot:
        n = acc.get("n", 0)
        if n <= 0:
            continue
        with _active_coil_runs_lock:
            run_id = _active_coil_runs.get(coil_id)
        _tn = acc.get("t_n", 0)
        _in = acc.get("i_n", 0)
        _bn = acc.get("b_n", 0)
        _an = acc.get("amb_n", 0)
        # ⚠️ D1.69 (B-1.7 · S-1.3 · sahip kararı Y6): metrik o dakika HİÇ ölçülmediyse NULL — 0.0 DEĞİL. Eskiden "eski
        # davranışla birebir" diye 0.0 yazılıyordu: bobin 1-5 (yalnız akım ölçer) her dakika "0,0 °C / 0,0 mT ölçüldü",
        # seans grafiği 0 °C çizgisi çizip "sensör verisi yok"u bastırıyordu. Tüketiciler NULL'a hazır (şema REAL NULL,
        # `/api/history/details`, arayüz grafiği `Number.isFinite` ile atlar). Ölçülen gerçek 0 → 0.0 (ayırt edilir).
        amb_avg = (acc["amb_sum"] / _an) if _an else None
        rows.append(
            {
                "coil_id": str(coil_id),
                "sample_ts": now,
                "temperature_c": (acc["t_sum"] / _tn) if _tn else None,
                "ambient_temp_c": amb_avg,
                "current_a": (acc["i_sum"] / _in) if _in else None,
                "magnetic_field_mt": (acc["b_sum"] / _bn) if _bn else None,
                "pwm_frequency_hz": acc.get("freq"),
                "pwm_duty_percent": acc.get("duty"),
                "phase": acc.get("phase"),
                "sample_count": n,
                "coil_run_id": run_id,
                "payload": {"aggregated": True, "minute": True},
            }
        )
        # Per-RUN ozet akumulatoru: dakika-ortalamasi run istatistigine de katki saglar.
        if run_id is not None:
            with _coil_run_stats_lock:
                st = _coil_run_stats.get(run_id)
                if st is not None:
                    st["n"] += n
                    st["t_sum"] += acc["t_sum"]
                    st["i_sum"] += acc["i_sum"]
                    st["b_sum"] += acc["b_sum"]
                    st["t_n"] = st.get("t_n", 0) + acc.get("t_n", 0)
                    st["i_n"] = st.get("i_n", 0) + acc.get("i_n", 0)
                    st["b_n"] = st.get("b_n", 0) + acc.get("b_n", 0)
                    tmn, tmx = acc.get("t_min"), acc.get("t_max")
                    if tmn is not None:
                        st["t_min"] = tmn if st["t_min"] is None else min(st["t_min"], tmn)
                    if tmx is not None:
                        st["t_max"] = tmx if st["t_max"] is None else max(st["t_max"], tmx)
    if rows:
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer.extend(rows)
            if len(_sensor_sample_buffer) > 20000:
                del _sensor_sample_buffer[: len(_sensor_sample_buffer) - 20000]


def _flush_sensor_buffer_if_active():
    """P2 audit 2026-06-28: aktif seansin db_session_id'si varsa _sensor_sample_buffer'i DB'ye yaz
    (periyodik kalicilastirma → cokmede/20k-cap'te telemetri kaybini onler). Basarisizsa GERI koyar.
    Yalniz arka-plan _sensor_persistence_loop thread'inden cagrilir → event-loop'u bloklamaz."""
    with _session_lock:
        _db_sid = _active_session.get("db_session_id")
    if not _db_sid:
        return
    with _sensor_sample_buffer_lock:
        pending = list(_sensor_sample_buffer)
        _sensor_sample_buffer.clear()
    if not pending:
        return
    try:
        _get_treatment_db().add_sensor_samples_batch(_db_sid, pending)
    except Exception:
        with _sensor_sample_buffer_lock:
            _sensor_sample_buffer[:0] = pending  # geri koy (sonraki flush/stop yazar)
        logging.getLogger(__name__).debug("periyodik sensor flush hatasi", exc_info=True)


def _sensor_persistence_loop():
    """Aktif seans boyunca her ~2sn _live_state'ten ÇALIŞAN bobinlerin sensör değerlerini
    DAKIKA-ortalama akumulatorunde toplar (canli WS yayini KORUNUR; yayin sim/HW kendi
    looplarinda). Her 60sn'de per-bobin dakika-ortalamasi _sensor_sample_buffer'a yazilir.
    Buffer /api/session/notes + /api/session/stop ile gercek db_session_id ile flush edilir.
    Boylece HAM yazma YERINE dakika-ortalamasi (20dk seans ≈ bobin basina ~20 satir)."""
    import time as _t

    minute_start = _t.time()
    while True:
        # D1.67: susan sensorun alani seans olsun olmasin '—'ye duser (yalniz gosterim; durdurma YOK).
        try:
            _olculen_alanlari_tazele()
        except Exception:
            _dongu_hatasini_bildir("olculen alan tazelik denetimi hatasi")
        try:
            with _session_lock:
                active = bool(_active_session.get("is_active"))
            if active:
                _simdi_m = time.monotonic()
                with _live_state_lock:
                    coils = [dict(_live_state["coils"][i]) for i in range(8)]
                    _taze = {i: _taze_alanlar_locked(i, _simdi_m) for i in range(8)}
                with _minute_acc_lock:
                    for coil in coils:
                        if not coil.get("running"):
                            continue
                        try:
                            cid = int(coil.get("id"))
                        except Exception:
                            continue
                        # DENETIM P2 (sahte olcum): STM bobinlerinde (1-5) sicaklik/akim/alan
                        # telemetrisi YOKTUR — seri protokol yalniz duty/phase/freq/duration
                        # dondurur ve update_live_coil_from_stm bu alanlara hic dokunmaz. Ama
                        # _live_state baslangic degeri 0.0 oldugu icin "is not None" kontrolu
                        # onu GERCEK olcum sayip DB'ye "temperature_c=0.0, sample_count=30"
                        # yaziyordu → gecmis/PDF raporunda "olculmedi" yerine "0.0 °C olculdu"
                        # gorunuyor, asiri-isinma analizi ve hasta sahibine giden rapor yanlis
                        # veriyle uretiliyordu. Olcum KAYNAGI (gercek MQTT telemetrisi) yoksa
                        # hic biriktirme → _emit_minute_averages n<=0 satirini zaten atlar.
                        # NOT: 0.0-yerine-NULL yolu BILEREK secilmedi; asagi-akis (PDF/KPI/grafik)
                        # 0.0 bekliyor (onceki denetimin bilincli karari) — sahte satiri hic
                        # uretmemek ayni sonucu downstream riski OLMADAN verir.
                        if _coil_last_telemetry.get(cid - 1) is None:
                            continue
                        # ⚠️ ALAN BAZINDA KAPI (2026-09-10): yukaridaki bobin-bazinda kapi
                        # ARTIK YETMEZ. Bobin 1-5 yalniz AKIM olcuyor, 6-7 yalniz sicaklik/
                        # alan. Olculmeyen alani biriktirmek DB'ye "0.0 olculdu" yazar.
                        # D1.67: yalniz TAZE alan — susan sensorun donmus degeri dakika satirina/run
                        # ozetine "olculdu" diye GIRMEZ.
                        _olculen = _taze.get(cid - 1) or set()
                        temp = coil.get("objectTemp")
                        cur = coil.get("currentA")
                        fld = coil.get("magneticMt")
                        amb = coil.get("ambientTemp")
                        acc = _minute_acc.get(cid)
                        if acc is None:
                            acc = {
                                "t_sum": 0.0,
                                "t_min": None,
                                "t_max": None,
                                "i_sum": 0.0,
                                "b_sum": 0.0,
                                "amb_sum": 0.0,
                                "n": 0,
                                "t_n": 0,
                                "i_n": 0,
                                "b_n": 0,
                                "amb_n": 0,
                                "freq": coil.get("frequencyHz"),
                                "duty": coil.get("dutyCycle"),
                                "phase": coil.get("phase"),
                            }
                            _minute_acc[cid] = acc
                        if temp is not None and "objectTemp" in _olculen:
                            tv = float(temp)
                            acc["t_sum"] += tv
                            acc["t_n"] += 1
                            acc["t_min"] = tv if acc["t_min"] is None else min(acc["t_min"], tv)
                            acc["t_max"] = tv if acc["t_max"] is None else max(acc["t_max"], tv)
                        if cur is not None and "currentA" in _olculen:
                            acc["i_sum"] += float(cur)
                            acc["i_n"] += 1
                        if fld is not None and "magneticMt" in _olculen:
                            acc["b_sum"] += float(fld)
                            acc["b_n"] += 1
                        if amb is not None and "ambientTemp" in _olculen:
                            acc["amb_sum"] += float(amb)
                            acc["amb_n"] += 1
                        acc["n"] += 1
                        # En guncel parametreleri sakla (dakika boyunca degisebilir).
                        acc["freq"] = coil.get("frequencyHz")
                        acc["duty"] = coil.get("dutyCycle")
                        if coil.get("phase") is not None:
                            acc["phase"] = coil.get("phase")
                # Dakika siniri: ortalama satirlarini emit et (akumulatoru sifirlar).
                if (_t.time() - minute_start) >= 60.0:
                    _emit_minute_averages(_t.time())
                    _flush_sensor_buffer_if_active()  # P2 audit: periyodik DB flush (cokme/cap kaybi onle)
                    minute_start = _t.time()
            else:
                minute_start = _t.time()
        except Exception:
            _dongu_hatasini_bildir("sensor persistence loop error")
        _t.sleep(2.0)


# (audit B-2.2) sensor-persist başlatma _start_background_threads()'e taşındı (lifespan startup).


def _daily_maintenance_loop():
    """Asama-2 (4): GUNLUK arka-plan bakim — retention temizligi + haftalik VACUUM. YEDEK ALMAZ.
    - Retention: session_events (PEMF_RETAIN_EVENT_DAYS, vars. 365, 0 = silme — headless bakımla aynı ayar; B2-1.6).
      ⚠️ D2.44 (B-4.18 · O-B2.1): sensör örneklerini bu döngü SİLMEZ — tek silici `services/headless_db_maintenance`
      (`PEMF_RETAIN_SENSOR_DAYS`, 0 = kapalı).
    - KVKK anonimlestirme turu (`services.kvkk_anonimlestirme.tur`; operator onayina bagli — D2.54 · A-06).
    - Haftada bir wal_checkpoint(TRUNCATE) + VACUUM (run_maintenance helper'i + VACUUM); seans yokken ertelenmis
      KVKK VACUUM'lari (tedavi DB'si D1.58, hasta DB'si Y121).
    - ⚠️ Gunluk .db yedegini BU DONGU ALMAZ (D6.07 · B-4.22): tek yedekleyici `services/headless_db_maintenance`
      (`_run_backup` → `create_backup`: online backup API; sifreli DB'de yedek de sifreli). Eskiden burada duz-metin
      dosya kopyasi aliniyordu — govdedeki "3) GUNLUK YEDEK" notu. Kapi: tests/test_belge_capalari_ve_yedek_iddiasi_D6_07.py
    Hata olursa loglanir, cokmez. Ilk calisma acilistan ~60sn sonra (acilisi yavaslatmamak icin)."""
    import time as _t

    log = logging.getLogger(__name__)
    _t.sleep(60)  # acilisi yavaslatma
    run_count = 0
    while True:
        try:
            db = _get_treatment_db()
            if db is not None:
                # 1) Retention temizligi.
                try:
                    # ⚠️ D2.44 (B-4.18 · O-B2.1): SENSÖR SİLME BU DÖNGÜDEN KALDIRILDI (dozdaki 2026-08-17 düzeltmesinin ikizi).
                    # Burası hiçbir yerde belgelenmemiş `PEMF_SENSOR_RETAIN_DAYS`i (vars. 90) okuyor ve `max(1, …)` ile siliyordu →
                    # dağıtım dosyasında `PEMF_RETAIN_SENSOR_DAYS=0` ("silme") yazan klinikte telemetri yine 90 günde gidiyor, eski
                    # ada 0 yazılırsa 1 GÜNDEN eski tüm telemetri siliniyordu (ölçüldü). Tek silici headless bakım; eski ad orada
                    # yalnız yeni ad yokken takma ad + uyarı. Kapı: tests/test_bakim_TEK_silici_sensor_sozlesmesi_D244.py
                    # ⚠️ B2-1.6: seans olayları (ACİL DURDUR kanıtı dahil) headless bakımla AYNI ayara uyar —
                    # `PEMF_RETAIN_EVENT_DAYS` (vars. 365, 0 = SİLME). Sabit 365 operatörün "silme"sini her gün eziyordu
                    # (dozdaki 2026-08-17 çelişkisinin aynısı). Kapı: tests/test_seans_olaylari_SAKLAMA_ayarina_uyar_B2_1_6.py
                    # S-F2-1.5: headless bakımla AYNI okuyucu (geçersiz / boş değer → adım KAPALI + WARNING; eskiden 365'e düşüyordu).
                    from services.headless_db_maintenance import HeadlessDBMaintenance as _HDM

                    _olay_gun = _HDM._retain_days("PEMF_RETAIN_EVENT_DAYS", 365)
                    removed_e = db.purge_old_session_events(_olay_gun) if _olay_gun > 0 else 0
                    # ⚠️ DOZ SİLME BU DÖNGÜDEN KALDIRILDI (denetim 2026-08-17). Burası
                    # `PEMF_SENSOR_RETAIN_DAYS` okuyordu — headless bakımın kullandığı
                    # `PEMF_RETAIN_SENSOR_DAYS`ten FARKLI, hiçbir yerde belgelenmemiş bir ad.
                    # Sonuç: operatör `PEMF_RETAIN_SENSOR_DAYS=0` yazıp "silme kapalı" sansa bile
                    # uygulanan doz 90 günde BURADAN silinmeye devam ediyordu. Üstelik bu yolda
                    # `0` = kapalı DEĞİLDİ: `purge_old_coil_runs` içindeki `max(1, ...)` yüzünden
                    # `0` → 1 GÜNLÜK saklama, yani neredeyse tüm doz geçmişi.
                    # Silme yeteneği kaybolmuyor: `services/headless_db_maintenance` üretimde her
                    # zaman koşuyor ve aynı işi `apply_data_retention_policy` üzerinden
                    # YAPILANDIRILABİLİR biçimde (`PEMF_RETAIN_DOSE_DAYS`) yapıyor.
                    log.info("Retention: %s event silindi.", removed_e)
                    # KVKK retention (2026-06-28): 5 YIL inaktif hastalari ANONIMLESTIR (canonical
                    # patient_database + treatment-history kopyasi). Muafiyet yok.
                    # ⚠️ D2.54 · A-06: anonimleştirme OPERATÖR ONAYINA bağlı (sessiz ve geri dönüşsüz işlem yok; A-09 onay eşiğe bağlı),
                    # tedavi-DB adımı düşerse sonraki turda yeniden denenir (B-3.34), AI kayıtları da anonimleşir (Y125), hekim atfı
                    # kalır (A-27). Eskiden burada onaysız `anonymize_inactive_patients(1825)` koşuyordu.
                    # Kapı: tests/test_kvkk_anonimlestirme_ONAYLI_ve_EKSIKSIZ_D254.py
                    try:
                        _pdb = get_patient_database()
                        if _pdb is not None:
                            from services import kvkk_anonimlestirme as _kvkk

                            _kvkk.tur(_pdb, db)
                    except Exception:
                        log.warning("Hasta retention (anonimlestirme) hatasi", exc_info=True)
                except Exception:
                    log.warning("Retention temizleme hatasi", exc_info=True)

                # 2) Haftada bir checkpoint + VACUUM.
                # DENETIM P3: kosul `run_count % 7 == 0` idi ve run_count 0'dan basladigi icin
                # VACUUM "haftada bir" DEGIL, HER BACKEND ACILISINDAN ~60 sn SONRA calisiyordu.
                # VACUUM tum DB'yi yeniden yazar ve OZEL kilit tutar; busy_timeout 5 sn oldugundan
                # o pencerede baslayan bir seansin sensor/coil-run yazimlari "database is locked"
                # ile dusebiliyordu (sessiz telemetri kaybi). Iki kapak: (a) ilk turda ATLA →
                # restart dongusu her seferinde VACUUM tetiklemesin; (b) AKTIF SEANS varken ATLA →
                # tedavi sirasinda DB'yi kilitleme (bir sonraki turda yapilir).
                _sess_active = False
                try:
                    with _session_lock:
                        _sess_active = bool(_active_session.get("is_active"))
                except Exception:
                    _sess_active = True  # emin degilsek VACUUM YAPMA (fail-safe)
                # D1.58 (B-3.88): ertelenmiş KVKK VACUUM'u (AI geçmişi silindiğinde seans sürüyordu) — seans yokken HER tur.
                if not _sess_active and hasattr(db, "bekleyen_vacuum_calistir"):
                    try:
                        db.bekleyen_vacuum_calistir()
                    except Exception:
                        log.warning("Ertelenmis KVKK VACUUM'u (bakim) hatasi", exc_info=True)
                if run_count > 0 and run_count % 7 == 0 and not _sess_active:
                    try:
                        if hasattr(db, "run_maintenance"):
                            db.run_maintenance()  # wal_checkpoint(TRUNCATE) + optimize
                        conn_fn = getattr(db, "_get_connection", None)
                        if conn_fn is not None:
                            with conn_fn() as conn:
                                cur = conn.cursor()
                                try:
                                    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                                except Exception:
                                    pass
                                # VACUUM islem (transaction) icinde calismaz → autocommit'e gec.
                                # ⚠️ D2.23 (B-3.79): bağlantı TreatmentHistoryDB'nin iş parçacığı başına HAVUZUNDAN gelir ve bu döngü
                                # iş parçacığında süreç ömrü boyunca KALIR → eski işlem kipi `finally`de GERİ YÜKLENİR. Eskiden autocommit
                                # kalıyordu: sonraki turların KVKK anonimleştirmesi (`anonymize_patients_by_uuid`) tek işlem sanılan üç
                                # UPDATE'i ayrı ayrı commit ediyor, ikincisi düşünce hasta kopyası [ANONIM] / seans geçmişinde ad kalıyordu
                                # (yarım anonimleştirme — ölçüldü). Kapı: tests/test_haftalik_VACUUM_havuz_baglantisini_KIRLETMEZ_D223.py
                                _onceki_kip = conn.isolation_level
                                try:
                                    conn.isolation_level = None
                                    cur.execute("VACUUM")
                                except Exception:
                                    log.warning(
                                        "Haftalik VACUUM yapilamadi (bir sonraki haftalik turda denenecek)",
                                        exc_info=True,
                                    )
                                finally:
                                    conn.isolation_level = _onceki_kip
                    except Exception:
                        log.warning("Haftalik VACUUM/checkpoint hatasi", exc_info=True)

                # 3) GUNLUK YEDEK: BURADA YAPILMIYOR (P1 cift-yazici cakismasi giderildi).
                # Yedegi services/headless_db_maintenance.py (HeadlessDBMaintenance) aliyor:
                # KEYED create_backup() → SIFRELI + atomik (sifreli DB'de duz-metin sizmaz).
                # Eskiden burada shutil.copy2 (duz-metin) ile AYNI backups/ dizinine + AYNI glob'a
                # (pemf_treatment_history_*.db, son-14) yaziliyordu → iki zamanlayici birbirinin
                # yedegini SILIYORDU ve PII duz-metin yedekleniyordu. Yedek tek noktada toplandi.

            # 4) Y121 (S-C.3 · D2.57): HASTA DB'sinin ertelenmiş KVKK VACUUM'u (toplu silmede düşmüştü) — ilk tur (açılıştan ~60 sn
            # sonra) ve her gün, YALNIZ seans yokken (VACUUM tüm DB'yi kilitler). Tedavi DB'sinden bağımsız.
            # Kapı: tests/test_hasta_DB_VACUUM_bekliyor_KALICI_Y121.py
            try:
                with _session_lock:
                    _seans_var = bool(_active_session.get("is_active"))
            except Exception:
                _seans_var = True  # emin degilsek VACUUM YAPMA (fail-safe)
            if not _seans_var:
                try:
                    _hdb = get_patient_database()
                    if _hdb is not None and hasattr(_hdb, "bekleyen_vacuum_calistir"):
                        _hdb.bekleyen_vacuum_calistir()
                except Exception:
                    log.warning("Hasta DB ertelenmis KVKK VACUUM'u (bakim) hatasi", exc_info=True)
        except Exception:
            _dongu_hatasini_bildir("daily maintenance loop genel hatasi", logger=log, seviye=logging.WARNING)
        run_count += 1
        _t.sleep(86400)  # gunde bir kez


_bg_threads_started = False


def _start_background_threads() -> None:
    """Arka-plan daemon thread'lerini başlat: safety süre-watchdog + sensör-persist + günlük-bakım
    (+ PEMF_SIMULATE ile sanal donanım). Idempotent — lifespan startup'tan BİR KEZ çağrılır (audit
    B-2.2: eskiden modül-import anında başlıyordu → import yan-etkisi; test/araç import'u gerçek
    thread açıyor, state.core set edilmeden). Fonksiyonlar bu noktada tanımlı."""
    global _bg_threads_started
    if _bg_threads_started:
        return
    _bg_threads_started = True
    _threading.Thread(target=_session_duration_watchdog, daemon=True, name="session-watchdog").start()
    _threading.Thread(target=_sensor_persistence_loop, daemon=True, name="sensor-persist").start()
    _threading.Thread(target=_daily_maintenance_loop, daemon=True, name="daily-maintenance").start()
    # ESP sessiz-ölüm (ungraceful) tespiti: 30sn telemetri sustuysa coil'i disconnected işaretle
    # (self-heal reconnect-audit). Sim modda no-op (timestamp sözlüğü boş).
    _threading.Thread(target=_esp_telemetry_watchdog, daemon=True, name="esp-telemetry-watchdog").start()
    # CANLI E-ALANI (2026-08-06): 2 Hz'de vekil modeli canlı B/duty ile çalıştırıp önbelleğe yazar.
    # AYRI thread olmasının sebebi: ONNX çağrısı dashboard-snapshot/WS istek yolunda ÇALIŞMASIN.
    # Yalnız aktif seansta + analiz bağlamı varken hesaplar (bkz. servers/efield_live.py).
    try:
        from servers import efield_live as _ef

        _ef.start_loop(
            read_coils=lambda: _build_ws_snapshot().get("coils", []),
            is_session_active=lambda: bool(_active_session.get("is_active")),
            # Y212 · S-D67.13: WS bağlıyken de akar (istemci yoklamayı atlar); periyodik tür → baskıda ilk o düşer.
            yayinla=lambda deger: _ws_broadcast_sync({"type": "efield_update", "data": deger}),
        )
    except Exception:
        logging.getLogger(__name__).warning("Canlı E-alanı döngüsü başlatılamadı", exc_info=True)
    if os.environ.get("PEMF_SIMULATE") == "1":
        _threading.Thread(target=_hardware_simulation_loop, daemon=True, name="hw-sim").start()
        logging.info("HARDWARE SIMULATION aktif (sanal STM+ESP+sensor) - PEMF_SIMULATE=1")


@app.post("/api/session/stop")
async def stop_session():
    """Stop the active treatment session.

    Asama-2: donanim durdurulduktan sonra seans+sensor KALICI yazilir (not beklenmez):
    bekleyen kismi dakika emit edilir, acik coil-run'lar kapatilir (run ozeti yazilir),
    sensor buffer'i gercek db_session_id ile flush edilir ve end_session ile GERCEK
    wall-clock sure yazilir. Hepsi best-effort (DB hatasi donanim durdurmayi engellemez)."""
    with _session_lock:
        _seans_var = bool(_active_session.get("is_active"))
        if _seans_var:
            coil_ids = _active_session.get("coil_ids", list(range(1, 9)))
            db_session_id = _active_session.get("db_session_id")
            started_epoch = _active_session.get("started_epoch") or _active_session.get("start_time")
            start_mono = _active_session.get("start_mono")  # kayıt süresi DST-güvenli (bkz. _kayit_suresi_dk)
            _stopping_session_id = _active_session.get("session_id")  # TOCTOU muhru (asagi bkz.)
            # 1-D inceleme i3-F-1: başlatma hâlâ UÇUŞTAYSA (sürüş sonrası denetim bitmedi) bu Durdur başlatmayı iptal
            # eder — başlatma 409 "BAŞLATILMADI" döner; satır "Tamamlandı" değil "İptal Edildi" kapanır.
            _ucustaki_baslatma = bool(_active_session.get("baslatma_ucusta"))
            _active_session["is_active"] = False
    if not _seans_var:
        # ⚠️ D1.81 (B-5.3 · İG-5.3): "Aktif seans yok" ARTIK STOP'SUZ DÖNMEZ. Ölçüldü: E-stop'un yarışında uçuştaki AI
        # turu bobinleri yeniden enerjiledikten sonra operatörün /session/stop'u "Aktif seans yok" deyip telde 0 STOP
        # bırakıyordu (keep-alive sürmeye devam). Seanssız sürüş (tekil/batch, eski bir AI turu) de durdurulmalı:
        # TÜM bobinlere STOP + yetki kesme. STOP idempotenttir (Ö.4-Y8: yalnız artar). O-1.1: KENDİ iş parçacığı.
        _teyitsiz = await _durdurma_is_parcaciginda(_seanssiz_durdur, ad="seanssiz-durdur") or []
        # 1-C inceleme i2-F3: seans yokken canlı durum "aktif" kalmasın (bayat bir yazımın takılı göstergesi ve açık seans
        # CSV'si — `update_live_session_state` sarmalayıcısı "aktif değil" yazımında CSV'yi kapatır). Mandal kuruluyken
        # "Acil Durdurma" kalır (live_state kuralı).
        update_live_session_state(is_active=False, mode="Sistem Hazır")
        _yanit_yok = {"status": "ok", "message": ceviri.t("seans.mesaj.aktifYokStop")}
        if _teyitsiz:
            _yanit_yok["hardware_stop_unconfirmed"] = _teyitsiz
        return _yanit_yok

    # (a) Bekleyen kismi dakikayi emit et — acik run-ozetine de katki saglar (finish'ten ONCE).
    try:
        _emit_minute_averages(time.time())
    except Exception:
        logging.getLogger(__name__).debug("stop: minute emit hatasi", exc_info=True)

    # Donanim STOP (ESP→MQTT, STM→update_coil). _stop_session_coils ayrica acik coil-run'lari kapatir.
    # P-1b: senkron _mqtt_publish (~2s/ESP-bobin) event-loop'u DONDURMASIN → to_thread (emergency_stop
    # deseniyle birebir; bobinler yine durur, sadece threadpool'da). Watchdog'dan (1327) cagri sync kalir.
    # DENETIM P2 (TOCTOU): yukarida is_active=False yapilip KILIT BIRAKILIYOR. Bu await
    # penceresinde (saglikli broker'da ~10-100 ms, cokuk broker'da saniyeler) BASKA bir istemci
    # /api/session/start atabilir → yeni seans bobinleri ENERJILER, hemen ardindan buradaki
    # _stop_session_coils AYNI fiziksel bobinleri durdurur: yeni seans sessizce olur (UI 'suruyor'
    # sanir, coil-run/sensor kayitlari bozulur). Sure-watchdog'da bu muhur (1600-1604 `_still_same`)
    # ZATEN vardi; /stop yolunda YOKTU. Donanima dokunmadan hemen once ayni seansta miyiz diye bak.
    with _session_lock:
        _takeover = bool(_active_session.get("is_active")) and _active_session.get("session_id") != _stopping_session_id
    # DENETIM 2. TUR [1.1]: donanim STOP'u dogrulanamayan bobinler yanita tasinir (asagida).
    _stop_teyitsiz: list = []
    if _takeover:
        logging.getLogger(__name__).warning(
            "stop: bu seans (%s) durdurulurken YENI seans (%s) baslamis → donanim STOP'u ATLANDI "
            "(bobinler yeni seansa ait).",
            _stopping_session_id,
            _active_session.get("session_id"),
        )
    else:
        # D1.81: seansı bitiren durdurma → yetki kesilir (uçuştaki START'lar bu STOP'tan sonra enerjileyemez).
        # O-1.1: KENDİ iş parçacığı — ortak havuz (`to_thread`) asılı G/Ç ile doluyken STOP sıra beklemez.
        # ⚠️ Y63 (sahip, 1-F S-F3): çalışan TÜM bobinler — seans sırasında seans DIŞINDAN (tekil / toplu / eski uç)
        # başlatılanlar dahil; onların koşu kaydı da ŞİMDİ kapanır (`_stop_session_coils`). Eskiden yalnız seansın listesi
        # duruyor, ötekiler keep-alive ile sürüyordu (1-F açık #1). STOP yalnız artar (Ö.4-Y8); seans kaydı değişmez.
        # Ek tespit HİÇBİR koşulda seansın KENDİ STOP'unu engellemez: hata → yalnız seansın bobinleri (eski kapsam).
        try:
            _seans_disi = _seans_disi_calisan_bobinler(coil_ids)
        except Exception:
            logging.getLogger(__name__).exception(
                "Y63: seans disi calisan bobinler belirlenemedi (seans STOP'u suruyor)"
            )
            _seans_disi = []
        _durdurulacak = sorted({int(c) for c in coil_ids} | set(_seans_disi))
        _stop_teyitsiz = (
            await _durdurma_is_parcaciginda(_stop_session_coils, _durdurulacak, True, ad="seans-durdur") or []
        )
        update_live_session_state(is_active=False, mode="Sistem Hazır")

    # (b) Sensor buffer'i gercek db_session_id ile FLUSH et + (c) end_session (gercek wall-clock sure).
    # P-2 fix: senkron SQLCipher yazimlari (add_sensor_samples_batch/end_session/set_meta) event-loop'u
    # BLOKLAMASIN → to_thread; buffer-grab + db_finalized-isaret hizli/async kalir.
    flushed = 0
    if db_session_id:
        try:
            with _sensor_sample_buffer_lock:
                pending = list(_sensor_sample_buffer)
                _sensor_sample_buffer.clear()

            def _persist_session_stop():
                _flushed = 0
                db = _get_treatment_db()
                if db is not None:
                    if pending:
                        try:
                            _flushed = db.add_sensor_samples_batch(db_session_id, pending)
                            logging.info("stop: sensor flush %d satir (session_id=%s)", _flushed, db_session_id)
                        except Exception:
                            logging.exception("stop: sensor flush hatasi")
                    try:
                        _now = time.time()
                        dur_min = _kayit_suresi_dk(start_mono, started_epoch)
                        db.end_session(
                            db_session_id,
                            duration_minutes=dur_min,
                            session_status="cancelled" if _ucustaki_baslatma else "completed",
                        )
                        # Yeni kolon: gercek wall-clock bitis epoch'u (end_session bunu yazmaz).
                        db.set_session_meta(db_session_id, ended_epoch=_now)
                    except Exception:
                        logging.exception("stop: end_session hatasi")
                return _flushed

            flushed = await asyncio.to_thread(_persist_session_stop)
            _bekleyen_vacuumu_arka_planda()  # D1.58: ertelenmiş KVKK VACUUM'u (seans bitti)
            # Bu seansin DB satiri kapandi → notes endpoint cift-kayit yapmasin.
            # YARIS FIX: kilit birakilip yeniden alindi; ARADA yeni bir seans BASLAMIS olabilir
            # (_active_session yeni dict ile degismis). db_finalized'i YENI seansa damgalama →
            # yalniz AYNI (bu) seans hala yerindeyse (is_active False + ayni db_session_id) isaretle.
            with _session_lock:
                if not _active_session.get("is_active") and _active_session.get("db_session_id") == db_session_id:
                    _active_session["db_finalized"] = True
        except Exception:
            logging.exception("stop: kalici kayit genel hatasi")
    else:
        # P2 audit 2026-06-28: db_session_id YOK → bu seansin sensor verisi DB'ye yazilamaz; eskiden
        # SESSIZCE kayboluyordu (sonraki seans start'inda buffer temizlenir). UYAR + buffer'i simdi
        # temizle (sonraki seansa sizmasin).
        with _sensor_sample_buffer_lock:
            _lost = len(_sensor_sample_buffer)
            _sensor_sample_buffer.clear()
        if _lost:
            logging.warning(
                "stop: db_session_id YOK → %d sensor satiri KALICI DEGIL (kayip). Seans DB'ye baglanmamis.", _lost
            )

    # DENETIM 2. TUR [1.1] (2026-08-20): ust-seviye status "success" KALIR (seans kaydi gercekten
    # kapatildi; mevcut cagiranlarin sozlesmesi bozulmaz) ama donanim STOP'u DOGRULANAMAYAN
    # bobinler ACIKCA listelenir. Eskiden broker oluyken bile kosulsuz "success" donuyordu →
    # istemcinin "Durdurma onaylanamadi — ACIL DURDUR'a basin" uyarisi HIC tetiklenmiyordu
    # (STOP hicbir bobine ulasmamisken UI seansi "durdu" gosterir). Alan yalniz teyitsizlik
    # VARSA eklenir — mutlu yolda yanit sekli birebir ayni (alarm yorgunlugu uretme).
    _yanit = {"status": "success", "message": ceviri.t("seans.mesaj.durduruldu"), "sensor_samples": flushed}
    if not _stop_teyitsiz:
        return _yanit

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # ⚠️ GÜVENLİK SİNYALİ SÖZLEŞMESİ — "BİLİNMİYORSA KÖTÜMSER" (sahip kararı 2026-08-22)
    #
    # [1.1]'in ilk hâli üst-seviye `status`u "success" bırakıp uyarıyı YENİ bir alana koyuyordu
    # (`hardware_stop_unconfirmed`). Sürüm kayması senaryosu ölçüldü: telefon eski sürümde
    # kalabilir (Android'de kurulumu İŞLETİM SİSTEMİ sorar; güncelleme zorunlu kılınamaz — bkz.
    # MobileUpdateGate). Eski istemcide o alanı okuyan kod YOKTUR ve kontrolü
    # `res.status === "error"` biçimindedir → tanımadığı her değeri BAŞARI sayar. Sonuç:
    # bobinler hâlâ çalışıyorken operatör düz "seans durduruldu" görüyordu. Yani düzeltme,
    # düzeltmeyi en çok gereken istemciye HİÇ ulaşmıyordu.
    #
    # ÇÖZÜM: uyarıyı yeni bir alana DEĞİL, eski istemcinin de anladığı KANALA koy → 2xx DIŞI
    # yanıt. Ölçülen davranış (apps/ui/src/services/apiClient.ts):
    #   · `!response.ok` → gövde `detail` alanı okunur ve `showError("Sunucu Hatası", detail)`
    #     ile EKRANA BASILIR → eski istemci uyarının METNİNİ görür,
    #   · çağrıya `null` döner → `useSessionControl` "Durdurma onaylanamadı … ACİL DURDUR'a
    #     basın" uyarısını gösterir → eylem TAVSİYESİ de doğru olur.
    # Yeni istemci `onHttpError` ile 409'u ayırt eder, seansı kapatır ve SPESİFİK bobin
    # listesini gösterir (aşağıdaki alanlar korunur).
    #
    # ⚠️ 2xx SEÇİLEMEZ: 207 Multi-Status da `response.ok`tur → eski istemci yine sessizce
    # başarı sayardı. Fail-safe olması için yanıt 2xx DIŞI olmalıdır. 409 Conflict seçildi:
    # istek işlendi (seans kaydı GERÇEKTEN kapandı) ama donanım durumu çelişkili.
    #
    # ⚠️ SEANS KAYDI KAPANDI — bu bir "işlem başarısız" durumu DEĞİLDİR. `session_closed: true`
    # alanı bunu açıkça söyler ki yeni istemci UI'da seansı yeniden "açık" göstermesin.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    _teyitsiz_bobinler = ", ".join(str(c) for c in _stop_teyitsiz)
    _uyari = ceviri.t("seans.uyari.stopDogrulanamadi", bobinler=_teyitsiz_bobinler)

    # ⚠️ UYARI KAYBOLMAYACAK BİR YERE DE DÜŞER (sahip kararı 2026-08-22, 3. madde): telefon eski
    # sürümdeyse ya da ekranı kimse görmüyorsa uyarı yok olmasın. Bildirim akışı klinik
    # bilgisayarındaki arayüzde görünür (masaüstü arayüzü paketle birlikte GÜNCELDİR) ve günlüğe
    # yazılır — böylece uyarı en azından BİRİNE ulaşır ve destek sonradan izini sürebilir.
    try:
        _bildir(
            lambda d: "🚨 " + ceviri.t("seans.uyari.stopDogrulanamadi", dil=d, bobinler=_teyitsiz_bobinler), "error"
        )
    except Exception:  # noqa: BLE001 — bildirim yolu çökse bile yanıt DÖNMELİ
        logging.exception("stop: teyitsiz-durdurma bildirimi gonderilemedi")
    logging.error("stop: donanim STOP DOGRULANAMADI — bobinler=%s", _stop_teyitsiz)

    _yanit["status"] = "hardware_stop_unconfirmed"
    _yanit["message"] = _uyari
    _yanit["detail"] = _uyari  # eski istemci YALNIZ bunu görebiliyor (apiClient showError)
    _yanit["hardware_stop_unconfirmed"] = _stop_teyitsiz
    _yanit["session_closed"] = True
    return JSONResponse(status_code=409, content=_yanit)


def _dosya_adi_guvenli(ad: str) -> str:
    """Dosya adına girecek metni güvenli hâle getirir (yol ayıracı / PII kaçağı yok)."""
    temiz = "".join(c for c in str(ad or "") if c.isalnum() or c in ("_", "-"))
    return temiz[:40] or "kayit"


class AiLogPayload(BaseModel):
    # Geriye-uyumlu alanlar (eski istemci yalnız bunları gönderir):
    patient_name: str = ""
    module: str = ""  # modül etiketi → module_label
    summary: str = ""  # sonuç özeti → result_summary
    # 2026-07 profesyonel DETAYLI kayıt — yeni istemci ayrıca gönderir:
    mode: str = ""  # profil (pet_owner/veterinarian/researcher)
    module_id: str = ""  # AiModule id (em_fantom, kidney_ct, ...)
    input_type: str = ""  # image / clinical / audio / csv ...
    result_detail: dict = {}  # tam sonuç JSON (heterojen)
    confidence: float | None = None
    operator_email: str = ""  # klinik-içi sahiplik — analizi yapan hekim ("Benim/Tüm Klinik")
    #: Hastanın OPAK KİMLİĞİ (2026-09-12). Ada göre eşleme aynı adlı iki hayvanda karışıyor,
    #: ad düzeltilince kopuyor ve PII maskelemesi açıkken tümüyle çöküyordu.
    #: ⚠️ BOŞ GEÇİLEBİLİR: kimlik göndermeyen ESKİ istemcide davranış AYNI kalır (ada bağlı).
    patient_id: str = ""


_ai_migrate_lock = _threading.Lock()


_ai_kimlik_tasima_lock = _threading.Lock()
_ai_kimlik_tasindi = False
#: D2.22 (B-3.85): taşımanın yapıldığı tedavi DB'sinin `system_settings`inde KALICI işaretlenir (yeniden açılışta tekrar koşmaz).
_AI_KIMLIK_TASIMA_ISARETI = "ai_hasta_kimlik_tasimasi_yapildi"


def _ai_hasta_kimliklerini_tasi_bir_kez(db) -> dict:
    """ESKİ AI analizlerine hasta KİMLİĞİ yaz — TEK SEFERLİK, best-effort, thread-safe.

    ═══════════════════════════════════════════════════════════════════════════════
    ⚠️ BELİRSİZ ADI TAHMİN ETMEZ
    ═══════════════════════════════════════════════════════════════════════════════
    Harita hasta defterinden kurulur ve YALNIZ TEK BİR hastaya çözülen adları içerir.
    Aynı ada sahip iki hayvan varsa o ad haritaya HİÇ KONMAZ → o analizler kimliksiz kalır
    ve eskisi gibi ada bağlı çalışır. Yanlış kimlik yazmak, taşımanın çözmeye çalıştığı
    sorunu KALICI hâle getirirdi: bir hayvanın analizi başka bir hayvanın kaydına gömülür
    ve ad belirsizliğinin aksine bu geri alınamazdı.

    ⚠️ NEDEN BURADA (API katmanı), DB İÇİNDE DEĞİL: hasta defteri AYRI bir veritabanıdır
    (`database/patient_database`). Tedavi-DB'nin ona uzanması iki depoyu birbirine bağlardı;
    harita burada kurulup DB'ye VERİ olarak geçilir.
    """
    global _ai_kimlik_tasindi
    if db is None or _ai_kimlik_tasindi:
        return {}
    with _ai_kimlik_tasima_lock:
        if _ai_kimlik_tasindi:
            return {}
        # ⚠️ D2.22 (B-3.85): "bir kez" KALICI — yalnız süreç bayrağı her açılışta sıfırlanıyordu: ilk koşuda aynı adlı iki hayvan
        # yüzünden BİLEREK kimliksiz bırakılan eski analiz, sonradan biri silinip ad tekilleşince bir sonraki açılışta kalan
        # hayvanın kimliğine BAĞLANIYORDU (ölçüldü). İşaret aynı DB'de: yedekten dönen DB kendi işaretini taşır. Taşıma DÜŞERSE
        # işaret konmaz (sonraki açılışta yeniden denenir). Kapı: tests/test_ai_kimlik_tasimasi_KALICI_tek_seferlik_D222.py.
        if getattr(db, "_get_system_setting", None) and db._get_system_setting(_AI_KIMLIK_TASIMA_ISARETI) == "1":
            _ai_kimlik_tasindi = True
            return {}
        try:
            from database.patient_database import get_patient_database
            from utils.turkce_metin import arama_katla

            pdb = get_patient_database()
            hastalar = pdb.get_all_patients(kati=True) if pdb else []
            # Ad → kimlik; ÇAKIŞAN adlar ELENİR (tekil çözülmeyen ad taşınmaz).
            sayac: dict = {}
            for h in hastalar or []:
                ad = arama_katla(h.get("name") or "")
                kimlik = str(h.get("id") or "")
                if not ad or not kimlik:
                    continue
                sayac.setdefault(ad, set()).add(kimlik)
            harita = {ad: next(iter(k)) for ad, k in sayac.items() if len(k) == 1}
            cakisan = [ad for ad, k in sayac.items() if len(k) > 1]
            if cakisan:
                logging.getLogger(__name__).warning(
                    "AI kimlik tasimasi: %d ad BIRDEN COK hastaya cozuluyor -> o analizler "
                    "kimliksiz BIRAKILDI (tahmin edilmedi).",
                    len(cakisan),
                )
            sonuc = db.ai_analiz_kimliklerini_doldur(harita)
            if sonuc.get("hata"):
                return sonuc  # C2-1.2: taşıma yazamadı → işaret konmaz, sonraki açılışta yeniden denenir
            db._set_system_setting(
                _AI_KIMLIK_TASIMA_ISARETI, "1", "AI analiz ad->kimlik tasimasi yapildi (D2.22: tek seferlik, kalici)"
            )
            _ai_kimlik_tasindi = True
            return sonuc
        except Exception:
            logging.getLogger(__name__).exception("AI hasta kimligi tasimasi basarisiz (kayitlar DEGISMEDI).")
            return {}


def _migrate_ai_jsonl_once(db) -> None:
    """Eski düz-metin ai_diagnoses.jsonl → şifreli ai_analyses (TEK SEFERLİK, best-effort, THREAD-SAFE).
    Çift-kontrollü kilit: iki eşzamanlı istek DUPLICATE kayıt üretemez. Yalnız POST yolunda çağrılır
    (GET read-only kalsın); başarılı taşımada dosya .migrated'a taşınır → sonraki çağrılarda no-op."""
    try:
        p = _app_data_dir() / "ai_diagnoses.jsonl"
        if db is None or not p.exists():
            return  # hızlı yol — kilit gerektirmez
        with _ai_migrate_lock:
            if not p.exists():
                return  # başka thread taşımış (kilit altında yeniden-kontrol → duplicate yok)
            for ln in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(ln)
                    db.add_ai_analysis(
                        module_label=r.get("module", ""),
                        patient_name=r.get("patient_name", ""),
                        result_summary=r.get("summary", ""),
                        result_detail={"legacy": True, "timestamp": r.get("timestamp", "")},
                    )
                except Exception:
                    pass
            p.rename(p.with_name("ai_diagnoses.jsonl.migrated"))
    except Exception:
        logging.exception("ai jsonl migrate failed")


def _hasta_adi_kimlikten(hasta_kimligi: str) -> str:
    """D2.69 (B-6.29): AI kaydı hasta KİMLİĞİYLE gelip adı boşsa ad hasta defterinden doldurulur (eski/hatalı istemci). Bilinmeyen
    kimlik ya da okunamayan defter → '' (ad UYDURULMAZ; kayıt yine kimliğe bağlıdır)."""
    try:
        from database.patient_database import get_patient_database

        pdb = get_patient_database()
        h = pdb.get_patient(hasta_kimligi) if pdb else None
        return str((h or {}).get("name") or "").strip()
    except Exception:
        logging.getLogger(__name__).warning("AI kaydi: hasta adi kimlikten okunamadi (ad bos kaldi).", exc_info=True)
        return ""


def _ad_doldurma_izni(request) -> bool:
    """S-A1.3 (a) · Y123 (2-C incelemesi): D2.69 ad doldurması bu isteğe açık mı? Kayıtlı operatörlü cihazda JETONSUZ bir LAN
    isteği hasta kimliğinden ADI öğrenemez (Y103: aynı istemciye hasta listesi zaten kapalı — kimlik→ad kâhini kapanır; kayıt
    yine kimlikle yazılır). Jetonlu hekim, operatörsüz klinik (Kural 2) ve cihazın kendi ekranı değişmez. Kimlik DB'si
    okunamazsa doldurulmaz (fail-closed — Y113). Senkron (kimlik DB okuması): olay döngüsü DIŞINDA çağrılır."""
    try:
        from servers import auth as _auth
        from servers import operator_tokens as _jetonlar

        if _jetonlar.cozumle(_auth._operator_jetonu(request)) or _auth.cihazin_kendisinden_mi(request):
            return True
        return not _auth.kayitli_operator_var()
    except Exception:
        logging.getLogger(__name__).warning("AI kaydi: ad doldurma izni belirlenemedi -> doldurulmadi", exc_info=True)
        return False


@app.post("/api/ai/log")
async def log_ai_result(payload: AiLogPayload, request: Request):
    """AI analiz sonucunu ŞİFRELİ (SQLCipher) geçmişe profesyonel+detaylı kaydeder (ai_analyses tablosu).
    Eski düz-metin JSONL + isim-maskeleme KALDIRILDI — şifreli olduğundan hasta adı TAM (KVKK-güvenli).

    ⚠️ D2.56 (B-3.86): kayıt YAZILAMAZSA "success" DÖNMEZ — 503 + eylem söyleyen gerekçe. Eskiden `add_ai_analysis` hatayı
    (disk korkuluğu dahil) yutup `None` döndürüyor, uç `200 {"status": "success", "id": None}` veriyordu → arayüz sessiz,
    hekim analizin geçmişe yazıldığını sanıyordu (değerlendirme ve PDF üretilemez). İstemci (`apiPost`) `!ok` yanıtta
    gerekçeyi bildirim olarak gösterir; eski LAN istemcileri de (A-01) aynı genel yoldan görür.
    Kapı: tests/test_ai_log_YAZILAMAZSA_basari_DONMEZ_D256.py (+ arayüz aiKaydiYazilamadi.D256)."""
    _yazilamadi = ceviri.t("ai.hata.gecmiseYazilamadi")
    try:
        db = _get_treatment_db()
        if db is None:
            raise HTTPException(status_code=503, detail=_yazilamadi)
        await asyncio.to_thread(_migrate_ai_jsonl_once, db)
        # ⚠️ Eski kayıtlara hasta kimliği yaz (tek seferlik, idempotent, best-effort).
        # Yalnız YAZMA yolunda: GET read-only kalmalı (jsonl taşımasıyla aynı ilke).
        await asyncio.to_thread(_ai_hasta_kimliklerini_tasi_bir_kez, db)
        from servers.auth import cozumlenmis_operator

        _hasta_kimligi = str(payload.patient_id or "").strip()
        _hasta_adi = str(payload.patient_name or "").strip()
        if _hasta_kimligi and not _hasta_adi and await asyncio.to_thread(_ad_doldurma_izni, request):
            _hasta_adi = await asyncio.to_thread(_hasta_adi_kimlikten, _hasta_kimligi)
        # SG.G2: kayıt profili istemcinin gönderdiği `mode` (geçerliyse); değilse isteğin profili (`X-PEMF-Profil`); o da yoksa
        # gönderilen değer AYNEN (okumada modülden türetilir — `utils/profil.ai_kaydi_profili`).
        from utils.profil import gecerli_profil as _gecerli_profil
        from utils.profil import istek_profili as _istek_profili

        _kayit_profili = _gecerli_profil(payload.mode) or _istek_profili(request) or (payload.mode or "").strip()
        rid = await asyncio.to_thread(
            db.add_ai_analysis,
            _kayit_profili,
            payload.module_id,
            payload.module,
            _hasta_adi,
            payload.input_type,
            payload.summary,
            payload.result_detail or {},
            payload.confidence,
            # ⚠️ 2026-08-09 (Tier 1): AI analizinin sahibi de jetondan türetilir — aksi hâlde
            # "bu teşhisi kim yaptı" sorusunun cevabı doğrulanmamış bir dizeydi.
            cozumlenmis_operator(request, payload.operator_email),
            _hasta_kimligi,
        )
        if rid is None:
            raise HTTPException(status_code=503, detail=_yazilamadi)
        return {"status": "success", "id": rid}
    except HTTPException:
        raise
    except Exception:
        logging.exception("log_ai_result failed")
        raise HTTPException(status_code=503, detail=_yazilamadi)


class AiReviewPayload(BaseModel):
    analysis_id: int
    status: str = ""  # approved | rejected | corrected
    note: str = ""  # red gerekçesi ya da hekimin düzeltilmiş teşhisi
    reviewed_by: str = ""  # karar veren hekimin e-postası


@app.post("/api/ai/log/review")
async def review_ai_analysis(payload: AiReviewPayload, request: Request):
    """AI analizine HEKİM DEĞERLENDİRMESİ ekle (2026-08-06, sahip isteği).

    AI çıktısı bir ÖNERİdir; klinik karar hekimindir. Onay/red/düzeltme kaydın YANINA yazılır —
    AI'ın ne dediği ile hekimin ne dediği ayrı ayrı görünür kalır (sonradan "model ne demişti?"
    sorusu cevaplanabilsin). Kayıt silinmez, AI sonucu değiştirilmez.
    """
    if payload.status not in ("approved", "rejected", "corrected"):
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.durumGecersiz"))
    # Red ve düzeltme GEREKÇESİZ olamaz: boş bir "reddedildi" denetim izinde işe yaramaz ve
    # modeli iyileştirmek için de veri taşımaz. Onay için not opsiyonel.
    if payload.status in ("rejected", "corrected") and not (payload.note or "").strip():
        raise HTTPException(status_code=422, detail=ceviri.t("ai.hata.gerekceZorunlu"))
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=503, detail=ceviri.t("ai.hata.kayitDbKullanilamiyor"))
    # ⚠️ D2.41 (B-2.3): "bu teşhisi kim onayladı" kaydı İSTEMCİ BEYANINDAN değil sunucu kuralından (jeton; kanıtsız
    # kayıtlı-hekim beyanı → sahipsiz; operatörsüz klinikte beyan — Kural 2). Eskiden LAN'dan jetonsuz başka bir hekimin adı
    # yazılabiliyordu. Kapı: tests/test_kayit_atfi_COZUMLENMIS_operator_D241.py.
    from servers import audit_log as _iz
    from servers import operator_tokens
    from servers.auth import _operator_jetonu, cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    _jetonlu = bool(operator_tokens.cozumle(_operator_jetonu(request)))
    _inceleyen = cozumlenmis_operator(request, payload.reviewed_by)
    # ⚠️ D2.19 (B-3.37): kayıt alanları her değerlendirmede ÜZERİNE yazılır; karar GEÇMİŞİ denetim izinde (append-only)
    # tutulur — eskiden önceki red/düzeltme iz bırakmadan siliniyordu. Kimlik KAYNAĞI işaretlenir: "jeton" (doğrulanmış),
    # "beyan" (jetonsuz kabul — Kural 2, DOĞRULANMAMIŞ), "yok" (kimlik çözülemedi; kanıtsız kayıtlı-hekim beyanını
    # `kimlikli_yaz` `kanitsiz_beyan` olarak saklar). İÇERİK YAZILMAZ: gerekçe METNİ ize girmez, yalnız varlığı.
    # Kapı: tests/test_ai_degerlendirme_IZI_D219.py.
    _iz_detay = {
        "analysis_id": int(payload.analysis_id),
        "status": payload.status,
        "gerekce_var": bool((payload.note or "").strip()),
        "kimlik_kaynagi": "jeton" if _jetonlu else ("beyan" if _inceleyen else "yok"),
    }
    # ⚠️ Y88 (İG-6.26 · D2.42): cihazda kayıtlı operatör varken kimliği ÇÖZÜLEMEYEN değerlendirme YAZILMAZ — 428. Eskiden
    # jetonsuz `reviewed_by: ""` 200 alıyor, kayıt imzasız "Hekim onayladı" oluyordu (D2.41'in sahipsiz yazması bu kolu
    # kapatmıyordu — ölçüldü). Deneme izde `reddedildi` olarak kalır (sinyal kaybolmasın). Kayıtlı operatörü OLMAYAN
    # klinik (Kural 2) ve A-01 (LAN erişim sınıfı) etkilenmez. Kapı: tests/test_degerlendirme_KIMLIKSIZ_428_Y88.py.
    if not _inceleyen and kayitli_operator_var():
        _iz.kimlikli_yaz(
            request,
            "ai.review",
            beyan=payload.reviewed_by,
            scope=f"ai_analiz:{int(payload.analysis_id)}",
            outcome="reddedildi",
            detail=_iz_detay,
        )
        # Y113: kimlik DB'si okunamıyorsa ileti arızayı ve çareyi söyler ("Operatör seçin" DEMEZ).
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("ai.kimlik.degerlendirme")),
        )
    ok = await asyncio.to_thread(db.set_ai_review, int(payload.analysis_id), payload.status, payload.note, _inceleyen)
    if not ok:
        raise HTTPException(status_code=404, detail=ceviri.t("ai.hata.analizYok"))
    # ⚠️ B2-2.4: iz, KAYDA yazılan kimliği taşır — kimlik İSTEKTEN yeniden çözülmez (değerlendirme yazılırken başka sekmenin
    # "Kilitle"si jetonu düşürürse kayıt Ayşe'yi, iz sahipsizi gösteriyordu). Kapı: tests/test_degerlendirme_IZI_KAYITLA_AYNI_kimlik_kilit_yarisi_B224.py
    _iz.yaz(
        request,
        "ai.review",
        operator_email=_inceleyen,
        scope=f"ai_analiz:{int(payload.analysis_id)}",
        detail=_iz_detay,
    )
    return {"status": "success", "analysisId": payload.analysis_id, "review": payload.status}


@app.get("/api/ai/log")
async def get_ai_log(
    request: Request,
    limit: int = 50,
    module_id: str = "",
    patient_name: str = "",
    before_id: int = 0,
    patient_id: str = "",
):
    """AI analiz geçmişini döndürür (yeni önce). Filtre: modül / hasta / keyset-pagination.

    ⚠️ `patient_id` TERCİH EDİLEN hasta süzgecidir (2026-09-12): ad bazlı süzme aynı adlı iki
    hayvanda karışır, ad düzeltilince kopar, PII maskelemesi açıkken çöker.
    ⚠️ `patient_name` ile BİRLİKTE verilirse VEYA ile bağlanır → kimliği yazılmış YENİ kayıtlar
    ile aynı hastanın ESKİ (kimliksiz) kayıtları TEK listede görünür; aksi hâlde taşıma günü
    geçmiş ikiye bölünmüş gibi görünürdü.

    ⚠️ OPERATÖR SÜZGECİ YOKTUR (bilinçli): kapsam kararı istemcide, `patientScope` tek
    kaynağıyla verilir. Çağıran ekranların hepsi `kapsamda()` ile süzmek ZORUNDADIR —
    kapı: tests/test_kapsam_sahipligi.py.
    ⚠️ PROFİL SÜZGECİ BURADA (SG.G2, 2026-10-14): istek `X-PEMF-Profil` bildiriyorsa yalnız o profilin kayıtları (sayfalama
    süzülmüş kümeyle tutarlı); bildirmeyen eski istemci (yayınlanmış APK) bugünkü gibi süzgeçsiz.
    """
    from utils.profil import istek_profili

    try:
        db = _get_treatment_db()
        if db is None:
            return {"status": "success", "data": []}
        data = await asyncio.to_thread(
            db.get_ai_analyses,
            int(limit),
            module_id or None,
            patient_name or None,
            (int(before_id) or None),
            (patient_id or None),
            istek_profili(request),
        )
        # ⚠️ Y126 (S-A2.3): bu liste LAN'dan JETONSUZ (A-02) — önceki değerlendirmelerin METİNLERİ (red gerekçesi, düzeltilmiş
        # teşhis; hasta adı / klinik bulgu taşıyabilir) listede TAŞINMAZ, yalnız SAYISI; metinler kayıt ayrıntısında
        # (`GET /api/ai/log/{id}` — Y122). Listelenen kayıtlar DEĞİŞMEZ. Kapı: tests/test_ai_gecmisi_DEGERLENDIRME_GECMISI_ayrintida_Y122_Y126.py
        for k in data:
            k["review_history_count"] = len(k.pop("review_history", None) or [])
        return {"status": "success", "data": data}
    except Exception:
        logging.exception("get_ai_log failed")
        return {"status": "error", "detail": ceviri.t("ai.hata.logOkunamadi"), "data": []}


@app.get("/api/ai/log/{analiz_id}")
async def get_ai_log_kaydi(request: Request, analiz_id: int):
    """TEK AI kaydı + ÖNCEKİ değerlendirmelerin metinleri (Y122 "Önceki değerlendirmeler": karar, metin, hekim, zaman).

    ⚠️ Y122 / Y126: metinler kaydı görebilen hekime — kimlik kuralı silme/değerlendirmeyle aynı: cihazda kayıtlı operatör VARSA kimlik
    YALNIZ operatör jetonundan (kimliksiz → 428); YOKSA (Kural 2, tek hekimli klinik) serbest. Tünel/uzak kuralı değişmez (ara katman).
    PDF bu ucu kullanmaz ve geçmişi basmaz."""
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    def _kimlik_tamam() -> bool:
        return (not kayitli_operator_var()) or bool(cozumlenmis_operator(request))

    if not await asyncio.to_thread(_kimlik_tamam):
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("ai.kimlik.oncekiDegerlendirmeler")),
        )
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=503, detail=ceviri.t("ai.hata.kayitDbAcilamadi"))
    kayitlar = await asyncio.to_thread(db.get_ai_analyses, 1, None, None, int(analiz_id) + 1)
    kayit = next((k for k in (kayitlar or []) if int(k.get("id", 0)) == int(analiz_id)), None)
    if not kayit:
        raise HTTPException(status_code=404, detail=ceviri.t("ai.hata.analizYok"))
    kayit["review_history_count"] = len(kayit.get("review_history") or [])
    return {"status": "success", "data": kayit}


def _enforce_privileged(request: Request) -> None:
    """Yıkıcı/PII ucu kapısı — LAN muafiyeti YOK (bkz. servers/auth.enforce_privileged).

    2026-08-09 denetimi (ENGEL): bu uçlar tüm hasta geçmişini dışarı verebiliyor ya da geri
    dönülemez silebiliyordu ve `is_local_request` LAN'ı auth-muaf saydığı için klinik WiFi'sindeki
    HERHANGİ bir cihaz kimliksiz çağırabiliyordu.
    """
    from servers.auth import enforce_privileged

    enforce_privileged(request)


class AiLogDeletePayload(BaseModel):
    """Tekil silme. `operator_email` doluysa yalnız O KİŞİYE ait kayıt silinebilir."""

    id: int
    operator_email: str = ""


class AiLogDeleteAllPayload(BaseModel):
    """Toplu silme. `confirm` ZORUNLU (yanlış-tık/otomatik-istek koruması — hasta silmedeki kural).

    `operator_email` doluysa yalnız o kişinin (ve sahipsiz) kayıtları silinir.

    ⚠️ DENETİM 2026-08-09 (Tier 1) — BOŞ `operator_email` ARTIK "HEPSİNİ SİL" DEMEK DEĞİL.
    Eski kural "boşsa TÜM klinik geçmişi gider" idi ve bu, kimliğin kaybolduğu HER durumu
    sessizce klinik-geneli silmeye çeviriyordu: çoklu-operatör kipinde kimse seçilmemişse
    istemcinin `operatorEmail`i bilerek "" döner → "kendi kayıtlarımı sil" isteği kliniğin
    TÜM AI geçmişini silerdi. Kimlik yokluğu ile "hepsini sil" NİYETİ artık ayrı:
    klinik-geneli silme `all_operators: true` ile AÇIKÇA istenmelidir.
    """

    confirm: str = ""
    operator_email: str = ""
    #: Klinik-geneli silme NİYETİ. Kimliksiz + bayraksız istek REDDEDİLİR (fail-closed).
    all_operators: bool = False


@app.get("/api/ai/log/{analiz_id}/pdf")
async def ai_analiz_pdf(request: Request, analiz_id: int, kaydet: int = 0):
    """Tek bir AI analizini PDF olarak ver — EV SAHİBİ PAYLAŞIMI (sahip isteği 2026-09-12).

    ⚠️ NEDEN EKLENDİ: ev sahibi profili analiz yapabiliyordu ama sonucu veterinerine
    GÖNDEREMİYORDU — PDF üretimi yalnız SEANS kayıtları için vardı. Analizi ekran
    görüntüsüyle paylaşmak hem eksik (sayısal detay kayboluyor) hem de kayıtsızdı.

    ⚠️ ERİŞİM SINIFI — D3.04 · A-02 (SAHİBİN KENDİ SEÇENEĞİ, 2026-10-01): AI geçmişi listesi (`GET /api/ai/log`) VE tek kaydın
    PDF'i LAN'dan TOKEN'SIZ. Tutarlılık A-01 yönünde kuruldu: liste ucu zaten LAN'a açıktı (hasta adı + `result_detail`, sayfa başına
    500, keyset ile tamamı) — tek kaydın PDF'ini ondan sıkı tutmak koruma sağlamıyordu. Tünel / uzak istek kuralı DEĞİŞMEZ: uzaktan
    gelen istek kimlik ara katmanında jeton ister (uç auth-muaf DEĞİL). Eskiden (2026-09-12) `_enforce_privileged` LAN'ı da
    reddediyordu. Risk kaydı (A-01): klinik Wi-Fi'ına giren cihaz AI geçmişini okuyabilir. Toplu silme (`/api/ai/log/delete_all`)
    AYRICALIKLI kalır. Kapı: tests/test_D3_04_ai_gecmisi_liste_ve_PDF_AYNI_erisim_sinifi_A02.py

    ⚠️ `kaydet=1`: masaüstü uygulaması WebView2'de dosya indiremiyor → backend AYNI
    makinede olduğunda dosyayı O yazar ve yolunu döndürür (seans raporlarıyla AYNI desen,
    bkz. history_router._diske_kaydet). D3.05: yalnız cihazın kendi ekranından; LAN / uzak isteğe akış.
    """
    try:
        db = _get_treatment_db()
        if db is None:
            raise HTTPException(status_code=503, detail=ceviri.t("ai.hata.kayitDbAcilamadi"))
        # ⚠️ TEKİL OKUMA UCU YOK: liste ucundan süzüyoruz. `before_id = analiz_id + 1` ile
        # keyset o kaydın KENDİSİNDEN başlar (id DESC), yani ilk satır aranan kayıttır.
        kayitlar = await asyncio.to_thread(db.get_ai_analyses, 1, None, None, int(analiz_id) + 1)
        kayit = next((k for k in (kayitlar or []) if int(k.get("id", 0)) == int(analiz_id)), None)
        if not kayit:
            raise HTTPException(status_code=404, detail=ceviri.t("ai.hata.analizYok"))

        # ⚠️ GECİKMELİ IMPORT: `FileResponse`/`Path` bu dosyada modül seviyesinde YOK
        # (backend açılış süresi için import grafiği dar tutuluyor). Uç nadir çağrılır.
        from pathlib import Path

        from fastapi.responses import FileResponse
        from utils.ai_rapor_ogeleri import analiz_pdf_ogeleri

        ogeler = analiz_pdf_ogeleri(kayit)
        # 2026-10-18 (sahip: "tamamen türkçe ve anlaşılır olmalı" — okuyucu veteriner + hayvan sahibi)
        baslik = ceviri.t("pdf.ai.baslik", modul=kayit.get("module_label") or ceviri.t("pdf.ai.modulYok"))
        tmp_dir = _app_data_dir() / "temp_reports"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        cikti = str(tmp_dir / f"ai_{analiz_id}_{int(time.time() * 1000)}.pdf")

        from utils.pdf_report_generator import get_pdf_generator

        uretici = get_pdf_generator(_app_data_dir())
        yol = await asyncio.to_thread(
            uretici.generate_xai_report,
            baslik,
            ogeler,
            cikti,
            ceviri.t("pdf.ai.rapor"),
            ceviri.t("pdf.ai.ozet"),
            ceviri.t("pdf.ai.dipnot"),
        )

        _ad = f"PEMF_AI_{_dosya_adi_guvenli(kayit.get('patient_name') or 'analiz')}_{analiz_id}.pdf"
        from servers.history_router import _masaustune_yazilir_mi

        if _masaustune_yazilir_mi(kaydet, request):  # D3.05: yalnız cihazın kendi ekranı; LAN / uzak → akış
            from servers.history_router import _diske_kaydet, _safe_unlink

            try:
                veri = Path(yol).read_bytes()
            finally:
                _safe_unlink(yol)  # geçici PII PDF'i her durumda sil
            return _diske_kaydet(veri, _ad)

        from starlette.background import BackgroundTask as _BGT

        from servers.history_router import _safe_unlink

        return FileResponse(
            path=yol,
            media_type="application/pdf",
            filename=_ad,
            background=_BGT(_safe_unlink, yol),  # gönderim sonrası PII PDF'i sil
        )
    except HTTPException:
        raise
    except Exception:
        logging.exception("ai_analiz_pdf failed")
        raise HTTPException(status_code=500, detail=ceviri.t("ai.hata.raporOlusmadi"))


@app.post("/api/ai/log/delete")
async def delete_ai_log_entry(payload: AiLogDeletePayload, request: Request):
    """Tek bir AI analiz kaydını sil (KVKK silme hakkı)."""
    _enforce_privileged(request)
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.dbHazirDegil"))
    from servers import audit_log as _iz
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi
    from servers.silme_yetkisi import kimliksiz_detay

    # ⚠️ D2.20 (B-3.38 · A-10 · Y83): kapsam OTURUM KİMLİĞİNDEN (jeton; kayıtlı operatör yoksa — Kural 2 — beyan), gövdedeki
    # beyandan DEĞİL. Eskiden beyan edilen e-posta kapsamdı ve sahipsiz kayıtlar da "kendi" sayılıyordu → başka hekimin
    # beyanıyla onun kaydı, her kimlikle sahipsiz kayıtlar silinebiliyordu. Tekil "Kaydı sil" sahipsizi SİLMEZ (404);
    # sahipsizler yalnız "Tüm Klinik" toplu silmesinden gider. Kapı: tests/test_ai_gecmisi_SILME_KAPSAMI_jetondan_D220.py.
    # ⚠️ B2-1.2 (A-10): kayıtlı operatörlü cihazda beyan HİÇ kullanılmaz — `cozumlenmis_operator` KAYITSIZ bir beyanı
    # (paylaşılan giriş e-postası, cihazdan çıkarılmış hekim, uydurma adres) kabul eder; jetonsuz istek o e-postanın
    # kayıtlarını siliyordu (ölçüldü). Kapı: tests/test_ai_gecmisi_KAYITSIZ_beyan_SILEMEZ_B2_1_2.py
    _kayitli = kayitli_operator_var()
    _ham_beyan = (payload.operator_email or "").strip()
    _beyan = "" if _kayitli else _ham_beyan
    kimlik = cozumlenmis_operator(request, _beyan)
    if not kimlik:
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete",
            beyan=_beyan,
            scope=f"id={payload.id}",
            item_count=0,
            outcome="reddedildi",
            detail={"kanitsiz_beyan": _ham_beyan[:200]} if (_kayitli and _ham_beyan) else None,
        )
        if _kayitli:
            raise HTTPException(status_code=428, detail=kimliksiz_detayi(kimliksiz_detay()))  # Y113
        raise HTTPException(status_code=400, detail=ceviri.t("gecmis.hata.silmeKapsamiKendi"))
    ok = await asyncio.to_thread(db.delete_ai_analysis, int(payload.id), kimlik)

    if not ok:
        # Kayıt yok VEYA başkasına ait → ikisini AYIRMA (varlık sızdırmayalım).
        # ⚠️ BAŞARISIZ deneme de yazılır: bir hesabın başkasının kaydını silmeye çalışması,
        # başarılı silme kadar önemli bir sinyaldir.
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete",
            beyan=_beyan,
            scope=f"id={payload.id}",
            item_count=0,
            outcome="reddedildi",
        )
        raise HTTPException(status_code=404, detail=ceviri.t("gecmis.hata.kayitYokYetkisiz"))
    logging.getLogger(__name__).warning("KVKK: AI analiz kaydı silindi (id=%s).", payload.id)
    _iz.kimlikli_yaz(request, "ai_log.delete", beyan=_beyan, scope=f"id={payload.id}", item_count=1)
    return {"status": "success", "deleted": 1}


@app.post("/api/ai/log/delete_all")
async def delete_ai_log_all(payload: AiLogDeleteAllPayload, request: Request):
    """AI analiz geçmişini TOPLU sil — `{"confirm":"DELETE_ALL"}` ZORUNLU.

    Hasta toplu-silmesiyle AYNI kapı (bkz. patient_router.remove_all_patients): boş bir POST'un
    geri-dönülemez biçimde tüm geçmişi silmesini engeller.
    """
    _enforce_privileged(request)
    if payload.confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail=ceviri.t("hasta.hata.topluSilmeOnayTumu"))
    db = _get_treatment_db()
    if db is None:
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.dbHazirDegil"))
    from servers import audit_log as _iz
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi
    from servers.silme_yetkisi import kimliksiz_detay

    # ⚠️ D2.20 (B-3.38 · A-10 · A-56): "kendi" kapsamı OTURUM KİMLİĞİNDEN (jeton; kayıtlı operatör yoksa — Kural 2 — beyan)
    # ve YALNIZ kimliğin kayıtları — sahipsizlere dokunulmaz (eskiden beyan kapsamdı ve sahipsizler de gidiyordu: başka
    # hekimin jetonuyla A beyan edilince A'nın geçmişi VACUUM'lu silindi — ölçüldü). "Tüm Klinik" = `all_operators` VE
    # beyansız (çelişkili istekte DAR kapsam kazanır). Kayıtlı operatörlü cihazda kimliksiz silme (her iki kapsam) 428.
    beyan = (payload.operator_email or "").strip()
    tum_klinik = bool(payload.all_operators) and not beyan
    # ⚠️ B2-1.2 (A-10): kayıtlı operatörlü cihazda beyan HİÇ kullanılmaz (kayıtsız beyan kapsam olurdu — ölçüldü).
    # Kapı: tests/test_ai_gecmisi_KAYITSIZ_beyan_SILEMEZ_B2_1_2.py
    _kayitli = kayitli_operator_var()
    _beyan = "" if _kayitli else beyan
    kimlik = cozumlenmis_operator(request, _beyan)
    if not kimlik and _kayitli:
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete_all",
            beyan=_beyan,
            scope="TUM_KLINIK" if tum_klinik else "kendi",
            item_count=0,
            outcome="reddedildi",
            detail={"kanitsiz_beyan": beyan[:200]} if beyan else None,
        )
        raise HTTPException(status_code=428, detail=kimliksiz_detayi(kimliksiz_detay()))  # Y113
    op = None if tum_klinik else (kimlik or None)
    # ⚠️ Y112 (S-B2.4): "Tüm Klinik" TAMAMI yalnız CİHAZIN KENDİ ekranından (loopback; tünel/ters-proxy sayılmaz — A-03 ile
    # aynı) ve kimlikli hekimle. Cihaz DIŞINDAN (LAN cihaz token'ı, tünel) "Tüm Klinik" = kimliğin kayıtları + SAHİPSİZ
    # (Y104 tanımı); başka kayıtlı hekimin AI kayıtları KALIR (eskiden jetonlu herhangi bir hekim herkesinkini siliyordu —
    # ölçüldü). Operatörsüz klinikte (Kural 2) kayıtlı kimse yok → kapsam fiilen tamamı. Kapı:
    # tests/test_ai_gecmisi_TUM_KLINIK_silme_kapsami_Y112.py
    from servers.auth import cihazin_kendisinden_mi, kayitli_operator_epostalari

    _kapsam = "kendi"
    _sahipsiz_dahil, _kayitli_set = False, None
    if tum_klinik:
        _kapsam = "tum_klinik"
        if _kayitli and not cihazin_kendisinden_mi(request):
            # None (kimlik DB okunamıyor) → kimin kayıtlı olduğu bilinmiyor: yalnız kendi + boş sahipli (fail-closed)
            _kayitli_set = kayitli_operator_epostalari()
            op, _sahipsiz_dahil, _kapsam = kimlik, True, "kendi_ve_sahipsiz"
    elif op and not _kayitli:
        # ⚠️ Y105 (S-B.2): kayıtlı operatörü OLMAYAN (tek kullanıcılı) cihazda "kendi geçmişimi sil" SAHİPSİZ (boş/NULL) eski
        # kayıtları da siler — orada sahipsiz kayıt o kullanıcınındır (ev sahibi "Tüm Klinik"e çıkamadığı için başka yolu yoktu).
        # Başka bir e-postayla yazılmış kayıt "kendi" DEĞİLDİR (`kayitli_epostalar=None` → yalnız boş/NULL). Kayıtlı operatörlü
        # klinikte A-10 aynen. Kapı: tests/test_ai_gecmisi_KENDI_silme_OPERATORSUZ_cihazda_sahipsizi_de_siler_Y105.py
        _sahipsiz_dahil, _kapsam = True, "kendi_ve_sahipsiz"
    # ⚠️ FAIL-CLOSED (2026-08-09): kimlik yok VE klinik-geneli silme AÇIKÇA istenmediyse reddet.
    # Aksi hâlde istemcideki bir kimlik kaybı (operatör seçilmemiş, oturum düşmüş, alan boş
    # gönderilmiş) sessizce "kliniğin tüm AI geçmişini sil"e dönüşürdü — geri dönüşü olmayan bir
    # işlem için kabul edilemez bir varsayılan.
    if op is None and not tum_klinik:
        raise HTTPException(
            status_code=400,
            detail=ceviri.t("gecmis.hata.silmeKapsami"),
        )
    # ⚠️ D1.58 (B-3.88): AKTİF SEANS sürüyorsa tüm-DB VACUUM ERTELENİR (yazım kilidi tedavi kaydını düşürebilir);
    # silme hemen yapılır, VACUUM seans bitince / bakımda (`_bekleyen_vacuumu_arka_planda`).
    with _session_lock:
        _seans_suruyor = bool(_active_session.get("is_active"))
    # SG.G2: istek profil bildiriyorsa toplu silme YALNIZ o profilin kayıtlarına DARALIR (ekranda görünen küme; kapsam genişlemez).
    from utils.profil import istek_profili as _istek_profili

    _silme_profili = _istek_profili(request)
    n = await asyncio.to_thread(db.clear_ai_analyses, op, _seans_suruyor, _sahipsiz_dahil, _kayitli_set, _silme_profili)
    # C2-4.1: DB okuması olay döngüsünde değil (tedavi DB'si kilitliyken döngüyü dondurmasın — Ö.4-Y8).
    _vacuum_bekliyor = bool(await asyncio.to_thread(getattr(db, "vacuum_bekliyor_mu", lambda: False)))

    if n < 0:
        _iz.kimlikli_yaz(
            request,
            "ai_log.delete_all",
            beyan=_beyan,
            scope=("KENDI_VE_SAHIPSIZ" if _sahipsiz_dahil else (op or "TUM_KLINIK")),
            item_count=0,
            outcome="hata",
        )
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.temizlenemedi"))
    # KVKK "sildim" kanıtı: kapsam + sayı loglanır (kayıt İÇERİĞİ loglanmaz).
    # SGI-1.6: kapsam profil süzgeciyle DARALDIYSA iz ve günlük bunu söyler (yoksa "TÜM KLİNİK silindi" yanlış kanıt olur).
    logging.getLogger(__name__).warning(
        "KVKK: AI analiz geçmişi TOPLU silindi (kapsam=%s%s, %d kayıt, VACUUM %s).",
        "KENDİ + SAHİPSİZ" if _sahipsiz_dahil else (op or "TÜM KLİNİK"),
        f" · yalnız profil {_silme_profili}" if _silme_profili else "",
        n,
        "ERTELENDİ (seans sonu/bakım)" if _vacuum_bekliyor else "uygulandı",
    )
    # ⚠️ Denetim izi SİLİNMEZ (ekleme-only mühür): "hepsini sil" bu satırı da silseydi, silmenin
    # olduğunu gösteren tek kanıt kaybolurdu.
    _iz.kimlikli_yaz(
        request,
        "ai_log.delete_all",
        beyan=_beyan,
        scope=("KENDI_VE_SAHIPSIZ" if _sahipsiz_dahil else (op or "TUM_KLINIK")),
        item_count=n,
        detail={
            "all_operators": tum_klinik,
            "kapsam": _kapsam,
            "vacuum": not _vacuum_bekliyor,
            **({"profil": _silme_profili} if _silme_profili else {}),
        },
    )
    return {"status": "success", "deleted": n, "vacuumErtelendi": _vacuum_bekliyor, "kapsam": _kapsam}


# ─────────────────── CİHAZ TAŞIMA: şifreli dışa/içe aktarma (2026-08-08) ───────────────────
# Kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu YOK). Tek gerçek dezavantajı cihaz
# değişimiydi; çözümü bulut değil, kliniğin kendi kontrolündeki şifreli dosya.


#: ⚠️ D2.E02 (İG-6.5): geri yükleme TEK kritik bölge — "hedef dolu mu" denetimi + içe aktarma bu kilidin içinde. Eskiden arada kilit
#: yoktu: ilk geri yükleme cihazda sürerken (arayüzün 8 sn zaman aşımı "Tekrar deneyin" diyordu — İG-6.21) gelen ikinci istek de
#: hedefi BOŞ görüp aynı paketi ekleme kipinde yazıyordu → tüm tıbbi kayıtlar İKİYE katlanıyordu (sahada 4000 seans ölçüldü).
#: İkinci istek BEKLEMEZ (SQLCipher'da dakikalık işi ikilerdi), hemen 409 alır; geri yükleme sürerken dışa aktarma da 409 (yarım
#: içe aktarılmış durum yedek diye verilmesin). Kilit, istek iptal edilse de iş BİTİNCE bırakılır (görev bitiş geri çağrısı).
#: Kapı: tests/test_ice_aktarma_TEK_kritik_bolge_ikinci_istek_409_D2E02.py
_VERI_TASIMA_KILIDI = threading.Lock()


def geri_yukleme_suruyor() -> str:
    return ceviri.t("yedek.hata.geriYuklemeSuruyor")


#: ⚠️ D2-4.2: aynı anda TEK dışa aktarma (bkz. `export_clinic_data`). Kapı: tests/test_disa_aktarma_TEK_SEFERDE_bir_D2_4_2.py
_DISA_AKTARMA_KILIDI = threading.Lock()


def yedek_alma_suruyor() -> str:
    return ceviri.t("yedek.hata.yedekAlmaSuruyor")


#: ⚠️ D2-4.1: geri yükleme ↔ süren seans (iki yön). Kapı: tests/test_geri_yukleme_SUREN_SEANSI_SILMEZ_D2_4_1.py
def geri_yukleme_surerken_seans() -> str:
    return ceviri.t("yedek.hata.geriYuklemeSurerkenSeans")


def seans_surerken_geri_yukleme() -> str:
    return ceviri.t("yedek.hata.seansSurerkenGeriYukleme")


class DataExportPayload(BaseModel):
    passphrase: str = ""
    #: D2.E01: True → dosyayı BU makinenin masaüstüne backend yazar ve doğrular (yalnız cihazın kendi ekranından).
    kaydet: bool = False


def _yedegi_masaustune_yaz(blob: bytes, ad: str) -> dict:
    """⚠️ D2.E01 (İG-6.20): şifreli yedek dosyasını cihazın masaüstüne yazar ve GERİ OKUYARAK doğrular.

    Masaüstü arayüzü Tauri WebView2'de koşar; `<a download>` orada sessizce ölebiliyor (09-11 saha arızası) ve ekran dosya oluşmasa da
    "Yedek oluşturuldu" diyordu (ölçüldü). Backend aynı makinede → dosyayı o yazar: geçici ada yazım + `fsync` + `os.replace`, sonra
    diskteki baytların SHA-256'sı pakete eşit mi denetlenir. Eşit değilse dosya silinir ve hata yükselir — yarım/bozuk `.pemfbak` "yedek"
    diye kalmaz. Hedef dizin TEK kaynaktan (`seans_alan_kaydi.masaustu_dizini` — test süiti onu yamalar, gerçek masaüstüne sızmaz)."""
    import hashlib as _hashlib
    from pathlib import Path

    from servers.seans_alan_kaydi import masaustu_dizini

    dizin, gerekce = masaustu_dizini()
    # ⚠️ D2-2.7 (2-D incelemesi) [KARAR — önerilen]: masaüstü bulunamayınca (`masaustu_dizini` → çalışma dizini: servis hesabı / yönlendirilmiş
    # masaüstü) tüm-klinik yedeği backend'in ÇALIŞMA DİZİNİNE (launcher: `runtime\PEMF_Backend` — güncellemede silinir; NSSM: kurulum dizini)
    # yazılıyor ve "doğrulandı" deniyordu. Ortak Masaüstü (`%PUBLIC%\Desktop`) kullanılır; o da yoksa YAZILMAZ (çağıran 500 "OLUŞTURULMADI").
    # Kapı: tests/test_yedek_kaydet_CALISMA_DIZININE_dusmez_D2_2_7.py
    if Path(dizin).resolve() == Path.cwd().resolve():
        ortak = Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "Desktop"
        if not ortak.is_dir():
            raise RuntimeError(f"masaüstü bulunamadı ({gerekce}) — yedek çalışma dizinine YAZILMAZ: {dizin}")
        dizin, gerekce = ortak, f"ortak masaüstü — {gerekce}"
    guvenli = "".join(c for c in ad if c.isalnum() or c in ("_", "-", ".")) or "pemf-vet-yedek.pemfbak"
    hedef = Path(dizin) / guvenli
    if hedef.exists():  # aynı dakikada ikinci yedek öncekinin ÜZERİNE yazmasın
        kok, uzanti = os.path.splitext(guvenli)
        hedef = Path(dizin) / f"{kok}_{int(time.time() * 1000)}{uzanti}"
    gecici = hedef.with_name(hedef.name + ".yazim.tmp")
    try:
        with open(gecici, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, hedef)
        okunan = hedef.read_bytes()
        if len(okunan) != len(blob) or _hashlib.sha256(okunan).digest() != _hashlib.sha256(blob).digest():
            try:
                hedef.unlink()
            except OSError:
                pass
            raise RuntimeError(f"yedek dosyası diske yazıldı ama DOĞRULANAMADI ({len(okunan)} / {len(blob)} bayt)")
    finally:
        try:
            if gecici.exists():
                gecici.unlink()
        except OSError:
            pass
    logging.getLogger(__name__).warning(
        "VERİ TAŞIMA: şifreli yedek diske yazıldı ve doğrulandı: %s (%s)", hedef, gerekce
    )
    return {"yol": str(hedef), "ad": hedef.name, "bayt": len(okunan)}


class DataImportPayload(BaseModel):
    passphrase: str = ""
    blob_b64: str = ""
    confirm: str = ""  # hedef DOLU ise "REPLACE_ALL" ZORUNLU


@app.post("/api/data/export")
async def export_clinic_data(payload: DataExportPayload, request: Request):
    """Hasta + seans + AI analiz kayıtlarını TEK şifreli dosyaya çıkarır (base64 döner).

    ⚠️ D2-4.2 (2-D incelemesi · Ö.4-Y8): aynı anda TEK dışa aktarma — ikincisi beklemez, hemen 409 (D2.E02 deseni). Dışa aktarma
    CPU yoğun (tüm tablolar + JSON + gzip + şifreleme + doğrulama için çözme); eşzamanlılık sınırsızken 25 istek (A-01: LAN'dan da)
    GIL'i doyuruyor, ACİL DURDUR'un KENDİ iş parçacığı aç kalıyordu: 2000 seanslık şifreli klinikte ACİL DURDUR yanıtı 12,0 sn, ilk
    donanım STOP paketi 2,9 sn (tek dışa aktarmada 0,47 / 0,45 sn — ölçüldü). Kilit iş BİTİNCE bırakılır (istemci koparsa da).
    Kapı: tests/test_disa_aktarma_TEK_SEFERDE_bir_D2_4_2.py"""
    _enforce_privileged(request)
    if _VERI_TASIMA_KILIDI.locked():  # D2.E02: yarım içe aktarılmış durum yedek diye verilmez
        raise HTTPException(status_code=409, detail=geri_yukleme_suruyor())
    if not _DISA_AKTARMA_KILIDI.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=yedek_alma_suruyor())
    try:
        gorev = asyncio.ensure_future(_disa_aktar(payload, request))
    except BaseException:
        _DISA_AKTARMA_KILIDI.release()
        raise

    def _bitti(g):
        _DISA_AKTARMA_KILIDI.release()
        if not g.cancelled():
            g.exception()  # istek iptal edildiyse sonuç yine "alınmış" sayılsın (gürültü yok)

    gorev.add_done_callback(_bitti)
    return await asyncio.shield(gorev)


async def _disa_aktar(payload: DataExportPayload, request: Request):
    """`/api/data/export` gövdesi — YALNIZ `_DISA_AKTARMA_KILIDI` tutulurken çağrılır (D2-4.2)."""
    _enforce_privileged(request)
    if _VERI_TASIMA_KILIDI.locked():  # D2.E02: yarım içe aktarılmış durum yedek diye verilmez
        raise HTTPException(status_code=409, detail=geri_yukleme_suruyor())
    # ⚠️ D2-2.5 (2-D incelemesi · S-D.1/Y103 ile tutarlılık) [KARAR — önerilen]: kayıtlı operatörlü klinikte kliniğin TAMAMINI çağıranın
    # seçtiği parolayla veren paket KİMLİK ister (jetonsuz 428). A-01 cihaz token'ı tek başına yetmez — LAN'daki herkese
    # `/api/auth/token`dan verilir. Operatörsüz klinik (Kural 2) ve kimlikli hekim (rol modeli yok, A-28) DEĞİŞMEZ.
    # Kapı: tests/test_data_export_KAYITLI_klinikte_KIMLIK_ister_D2_2_5.py
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    if kayitli_operator_var() and not cozumlenmis_operator(request):
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("yedek.kimlik.disaAktar")),
        )
    if payload.kaydet:
        from servers.auth import cihazin_kendisinden_mi

        if not cihazin_kendisinden_mi(request):
            # D2.E01: dosya CİHAZIN masaüstüne yazılır — telefon/LAN istemcisi onu göremez; o yol dosyayı yanıtta alır.
            raise HTTPException(
                status_code=400,
                detail=ceviri.t("yedek.hata.cihazaKaydetEkran"),
            )
    import base64 as _base64

    from utils.data_export import BUNDLE_VERSION, ExportError, encrypt_bundle

    try:
        thdb = _get_treatment_db()
        pdb = get_patient_database()
        if thdb is None or pdb is None:
            raise HTTPException(status_code=500, detail=ceviri.t("yedek.hata.dbHazirDegil"))
        rows = await asyncio.to_thread(thdb.export_rows)
        # ⚠️ İKİ AYRI HASTA DEPOSU VAR ve ikisi de taşınmalı:
        #   rows["patients"]  → tedavi DB'sindeki hasta satırları; `treatment_sessions.patient_id`
        #                       BUNLARA bakar, dolayısıyla ilişkiyi kurmak için ŞART.
        #   pdb.get_all_patients → ayrı hasta veritabanı (arayüzün hasta listesi).
        # Eskiden yalnız ikincisi taşınıyor ve `rows`daki `patients` anahtarını EZİYORDU.
        # ⚠️ D2.66 (B-3.110): hasta okuması KATI — okunamayan hasta DB'si "hasta yok" sayılırsa yedek hasta listesiz "başarılı"
        # çıkıyordu (yeni cihaza yüklenince 0 hasta — veri kaybı zinciri). Kapı: tests/test_hasta_DB_okunamazken_SESSIZ_DEGIL_D266.py
        try:
            _hastalar_disa = await asyncio.to_thread(pdb.disa_aktarim_hastalari)  # D2.53: katı + çözülemeyen alan özgün
        except Exception:
            logging.getLogger(__name__).exception("VERİ TAŞIMA: hasta kayıtları okunamadı — yedek oluşturulmadı")
            raise HTTPException(
                status_code=503,
                detail=ceviri.t("yedek.hata.hastaOkunamadi"),
            )
        paket = {
            "bundle_version": BUNDLE_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            **rows,
            "patient_db": _hastalar_disa,
        }
        blob = await asyncio.to_thread(encrypt_bundle, paket, payload.passphrase)
        # ⚠️ DENETİM 2026-08-09 (Tier 1) — ÜRETİLEN DOSYA GERÇEKTEN AÇILIYOR MU?
        # Yedeğin bozuk olduğu, ancak KULLANILMASI gereken gün (eski makine ölmüş, geri dönüş yok)
        # anlaşılırdı. Round-trip doğrulama, aynı parolayla çözüp kayıt sayılarını karşılaştırır;
        # maliyeti tek bir PBKDF2 + gzip açma, karşılığı "bu dosya açılabilir" güvencesi.
        from utils.data_export import decrypt_bundle as _coz

        _geri = await asyncio.to_thread(_coz, blob, payload.passphrase)
        for _t in ("treatment_sessions", "session_coil_runs", "ai_analyses"):
            if len(_geri.get(_t) or []) != len(paket.get(_t) or []):
                logging.getLogger(__name__).error(
                    "VERİ TAŞIMA: round-trip doğrulaması BAŞARISIZ (%s: %d != %d)",
                    _t,
                    len(_geri.get(_t) or []),
                    len(paket.get(_t) or []),
                )
                raise HTTPException(
                    status_code=500,
                    detail=ceviri.t("yedek.hata.dogrulanamadi"),
                )
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logging.exception("data export failed")
        raise HTTPException(status_code=500, detail=ceviri.t("yedek.hata.disaAktarBasarisiz"))
    logging.getLogger(__name__).warning(
        "VERİ TAŞIMA: dışa aktarıldı (%d hasta, %d seans, %d bobin-koşusu, %d sensör, %d analiz).",
        len(paket["patient_db"]),
        len(paket["treatment_sessions"]),
        len(paket["session_coil_runs"]),
        len(paket["sensor_samples"]),
        len(paket["ai_analyses"]),
    )
    # ⚠️ Dışa aktarma, at-rest şifrelemesinin dışına ÇIKAN tek meşru yoldur: klinik verisinin
    # tamamı, çağıranın SEÇTİĞİ bir parolayla tek dosyaya iner. Kim, ne zaman, nereden ve kaç
    # kayıt çıkardı — bu kayıt olmadan bir veri sızıntısı geriye dönük hiç görünmez.
    # ⚠️ D2.43 (B-2.10): "kim" sorusunun cevabı da izde — `kimlikli_yaz` (eskiden `yaz`: jetonlu istekte de operatör '').
    from servers import audit_log as _iz

    _iz.kimlikli_yaz(
        request,
        "data.export",
        scope="klinik",
        item_count=len(paket["treatment_sessions"]),
        detail={
            k: len(paket.get(k) or [])
            for k in (
                "patient_db",
                "treatment_sessions",
                "session_coil_runs",
                "sensor_samples",
                "session_events",
                "ai_analyses",
            )
        },
    )
    _dosya_adi = f"pemf-vet-yedek-{datetime.now():%Y%m%d-%H%M}.pemfbak"
    _kayit = {}
    if payload.kaydet:
        try:
            _kayit = await asyncio.to_thread(_yedegi_masaustune_yaz, blob, _dosya_adi)
        except Exception:
            logging.getLogger(__name__).exception("VERİ TAŞIMA: yedek dosyası diske yazılamadı/doğrulanamadı")
            raise HTTPException(
                status_code=500,
                detail=ceviri.t("yedek.hata.cihazaYazilamadi"),
            )
    return {
        "status": "success",
        "filename": _dosya_adi,
        # D2.E01: cihaza kaydedildiyse içerik yanıtta TAŞINMAZ (yol + boyut + doğrulandı); değilse istemci indirir.
        **(
            {"yol": _kayit["yol"], "ad": _kayit["ad"], "bayt": _kayit["bayt"], "dogrulandi": True}
            if _kayit
            else {"data_b64": _base64.b64encode(blob).decode("ascii")}
        ),
        # Sayımlar kullanıcıya gösterilir: "ne taşındığını" görebilmeli. Doz kaydı (bobin
        # koşuları) ayrı kalem — eskiden hiç taşınmadığı için hiç görünmüyordu da.
        #
        # ⚠️ DENETİM 2026-08-28 #05: `patients` anahtarı EKLEMELİ ve KALMALI. Arayüz (masaüstü +
        # yayınlanmış APK'lar dahil) `counts.patients ?? 0` okur; bu anahtar yanıtta HİÇ yoktu →
        # 300 hastalık yedek alan operatör "Yedek oluşturuldu: 0 hasta" görüyordu. Veri doğruydu,
        # SAYI yalan söylüyordu — operatör yedeğe güvenmiyor ya da işlemi tekrarlıyordu.
        # `patient_db` geriye uyum için duruyor; ikisi AYNI değeri taşır (kapı: test_yedek_sayaclari).
        "counts": {
            **{
                k: len(paket.get(k) or [])
                for k in (
                    "patient_db",
                    "treatment_sessions",
                    "session_coil_runs",
                    "sensor_samples",
                    "session_events",
                    "ai_analyses",
                )
            },
            "patients": len(paket.get("patient_db") or []),
        },
    }


@app.post("/api/data/import")
async def import_clinic_data(payload: DataImportPayload, request: Request):
    """Şifreli yedeği geri yükler.

    ⚠️ HEDEF BOŞ DEĞİLSE `{"confirm":"REPLACE_ALL"}` ZORUNLU ve mevcut TIBBİ KAYITLARIN TAMAMI
    SİLİNİR. Sessiz birleştirme YAPMIYORUZ: seans ve analiz append-only günlüklerdir, aynı dosyayı
    iki kez almak kayıtları ÇOĞALTIR ve klinik geçmişini sessizce bozar.

    ⚠️ 2026-08-09: silme kapsamı GENİŞLEDİ. Paket artık bağlı tabloların tamamını taşıdığı için
    (bobin koşuları = uygulanan doz, sensör telemetrisi, seans olayları/parametreleri ve tedavi
    DB'sinin hasta satırları) `replace` bunların HEPSİNİ siler. Yalnız seans+analiz silinip
    çocuk satırlar bırakılsaydı, eski telemetri yeni seanslara bağlanır ve kayıtlar karışırdı.

    ⚠️ D2.E02 (İG-6.5): tek kritik bölge — eşzamanlı ikinci istek 409 (`_VERI_TASIMA_KILIDI` notu).
    """
    _enforce_privileged(request)
    if not _VERI_TASIMA_KILIDI.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=geri_yukleme_suruyor())
    try:
        gorev = asyncio.ensure_future(_ice_aktar(payload, request))
    except BaseException:
        _VERI_TASIMA_KILIDI.release()
        raise

    def _bitti(g):
        _VERI_TASIMA_KILIDI.release()
        if not g.cancelled():
            g.exception()  # istek iptal edildiyse sonuç yine "alınmış" sayılsın (gürültü yok)

    gorev.add_done_callback(_bitti)
    return await asyncio.shield(gorev)


def cihaz_disi_geri_yukleme() -> str:
    return ceviri.t("yedek.hata.cihazDisiGeriYukleme")


def _hedef_dolu_mu_hizli(thdb, pdb) -> bool:
    """D2-1.9: hedef dolu mu — `export_rows` tam okuması YAPMADAN (EXISTS). Hasta okuması KATI (D2.66): okunamazsa istisna yükselir."""
    with thdb._get_connection() as c:
        tablolar = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for t in ("treatment_sessions", "ai_analyses"):
            if t in tablolar and c.execute(f"SELECT EXISTS(SELECT 1 FROM {t})").fetchone()[0]:
                return True
    return bool(pdb.get_all_patients(kati=True))


async def _ice_aktar(payload: DataImportPayload, request: Request):
    """`/api/data/import` gövdesi — YALNIZ `_VERI_TASIMA_KILIDI` tutulurken çağrılır (D2.E02)."""
    import base64 as _base64

    from utils.data_export import ExportError, decrypt_bundle

    from servers.auth import cozumlenmis_operator as _kimlik_coz

    # ⚠️ O-A2.3 (2-B incelemesi): kimlik İŞLEMDEN ÖNCE bir kez çözülür (istek kapsamında saklanır — C2-3.3). Boş cihaza ilk içe
    # aktarma eskiden kimliği hiç çözmeden işleme giriyor, başarı izi sonda İLK KEZ çözüyordu → işlem sürerken "Kilitle" izi SAHİPSİZ
    # bırakıyordu (ölçüldü). Döngü dışında (kimlik DB okuması). Kapı: tests/test_ice_aktarma_IZI_islem_SURERKEN_kilitte_YETKILENDIREN_OA23.py
    await asyncio.to_thread(_kimlik_coz, request)
    thdb = _get_treatment_db()
    pdb = get_patient_database()
    if thdb is None or pdb is None:
        raise HTTPException(status_code=500, detail=ceviri.t("yedek.hata.dbHazirDegil"))
    try:
        blob = _base64.b64decode(payload.blob_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail=ceviri.t("yedek.hata.kodlama"))
    try:
        paket = await asyncio.to_thread(decrypt_bundle, blob, payload.passphrase)
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # ⚠️ D2-1.9 (2-D incelemesi · Y111): cihaz DIŞI istekte hedef doluluğu ÖNCE ucuz sorguyla; doluysa hedefin tüm satırları okunmadan
    # 403. Eskiden reddedilecek LAN isteği kilidi tam okuma (`export_rows`) boyunca tutuyor, cihazın KENDİ yedeği o sırada "Geri yükleme
    # bu cihazda sürüyor" 409'u alıyordu (ölçüldü). Okuma düşerse aşağıdaki tam yol karar verir (hata metinleri orada).
    # Kapı: tests/test_cihaz_disi_REDDEDILECEK_istek_kilidi_TUTMAZ_D2_1_9.py
    from servers.auth import cihazin_kendisinden_mi as _cihazdan_mi

    if not _cihazdan_mi(request):
        try:
            _dolu_hizli = await asyncio.to_thread(_hedef_dolu_mu_hizli, thdb, pdb)
        except Exception:
            _dolu_hizli = False
        if _dolu_hizli:
            from servers import audit_log as _iz0

            _iz0.kimlikli_yaz(
                request,
                "data.import",
                scope="replace_all",
                item_count=0,
                outcome="reddedildi",
                detail={"neden": "cihaz_disi"},
            )
            raise HTTPException(status_code=403, detail=cihaz_disi_geri_yukleme())

    mevcut = await asyncio.to_thread(thdb.export_rows)
    # ⚠️ D2.66: hasta okuması KATI — okunamayan hasta DB'si DOLU cihazı BOŞ gösterip onayı (REPLACE_ALL) ve Y111'i atlatmasın.
    try:
        _mevcut_hastalar = await asyncio.to_thread(pdb.get_all_patients, kati=True)
    except Exception:
        logging.getLogger(__name__).exception("VERİ TAŞIMA: hedefin hasta kayıtları okunamadı — geri yükleme yapılmadı")
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("yedek.hata.geriYuklemeHastaOkunamadi"),
        )
    dolu = bool(mevcut["treatment_sessions"] or mevcut["ai_analyses"] or _mevcut_hastalar)
    from servers import audit_log as _iz

    if dolu:
        # ⚠️ Y111 (sahip · S-B2.3): DOLU cihazda geri yükleme (REPLACE_ALL) tüm tedavi kayıtlarını siler → yalnız CİHAZIN KENDİSİNDEN
        # (loopback; tünel / ters-proxy sayılmaz — A-03 deseni) ve kayıtlı operatörlü klinikte KİMLİKLİ hekimle. Eskiden LAN'daki
        # herhangi bir eşleşmiş istemci (cihaz token'ı) kliniğin tüm tedavi geçmişini değiştirebiliyordu (2-B incelemesi B2-1.7).
        # Boş cihaza ilk içe aktarma bugünkü gibi. Kapı: tests/test_geri_yukleme_BUTUNLUKLU_D252_Y12_Y111.py
        from servers.auth import cihazin_kendisinden_mi, cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

        if not cihazin_kendisinden_mi(request):
            _iz.kimlikli_yaz(
                request,
                "data.import",
                scope="replace_all",
                item_count=0,
                outcome="reddedildi",
                detail={"neden": "cihaz_disi"},
            )
            raise HTTPException(status_code=403, detail=cihaz_disi_geri_yukleme())
        if kayitli_operator_var() and not cozumlenmis_operator(request):
            _iz.kimlikli_yaz(
                request,
                "data.import",
                scope="replace_all",
                item_count=0,
                outcome="reddedildi",
                detail={"neden": "kimliksiz"},
            )
            raise HTTPException(
                status_code=428,
                detail=kimliksiz_detayi(ceviri.t("yedek.kimlik.geriYukleme")),
            )
    if dolu and payload.confirm != "REPLACE_ALL":
        # ⚠️ Y12 (sahip · B-3.21): metin GERÇEĞİ söyler — hasta kartları (patients.db) SİLİNMEZ; yedekte olmayan hastanın kartı kalır
        # ama bu cihazdaki tedavi geçmişi (tedavi DB'sinin tamamı) yedektekiyle değişir. Eskiden "hasta kayıtları SİLER" diyordu.
        raise HTTPException(
            status_code=409,
            detail=ceviri.t("yedek.hata.geriYuklemeOnay"),
        )

    # ⚠️ D2-4.1 (2-D incelemesi · A-07 · B2-1.5 ilkesi): SÜREN seans (elle ya da AI Pro) varken geri yükleme YAPILMAZ. `import_rows` tüm
    # tedavi tablolarını siliyor: süren seansın satırı ve bobin koşusu gidiyor, tedavi donanımda sürüyor; durdurma / ACİL DURDUR sonrası
    # uygulanan dozun ve ACİL DURDUR olayının KAYDI KALMIYORDU (ölçüldü). Silme uçlarıyla aynı ilke: 409, hiçbir şey değişmez.
    # ⚠️ Ö.4-Y8: `_session_lock` ALINMAZ (`dict.get` atomik). Kilit tutulurken yeni seans başlatılamaz (`GERI_YUKLEME_SURERKEN_SEANS`),
    # denetim silmeden hemen önce. Kapı: tests/test_geri_yukleme_SUREN_SEANSI_SILMEZ_D2_4_1.py
    if _active_session.get("is_active"):
        _iz.kimlikli_yaz(
            request,
            "data.import",
            scope=("replace_all" if dolu else "bos_cihaz"),
            item_count=0,
            outcome="reddedildi",
            detail={"neden": "seans_suruyor"},
        )
        raise HTTPException(status_code=409, detail=seans_surerken_geri_yukleme())

    # ⚠️ D2-3.3 (2-D incelemesi): sayfalı okuyucular (D2.16 "Tümünü" CSV'si) geri yüklemenin ARAYA girdiğini görsün — nesil sayacı
    # (tek = sürüyor, çift = bitti; düşse de çifte döner). Eskiden sayfalar arasında commit edilen REPLACE_ALL CSV'yi eski geçmişin
    # ilk sayfasıyla (5000 / 10 001) 200 döndürüyordu. Kapı: tests/test_csv_TUMU_sayfalar_arasi_GERI_YUKLEME_kesik_dosya_VERMEZ_D233.py
    thdb._geri_yukleme_nesli = getattr(thdb, "_geri_yukleme_nesli", 0) + 1
    try:
        try:
            n = await asyncio.to_thread(thdb.import_rows, paket, bool(dolu))
        finally:
            thdb._geri_yukleme_nesli += 1
    except Exception as _hata:
        # ⚠️ D2.52 (B-3.28) + P2u: `import_rows` artık bütünlüklü — düşerse HİÇBİR şey commit edilmez ve hasta kartlarına da
        # geçilmez. Eskiden hata yutulup "success" (0 seans ya da eski + yeni yan yana) dönülüyordu.
        logging.getLogger(__name__).exception(
            "VERİ TAŞIMA: içe aktarma DÜŞTÜ — tedavi DB'si geri alındı, kayıtlar değişmedi"
        )
        _iz.kimlikli_yaz(
            request,
            "data.import",
            scope=("replace_all" if dolu else "bos_cihaz"),
            item_count=0,
            outcome="hata",
            detail={"neden": type(_hata).__name__},
        )
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("yedek.hata.geriYuklemeYazilamadi"),
        )
    eklenen_hasta = 0
    # v2'de ayrı hasta veritabanı `patient_db` anahtarındadır; v1 yedeklerinde `patients` idi
    # (o sürümde tedavi DB'sinin hasta tablosu hiç taşınmıyordu, çakışma yok).
    _hastalar = paket.get("patient_db")
    if _hastalar is None and int(paket.get("bundle_version") or 1) < 2:
        _hastalar = paket.get("patients")
    # ⚠️ ÜÇ SONUÇ AYRI SAYILIR — "zaten vardı" ile "İÇE AKTARILAMADI" AYNI KOVAYA KONMAZ.
    # İlk yazımda her istisna tek bir "zaten vardı/atlandı" sayacını artırıyordu; o hâlde
    # operatör "0 hasta [+50 zaten vardı]" görüp "sorun yok" diye okuyabilirdi — oysa 50 satır da
    # GERÇEKTEN başarısız olmuş olabilirdi. Tıbbi kayıt taşımada bu kabul edilemez bir belirsizlik.
    # Ayrım hata METNİNDEN değil, ÖNCE varlık sorgusundan türetilir (metin kırılgan olurdu).
    _zaten_var, _basarisiz = 0, 0
    # ⚠️ Y12: REPLACE_ALL yedekte olmayan hastanın kartını SİLMEZ; RAPORLAR (kimlikler — PII değil) ve yanıt gerçeği söyler.
    _paket_kimlikleri = {str(h.get("id")) for h in (_hastalar or []) if isinstance(h, dict) and h.get("id")}
    _yedekte_olmayan = (
        [str(h.get("id")) for h in (_mevcut_hastalar or []) if str(h.get("id")) not in _paket_kimlikleri]
        if dolu
        else []
    )
    for h in _hastalar or []:
        _hid = h.get("id") if isinstance(h, dict) else None
        try:
            # ⚠️ DENETİM 2026-08-17 — UUID ZİNCİRİ: paketteki `id` AYNEN korunmalı. Eskiden
            # `add_patient` gelen id'yi yok sayıp yeni uuid4 üretiyordu ve `patients.db` ↔ tedavi-DB
            # (`patients.patient_uuid`) bağı HER içe aktarımda kopuyordu → 5 yıl inaktif hastada
            # tedavi geçmişindeki ad kopyası `[REDACTED]` olmuyordu (sessiz KVKK boşluğu).
            # Bkz. `patient_database.add_patient` docstring'i + tests/test_ice_aktarma_hasta_uuid_zinciri.py
            if _hid and await asyncio.to_thread(pdb.get_patient, _hid):
                # Aynı paketin ikinci kez alınması: `id` korunduğu için satır ZATEN burada.
                # Sessiz çoğaltma YOK — bu İSTENEN sonuç, hata değil.
                _zaten_var += 1
                continue
            if await asyncio.to_thread(pdb.add_patient, h, _hid):
                eklenen_hasta += 1
        except Exception as _e:
            _basarisiz += 1
            logging.getLogger(__name__).warning("Hasta İÇE AKTARILAMADI (id=%s): %s", _hid, _e)
    logging.getLogger(__name__).warning(
        "VERİ TAŞIMA: içe aktarıldı (%d hasta eklendi, %d zaten vardı, %d BAŞARISIZ, %d seans, "
        "%d bobin-koşusu, %d analiz; replace=%s).",
        eklenen_hasta,
        _zaten_var,
        _basarisiz,
        n["treatment_sessions"],
        n["session_coil_runs"],
        n["ai_analyses"],
        dolu,
    )
    # ⚠️ `replace=True` ise bu işlem cihazdaki TÜM tıbbi kayıtları SİLDİ. Denetim izi (ekleme-only)
    # silinmediği için "hangi yedek, ne zaman, kaç kaydın üzerine yazıldı" sorusu cevaplanabilir
    # kalır — aksi hâlde yanlış yedeği geri yükleyen bir işlem geriye dönük görünmez olurdu.
    # ⚠️ D2.43 (B-2.10): operatörlü (`kimlikli_yaz`; eskiden `yaz` — operatör hep '').
    # ⚠️ D2-1.6 (2-D incelemesi): hasta ayağı tedavi commit'inden SONRA düşerse iz "ok" diyordu ve başarısız sayıyı taşımıyordu —
    # yarım geri yükleme kalıcı izde başarılı görünüyordu (ölçüldü). Kapı: tests/test_geri_yukleme_hasta_ayagi_DUSERSE_denetim_izi_GERCEGI_soyler_D2_1_6.py
    _iz.kimlikli_yaz(
        request,
        "data.import",
        scope=("replace_all" if dolu else "bos_cihaz"),
        item_count=n.get("treatment_sessions", 0),
        outcome=("kismi" if _basarisiz else "ok"),
        detail={
            "replace": bool(dolu),
            "hasta": eklenen_hasta,
            "hasta_zaten_vardi": _zaten_var,
            "hasta_basarisiz": _basarisiz,
            "yedekte_olmayan_hasta": len(_yedekte_olmayan),
            "bundle_version": paket.get("bundle_version"),
            **n,
        },
    )
    # ⚠️ ÜÇ SONUÇ YANITTA DA RAPORLANIR (yalnız logda değil). Operatör geri yüklemenin gerçekten
    # ne yaptığını görmeli: "0 hasta" tek başına "hepsi zaten vardı" mı yoksa "hepsi BAŞARISIZ" mı
    # olduğunu söylemez — tıbbi kayıt taşımada bu ayrım kritiktir. EKLEMELİ alanlar: mevcut
    # istemciler (`SettingsScreen` yalnız `patients`/`treatment_sessions`/`ai_analyses` okur)
    # etkilenmez.
    #
    # ⚠️ DENETİM 2026-08-28 #05: `n["patients"]` GERÇEK hasta sayısı DEĞİL — tedavi DB'sindeki
    # FK hasta KOPYASININ satır sayısı. Arayüz `counts.patients` okuduğu için geri yüklemede
    # yanlış sayıyı gösteriyordu. FK kopyası `patients_fk_kopya` adına taşındı; `patients` artık
    # gerçekten eklenen hasta sayısını taşır (export ile aynı anlam). Kapı: test_yedek_sayaclari.
    _n_disari = dict(n)
    _fk_kopya = _n_disari.pop("patients", 0)
    _uyari = ceviri.t("yedek.uyari.yedekteOlmayan", count=len(_yedekte_olmayan)) if _yedekte_olmayan else ""
    if _basarisiz:
        _uyari = (ceviri.t("yedek.uyari.kartAktarilamadi", count=_basarisiz) + " " + _uyari).strip()
    return {
        "status": "success",
        "yedekte_olmayan_hasta": len(_yedekte_olmayan),
        "yedekte_olmayan_hasta_kimlikleri": _yedekte_olmayan,
        "uyari": _uyari,
        "counts": {
            "patient_db": eklenen_hasta,
            "patient_db_zaten_vardi": _zaten_var,
            "patient_db_basarisiz": _basarisiz,
            **_n_disari,
            "patients": eklenen_hasta,
            "patients_fk_kopya": _fk_kopya,
        },
    }


#: D1.55 (B-1.23): E-stop yanıtındaki `stmStopped` için STOP baytlarının porta YAZILMASINI bekleme
#: üst sınırı (sn). Bekleme tüm gönderimlerden (STM kuyruğu, ESP yayınları) ve kayıttan SONRA yapılır →
#: durdurmayı geciktirmez; sağlıklı göndericide yazım ms içinde olur, bekleme hemen döner.
#: ⚠️ 1-C inceleme i3-F-5 / i5-F-4: 1,0 sn idi ve yazılamayan STOP'ta (kablo çıkık / ölü gönderici) yanıtı o kadar
#: geciktiriyordu; istemcinin yedek adımları sıralı → 3. adım ~2 sn sonra. Artık 0,5 sn ve STOP'un şu an yazılamayacağı
#: belliyse hiç beklenmez (`hw_*_bekle` erken çıkar). Teyitsizlik yalnız istemcinin yedek adımlarını çalıştırır (A-63).
_ESTOP_STM_YAZIM_BEKLEME_S = 0.5

#: TD3: STOP porta yazıldıktan SONRA kartın yanıtını (tüm-sıfır `STM_OK` / `STM_NACK`) bekleme üst sınırı (sn). Kabul gelir gelmez
#: döner (115200 baud'da ~20 ms); NACK'li ya da yanıtsız kartta bu kadar sürer. STOP'lar ÇOKTAN gitti — yalnız RAPOR (Ö.4-Y8).
_ESTOP_STM_YANIT_BEKLEME_S = 0.25


def _stm_yazim_isareti_al():
    """STOP'tan ÖNCE çekirdeğin yazım sayacı (yazım izi bildirmeyen çekirdekte None)."""
    _isaret = getattr(getattr(state.hardware, "core", None), "hw_yazim_isareti", None)
    if not callable(_isaret):
        return None
    try:
        return _isaret()
    except Exception:
        logging.getLogger(__name__).warning("E-stop: STM yazim isareti okunamadi", exc_info=True)
        return None


def _stm_son_stop_sirasi_al():
    """`stop_all_coils`'tan HEMEN sonra: bu E-stop'un kuyruğa koyduğu STOP'un sırası (i5-F-2; bildirmeyen HC'de None)."""
    _sira = getattr(state.hardware, "son_stop_sirasi", None)
    if not callable(_sira):
        return None
    try:
        return int(_sira()) or None
    except Exception:
        logging.getLogger(__name__).warning("E-stop: STM STOP sirasi okunamadi", exc_info=True)
        return None


def _stm_stop_porta_yazildi_mi(isaret, sira_once) -> bool:
    """E-stop DIŞI durdurmalar için (1-C §9 #2 · A-63): STOP'tan ÖNCE alınan yazım işareti ve STOP sırasıyla, bu çağrının
    STOP'u porta yazıldı mı? Yeni bir tüm-sıfır paketi sıralandıysa ona bağlanır (önceki bir STOP'un yazımı sayılmaz);
    sıralanmadıysa (başka bobin hâlâ sürülüyor) işaretten sonraki herhangi bir yazım. Yalnız RAPOR — STOP'u kapılamaz."""
    sira_sonra = _stm_son_stop_sirasi_al()
    sira = sira_sonra if sira_sonra and sira_sonra != sira_once else None
    return _stm_stop_yazildi_mi(True, isaret, sira)


def _stm_stop_yazildi_mi(kuyruga_verildi: bool, isaret, stop_sirasi=None) -> bool:
    """`stmStopped`: STOP porta GERÇEKTEN yazıldı mı (D1.55 · B-1.23).

    ⚠️ Kuyruğa vermek YETMEZ: gönderici ölüyse ya da seri bağlantı yoksa paket porta hiç gitmez; eskiden
    bu durumda da `stmStopped=True` yayınlanıyordu (ölçüldü: porta 0 bayt). Çekirdek yazım izi bildirmiyorsa
    (test vekilleri) eski anlam ("kuyruğa verildi") korunur. Bu yalnız RAPORLANAN teyittir — STOP'u
    kapılamaz, gönderimi azaltmaz (Ö.4-Y8); teyitsizlik istemcinin yedek adımlarını çalıştırır.
    ⚠️ 1-C inceleme i5-F-2: teyit bu E-stop'un KENDİ STOP'una (kuyruk sırası) bağlıdır — E-stop'tan ÖNCE kuyruğa girmiş
    başka bir STOP'un yazılması sayılmaz (önceki STOP + RUN sırasında E-stop'un STOP'u yazılamazsa yalan "True" oluyordu)."""
    if not kuyruga_verildi or isaret is None:
        return bool(kuyruga_verildi)
    _sirali = getattr(getattr(state.hardware, "core", None), "hw_stop_sirasi_yazildi_bekle", None)
    if stop_sirasi and callable(_sirali):
        try:
            return bool(_sirali(stop_sirasi, _ESTOP_STM_YAZIM_BEKLEME_S))
        except Exception:
            logging.getLogger(__name__).warning("E-stop: STM STOP yazimi dogrulanamadi", exc_info=True)
            return False
    _bekle = getattr(getattr(state.hardware, "core", None), "hw_stop_yazildi_bekle", None)
    if not callable(_bekle):
        return True
    try:
        return bool(_bekle(isaret, _ESTOP_STM_YAZIM_BEKLEME_S))
    except Exception:
        logging.getLogger(__name__).warning("E-stop: STM STOP yazimi dogrulanamadi", exc_info=True)
        return False


def _stm_stop_kart_yaniti(stop_sirasi):
    """TD3: bu E-stop'un STOP'una kartın yanıtı — "kabul" | "red" | "yanitsiz" (T2D-1) | None (izi bildirmeyen çekirdek). Yalnız RAPOR."""
    _bekle = getattr(getattr(state.hardware, "core", None), "hw_stop_yaniti_bekle", None)
    if not stop_sirasi or not callable(_bekle):
        return None
    try:
        yanit = _bekle(stop_sirasi, _ESTOP_STM_YANIT_BEKLEME_S)
    except Exception:
        logging.getLogger(__name__).warning("E-stop: kartin STOP yaniti okunamadi", exc_info=True)
        return None
    return yanit if yanit in ("kabul", "red", "yanitsiz") else None


def _emergency_stop_all(reason: str = "manual", mode: str = "Acil Durdurma", kalici: bool = True):
    """Tüm transport'lardan (STM 1-5 + ESP 6-8) DONANIM STOP + seans kapat + WS bildir.
    Manuel acil-durdurma + ESP firmware ALARM'ı + STM bağlantı kaybı ortak bunu çağırır.
    NOT: backend bir sıcaklık/parametre EŞİĞİ dayatmaz; donanımın/operatörün kararına tepki verir.
    `kalici=False` YALNIZ launcher'ın BOŞTA kapanış durdurması (`kapanis_durdur`): STOP'lar ve bellekteki mandal AYNEN, yalnız
    mandal DİSKE yazılmaz (temiz kapanış yeniden başlatmada "önceki oturumda ACİL DURDUR" doğurmasın — D1.75 ilkesi)."""
    import time as _t

    # ⚠️ D1.81 · Y4 — MANDAL HER ŞEYDEN ÖNCE (bütün kaynaklar: düğme, STM kopması/reddi/watchdog'u, ESP alarmı). STOP'tan
    # ÖNCE kurulur: arada kabul edilen bir START, bu E-stop'un STOP'undan sonra keep-alive ile sürerdi. Kurmak yalnız
    # bir bayrak + sayaç (beklemez, hiçbir şeye kapılanmaz); başarısız olsa bile E-stop'un geri kalanı KOŞAR (Ö.4-Y8).
    try:
        estop_mandali.mandalla(
            reason, bosta_kapanis=not kalici
        )  # Y226: boştaki kapanış → arayüzde alarm yerine nötr satır
    except Exception:
        logging.getLogger(__name__).exception("E-stop: mandal kurulamadi (durdurma SURUYOR)")

    with _session_lock:
        coil_ids = _active_session.get("coil_ids") or list(range(1, 9))
        _was_active = bool(_active_session.get("is_active"))
        _db_sid = _active_session.get("db_session_id")
        _started_ep = _active_session.get("started_epoch")
        _start_mono_es = _active_session.get("start_mono")  # kayıt süresi DST-güvenli
        _active_session["is_active"] = False
    # Y227: durdurma ANINDA bir şey çalışıyor muydu (teyit iletisine) — STOP'tan ÖNCE okunur, hiçbir şey BEKLEMEZ (Ö.4-Y8).
    _calisiyordu = _durdurma_aninda_calisiyor_mu(_was_active)
    stm_stopped = False
    _stm_isaret = None
    _stm_stop_sirasi = None
    if state.hardware:
        _stm_isaret = _stm_yazim_isareti_al()
        try:
            stm_stopped = bool(state.hardware.stop_all_coils())
        except Exception:
            logging.exception("STM emergency stop failed")
        _stm_stop_sirasi = _stm_son_stop_sirasi_al()  # i5-F-2: teyit bu STOP'a bağlanır

    # P0 audit 2026-06-28: ESP stop publish'lerini PARALEL gonder (eskiden bobin basina 2 senkron
    # publish sirayla → acil-durdurma N-bobin x ~7sn gecikiyordu). _emergency_stop_all DAIMA bir
    # thread'de calisir (async endpoint asyncio.to_thread; ESP-alarm/STM-disconnect zaten thread),
    # dolayisiyla burada ThreadPoolExecutor guvenli + event-loop'u etkilemez.
    def _estop_one(coil_id):
        # [3.2]: `_{next(_estop_sira)}` eki ŞART — ms tek başına çakışabilir (üstteki blok yorumu).
        command_id = f"estop_{coil_id}_{int(_t.time() * 1000)}_{next(_estop_sira)}"
        # HG-4 (2026-08-19): onay kaydını publish'ten ÖNCE aç (hızlı ESP ack yarışı kaybolmasın).
        _register_ack(command_id, bobin=coil_id)
        ok = _mqtt_publish(
            f"pemf/coil/{coil_id}/control",
            {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()},
        )
        legacy_ok = _mqtt_publish(
            f"pemf/esp32_{coil_id}/command",
            {"command": "stop", "command_id": command_id, "emergency": True, "timestamp": _t.time()},
        )
        # ⚠️ E-stop'u BLOKLAMA: publish gitti, onayı ARKA PLANDA izle. Gelmezse operatör uyarılır.
        # PUBACK bile yoksa bekleme anlamsız → pending kaydını temizle (bekçi thread açma).
        if ok or legacy_ok:
            # ⚠️ Thread start'ı try/except'te (2026-08-19 denetimi): thread tükenirse
            # (`RuntimeError: can't start new thread`) istisna _ex.map üzerinden yayılıp E-stop'un
            # POST-güvenlik işini (live_state sıfırlama, WS yayını, DB finalize) atlardı — oysa
            # fiziksel STOP publish'i ZATEN gitti (yukarıda). Ack izlemenin açılmaması yalnız onay
            # gözlemini kaçırır; E-stop'u düşürmemeli.
            try:
                threading.Thread(
                    target=_estop_ack_watch,
                    args=(int(coil_id), command_id),
                    name=f"estop-ack-{coil_id}",
                    daemon=True,
                ).start()
            except RuntimeError:
                with _pending_acks_lock:
                    _pending_acks.pop(command_id, None)
                logging.getLogger(__name__).error(
                    "E-stop bobin %s: ack-izleme thread'i açılamadı (STOP publish'i gitti, onay izlenmeyecek).",
                    coil_id,
                )
        else:
            with _pending_acks_lock:
                _pending_acks.pop(command_id, None)
        # D1.98 / A-63: ESP BİLEREK kapalıyken satır `devre_disi` (yayın yine denendi); broker ölü `mqtt_unavailable`.
        return {"coilId": coil_id, "mqtt": _esp_yanit_durumu(ok or legacy_ok)}

    # DENETIM P0: kapsam `[cid for cid in coil_ids if cid in ESP_COIL_IDS]` idi → ESP STOP'lari
    # AKTIF SEANSIN bobin listesiyle sinirlaniyordu. STM tarafi ise kosulsuz stop_all_coils()
    # cagiriyor; bu asimetri hatanin kasitsiz oldugunu gosteriyor. Somut ariza: seans coil_ids=[1,2,3]
    # (yalniz STM) iken bobin 7 seans-disi surulmusse (/api/coil/7/control veya onceki seans),
    # _estop_coils BOS kaliyor → bobin 7'ye HIC stop yayinlanmiyor, ustelik asagida mqtt_results
    # bos oldugu icin _esp_ok=True → yanit "success"/confirmed=True ve canli-durum 8 bobini de
    # "durdu" gosteriyor: operatore YANLIS guvence. Acil durdurma ASLA seans kapsamiyla
    # sinirlandirilmaz → DAIMA tum ESP bobinleri. Calismayan bobine STOP zararsiz/idempotenttir.
    _estop_coils = sorted(ESP_COIL_IDS)
    # HG-5 (Plan A-2): E-stop'u BULUT broker'ına da aynala — buluta failover etmiş ESP'ye
    # yerel yayın ulaşmaz. Ayrı daemon thread: yerel yolu (aşağıda, öncelikli) BLOKLAMAZ.
    # ⚠️ try/except ŞART (review F2): thread tükenmesinde istisna buradan yükselirse aşağıdaki
    # YEREL ESP STOP havuzu + live_state sıfırlama + DB finalize ATLANIR — ayna best-effort,
    # E-stop'un esas yolunu asla düşüremez (_estop_ack_watch spawn'ındaki korumanın simetriği).
    # ⚠️ YH-A3 (Y289, P0-2): ayna YALNIZ ESP AÇIKKEN — ESP söküldü (Y230), aynanın tüketicisi (buluta göçmüş ESP) yok;
    # her ACİL DURDUR'da eski HiveMQ kimliğiyle boşuna bağlanıp zaman aşımına düşüyordu (AP B9). Yerel yol aşağıda AYNEN.
    if live_state.esp_etkin():
        try:
            threading.Thread(
                target=_estop_cloud_mirror,
                args=(list(_estop_coils), reason),
                name="estop-cloud-mirror",
                daemon=True,
            ).start()
        except Exception:
            logging.getLogger(__name__).error("E-stop bulut-ayna thread'i açılamadı (yerel yol sürüyor).")
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=max(1, len(_estop_coils))) as _ex:
        mqtt_results = list(_ex.map(_estop_one, _estop_coils))
    # ⚠️ Y46: mandal DİSKE — STM ve ESP STOP'ları gönderildikten SONRA, arka planda. Yazma hatası E-stop'u geciktirmez
    # ya da engellemez (yalnız günlük; Ö.4-Y8). `kalici=False`: boşta kapanış — disk DEĞİŞMEZ (önceki kurulu mandal korunur).
    try:
        if kalici:
            estop_mandali.diske_yaz_arka_planda()
    except Exception:
        logging.getLogger(__name__).exception("E-stop: mandal diske yazdirilamadi (durdurma tamam)")
    with _live_state_lock:
        for idx in range(8):
            coil = _live_state["coils"][idx]
            coil["running"] = False
            coil["dutyCycle"] = 0.0
        snapshots = [dict(_live_state["coils"][i]) for i in range(8)]
    update_live_session_state(is_active=False, mode=mode)
    for coil in snapshots:
        _ws_broadcast_sync({"type": "coil_status", "coilId": coil["id"], "data": coil})
    _ws_broadcast_sync({"type": "emergency_stop", "data": {"timestamp": _t.time(), "reason": reason}})
    # D1.81 · Y4: arayüz (Karşılama/Giriş dahil) mandalı ve "Sıfırla"yı gösterir.
    _ws_broadcast_sync({"type": "estop_mandali", "data": estop_mandali.durum()})

    # DENETIM P2: acil durdurma seansi DB'de KAPATMIYOR, acik coil-run'lari ve son dakikanin
    # sensor verisini kaybediyordu → guvenlik olayinin telemetri KANITI yok oluyordu. Bobinler
    # ZATEN durduruldu (yukarida); bu blok yalnizca kaydi tamamlar, durdurmayi geciktirmez.
    # Denetim izi olarak ayrica session_events'e emergency_stop olayi yazilir.
    # ⚠️ C2-2.5 / C2-4.2 (2-C inceleme · Ö.4-Y8): kayıt kapanışı tek işçili KAYIT kuyruğunda koşar (kuyruğa önceden girmiş
    # koşu başlatma / seans izi kayıtlarından SONRA — sıra korunur); yanıt ve teyit en çok `DURDURMA_KAYIT_BEKLEME_SN`
    # bekler. Tedavi DB'si kilitliyken yanıt ve teyit kayıt yazımlarını 21,7 sn (kilit sürdükçe ~44 sn) bekliyordu — STOP'lar
    # zaten gitmişti. Sağlıklı DB'de kapanış ms'de biter: yanıt eskisi gibi kayıttan SONRA döner.
    def _estop_kaydini_kapat():
        if _was_active and _db_sid:
            try:
                _get_treatment_db().record_session_event(
                    _db_sid,
                    "emergency_stop",
                    payload={"reason": reason, "mode": mode, "coil_ids": list(coil_ids)},
                    severity="critical",
                )
            except Exception:
                logging.getLogger(__name__).warning("estop: session_event yazilamadi", exc_info=True)
            _finalize_session_db(
                _db_sid, _started_ep, coil_ids=coil_ids, reason=f"acil-durdurma:{reason}", start_mono=_start_mono_es
            )
        # ⚠️ D1.68 (B-1.6): finalize kapsamı STOP kapsamıyla EŞLEŞİR — `stop_all_coils` TÜM bobinleri durdurdu; seansın bobin
        # listesi dışındaki (seans sırasında tekil başlatılmış) bobinlerin AÇIK koşuları da kapanır. Eskiden yalnız seansın
        # bobinleri kapanıyor, ötekiler `ended_epoch=NULL` kalıcı kalıyordu. Seans yokken de (önceki seanstan kalan koşu).
        with _active_coil_runs_lock:
            _acik_kosular = list(_active_coil_runs.keys())
        for _cid in _acik_kosular:
            try:
                _finish_coil_run(_cid)
            except Exception:
                logging.getLogger(__name__).warning("estop: kosu kaydi kapatilamadi (bobin %s)", _cid, exc_info=True)

    try:
        from utils import dongu_disi_yazim as _kayit_kuyrugu

        _kayit_kuyrugu.sirada_calistir(_estop_kaydini_kapat, ad="acil durdurma seans kaydi kapanisi")
    except Exception:
        logging.getLogger(__name__).exception("E-stop: seans kaydi kapatilamadi (durdurma tamam)")
    # Audit P2: ust-seviye status'u transport sonuclarindan TURET — eskiden kosulsuz 'success'
    # donuyordu (STM hatasi + broker cokuk olsa bile UI 'ciktilar kesildi' saniyordu). Bir transport
    # dogrulanamadiysa 'partial'/'error' don + confirmed=False (keep-alive/firmware fiziksel-telafi P2).
    # DENETIM P0 (yukaridaki kapsam fix'inin ikinci yarisi): mqtt_results BOS iken _esp_ok=True
    # varsayimi "dogrulanmadi"yi "basarili" sayiyordu. Kapsam artik daima tum ESP bobinleri
    # oldugundan liste bos olamaz; yine de bos-liste FAIL-CLOSED yorumlanir (bos = dogrulanmadi).
    # ⚠️ D1.105 · A-63 (sahip): ESP BİLEREK kapalıyken teyit STM onayına göre — `devre_disi` ESP satırı teyidi düşürmez.
    # ESP STOP'ları yine GÖNDERİLDİ (yukarıda, koşulsuz); istemcinin yedek adımları da teyitten bağımsız koşar
    # (emergencyStop.ts) → gönderim AZALMAZ (Ö.4-Y8). ESP açıkken başarısız yayın teyidi düşürür (eskisi gibi).
    _esp_ok = bool(mqtt_results) and all(r.get("mqtt") in ("success", "devre_disi") for r in mqtt_results)
    stm_stopped = _stm_stop_yazildi_mi(stm_stopped, _stm_isaret, _stm_stop_sirasi)  # D1.55: kuyruk değil PORT
    # ⚠️ D1.114 (B-4.6): oto-firmware YAKMA PENCERESİNDE MCU yeniden programlanıyor — port backend'de AÇIK tutulduğu için
    # STOP baytı ST-Link VCP'ye YAZILIR ama kart işlemez; "porta yazıldı" teyit SAYILMAZ. Yalnız RAPOR: STOP yukarıda
    # yine verildi (Ö.4-Y8 — kapılanmaz, azaltılmaz); yakma yalnız seans/bobin yokken başlar, pencerede başlatma reddedilir.
    try:
        from utils import firmware_yakma_penceresi as _fw_pencere

        _fw_yakiliyor = _fw_pencere.acik_mi()
    except Exception:
        _fw_yakiliyor = False
    if _fw_yakiliyor and stm_stopped:
        logging.getLogger(__name__).warning(
            "E-stop: firmware YAKILIYOR — STOP verildi ama kart işlemiyor olabilir; STM teyidi YOK sayıldı"
        )
        stm_stopped = False
    # ⚠️ TD3 (tezgâh Oturum 13): "porta yazıldı" kartın KABULÜ değildir — uyumsuz kart STOP dahil her pakete CRC NACK dönerken
    # E-stop "teyitli" diyordu. Yazılan STOP'a kartın yanıtı kısa süre beklenir: yalnız NACK → teyit DÜŞER (eylem metni); kabul
    # ya da yanıt yok → bugünkü anlam. STOP'lar yukarıda GİTTİ, NACK yeniden yazımı ve keep-alive telafisi SÜRER (Ö.4-Y8).
    # ⚠️ T2D-1 (Tezgâh-2, 120 B kart + 1.9.51): kart STOP'a çoğunlukla HİÇ yanıt vermedi (NACK ~1 sn sonra) → "teyitli" sahte
    # yeşildi. Yanıtsızlık da teyit DÜŞÜRÜR (eylem metni); sonradan gelen tüm-sıfır ACK teyidi yine verir (D1.E04).
    _stm_kart_yaniti = _stm_stop_kart_yaniti(_stm_stop_sirasi) if stm_stopped else None
    _stm_red = _stm_kart_yaniti == "red"
    _stm_yanitsiz = _stm_kart_yaniti == "yanitsiz"
    _stm_ok = (
        stm_stopped and not (_stm_red or _stm_yanitsiz)
    ) or state.hardware is None  # STM yoksa STM-basarisizligi sayma
    _status = "success" if (_stm_ok and _esp_ok) else ("error" if (not _stm_ok and not _esp_ok) else "partial")
    # D1.E04 · İG-6.7: teyit durumu `running:false` sıfırlamasından AYRI yayınlanır (istemci teyitsizken durdurmayı tutar).
    try:
        live_state.estop_teyidi_yaz(
            bool(_stm_ok and _esp_ok),
            "stm_red" if _stm_red else ("stm_yanitsiz" if _stm_yanitsiz else "estop"),
            calisiyordu=_calisiyordu,
        )
    except Exception:
        logging.getLogger(__name__).exception("E-stop: teyit durumu yayinlanamadi (durdurma tamam)")
    # Y226: boştaki kapanış durdurmasında (`kalici=False`) istemciye ALARM gitmez — günlüğe yine yazılır.
    if _stm_red:
        logging.getLogger(__name__).error("E-stop: kart STOP'u REDDETTI (STM_NACK, kabul yok) — teyit YOK")
        try:
            if kalici:
                _bildir(lambda d: "⛔ " + _stm32_kimlik.estop_kart_red_metni(d), "error")
        except Exception:
            logging.getLogger(__name__).exception("E-stop: kart reddi bildirilemedi (durdurma tamam)")
    elif _stm_yanitsiz:
        logging.getLogger(__name__).error("E-stop: kart STOP'a YANIT VERMEDI (tum-sifir STM_OK / NACK yok) — teyit YOK")
        try:
            if kalici:
                _bildir(lambda d: "⛔ " + _stm32_kimlik.estop_kart_yanitsiz_metni(d), "error")
        except Exception:
            logging.getLogger(__name__).exception("E-stop: kart yanitsizligi bildirilemedi (durdurma tamam)")
    return {
        "status": _status,
        "confirmed": bool(_stm_ok and _esp_ok),
        "stmStopped": stm_stopped,
        "mqttResults": mqtt_results,
        "reason": reason,
        # Denetim izi: acil-durdurma ANINDAKI seans kapsami (STOP kapsamini ARTIK belirlemez).
        "sessionCoilIds": list(coil_ids),
        # D1.81 · Y4 (yalnız-ek): mandal kuruldu — yeni START için operatörün "Sıfırla"sı gerekir.
        "estopMandali": estop_mandali.durum(),
        # Y59: mandal dosyası yazılamıyorsa (SON BİLİNEN durum — disk yazımı BEKLENMEZ, Y46) yeniden başlatmada ne olacağı.
        # Uç auth-muaf → dosya YOLU yok (yol kimlikli bildirimde).
        "mandalDosyasi": estop_mandali.yazim_durumu(),
        # D1.114 (yalnız-ek): E-stop anında STM'e firmware yakılıyordu — STM teyidi neden yok, operatör/destek görsün.
        "firmwareYakiliyor": bool(_fw_yakiliyor),
        # TD3 (yalnız-ek): kartın bu STOP'a yanıtı — "kabul" | "red" | "yanitsiz" (T2D-1) | None; red / yanıtsızda eylem metni.
        "stmKartYaniti": _stm_kart_yaniti,
        "stmRedMesaji": (
            _stm32_kimlik.estop_kart_red_metni()
            if _stm_red
            else (_stm32_kimlik.estop_kart_yanitsiz_metni() if _stm_yanitsiz else None)
        ),
        # Y227 (yalnız-ek): durdurma ANINDA bobin / seans var mıydı (True / False / None = okunamadı) — istemci teyitsiz düğmeyi buna göre tutar.
        "calisiyordu": _calisiyordu,
    }


def _emergency_stop_async(reason: str = "manual", mode: str = "Acil Durdurma"):
    """Audit P2: _emergency_stop_all'i AYRI daemon-thread'de tetikle. STM seri-okuyucu ve MQTT paho
    callback thread'leri (senkron event/mesaj dispatch) bloklanan MQTT publish'iyle ~sn'lerce
    takilmasin — stop bagimsizca yurur, cagiran guvenlik-kritik thread hemen doner (ag-I/O'da
    bloklanmaz; ayrica paho callback'i icinden publish deadlock'u onlenir)."""
    import threading as _th

    _th.Thread(
        target=_emergency_stop_all, kwargs={"reason": reason, "mode": mode}, name=f"estop-{reason}"[:24], daemon=True
    ).start()


def _durdurma_is_parcaciginda(fn, *args, ad: str = "pemf-durdurma"):
    """⚠️ O-1.1 (1-F inceleme §22 #1 · Ö.4-Y8): bir STOP yolunu olay döngüsünün ORTAK iş parçacığı havuzuna
    (`asyncio.to_thread` → varsayılan yürütücü, `min(32, cpu+4)` işçi) BAĞLAMADAN, KENDİ daemon iş parçacığında koşturur ve
    beklenebilir döner. Havuz asılı G/Ç ile (asılı diskte DB yazımları vb.) doluyken `to_thread` SIRAYA giriyordu: ACİL
    DURDUR'un STOP'u porta GİTMİYOR, yanıt dönmüyordu; istemci vazgeçince sıradaki iş İPTAL edilip STOP HİÇ gitmiyordu
    (ölçüldü — 1-G önce-kırmızı: ACİL DURDUR, seans durdurma, AI Pro, 0 Hz, ESP STOP yollarında 30/30).
    * Bağlam (`contextvars`) `to_thread` gibi kopyalanır (sürüş niyeti damgası vb.).
    * Bekleyen iptal edilse de (istemci zaman aşımı) iş YİNE koşar — yalnız sonucu yazılmaz.
    * İş parçacığı açılamazsa (kaynak tükendi) iş BU iş parçacığında eşzamanlı koşar: döngü kısa süre bloklanır ama STOP
      gider (gitmemesinden iyidir)."""
    import concurrent.futures as _cf
    import contextvars as _cv

    gelecek: _cf.Future = _cf.Future()
    baglam = _cv.copy_context()

    def _kos() -> None:
        dinleniyor = gelecek.set_running_or_notify_cancel()  # False: bekleyen vazgeçti — iş YİNE koşar
        try:
            sonuc = baglam.run(fn, *args)
        except BaseException as exc:
            if dinleniyor:
                gelecek.set_exception(exc)
            else:
                logging.getLogger(__name__).warning("%s: durdurma işi hata verdi (bekleyen yok)", ad, exc_info=True)
        else:
            if dinleniyor:
                gelecek.set_result(sonuc)

    try:
        threading.Thread(target=_kos, name=str(ad)[:24], daemon=True).start()
    except RuntimeError:
        logging.getLogger(__name__).error("%s: iş parçacığı açılamadı — durdurma EŞZAMANLI koşuyor (Ö.4-Y8)", ad)
        _kos()
    return asyncio.wrap_future(gelecek)


@app.post("/api/hardware/emergency_stop")
async def emergency_stop():
    """Stop all outputs through every available transport and notify clients."""
    # P0 audit 2026-06-28: _emergency_stop_all senkron MQTT publish yapar (~7sn worst-case) →
    # event-loop'u BLOKLARDI (acil-durdurma yaniti gecikir + tum WS/istemci donardi). Thread'e al — loop responsive
    # kalir; fonksiyon icindeki ESP publish'leri de paralel. ⚠️ O-1.1: KENDİ iş parçacığı — ortak havuz (`to_thread`)
    # asılı G/Ç ile doluyken ACİL DURDUR sıra beklemez.
    result = await _durdurma_is_parcaciginda(_emergency_stop_all, "manual", ad="estop-manual")
    _bildir(lambda d: ceviri.t("bildirim.acilDurdurUygulandi", dil=d), "error")
    return result


#: Launcher'ın kapanış durdurmasının mandal nedeni (arayüz: `EstopMandalBandi.mandalNedeni`).
KAPANIS_DURDURMA_NEDENI = "uygulama_kapanisi"


@app.post("/api/hardware/kapanis_durdur")
async def kapanis_durdur(request: Request):
    """Launcher'ın KAPANIŞ durdurması (`launcher/core/src/backend.rs::safe_stop_coils`) — backend öldürülmeden hemen önce.

    SAHİP BİLDİRİMİ (2026-10-18): "uygulama ilk açılışta niye bu uyarıyı veriyor daha yeni açtık … sürekli çıkmasın". ÖLÇÜLDÜ:
    launcher her pencere kapanışında operatörün ACİL DURDUR ucunu (`/api/hardware/emergency_stop`, neden "manual") çağırıyordu →
    mandal kurulup DİSKE yazılıyor (Y46) → her açılışta "önceki oturumda ACİL DURDUR — sıfırlanmadı (ACİL DURDUR düğmesi)"
    (bu makinede 13.10 20:22:26'daki launcher kapanışından). Temiz kapanış bir acil durdurma değildir (D1.75, `kapanis_kur`).

    Davranış: STOP'lar ACİL DURDUR'la BİREBİR (`_emergency_stop_all`; Ö.4-Y8 — gönderim azalmaz) ve bellekteki mandal kurulur
    (öldürmeye dek START reddi; backend yaşarsa operatör Sıfırla'yı görür). Mandal DİSKE yalnız kapanış anında herhangi bir bobin
    çalışıyorsa ya da seans sürüyorsa yazılır (Y45 ilkesi: boştayken kesinti mandal kurmaz; seans sürerken kapatma GERÇEK kesinti →
    yeniden açılışta Sıfırla ister). Durum okunamazsa ÇALIŞIYOR sayılır (`_herhangi_bobin_calisiyor` — güvenli taraf).
    Yalnız launcher çağırır: SIKI loopback + `{"onay": true}` JSON (tarayıcı çapraz kökenden ön-uçuşsuz gönderemez). Reddedilirse
    launcher ACİL DURDUR ucuna düşer (bobin durdurma yine olur)."""
    _istemci = (getattr(getattr(request, "client", None), "host", "") or "").strip()
    if _istemci not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail=ceviri.t("sistem.hata.kapanisYalnizYerel"))
    if "application/json" not in (request.headers.get("content-type") or "").lower():
        raise HTTPException(status_code=415, detail=ceviri.t("sistem.hata.kapanisJson"))
    try:
        _govde = await request.json()
    except Exception:
        _govde = None
    if not isinstance(_govde, dict) or _govde.get("onay") is not True:
        raise HTTPException(status_code=400, detail=ceviri.t("sistem.hata.kapanisOnay"))
    with _session_lock:
        _seans = bool(_active_session.get("is_active"))
    _kalici = _seans or _herhangi_bobin_calisiyor()
    result = await _durdurma_is_parcaciginda(
        _emergency_stop_all, KAPANIS_DURDURMA_NEDENI, "Uygulama Kapanışı", _kalici, ad="estop-kapanis"
    )
    result["mandalKalici"] = _kalici
    if _kalici:
        _bildir(lambda d: ceviri.t("bildirim.kapanisMandal", dil=d), "error")
    return result


@app.post("/api/hardware/estop_mandali/sifirla")
async def estop_mandalini_sifirla(request: Request):
    """Y4 (sahip kararı) — operatörün AYRI ve BİLİNÇLİ "Sıfırla" eylemi: acil durdurma MANDALINI kaldırır.

    ⚠️ HİÇBİR ŞEYİ BAŞLATMAZ: mandallıyken reddedilen START'lar diriltilmez, seans açılmaz; ardından ayrıca yeni bir
    START gerekir. Acil durdurmadan ÖNCE kurulmuş niyetler E-stop'un artırdığı nesille bayattır; mandal KURULUYKEN
    alınmış niyetler de bayat kalsın diye Sıfırla nesli bir artırır (`estop_mandali.sifirla`, 1-C inceleme i1-F1).
    Yetki: `/api/hardware/*` ile aynı — muaf DEĞİL (`auth._EXEMPT_EXACT` yalnız `/api/hardware/emergency_stop`'u TAM
    yol olarak muaf tutar): yerel ya da LAN (A-01) ya da jeton. Masaüstü Karşılama/Giriş ekranları yerel istemcidir.
    ⚠️ 1-C inceleme i3-F-6: yalnız BİLİNÇLİ istek — `Content-Type: application/json` + `{"onay": true}`. Eskiden
    gövdesiz/JSON'suz POST kabul ediliyordu → LAN'da ya da cihazda açılan HERHANGİ bir sayfa "basit" (ön-uçuşsuz)
    POST ile mandalı kaldırabiliyordu (ölçüldü: `Origin: http://kotu.example`, `text/plain` → 200). Tarayıcı çapraz
    kökenden JSON'u ön-uçuşsuz gönderemez (ön-uçuş CORS'ta düşer); içerik türsüz gövde de reddedilir. Origin listesi
    denetimi SEÇİLMEDİ: tünelden açılan web arayüzünün kendi kökeni LAN listesinde değildir (meşru uzaktan Sıfırla 403).
    Kim sıfırladı → denetim izi (`session_events`, append-only): operatör + istemci adresi + köken (oturumsuz ekranda
    `operator` boştur)."""
    from servers.auth import cozumlenmis_operator

    if "application/json" not in (request.headers.get("content-type") or "").lower():
        raise HTTPException(status_code=415, detail=ceviri.t("sistem.hata.sifirlaJson"))
    try:
        _govde = await request.json()
    except Exception:
        _govde = None
    if not isinstance(_govde, dict) or _govde.get("onay") is not True:
        raise HTTPException(status_code=400, detail=ceviri.t("sistem.hata.sifirlaOnay"))
    _kim = cozumlenmis_operator(request, "") or ""
    _onceki = estop_mandali.durum()
    _kurulu = estop_mandali.sifirla(_kim or "operator")
    # Y46: yeniden başlatmada mandal geri gelmesin. Y59: yazım EŞZAMANLI (≤ 2 sn) — sonucu yanıtta söylenir; yazılamazsa
    # mandal yine KALKAR (Y56) ve ekran bildirimi gider (`yazim_hatasi_kancasi`). ⚠️ 1-F inceleme: yazım KENDİ iş
    # parçacığında — `asyncio.to_thread` DEĞİL (asılı diskte ortak havuzu tüketip ACİL DURDUR'u bekletiyordu, B-1.2);
    # süresinde bitmezse yanıt ve bildirim bunu söyler ("sorun yok" demez, B-1.1).
    _yazim_bitmedi = False
    try:
        await asyncio.wait_for(asyncio.wrap_future(estop_mandali.diske_yaz_ayri_is_parcaciginda()), timeout=2.0)
    except Exception:  # asyncio.TimeoutError dahil (iş parçacığı açılamadı da "bitmedi")
        _yazim_bitmedi = True
        logging.getLogger(__name__).warning("Sıfırla: mandal dosyası yazımı 2 sn'de bitmedi (arka planda sürüyor)")
        _md_bitmedi = estop_mandali.yazim_durumu(yol_dahil=True, bitmedi=True)
        if _md_bitmedi.get("mesaj"):
            _bildir(lambda d: "⚠️ " + (_md_bitmedi.get("mesajlar") or {}).get(d, _md_bitmedi["mesaj"]), "error")
    _durum = estop_mandali.durum()
    if _kurulu:
        try:
            await asyncio.to_thread(
                lambda: _get_treatment_db().record_session_event(
                    None,
                    "estop_mandali_sifirlandi",
                    payload={
                        "operator": _kim,
                        "neden": _onceki.get("neden"),
                        "mandal_zamani": _onceki.get("zaman"),
                        "istemci": getattr(request.client, "host", "") or "",  # i3-F-6: NEREDEN (oturumsuz ekran)
                        "koken": request.headers.get("origin", ""),
                    },
                    severity="warning",
                )
            )
        except Exception:
            logging.getLogger(__name__).warning("Mandal sıfırlama denetim izi yazılamadı.", exc_info=True)
        _bildir(lambda d: ceviri.t("bildirim.mandalSifirlandi", dil=d), "warning")
        with _session_lock:
            _aktif = bool(_active_session.get("is_active"))
        if not _aktif:
            update_live_session_state(is_active=False, mode="Sistem Hazır")
    _ws_broadcast_sync({"type": "estop_mandali", "data": _durum})
    return {
        "status": "success",
        "mandalKuruluydu": _kurulu,
        "estopMandali": _durum,
        "mandalDosyasi": estop_mandali.yazim_durumu(yol_dahil=True, bitmedi=_yazim_bitmedi),  # Y59 (kimlikli — yol var)
    }


# Y59: mandal dosyası yazılamazsa ekran bildirimi (her yazım yolu: E-stop arka plan yazımı, Sıfırla, Y45). Geç bağlama:
# `_push_notification` çağrı anında çözülür.
estop_mandali.yazim_hatasi_kancasi_bagla(
    lambda d: _bildir(lambda dil: "⚠️ " + (d.get("mesajlar") or {}).get(dil, d.get("mesaj", "")), "error")
)


# --- PATIENT DATABASE ENDPOINTS ---
# (audit B-2.2) Hasta CRUD uçları servers/patient_router.py'ye taşındı (modüler ayrım; yollar aynı).

# ── ARAYÜZ ÖNBELLEK POLİTİKASI (2026-09-09, ÖLÇÜLEN SAHA ARIZASI) ─────────────────────────
#
# BELİRTİ: masaüstü istemcide "Beklenmeyen bir hata oluştu — Loading module .../ControlScreen-
# <hash>.js failed" ve `client_errors.jsonl`de `[FATAL] Requiring unknown module "2636"`.
#
# ÖLÇÜM: istenen chunk diskte İSTENEN HASH'LE VARDI ve HTTP 200 dönüyordu → dosya kaybı değil.
# `base-app.zip` 15:21'de kuruldu, sunulan 13 chunk'ın hepsi 15:21 damgalı (tek tutarlı yapı),
# ilk FATAL 15:21:55 — kurulumdan 34 sn sonra. "Requiring unknown module" YALNIZCA paketin iki
# yarısı FARKLI YAPILARDAN geldiğinde olur: Metro modül numaralarını her yapıda yeniden atar.
#
# KÖK NEDEN: `StaticFiles` yalnız `last-modified` + `etag` gönderir, `Cache-Control` GÖNDERMEZ.
# Cache-Control'süz yanıtta tarayıcı SEZGİSEL önbellekleme uygular (RFC 9111 §4.2.2) → WebView2
# `index.html`i doğrulamadan yeniden kullanabiliyor. Güncelleme `entry-*`/`__common-*` hash'lerini
# değiştirdiği için önbellekten gelen ESKİ sayfa YENİ chunk'larla karışıyor ve modül kayıt
# defteri uyuşmuyor. Sessiz güncelleme + sezgisel önbellek = her açılışta FATAL.
#
# POLİTİKA (SPA'ların standart deseni):
#   · `*.html`            → `no-store`  : giriş belgesi ASLA önbellekten gelmez → sayfa ve
#                                          chunk'lar HER ZAMAN aynı yapıdan gelir.
#   · içerik-hash'li dosya → 1 yıl `immutable` : adı içeriğine bağlı, yapı değişince ad değişir.
#                                          ⚠️ Bunu `no-store` yapmak arızayı "çözer" ama her
#                                          açılışta tüm paketi yeniden indirtir (klinik hotspot).
#   · diğerleri           → `no-cache`  : ETag ile 304 döner (ucuz) ama bayat kalmaz.
_ICERIK_HASHI = re.compile(r"[-.][0-9a-f]{16,}(?=[.@]|$)")


def _onbellek_politikasi(yol: str, icerik_tipi: str = "") -> str:
    """Statik dosya yolundan `Cache-Control` değeri. SAF fonksiyon — kapı bunu doğrudan ölçer.

    ⚠️ `icerik_tipi` PARAMETRESİ ZORUNLU (kapı yakaladı): `/` isteğinde Starlette
    `get_response`a yol olarak "." verir ve `index.html`i KENDİ İÇİNDE sunar. Yalnız dosya
    adına bakan ilk sürüm bu yüzden giriş belgesine `no-cache` yazıyordu — revalidasyon
    zorladığı için tehlikesiz ama hedeflenen `no-store` DEĞİL. Yanıtın gerçek içerik tipine
    bakmak hem `/` hem `/index.html` hem de html geri-düşüşlerini kapsar.
    """
    ad = yol.replace("\\", "/").rsplit("/", 1)[-1]
    if ad.endswith((".html", ".htm")) or icerik_tipi.startswith("text/html"):
        return "no-store, must-revalidate"
    if _ICERIK_HASHI.search(ad):
        return "public, max-age=31536000, immutable"
    return "no-cache"


class OnbellekPolitikaliStatik(StaticFiles):
    """`StaticFiles` + açık `Cache-Control`.

    ⚠️ Kanca `get_response`, `file_response` DEĞİL: 304 (koşullu istek) ve 404 yolları
    `file_response`tan GEÇMEZ — politika oraya konsaydı tam da tarayıcının ETag'le sorduğu
    anda düşer ve sezgisel davranış geri gelirdi.
    """

    async def get_response(self, path, scope):  # type: ignore[override]
        yanit = await super().get_response(path, scope)
        yanit.headers["Cache-Control"] = _onbellek_politikasi(path, yanit.headers.get("content-type", ""))
        return yanit


# 2. DEMA Simülatörü host etme
sim_path = str(packaged_resource_path("dema-terapi-simülatörü", "dist"))
if os.path.exists(sim_path):
    # Aynı politika: simülatör de hash'li varlıklı bir SPA, aynı karışık-yapı riskini taşır.
    app.mount("/simulator", OnbellekPolitikaliStatik(directory=sim_path, html=True), name="simulator")

# 1. Ana React Arayüzünü host etme (frontend/dist)
frontend_candidates = [
    packaged_resource_path("frontend", "dist"),
    packaged_resource_path("frontend_temp"),
]
frontend_path = next((str(path) for path in frontend_candidates if (path / "index.html").exists()), None)
if frontend_path:
    # DİKKAT: / endpoint'i diğer tüm API rotalarından (örn: /api) SONRA tanımlanmalıdır.
    # Bu yüzden mount işlemini en alta (API router'larından sonra) ekliyoruz.
    app.mount("/", OnbellekPolitikaliStatik(directory=frontend_path, html=True), name="frontend")
else:
    import logging

    logging.getLogger(__name__).warning("Frontend derlemesi bulunamadı! Tarayıcıda boş sayfa çıkabilir.")

# P2 audit 2026-06-28: start_fastapi_server() + __main__ KALDIRILDI — main.py silindi, HeadlessCore
# cagirmiyordu, backend_service.py kullanmiyordu (olu). Bu alt-giris uvicorn.run'i backend_service.py'nin
# guvenlik/reconcile setup'i (PEMF_REQUIRE_AUTH zorlama, stale-session reconcile, named-tunnel) OLMADAN
# yapiyordu → kaza-guvensiz. TEK gercek giris noktasi: backend_service.py.
