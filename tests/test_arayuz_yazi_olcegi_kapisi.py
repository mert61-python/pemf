# Author: mertaygn, cglrgrkn
"""SİSTEM YAZI ÖLÇEĞİ KAPISI  [S6 adım 9, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM: `grep allowFontScaling|maxFontSizeMultiplier pf/src` = 0 eşleşme. React Native
varsayılanı sistem yazı ölçeğini SINIRSIZ uygular; Android "Yazı boyutu" en büyükte (≈1,3) alt bar
etiketleri, seans süresi, bildirim rozeti ve seans detay tablosu taşıyor/kırpılıyordu.

SÖZLEŞME:
  1. Tavan TEK KAYNAKTAN gelir: `tokens.MAX_FONT_SCALE`. Başka dosya bu sayıyı HAM yazmaz.
  2. Tavan `injectFont` içinde `fontFamily` erken-dönüşünden ÖNCE uygulanır (ikon fontlu Text'ler
     de kapsansın).
  3. `allowFontScaling={false}` HİÇBİR yerde kullanılmaz: görme zorluğu olan operatör için ölçek
     tamamen KAPATILMAZ, yalnız tavanlanır. (Yerel `maxFontSizeMultiplier` serbesttir — bileşen
     kendi daha sıkı tavanını koyabilir.)
  4. Kritik sayısal alanlar (seans süresi, canlı bobin okuması) tek satır + sığdırma taşır.

⚠️ Davranış jest ile ölçülür: pf/src/theme/__tests__/fontOlcegiTavani.test.ts ve
   pf/src/components/domain/__tests__/SessionProgressCard.yaziOlcegi.test.tsx.
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"

pytestmark = pytest.mark.skipif(
    not (_PF / "theme" / "fonts.ts").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)


def _oku(bagil: str) -> str:
    # ⚠️ Gömülü python stdout cp1254; dosya okumada encoding AÇIKÇA verilir.
    return (_PF / bagil).read_text(encoding="utf-8")


def _yorum_mu(satir: str) -> bool:
    """Tek satırlık `//` ve blok yorum gövdesi (`*`) satırlarını ele."""
    kirp = satir.strip()
    return kirp.startswith("//") or kirp.startswith("*") or kirp.startswith("/*")


def _kodu(src: str) -> str:
    """Yorum satırlarını boşa çevirir (satır numaraları/konum sırası korunur)."""
    return "\n".join("" if _yorum_mu(l) else l for l in src.splitlines())


def test_KRITIK_tavan_tek_kaynaktan_ve_erken_donusten_ONCE():
    """Tavan `fontFamily` erken-dönüşünün ALTINA kayarsa ikon fontlu Text'ler kapsam dışı kalır.

    ⚠️ Konum karşılaştırması YORUMSUZ kaynak üzerinde yapılır: ilk sürüm ham metinde arıyordu ve
    dosyanın 53. satırındaki AÇIKLAMA yorumu ("...maxFontSizeMultiplier YOKTU") her zaman erken
    dönüşten önce geldiği için, tavan bloğu gerçekten aşağı taşındığında bile kapı YEŞİL kalıyordu
    (ölçüldü). Davranışsal kanıt: pf/src/theme/__tests__/fontOlcegiTavani.test.ts 5. vaka.
    """
    src = _oku("theme/fonts.ts")
    assert "MAX_FONT_SCALE" in src, "fonts.ts tavanı tokens'tan almıyor"
    kod = _kodu(src)
    tavan = kod.find("maxFontSizeMultiplier: MAX_FONT_SCALE")
    erken = kod.find("if (flat.fontFamily) return")
    assert tavan > -1, "injectFont tavanı uygulamıyor (atama bulunamadı)"
    assert erken > -1, "fontFamily erken-dönüşü bulunamadı (yeniden yazıldıysa kapı güncellenmeli)"
    assert tavan < erken, (
        "Tavan ataması `flat.fontFamily` erken-dönüşünden SONRA: ikon fontlu Text'ler (Ionicons vb.) tavansız kalır."
    )


def test_KRITIK_allowFontScaling_false_kullanilmiyor():
    """Ölçeği tamamen kapatmak erişilebilirliği keser; sözleşme TAVAN koymaktır."""
    ihlal = []
    for p in sorted(_PF.rglob("*.ts*")):
        if "__tests__" in p.parts:
            continue
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            # ⚠️ YORUM SATIRLARI ELENİR: sözleşmenin KENDİSİ ("allowFontScaling={false} ASLA
            # kullanılmaz") kaynak yorumlarında geçiyor ve kapı ilk sürümde onları ihlal saydı.
            if _yorum_mu(satir):
                continue
            if re.search(r"allowFontScaling\s*=\s*\{\s*false\s*\}", satir) or re.search(
                r"allowFontScaling:\s*false", satir
            ):
                ihlal.append(f"{p.relative_to(_PF).as_posix()}:{no}")
    assert not ihlal, (
        "allowFontScaling={false} erişilebilirliği KAPATIR; yerine maxFontSizeMultiplier "
        "(yerel tavan) kullanın:\n" + "\n".join(ihlal)
    )


def test_tavan_sayisi_baska_dosyada_HAM_yazilmamis():
    """1.2 sayısı yalnız tokens.ts'te; başka yerde ham yazılırsa iki kaynak oluşur."""
    tokens = _oku("theme/tokens.ts")
    assert "MAX_FONT_SCALE = 1.2" in tokens, "tavan sabiti tokens.ts'te değil"
    ihlal = []
    for p in sorted(_PF.rglob("*.ts*")):
        if "__tests__" in p.parts or p.name == "tokens.ts":
            continue
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"maxFontSizeMultiplier[=:]\s*\{?\s*1\.2\b", satir):
                ihlal.append(f"{p.relative_to(_PF).as_posix()}:{no}")
    assert not ihlal, "Tavan sayısı ham yazılmış (tek kaynak MAX_FONT_SCALE):\n" + "\n".join(ihlal)


