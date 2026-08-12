# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF-Gateway HOTSPOT'U BACKEND AÇAR (2026-08-10, sahip kararı).

ARIZA: hotspot'u kuran tek yol `setup_services.ps1 -Mode device`in kaydettiği logon-task'tı.
Ama SİTEDEN İNDİRİP KURAN yol — PEMF Vet Client — `setup_services.ps1`i **hiç çalıştırmıyor**
(ölçüldü: launcher kaynağında ne `setup_services` ne `schtasks` geçiyor). Sonuç: launcher ile
kuran HER kullanıcıda `PEMF-Gateway` WiFi'si hiç oluşmuyor ve **8 bobinin 3'ü (ESP 6-8)
bağlanamıyor** — üstelik arayüzde bunun hiçbir göstergesi yoktu.

ÇÖZÜM: backend açılışta hotspot'u kendisi başlatır. Windows Mobile Hotspot API'si kullanıcı
oturumu ister; launcher backend'i KENDİ oturumunda çocuk süreç olarak başlattığı için bu
mümkündür. Servis kurulumunda (session 0) yol kendini devre dışı bırakır — logon-task orada
zaten işi yapıyor, iki başlatıcı çakışmasın.

Kilitlenen değişmezler:
  1) Açılışta ÇAĞRILIR (unutulursa hotspot yine hiç açılmaz).
  2) Açılışı BLOKLAMAZ (ayrı thread) ve hata hâlinde servisi DÜŞÜRMEZ — hotspot yoksa STM
     bobinleri (1-5) ve tüm arayüz çalışmaya devam etmeli.
  3) SSID/parola BURADA parametre olarak geçilmez: tek kaynak `start_hotspot.ps1`tir (ESP
     firmware'i değerleri kendi içinde taşır, değiştirilemez).
  4) Arayüzde "Kablosuz Bağlantı" satırı vardır (aksi hâlde arıza yine görünmez).
