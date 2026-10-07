# -*- coding: utf-8 -*-
"""2-A İNCELEME A2-1.1 · A2-1.3 (D2.45 · Y9 · Ö.4-Y8 · B-9.25) — ALAN ŞİFRELEME ANAHTARI İÇE AKTARMADA ALINMAZ.

ÖLÇÜLEN KUSUR. `pemf_gui/config.py`nin modül düzeyi singleton'ı (`config = ConfigManager()`) birincil alan anahtarını
(`patient_fernet_key`) KURULURKEN alıyordu; modül `backend_service` → `headless_core` → `patient_database` zincirinde
İÇE AKTARILIRKEN yüklenir:
  * Sır dosyası BOZUKKEN ya da `patient_fernet_key` bu makinede ÇÖZÜLEMEZKEN (makine değişimi / Windows yeniden
    kurulumu) fail-closed `RuntimeError` içe aktarmadan kaçıyor → backend HİÇ açılmıyor: ACİL DURDUR, sağlık ucu, açılış
    STOP mutabakatı, günlük YOK (uçtan uca kol: test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.py "sir_bozuk",
    "sir_cozulemez_ikisi"). Felaket kurtarma aracı (`PEMF_Backend.exe --kurtarma`) da aynı içe aktarmada ölüyordu.
  * Taze kurulumda içe aktarma YENİ bir `patient_fernet_key` üretip sır dosyasına yazıyor; `--kurtarma --yaz` onu
    "mevcut" sayıp "DURDURULDU: bu makinede zaten anahtar var → patient_fernet_key" (rc 3) diyordu — belgelenen kurtarma
    sırası (taze kur → `--yaz`) zorlama bayrağı olmadan YÜRÜMÜYORDU.

SÖZLEŞME: anahtar ilk ihtiyaçta (hasta DB'si açılırken) alınır; alınamazsa hasta DB'sine DOKUNULMADAN açılış düşer (DB'siz
kısıtlı kip — Y9), aynı süreçte sonraki deneme (Y43 arka plan yeniden açması) anahtarı YENİDEN alır.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"


@pytest.fixture
def sm(monkeypatch):
    """İzole veri kökünde temiz SecretsManager (ACL kilidi kaydedilmez, uygulanmaz)."""
    from utils import file_acl
    from utils import secrets_manager as _sm

    monkeypatch.setattr(file_acl, "lock_down_file", lambda *a, **k: True)
    _sm._cache = None
    yield _sm
    _sm._cache = None


def _cozulemeyen_blob(sm, tohum: bytes) -> str:
    onek = sm._DPAPI_PREFIX if os.name == "nt" else sm._MKEY_PREFIX
    return onek + base64.b64encode(tohum * 4).decode("ascii")


def test_KRITIK_A21_alan_anahtari_ALINAMAZKEN_hasta_DB_DOKUNULMADAN_acilmaz_sir_DUZELINCE_yeniden_baslatmadan_ACILIR(
    sm, tmp_path, monkeypatch
):
    """MUTASYON: anahtarı yeniden `__init__`te almak → KIRMIZI (kurucu düşer = modül düzeyi singleton içe aktarmada
    ölür); hasta DB kurucusunda anahtarı ALMAMAK → KIRMIZI (sır düzelince de açılmaz — Y43 iyileşmesi yok)."""
    import database.patient_database as pdb
    from cryptography.fernet import Fernet

    from pemf_gui.config import ConfigManager

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    sir = sm.secrets_path()
    sir.parent.mkdir(parents=True, exist_ok=True)
    sir.write_text(
        json.dumps(
            {
                "_version": 1,
                "auto": {"patient_fernet_key": _cozulemeyen_blob(sm, b"A21 baska makinenin fernet blobu ")},
                "operator": {},
                "embedded": {},
            }
        ),
        encoding="utf-8",
    )
    sm._cache = None
    try:
        cfg = ConfigManager(config_file=str(tmp_path / "cfg" / "config.json"))
    except RuntimeError as e:
        pytest.fail(
            f"ConfigManager KURULURKEN düştü — modül düzeyi singleton bu yüzden İÇE AKTARMADA ölür, backend (ACİL DURDUR "
            f"dahil) hiç açılmaz: {e}"
        )
    monkeypatch.setattr(pdb, "get_config", lambda: cfg)
    yol = tmp_path / "hasta" / "patients.db"
    yol.parent.mkdir()

    with pytest.raises(RuntimeError):
        pdb.PatientDatabase(str(yol))
    assert not yol.exists(), "alan anahtarı yokken hasta DB dosyası OLUŞTURULDU / dokunuldu"
    assert "Yeni RASTGELE" not in json.dumps(json.loads(sir.read_text(encoding="utf-8")))
    assert json.loads(sir.read_text(encoding="utf-8"))["auto"]["patient_fernet_key"].startswith(
        (sm._DPAPI_PREFIX, sm._MKEY_PREFIX)
    ), "çözülemeyen sır EZİLDİ"

    # Operatör doğru sırrı geri koydu (yedekten) — süreç YENİDEN BAŞLATILMADAN (Y43) hasta DB'si açılmalı.
    sm.set_secret("patient_fernet_key", Fernet.generate_key().decode("ascii"))
    db = pdb.PatientDatabase(str(yol))
    try:
        hid = db.add_patient({"name": "A21Hasta", "owner": "A21", "species": "Kedi"})
        assert (db.get_patient(hid) or {}).get("name") == "A21Hasta"
    finally:
        conn = getattr(getattr(db, "_local", None), "conn", None)
        if conn is not None:
            conn.close()


# ─────────────────────────── A2-1.3 · `PEMF_Backend.exe --kurtarma` (gerçek alt süreç) ───────────────────────────


def _kurtarma_kos(tmp_path: Path, argv: list, sir: dict | None = None, on_kod: str = ""):
    """`on_kod`: ürün koşmadan ÖNCE çocukta çalışan kod (ör. sır deposu yazımını düşüren alt-kat taklidi)."""
    veri = tmp_path / "veri"
    app = veri / "PEMF_GUI"
    app.mkdir(parents=True)
    if sir is not None:
        (app / "pemf_secrets.json").write_text(json.dumps(sir), encoding="utf-8")
    env = yalitik_ortam(tmp_path / "ev")
    env.update(
        {
            "PEMF_DATA_DIR": str(veri),
            "PEMF_DEVICE_IDENTITY_DIR": str(tmp_path / "kimlik"),
            "PEMF_CLOUD_PROVISION_PATH": str(tmp_path / "yok" / "p.json"),
            "PEMF_LOG_DIR": str(tmp_path / "log"),
            "PEMF_ENCRYPT_AT_REST": "1",
        }
    )
    kod = (
        f"import sys; sys.path.insert(0, r'{TESTLER}'); import alt_surec_ag_bekcisi as _ag; sys.path.remove(r'{TESTLER}'); "
        f"import runpy; sys.path.insert(0, r'{KOK}'); sys.path.insert(0, r'{BACKEND}')\n"
        f"{on_kod}"
        f"sys.argv = ['PEMF_Backend.exe'] + {argv!r}\n"
        "rc = 0\n"
        "try:\n"
        "    runpy.run_path(r'apps/backend/backend_service.py', run_name='__main__')\n"
        "except SystemExit as e:\n"
        "    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)\n"
        "print('AG=' + repr(_ag.ENGELLENEN)); print('RC=' + str(rc))\n"
    )
    (tmp_path / "kurtarma_surucu.py").write_text(kod, encoding="utf-8")
    p = kostur([str(tmp_path / "kurtarma_surucu.py")], cwd=KOK, env=env, sure=300)
    return p, app


def _zarf(tmp_path: Path):
    from utils.backup_recovery import build_envelope, generate_recovery_code

    kod = generate_recovery_code()
    z = tmp_path / "kurtarma-zarfi.enc"
    z.write_bytes(
        build_envelope(
            kod,
            {
                "sqlcipher_key": "SAHTE-KURTARMA-ANAHTARI",
                "patient_fernet_key": base64.urlsafe_b64encode(bytes(range(64, 96))).decode("ascii"),
            },
        )
    )
    return z, kod


def test_KRITIK_A13_TAZE_kurulumda_kurtarma_YAZ_anahtarlari_YAZAR(tmp_path):
    """Belgelenen felaket kurtarma sırası (tools/kurtarma.py): yeni makineye kur → `--kurtarma --zarf --kod --yaz`.
    İçe aktarma kendi anahtarını üretiyorsa araç onu "mevcut" sayıp DURUR (rc 3) — zarftaki anahtarlar yazılmaz."""
    z, kod = _zarf(tmp_path)
    p, app = _kurtarma_kos(tmp_path, ["--kurtarma", "--zarf", str(z), "--kod", kod, "--yaz"])
    cikti = p.stdout + p.stderr
    assert "AG=[]" in p.stdout, f"kurtarma alt süreci AĞA çıkmayı denedi: {p.stdout[-500:]}"
    assert "DURDURULDU" not in cikti, (
        "taze kurulumda kurtarma DURDU ('zaten anahtar var') — içe aktarma kendi anahtarını üretmiş: " + cikti[-600:]
    )
    assert "RC=0" in p.stdout, f"kurtarma --yaz başarısız: {cikti[-1200:]}"
    doc = json.loads((app / "pemf_secrets.json").read_text(encoding="utf-8"))
    assert all((doc.get("auto") or {}).get(k) for k in ("sqlcipher_key", "patient_fernet_key")), (
        "zarftaki anahtarlar sır deposuna YAZILMADI"
    )


def test_KRITIK_A13_COZULEMEYEN_eski_sir_dururken_kurtarma_araci_ACILIR(tmp_path):
    """Makine değişimi: eski veri kökü (çözülemeyen DPAPI sırlarıyla) yeni makinede duruyor; kurtarma aracı zarfı
    AÇABİLMELİ (göster kipi, yazmadan). Eskiden `import backend_service` ConfigManager'da `RuntimeError`la ölüyordu."""
    from utils import secrets_manager as _sm

    z, kod = _zarf(tmp_path)
    sir = {
        "_version": 1,
        "auto": {
            "sqlcipher_key": _cozulemeyen_blob(_sm, b"eski makine sqlcipher "),
            "patient_fernet_key": _cozulemeyen_blob(_sm, b"eski makine fernet "),
        },
        "operator": {},
        "embedded": {},
    }
    p, _app = _kurtarma_kos(tmp_path, ["--kurtarma", "--zarf", str(z), "--kod", kod], sir=sir)
    cikti = p.stdout + p.stderr
    assert "Zarf ACILDI" in cikti and "RC=0" in p.stdout, (
        f"çözülemeyen eski sır dururken kurtarma aracı AÇILAMADI: {cikti[-1500:]}"
    )


