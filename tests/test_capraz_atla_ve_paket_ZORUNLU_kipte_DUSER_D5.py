# -*- coding: utf-8 -*-
"""D5-F (K5-F P4) — `capraz.atla` / `capraz.paket_yoksa_atla`: eser / paket yoksa varsayılan kipte ATLAR, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞER.

🔴 ÖLÇÜLEN DURUM (2026-10-27, K5-F envanteri): `tests/` içinde yol DIŞI eser yokluğuna bağlı atlamalar (ürünün model köklerinden
çözümlenen ağırlık, `shutil.which` ile aranan araç ikilisi, `pytest.importorskip` ile isteğe bağlı paket) `capraz` kanalının
DIŞINDAYDI: yayın makinesinin `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` bayrağı bunları göremiyor, eksik eserle süit YEŞİL bitiyordu.
`capraz.atla_yoksa` yalnız depo köküne göre YOL alır; bu iki ikiz çözümleme sonucu / paket adı alır.

KAPI (davranış): gerçek `pytest.skip` / `pytest.fail` istisnaları yakalanır. Varsayılan kipte `importorskip` ile AYNI sonuç (3. taraf
alt bağımlılık eksikse de atlar — CI davranışı değişmez); DEPO paketinin eksik modülü atlamaya gizlenmez (ürün / taşıma hatası).
KARŞIT kol: düz `pytest.importorskip` ZORUNLU=1'de de ATLAR (ölçücü ayırt ediyor).
Meta kapı: `tests/test_atlama_ZORUNLU_kipte_DUSER_D5.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

_OLMAYAN = "pemf_k5f_olmayan_paket_6b1d"


def _yakala(cagri) -> BaseException | None:
    """Çağrının yükselttiği HER şeyi (Skipped / Failed / ImportError) yakalar — tür kolda denetlenir.

    ⚠️ `pytest.raises(Failed)` kullanılmaz: beklenmeyen `Skipped` raises'tan SIZAR ve testi KIRMIZI değil ATLANDI gösterir
    (ölçüldü — `atla`nın ZORUNLU kolunu silen mutantta ZORUNLU parametreli 4 test "skipped" oldu)."""
    try:
        cagri()
    except BaseException as e:  # noqa: BLE001 — tür aşağıda iddia edilir
        return e
    return None


@pytest.mark.parametrize("zorunlu", [False, True], ids=["varsayilan", "ZORUNLU"])
def test_KRITIK_atla_varsayilanda_ATLAR_zorunluda_DUSER(monkeypatch, zorunlu):
    monkeypatch.setattr(capraz, "ZORUNLU", zorunlu)
    beklenen = pytest.fail.Exception if zorunlu else pytest.skip.Exception
    e = _yakala(lambda: capraz.atla("ağırlık yok: ornek.onnx"))
    assert type(e) is beklenen, f"beklenen {beklenen.__name__}, gelen {type(e).__name__}: {e}"
    assert "ağırlık yok: ornek.onnx" in str(e)
    assert ("PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama" in str(e)) is zorunlu


@pytest.mark.parametrize("zorunlu", [False, True], ids=["varsayilan", "ZORUNLU"])
@pytest.mark.parametrize("ad", [_OLMAYAN, f"json.{_OLMAYAN}", "sqlcipher3_pemf_k5f_olmayan"])
def test_KRITIK_paket_YOKSA_varsayilanda_ATLAR_zorunluda_DUSER(monkeypatch, zorunlu, ad):
    monkeypatch.setattr(capraz, "ZORUNLU", zorunlu)
    beklenen = pytest.fail.Exception if zorunlu else pytest.skip.Exception
    e = _yakala(lambda: capraz.paket_yoksa_atla(ad, sebep="örnek"))
    assert type(e) is beklenen, f"beklenen {beklenen.__name__}, gelen {type(e).__name__}: {e}"
    assert f"isteğe bağlı paket yok: {ad} — örnek" in str(e)
    # A-46 yerel kapısı atlama NEDENİNDE "sqlcipher" arar: ad nedende kalmalı.
    if ad.startswith("sqlcipher"):
        assert "sqlcipher" in str(e).lower()


@pytest.mark.parametrize("zorunlu", [False, True], ids=["varsayilan", "ZORUNLU"])
def test_paket_VARSA_modulu_dondurur_ve_atlamaz(monkeypatch, zorunlu):
    monkeypatch.setattr(capraz, "ZORUNLU", zorunlu)
    import json

    assert capraz.paket_yoksa_atla("json") is json
    assert capraz.paket_yoksa_atla("json.decoder") is sys.modules["json.decoder"]


def _sahte_paket(tmp_path: Path, monkeypatch, ad: str, govde: str) -> None:
    paket = tmp_path / ad
    paket.mkdir()
    (paket / "__init__.py").write_text(govde, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, ad, raising=False)


@pytest.mark.parametrize("zorunlu", [False, True], ids=["varsayilan", "ZORUNLU"])
def test_KRITIK_3_taraf_ALT_BAGIMLILIK_eksik_importorskip_ile_AYNI(tmp_path, monkeypatch, zorunlu):
    """Paket VAR, içe aktarırken istediği 3. taraf bağımlılık YOK → `importorskip` gibi varsayılanda ATLAR (CI davranışı aynı),
    ZORUNLU'da DÜŞER; neden eksik modülü de söyler."""
    monkeypatch.setattr(capraz, "ZORUNLU", zorunlu)
    _sahte_paket(tmp_path, monkeypatch, "pemf_k5f_bagimli_paket", f"import {_OLMAYAN}_alt_bagimlilik\n")
    beklenen = pytest.fail.Exception if zorunlu else pytest.skip.Exception
    e = _yakala(lambda: capraz.paket_yoksa_atla("pemf_k5f_bagimli_paket"))
    assert type(e) is beklenen, f"beklenen {beklenen.__name__}, gelen {type(e).__name__}: {e}"
    assert f"isteğe bağlı paket yok: pemf_k5f_bagimli_paket ({_OLMAYAN}_alt_bagimlilik)" in str(e)


