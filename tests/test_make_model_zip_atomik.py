# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`make_model_zip.py` ATOMİK OLMAYAN YAZIM + TEST EDİLEMEZLİK (denetim 2026-08-17, cid. 3).

İki alt kalem:

**2A — atomiklik.** `zip_yaz` hedefi DOĞRUDAN `'w'` ile açıp KIRPIYORDU. Yazım ortasında bir hata
olursa `zipfile`ın `__exit__`i merkezi dizini YAZDIĞI için diskte **"GEÇERLİ ama EKSİK"** bir
`home.zip` kalıyordu (ölçüldü: 3 girdi yerine 1, `testzip()` yine `None`). `scripts/make_manifest.py`
`home.zip` için bütünlük kontrolü YAPMAZ; sha'yı MÜHÜRLER ve EXIT=0 verir. Sonrası iki yoldan biri:
sha değiştiği için URL yeni etikete taşınır ama BUILD.md yükleme listesinde `home.zip` YOK →
"Ev Sahibi" profilinde **404**; ya da yüklenirse sha UYUŞUR → launcher eksik paketi kabul eder →
modeller sessizce eksik.

**2B — test edilemezlik.** Çıktı dizini SABİTTİ (`pemf-app-packages`), yani betiği test etmek
GERÇEK 318 MB'lık yayın varlığını ezerdi. `make_base_zip.py`deki `PEMF_PKG_OUT` yönlendirmesi buraya
da getirildi; **varsayılan davranış değişmedi**.

⚠️ `make_base_zip._yaz` ORTAK YARDIMCI YAPILMADI. Ölçüldü: o `sorted()` + `z.open(...,
force_zip64=True)` kullanıyor; ikisi de `home.zip`in baytlarını (6013 → 6053) ve sırasını değiştirir
→ sha kayar → URL `home.zip`in YÜKLENMEDİĞİ etikete taşınır → deterministik 404. İki paketleyici
bilerek bağımsız kaldı (~8 satır tekrar, bilinçli).

