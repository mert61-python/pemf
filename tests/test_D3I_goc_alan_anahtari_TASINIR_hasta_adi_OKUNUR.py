# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-O.1 = D3I-A2.1 (D3.37 · Y10) — ESKİ KÖK GÖÇÜ HASTA ALANLARININ ANAHTARINI (`patient_fernet_key`) DA TAŞIR; TAŞIYAMAZSA HASTA DB'si
KOPYALANMAZ.

ÖLÇÜLEN KUSUR (önceden var — `d2feca4f` "YALNIZ sqlcipher_key"; D3.37'nin "KOPYALA → DOĞRULA" iddiasının kapsamında):
`_kullanicidan_makineye_gocur` eski kökten (`%APPDATA%\\PEMF_GUI`; NSSM / LocalSystem'de `systemprofile\\…`) makine köküne (`PEMF_DATA_DIR`)
`patients.db`yi (WAL dahil, SHA-256 doğrulamalı) kopyalıyor, `pemf_secrets.json`dan YALNIZ `sqlcipher_key`i taşıyordu — eski kökte
`sqlcipher_key` YOKSA (A-11 öncesi at-rest KAPALI kurulum) HİÇBİR anahtar taşınmıyordu. Hasta alanları (ad / sahip / tür …) DB SQLCipher
olsun olmasın AYRICA `patient_fernet_key` ile şifrelidir (`enc:`); hedefte o anahtar YOKTU → ilk açılış YENİSİNİ ÜRETTİ → taşınan her hasta
"[okunamayan kayıt]", arama boş (ölçüldü: gerçek `backend_service.main()` 1.9.50 → HEAD 4/4; bu dosyada HEAD → HEAD iki alt süreçle 2/2).
Veri eski kökte duruyordu ama hedefte YENİ anahtarla yeni hasta yazıldıkça iki anahtarlı karışık bir DB oluşuyordu.

SÖZLEŞME (`sqlcipher_key` dalıyla AYNI kurallar): alan anahtarı hedefte YOKSA ve BU makinede çözülebiliyorsa ham (DPAPI-sarılı) değeri
OLDUĞU GİBİ taşınır (`sqlcipher_key` olsun olmasın); hedefte VARSA ASLA ezilmez; cihaz kimliği / eşleştirme / operatör sırları TAŞINMAZ.
Kaynakta alan anahtarı VAR ve hedefteki ham değer AYNI DEĞİLSE `patients.db` KOPYALANMAZ + "VERİ GÖÇÜ ATLANDI" ERROR (eski kayıt eski kökte
okunur kalır, hedefte okunamaz kopya oluşmaz). Göç yolu SIR / KRİPTO KATMANINA (`get_secret`, `get_sqlcipher_key`,
`get_app_data_directory`) DÖNMEZ (1.9.9/1.9.10 BSOD özyinelemesi) — yalnız ham JSON + `bu_makinede_cozulebilir_mi`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import sys
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="göç yalnız Windows'ta koşar (path_utils)")

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
YER_TUTUCU = "[okunamayan kayıt]"
HASTALAR = [
    {"name": "Pamuk", "owner": "Ayşe Yılmaz", "species": "Kedi"},
    {"name": "Karabaş", "owner": "Mehmet Öz", "species": "Köpek"},
]
DUZ_DB = b"SQLite format 3\x00" + b"HASTALAR" * 8
SIFRELI_DB = b"\x00\x01SIFRELI-HASTA-SAYFASI" * 4


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _goruntu(d: Path) -> dict:
    return {p.name: _sha(p) for p in d.iterdir() if p.is_file()}


def _auto(kok: Path) -> dict:
    j = kok / "pemf_secrets.json"
    return (json.loads(j.read_text(encoding="utf-8")).get("auto") or {}) if j.is_file() else {}


# ─────────────────────────── uçtan uca: iki ayrı açılış (alt süreç, HEAD DB katmanı, sahte YOK) ───────────────────────────


def _cocuk(tmp_path: Path, ad: str, govde: str, at_rest: str, makine: bool) -> dict:
    env = yalitik_ortam(tmp_path / "ev")  # açılışlar AYNI ev: eski kök = <ev>\appdata\PEMF_GUI
    env.update(
        {
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "p.json"),
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "PEMF_LOG_DIR": str(tmp_path / f"log_{ad}"),
            "PEMF_ENCRYPT_AT_REST": at_rest,
        }
    )
    if makine:
        env["PEMF_DATA_DIR"] = str(tmp_path / "makine")
    kod = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(TESTLER)!r})\n"
        "import alt_surec_ag_bekcisi as _ag\n"
        f"sys.path.remove({str(TESTLER)!r})\n"
        f"sys.path[:0] = [{str(KOK)!r}, {str(BACKEND)!r}]\n"
        "from database.patient_database import get_patient_database\n"
        "from utils.path_utils import get_app_data_directory\n"
        "out = {}\n"
        "pdb = get_patient_database()\n"
        "out['kok'] = str(get_app_data_directory())\n"
        "out['sqlcipher'] = bool(pdb.at_rest_encrypted)\n"
        f"{govde}"
        "c = getattr(pdb._local, 'conn', None)\n"
        "if c is not None:\n"
        "    c.close()\n"
        "out['ag'] = _ag.ENGELLENEN\n"
        "print('SONUC ' + json.dumps(out, ensure_ascii=False))\n"
    )
    betik = tmp_path / f"{ad}.py"
    betik.write_text(kod, encoding="utf-8")
    p = kostur([str(betik)], cwd=tmp_path, env=env, sure=300)
    satir = [s for s in p.stdout.splitlines() if s.startswith("SONUC ")]
    assert p.returncode == 0 and satir, f"{ad} çocuğu düştü rc={p.returncode}: {p.stderr[-1500:]}"
    return json.loads(satir[-1][len("SONUC ") :])


