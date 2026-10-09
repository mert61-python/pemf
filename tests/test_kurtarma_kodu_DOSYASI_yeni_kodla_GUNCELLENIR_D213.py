# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.13 (B-3.39) — kurtarma kodu yeniden üretildiğinde `KURTARMA-KODU.txt` ve `/api/system/recovery-code` zarfla AYNI yeni kodu
gösterir; operatörün eski koda verdiği "makine dışına kaydettim" onayı yeni kodu ONAYLAMIŞ sayılmaz.

Kusur: `refresh_recovery_material` kod dosyasını yalnız YOKSA yazıyordu (`if not code_file.exists()`). Kod değişince (sır dosyası
sıfırlanıp `get_or_create_code` yenisini üretince) zarf YENİ kodla yeniden yazılıyor, cihazdaki `KURTARMA-KODU.txt` (ve onu
okuyan `/api/system/recovery-code`) ESKİ kodu göstermeye devam ediyordu. Operatör eski kodu kasaya koyarsa felaket günü zarf
açılmaz → şifreli yedekler açılmaz. Ayrıca onay koda bağlı değildi: eski kod için "Kaydettim" denmişse uyarı bandı yeni kod için
hiç geri gelmiyordu.

Kapı GERÇEK `refresh_recovery_material` + GERÇEK sır deposu (conftest'in yalıtılmış veri kökü, DPAPI) + GERÇEK uçlar. Kodlar
sentetiktir (test veri kökünde üretilir); gerçek `KURTARMA-KODU.txt` / zarf okunmaz.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def kurulum(tmp_path):
    from utils import backup_recovery as br
    from utils import secrets_manager as sm

    # Sentetik değer KISA tutulur: gitleaks "generic-api-key" kuralı anahtar adlı alana ≥10 karakterlik yüksek entropili değeri sır sayar.
    sm.set_secrets({"sqlcipher_key": "d213-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    veri = sm._data_dir()
    hedef = tmp_path / "yedek"
    hedef.mkdir()
    return br, sm, veri, hedef


def _kod_degistir(br, sm) -> tuple[str, str]:
    """Sır dosyası sıfırlanıp kodun yeniden üretilmesinin diskteki sonucu: sır deposunda YENİ kod."""
    eski = sm.get_secret("backup_recovery_code", generate=False)
    yeni = br.generate_recovery_code()
    assert yeni != eski
    sm.set_secret("backup_recovery_code", yeni)
    return eski, yeni


def test_KRITIK_kod_DEGISINCE_KURTARMA_KODU_txt_YENI_kodu_tasir_zarf_onunla_acilir_D213(kurulum):
    br, sm, veri, hedef = kurulum
    assert br.refresh_recovery_material(veri, [hedef]) is True, "ön koşul: ilk zarf ve kod dosyası yazılmalı"
    dosya = veri / br.CODE_FILE_NAME
    eski, yeni = _kod_degistir(br, sm)
    assert br.format_code(eski) in dosya.read_text(encoding="utf-8"), "ön koşul: dosya ilk kodu taşımalı"

    assert br.refresh_recovery_material(veri, [hedef]) is True
    metin = dosya.read_text(encoding="utf-8")
    assert br.open_envelope(yeni, (hedef / br.ENVELOPE_NAME).read_bytes()), "zarf YENİ kodla açılmalı"
    assert br.format_code(yeni) in metin, "KURTARMA-KODU.txt zarfın YENİ kodunu göstermiyor"
    assert br.format_code(eski) not in metin, "KURTARMA-KODU.txt ESKİ (artık zarfı AÇMAYAN) kodu gösteriyor"


def test_KRITIK_recovery_code_ucu_ZARFIN_kodunu_gosterir_D213(kurulum, monkeypatch):
    """`/api/system/recovery-code` (yalnız loopback) kod değişiminden sonraki ilk turda zarfı AÇAN kodu döndürmeli."""
    br, sm, veri, hedef = kurulum
    from servers import api_server

    monkeypatch.setattr(api_server, "_app_data_dir", lambda: veri)
    br.refresh_recovery_material(veri, [hedef])
    _eski, yeni = _kod_degistir(br, sm)
    br.refresh_recovery_material(veri, [hedef])
    r = TestClient(api_server.app, client=("127.0.0.1", 51234)).get("/api/system/recovery-code")
    assert r.status_code == 200, r.text
    assert br.format_code(yeni) in r.json()["content"], "uç zarfı açmayan (eski) kodu döndürüyor"


def test_KRITIK_ESKI_koda_verilen_onay_YENI_kodu_onaylamaz_uyari_GERI_gelir_D213(kurulum, monkeypatch):
    """Operatör eski kod için "Kaydettim" dedi; kod değişti → uyarı bandı (warn) YENİDEN istenmeli. Aksi hâlde operatör kasadaki
    eski kodla kalır ve bunu hiçbir yerden öğrenmez."""
    br, sm, veri, hedef = kurulum
    from servers import api_server

    monkeypatch.setattr(api_server, "_app_data_dir", lambda: veri)
    istemci = TestClient(api_server.app, client=("127.0.0.1", 51234))
    br.refresh_recovery_material(veri, [hedef])
    assert istemci.post("/api/system/recovery-ack", json={}).status_code == 200
    durum = istemci.get("/api/system/recovery-status").json()
    if not durum.get("atRestEncrypted"):
        pytest.skip("test DB'si şifreli açılamadı (sqlcipher3 yok?) — uyarı bandı kolu ölçülemez")
    assert durum["warn"] is False, f"ön koşul: onaydan sonra uyarı susmalı: {durum}"

    _kod_degistir(br, sm)
    br.refresh_recovery_material(veri, [hedef])
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["warn"] is True, f"kod DEĞİŞTİ ama eski koda verilen onay yeni kodu da onaylamış sayıldı: {durum}"


def test_KARSIT_kod_DEGISMEDIKCE_onay_SURER_ve_dosya_yeniden_YAZILMAZ_D213(kurulum, monkeypatch):
    """Karşıt: kod değişmedikçe onay geçerli kalır (alarm körlüğü yok) ve kod dosyası her turda yeniden yazılmaz."""
    br, sm, veri, hedef = kurulum
    from servers import api_server

    monkeypatch.setattr(api_server, "_app_data_dir", lambda: veri)
    istemci = TestClient(api_server.app, client=("127.0.0.1", 51234))
    br.refresh_recovery_material(veri, [hedef])
    dosya = veri / br.CODE_FILE_NAME
    damga = dosya.stat().st_mtime_ns
    assert istemci.post("/api/system/recovery-ack", json={}).status_code == 200
    br.refresh_recovery_material(veri, [hedef])
    assert dosya.stat().st_mtime_ns == damga, "kod değişmediği hâlde kod dosyası yeniden yazıldı"
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["warn"] is False, f"kod değişmediği hâlde onay düştü: {durum}"
