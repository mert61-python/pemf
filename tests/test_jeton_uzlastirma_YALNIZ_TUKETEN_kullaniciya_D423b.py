# -*- coding: utf-8 -*-
"""D4.23 eki (Y24) — çevrimdışı tüketim YALNIZ onu tüketen kullanıcının bakiyesinden uzlaşır.

ARIZA (D4.23 `38ff3cbf`'in kendi açığı, 4-B kapanışında fark edildi): çevrimdışı defter CİHAZ-GENELİ (`PEMF_DATA_DIR/jeton_bekleyen.json`) ve
kayıtlar kullanıcı kimliği taşımıyordu; arka plan uzlaştırması ise "bağlantı döndü" anındaki İSTEĞİN jetonuyla (RPC `auth.uid()`) gönderiyordu →
aynı cihazda iki Supabase hesabı varsa A'nın çevrimdışı analizleri B'nin bakiyesinden düşerdi. Zorlama bugün KAPALI (`PEMF_JETON_ENFORCED=0`) —
canlı etki yok; zorlama açılmadan önce kapanmalı.

Ölçüm: GERÇEK `_jeton_kapisi_karari` (gönderilemeyen düşüm deftere düşer) ve GERÇEK `bakiye_ozeti` (bağlantı döner → uzlaştırma) üretim
yolları; Supabase taşıma katmanı sahte (canlı YOK). Kimlik, jetonun JWT gövdesindeki `sub`'dan; test türetmeyi SABİTLEMEZ — yalnız davranışı ölçer.
2026-10-19 (S-4B.5): çevrimdışı analiz kaldırıldı; defter kaydı artık YOLDA KALAN ÖDEME (çevrimiçi karar, düşüm o an gönderilemedi) —
sahibe bağlama sözleşmesi aynen geçerli.
"""

from __future__ import annotations

import base64
import importlib
import json

import pytest


def _jwt(sub: str | None) -> str:
    from jwt_test_anahtari import imzali_jwt  # TA T4: GERÇEK ES256 imza (JWKS doğrulaması)

    govde = {"sub": sub, "role": "authenticated"} if sub else {"role": "authenticated"}
    return imzali_jwt(govde)


class _Istek:
    def __init__(self, token: str, yol: str = "/api/jeton/bakiye"):
        self.headers = {"authorization": f"Bearer {token}"}
        self.url = type("U", (), {"path": yol})()


