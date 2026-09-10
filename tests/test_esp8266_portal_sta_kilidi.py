# -*- coding: utf-8 -*-
# Author: mertaygn
"""8266 PORTAL, STA'yı KİLİTLEMEZ — sahada ESP dakikalarca "offline" kalıyordu.

BELİRTİ (sahip bildirimi 2026-09-10, iki senaryo):
  1. ESP erken açılıp ilk fazda PEMF-Gateway'e bağlanamazsa, kullanıcı 5 dakika sonra
     uygulamayı açsa bile ESP **hep offline** görünüyor.
  2. ESP hazırken hotspot kapatılıyor; geri açıldığında ESP hotspot'a **bağlanmıyor**.

KÖK NEDEN (ölçüldü): portal `WiFi.mode(WIFI_AP)` ile **AP-ONLY** açılıyor → STA ölür.
Eski akışta krediler tükenince portal KOŞULSUZ açılıyordu ve `PORTAL_TIMEOUT` (5 dk)
boyunca cihaz hotspot'u GÖREMİYORDU. Üstelik portal açıkken `update()`'teki reconnect
bloğu (`!_portalActive`) ve `_reconnectWiFi()` (erken `return`) de kapalı. Dinleme payı:

    kayıtlı ağ 1 → 30 sn dene / 300 sn kör  = %9
    kayıtlı ağ 2 → 60 sn / 300 sn           = %17
    kayıtlı ağ 5 → 150 sn / 300 sn          = %33

Yani tek kayıtlı ağda ESP zamanın ~onda birinde hotspot'u görebiliyor; "5 dakika" da
tam olarak `PORTAL_TIMEOUT` değeri.

SAHİP KARARI 2026-09-10: "sürekli reconnect denemeli; bağlanmazsa PEMF-Gateway'e anlamı
yok tek başına." → kayıtlı kredi VARSA çalışırken-kopuşta portal AÇILMAZ, STA'da sonsuza
kadar denenir (30 sn/kredi doğal kısıcı). Portal yalnız (a) hiç kredi YOKKEN — sahibin
eski "süresiz açık kalsın" kararı KORUNUR — ya da (b) `PROVIZYON_GERI_DONUS` süresince
KESİNTİSİZ başarısızlıktan sonra bir kez açılır (SSID/parola değişirse provizyon yolu
kapanmasın).

C bu makinede DERLENEMEZ → doğrulanabilir olan YAPISAL. Gerçek doğrulama (ESP erken
açılıp sonradan bağlanıyor; hotspot dönünce ~30 sn içinde geliyor) tezgâh-ONLY.
⚠️ ÇIPA YORUMA DEĞİL KODA: aşağıdaki `_kod()` yorumları ve string literallerini SIYIRIR —
bu depoda düz-metin araması kendi açıklama yorumunu bulup mutasyonu YEŞİL bırakmıştı.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NM_CPP = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp"
NM_H = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.h"

pytestmark = pytest.mark.skipif(not NM_CPP.exists(), reason="firmware/ kaynak agaci yok")

#: Kredi kontrolünü temsil eden belirteçler (doğrudan çağrı ya da türetilmiş yerel).
KREDI_BELIRTECI = ("_hasSavedCredentials", "krediVar")


def _kod(kaynak: str) -> str:
    """C/C++ yorumlarını ve string/char literallerini SIYIRIR; yalnız kod kalır."""
    cikti: list[str] = []
    i, n, durum = 0, len(kaynak), "kod"
    BS = chr(92)
    TEK = chr(39)
    while i < n:
        ch = kaynak[i]
        if durum == "kod":
            if kaynak[i : i + 2] == "//":
                durum = "satir"
                i += 2
                continue
            if kaynak[i : i + 2] == "/*":
                durum = "blok"
                i += 2
                continue
            if ch == '"':
                durum = "str"
                i += 1
                continue
            if ch == TEK:
                durum = "chr"
                i += 1
                continue
            cikti.append(ch)
        elif durum == "satir":
            if ch == "\n":
                durum = "kod"
                cikti.append(ch)
        elif durum == "blok":
            if kaynak[i : i + 2] == "*/":
                durum = "kod"
                i += 2
                continue
        else:  # str / chr
            if ch == BS:
                i += 2
                continue
            if (durum == "str" and ch == '"') or (durum == "chr" and ch == TEK):
                durum = "kod"
        i += 1
    return "".join(cikti)


def _kaynak(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def _kapsayan_kosul(kod: str, cagri_konumu: int) -> str | None:
    """`cagri_konumu`daki ifadeyi saran `if (...)` KOŞULUNU döndürür (yoksa None).

    ⚠️ NEDEN YAKINLIK PENCERESİ DEĞİL: ilk yazımda "çağrıdan önceki 500 karakterde
    kredi belirteci geçiyor mu" bakılıyordu. MUTASYON TESTİ bunun SAHTE-YEŞİL olduğunu
    gösterdi: koşuldan `krediVar` çıkarılsa bile `const bool krediVar = ...` BİLDİRİMİ
    pencerede kalıyor ve kapı geçiyordu. Bu, depoda üç kez tekrarlanan zayıf-çıpa
    hatasının aynısı. Artık GERÇEK saran koşul metni ayrıştırılıyor.

    Yöntem: çağrıdan geriye süslü parantez sayarak kapsayan bloğun `{`ini bul; onun
    hemen öncesindeki `)`den geriye eşleyerek `(`ı bul; öncesinde `if` var mı bak.
    """
    # 1) kapsayan blogun aciligi
    derinlik = 0
    i = cagri_konumu - 1
    while i >= 0:
        c = kod[i]
        if c == "}":
            derinlik += 1
        elif c == "{":
            if derinlik == 0:
                break
            derinlik -= 1
        i -= 1
    if i < 0:
        return None
    # 2) `{` oncesindeki `)` -> eslesen `(`
    j = i - 1
    while j >= 0 and kod[j].isspace():
        j -= 1
    if j < 0 or kod[j] != ")":
        return None
    par = 0
    k = j
    while k >= 0:
        if kod[k] == ")":
            par += 1
        elif kod[k] == "(":
            par -= 1
            if par == 0:
                break
        k -= 1
    if k < 0:
        return None
    kosul = kod[k + 1 : j]
    # 3) `(` oncesinde `if` olmali (else if de kabul)
    onc = " ".join(kod[max(0, k - 12) : k].split())
    if not onc.endswith("if"):
        return None
    return kosul


def portal_ihlalleri(kod: str) -> list[int]:
    """Kredi kontrolüyle KORUNMAYAN `_startWiFiPortal();` çağrılarının konumları.

    Ölçüt: çağrıyı saran `if` KOŞULUNUN KENDİSİ kredi belirteci içermeli. Bildirimin
    yakınlarda durması YETMEZ (bkz. `_kapsayan_kosul` docstring'i).
    """
    ihlal: list[int] = []
    # YALNIZ ÇAĞRI: `_startWiFiPortal();` noktalı virgülle biter; tanım `{` ile biter.
    for m in re.finditer(r"_startWiFiPortal\s*\(\s*\)\s*;", kod):
        kosul = _kapsayan_kosul(kod, m.start())
        if kosul is None or not any(t in kosul for t in KREDI_BELIRTECI):
            ihlal.append(m.start())
    return ihlal


def test_KRITIK_portal_cagrilari_KREDI_KONTROLUYLE_korunuyor():
    """Hiçbir `_startWiFiPortal()` çağrısı koşulsuz olmamalı.

    MUTASYON: tükenme dalındaki `if (!_portalActive && (!krediVar || uzunKopus))`
    koşulunu `if (!_portalActive)`e çevir → çağrı koşulsuzlaşır → KIRMIZI.
    Sahadaki etki: kayıtlı ağ varken de portal açılır, cihaz 5 dk kör kalır.
    """
    kod = _kod(_kaynak(NM_CPP))
    assert "_startWiFiPortal" in kod, "cagri/tanim hic yok -> kapi BAYAT"
    ihlal = portal_ihlalleri(kod)
    assert not ihlal, (
        f"{len(ihlal)} adet KOSULSUZ _startWiFiPortal() cagrisi var (konum {ihlal}). "
        "Portal AP-ONLY oldugu icin STA'yi oldurur ve cihaz PORTAL_TIMEOUT boyunca "
        "hotspot'u GOREMEZ (tek kayitli agda dinleme payi %9). Kayitli kredi VARKEN "
        "calisirken-kopusta portal ACILMAMALI."
    )


def test_KRITIK_provizyon_geri_donus_sabiti_MAKUL():
    """`PROVIZYON_GERI_DONUS` tanımlı ve yeterince uzun olmalı.

    Çok kısa olursa (ör. 60 sn) kör pencere geri gelir — düzeltmenin amacı boşa çıkar.
    """
    h = _kod(_kaynak(NM_H))
    m = re.search(r"PROVIZYON_GERI_DONUS\s*=\s*(\d+)", h)
    assert m, "PROVIZYON_GERI_DONUS tanimli degil (NetworkManager.h)"
    ms = int(m.group(1))
    assert ms >= 600000, (
        f"PROVIZYON_GERI_DONUS={ms} ms COK KISA: portal sik acilir ve AP-ONLY kor "
        "penceresi geri gelir. En az 10 dk olmali."
    )
    p = re.search(r"PORTAL_TIMEOUT\s*=\s*(\d+)", h)
    assert p, "PORTAL_TIMEOUT tanimli degil"
    assert ms > int(p.group(1)), (
        "PROVIZYON_GERI_DONUS, PORTAL_TIMEOUT'tan UZUN olmali; aksi halde portal sokulur-acilir dongusune girer"
    )


def test_KRITIK_baglanti_kurulunca_kopus_sayaci_SIFIRLANIYOR():
    """Başarılı bağlantı `_staKopusBasiMs`i sıfırlamalı.

    MUTASYON: `_staKopusBasiMs = 0;` satırını sil → eski kopuş süresi birikir, portal
    ilk kısa kopuşta bile açılır → KIRMIZI.
    """
    kod = _kod(_kaynak(NM_CPP))
    assert "_staKopusBasiMs" in kod, "_staKopusBasiMs kullanilmiyor -> kapi BAYAT"
    sifirlar = re.findall(r"_staKopusBasiMs\s*=\s*0\s*;", kod)
    assert len(sifirlar) >= 2, (
        f"_staKopusBasiMs = 0 atamasi {len(sifirlar)} yerde; en az 2 olmali (kurucu + baglanti kurulunca sifirlama)."
    )


def test_hic_kredi_yokken_portal_yolu_KORUNUYOR():
    """Sahibin eski kararı: kredi YOKKEN portal açılabilir kalmalı (ilk kurulum).

    Karşıt kanıt: düzeltme "portalı tamamen kaldır"a kaymasın.
    """
    kod = _kod(_kaynak(NM_CPP))
    assert re.search(r"!\s*_hasSavedCredentials\s*\(\s*\)", kod), (
        "`!_hasSavedCredentials()` kosullu portal yolu KAYBOLMUS -> ilk kurulumda "
        "provizyon imkansizlasir (sahibin ESKI karari)"
    )


def test_KARSIT_KANIT_kapi_gercekten_olcuyor():
    """Öz-test: `portal_ihlalleri` koşulsuz çağrıyı YAKALIYOR, korunanı yakalamıyor.

    Kapı bozuksa (ör. her zaman boş liste dönüyorsa) yukarıdaki testler SESSİZCE
    yeşil kalırdı. Burada sentetik iyi/kötü kaynakla ayırt ettiği gösterilir.
    """
    kotu = "void f() { if (!_portalActive) { _startWiFiPortal(); } }"
    assert portal_ihlalleri(kotu), "kapi KOSULSUZ cagriyi yakalamadi -> hicbir sey olcmuyor"

    iyi = (
        "void f() { const bool krediVar = _hasSavedCredentials();"
        " if (!_portalActive && !krediVar) { _startWiFiPortal(); } }"
    )
    assert not portal_ihlalleri(iyi), "kapi KORUNAN cagriyi ihlal sandi (yanlis pozitif)"

    # ⚠️ ASIL MUTASYON: kredi kontrolu KOSULDAN cikarilir ama BILDIRIM yakinda KALIR.
    # Kapinin ilk hali (yakinlik penceresi) bunu YAKALAMIYORDU -> sahte-yesil.
    sahte_yesil = (
        "void f() { const bool krediVar = _hasSavedCredentials(); if (!_portalActive) { _startWiFiPortal(); } }"
    )
    assert portal_ihlalleri(sahte_yesil), (
        "kapi, kosuldan cikarilmis ama yakinda BILDIRILMIS krediVar ile aldanabiliyor "
        "-> yakinlik penceresi degil GERCEK kosul okunmali"
    )

    # Kosulsuz (if bile yok) cagri da ihlal
    assert portal_ihlalleri("void f() { _startWiFiPortal(); }"), "if'siz cagri ihlal sayilmadi"

    # Yorum-ici belirtec kapiyi ALDATMAMALI (bu depoda 3 kez yasanan zayif-cipa hatasi)
    aldatma = (
        "void f() { /* _hasSavedCredentials burada sadece YORUMDA gecer */"
        " if (!_portalActive) { _startWiFiPortal(); } }"
    )
    assert portal_ihlalleri(_kod(aldatma)), "YORUM icindeki belirtec kapiyi aldatti -> _kod() siyirmasi calismiyor"