#: Sır deposunun `patient_fernet_key` taşıyan kaydını düşüren alt-kat taklidi (AV / kilit — `os.replace` PermissionError'ı).
_ALAN_ANAHTARI_YAZIMI_DUSER = (
    "from utils import secrets_manager as _sm\n"
    "_o_save = _sm._save\n"
    "def _save(doc):\n"
    "    if (doc.get('auto') or {}).get('patient_fernet_key'):\n"
    "        raise PermissionError(32, 'Dosya baska bir islem tarafindan kullaniliyor (taklit)')\n"
    "    return _o_save(doc)\n"
    "_sm._save = _save\n"
)


def test_KRITIK_A16_kurtarma_YAZ_yazim_DUSERSE_HICBIR_anahtar_yazilmaz_operator_UYARILIR(tmp_path):
    """2-A inceleme A2-1.6 (D2.45 · Karar 6): `--yaz` zarftaki anahtarları TEK yazımda kaydetmeli. Eskiden tek tek
    yazıyordu; `patient_fernet_key` kaydı düşünce `sqlcipher_key` diskte KALIYOR, araç ham istisnayla çıkıyor ve sonraki
    açılış eksik alan anahtarını YENİDEN ÜRETİYORDU (zarftakinden farklı → kurtarılan hasta alanları çözülemez; yeniden
    `--yaz` "zaten anahtar var" ile durur — ölçüldü). Artık hiçbir anahtar yazılmaz, araç rc 4 ile "servisi BAŞLATMAYIN" der.
    MUTASYON: `--yaz` anahtarları yeniden tek tek `set_secret` ile yazar → KIRMIZI."""
    z, kod = _zarf(tmp_path)
    p, app = _kurtarma_kos(
        tmp_path, ["--kurtarma", "--zarf", str(z), "--kod", kod, "--yaz"], on_kod=_ALAN_ANAHTARI_YAZIMI_DUSER
    )
    cikti = p.stdout + p.stderr
    assert "RC=4" in p.stdout and "HICBIR anahtar yazilmadi" in cikti and "BASLATMAYIN" in cikti, (
        f"yazım düştü ama araç yarım durumu ve yapılacağı SÖYLEMEDİ (ham istisna?): {cikti[-1500:]}"
    )
    assert "AG=[]" in p.stdout, f"kurtarma alt süreci AĞA çıkmayı denedi: {p.stdout[-500:]}"
    assert "yazildi:" not in cikti, f"yazım düştüğü hâlde 'yazildi' basıldı: {cikti[-800:]}"
    sir = app / "pemf_secrets.json"
    auto = (json.loads(sir.read_text(encoding="utf-8")) if sir.exists() else {}).get("auto") or {}
    yarim = [k for k in ("sqlcipher_key", "patient_fernet_key") if auto.get(k)]
    assert yarim == [], (
        f"yazım düştü ama sır deposunda YARIM anahtar kaldı: {yarim} -> sonraki açılış eksik alan anahtarını YENİDEN "
        "ÜRETİR, kurtarılan hasta alanları çözülemez"
    )