@pytest.fixture
def j(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    mod = importlib.import_module("servers.jeton")
    monkeypatch.setattr(mod, "JETON_ENFORCED", True)
    monkeypatch.setattr(mod, "_son_uzlastirma", None, raising=False)
    yield mod
    t = getattr(mod, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _yolda_kalan(j, monkeypatch, token: str, adet: int) -> None:
    """`adet` analiz çevrimiçi karar alır ve teslim edilir; düşüm ağ kopukluğuyla gönderilemez → defterde sahipli yolda kalan ödeme.
    Bu sırada uzlaştırma tetiklenmez (sonraki "bağlantı döndü" anı testin kendisi)."""
    gercek_tetik = j._uzlastirmayi_tetikle
    monkeypatch.setattr(j, "_uzlastirmayi_tetikle", lambda _t: False)
    monkeypatch.setattr(
        j, "_bakiye_satiri_oku", lambda _t: {"aylik_hak": 10, "satin_alinan": 0, "odeme_modeli": "on_odemeli"}
    )
    monkeypatch.setattr(j, "_tuketim_gonder_canli", lambda token, **k: False)
    for _ in range(adet):
        j._jeton_kapisi_karari(_Istek(token, "/api/ai/vision/wound"))  # karar + teslim; düşüm gönderilemez → deftere
    monkeypatch.setattr(j, "_uzlastirmayi_tetikle", gercek_tetik)


def _cevrimici(j, monkeypatch, gonderilen: list) -> None:
    monkeypatch.setattr(
        j, "_bakiye_satiri_oku", lambda _t: {"aylik_hak": 10, "satin_alinan": 0, "odeme_modeli": "on_odemeli"}
    )
    monkeypatch.setattr(
        j, "_tuketim_gonder_canli", lambda token, **k: gonderilen.append((token, k.get("istek_id"))) or True
    )


def _bitir(j) -> bool:
    t = getattr(j, "_son_uzlastirma", None)
    if t is None:
        return False
    t.join(timeout=10)
    assert not t.is_alive()
    return True


def _defter(j) -> list:
    yol = j._defter_yolu()
    return json.loads(yol.read_text(encoding="utf-8") or "[]") if yol.exists() else []


def test_KRITIK_A_nin_yolda_kalan_odemesi_B_nin_jetonuyla_GONDERILMEZ(j, monkeypatch):
    a, b = _jwt("kullanici-A"), _jwt("kullanici-B")
    _yolda_kalan(j, monkeypatch, a, 2)
    assert len(_defter(j)) == 2, "gönderilemeyen düşüm deftere düşmedi (vakum)"
    gonderilen: list = []
    _cevrimici(j, monkeypatch, gonderilen)
    j.bakiye_ozeti(_Istek(b))
    _bitir(j)
    yanlis = [i for t, i in gonderilen if t == b]
    assert not yanlis, f"A'nın yolda kalan ödemesi B'nin jetonuyla (B'nin bakiyesinden) düşürüldü: {yanlis}"
    assert len(_defter(j)) == 2, "A'nın kayıtları B'nin bağlantısında defterden SİLİNDİ"


def test_KRITIK_A_baglaninca_KENDI_kayitlari_uzlasir(j, monkeypatch):
    a, b = _jwt("kullanici-A"), _jwt("kullanici-B")
    _yolda_kalan(j, monkeypatch, a, 2)
    _yolda_kalan(j, monkeypatch, b, 1)
    gonderilen: list = []
    _cevrimici(j, monkeypatch, gonderilen)
    j.bakiye_ozeti(_Istek(a))
    assert _bitir(j), "A bağlandığı hâlde uzlaştırma başlamadı"
    assert [t for t, _ in gonderilen] == [a, a], f"A'nın iki kaydı A'nın jetonuyla gitmeli: {gonderilen}"
    assert len(_defter(j)) == 1, "yalnız B'nin kaydı kalmalı"


def test_KRITIK_bekleyen_sayisi_KULLANICIYA_ozel(j, monkeypatch):
    a, b = _jwt("kullanici-A"), _jwt("kullanici-B")
    _yolda_kalan(j, monkeypatch, a, 3)
    _yolda_kalan(j, monkeypatch, b, 1)
    assert j.bakiye_ozeti(_Istek(b)).get("bekleyen") == 1, (
        "B'nin ekranı A'nın yolda kalan ödemesini de 'bekleyen' gösteriyor"
    )


def test_KARSIT_kimligi_cozulemeyen_jetonla_uzlastirma_DENENMEZ(j, monkeypatch):
    a = _jwt("kullanici-A")
    _yolda_kalan(j, monkeypatch, a, 1)
    # Sahibi bilinmeyen (eski) kayıt. 4B-1.5'ten beri jetonsuz istek kayıt ÜRETMEZ (402); defterde kalmış olabilecek eski kayıt elle konur.
    k = _defter(j)
    k.append(
        {
            "istek_id": "sahipsiz-eski-1",
            "miktar": 1,
            "tur": "analiz",
            "detay": "goruntu",
            "cihaz_id": None,
            "sahip": None,
        }
    )
    j._defter_yolu().write_text(json.dumps(k), encoding="utf-8")
    gonderilen: list = []
    _cevrimici(j, monkeypatch, gonderilen)
    j.bakiye_ozeti(_Istek(_jwt(None)))
    _bitir(j)
    assert not gonderilen and len(_defter(j)) == 2, f"kimliği çözülemeyen jetonla kayıt gönderildi: {gonderilen}"
