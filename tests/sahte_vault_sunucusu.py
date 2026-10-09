# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SAHTE HashiCorp Vault HTTP ucu — `scripts/vault_emanet.py` kapıları için (D2.14 · D2.E05 · A-84 · Y86).

Gerçek Vault YOK (`vault.exe` indirmek yasak); yalnız betiğin kullandığı KV v2 / sys / token yolları. Loopback'te işletim
sisteminin verdiği RASTGELE yüksek portta dinler; yasaklı portlar (8000/8100/1883/5173/8177/8200) REDDEDİLİR. Her isteğin
yöntemi, yolu ve `X-Vault-Token` SINIFI ("kok" / "kurtarma" / "iptal" / "bilinmeyen" / "yok") kaydedilir — token DEĞERİ
kaydedilmez. Kip `hepsi_403`: her isteğe 403 (yetkisiz kök token / yanlış politika modeli).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

YASAK_PORTLAR = {8000, 8100, 1883, 5173, 8177, 8200}
MOUNT = "pemf"
EMANET_YOLU = "klinik/hasta-anahtari"


def sqlcipher_mod():
    """SQLCipher bağlaması (yoksa None — çağıran kolu atlar)."""
    try:
        from database.sqlcipher_util import import_sqlcipher

        return import_sqlcipher()
    except Exception:
        return None


def sentetik_veri_koku(kok: Path, anahtar: str, fernet: str) -> Path:
    """Sentetik veri kökü (`<kok>/PEMF_GUI`): düz-metin değerli `pemf_secrets.json` + `anahtar`la şifreli iki GERÇEK SQLCipher
    veritabanı (tatbikatın açtığı tablolar). Değerler sentetiktir; gerçek kökler okunmaz."""
    from database.sqlcipher_util import open_encrypted_conn

    mod = sqlcipher_mod()
    veri = kok / "PEMF_GUI"
    veri.mkdir(parents=True, exist_ok=True)
    (veri / "pemf_secrets.json").write_text(
        json.dumps({"auto": {"sqlcipher_key": anahtar, "patient_fernet_key": fernet}}), encoding="utf-8"
    )
    for ad, tablo in (("patients.db", "patients"), ("pemf_treatment_history.db", "treatment_sessions")):
        c = open_encrypted_conn(veri / ad, anahtar, mod)
        try:
            c.execute(f"CREATE TABLE {tablo} (id INTEGER PRIMARY KEY, ad TEXT)")
            c.execute(f"INSERT INTO {tablo} (ad) VALUES ('sentetik')")
            c.commit()
        finally:
            c.close()
    return veri


