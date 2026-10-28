# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10e — PDF raporu (seans / hasta), yedek dosyası (parola + içe aktarma iletileri) ve seans durumu etiketi istek dilinde.

Türkçe çıktı ESKİ metinle BAYT BAYT aynı (beklenen metinler burada sabittir); `X-PEMF-Dil: en` → İngilizce. PDF GERÇEK: gerçek DB + gerçek `PDFReportGenerator` + PDF'ten çıkarılan metin.
MUTASYON: katalog TR değeri değişirse / etiket ham metne dönerse / durum tablosu ham dönerse KIRMIZI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


@pytest.fixture(params=["tr", "en"])
def dil(request):
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(request.param)
    try:
        yield request.param
    finally:
        ceviri.istek_dili_var.reset(jeton)


def _t(tr, en, dil):
    return tr if dil == "tr" else en


# ── yedek dosyası ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_yedek_parola_iletileri_TR_bayt_bayt_EN_ingilizce(dil):
    from utils.data_export import MIN_PAROLA, parola_gecerli_mi

    assert parola_gecerli_mi("") == (
        False,
        _t(
            "Parola boş olamaz — şifresiz tıbbi veri dosyası üretilmez.",
            "The password cannot be empty — an unencrypted medical data file is never produced.",
            dil,
        ),
    )
    assert parola_gecerli_mi("kisa") == (
        False,
        _t(
            f"Parola en az {MIN_PAROLA} karakter olmalı. Bu dosya kliniğin tüm hasta geçmişini taşır ve tek koruması bu paroladır.",
            f"The password must be at least {MIN_PAROLA} characters. This file carries the whole patient history of the clinic and the password is its only protection.",
            dil,
        ),
    )
    assert parola_gecerli_mi("aaaaaaaaaaaaaaaa") == (
        False,
        _t(
            "Parola çok basit (aynı karakterlerin tekrarı). Farklı karakterler kullanın.",
            "The password is too simple (a repetition of the same characters). Use different characters.",
            dil,
        ),
    )
    assert parola_gecerli_mi("Bu-Yeterince-Uzun-Bir-Parola") == (True, "")


def test_yedek_dosya_hatalari_TR_bayt_bayt_EN_ingilizce(dil):
    from utils.data_export import ExportError, decrypt_bundle, encrypt_bundle

    with pytest.raises(ExportError) as e:
        decrypt_bundle(b"degil", "Bu-Yeterince-Uzun-Bir-Parola")
    assert str(e.value) == _t(
        "Bu dosya bir PEMF Vet veri yedeği değil.", "This file is not a PEMF Vet data backup.", dil
    )
    blob = encrypt_bundle({"x": 1}, "Bu-Yeterince-Uzun-Bir-Parola")
    with pytest.raises(ExportError) as e2:
        decrypt_bundle(blob, "Baska-Yeterince-Uzun-Parola")
    assert str(e2.value) == _t(
        "Parola yanlış ya da dosya bozulmuş.", "The password is wrong or the file is corrupt.", dil
    )
    yeni = encrypt_bundle({"bundle_version": 99}, "Bu-Yeterince-Uzun-Bir-Parola")
    with pytest.raises(ExportError) as e3:
        decrypt_bundle(yeni, "Bu-Yeterince-Uzun-Bir-Parola")
    assert str(e3.value) == _t(
        "Bu yedek daha yeni bir sürümle üretilmiş (v99). Önce uygulamayı güncelleyin.",
        "This backup was produced by a newer version (v99). Update the app first.",
        dil,
    )


# ── seans durumu ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_seans_durumu_etiketi_istek_dilinde_ham_deger_degismez(dil):
    from utils.seans_durum import durum_etiketi

    assert durum_etiketi("completed") == _t("Tamamlandı", "Completed", dil)
    assert durum_etiketi("EMERGENCY_STOPPED") == _t("Acil Durduruldu", "Emergency Stopped", dil)
    assert durum_etiketi("aborted_due_to_power") == _t("Elektrik Kesintisi", "Power Outage", dil)
    assert durum_etiketi("hardware_rejected") == _t("Donanım Reddetti", "Hardware Rejected", dil)
    assert durum_etiketi("quantum_flux") == "Quantum_flux"  # bilinmeyen: çevrilmeden, silinmeden
    assert durum_etiketi(None) == "" and durum_etiketi("") == ""


