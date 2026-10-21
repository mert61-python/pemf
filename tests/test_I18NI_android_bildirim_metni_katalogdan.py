# -*- coding: utf-8 -*-
"""I18NI-A2.13 sondası: APK güncellemesinin Android ön plan bildirimi (`apps/ui/modules/apk-installer/android/.../IndirmeServisi.kt`)
içerik metnini ve bildirim KANALI adını Kotlin'de SABİT (ASCII) Türkçe yazar: "Paket arka planda indiriliyor; uygulamayi kapatabilirsiniz.",
"Guncelleme indirme". Başlık JS'ten (`i18n.t("guncelleme.indirmeBildirimi")`) gelir, içerik ve kanal gelmez. `apps/ui/modules/` hiçbir yüzeyin
önekinde değil, Kotlin hiçbir çıkarıcıda yok → K-2 "hepsi" kapsamı bu dosyaları GÖRMEZ.
Bu sonda: bildirim kurucusundaki (`setContentTitle` / `setContentText` / `NotificationChannel`) metin JS'ten (Intent extra) gelir; Kotlin'deki
dizgi yalnız eski JS için YEDEK olabilir (`?: "…"`).
Koşum: bash $SP/aj.sh b pytest _inceleme/I18NI-A2.13/test_i18n_android_bildirim_metni_katalogdan.py -q -rfE
"""

from __future__ import annotations

import re
from pathlib import Path


def _kok() -> Path:
    p = Path(__file__).resolve().parent
    while not (p / "i18n" / "kapsam.json").exists():
        p = p.parent
    return p


KOK = _kok()
KT = KOK / "apps/ui/modules/apk-installer/android/src/main/java/expo/modules/apkinstaller/IndirmeServisi.kt"


def test_bildirim_icerik_metni_ve_kanal_adi_JSten_gelir():
    s = KT.read_text(encoding="utf-8")
    sabit = []
    for m in re.finditer(r"(?m)\.(setContentTitle|setContentText)\((.*)\)\s*$", s):
        if not re.search(r'getStringExtra\("\w+"\)\s*\?:', m.group(2)):
            sabit.append(f"{m.group(1)}({m.group(2).strip()})")
    for m in re.finditer(r"NotificationChannel\(\s*\w+\s*,\s*([^,]+),", s):
        if not re.search(r'getStringExtra\("\w+"\)\s*\?:', m.group(1)):
            sabit.append(f"NotificationChannel(ad={m.group(1).strip()})")
    assert not sabit, (
        "Android bildiriminde dile bağlanmamış SABİT Türkçe metin (EN kullanıcı Türkçe görür): " + "; ".join(sabit)
    )


def test_JS_kopru_metni_katalogdan_gecirir():
    js = (KOK / "apps/ui/src/services/mobileUpdate.ts").read_text(encoding="utf-8")
    m = re.search(r"indirmeServisiniBaslat\?\.\(([^;]*)\)", js)
    assert m, "mobileUpdate indirme servisini başlatmıyor"
    assert m.group(1).count("i18n.t(") >= 3, f"başlık + içerik + kanal adı katalogdan geçirilmiyor: {m.group(1)[:160]}"


def test_yerli_modul_dizini_ARAYUZ_yuzeyinde_ve_defterde():
    """Orkestratör (14): `apps/ui/modules/` hiçbir yüzeyde değildi → köprüye (`index.ts`) eklenen sabit Türkçe K-2'den KAÇIYORDU (ajan
    mutantı SAĞ kaldı). Önek arayüz yüzeyine alındı; dosyalar kapsam defterinde (K-2 `hepsi` kapsamı onları da tarar)."""
    import sys

    if str(KOK) not in sys.path:
        sys.path.insert(0, str(KOK))
    from scripts.i18n import kapsam, ortak

    dosyalar = ortak.yuzey_dosyalari("arayuz", KOK)
    assert "apps/ui/modules/apk-installer/index.ts" in dosyalar
    defter = kapsam.defter_oku(KOK)["dosyalar"]
    eksik = [f for f in dosyalar if f.startswith("apps/ui/modules/") and f not in defter]
    assert not eksik, f"yerli modül dosyası kapsam defterinde yok: {eksik}"
