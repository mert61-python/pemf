# -*- coding: utf-8 -*-
"""E2-1.10 (2-E incelemesi, A1) — S-E.1 kalan riski ÖLÇÜLDÜ: önekli mühürden sonra `KURTARMA-KODU.txt` operatör "Kaydettim" DEMEDEN
yok olursa (operatör dosyanın "silebilirsiniz" metnine güvenip kodu almadan sildi / AV / temizlik aracı) dosya bir daha yazılmaz ve
UYARI BANDI KAYBOLUR (`warn = kod_var and not onay` → kod_var False). Operatöre kodu almadığı hiç söylenmez; disk ölünce makine dışı
yedekler (zarf) AÇILAMAZ. 2-E bunu "ayırt etmek S-E.1 (c)'yi (onay kaydı — tedavi DB) gerektirir" diye açık bıraktı.
Önerilen (c-hafif): onay ucu veri kökünde küçük bir onay işareti de bırakır; yedek turu kod dosyası YOK + onay işareti YOK görürse dosyayı
bir kez daha yazar (DB'ye bağlanmadan). Onaydan sonra silinen dosya geri yazılmaz (S-E.1 korunur).
GERÇEK refresh_recovery_material + GERÇEK sır deposu + GERÇEK recovery-ack / recovery-status (yerel istemci).
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    from servers import api_server
    from utils import backup_recovery as br
    from utils import secrets_manager as sm

    veri = sm._data_dir()
    hedef = tmp_path / "yedek"
    hedef.mkdir()
    monkeypatch.setattr(api_server, "_app_data_dir", lambda: veri)
    istemci = TestClient(api_server.app, client=("127.0.0.1", 51234))
    sm.set_secrets({"sqlcipher_key": "e2110-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    return br, sm, veri, hedef, istemci


def test_KRITIK_ONAYSIZ_silinen_kod_dosyasi_sonraki_turda_GERI_gelir_bant_KALIR_E2_1_10(ortam):
    br, sm, veri, hedef, istemci = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert istemci.get("/api/system/recovery-status").json()["warn"] is True, "aparat: ilk uyarı yok"
    (veri / br.CODE_FILE_NAME).unlink()  # "Kaydettim" DENMEDEN dosya gitti
    br.refresh_recovery_material(veri, [hedef])  # sonraki yedek turu
    durum = istemci.get("/api/system/recovery-status").json()
    assert (veri / br.CODE_FILE_NAME).is_file() and durum["warn"] is True, (
        f"operatör kodu ONAYLAMADAN dosya yok oldu; dosya geri yazılmadı ve uyarı bandı KAYBOLDU: {durum} — operatöre kodu almadığı "
        "bir daha söylenmez"
    )
    kod = sm.get_secret("backup_recovery_code", generate=False)
    assert br.format_code(kod) in (veri / br.CODE_FILE_NAME).read_text(encoding="utf-8")
    assert br.open_envelope(kod, (hedef / br.ENVELOPE_NAME).read_bytes())


def test_KARSIT_ONAYDAN_sonra_silinen_kod_dosyasi_GERI_yazilmaz_bant_YOK_E2_1_10(ortam):
    """S-E.1 sınırı korunur: operatör kodu dışarı alıp "Kaydettim" dedikten sonra sildiyse dosya geri gelmez."""
    br, sm, veri, hedef, istemci = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert istemci.post("/api/system/recovery-ack").status_code == 200
    (veri / br.CODE_FILE_NAME).unlink()
    for _ in range(2):
        br.refresh_recovery_material(veri, [hedef])
    durum = istemci.get("/api/system/recovery-status").json()
    assert not (veri / br.CODE_FILE_NAME).exists(), "onaydan sonra silinen kod dosyası geri yazıldı"
    assert durum["warn"] is False, durum


def test_KRITIK_ESKI_koda_verilen_onay_isareti_YENI_kodun_onaysiz_silinmesini_ORTMEZ_E2_1_10(ortam):
    """2-E incelemesi orkestratörü: onay işareti yalnız VARLIĞIYLA sayılırsa, kod değiştikten sonra (eski koda verilmiş) işaret YENİ kodun
    onaysız silinmesini "operatör aldı" sayar → dosya geri gelmez, bant kaybolur. İşaret onaylanan KODA bağlı olmalı."""
    br, sm, veri, hedef, istemci = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert istemci.post("/api/system/recovery-ack").status_code == 200  # eski kod onaylandı (işaret yazıldı)
    sm.set_secret("backup_recovery_code", br.generate_recovery_code())  # kod değişti
    br.refresh_recovery_material(veri, [hedef])
    assert istemci.get("/api/system/recovery-status").json()["warn"] is True, "aparat: yeni kod için uyarı yok"
    (veri / br.CODE_FILE_NAME).unlink()  # YENİ kod "Kaydettim" denmeden gitti
    br.refresh_recovery_material(veri, [hedef])
    durum = istemci.get("/api/system/recovery-status").json()
    assert (veri / br.CODE_FILE_NAME).is_file() and durum["warn"] is True, (
        f"ESKİ koda verilmiş onay işareti YENİ kodun onaysız silinmesini örttü: dosya geri gelmedi, bant kayboldu ({durum})"
    )
