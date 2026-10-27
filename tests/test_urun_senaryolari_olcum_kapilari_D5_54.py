# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.54 (B-10.99 · .100 · .101 · .167 · .168) — ürün-senaryo ölçüm aracının (`scripts/urun_senaryolari.py`) kendi kapıları DAVRANIŞLA.

Araç sevk edilen EXE'yi ölçer; CI'da EXE yoktur ve bu dosya da EXE BAŞLATMAZ: `main()` / grup fonksiyonları sahte `kostur` / `http` /
`durdur` ve geçici bir GUII ağacıyla koşar. Ölçülen beş değişmez (her biri bugün mutantla YEŞİL kalıyordu — rapor):
  (a) BAYAT-İKİLİ NÖBETİ: EXE'den sonra değişen HER `apps/backend/**/*.py` ölçümü DURDURUR (eskiden yalnız `database/*.py` + 7 sabit dosya:
      `services/`, `headless_core.py` … değişip eski EXE ölçülse nöbet geçiyordu).
  (b) C0 KARŞIT KANIT: jeton kapısı ücretli analizi 402 ile reddetmiyorsa (her uç 200) C0 GEÇMEZ — aksi hâlde C1-C4 hiçbir şey kanıtlamaz.
  (c) B8 SIR SIZINTISI: sır dosyası BÖLÜMLÜ (`secrets_manager._empty_doc`); `auto.api_token`'ın değeri log'da geçerse B8 bunu GÖRÜR
      (eskiden yalnız üst düzey değerlere bakıyordu → hiçbir sır ölçülmüyordu). Değer çıktıya BASILMAZ, yalnız alan adı.
  (d) `main` argv'deki grubu GERÇEKTEN koşar (D → `grup_d`).
  (e) Bayat EXE'de `SystemExit` YUTULMAZ: hiçbir grup koşmaz.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time

import pytest
from exe_kapisi_surucusu import urun_senaryolari_modulu


def _agac(tmp_path, eski_sn: float, yeni: dict[str, float]):
    """Geçici GUII: EXE + backend ağacı. `yeni` = {göreli yol: mtime farkı (EXE'ye göre sn)}."""
    guii = tmp_path / "guii"
    exe = guii / "PEMF_BUILD" / "dist" / "PEMF_Backend" / "PEMF_Backend.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    t0 = time.time() - 1000
    os.utime(exe, (t0, t0))
    for rel, fark in {"apps/backend/database/patient_db.py": -eski_sn, **yeni}.items():
        p = guii / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# sahte\n", encoding="utf-8")
        os.utime(p, (t0 + fark, t0 + fark))
    return guii, exe


@pytest.mark.parametrize(
    "rel",
    ["apps/backend/services/yeni_servis.py", "apps/backend/headless_core.py", "apps/backend/controllers/x/derin.py"],
)
def test_KRITIK_a_EXE_den_SONRA_degisen_HER_backend_py_olcumu_DURDURUR(tmp_path, monkeypatch, rel):
    us = urun_senaryolari_modulu()
    guii, exe = _agac(tmp_path, eski_sn=100, yeni={rel: +100})
    monkeypatch.setattr(us, "GUII", guii)
    monkeypatch.setattr(us, "EXE", exe)
    with pytest.raises(SystemExit) as e:
        us.bayat_ikili_nobeti()
    assert "BAYAT" in str(e.value) and rel in str(e.value), (
        f"EXE'den SONRA değişen `{rel}` nöbeti durdurmadı ya da adını söylemedi: {e.value} — eski EXE ölçülüp 'ürün doğru' raporlanır (D5.54)"
    )


def test_KARSIT_a_kaynaklar_EXE_den_ESKIYSE_nobet_GECER(tmp_path, monkeypatch, capsys):
    us = urun_senaryolari_modulu()
    guii, exe = _agac(tmp_path, eski_sn=100, yeni={"apps/backend/services/yeni_servis.py": -50})
    monkeypatch.setattr(us, "GUII", guii)
    monkeypatch.setattr(us, "EXE", exe)
    us.bayat_ikili_nobeti()
    assert "EXE taze" in capsys.readouterr().out