# ── PDF (uçtan uca) ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────

fitz = capraz.paket_yoksa_atla("fitz", sebep="PyMuPDF yok -> PDF metni çıkarılamaz")


def _rapor(tmp_path, dil_kodu):
    from database.treatment_history_db import TreatmentHistoryDB
    from utils import ceviri
    from utils.pdf_report_generator import PDFReportGenerator

    kok = tmp_path / f"pdf_{dil_kodu}"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    sid = db.start_session(treatment_mode="Manuel", patient_name="Mia")
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


def test_PDF_Turkce_eski_etiketlerle_ayni(tmp_path):
    seans, hasta = _rapor(tmp_path, "tr")
    for s in (
        "PEMF SEANS RAPORU",  # Y163 (YH A2): TEDAVİ → SEANS
        "İSTATİSTİKLER",
        "Toplam Seans Sayısı",
        "Toplam Seans Süresi",
        "Ortalama Seans Süresi",
        "Manuel Modu",
        "SEANSLAR",
        "Başlangıç Saati",
        "Bitiş Saati",
        "Seans Modu",
        "Hedef Durum",
        "Hasta Adı",
        "Bobin Çalışmaları",
        "Ayarlanan (mT)",
        "Ort. Sıc. (C)",
    ):
        assert s in seans, (s, seans[:300])
    assert "1 seans" in seans
    for s in (
        "HASTA RAPORU: MIA",
        "Hasta Adı:",
        "Hasta Soyadı:",
        "Belirtilmemiş",
        "İlk Seans:",
        "HASTA İSTATİSTİKLERİ",
        "İlk Seans Tarihi",
        "Son Seans Tarihi",
        "SEANS GEÇMİŞİ",
        "Süre (dk)",
        "Frekans (Hz)",
    ):
        assert s in hasta, (s, hasta[:300])
    # Y163 (YH A2): seans / hasta PDF'inde "tedavi" sözcüğü KALMAZ (hukuki cümle bu raporlarda yok)
    for metin in (seans, hasta):
        assert not re.search(r"[Tt]edavi|TEDAV[İI]", metin), re.findall(r".{0,30}(?:[Tt]edavi|TEDAV[İI]).{0,30}", metin)


def test_PDF_Ingilizce_etiketler_Ingilizce_veri_aynen(tmp_path):
    seans, hasta = _rapor(tmp_path, "en")
    for s in (
        "PEMF SESSION REPORT",
        "STATISTICS",
        "Total Number of Sessions",
        "Total Session Duration",  # Y163 (YH A2): Session (treatment / therapy YOK)
        "Average Session Duration",
        "Manual Mode",  # EN1: seans modu DB değeri `Manuel` gösterimde çevrilir (değer → anahtar; DB değeri değişmez)
        "SESSIONS",
        "Start Time",
        "End Time",
        "Session Mode",
        "Target Condition",
        "Patient Name",
        "Coil Runs",
        "Set (mT)",
        "Avg. Temp. (C)",
    ):
        assert s in seans, (s, seans[:300])
    assert "1 session" in seans and "1 seans" not in seans
    for s in (
        "PATIENT REPORT: MIA",
        "Patient Name:",
        "Patient Surname:",
        "Not specified",
        "First Session:",
        "PATIENT STATISTICS",
        "First Session Date",
        "Last Session Date",
        "SESSION HISTORY",
        "Duration (min)",
        "Frequency (Hz)",
    ):
        assert s in hasta, (s, hasta[:300])
    # Türkçe etiket KALMAZ (hasta adı / mod değeri kullanıcı verisidir: "Mia", "Manuel")
    for metin in (seans, hasta):
        kalan = [
            k for k in ("Başlangıç", "Bitiş", "Hasta", "Seans", "Tedavi", "Bobin", "İSTATİSTİK", "dakika") if k in metin
        ]
        assert not kalan, kalan
        assert not TR_HARF.search(metin), TR_HARF.findall(metin)
        # PEMF açılımı ("Pulsed Electromagnetic Field Therapy") terim sözlüğünün gerekçeli istisnası — ürün adı, tedavi iddiası değil
        sade = metin.replace("Pulsed Electromagnetic Field Therapy", "")
        assert not re.search(r"(?i)treatment|therapy", sade), re.findall(
            r"(?i).{0,30}(?:treatment|therapy).{0,30}", sade
        )
