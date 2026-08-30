# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""XAI BATCH RAPOR CLI — davranış kilitleri (docs/xai-entegrasyon-plani.md §KALAN B).

Kilitlenenler:
 1) Çıktı-dizini bekçisi: girdinin içine/kendisine yazmak AÇIK SystemExit
    (özyinelemeli kendi-çıktısı tuzağı — sonraki koşu çıktıyı girdi sanır).
 2) RNA işaretli CSV: attribution işareti yön okuna (↑/↓) doğru çevrilir.
 3) Zarif düşüş: tek dosyanın hatası akışı DÜŞÜRMEZ — summary'de hata satırı,
    kalan dosyalar işlenir, index.html yine yazılır.
 4) PDF üreticisi generate_xai_report: görselli PDF üretir; OKUNAMAYAN görüntü
    raporu düşürmez (uyarı + metin satırı).
"""

import csv
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("xai_batch_rapor", KOK / "scripts" / "xai_batch_rapor.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["xai_batch_rapor"] = m
    spec.loader.exec_module(m)
    return m


# ── 1) çıktı bekçisi ─────────────────────────────────────────────────────────
def test_KRITIK_cikti_girdinin_icindeyse_ACIK_hata(cli, tmp_path):
    girdi = tmp_path / "fotolar"
    girdi.mkdir()
    with pytest.raises(SystemExit, match="kendi çıktısını"):
        cli._cikti_bekcisi(girdi, girdi / "out")
    with pytest.raises(SystemExit, match="kendi çıktısını"):
        cli._cikti_bekcisi(girdi, girdi)  # çıktı == girdi


def test_KARSIT_KANIT_disaridaki_cikti_ve_TEK_DOSYA_gecer(cli, tmp_path):
    girdi = tmp_path / "fotolar"
    girdi.mkdir()
    cli._cikti_bekcisi(girdi, tmp_path / "cikti")  # raise etmemeli
    # TEK-DOSYA girdisinde tarama yok → aynı klasöre çıktı SERBEST (düşman-doğrulama
    # 2026-08-27: eski hâli docstring'in kendi 'hasta.csv → out_rna' örneğini reddediyordu)
    (girdi / "hasta.csv").write_text("x", encoding="utf-8")
    cli._cikti_bekcisi(girdi / "hasta.csv", girdi / "out_rna")


def test_KRITIK_bekci_main_uzerinden_BAGLI(cli, tmp_path, monkeypatch):
    """Wiring kilidi: helper'ı değil main()'i ölç — main bekçiyi çağırmayı bırakırsa kırmızı
    (mutasyon-körlüğü ölçüldü: yalnız-helper testi wiring silinince yeşil kalıyordu)."""
    girdi = tmp_path / "fotolar"
    girdi.mkdir()
    (girdi / "a.jpg").write_bytes(b"x")
    monkeypatch.setattr(
        "sys.argv",
        ["xai_batch_rapor", "--modul", "ct", "--girdi", str(girdi), "--cikti", str(girdi / "out")],
    )
    with pytest.raises(SystemExit, match="kendi çıktısını"):
        cli.main()


def test_KRITIK_tarama_cikti_icine_cozumlenen_yollari_ATLAR(cli, tmp_path):
    """Symlink/junction deliği (ölçüldü): girdi içindeki bağlantı çıktıya işaret ederse
    tarama onu İŞLEMEMELİ — yoksa sonraki koşu kendi çıktısını girdi sanır."""
    girdi = tmp_path / "fotolar"
    girdi.mkdir()
    (girdi / "a.jpg").write_bytes(b"x")
    cikti = tmp_path / "out"
    cikti.mkdir()
    (cikti / "eski_xai.jpg").write_bytes(b"x")
    link = girdi / "link"
    try:
        link.symlink_to(cikti, target_is_directory=True)
    except OSError:
        pytest.skip("bu ortamda symlink izni yok (Windows dev-mode kapalı)")
    dosyalar = cli._dosyalari_tara(girdi, cikti, {".jpg"}, None)
    adlar = [p.name for p in dosyalar]
    assert "a.jpg" in adlar and "eski_xai.jpg" not in adlar, adlar


def test_KRITIK_ayni_stem_farkli_klasor_AYRI_ciktiya(cli, tmp_path, monkeypatch):
    """Özyinelemeli taramada klinik1/kedi.jpg ile klinik2/kedi.jpg aynı çıktıya yazılıp
    XAI görseli sessizce yanlış girdiye atanıyordu (ölçüldü) — yol-tabanlı benzersiz ad."""
    import base64 as _b64

    girdi = tmp_path / "fotolar"
    (girdi / "klinik1").mkdir(parents=True)
    (girdi / "klinik2").mkdir()
    (girdi / "klinik1" / "kedi.jpg").write_bytes(b"x")
    (girdi / "klinik2" / "kedi.jpg").write_bytes(b"x")
    cikti = tmp_path / "out"
    cikti.mkdir()

    sayac = {"n": 0}

    def _fabrika(modul, method):
        def _fn(p):
            sayac["n"] += 1
            return {"xai_image_base64": _b64.b64encode(f"gorsel-{sayac['n']}".encode()).decode(), "method": "x"}

        return _fn

    monkeypatch.setattr(cli, "_gorsel_explain_fn", _fabrika)
    satirlar, _k = cli._kos_gorsel("ct", girdi, cikti, SimpleNamespace(limit=None, xai_method="gradcam++"))
    ciktilar = sorted(p.name for p in cikti.glob("*_xai.jpg"))
    assert len(ciktilar) == 2 and len(set(ciktilar)) == 2, f"aynı-stem çakıştı: {ciktilar}"
    assert all(s["hata"] == "" for s in satirlar)


# ── ses: sessizlik kapısı XAI'den ÖNCE (değişmez) ────────────────────────────
def test_KRITIK_ses_sessizlik_kapisi_XAIden_ONCE(cli, tmp_path, monkeypatch):
    import subprocess

    import ai_hub.inference_cat_sound.inference_cat_sound as ses_mod
    import utils.ses_kalitesi as sk

    monkeypatch.setattr("imageio_ffmpeg.get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=b""))
    cagrildi = {"explain": False}

    def _sahte_explain(yol, pt, yontem):
        cagrildi["explain"] = True
        return {"xai_image_base64": "X", "method": yontem}

    monkeypatch.setattr(ses_mod, "xai_ses_isi_haritasi", _sahte_explain)
    kayit = tmp_path / "kayit.mp3"
    kayit.write_bytes(b"x")

    # SESSİZ kayıt: kapı ısı haritasını ENGELLEMELİ, explainer HİÇ çağrılmamalı
    monkeypatch.setattr(sk, "wav_rms_dbfs", lambda yol: -60.0)
    with pytest.raises(RuntimeError, match="sessizlik kapısı"):
        cli._ses_kapili_explain(kayit, "gradcam++")
    assert cagrildi["explain"] is False, "sessiz kayda duygu ısı-haritası üretildi — kapı delindi"

    # KARŞIT: gerçek-kayıt seviyesinde RMS → kapı geçer, explainer çağrılır
    monkeypatch.setattr(sk, "wav_rms_dbfs", lambda yol: -20.0)
    sonuc = cli._ses_kapili_explain(kayit, "eigencam")
    assert cagrildi["explain"] and sonuc["method"] == "eigencam"


def test_KRITIK_em_sample_id_sanitize(cli):
    """Ham sample_id dosya adına gömülüyordu: path ayracı em_paket dışına yazar, NaN'ler
    üst üste biner (ölçüldü)."""
    import pandas as pd

    df = pd.DataFrame({"sample_id": ["A/1", "A/1", float("nan"), "temiz-01"]})
    idler = cli._guvenli_ornek_idler(df)
    assert len(idler) == len(set(idler)), f"benzersiz değil: {idler}"
    assert all("/" not in i and "\\" not in i for i in idler), idler
    assert "temiz-01" in idler
    assert not any(i.lower().startswith("nan") for i in idler), idler


# ── 2) RNA işaretli CSV ──────────────────────────────────────────────────────
def test_KRITIK_rna_imzali_csv_yon_oklari_DOGRU(cli, tmp_path, monkeypatch):
    import ai_hub.inference_human_kidney_rna.inference_human_kidney_rna as rna_mod

    monkeypatch.setattr(
        rna_mod,
        "xai_top_genler",
        lambda df, top_n=10: [
            {
                "patient_id": "hasta_A",
                "top_genes": [
                    {"gene": "GEN_POZ", "attribution": 0.42},
                    {"gene": "GEN_NEG", "attribution": -0.17},
                ],
            },
        ],
    )
    girdi = tmp_path / "hasta.csv"
    girdi.write_text(",g1,g2\nhasta_A,1.0,2.0\n", encoding="utf-8")
    cikti = tmp_path / "out"
    cikti.mkdir()
    args = SimpleNamespace(limit=None, top_n=2)
    satirlar, kartlar = cli._kos_rna(girdi, cikti, args)

    with open(cikti / "rna_top_genler.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert [(r["gene"], r["yon"]) for r in rows] == [("GEN_POZ", "↑"), ("GEN_NEG", "↓")], rows
    assert satirlar[0]["top1_gen"] == "GEN_POZ"
    assert "GEN_NEG ↓" in kartlar[0]["not"]


# ── 3) zarif düşüş (görüntü akışı) ───────────────────────────────────────────
def test_KRITIK_tek_dosya_hatasi_akisi_DUSURMEZ(cli, tmp_path, monkeypatch):
    girdi = tmp_path / "fotolar"
    girdi.mkdir()
    (girdi / "a_iyi.jpg").write_bytes(b"x")
    (girdi / "b_bozuk.jpg").write_bytes(b"x")
    (girdi / "c_iyi.jpg").write_bytes(b"x")
    cikti = tmp_path / "out"
    cikti.mkdir()

    import base64 as _b64

    JPG64 = _b64.b64encode(b"sahte-jpg").decode()

    def _sahte_fn_fabrikasi(modul, method):
        def _fn(p):
            if "bozuk" in p.name:
                raise RuntimeError("model patladı (test)")
            return {"xai_image_base64": JPG64, "method": "eigencam"}

        return _fn

    monkeypatch.setattr(cli, "_gorsel_explain_fn", _sahte_fn_fabrikasi)
    args = SimpleNamespace(limit=None, xai_method="gradcam++")
    satirlar, kartlar = cli._kos_gorsel("ct", girdi, cikti, args)

    assert len(satirlar) == 3, "hatalı dosya kalanların işlenmesini durdurdu"
    hatalar = [s for s in satirlar if s["hata"]]
    assert len(hatalar) == 1 and "b_bozuk" in hatalar[0]["dosya"]
    assert (cikti / "a_iyi_xai.jpg").exists() and (cikti / "c_iyi_xai.jpg").exists()
    # index + summary hatayla birlikte yazılabilmeli
    cli._summary_yaz(cikti, satirlar)
    cli._index_html_yaz(cikti, "test", kartlar, embed=False)
    assert (cikti / "summary.csv").exists() and (cikti / "index.html").exists()
    idx = (cikti / "index.html").read_text(encoding="utf-8")
    assert "HATA" in idx and "a_iyi_xai.jpg" in idx


# ── 4) PDF: görselli rapor + bozuk görüntüde zarif düşüş ─────────────────────
def test_KRITIK_pdf_xai_raporu_uretir_ve_bozuk_gorsel_DUSURMEZ(tmp_path):
    pytest.importorskip("reportlab")
    # 1x1 gerçek PNG (reportlab gerçekten çizebilsin)
    import base64 as _b64

    from utils.pdf_report_generator import PDFReportGenerator

    png = tmp_path / "xai.png"
    png.write_bytes(
        _b64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    )
    gen = PDFReportGenerator(app_data_dir=tmp_path)  # DB izolasyonu: gerçek kliniğe dokunma
    out = gen.generate_xai_report(
        "Test XAI",
        [
            {"etiket": "iyi görsel", "goruntu": str(png), "aciklama": "yöntem: eigencam"},
            {"etiket": "bozuk görsel", "goruntu": str(tmp_path / "yok.png"), "aciklama": None},
            {"etiket": "görselsiz not", "goruntu": None, "aciklama": "yalnız metin"},
        ],
        str(tmp_path / "rapor.pdf"),
    )
    p = Path(out)
    assert p.exists() and p.stat().st_size > 500, "PDF üretilmedi/boş"
    icerik = p.read_bytes()
    assert icerik[:5] == b"%PDF-"
    # 'Görselli' iddiasının kanıtı (mutasyon-körlüğü ölçüldü: gömme tamamen kapatılınca
    # eski test yeşil kalıyordu): PDF gerçekten bir görüntü XObject'i içermeli.
    assert b"/Image" in icerik, "PDF görüntü içermiyor — görsel gömme sessizce kapanmış"
