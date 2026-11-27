# -*- coding: utf-8 -*-
"""CT1 b (istem 66 · Y324 · CI-STANDART #3): CI model paketi GENİŞLER — tam ağırlık ağacı (~4,2 GB) + PT ikizleri + test girdileri.
GitHub sürüm varlığı dosya başına 2 GiB sınırlı → paket PARÇALI (`scripts/ci_modelleri.py`). Ağ YOK (indirme açıcısı sahte).

Sözleşme: (a) `paketle` dosyaları parça sınırına (varsayılan 1900 MiB) göre parçalara böler, her dosya TEK parçada; tek dosya
sınırı aşarsa çıkış 1; parça adı / SHA-256 / bayt listeye (`paket.parcalar`) yazılır · (b) `indir` birden çok parçayı (yerel ya da
`PEMF_CI_MODEL_KAYNAGI`'nda boşlukla ayrılmış adresler) birleşik doğrular: adres sayısı ≠ parça sayısı, parça özeti listede yok, aynı
girdi iki parçada → çıkış 1 (atlama YOK) · (c) `--onbellek`: özeti tutan parça yeniden İNDİRİLMEZ, bozuk önbellek yeniden indirilir ·
(d) depodaki liste: tam ağırlık ağacı + test girdileri pakette, her parça < 2 GiB · (e) iş akışı: paket önbelleği (anahtar = liste
özeti) + süit `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` (eser yoksa atlama değil KIRMIZI)."""

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
_spec = importlib.util.spec_from_file_location("ci_modelleri_ct1b", KOK / "scripts" / "ci_modelleri.py")
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

GIB2 = 2 * 1024**3
ICERIK = {
    "modeller/ai_hub/a/buyuk.onnx": b"A" * 700,
    "modeller/ai_hub/b/orta.pt": b"B" * 500,
    "modeller/ai_hub/c/kucuk.pkl": b"C" * 300,
    "depo/ai_hub/PEMF_AI_Test_Girdileri/x.jpg": b"J" * 200,
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _kaynak(tmp_path: Path) -> tuple[Path, Path, Path]:
    modeller, depo = tmp_path / "rel", tmp_path / "repo"
    for y, b in ICERIK.items():
        kok, goreli = y.split("/", 1)
        p = (modeller if kok == "modeller" else depo) / goreli
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    liste = tmp_path / "liste.json"
    liste.write_text(
        json.dumps({"kaynak": {"url": ""}, "dosyalar": [{"yol": y, "sha256": "0" * 64} for y in ICERIK]}),
        encoding="utf-8",
    )
    return modeller, depo, liste


def _paketle(tmp_path: Path, ust: int = 1000) -> tuple[Path, list[Path]]:
    modeller, depo, liste = _kaynak(tmp_path)
    assert cm.paketle(modeller, depo, tmp_path / "out" / "paket.zip", liste, parca_ust=ust) == 0
    meta = json.loads(liste.read_text(encoding="utf-8"))["paket"]
    return liste, [tmp_path / "out" / p["ad"] for p in meta["parcalar"]]


@pytest.fixture(autouse=True)
def _ortam_temiz(monkeypatch):
    monkeypatch.delenv("PEMF_CI_MODEL_KAYNAGI", raising=False)
    monkeypatch.delenv("PEMF_CI_MODEL_ANAHTARI", raising=False)


def test_KRITIK_paketle_PARCA_sinirina_boler_her_dosya_TEK_parcada_meta_listeye(tmp_path):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path, ust=1000)
    veri = json.loads(liste.read_text(encoding="utf-8"))
    assert len(parcalar) == 2 and [p.name for p in parcalar] == ["paket_1.zip", "paket_2.zip"]
    gorulen = []
    for p, m in zip(parcalar, veri["paket"]["parcalar"]):
        with zipfile.ZipFile(p) as z:
            adlar = z.namelist()
            assert sum(z.getinfo(a).file_size for a in adlar) <= 1000, "parça sınırı aşıldı"
        gorulen += adlar
        assert m["sha256"] == _sha(p.read_bytes()) and m["bayt"] == p.stat().st_size and m["dosya"] == len(adlar)
    assert sorted(gorulen) == sorted(ICERIK), "dosya eksik ya da iki parçada"
    assert {d["yol"]: d["sha256"] for d in veri["dosyalar"]} == {y: _sha(b) for y, b in ICERIK.items()}
    assert veri["paket"]["parca_ust_bayt"] == 1000


def test_paketle_tek_parcaya_sigarsa_ADI_degismez(tmp_path):
    (tmp_path / "out").mkdir()
    _, parcalar = _paketle(tmp_path, ust=10_000)
    assert [p.name for p in parcalar] == ["paket.zip"]