class SahteVault:
    def __init__(self, *, kok: str, kurtarma: str, iptal: str = "", emanet: dict | None = None, kurtarma_ttl: int = 0):
        self.tokenler = {kok: "kok", kurtarma: "kurtarma"}
        if iptal:
            self.tokenler[iptal] = "iptal"
        self.emanet = dict(emanet or {})
        self.kurtarma_ttl = kurtarma_ttl
        self.kip = "normal"
        self.mountlar: dict = {}
        self.denetim: dict = {}
        self.politikalar: dict = {}
        self.uretilen: list[dict] = []
        self.istekler: list[tuple[str, str, str]] = []
        self._sunucu: ThreadingHTTPServer | None = None

    # ── yaşam döngüsü ───────────────────────────────────────────────────────────────────────────────────────────
    def __enter__(self) -> "SahteVault":
        for _ in range(20):
            sunucu = ThreadingHTTPServer(("127.0.0.1", 0), self._isleyici())
            if sunucu.server_address[1] not in YASAK_PORTLAR:
                break
            sunucu.server_close()
        else:  # pragma: no cover - 20 denemede hep yasaklı port: olası değil
            raise RuntimeError("yasaklı olmayan port alınamadı")
        self._sunucu = sunucu
        threading.Thread(target=sunucu.serve_forever, daemon=True, name="sahte-vault").start()
        return self

    def __exit__(self, *a) -> None:
        if self._sunucu is not None:
            self._sunucu.shutdown()
            self._sunucu.server_close()

    @property
    def adres(self) -> str:
        assert self._sunucu is not None
        return f"http://127.0.0.1:{self._sunucu.server_address[1]}"

    def siniflar(self, yol_parcasi: str = "") -> list[str]:
        """Yolunda `yol_parcasi` geçen isteklerin token sınıfları (sırayla)."""
        return [s for _y, p, s in self.istekler if yol_parcasi in p]

    # ── HTTP ────────────────────────────────────────────────────────────────────────────────────────────────────
    def _isleyici(self):
        vault = self

        class _I(BaseHTTPRequestHandler):
            def log_message(self, *a):  # sessiz
                pass

            def _govde(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                if not n:
                    return {}
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return {}

            def _yanit(self, kod: int, veri: dict | None = None) -> None:
                ham = json.dumps(veri).encode() if veri is not None else b""
                self.send_response(kod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(ham)))
                self.end_headers()
                if ham:
                    self.wfile.write(ham)

            def _isle(self, yontem: str) -> None:
                yol = self.path.split("?", 1)[0]
                tok = self.headers.get("X-Vault-Token")
                sinif = vault.tokenler.get(tok, "bilinmeyen") if tok else "yok"
                vault.istekler.append((yontem, yol, sinif))
                govde = self._govde() if yontem in ("POST", "PUT") else {}
                if vault.kip == "hepsi_403":
                    return self._yanit(403, {"errors": ["permission denied"]})
                if sinif == "iptal":
                    return self._yanit(403, {"errors": ["permission denied", "token revoked"]})
                if sinif in ("bilinmeyen", "yok"):
                    return self._yanit(403, {"errors": ["permission denied"]})
                emanet = f"/v1/{MOUNT}/data/{EMANET_YOLU}"
                if yol == "/v1/auth/token/lookup-self" and yontem == "GET":
                    if sinif == "kok":
                        return self._yanit(200, {"data": {"policies": ["root"], "ttl": 0}})
                    return self._yanit(
                        200, {"data": {"policies": ["default", "pemf-kurtarma"], "ttl": vault.kurtarma_ttl}}
                    )
                if yol == emanet and yontem == "GET":
                    if not vault.emanet:
                        return self._yanit(404, {"errors": []})
                    return self._yanit(200, {"data": {"data": vault.emanet, "metadata": {"version": 1}}})
                if sinif != "kok":  # kurtarma politikası YALNIZ emaneti okur
                    return self._yanit(403, {"errors": ["permission denied"]})
                if yol == "/v1/sys/mounts" and yontem == "GET":
                    return self._yanit(200, dict(vault.mountlar))
                if yol == f"/v1/sys/mounts/{MOUNT}" and yontem == "POST":
                    vault.mountlar[f"{MOUNT}/"] = {"type": "kv"}
                    return self._yanit(204)
                if yol == "/v1/sys/audit" and yontem == "GET":
                    return self._yanit(200, dict(vault.denetim))
                if yol == "/v1/sys/audit/file" and yontem in ("POST", "PUT"):
                    vault.denetim["file/"] = {"type": "file"}
                    return self._yanit(204)
                if yol.startswith("/v1/sys/policies/acl/") and yontem == "PUT":
                    vault.politikalar[yol.rsplit("/", 1)[1]] = govde.get("policy", "")
                    return self._yanit(204)
                if yol == "/v1/auth/token/create" and yontem == "POST":
                    vault.uretilen.append(govde)
                    return self._yanit(
                        200,
                        {
                            "auth": {
                                "client_token": "kurtarma-yeni",
                                "policies": govde.get("policies"),
                                "lease_duration": 315360000,
                            }
                        },
                    )
                if yol == emanet and yontem == "POST":
                    vault.emanet = dict(govde.get("data") or {})
                    return self._yanit(200, {"data": {"version": 2}})
                return self._yanit(404, {"errors": [f"sahte vault: bilinmeyen uc {yontem} {yol}"]})

            def do_GET(self):
                self._isle("GET")

            def do_POST(self):
                self._isle("POST")

            def do_PUT(self):
                self._isle("PUT")

        return _I
