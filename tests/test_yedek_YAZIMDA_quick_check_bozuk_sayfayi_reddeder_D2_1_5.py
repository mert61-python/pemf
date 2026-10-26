# -*- coding: utf-8 -*-
"""D2-1.5 (2-D incelemesi, A1) — KÖR KAPI: "yazım anında `PRAGMA quick_check`" (D2.63) kilitli değil.

`yedek_yaz` geçici dosyayı `yedek_acilir_mi(…, tam=True)` ile doğrular. `tam=False` (yalnız şema okuması) mutantı 2-D kapılarında
(D2.63 + D2.61 + retention) YEŞİL kalır [ÖLÇTÜM kayit/K2_mutasyon.txt a1k2_m1: 32 passed]: yazım sırasında veri sayfası bozulan bir
yedek (başlık + sqlite_master sağlam) "doğrulandı" sayılıp son ada taşınır ve rotasyonda sağlam bir yedeğin yuvasını alır.
Bu kol bozulmayı EN ALT katta, gerçek baytla kurar: yazım bittikten sonra, doğrulamadan hemen önce geçici dosyada hedef tablonun
(`treatment_sessions` / `patients`) b-ağacından inilerek bulunan CANLI bir yaprak sayfa bozulur (sayfa 1 = başlık + şema DOKUNULMAZ).
Beklenen: create_backup False, son ad yok, geçici yok.

D5 (D3 devri, kararsız aparat — D3 tabanda `[hasta]` kolunu 1 / 4 KIRMIZI ölçtü): eski aparat bozulacak baytı sabit uzaklıkta
(`boyut - 300`, 256 bayt XOR) seçiyordu — kırmızının o anki kökü bu makinede YENİDEN ÜRETİLEMEDİ (gerçek akışta 30 / 30 yakalandı), ama
aynı uzaklık bitmiş hasta yedeklerinin 13 / 30'unda quick_check'in görmediği alana düşüyordu (k5 sondası) → aparat veri yerleşimine
bağlıydı. Şimdi: (1) bozulma b-ağacı yapısından seçilir; (2) iki bozulma türü ürünün iki ayrı reddini ölçer — tür baytı bozuk yaprakta
quick_check İSTİSNA atar (except dalı), hücre yapısı bozuk yaprakta hata SATIRI döndürür ('ok' karşılaştırması); tek türle "satırı 'ok'
denetlemeden kabul et" mutantı YAŞIYORDU; hata satırı üreten yöntem yerleşime göre değişebildiği için birkaç yöntem önce KOPYADA denenir,
öz-denetimden geçen ilki uygulanır; (3) kanca yalnız bu testin hedefinin geçici dosyasını bozar (modül düzeyi yama süreçteki başka
yedeklere de uğrar).
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest

_TABLO = {"tedavi": "treatment_sessions", "hasta": "patients"}


def _canli_yaprak_sayfa(yol: str, tablo: str) -> tuple[int, int]:
    """(sayfa_boyutu, sayfa_no): `tablo`nun b-ağacında kökten EN SAĞ yaprağa inilir; yaprak = 0x0D ve hücre sayısı > 0 olmalı."""
    c = sqlite3.connect(f"file:{Path(yol).as_posix()}?mode=ro", uri=True)
    try:
        kok = c.execute("SELECT rootpage FROM sqlite_master WHERE type='table' AND name=?", (tablo,)).fetchone()[0]
    finally:
        c.close()
    ham = Path(yol).read_bytes()
    boy = struct.unpack(">H", ham[16:18])[0]
    boy = 65536 if boy == 1 else boy
    sayfa = kok
    for _ in range(16):
        bas = (sayfa - 1) * boy
        tur = ham[bas]
        if tur == 0x0D:
            hucre = struct.unpack(">H", ham[bas + 3 : bas + 5])[0]
            assert hucre > 0, f"aparat: {tablo} yaprağı {sayfa} boş"
            assert sayfa != 1, "aparat: sayfa 1 (başlık + şema) bozulmamalı"
            return boy, sayfa
        assert tur == 0x05, f"aparat: {tablo} b-ağacında beklenmeyen sayfa türü {tur:#x} (sayfa {sayfa})"
        sayfa = struct.unpack(">I", ham[bas + 8 : bas + 12])[0]  # iç sayfanın en sağ çocuğu
    raise AssertionError("aparat: yaprak sayfaya inilemedi")


def _quick_check_sonucu(yol: str) -> str:
    """Aparat öz-denetimi (düz sqlite3): 'ok' | 'SATIR' (quick_check hata satırı döndürdü) | 'ISTISNA' (sorgu yükseldi)."""
    c = sqlite3.connect(f"file:{Path(yol).as_posix()}?mode=ro", uri=True)
    try:
        r = c.execute("PRAGMA quick_check").fetchone()
        return "ok" if r and str(r[0]).strip().lower() == "ok" else "SATIR"
    except sqlite3.DatabaseError:
        return "ISTISNA"
    finally:
        c.close()


def _tur_bayti(ham: bytearray, bas: int, boy: int) -> None:
    ham[bas] = 0x00


def _isaretci_disari(ham: bytearray, bas: int, boy: int) -> None:
    ham[bas + 8 : bas + 10] = struct.pack(">H", boy - 1)


def _hucre_sayisi_fazla(ham: bytearray, bas: int, boy: int) -> None:
    n = struct.unpack(">H", ham[bas + 3 : bas + 5])[0]
    ham[bas + 3 : bas + 5] = struct.pack(">H", n + 3)


def _icerik_alani_basi(ham: bytearray, bas: int, boy: int) -> None:
    ham[bas + 5 : bas + 7] = struct.pack(">H", 20)


# tür → (beklenen quick_check sonucu, sırayla denenen yöntemler)
_BOZULMA = {
    "istisna": ("ISTISNA", (_tur_bayti,)),
    "hata_satiri": ("SATIR", (_icerik_alani_basi, _hucre_sayisi_fazla, _isaretci_disari)),
}


def _boz(yol: str, tablo: str, bozulma: str) -> str:
    """Geçici dosyanın canlı yaprağını `bozulma` türüyle bozar. Yöntemler sırayla ASIL dosyaya uygulanır; quick_check öz-denetimi
    beklenen sonucu (iki ardışık okumada) vermezse baytlar geri yazılıp sonraki yönteme geçilir (k5: aynı işaretçi bozulması bir
    dosyada hata satırı, öbüründe istisna verdi — sonuç yerleşime bağlı)."""
    beklenen, yontemler = _BOZULMA[bozulma]
    boy, no = _canli_yaprak_sayfa(yol, tablo)
    bas = (no - 1) * boy
    asil = bytes(Path(yol).read_bytes())
    assert asil[bas] == 0x0D
    denenen = []
    for yontem in yontemler:
        ham = bytearray(asil)
        yontem(ham, bas, boy)
        Path(yol).write_bytes(ham)
        sonuclar = (_quick_check_sonucu(yol), _quick_check_sonucu(yol))
        denenen.append(f"{yontem.__name__}={sonuclar}")
        if sonuclar == (beklenen, beklenen):
            return f"sayfa{no}:{yontem.__name__}:{beklenen}"
        Path(yol).write_bytes(asil)
    raise AssertionError(
        f"aparat: {bozulma} türünü ({beklenen}) üreten bozma yöntemi bulunamadı (sayfa {no}; {denenen})"
    )


@pytest.mark.parametrize("bozulma", sorted(_BOZULMA))
@pytest.mark.parametrize("hangisi", ["tedavi", "hasta"])
def test_KRITIK_yazimda_veri_sayfasi_bozulan_yedek_SON_ADA_tasinmaz(temp_app_data, monkeypatch, hangisi, bozulma):
    from database import patient_database as pdb
    from database import sqlcipher_util as su
    from database import treatment_history_db as thdb
    from database import yedek_dosyasi as yd

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = thdb.TreatmentHistoryDB(temp_app_data)
    hdb = pdb.PatientDatabase(str(temp_app_data / "patients.db"))
    try:
        for i in range(150):
            tdb.start_session(treatment_mode="Manuel", patient_name=f"D215-{i:03d}-" + "q" * 120)
            hdb.add_patient({"name": f"D215-{i:03d}", "species": "Kedi", "owner_name": "w" * 120})
        db = tdb if hangisi == "tedavi" else hdb
        bdir = temp_app_data / "backups"
        bdir.mkdir(exist_ok=True)
        hedef = bdir / f"{'pemf_treatment_history_' if hangisi == 'tedavi' else 'pemf_patients_'}20261009_090909.db"
        gercek = yd.yedek_acilir_mi
        bozuldu = []

        def _bozup_dogrula(yol, *a, **k):
            if str(yol) == yd.gecici_yol(str(hedef)) and not bozuldu:
                bozuldu.append(_boz(str(yol), _TABLO[hangisi], bozulma))
            return gercek(yol, *a, **k)

        monkeypatch.setattr(yd, "yedek_acilir_mi", _bozup_dogrula)
        sonuc = db.create_backup(str(hedef))
        assert bozuldu, "aparat: geçici dosya doğrulamadan önce bozulamadı"
        assert sonuc is False and not hedef.exists(), (
            f"yazımda veri sayfası bozulan yedek 'doğrulandı' sayılıp SON ADA taşındı (create_backup={sonuc}, {bozuldu}) — "
            "yazım anında quick_check yapılmıyor (yalnız şema okuması) ya da quick_check sonucu 'ok' denetlenmiyor"
        )
        assert not list(bdir.glob("*" + yd.GECICI_EK)), "bozuk geçici dosya kaldı"
    finally:
        tdb.close()
        hdb._reset_thread_conn()
