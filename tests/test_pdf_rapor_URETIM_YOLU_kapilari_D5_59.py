# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.59 (B-10.146 · B-10.153 · B-10.169) KAPISI — PDF rapor kapıları rapor ÜRETİM YOLUNA bağlı.

Üç eski kapı kaynak METNİNE ya da yardımcıya bakıyordu, rapor yoluna değil (ölçüldü, HEAD d38b0db5):
  (a) `test_mt_dose_honesty.py::test_klinik_ici_tablo_AYARLANAN_der_siddet_DEMEZ` `'"Ayarlanan (mT)"' in pdf` arıyordu — I18N
      göçünden beri o dize YALNIZ bir YORUMDA (başlık `ceviri.t("pdf.seans.ayarlananMt")`); başlık "Yoğunluk (mT)" literaline ya da
      başka bir katalog anahtarına çevrilse de YEŞİLDİ. Rapor metnini okuyan tek kapı (`test_sunucu_pdf_yedek_durum_istek_dilinde_P1.py`)
      PyMuPDF'e (`fitz`) muhtaç; fitz `requirements*.txt`'te YOK → CI'da modül düzeyinde ATLAR. Okuyucu (veteriner / hayvan sahibi)
      uygulanmamış ayarı ölçülmüş gibi okurdu.
  (b) `test_pdf_safety.py` `_esc`i DOĞRUDAN çağırıyordu — `_add_single_session`ta hasta notundan `_esc` kaldırılınca YEŞİLDİ; oysa
      `<b>kapanmamış` notu ReportLab ayrıştırıcısında ValueError → o seansın PDF'i KALICI 500 (+ `<img src=…>` dış istek denemesi).
  (c) `test_xai_batch_rapor.py` `b"/Image" in pdf` arıyordu — ReportLab her sayfanın `/ProcSet [/PDF /Text /ImageB /ImageC /ImageI]`
      satırında bu diziyi ZATEN yazar; görsel gömme `pass` yapılsa da YEŞİLDİ.

KAPI: GERÇEK üretim yolu koşar — gerçek DB'ye (geçici kök) seans + bobin koşusu + hasta notu yazılır, `generate_session_report` raporu
üretir (gerçek `doc.build`); derlenen story'nin bir KOPYASI `_build_pdf` sarmalayıcısında okunur (derleme yine gerçek yöntemle yapılır).
  (a) bobin koşu tablosunun BAŞLIK hücresi istek dilinde birebir "Ayarlanan (mT)" / "Set (mT)", ayar değeri O sütunda, hiçbir başlık
      "şiddet / yoğunluk / intensity / measured" demez (fitz'e muhtaç değil — CI'da da koşar);
  (b) kapanmamış etiketli not ile rapor üretilir, not PDF'te VERİ olarak (aynen) durur;
  (c) üretilen XAI PDF'indeki gerçek görüntü XObject'leri (`/Subtype /Image`) boyutlarıyla sayılır;
  (d) TUR 2 (çürütücü n4): `_esc`in ikiz çağrı yeri — HASTA raporu başlığı `<b>…` adlı hastanın adını VERİ olarak taşır.
