# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""İG-9.48 KARA KUTU KAPISI — build AI kapısı ve ürün senaryoları EXE'yi açarken ÜRÜN gerçek sisteme dokunmaz.

ARIZA SINIFI (İG-9.48 · D0Ö.03 / D0Ö.06 / D0Ö.09): `scripts/build_backend_exe.ps1` AI hazırlık kapısı ve
`scripts/urun_senaryolari.py` `kostur` derlenen EXE'yi build / geliştirici makinesinde açar. Eskiden yalnız `PEMF_SIMULATE=1`
veriliyordu: EXE takılı STM'e (COM10) bağlanıyor, oto-firmware açık kalıyor, canlı Supabase'e `upsert_device` yazıyordu.
Bugün iki betik yalıtım ortamı verir; mevcut kapılar (`test_exe_kapisi_firmware_kapali`, `test_build_kapisi_yalitimi`) yalnız
DEĞİŞKENLERİN DEĞERİNE bakar — ürünün o değişkenleri GERÇEKTEN onurlandırıp onurlandırmadığını ölçmez.

BU KAPI (planın FARKLI yöntemi, EXE derlenmeden): betiğin EXE'ye vereceği ortam + argümanlar GERÇEK betik kodundan alınır
(build: PowerShell ayrıştırıcısıyla çıkarılan kapı bloğu, `Start-Process` gölgeli; senaryo: `kostur`, `Popen` sahte) ve
`backend_service.main()` AYNI ortam/argümanlarla AYRI SÜREÇTE açılır (`exe_kara_kutu_cocugu.py`; uvicorn dinlemez, port YOK).
Çocukta her dokunma ENGELLENİR ve SAYILIR: gerçek COM portu, loopback dışı ağ / DNS, sahip portları, LAN dinleyici, alt süreç,
izinli kök dışına disk yazımı, dış ortamın "gerçek" kökleri, kayıt defteri, gerçek kimlik kasası.

DIŞ ORTAM TERSİNE KURULUR (hafıza "dış koşucu maskeler"): betiklerin ÇAĞRILDIĞI ortam yalıtımsız ve düşmancadır — COM10, oto-FW
açık, gerçek bir Supabase adresi, ESP/hotspot açık, null kasa YOK, APPDATA / LOCALAPPDATA / PROGRAMDATA / USERPROFILE "gerçek"
kök nöbetçilerinde. Yalıtım betiğin KENDİSİNDEN gelmezse kapı KIRMIZI olur.

POZİTİF DENETİM (kapı kör değil): (1) aynı ölçüm, yalıtım anahtarları SİLİNMİŞ senaryo ortamında COM + DNS + kasa + gerçek kök
denemesini GÖRÜR; (2) yalıtılmış koşuda STM bağlantısı GERÇEKTEN denenir (seri port adı kaydı) ve bulut kaydı GERÇEKTEN kara
deliğe (127.0.0.1:9) gider — "deneme yok" sonucu "o kod hiç koşmadı"dan ayırt edilir.

MUTASYON (betiklerde): `PEMF_STM_PORT` / `SUPABASE_URL` / `PROGRAMDATA` / `PYTHON_KEYRING_BACKEND` satırını silmek → KIRMIZI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from exe_kapisi_surucusu import PWSH, YALITIM_DEGISKENLERI, AltSurecVekili, kapi_blogunu_kostur, urun_senaryolari_modulu

KOK = Path(__file__).resolve().parents[1]
COCUK = KOK / "tests" / "exe_kara_kutu_cocugu.py"
#: Açılış tamamlandıktan sonra arka planın (HWSender, bulut senkronu, ısıtma) yaşadığı süre.
SURE_SN = 12
#: Sahibin servis portları — çocuk bunlara ne bağlanır ne bind eder (alt_surec_ag_bekcisi ile aynı küme, burada PİNLİ).
SAHIP_PORTLARI = frozenset({8000, 8100, 1883, 5173, 8177, 8200})
_GERCEK_KOKLER = ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE")
_COM = re.compile(r"^(\\\\\.\\)?COM\d+$", re.IGNORECASE)


