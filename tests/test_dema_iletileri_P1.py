# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""I18N-P1 · dema-13 — DEMA simülatörü görünen metinleri (`dema-terapi-simülatörü/src/App.tsx`) katalogdan.

  * ALTIN: göç ÖNCESİ App.tsx'ten Türkçe değerler (HEAD kaynağında birebir doğrulandı) — katalog (tr) bunlardan sapmaz; EN dolu, Türkçe harfsiz,
    aynı yer tutucular; tanıtım / eğitim etiketi ve "sağlık profesyoneline danışın" uyarısı İngilizcede de VAR (anlam birebir).
  * KAYNAK: her anahtar App.tsx'te `t('anahtar')` ile KULLANILIR; kodda görünür Türkçe dizgi KALMAZ (yalnız dalga formu enum VERİSİ:
    'Sinüs' | 'Kare' | 'Testere dişi' — durum / karşılaştırma / `<option value>`); dalga formu görünen adı `dalgaAdi()` ile değer → anahtar.
  * TR görünüm eskisiyle aynı: ["Kare" → "Kare", "Sinüs" → "Sinüs", "Testere dişi" → "Testere dişi"] (değer = TR görünen ad).
Hukuki / sağlık uyarı metninin İngilizcesi için yayın onayı SAHİBE aittir. Sayfa dilinde `<html lang>` DEĞİŞMEZ (C15, S-I18N.10).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "tests"))
import i18n_yardimci as iy  # noqa: E402

DEMA = "dema-terapi-simülatörü"
APP = KOK / DEMA / "src" / "App.tsx"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

#: Altın tablo: anahtar → göç ÖNCESİ Türkçe değer.
ALTIN = {
    "aciklama.derin": "3-5 mT: Derin",
    "aciklama.yuzeysel": "1-2 mT: Yüzeysel",
    "alan.dielektrik": "Dielektrik Çıkış",
    "alan.indukleneKisa": "E-Alan",
    "alan.indukleneUzun": "İndüklenen E-Alan (Girdap Akımları)",
    "alan.yogunKisa": "Yoğun Alan",
    "alan.yogunUzun": "Yoğun Alan Dağılımı",
    "alt.gorsellestirme": "* Görselleştirme ve etkiler eğitim amaçlıdır.",
    "alt.uyari": "Bu simülatör tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez. DEMA terapisi uygulamadan önce mutlaka bir sağlık profesyoneline danışın.",
    "baslik.belge": "DEMA Simülatörü — tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez",
    "baslik.uygulama": "DEMA Terapi Simülatörü",
    "dalga.kare": "Kare",
    "dalga.modu": "{{dalga}} Modu",
    "dalga.secili": "Seçili Mod: ",
    "dalga.sinus": "Sinüs",
    "dalga.sinyali": "{{dalga}} Sinyali",
    "dalga.testere": "Testere dişi",
    "doku.deri": "Deri",
    "doku.kasDoku": "Kas/Doku",
    "doku.kesit": "DOKU KESİTİ",
    "doku.yag": "Yağ",
    "etki.agri.aciklama": "Akut Ağrı, Sinir Modülasyonu",
    "etki.agri.baslik": "Ağrı Yönetimi",
    "etki.baslik": "Potansiyel Biyolojik Etkiler",
    "etki.derin.aciklama": "Kemik, Eklem ve Derin Kas",
    "etki.derin.baslik": "Derin Etki",
    "etki.derinEtki": "Derin Etki",
    "etki.derinlik": "ETKİ DERİNLİĞİ: {{deger}} mT",
    "etki.dolasim.aciklama": "Kan Akışı, Doku İyileşmesi",
    "etki.dolasim.baslik": "Dolaşım",
    "etki.enerji.aciklama": "Metabolizma, Hücre Aktivasyonu",
    "etki.enerji.baslik": "Enerji",
    "etki.gevseme.aciklama": "Uyku Düzeni, Stres Azaltma",
    "etki.gevseme.baslik": "Gevşeme",
    "etki.yuzeysel.aciklama": "Deri ve Yüzey Dokular",
    "etki.yuzeysel.baslik": "Yüzeysel",
    "etki.yuzeyselEtki": "Yüzeysel Etki",
    "izleme.baslik": "Sinyal İzleme",
    "parametre.animasyon": "Animasyon",
    "parametre.baslik": "Terapi Parametreleri",
    "parametre.dalgaFormu": "Dalga Formu",
    "parametre.frekans": "Frekans",
    "parametre.sure": "Süre",
    "parametre.yogunluk": "Yoğunluk (mT)",
    "sure.dk": "{{deger}} dk",
    "ust.etiket": "Tanıtım/eğitim amaçlıdır, cihaz davranışını temsil etmez.",
}


def _tr():
    return iy.katalog("dema", "tr")


def _en():
    return iy.katalog("dema", "en")


