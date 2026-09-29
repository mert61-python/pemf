# Author: mertaygn, cglrgrkn
"""D0Ö.02 (B-3.6) KAPISI — test süiti GERÇEK Windows kimlik kasasına DOKUNMAZ.

ARIZA (sahip ölçtü): tam süit gerçek kasaya 1603 okuma yapıyordu ve kasada
`PEMF_GUI/sqlcipher_key` VAR. Gerçek at-rest anahtarı test DB'lerine göçüyor, kopyaları
%TEMP%'te birikiyor, sonuçlar makinenin kasa durumuna bağlı kalıyordu. Süit bir klinik
PC'sinde koşturulursa o makinenin kasasını okur.

ÜÇ KOL (her biri ayrı mutasyonla kırmızı):
  1. Oturumdaki arka uç null olmalı — yalnız TÜRE bakar, kasaya çağrı yapmaz.
  2. Dış ortam ne verirse versin conftest null'a çekmeli: alt süreç TUZAK arka uçla
     (`keyring.backends.fail.Keyring` — her çağrıda hata, gerçek kasaya ASLA uzanmaz) başlar.
     conftest yalıtımı silinirse alt süreç tuzağı görür → KIRMIZI. (Dış koşucu null verse bile
     bu kol kör kalmaz: ortamı alt süreçte kendimiz kuruyoruz.)
  3. Gerçek Windows arka ucuna uzanan çağrı ENGELLENİR ve SAYILIR (conftest kaydedicisi).
     `win32cred` burada tuzakla değiştirilir → engel yoksa çağrı tuzağa düşer, gerçek kasaya değil.

MUTASYON: conftest'ten `PYTHON_KEYRING_BACKEND` + `keyring.set_keyring` yalıtımını silmek → (2)
KIRMIZI (ve dış ortam null değilse (1)). Engel sarmalayıcısını silmek → (3) KIRMIZI.
"""

import os
import subprocess
import sys
from pathlib import Path

import keyring
import pytest

_KOK = Path(__file__).resolve().parent.parent
_BU_DOSYA = "tests/test_kasa_yalitimi.py"


def test_KRITIK_oturum_kasa_arka_ucu_NULL():
    from keyring.backends import null

    kr = keyring.get_keyring()
    assert isinstance(kr, null.Keyring), (
        f"süit gerçek/başka bir kasa arka ucuyla koşuyor: {type(kr).__module__}.{type(kr).__name__} "
        "— tests/conftest.py kasayı null'a yalıtmalı (D0Ö.02)"
    )


def test_KRITIK_conftest_dis_ortamdan_BAGIMSIZ_yalitir(tmp_path):
    env = dict(os.environ)
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"  # TUZAK: gerçek kasa değil
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            f"{_BU_DOSYA}::test_KRITIK_oturum_kasa_arka_ucu_NULL",
        ],
        cwd=str(_KOK),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    cikti = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
    assert r.returncode == 0 and "1 passed" in (r.stdout or ""), (
        f"dış ortam tuzak arka uç verince conftest kasayı null'a ÇEKMEDİ (rc={r.returncode}):\n{cikti}"
    )


def test_KRITIK_gercek_kasa_cagrisi_ENGELLENIR_ve_SAYILIR(monkeypatch):
    kw = pytest.importorskip("keyring.backends.Windows")
    tuzak = []

    class _TuzakCred:
        """Gerçek `win32cred` yerine: WinVaultKeyring buraya ulaşırsa kasaya ULAŞMIŞ sayılır."""

        CRED_TYPE_GENERIC = 1
        CRED_PERSIST_ENTERPRISE = 3

        def __getattr__(self, ad):
            def _tuzak(*a, **k):
                tuzak.append(ad)
                raise RuntimeError(f"TUZAK: gerçek kasa API'si çağrıldı ({ad})")

            return _tuzak

    monkeypatch.setattr(kw, "win32cred", _TuzakCred(), raising=False)
    import conftest as _c

    kaydedici = getattr(_c, "_GERCEK_KASA_CAGRILARI", None)
    n0 = len(kaydedici) if kaydedici is not None else 0
    with pytest.raises(Exception):
        kw.WinVaultKeyring().get_password("PEMF_GUI", "d0o02-kapi-sondasi")
    assert tuzak == [], f"WinVaultKeyring gerçek kasa yoluna ULAŞTI ({tuzak}) — conftest engeli yok"
    assert kaydedici is not None, "conftest'te gerçek-kasa kaydedicisi (_GERCEK_KASA_CAGRILARI) yok"
    assert len(kaydedici) == n0 + 1, f"engellenen çağrı SAYILMADI: {kaydedici[n0:]}"
    assert kaydedici[n0][0] == "get_password", kaydedici[n0:]
    del kaydedici[n0:]  # kendi sondamız: kaydedici bu testi kırmasın
