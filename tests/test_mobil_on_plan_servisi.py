# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ÖN-PLAN SERVİSİ BAŞLATMA BORCU — saha çökmesi 2026-08-29 (Galaxy S23, Android 16 / API 36).

Kullanıcı "Güncelle"ye basar basmaz uygulama KAPANIYORDU. Logcat, 23 milisaniyelik kesin bir
zincir verdi:

    17:37:01.916  ActivityManager: Background started FGS: Allowed [uidState: TOP]
    17:37:01.924  ActivityManager: Bringing down service while still waiting for start foreground
    17:37:01.939  FATAL: ForegroundServiceDidNotStartInTimeException

⚠️ TEŞHİSİN KRİTİK YANI — bu bir İZİN sorunu DEĞİLDİ: FGS başlatma "Allowed" ve uygulama TOP
durumunda. Yanlış teşhis (Android 15+ arka plan kısıtı sanmak) izin/manifest turuna sokar ve
gerçek hatayı ıskalar. Olan şey bir SIRA hatasıydı: `startForegroundService()` çağrıldıktan
sonra servis `startForeground()` çağırmadan durduruldu. Android bunu ölümcül sayar.

Tetikleyici: indirmenin ÇOK HIZLI bitmesi (ör. APK zaten tam inmiş → hızlı yol) — o zaman
`finally` bloğundaki durdurma, başlatma yerli tarafa varmadan gidiyordu.

İki taraf da bağımsız olarak sağlamlaştırıldı; bu dosya YERLİ tarafı ölçer:
  - `IndirmeServisi`: `startForeground` her yolda İLK iş, durdurma isteğiyle gelinse bile.
  - `ApkInstallerModule`: durdurma, düz `stopService` değil DUR-NİYETİ ile yapılır.
JS tarafındaki sıra koruması ayrı ölçülür (mobileUpdate.test.ts, "durdurma ... gönderilmez").