def _yer_tutucu(s: str) -> list:
    return sorted(re.findall(r"\{\{(\w+)\}\}", s))


def _kod() -> str:
    """App.tsx — blok / satır yorumları ve import'lar HARİÇ."""
    s = APP.read_text(encoding="utf-8")
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(re.sub(r"(?m)(^|\s)//.*$", "", x) for x in s.splitlines())


def test_altin_tablo_boyutu():
    assert len(ALTIN) == 46, "kapı küçülmesin"


@pytest.mark.parametrize("anahtar", sorted(ALTIN))
def test_TR_deger_goc_oncesiyle_BAYT_BAYT_ayni_EN_dolu_Turkce_harfsiz_ayni_yer_tutucular(anahtar):
    tr, en = _tr(), _en()
    assert tr.get(anahtar) == ALTIN[anahtar], f"TR değer eskisinden FARKLI: {anahtar}"
    assert str(en.get(anahtar, "")).strip(), f"EN boş: {anahtar}"
    assert not TR_HARF.search(en[anahtar]), f"EN'de Türkçe harf: {anahtar}: {en[anahtar]!r}"
    assert _yer_tutucu(en[anahtar]) == _yer_tutucu(tr[anahtar]), f"yer tutucu kümesi ayrışmış: {anahtar}"


def test_her_anahtar_App_tsx_de_KULLANILIYOR_t_kaldirilirsa_KIRMIZI():
    kod = _kod()
    # başlıklar src/main.tsx'te kullanılır; geri kalan her anahtar App.tsx'te
    kullanilmayan = [k for k in ALTIN if not k.startswith("baslik.") and f"t('{k}'" not in kod]
    assert not kullanilmayan, f"katalogda var, App.tsx'te kullanılmıyor: {kullanilmayan}"


def test_App_tsx_de_gorunur_Turkce_dizgi_KALMADI_yalniz_dalga_formu_enum_VERISI():
    """Kodda (yorumsuz) Türkçe harf içeren dizgi yalnız dalga formu enum değerleridir ('Sinüs', 'Testere dişi')."""
    bulunan = set()
    for dizgi in re.findall(r"""(?<![\w])(?:'([^'\n]*)'|"([^"\n]*)")""", _kod()):
        for d in dizgi:
            if d and TR_HARF.search(d):
                bulunan.add(d)
    assert bulunan <= {"Sinüs", "Testere dişi"}, (
        f"kodda görünür Türkçe dizgi: {sorted(bulunan - {'Sinüs', 'Testere dişi'})}"
    )
    # JSX metin düğümlerinde (etiketler arası) Türkçe harf yok
    jsx = re.findall(r">([^<>{}\n]*[çğıöşüÇĞİÖŞÜ][^<>{}\n]*)<", _kod())
    assert not [j for j in jsx if j.strip()], f"JSX metninde Türkçe: {jsx}"


def test_dalga_formu_gorunen_adi_DEGER_ANAHTAR_eslemesi_ve_enum_degerleri_korunur():
    kod = _kod()
    m = re.search(r"function dalgaAdi\(w: Waveform\): string \{(.*?)\n\}", kod, re.S)
    assert m, "dalgaAdi işlevi yok"
    govde = m.group(1)
    for deger, anahtar in (("Sinüs", "dalga.sinus"), ("Kare", "dalga.kare"), ("Testere dişi", "dalga.testere")):
        assert f"t('{anahtar}')" in govde, anahtar
    # enum DEĞERLERİ veri olarak kalır: <option value> + tür
    for deger in ("Sinüs", "Kare", "Testere dişi"):
        assert f'<option value="{deger}">' in kod
    assert "type Waveform = 'Sinüs' | 'Kare' | 'Testere dişi'" in kod
    # TR görünen ad = değer (davranış aynı)
    tr = _tr()
    assert (tr["dalga.sinus"], tr["dalga.kare"], tr["dalga.testere"]) == ("Sinüs", "Kare", "Testere dişi")


def test_tanitim_egitim_etiketi_ve_saglik_uyarisi_iki_dilde_VAR():
    tr, en = _tr(), _en()
    assert "cihaz davranışını temsil etmez" in tr["ust.etiket"] and "cihaz davranışını temsil etmez" in tr["alt.uyari"]
    assert (
        "does not represent device behavior" in en["ust.etiket"]
        and "does not represent device behavior" in en["alt.uyari"]
    )
    assert "sağlık profesyoneline danışın" in tr["alt.uyari"] and "consult a health professional" in en["alt.uyari"]
    # A-37: etiket başlık + üst + alt metinde; uyumluluk iddiası YOK (İngilizcede de)
    for dil in (tr, en):
        for v in dil.values():
            assert not re.search(r"ISO\s*13485|uyumlu tek|only .*compliant|compliant device", v, re.I), v
