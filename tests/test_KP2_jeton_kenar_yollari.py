# -*- coding: utf-8 -*-
"""KP-2 · apps/backend/servers/jeton.py · sözleşmeler: bayrak / canlı oturum unutma / sonuçsuz kare kuralının kenarları · ayrım
istisnada bırakılır · eski defter taşıması silinemeyen / okunamayan dosyada veriyi KORUR · defter okunamaz / yazılamaz / karantina
yazılamaz iken analiz yolu çökmez ve eski defter bozulmaz · aynı istek defterde iki kez durmaz · gönderici istisnası kaydı silmez ·
Supabase taşıma katmanı (yapılandırma yok / boş satır / ağ istisnası) · uzlaştırma tetikleyicisi asla fırlatmaz, düşen iplik kaydı
KORUR ve tek-uçuş kilidini bırakır · bozuk defter kararı engellemez · tüketim bağımlılığının hata yolları yanıtı bozmaz.

Bugünkü davranış (Y194): `JETON_SAHIP_ACIK = False` → `JETON_ENFORCED` False. Ücretlendirme yolları `monkeypatch` ile True yapılarak
sınanır (mevcut jeton testleriyle aynı desen). Sahte EN ALT katta: `requests.post`, kasa (`utils.secrets_manager.get_secret`),
`threading.Thread` (başlatılamayan iplik), `Path.unlink` (Windows kilidi). Defter yalnız tmp_path (`PEMF_DATA_DIR`).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import pathlib
import threading
import types

import pytest
from servers import jeton

ANALIZ = "/api/ai/vision/ornek_analiz"


def _jwt(sub: str) -> str:
    b = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{b}.imza"


class _Istek:
    def __init__(self, sub: "str | None", yol: str = ANALIZ, basliklar: "dict | None" = None):
        self.headers = {"authorization": f"Bearer {_jwt(sub)}"} if sub else {}
        self.headers.update(basliklar or {})
        self.url = types.SimpleNamespace(path=yol)
        self.state = types.SimpleNamespace()


class _Yanit:
    def __init__(self, govde, ok=True, durum=200):
        self._govde = govde
        self.ok = ok
        self.status_code = durum
        self.content = b"" if govde is None else json.dumps(govde).encode()

    def json(self):
        return self._govde

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def kok(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(jeton, "_DEFTER_GOCU", {})
    monkeypatch.setattr(jeton, "_son_uzlastirma", None)
    yield tmp_path
    t = jeton._son_uzlastirma
    if t is not None:
        t.join(timeout=10)


@pytest.fixture
def supabase(monkeypatch):
    """Kasa + ağ EN ALT katta: yapılandırma var; `requests.post` çağrıları kaydedilir, yanıtlar sıradan verilir."""
    import requests
    import utils.secrets_manager as sm

    gercek = sm.get_secret
    ayar = {"supabase_url": "https://ornek.supabase.test/", "supabase_anon_key": "anon-ornek"}

    def _get_secret(ad, *a, **k):
        if ad in ayar:
            return ayar[ad]
        return gercek(ad, *a, **k)

    monkeypatch.setattr(sm, "get_secret", _get_secret)
    durum = types.SimpleNamespace(cagrilar=[], yanitlar=[], ayar=ayar)

    def _post(url, json=None, headers=None, timeout=None):
        durum.cagrilar.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        y = durum.yanitlar.pop(0) if durum.yanitlar else _Yanit({"ok": True})
        if isinstance(y, BaseException):
            raise y
        return y

    monkeypatch.setattr(requests, "post", _post)
    return durum


def _defteri_yaz(kok_dizin, kayitlar):
    p = kok_dizin / "PEMF_GUI" / jeton.DEFTER_ADI
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kayitlar), encoding="utf-8")
    return p


def _yonetici(defter, gonderici=None, sahip="s1", **k):
    return jeton.JetonYoneticisi(
        bakiye_okuyucu=lambda: 10,
        tuketim_gonderici=gonderici or (lambda **kw: True),
        defter_yolu=defter,
        sahip=sahip,
        **k,
    )


# ---------------------------------------------------------------- saf yardımcılar


@pytest.mark.parametrize(
    "deger, beklenen", [("1", True), ("true", True), (" YES ", True), ("On", True), ("0", False), ("hayir", False)]
)
def test_flag_dogruluk_kumesi(monkeypatch, deger, beklenen):
    """`_flag`: yalnız 1/true/yes/on (büyük-küçük harf ve boşluk duyarsız) açık; başka her şey kapalı."""
    monkeypatch.setenv("PEMF_KP2_BAYRAK", deger)
    assert jeton._flag("PEMF_KP2_BAYRAK") is beklenen


def test_flag_degisken_YOKKEN_varsayilan(monkeypatch):
    monkeypatch.delenv("PEMF_KP2_BAYRAK", raising=False)
    assert jeton._flag("PEMF_KP2_BAYRAK") is False
    assert jeton._flag("PEMF_KP2_BAYRAK", True) is True


def test_canli_oturum_SON_kareden_4_saat_sonra_UNUTULUR_yeni_nesil_alir(monkeypatch):
    monkeypatch.setattr(jeton, "_canli_oturumlar", {})
    assert jeton._canli_kova("s", "oturumA", simdi=0.0) == 0
    assert jeton._canli_kova("s", "oturumA", simdi=125.0) == 2
    eski_nesil = jeton._canli_oturumlar[("s", "oturumA")]["nesil"]
    # başka bir oturumun karesi 4 sa + 1 sn sonra: A unutulur
    jeton._canli_kova("s", "oturumB", simdi=125.0 + 4 * 3600 + 1)
    assert ("s", "oturumA") not in jeton._canli_oturumlar
    assert jeton._canli_kova("s", "oturumA", simdi=125.0 + 4 * 3600 + 2) == 0
    assert jeton._canli_oturumlar[("s", "oturumA")]["nesil"] != eski_nesil


@pytest.mark.parametrize(
    "veri",
    [
        None,
        "metin",
        {"status": "error", "detected": False},
        {"detected": False},
        {"status": "success", "cat_count": "iki"},
        {"status": "success", "cat_count": None},
    ],
)
def test_sonucsuz_mu_basarisiz_ya_da_bozuk_sayi_SONUCSUZ_DEGIL(veri):
    """Başarısız yanıt / sözlük olmayan / sayıya çevrilemeyen `cat_count` → sonuçsuz sayılmaz (ücret kuralı değişmez)."""
    assert jeton.sonucsuz_mu(veri) is False


def test_sonuc_izle_govdesi_cozulemeyen_yanit_AYNEN_doner_isaret_KONMAZ():
    class _Yanit2:
        body = b"\xff\xfe json degil"

    yanit = _Yanit2()

    async def _uc():
        return yanit

    sarili = jeton.sonuc_izle(_uc)

    async def _kos():
        jeton._SONUC_YOK.set(False)
        r = await sarili()
        return r, jeton._SONUC_YOK.get()

    r, isaret = asyncio.run(_kos())
    assert r is yanit
    assert isaret is False


def test_kesin_red_nesnesi_YANLIS_degerli_ve_adini_soyler():
    assert not jeton.TUKETIM_REDDEDILDI
    assert repr(jeton.TUKETIM_REDDEDILDI) == "TUKETIM_REDDEDILDI"


def test_rezervli_tuketici_ISTISNADA_ayrimi_BIRAKIR_ve_istisnayi_yukseltir(monkeypatch):
    monkeypatch.setattr(jeton, "_rezervler", {})
    assert jeton._rezerve_et("sahip:x", "r1", 1, kalan=1, okuma_ani=0.0) is True
    assert jeton._rezerve_et("sahip:x", "r2", 1, kalan=1, okuma_ani=0.0) is False  # tek jeton ayrıldı

    def _patlar():
        raise ConnectionError("gonderim koptu")

    t = jeton._RezervliTuketici(_patlar, "sahip:x", "r1")
    with pytest.raises(ConnectionError):
        t()
    assert "r1" not in jeton._rezervler["sahip:x"]
    assert jeton._rezerve_et("sahip:x", "r2", 1, kalan=1, okuma_ani=0.0) is True  # bırakılan jeton yeniden ayrılabilir


def test_tuketmeden_birak_birak_ISTISNASI_yutulur():
    cagri = []

    class _T:
        def birak(self):
            cagri.append(1)
            raise RuntimeError("birakilamadi")

    jeton._tuketmeden_birak(_T())
    jeton._tuketmeden_birak(object())  # birak yok → no-op
    assert cagri == [1]


# ---------------------------------------------------------------- eski defter taşıması (Y202)


def test_eski_defter_tasindi_ama_eski_ad_SILINEMEDI_icerik_yeni_konumda_uyari(tmp_path, monkeypatch, caplog):
    eski = tmp_path / "eski" / jeton.DEFTER_ADI
    yeni = tmp_path / "yeni" / jeton.DEFTER_ADI
    eski.parent.mkdir()
    yeni.parent.mkdir()
    eski.write_text('[{"istek_id": "a1", "miktar": 1}]', encoding="utf-8")
    gercek_unlink = pathlib.Path.unlink

    def _unlink(self, *a, **k):
        if self == eski:
            raise PermissionError(13, "Dosya baska bir islem tarafindan kullaniliyor", str(self))
        return gercek_unlink(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "unlink", _unlink)
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        assert jeton._eski_defteri_tasi_bir_kez(eski, yeni) == yeni
    assert yeni.read_text(encoding="utf-8") == '[{"istek_id": "a1", "miktar": 1}]'
    assert eski.exists()
    assert "eski adı silinemedi" in caplog.text


def test_yeni_konum_OKUNAMAZSA_eski_defter_AYNI_sayilmaz_SILINMEZ(tmp_path, caplog):
    eski = tmp_path / jeton.DEFTER_ADI
    eski.write_text("[]", encoding="utf-8")
    yeni = tmp_path / "PEMF_GUI" / jeton.DEFTER_ADI
    yeni.mkdir(parents=True)  # yeni ad bir DİZİN → okunamaz
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        assert jeton._eski_defteri_tasi_bir_kez(eski, yeni) == yeni
    assert eski.read_text(encoding="utf-8") == "[]"
    assert "İKİ konumda" in caplog.text
    assert jeton._ayni_defter(tmp_path / "yok1", tmp_path / "yok2") is False


# ---------------------------------------------------------------- defter G/Ç


def test_bozuk_miktarli_kayit_yolda_kalana_0_katar(tmp_path):
    d = tmp_path / "d.json"
    d.write_text(
        json.dumps(
            [
                {"istek_id": "1", "miktar": "iki", "sahip": "s1"},
                {"istek_id": "2", "miktar": 3, "sahip": "s1"},
                {"istek_id": "3", "miktar": [1], "sahip": "s1"},
                {"istek_id": "4", "miktar": 5, "sahip": "s2"},
            ]
        ),
        encoding="utf-8",
    )
    assert _yonetici(d).sahibin_yolda_kalani() == 3


def test_defter_OKUNAMAZSA_bos_ve_uyari(tmp_path, caplog):
    d = tmp_path / "defter_dizin"
    d.mkdir()
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        assert _yonetici(d).bekleyen_tuketim_sayisi() == 0
    assert "defteri okunamadı" in caplog.text


def test_bozuk_defter_karantina_dosyasi_YAZILAMAZSA_yine_bos_ve_HATA_gunlugu(tmp_path, caplog):
    d = tmp_path / "d.json"
    d.write_text("[{yarim", encoding="utf-8")
    (tmp_path / ("d.json" + jeton.DEFTER_KARANTINA_EKI)).mkdir()  # karantina adı dizin → eklenemez
    with caplog.at_level(logging.ERROR, logger=jeton.logger.name):
        assert _yonetici(d).bekleyen_tuketim_sayisi() == 0
    assert "defteri BOZUK" in caplog.text
    assert d.read_text(encoding="utf-8") == "[{yarim"


def test_defter_YAZILAMAZSA_uyari_eski_defter_BOZULMAZ_gecici_temizlenemese_de_fırlatmaz(tmp_path, caplog):
    d = tmp_path / "d.json"
    d.write_text('[{"istek_id": "eski", "miktar": 1, "sahip": "s1"}]', encoding="utf-8")
    (tmp_path / ("d.json" + jeton.DEFTER_GECICI_EKI)).mkdir()  # geçici ad dizin → yazım VE silme düşer
    y = _yonetici(d, gonderici=lambda **k: False)
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        k = y._tuket(1, "goruntu", "yeni-istek", None, tur="analiz")
    assert k.izinli and k.jeton_harcandi == 1
    assert "defteri yazılamadı" in caplog.text
    assert json.loads(d.read_text(encoding="utf-8")) == [{"istek_id": "eski", "miktar": 1, "sahip": "s1"}]


def test_gonderici_ISTISNASI_kaydi_deftere_yazar_ayni_istek_IKINCI_kez_yazilmaz(tmp_path):
    d = tmp_path / "d.json"

    def _patlar(**k):
        raise ConnectionError("ag koptu")

    y = _yonetici(d, gonderici=_patlar)
    for _ in range(2):
        k = y._tuket(3, "agir_arastirma", "istek-1", "cihaz-9", tur="analiz")
        assert k.sebep == "tuketildi" and k.jeton_harcandi == 3
    assert json.loads(d.read_text(encoding="utf-8")) == [
        {
            "istek_id": "istek-1",
            "miktar": 3,
            "tur": "analiz",
            "detay": "agir_arastirma",
            "cihaz_id": "cihaz-9",
            "sahip": "s1",
        }
    ]


def test_uzlastirma_bos_defterde_0_gondericiye_GITMEZ(tmp_path):
    cagri = []
    assert _yonetici(tmp_path / "yok.json", gonderici=lambda **k: cagri.append(k) or True).bekleyenleri_uzlastir() == 0
    assert cagri == []


def test_uzlastirmada_gonderici_ISTISNASI_kaydi_SILMEZ(tmp_path):
    d = tmp_path / "d.json"
    kayitlar = [{"istek_id": "a", "miktar": 1, "sahip": "s1"}, {"istek_id": "b", "miktar": 1, "sahip": "s1"}]
    d.write_text(json.dumps(kayitlar), encoding="utf-8")

    def _gonder(**k):
        if k["istek_id"] == "a":
            raise TimeoutError("zaman asimi")
        return True

    assert _yonetici(d, gonderici=_gonder).bekleyenleri_uzlastir() == 1
    assert json.loads(d.read_text(encoding="utf-8")) == [{"istek_id": "a", "miktar": 1, "sahip": "s1"}]


# ---------------------------------------------------------------- Supabase taşıma katmanı


@pytest.mark.parametrize("eksik", ["supabase_url", "supabase_anon_key", "token"])
def test_bakiye_okuma_yapilandirma_ya_da_jeton_YOKSA_ConnectionError_aga_CIKMAZ(supabase, eksik):
    if eksik != "token":
        supabase.ayar[eksik] = ""
    with pytest.raises(ConnectionError, match="yapilandirmasi/token yok"):
        jeton._bakiye_satiri_oku("" if eksik == "token" else "tok")
    assert supabase.cagrilar == []


@pytest.mark.parametrize("govde", [[], None, {"hata": "liste degil"}])
def test_bakiye_satiri_YOKSA_sifir_bakiye_on_odemeli(supabase, govde):
    supabase.yanitlar.append(_Yanit(govde))
    assert jeton._bakiye_satiri_oku("tok") == {
        "aylik_hak": 0,
        "satin_alinan": 0,
        "odeme_modeli": "on_odemeli",
        "kullandikca_borc": 0,
    }
    c = supabase.cagrilar[0]
    assert c["url"] == "https://ornek.supabase.test/rest/v1/rpc/jeton_bakiyem"
    assert c["headers"]["Authorization"] == "Bearer tok" and c["headers"]["apikey"] == "anon-ornek"


def test_tuketim_gonderimi_yapilandirma_YOKSA_False_aga_CIKMAZ(supabase):
    supabase.ayar["supabase_anon_key"] = ""
    assert jeton._tuketim_gonder_canli("tok", miktar=1, istek_id="x") is False
    supabase.ayar["supabase_anon_key"] = "anon-ornek"
    assert jeton._tuketim_gonder_canli("", miktar=1, istek_id="x") is False
    assert supabase.cagrilar == []


def test_tuketim_gonderimi_AG_ISTISNASINDA_False(supabase):
    supabase.yanitlar.append(ConnectionError("baglanti reddedildi"))
    assert (
        jeton._tuketim_gonder_canli("tok", miktar=2, tur="analiz", detay="goruntu", istek_id="i-1", cihaz_id="c")
        is False
    )
    assert supabase.cagrilar[0]["json"] == {
        "p_miktar": 2,
        "p_tur": "analiz",
        "p_detay": "goruntu",
        "p_istek_id": "i-1",
        "p_cihaz_id": "c",
    }


# ---------------------------------------------------------------- uzlaştırma tetikleyicisi


def test_uzlastirma_tetigi_defter_kurulamazsa_False_FIRLATMAZ(tmp_path, monkeypatch):
    dosya = tmp_path / "kok_dosya"
    dosya.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(dosya))  # veri kökü bir DOSYA → defter dizini kurulamaz
    monkeypatch.setattr(jeton, "_son_uzlastirma", None)
    assert jeton._uzlastirmayi_tetikle(_jwt("u1")) is False
    assert jeton._son_uzlastirma is None
    assert jeton._UZLASTIRMA_TEK_UCUS.acquire(blocking=False)
    jeton._UZLASTIRMA_TEK_UCUS.release()


def test_uzlastirma_ipligi_BASLATILAMAZSA_False_kilit_BIRAKILIR_kayit_DURUR(kok, monkeypatch, caplog):
    sahip = jeton._jwt_sahip(_jwt("u1"))
    p = _defteri_yaz(kok, [{"istek_id": "a", "miktar": 1, "sahip": sahip}])

    class _BaslamayanIplik:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading, "Thread", _BaslamayanIplik)
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        assert jeton._uzlastirmayi_tetikle(_jwt("u1")) is False
    monkeypatch.setattr(jeton, "_son_uzlastirma", None)
    assert "ipliği başlatılamadı" in caplog.text
    assert jeton._UZLASTIRMA_TEK_UCUS.acquire(blocking=False), "tek-uçuş kilidi bırakılmalıydı"
    jeton._UZLASTIRMA_TEK_UCUS.release()
    assert json.loads(p.read_text(encoding="utf-8")) == [{"istek_id": "a", "miktar": 1, "sahip": sahip}]


def test_uzlastirma_ipligi_beklenmedik_HATADA_kayit_DEFTERDE_kalir_kilit_birakilir(kok, supabase, caplog):
    """Defterde kimliği hash'lenemeyen (liste) bozuk kayıt: gönderim başarılı döner ama ayıklama TypeError ile düşer → iplik uyarı
    yazar, defter DEĞİŞMEZ, tek-uçuş kilidi bırakılır."""
    sahip = jeton._jwt_sahip(_jwt("u1"))
    kayitlar = [{"istek_id": ["bozuk"], "miktar": 1, "sahip": sahip}]
    p = _defteri_yaz(kok, kayitlar)
    supabase.yanitlar.append(_Yanit({"ok": True}))
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        assert jeton._uzlastirmayi_tetikle(_jwt("u1")) is True
        jeton._son_uzlastirma.join(timeout=10)
    assert not jeton._son_uzlastirma.is_alive()
    assert "uzlaştırması düştü" in caplog.text
    assert json.loads(p.read_text(encoding="utf-8")) == kayitlar
    assert jeton._UZLASTIRMA_TEK_UCUS.acquire(blocking=False)
    jeton._UZLASTIRMA_TEK_UCUS.release()


def test_bozuk_defter_KAYDI_karari_ENGELLEMEZ_yolda_kalan_0_sayilir(kok, supabase, monkeypatch):
    """Defterde sözlük olmayan kayıt (yolda kalan ölçülemez) → yolda kalan 0; bakiye 1 iken analiz İZİNLİ (402 değil)."""
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(jeton, "_rezervler", {})
    _defteri_yaz(kok, ["bozuk-kayit"])
    supabase.yanitlar.append(_Yanit([{"aylik_hak": 1, "satin_alinan": 0, "odeme_modeli": "on_odemeli"}]))
    tuketici = jeton._jeton_on_karari(_Istek("u1"))
    assert tuketici is not None
    assert [c["url"].rsplit("/", 1)[-1] for c in supabase.cagrilar] == ["jeton_bakiyem"]
    tuketici.birak()


def test_bakiye_ozeti_defter_OLCULEMEZSE_bekleyen_0_bakiye_yine_gosterilir(tmp_path, supabase, monkeypatch):
    dosya = tmp_path / "kok_dosya"
    dosya.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(dosya))
    monkeypatch.setattr(jeton, "JETON_ENFORCED", True)
    monkeypatch.setattr(jeton, "_son_uzlastirma", None)
    supabase.yanitlar.append(_Yanit([{"aylik_hak": 4, "satin_alinan": 2, "odeme_modeli": "on_odemeli"}]))
    ozet = jeton.bakiye_ozeti(_Istek("u1"))
    assert ozet["etkin"] is True and ozet["bilinmiyor"] is False
    assert ozet["bekleyen"] == 0 and ozet["kalan"] == 6 and ozet["aylikHak"] == 4 and ozet["satinAlinan"] == 2


# ---------------------------------------------------------------- tüketim bağımlılığı (jeton_tuketimi)


async def _surdur(istek):
    gen = jeton.jeton_tuketimi(istek)
    await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


def test_kopma_sorusu_YANITLANAMAZSA_analiz_teslim_sayilir_tuketim_YAPILIR(monkeypatch):
    istek = _Istek("u1")
    cagri = []
    setattr(istek.state, jeton._BEKLEYEN_TUKETIM, lambda: cagri.append("tuketildi"))

    async def _kopuk_mu():
        raise RuntimeError("receive kanali kapali")

    istek.is_disconnected = _kopuk_mu
    asyncio.run(_surdur(istek))
    assert cagri == ["tuketildi"]
    assert getattr(istek.state, jeton._BEKLEYEN_TUKETIM) is None


def test_tuketim_ISTISNASI_yanit_akisini_BOZMAZ_uyari_yazilir(caplog):
    istek = _Istek("u1")

    def _patlar():
        raise OSError("defter diski dolu")

    setattr(istek.state, jeton._BEKLEYEN_TUKETIM, _patlar)

    async def _bagli():
        return False

    async def _receive():
        return {"type": "http.request"}

    istek.is_disconnected = _bagli
    istek.receive = _receive
    with caplog.at_level(logging.WARNING, logger=jeton.logger.name):
        asyncio.run(_surdur(istek))
    assert "tüketim kaydedilemedi" in caplog.text
