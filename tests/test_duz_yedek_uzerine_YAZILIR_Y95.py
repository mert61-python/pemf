# -*- coding: utf-8 -*-
"""Y95 (SAHİP KARARI, Y13 güvenli silme ilkesi) — düz-metin yedek, şifreli kopyası DOĞRULANDIKTAN sonra değiştirilirken
eski düz içeriğin ÜZERİNE YAZILIR; doğrulanmış şifreli kopya yoksa dosyaya DOKUNULMAZ.

ÖLÇÜLEN KUSUR (2-A §7 S3): D2.48 `_duz_kopyayi_sifrele` doğrulanmış şifreli kopyayı `os.replace` ile özgün adın yerine
koyuyordu; değiştirilen düz dosyanın blokları ÜZERİNE YAZILMADAN serbest kalıyor → hasta adları diskte okunur kalıyordu.

Sahte EN ALT katta — "serbest bırakma casusu": `os.replace` hedefi ya da `os.remove`/`os.unlink` kurbanı, son adı
(`st_nlink == 1`) giderken hâlâ düz içerik (hasta adı baytı) taşıyorsa kaydedilir. Ürün zinciri gerçek (gerçek ve sahte
bağlayıcı; sahte bağlayıcı içeriği ŞİFRELEMEZ — "diskte ad yok" taraması yalnız gerçek kolda).
SSD/eMMC aşınma dengelemesi (eski blokların başka yerde kalması) bu testin ölçemeyeceği "en iyi çaba" sınırıdır.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest
import sahte_sqlcipher

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

K = "Y95-at-rest-anahtar"
_SQLITE_BASLIK = b"SQLite format 3\x00"
_AD = b"HastaY95-Pamuk"


@pytest.fixture(params=sahte_sqlcipher.BAGLAYICILAR)
def baglayici(request, monkeypatch):
    return sahte_sqlcipher.baglayici_kur(request.param, monkeypatch)


def _duz_yedek(yol: Path) -> bytes:
    """>64 KiB, çok sayfalı düz yedek; hasta adı SON satırda da (yalnız ilk blokları sıfırlayan mutant görünsün)."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(yol))
    c.execute("CREATE TABLE kayit (ad TEXT, dolgu TEXT)")
    c.executemany("INSERT INTO kayit VALUES (?, ?)", [(f"dolgu{i}", "x" * 300) for i in range(400)])
    c.execute("INSERT INTO kayit VALUES (?, ?)", (_AD.decode(), "son"))
    c.commit()
    c.close()
    ham = yol.read_bytes()
    assert len(ham) > 65536 and ham.rfind(_AD) > 65536, "ön koşul: hasta adı ilk 64 KiB'ın ÖTESİNDE de olmalı"
    os.utime(yol, (1_700_000_000, 1_700_000_000))
    return ham


@pytest.fixture
def casus(monkeypatch, tmp_path):
    """Veri kökünde (tmp_path) son adı giderken düz içerik taşıyan dosyaları kaydeder (davranışı değiştirmez). Sahte
    bağlayıcının TEMP'teki kendi ara dosyaları (ürün değil, aparat) kapsam dışıdır."""
    olay = []
    kok = os.path.normcase(str(tmp_path))

    def _duz_ve_son_ad(p) -> bool:
        try:
            if not os.path.normcase(os.path.abspath(str(p))).startswith(kok):
                return False
            if not os.path.isfile(p) or os.stat(p).st_nlink != 1:
                return False
            with open(p, "rb") as fh:
                return _AD in fh.read()
        except OSError:
            return False

    gercek_replace, gercek_remove, gercek_unlink = os.replace, os.remove, os.unlink

    def _replace(src, dst, *a, **k):
        if _duz_ve_son_ad(dst):
            olay.append(("os.replace hedefi", str(dst)))
        return gercek_replace(src, dst, *a, **k)

    def _remove(p, *a, **k):
        if _duz_ve_son_ad(p):
            olay.append(("os.remove", str(p)))
        return gercek_remove(p, *a, **k)

    def _unlink(p, *a, **k):
        if _duz_ve_son_ad(p):
            olay.append(("os.unlink", str(p)))
        return gercek_unlink(p, *a, **k)

    monkeypatch.setattr(os, "replace", _replace)
    monkeypatch.setattr(os, "remove", _remove)
    monkeypatch.setattr(os, "unlink", _unlink)
    return olay


def _anahtarla_acilir(mod, yol: Path) -> bool:
    c = mod.connect(str(yol))
    try:
        c.execute(f"PRAGMA key='{K}'")
        return c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0
    except Exception:
        return False
    finally:
        c.close()


def _sifrele(app: Path, mod):
    from database import sqlcipher_util as su

    return su.duz_metin_yedekleri_sifrele(app, f"'{K}'", mod, logging.getLogger("y95"), etiket="Y95")


def _artik(app: Path) -> list:
    return sorted(p.name for p in app.rglob("*") if p.name.endswith((".duz.sil", ".enc.tmp")))


