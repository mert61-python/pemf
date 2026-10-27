# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN İŞARETİ DOKÜMAN TUTARLILIĞI (Faz 4, 2026-09-09).

ÖLÇÜLEN SAPMA: `phantom_cv/README.md` ve `petri_cv/README.md` kullanıcıya **DICT_5X5_100** sözlüğünü
ve **5 cm** kenar bas diyordu; basılı sayfa `PEMF_ArUco_Marker_5X5_50_ID0_10cm_A4.pdf`
(DICT_5X5_50 · 10,0 cm) ve üç kabin yaml'ı da `dict: DICT_5X5_50` + `real_cm: 10.0` okuyor.

NEDEN KAPI (iki ayrı sessiz arıza):
  · YANLIŞ SÖZLÜK → işaret HİÇ tespit edilmez; yöntem `aruco_pnp` olmaz, araştırma AI Pro hedefi
    reddeder ve kullanıcı işareti asmış olduğu hâlde "kabin işareti görünmüyor" okur.
  · DOĞRU sözlük + YANLIŞ KENAR (5 cm yerine 10 cm) → tespit ÇALIŞIR, ölçek 2 kat yanlış olur ve
    3B koordinat sessizce iki katına çıkar. Hiçbir ekran hata göstermez; bobinler yanlış noktaya
    odaklanır. Bu, "ölçüm doğru görünüyor ama yanlış" sınıfının tam örneğidir.

⚠️ Kapı DOKÜMANI koda pinler: yaml'daki değer değişirse (ör. daha büyük bir sayfaya geçilirse)
dokümanların da değişmesi ZORUNLU olur.
"""

import pathlib
import re

import capraz
import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_AI_HUB = _KOK / "ai_hub"


def _basili_sayfalar() -> "list[pathlib.Path]":
    """Depodaki basılabilir kabin işareti sayfaları (ad sözlüğü ve kenarı taşır).

    ⚠️ PNG'ye bakılır, PDF'e DEĞİL: `.gitignore` `*.pdf`i dışlıyor → temiz bir checkout'ta (ve
    CI'da) PDF YOKTUR. PDF'i arayan bir kapı sahte-kırmızı yanardı; sayfayı üreten betik ikisini
    birlikte yazar, izlenen kopya PNG'dir."""
    return sorted(_AI_HUB.glob("PEMF_ArUco_Marker_*_A4.png"))


#: Kabin yaml'ları — hepsi AYNI işareti okumak zorunda (tek kabin, tek işaret).
_YAMLLAR = (
    "inference_cat_organ/cabin_config_example.yaml",
    # AI-2 C6: v1 `phantom_cv` / `petri_cv` emekli → hocanın v3 / v2 profil YAML'ları.
    "inference_em_fantom/phantom_cv_v3/cabin_config_v3.yaml",
    "inference_petri_dish/petri_cv_v2/cabin_config_v2.yaml",
)

#: Kullanıcıyı işaret basmaya yönlendiren dokümanlar. AI-2 C6: v1 paket README'leri (`phantom_cv/`, `petri_cv/`) paketle
#: birlikte emekli — hocanın v2 / v3'ü README getirmedi; kurulum yönergesi TEK yerde: kabin kılavuzu.
_DOKUMANLAR = ("KABIN_KURULUM_KILAVUZU.md",)


@pytest.fixture(autouse=True)
def _ai_hub_kaynagi():
    """D5-L (L-2): `ai_hub/` İZLENEN ağaçtır — yoksa atla, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞ (F-P1 / D4.04 deseni).

    Eskiden modül düzeyi düz `skipif(not ….exists())` idi: zorunlu kipte de sessizce ATLIYORDU. Dosyadaki HER test ilk kabin
    yaml'ını okur; varlık hedefi eski koşulla AYNI."""
    capraz.atla_yoksa(f"ai_hub/{_YAMLLAR[0]}", izlenen=True)


#: Sayfa üreteci — kenar TEK sabitten gelir ve yaml ile aynı olmalı.
_URETEC = _KOK / "scripts" / "kabin_marker_a4.py"


def _yaml_isaret(gorece: str) -> "tuple[str, float]":
    src = (_AI_HUB / gorece).read_text(encoding="utf-8")
    d = re.search(r"^\s*dict:\s*(\S+)", src, re.M)
    r = re.search(r"^\s*real_cm:\s*([\d.]+)", src, re.M)
    assert d and r, f"{gorece}: aruco.dict / aruco.real_cm okunamadı"
    return d.group(1), float(r.group(1))


