# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BIR BELGE KENDI KENDISIYLE CELISEMEZ — ozet tablosu ↔ bolum basligi (2026-09-17).

⚠️ BU KAPI GERCEK VE TEHLIKELI BIR CELISKIDEN DOGDU.

`docs/VERIFICATION.md` §9 (firmware `[FIX-1c]` duty gecisi) AYNI BELGEDE UC FARKLI SEY
soyluyordu:

    ozet tablosu   ->  "⏳ donanim — YAYIN ONCESI ZORUNLU"
    bolum basligi  ->  "✅ SAHIP TEYIDI 2026-08-20: reflash + tezgah sorunsuz"
    bolum govdesi  ->  "⚠️ BU DUZELTME TEZGAHTA OLCULMEDI"

Olculdu (git ile), basliktaki ✅ YANLISTI:
  · ✅'i ekleyen commit `bfbcf78`, AYNI cumleyi §9 · §11 · §12 · §13'e birden yazmis.
  · O commit'in mesaji: "FIRMWARE (S3 + 8266 REFLASH gerekir)" — saydigi uc madde de ESP.
    STM32 `[FIX-1c]` listede YOK.
  · AYNI commit'in ekledigi §14: "S3+8266 REFLASH — STM DEGISMEDI".
  · Govdedeki "olculmedi" uyarisi o commit'te HIC duzenlenmemis.
=> Sahibin 20 Agustos tezgah teyidi ESP icindi; STM32 maddesine kopyala-yapistir tasinmis.

⚠️ NEDEN BU YON DAHA TEHLIKELI: bayat bir "yapilacak" etiketi isi gereksiz yere acik tutar;
bayat bir "YAPILDI" etiketi ise doz guvenligiyle ilgili bir tezgah dogrulamasini YAPILMIS
SAYAR. §9, frekans ARTIRILDIGINDA duty tick'inin bayat kalip istenen dozun 4,78 katina kadar
on-time uretebilmesiyle ilgilidir.

SOZLESME
  Ozet tablosunda VE bolum basliginda birden gecen her madde icin, iki taraftaki durum
  isaretleri KESISMELI. Tablo "⏳" derken baslik yalniz "✅" diyemez (ya da tersi).
  Karma durum serbesttir: tablo "✅ … / ⏳ …" derken baslik "✅" olabilir — kesisim var.

⚠️ KAPI NE YAPMAZ: hangisinin DOGRU oldugunu bilmez. Yalnizca belgenin kendi kendisiyle
celismesini kirmizi yapar; hangi tarafin duzeltilecegine insan karar verir.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BELGE = KOK / "docs" / "VERIFICATION.md"

#: Belgede kullanilan durum isaretleri. D5.35 (B-10.230): ❌ da durumdur — eskiden tablo "❌ ACIK" derken baslik "✅" diyebiliyordu
#: (yalniz baslik isareti sayildigi icin kesisim BOS sayilmiyor, celiski gorunmuyordu).
ISARETLER = ("✅", "⏳", "⚠️", "⛔", "❌")
#: Durum hucresindeki / baslikta gecen tarih (YYYY-MM-DD).
_TARIH = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")

_TABLO = re.compile(r"^\|\s*(\d+[a-z]?)\s*\|")
_BASLIK = re.compile(r"^##\s+(.*?)\s*(\d+[a-z]?)\s+—")


def _isaretler(metin: str) -> set[str]:
    return {i for i in ISARETLER if i in metin}


def _tablo_durumlari(metin: str) -> dict[str, str]:
    """OZET tablosundaki madde -> DURUM SUTUNU (3. hucre) metni.

    ⚠️ YALNIZ ILK `##` BASLIGINDAN ONCESI taranir. Ilk yazimda TUM belgeyi tariyordum ve
    §2a'daki "kurtarma seti" tablosunun `| 2 | ~/pemf-vault-kurtarma.json | ...` satiri
    ozet tablosunun 2. maddesi saniliyordu (o an `setdefault` sayesinde zarar vermedi —
    yani kapi DOGRU sonucu YANLIS sebeple veriyordu). Ozet tablosu belgenin en ustundedir.
    """
    out: dict[str, str] = {}
    for satir in metin.splitlines():
        if satir.startswith("## "):
            break  # ozet tablosu bitti; asagisi bolum govdeleri
        m = _TABLO.match(satir)
        if not m:
            continue
        hucre = satir.split("|")
        if len(hucre) < 4:
            continue
        # ⚠️ YALNIZ 3. hucre: "Nasil" sutununda da isaret gecebilir, o karari temsil etmez.
        out.setdefault(m.group(1), hucre[3])
    return out


