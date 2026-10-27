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

import re
import sys
from pathlib import Path

import pytest

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
    # ⚠️ 2026-09-11: `B` = `unipolar_maskesi` (bobin başına bipolar/unipolar İSTEĞİ).
    # Bu kapı "pakete YOĞUNLUK (mT) alanı sızdı mı?" diye sorar. Kip alanı bir doz
    # büyüklüğü DEĞİL, bir dalga-biçimi anahtarıdır: uygulanan mT'yi beyan etmez, cihazın
    # ürettiği alanı ölçmez. Yine de kapı bilerek DAR: yeni bir alan eklenirse düşer ve
    # "bu alan doz beyan ediyor mu?" sorusu TEKRAR sorulur. Genişletmeden önce oku.
    beklenen = "<BB {n}f {n}f {n}f {n}I H B".format(n=n)
    assert STM_PAKET_FMT == beklenen, (
        f"STM paket bicimi {STM_PAKET_FMT!r}, beklenen {beklenen!r} — YENI BIR ALAN mi eklendi? "
        "mT/yogunluk eklendiyse PDF ve arayuz etiketleri GOZDEN GECIRILMELI (uygulanmayan doz "
        "beyan edilmesin)."
    )
    # Bobin genisligindeki grup sayisi: 3 float + 1 uint32. Fazlasi = yeni alan.
    gruplar = _re.findall(r"(\d+)([fI])", STM_PAKET_FMT)
    assert [g[1] for g in gruplar] == ["f", "f", "f", "I"], f"paket alan gruplari degismis: {gruplar}"
    assert all(int(g[0]) == n for g in gruplar), gruplar

    hc = (KOK / "apps" / "backend" / "controllers" / "hardware_controller.py").read_text(encoding="utf-8")
    # `update_coil` imzasında yoğunluk parametresi YOK.
    imza = hc.split("def update_coil(")[1].split(")")[0]
    assert "intensity" not in imza and "magnetic" not in imza, (
        f"update_coil artik yogunluk aliyor — PDF/UI etiketleri GUNCELLENMELI: {imza}"
    )


def test_KRITIK_ESP_komutu_mT_TASIMIYOR():
    api = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    # Seans başlatmada ESP'ye giden mqtt_payload gövdesi. (3. tur E1: command_id artık değişkene
    # çıkarıldı — D1.E10'dan beri `command_id = _komut_kimligi("sess", coil_id)`; anchor o atamaya
    # pinlenir, gövde mqtt_payload dict'idir. `payload.intensity` DB-run kaydında geçer ama tırnaksızdır;
    # kapı '"intensity"' JSON-anahtarını arar → yalnız komut gövdesine eklenirse düşer.)
    i = api.find('command_id = _komut_kimligi("sess", coil_id)')
    assert i > 0, "ESP seans komutu bulunamadi"
    j = api.index("mqtt_payload = {", i)  # seans yolundaki komut gövdesi (bu satırdan hemen sonra)
    govde = api[j : api.index("}", j)]  # dict'in kapanışına kadar (değerlerde iç içe süslü yok)
    assert '"intensity"' not in govde, "ESP komutuna yogunluk eklendi — etiketler GUNCELLENMELI"


# ── hasta sahibine giden PDF ─────────────────────────────────────────────────


# ⚠️ D5.59 TUR 2 (B-10.146; çürütücü n2b / n3b): aşağıdaki iki kapı eskiden kaynak METNİNDE iki literal arıyordu
# (`["Yoğunluk", f"{parameters.get('intensity'…` ve `"Yoğunluk (mT)", "Hedef"`). I18N göçünden beri başlıklar katalog anahtarıyla
# yazılıyor: aynı satır / sütun `ceviri.t("gecmis.csv.ortAlan")` (TR "Ort.Alan(mT)", EN "Avg.Field(mT)") ya da başka bir anahtarla
# geri gelse literal hiç oluşmaz → ikisi de YEŞİL kalıyordu (ölçüldü: rapor yolunu okuyan 25 dosyalık kümede 207 passed).
# Artık GERÇEK üretim yolu koşar: gerçek DB'ye (geçici kök) ayarlanan mT'si BELİRGİN bir seans yazılır, rapor gerçek yöntemle
# üretilir, derlenen story'nin TABLOLARI okunur. Bobin koşu tablosu ("Ayarlanan (mT)" başlıklı klinik-içi kayıt — meşru) DIŞINDAKİ
# HER tabloda (1) hiçbir hücre ölçülmüş-gibi / mT etiketi taşımaz, (2) ayarlanan değer hiçbir hücrede yok (etiket masum olsa bile).
# TR + EN. Beklenen başlık testte SABİT (katalogdan okunmaz). Başlığın kendisi: test_pdf_rapor_URETIM_YOLU_kapilari_D5_59.py (a).
_AYARLANAN_MT = 7.3  # belirgin değer: tarih / saat / süre / sayaç hücrelerinde rastlantıyla oluşmaz
_DEGER_DESENI = re.compile(r"(?<!\d)7[.,]3")
_MT_ETIKETI = re.compile(
    r"(?i)şiddet|siddet|yoğunluk|yogunluk|intensity|strength|ölçülen|olculen|measured|\balan|field|\(\s*mt\s*\)|\bmt\b|tesla|gauss"
)
_AYARLANAN_BASLIK = {"tr": "Ayarlanan (mT)", "en": "Set (mT)"}


