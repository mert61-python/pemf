# -*- coding: utf-8 -*-
"""D2-1.7 (2-D incelemesi, A1) — KÖR KAPI: D2.52'nin asıl iddiası ("REPLACE_ALL'da SİLMELERDEN SONRA eklemelerin ortasında düşüş → hiçbir şey
commit edilmez") kilitli değil.

2-D kapısı (test_geri_yukleme_BUTUNLUKLU_D252_Y12_Y111.py) arızayı yalnız SİLME adımında (`BEFORE DELETE` tetikleyicisi) ve BOŞ hedefe
eklemede (kilit) kuruyor. `import_rows`'a silme döngüsünden hemen sonra `conn.commit()` eklenen mutant 2-D kapılarında YEŞİL kalır
[ÖLÇTÜM kayit/K4_mutasyon.txt a1k4_m1: 12 passed] — oysa o sürümde eklemeler ortasında disk dolarsa cihazın TÜM tedavi geçmişi silinmiş,
yedektekinin yalnız bir kısmı yazılmış olur. Bu kapı arızayı EN ALT katta kurar: içe aktarma bağlantısında SQLite'ın kendi sayfa sınırı
(`PRAGMA max_page_count` = mevcut sayfa sayısı) — silinen sayfalar serbest listeye gider, eklemeler onları doldurup büyümeye başlayınca
SQLITE_FULL. Düz ve GERÇEK sqlcipher3 ile şifreli; doğrudan `import_rows` ve uçtan uca `/api/data/import` (cihazın kendisi).
Önce/sonra: tablo başına sayı + kanonik satır SHA-256 (rowid sırası).
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, disa_aktar, doldur, istekler, kapat, uclari_bagla

ANAHTAR = "2D-aparat-anahtari"


def _ozet(tdb, sifreli):
    mod = tdb._import_sqlcipher() if sifreli else sqlite3
    c = mod.connect(str(tdb.db_path))
    try:
        if sifreli:
            c.execute(f"PRAGMA key='{ANAHTAR}'")
        out = {}
        for (ad,) in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'audit_events' ORDER BY name"
        ).fetchall():
            h = hashlib.sha256()
            n = 0
            for satir in c.execute(f'SELECT * FROM "{ad}" ORDER BY rowid'):
                h.update(repr(tuple(satir)).encode("utf-8"))
                n += 1
            out[ad] = (n, h.hexdigest())
        return out
    finally:
        c.close()


@pytest.fixture
def kur(tmp_path, monkeypatch):
    acik = []

    def _kur(sifreli):
        from servers import api_server as api

        ta, ha = cihaz_kur(monkeypatch, tmp_path / "A", sifreli=sifreli)
        uclari_bagla(monkeypatch, ta, ha)
        doldur(ta, ha, ["Mia", "Pamuk"], seans_basi=3, sensor=200)  # yedek, hedefteki eski veriden BÜYÜK
        paket = disa_aktar(api.app)
        tb, hb = cihaz_kur(monkeypatch, tmp_path / "B", sifreli=sifreli)
        uclari_bagla(monkeypatch, tb, hb)
        doldur(tb, hb, ["Zeytin"], seans_basi=1)
        acik.extend([ta, ha, tb, hb])
        return api, paket, tb

    yield _kur
    kapat(*acik)


def _disk_dolu_baglanti(monkeypatch, tb):
    """İçe aktarma hangi iş parçacığında koşarsa koşsun, YENİ bağlantısına SQLite sayfa sınırı konur (mevcut boyut)."""
    gercek = tb._create_connection

    def _sinirli(*a, **k):
        c = gercek(*a, **k)
        c.execute(f"PRAGMA max_page_count={c.execute('PRAGMA page_count').fetchone()[0]}")
        return c

    monkeypatch.setattr(tb, "_create_connection", _sinirli)
    tb._invalidate_connections("D2-1.7 aparat: yeni bağlantılar sınırlı açılsın")


@pytest.mark.parametrize("sifreli", [False, True], ids=["duz", "sifreli"])
def test_KRITIK_D252_REPLACE_SILMEDEN_SONRA_eklemede_disk_dolarsa_HICBIR_sey_commit_edilmez(kur, monkeypatch, sifreli):
    from utils.data_export import decrypt_bundle

    api, paket, tb = kur(sifreli)
    satirlar = decrypt_bundle(base64.b64decode(paket["data_b64"]), PAROLA)
    once = _ozet(tb, sifreli)
    assert once["treatment_sessions"][0] == 1, "ön koşul: hedefte eski seans var (okuyucu görüyor)"
    _disk_dolu_baglanti(monkeypatch, tb)
    with pytest.raises(Exception):
        tb.import_rows(satirlar, True)
    sonra = _ozet(tb, sifreli)
    assert sonra == once, (
        "silmelerden SONRA eklemede disk doldu ama tedavi DB'si ilk hâline DÖNMEDİ (eski kayıtlar gitti / yarım yedek yazıldı): "
        f"{ {t: (once[t][0], sonra.get(t, (None,))[0]) for t in once if once[t] != sonra.get(t)} }"
    )


@pytest.mark.parametrize("sifreli", [False, True], ids=["duz", "sifreli"])
def test_KRITIK_D252_uc_REPLACE_eklemede_disk_dolarsa_503_ve_kayitlar_DEGISMEZ(kur, monkeypatch, sifreli):
    api, paket, tb = kur(sifreli)
    once = _ozet(tb, sifreli)
    _disk_dolu_baglanti(monkeypatch, tb)
    govde = {"passphrase": PAROLA, "blob_b64": paket["data_b64"], "confirm": "REPLACE_ALL"}
    (r,) = istekler(api.app, [("POST", "/api/data/import", govde, None)])
    assert r.status_code == 503 and "DEĞİŞMEDİ" in r.json().get("detail", ""), f"{r.status_code} {r.text[:300]}"
    assert _ozet(tb, sifreli) == once, "uç 'kayıtlar DEĞİŞMEDİ' dedi ama tedavi DB'si değişti"