def test_KRITIK_TEK_basili_sayfa_var():
    """⚠️ TEK sayfa: iki farklı boyutta sayfa dururken yanlışını basmak SESSİZ ölçek hatasıdır.

    Dokümanların yönlendirdiği sayfa gerçekten depoda olmalı (ölü yönlendirme yok) ve BAŞKA
    boyutta bir sayfa YANINDA DURMAMALI (2026-09-09'da 10 cm sayfası 15 cm'e geçilirken silindi)."""
    sayfalar = _basili_sayfalar()
    assert len(sayfalar) == 1, f"basılı işaret sayfası tekil değil: {[p.name for p in sayfalar]}"


def test_KRITIK_UC_kabin_yamli_AYNI_isareti_okur():
    """Tek kabin, tek işaret: modüller ayrışırsa biri işareti hiç bulamaz."""
    okunan = {y: _yaml_isaret(y) for y in _YAMLLAR}
    tekil = set(okunan.values())
    assert len(tekil) == 1, f"kabin yaml'ları farklı işaret okuyor: {okunan}"
    sozluk, kenar = tekil.pop()
    # Basılı sayfanın ADI sözlüğü ve kenarı taşır; yaml ile UYUŞMAK ZORUNDA.
    basili = _basili_sayfalar()[0].name
    assert sozluk.replace("DICT_", "") in basili, f"yaml sözlüğü ({sozluk}) basılı sayfayla uyuşmuyor: {basili}"
    assert f"{kenar:g}cm" in basili, f"yaml kenar uzunluğu ({kenar} cm) basılı sayfayla uyuşmuyor: {basili}"


def test_KRITIK_DOKUMANLAR_yanlis_SOZLUK_onermez():
    """MUTASYON: bir README'ye `DICT_5X5_100` yazın → KIRMIZI (işaret hiç tespit edilmez)."""
    sozluk, _ = _yaml_isaret(_YAMLLAR[0])
    for gorece in _DOKUMANLAR:
        yol = _AI_HUB / gorece
        if not yol.exists():
            continue
        src = yol.read_text(encoding="utf-8")
        yanlis = {m for m in re.findall(r"DICT_\w+", src) if m != sozluk}
        assert not yanlis, f"{gorece} yanlış ArUco sözlüğü öneriyor: {sorted(yanlis)} (doğrusu {sozluk})"


#: D5.39 (B-10.248): BASIM TALİMATI kalıpları — bugünkü kılavuz biçimleri. Eski tek kalıp (`N cm × N cm yazdır` / `N cm kenar`) v1
#: README'lerle birlikte emekli oldu; kılavuzun `**10×10 cm**`, `kenar = 10.0 cm`, `tam 10×10 cm` satırlarının HİÇBİRİNİ görmüyordu
#: (eşleşme 0 → kenar 5'e indirilse de YEŞİL). Sayılar `(×|x)` iki kenarı ya da tek kenarı verir.
_KARE_KALIBI = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:cm)?\s*(?:×|x)\s*(\d+(?:[.,]\d+)?)\s*cm")
_KENAR_KALIPLARI = (
    re.compile(r"kenar[ıi]?\s*(?:=|:)\s*\**\s*(\d+(?:[.,]\d+)?)\s*cm", re.I),
    re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*cm\s*kenar", re.I),
)
#: `N×N cm` YALNIZ işareti anan ya da basım fiili taşıyan satırda talimattır — "Kesik çizgiden kes (14×14 cm)" sessiz bölgeli
#: KESİM ölçüsüdür, kabin ölçüleri (`55,5 × 35 × 40,5 cm`) işaret değildir.
_ISARET_BAGLAMI = re.compile(r"marker|[İIi]şaret|İŞARET|aruco|yazdır|\bbas\b", re.I)
#: Kesim ölçüsü (işaret + sessiz bölge, ör. "Kesik çizgiden kes (14×14 cm)") işaret kenarı DEĞİLDİR.
_KESIM = re.compile(r"\bkes\b|kesik", re.I)
#: Kılavuzda ölçülen tarihçe bölümleri (eski düzeneğin 15 cm işaretiyle ölçümleri) — basım talimatı DEĞİL.
_TARIHCE = "TARİHÇE"