def _rapor_tablolari(tmp_path, monkeypatch, dil: str, rapor: str) -> list[list[list[str]]]:
    """Gerçek DB → gerçek `generate_session_report` / `generate_patient_report` → derlenen story'deki tabloların hücreleri."""
    from utils import ceviri
    from utils.pdf_report_generator import PDFReportGenerator

    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)  # ad AYNEN saklansın (maskeleme opt-in)
    uretici = PDFReportGenerator(app_data_dir=tmp_path)  # DB izolasyonu: gerçek kliniğe dokunma
    db = uretici.db
    sid = db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
    assert sid, "aparat: seans yazılamadı"
    assert db.start_coil_run(
        sid,
        3,
        frequency_hz=50,
        duty_percent=25,
        phase=0,
        intensity_mt=_AYARLANAN_MT,
        hw_type="stm",
        started_epoch=1757000000.0,
    ), "aparat: bobin koşusu yazılamadı"
    db.end_session(
        sid,
        parameters={"frequency_hz": 50, "intensity_mt": _AYARLANAN_MT, "intensity": _AYARLANAN_MT},
        patient_notes="not",
        session_status="completed",
    )
    yakalanan: list = []
    gercek = uretici._build_pdf

    def _yakala(story, output_path, label):
        yakalanan.append(list(story))  # doc.build story'yi TÜKETİR → önce kopya
        return gercek(story, output_path, label)

    uretici._build_pdf = _yakala
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        if rapor == "seans":
            uretici.generate_session_report(session_ids=[sid], output_path=str(tmp_path / f"seans_{dil}.pdf"))
        else:
            uretici.generate_patient_report(patient_name="Pamuk", output_path=str(tmp_path / f"hasta_{dil}.pdf"))
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert len(yakalanan) == 1, "aparat: rapor derlenmedi"
    return [[[str(h) for h in satir] for satir in x._cellvalues] for x in yakalanan[0] if type(x).__name__ == "Table"]


def _mT_ihlalleri(tablolar) -> list[str]:
    return [h for t in tablolar for satir in t for h in satir if _MT_ETIKETI.search(h) or _DEGER_DESENI.search(h)]


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_hasta_raporunda_YOGUNLUK_SATIRI_YOK(temp_app_data, tmp_path, monkeypatch, dil):
    """Uygulanmamış bir dozu uygulanmış gibi beyan etmek, üçüncü kişiye yanlış tıbbi bilgidir.

    Seans raporu hasta sahibine gider: rapor bilgisi / istatistik / seans BİLGİ tablosu (2026-08-09'da "Yoğunluk: X mT" satırı
    buradan kaldırıldı) ayarlanan mT'yi ne etiketle ne değerle taşır. MUTASYON: `_session_info_rows`a
    `[ceviri.t("gecmis.csv.ortAlan"), <ayarlanan>]` (n2b) / "Yoğunluk (mT)" literali (n2) / masum etiketli değer → KIRMIZI.
    """
    tablolar = _rapor_tablolari(tmp_path, monkeypatch, dil, "seans")
    bobin = [i for i, t in enumerate(tablolar) if "Hz" in t[0]]
    assert len(bobin) == 1, f"bobin koşu tablosu rapora girmedi (ya da çift): {[t[0] for t in tablolar]}"
    assert _AYARLANAN_BASLIK[dil] in tablolar[bobin[0]][0], (
        f"bobin koşu tablosu başlığı '{_AYARLANAN_BASLIK[dil]}' değil ({dil}): {tablolar[bobin[0]][0]}"
    )
    assert any(_DEGER_DESENI.search(h) for h in tablolar[bobin[0]][1]), (
        f"ayarlanan değer bobin koşu tablosunda yok (kayıt rapora ulaşmıyor; yokluk ölçümü de anlamsızlaşır): {tablolar[bobin[0]]}"
    )
    digerleri = [t for i, t in enumerate(tablolar) if i != bobin[0]]
    assert any(h == "Pamuk" for t in digerleri for satir in t for h in satir), (
        "aparat: seans BİLGİ tablosu (hasta adı satırı) okunmadı"
    )
    ihlal = _mT_ihlalleri(digerleri)
    assert not ihlal, (
        f"hasta sahibine giden seans raporunda bobin tablosu DIŞINDA ayarlanan mT / ölçülmüş-gibi etiket var ({dil}): {ihlal}"
    )


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_ozet_tablosunda_YOGUNLUK_SUTUNU_YOK(temp_app_data, tmp_path, monkeypatch, dil):
    """Hasta raporu (hasta bilgisi / istatistik / tedavi GEÇMİŞİ tablosu — "Yoğunluk (mT)" sütunu kaldırıldı) ayarlanan mT'yi
    ne etiketle ne değerle taşır. MUTASYON: geçmiş tablosuna `ceviri.t("gecmis.csv.ortAlan")` sütunu + değer (n3b) /
    "Yoğunluk (mT)" literali (n3) → KIRMIZI."""
    tablolar = _rapor_tablolari(tmp_path, monkeypatch, dil, "hasta")
    assert any(re.fullmatch(r"50(\.0+)?", h) for t in tablolar for satir in t[1:] for h in satir), (
        f"aparat: tedavi geçmişi tablosu seans satırını (50 Hz) taşımıyor: {tablolar}"
    )
    ihlal = _mT_ihlalleri(tablolar)
    assert not ihlal, f"hasta raporunda ayarlanan mT / ölçülmüş-gibi etiket var ({dil}): {ihlal}"


