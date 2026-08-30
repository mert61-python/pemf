# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BULUT ENVANTERİ `-dev` ETİKETİ — saha bulgusu 2026-08-29/30.

`devices` tablosunda 26 satır birikmişti ve yalnız BİRİ gerçek cihazdı; gerisi aynı makinenin
farklı ortamlarıydı (`dist/`, `PEMF_BUILD/`, geçici kopyalar, Docker — IP'lerden ölçüldü:
192.168.1.34-48, 172.18.0.x, hotspot). Sebep: `device_id` `uuid.getnode()`ten türer, yani her
veri kökü kendi kimliğini üretir ve ÜRETİM tablosuna yazar; bulut yazımını sınırlayan hiçbir
koruma yoktu. Bir teşhis turu bile yeni satır oluşturdu (`211929771043172`).

Sonuç: filo envanterinin TEK var oluş sebebi olan "hangi klinik hangi sürümde?" sorusu
(geri çağırma) okunamaz hâle geliyordu.

⚠️ ENGELLEME DEĞİL ETİKETLEME — SAHİP KARARI (2026-08-30). "Kurulu değilse yazma" daha temiz
görünür ama SESSİZ ARIZA üretir: kurulum yolu beklenenden farklı bir klinikte cihaz bulut
kaydını hiç oluşturmaz ve uzaktan erişim kimse fark etmeden ölür. Etiketleme bu riski taşımaz;
kayıt her koşulda yazılır.

Bu dosya iki şeyi birlikte kilitler:
  1. Üretim (launcher'ın başlattığı) kurulum ETİKETLENMEZ.
  2. Launcher'sız koşum ETİKETLENİR — ama kaydı YİNE oluşturur.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_SYNC = _KOK / "servers" / "sync_worker.py"


@pytest.fixture(autouse=True)
def _ortam_temiz(monkeypatch):
    """Testler ortamdan sızan gerçek değerlerle YANLIŞ NEDENLE yeşil olmasın."""
    monkeypatch.delenv("PEMF_LAUNCHER_VERSION", raising=False)
    monkeypatch.delenv("PEMF_DEVICE_NAME", raising=False)


def _ad() -> str:
    from servers.sync_worker import _cihaz_adi

    return _cihaz_adi()


# ── Davranış ────────────────────────────────────────────────────────────────


def test_KRITIK_launcher_YOKSA_dev_etiketlenir(monkeypatch):
    """Launcher'sız koşum = geliştirme/test ortamı → envanterde ayırt edilebilmeli."""
    assert _ad().endswith("-dev"), "launcher'sız koşum üretim cihazıymış gibi kaydoluyor → envanter yine kirlenir"


def test_KRITIK_launcher_VARSA_etiketlenmez(monkeypatch):
    """⚠️ ASIL RİSK BURADA: gerçek klinik cihazı '-dev' görünürse destek yanlış eler."""
    monkeypatch.setenv("PEMF_LAUNCHER_VERSION", "1.9.42")
    ad = _ad()
    assert not ad.endswith("-dev"), "üretim kurulumu yanlışlıkla '-dev' etiketlendi"
    assert ad == "PEMF-Vet"


def test_KARSIT_KANIT_etiket_kaydi_ENGELLEMEZ(monkeypatch):
    """⚠️ SAHİP KARARININ KİLİDİ: etiketleme bir ENGEL değildir.

    Bu kapı, düzeltmeyi "dev ise hiç yazma"ya çeviren bir refaktörü yakalar — o refaktör
    sessiz arıza sınıfını geri getirirdi (kurulum yolu farklı klinikte uzaktan erişim ölür)."""
    ad = _ad()
    assert ad, "cihaz adı boş döndü → kayıt yazılamaz, bu bir ENGELLEME davranışıdır"
    assert ad.startswith("PEMF-Vet"), "ad tanınmaz hâle geldi"

    kaynak = _SYNC.read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    for d in ast.walk(agac):
        if isinstance(d, ast.FunctionDef) and d.name == "_cihaz_adi":
            govde = ast.get_source_segment(kaynak, d) or ""
            assert "return None" not in govde, "ad None dönebiliyor → kayıt engellenir"
            break
    else:
        raise AssertionError("_cihaz_adi bulunamadı")


def test_ozel_ad_KORUNUR(monkeypatch):
    """`PEMF_DEVICE_NAME` operatör ayarıdır; etiket onu EZMEMELİ, yalnız ekleme yapmalı."""
    monkeypatch.setenv("PEMF_DEVICE_NAME", "PEMF-Klinik-07")
    assert _ad() == "PEMF-Klinik-07-dev"
    monkeypatch.setenv("PEMF_LAUNCHER_VERSION", "1.9.42")
    assert _ad() == "PEMF-Klinik-07"


def test_etiket_IKI_KEZ_eklenmez(monkeypatch):
    """Ad zaten '-dev' ile bitiyorsa 'PEMF-Vet-dev-dev' üretilmemeli."""
    monkeypatch.setenv("PEMF_DEVICE_NAME", "PEMF-Vet-dev")
    assert _ad() == "PEMF-Vet-dev"


# ── Bağlantı: heartbeat gerçekten bu adı kullanıyor mu ──────────────────────


def test_KRITIK_heartbeat_ETIKETLI_adi_KULLANIYOR():
    """⚠️ ZAYIF-ÇIPA KORUMASI: `_cihaz_adi` doğru çalışsa da heartbeat onu ÇAĞIRMIYORSA
    hiçbir şey değişmez (envanter yine kirlenir)."""
    kaynak = _SYNC.read_text(encoding="utf-8")
    assert '"name": _cihaz_adi()' in kaynak, "heartbeat payload'ı `_cihaz_adi()` kullanmıyor → etiket sahaya HİÇ çıkmaz"
    assert 'os.environ.get("PEMF_DEVICE_NAME", "PEMF-Vet")' not in kaynak.replace(
        '_os.environ.get("PEMF_DEVICE_NAME", "PEMF-Vet")', ""
    ), "payload hâlâ ortam değişkenini DOĞRUDAN okuyor (etiket atlanır)"
