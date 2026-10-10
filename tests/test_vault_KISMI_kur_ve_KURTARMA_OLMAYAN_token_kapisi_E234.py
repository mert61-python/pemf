# -*- coding: utf-8 -*-
"""E2-3.4 (2-E incelemesi A3) — D2.E05 kapısının KÖR kolları: KISMİ `--kur` başarısı, yetkili ama KURTARMA OLMAYAN token, Y86'nın
"işe yaramayan token → BAŞARISIZ" ifadesi.

Ürün HEAD'de doğru (ölçüldü), ama 2-E'nin kapısı (`test_vault_emanet_KUR_rc_ve_TATBIKAT_kurtarma_tokeni_D2E05.py`) şu mutantlarda
YEŞİL kaldı (2-E incelemesi A3, 2-E incelemesi kaydı):
  k1a  `_kurtarma_tokeni` politika denetimi yalnız `root`a bakar (`pemf-kurtarma` şartı düşer) → kapı YEŞİL
  k1b  `--kur` denetim adımının hatası SAYILMAZ                                              → kapı YEŞİL
  k1c  `lookup-self` 403 dalı düşer (iptal token'a "SINANMADI — kurtarma token'i DEGIL" der)   → kapı YEŞİL
Nedeni: kapının `--kur` kolları ÜÇ adımı birden düşürür (403 / kapalı) — tek adımın sayılmaması görünmez; sahte Vault her
tanınan kök-dışı token'a `pemf-kurtarma` politikası verir — kurtarma politikasız ama emaneti okuyabilen (ör. yönetici) token
modellenmez; iptal kolu yalnız "BASARILI değil" der, Y86'nın "BAŞARISIZ" sözünü sabitlemez.

Kapı: betiğin KENDİ `main()`i (süreç içi), loopback rastgele portta tablo-güdümlü küçük sahte Vault (yasaklı portlar reddedilir).
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from betik_alt_sureci import betik_modulu

KOK = "kok-sahte-e234"
YONETICI = "yonetici-sahte-e234"
IPTAL = "iptal-sahte-e234"
YASAK = {8000, 8100, 1883, 5173, 8177, 8200}
EMANET = "/v1/pemf/data/klinik/hasta-anahtari"


class _Vault:
    """`dusen`: (yöntem, yol) → bu adım 500 döner; öteki adımlar başarılı. Token sınıfı kaydedilir (değer değil)."""

    def __init__(self, dusen: tuple[str, str] | None = None):
        self.dusen, self.istekler = dusen, []

    def __enter__(self):
        vault = self

        class _I(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _yanit(self, kod, veri=None):
                ham = json.dumps(veri).encode() if veri is not None else b""
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(ham)))
                self.end_headers()
                if ham:
                    self.wfile.write(ham)

            def _isle(self, y):
                yol = self.path.split("?", 1)[0]
                tok = self.headers.get("X-Vault-Token")
                sinif = {KOK: "kok", YONETICI: "yonetici", IPTAL: "iptal"}.get(tok, "yok" if not tok else "bilinmeyen")
                vault.istekler.append((y, yol, sinif))
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                if (y, yol) == vault.dusen:
                    return self._yanit(500, {"errors": ["sahte adim hatasi"]})
                if sinif in ("iptal", "yok", "bilinmeyen"):
                    return self._yanit(403, {"errors": ["permission denied"]})
                if yol == "/v1/auth/token/lookup-self":
                    pol = ["root"] if sinif == "kok" else ["default", "pemf-yonetici"]
                    return self._yanit(200, {"data": {"policies": pol, "ttl": 0}})
                if yol == EMANET and y == "GET":  # yönetici politikası emaneti OKUYABİLİR (kurtarma politikası DEĞİL)
                    return self._yanit(200, {"data": {"data": {"auto.sqlcipher_key": "x"}, "metadata": {"version": 1}}})
                if sinif != "kok":
                    return self._yanit(403, {"errors": ["permission denied"]})
                if (y, yol) in (("GET", "/v1/sys/mounts"), ("GET", "/v1/sys/audit")):
                    return self._yanit(200, {})
                if y in ("POST", "PUT"):
                    return self._yanit(204)
                return self._yanit(404, {"errors": []})

            def do_GET(self):
                self._isle("GET")

            def do_POST(self):
                self._isle("POST")

            def do_PUT(self):
                self._isle("PUT")

        for _ in range(20):
            self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _I)
            if self.srv.server_address[1] not in YASAK:
                break
            self.srv.server_close()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()

    @property
    def adres(self):
        return f"http://127.0.0.1:{self.srv.server_address[1]}"


@pytest.fixture()
def ve(tmp_path, monkeypatch):
    for ad in ("PROGRAMDATA", "APPDATA"):
        (tmp_path / ad.lower()).mkdir()
        monkeypatch.setenv(ad, str(tmp_path / ad.lower()))
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "veri"))
    m = betik_modulu("vault_emanet")
    dosya = tmp_path / "pemf-vault-kurtarma.json"
    dosya.write_text(json.dumps({"root_token": KOK, "keys_base64": ["sahte"]}), encoding="utf-8")
    monkeypatch.setattr(m, "KURTARMA_DOSYASI", dosya)
    return m


def _kos(m, monkeypatch, capsys, adres, *arg):
    monkeypatch.setattr(m, "ADRES", adres)
    monkeypatch.setattr(m, "_KURTARMA_TOKENI", None, raising=False)
    monkeypatch.setattr(sys, "argv", ["vault_emanet.py", *arg])
    mesaj = ""
    try:
        rc = m.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        mesaj = "" if isinstance(e.code, int) or e.code is None else str(e.code)
    c = capsys.readouterr()
    return rc, c.out + c.err + mesaj


@pytest.mark.parametrize(
    "dusen",
    [("POST", "/v1/sys/mounts/pemf"), ("POST", "/v1/sys/audit/file"), ("PUT", "/v1/sys/policies/acl/pemf-kurtarma")],
    ids=["kv_mount", "denetim", "politika"],
)
def test_KRITIK_kur_TEK_adim_duserse_cikis_1_E234(ve, monkeypatch, capsys, dusen):
    with _Vault(dusen=dusen) as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--kur")
    assert any((y, p) == dusen for y, p, _s in v.istekler), f"aparat: düşen adım hiç denenmedi: {v.istekler}"
    assert "HATA 500" in cikti, f"aparat: adım hatası basılmadı: {cikti[-400:]}"
    assert rc != 0 and "KURULUM EKSIK" in cikti, f"yalnız {dusen} düştü ama --kur çıkış kodu {rc}:\n{cikti[-400:]}"


def test_KRITIK_tatbikat_KURTARMA_POLITIKASIZ_yetkili_token_SINANMADI_emanet_okunmaz_E234(ve, monkeypatch, capsys):
    with _Vault() as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", YONETICI)
    assert "TATBIKAT BASARILI" not in cikti and "SINANMADI" in cikti, cikti[-500:]
    assert rc != 0
    assert not [i for i in v.istekler if i[1] == EMANET], f"kurtarma OLMAYAN token'la emanet okundu: {v.istekler}"


def test_KRITIK_tatbikat_IPTAL_token_Y86_BASARISIZ_der_E234(ve, monkeypatch, capsys):
    with _Vault() as v:
        rc, cikti = _kos(ve, monkeypatch, capsys, v.adres, "--tatbikat", "--token", IPTAL)
    assert rc != 0 and "TATBIKAT BASARISIZ" in cikti, (
        f"Y86: işe yaramayan kurtarma token'ı → 'BASARISIZ' denmeli:\n{cikti[-500:]}"
    )
