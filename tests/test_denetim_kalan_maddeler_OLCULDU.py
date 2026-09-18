# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DENETIMIN KALAN UC MADDESI OLCULDU — UCU DE DUZELTILDI (2026-09-17).

`DEPO-DENETIMI-2026-09-15.md`nin son uc acik maddesi (A2 · B4 · C5) uygulanmadan ONCE
olculdu. Ucu de yanlis ya da bayat cikti. Bu dosya duzeltmelerin yerinde kalmasini
saglar — cunku ilk yazimlari uygulanabilir "yapilacak" maddeleri olarak duruyordu.

─── A2: "guvenlik-ilgili hesap" IDDIASI TERSINE DONDU ──────────────────────────
Kopya GERCEK (MD5 ayni). Ama `phantom_cv`/`petri_cv` ARASTIRMA saglayicilari ve
`PEMF_ARASTIRMA_AIPRO=0` ile kapali; `_arastirma_aipro_kapisi` 409 donuyor
("bobin surulmez"). Ustelik BAYRAGIN VAR OLMA SEBEBI TAM DA BU DOSYA:
`ai_pro_hedef.py` -> "coord_transform marker->kabin ROTASYONUNU uygulamiyor ... iki
hattin AYNI cerceveyi urettigi KANITLANMADI".
=> Kopya kod HIC BOBIN SURMUYOR ve zaten yeniden yazilmayi bekliyor. Simdi birlestirmek,
silinecek geometriyi birlestirmek olurdu. ERTELENDI.

─── B4: dogru ama OLCUT yanlisti ───────────────────────────────────────────────
api_server.py 5135 satir ama KOD 3530 (%22 yorum). Bu depoda yorumlar denetim gecmisini
tasir — OZELLIK onlar, sisme degil. Gercek sorun `treatment_history_db.py`: TEK SINIFTA
94 metot.

─── C5: iddia BAYAT; kalan tek madde de YAPILAMAZ ──────────────────────────────
PEMF_BUILD / pf/android/app/build / build_tools/Output -> UCU DE ZATEN YOK.
Kalan: `launcher/target` 6,9 GB — ve SILMEKLE COZULMUYOR, her `cargo` kosumunda geri
geliyor. `CARGO_TARGET_DIR` ile agac disina almak OLCULDU, KIRARDI:
`.github/workflows/launcher.yml` satir 175 ve 190 `launcher/target/release/bundle`
yolunu SABIT yaziyor; ustelik o workflow yalniz `launcher-v*` etiketiyle kosuyor (YAYIN,
donmus) -> duzeltme DOGRULANAMAZ. Yapilmadi.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_DENETIM = KOK / "docs" / "DEPO-DENETIMI-2026-09-15.md"
_TAKIPCI = KOK / "docs" / "ARIZA-LISTESI.md"
_AI_PRO = KOK / "servers" / "ai_pro_hedef.py"
_AI_ROUTER = KOK / "servers" / "ai_router.py"
_DEVICE_ENV = KOK / "deploy" / "device.env"
_LAUNCHER_YML = KOK / ".github" / "workflows" / "launcher.yml"


# ═══════════════════════════════════════════════════════════════════════════════════════
# A2 — kopya kod BOBIN SURMUYOR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_arastirma_saglayicilari_BAYRAKLA_kapali():
    """A2'nin "guvenlik-ilgili" iddiasini curuten olcum: kapi GERCEKTEN var mi?

    ⚠️ Bu kapi kaldirilirsa `phantom_cv`/`petri_cv` bobin surmeye baslar ve A2 bir anda
    GERCEKTEN guvenlik-ilgili hale gelir. O zaman erteleme karari da gecersizlesir.
    """
    kod = _AI_ROUTER.read_text(encoding="utf-8")
    assert "def _arastirma_aipro_kapisi" in kod, (
        "arastirma AI Pro kapisi KAYBOLMUS -> bayrakla kapali saglayicilar bobin surebilir; "
        "A2'nin ertelenme gerekcesi COKER"
    )
    fn = next(
        (n for n in ast.walk(ast.parse(kod)) if isinstance(n, ast.FunctionDef) and n.name == "_arastirma_aipro_kapisi"),
        None,
    )
    assert fn is not None

    # ⚠️ `"409" in ast.unparse(fn)` YETMEZ — mutasyonla olculdu (bu oturumda DOKUZUNCU
    # "metin kapiyi kandirdi" vakasi). Fonksiyonun DOCSTRING'i zaten "...denetle → 409"
    # diyor; gercek `status_code`u 200 yapan mutasyon kapiyi YESIL birakti. Capa,
    # `HTTPException(status_code=...)` cagrisinin ARGUMAN DEGERINE pinli.
    kodlar = []
    for c in ast.walk(fn):
        if not isinstance(c, ast.Call):
            continue
        ad = getattr(c.func, "id", getattr(c.func, "attr", None))
        if ad != "HTTPException":
            continue
        for kw in c.keywords:
            if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                kodlar.append(kw.value.value)
    assert kodlar, "kapi artik HTTPException YUKSELTMIYOR -> surus reddi kaybolmus"
    assert 409 in kodlar, (
        f"kapinin donduru durum kodlari {kodlar} — 409 YOK. Arastirma saglayicilari artik "
        "reddedilmiyor olabilir; A2'nin ertelenme gerekcesi (bobin surmuyor) COKER."
    )


def test_KRITIK_arastirma_bayragi_VARSAYILAN_KAPALI():
    """Varsayilan `1` olsaydi kopya kod sahada bobin surerdi."""
    satirlar = [s.strip() for s in _DEVICE_ENV.read_text(encoding="utf-8").splitlines()]
    hedef = [s for s in satirlar if s.startswith("PEMF_ARASTIRMA_AIPRO=")]
    assert hedef == ["PEMF_ARASTIRMA_AIPRO=0"], (
        f"arastirma AI Pro bayragi varsayilan KAPALI degil: {hedef} -> kopya CV kodu sahada "
        "bobin surer ve A2 ertelemesi gecersiz olur"
    )


