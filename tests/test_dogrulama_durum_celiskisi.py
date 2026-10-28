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


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════
# D6.39 (B-11.10 · B-11.22) — sahip kararıyla KAPATILAN işler (Ö.4-Y3 onnx/torch yükseltmesi · Ö.4-Y4 AI model lisans envanteri ·
# Ö.4-Y5 doz kalibrasyonu) belgede AÇIK iş gibi durmaz; STM uzaktan güncelleme planının başlığı faz tablosuyla ve kodla aynı.
# ÖLÇÜLEN (HEAD ebf1c3fe): `acik-isler:162` "B4 §5 onnx + torch yükseltmesi" (Hâlâ açık tablosu), `:230` "A-2 Model lisans envanteri …
# çıkarılabilir"; VERIFICATION `:14` "⏳ onnx+torch", `:90` "onnx/torch maintainer'da", `:122` "lisansı … envanter çıkar";
# `firmware/README` "tezgahta doz yeniden kalibre edilmeli"; `stm32-uzaktan-guncelleme-plani.md:3` "Faz 3-4 hâlâ plan" ↔ aynı belgenin
# faz tablosu "Faz 3 ✅ BİTTİ"; `docs/README.md:32` "Faz 3-4 açık"; Faz 3 açılış denetimi `backend_service.py` — varsayılan KAPALI (Y1).
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════

import ast as _ast

_KAPANAN_BELGELER = ("docs/acik-isler-2026-09-12.md", "docs/VERIFICATION.md", "firmware/README.md")
_KAPANAN_KONULAR = {
    "onnx/torch yükseltmesi (Ö.4-Y3)": re.compile(
        r"(onnx|torch)[^\n]*(⏳|yükselt|upgrade|maintainer)|(⏳|yükselt|upgrade)[^\n]{0,40}(onnx|torch)", re.I
    ),
    "AI model lisans envanteri (Ö.4-Y4)": re.compile(r"lisans\w*\**[^\n]{0,80}envanter", re.I),
    "doz kalibrasyonu (Ö.4-Y5)": re.compile(r"doz\w*\s+(yeniden\s+)?kalibr|kalibre\s+edilmeli", re.I),
}
_KAPALI_ISARET = ("⛔", "YAPILMAYACAK", "KALDIRILDI", "KAPANDI")


def _cizgisiz(md: str) -> str:
    return re.sub(r"~~.*?~~", " ", md, flags=re.S)


def test_KRITIK_D6_39_kapanan_isler_ACIK_is_gibi_durmaz():
    ihlal = []
    for yol in _KAPANAN_BELGELER:
        for no, satir in enumerate(_cizgisiz((KOK / yol).read_text(encoding="utf-8")).splitlines(), 1):
            for konu, desen in _KAPANAN_KONULAR.items():
                if desen.search(satir) and not any(i in satir for i in _KAPALI_ISARET):
                    ihlal.append(f"{yol}:{no} [{konu}] {satir.strip()[:110]}")
    assert not ihlal, (
        "sahip kararıyla KAPATILAN iş belgede açık / yapılabilir gibi duruyor — ⛔ YAPILMAYACAK işaretleyin ya da üstünü çizin "
        "(SİLMEYİN, tarih kaydı):\n  " + "\n  ".join(ihlal)
    )


