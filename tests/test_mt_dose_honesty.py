# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""mT DOZU DÜRÜSTLÜĞÜ (2026-08-09 denetimi, Tier 2).

ÖLÇÜLEN DURUM: operatörün girdiği yoğunluk (mT) CİHAZA HİÇ ULAŞMIYOR.
  • STM binary paketi: `<BB 5f 5f 5f 5I H` = başlık + duty[5] + phase[5] + freq[5] + duration[5]
    + ref_ms. **mT alanı YOK.** `update_coil(coil_id, freq, duty, phase, duration)` imzasında da yok.
  • ESP MQTT komutu: `{command, freq, duty, phase, duration}`. **mT alanı YOK.**
Değer yalnız veritabanına yazılıyor.

ARIZA: buna rağmen HASTA SAHİBİNE GİDEN PDF'te `Yoğunluk: X mT` satırı basılıyordu — yani
uygulanmamış bir doz, uygulanmış gibi üçüncü kişiye beyan ediliyordu. Klinik-içi tablolarda da
"Şiddet (mT)" deniyordu; "şiddet" ölçülmüş bir büyüklük gibi okunur.

⚠️ Bu testler dozu UYGULATMAZ — gerçek çözüm firmware'dedir (paketi genişlet + osiloskopla
doğrula). Yaptıkları, yazılımın uygulamadığı bir şeyi İDDİA ETMEMESİNİ kilitlemektir.
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "tests"))  # `tests` paket değil (conftest tabanlı toplama)
import capraz  # noqa: E402  — kardeş-depo kaynakları için atlama yardımcısı

# ── dayanak: mT gerçekten taşınmıyor ─────────────────────────────────────────


def test_KRITIK_STM_paketi_mT_TASIMIYOR():
    """İddianın dayanağı. Bir gün paket genişletilirse bu test düşer ve etiketler/PDF
    gözden geçirilir — sessizce 'artık uygulanıyor' sanılmasın."""
    hc = (KOK / "controllers" / "hardware_controller.py").read_text(encoding="utf-8")
    assert "'<BB 5f 5f 5f 5I H'" in hc, "STM paket formatı değişti — mT eklendi mi?"
    # `update_coil` imzasında yoğunluk parametresi YOK.
    imza = hc.split("def update_coil(")[1].split(")")[0]
    assert "intensity" not in imza and "magnetic" not in imza, (
        f"update_coil artik yogunluk aliyor — PDF/UI etiketleri GUNCELLENMELI: {imza}"
    )


def test_KRITIK_ESP_komutu_mT_TASIMIYOR():
    api = (KOK / "servers" / "api_server.py").read_text(encoding="utf-8")
    # Seans başlatmada ESP'ye giden gövde.
    i = api.find('"command_id": f"sess_{coil_id}')
    assert i > 0, "ESP seans komutu bulunamadi"
    govde = api[i : i + 400]
    assert '"intensity"' not in govde, "ESP komutuna yogunluk eklendi — etiketler GUNCELLENMELI"


# ── hasta sahibine giden PDF ─────────────────────────────────────────────────


def test_KRITIK_hasta_raporunda_YOGUNLUK_SATIRI_YOK():
    """Uygulanmamış bir dozu uygulanmış gibi beyan etmek, üçüncü kişiye yanlış tıbbi bilgidir."""
    pdf = (KOK / "utils" / "pdf_report_generator.py").read_text(encoding="utf-8")
    assert '["Yoğunluk", f"{parameters.get(\'intensity\'' not in pdf, (
        "hasta raporunda 'Yogunluk: X mT' satiri geri geldi"
    )


def test_KRITIK_ozet_tablosunda_YOGUNLUK_SUTUNU_YOK():
    pdf = (KOK / "utils" / "pdf_report_generator.py").read_text(encoding="utf-8")
    assert '"Yoğunluk (mT)", "Hedef"' not in pdf, "ozet tablosunda mT sutunu geri geldi"


def test_klinik_ici_tablo_AYARLANAN_der_siddet_DEMEZ():
    """Kaydı tutmak meşru; "şiddet" demek ölçülmüş gibi okutur."""
    pdf = (KOK / "utils" / "pdf_report_generator.py").read_text(encoding="utf-8")
    assert '"Ayarlanan (mT)"' in pdf, "bobin kosusu tablosu etiketi duzeltilmemis"
    # Yalnız yorum satırında geçebilir; veri başlığı olarak GEÇMEMELİ.
    #
    # ⚠️ Eskiden `pdf.split("table_data = [[")` ile ayrıştırılıyordu — `ruff format` listeyi
    # çok satıra açınca (`table_data = [\n    [...]`) desen tutmadı ve test kırıldı. Biçime
    # değil ANLAMA bak: "Şiddet (mT)" bir DİZE OLARAK hiçbir yerde geçmemeli; yorumda geçmesi
    # serbest (yorum satırları elenir).
    kod = "\n".join(s for s in pdf.splitlines() if not s.lstrip().startswith("#"))
    assert '"Şiddet (mT)"' not in kod, "veri basliginda hala 'Siddet (mT)'"


def test_CSV_basliklari_AYARLANAN_der():
    hr = (KOK / "servers" / "history_router.py").read_text(encoding="utf-8")
    assert "Siddet(mT)" not in hr, "CSV basligi hala 'Siddet(mT)'"
    assert "Ayarlanan(mT)" in hr, "CSV basligi duzeltilmemis"


# ── arayüz ───────────────────────────────────────────────────────────────────


def test_KRITIK_UI_alani_YALNIZ_KAYIT_oldugunu_soyler():
    """Etiket bunu söylemezse operatör yoğunluğu ayarladığını sanır ve gerçek doz
    beklediğinden farklı olur.

    ⚠️ `pf/` (Expo mobil) AYRI projedir ve bu depoda izlenmez → CI'da dosya YOKTUR ve test
    `FileNotFoundError` ile düşerdi (2026-08-12). Atlanır; `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`
    ile atlama yasaklanabilir. Bu dosyadaki DİĞER testler (STM paketi / ESP komutu / PDF /
    history_router) depo içi kaynakları okur ve CI'da tam koşmaya devam eder.
    """
    cs = capraz.oku("pf/src/screens/ControlScreen.tsx")
    assert 'label="Yoğunluk (mT, yalnız kayıt)"' in cs, "UI etiketi hala cihaza gidiyormus gibi gosteriyor"


# ── veri KAYBEDİLMEDİ ────────────────────────────────────────────────────────


def test_deger_VERITABANINDA_korunur(temp_app_data):
    """Etiketleri düzeltmek veriyi silmek değildir: operatörün girdiği hedef kayıtta kalmalı
    (klinik notu + ileride firmware desteği gelirse karşılaştırma tabanı)."""
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    try:
        with db._get_connection() as c:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO session_coil_runs (coil_id, started_epoch, intensity_mt, created_at) VALUES (?,?,?,?)",
                (3, 1.0, 2.5, 1.0),
            )
            c.commit()
        satir = db.export_rows()["session_coil_runs"][0]
        assert satir["intensity_mt"] == 2.5, "operatorun girdigi hedef kayittan silindi"
    finally:
        db.close_connections()