"""

import os
from pathlib import Path

os.environ.pop("PEMF_SIMULATE", None)

import sys

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))  # `tests` paket değil (conftest tabanlı toplama)
import capraz  # noqa: E402  — kardeş-depo kaynakları için atlama yardımcısı

# ⚠️ HOTSPOT WINDOWS'A ÖZGÜDÜR (2026-08-12). `_start_hotspot_safe` daha ikinci koşulda
# `if os.name != "nt": return` ile ERKEN DÖNER (backend_service.py:545) — Mobile Hotspot API
# ve `powershell.exe` yalnız orada vardır. Linux'ta o satırdan SONRAKİ hiçbir davranış oluşmaz.
#
# Bu, CI'da iki ayrı biçimde sorun çıkarıyordu:
#   • `test_KRITIK_acilisi_BLOKLAMAZ` "arka plan thread'i başlatıldı" diyordu → Linux'ta hiç
#     başlatılmaz, test DÜŞÜYORDU (uvicorn düzeltilene kadar bu gizliydi: setup hatası veriyordu).
#   • `..._betik_yoksa_ACILIS_DUSMEZ` ve `..._servis_oturumunda_ATLANIR` ise Linux'ta BOŞUNA
#     GEÇİYORDU: iddia ettikleri dallara hiç girilmediği için "istisna atmadı" / "betik
#     çağrılmadı" kendiliğinden doğruydu. Yanlış yeşil, kırmızıdan daha tehlikelidir —
#     kapının çalıştığı sanılır. İşaretlenerek atlanması dürüst olanı.
# `PEMF_HOTSPOT=0` bayrağı `os.name` kontrolünden ÖNCE okunduğu için o test her platformda
# gerçekten koşar ve işaretlenmemiştir.
SADECE_WINDOWS = pytest.mark.skipif(
    os.name != "nt",
    reason="hotspot yalnız Windows'ta çalışır (_start_hotspot_safe `os.name != 'nt'` ile erken döner)",
)


@pytest.fixture(scope="module")
def bs():
    import backend_service

    return backend_service


# ── açılışta çağrılıyor mu ──────────────────────────────────────────────────


def test_KRITIK_acilista_CAGRILIYOR(bs):
    import inspect

    src = inspect.getsource(bs)
    assert "_start_hotspot_safe(logger)" in src, (
        "hotspot baslatici acilis akisinda CAGRILMIYOR — launcher kurulumunda PEMF-Gateway "
        "hic acilmaz ve ESP bobinleri (6-8) baglanamaz"
    )


@SADECE_WINDOWS
def test_KRITIK_acilisi_BLOKLAMAZ(bs, monkeypatch, caplog):
    """PowerShell çağrısı saniyeler sürebilir; `main()` bunu beklerse backend geç açılır."""
    import threading as _t

    baslatilan = {}

    class _SahteThread:
        def __init__(self, target=None, name=None, daemon=None, **kw):
            baslatilan["target"] = target
            baslatilan["daemon"] = daemon
            baslatilan["name"] = name

        def start(self):
            baslatilan["start"] = True

    monkeypatch.setattr(_t, "Thread", _SahteThread)
    monkeypatch.setattr(bs, "_oturum_var_mi", lambda: True)
    monkeypatch.setattr(bs, "_hotspot_betigi", lambda: KOK / "scripts" / "start_hotspot.ps1")
    monkeypatch.delenv("PEMF_HOTSPOT", raising=False)

    import logging

    bs._start_hotspot_safe(logging.getLogger("t"))
    assert baslatilan.get("start"), "hotspot ARKA PLANDA baslatilmadi (acilis bloklanir)"
    assert baslatilan.get("daemon") is True, "thread daemon degil — kapanisi geciktirir"


# ── fail-safe ───────────────────────────────────────────────────────────────


@SADECE_WINDOWS
def test_KRITIK_betik_yoksa_ACILIS_DUSMEZ(bs, monkeypatch):
    monkeypatch.setattr(bs, "_oturum_var_mi", lambda: True)
    monkeypatch.setattr(bs, "_hotspot_betigi", lambda: None)
    import logging

    bs._start_hotspot_safe(logging.getLogger("t"))  # istisna ATMAMALI


@SADECE_WINDOWS
def test_KRITIK_servis_oturumunda_ATLANIR(bs, monkeypatch):
    """Session 0'da Mobile Hotspot API çalışmaz; ayrıca logon-task zaten var → çakışmasın."""
    cagrildi = {}
    monkeypatch.setattr(bs, "_oturum_var_mi", lambda: False)
    monkeypatch.setattr(bs, "_hotspot_betigi", lambda: cagrildi.setdefault("betik", True))
    import logging

    bs._start_hotspot_safe(logging.getLogger("t"))
    assert "betik" not in cagrildi, "servis oturumunda hotspot baslatilmaya calisildi"


def test_bayrakla_KAPATILABILIR(bs, monkeypatch):
    cagrildi = {}
    monkeypatch.setenv("PEMF_HOTSPOT", "0")
    monkeypatch.setattr(bs, "_oturum_var_mi", lambda: cagrildi.setdefault("oturum", True))
    import logging

    bs._start_hotspot_safe(logging.getLogger("t"))
    assert "oturum" not in cagrildi, "PEMF_HOTSPOT=0 iken bile baslatma yoluna girildi"


# ── SSID/parola tek kaynak ──────────────────────────────────────────────────


