# -*- coding: utf-8 -*-
"""E2-1.8 (2-E incelemesi, A1) — KÖR KAPI: `config_json_yaz`ın (D2.81 ortak atomik yazıcı) "tmp + fsync + replace" sözleşmesinin
fsync kolu hiçbir kapıda ölçülmüyor. A1 mutantı k3m1 (`os.fsync(f.fileno())` silindi) D2.81 + D2.31 + config_okunamayinca kapılarında
16/16 YEŞİL kaldı. fsync yoksa `os.replace` sonrası elektrik kesintisinde NTFS `config.json`u 0 bayt / yarım bırakabilir → sonraki
açılışta PCM ve sahip "okunamadı — KAYDETME KAPATILDI" der, klinik ayarları (MQTT broker/port) varsayılana döner (2-E'nin kendi
denetim notu: "DENETIM P0 (dayaniklilik): fsync YOKTU → guc kesintisinde NTFS'te 0-baytlik/yarim dosya").

Ölçüm EN ALT katta: `os.fsync` / `os.replace` çağrı SIRASI kaydedilir (gerçek çağrılar yine yapılır); GERÇEK `config_json_yaz`,
gerçek disk. İddia: tmp'ye yazılan tanıtıcı `os.replace(tmp, hedef)`ten ÖNCE fsync'lenir.
"""

from __future__ import annotations

import json
import os


def test_KRITIK_config_json_yaz_tmp_yi_REPLACE_ONCESI_fsync_eder_E2_1_8(tmp_path, monkeypatch):
    from pemf_gui import config as sahip

    olaylar = []
    gercek_fsync, gercek_replace = os.fsync, os.replace

    def _fsync(fd):
        olaylar.append(("fsync", fd))
        return gercek_fsync(fd)

    def _replace(a, b, *x, **k):
        olaylar.append(("replace", os.path.basename(str(a)), os.path.basename(str(b))))
        return gercek_replace(a, b, *x, **k)

    monkeypatch.setattr(os, "fsync", _fsync)
    monkeypatch.setattr(os, "replace", _replace)
    monkeypatch.setattr("utils.file_acl.lock_down_file", lambda *a, **k: True)  # ACL konu değil
    hedef = tmp_path / "config.json"
    sahip.config_json_yaz(str(hedef), {"mqtt": {"broker_url": "10.0.0.9"}})
    assert json.loads(hedef.read_text(encoding="utf-8"))["mqtt"]["broker_url"] == "10.0.0.9", "aparat: yazım olmadı"
    rep = [i for i, o in enumerate(olaylar) if o[0] == "replace" and o[2] == "config.json"]
    assert rep, f"aparat: os.replace(…, config.json) görülmedi: {olaylar}"
    assert any(o[0] == "fsync" for o in olaylar[: rep[0]]), (
        f"config.json atomik takastan ÖNCE fsync EDİLMEDİ (elektrik kesintisinde 0 bayt / yarım dosya): {olaylar}"
    )


def test_KARSIT_yarim_yazim_eski_baytlari_birakir_E2_1_8(tmp_path, monkeypatch):
    """Karşıt (D2.31'in ölçtüğü kol): tmp'ye yazım düşerse hedef önceki baytlarla kalır — bu kapı fsync'e ÖZGÜ olanı ayırır."""
    from pemf_gui import config as sahip

    hedef = tmp_path / "config.json"
    hedef.write_text('{"eski": 1}', encoding="utf-8")
    monkeypatch.setattr("utils.file_acl.lock_down_file", lambda *a, **k: True)

    def _patlat(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sahip.json, "dump", _patlat)
    try:
        sahip.config_json_yaz(str(hedef), {"yeni": 2})
    except OSError:
        pass
    assert hedef.read_text(encoding="utf-8") == '{"eski": 1}'
