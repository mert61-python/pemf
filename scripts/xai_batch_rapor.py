# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""xai_batch_rapor.py — Mod-2 toplu XAI raporu (xai-entegrasyon-plani.md §KALAN B).

TEK CLI: klasör/dosya tara → modülün TEK-KAYNAK explain fonksiyonunu çağır →
PNG/JPG + summary.csv + index.html (+ opsiyonel --pdf). Canlı döngüye ağır XAI
asla girmez (plan değişmezi) — bu araç SEANS-SONRASI/araştırma yüzeyidir.

Kullanım örnekleri:
    python scripts/xai_batch_rapor.py --modul ct --girdi foto_klasoru --cikti out_ct
    python scripts/xai_batch_rapor.py --modul termal --girdi t.jpg --cikti out_t --xai-method eigencam
    python scripts/xai_batch_rapor.py --modul rna --girdi hasta.csv --cikti out_rna --top-n 10
    python scripts/xai_batch_rapor.py --modul em_fantom --girdi points.csv --cikti out_em
    (+ --pdf: çıktıdaki görselleri tek PDF'te topla)

⚠️ ÇIKTI DİZİNİ GİRDİNİN DIŞINDA OLMALI: girdi klasörünün içine yazmak, sonraki
koşuda aracın KENDİ çıktısını girdi sanıp özyinelemeli işlemesine yol açar —
açık hatayla reddedilir.

Zarif düşüş: tek dosyanın hatası akışı DÜŞÜRMEZ; summary.csv'ye hata satırı
yazılır ve devam edilir (plan ilkesi: XAI hatası analizi düşürmez).
"""

from __future__ import annotations

import argparse
import base64
import csv
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

# Windows konsolu cp1254 olabilir (make_manifest cp1252 tuzağıyla aynı ders):
# ok/Türkçe karakterli ilerleme satırları UnicodeEncodeError ile akışı düşürmesin.
for _akis in (sys.stdout, sys.stderr):
    try:
        _akis.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GECERLI_CAM = ("gradcam++", "gradcam", "eigencam", "hirescam")
GORUNTU_UZANTILARI = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
SES_UZANTILARI = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def _cikti_bekcisi(girdi: Path, cikti: Path) -> None:
    """Çıktı dizini girdinin içinde/kendisiyse AÇIK hata (özyinelemeli kendi-çıktısı tuzağı)."""
    g = girdi.resolve()
    c = cikti.resolve()
    hedef = g if g.is_dir() else g.parent
    if c == hedef or c.is_relative_to(hedef):
        raise SystemExit(
            f"HATA: çıktı dizini ({c}) girdi klasörünün ({hedef}) içinde — sonraki koşu "
            "kendi çıktısını girdi sanır. Çıktıyı girdinin DIŞINA verin."
        )


def _dosyalari_tara(girdi: Path, uzantilar: set[str], limit: int | None) -> list[Path]:
    if girdi.is_file():
        dosyalar = [girdi]
    else:
        dosyalar = sorted(p for p in girdi.rglob("*") if p.suffix.lower() in uzantilar)
    if limit and len(dosyalar) > limit:
        print(f"NOT: {len(dosyalar)} dosyadan ilk {limit} işlenecek (--limit); kalanı ATLANDI.")
        dosyalar = dosyalar[:limit]
    if not dosyalar:
        raise SystemExit(f"HATA: {girdi} altında uygun dosya yok ({', '.join(sorted(uzantilar))}).")
    return dosyalar


def _b64_yaz(b64: str, hedef: Path) -> Path:
    hedef.write_bytes(base64.b64decode(b64))
    return hedef


def _index_html_yaz(cikti: Path, baslik: str, kartlar: list[dict], embed: bool) -> Path:
    """Basit galeri: her kart {"etiket", "gorseller": [(altyazi, dosya-adı)], "not"}.
    Kaçırma report_html._esc'ten (tek kaynak — PII/XSS)."""
    from ai_hub.xai_utils.report_html import _esc, _img_data_uri

    def _src(ad: str) -> str:
        return _img_data_uri(cikti / ad) if embed else ad

    parcalar = [
        "<!doctype html>",
        '<meta charset="utf-8">',
        f"<title>{_esc(baslik)}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#222;max-width:1400px}"
        "h1{border-bottom:2px solid #333;padding-bottom:6px}figure{display:inline-block;margin:8px}"
        "img{max-width:440px;border:1px solid #ccc}figcaption{text-align:center;font-size:13px;color:#333}"
        ".kart{border-bottom:1px solid #ddd;padding:12px 0}.hata{color:#b00020}</style>",
        f"<h1>{_esc(baslik)}</h1>",
    ]
    for k in kartlar:
        parcalar.append(f'<div class="kart"><h2>{_esc(k["etiket"])}</h2>')
        for altyazi, ad in k.get("gorseller", []):
            parcalar.append(f'<figure><img src="{_esc(_src(ad))}"><figcaption>{_esc(altyazi)}</figcaption></figure>')
        if k.get("not"):
            sinif = ' class="hata"' if k.get("hata") else ""
            parcalar.append(f"<p{sinif}>{_esc(k['not'])}</p>")
        parcalar.append("</div>")
    yol = cikti / "index.html"
    yol.write_text("\n".join(parcalar), encoding="utf-8")
    return yol


def _summary_yaz(cikti: Path, satirlar: list[dict]) -> Path:
    yol = cikti / "summary.csv"
    alanlar = sorted({k for s in satirlar for k in s})
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(satirlar)
    return yol


# ── görüntü/ses modülleri ────────────────────────────────────────────────────
def _gorsel_explain_fn(modul: str, xai_method: str):
    """Modülün TEK-KAYNAK explain fonksiyonunu (dosya-yolu → dict) closure olarak döndür."""
    if modul == "termal":
        from ai_hub.cat_thermal.inference_cat_thermal import xai_termal_isi_haritasi

        return lambda p: xai_termal_isi_haritasi(str(p), None, xai_method)
    if modul == "ses":
        from ai_hub.inference_cat_sound.inference_cat_sound import xai_ses_isi_haritasi

        return lambda p: xai_ses_isi_haritasi(str(p), None, xai_method)
    if modul == "ct":
        from ai_hub.inference_human_kidney_ct.inference_human_kidney_ct import xai_ct_isi_haritasi

        return lambda p: xai_ct_isi_haritasi(str(p))
    if modul == "histopat":
        from ai_hub.inference_renal_histopath_kmc.inference_renal_histopath_kmc import (
            xai_histopat_isi_haritasi,
        )

        return lambda p: xai_histopat_isi_haritasi(str(p))
    if modul == "retikulosit":
        from ai_hub.feline_reticulocytes.inference_feline_reticulocytes import (
            xai_retikulosit_isi_haritasi,
        )

        return lambda p: xai_retikulosit_isi_haritasi(str(p))
    raise SystemExit(f"HATA: bilinmeyen görüntü/ses modülü: {modul}")


def _kos_gorsel(modul: str, girdi: Path, cikti: Path, args) -> tuple[list[dict], list[dict]]:
    uzantilar = SES_UZANTILARI if modul == "ses" else GORUNTU_UZANTILARI
    dosyalar = _dosyalari_tara(girdi, uzantilar, args.limit)
    fn = _gorsel_explain_fn(modul, args.xai_method)
    satirlar: list[dict] = []
    kartlar: list[dict] = []
    for i, p in enumerate(dosyalar, 1):
        t0 = time.time()
        try:
            sonuc = fn(p)
            ana = _b64_yaz(sonuc["xai_image_base64"], cikti / f"{p.stem}_xai.jpg")
            gorseller = [("XAI ısı haritası", ana.name)]
            if sonuc.get("xai_disagreement_base64"):
                kar = _b64_yaz(sonuc["xai_disagreement_base64"], cikti / f"{p.stem}_kararsizlik.jpg")
                gorseller.append(("Model kararsızlık haritası", kar.name))
            sure = round(time.time() - t0, 2)
            satirlar.append(
                {"dosya": p.name, "yontem": sonuc.get("method", "?"), "cikti": ana.name, "sure_s": sure, "hata": ""}
            )
            kartlar.append(
                {"etiket": p.name, "gorseller": gorseller, "not": f"yöntem: {sonuc.get('method', '?')} · {sure}s"}
            )
            print(f"[{i}/{len(dosyalar)}] {p.name} OK ({sure}s)")
        except Exception as e:  # tek dosya akışı düşürmez
            sure = round(time.time() - t0, 2)
            satirlar.append(
                {"dosya": p.name, "yontem": "-", "cikti": "-", "sure_s": sure, "hata": f"{type(e).__name__}: {e}"}
            )
            kartlar.append({"etiket": p.name, "gorseller": [], "hata": True, "not": f"HATA: {type(e).__name__}: {e}"})
            print(f"[{i}/{len(dosyalar)}] {p.name} HATA: {e}")
    return satirlar, kartlar


# ── rna ──────────────────────────────────────────────────────────────────────
def _kos_rna(girdi: Path, cikti: Path, args) -> tuple[list[dict], list[dict]]:
    """Hasta-CSV → IG top-genler → İŞARETLİ CSV (gene, attribution, yön) + index tablosu."""
    import pandas as pd

    from ai_hub.inference_human_kidney_rna.inference_human_kidney_rna import xai_top_genler

    if girdi.is_dir():
        raise SystemExit("HATA: rna modülü TEK CSV dosyası ister (klasör değil).")
    df = pd.read_csv(girdi, index_col=0)
    if args.limit and len(df) > args.limit:
        print(f"NOT: {len(df)} hastadan ilk {args.limit} işlenecek (--limit); kalanı ATLANDI.")
        df = df.iloc[: args.limit]
    t0 = time.time()
    sonuc = xai_top_genler(df, top_n=args.top_n)
    sure = round(time.time() - t0, 2)

    imzali = cikti / "rna_top_genler.csv"
    with open(imzali, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "sira", "gene", "attribution", "yon"])
        for hasta in sonuc:
            for j, g in enumerate(hasta["top_genes"], 1):
                w.writerow([hasta["patient_id"], j, g["gene"], g["attribution"], "↑" if g["attribution"] > 0 else "↓"])

    satirlar = [
        {
            "dosya": girdi.name,
            "hasta": h["patient_id"],
            "top1_gen": h["top_genes"][0]["gene"] if h["top_genes"] else "-",
            "sure_s": sure,
            "hata": "",
        }
        for h in sonuc
    ]
    kartlar = [
        {
            "etiket": h["patient_id"],
            "gorseller": [],
            "not": " · ".join(f"{g['gene']} {'↑' if g['attribution'] > 0 else '↓'}" for g in h["top_genes"]),
        }
        for h in sonuc
    ]
    print(f"RNA: {len(sonuc)} hasta, top-{args.top_n} gen → {imzali.name} ({sure}s)")
    return satirlar, kartlar


