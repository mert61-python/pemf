# -*- coding: utf-8 -*-
"""CT2 a (istem 66 · Y326 katman 1) — YAYIN CI KAPISI: uç commit'in GitHub CI'ında GEREKLİ işlerin hepsi yeşil değilse ya da biri
koşmadıysa yayın DURUR; liste TEK yerde (`scripts/ci_sozlesmesi.json`, CT3 dal koruması da onu kullanır); gece kırmızısı UYARI.

Ölçüm (ağ YOK): `scripts/ci_durum.py` değerlendirmesi sahte check-run kayıtlarıyla; `yayin_ci_kapisi.ps1` gerçek pwsh ile sahte JSON
dosyalarıyla; `publish_release.ps1` Y30 sarmalında (süit → CI kapısı → kimlik sırası) CI kırmızısında kimlik adımına GEÇMEZ.
Sözleşme ↔ iş akışları: her gerekli iş HER push'ta koşan (yol süzgeçsiz, iş düzeyi koşulsuz) bir işin GERÇEK adıdır.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_yayin_oncesi_suit_Y30_D410 import BETIKLER, _publish_golge, _pwsh_gerekli

KOK = Path(__file__).resolve().parents[1]
W = KOK / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("ci_durum_ct2a", KOK / "scripts" / "ci_durum.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)
SOZ = cd.sozlesme_oku()


def _hepsi_yesil(ek: list[dict] | None = None) -> list[dict]:
    kayit = [
        {"id": 100 + i, "name": g["ad"], "status": "completed", "conclusion": "success", "html_url": f"u{i}"}
        for i, g in enumerate(SOZ["gerekli_isler"])
    ]
    return kayit + (ek or [])


GECE_YESIL = {"conclusion": "success", "html_url": "g", "created_at": "t"}


def test_KRITIK_hepsi_yesil_DURMAZ():
    dur, uyari, yesil = cd.degerlendir(SOZ, _hepsi_yesil(), GECE_YESIL)
    assert not dur and len(yesil) == len(SOZ["gerekli_isler"])


@pytest.mark.parametrize("bozuk", ["eksik", "suruyor", "kirmizi", "iptal"])
def test_KRITIK_gerekli_is_eksik_SURUYOR_kirmizi_ise_DURUR(bozuk):
    kayit = _hepsi_yesil()
    hedef = SOZ["gerekli_isler"][0]["ad"]
    if bozuk == "eksik":
        kayit = [k for k in kayit if k["name"] != hedef]
    else:
        k = next(k for k in kayit if k["name"] == hedef)
        k.update(
            {"suruyor": {"status": "in_progress", "conclusion": None}, "kirmizi": {"conclusion": "failure"}}.get(
                bozuk, {"conclusion": "cancelled"}
            )
        )
    dur, _, _ = cd.degerlendir(SOZ, kayit, GECE_YESIL)
    assert len(dur) == 1 and hedef in dur[0], dur


def test_yeniden_kosu_EN_SON_kayit_gecerli():
    hedef = SOZ["gerekli_isler"][0]["ad"]
    kayit = _hepsi_yesil([{"id": 1, "name": hedef, "status": "completed", "conclusion": "failure"}])
    assert not cd.degerlendir(SOZ, kayit, GECE_YESIL)[0], "eski kırmızı, sonraki yeşil yeniden koşuyu gölgeledi"
    kayit = _hepsi_yesil([{"id": 999, "name": hedef, "status": "completed", "conclusion": "failure"}])
    assert cd.degerlendir(SOZ, kayit, GECE_YESIL)[0], "son koşu kırmızıyken yayın geçti"


def test_KRITIK_kosulluysa_gerekli_KOSMADIYSA_engel_degil_KOSTUYSA_yesil_olmali():
    ad = SOZ["kosulluysa_gerekli"][0]["ad"]
    dur, uyari, _ = cd.degerlendir(SOZ, _hepsi_yesil(), GECE_YESIL)
    assert not dur and any(ad in u for u in uyari)
    kirmizi = _hepsi_yesil([{"id": 5000, "name": ad, "status": "completed", "conclusion": "failure", "html_url": "x"}])
    assert any(ad in d for d in cd.degerlendir(SOZ, kirmizi, GECE_YESIL)[0])


def test_KRITIK_gece_kirmizisi_UYARI_yayini_DURDURMAZ():
    dur, uyari, _ = cd.degerlendir(SOZ, _hepsi_yesil(), {"conclusion": "failure", "html_url": "g", "created_at": "t"})
    assert not dur and any("GECE" in u for u in uyari)
    dur, uyari, _ = cd.degerlendir(SOZ, _hepsi_yesil(), None)
    assert not dur and any("gece" in u for u in uyari)


def _json(tmp_path: Path, ad: str, veri) -> Path:
    p = tmp_path / ad
    p.write_text(json.dumps(veri) if not isinstance(veri, str) else veri, encoding="utf-8")
    return p


def test_KRITIK_main_sahte_durumla_cikis_kodlari(tmp_path, capsys):
    gece = _json(tmp_path, "g.json", GECE_YESIL)
    yesil = _json(tmp_path, "y.json", "\n".join(json.dumps(k) for k in _hepsi_yesil()))
    assert cd.main(["--sha", "a" * 40, "--checks-json", str(yesil), "--gece-json", str(gece)]) == 0
    kirmizi = _hepsi_yesil()
    kirmizi[1]["conclusion"] = "failure"
    k = _json(tmp_path, "k.json", kirmizi)
    assert cd.main(["--sha", "a" * 40, "--checks-json", str(k), "--gece-json", str(gece)]) == 1
    assert "YAYIN DURDU" in capsys.readouterr().out
    assert (
        cd.main(
            ["--sha", "a" * 40, "--checks-json", str(_json(tmp_path, "b.json", "{bozuk")), "--gece-json", str(gece)]
        )
        == 2
    )


def test_KRITIK_gh_YOKSA_fail_closed(monkeypatch, capsys):
    monkeypatch.setattr(cd.shutil, "which", lambda ad: None)
    assert cd.main(["--sha", "b" * 40]) == 2
    assert "OKUNAMADI" in capsys.readouterr().out


def test_gh_sorgusu_check_runs_ve_gece_dosyasi(monkeypatch):
    cagri = []

    def sahte(args, **k):
        cagri.append(args)
        cikti = json.dumps(_hepsi_yesil()[0]) if "check-runs" in " ".join(args) else json.dumps(GECE_YESIL)
        return subprocess.CompletedProcess(args, 0, cikti + "\n", "")

    monkeypatch.setattr(cd.shutil, "which", lambda ad: "gh")
    monkeypatch.setattr(cd.subprocess, "run", sahte)
    assert cd.check_runlari_getir("o/r", "c" * 40)[0]["name"] == SOZ["gerekli_isler"][0]["ad"]
    assert cd.gece_son_kosu("o/r", "gece.yml")["conclusion"] == "success"
    assert "repos/o/r/commits/" + "c" * 40 + "/check-runs?per_page=100" in cagri[0]
    assert "repos/o/r/actions/workflows/gece.yml/runs?per_page=1&status=completed" in cagri[1]
    monkeypatch.setattr(cd.subprocess, "run", lambda a, **k: subprocess.CompletedProcess(a, 1, "", "HTTP 401"))
    with pytest.raises(RuntimeError, match="401"):
        cd.check_runlari_getir("o/r", "c" * 40)


# ── sözleşme ↔ iş akışları ───────────────────────────────────────────────────


def _akislar() -> dict[str, tuple[str, dict]]:
    sonuc = {}
    for p in sorted(W.glob("*.yml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        sonuc[d["name"]] = (p.name, d)
    return sonuc


def _is_adlari(is_id: str, is_: dict) -> list[str]:
    ad = str(is_.get("name") or is_id)
    if "${{ matrix.os }}" in ad:
        return [ad.replace("${{ matrix.os }}", os_) for os_ in is_["strategy"]["matrix"]["os"]]
    return [ad]


def test_KRITIK_her_GEREKLI_is_HER_pushta_kosan_gercek_is():
    akis = _akislar()
    for g in SOZ["gerekli_isler"]:
        assert g["is_akisi"] in akis, f"sözleşmedeki iş akışı yok: {g}"
        dosya, d = akis[g["is_akisi"]]
        tetik = d.get("on", d.get(True))
        assert "push" in tetik and "production-hardening" in tetik["push"]["branches"], f"{dosya}: push'ta koşmuyor"
        assert "paths" not in tetik["push"], (
            f"{dosya}: yol süzgeçli iş GEREKLİ olamaz (koşmadığında durum yazmaz → dal kilitlenir)"
        )
        eslesen = [(i, j) for i, j in d["jobs"].items() if g["ad"] in _is_adlari(i, j)]
        assert len(eslesen) == 1, f"{dosya}: '{g['ad']}' adlı iş {len(eslesen)} (tam bir olmalı)"
        assert "if" not in eslesen[0][1], (
            f"{dosya}: gerekli iş '{g['ad']}' iş düzeyinde koşullu (atlanırsa durum yazmaz)"
        )


def test_KRITIK_kosulluysa_gerekli_isler_YOL_SUZGECLI_ve_gece_GEREKLI_DEGIL():
    akis = _akislar()
    for g in SOZ["kosulluysa_gerekli"]:
        dosya, d = akis[g["is_akisi"]]
        assert "paths" in d.get("on", d.get(True))["push"], f"{dosya}: yol süzgeci yok — gerekli listeye alınmalı"
        assert any(g["ad"] in _is_adlari(i, j) for i, j in d["jobs"].items()), g
    gece_dosya, gece = akis[SOZ["gece"]["is_akisi"]]
    assert gece_dosya == SOZ["gece"]["dosya"] and "schedule" in gece.get("on", gece.get(True))
    assert SOZ["gece"]["is_akisi"] not in {g["is_akisi"] for g in SOZ["gerekli_isler"]}
    assert "istem 64 OF1" in " ".join(SOZ["on_denetim"]), "64'ün ekleyeceği ön denetim satırı belgelenmemiş (Y322)"


# ── yayın betikleri ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "betik,sonraki",
    [
        ("publish_release.ps1", "| git credential fill"),
        ("katmanli_yayin_hazirla.ps1", r"(Join-Path $kok 'scripts\make_manifest.py')"),
    ],
)
def test_KRITIK_yayin_betikleri_Y30_SONRA_CI_kapisi_kimlik_manifest_ONCE(betik, sonraki):
    t = (BETIKLER / betik).read_text(encoding="utf-8-sig")
    i_y30 = t.index("& (Join-Path $PSScriptRoot 'yayin_oncesi_suit.ps1')")
    i_ci, i_son = t.index("& (Join-Path $PSScriptRoot 'yayin_ci_kapisi.ps1')"), t.index(sonraki)
    assert i_y30 < i_ci < i_son, (betik, i_y30, i_ci, i_son)
    blok = t[i_ci : i_ci + 400]
    assert "if ($LASTEXITCODE -ne 0) { throw" in blok, f"{betik}: CI kapısı çıkış kodu yayını DURDURMUYOR"


def test_KRITIK_yayin_ci_kapisi_ASCII_ve_PS51_kurali():
    ham = (BETIKLER / "yayin_ci_kapisi.ps1").read_bytes()
    assert all(b < 128 for b in ham), "yayin_ci_kapisi.ps1 ASCII değil (PS 5.1 BOM'suz betiği ANSI okur)"


def _kapi_kos(tmp_path: Path, kayit: list[dict]) -> subprocess.CompletedProcess:
    pwsh = _pwsh_gerekli()
    c = _json(tmp_path, "c.json", kayit)
    g = _json(tmp_path, "g.json", GECE_YESIL)
    return subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BETIKLER / "yayin_ci_kapisi.ps1"),
         "-Python", sys.executable, "-Sha", "d" * 40, "-ChecksJson", str(c), "-GeceJson", str(g)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )  # fmt: skip


def test_KRITIK_yayin_ci_kapisi_GERCEK_pwsh_kirmizida_1_yesilde_0(tmp_path):
    kirmizi = _hepsi_yesil()
    kirmizi[2]["conclusion"] = "failure"
    (tmp_path / "k").mkdir()
    r = _kapi_kos(tmp_path / "k", kirmizi)
    assert r.returncode == 1 and kirmizi[2]["name"] in r.stdout, r.stdout + r.stderr
    (tmp_path / "y").mkdir()
    r = _kapi_kos(tmp_path / "y", _hepsi_yesil())
    assert r.returncode == 0 and "CI kapısı: tamam" in r.stdout, r.stdout + r.stderr


def test_KRITIK_publish_CI_KIRMIZIYKEN_kimlik_ve_aga_DOKUNMADAN_durur(tmp_path):
    rc, kayit, cikti = _publish_golge(tmp_path, suit_rc=0, ci_rc=1)
    assert kayit == ["SUIT", "CI"], f"CI kırmızıyken publish ilerledi ya da sıra bozuk: {kayit}\n{cikti[-800:]}"
    assert rc == 9 and "CT2 a" in cikti and "PUBLISH-BITTI" not in cikti, f"rc={rc}\n{cikti[-800:]}"


def test_KARSIT_publish_CI_YESILKEN_kimlik_adimina_gecer(tmp_path):
    rc, kayit, cikti = _publish_golge(tmp_path, suit_rc=0, ci_rc=0)
    assert kayit[:2] == ["SUIT", "CI"] and any(s.startswith("GIT credential") for s in kayit[2:]), (
        f"{kayit}\n{cikti[-800:]}"
    )


def test_sozlesme_bicimi():
    assert re.fullmatch(r"\d+\.\d+\.\d+", SOZ["urun_python"])
    adlar = [g["ad"] for g in SOZ["gerekli_isler"]]
    assert len(adlar) == len(set(adlar)) >= 5
