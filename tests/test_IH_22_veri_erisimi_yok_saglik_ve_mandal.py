# -*- coding: utf-8 -*-
"""T2Y #22 (Y275, istem 46 · 2c) — İKİNCİ WINDOWS HESABI veri köküne / sırlara ERİŞEMEZKEN backend nedeni SÖYLER, ACİL DURDUR mandalı
güvenli tarafta kalır.

ÖLÇÜLEN (11 Kasım, ikinci yerel hesap `Şükrü`, KD runtime): `pemf_secrets.json OKUNAMADI (PermissionError)` → hasta + tedavi DB'si
açılmıyor; `/api/health` `dbSebep` "… açılamadı (RuntimeError). … cihazı yeniden başlatın, … teknik desteğe başvurun" diyordu (iki kez,
eylemi YANLIŞ: yeniden başlatmak düzeltmez); "ACIL DURDUR mandal kaliciligi kurulamadi" yalnız günlükteydi — `kalicilik_kur` dosyanın
VARLIĞINI denetlerken İZİN hatası fırlatıp "okunamayan dosya → KURULU" kuralını (Y46) ve açılış bildirimini (Y64) atlıyordu;
`/api/system/recovery-status` yakalanmamış `PermissionError` ile 500 dönüyordu.

Ölçüm GERÇEK ACL ile (bu hesabın kendi geçici dizininde RET; test sonunda kaldırılır) — erişim reddi taklit EDİLMEZ. Windows dışında atlanır
(ACL yok); saf sınıflandırma kolları her yerde koşar.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import types

import pytest

_WIN = pytest.mark.skipif(os.name != "nt", reason="Windows ACL")
TR = "Bu Windows hesabının PEMF verisine erişimi yok — başlatıcıdaki paylaşım kartıyla erişim verin."
EN = "This Windows account has no access to the PEMF data — grant access with the sharing card in the launcher."


def _sid() -> str:
    c = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace", check=True
    )
    return c.stdout.strip().split(",")[-1].strip('"')


class _Ret:
    """`kok` dizinine (ve mirasla içindekilere) bu hesaba RET (oku + yaz); çıkışta kaldırılır (tmp silinebilsin)."""

    def __init__(self, kok):
        self.kok, self.sid = kok, _sid()

    def __enter__(self):
        subprocess.run(
            ["icacls", str(self.kok), "/deny", f"*{self.sid}:(OI)(CI)(RX,W)", "/C", "/Q"],
            check=True,
            capture_output=True,
        )
        with pytest.raises(PermissionError):
            os.listdir(self.kok)  # ret uygulanmadıysa ölçüm geçersiz
        return self

    def __exit__(self, *a):
        subprocess.run(["icacls", str(self.kok), "/remove:d", f"*{self.sid}", "/T", "/C", "/Q"], capture_output=True)


def _gercek_ret_zinciri(kok):
    """Sırlar dosyası okunamayınca ürünün kurduğu zincirin biçimi: RuntimeError ← PermissionError (gerçek WinError 5)."""
    try:
        (kok / "pemf_secrets.json").read_bytes()
    except PermissionError as e:
        try:
            raise RuntimeError("patient_fernet_key okunamadi/yazilamadi (PermissionError)") from e
        except RuntimeError as r:
            return r
    raise AssertionError("ret uygulanmadı")


def _cekirdek(kok):
    return types.SimpleNamespace(
        db_acilis_hatalari={},
        db_acilis_ayrintilari={},
        app_data_dir=kok,
        logger=logging.getLogger("ih22"),
        stm_is_connected=False,
        stm_uyumlu=None,
    )


def _ac_hata_ile(exc):
    def _ac():
        raise exc

    return _ac


@_WIN
def test_KRITIK_ERISIM_REDDI_saglikta_EYLEM_soyleyen_TEK_cumle_TR_ve_EN(monkeypatch, tmp_path):
    """MUTASYON: sınıflandırma kaldırılırsa (her hata "açılamadı") ya da tekilleştirme kaldırılırsa KIRMIZI."""
    from fastapi.testclient import TestClient
    from headless_core import HeadlessCore
    from servers import api_server as api

    kok = tmp_path / "PEMF_GUI"
    kok.mkdir()
    (kok / "pemf_secrets.json").write_text("{}", encoding="utf-8")
    cekirdek = _cekirdek(kok)
    with _Ret(kok):
        for ad in ("hasta", "tedavi"):
            assert HeadlessCore._db_ac(cekirdek, ad, _ac_hata_ile(_gercek_ret_zinciri(kok))) is None
    assert cekirdek.db_acilis_ayrintilari["hasta"][0] == "erisimYok", cekirdek.db_acilis_ayrintilari
    assert cekirdek.db_acilis_hatalari["hasta"] == TR, "durum alanı (Türkçe) eylemi söylemiyor"
    monkeypatch.setattr(api.state, "core", cekirdek)
    monkeypatch.setattr(api, "_app_data_dir", lambda: kok)
    c = TestClient(api.app, client=("127.0.0.1", 50122))
    for baslik, beklenen in (({}, TR), ({"X-PEMF-Dil": "en"}, EN)):
        r = c.get("/api/health", headers=baslik)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["dbReady"] is False, j
        assert j["dbSebep"] == beklenen, f"neden tek cümle ve eylemli değil: {j['dbSebep']!r}"


@_WIN
def test_dosya_KILIDI_erisim_yok_SAYILMAZ_eski_metin_kalir(tmp_path):
    """Paylaşım ihlali (WinError 32: virüs tarayıcı / yedekleme dosyayı tutuyor) da `PermissionError`dır ama hesabın ERİŞİMİ VAR —
    "paylaşım kartıyla erişim verin" demek yanlış eylem olurdu."""
    from headless_core import HeadlessCore, izin_hatasi_mi

    kilit = PermissionError(13, "Dosya başka bir işlem tarafından kullanılıyor", None, 32)
    try:
        raise RuntimeError("SQLCipher anahtari okunamadi") from kilit
    except RuntimeError as r:
        zincir = r
    assert not izin_hatasi_mi(zincir)
    cekirdek = _cekirdek(tmp_path)
    HeadlessCore._db_ac(cekirdek, "hasta", _ac_hata_ile(zincir))
    assert cekirdek.db_acilis_ayrintilari["hasta"][0] == "acilamadi"
    assert cekirdek.db_acilis_hatalari["hasta"] != TR
    # `open()` kilidi errno 13 / winerror YOK verir (erişim reddiyle aynı biçim) — veri dizini bu hesapça LİSTELENEBİLİYORSA erişim VAR.
    try:
        raise RuntimeError("SQLCipher anahtari okunamadi") from PermissionError(13, "Permission denied")
    except RuntimeError as r:
        crt = r
    assert izin_hatasi_mi(crt)
    HeadlessCore._db_ac(cekirdek, "tedavi", _ac_hata_ile(crt))
    assert cekirdek.db_acilis_ayrintilari["tedavi"][0] == "acilamadi", (
        "listelenebilen veri dizininde 'erişim yok' dendi"
    )


def test_izin_hatasi_siniflandirmasi_ZINCIR_ve_DONGU_korumasi():
    from headless_core import izin_hatasi_mi

    assert not izin_hatasi_mi(None)
    assert not izin_hatasi_mi(RuntimeError("x"))
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__context__, b.__context__ = b, a  # döngü — sonsuza dek dönmez
    assert not izin_hatasi_mi(a)


@_WIN
def test_KRITIK_mandal_dosyasi_DENETLENEMEZSE_KURULU_ve_ACILISTA_GORUNUR_uyari_STOP_ve_SIFIRLA_aynen(tmp_path):
    """Y46: okunamayan mandal dosyası → mandal KURULU (güvenli taraf); Y64: açılışta ekran bildirimi; bellekteki mandal / Sıfırla AYNEN
    (Y4 yalnız Sıfırla). MUTASYON: `exists()` korumasız → `kalicilik_kur` İZİN hatası fırlatır → KIRMIZI."""
    from utils import estop_mandali as m

    kok = tmp_path / "PEMF_GUI"
    kok.mkdir()
    yol = kok / "estop_mandali.json"
    yol.write_text(json.dumps({"aktif": False}), encoding="utf-8")
    bildirimler: list = []
    eski_kanca = m._yazim_hatasi_kancasi
    m.yazim_hatasi_kancasi_bagla(bildirimler.append)
    try:
        m.sifirla("test-izolasyon")
        with _Ret(kok):
            d = m.kalicilik_kur(yol)  # fırlatmaz
            assert d["aktif"] is True and d["oncekiOturum"] is True, d
            assert m.yazim_durumu()["yazilamadi"] is True
            assert bildirimler and bildirimler[0]["yazilamadi"] is True, f"açılışta görünür uyarı yok: {bildirimler}"
            assert m.sifirla("operator") is True and m.durum()["aktif"] is False, (
                "Sıfırla bellekteki mandalı kaldırmadı"
            )
            m.mandalla("estop")
            assert m.durum()["aktif"] is True, "ACİL DURDUR bellekteki mandalı kurmadı"
    finally:
        m.yazim_hatasi_kancasi_bagla(eski_kanca)
        m.kalicilik_kapat()
        m.sifirla("test-izolasyon")


@_WIN
def test_KRITIK_kurtarma_durumu_ERISIM_YOKKEN_500_DEGIL(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from servers import api_server as api

    kok = tmp_path / "PEMF_GUI"
    kok.mkdir()
    (kok / "KURTARMA-KODU.txt").write_text("kod", encoding="utf-8")
    monkeypatch.setattr(api, "_app_data_dir", lambda: kok)
    c = TestClient(api.app, client=("127.0.0.1", 50124), raise_server_exceptions=False)
    with _Ret(kok):
        r = c.get("/api/system/recovery-status")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert r.json()["codeExists"] is False