Bobin tablosu DIŞINDAKİ tablolar ve TÜM paragraflar (seans bilgisi / hasta raporu geçmişi / istatistik; çürütücü n2b / n3b, TUR 3
y1 / y2 / y4 — iki seanslı aparat, bobin tablosunda ikiz mT sütunu): `test_mt_dose_honesty.py`
`test_KRITIK_seans_raporunda_YOGUNLUK_SATIRI_ve_mT_YOK` / `test_KRITIK_hasta_raporunda_YOGUNLUK_SUTUNU_ve_mT_YOK` (aynı üretim yolu, TR + EN).
MUTASYON: (a) başlığı `"Yoğunluk (mT)"` literali / başka anahtar yapmak; (b) `Paragraph(_esc(patient_notes), …)` → `Paragraph(patient_notes, …)`
ya da `_esc` yalnız `<img` kaçırır; (c) `story.append(Image(...))` → `pass` / görsel yerine dosya adı metni; (d) başlıkta `_esc` yok /
çift kaçış / etiket ayıklama → KIRMIZI.
reportlab ÇALIŞMA-ZAMANI bağımlılığıdır (requirements.txt + requirements-test.txt) — atlama YOK: yoksa kapı düşer.
"""

from __future__ import annotations

import base64
import re

import pytest

_PNG_1x1_RGBA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

#: Ürün kataloğundan OKUNMAZ (mutasyon hedefi) — beklenen başlık burada sabittir (TR birebir, Y157).
_AYARLANAN_BASLIK = {"tr": "Ayarlanan (mT)", "en": "Set (mT)"}
_OLCULMUS_GIBI = re.compile(r"(?i)şiddet|siddet|yoğunluk|yogunluk|intensity|strength|ölçülen|measured")
_MT_ALAN = re.compile(r"(?i)\(\s*mt\s*\)|\bmt\b|\balan|field|tesla|gauss")
_NOT = "<b>kapanmamış <img src='yok_D559.png'/> & notu"


@pytest.fixture()
def uretici(temp_app_data, tmp_path, monkeypatch):
    monkeypatch.delenv("PEMF_MASK_HISTORY_PII", raising=False)  # not AYNEN saklanmalı (maskeleme opt-in)
    from utils.pdf_report_generator import PDFReportGenerator

    return PDFReportGenerator(app_data_dir=tmp_path)  # DB izolasyonu: gerçek kliniğe dokunma


def _seans_raporu(uretici, tmp_path, dil: str, notlar: str):
    """Gerçek DB → gerçek `generate_session_report` → (pdf yolu, derlenen story kopyası)."""
    from utils import ceviri

    db = uretici.db
    sid = db.start_session(treatment_mode="Manuel", patient_name="Pamuk")
    assert sid, "aparat: seans yazılamadı"
    assert db.start_coil_run(
        sid, 3, frequency_hz=50, duty_percent=25, phase=0, intensity_mt=2.5, hw_type="stm", started_epoch=1757000000.0
    ), "aparat: bobin koşusu yazılamadı"
    db.end_session(sid, patient_notes=notlar, session_status="completed")
    yakalanan: list = []
    gercek = uretici._build_pdf

    def _yakala(story, output_path, label):
        yakalanan.append(list(story))  # doc.build story'yi TÜKETİR → önce kopya
        return gercek(story, output_path, label)

    uretici._build_pdf = _yakala
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        yol = uretici.generate_session_report(session_ids=[sid], output_path=str(tmp_path / f"seans_{dil}.pdf"))
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert len(yakalanan) == 1, "aparat: rapor derlenmedi"
    with open(yol, "rb") as f:
        assert f.read(5) == b"%PDF-", "PDF basılmadı"
    return yol, yakalanan[0]


def _bobin_tablosu(story):
    """Story'deki bobin koşu tablosu (başlığında "Hz" olan TEK tablo; seans bilgi tablosu iki sütunlu anahtar/değerdir)."""
    tablolar = [x for x in story if type(x).__name__ == "Table" and "Hz" in [str(h) for h in x._cellvalues[0]]]
    assert len(tablolar) == 1, f"bobin koşu tablosu rapora girmedi (ya da çift): {len(tablolar)}"
    return tablolar[0]


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_D559a_bobin_kosu_tablosu_basligi_AYARLANAN_mT_rapor_yolunda(uretici, tmp_path, dil):
    _, story = _seans_raporu(uretici, tmp_path, dil, "not")
    tablo = _bobin_tablosu(story)
    baslik = [str(h) for h in tablo._cellvalues[0]]
    beklenen = _AYARLANAN_BASLIK[dil]
    assert beklenen in baslik, f"bobin koşu tablosu başlığı '{beklenen}' değil ({dil}): {baslik}"
    olculmus = [h for h in baslik if _OLCULMUS_GIBI.search(h)]
    assert not olculmus, f"başlık uygulanmamış ayarı ÖLÇÜLMÜŞ gibi okutuyor ({dil}): {olculmus}"
    # TUR 3 (çürütücü 2 y4): beklenen başlığın YANINA ikinci bir mT / alan sütunu ("Ort.Alan(mT)" = ölçülmüş ortalama gibi) da yasak.
    ikiz = [h for h in baslik if h != beklenen and _MT_ALAN.search(h)]
    assert not ikiz, f"bobin koşu tablosunda '{beklenen}' DIŞINDA mT / alan etiketli sütun var ({dil}): {ikiz}"
    satir = [str(v) for v in tablo._cellvalues[1]]
    assert satir[baslik.index(beklenen)] == "2.5", (
        f"ayarlanan değer (2.5 mT) '{beklenen}' sütununda değil: {list(zip(baslik, satir))}"
    )


def test_KRITIK_D559b_hasta_notu_VERI_olarak_basilir_rapor_yolunda(uretici, tmp_path):
    try:
        _, story = _seans_raporu(uretici, tmp_path, "tr", _NOT)
    except AssertionError:
        raise
    # escape yoksa ReportLab ayrıştırıcısı: ValueError (kapanmamış etiket) / OSError (img src çözümü) — her istisna kapının kırmızısı
    except Exception as e:
        pytest.fail(
            f"hasta notu ReportLab mini-XML'i olarak YORUMLANDI ({type(e).__name__}: {str(e)[:80]}) — seansın PDF'i KALICI 500, "
            "<img src=…> dış kaynak dener"
        )
    paragraflar = [x for x in story if type(x).__name__ == "Paragraph"]
    assert any(p.getPlainText() == _NOT for p in paragraflar), (
        "hasta notu PDF'te AYNEN (veri olarak) yok — biçimlendirme dili olarak yorumlandı: "
        f"{[p.getPlainText()[:60] for p in paragraflar if 'kapanmam' in p.getPlainText()]}"
    )