def test_KRITIK_paketle_SINIRI_asan_tek_dosya_CIKIS_1(tmp_path, capsys):
    modeller, depo, liste = _kaynak(tmp_path)
    assert cm.paketle(modeller, depo, tmp_path / "p.zip", liste, parca_ust=600) == 1
    assert "parça sınırını aşan dosya" in capsys.readouterr().out
    assert not (tmp_path / "p.zip").exists()


def test_KRITIK_cok_parcali_YEREL_paket_dogrulanir_yerlestirilir(tmp_path):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    hedef, depo = tmp_path / "m", tmp_path / "d"
    assert cm.indir(hedef, depo, None, parcalar, liste_yolu=liste) == 0
    assert (hedef / "ai_hub/a/buyuk.onnx").read_bytes() == ICERIK["modeller/ai_hub/a/buyuk.onnx"]
    assert (depo / "ai_hub/PEMF_AI_Test_Girdileri/x.jpg").read_bytes() == ICERIK[
        "depo/ai_hub/PEMF_AI_Test_Girdileri/x.jpg"
    ]


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _acici(parcalar: list[Path], kayit: list):
    adres = {f"https://ornek.invalid/{i}": p.read_bytes() for i, p in enumerate(parcalar)}

    def ac(istek, timeout):
        kayit.append(istek)
        return _Yanit(adres[istek.full_url])

    return " ".join(adres), ac


def test_KRITIK_cok_parcali_ADRESLERDEN_indirilir_anahtar_her_parcada(tmp_path, monkeypatch):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    kayit: list = []
    kaynak, ac = _acici(parcalar, kayit)
    monkeypatch.setenv("PEMF_CI_MODEL_KAYNAGI", kaynak)
    monkeypatch.setenv("PEMF_CI_MODEL_ANAHTARI", "gizli")
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=liste) == 0
    assert len(kayit) == 2 and all(i.get_header("Authorization") == "Bearer gizli" for i in kayit)


def test_KRITIK_adres_sayisi_PARCA_sayisini_tutmazsa_CIKIS_1(tmp_path, monkeypatch, capsys):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    kayit: list = []
    kaynak, ac = _acici(parcalar, kayit)
    monkeypatch.setenv("PEMF_CI_MODEL_KAYNAGI", kaynak.split()[0])
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=liste) == 1
    assert "2 parça bekler" in capsys.readouterr().out and not kayit


def test_KRITIK_listede_OLMAYAN_parca_ozeti_CIKIS_1(tmp_path, capsys):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    with zipfile.ZipFile(parcalar[1], "a") as z:  # aynı girdiler + fazladan yorum → parça özeti değişir
        z.comment = b"kurcalandi"
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, parcalar, liste_yolu=liste) == 1
    assert "parça SHA-256" in capsys.readouterr().out


def test_KRITIK_ayni_girdi_IKI_parcada_CIKIS_1(tmp_path, capsys):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    veri = json.loads(liste.read_text(encoding="utf-8"))
    veri.pop("paket")  # parça özeti denetimi devre dışı → girdi denetimi tek başına
    liste.write_text(json.dumps(veri), encoding="utf-8")
    assert (
        cm.indir(tmp_path / "m", tmp_path / "d", None, [parcalar[0], parcalar[0], parcalar[1]], liste_yolu=liste) == 1
    )
    assert "birden çok parçada" in capsys.readouterr().out


def test_KRITIK_onbellek_TUTAN_parcayi_yeniden_indirmez_BOZUK_onbellegi_indirir(tmp_path, monkeypatch, capsys):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    kayit: list = []
    kaynak, ac = _acici(parcalar, kayit)
    monkeypatch.setenv("PEMF_CI_MODEL_KAYNAGI", kaynak)
    ob = tmp_path / "onbellek"
    assert cm.indir(tmp_path / "m", tmp_path / "d", None, None, ac=ac, liste_yolu=liste, onbellek=ob) == 0
    assert len(kayit) == 2 and len(list(ob.glob("*.zip"))) == 2
    assert cm.indir(tmp_path / "m2", tmp_path / "d2", None, None, ac=ac, liste_yolu=liste, onbellek=ob) == 0
    assert len(kayit) == 2, "önbellekte özeti tutan parçalar YENİDEN indirildi"
    assert "önbellekten: 2 parça" in capsys.readouterr().out
    sorted(ob.glob("*.zip"))[0].write_bytes(b"bozuk")
    assert cm.indir(tmp_path / "m3", tmp_path / "d3", None, None, ac=ac, liste_yolu=liste, onbellek=ob) == 0
    assert len(kayit) == 4, "bozuk önbellek yeniden indirilmedi"


