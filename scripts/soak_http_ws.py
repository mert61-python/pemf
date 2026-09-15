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
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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


def _backend_surecleri() -> list:
    try:
        import psutil
    except Exception:
        return []
    bulunan = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            if (p.info["name"] or "").lower().startswith("pemf_backend"):
                bulunan.append(p)
        except Exception:
            continue
    return bulunan


def _backend_rss_mb() -> float:
    """Backend süreç(ler)inin TOPLAM RSS'i (MB). psutil yoksa 0 döner (ölçüm atlanır).

    ⚠️ TOPLAR. Makinede birden çok backend koşuyorsa (test instance'ları, launcher'ın
    kendi backend'i) sayı onların TOPLAMIDIR. Ölçüldü (2026-09-13): iki instance varken
    4106 MB okundu ve bir an "1,8 GB sızıntı" gibi göründü — oysa tek instance'ın oturmuş
    tabanı ~2310 MB idi. `_surec_sayisi_uyar` bu yanılgıyı görünür kılar.
    """
    sur = _backend_surecleri()
    if not sur:
        return 0.0
    toplam = 0
    for p in sur:
        try:
            toplam += p.info["memory_info"].rss
        except Exception:
            continue
    return round(toplam / 1024 / 1024, 1)


def _surec_sayisi_uyar() -> int:
    """Birden çok backend varsa RSS okuması TOPLAMDIR — kullanıcıya söyle."""
    n = len(_backend_surecleri())
    if n > 1:
        print(
            f"  ⚠️ {n} adet PEMF_Backend sureci calisiyor — RSS okumasi bunlarin TOPLAMIDIR.\n"
            "     Sizinti olcumu icin TEK instance birakin, yoksa sayi yaniltir."
        )
    return n


def _rss_oturmasini_bekle(azami_sn: float = 180.0, kararli_tur: int = 3) -> float:
    """AI ısıtması bitene kadar bekle; oturmuş RSS'i döndür.

    ⚠️ BU BEKLEME OLMADAN KAPI YANLIŞ ALARM VERİR. Ölçüldü (2026-09-13):
    backend `/api/health` 200 döndüğünde RSS **254 MB**; arka plandaki AI ısıtması
    ~15 sn içinde onu **2310 MB**'a çıkarıyor ve orada SABİTLİYOR. Soak sağlık
    kontrolünden hemen sonra taban alırsa 254 → 2310 = **%809 artış** görür ve
    "SIZINTI SUPHESI" der — oysa hiçbir şey sızmamıştır.

    Ölçüt: ardışık `kararli_tur` örnekte değişim %1'in altındaysa oturmuştur.
    """
    onceki = _backend_rss_mb()
    kararli = 0
    bitis = time.monotonic() + azami_sn
    while time.monotonic() < bitis:
        time.sleep(5)
        simdi = _backend_rss_mb()
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
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from utils.path_utils import get_app_data_directory

        adaylar.append(Path(get_app_data_directory()))
    except Exception:
        pass

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
    ap.add_argument("--port", type=int, default=8000)
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

    veri_koku = _veri_koku()

    # ⚠️ ISINMAYI BEKLE (bkz. _rss_oturmasini_bekle). Taban, AI ısıtması bittikten SONRA
    # alınmalı; yoksa ısıtmanın kendisi "sızıntı" diye raporlanır.
    _surec_sayisi_uyar()
    print("  AI isitmasinin oturmasi bekleniyor (taban olcumu icin)...")
    oturmus = _rss_oturmasini_bekle()
    print(f"  taban RSS oturdu: {oturmus} MB")

    bitis = time.monotonic() + a.dakika * 60
    ornekler: list[tuple[float, float, int, int]] = []
    tur = 0
    hata = 0
    basla = time.monotonic()

    print(f"soak basladi: {taban}  sure={a.dakika} dk  aralik={a.aralik} sn")
    print(f"  veri koku: {veri_koku}")
    print(f"{'dk':>6} {'RSS(MB)':>9} {'DB(KB)':>8} {'tur':>7} {'hata':>6}")

    sonraki_ornek = 0.0
    while time.monotonic() < bitis:
        for yol in UCLAR:
            kod, _ = _istek(taban, yol)
            tur += 1
            if kod not in KABUL:
                hata += 1
        gecen = time.monotonic() - basla
        if gecen >= sonraki_ornek:
            rss, db = _backend_rss_mb(), _db_kb(veri_koku)
            ornekler.append((gecen / 60.0, rss, db, hata))
            print(f"{gecen / 60:6.1f} {rss:9.1f} {db:8d} {tur:7d} {hata:6d}")
            sonraki_ornek = gecen + a.aralik
        time.sleep(0.25)

    if len(ornekler) < 2:
        print("\nSONUC: ornek sayisi yetersiz — daha uzun kosturun.")
        return 0

    ilk_rss, son_rss = ornekler[0][1], ornekler[-1][1]
    ilk_db, son_db = ornekler[0][2], ornekler[-1][2]
    artis = son_rss - ilk_rss
    oran = (artis / ilk_rss * 100) if ilk_rss else 0.0

    print("\n=== OZET ===")
    print(f"  istek: {tur}  hata: {hata}")
    print(f"  RSS: {ilk_rss} -> {son_rss} MB  (fark {artis:+.1f} MB, %{oran:+.1f})")
    print(f"  DB : {ilk_db} -> {son_db} KB  (fark {son_db - ilk_db:+d} KB)")

    # ⚠️ ESIK GEREKCESI: kisa soak'ta birkac MB dalgalanma NORMALDIR (GC, arena, onbellek).
    # Sizinti isareti MONOTON ve ORANSAL artistir. %25 esigi, 20 dk'lik bir kosuda
    # gurultuyu eleyip gercek bir sizintiyi yakalayacak kadar genis; daha dar bir esik
    # yanlis alarm uretir ve kapi guvenilmez olur.
    if ilk_rss and oran > 25.0:
        print("\n  ⚠️ RSS %25'ten fazla artti -> SIZINTI SUPHESI. Daha uzun kosturup dogrulayin.")
        return 1
    if hata:
        print(f"\n  ⚠️ {hata} istek basarisiz -> WS/HTTP kararliligi supheli.")
        return 1
    print("\nSONUC: TEMIZ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
