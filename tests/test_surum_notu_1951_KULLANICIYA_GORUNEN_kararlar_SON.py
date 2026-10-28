# -*- coding: utf-8 -*-
"""SON-A3.52 · Sahaya 1.9.50 → 1.9.51 ile giden KULLANICIYA GÖRÜNEN davranış değişiklikleri (sahip kararları) sürümün değişiklik kaydında yazılı.

ÖLÇÜLEN (HEAD `8b002fc0`, 22-SON A3b): zincirde `CHANGELOG.md`'ye TEK commit girdi (YH D1 `b9bac7e6`, +39 satır: dil seçeneği, PDF "Seans",
launcher 1.9.52). 1.9.50 (`9749d5d1`) → aday aralığında commit'le doğrulanan kullanıcıya görünen kararların HİÇBİRİ aday notlarda yok
(`_inceleme/A3b/notlar_kapsami.py`): Y4 ACİL DURDUR mandalı / "Sıfırla" (`c5b3c04f`), Y152 geçmiş ölçülen mT ÷5 (`2f1ccb84`), Y154 akım
gösterilmez / kaydedilmez (`f4f07422`), Y189 Koşullu | Koşulsuz (`ec1beabf`), Y190 "Fotoğraf Çek" kabin kamerası (`4c743afc`), Y191b kuyu
skoru eşiği 0,6 (`85acab5e`), Y193 yalnız 24 kuyucuklu plaka (`e39a3842`), Y200 eski veri klasörü taşınamazsa boş veritabanı kurulmaz
(`ab301815`; D67 §5 SONRAKİ "Y200 CHANGELOG satırı" — uygulanmadı). CHANGELOG'un kendi gerekçesi: sessiz güncellemede "bir davranış
değiştiğinde veteriner bunu arıza sanar" (ACİL DURDUR sonrası başlatmanın kapalı kalması, eski seans mT değerlerinin beşte bire inmesi,
akım değerinin kaybolması tam bu sınıf). Y191 (YOLO güveni 0,25 → 0,6) listede YOK: plaka kipinde sonuç 12/12 karede aynı ölçüldü
(`468d0d43`) ve tekil kip arayüzden kalktı (Y193) — kullanıcıya görünen etkisi yok.

KAPI: `## app 1.9.51` bölümü (sabit sürüm — bu kararlar sahaya İLK bu sürümle çıkar; yayınlanınca başlık tarihe döner, not kalır; HTML
yorumu okura görünmez → düşülür) her kararı kendi ölçütüyle anar. Ölçütler kararın kullanıcıya görünen ÇEKİRDEĞİNİ arar (ör. Y152'de "÷5"
ve "orijinal saklanır"), yalnız anahtar sözcüğü değil.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
CHANGELOG = KOK / "CHANGELOG.md"
SURUM = "1.9.51"
_BASLIK = re.compile(r"^##[^\n—]*\bapp\s+" + re.escape(SURUM) + r"\b")

#: karar → [her biri ZORUNLU desen] (cümle içi; boşluklar tek boşluğa indirilmiş metinde)
KARARLAR: dict[str, list[str]] = {
    "Y4_ACIL_DURDUR_mandali_Sifirla": [r"ACİL DURDUR[^.]{0,60}mandal", r"\"?Sıfırla\"?[^.]{0,80}başlatmaz"],
    "Y152_gecmis_mT_bolu5_orijinal_sakli": [r"÷\s*5|5'e bölün", r"orijinal[^.]{0,40}saklanır"],
    "Y154_akim_gosterilmez_kaydedilmez": [r"akım[^.]{0,60}gösterilmiyor[^.]{0,20}kaydedilmiyor"],
    "Y189_Kosullu_Kosulsuz": [r"Koşullu \| Koşulsuz|Koşullu / Koşulsuz", r"Koşulsuz[^.]{0,200}doğrulanmamış"],
    "Y190_Fotograf_Cek_kabin_kamerasi": [r"Fotoğraf Çek[^.]{0,120}kabin kamera"],
    "Y191b_kuyu_skoru_esigi_0_6": [r"kuyu skoru eşiği[^.]{0,80}0,6"],
    "Y193_yalniz_24_kuyucuklu_plaka": [r"yalnız 24 kuyucuklu plaka", r"Tekil petri kapları[^.]{0,80}kaldırıldı"],
    "Y200_eski_veri_klasoru_bos_DB_kurulmaz": [
        r"[Ee]ski veri klasör",
        r"boş (bir )?veritabanı kurulmaz",
        r"SİLMEYİN|silmeyin",
    ],
}


def _bolum(metin: str) -> str:
    metin = re.sub(r"<!--.*?-->", "", metin, flags=re.S)
    parcalar = re.split(r"^(## [^\n]*)\n", metin, flags=re.M)
    bolumler = [parcalar[i + 1] for i in range(1, len(parcalar) - 1, 2) if _BASLIK.search(parcalar[i])]
    assert len(bolumler) == 1, f"CHANGELOG'da '## app {SURUM}' bölümü tek değil: {len(bolumler)}"
    return re.sub(r"\s+", " ", bolumler[0].replace("**", ""))


def eksikler(bolum: str) -> dict[str, list[str]]:
    return {
        k: [d for d in desenler if not re.search(d, bolum)]
        for k, desenler in KARARLAR.items()
        if any(not re.search(d, bolum) for d in desenler)
    }


@pytest.mark.parametrize("karar", sorted(KARARLAR))
def test_KRITIK_1951_degisiklik_kaydi_karari_ANAR(karar):
    """MUTASYON: bir kararın paragrafı silinir / HTML yorumuna alınır / çekirdeği (÷5, 'başlatmaz', 0,6) değişirse o karar KIRMIZI."""
    bolum = _bolum(CHANGELOG.read_text(encoding="utf-8"))
    eksik = [d for d in KARARLAR[karar] if not re.search(d, bolum)]
    assert not eksik, (
        f"CHANGELOG app {SURUM}: {karar} kullanıcıya görünen değişikliği yazılı değil (eksik ölçüt: {eksik}) — sessiz güncelleme "
        "veterinere arıza gibi görünür"
    )


def test_KARSIT_olcutler_sentetik_bolumde_ayirt_eder():
    tam = (
        "ACİL DURDUR artık mandallı. Yeniden başlatmak için önce \"Sıfırla\" gerekir; sıfırlama bobinleri başlatmaz. "
        "Eski değerler 5'e bölünür; orijinal değer saklanır. Bobin akımı artık gösterilmiyor ve kaydedilmiyor. "
        "Koşullu | Koşulsuz seçimi: Koşulsuz sonuç \"KOŞULSUZ — doğrulanmamış\" uyarısı taşır. "
        "\"Fotoğraf Çek\" bilgisayar uygulamasında kabin kamerasını kullanır. Plaka ızgarasında kuyu skoru eşiği (varsayılan 0,6). "
        "Petri analizi yalnız 24 kuyucuklu plaka ile çalışır; \"Tekil petri kapları\" kipi arayüzden kaldırıldı. "
        "Eski veri klasöründen taşıma tamamlanamazsa boş veritabanı kurulmaz. Eski dosyayı SİLMEYİN."
    )
    assert eksikler(tam) == {}, eksikler(tam)
    assert set(eksikler(tam.replace("5'e bölünür", "düzeltilir"))) == {"Y152_gecmis_mT_bolu5_orijinal_sakli"}
    assert set(eksikler(tam.replace("başlatmaz", "başlatır"))) == {"Y4_ACIL_DURDUR_mandali_Sifirla"}
    assert set(eksikler("")) == set(KARARLAR)
    ch = f"## launcher 9.9.9 — YAYIN ADAYI (app {SURUM} ile birlikte)\n\n{tam}\n\n## app {SURUM} — YAYINLANMADI\n\n<!-- {tam} -->\n"
    assert set(eksikler(_bolum(ch))) == set(KARARLAR), "launcher başlığı app bölümü sayıldı ya da HTML yorumu okundu"
