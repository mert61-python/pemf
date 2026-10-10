# -*- coding: utf-8 -*-
"""E2-3.2 (2-E incelemesi A3) — `vault_emanet.py --durum` emaneti / mount'u OKUYAMAYINCA "YOK" demez ve çıkış kodu 1 verir.

D2.E05 `--kur`un "her durumda 0" kusurunu kapattı; `--durum` aynı kusuru taşıyor (ölçüldü): kök token geçersiz / yetkisiz (403),
Vault 500 ya da sağlık ucu 403 iken `--durum` "KV mount : YOK (--kur)" + "EMANET : YOK (--yaz)" basıp **0** ile çıkıyordu —
emanet VARKEN "yok" der (yanlış teşhis), izleyen otomasyon / operatör her şeyi yolunda sanır.

Kapı: betiğin KENDİ `main()`i (süreç içi), loopback'te işletim sisteminin verdiği RASTGELE portta küçük sahte Vault (yasaklı
portlar reddedilir; gerçek Vault gibi sağlık ucu token İSTEMEZ, öteki uçlar yalnız doğru kök token'la 200), sentetik kurtarma
dosyası (tmp_path). Gerçek `~/pemf-vault-kurtarma.json` okunmaz.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from betik_alt_sureci import betik_modulu

KOK = "kok-sahte-e232"
YASAK = {8000, 8100, 1883, 5173, 8177, 8200}
EMANET = "/v1/pemf/data/klinik/hasta-anahtari"


class _MiniVault:
    """`kip`: "saglam" (doğru kök token → mount + emanet VAR) · "500" (sağlık 200, öteki her şey 500) · "saglik_403"."""

    def __init__(self, kip: str = "saglam", emanet_var: bool = True):
        self.kip, self.emanet_var = kip, emanet_var

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

            def do_GET(self):
                yol = self.path.split("?", 1)[0]
                if yol == "/v1/sys/health":
                    if vault.kip == "saglik_403":
                        return self._yanit(403, {"errors": ["permission denied"]})
                    return self._yanit(200, {"initialized": True, "sealed": False, "version": "sahte"})
                if vault.kip in ("500", "saglik_403"):
                    return self._yanit(500 if vault.kip == "500" else 403, {"errors": ["sahte hata"]})
                if self.headers.get("X-Vault-Token") != KOK:
                    return self._yanit(403, {"errors": ["permission denied"]})
                if yol == "/v1/sys/mounts":
                    return self._yanit(200, {"pemf/": {"type": "kv"}})
                if yol == EMANET:
                    if not vault.emanet_var:
                        return self._yanit(404, {"errors": []})
                    return self._yanit(200, {"data": {"data": {"auto.sqlcipher_key": "x"}, "metadata": {"version": 3}}})
                return self._yanit(404, {"errors": []})

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
    return m, dosya


def _durum(m, monkeypatch, capsys, adres: str) -> tuple[int, str]:
    monkeypatch.setattr(m, "ADRES", adres)
    monkeypatch.setattr(sys, "argv", ["vault_emanet.py", "--durum"])
    try:
        rc = m.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    c = capsys.readouterr()
    return rc, c.out + c.err


def test_KRITIK_durum_KOK_TOKEN_GECERSIZken_emanet_VARKEN_YOK_demez_cikis_1_E232(ve, monkeypatch, capsys):
    m, dosya = ve
    dosya.write_text(json.dumps({"root_token": "gecersiz-kok-e232", "keys_base64": ["sahte"]}), encoding="utf-8")
    with _MiniVault() as v:
        rc, cikti = _durum(m, monkeypatch, capsys, v.adres)
    assert "EMANET      : YOK" not in cikti, f"emanet VARKEN (yalnız kök token geçersiz) 'YOK' dedi:\n{cikti}"
    assert rc != 0, f"--durum emaneti OKUYAMADI ama çıkış kodu {rc}:\n{cikti}"


@pytest.mark.parametrize("kip", ["500", "saglik_403"])
def test_KRITIK_durum_VAULT_HATASINDA_cikis_1_YOK_demez_E232(ve, monkeypatch, capsys, kip):
    m, _ = ve
    with _MiniVault(kip=kip) as v:
        rc, cikti = _durum(m, monkeypatch, capsys, v.adres)
    assert rc != 0, f"Vault hata verirken ({kip}) --durum çıkış kodu {rc}:\n{cikti}"
    assert "EMANET      : YOK" not in cikti, f"okunamayan emanet için 'YOK (--yaz)' dedi ({kip}):\n{cikti}"


def test_KARSIT_durum_SAGLAM_vaultta_0_ve_emanet_VAR_E232(ve, monkeypatch, capsys):
    m, _ = ve
    with _MiniVault() as v:
        rc, cikti = _durum(m, monkeypatch, capsys, v.adres)
    assert rc == 0 and "EMANET      : VAR" in cikti and "KV mount    : VAR" in cikti, cikti


def test_KARSIT_durum_emanet_GERCEKTEN_yoksa_YOK_der_0_doner_E232(ve, monkeypatch, capsys):
    m, _ = ve
    with _MiniVault(emanet_var=False) as v:
        rc, cikti = _durum(m, monkeypatch, capsys, v.adres)
    assert rc == 0 and "EMANET      : YOK" in cikti, cikti