def _kenar_talimatlari(metin: str) -> "list[tuple[str, list[float]]]":
    """[(satır, [cm sayıları])] — `## ` bölümünün ilk satırlarında "TARİHÇE" yazan bölümler atlanır."""
    sonuc, tarihce = [], False
    satirlar = metin.splitlines()
    for i, satir in enumerate(satirlar):
        if satir.startswith("## "):
            tarihce = any(_TARIHCE in s for s in satirlar[i : i + 4])
        if tarihce:
            continue
        kare = _ISARET_BAGLAMI.search(satir) and not _KESIM.search(satir)
        kaliplar = _KENAR_KALIPLARI + ((_KARE_KALIBI,) if kare else ())
        for kalip in kaliplar:
            for m in kalip.finditer(satir):
                sonuc.append((satir.strip(), [float(g.replace(",", ".")) for g in m.groups() if g]))
    return sonuc


def test_KRITIK_DOKUMANLAR_yanlis_KENAR_uzunlugu_onermez():
    """Doğru sözlük + yanlış kenar = SESSİZ ölçek hatası (3B koordinat kat kat yanlış).

    MUTASYON: kılavuzda `kenar = 10.0 cm` / `**10×10 cm**` / `tam 10×10 cm` satırlarından birini 5'e indirin → KIRMIZI.
    ⚠️ D5.39: talimat hiç bulunamazsa (vakum) da KIRMIZI — kalıp bayatlarsa kapı sessizce geçmesin."""
    _, kenar = _yaml_isaret(_YAMLLAR[0])
    bulunan = 0
    for gorece in _DOKUMANLAR:
        yol = _AI_HUB / gorece
        assert yol.exists(), f"kurulum dokümanı YOK: {gorece}"
        for satir, sayilar in _kenar_talimatlari(yol.read_text(encoding="utf-8")):
            bulunan += 1
            assert all(abs(s - kenar) < 0.01 for s in sayilar), (
                f"{gorece} işareti {sayilar} cm basmayı söylüyor, kabin {kenar} cm okuyor "
                f"→ ölçek {max(sayilar) / kenar:.1f}× yanlış olurdu: {satir[:90]}"
            )
    assert bulunan >= 2, (
        f"VAKUM: dokümanlarda yalnız {bulunan} kenar talimatı bulundu — kalıp bugünkü biçimi görmüyor olabilir"
    )


def test_KAPI_gercekten_olcuyor():
    """MUTASYON ÖZ-TESTİ: tarayıcı yanlış kenar talimatını sentetik metinde görüyor mu (bugünkü ve eski biçimler)?"""
    _, kenar = _yaml_isaret(_YAMLLAR[0])
    for metin in (
        "5 cm × 5 cm yazdır, kabinin sol duvarına yapıştır.",
        "| **Marker** | DICT_5X5_50 · ID 0 · **5×5 cm** (cetvel) |",
        "`DICT_5X5_50`, ID `0`, **kenar = 5.0 cm** (saha ölçüsü)",
        "> ⚠️ Marker'ı **tam 5×5 cm** bas",
    ):
        talimat = _kenar_talimatlari(metin)
        assert talimat, f"tarayıcı basım talimatını görmüyor: {metin}"
        assert not all(abs(s - kenar) < 0.01 for _, sayilar in talimat for s in sayilar), (
            f"yanlış kenar doğru sayıldı: {metin}"
        )
    # TARİHÇE bölümündeki eski ölçüm talimat sayılmaz; tarihçeden çıkınca yine taranır.
    tarihce = "## 0.5) ESKİ\n> ℹ️ Bu bölüm eski düzeneğin ölçümleridir (TARİHÇE).\nişaret kenarı = 15 cm\n## 1) GÜNCEL\nkenar = 15 cm\n"
    assert [s for _, s in _kenar_talimatlari(tarihce)] == [[15.0]], _kenar_talimatlari(tarihce)


def test_KRITIK_SAYFA_URETECI_yaml_ile_AYNI_kenari_uretir():
    """Sayfa elle değil betikle üretilir; betiğin kenarı yaml'dan AYRIŞIRSA bir sonraki baskı
    sessizce yanlış ölçekte çıkar. MUTASYON: `KENAR_CM`i 10.0 yapın → KIRMIZI."""
    _, kenar = _yaml_isaret(_YAMLLAR[0])
    src = _URETEC.read_text(encoding="utf-8")
    m = re.search(r"^KENAR_CM\s*=\s*([\d.]+)", src, re.M)
    assert m, "kabin_marker_a4.py içinde KENAR_CM bulunamadı"
    assert abs(float(m.group(1)) - kenar) < 0.01, (
        f"sayfa üreteci {m.group(1)} cm basıyor, kabin yaml'ı {kenar} cm okuyor — "
        "bir sonraki baskı yanlış ölçekte çıkar"
    )