_YAZ = (
    f"for h in {HASTALAR!r}:\n"
    "    pdb.add_patient(h)\n"
    "with pdb._get_connection() as c:\n"
    "    c.execute('PRAGMA wal_checkpoint(TRUNCATE)')\n"
)
_OKU = (
    "hepsi = pdb.get_all_patients()\n"
    "out['adlar'] = sorted(str(h.get('name')) for h in hepsi)\n"
    "out['sahipler'] = sorted(str(h.get('owner')) for h in hepsi)\n"
    "out['arama'] = [h.get('name') for h in pdb.search_patients('Pamuk')]\n"
)


@pytest.mark.parametrize(
    "eski_at_rest, yeni_at_rest",
    [("1", "1"), ("0", "1"), ("0", "0")],
    ids=["eski_kok_SIFRELI", "eski_kok_SIFRESIZ_A11_oncesi_yeni_SIFRELI", "iki_kok_SIFRESIZ"],
)
def test_KRITIK_D3I_O1_eski_kokten_gocen_hasta_ADI_OKUNUR_arama_BULUR_kaynak_DEGISMEZ(
    tmp_path, eski_at_rest, yeni_at_rest
):
    """MUTASYON: alan anahtarını taşımamak → KIRMIZI (ya "[okunamayan kayıt]" ya hasta DB'si hiç taşınmaz → boş liste)."""
    eski = tmp_path / "ev" / "appdata" / "PEMF_GUI"
    hedef = tmp_path / "makine" / "PEMF_GUI"

    a = _cocuk(tmp_path, "eski_acilis", _YAZ, eski_at_rest, makine=False)
    assert a["ag"] == [], a["ag"]
    assert Path(a["kok"]) == eski, f"ilk açılış eski köke yazmadı: {a['kok']}"
    assert a["sqlcipher"] is (eski_at_rest == "1"), "senaryo kurulamadı (eski kök SQLCipher kolu beklenenden farklı)"
    assert _auto(eski).get("patient_fernet_key"), "senaryo kurulamadı: eski kökte alan anahtarı yok"
    # `_empty_doc` her anahtarı "" ile açar — kol DOLU / BOŞ değerle ayrılır (A-11 öncesi kurulumda sqlcipher_key BOŞ).
    assert bool(_auto(eski).get("sqlcipher_key")) is (eski_at_rest == "1"), (
        "senaryo kurulamadı (eski kökte sqlcipher_key kolu)"
    )
    assert not hedef.exists()
    once = _goruntu(eski)

    b = _cocuk(tmp_path, "makine_acilisi", _OKU, yeni_at_rest, makine=True)
    assert b["ag"] == [], b["ag"]
    assert Path(b["kok"]) == hedef
    assert b["sqlcipher"] is (yeni_at_rest == "1")
    assert _goruntu(eski) == once, "KAYNAK değişti / silindi (Y10: kaynak SİLİNMEZ, DEĞİŞTİRİLMEZ)"
    assert YER_TUTUCU not in b["adlar"], (
        f"göçen hasta adları hedefte ÇÖZÜLEMİYOR ({b['adlar'].count(YER_TUTUCU)}/{len(b['adlar'])} '{YER_TUTUCU}') — "
        "alan anahtarı (patient_fernet_key) taşınmadı, hedef YENİSİNİ üretti"
    )
    assert b["adlar"] == sorted(h["name"] for h in HASTALAR), f"hasta listesi eksik / boş: {b['adlar']}"
    assert b["sahipler"] == sorted(h["owner"] for h in HASTALAR), b["sahipler"]
    assert b["arama"] == ["Pamuk"], f"arama göçen hastayı BULMUYOR: {b['arama']}"
    ayni = _auto(hedef).get("patient_fernet_key") == _auto(eski).get("patient_fernet_key")
    assert ayni, "hedefteki alan anahtarı eski kökün ham değeri DEĞİL (sır değeri yazdırılmadı)"
    # Karşıt kanıt: okuma yolu sağlam ve eski kök göçten sonra da AYNEN okunur (kırmızı ölçüm aracından gelmez).
    c = _cocuk(tmp_path, "eski_yeniden", _OKU, eski_at_rest, makine=False)
    assert c["ag"] == [] and Path(c["kok"]) == eski
    assert c["adlar"] == sorted(h["name"] for h in HASTALAR), f"eski kök göçten sonra okunamıyor: {c['adlar']}"


