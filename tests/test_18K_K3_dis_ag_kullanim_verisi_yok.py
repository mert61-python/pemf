# -*- coding: utf-8 -*-
"""18K K3 · D3.13 — DIŞARIYA KULLANIM VERİSİ YOK: ürün süreçleri üçüncü taraf telemetri / güncelleme sorgusu göndermez.

Ölçüldü (ultralytics 8.4.47, albumentations 2.0.8): ultralytics İÇE AKTARILIRKEN `is_online()` → `one.one.one.one` / `dns.google`
DNS sorgusu; `ONLINE` doğruysa kendi Sentry'sini kurar ve her `predict` başında Google Analytics'e olay yollar (MAC türevli kimlik +
CPU / işletim sistemi). albumentations içe aktarılırken pypi.org'a sürüm sorar. Kilit: `runtime_guards.dis_ag_cagrilarini_kapat`
(`YOLO_OFFLINE=true` + `NO_ALBUMENTATIONS_UPDATE=1`) üç giriş noktasında (backend, AI mikroservisi, ai_hub) ultralytics'ten ÖNCE.

Kapı ayrı süreçte koşar: pytest'in kendi `PYTEST_CURRENT_TEST` / `pytest` modülü ultralytics'e "test" dedirtip telemetriyi zaten kapatır
(kör kapı) — çocukta ikisi de yok. Çocuk ilk iş `socket` adres çözme / bağlanma işlevlerini EN DIŞTAN sarar (kaydeder, loopback dışını
REDDEDER; kafes yüklüyse kafes de reddeder) ve C düzeyi için denetim kancası kurar; sonra GERÇEK giriş noktasını içe aktarır, albumentations
+ ultralytics yükler ve bir YOLO analizi koşturur. Sonda kendi bekçisini kanıtlar (`kafes-kanit.invalid` kaydedilmeli).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
GIRISLER = {
    "backend": KOK / "apps" / "backend" / "backend_service.py",
    "ai_service": KOK / "ai_service" / "app.py",
    "ai_hub": KOK / "ai_hub" / "__init__.py",
}

_COCUK = r'''
import ipaddress, json, os, socket, sys, time
KOK, CIKTI, GIRIS = sys.argv[1], sys.argv[2], sys.argv[3]
denemeler = []

def _loopback(h):
    if h is None:
        return True
    h = h.decode() if isinstance(h, bytes) else str(h)
    if h.lower() in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h.split("%")[0]).is_loopback
    except ValueError:
        return False

def _kaydet(tur, h):
    denemeler.append(f"{tur} {h}")
    raise OSError(f"18K-K3 bekcisi: dis ag YOK ({tur} {h})")

for _ad in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"):
    _eski = getattr(socket, _ad)
    def _sar(host, *a, _eski=_eski, _ad=_ad, **k):
        if not _loopback(host):
            _kaydet(_ad, host)
        return _eski(host, *a, **k)
    setattr(socket, _ad, _sar)
for _ad in ("connect", "connect_ex"):
    _eski = getattr(socket.socket, _ad)
    def _sar(self, adres, _eski=_eski, _ad=_ad):
        if isinstance(adres, tuple) and not _loopback(adres[0]):
            _kaydet(_ad, adres[0])
        return _eski(self, adres)
    setattr(socket.socket, _ad, _sar)

def _kanca(olay, arg):
    if olay == "socket.getaddrinfo" and not _loopback(arg[0]):
        if f"getaddrinfo {arg[0]}" not in denemeler:
            _kaydet("getaddrinfo", arg[0])
    elif olay == "socket.connect" and isinstance(arg[1], tuple) and not _loopback(arg[1][0]):
        if f"connect {arg[1][0]}" not in denemeler:
            _kaydet("connect", arg[1][0])
sys.addaudithook(_kanca)

sys.path[:0] = [os.path.join(KOK, "apps", "backend"), KOK, os.path.join(KOK, "ai_service")]
if GIRIS == "backend":
    import backend_service  # noqa: F401  GERÇEK giriş noktası — modül düzeyindeki kilitler burada koşar
elif GIRIS == "ai_service":
    import app  # noqa: F401
else:
    import ai_hub  # noqa: F401

import albumentations  # noqa: F401  (scratch ısıtma yolu)
import numpy as np
import ultralytics.utils as U
from ultralytics import YOLO

model = YOLO("yolov8n.yaml")  # paketin kendi yapılandırması — ağırlık / indirme yok
model.predict(np.zeros((64, 64, 3), dtype=np.uint8), device="cpu", verbose=False)
from ultralytics.utils.events import events
time.sleep(1.5)  # olay gönderimi ayrı iş parçacığında
urun = list(denemeler)
try:
    socket.getaddrinfo("kafes-kanit.invalid", 80)
except OSError:
    pass
json.dump({"denemeler": urun, "bekci": denemeler[len(urun):], "online": U.ONLINE, "olay": events.enabled,
           "offline": os.environ.get("YOLO_OFFLINE"), "alb": os.environ.get("NO_ALBUMENTATIONS_UPDATE")}, open(CIKTI, "w"))
'''


def _kos(giris: str, tmp_path: Path) -> dict:
    # Varlık İÇE AKTARMADAN sorulur: ebeveynde `import ultralytics` bayraklarını (AUTOINSTALL) erken dondurup sonraki kapıları
    # sıraya bağlar ve ebeveynde DNS dener (ölçüldü: test_calisma_ani_pip_yasagi kırmızısı).
    for paket in ("ultralytics", "albumentations"):
        if importlib.util.find_spec(paket) is None:
            pytest.skip(f"{paket} kurulu değil")
    betik, cikti = tmp_path / f"k3_{giris}.py", tmp_path / f"k3_{giris}.json"
    betik.write_text(_COCUK, encoding="utf-8")
    ortam = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTEST_CURRENT_TEST", "GITHUB_ACTIONS", "GITHUB_WORKFLOW", "RUNNER_OS", "CI")
        and k
        not in ("YOLO_OFFLINE", "NO_ALBUMENTATIONS_UPDATE", "YOLO_AUTOINSTALL", "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS")
    }
    ortam["YOLO_CONFIG_DIR"] = str(tmp_path / "ultralytics_ayar")  # taze ayar dosyası: `sync` VARSAYILAN (açık)
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(betik), str(KOK), str(cikti), giris],
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        cwd=str(tmp_path),
    )
    assert r.returncode == 0 and cikti.exists(), (
        f"çocuk süreç düştü (rc={r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-3000:]}"
    )
    return json.loads(cikti.read_text(encoding="utf-8"))


@pytest.mark.parametrize("giris", sorted(GIRISLER))
def test_KRITIK_18K_K3_AI_ice_aktarma_ve_analiz_boyunca_DIS_AG_DNS_denemesi_YOK(giris, tmp_path):
    s = _kos(giris, tmp_path)
    print(f"K3OLC|{giris}|{s}")
    assert s["bekci"] == ["getaddrinfo kafes-kanit.invalid"], f"bekçi kendi sondasını görmedi — kapı KÖR: {s}"
    assert s["denemeler"] == [], f"{giris}: AI içe aktarma / analiz DIŞARIYA bağlanmayı denedi: {s['denemeler']}"
    assert s["online"] is False and s["olay"] is False, f"{giris}: ultralytics çevrimiçi / analitik AÇIK: {s}"


def test_18K_K3_kilit_ultralytics_ve_albumentationsi_TANINAN_degerle_kapatir(monkeypatch):
    """ultralytics YALNIZ "true" dizgesini tanır (`str(os.getenv("YOLO_OFFLINE","")).lower() == "true"`); albumentations "1" / "true"."""
    from utils.runtime_guards import dis_ag_cagrilarini_kapat

    monkeypatch.setenv("YOLO_OFFLINE", "false")
    monkeypatch.setenv("NO_ALBUMENTATIONS_UPDATE", "0")
    dis_ag_cagrilarini_kapat()
    assert os.environ["YOLO_OFFLINE"] == "true" and os.environ["NO_ALBUMENTATIONS_UPDATE"] == "1"


@pytest.mark.parametrize("giris", sorted(GIRISLER))
def test_18K_K3_giris_noktasi_kilidi_AI_zincirinden_ONCE_cagirir(giris):
    """Sıra kilidi: bayraklar içe aktarma ANINDA okunur — kilit, AI zincirini çeken ilk import'tan önce."""
    metin = GIRISLER[giris].read_text(encoding="utf-8")
    cagri = re.search(r"^\s*_dis_ag_kapat\(\)\s*$", metin, re.M)
    assert cagri, f"{giris}: dis_ag_cagrilarini_kapat çağrısı YOK"
    zincir = re.search(r"^(?:import (?:uvicorn|onnxruntime|numpy)|from (?:headless_core|ultralytics))\b", metin, re.M)
    if zincir:
        assert cagri.start() < zincir.start(), f"{giris}: kilit '{zincir.group(0)}' importundan SONRA"