def test_KRITIK_dogrulanmis_sifreli_kopyadan_sonra_eski_duz_icerik_UZERINE_YAZILIR(baglayici, tmp_path, casus):
    """MUTASYON: sıfırlamayı kaldırmak (yalnız silmek) ya da yalnız ilk bloğu sıfırlamak → KIRMIZI."""
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    _duz_yedek(y)
    sonuc = _sifrele(app, baglayici)
    assert sonuc["sifrelendi"] == [str(y)], sonuc
    assert casus == [], f"düz içerik ÜZERİNE YAZILMADAN serbest bırakıldı (Y95): {casus}"
    assert y.read_bytes()[:16] != _SQLITE_BASLIK and _anahtarla_acilir(baglayici, y), "şifreli kopya yerinde değil"
    assert int(y.stat().st_mtime) == 1_700_000_000, "değişiklik zamanı korunmadı (D2.48)"
    assert _artik(app) == [], f"ikinci ad / geçici dosya artığı: {_artik(app)}"
    assert "duz_icerik_sifirlanamadi" not in sonuc, sonuc
    if baglayici is not sahte_sqlcipher:
        duz = [p.name for p in app.rglob("*") if p.is_file() and _AD in p.read_bytes()]
        assert duz == [], f"diskte (dosyalarda) hasta adı DÜZ: {duz}"