def _dusmanca_dis_ortam(tmp: Path) -> tuple[dict, list[str]]:
    """Betiklerin ÇAĞRILDIĞI ortam: yalıtımsız ve düşmanca (yalıtım betikten gelmeli)."""
    ortam = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PEMF_", "SUPABASE_"))}
    for ad in YALITIM_DEGISKENLERI:
        ortam.pop(ad, None)
    ortam.pop("PYTHON_KEYRING_BACKEND", None)  # build makinesinde null kasa YOK → ürün gerçek kasaya giderdi
    ortam.pop("PYTEST_ADDOPTS", None)
    nobetciler = []
    for ad in _GERCEK_KOKLER:
        yol = tmp / f"GERCEK_{ad}"
        yol.mkdir(parents=True, exist_ok=True)
        ortam[ad] = str(yol)
        nobetciler.append(str(yol))
    ortam["HOME"] = ortam["USERPROFILE"]
    ortam.update(
        {
            "PEMF_STM_PORT": "COM10",
            "PEMF_FW_AUTO_UPDATE": "1",
            "SUPABASE_URL": "https://dis-ortam-gercek.supabase.co",
            "PEMF_ESP_ENABLED": "1",
            "PEMF_HOTSPOT": "1",
        }
    )
    return ortam, nobetciler


def _build_ortami(tmp: Path) -> tuple[dict, list[str], list[str]]:
    """Build AI kapısı bloğunun EXE'ye vereceği (ortam, argümanlar) — GERÇEK blok, düşmanca dış ortamla."""
    dis, nobetciler = _dusmanca_dis_ortam(tmp)
    veri = kapi_blogunu_kostur(tmp, dis)
    yakalanan = veri.get("yakalanan")
    assert yakalanan, f"build kapı bloğu EXE'yi başlatmadı: {veri.get('hata')}"
    return dict(yakalanan["Env"]), [str(a) for a in yakalanan["ArgumentList"]], nobetciler


def _urun_ortami(tmp: Path, monkeypatch) -> tuple[dict, list[str], list[str]]:
    """`urun_senaryolari.kostur`un EXE'ye vereceği (ortam, argümanlar) — Popen SAHTE, düşmanca dış ortamla."""
    dis, nobetciler = _dusmanca_dis_ortam(tmp)
    for ad in list(os.environ):
        if ad not in dis:
            monkeypatch.delenv(ad, raising=False)
    for ad, deger in dis.items():
        monkeypatch.setenv(ad, deger)
    us = urun_senaryolari_modulu()
    yakalanan = {}

    class _SahteSurec:
        def __init__(self, argv, env=None, **kw):
            yakalanan["argv"] = [str(a) for a in argv]
            yakalanan["env"] = dict(env or {})

        def poll(self):
            return 0

    monkeypatch.setattr(us, "subprocess", AltSurecVekili(Popen=_SahteSurec))
    calisma = tmp / "calisma"
    calisma.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(us, "CALISMA", calisma)
    us.kostur(tmp / "veri", sifreli=False, sure=1, saglik_bekle=False)
    monkeypatch.undo()  # pytest sürecinin ortamı HEMEN geri gelsin (çocuk ortamı yakalandı)
    assert "env" in yakalanan, "kostur EXE'yi Popen ile başlatmadı (çıpa kaymış)"
    return yakalanan["env"], yakalanan["argv"][1:], nobetciler