def test_KRITIK_seans_suresi_tek_satir_ve_sigdirilir():
    """KALAN süre ACİL DURDUR ile aynı kartta okunur; kırpılırsa hekim süreyi göremez."""
    src = _oku("components/domain/SessionProgressCard.tsx")
    assert "adjustsFontSizeToFit" in src and "numberOfLines" in src
    assert "SURE_METNI" in src, "süre metni sözleşmesi (tek satır + sığdırma) kaldırılmış"
    # Saatli biçim geri gelirse 320 px'te taşar.
    assert "}:${String(m).padStart" not in src, (
        "formatTime saatli biçime dönmüş ('1:05:30'); klinik kapağı 120 dk, biçim 'mm:ss' olmalı."
    )


def test_canli_bobin_okumasi_tek_satir():
    src = _oku("components/domain/CoilParameterPanel.tsx")
    i = src.find("styles.readingValue")
    assert i > -1, "readingValue kullanımı bulunamadı"
    assert "adjustsFontSizeToFit" in src[i : i + 400], (
        "Canlı okuma (mT/°C/A) sığdırma taşımıyor: ölçek 1,3'te iki satıra bölünür."
    )


def test_rf_9_ve_10_puntolari_azaliyor():
    """CIRCIR: 9-10 px'lik puntolar 320 px'te 8-9 px'e düşüyor. Faz D hedefi 0."""
    kalan = []
    for p in sorted(_PF.rglob("*.tsx")):
        if "__tests__" in p.parts:
            continue
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"fontSize:\s*rf\(\s*(9|10)\s*\)", satir):
                kalan.append(f"{p.relative_to(_PF).as_posix()}:{no}")
    # 2026-09-05: 17 → 9 (S6) → 7 (S7 adım 10: liveText, serverCamNote).
    assert len(kalan) == 7, (
        f"rf(9|10) punto sayısı {len(kalan)}, sabit 7.\nARTTIYSA: typography.small (11) kullanın.\n"
        "AZALDIYSA: bu sabiti düşürün.\n" + "\n".join(kalan)
    )
