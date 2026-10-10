# -*- coding: utf-8 -*-
"""E2-1.9 (2-E incelemesi, A1) — kurtarma kodu DEĞİŞMEDİĞİ hâlde (yalnız `KURTARMA-KODU.txt` METİN ŞABLONU değişti — D2.75 bunu bu
dalda zaten yaptı) dosya yeniden yazılınca:
  (1) günlük "KURTARMA KODU GUNCELLENDI (kod degisti; eski kod artik zarfi ACMAZ)" der — YANLIŞ: kasadaki kod zarfı AÇAR; operatör /
      destek geçerli kodu "geçersiz" sanır (`backup_recovery.py:401-412`: ileti yalnız "dosya vardı mı?"ya bakar);
  (2) D2.13'ün onay izi DOSYA METNİNİN özetidir (`system_router._kod_dosyasi_izi`) → aynı kod için verilmiş onay DÜŞER, uyarı bandı geri
      gelir ("kodu yeniden kaydedin") — her şablon değişikliğinde bütün klinikler yeniden uyarılır.
Tetikleyici gerçek ve sıradan: operatör makine dışı yedek dizini ekler (yeni hedefte zarf "eksik" → erken dönüş yok → kod dosyası
şablona göre "güncel değil" → yeniden yazılır). 1.9.50'den yükseltmede (öneksiz mühür) aynı yanlış ileti ilk turda basılır.
GERÇEK refresh_recovery_material + GERÇEK sır deposu + GERÇEK recovery-ack / recovery-status (yerel istemci). Şablon değişimi:
`kod_dosyasi_metni` sonraki sürüm metniyle (aynı kod) — ürün kodu değil, "yeni sürüm" benzetimi.
"""

from __future__ import annotations

import logging
import re

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
    sm.set_secrets({"sqlcipher_key": "e219-sql", "patient_fernet_key": Fernet.generate_key().decode()})
    return br, sm, veri, hedef, istemci, tmp_path


class _Topla(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.satirlar = []

    def emit(self, r):
        self.satirlar.append(r.getMessage())


def _yenile(br, veri, hedefler):
    t = _Topla()
    lg = logging.getLogger("utils.backup_recovery")
    lg.addHandler(t)
    try:
        br.refresh_recovery_material(veri, hedefler)
    finally:
        lg.removeHandler(t)
    return [s for s in t.satirlar if "KURTARMA KODU" in s]


def _sablon_degisir(br, monkeypatch):
    eski = br.kod_dosyasi_metni
    monkeypatch.setattr(br, "kod_dosyasi_metni", lambda c: eski(c) + "  (sonraki surumun yonergesi)\n")


def test_KRITIK_kod_AYNIYKEN_sablon_degisince_kod_DEGISTI_denmez_ONAY_dusmez_E2_1_9(ortam, monkeypatch):
    br, sm, veri, hedef, istemci, tmp = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert istemci.post("/api/system/recovery-ack").status_code == 200
    assert istemci.get("/api/system/recovery-status").json()["warn"] is False, "aparat: onay tutmadı"
    kod = sm.get_secret("backup_recovery_code", generate=False)
    _sablon_degisir(br, monkeypatch)
    yeni = tmp / "makine_disi"
    yeni.mkdir()
    ileti = _yenile(br, veri, [hedef, yeni])
    assert sm.get_secret("backup_recovery_code", generate=False) == kod, "aparat: kod değişti"
    assert br.open_envelope(kod, (yeni / br.ENVELOPE_NAME).read_bytes()), (
        "aparat: yeni hedefin zarfı aynı kodla açılmıyor"
    )
    assert not [s for s in ileti if "kod degisti" in s or "ACMAZ" in s], (
        f"kod DEĞİŞMEDİ (kasadaki kod zarfı açar) ama günlük 'kod değişti; eski kod artık zarfı AÇMAZ' dedi: {[s[:90] for s in ileti]}"
    )
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["warn"] is False and durum["acknowledged"] is True, (
        f"AYNI koda verilmiş onay yalnız metin şablonu değişti diye DÜŞTÜ, uyarı bandı geri geldi: {durum}"
    )


def test_KRITIK_1950den_yukseltme_ayni_kod_eski_metin_kod_DEGISTI_denmez_E2_1_9(ortam):
    br, sm, veri, hedef, istemci, tmp = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    kod = sm.get_secret("backup_recovery_code", generate=False)
    muhur = veri / ".recovery_fp"
    muhur.write_text(
        re.search(r"[0-9a-f]{64}$", muhur.read_text(encoding="utf-8").strip()).group(0), encoding="utf-8"
    )  # öneksiz
    (veri / br.CODE_FILE_NAME).write_text(
        f"PEMF — YEDEK KURTARMA KODU\n\n    {br.format_code(kod)}\n\nKURTARMA: python tools/kurtarma.py --zarf ... --kod <kod>\n",
        encoding="utf-8",
    )  # 1.9.50'nin metni (aynı kod)
    ileti = _yenile(br, veri, [hedef])
    assert not [s for s in ileti if "kod degisti" in s or "ACMAZ" in s], (
        f"yükseltmede AYNI kod için 'kod değişti' dendi: {ileti}"
    )


def test_KARSIT_kod_GERCEKTEN_degisince_kod_degisti_denir_onay_duser_E2_1_9(ortam):
    br, sm, veri, hedef, istemci, tmp = ortam
    assert br.refresh_recovery_material(veri, [hedef]) is True
    assert istemci.post("/api/system/recovery-ack").status_code == 200
    sm.set_secret("backup_recovery_code", br.generate_recovery_code())  # sır deposu sıfırlanıp yeni kod üretildi
    ileti = _yenile(br, veri, [hedef])
    assert [s for s in ileti if "kod degisti" in s], f"kod değişti ama ileti söylemedi: {ileti}"
    durum = istemci.get("/api/system/recovery-status").json()
    assert durum["warn"] is True and durum["acknowledged"] is False, durum