def test_klinik_ici_tablo_AYARLANAN_der_siddet_DEMEZ():
    """Kaydı tutmak meşru; "şiddet" demek ölçülmüş gibi okutur."""
    pdf = (KOK / "apps" / "backend" / "utils" / "pdf_report_generator.py").read_text(encoding="utf-8")
    # ⚠️ D5.59 (B-10.146): eskiden burada `'"Ayarlanan (mT)"' in pdf` vardı — I18N göçünden beri o dize YALNIZ bir YORUMDA (başlık
    # `ceviri.t("pdf.seans.ayarlananMt")`); başlık "Yoğunluk (mT)" literaline ya da başka anahtara çevrilse de YEŞİLDİ (ölçüldü).
    # Başlığın KENDİSİ rapor üretim yolunda (gerçek DB → generate_session_report → bobin tablosu başlık hücresi, TR + EN) ölçülür:
    # tests/test_pdf_rapor_URETIM_YOLU_kapilari_D5_59.py::test_KRITIK_D559a_bobin_kosu_tablosu_basligi_AYARLANAN_mT_rapor_yolunda.
    # Burada kalan: "Şiddet (mT)" bir veri DİZESİ olarak geri gelmesin (yorum satırları elenir).
    #
    # ⚠️ Eskiden `pdf.split("table_data = [[")` ile ayrıştırılıyordu — `ruff format` listeyi
    # çok satıra açınca (`table_data = [\n    [...]`) desen tutmadı ve test kırıldı. Biçime
    # değil ANLAMA bak: "Şiddet (mT)" bir DİZE OLARAK hiçbir yerde geçmemeli; yorumda geçmesi
    # serbest (yorum satırları elenir).
    kod = "\n".join(s for s in pdf.splitlines() if not s.lstrip().startswith("#"))
    assert '"Şiddet (mT)"' not in kod, "veri basliginda hala 'Siddet (mT)'"


def test_CSV_basliklari_AYARLANAN_der():
    hr = (KOK / "apps" / "backend" / "servers" / "history_router.py").read_text(encoding="utf-8")
    assert "Siddet(mT)" not in hr, "CSV basligi hala 'Siddet(mT)'"
    # I18N: CSV basligi kataloga tasindi — olcut GEVSEMEDI, yer degistirdi (kaynak anahtari KULLANIR + TR birebir "Ayarlanan(mT)" + EN dolu).
    import i18n_yardimci as iy

    iy.metin_kapisi("apps/backend/servers/history_router.py", "gecmis.csv.ayarlanan", "Ayarlanan(mT)", yuzey="sunucu")


# ── arayüz ───────────────────────────────────────────────────────────────────


def test_KRITIK_UI_alani_YALNIZ_KAYIT_oldugunu_soyler():
    """Etiket bunu söylemezse operatör yoğunluğu ayarladığını sanır ve gerçek doz
    beklediğinden farklı olur.

    ⚠️ `apps/ui/` (Expo mobil) AYRI projedir ve bu depoda izlenmez → CI'da dosya YOKTUR ve test
    `FileNotFoundError` ile düşerdi (2026-08-12). Atlanır; `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`
    ile atlama yasaklanabilir. Bu dosyadaki DİĞER testler (STM paketi / ESP komutu / PDF /
    history_router) depo içi kaynakları okur ve CI'da tam koşmaya devam eder.
    """
    cs = capraz.oku("apps/ui/src/screens/ControlScreen.tsx")
    # I18N: etiket kataloğa taşındı — ölçüt GEVŞEMEDİ, yer değiştirdi (aynı alan etiketi `t(anahtar)`; kaynak anahtarı kullanıyor + TR birebir + EN dolu).
    # İşlev içinde içe aktarım: meta kapılar (D404) asgari ağaca yalnız capraz.py + c_soyucu.py kopyalar (dosya yoksa yukarıda atlanır).
    import i18n_yardimci as iy

    iy.metin_kapisi(
        "apps/ui/src/screens/ControlScreen.tsx", "kontrol.ekran.yogunlukKayit", "Yoğunluk (mT, yalnız kayıt)"
    )
    assert 'label={t("kontrol.ekran.yogunlukKayit")}' in cs, "UI etiketi hala cihaza gidiyormus gibi gosteriyor"


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
