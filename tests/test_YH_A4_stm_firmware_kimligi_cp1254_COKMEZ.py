# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YH · A4 (istem 50 · Tezgâh-2 listesi 7): `scripts/stm_firmware_kimligi.py` Türkçe Windows konsolunda (cp1254) KARAR satırında
("✅ UYUMLU" / "❌ … FIRMWARE" / "❓ DOĞRULANAMADI") `UnicodeEncodeError` ile ÇÖKÜYORDU — tezgâhta yalnız `PYTHONIOENCODING=utf-8` ile
geçiyordu; yani aracın tek işi olan cevabı tam basacağı anda düşüyordu. Düzeltme: `main()` çıkışı UTF-8'e çevirir (`make_manifest`
deseni; yönlendirilmiş akışta `reconfigure` yoksa sessiz geçer).

Ölçüm: GERÇEK `main()`; çıkış akışı cp1254 (`errors=strict`, Türkçe konsolun kod sayfası) sahte metin akışı; kart / port EN ALT katta
sahte (`_portlari_bul`, `_kart_dogrula`) — karar GERÇEK `firmware_karari` yolundan (sahte kimlik yanıtı satırlarıyla). Ağ / COM yok.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


def _betik():
    spec = importlib.util.spec_from_file_location(
        "stm_firmware_kimligi_yh_a4", KOK / "scripts" / "stm_firmware_kimligi.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cp1254_akis():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1254", errors="strict", newline="\n", write_through=True)


@pytest.mark.parametrize("karar", [True, False, None])
def test_KRITIK_cp1254_konsolda_KARAR_satiri_COKMEZ_ve_tam_basilir(monkeypatch, karar):
    m = _betik()
    akis = _cp1254_akis()
    monkeypatch.setattr(sys, "stdout", akis)
    monkeypatch.setattr(sys, "argv", ["stm_firmware_kimligi.py", "--port", "COM99", "--sure", "0"])
    monkeypatch.setattr(m, "_portlari_bul", lambda istenen: ["COM99"])
    monkeypatch.setattr(m, "_kart_dogrula", lambda port, sure: (["STM_READY DDS v2.6", "STM_OK"], None))
    monkeypatch.setattr(m, "firmware_karari", lambda satirlar: (karar, "kart paketi reddetti", None))
    kod = m.main()  # cp1254'te "✅ / ❌ / ❓" eskiden UnicodeEncodeError
    sys.stdout.flush()
    cikti = akis.buffer.getvalue().decode("utf-8")
    beklenen = {True: "✅ UYUMLU", False: "❌ UYUMSUZ FIRMWARE YUKLU", None: "❓ DOĞRULANAMADI"}[karar]
    assert beklenen in cikti, cikti[-600:]
    assert kod == {True: 0, False: 1, None: 2}[karar]


def test_KARSIT_olcucu_cp1254_akista_duzeltmesiz_basimi_GERCEKTEN_dusurur():
    """Aparat kanıtı: sahte akış Türkçe konsol gibi davranır (✅ cp1254'te yok → strict hata)."""
    akis = _cp1254_akis()
    with pytest.raises(UnicodeEncodeError):
        print("  ✅ UYUMLU", file=akis)
