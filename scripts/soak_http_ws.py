#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: mertaygn
"""SOAK — HTTP + WebSocket yolu (VERIFICATION §7'nin bugünkü mimariye uyarlaması).

⚠️ NEDEN YENİ BİR BETİK
=======================
`scripts/soak_publish_5hz_8coil.py` yükü **MQTT** üzerinden basıyor. ESP kartları söküldü
(2026-09-11) ve `PEMF_ESP_ENABLED=0` varsayılan — MQTT dinleyicisi HİÇ başlamıyor. Yani o
betik bugün **hiçbir canlı yolu zorlamıyor**: koşar, "başarılı" görünür ve sıfır şey ölçer.
(Silmiyoruz: ESP geri gelirse yine geçerli olacak — bkz. `PEMF_ESP_ENABLED`.)

Bugün canlı yol: istemci ↔ backend **HTTP + WebSocket**. Bu betik onu zorlar ve §7'nin üç
sorusunu ölçer:
  · bellek sızıntısı  → backend RSS zaman serisi (monoton artıyor mu)
  · WS kararlılığı    → bağlantı kopuyor mu, kaç kez yeniden bağlandı
  · DB büyümesi       → veri kökündeki .db dosyalarının toplamı

⚠️ HASTA GÜVENLİĞİ: bu betik **BOBİN SÜRMEZ**. Yalnız okuma uçlarını ve WS'i zorlar; hiçbir
`/session/start`, `/coil/*/control` ya da E-stop çağrısı yapmaz. Donanım bağlıyken güvenle
koşturulabilir.

KULLANIM
--------
    python scripts/soak_http_ws.py --port 8082 --dakika 20
    python scripts/soak_http_ws.py --port 8000 --dakika 120 --aralik 60

⚠️ ÖN-UÇUŞ: HTTP uçları VE `/ws` (bağlantı + ilk mesaj) soak BAŞLAMADAN denetlenir; biri
ölçülemeyecekse (yanlış yol, websockets yok, auth açık profil 1008) koşu başlamaz, çıkış 2.
Çıkış: 0 = TEMIZ · 1 = en az bir neden (hepsi basılır) · 2 = ön-uçuş reddi.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU (D0Ö.19/21 · B-10.32, B-9.27) ──────────────────
# ⚠️ `_veri_koku` eskiden fonksiyon içinde DEPO KÖKÜNÜ (`parents[1]`) ekliyordu; F4'ten beri
#    `utils` orada değil → `get_app_data_directory` sessizce düştü ve soak YANLIŞ kökün DB
#    büyümesini ölçtü. Kök İŞARET DOSYASIYLA aranır (scripts/stm_firmware_kimligi.py deseni).
#    Kapı: tests/test_betikler_ACILIYOR.py::test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend). Betik depo dışına mı taşındı?")


_KOK = _depo_koku(Path(__file__).resolve())
for _yol in (_KOK, _KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

#: Yalnız OKUMA uçları — sıra önemli değil, hepsi her turda çağrılır.
#
#: ⚠️ İLK YAZIMDA `/api/history/sessions?limit=50` vardı — BÖYLE BİR UÇ YOK. İstek
#: `/api/history/{session_id}` rotasına düşüp her turda **422** döndürdü ve 25 dakikalık koşu
#: "4453 istek başarısız → WS/HTTP kararlılığı şüpheli" diye bitti. Yani BETİĞİN YAZIM HATASI
#: ÜRÜN ARIZASI gibi raporlandı. Bu yüzden aşağıda `_uclari_dogrula` var: soak başlamadan her
#: uç BİR KEZ çağrılır ve beklenmedik kod dönen varsa koşu HİÇ BAŞLAMAZ.
UCLAR = [
    "/api/health",
    "/api/dashboard-snapshot",
    "/api/gateway/status",
    "/api/patients",
    "/api/history/",
]

#: Kabul edilen kodlar. 401/403 auth açıkken normaldir; 404/422 DEĞİLDİR (yanlış yol demektir).
KABUL = (200, 401, 403)

#: Ürünün canlı telemetri/kontrol kanalı (`api_server` → `@app.websocket("/ws")`). Bağlanınca
#: `snapshot` yollar, `{"type": "ping"}`e `pong` döner.
#: ⚠️ D0Ö.22 ek: "yerel bağlantıda auth istemez" YALNIZ klinik profilde doğru — auth açık profilde
#: (loopback yerel sayılmıyorsa) token'sız bağlantıyı accept() edip 1008 ile kapatır. Betik token
#: GÖNDERMEZ; ön-uçuş bunu "auth" diye adlandırıp soak'ı BAŞLATMAZ (kopma sayılmaz).
WS_YOLU = "/ws"

#: WS ön-uçuşunda bağlantı + İLK mesaj (snapshot) için azami bekleme (sn).
WS_ON_UCUS_S = 5.0

#: RFC 6455 "policy violation" — `api_server` token'sız `/ws`i bununla kapatır.
_WS_AUTH_KODU = 1008


def _ws_on_ucus(uri: str) -> str:
    """Soak BAŞLAMADAN `/ws`ye bir kez bağlan ve İLK mesajı bekle; sorun varsa nedenini döndür ("" = sağlam).

    ⚠️ D0Ö.22 ek (tur 4): eskiden WS için ön-uçuş yoktu — websockets'siz bir Python ya da token isteyen
    profil 72 saat koşar, ancak SONDA "ölçülmedi" derdi. HTTP ön-uçuşu (`_uclari_dogrula`) gibi, WS de
    ölçülemeyecekse koşu HİÇ BAŞLAMAZ.
    """
    try:
        from websockets.sync.client import connect
    except ImportError as e:
        return f"websockets paketi yuklenemedi ({e})"
    try:
        ws = connect(uri, open_timeout=WS_ON_UCUS_S, close_timeout=1)
    except Exception as e:
        return f"baglanilamadi — {type(e).__name__}: {e}"[:240]
    with ws:
        try:
            ws.recv(timeout=WS_ON_UCUS_S)
        except TimeoutError:
            return f"baglandi ama {WS_ON_UCUS_S:g} sn icinde ILK mesaj (snapshot) GELMEDI"
        except Exception as e:
            kod = getattr(getattr(e, "rcvd", None), "code", None)
            if kod == _WS_AUTH_KODU:
                return (
                    f"sunucu {_WS_AUTH_KODU} (politika) ile kapatti — auth acik profil: /ws token istiyor, "
                    "betik token GONDERMEZ (auth kapali klinik profilde kosturun)"
                )
            return f"ilk mesaj beklenirken koptu — {type(e).__name__}: {e}"[:240]
    return ""


class _WsIzleyici(threading.Thread):
    """`/ws`ye soak BOYUNCA bağlı kalır; kopmaları ve bağlanamamaları SAYAR, yeniden bağlanır.

    ⚠️ D0Ö.22 (B-9.26): betik adı ve belgeler "HTTP + WebSocket soak" diyordu ama HİÇ `/ws` açmıyordu —
    canlı kanalın kopma sınıfı soak'ta GÖRÜNMÜYORDU, yine de "TEMIZ" kaydı düşüldü (VERIFICATION §7).
    Sayaçlar karara girer (bkz. `main`). Soak'ı DÜŞÜRMEZ: her hata sayılır, 2 sn sonra yeniden denenir.
    """

    def __init__(self, uri: str, ping_aralik: float = 15.0):
        super().__init__(name="soak-ws", daemon=True)
        self.uri = uri
        self.ping_aralik = ping_aralik
        self.dur = threading.Event()
        self.baglanti = 0
        self.kopma = 0
        self.baglanamama = 0
        self.mesaj = 0
        self.son_hata = ""

    def run(self) -> None:
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            self.son_hata = f"websockets paketi yuklenemedi ({e})"
            return
        while not self.dur.is_set():
            bagli = False
            try:
                with connect(self.uri, open_timeout=5, close_timeout=1) as ws:
                    bagli = True
                    self.baglanti += 1
                    son_ping = time.monotonic()
                    while not self.dur.is_set():
                        try:
                            ws.recv(timeout=1.0)
                            self.mesaj += 1
                        except TimeoutError:
                            pass
                        if time.monotonic() - son_ping >= self.ping_aralik:
                            ws.send('{"type": "ping"}')
                            son_ping = time.monotonic()
            except Exception as e:  # kopma YA DA bağlanamama — ikisi de sayılır, soak düşmez
                if self.dur.is_set():
                    break
                self.son_hata = f"{type(e).__name__}: {e}"[:200]
                if bagli:
                    self.kopma += 1
                else:
                    self.baglanamama += 1
            self.dur.wait(2.0)  # yeniden bağlanma aralığı

    def durdur(self) -> None:
        self.dur.set()
        self.join(timeout=10)


def _istek(taban: str, yol: str, zaman_asimi: float = 10.0):
    try:
        with urllib.request.urlopen(taban + yol, timeout=zaman_asimi) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:
        return 0, 0


def _uclari_dogrula(taban: str) -> list[str]:
    """Soak BASLAMADAN her ucu bir kez cagir; beklenmedik kod donen varsa listele.

    ⚠️ Bu kapi 2026-09-13'te eklendi: betikteki bir YAZIM HATASI (`/api/history/sessions`,
    boyle bir uc yok) 25 dakika boyunca her turda 422 dondurmustu ve sonuc "urun kararsiz"
    gibi raporlanmisti. Olcum aracinin kendi hatasi, olctugu seyin hatasi gibi gorunmemeli.
    """
    kotu = []
    for yol in UCLAR:
        kod, _ = _istek(taban, yol)
        if kod not in KABUL:
            kotu.append(f"{yol} -> HTTP {kod}")
    return kotu


def _port_sureci(port: int):
    """(`port`u LISTEN eden süreç, "") ya da (None, NEDEN + EYLEM).

    ⚠️ D0Ö.15 ek (tur 4, ORTA): RSS eskiden ADA göre (`pemf_backend*`) seçiliyordu ve `--port` ile bağı
    yoktu. Hedef kaynaktan koşan dev backend (`python.exe`) iken makinede başka bir PEMF_Backend (ör.
    sahibin 8000'deki backend'i) varsa RSS O süreçten okunuyor, hedef ÖLÇÜLMEDEN "TEMIZ" çıkıyordu
    (ölçüldü: iki senaryoda da `SONUC: TEMIZ`). Birden çok instance'ın TOPLANMASI (2026-09-13: 4106 MB
    "1,8 GB sızıntı" yanılgısı) da böylece biter: yalnız hedef portun süreci okunur.
    """
    try:
        import psutil
    except ImportError:
        return None, "psutil yuklu degil (kurun: pip install psutil)"
    try:
        for b in psutil.net_connections(kind="tcp"):
            if b.laddr and b.laddr.port == port and b.status == psutil.CONN_LISTEN and b.pid:
                return psutil.Process(b.pid), ""
    except Exception as e:
        return None, f"baglanti tablosu okunamadi ({type(e).__name__}: {e}) — yonetici olarak calistirin"
    return None, f"{port} portunu dinleyen surec gorulemedi (psutil PID vermedi) — yonetici olarak calistirin"


def _backend_rss_mb(port: int) -> float:
    """`port`u LISTEN eden backend sürecinin RSS'i (MB). Ölçülemezse 0 (neden: `_port_sureci`)."""
    p, _neden = _port_sureci(port)
    if p is None:
        return 0.0
    try:
        return round(p.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return 0.0


def _rss_kaynagini_bildir(port: int) -> bool:
    """Hangi sürecin ölçüleceğini (ya da NEDEN ölçülemeyeceğini) koşu BAŞINDA söyle."""
    p, neden = _port_sureci(port)
    if p is None:
        print(
            f"  UYARI: RSS OLCULEMIYOR — {neden}. Bu kosu bellek sizintisi icin KARAR VEREMEZ "
            "(sonuc RSS OLCULMEDI olur)."
        )
        return False
    try:
        ad = p.name()
    except Exception:
        ad = "?"
    print(f"  RSS kaynagi: PID {p.pid} ({ad}) — {port} portunu dinleyen surec")
    return True


def _rss_oturmasini_bekle(port: int, azami_sn: float = 180.0, kararli_tur: int = 3) -> float:
    """AI ısıtması bitene kadar bekle; oturmuş RSS'i döndür.

    ⚠️ BU BEKLEME OLMADAN KAPI YANLIŞ ALARM VERİR. Ölçüldü (2026-09-13):
    backend `/api/health` 200 döndüğünde RSS **254 MB**; arka plandaki AI ısıtması
    ~15 sn içinde onu **2310 MB**'a çıkarıyor ve orada SABİTLİYOR. Soak sağlık
    kontrolünden hemen sonra taban alırsa 254 → 2310 = **%809 artış** görür ve
    "SIZINTI SUPHESI" der — oysa hiçbir şey sızmamıştır.

    Ölçüt: ardışık `kararli_tur` örnekte değişim %1'in altındaysa oturmuştur.
    """
    onceki = _backend_rss_mb(port)
    if onceki <= 0:
        # ⚠️ D0Ö.15 (B-10.97): ÖLÇÜLEMEYEN şey OTURMAZ — eskiden `azami_sn` (180 sn) boşuna beklenip
        # 0 ile devam ediliyordu; sonuç da TEMIZ çıkıyordu (bkz. `main` kararı).
        print("  UYARI: backend RSS okunamiyor — isinma BEKLENMIYOR.")
        return 0.0
    kararli = 0
    bitis = time.monotonic() + azami_sn
    while time.monotonic() < bitis:
        time.sleep(5)
        simdi = _backend_rss_mb(port)
        if onceki <= 0:
            onceki = simdi
            continue
        degisim = abs(simdi - onceki) / onceki * 100.0
        kararli = kararli + 1 if degisim < 1.0 else 0
        onceki = simdi
        if kararli >= kararli_tur:
            return simdi
    return onceki


def _veri_koku() -> Path:
    """Backend'in GERÇEKTEN yazdığı veri kökü.

    ⚠️ `get_app_data_directory()` tek başına YETMEZ: launcher backend'i
    `PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System` ile başlatır, yani saha DB'leri
    `%PROGRAMDATA%\\PEMF_System\\PEMF_GUI` altındadır. Bu betik launcher'sız koştuğunda
    `%APPDATA%\\PEMF_GUI`ye düşer ve **yanlış veritabanlarının** büyümesini ölçer
    (ölçüldü 2026-09-13: ilk koşuda tam olarak bu oldu, DB büyümesi anlamsız çıktı).
    """
    import os

    adaylar: list[Path] = []
    pd = os.environ.get("PROGRAMDATA", "").strip()
    if pd:
        adaylar.append(Path(pd) / "PEMF_System" / "PEMF_GUI")
    # ⚠️ D0Ö.21 (B-9.27): import hatası YUTULMAZ — eskiden `except Exception: pass` ile
    # `get_app_data_directory` sessizce düşüyor ve soak YANLIŞ kökün DB büyümesini ölçüyordu.
    try:
        from utils.path_utils import get_app_data_directory
    except ImportError as e:
        raise SystemExit(
            f"HATA: utils.path_utils yuklenemedi ({e}) — veri koku bulunamaz, DB buyumesi YANLIS kokte "
            "olculur. Betigi depodan (scripts/) calistirin; depo/kurulum bozuk olabilir."
        ) from e
    adaylar.append(Path(get_app_data_directory()))

    for kok in adaylar:
        if kok.is_dir() and any(kok.glob("*.db")):
            return kok
    return adaylar[0] if adaylar else Path(".")


def _db_kb(veri_koku: Path) -> int:
    try:
        return int(sum(f.stat().st_size for f in veri_koku.glob("*.db")) / 1024)
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    # ⚠️ D0Ö.22: ZORUNLU — betik artık `/ws` de açar; varsayılan 8000 (çalışan klinik backend'i)
    # SESSİZCE hedeflenmesin. Ölçülmesi istenen backend'in portu AÇIKÇA verilir.
    ap.add_argument("--port", type=int, required=True, help="olculecek backend portu (HTTP + /ws)")
    ap.add_argument("--dakika", type=float, default=20.0)
    ap.add_argument("--aralik", type=float, default=30.0, help="ornekleme araligi (sn)")
    a = ap.parse_args()

    taban = f"http://127.0.0.1:{a.port}"
    kod, _ = _istek(taban, "/api/health", 5.0)
    if kod != 200:
        print(f"HATA: backend ayakta degil ({taban}/api/health -> {kod})")
        return 2

    kotu = _uclari_dogrula(taban)
    if kotu:
        print("HATA: on-ucus dogrulamasi BASARISIZ — soak baslatilmadi.")
        for k in kotu:
            print("  " + k)
        print("  Bu, URUNUN degil BETIGIN sorunu olabilir (yanlis yol). Uc listesini duzeltin.")
        return 2

    ws_uri = f"ws://127.0.0.1:{a.port}{WS_YOLU}"
    ws_sorun = _ws_on_ucus(ws_uri)
    if ws_sorun:
        print(f"HATA: WS on-ucus BASARISIZ ({ws_uri}): {ws_sorun}")
        print("  Bu kosuda WS kararliligi OLCULMEDI olurdu — soak baslatilmadi.")
        return 2

    veri_koku = _veri_koku()

    # ⚠️ ISINMAYI BEKLE (bkz. _rss_oturmasini_bekle). Taban, AI ısıtması bittikten SONRA
    # alınmalı; yoksa ısıtmanın kendisi "sızıntı" diye raporlanır.
    _rss_kaynagini_bildir(a.port)
    print("  AI isitmasinin oturmasi bekleniyor (taban olcumu icin)...")
    oturmus = _rss_oturmasini_bekle(a.port)
    print(f"  taban RSS oturdu: {oturmus} MB" if oturmus > 0 else "  taban RSS: OLCULEMEDI")

    bitis = time.monotonic() + a.dakika * 60
    ornekler: list[tuple[float, float, int, int]] = []
    tur = 0
    hata = 0
    basla = time.monotonic()

    ws = _WsIzleyici(ws_uri)
    ws.start()

    print(f"soak basladi: {taban}  sure={a.dakika} dk  aralik={a.aralik} sn  (+ WS {WS_YOLU})")
    print(f"  veri koku: {veri_koku}")
    # D0Ö.22 ek: WS sayaçları periyodik satırda — kopma 72 saatin SONUNDA değil anında görünür.
    print(f"{'dk':>6} {'RSS(MB)':>9} {'DB(KB)':>8} {'tur':>7} {'hata':>6} {'ws':>4} {'kop':>4} {'red':>4}")

    sonraki_ornek = 0.0
    while time.monotonic() < bitis:
        for yol in UCLAR:
            kod, _ = _istek(taban, yol)
            tur += 1
            if kod not in KABUL:
                hata += 1
        gecen = time.monotonic() - basla
        if gecen >= sonraki_ornek:
            rss, db = _backend_rss_mb(a.port), _db_kb(veri_koku)
            ornekler.append((gecen / 60.0, rss, db, hata))
            print(
                f"{gecen / 60:6.1f} {rss:9.1f} {db:8d} {tur:7d} {hata:6d} {ws.baglanti:4d} {ws.kopma:4d} {ws.baglanamama:4d}"
            )
            sonraki_ornek = gecen + a.aralik
        time.sleep(0.25)

    ws.durdur()
    ws_ozeti = f"  WS : baglanti {ws.baglanti}, KOPMA {ws.kopma}, baglanamama {ws.baglanamama}, mesaj {ws.mesaj}" + (
        f"  (son hata: {ws.son_hata})" if ws.son_hata else ""
    )
    if len(ornekler) < 2:
        # D0Ö.15 (B-10.97): tek örnekle sızıntı/kararlılık kararı VERİLEMEZ — eskiden 0 dönüyordu.
        print("\nSONUC: ornek sayisi yetersiz — karar VERILEMEDI; daha uzun kosturun.")
        print(ws_ozeti)  # D0Ö.22 ek: bu yolda da WS sayaçları görünür
        return 1

    ilk_rss, son_rss = ornekler[0][1], ornekler[-1][1]
    ilk_db, son_db = ornekler[0][2], ornekler[-1][2]
    artis = son_rss - ilk_rss
    oran = (artis / ilk_rss * 100) if ilk_rss else 0.0
    rss_olculdu = bool(ilk_rss and son_rss)

    print("\n=== OZET ===")
    print(f"  istek: {tur}  hata: {hata}")
    # D0Ö.15 ek: ölçülmeyen RSS "0.0 -> 0.0 MB (%+0.0)" diye ÖLÇÜLMÜŞ bir %0 gibi basılmaz.
    print(
        f"  RSS: {ilk_rss} -> {son_rss} MB  (fark {artis:+.1f} MB, %{oran:+.1f})" if rss_olculdu else "  RSS: OLCULMEDI"
    )
    print(f"  DB : {ilk_db} -> {son_db} KB  (fark {son_db - ilk_db:+d} KB)")
    print(ws_ozeti)

    # ⚠️ D0Ö.22 ek: TÜM nedenler toplanıp basılır — eskiden ilk başarısız nedende dönülüyordu
    # (RSS ölçülemeyip WS de koptuysa yalnız RSS söyleniyordu).
    sorunlar: list[str] = []
    # ⚠️ D0Ö.15 (B-10.97): RSS okunamadıysa (psutil yok / hedef portu dinleyen süreç yok) oran 0 çıkar
    # ve eskiden sonuç "TEMIZ" oluyordu — bellek sızıntısı hiç ölçülmeden. Ölçülmeyen şey temiz sayılmaz.
    # D0Ö.15 ek: jeton ASCII (`RSS OLCULMEDI` — günlükte tek jetonla aranır), neden + eylem yanında.
    if not rss_olculdu:
        _p, neden = _port_sureci(a.port)
        sorunlar.append(
            f"UYARI: RSS OLCULMEDI — {neden or 'hedef surecin RSS okumasi 0 dondu'}; bellek sizintisi DEGERLENDIRILMEDI."
        )
    # ⚠️ ESIK GEREKCESI: kisa soak'ta birkac MB dalgalanma NORMALDIR (GC, arena, onbellek).
    # Sizinti isareti MONOTON ve ORANSAL artistir. %25 esigi, 20 dk'lik bir kosuda
    # gurultuyu eleyip gercek bir sizintiyi yakalayacak kadar genis; daha dar bir esik
    # yanlis alarm uretir ve kapi guvenilmez olur.
    elif oran > 25.0:
        sorunlar.append("⚠️ RSS %25'ten fazla artti -> SIZINTI SUPHESI. Daha uzun kosturup dogrulayin.")
    if hata:
        sorunlar.append(f"⚠️ {hata} istek basarisiz -> HTTP kararliligi supheli.")
    # D0Ö.22: WS sonucu KARARA girer — bağlanılamayan kanal "kararlı" sayılamaz.
    if ws.baglanti == 0:
        sorunlar.append(f"UYARI: {WS_YOLU} kanalina HIC baglanilamadi -> WS kararliligi OLCULMEDI.")
    else:
        if ws.kopma or ws.baglanamama:
            sorunlar.append(
                f"UYARI: WS {ws.kopma} kez KOPTU, {ws.baglanamama} kez yeniden baglanamadi -> WS kararliligi SUPHELI."
            )
        if ws.mesaj == 0:
            # D0Ö.22 ek: açık kalıp snapshot bile almayan bağlantı "kararlı" değildir.
            sorunlar.append("UYARI: WS bagli kaldi ama HIC mesaj gelmedi (snapshot bile) -> WS kararliligi SUPHELI.")
    if sorunlar:
        print()
        for s in sorunlar:
            print(f"  {s}")
        print(f"\nSONUC: SORUNLU ({len(sorunlar)} neden)")
        return 1
    print("\nSONUC: TEMIZ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