def test_KRITIK_erteleme_GEREKCESI_kodda_yazili():
    """Erteleme karari bir IDDIAYA dayaniyor: geometri dogrulanmamis. O iddia kodda mi?"""
    metin = _AI_PRO.read_text(encoding="utf-8")
    assert "KANITLANMADI" in metin or "kanıtlanmadı" in metin.lower(), (
        "phantom/petri geometrisinin DOGRULANMADIGI notu kaybolmus -> erteleme gerekcesi belgesiz kalir"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# C5 — tasima YAPILAMAZ (yayin workflow'unu kirar)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_launcher_yml_target_yolunu_SABIT_yaziyor():
    """⚠️ C5'in "cikitilari agac disina al" tavsiyesi BU YUZDEN uygulanamaz.

    Kapi kirmizi donerse yol artik sabit degildir -> `CARGO_TARGET_DIR` tasimasi yeniden
    degerlendirilebilir. Yani bu test bir ENGELIN hala durdugunu olcer.
    """
    metin = _LAUNCHER_YML.read_text(encoding="utf-8")
    assert "launcher/target" in metin or "target/release" in metin, (
        "launcher.yml artik `launcher/target` yolunu sabit yazmiyor -> C5 tasimasi yeniden "
        "degerlendirilebilir; denetim notunu guncelleyin"
    )


def test_KRITIK_launcher_yml_YALNIZ_etiketle_kosar():
    """Tasimanin dogrulanamamasinin sebebi: o workflow bir YAYIN yolu."""
    metin = _LAUNCHER_YML.read_text(encoding="utf-8")
    assert re.search(r'tags:\s*\[\s*"launcher-v\*"\s*\]', metin), (
        "launcher.yml tetikleyicisi degismis -> 'dogrulanamaz cunku yayin' gerekcesi yeniden olculmeli"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# BELGELER — duzeltmeler yerinde mi
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_denetim_UC_maddeyi_de_DUZELTMIS():
    metin = _DENETIM.read_text(encoding="utf-8")
    assert "A2 · B4 · C5 — ÖLÇÜLDÜ" in metin, (
        "denetimde A2/B4/C5 duzeltmesi YOK -> bayat 'yapilacak' maddeleri uygulanabilir gorunur"
    )
    for isaret in ("TERSİNE DÖNDÜ", "ÖLÇÜT", "BAYAT"):
        assert isaret in metin, f"duzeltme metninde '{isaret}' yok — uc maddenin biri eksik"


def test_KARSIT_KANIT_takipci_A2yi_ERTELENDI_isaretliyor():
    """Denetim duzeltilip takipci duzeltilmezse is yine listeden alinir."""
    metin = _TAKIPCI.read_text(encoding="utf-8")
    assert "ERTELENDİ" in metin, "takipcide A2 hala yapilacak gorunuyor"
    assert "YAPILAMAZ" in metin, "takipcide C5 hala yapilacak gorunuyor"


def test_KARSIT_KANIT_B4_OLCUTU_satir_degil():
    """B4 ÇOZULDU (2026-09-18) — kapinin yonu CEVRILDI.

    ⚠️ BU TEST DAHA ONCE `en_buyuk >= 40` DIYORDU ve icine su not yazilmisti:
        "en buyuk sinif artik N metot -> B4 gercekten cozulmus olabilir;
         duzeltme notunu guncelleyin (bu KOTU haber degil)"
    Tam o oldu: `TreatmentHistoryDB` 93 -> 17 metoda indi (8 karisim modulu), dosya
    3530 -> 710 satir. Kapi simdi COZULMUS hali kilitliyor; geri sisme `UST_SINIR` ile
    `tests/test_tedavi_db_bolunmus_KALIR.py`de olculuyor.

    ⚠️ KORUNAN DERS DEGISMEDI: B4'un olcutu SATIR SAYISI DEGILDI. `api_server.py` 5.135
    satir ama kodu 3.530 — fark yorumlar ve bu depoda yorumlar OZELLIKTIR (denetim gecmisini
    tasirlar). Sorun tek nesnedeki YEDI ayri sorumluluktu. Birini satir sayisina bakip
    "bu dosya da buyuk, bolelim" derken bulursaniz, once NE olctugunu sorun.
    """
    src = (KOK / "database" / "treatment_history_db.py").read_text(encoding="utf-8")
    t = ast.parse(src)
    siniflar = [n for n in ast.walk(t) if isinstance(n, ast.ClassDef)]
    assert siniflar, "treatment_history_db'de sinif yok — kapi bayatlamis"
    en_buyuk = max(sum(1 for x in c.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))) for c in siniflar)
    assert en_buyuk <= 22, (
        f"en buyuk sinif {en_buyuk} metoda cikmis -> B4 bolmesi geri aliniyor olabilir. "
        "Yeni islev ILGILI KARISIMA eklenir (database/thdb_*.py); ana sinif yalniz BAGLANTI "
        "havuzu ve yasam dongusu tasir."
    )
    # ⚠️ Karsit kanit: bolme GERCEKTEN yapilmis mi — yoksa sinif bos birakilip is baska bir
    # dev sinifa mi tasinmis? Karisim modulleri var olmali.
    karisimlar = sorted((KOK / "database").glob("thdb_*.py"))
    assert len(karisimlar) >= 8, f"yalniz {len(karisimlar)} karisim modulu var — B4 bolmesi eksik ya da geri alinmis"