# ── em üçlüsü ────────────────────────────────────────────────────────────────
_EM_MODULLER = {
    "em_fantom": ("ai_hub.inference_em_fantom.inference_em_fantom", "PhantomPredictor"),
    "em_petri": ("ai_hub.inference_em_petri.inference_em_petri", "PetriPredictor"),
    "em_kedi": ("ai_hub.em_kedi.inference_em_kedi", "KediPredictor"),
}


def _kos_em(modul: str, girdi: Path, cikti: Path, args) -> tuple[list[dict], list[dict]]:
    """points.csv (x,y,z,organ_id,achieved_B,duty_sum) → Mod-2 tam paket (_run_xai_em)."""
    import importlib

    import pandas as pd

    from ai_hub.xai_tabular.em_sensitivity import EM_FEATURES

    if girdi.is_dir():
        raise SystemExit(f"HATA: {modul} modülü points.csv dosyası ister (klasör değil).")
    df = pd.read_csv(girdi)
    eksik = [k for k in EM_FEATURES if k not in df.columns]
    if eksik:
        raise SystemExit(f"HATA: {girdi.name} kolonları eksik: {eksik} (beklenen: {EM_FEATURES})")
    if args.limit and len(df) > args.limit:
        print(f"NOT: {len(df)} noktadan ilk {args.limit} işlenecek (--limit); kalanı ATLANDI.")
        df = df.iloc[: args.limit]

    mod_yolu, sinif_adi = _EM_MODULLER[modul]
    m = importlib.import_module(mod_yolu)
    pred = getattr(m, sinif_adi)()
    ornek_idler = (
        [str(v) for v in df["sample_id"]] if "sample_id" in df.columns else [f"nokta_{i}" for i in range(len(df))]
    )
    t0 = time.time()
    paket = m._run_xai_em(
        pred, df[list(EM_FEATURES)].values, cikti / "em_paket", sample_ids=ornek_idler, run_shap=not args.no_shap
    )
    sure = round(time.time() - t0, 2)

    uretilen = sorted(x.name for x in (cikti / "em_paket").iterdir())
    satirlar = [
        {
            "dosya": girdi.name,
            "nokta_sayisi": len(df),
            "paket": "em_paket/",
            "shap": "hayır" if args.no_shap else "evet",
            "sure_s": sure,
            "hata": "",
        }
    ]
    kartlar = [
        {
            "etiket": f"{modul} · {len(df)} nokta",
            "gorseller": [(ad, f"em_paket/{ad}") for ad in uretilen if ad.endswith(".png")],
            "not": f"tam paket: {', '.join(uretilen)} ({sure}s)",
        }
    ]
    print(f"{modul}: {len(df)} nokta → em_paket/ ({sure}s); dosyalar: {uretilen}")
    del paket
    return satirlar, kartlar


