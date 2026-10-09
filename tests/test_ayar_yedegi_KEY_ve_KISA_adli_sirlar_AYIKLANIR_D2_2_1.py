# -*- coding: utf-8 -*-
"""D2-2.1 (2-D incelemesi A2) — A-32 "SIR hariç" ayar yedeği: `*_key` ve kısa adlı sır alanları da ayıklanır.

ÖLÇÜLEN KUSUR: `yedek_dosyasi._SIR_ANAHTARI` ad deseni `pass|parola|sifre|secret|token|api_?key|private|credential|^user(name)?$`
`key` ile BİTEN adları (yalnız `api_key`/`apikey` hariç) ve kısa adları (`pin`, `pwd`, `otp`, `psk`, `salt`, `hmac`, `kod`, `jwt`,
`bearer`, `Authorization`, `cookie`) yakalamıyor. Kodun KENDİSİ `config.json`dan `supabase_key` okur
(`backend_service._resolve_supabase_credentials` → `pemf_gui.config` — üretimde PEMF_DATA_DIR ile backend'in config.json'ı AYNI
dosya [ÖLÇTÜM sonda]); bu alan ayar yedeğine — ve makine dışı hedefe — DÜZ gidiyordu. Sır değeri bu dosyada sentetiktir.

KARŞIT: şablon config'in (config/config.json.template) sır olmayan hiçbir alanı ayıklanmaz (geri yüklemede kaybolmaz).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

KLON_KOK = Path(__file__).resolve().parents[1]


def _isci(app: Path):
    from services.headless_db_maintenance import HeadlessDBMaintenance

    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = app, None, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    return w


def _degerler(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _degerler(v)
    elif isinstance(o, list):
        for v in o:
            yield from _degerler(v)
    elif isinstance(o, str):
        yield o


ADLAR = (
    "supabase_key",
    "anon_key",
    "service_role_key",
    "sqlcipher_key",
    "hmac_key",
    "license_key",
    "wifi_key",
    "pin",
    "pwd",
    "otp",
    "psk",
    "salt",
    "kod",
    "jwt",
    "bearer",
    "Authorization",
    "cookie",
)


def test_KRITIK_D2_2_1_key_ile_biten_ve_kisa_adli_sir_alanlari_ayar_yedeginden_AYIKLANIR(temp_app_data):
    sirlar = {ad: f"SENTETIK-D2-2-1-{i:02d}-ğ" for i, ad in enumerate(ADLAR)}
    config = {
        "supabase_url": "https://ornek.invalid",
        "supabase_key": sirlar["supabase_key"],  # kodun OKUDUĞU gerçek ad
        "ek": {ad: v for ad, v in sirlar.items() if ad != "supabase_key"},
        "application": {"language": "tr"},
    }
    # pemf_gui.ConfigManager.save biçimi: json.dump varsayılanı (ensure_ascii=True → \\uXXXX)
    (temp_app_data / "config.json").write_text(json.dumps(config, indent=4), encoding="utf-8")
    bdir = temp_app_data / "backups"
    bdir.mkdir()
    uretilen = _isci(temp_app_data)._ek_kapsam_yedekle(bdir, "20261009_120000")
    assert [p.name for p in uretilen] == ["pemf_config_20261009_120000.json"]
    ham = uretilen[0].read_bytes()
    degerler = list(_degerler(json.loads(ham.decode("utf-8"))))
    sizan = sorted(
        ad
        for ad, v in sirlar.items()
        if ham.count(v.encode("utf-8")) or ham.count(json.dumps(v)[1:-1].encode()) or any(v in d for d in degerler)
    )
    assert not sizan, f"ayar yedeğine DÜZ giden sır alanı ADLARI ({len(sizan)}): {sizan}"
    yedek = json.loads(ham.decode("utf-8"))
    assert yedek["application"] == {"language": "tr"} and yedek["supabase_url"] == "https://ornek.invalid"


def test_KARSIT_D2_2_1_sablon_configin_SIR_OLMAYAN_alanlari_AYIKLANMAZ():
    from database.yedek_dosyasi import sirsiz_ayarlar
    from services.headless_db_maintenance import HeadlessDBMaintenance

    sablon = json.loads((KLON_KOK / "config" / "config.json.template").read_text(encoding="utf-8"))
    sablon.setdefault("mqtt", {})["cloud_broker"] = {"tls_cert_sha256": "ab" * 32, "broker_url": "b.ornek.invalid"}
    sablon["system_settings_benzeri"] = {
        "clinic_name": "Klinik",
        "ble_gateway_mac": "AA:BB",
        "email_sender": "a@b.invalid",
    }
    _, ayiklanan = sirsiz_ayarlar(sablon, HeadlessDBMaintenance._config_sir_yollari())
    assert sorted(ayiklanan) == ["mqtt.local_broker.password", "mqtt.local_broker.username"], (
        f"sır OLMAYAN ayar da ayıklandı (geri yüklemede kaybolur): {sorted(ayiklanan)}"
    )


def test_KAPI_D2_2_1_enc_onekli_deger_SIR_ADI_tasimasa_da_ve_bozuk_kaynakta_HAM_kopya_YOK(temp_app_data):
    """Mutant öldürücü (HEAD'de YEŞİL): `enc:` öneki kolu (ör. pemf_gui'nin şifrelediği `mqtt.cloud_broker.tls_cert_sha256`) ve
    "kaynak okunamazsa HAM kopya ALINMAZ" kolu 2-D kapısında hiç koşmuyordu (mutantları YAŞADI)."""
    enc = "enc:gAAAAAB-SENTETIK-D2-2-1-sifreli"
    (temp_app_data / "config.json").write_text(
        json.dumps({"mqtt": {"cloud_broker": {"tls_cert_sha256": enc}}, "application": {"theme": "dark"}}),
        encoding="utf-8",
    )
    bozuk_sir = "SENTETIK-D2-2-1-bozuk-kaynaktaki-parola"
    # pemf_gui.ConfigManager.save atomik DEĞİL (kes-yaz): çökme yarım JSON bırakır — içinde sır olabilir
    (temp_app_data / "system_settings.json").write_text(
        '{"email_password": "' + bozuk_sir + '", "clin', encoding="utf-8"
    )
    bdir = temp_app_data / "backups"
    bdir.mkdir()
    uretilen = _isci(temp_app_data)._ek_kapsam_yedekle(bdir, "20261009_120000")
    assert [p.name for p in uretilen] == ["pemf_config_20261009_120000.json"], [p.name for p in uretilen]
    for p in bdir.iterdir():
        veri = p.read_bytes()
        assert enc.encode() not in veri, f"enc: önekli değer yedekte: {p.name}"
        assert bozuk_sir.encode() not in veri, f"okunamayan kaynağın HAM kopyası yedekte: {p.name}"
