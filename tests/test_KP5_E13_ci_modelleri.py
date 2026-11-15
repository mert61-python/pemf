# -*- coding: utf-8 -*-
"""KP-5 E13 (sahip Y279 / Y282): CI model paketi — `scripts/ci_modelleri.py`. Ağ YOK (indirme açıcısı sahte; yerel zip).

Sözleşme: (a) paket listeye göre doğrulanır — SHA-256 uyuşmazlığı, eksik dosya ya da listede OLMAYAN girdi → çıkış 1 (CI KIRMIZI,
"eser yoksa atla" YOK); (b) yerleştirme yalnız iki köke (`modeller/` → PEMF_AI_MODELS_DIR, `depo/` → depo kökü), zip-slip / mutlak
yol reddedilir; (c) gizli anahtar ortamdaysa `Authorization: Bearer` gönderilir, yoksa anahtarsız denenir; anahtar DEĞERİ basılmaz;
(d) başarıda `PEMF_AI_MODELS_DIR` GITHUB_ENV'e yazılır; (e) `paketle` listedeki her dosyayı kaynağından koyar ve özetleri yeniler;
(f) iş akışı adımı testlerden ÖNCE, anahtarı gizliden alır, hata yutmaz.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ci_modelleri_kp5", KOK / "scripts" / "ci_modelleri.py")
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


ICERIK = {
    "modeller/ai_hub/odak/veri/alan_tablosu.npz": b"ALAN",
    "depo/ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg": b"JPG",
}


def _liste(tmp_path: Path, icerik=ICERIK, kaynak="https://ornek.invalid/paket.zip") -> Path:
    p = tmp_path / "liste.json"
    p.write_text(
        json.dumps({"kaynak": {"url": kaynak}, "dosyalar": [{"yol": y, "sha256": _sha(b)} for y, b in icerik.items()]}),
        encoding="utf-8",
    )
    return p


def _zip(tmp_path: Path, icerik=ICERIK, ad="paket.zip") -> Path:
    z = tmp_path / ad
    with zipfile.ZipFile(z, "w") as f:
        for y, b in icerik.items():
            f.writestr(y, b)
    return z


def test_KRITIK_yerel_paket_dogrulanir_yerlestirilir_GITHUB_ENV_yazilir(tmp_path):
    hedef, depo, env = tmp_path / "m", tmp_path / "d", tmp_path / "env"
    rc = cm.indir(hedef, depo, str(env), _zip(tmp_path), liste_yolu=_liste(tmp_path))
    assert rc == 0
    assert (hedef / "ai_hub/odak/veri/alan_tablosu.npz").read_bytes() == b"ALAN"
    assert (depo / "ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg").read_bytes() == b"JPG"
    assert env.read_text(encoding="utf-8") == f"PEMF_AI_MODELS_DIR={hedef}\n"


@pytest.mark.parametrize(
    "bozuk, neden",
    [
        ({**ICERIK, "modeller/ai_hub/odak/veri/alan_tablosu.npz": b"BOZUK"}, "SHA-256 uyuşmuyor"),
        ({"depo/ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg": b"JPG"}, "pakette yok"),
        ({**ICERIK, "modeller/fazla.onnx": b"X"}, "listede olmayan girdi"),
    ],
)
def test_KRITIK_dogrulanamayan_paket_CIKIS_1_atlanmaz(tmp_path, capsys, bozuk, neden):
    rc = cm.indir(
        tmp_path / "m", tmp_path / "d", str(tmp_path / "env"), _zip(tmp_path, bozuk), liste_yolu=_liste(tmp_path)
    )
    assert rc == 1 and neden in capsys.readouterr().out
    assert not (tmp_path / "env").exists(), "doğrulanamayan pakette PEMF_AI_MODELS_DIR yazıldı"


@pytest.mark.parametrize(
    "yol", ["../kacis.txt", "modeller/../../kacis.txt", "/mutlak.txt", "C:/x.txt", "baska/x.onnx", "modeller\\x"]
)
def test_KRITIK_guvensiz_liste_yolu_REDDEDILIR(yol):
    with pytest.raises(ValueError):
        cm._guvenli_goreli(yol)


def test_bozuk_zip_ve_bos_liste(tmp_path, capsys):
    kotu = tmp_path / "kotu.zip"
    kotu.write_bytes(b"zip degil")
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, kotu, liste_yolu=_liste(tmp_path)) == 1
    assert "paket açılamadı" in capsys.readouterr().out
    bos = tmp_path / "bos.json"
    bos.write_text(json.dumps({"dosyalar": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        cm.liste_oku(bos)
    cift = tmp_path / "cift.json"
    k = {"yol": "modeller/a.onnx", "sha256": "0" * 64}
    cift.write_text(json.dumps({"dosyalar": [k, k]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cm.liste_oku(cift)


class _SahteYanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_KRITIK_anahtar_VARSA_Bearer_gonderilir_YOKSA_anahtarsiz_deger_BASILMAZ(tmp_path, monkeypatch, capsys):
    paket = _zip(tmp_path).read_bytes()
    istekler = []

    def ac(istek, timeout):
        istekler.append(istek)
        return _SahteYanit(paket)

    monkeypatch.delenv("PEMF_CI_MODEL_KAYNAGI", raising=False)
    monkeypatch.setenv("PEMF_CI_MODEL_ANAHTARI", "gizli-deger-123")
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=_liste(tmp_path)) == 0
    assert istekler[0].full_url == "https://ornek.invalid/paket.zip"
    assert istekler[0].get_header("Authorization") == "Bearer gizli-deger-123"
    assert "gizli-deger-123" not in capsys.readouterr().out, "anahtar DEĞERİ basıldı"
    monkeypatch.delenv("PEMF_CI_MODEL_ANAHTARI")
    monkeypatch.setenv("PEMF_CI_MODEL_KAYNAGI", "https://baska.invalid/p.zip")
    assert cm.indir(tmp_path / "m2", tmp_path / "d2", None, None, ac=ac, liste_yolu=_liste(tmp_path)) == 0
    assert istekler[1].full_url == "https://baska.invalid/p.zip" and istekler[1].get_header("Authorization") is None


def test_KRITIK_indirme_hatasi_ve_https_olmayan_kaynak_CIKIS_1(tmp_path, monkeypatch, capsys):
    def ac(istek, timeout):
        raise OSError("ağ yok")

    monkeypatch.delenv("PEMF_CI_MODEL_KAYNAGI", raising=False)
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=_liste(tmp_path)) == 1
    assert "indirilemedi" in capsys.readouterr().out
    assert (
        cm.indir(
            tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=_liste(tmp_path, kaynak="http://x/p.zip")
        )
        == 1
    )
    assert "https değil" in capsys.readouterr().out


def test_paketle_listedekileri_koyar_ozetleri_yeniler(tmp_path):
    modeller, depo = tmp_path / "rel", tmp_path / "repo"
    (modeller / "ai_hub/odak/veri").mkdir(parents=True)
    (modeller / "ai_hub/odak/veri/alan_tablosu.npz").write_bytes(b"YENI")
    (depo / "ai_hub/PEMF_AI_Test_Girdileri").mkdir(parents=True)
    (depo / "ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg").write_bytes(b"JPG")
    liste = _liste(tmp_path)
    assert cm.paketle(modeller, depo, tmp_path / "cikti.zip", liste) == 0
    yeni = {d["yol"]: d["sha256"] for d in json.loads(liste.read_text(encoding="utf-8"))["dosyalar"]}
    assert yeni["modeller/ai_hub/odak/veri/alan_tablosu.npz"] == _sha(b"YENI")
    with zipfile.ZipFile(tmp_path / "cikti.zip") as z:
        assert sorted(z.namelist()) == sorted(ICERIK)
    (depo / "ai_hub/PEMF_AI_Test_Girdileri/06_PetriKuyu.jpg").unlink()
    assert cm.paketle(modeller, depo, tmp_path / "c2.zip", liste) == 1


def test_main_komutlari(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "LISTE", _liste(tmp_path))
    z = _zip(tmp_path)
    assert cm.main(["indir", "--hedef", str(tmp_path / "m"), "--depo", str(tmp_path / "d"), "--yerel-zip", str(z)]) == 0
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{", encoding="utf-8")
    monkeypatch.setattr(cm, "LISTE", bozuk)
    assert cm.main(["indir", "--hedef", str(tmp_path / "m")]) == 2


def test_KRITIK_depodaki_liste_GECERLI_ve_ODAK_dosyalarini_icerir_Y282():
    veri = cm.liste_oku()
    yollar = {d["yol"] for d in veri["dosyalar"]}
    assert any(y.startswith("modeller/ai_hub/odak/veri/") and y.endswith(".onnx") for y in yollar), (
        "ODAK ONNX CI paketinde yok (Y282)"
    )
    assert "modeller/ai_hub/odak/veri/alan_tablosu.npz" in yollar, "ODAK alan tablosu CI paketinde yok (Y282)"
    assert not any("/odak/veri/" in y for y in _izlenen_dosyalar()), "ODAK veri dosyası açık depoda İZLENİYOR (Y282)"


def _izlenen_dosyalar() -> list[str]:
    import subprocess

    c = subprocess.run(
        ["git", "ls-files", "--", "ai_hub/odak/veri"], cwd=KOK, capture_output=True, text=True, check=True
    )
    return [y for y in c.stdout.splitlines() if not y.endswith(".json")]


def test_KRITIK_is_akisi_adimi_testlerden_ONCE_gizli_anahtarla_hata_YUTMAZ():
    yml = (KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    bas = yml.index("  backend:\n")
    is_ = yml[bas : yml.index("\n  sir-taramasi:", bas)]
    adim = re.search(r"- name: AI modelleri[^\n]*\n(?:\s{8}.*\n)+", is_)
    assert adim, "backend işinde AI model adımı yok"
    a = adim.group(0)
    assert "${{ secrets.PEMF_CI_MODEL_ANAHTARI }}" in a and "python scripts/ci_modelleri.py indir" in a
    assert "continue-on-error" not in a and "|| true" not in a and "|| echo" not in a, "model adımı hatayı yutuyor"
    assert is_.index("- name: AI modelleri") < is_.index("- name: Kritik-yol testleri"), "model adımı testlerden SONRA"