⚠️ TESTLER SÜREÇ İÇİ (alt-süreç DEĞİL): `make_model_zip` kaynağını modül SABİTİNDEN alıyor, yani
alt-süreç olarak koşmak gerçek 318 MB modeli okur+yazar.
"""

import ast
import importlib
import io as _io
import os
import sys
import zipfile
from pathlib import Path

import pytest

GUII = Path(__file__).resolve().parent.parent
BETIK = GUII / "build_tools" / "make_model_zip.py"
GERCEK_CIKTI = GUII / "pemf-app-packages"
GERCEK_HOME = GERCEK_CIKTI / "home.zip"


def _mmz():
    """`build_tools/make_model_zip`i `test_cekirdek_model_cozumu.py` ile AYNI yoldan import et."""
    yol = str(GUII / "build_tools")
    if yol not in sys.path:
        sys.path.insert(0, yol)
    import make_model_zip as m

    # ⚠️ MODÜL KİMLİK KAPISI: modül iki isimle yüklenirse İKİ `PROFILLER`/`CIKTI` doğar ve yamalar
    # sessizce boşa düşer (bu depoda o tuzağa bir kez düşüldü).
    assert Path(m.__file__).resolve() == BETIK.resolve(), f"yanlis modul nesnesi: {m.__file__}"
    # ⚠️ Ölçüt ALT-DİZE DEĞİL, tam ad: bu test dosyasının kendi modül adı da ("test_make_model_zip_atomik")
    # alt-dizeyi içeriyor ve naif bir sayım kendi kendini yakalıyordu (ölçüldü: 2 == 1 düştü).
    ayni = [k for k in sys.modules if k == "make_model_zip" or k.endswith(".make_model_zip")]
    assert len(ayni) == 1, f"modul IKI isimle yuklenmis: {ayni}"
    return m


@pytest.fixture()
def mmz(tmp_path):
    """Kaynak/çıktı/profil tmp'ye yönlendirilir. GERÇEK yayın dosyasına dokunmak İMKÂNSIZ.

    ⚠️ KENDİ `MonkeyPatch()` ÖRNEĞİ kullanılır, testin paylaşılan `monkeypatch` fixture'ı DEĞİL:
    `conftest.py`de kayda geçmiş ders — testin kendi `undo()`su paylaşılan örnekteki KORUMAYI da
    siler ve gerçek dizine yazım geri gelir."""
    m = _mmz()
    mp = pytest.MonkeyPatch()

    kaynak = tmp_path / "ai_models"
    cikti = tmp_path / "paket_cikti"
    # ⚠️ BİLEREK SIRALANMAMIŞ + içerikleri FARKLI: `sorted()` mutasyonu bayt değiştirmezse
    # sessizce geçerdi. `sorted()` ilk sıraya `cat_disease/c.pkl`i alır.
    yollar = ("ai_hub/cat_landmark/a.json", "ai_hub/cat_landmark/b.onnx", "ai_hub/cat_disease/c.pkl")
    for i, r in enumerate(yollar):
        f = kaynak / r
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(bytes([65 + i]) * (100 + i * 37))

    mp.setattr(m, "KAYNAK", kaynak)
    mp.setattr(m, "CIKTI", cikti)
    mp.setitem(m.PROFILLER, "home", yollar)
    mp.setenv("PEMF_PKG_OUT", str(cikti))  # kaçak bir reload/alt-süreç de tmp'ye düşsün

    # SERT KAPI: gerçek dizine yazma ihtimali sıfırlanmadan devam etme.
    assert m.CIKTI != GERCEK_CIKTI and str(tmp_path) in str(m.CIKTI)

    def _nobet():
        st = GERCEK_HOME.stat() if GERCEK_HOME.exists() else None
        return (st.st_size, st.st_mtime_ns) if st else None

    once = _nobet()
    try:
        yield m, cikti
    finally:
        mp.undo()
        assert _nobet() == once, "GERCEK pemf-app-packages/home.zip DEGISTI — test yayin varligini ezdi"
        assert not (GERCEK_CIKTI / "home.zip.tmp").exists(), "gercek dizinde .tmp artigi kaldi"


# ── 2A: atomiklik ────────────────────────────────────────────────────────────


def test_KRITIK_yarim_kalan_yazim_ONCEKI_home_zipi_BOZMAZ(mmz):
    """Yarım kalan yazım ÖNCEKİ geçerli `home.zip`i bozmamalı."""
    m, cikti = mmz
    hedef = m.zip_yaz("home")
    saglam = hedef.read_bytes()

    # ⚠️ DETERMİNİST PATLAMA YAZIMIN ORTASINDA (sert-kill YOK, bu ortamda güvenilir değil).
    # `dosyalari_topla` sarılır: gerçeğini çağırıp 2. çiftin kaynağını bir DİZİNE çevirir →
    # `open(dizin, "rb")` OSError atar. Gerçek toplayıcı yamalanmak ZORUNDA, çünkü onun kendi
    # `is_file()` kapısı okunamaz kaynağı YAZIMDAN ÖNCE reddeder ve kaza hiç ortaya düşmez.
    gercek = m.dosyalari_topla
    cagri = []

    def _sabotaj(profil, tablo=None):  # FAZ 4.5: zip_yaz artik tablo da gecirir
        cagri.append(profil)
        ciftler = list(gercek(profil) if tablo is None else gercek(profil, tablo))
        src, arc = ciftler[1]
        src.unlink()
        src.mkdir()
        return ciftler

    mp = pytest.MonkeyPatch()
    mp.setattr(m, "dosyalari_topla", _sabotaj)
    try:
        with pytest.raises(OSError):
            m.zip_yaz("home")
    finally:
        mp.undo()

    assert cagri == ["home"], "sahte toplayici GERCEK nesneye ulasmadi → test hicbir sey olcmedi"
    assert hedef.read_bytes() == saglam, (
        "onceki GECERLI home.zip EZILDI → make_manifest butunluk kontrolu YAPMADAN sha'yi muhurler; "
        "sonuc ya 'Ev Sahibi' profilinde 404 ya da sessizce EKSIK modeller"
    )
    with zipfile.ZipFile(hedef) as z:
        assert len(z.namelist()) == 3 and z.testzip() is None, "hedef 'gecerli ama EKSIK' hale geldi"

    assert sorted(p.name for p in cikti.iterdir()) == ["home.zip"], (
        f"basarisiz kosudan artik kaldi: {sorted(p.name for p in cikti.iterdir())}"
    )


def test_gecici_ad_YAYIN_JOKERINE_gorunmez():
    """Geçici dosya adı `.zip` ile BİTMEMELİ — `gh release upload ... *.zip` onu YAYINA sokardı.

    ⚠️ AYRI TEST: yukarıdaki testte geçici adı gözlemlemek İMKÂNSIZ (`finally` her hâlde siliyor).
    `make_base_zip`te ilk yazımda tam bu mutasyon SESSİZCE geçmişti.
    ⚠️ METİN ARAMASI DEĞİL: adlandırma ifadesi `ast` ile BULUNUP GERÇEKTEN DEĞERLENDİRİLİYOR.
    `ast` yorum düğümü üretmez; docstring `Expr` olarak görünür ama `Assign` filtresini geçmez.
    ⚠️ `next(...)` VARSAYILANSIZ: `next(gen, None)` yazılsaydı düğüm yokken `str(None)` `.zip` ile
    bitmez ve test YANLIŞ-YEŞİL olurdu."""
    agac = ast.parse(BETIK.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "zip_yaz")
    atama = next(n for n in fn.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "gecici")
    ad = eval(  # noqa: S307 — ifade `zip_yaz` gövdesinden AST ile alındı, dış girdi değil
        compile(ast.Expression(atama.value), "<gecici>", "eval"),
        {"str": str, "os": os, "Path": Path},
        {"hedef": Path("C:/paket/home.zip"), "profil": "home", "CIKTI": Path("C:/paket")},
    )

    assert not str(ad).endswith(".zip"), (
        f"gecici ad '.zip' ile bitiyor ({ad!r}) → sert-kill sonrasi kalan YARIM dosya "
        "`gh release upload ... *.zip` joker'iyle YAYINA girer"
    )
    assert os.path.basename(str(ad)) != "home.zip", "gecici ad hedefle AYNI (atomiklik yok)"


def test_KRITIK_zip_BAYT_BICIMI_degismez(mmz):
    """⚠️ sha KİLİDİ: yayındaki `home.zip`in bayt biçimi korunmalı.

    `sorted()`, `force_zip64` akışı ya da `SABIT_TARIH`in kalkması sha'yı kaydırır →
    `make_manifest` URL'yi paketin YÜKLENMEDİĞİ etikete taşır → "Ev Sahibi" profilinde 404.
    Bu test düzeltmeden ÖNCE de yeşildi; amacı düzeltmenin (ya da ileride bir "ortak yardımcıya
    birleştirme" girişiminin) baytları kaydırmasını yakalamak."""
    m, _ = mmz
    hedef = m.zip_yaz("home")

    # ⚠️ TARİH LİTERAL OLARAK SABİTLENİR, `m.SABIT_TARIH` OKUNMAZ. İlk yazımda referans üretim
    # koduyla AYNI sabiti okuyordu; sabitin DEĞERİNİ değiştiren bir mutasyon iki tarafı birlikte
    # kaydırıp SESSİZCE geçiyordu (ölçüldü). Sabiti değiştirmek yayındaki home.zip'in sha'sını
    # kaydırır ve paketin YENİDEN YÜKLENMESİNİ zorunlu kılar — testin bunu yakalaması gerekir.
    # (Not: `zipfile.ZipInfo`un kendi varsayılanı da (1980,1,1,0,0,0)'dır; yani `date_time=`
    # argümanını SİLMEK bayt-özdeş çıktı verir ve haklı olarak yakalanmaz.)
    BEKLENEN_TARIH = (1980, 1, 1, 0, 0, 0)
    assert m.SABIT_TARIH == BEKLENEN_TARIH, (
        f"SABIT_TARIH degistirilmis ({m.SABIT_TARIH}) → yayindaki home.zip'in sha'si kayar; "
        "paket YENIDEN YUKLENMEDEN yayinlanirsa 'Ev Sahibi' profilinde 404"
    )

    tampon = _io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for rel in m.PROFILLER["home"]:  # BEYAN sırası, sorted DEĞİL
            zi = zipfile.ZipInfo(f"ai_models/{rel}", date_time=BEKLENEN_TARIH)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, (m.KAYNAK / rel).read_bytes())

    assert hedef.read_bytes() == tampon.getvalue(), (
        "zip bayt bicimi DEGISTI → home.zip'in sha'si kayar ve yayin URL'si bos etikete tasinir"
    )