def test_main_cok_parcali_yerel_ve_onbellek_secenekleri(tmp_path, monkeypatch):
    (tmp_path / "out").mkdir()
    liste, parcalar = _paketle(tmp_path)
    monkeypatch.setattr(cm, "_konsol_utf8", lambda: None)
    monkeypatch.setattr(cm, "LISTE", liste)
    arg = ["indir", "--hedef", str(tmp_path / "m"), "--depo", str(tmp_path / "d"), "--yerel-zip", *map(str, parcalar)]
    assert cm.main(arg) == 0
    modeller, depo, _ = _kaynak(tmp_path / "ikinci")
    monkeypatch.setattr(cm, "LISTE", tmp_path / "ikinci" / "liste.json")
    (tmp_path / "p2").mkdir()
    assert (
        cm.main(
            [
                "paketle",
                "--modeller",
                str(modeller),
                "--depo",
                str(depo),
                "--cikti",
                str(tmp_path / "p2" / "z.zip"),
                "--parca-mb",
                "1",
            ]
        )
        == 0
    )


def test_KRITIK_depodaki_liste_TAM_agac_ve_test_girdileri_PARCALAR_2GiB_altinda():
    veri = cm.liste_oku()
    yollar = {d["yol"] for d in veri["dosyalar"]}
    for gerekli in (
        "modeller/ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",
        "modeller/ai_hub/inference_em_petri/BaggingRegressor.onnx",
        "modeller/ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx",
        "modeller/ai_hub/inference_petri_dish/yolo11m-seg.onnx",
        "modeller/ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt",
        "modeller/ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.pt",
        "depo/ai_hub/PEMF_AI_Test_Girdileri/12a_YaraKapanma_0H.tif",
        "depo/ai_hub/PEMF_AI_Test_Girdileri/11_BobrekRNA.csv",
        "depo/ai_hub/inference_human_kidney_rna/mlp_medium_kirc.pt",
        "depo/ai_hub/inference_human_kidney_disease/preprocessor.pkl",
    ):
        assert gerekli in yollar, f"CI paketinde yok: {gerekli}"
    parcalar = veri["paket"]["parcalar"]
    assert parcalar and all(0 < p["bayt"] < GIB2 for p in parcalar), "GitHub sürüm varlığı 2 GiB / dosya"
    assert sum(p["dosya"] for p in parcalar) == len(veri["dosyalar"])
    assert all(d.get("bayt", 0) > 0 for d in veri["dosyalar"])


def _backend_isi() -> str:
    yml = (KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    bas = yml.index("  backend:\n")
    return yml[bas : yml.index("\n  sir-taramasi:", bas)]


def test_KRITIK_is_akisi_paket_ONBELLEGI_liste_ozetiyle_ve_ZORUNLU_kip():
    is_ = _backend_isi()
    ob = re.search(r"- name: AI model paketi önbelleği\n(?:\s{8}.*\n)+", is_)
    assert ob, "model paketi önbellek adımı yok (CT1 e)"
    a = ob.group(0)
    assert "actions/cache" in a and "hashFiles('scripts/ci_modelleri_listesi.json')" in a and "restore-keys" not in a
    assert is_.index("- name: AI model paketi önbelleği") < is_.index("- name: AI modelleri")
    adim = re.search(r"- name: AI modelleri[^\n]*\n(?:\s{8}.*\n)+", is_).group(0)
    assert "--onbellek" in adim
    assert '--hedef "$GITHUB_WORKSPACE/release_assets/ai_models"' in adim, "ağaç yayın makinesi düzeninde açılmıyor"
    test = re.search(r"- name: Kritik-yol testleri[^\n]*\n(?:\s{8}.*\n)+", is_).group(0)
    assert re.search(r'PEMF_CAPRAZ_KAYNAK_ZORUNLU: "1"', test), "CI süiti eser yoksa ATLIYOR (ZORUNLU kip yok)"


def test_KRITIK_pakette_git_te_IZLENEN_dosya_YOK():
    """🔴 ölçüldü (27-11, CI eşi): `release_assets/ai_models` altındaki 11 dosya git'te İZLENİR; paket onları guii kopyasıyla (LF) EZİYORDU,
    checkout kopyası CRLF (autocrlf) → spec'in bayt karşılaştırması (4B-2.5: modül kopyası ↔ release_assets kopyası) düştü, 16 spec
    testi KIRMIZI. İzlenen dosya checkout'tan gelir — pakete GİRMEZ."""
    import subprocess

    hedefler = []
    for d in cm.liste_oku()["dosyalar"]:
        kok, goreli = d["yol"].split("/", 1)
        hedefler.append(f"release_assets/ai_models/{goreli}" if kok == "modeller" else goreli)
    cikti = subprocess.run(["git", "ls-files", "-z", "--", *hedefler], cwd=KOK, capture_output=True, check=True).stdout
    izlenen = sorted(x for x in cikti.decode("utf-8").split("\x00") if x)
    assert not izlenen, f"pakette git'te İZLENEN dosya (checkout'u ezer): {izlenen}"