⚠️ Kotlin bu depoda DERLENMEZ (Android toolchain'i build makinesinde). Kapı bu yüzden yapısal;
ama "sembol tanımlı mı" demez — çağrıların GERÇEK SIRASINI ve durdurma yolunun HANGİSİ olduğunu
ölçer, çünkü sahadaki hata tam olarak sıraydı.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
_YERLI = _KOK / "pf" / "modules" / "apk-installer" / "android" / "src" / "main"
_SERVIS = _YERLI / "java" / "expo" / "modules" / "apkinstaller" / "IndirmeServisi.kt"
_MODUL = _YERLI / "java" / "expo" / "modules" / "apkinstaller" / "ApkInstallerModule.kt"
_MANIFEST = _YERLI / "AndroidManifest.xml"


def _oku(p: Path) -> str:
    assert p.exists(), f"beklenen kaynak yok: {p}"
    return p.read_text(encoding="utf-8")


def _yorumsuz(kaynak: str) -> str:
    """Yorumları boşlukla değiştirir (uzunluk korunur, indeks aritmetiği bozulmaz).

    ⚠️ BU KAPI ONSUZ BOŞ ÇALIŞIYORDU — ölçüldü: sahadaki çökmeyi birebir geri koyan iki mutasyon
    (`stopSelf`i öne alma, erken `return` ekleme) YEŞİL geçti. Sebep: bu dosyanın ve Kotlin
    kaynağının gerekçe yorumları `startForeground()` sözcüğünü içeriyor, dolayısıyla
    `find("startForeground(")` gerçek ÇAĞRIYI değil YORUMU buluyor ve indeks daima en başa
    düşüyordu. Kapı, gerekçesini anlattığı hatayı yakalayamıyordu.
    """
    out: list[str] = []
    i, n, blok = 0, len(kaynak), False
    while i < n:
        if blok:
            if kaynak.startswith("*/", i):
                blok, i = False, i + 2
                out.append("  ")
                continue
            out.append("\n" if kaynak[i] == "\n" else " ")
            i += 1
        elif kaynak.startswith("/*", i):
            blok, i = True, i + 2
            out.append("  ")
        elif kaynak.startswith("//", i):
            j = kaynak.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        else:
            out.append(kaynak[i])
            i += 1
    return "".join(out)


def _govde(kaynak: str, imza: str) -> str:
    """`imza` ile başlayan bloğun gövdesi — süslü parantez sayarak, komşu fonksiyona taşmadan.

    ⚠️ Sabit karakter penceresi (`kaynak[i:i+900]`) KULLANILMIYOR: daha önce ölçüldü, bir sonraki
    fonksiyona taşıp kapıyı yanlış nedenle yeşil bırakıyordu.

    Yorumlar burada, TEK noktada sökülür (gerekçe: `_yorumsuz`) — böylece hiçbir kapı yanlışlıkla
    bir gerekçe metnine çıpalanamaz.
    """
    kaynak = _yorumsuz(kaynak)
    i = kaynak.find(imza)
    assert i != -1, f"imza bulunamadi: {imza}"
    a = kaynak.index("{", i)
    derinlik, j = 0, a
    while j < len(kaynak):
        if kaynak[j] == "{":
            derinlik += 1
        elif kaynak[j] == "}":
            derinlik -= 1
            if derinlik == 0:
                return kaynak[a : j + 1]
        j += 1
    raise AssertionError(f"blok kapanmadi: {imza}")


# ── 1) Servis: startForeground borcu HER YOLDA kapanır ──────────────────────


def test_KRITIK_startForeground_stopSelf_ten_ONCE_cagriliyor():
    """⚠️ SAHADAKİ ÇÖKMENİN TA KENDİSİ: ters sıra = süreç öldürülür.

    Servis, durdurma isteğiyle uyandırılsa bile önce kendini ön plana almalı; ancak ondan sonra
    durabilir."""
    govde = _govde(_oku(_SERVIS), "override fun onStartCommand")
    ilk_fg = govde.find("startForeground(")
    assert ilk_fg != -1, "servis kendini hic on plana almiyor -> her baslatma cokme demek"

    stop = govde.find("stopSelf(")
    if stop != -1:
        assert ilk_fg < stop, (
            "stopSelf(), startForeground()'dan ONCE cagriliyor -> "
            "ForegroundServiceDidNotStartInTimeException (saha cokmesi 2026-08-29)"
        )


def test_KRITIK_erken_return_startForeground_i_ATLAYAMAZ():
    """`startForeground`'dan ÖNCE koşullu bir `return` eklenirse borç ödenmeden çıkılır.

    ⚠️ Bu, düzeltmeyi sessizce geri alacak en olası refaktör: "durdurma isteğiyse hemen dön"
    kestirmesi doğru GÖRÜNÜR ama sahadaki çökmeyi birebir geri getirir."""
    govde = _govde(_oku(_SERVIS), "override fun onStartCommand")
    kod = govde[: govde.find("startForeground(")]
    assert "return" not in kod, (
        "startForeground() cagrilmadan once bir 'return' yolu var -> baslatma borcu odenmeden cikilabilir (cokme)"
    )


def test_dur_niyeti_servis_tarafinda_ISLENIYOR():
    kaynak = _oku(_SERVIS)
    assert "EXTRA_DUR" in kaynak, "dur-niyeti sabiti yok"
    govde = _govde(kaynak, "override fun onStartCommand")
    assert "EXTRA_DUR" in govde, "servis dur-niyetini hic okumuyor -> durdurma yolu duz stopService'e doner"
    assert "stopSelf(" in govde, "dur-niyeti gelse bile servis kendini durdurmuyor -> bildirim asili kalir"


# ── 2) Modül: durdurma yolu DUR-NİYETİ, stopService değil ───────────────────


def test_KRITIK_durdurma_DUZ_stopService_ILE_BASLAMIYOR():
    """⚠️ Asıl regresyon riski: birisi "basitleştirelim" deyip `stopService`e geri döner.

    `stopService` tamamen yasak değil — servis hiç başlamamışken ya da zaten ön plandayken
    zararsızdır ve geri-çekilme yolu olarak DURUR. Yasak olan, onun BİRİNCİL yol olması."""
    govde = _govde(_oku(_MODUL), 'AsyncFunction("indirmeServisiniDurdur")')
    assert "EXTRA_DUR" in govde, (
        "durdurma dur-niyeti gondermiyor -> servis startForeground cagirmadan indirilir (cokme)"
    )
    ilk_stop = govde.find("stopService(")
    ilk_dur = govde.find("EXTRA_DUR")
    if ilk_stop != -1:
        assert ilk_dur < ilk_stop, "duz stopService, dur-niyetinden ONCE geliyor -> birincil yol yine cokme ureten yol"
        # Geri-çekilme olduğu gerçekten kanıtlansın: `catch` bloğunun içinde kalmalı.
        assert "catch" in govde[:ilk_stop], (
            "stopService bir catch (geri-cekilme) icinde degil -> normal akista da calisiyor"
        )


def test_baslatma_ve_durdurma_AYNI_SERVISI_hedefliyor():
    """Yol/sınıf ayrışırsa durdurma hiçbir şeyi durdurmaz; bildirim asılı kalır."""
    kaynak = _oku(_MODUL)
    for imza in ('AsyncFunction("indirmeServisiniBaslat")', 'AsyncFunction("indirmeServisiniDurdur")'):
        assert "IndirmeServisi::class.java" in _govde(kaynak, imza), f"{imza} baska bir servisi hedefliyor"


# ── 3) Manifest: dataSync tipi + izni ───────────────────────────────────────


def test_KRITIK_dataSync_tipi_ve_izni_BIRLIKTE_var():
    """Android 14+ tipli FGS ister; tip VAR ama izin YOKSA `startForeground` SecurityException atar
    ve sonuç yine aynı çökmedir — ikisi ayrılamaz."""
    m = _oku(_MANIFEST)
    assert re.search(r'foregroundServiceType\s*=\s*"[^"]*dataSync', m), "servis dataSync tipiyle bildirilmemis"
    assert "android.permission.FOREGROUND_SERVICE_DATA_SYNC" in m, (
        "dataSync tipi bildirilmis ama izni istenmemis -> startForeground SecurityException atar"
    )
    assert "android.permission.FOREGROUND_SERVICE" in m, "temel FOREGROUND_SERVICE izni yok"


def test_servis_manifeste_KAYITLI():
    assert "IndirmeServisi" in _oku(_MANIFEST), (
        "servis manifeste kayitli degil -> startForegroundService sessizce basarisiz olur"
    )