def _baslik_durumlari(metin: str) -> dict[str, str]:
    """`## <isaret> <no> — ...` bicimindeki bolum basliklari."""
    out: dict[str, str] = {}
    for satir in metin.splitlines():
        m = _BASLIK.match(satir)
        if m and _isaretler(m.group(1)):
            out.setdefault(m.group(2), satir)
    return out


def test_KRITIK_ozet_tablosu_ile_bolum_basligi_CELISMIYOR():
    """⚠️ Kapinin dogdugu vaka: §9 tabloda ⏳, baslikta ✅ idi (doz guvenligi maddesi)."""
    metin = BELGE.read_text(encoding="utf-8")
    tablo, basliklar = _tablo_durumlari(metin), _baslik_durumlari(metin)
    ortak = sorted(set(tablo) & set(basliklar), key=lambda s: (int(re.sub(r"\D", "", s) or 0), s))
    assert ortak, "ozet tablosu ile bolum basliklari HIC eslesmiyor — kapi korlesmis olabilir"

    celiskiler = []
    for no in ortak:
        t, b = _isaretler(tablo[no]), _isaretler(basliklar[no])
        if t and b and not (t & b):
            celiskiler.append(f"§{no}: tablo={sorted(t)} baslik={sorted(b)}")
    assert not celiskiler, (
        "VERIFICATION.md KENDI KENDISIYLE CELISIYOR:\n  "
        + "\n  ".join(celiskiler)
        + "\n\nHangisinin dogru oldugunu bu kapi bilmez — OLCUN, sonra iki tarafi da duzeltin. "
        "§9'da bu celiski, yapilmamis bir DOZ tezgah dogrulamasini 'yapilmis' gosteriyordu."
    )


def _tarih_celiskileri(metin: str) -> list[str]:
    """D5.35 (B-10.189 kapi onerisi): ozet tablosunun DURUM hucresi ve bolum basligi ikisi de tarih tasiyorsa EN SON tarihleri ayni
    olmali — tablo "son 2026-09-20" derken baslik "2026-09-17" diyorsa biri bayattir (hangisi oldugunu kapi bilmez)."""
    tablo, basliklar = _tablo_durumlari(metin), _baslik_durumlari(metin)
    out = []
    for no in sorted(set(tablo) & set(basliklar)):
        t, b = _TARIH.findall(tablo[no]), _TARIH.findall(basliklar[no])
        if t and b and max(t) != max(b):
            out.append(f"§{no}: tablo son tarih {max(t)} ≠ baslik son tarih {max(b)}")
    return out


#: ⚠️ SAYAÇLI, BİLİNEN çelişki — D5.35 kapısı ilk koşuda §17'yi buldu (B-10.189: tablo "son: 2026-09-20", başlık "2026-09-17").
#: Belgeyi düzeltmek D6.72'nin işidir (hangi tarafın doğru olduğunu ölçüm söyler, bu kapı değil). Muafiyet TAM metniyle pinlidir:
#: yeni bir çelişki eklenirse ya da bu çözülünce (muafiyet bayatlar) kapı KIRMIZI — D6.72 bu girdiyi SİLER.
BILINEN_TARIH_CELISKILERI = {"§17: tablo son tarih 2026-09-20 ≠ baslik son tarih 2026-09-17": "D6.72 · B-10.189"}


