# Author: mertaygn, cglrgrkn
"""D0Ö.02 (B-3.6) KAPISI — test süiti GERÇEK Windows kimlik kasasına python-keyring ile DOKUNMAZ.

ARIZA (sahip ölçtü): tam süit gerçek kasaya 1603 okuma yapıyordu ve kasada
`PEMF_GUI/sqlcipher_key` VAR. Gerçek at-rest anahtarı test DB'lerine göçüyor, kopyaları
%TEMP%'te birikiyor, sonuçlar makinenin kasa durumuna bağlı kalıyordu. Süit bir klinik
PC'sinde koşturulursa o makinenin kasasını okur.

KOLLAR (her biri ayrı mutasyonla kırmızı):
  1. Oturumdaki arka uç null olmalı — yalnız TÜRE bakar, kasaya çağrı yapmaz. Ayrıca conftest
     YÜKLEMEYEN bir torun süreç (env'i miras alır) de null görmeli: conftest'in env satırı
     taşıyıcıdır (ör. test_recovery_reachable `backend_service`'i conftest'siz koşar).
  2. Dış ortam ne verirse versin conftest null'a çekmeli: alt süreç TUZAK arka uçla
     (`keyring.backends.fail.Keyring` — her çağrıda hata, gerçek kasaya ASLA uzanmaz) başlar.
     conftest yalıtımı (ya da yalnız env satırı) silinirse alt süreç/torun tuzağı görür → KIRMIZI.
  3. Gerçek Windows arka ucuna uzanan çağrı ENGELLENİR ve SAYILIR (conftest kaydedicisi).
     `win32cred` burada tuzakla değiştirilir → engel yoksa çağrı tuzağa düşer, gerçek kasaya değil.
  4. Kaydedici, kasaya uzanan testi GERÇEKTEN kırmızı yapar: alt süreçte sonda testi koşar ve
     kaydını SİLMEZ → sonda ERROR olmalı.

⚠️ KAPSAM: yalnız python-keyring kanalı. `cmdkey` alt süreciyle kasaya dokunan teardown testleri
bu kapının dışındadır (açık bulgu).

MUTASYON: conftest'ten env + `set_keyring` yalıtımını silmek → (2) KIRMIZI; yalnız env satırını silmek
→ (2) KIRMIZI (torun); engel sarmalayıcısını silmek → (3) KIRMIZI; kaydedicinin `pytest.fail`'ini
silmek → (4) KIRMIZI.
"""

import os
import subprocess
import sys
from pathlib import Path

import keyring
import pytest

_KOK = Path(__file__).resolve().parent.parent
_BU_DOSYA = "tests/test_kasa_yalitimi.py"
_SONDA_ORTAMI = "D0O02_KAYDEDICI_SONDASI"


def _kayitli_conftest():
    """pytest'in YÜKLEDİĞİ conftest modülü. `import conftest` KULLANILMAZ: başka bir içe aktarma kipinde
    (importlib/xdist) ikinci bir kopya yaratıp bütün modül-düzeyi yan etkileri yeniden koşturur ve
    kaydediciyi sessizce körleştirirdi. Kayıtlı modül yoksa sessizce geçmek yerine KIRMIZI."""
    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (_KOK / "tests" / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir) — kasa kapısı ölçemez"
    )
    return c