@pytest.mark.parametrize("zorunlu", [False, True], ids=["varsayilan", "ZORUNLU"])
@pytest.mark.parametrize("hedef", ["servers.pemf_k5f_olmayan_modul", "paket_ici"])
def test_KRITIK_DEPO_modulu_eksikse_ATLAMAYA_gizlenmez(tmp_path, monkeypatch, zorunlu, hedef):
    """Eksik modül DEPO paketindense (`servers.…`, `ai_hub.…`) bu "isteğe bağlı paket yok" değil ürün / taşıma hatasıdır →
    atlama da düşüş-mesajı da DEĞİL, `ImportError` olduğu gibi yükselir (her iki kipte)."""
    monkeypatch.setattr(capraz, "ZORUNLU", zorunlu)
    ad = hedef
    if hedef == "paket_ici":
        ad = "pemf_k5f_depoya_bagli_paket"
        _sahte_paket(tmp_path, monkeypatch, ad, "import ai_hub.pemf_k5f_olmayan_alt_modul\n")
    e = _yakala(lambda: capraz.paket_yoksa_atla(ad))
    assert isinstance(e, ImportError) and not isinstance(e, (pytest.skip.Exception, pytest.fail.Exception)), (
        f"depo modülü eksikliği {type(e).__name__} oldu (atlamaya / düşüşe GİZLENDİ): {e}"
    )
    assert (e.name or "").split(".")[0] in {"servers", "ai_hub"}


def _alt_kosu(tmp_path: Path, ad: str, govde: str, zorunlu: bool) -> tuple[int, str]:
    """`capraz.py` + tek test dosyası olan geçici bir kökte AYRI süreçte pytest (modül düzeyi davranış süreç içinde ölçülemez)."""
    kok = tmp_path / ad
    (kok / "tests").mkdir(parents=True)
    shutil.copy2(Path(capraz.__file__), kok / "tests" / "capraz.py")
    (kok / "tests" / "test_modul_duzeyi.py").write_text(govde, encoding="utf-8")
    (kok / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PEMF_CAPRAZ_KAYNAK_ZORUNLU"}
    if zorunlu:
        env["PEMF_CAPRAZ_KAYNAK_ZORUNLU"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    komut = [sys.executable, "-m", "pytest", str(kok / "tests" / "test_modul_duzeyi.py"), "-q", "-rfEs"]
    komut += ["-p", "no:cacheprovider", "-p", "no:randomly", "--rootdir", str(kok), "-c", str(kok / "pytest.ini")]
    r = subprocess.run(
        komut, cwd=kok, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    return r.returncode, r.stdout + r.stderr


def test_KRITIK_MODUL_DUZEYINDE_varsayilanda_modulu_ATLAR_zorunluda_TOPLAMA_HATASI(tmp_path):
    """`importorskip` gibi modül düzeyinde çağrılır: varsayılan kipte modül atlanır (öğe toplanmaz → çıkış 5 "test yok", kırmızı DEĞİL),
    ZORUNLU'da toplama hatası (çıkış 1/2 — kırmızı)."""
    govde = f"import capraz\n\ncapraz.paket_yoksa_atla({_OLMAYAN!r})\n\n\ndef test_a():\n    assert True\n"
    rc_v, cikti_v = _alt_kosu(tmp_path, "v", govde, zorunlu=False)
    rc_z, cikti_z = _alt_kosu(tmp_path, "z", govde, zorunlu=True)
    assert rc_v in (0, 5) and "1 skipped" in cikti_v, f"varsayılan kip: rc={rc_v}\n{cikti_v[-1500:]}"
    assert f"isteğe bağlı paket yok: {_OLMAYAN}" in cikti_v
    assert rc_z not in (0, 5) and "passed" not in cikti_z and "skipped" not in cikti_z, (
        f"ZORUNLU kip: modül düzeyi eksik paket yine ATLANDI / geçti: rc={rc_z}\n{cikti_z[-1500:]}"
    )
    assert f"PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama isteğe bağlı paket yok: {_OLMAYAN}" in cikti_z


def test_KARSIT_KANIT_duz_importorskip_ZORUNLU_kipte_de_ATLAR(monkeypatch):
    """Ölçücü körse yukarıdaki kapı anlamsızdır: ESKİ biçim (`pytest.importorskip`) ZORUNLU=1'de de Skipped yükseltir."""
    monkeypatch.setattr(capraz, "ZORUNLU", True)
    e = _yakala(lambda: pytest.importorskip(_OLMAYAN))
    assert type(e) is pytest.skip.Exception, f"düz importorskip artık {type(e).__name__} yükseltiyor — karşıt kol bayat"
