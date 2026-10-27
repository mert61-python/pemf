# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.02 = D5.11 = D5.24 (B-3.3 · B-3.4 · B-9.13 · B-10.98) — `supabase_sql.py --denetim` bulguyu ÇIKIŞ KODUYLA söyler ve
anon-çağrılabilir SECURITY DEFINER fonksiyonları AD ile değil İMZA ile (p_secret) denetler.

ÖLÇÜLEN KUSUR: (1) `denetim()` bulgu sayısından bağımsız `return 0` — "3 BULGU" basılsa da betik / CI "geçti" sanıyordu.
(2) 5. madde beklenen listeyi YALNIZ ADLA süzüyordu: sırsız ESKİ imza (`upsert_patient(p_device_id text, p_patient jsonb)`,
secure_v2 öncesi; cihaz sırrı OLMADAN hasta yazabilir) canlıda kalsa "temiz" çıkıyordu. Kontrol kolu: listede OLMAYAN
`jeton_donem_yenile` bugün de bulgu sayılır (araç kırmızı olabiliyor — yalnız çıkış kodu söylemiyordu).

GERÇEK: `main()` / `denetim()` / `DENETIM` sorguları / süzgeç. Sahte EN ALT katta: `urllib.request.urlopen` (ağ YOK; sorgu metnine
göre sahte satır döner) ve PAT okuyucu (sır OKUNMAZ). `--ref` açık verilir (sır dosyası taranmaz). Canlıya istek YOK.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent


def _arac():
    spec = importlib.util.spec_from_file_location("supabase_sql_denetim_d502", _KOK / "scripts" / "supabase_sql.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


#: DENETIM sözlüğünün başlık öneki → sorgu metninde o maddeye özgü parça (sahte sunucu yanıtı seçer).
_MADDE_IZI = {
    "1.": "not c.relrowsecurity",
    "2.": "role_table_grants",
    "3.": "proconfig",
    "5.": "has_function_privilege('anon'",
    "BILGI": "and c.relrowsecurity",
}


@pytest.fixture
def denetle(monkeypatch, capsys):
    arac = _arac()
    sorgular: list[dict] = []

    def kos(yanitlar: dict) -> tuple[int, str]:
        """`yanitlar`: madde öneki → sahte satırlar. Gerçek `main(['--denetim'])` koşar."""

        def _urlopen(istek, timeout=None):
            govde = json.loads(istek.data.decode("utf-8"))
            sorgular.append(govde)
            q = govde["query"]
            eslesen = [k for k, iz in _MADDE_IZI.items() if iz in q]
            assert len(eslesen) == 1, f"sahte sunucu sorguyu tanımadı ({eslesen}): {q[:120]}"
            veri = json.dumps(yanitlar.get(eslesen[0], [])).encode("utf-8")

            class _Y:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self):
                    return veri

            return _Y()

        monkeypatch.setattr(arac.urllib.request, "urlopen", _urlopen)
        monkeypatch.setattr(arac, "_pat", lambda: "sahte-pat")
        monkeypatch.setattr("sys.argv", ["supabase_sql.py", "--ref", "abcdefghijklmnopqrst", "--denetim"])
        rc = arac.main()
        return rc, capsys.readouterr().out

    return kos, sorgular


def test_KRITIK_D5_02_sirsiz_ESKI_imza_bulgudur_ve_cikis_SIFIR_DEGIL(denetle):
    kos, sorgular = denetle
    rc, out = kos({"5.": [{"fonksiyon": "upsert_patient", "parametreler": "p_device_id text, p_patient jsonb"}]})
    assert "1 BULGU" in out and rc != 0, f"sırsız eski imza TEMIZ sayıldı / çıkış 0: rc={rc}\n{out}"
    assert all(s["read_only"] is True for s in sorgular), "denetim salt-okur olmalı"


def test_KRITIK_D5_11_RLS_kapali_tablo_bulgusunda_cikis_SIFIR_DEGIL(denetle):
    kos, _ = denetle
    rc, out = kos({"1.": [{"tablo": "patients"}]})
    assert "1 BULGU" in out and rc != 0, f"bulgu var ama çıkış {rc}\n{out}"


def test_KONTROL_listede_olmayan_jeton_donem_yenile_bulgu_ve_cikis_SIFIR_DEGIL(denetle):
    kos, _ = denetle
    rc, out = kos({"5.": [{"fonksiyon": "jeton_donem_yenile", "parametreler": "p_user uuid, p_hak integer"}]})
    assert "1 BULGU" in out and rc != 0


@pytest.mark.parametrize(
    "satir",
    [
        {"fonksiyon": "upsert_patient", "parametreler": "p_device_id text, p_patient jsonb, p_secret text"},
        {
            "fonksiyon": "upsert_device",
            "parametreler": "p_device_id text, p_name text, p_tunnel_url text, p_local_ip text, p_api_port integer, p_pairing_code text, p_secret text",
        },
        {"fonksiyon": "resolve_sessions", "parametreler": "p_device_id text, p_secret text"},
        {"fonksiyon": "resolve_device", "parametreler": "p_code text, p_device_id text"},
        {"fonksiyon": "usage_counts", "parametreler": ""},
    ],
    ids=[
        "upsert_patient_v2",
        "upsert_device_v2",
        "resolve_sessions_v2",
        "resolve_device_tasarim",
        "usage_counts_tasarim",
    ],
)
def test_KARSIT_depo_niyetindeki_imzalar_TEMIZ_cikis_0(denetle, satir):
    kos, _ = denetle
    rc, out = kos({"5.": [satir]})
    assert rc == 0 and "\nTEMIZ" in out, f"depo niyetindeki imza bulgu sayıldı: {satir}\n{out}"


@pytest.mark.parametrize("ad", ["upsert_device", "upsert_session", "resolve_patients", "resolve_sessions"])
def test_KRITIK_sirli_olmasi_gereken_her_RPC_sirsiz_imzada_bulgu(denetle, ad):
    kos, _ = denetle
    rc, out = kos({"5.": [{"fonksiyon": ad, "parametreler": "p_device_id text"}]})
    assert rc != 0 and "1 BULGU" in out, f"{ad} sırsız imzada temiz sayıldı"


def test_KARSIT_p_secret_ADI_tam_eslesir_onek_benzeri_yetmez(denetle):
    kos, _ = denetle
    rc, out = kos({"5.": [{"fonksiyon": "upsert_patient", "parametreler": "p_device_id text, p_secret_ipucu text"}]})
    assert rc != 0, "p_secret_ipucu parametresi sır doğrulaması değildir"


def test_KARSIT_hic_bulgu_yoksa_TEMIZ_cikis_0_ve_BILGI_satiri_bulgu_sayilmaz(denetle):
    kos, sorgular = denetle
    rc, out = kos({"BILGI": [{"tablo": "token_ledger"}]})
    assert rc == 0 and "\nTEMIZ" in out
    assert len(sorgular) == 5, f"beş denetim sorgusunun hepsi koşmalı: {len(sorgular)}"
