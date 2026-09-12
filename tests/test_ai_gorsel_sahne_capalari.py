# -*- coding: utf-8 -*-
# Author: mertaygn
"""GÖRSEL SAHNE KAYNAK ÇIPALARI — AI Hub planı, ADIM 4 / G9.

===============================================================================
NEDEN KAYNAK ÇIPASI DA GEREKLİ
===============================================================================
`GorselSahne.test.tsx` bileşenin DAVRANIŞINI ölçer; bu dosya bileşenin EKRANLARDA GERÇEKTEN
KULLANILDIĞINI ölçer. İkisi ayrı sorulardır ve bu depoda ikincisi bir kez ihmal edildiğinde
kapı sessizce anlamını yitirdi (`test_responsive_grafik_kapisi.py` dosya başlığındaki not:
"saf hesap testleri, bileşenin o hesabı KULLANMAYI bırakmasını yakalayamıyor").

⚠️ YORUMLAR SÖKÜLÜR. 2026-09-12'de bizzat ölçüldü: `kameraKutusu(onizlemeW…)` çağrısını ANAN iki
açıklama yorumu `test_responsive_grafik_kapisi.py`deki sayacı 2 → 4 yaptı; çağrı sayısı hiç
değişmemişti. Bu depoda "yorum kapıyı kandırdı" hatasının beşinci tekrarı.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

pytestmark = pytest.mark.skipif(
    not (_PF / "components" / "ui" / "GorselSahne.tsx").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)

#: `<GorselSahne` beklenen sayısı — 5 AI Hub modülü + PetOwner ekranı (aynı dosyada).
#: ⚠️ SABİT SAYAÇ, ">= 1" DEĞİL: bir modül sessizce eski `<Image>`a geri dönerse yalnız O modülde
#: girdi kaybolur ve arıza tek bir sekmede yaşamaya devam eder (bu deponun tekrar eden sınıfı).
BEKLENEN_SAHNE_SAYISI = 6


def _kod(bagil: str) -> str:
    """Kaynağı YORUMLARI SÖKÜLMÜŞ döndürür (string literalleri aynen korunur)."""
    from c_soyucu import c_soy

    return c_soy((_PF / bagil).read_text(encoding="utf-8"))


# ============================================================================
# 1. ⚠️ ASIL KAPI — ESKİ TERNARY GERİ GELMEZ
# ============================================================================


def test_KRITIK_GIRDIYI_SILEN_ternary_GERI_GELMEDI():
    """⚠️ SAHİBİN 1. ŞİKÂYETİNİN KAYNAĞI, birebir bu satırdı (BEŞ kopya):

        source={{ uri: result?.image_base64 ? `data:...` : imageUri }}

    Sonuç gelir gelmez kullanıcının fotoğrafı ekrandan siliniyor ve bir daha erişilemiyordu.
    ⚠️ Fantom/petri'de sunucu `image_base64`'ü `no_detection` yolunda da gönderdiği için ternary
    GİRDİ dalına **asla** düşmüyordu — yani girdi hiçbir koşulda geri gelmiyordu.

    MUTASYON: bir modülde `<GorselSahne>`u eski `<Image>` ternary'sine çevir → KIRMIZI.
    """
    src = _kod("screens/AiHubScreen.tsx")
    assert "result?.image_base64 ?" not in src, (
        "GIRDIYI SILEN ternary geri gelmis: sonuc gelince kullanicinin fotografi kayboluyor"
    )


def test_KRITIK_bes_modul_ve_petowner_SAHNEYI_kullaniyor():
    """MUTASYON: `BEKLENEN_SAHNE_SAYISI`yı bozmadan bir `<GorselSahne>`u kaldır → KIRMIZI."""
    src = _kod("screens/AiHubScreen.tsx")
    n = src.count("<GorselSahne")
    assert n == BEKLENEN_SAHNE_SAYISI, (
        f"<GorselSahne> sayisi {n}, beklenen {BEKLENEN_SAHNE_SAYISI} "
        "(5 AI Hub modulu + PetOwner). Bir modul eski gosterime dondurulmus olabilir."
    )


def test_KRITIK_sahne_sayfalari_TEK_KAYNAKTAN_gelir():
    """Her `<GorselSahne>` sayfalarını `sahneSayfalari()` ile üretmeli.

    ⚠️ Bir modül sayfaları elle kurarsa girdi-değiştirme kuralı (yerel dosya) ve boş-panel
    filtresi orada UYGULANMAZ; arıza yalnız o sekmede sessizce yaşar.
    """
    src = _kod("screens/AiHubScreen.tsx")
    assert src.count("sahneSayfalari(result, imageUri)") == BEKLENEN_SAHNE_SAYISI, (
        "sayfalar TEK KAYNAKTAN uretilmiyor — bir modul kendi listesini kuruyor olabilir"
    )


# ============================================================================
# 2. ⚠️ ORAN KİLİDİ TEK KAYNAKTA (§5 yeniden pinleme)
# ============================================================================


def test_KRITIK_oran_kilidi_sahnede_TEK_cagri():
    """`GorselSahne` kutuyu `kameraKutusu()` ile hesaplar — ikinci bir hesap İŞARET KAYMASIDIR.

    ⚠️ Sayaç 1: ikinci bir çağrı, iki farklı kutu demektir ve üzerine çizilen organ/tümör
    işaretleri taban görüntüyle kayar (tıbbi karar ekranı).

    MUTASYON: kutuyu `{width: kapW, height: tavanY}` ile elle kur → KIRMIZI.
    """
    src = _kod("components/ui/GorselSahne.tsx")
    assert src.count("kameraKutusu(") == 1, (
        f"GorselSahne'de kameraKutusu( sayisi {src.count('kameraKutusu(')}, beklenen 1"
    )


def test_KRITIK_canli_kamera_kutulari_DOKUNULMADI():
    """⚠️ Canlı kamera kutusu AYRI bir sorundur ve refaktörde kaybolmamalı.

    Galeri sonuç panellerini gezer; canlı önizleme ise kamera karesi + üzerine bindirilen
    organ işaretlerini hizalar. İkisi karıştırılırsa canlı görüntüde işaretler kayar.
    """
    aihub = _kod("screens/AiHubScreen.tsx")
    assert aihub.count("kameraKutusu(onizlemeW") == 2, (
        "canli modullerin (VisionModule, CatOrganModule) oran kilidi kaybolmus"
    )
    aipro = _kod("components/domain/AiProPanel.tsx")
    assert "kameraKutusu(kutuW" in aipro, "AI Pro paneli kutu oran kilidini birakmis"


def test_KRITIK_sahnede_aspectRatio_YASAK():
    """⚠️ `aspectRatio` + `maxHeight` birlikte oranı BOZAR: maxHeight yüksekliği kırpınca
    genişlik %100 kalır. Kutu AÇIK px hesaplanmalı — yasak `kameraKutusu.ts`te zaten vardı,
    yeni bileşene de genişletildi.

    MUTASYON: kutuya `aspectRatio: oran` ekle → KIRMIZI.
    """
    src = _kod("components/ui/GorselSahne.tsx")
    assert "aspectRatio" not in src, "GorselSahne aspectRatio kullaniyor -> oran kilidi bozulur, isaretler kayar"


def test_KRITIK_ORAN_KILITLI_gorsel_YUZDE_olcu_almaz():
    """Oran-kilitli taban görsel AÇIK SAYISAL kutu almalı.

    ⚠️ Yüzde ölçü, üst katmanın (organ işaretleri) taban görselden FARKLI bir kutuya oturmasına
    yol açar — G10'un yasakladığı tam durum.

    ⚠️ TEK İSTİSNA `olcumsuzGorsel`: ölçüm gelmeden çizilen yedek kare. Orada kutu HENÜZ
    BİLİNMİYOR (yüzde vermekten başka seçenek yok) ve ÜST KATMAN ÇİZİLMİYOR, dolayısıyla hizalama
    sorunu doğmaz. Bu istisnanın bedeli aşağıdaki ikinci iddiayla ödeniyor: üst katman YALNIZ
    ölçülmüş dalda çağrılabilir.
    ⚠️ Kural ilk yazımda kaba bir "hiçbir yerde yüzde olmasın" biçimindeydi ve yedek çizimi
    (sahada görselin HİÇ görünmemesini düzelten şey) engelledi — kapı, gerekçesine göre daraltıldı.
    """
    src = _kod("components/ui/GorselSahne.tsx")

    # İstisna satırını ayıkla, kalan her yerde yüzde-ölçü YASAK.
    kalan = "\n".join(s for s in src.splitlines() if "olcumsuzGorsel" not in s)
    assert 'width: "100%", height: "100%"' not in kalan, (
        "oran-kilitli gorsel yuzde olcu aliyor -> ust katman FARKLI kutuya oturur"
    )
    assert "width: '100%', height: '100%'" not in kalan

    # ⚠️ ÜST KATMAN YALNIZ ÖLÇÜLMÜŞ DALDA: yedek dalda çizilseydi, bilinmeyen bir kutuya
    # oturur ve işaretler kayardı (istisnanın bedeli tam olarak budur).
    assert src.count("ustKatman?.(") == 1, (
        f"ustKatman {src.count('ustKatman?.(')} yerde cagriliyor — olcumsuz dalda da cizilmis olabilir"
    )


# ============================================================================
# 3. YORUM TUZAĞINA KARŞI KANIT
# ============================================================================


def test_KRITIK_kapi_YORUMLA_kandirilamaz():
    """⚠️ KARŞIT KANIT: bu dosyanın sayaçları yorum metnini SAYMAMALI.

    `GorselSahne.tsx` kendi başlığında `kameraKutusu()` ifadesini ANIYOR; yorum sökülmeseydi
    yukarıdaki "== 1" kapısı 2 sayar ve SAHTE KIRMIZI verirdi (aynı tur içinde
    `test_responsive_grafik_kapisi.py`de bizzat yaşandı: 2 → 4).
    """
    ham = (_PF / "components" / "ui" / "GorselSahne.tsx").read_text(encoding="utf-8")
    assert ham.count("kameraKutusu(") > 1, "onkosul kayboldu: baslikta artik anilmiyor"
    assert _kod("components/ui/GorselSahne.tsx").count("kameraKutusu(") == 1