# ─────────────────────────── süreç içi: göç kuralları (sahte eski / yeni kök, saf JSON) ───────────────────────────


@pytest.fixture
def kokler(tmp_path, monkeypatch):
    from utils import path_utils as pu

    eski_appdata = tmp_path / "kullanici" / "AppData" / "Roaming"
    eski = eski_appdata / "PEMF_GUI"
    eski.mkdir(parents=True)
    yeni = tmp_path / "ProgramData" / "PEMF_System" / "PEMF_GUI"
    yeni.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(eski_appdata))
    monkeypatch.setattr(pu, "_GOC_YAPILDI", set())
    monkeypatch.setattr(pu, "_GOC_ENGELI", {}, raising=False)  # taban (5df8406d) ölçümünde öznitelik yok
    return pu, eski, yeni


def _sir_yaz(kok: Path, auto: dict) -> None:
    (kok / "pemf_secrets.json").write_text(
        json.dumps({"_version": 1, "auto": auto, "operator": {"mqtt_pass": "OPERATOR"}, "embedded": {}}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("db", [DUZ_DB, SIFRELI_DB], ids=["duz_db", "sqlcipher"])
def test_KARSIT_D3I_O1_hedefte_FARKLI_alan_anahtari_varken_hasta_DBsi_KOPYALANMAZ_anahtar_EZILMEZ(kokler, caplog, db):
    """Hedefin KENDİ alan anahtarı var (ezilmez) → kopya orada '[okunamayan kayıt]' olurdu: `patients.db` KOPYALANMAZ, sqlcipher
    uyuşmazlığıyla AYNI sınıf "VERİ GÖÇÜ ATLANDI" ERROR. SQLCipher kolunda `sqlcipher_key` iki tarafta AYNI — kapı yalnız düz-DB dalına
    konursa bu kol KIRMIZI. MUTASYON: `_tasinabilir_mi` alan anahtarı denetimi YOK → KIRMIZI; hedefteki anahtarı ezmek → KIRMIZI."""
    pu, eski, yeni = kokler
    _sir_yaz(eski, {"sqlcipher_key": "AYNI-SQLCIPHER", "patient_fernet_key": "KAYNAK-ALAN-ANAHTARI"})
    _sir_yaz(yeni, {"sqlcipher_key": "AYNI-SQLCIPHER", "patient_fernet_key": "HEDEFIN-KENDI-ALAN-ANAHTARI"})
    (eski / "patients.db").write_bytes(db)
    (eski / "auth_users.db").write_bytes(DUZ_DB)
    once = _goruntu(eski)

    with caplog.at_level(logging.WARNING):
        pu._kullanicidan_makineye_gocur(yeni)

    assert not (yeni / "patients.db").exists(), "alan anahtarı FARKLI hedefe hasta DB'si KOPYALANDI → adlar okunamaz"
    assert (yeni / "auth_users.db").exists(), "göç tamamen kapandı (karşıt kanıt: öteki DB'ler taşınmalı)"
    assert _goruntu(eski) == once, "KAYNAK değişti / silindi"
    assert _auto(yeni)["patient_fernet_key"] == "HEDEFIN-KENDI-ALAN-ANAHTARI", "hedefin alan anahtarı EZİLDİ"
    atlandi = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "VERİ GÖÇÜ ATLANDI" in r.getMessage() and "patients.db" in r.getMessage()
    ]
    assert atlandi, "hasta DB'si atlandı ama operatöre ERROR günlüğü YAZILMADI (sessiz atlama)"


def test_KRITIK_D3I_O1_yalniz_IKI_at_rest_anahtari_tasinir_cihaz_kimligi_TASINMAZ(kokler):
    """Gerçek DPAPI (LOCAL_MACHINE) ile sarılı TEST anahtarları: ham değerler OLDUĞU GİBİ taşınır, hasta DB'si kopyalanır;
    cihaz kimliği / eşleştirme / bulut sırrı / kurtarma kodu / operatör sırları TAŞINMAZ."""
    from cryptography.fernet import Fernet
    from utils import secrets_manager as sm

    pu, eski, yeni = kokler
    kaynak = {
        "sqlcipher_key": sm._enc("D3I-O1-sqlcipher-test", critical=True),
        "patient_fernet_key": sm._enc(Fernet.generate_key().decode("ascii"), critical=True),
        "device_id": "111",
        "pairing_code": "ABC123",
        "api_token": "TOKEN",
        "admin_reset_code": "ADMIN",
        "device_registry_secret": "BULUT",
        "backup_recovery_code": "KURTARMA",
    }
    _sir_yaz(eski, kaynak)
    (eski / "patients.db").write_bytes(DUZ_DB)

    pu._kullanicidan_makineye_gocur(yeni)

    hedef = _auto(yeni)
    assert set(hedef) == {"sqlcipher_key", "patient_fernet_key"}, f"taşınan sır adları: {sorted(hedef)}"
    esit = all(hedef[k] == kaynak[k] for k in ("sqlcipher_key", "patient_fernet_key"))
    assert esit, "ham (DPAPI-sarılı) değer olduğu gibi taşınmadı (sır değeri yazdırılmadı)"
    assert "operator" not in json.loads((yeni / "pemf_secrets.json").read_text(encoding="utf-8")), (
        "operatör sırları taşındı"
    )
    assert (yeni / "patients.db").read_bytes() == DUZ_DB, "alan anahtarı taşındığı hâlde hasta DB'si kopyalanmadı"


def test_KRITIK_D3I_O1_bu_makinede_COZULEMEYEN_alan_anahtari_TASINMAZ_hasta_DBsi_eski_kokte_KALIR(kokler):
    """Çözülemeyen blob hedefe yazılırsa `get_secret` fail-closed → hasta DB'si hiç açılmaz; yazılmazsa hedef YENİ anahtar üretir →
    kopya okunamaz. İkisi de olmamalı: anahtar TAŞINMAZ, `patients.db` KOPYALANMAZ (eski kökte okunur kalır), öteki DB'ler taşınır.
    MUTASYON: alan anahtarında çözülebilirlik kapısı atlanır → KIRMIZI."""
    from utils import secrets_manager as sm

    pu, eski, yeni = kokler
    cozulemez = sm._DPAPI_PREFIX + base64.b64encode(b"baska-makinenin-alan-blobu" * 4).decode("ascii")
    _sir_yaz(eski, {"patient_fernet_key": cozulemez})
    (eski / "patients.db").write_bytes(DUZ_DB)
    (eski / "auth_users.db").write_bytes(DUZ_DB)
    once = _goruntu(eski)

    pu._kullanicidan_makineye_gocur(yeni)

    yazildi = "patient_fernet_key" in _auto(yeni)  # değer assert çıktısına düşmesin
    assert not yazildi, "bu makinede ÇÖZÜLEMEYEN alan anahtarı hedefe yazıldı → hasta DB'si açılmaz"
    assert not (yeni / "patients.db").exists(), (
        "alan anahtarı taşınamadığı hâlde hasta DB'si KOPYALANDI → adlar okunamaz"
    )
    assert (yeni / "auth_users.db").exists(), "göç tamamen kapandı"
    assert _goruntu(eski) == once, "KAYNAK değişti / silindi"


def test_KRITIK_D3I_O1_goc_yolu_SIR_KATMANINA_donmez_ozyineleme_yok(kokler, monkeypatch):
    """1.9.9/1.9.10 BSOD dersi: alan anahtarı göçü de saf JSON + `_dec` — `get_secret` / `get_sqlcipher_key` /
    `get_app_data_directory` ÇAĞRILMAZ. Kaynakta `sqlcipher_key` YOK (A-11 öncesi at-rest kapalı) — alan anahtarı yine taşınır."""
    import database.sqlcipher_util as su
    from utils import secrets_manager as sm

    pu, eski, yeni = kokler

    def _patlat(*a, **k):
        raise AssertionError("göç yolu sır / kripto katmanına döndü → özyineleme riski")

    sayac = {"n": 0}
    gercek = pu.get_app_data_directory

    def _sayan(*a, **k):
        sayac["n"] += 1
        return gercek(*a, **k)

    monkeypatch.setattr(sm, "get_secret", _patlat)
    monkeypatch.setattr(su, "get_sqlcipher_key", _patlat)
    monkeypatch.setattr(pu, "get_app_data_directory", _sayan)
    _sir_yaz(eski, {"patient_fernet_key": "DUZ-ALAN-ANAHTARI"})
    (eski / "patients.db").write_bytes(DUZ_DB)

    pu._kullanicidan_makineye_gocur(yeni)

    assert sayac["n"] == 0, f"göç yolu get_app_data_directory'yi {sayac['n']} kez çağırdı"
    assert _auto(yeni).get("patient_fernet_key") == "DUZ-ALAN-ANAHTARI", (
        "alan anahtarı taşınmadı (sqlcipher_key yokken)"
    )
    assert (yeni / "patients.db").exists()
