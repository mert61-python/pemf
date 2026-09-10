# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""mT DOZU DÜRÜSTLÜĞÜ (2026-08-09 denetimi, Tier 2).

ÖLÇÜLEN DURUM: operatörün girdiği yoğunluk (mT) CİHAZA HİÇ ULAŞMIYOR.
  • STM binary paketi: `<BB Nf Nf Nf NI H` = başlık + duty[N] + phase[N] + freq[N] + duration[N]
    + ref_ms (N = `STM_PAKET_BOBIN_SAYISI`). **mT alanı YOK.**
    `update_coil(coil_id, freq, duty, phase, duration)` imzasında da yok.
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
    """İddianın dayanağı: pakette YALNIZ duty/phase/freq/duration + ref_ms + crc32 var.

    ⚠️ ÇIPA DEĞİŞTİRİLDİ (2026-09-10). Eskiden `"'<BB 5f 5f 5f 5I H'" in hc` yazıyordu, yani
    çıpa ELLE yazılmış bir bicim dizesineydi. O gün paket 5 bobinden 7'ye çıkarıldı (bobin 6-7
    ESP'den STM'e taşındı) ve bu kapı, mT ile İLGİSİ OLMAYAN bir değişiklikte kırıldı — üstelik
    dize tek kaynağa taşındığı için ARTIK HİÇ eşleşmeyecekti (dosyada literal kalmadı) ve
    "mT eklendi mi?" sorusu bir daha ASLA sorulmayacaktı: sahte-kırmızı, sonra sahte-yeşil.

    Yeni çıpa GENİŞLİKTEN BAĞIMSIZ ama ALAN EKLEMEYE duyarlı: biçim dizesi tek kaynaktan
    okunur ve alan gruplarının SAYISI (3 float grubu + 1 uint32 grubu + ref_ms + crc32)
    ölçülür. Bobin sayısı serbestçe değişebilir; yeni bir ALAN eklenirse kapı düşer.

    MUTASYON: `STM_PAKET_FMT`e bir grup ekle (ör. `... {n}f H` → yoğunluk) → KIRMIZI.
    """
    import re as _re

    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_FMT

    n = STM_PAKET_BOBIN_SAYISI
    beklenen = "<BB {n}f {n}f {n}f {n}I H".format(n=n)
    assert STM_PAKET_FMT == beklenen, (
        f"STM paket bicimi {STM_PAKET_FMT!r}, beklenen {beklenen!r} — YENI BIR ALAN mi eklendi? "
        "mT/yogunluk eklendiyse PDF ve arayuz etiketleri GOZDEN GECIRILMELI (uygulanmayan doz "
        "beyan edilmesin)."
    )
    # Bobin genisligindeki grup sayisi: 3 float + 1 uint32. Fazlasi = yeni alan.
    gruplar = _re.findall(r"(\d+)([fI])", STM_PAKET_FMT)
    assert [g[1] for g in gruplar] == ["f", "f", "f", "I"], f"paket alan gruplari degismis: {gruplar}"
    assert all(int(g[0]) == n for g in gruplar), gruplar

    hc = (KOK / "controllers" / "hardware_controller.py").read_text(encoding="utf-8")
    # `update_coil` imzasında yoğunluk parametresi YOK.
    imza = hc.split("def update_coil(")[1].split(")")[0]
    assert "intensity" not in imza and "magnetic" not in imza, (
        f"update_coil artik yogunluk aliyor — PDF/UI etiketleri GUNCELLENMELI: {imza}"
    )


def test_KRITIK_ESP_komutu_mT_TASIMIYOR():
    api = (KOK / "servers" / "api_server.py").read_text(encoding="utf-8")
    # Seans başlatmada ESP'ye giden mqtt_payload gövdesi. (3. tur E1: command_id artık değişkene
    # çıkarıldı — `command_id = f"sess_{coil_id}...`; anchor o atamaya pinlenir, gövde mqtt_payload
    # dict'idir. `payload.intensity` DB-run kaydında geçer ama tırnaksızdır; kapı '"intensity"'
    # JSON-anahtarını arar → yalnız komut gövdesine eklenirse düşer.)
    i = api.find('command_id = f"sess_{coil_id}')
    assert i > 0, "ESP seans komutu bulunamadi"
    j = api.index("mqtt_payload = {", i)  # seans yolundaki komut gövdesi (bu satırdan hemen sonra)
    govde = api[j : api.index("}", j)]  # dict'in kapanışına kadar (değerlerde iç içe süslü yok)
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
