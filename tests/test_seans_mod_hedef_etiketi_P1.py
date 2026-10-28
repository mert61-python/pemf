# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""I18N-P1 (kapanış İngilizce taraması) · SEANS MODU + HEDEF DURUMU gösterimde değer → anahtar (PDF · CSV) ve arayüz eşliği.

`treatment_mode` ("Manuel" | "Otomatik" | "AI") ve `target_condition` (arayüz `AUTO_TARGETS`) DB'ye giden VERİdir ve Türkçe kalır; PDF / CSV'ye
basılırken istek dilinde çevrilir (`utils/seans_durum.py::mod_etiketi / hedef_etiketi`). Türkçe çıktı eskisiyle BAYT BAYT aynı; bilinmeyen değer
(serbest metin, eski kayıt, `AI`, None) AYNEN. ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz).
Arayüz karşılığı `apps/ui/src/utils/seansDegerEtiketi.ts`: iki tablo ANAHTAR ANAHTAR ve çözülen TR / EN etiketle karşılaştırılır.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

#: ham değer → (TR görünüm, EN görünüm)
HEDEFLER = {
    "Doku İyileşmesi": ("Doku İyileşmesi", "Tissue Healing"),
    "Eklem Ağrısı": ("Eklem Ağrısı", "Joint Pain"),
    "Kas Spazmı": ("Kas Spazmı", "Muscle Spasm"),
    "Kırık İyileşmesi": ("Kırık İyileşmesi", "Fracture Healing"),
    "Enflamasyon Azaltma": ("Enflamasyon Azaltma", "Inflammation Reduction"),
    "Sinir Rejenerasyonu": ("Sinir Rejenerasyonu", "Nerve Regeneration"),
    "Bağ Dokusu Tamiri": ("Bağ Dokusu Tamiri", "Connective Tissue Repair"),
    "Ödem Azaltma": ("Ödem Azaltma", "Edema Reduction"),
}
MODLAR = {"Manuel": ("Manuel", "Manual"), "Otomatik": ("Otomatik", "Automatic")}


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _gor(cift, dil):
    return cift[0] if dil == "tr" else cift[1]


# ── işlevler ─────────────────────────────────────────────────────────


def test_hedef_etiketi_TR_ham_degerin_KENDISI_EN_ingilizce(dil):
    from utils.seans_durum import hedef_etiketi

    assert len(HEDEFLER) == 8, "kapı küçülmesin"
    for ham, cift in HEDEFLER.items():
        assert hedef_etiketi(ham) == _gor(cift, dil), ham


def test_mod_etiketi_TR_ham_degerin_KENDISI_EN_ingilizce_AI_aynen(dil):
    from utils.seans_durum import mod_etiketi

    for ham, cift in MODLAR.items():
        assert mod_etiketi(ham) == _gor(cift, dil), ham
    assert mod_etiketi("AI") == "AI"


def test_bilinmeyen_serbest_metin_bos_ve_metin_olmayan_AYNEN_doner(dil):
    from utils.seans_durum import hedef_etiketi, mod_etiketi

    for serbest in ("Eklem", "Tümör modeli (DEMO)", "", "ödem azaltma", "Belirtilmemiş"):
        assert hedef_etiketi(serbest) == serbest
    for serbest in ("manual", "", "Manuel (eski)", "Bilinmiyor"):
        assert mod_etiketi(serbest) == serbest
    assert hedef_etiketi(None) is None and mod_etiketi(None) is None  # eski davranış: None'a dokunulmaz
    assert hedef_etiketi(5) == 5 and mod_etiketi(5) == 5


def _yaprak_degeri(katalog, anahtar):
    for parca in anahtar.split("."):
        katalog = katalog[parca]
    return katalog