def test_KRITIK_SSID_parola_BACKENDDE_GECILMEZ(bs):
    """ESP firmware'i SSID/parolayı kendi içinde taşır → tek kaynak `start_hotspot.ps1`.
    Backend'in parametre geçmesi ikinci bir gerçek üretir ve sahadaki ESP'ler bağlanamaz.

    ⚠️ İlk yazımda ham kaynak metninde arama yapılıyordu ve fonksiyonun KENDİ DOCSTRING'indeki
    "PEMF-Gateway" kelimesine takıldı. Kaynak-metin iddiası kodu belgeden ayırt etmeli: burada
    AST ile yalnız GERÇEK dize sabitlerine bakılıyor.
    """
    import ast
    import inspect

    agac = ast.parse(inspect.getsource(bs._start_hotspot_safe).lstrip())

    # ⚠️ Yalnız KOMUT SATIRINA bak. İlk iki denemede (a) docstring'e, sonra (b) LOG METİNLERİNE
    # takıldı ("PEMF-Gateway açılmayacak…"). İkisi de kimlik geçirme DEĞİL. Değişmez şudur:
    # `subprocess.run`a verilen argüman listesinde SSID/parola geçmemeli.
    komutlar: list[str] = []
    for n in ast.walk(agac):
        if not isinstance(n, ast.Call):
            continue
        ad = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        if ad != "run" or not n.args:
            continue
        arg0 = n.args[0]
        if isinstance(arg0, (ast.List, ast.Tuple)):
            komutlar += [e.value for e in arg0.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    assert komutlar, "subprocess.run komut listesi bulunamadi — test neyi olctugunu bilmiyor"
    assert any("start_hotspot" in k or "-File" in k for k in komutlar), (
        f"komut hotspot betigini calistirmiyor: {komutlar}"
    )

    for yasak in ("-Ssid", "-Pass", "PEMF-Gateway", "pemf1234"):
        eslesen = [k for k in komutlar if yasak in k]
        assert not eslesen, (
            f"backend hotspot kimligini KOMUTA gecirmis ({yasak} -> {eslesen}) — tek kaynak "
            "`start_hotspot.ps1` bozulur, sahadaki ESP'ler baglanamaz"
        )


def test_betik_paketle_BIRLIKTE_gidiyor():
    """`start_hotspot.ps1` app katmanında olmalı; yoksa frozen kurulumda bulunamaz."""
    mbz = (KOK / "build_tools" / "make_base_zip.py").read_text(encoding="utf-8")
    assert "start_hotspot.ps1" in mbz, "betik pakete girmiyor → kurulumda bulunamaz"


def test_betik_SSID_i_hala_tasiyor():
    p = KOK / "scripts" / "start_hotspot.ps1"
    s = p.read_text(encoding="utf-8", errors="replace")
    assert "PEMF-Gateway" in s, "SSID kaynaktan kaybolmus"


# ── arayüz göstergesi ───────────────────────────────────────────────────────


def test_KRITIK_arayuzde_KABLOSUZ_BAGLANTI_satiri_VAR():
    """Hotspot kapalıyken 6-8 bobinleri sessizce bağlanamıyordu; `hotspotActive` çekiliyor ama
    HİÇ GÖSTERİLMİYORDU. Arıza görünür olmalı."""
    # ⚠️ `pf/` (Expo mobil) AYRI projedir ve bu depoda izlenmez → CI'da dosya YOKTUR ve test
    # `FileNotFoundError` ile düşerdi (2026-08-12). Atlanır; `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`
    # ile atlama yasaklanabilir. Bu dosyanın hotspot davranış testleri depo içidir, koşar.
    s = capraz.oku("pf/src/components/domain/GatewayStatusPanel.tsx")
    assert "Kablosuz Bağlantı" in s, "durum panelinde 'Kablosuz Bağlantı' satiri YOK"
    assert "gwInfo.hotspotActive" in s, "satir hotspotActive'e BAGLI degil (olu gosterge)"
    # Bağlantı yokken bayat "Aktif" göstermemeli (panelin genel kuralı).
    kesit = s[s.index("Kablosuz Bağlantı") - 200 : s.index("Kablosuz Bağlantı") + 300]
    assert "stale" in kesit, "bayat-durum korumasi yok — WS kopukken yesil 'Aktif' donar"