# ── 2B: çıktı yönlendirmesi ──────────────────────────────────────────────────


def _reload_ile(env_degeri, tmp_path):
    """`CIKTI` IMPORT ANINDA hesaplanıyor → env değişince `reload` ŞART.

    ⚠️ `finally`de İKİNCİ bir reload zorunlu: yoksa `CIKTI` pytest'in sildiği `tmp_path`e bakar
    kalır ve `test_cekirdek_model_cozumu.py` sessizce başka bir dizine bakar (çapraz kirlenme)."""
    m = _mmz()
    mp = pytest.MonkeyPatch()
    if env_degeri is None:
        mp.delenv("PEMF_PKG_OUT", raising=False)
    else:
        mp.setenv("PEMF_PKG_OUT", env_degeri)
    try:
        m = importlib.reload(m)
        return Path(m.CIKTI)
    finally:
        mp.undo()
        importlib.reload(m)


def test_KRITIK_cikti_dizini_PEMF_PKG_OUT_ile_yonlendirilebilir(tmp_path):
    """Yönlendirme olmadan bu betiği test etmek GERÇEK 318 MB'lık yayın varlığını ezerdi."""
    ozel = tmp_path / "ozel"

    assert _reload_ile(str(ozel), tmp_path) == ozel, (
        "PEMF_PKG_OUT YOK SAYILIYOR → testler gercek pemf-app-packages/home.zip uzerine yazar"
    )


def test_KARSIT_KANIT_PEMF_PKG_OUT_YOKSA_varsayilan_AYNI_kalir(tmp_path):
    """⚠️ Varsayılan DEĞİŞMEMELİ: BUILD.md yayın akışı ve `make_manifest --dir` buna bağlı.

    Ayrıca import'un YAN ETKİSİZLİĞİ ölçülür: `make_base_zip`in modül-seviyesi `makedirs`ini körü
    körüne kopyalayan bir yama, `test_cekirdek_model_cozumu.py`nin düz import'unda GERÇEK dizini
    yaratmaya başlardı."""
    assert _reload_ile(None, tmp_path) == GUII / "pemf-app-packages"

    olmayan = tmp_path / "olmayan_cikti"
    _reload_ile(str(olmayan), tmp_path)
    assert not olmayan.exists(), "modul IMPORT'u dizin YARATTI (makedirs modul seviyesine sizmis)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
