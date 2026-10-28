# Author: mertaygn, cglrgrkn
"""S-LN.5 (DEVREDEN; Y96 · Y182 · Y202) — çok hesaplı klinikte paylaşılan grup adımı KURULUM BELGESİNDE ve kodla aynı adları taşır.

Eksik (LN raporu, 10-22): ikinci Windows hesabı için paylaşılan yerel grup + `PEMF_DATA_GROUP_SID` adımı hiçbir kurulum belgesinde yoktu.
D3 T-g (Y182) adımı launcher'a taşıdı ("Paylaşımı kur (yönetici)", tek seferlik UAC); belge yine sessizdi. `deploy/README.md` §8 adımı,
grup adını, ortam değişkenini ve hakkın YALNIZ `PEMF_GUI` ağacına verildiğini (Y202) anlatır.

KAPI: belgedeki grup adı / ortam değişkeni / düğme etiketi KAYNAKTAN okunur (Rust sabiti, launcher TR kataloğu) — biri yeniden
adlandırılırsa belge bayatlar ve kapı KIRMIZI olur; kök `PEMF_System`'in gruba açıldığını söyleyen cümle YOK.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _bolum() -> str:
    metin = (KOK / "deploy" / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^## 8\) Çok hesaplı klinik.*?(?=^## |\Z)", metin, re.S | re.M)
    assert m, "deploy/README.md §8 (çok hesaplı klinik) yok"
    return m.group(0)


def test_KRITIK_grup_adi_ortam_degiskeni_ve_dugme_KAYNAKLA_ayni():
    paylasim = (KOK / "launcher" / "core" / "src" / "paylasim.rs").read_text(encoding="utf-8")
    install = (KOK / "launcher" / "core" / "src" / "install.rs").read_text(encoding="utf-8")
    grup = re.search(r'pub const GRUP_ADI: &str = "([^"]+)";', paylasim)
    ortam = re.search(r'pub const ENV_DATA_GROUP_SID: &str = "([^"]+)";', install)
    assert grup and ortam, "aparat: Rust sabitleri bulunamadı"
    dugme = json.loads((KOK / "launcher" / "i18n" / "tr.json").read_text(encoding="utf-8"))
    etiket = next(v["paylasimKur"] for v in dugme.values() if isinstance(v, dict) and "paylasimKur" in v)
    b = _bolum()
    for deger, ne in ((grup.group(1), "grup adı"), (ortam.group(1), "ortam değişkeni"), (etiket, "düğme etiketi")):
        assert deger in b, f"§8 {ne} kaynakla aynı değil / yok: {deger!r}"


def test_KRITIK_hak_YALNIZ_PEMF_GUI_kok_gruba_ACILMAZ_ve_oturum_yenileme():
    b = re.sub(r"\s+", " ", _bolum())
    assert "PEMF_GUI" in b and "YALNIZ" in b, "§8 grup hakkının yalnız PEMF_GUI ağacına verildiğini söylemiyor (Y202)"
    assert re.search(r"kök[^.]*gruba AÇILMAZ", b), "§8 kökün (PEMF_System) gruba açılmadığını söylemiyor"
    assert "oturum" in b.lower() and "PAYLAŞILIR" in b, "§8 oturum yenileme / KVKK paylaşım uyarısı eksik"
    assert not re.search(r"PEMF_System`?[^.]*\(OI\)\(CI\)M", b), "§8 köke grup hakkı verildiğini söylüyor"