def test_KRITIK_D5_35_ozet_tablosu_ile_bolum_basligi_TARIHTE_celismiyor():
    celiski = _tarih_celiskileri(BELGE.read_text(encoding="utf-8"))
    yeni = [c for c in celiski if c not in BILINEN_TARIH_CELISKILERI]
    assert not yeni, "VERIFICATION.md tarihte KENDI KENDISIYLE CELISIYOR:\n  " + "\n  ".join(yeni)
    bayat = sorted(set(BILINEN_TARIH_CELISKILERI) - set(celiski))
    assert not bayat, f"bilinen tarih celiskisi COZULMUS — muafiyeti SILIN (kapi sessizce genislemesin): {bayat}"
    assert len(BILINEN_TARIH_CELISKILERI) <= 1, (
        "bilinen celiski listesi sismis — yeni celiski belgede duzeltilir, buraya yazilmaz"
    )


def test_KARSIT_KANIT_D5_35_carpi_ve_tarih_celiskisi_GORULUR():
    sahte = "| 2a | k | ❌ ACIK | n |\n\n## ✅ 2a — k\n"
    t, b = _isaretler(_tablo_durumlari(sahte)["2a"]), _isaretler(_baslik_durumlari(sahte)["2a"])
    assert t and b and not (t & b), "❌ durum sayilmiyor — tablo ❌ / baslik ✅ celiskisi gorunmez"
    tarihli = "| 7 | k | ✅ son 2026-09-20 | n |\n\n## ✅ 7 — k (2026-09-17)\n"
    assert _tarih_celiskileri(tarihli) == ["§7: tablo son tarih 2026-09-20 ≠ baslik son tarih 2026-09-17"]
    ayni = "| 7 | k | ✅ son 2026-09-17 | n |\n\n## ✅ 7 — k (2026-09-17)\n"
    assert _tarih_celiskileri(ayni) == [], "ayni tarih celiski sayildi"


def test_KRITIK_9_TEZGAH_dogrulamasi_YAPILMADI_isaretli():
    """⚠️ §9 yeniden '✅' yapilirsa bu kapi KIRMIZI doner.

    Geri acilmasi icin sart: GERCEK tezgah olcumu — ve §16 reflash'indan SONRAKI firmware
    uzerinde (STM surus dalgasi `356d576` ile simetrik bipolara cevrildi; eski bir olcum
    gecersizdir). O zaman bu testi bilincli olarak guncelleyin.
    """
    metin = BELGE.read_text(encoding="utf-8")
    baslik = _baslik_durumlari(metin).get("9", "")
    assert baslik, "§9 bolum basligi bulunamadi — belge yapisi degismis, kapi guncellenmeli"
    assert "✅" not in _isaretler(baslik), (
        f"§9 basligi '✅' diyor: {baslik!r}. Gercekten tezgahta olculduyse bu testi guncelleyin; "
        "aksi halde YAPILMAMIS bir doz dogrulamasi yapilmis gorunur (2026-09-17'de tam bu oldu)."
    )


def test_KARSIT_KANIT_kapi_CELISKIYI_gercekten_goruyor():
    """Kapi 'hic celiski bulamayan' bir no-op olmamali — uydurma celiski KIRMIZI olmali."""
    sahte = "| 9 | konu | ✅ yapildi | nasil |\n\n## ⏳ 9 — konu\n"
    tablo, basliklar = _tablo_durumlari(sahte), _baslik_durumlari(sahte)
    t, b = _isaretler(tablo["9"]), _isaretler(basliklar["9"])
    assert t and b and not (t & b), "kapinin celiski tespiti CALISMIYOR — ayristirma bozulmus olabilir"


def test_KARSIT_KANIT_karma_durum_YANLIS_ALARM_vermiyor():
    """Tablo '✅ … / ⏳ …' derken baslik '✅' ise celiski YOKTUR (kesisim var)."""
    sahte = "| 5 | konu | ✅ ucu YAPILDI / ⏳ onnx | nasil |\n\n## ⏳ 5 — konu\n"
    tablo, basliklar = _tablo_durumlari(sahte), _baslik_durumlari(sahte)
    t, b = _isaretler(tablo["5"]), _isaretler(basliklar["5"])
    assert t & b, "karma durum yanlis alarm uretiyor — kapi fazla siki"
