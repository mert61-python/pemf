# -*- coding: utf-8 -*-
"""TA T5 · ÇOKLU KLİNİK P2 (`resolve_device` kod kaba kuvveti) — seçenek (a): eşleştirme kodu 6 → 8 karakter (DoS-nötr).

Önce: iki üretici (`utils/path_utils.get_pairing_code`, `utils/secrets_manager._gen_pairing`) 6 karakter üretiyordu (31⁶ ≈ 887 milyon);
bulut `resolve_device` sır almadan kodu çözüyor ve hız sınırı yok. Şimdi YENİ kodlar 8 karakter (31⁸ ≈ 852 milyar); cihazda kayıtlı
6 karakterli kod GEÇERLİ kalır (geçiş); depodaki her `resolve_device` tanımı 6 VE 8'i kabul eder; göç dosyası
`supabase/cihaz_kodu_8_karakter.sql` (canlıya AÇILIŞ GÜNÜ). Mobil istemci 8 karakterliyi "kod" sayar (`KOD_MAX_UZUNLUK`).
Sahte EN ALT katta: veri kökü (`get_app_data_directory` → tmp_path).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from utils import path_utils as pu
from utils import secrets_manager as sm

KOK = Path(__file__).resolve().parents[1]
ALFABE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


@pytest.fixture
def kok(tmp_path, monkeypatch):
    monkeypatch.setattr(pu, "get_app_data_directory", lambda: tmp_path)
    monkeypatch.delenv("PEMF_RESET_PAIRING_CODE", raising=False)
    return tmp_path


def _gecerli(kod: str, n: int) -> bool:
    return len(kod) == n and all(c in ALFABE for c in kod)


def test_KRITIK_yeni_kurulumda_kod_8_karakter_ve_KALICI(kok):
    kod = pu.get_pairing_code()
    assert _gecerli(kod, 8), kod
    assert (kok / "pairing_code.txt").read_text(encoding="utf-8") == kod
    assert pu.get_pairing_code() == kod, "kod kalıcı değil"
    assert pu._PAIRING_CODE_LENGTH == 8 and pu._PAIRING_CODE_ALPHABET == ALFABE


def test_KRITIK_GECIS_kayitli_6_karakterli_kod_GECERLI_kalir_yeniden_uretilmez(kok):
    (kok / "pairing_code.txt").write_text("k7m2pq\n", encoding="utf-8")
    assert pu.get_pairing_code() == "K7M2PQ"
    assert (kok / "pairing_code.txt").read_text(encoding="utf-8") == "k7m2pq\n", (
        "kayıtlı kod EZİLDİ (telefonlar yeniden eşleşmek zorunda kalırdı)"
    )
    (kok / "pairing_code.txt").write_text("K7M2PQ9A", encoding="utf-8")
    assert pu.get_pairing_code() == "K7M2PQ9A"


@pytest.mark.parametrize("bozuk", ["K7M2P", "K7M2PQ9", "K7M2PQ9AB", "K7M2PQ0A", "K7M2-Q9A", ""])
def test_gecersiz_kayitli_kod_8_karakterle_YENIDEN_uretilir(kok, bozuk):
    (kok / "pairing_code.txt").write_text(bozuk, encoding="utf-8")
    kod = pu.get_pairing_code()
    assert _gecerli(kod, 8) and kod != bozuk


def test_sifirlama_istegi_8_karakterli_yeni_kod_uretir(kok, monkeypatch):
    (kok / "pairing_code.txt").write_text("K7M2PQ", encoding="utf-8")
    monkeypatch.setenv("PEMF_RESET_PAIRING_CODE", "1")
    kod = pu.get_pairing_code()
    assert _gecerli(kod, 8) and kod != "K7M2PQ"


def test_sir_deposu_ureteci_de_8_karakter_ve_AYNI_alfabe():
    for _ in range(50):
        kod = sm._gen_pairing()
        assert _gecerli(kod, pu._PAIRING_CODE_LENGTH), kod


def _izlenen_sql() -> list[Path]:
    r = subprocess.run(["git", "ls-files", "-z", "*.sql"], cwd=KOK, capture_output=True, timeout=120, check=True)
    izli = [KOK / p for p in r.stdout.decode("utf-8").split("\0") if p]
    goc = KOK / "supabase" / "cihaz_kodu_8_karakter.sql"
    return sorted(set(izli) | {goc})


def test_KRITIK_depodaki_HER_resolve_device_tanimi_6_VE_8_karakteri_kabul_eder():
    tanimlar = 0
    for p in _izlenen_sql():
        metin = p.read_text(encoding="utf-8").lower()
        for govde in re.findall(r"function\s+public\.resolve_device\s*\(.*?\$\$(.*?)\$\$", metin, re.S):
            if "p_code" not in govde:
                continue
            tanimlar += 1
            assert not re.search(r"length\(p_code\)\s*=\s*6", govde), f"{p.name}: yalnız 6 karakter kabul ediyor"
            assert re.search(r"length\(p_code\)\s+in\s*\(\s*6\s*,\s*8\s*\)", govde), (
                f"{p.name}: 8 karakterli kod kabul edilmiyor"
            )
    assert tanimlar >= 3, f"VAKUM: yalnız {tanimlar} resolve_device tanımı bulundu"


def test_goc_dosyasi_YALNIZ_resolve_device_imzasi_ayni_yetki_anon_ve_islem_icinde():
    metin = (KOK / "supabase" / "cihaz_kodu_8_karakter.sql").read_text(encoding="utf-8").lower()
    assert re.search(
        r"create\s+or\s+replace\s+function\s+public\.resolve_device\s*\(\s*p_code\s+text\s+default\s+null\s*,\s*p_device_id\s+text\s+default\s+null\s*\)",
        metin,
    )
    assert "returns table (device_id text, name text, tunnel_url text, local_ip text, last_seen timestamptz)" in metin
    assert "grant execute on function public.resolve_device(text,text) to anon" in metin
    assert metin.count("create or replace function") == 1 and "upsert_device" not in re.sub(r"--[^\n]*", "", metin)
    assert re.search(r"^begin;", metin, re.M) and re.search(r"^commit;", metin, re.M)
    taban = (KOK / "supabase" / "resolve_device_bayat_gorunur.sql").read_text(encoding="utf-8").lower()
    govde = lambda m: re.search(r"\$\$(.*?)\$\$", m, re.S).group(1)  # noqa: E731
    assert govde(metin) == govde(taban), "göç gövdesi taban (bayat_gorunur) ile ayrıştı — tek fark length koşulu olmalı"


def test_mobil_istemci_8_karakterliyi_KOD_sayar_ve_rehber_metni_iki_dilde_dogru():
    ts = (KOK / "apps" / "ui" / "src" / "services" / "pairing.ts").read_text(encoding="utf-8")
    m = re.search(r"export const KOD_MAX_UZUNLUK = (\d+);", ts)
    assert m and int(m.group(1)) >= pu._PAIRING_CODE_LENGTH, "8 karakterli kod cihaz kimliği sanılırdı"
    tr = json.loads((KOK / "apps/ui/src/i18n/tr/ayarlar.json").read_text(encoding="utf-8"))["eslestirmeRehberi"][
        "ekranAciklama"
    ]
    en = json.loads((KOK / "apps/ui/src/i18n/en/ayarlar.json").read_text(encoding="utf-8"))["eslestirmeRehberi"][
        "ekranAciklama"
    ]
    assert "8 ya da 6 karakterlik eşleştirme kodu" in tr
    assert "8- or 6-character pairing code" in en
