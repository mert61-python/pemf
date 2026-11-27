# -*- coding: utf-8 -*-
"""CT2 c (istem 66 · Y326 katman 6) — HIZLI PUSH + GECE TAM: kip kararı, küme seçimi ve iş akışı ayrımı.

· TAM: gece (cron / `kip: tam` çağrısı) · elle `kip=tam` · production-hardening / main / master push'u · birleşme tabanı yok ·
  geniş etkili dosya (conftest, test yardımcıları, kilitler, tests.yml, CI betikleri, defter / taban, i18n kataloğu) · çok dosya
· HIZLI: kalan push — küme = değişen testler + değişen dosyanın adını anan testler + sabit CI / i18n kapıları
· iş akışı: tam adım (`pytest tests`, fail_under = 100) YALNIZ tam kipte; hızlı adım YALNIZ hızlı kipte ve paket toplamını ölçmez —
  `--cov-fail-under=0` YALNIZ orada; fark kapsamı %100 iki kipte de; defter tam kipte tam, hızlı kipte `--kismi`
· gece.yml tests.yml'i `kip: tam` ile çağırır (gerekli DEĞİL)
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

KOK = Path(__file__).resolve().parents[1]
W = KOK / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("ci_hizli_kume_ct2c", KOK / "scripts" / "ci_hizli_kume.py")
hk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hk)


@pytest.fixture
def sahte_git(monkeypatch):
    durum = {"taban": "a" * 40, "degisen": []}
    monkeypatch.setattr(hk, "birlesme_tabani", lambda: durum["taban"])
    monkeypatch.setattr(hk, "degisenler", lambda t: list(durum["degisen"]))
    return durum


@pytest.mark.parametrize(
    "olay,dal,istek",
    [
        ("schedule", "production-hardening", ""),
        ("push", "production-hardening", ""),
        ("push", "main", ""),
        ("push", "master", ""),
        ("workflow_dispatch", "duzeltme/x", "tam"),
        ("workflow_call", "main", "tam"),
    ],
)
def test_KRITIK_yayin_dali_gece_ve_istek_TAM(sahte_git, olay, dal, istek):
    sahte_git["degisen"] = ["apps/backend/servers/auth.py"]
    assert hk.kip_belirle(olay, dal, istek)[0] == "tam"


@pytest.mark.parametrize(
    "dosya",
    [
        "tests/conftest.py",
        "tests/capraz.py",
        "tests/ci_atlanan_defteri.json",
        "tests/kapsam_tabani.json",
        "pyproject.toml",
        "requirements-test.txt",
        "build_tools/myenv-requirements.txt",
        ".github/workflows/tests.yml",
        "scripts/ci_hizli_kume.py",
        "scripts/fark_kapsami.py",
        "scripts/ci_sozlesmesi.json",
        "i18n/sunucu.tr.json",
        "apps/backend/backend_service.py",
    ],
)
def test_KRITIK_genis_etkili_dosya_TAM(sahte_git, dosya):
    sahte_git["degisen"] = [dosya, "apps/backend/servers/auth.py"]
    kip, neden, _, _ = hk.kip_belirle("push", "duzeltme/x", "")
    assert kip == "tam" and dosya in neden, (kip, neden)


def test_KRITIK_taban_yoksa_ve_cok_dosyada_TAM(sahte_git):
    sahte_git["taban"] = None
    assert hk.kip_belirle("push", "duzeltme/x", "")[0] == "tam"
    sahte_git["taban"] = "b" * 40
    sahte_git["degisen"] = [f"apps/backend/utils/m{i}.py" for i in range(hk.SINIR + 1)]
    assert hk.kip_belirle("push", "duzeltme/x", "")[0] == "tam"


def test_KRITIK_dar_degisiklik_HIZLI_kume_dogru(sahte_git):
    sahte_git["degisen"] = [
        "apps/backend/utils/secrets_manager.py",
        "tests/test_secrets_manager_LINUX_kalici_makine_kimligi_D412.py",
    ]
    kip, _, _, kume = hk.kip_belirle("push", "duzeltme/x", "")
    assert kip == "hizli"
    assert "tests/test_secrets_manager_LINUX_kalici_makine_kimligi_D412.py" in kume
    anan = [t for t in kume if "secrets_manager" in (KOK / t).read_text(encoding="utf-8", errors="replace")]
    assert len(anan) >= 5, f"modülü anan testler kümeye girmedi: {len(anan)}"
    for sabit in (
        "tests/test_ci_workflow_gate.py",
        "tests/test_CT2c_ci_hizli_kume_KIP.py",
        "tests/test_i18n_esle_K1.py",
    ):
        assert sabit in kume, sabit
    tum = len(list((KOK / "tests").glob("test_*.py")))
    assert len(kume) < tum, "küme tam süite eşit — hızlı kip kazanç sağlamıyor"


def test_kume_ANAHTARI_init_ve_kisa_ad(tmp_path):
    assert hk.anahtar("apps/backend/servers/auth.py") == "auth"
    assert hk.anahtar("apps/backend/servers/__init__.py") == "servers"
    assert hk.anahtar("firmware/stm32_pemf/Core/Src/main.c") == "main.c"
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("import zzmodul\n", encoding="utf-8")
    (tmp_path / "tests" / "test_b.py").write_text("x = 1\n", encoding="utf-8")
    assert "tests/test_a.py" in hk.kume(["pkg/zzmodul.py"], kok=tmp_path)
    assert "tests/test_b.py" not in hk.kume(["pkg/zzmodul.py"], kok=tmp_path)


def test_alan_karari(sahte_git):
    assert hk.alan_degisti("launcher", ["launcher/core/src/lib.rs"])
    assert not hk.alan_degisti("launcher", ["apps/backend/servers/auth.py"])
    assert hk.alan_degisti("firmware", ["firmware/stm32_pemf/Core/Src/main.c"])
    assert hk.alan_degisti("firmware", ["tests/firmware_dongu_aparat.py"])


def test_main_github_env_yazar(sahte_git, tmp_path):
    env = tmp_path / "env"
    sahte_git["degisen"] = ["apps/backend/servers/auth.py"]
    assert (
        hk.main(
            [
                "kip",
                "--olay",
                "push",
                "--dal",
                "duzeltme/x",
                "--github-env",
                str(env),
                "--kume-dosyasi",
                str(tmp_path / "k.txt"),
            ]
        )
        == 0
    )
    assert (
        "CI_KIP=hizli" in env.read_text(encoding="utf-8") and (tmp_path / "k.txt").read_text(encoding="utf-8").strip()
    )
    assert hk.main(["alan", "launcher", "--olay", "push", "--dal", "duzeltme/x", "--github-env", str(env)]) == 0
    assert "CI_ALAN=0" in env.read_text(encoding="utf-8")
    assert hk.main(["alan", "launcher", "--olay", "schedule", "--github-env", str(env)]) == 0
    assert env.read_text(encoding="utf-8").rstrip().endswith("CI_ALAN=1")


def test_firmware_testleri_APARAT_kullananlar_CT1g_haric(tmp_path):
    liste = hk.firmware_testleri()
    assert (
        "tests/test_firmware_ANA_DONGU_UART_teslimi_D1106.py" in liste
        and "tests/test_firmware_isr_ANA_MAKINE.py" in liste
    )
    assert "tests/test_CT1g_firmware_kapsam.py" not in liste, "CT1g sahte .gcda yazar — gcov kökünü bozar"
    assert hk.main(["firmware-testleri", "--kume-dosyasi", str(tmp_path / "f.txt")]) == 0


# ── iş akışı ─────────────────────────────────────────────────────────────────


def _backend() -> list[dict]:
    return yaml.safe_load((W / "tests.yml").read_text(encoding="utf-8"))["jobs"]["backend"]["steps"]


def _adim(ad: str) -> dict:
    a = [s for s in _backend() if s.get("name") == ad]
    assert len(a) == 1, ad
    return a[0]


def test_KRITIK_tam_ve_hizli_adim_AYRIMI():
    kip_i = next(i for i, s in enumerate(_backend()) if s.get("name") == "CI kipi (hızlı küme / tam süit)")
    tam = _adim("Kritik-yol testleri + kapsam ratcheti")
    hizli = _adim("Hızlı küme testleri (değişen alanlar — paket toplamı ölçülmez)")
    assert kip_i < _backend().index(tam) < _backend().index(hizli)
    assert tam["if"] == "runner.os == 'Windows' && env.CI_KIP == 'tam'"
    assert hizli["if"] == "runner.os == 'Windows' && env.CI_KIP == 'hizli'"
    assert "--cov-fail-under" not in tam["run"] and "--cov " in tam["run"]
    assert (
        "@ci_kume.txt" in hizli["run"]
        and "--cov-fail-under=0" in hizli["run"]
        and "--junitxml=pytest-junit.xml" in hizli["run"]
    )
    assert tam["env"] == hizli["env"], "iki kip farklı ortam bayraklarıyla koşuyor (ZORUNLU kip ayrışır)"
    disari = [
        s.get("name")
        for s in _backend()
        if "--cov-fail-under" in str(s.get("run", "")) and s.get("name") != hizli["name"]
    ]
    assert not disari, f"fail_under hızlı adım DIŞINDA eziliyor: {disari}"


def test_KRITIK_fark_kapsami_IKI_kipte_paket_toplami_YALNIZ_tamda():
    k = _adim("Kapsam kilidi (taban + fark kapsamı)")
    assert "if" not in k
    satirlar = [s for s in k["run"].splitlines() if s.strip()]
    assert re.search(
        r'if \[ "\$CI_KIP" = tam \]; then python scripts/kapsam_tabani_kapisi\.py --json coverage\.json; else .*--yalniz-json; fi',
        satirlar[0],
    )
    assert satirlar[1].strip() == "python scripts/fark_kapsami.py --covjson coverage.json"


def test_KRITIK_defter_TAMDA_tam_HIZLIDA_kismi():
    assert _adim("Atlanan defteri kapısı (CT1 c)")["if"] == "env.CI_KIP == 'tam'"
    h = _adim("Atlanan defteri kapısı — hızlı küme (kısmi)")
    assert h["if"] == "env.CI_KIP == 'hizli'" and h["run"].endswith("--kismi")


def test_KRITIK_gece_TAM_kipte_cagirir_ve_tests_yml_cagrilabilir():
    gece = yaml.safe_load((W / "gece.yml").read_text(encoding="utf-8"))
    tetik = gece.get("on", gece.get(True))
    assert tetik["schedule"][0]["cron"] and "workflow_dispatch" in tetik
    is_ = gece["jobs"]["tam"]
    assert (
        is_["uses"] == "./.github/workflows/tests.yml" and is_["with"]["kip"] == "tam" and is_["secrets"] == "inherit"
    )
    t = yaml.safe_load((W / "tests.yml").read_text(encoding="utf-8"))
    tt = t.get("on", t.get(True))
    assert tt["workflow_call"]["inputs"]["kip"]["default"] == "tam"
    assert "tam" in tt["workflow_dispatch"]["inputs"]["kip"]["options"]
    assert gece["concurrency"]["group"] != t["concurrency"]["group"], (
        "çağıran ve çağrılan aynı eşzamanlılık grubu → kilitlenir"
    )


def test_kip_adimi_olay_dal_istek_gecirir():
    run = _adim("CI kipi (hızlı küme / tam süit)")["run"]
    for parca in ("${{ github.event_name }}", "${{ github.ref_name }}", "${{ inputs.kip }}", '"$GITHUB_ENV"'):
        assert parca in run, parca


def test_sozlesme_gece_dosyasi_ayni():
    soz = json.loads((KOK / "scripts" / "ci_sozlesmesi.json").read_text(encoding="utf-8"))
    assert (W / soz["gece"]["dosya"]).is_file()