class _TuzakCred:
    """Gerçek `win32cred` yerine: WinVaultKeyring buraya ulaşırsa kasaya ULAŞMIŞ sayılır."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_ENTERPRISE = 3

    def __init__(self):
        self.cagrilar = []

    def __getattr__(self, ad):
        def _tuzak(*a, **k):
            self.cagrilar.append(ad)
            raise RuntimeError(f"TUZAK: gerçek kasa API'si çağrıldı ({ad})")

        return _tuzak


def _pytest_alt_sureci(dugum: str, ek_env: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.update(ek_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist", "-q", "-rE", dugum],
        cwd=str(_KOK),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_KRITIK_oturum_kasa_arka_ucu_NULL():
    from keyring.backends import null

    kr = keyring.get_keyring()
    assert isinstance(kr, null.Keyring), (
        f"süit gerçek/başka bir kasa arka ucuyla koşuyor: {type(kr).__module__}.{type(kr).__name__} "
        "— tests/conftest.py kasayı null'a yalıtmalı (D0Ö.02)"
    )
    # conftest YÜKLEMEYEN torun süreç: arka ucu yalnız miras aldığı env'den seçer.
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import keyring; k = keyring.get_keyring(); print(type(k).__module__ + '.' + type(k).__name__)",
        ],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert (r.stdout or "").strip() == "keyring.backends.null.Keyring", (
        f"conftest'siz alt süreç kasa arka ucu olarak {r.stdout.strip() or r.stderr[-300:]!r} seçti — "
        "conftest'in PYTHON_KEYRING_BACKEND env satırı eksik; bu tür alt süreçler gerçek kasayı okur"
    )


def test_KRITIK_conftest_dis_ortamdan_BAGIMSIZ_yalitir(tmp_path):
    r = _pytest_alt_sureci(
        f"{_BU_DOSYA}::test_KRITIK_oturum_kasa_arka_ucu_NULL",
        {"PYTHON_KEYRING_BACKEND": "keyring.backends.fail.Keyring"},  # TUZAK: gerçek kasa değil
    )
    cikti = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
    assert r.returncode == 0 and "1 passed" in (r.stdout or ""), (
        f"dış ortam tuzak arka uç verince conftest kasayı null'a ÇEKMEDİ (rc={r.returncode}):\n{cikti}"
    )


def test_KRITIK_gercek_kasa_cagrisi_ENGELLENIR_ve_SAYILIR(monkeypatch):
    kw = pytest.importorskip("keyring.backends.Windows")
    tuzak = _TuzakCred()
    monkeypatch.setattr(kw, "win32cred", tuzak, raising=False)
    _c = _kayitli_conftest()

    kaydedici = getattr(_c, "_GERCEK_KASA_CAGRILARI", None)
    n0 = len(kaydedici) if kaydedici is not None else 0
    with pytest.raises(Exception):
        kw.WinVaultKeyring().get_password("PEMF_GUI", "d0o02-kapi-sondasi")
    assert tuzak.cagrilar == [], f"WinVaultKeyring gerçek kasa yoluna ULAŞTI ({tuzak.cagrilar}) — conftest engeli yok"
    assert kaydedici is not None, "conftest'te gerçek-kasa kaydedicisi (_GERCEK_KASA_CAGRILARI) yok"
    assert len(kaydedici) == n0 + 1, f"engellenen çağrı SAYILMADI: {kaydedici[n0:]}"
    assert kaydedici[n0][0] == "get_password", kaydedici[n0:]
    del kaydedici[n0:]  # kendi sondamız: kaydedici bu testi kırmasın


@pytest.mark.skipif(os.environ.get(_SONDA_ORTAMI) != "1", reason="yalnız kol 4 alt sürecinde koşar")
def test_SONDA_kaydedici_kasaya_uzanan_testi_KIRMIZI_yapar(monkeypatch):
    """Kol 4'ün sondası: kasaya uzanır ve kaydını SİLMEZ → autouse kaydedici bu testi ERROR yapmalı."""
    kw = pytest.importorskip("keyring.backends.Windows")
    monkeypatch.setattr(kw, "win32cred", _TuzakCred(), raising=False)
    with pytest.raises(Exception):
        kw.WinVaultKeyring().get_password("PEMF_GUI", "d0o02-kaydedici-sondasi")


def test_KRITIK_kaydedici_kasaya_uzanan_testi_KIRMIZI_yapar():
    pytest.importorskip("keyring.backends.Windows")
    r = _pytest_alt_sureci(f"{_BU_DOSYA}::test_SONDA_kaydedici_kasaya_uzanan_testi_KIRMIZI_yapar", {_SONDA_ORTAMI: "1"})
    cikti = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
    assert r.returncode != 0 and "1 error" in (r.stdout or ""), (
        f"kasaya uzanan sonda testi KIRMIZI olmadı — autouse kaydedici kör (rc={r.returncode}):\n{cikti}"
    )
    assert "GERÇEK kimlik kasasına uzandı" in (r.stdout or ""), f"hata kaydedicinin iletisi değil:\n{cikti}"