def test_KRITIK_degistirme_DUSERSE_duz_yedek_AYNEN_kalir_ikinci_ad_kalkar(
    baglayici, tmp_path, monkeypatch, casus, caplog
):
    """Şifreli kopya özgün adla yerine konamazsa (kilit) düz yedek BAYT BAYT aynı kalır; ikinci ad kaldırılır, sıfırlama
    YAPILMAZ. MUTASYON: hata dalında ikinci adı silmek yerine sıfırlamak → KIRMIZI (aynı dosya = VERİ KAYBI)."""
    app = tmp_path / "PEMF_GUI"
    y = app / "migration_backups" / "pre_migration_v2_20261001_000000.db"
    once = _duz_yedek(y)
    gercek = os.replace

    def _replace(src, dst, *a, **k):
        if os.path.normcase(str(dst)) == os.path.normcase(str(y)):
            raise PermissionError(32, "Dosya baska bir islem tarafindan kullaniliyor (taklit)")
        return gercek(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", _replace)
    with caplog.at_level(logging.WARNING):
        sonuc = _sifrele(app, baglayici)
    assert y.read_bytes() == once, "değiştirme düşünce düz yedek DEĞİŞTİ (sıfırlandı?) — veri kaybı"
    assert sonuc["sifrelenemedi"] == [str(y)] and "SIFRELENEMEDI" in caplog.text
    assert _artik(app) == [], f"ikinci ad / geçici dosya artığı: {_artik(app)}"


def test_KRITIK_dogrulanamayan_kopyada_duz_yedege_HIC_DOKUNULMAZ(tmp_path, monkeypatch, casus):
    """Şifreli kopya doğrulanamazsa (boş şema) düz yedeğe ikinci ad bile verilmez; içerik ve ad aynen kalır."""
    import sqlite3 as _sq

    sahte_sqlcipher.baglayici_kur("sahte", monkeypatch)
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    once = _duz_yedek(y)
    linkler = []
    gercek_link = os.link
    monkeypatch.setattr(os, "link", lambda a, b, *x, **k: (linkler.append(str(b)), gercek_link(a, b, *x, **k))[1])

    def _bos_aktar(self):
        hedef, anahtar = self._ekli
        bos = hedef + ".bos"
        c = _sq.connect(bos)
        c.execute("CREATE TABLE gecici (a)")
        c.execute("DROP TABLE gecici")
        c.commit()
        c.close()
        veri = open(bos, "rb").read()
        os.remove(bos)
        with open(hedef, "wb") as f:
            f.write(sahte_sqlcipher._baslik(anahtar) + veri[len(_SQLITE_BASLIK) :])

    monkeypatch.setattr(sahte_sqlcipher.Baglanti, "_disa_aktar", _bos_aktar)
    sonuc = _sifrele(app, sahte_sqlcipher)
    assert sonuc["sifrelenemedi"] == [str(y)], sonuc
    assert y.read_bytes() == once, "doğrulanamayan kopyada düz yedek DEĞİŞTİ"
    assert linkler == [], f"doğrulanmamış kopyada düz yedeğe ikinci ad verildi: {linkler}"
    assert casus == [] and _artik(app) == []


def test_KRITIK_yarim_kalan_islem_toparlanir_eski_duz_icerik_SIFIRLANIR(baglayici, tmp_path, casus):
    """Değiştirme ile sıfırlama ARASINDA kesilmiş önceki işlem: özgün ad doğrulanmış şifreli kopya, `.duz.sil` eski düz
    içerik. Sonraki koşu eski içeriği sıfırlayıp siler; şifreli kopyaya dokunmaz."""
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    _duz_yedek(y)
    assert _sifrele(app, baglayici)["sifrelendi"] == [str(y)]  # özgün ad: doğrulanmış şifreli kopya
    eski = Path(str(y) + ".duz.sil")
    eski.write_bytes(_duz_kopya_bayt(tmp_path))  # kesintiden kalan eski düz içerik (ayrı dosya, tek ad)
    casus.clear()
    sifreli = y.read_bytes()
    _sifrele(app, baglayici)
    assert not eski.exists(), "yarım kalan eski düz içerik toparlanmadı"
    assert casus == [], f"yarım kalan düz içerik sıfırlanmadan silindi: {casus}"
    assert y.read_bytes() == sifreli and _anahtarla_acilir(baglayici, y), "toparlama şifreli kopyaya dokundu"


def _duz_kopya_bayt(tmp_path: Path) -> bytes:
    p = tmp_path / "ayri" / "duz.db"
    return _duz_yedek(p)


def test_KRITIK_yarim_kalan_ikinci_ad_DOGRULANMAMIS_ozgunde_DOKUNULMAZ(baglayici, tmp_path, casus, caplog):
    """Özgün ad doğrulanmış şifreli kopya DEĞİLSE (ör. bozuk) `.duz.sil` tek sağlam kopya olabilir → dokunulmaz, loglanır."""
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    y.parent.mkdir(parents=True)
    y.write_bytes(b"\xab" * 8192)  # ne düz SQLite ne anahtarla açılır
    eski = Path(str(y) + ".duz.sil")
    once = _duz_kopya_bayt(tmp_path)
    eski.write_bytes(once)
    with caplog.at_level(logging.WARNING):
        _sifrele(app, baglayici)
    assert eski.exists() and eski.read_bytes() == once, (
        "doğrulanmamış özgünde tek sağlam düz kopya SIFIRLANDI/SİLİNDİ — veri kaybı"
    )
    assert str(eski) in caplog.text and "DOKUNULMADI" in caplog.text, caplog.text[-800:]


def test_KARSIT_sabit_bag_kurulamazsa_eski_davranis_ve_UYARI(baglayici, tmp_path, monkeypatch, caplog):
    """FAT/exFAT gibi bağ desteklemeyen dosya sisteminde şifreleme yine yapılır (eski davranış), sıfırlanamadığı söylenir."""
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    _duz_yedek(y)

    def _link(*a, **k):
        raise OSError(1, "Islem desteklenmiyor (taklit)")

    monkeypatch.setattr(os, "link", _link)
    with caplog.at_level(logging.WARNING):
        sonuc = _sifrele(app, baglayici)
    assert sonuc["sifrelendi"] == [str(y)] and sonuc.get("duz_icerik_sifirlanamadi") == [str(y)], sonuc
    assert _anahtarla_acilir(baglayici, y) and "UZERINE YAZILAMAYACAK" in caplog.text


def test_KRITIK_ozgun_DUZ_ve_FARKLI_ikinci_ad_varken_IKISINE_DE_DOKUNULMAZ(baglayici, tmp_path, caplog):
    """B2-4.2 (2-B bağımsız incelemesi): özgün ad DÜZ-METİN ve önceki bir işlemden kalan `.duz.sil` FARKLI bir dosyaysa
    (aynı ada sonradan düz bir yedek konmuş; `.duz.sil` önceki düz içeriğin TEK kopyası olabilir) ikinci ada DOKUNULMAZ:
    özgün ad bu koşuda şifrelenmez (`sifrelenemedi`, nedeni loglanır), `.duz.sil` bayt bayt aynı kalır. Bu koruma dalının
    kapısı yoktu (ölçüldü: korumayı kaldırıp ikinci adı silen mutantta Y95 + D2.48 21/21 YEŞİL). MUTASYON:
    `_duz_kopyayi_sifrele`'deki "farklı dosya" korumasını kaldırmak (ikinci adı silip sürdürmek) → KIRMIZI."""
    app = tmp_path / "PEMF_GUI"
    y = app / "backups" / "pemf_patients_20261001_000000.db"
    once_ozgun = _duz_yedek(y)
    eski = Path(str(y) + ".duz.sil")
    once_eski = _duz_kopya_bayt(tmp_path) + b"ONCEKI-DUZ-ICERIK"  # ayrı dosya (farklı içerik ve kimlik)
    eski.write_bytes(once_eski)
    assert not os.path.samefile(y, eski), "ön koşul: ikinci ad özgünle AYNI dosya olmamalı"
    with caplog.at_level(logging.WARNING):
        sonuc = _sifrele(app, baglayici)
    assert eski.exists() and eski.read_bytes() == once_eski, (
        "önceki yarım işlemden kalan FARKLI ikinci ad SİLİNDİ ya da DEĞİŞTİ — tek kopya olabilirdi (veri kaybı)"
    )
    assert y.read_bytes() == once_ozgun and sonuc["sifrelenemedi"] == [str(y)], sonuc
    assert "farkli dosya" in caplog.text and str(eski) in caplog.text, caplog.text[-800:]