def test_KRITIK_b_C0_tum_uclar_200_ise_KARSIT_KANIT_GECMEZ(tmp_path, monkeypatch):
    us = urun_senaryolari_modulu()
    monkeypatch.setattr(us, "CALISMA", tmp_path / "calisma")
    monkeypatch.setattr(us, "SONUCLAR", [])
    monkeypatch.setattr(us, "jeton_kodda_acik", lambda: True)
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    monkeypatch.setattr(us, "kostur", lambda *a, **k: (None, log, True, 1))
    monkeypatch.setattr(us, "durdur", lambda p: None)
    monkeypatch.setattr(us, "http", lambda *a, **k: (200, b"{}", {}))  # jeton kapısı HİÇ reddetmiyor
    us.grup_c()
    c0 = [g for kod, _b, g, _k in us.SONUCLAR if kod == "C0"]
    assert c0 == [False], (
        f"her uç 200 dönerken C0 (jeton kapısı GERÇEKTEN 402 veriyor mu) GEÇTİ sayıldı: {c0} — C1-C4 bedavaya yeşillenir (D5.54)"
    )


def test_KRITIK_c_B8_BOLUMLU_sir_dosyasinda_api_token_sizintisini_GORUR():
    us = urun_senaryolari_modulu()
    from utils import secrets_manager as sm

    doc = sm._empty_doc()
    assert "api_token" in doc["auto"], "çıpa: _empty_doc şemasında auto.api_token yok — kapı bayat"
    deger = "SAHTE-TOKEN-" + secrets.token_hex(12)
    doc["auto"]["api_token"] = deger
    for bolum in ("operator", "embedded"):
        for k in doc[bolum]:
            doc[bolum][k] = "LOGDA-OLMAYAN-" + secrets.token_hex(8)
    metin = f"2026-10-27 INFO istek basliginda token={deger} goruldu\n"
    sizan = us._log_sizan_sir_adlari(json.loads(json.dumps(doc)), metin)
    assert sizan == ["auto.api_token"], (
        f"log'a sızan auto.api_token B8'de görünmedi (sızan={sizan}) — bölümlü sır dosyasında B8 kör (D5.54). Değer basılmadı."
    )
    assert us._log_sizan_sir_adlari(doc, "temiz log\n") == [], "karşıt: sızıntı yokken B8 alan bildirdi"


def _main_sahteli(tmp_path, monkeypatch, grup: str):
    us = urun_senaryolari_modulu()
    cagri: list[str] = []
    monkeypatch.setattr(us, "CALISMA", tmp_path / "calisma")
    monkeypatch.setattr(us, "tohum_uret", lambda: True)
    for ad in ("grup_a", "grup_b", "grup_c", "grup_d"):
        monkeypatch.setattr(us, ad, lambda ad=ad: cagri.append(ad))
    monkeypatch.setattr(us, "SONUCLAR", [])
    monkeypatch.setattr(us, "_anahtar_deposu_ozeti", lambda: (0, "ozet"))
    monkeypatch.setattr(sys, "argv", ["urun_senaryolari.py", grup])
    return us, cagri


@pytest.mark.parametrize("grup,beklenen", [("D", ["grup_d"]), ("B", ["grup_b"])])
def test_KRITIK_d_main_argvdeki_grubu_GERCEKTEN_kosar(tmp_path, monkeypatch, grup, beklenen):
    us, cagri = _main_sahteli(tmp_path, monkeypatch, grup)
    monkeypatch.setattr(us, "bayat_ikili_nobeti", lambda: None)
    us.main()
    assert cagri == beklenen, f"argv={grup} iken koşan gruplar {cagri}, beklenen {beklenen} (D5.54)"


def test_KRITIK_e_bayat_EXE_de_SystemExit_YUTULMAZ_hicbir_grup_kosmaz(tmp_path, monkeypatch):
    us, cagri = _main_sahteli(tmp_path, monkeypatch, "HEPSI")

    def _bayat():
        raise SystemExit("[DUR] EXE BAYAT — sonradan degismis kaynaklar: ['apps/backend/x.py']")

    monkeypatch.setattr(us, "bayat_ikili_nobeti", _bayat)
    with pytest.raises(SystemExit):
        us.main()
    assert cagri == [], f"bayat EXE'de gruplar YİNE koştu: {cagri} — rapor geçersiz ama geçerli görünür (D5.54)"