# ── pdf ──────────────────────────────────────────────────────────────────────
def _pdf_yaz(cikti: Path, baslik: str, kartlar: list[dict]) -> None:
    """Opsiyonel: çıktı görsellerini tek PDF'te topla (utils.pdf_report_generator §KALAN B)."""
    try:
        from utils.pdf_report_generator import get_pdf_generator

        ogeler = []
        for k in kartlar:
            gorseller = k.get("gorseller") or [(None, None)]
            for altyazi, ad in gorseller:
                ogeler.append(
                    {
                        "etiket": k["etiket"] + (f" — {altyazi}" if altyazi else ""),
                        "goruntu": str(cikti / ad) if ad else None,
                        "aciklama": k.get("not"),
                    }
                )
        yol = get_pdf_generator().generate_xai_report(baslik, ogeler, str(cikti / "rapor.pdf"))
        print(f"PDF: {yol}")
    except Exception as e:  # PDF opsiyonel — hatası batch'i düşürmez
        print(f"UYARI: PDF üretilemedi (batch çıktıları geçerli): {type(e).__name__}: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="xai_batch_rapor",
        description="PEMF Mod-2 toplu XAI raporu (görüntü/ses CAM · RNA IG · EM sensitivity+SHAP)",
    )
    ap.add_argument(
        "--modul",
        required=True,
        choices=["ct", "histopat", "termal", "retikulosit", "ses", "rna", "em_fantom", "em_petri", "em_kedi"],
    )
    ap.add_argument("--girdi", required=True, help="dosya ya da klasör (rna/em: CSV dosyası)")
    ap.add_argument("--cikti", required=True, help="çıktı dizini (girdinin DIŞINDA olmalı)")
    ap.add_argument("--limit", type=int, default=None, help="en fazla N dosya/satır işle")
    ap.add_argument(
        "--xai-method",
        default="gradcam++",
        choices=GECERLI_CAM,
        help="termal/ses CAM yöntemi (diğer modüllerde yok sayılır)",
    )
    ap.add_argument("--top-n", type=int, default=10, help="rna: hasta başına top-N gen")
    ap.add_argument("--no-shap", action="store_true", help="em: SHAP'ı atla (yalnız sensitivity)")
    ap.add_argument("--embed", action="store_true", help="index.html'e görselleri data-URI göm")
    ap.add_argument("--pdf", action="store_true", help="çıktı görsellerinden tek PDF derle")
    args = ap.parse_args()

    girdi = Path(args.girdi)
    if not girdi.exists():
        raise SystemExit(f"HATA: girdi yok: {girdi}")
    cikti = Path(args.cikti)
    _cikti_bekcisi(girdi, cikti)
    cikti.mkdir(parents=True, exist_ok=True)

    baslik = f"PEMF XAI Batch — {args.modul}"
    if args.modul == "rna":
        satirlar, kartlar = _kos_rna(girdi, cikti, args)
    elif args.modul in _EM_MODULLER:
        satirlar, kartlar = _kos_em(args.modul, girdi, cikti, args)
    else:
        satirlar, kartlar = _kos_gorsel(args.modul, girdi, cikti, args)

    _summary_yaz(cikti, satirlar)
    _index_html_yaz(cikti, baslik, kartlar, embed=args.embed)
    if args.pdf:
        _pdf_yaz(cikti, baslik, kartlar)

    hatalar = [s for s in satirlar if s.get("hata")]
    print(f"BİTTİ: {len(satirlar)} kayıt ({len(hatalar)} hata) → {cikti / 'summary.csv'} + index.html")
    if hatalar:
        print("Hatalı kayıtlar summary.csv'de işaretli (akış düşürülmedi — zarif düşüş).")


if __name__ == "__main__":
    main()