_AD = "<b>Pamuk & Tom"  # i / ı içermez: büyük harfe çevirme dil kuralından bağımsız (karşılaştırma casefold)


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_D559d_hasta_raporu_basligi_hasta_adini_VERI_olarak_tasir(uretici, tmp_path, dil):
    """TUR 2 (çürütücü n4) — `_esc`in İKİZ çağrı yeri: `_add_patient_header` hasta adını başlık Paragraph'ına koyar.

    `ad=_esc(patient_name).upper()` → `str(patient_name).upper()` yapılınca eski kapılar (ve tur 1'in (b) kolu) YEŞİLDİ; oysa `<b>…`
    adlı hastanın HASTA raporu `ValueError: Parse error` → kalıcı 500. Kapı: gerçek DB → gerçek `generate_patient_report`; istisna =
    `pytest.fail`; başlık adı VERİ olarak (aynen, büyük/küçük harf hariç) taşır — çift kaçış / etiket ayıklama da KIRMIZI.
    """
    from utils import ceviri

    db = uretici.db
    sid = db.start_session(treatment_mode="Manuel", patient_name=_AD)
    assert sid, "aparat: seans yazılamadı"
    db.end_session(sid, patient_notes="not", session_status="completed")
    yakalanan: list = []
    gercek = uretici._build_pdf

    def _yakala(story, output_path, label):
        yakalanan.append(list(story))
        return gercek(story, output_path, label)

    uretici._build_pdf = _yakala
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        yol = uretici.generate_patient_report(patient_name=_AD, output_path=str(tmp_path / f"hasta_{dil}.pdf"))
    except AssertionError:
        raise
    except Exception as e:  # escape yoksa ReportLab ayrıştırıcısı ValueError verir — her istisna kapının kırmızısı
        pytest.fail(
            f"hasta ADI ReportLab mini-XML'i olarak YORUMLANDI ({type(e).__name__}: {str(e)[:80]}) — o hastanın raporu KALICI 500"
        )
    finally:
        ceviri.istek_dili_var.reset(jeton)
    with open(yol, "rb") as f:
        assert f.read(5) == b"%PDF-", "PDF basılmadı"
    assert len(yakalanan) == 1, "aparat: rapor derlenmedi"
    metinler = [x.getPlainText() for x in yakalanan[0] if type(x).__name__ == "Paragraph"]
    assert any(_AD.casefold() in m.casefold() for m in metinler), (
        f"hasta raporu başlığı hastanın adını AYNEN (veri olarak) taşımıyor: {[m[:60] for m in metinler[:4]]}"
    )


def _goruntu_boyutlari(pdf: bytes) -> list[tuple[int, int]]:
    """Gerçek görüntü XObject'lerinin (`/Subtype /Image`) boyutları — başka bir görüntünün `/SMask`ı (alfa kanalı) olan nesne hariç."""
    maske = {int(n) for n in re.findall(rb"/SMask\s+(\d+)\s+0\s+R", pdf)}
    boy = []
    for m in re.finditer(rb"(\d+)\s+0\s+obj\s*<<(.*?)>>", pdf, re.S):
        sozluk = m.group(2)
        if int(m.group(1)) in maske or not re.search(rb"/Subtype\s*/Image\b", sozluk):
            continue
        w = re.search(rb"/Width\s+(\d+)", sozluk)
        h = re.search(rb"/Height\s+(\d+)", sozluk)
        boy.append((int(w.group(1)), int(h.group(1))))
    return boy


def test_KRITIK_D559c_XAI_raporunda_GERCEK_goruntu_XObject_var(uretici, tmp_path):
    from PIL import Image as PilImage

    p1 = tmp_path / "xai_1x1.png"
    p1.write_bytes(base64.b64decode(_PNG_1x1_RGBA))
    p2 = tmp_path / "xai_3x2.png"
    PilImage.new("RGB", (3, 2), (200, 10, 10)).save(p2)
    gorselli = uretici.generate_xai_report(
        "D559 XAI",
        [
            {"etiket": "görsel 1", "goruntu": str(p1), "aciklama": "yöntem: hirescam"},
            {"etiket": "görsel 2", "goruntu": str(p2), "aciklama": "yöntem: eigencam"},
        ],
        str(tmp_path / "a.pdf"),
    )
    gorselsiz = uretici.generate_xai_report(
        "D559 XAI", [{"etiket": "not", "goruntu": None, "aciklama": "yalnız metin"}], str(tmp_path / "b.pdf")
    )
    with open(gorselli, "rb") as f:
        a = f.read()
    with open(gorselsiz, "rb") as f:
        b = f.read()
    assert b"/Image" in b, (
        "aparat: ProcSet'teki /ImageB… dizisi görselsiz PDF'te yok (eski kapının neden kör olduğu ölçülemez)"
    )
    assert _goruntu_boyutlari(b) == [], f"karşıt: görselsiz raporda görüntü XObject'i var: {_goruntu_boyutlari(b)}"
    boy = _goruntu_boyutlari(a)
    assert boy, "XAI raporu GÖRSEL GÖMMÜYOR (yalnız /ProcSet adı var)"
    assert sorted(boy) == [(1, 1), (3, 2)], f"XAI raporu her öğenin görselini gömmüyor: {boy} ≠ [(1, 1), (3, 2)]"