def test_katalog_anahtarlari_TR_ham_deger_EN_Turkce_harfsiz():
    from utils.seans_durum import HEDEF_ETIKETLERI, MOD_ETIKETLERI

    assert set(HEDEF_ETIKETLERI) == set(HEDEFLER) and set(MOD_ETIKETLERI) == set(MODLAR)
    tr_harf = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
    tr = json.loads((KOK / "apps/backend/i18n/tr.json").read_text(encoding="utf-8"))
    en = json.loads((KOK / "apps/backend/i18n/en.json").read_text(encoding="utf-8"))
    for tablo in (HEDEF_ETIKETLERI, MOD_ETIKETLERI):
        for ham, anahtar in tablo.items():
            assert _yaprak_degeri(tr, anahtar) == ham, f"TR katalog değeri ham değerden FARKLI: {anahtar}"
            e = _yaprak_degeri(en, anahtar)
            assert e.strip() and not tr_harf.search(e), f"EN boş / Türkçe harf: {anahtar}: {e!r}"


# ── arayüz ↔ sunucu eşliği ──────────────────────────────────────────


def _duz(o, onek=""):
    for k, v in o.items():
        yol = f"{onek}.{k}" if onek else k
        if isinstance(v, dict):
            yield from _duz(v, yol)
        else:
            yield yol, v


def _arayuz_tablosu():
    kaynak = (KOK / "apps/ui/src/utils/seansDegerEtiketi.ts").read_text(encoding="utf-8")
    cikti = {}
    for fonksiyon in ("hedefEtiketi", "modEtiketi"):
        govde = re.search(rf"export const {fonksiyon} = .*?\n}};", kaynak, re.S).group(0)
        cikti[fonksiyon] = re.findall(r'case "(.+?)": return t\("(.+?)"\);', govde)
    return cikti


def test_arayuz_ve_sunucu_tablolari_ANAHTAR_ANAHTAR_ve_TR_EN_etiketle_AYNI():
    from utils.seans_durum import HEDEF_ETIKETLERI, MOD_ETIKETLERI

    ui = _arayuz_tablosu()
    katalog = {
        dil: dict(_duz(json.loads((KOK / f"apps/ui/src/i18n/{dil}/kontrol.json").read_text(encoding="utf-8"))))
        for dil in ("tr", "en")
    }
    sunucu = {
        dil: dict(_duz(json.loads((KOK / f"apps/backend/i18n/{dil}.json").read_text(encoding="utf-8"))))
        for dil in ("tr", "en")
    }
    for ad, tablo in (("hedefEtiketi", HEDEF_ETIKETLERI), ("modEtiketi", MOD_ETIKETLERI)):
        assert sorted(d for d, _ in ui[ad]) == sorted(tablo), f"{ad}: değer kümesi ayrışmış"
        for ham, ui_anahtar in ui[ad]:
            for dil in ("tr", "en"):
                ad_alani, anahtar = ui_anahtar.split(
                    ".", 1
                )  # arayüz katalogu ad alanı = dosya adı (`kontrol.json` → `kontrol.`)
                assert ad_alani == "kontrol"
                assert katalog[dil][anahtar] == sunucu[dil][tablo[ham]], (
                    f"{ad}[{ham}] {dil}: arayüz ve sunucu etiketi ayrışmış"
                )
    # TR görünüm = ham değer (iki yüzeyde de)
    for ham, ui_anahtar in ui["hedefEtiketi"] + ui["modEtiketi"]:
        assert katalog["tr"][ui_anahtar.split(".", 1)[1]] == ham


# ── PDF (gerçek DB + gerçek üretici) ────────────────────────────────

fitz = capraz.paket_yoksa_atla("fitz", sebep="PyMuPDF yok -> PDF metni çıkarılamaz")


