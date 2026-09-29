# Author: mertaygn, cglrgrkn
"""D0Ö.01 (B-3.84) KAPISI — hasta alan-şifreleme testi SIRAYA BAĞLI olmamalı.

ARIZA: `tests/test_patient_encryption.py` `PatientDatabase`'i MODÜL DÜZEYİNDE bağlıyordu.
`test_anahtar_uyusmazligi_karantina.py` `database.patient_database`'i sys.modules'tan silip
yeniden içe aktarınca test yamayı YENİ modüle yapıyor, bayat sınıf ise ESKİ modülün yamasız
`get_sqlcipher_key`'ini kullanıyordu. Makinede bir at-rest anahtarı varsa DB tümden şifreli
açılıyor, ham `sqlite3` okuması (:32) "file is not a database" ile düşüyor ve 'enc:' değişmezi
(:35-36) HİÇ denetlenmiyordu. Sahibin makinesinde tam süitte "bilinen sıra kırmızısı" diye
duruyordu — aynı noktadaki gerçek bir alan-şifreleme regresyonu onun içinde kaybolurdu.

KAPI: iki dosya AYNI alt süreçte, BU SIRAYLA koşar. Anahtar kaynağı denetimli kurulur:
gerçek kasa KAPALI (null keyring), anahtar yalnız `PEMF_SQLCIPHER_KEY`'den gelir. Böylece
"makinede anahtar var" durumu makineden BAĞIMSIZ üretilir.
⚠️ Anahtarı keyring üzerinden VERME: conftest kasayı süreç başında null'a yalıtır (D0Ö.02);
kasadan gelen tetik orada söner ve bu kapı sessizce kör olur (B-3.84 → B-3.6 sırası).

MUTASYON: `test_patient_encryption.py`'ye modül düzeyi `from database.patient_database import
PatientDatabase` bağını geri getirip `_db()`'yi ona bağlamak → bu test KIRMIZI.
"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_KARANTINA = "tests/test_anahtar_uyusmazligi_karantina.py"
_SIFRELEME = "tests/test_patient_encryption.py"


def _sqlcipher_var() -> bool:
    from database.sqlcipher_util import import_sqlcipher

    return import_sqlcipher() is not None


def test_KRITIK_sifreleme_testi_karantina_SONRASINDA_da_gecer(tmp_path):
    if not _sqlcipher_var():
        pytest.skip("sqlcipher3 yok: bayat sınıf da düz-metin açar, sıra kusuru bu ortamda TETİKLENEMEZ")

    junit = tmp_path / "sirali_cift.xml"
    env = dict(os.environ)
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"  # gerçek kasa ASLA
    env["PEMF_SQLCIPHER_KEY"] = "sira-kapisi-denetimli-anahtar"  # "makinede anahtar var"
    env.pop("PEMF_ENCRYPT_AT_REST", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", _KARANTINA, _SIFRELEME, f"--junitxml={junit}"],
        cwd=str(_KOK),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    cikti = (r.stdout or "")[-4000:] + (r.stderr or "")[-2000:]
    assert junit.is_file(), f"alt süreç junit üretmedi (rc={r.returncode}):\n{cikti}"

    sonuclar = []  # (dosya, test adı, sonuç) — koşum SIRASIYLA
    for tc in ET.parse(junit).getroot().iter("testcase"):
        sonuc = "passed"
        for alt in tc:
            if alt.tag in ("failure", "error", "skipped"):
                sonuc = alt.tag
        sonuclar.append((tc.get("classname", ""), tc.get("name", ""), sonuc))

    karantina = [s for s in sonuclar if "anahtar_uyusmazligi_karantina" in s[0]]
    sifreleme = [s for s in sonuclar if s[0].endswith("test_patient_encryption")]
    # ── Senaryo GERÇEKTEN kuruldu mu? (kurulmadıysa bu koşu hiçbir şey kanıtlamaz) ──
    assert karantina and all(s[2] == "passed" for s in karantina), (
        f"tetik koşmadı: karantina testleri geçmedi/atlandı → sys.modules silinmedi:\n{karantina}\n{cikti}"
    )
    assert any(s[1] == "test_KRITIK_ESKI_anahtarli_DB_backendi_OLDURMEZ" for s in karantina), (
        "sys.modules'u silen karantina testi koşu listesinde yok (çıpa kaymış olabilir)"
    )
    ilk_sifreleme = sonuclar.index(sifreleme[0]) if sifreleme else -1
    son_karantina = max(sonuclar.index(s) for s in karantina)
    assert sifreleme and son_karantina < ilk_sifreleme, f"sıra kurulamadı (karantina ÖNCE koşmalı):\n{sonuclar}"

    # ── Asıl iddia: yamalar gerçek modüle gidiyor → 'enc:' değişmezi (:35-36) gerçekten koşup geçiyor ──
    roundtrip = [s for s in sifreleme if s[1] == "test_patient_roundtrip_encrypted_at_rest"]
    assert roundtrip == [(sifreleme[0][0], "test_patient_roundtrip_encrypted_at_rest", "passed")], (
        f"karantinadan SONRA şifreleme testi sıraya bağlı düştü (bayat PatientDatabase bağı): {roundtrip}\n{cikti}"
    )
    assert all(s[2] == "passed" for s in sifreleme), f"şifreleme dosyasında başka kırmızı: {sifreleme}\n{cikti}"
    assert r.returncode == 0, f"sıralı çift rc={r.returncode}:\n{cikti}"