def _fw_oto_varsayilan() -> str:
    """`backend_service.py`deki `PEMF_FW_AUTO_UPDATE` varsayılanı — AST'den (sabit kopya DEĞİL; Y1 değişirse belge de değişmeli)."""
    agac = _ast.parse((KOK / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8"))
    degerler = {
        d.args[1].value
        for d in _ast.walk(agac)
        if isinstance(d, _ast.Call)
        and len(d.args) == 2
        and isinstance(d.args[0], _ast.Constant)
        and d.args[0].value == "PEMF_FW_AUTO_UPDATE"
        and isinstance(d.args[1], _ast.Constant)
    }
    assert len(degerler) == 1, f"PEMF_FW_AUTO_UPDATE varsayılanı tek olmalı: {degerler}"
    return degerler.pop()


def test_KRITIK_D6_39_stm_guncelleme_plani_basligi_FAZ_tablosuyla_ve_KODLA_ayni():
    plan = (KOK / "docs" / "stm32-uzaktan-guncelleme-plani.md").read_text(encoding="utf-8")
    biten = sorted(set(re.findall(r"^\|\s*~~\*\*(\d)\*\*~~\s*\|\s*✅\s*\*\*BİTTİ", plan, re.M)))
    assert "3" in biten, f"aparat: faz tablosu Faz 3'ü BİTTİ göstermeli (bulunan: {biten})"
    baslik = plan.split("\n\n", 2)[1]  # başlıktan sonraki ilk paragraf = **Tarih:** · **Durum:**
    assert "**Durum:**" in baslik, "aparat: durum paragrafı bulunamadı"
    for n in biten:
        assert not re.search(r"Faz [\d\s,–-]*" + n + r"[\d\s,–-]*\s+hâlâ plan", _cizgisiz(baslik)), (
            f"plan başlığı Faz {n}'i 'hâlâ plan' diyor ama faz tablosu ✅ BİTTİ diyor"
        )
    v = _fw_oto_varsayilan()
    assert f'varsayılanı `"{v}"`' in baslik, (
        f"plan başlığı otomatik yakma varsayılanını koddan farklı / hiç söylemiyor (kod: \"{v}\")"
    )
    satir = [
        s
        for s in (KOK / "docs" / "README.md").read_text(encoding="utf-8").splitlines()
        if "stm32-uzaktan-guncelleme-plani.md" in s
    ]
    assert len(satir) == 1 and not re.search(r"Faz 3-4 açık", satir[0]), f"docs/README dizin satırı bayat: {satir}"
    assert f'varsayılanı `"{v}"`' in satir[0], (
        "docs/README dizin satırı otomatik yakma varsayılanını koddan farklı söylüyor"
    )


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════
# D6.48 (B-10.61 · B-10.62) — VERIFICATION gövdesi §9'u "koşuldu / teyit" diye anmaz; §9 klemp formülü FIRMWARE KAYNAĞIYLA aynı.
# ÖLÇÜLEN (HEAD ebf1c3fe): §14 "**Bağlam:** §9-13 tezgâhı 2026-08-20'de sahip tarafından koşuldu (sorunsuz)" (bfbcf78 kalıntısı —
# başlık kapısı gövdeyi görmüyordu); §9 "`g_tpp - 1 - DDS_DEAD_TIME_TICKS` ile klempliyor" ve Ölçüm 3 "klemp `g_tpp - 1`'e dayanıyor"
# ↔ `main.c` `[FIX-1c]` `max_d_now = g_unipolar[i] ? (g_tpp[i] - 1) : ((g_tpp[i] / 2U) - DDS_BIPOLAR_GAP_TICKS)` (HG-2);
# §9 "§16 reflash'ı ile aynı tezgâh oturumunda" ↔ §16 = DOZ KALİBRASYONU KALDIRILDI (Ö.4-Y5 — geri EKLENMEZ).
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════

_MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
_S9_YAPILDI = re.compile(r"§\s*9(?:\s*[-–]\s*\d+)?\b[^\n]{0,80}(koşuldu|teyit|DOĞRULANDI|sorunsuz)", re.I)


def _bolum(metin: str, baslik_basi: str) -> str:
    bas = metin.index(baslik_basi)
    son = metin.find("\n## ", bas + 5)
    return metin[bas : son if son > 0 else len(metin)]


def _bosluksuz(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _fix1c_bipolar_klempi() -> str:
    import sys as _sys

    _sys.path.insert(0, str(KOK / "tests"))
    from c_soyucu import c_soy

    kod = c_soy(_MAIN_C.read_text(encoding="utf-8"))
    m = re.search(r"max_d_now\s*=\s*g_unipolar\[i\]\s*\?\s*(\(.*?\))\s*:\s*(\(.*?\));", kod, re.S)
    assert m, "aparat: main.c [FIX-1c] max_d_now klempi bulunamadı"
    return m.group(2)


def test_KRITIK_D6_48_govde_9u_KOSULDU_diye_ANMAZ():
    metin = _cizgisiz(BELGE.read_text(encoding="utf-8"))
    govde = [s for s in metin.splitlines() if not s.startswith("## ")]
    ihlal = [s.strip()[:120] for s in govde if _S9_YAPILDI.search(s) and not re.search(r"ÖLÇÜLMEDİ|YANLIŞ", s)]
    assert not ihlal, "VERIFICATION gövdesi §9 (STM [FIX-1c]) tezgâhını yapılmış gösteriyor:\n  " + "\n  ".join(ihlal)


def test_KRITIK_D6_48_bolum9_klemp_formulu_FIRMWARE_ile_ayni():
    b9 = _cizgisiz(_bolum(BELGE.read_text(encoding="utf-8"), "## ⏳ 9 — "))
    bipolar = _fix1c_bipolar_klempi()
    assert _bosluksuz(bipolar) in _bosluksuz(b9), f"§9 firmware bipolar klempini ({bipolar}) aynen anmalı"
    assert "g_tpp - 1 - DDS_DEAD_TIME_TICKS" not in b9, "§9 HG-2 öncesi klemp formülünü anlatıyor"
    assert not re.search(r"klemp `g_tpp - 1`'e dayanıyor", b9), "§9 Ölçüm 3 eski tavanı (tpp−1) anlatıyor"
    assert not re.search(r"§16 reflash", b9), (
        "§9 artık doz kalibrasyonu KALDIRILDI olan §16'ya 'reflash' diye yönlendiriyor (Ö.4-Y5)"
    )


def test_D6_48_bolum9_HER_bipolar_klemp_ifadesi_FIRMWARE_ile_ayni():
    # D67 orkestratör kolu: §9 bipolar klempi İKİ yerde anar; yalnız birini bozan mutant ("in" denetimi) YAŞIYORDU.
    b9 = _cizgisiz(_bolum(BELGE.read_text(encoding="utf-8"), "## ⏳ 9 — "))
    bipolar = _bosluksuz(_fix1c_bipolar_klempi())
    ifadeler = re.findall(r"`([^`]*g_tpp\[i\]\s*/\s*2U[^`]*)`", b9)
    assert ifadeler, "aparat: §9'da bipolar klemp ifadesi (`… g_tpp[i] / 2U …`) bulunamadı"
    farkli = [i for i in ifadeler if bipolar not in _bosluksuz(i)]
    assert not farkli, f"§9'daki bipolar klemp ifadesi firmware [FIX-1c] ile farklı: {farkli} (firmware: {bipolar})"