def _pdf_metni(tmp_path, dil_kodu):
    from database.treatment_history_db import TreatmentHistoryDB
    from utils import ceviri
    from utils.pdf_report_generator import PDFReportGenerator

    kok = tmp_path / f"pdf_{dil_kodu}"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    sid = db.start_session(treatment_mode="Otomatik", target_condition="Ödem Azaltma", patient_name="Mia")
    db.start_coil_run(
        sid, 1, frequency_hz=100, duty_percent=50, phase=0, intensity_mt=0.0, hw_type="stm", started_epoch=1757000000.0
    )
    db.end_session(sid, session_status="completed")
    uretici = PDFReportGenerator(kok)
    jeton = ceviri.istek_dili_var.set(dil_kodu)
    try:
        s = str(tmp_path / f"seans_{dil_kodu}.pdf")
        uretici.generate_session_report(session_ids=[sid], output_path=s)
        h = str(tmp_path / f"hasta_{dil_kodu}.pdf")
        uretici.generate_patient_report(patient_name="Mia", output_path=h)
    finally:
        ceviri.istek_dili_var.reset(jeton)

    def metin(yol):
        with fitz.open(yol) as d:
            return "\n".join(sayfa.get_text() for sayfa in d)

    return metin(s), metin(h)


def test_PDF_TR_eski_degerlerle_AYNI_EN_ingilizce_ham_Turkce_deger_KALMADI(tmp_path):
    seans_tr, hasta_tr = _pdf_metni(tmp_path, "tr")
    for metin in (seans_tr, hasta_tr):
        assert "Otomatik" in metin and "Ödem Azaltma" in metin
    seans_en, hasta_en = _pdf_metni(tmp_path, "en")
    for metin in (seans_en, hasta_en):
        assert "Automatic" in metin and "Edema Reduction" in metin
        assert "Otomatik" not in metin and "Ödem Azaltma" not in metin, "EN PDF'te ham Türkçe seans değeri kaldı"


# ── CSV (gerçek uç, TestClient) ─────────────────────────────────────


@pytest.fixture
def uc(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from database.treatment_history_db import TreatmentHistoryDB
    from fastapi.testclient import TestClient
    from servers import api_server as api
    from servers import history_router as hr

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    tdb = TreatmentHistoryDB(tmp_path / "gecmis")
    with tdb._get_connection() as c:
        c.executemany(
            "INSERT INTO treatment_sessions (session_date, start_time, treatment_mode, target_condition, patient_name, session_status) "
            "VALUES (?, ?, ?, ?, ?, 'completed')",
            [
                ("2026-10-01", "10:00:00", "Manuel", "Ödem Azaltma", "Tekir"),
                ("2026-10-02", "10:00:00", "AI", "Eklem", "Pamuk"),
            ],
        )
        c.commit()
    api.app.dependency_overrides[hr.get_db] = lambda: tdb
    try:
        yield TestClient(api.app, client=("127.0.0.1", 53217))
    finally:
        api.app.dependency_overrides.pop(hr.get_db, None)
        tdb.close()


def _csv(istemci, dil_kodu):
    r = istemci.get("/api/history/export_csv", headers={"X-PEMF-Dil": dil_kodu})
    assert r.status_code == 200, r.text[:200]
    satirlar = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    return {s[1]: (s[2], s[3]) for s in satirlar[1:]}  # hasta → (hedef, mod)


def test_CSV_TR_eski_degerlerle_AYNI_EN_ingilizce_serbest_metin_ve_AI_aynen(uc):
    tr = _csv(uc, "tr")
    assert tr == {"Tekir": ("Ödem Azaltma", "Manuel"), "Pamuk": ("Eklem", "AI")}
    en = _csv(uc, "en")
    assert en == {"Tekir": ("Edema Reduction", "Manual"), "Pamuk": ("Eklem", "AI")}


# ── kaynak kapıları ─────────────────────────────────────────────────


def test_PDF_ve_CSV_ham_seans_degerini_BASMAZ_gosterim_islevinden_gecer():
    pdf = (KOK / "apps/backend/utils/pdf_report_generator.py").read_text(encoding="utf-8")
    assert pdf.count("mod_etiketi(") >= 3 and pdf.count("hedef_etiketi(") >= 2
    assert 'ceviri.t("pdf.seans.modu", mode=mod_etiketi(mode))' in pdf
    hr = (KOK / "apps/backend/servers/history_router.py").read_text(encoding="utf-8")
    assert '_csv_safe(hedef_etiketi(s.get("target_condition", "")))' in hr
    assert '_csv_safe(mod_etiketi(s.get("treatment_mode", "")))' in hr