def _cocugu_baslat(tmp: Path, ortam: dict, argv: list[str], nobetciler: list[str]):
    tmp.mkdir(parents=True, exist_ok=True)
    cikti = tmp / "kara_kutu.json"
    gunluk = (tmp / "kara_kutu_cikti.txt").open("w", encoding="utf-8", errors="replace")
    komut = [sys.executable, str(COCUK), str(cikti), str(SURE_SN), "--izinli", str(tmp)]
    for n in nobetciler:
        komut += ["--gercek", n]
    ortam = {**ortam, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.Popen(
        komut + ["--", *argv],
        env=ortam,
        cwd=str(tmp),
        stdout=gunluk,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return p, cikti, gunluk


def _bitir(p, cikti: Path, gunluk) -> dict:
    try:
        p.wait(timeout=SURE_SN + 240)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=30)
    gunluk.close()
    metin = Path(gunluk.name).read_text(encoding="utf-8", errors="replace")
    assert cikti.is_file(), f"kara kutu çocuğu sonuç yazmadı (rc={p.returncode}):\n{metin[-3000:]}"
    veri = json.loads(cikti.read_text(encoding="utf-8"))
    assert veri["durum"] == "TAMAM", (
        f"kara kutu açılışı tamamlanmadı ({veri['durum']}): {veri['iz'][-3:]}\n{metin[-2000:]}"
    )
    return veri


def _siniflandir(veri: dict) -> dict[str, list[str]]:
    s: dict[str, list[str]] = {
        k: []
        for k in (
            "com",
            "dis_ag",
            "sahip_portu",
            "kara_delik",
            "loopback_diger",
            "lan_bind",
            "surec",
            "surec_dis",
            "udp_rota",
            "disk_disi",
            "gercek_kok",
            "gercek_okuma",
            "kayit_defteri",
            "kasa",
        )
    }
    for port in veri["seri"]:
        if _COM.match(port.strip()):
            s["com"].append(port)
    for tur, adres, port in veri["ag_engellenen"]:
        if "dns" in tur or "gethostby" in tur or "getnameinfo" in tur:
            s["dis_ag"].append(f"{tur} {adres}")
        elif adres in ("127.0.0.1", "::1", "localhost"):
            if port in SAHIP_PORTLARI:
                s["sahip_portu"].append(f"{tur} {adres}:{port}")
            elif port == 9:
                s["kara_delik"].append(f"{tur} {adres}:{port}")
            else:
                s["loopback_diger"].append(f"{tur} {adres}:{port}")
        else:
            s["dis_ag"].append(f"{tur} {adres}:{port}")
    for tur, ayrinti in veri["kayit"]:
        s.setdefault(tur, []).append(ayrinti)
    s["seri_denemesi"] = list(veri["seri"])
    return s


#: Yalıtılmış koşuda SIFIR olması gereken dokunma sınıfları.
YASAK_SINIFLAR = (
    "com",
    "dis_ag",
    "sahip_portu",
    "loopback_diger",
    "lan_bind",
    "surec_dis",
    "disk_disi",
    "gercek_kok",
    "gercek_okuma",
    "kayit_defteri",
    "kasa",
)


def _rapor(ad: str, s: dict) -> str:
    return f"{ad}: " + "; ".join(f"{k}={v[:4]}" for k, v in s.items() if v)


def test_KRITIK_iki_betigin_EXE_ortami_URUNDE_gercek_sisteme_dokunmaz_ve_olcum_kor_degil(tmp_path, monkeypatch):
    kollar = {}
    kollar["urun_senaryolari"] = _urun_ortami(tmp_path / "u_ortam", monkeypatch)
    if PWSH:  # build betiği pwsh ile koşar; yoksa (Linux CI) yalnız ürün senaryoları ortamı sınanır
        kollar["build AI kapısı"] = _build_ortami(tmp_path / "b_ortam")
    # KARŞIT (pozitif denetim): senaryo ortamından yalıtım anahtarları SİLİNİR, makine kökü "gerçek" nöbetçiye döner.
    u_env, u_argv, u_nob = kollar["urun_senaryolari"]
    karsit = {
        k: v for k, v in u_env.items() if k.upper() not in ("PEMF_STM_PORT", "SUPABASE_URL", "PYTHON_KEYRING_BACKEND")
    }
    karsit["PROGRAMDATA"] = [n for n in u_nob if n.endswith("GERCEK_PROGRAMDATA")][0]
    karsit.pop("PEMF_DEVICE_IDENTITY_DIR", None)
    kollar["KARSIT (yalitimsiz)"] = (karsit, u_argv, u_nob)

    calisan = {ad: _cocugu_baslat(tmp_path / f"cocuk_{i}", *kol) for i, (ad, kol) in enumerate(kollar.items())}
    sonuc = {ad: _siniflandir(_bitir(*c)) for ad, c in calisan.items()}

    ks = sonuc.pop("KARSIT (yalitimsiz)")
    for sinif in ("com", "dis_ag", "kasa", "gercek_kok"):
        assert ks[sinif], f"ÖLÇÜM KÖR: yalıtımsız ortamda '{sinif}' denemesi GÖRÜLMEDİ — {_rapor('karşıt', ks)}"

    for ad, s in sonuc.items():
        assert s["seri_denemesi"], (
            f"{ad}: STM bağlantısı hiç denenmedi — 'COM denemesi yok' ölçümü kör ({_rapor(ad, s)})"
        )
        assert s["kara_delik"], (
            f"{ad}: bulut cihaz kaydı hiç denenmedi — 'bulut denemesi yok' ölçümü kör ({_rapor(ad, s)})"
        )
    ihlal = {
        ad: {f"{k} ({len(s[k])})": s[k][:4] for k in YASAK_SINIFLAR if s[k]}
        for ad, s in sonuc.items()
        if any(s[k] for k in YASAK_SINIFLAR)
    }
    assert not ihlal, f"betiğin verdiği ortamla açılan ÜRÜN gerçek sisteme DOKUNMAYA çalıştı (İG-9.48): {ihlal}"
