# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-16 (Bulgu 1): HEP-AÇIK makine hiç güncelleme almıyordu.

`boot()` sayfa yüklenirken BİR KEZ çalışıyor; periyodik kontrol hiçbir yerde yoktu (ne Rust
ne JS), pencere odağında da yeniden bakılmıyordu. Launcher penceresi uygulama kullanılırken
AÇIK KALDIĞI için haftalarca açık duran bir klinik makinesi manifesti HİÇ yeniden çekmiyordu.

🔴 EN CİDDİ SONUCU — GERİ ÇAĞIRMA ULAŞAMIYORDU. `min_supported_version`, kodun kendi yorumuyla
"bir bobin-güvenliği hatası bulunduğunda MEVCUT kurulumları güncellemeye ZORLAMAK" için var ve
`rollout` frenini EZİYOR. Ama teslim yolu yoktu: mekanizmanın çalışması için cihazın yeniden
başlatılması gerekiyordu — ki en çok hep-açık kalan cihazlar da klinikler.

ÇÖZÜM: periyodik tur (6 saat) manifesti yeniden çeker; paketleri ARKA PLANDA indirir ve durumu
BİLDİRİR. ⚠️ Güncellemeyi UYGULAMAZ: uygulamak backend'i durdurur ve süren bir seansı keserdi
(hasta güvenliği kararı). Kurulum, kullanıcı uygulamayı kapatıp açtığında — zaten güvenli olan
anda — yapılır. Geri çağırma varsa mesaj YÜKSELTİLİR (kullanıcı sebebi bilmeli).
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_FLOW_RS = _KOK / "launcher" / "core" / "src" / "flow.rs"


@pytest.fixture(scope="module")
def ui() -> str:
    return _UI.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rs() -> str:
    return _MAIN_RS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flow() -> str:
    return _FLOW_RS.read_text(encoding="utf-8")


def _recheck(ui: str) -> str:
    m = re.search(r"async function recheckUpdates\(\)\s*\{(.*?)\n      \}", ui, re.S)
    assert m, "recheckUpdates bulunamadı"
    return m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# Periyodik tur VAR ve başlatılıyor mu?
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_periyodik_kontrol_VAR(ui):
    """🔴 ASIL BULGU: tek seferlik `boot()` dışında kontrol yoktu."""
    assert "recheckUpdates" in ui, "periyodik yeniden kontrol yok"
    # NOT: `[^)]*` kullanılamaz — `setInterval(() => {...})` içindeki ok-fonksiyonunun kendi
    # parantezine takılır. Aynı satırda ikisinin birlikte geçmesini arıyoruz.
    assert re.search(r"setInterval\(.*recheckUpdates", ui), "zamanlayıcıya bağlanmamış"
    assert re.search(r"setInterval\(.*recheckUpdates.*GUNCELLEME_KONTROL_MS", ui), (
        "zamanlayıcı sabit aralığa bağlanmamış"
    )


def test_periyodik_tur_ACILISTA_baslatilir(ui):
    """Tanımlanıp hiç çağrılmazsa özellik ölüdür."""
    assert "startUpdateWatch()" in ui, "izleme başlatılmıyor"
    # boot akışında çağrılmalı (tryRuntimeUpdate'in yanında).
    assert re.search(r"startUpdateWatch\(\);\s*//.*\n\s*if \(await tryRuntimeUpdate", ui), (
        "izleme boot akışına bağlanmamış"
    )


def test_aralik_makul(ui):
    """Çok sık = gereksiz ağ/CPU; çok seyrek = geri çağırma geç ulaşır."""
    m = re.search(r"GUNCELLEME_KONTROL_MS\s*=\s*([^;]+);", ui)
    assert m, "aralık sabiti yok"
    ms = eval(m.group(1).split("//")[0].strip(), {"__builtins__": {}})  # noqa: S307 (sabit ifade)
    assert 30 * 60 * 1000 <= ms <= 24 * 60 * 60 * 1000, f"aralık makul değil: {ms} ms"


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 GÜVENLİK SINIRI: periyodik tur seansı KESMEZ
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_periyodik_tur_GUNCELLEMEYI_UYGULAMAZ(ui):
    """🔴 Uygulamak backend'i durdurur → süren seans kesilir (hasta güvenliği).

    Periyodik tur yalnız indirir ve bildirir; kurulum kullanıcı uygulamayı kapatıp açtığında
    yapılır. `apply_runtime_update` buraya SIZARSA veteriner çalışırken cihaz durur.
    """
    g = _recheck(ui)
    assert "apply_runtime_update" not in g, (
        "periyodik tur güncellemeyi UYGULUYOR — süren seansı keser; yalnız indirmeli ve bildirmeli"
    )
    assert "prefetch_runtime_update" in g, "arka plan indirme yapılmıyor → paketler hiç inmez"


def test_KRITIK_kurulum_surerken_ARAYA_GIRMEZ(ui):
    """Kullanıcı kurulum/onarım yaparken periyodik tur ekranı/­durumu bozmamalı."""
    g = _recheck(ui)
    assert re.search(r"if \(busy[^)]*\) return;", g), "`busy` kontrolü yok → kurulumla çakışır"


def test_kurulu_degilse_calismaz(ui):
    """Henüz kurulum yapılmamış cihazda güncelleme kontrolü anlamsız."""
    g = _recheck(ui)
    assert "baseInstalled" in g, "kurulu olmayan cihazda da koşuyor"


def test_cevrimdisi_SESSIZ_gecer(ui):
    """Klinik hattı kopuk olabilir; her turda kırmızı hata basmak kabul edilemez."""
    g = _recheck(ui)
    assert g.count("catch (_) { return; }") >= 1 or "catch (_) { return; }" in g, (
        "manifest/plan hatası sessizce geçilmiyor"
    )


# ─────────────────────────────────────────────────────────────────────────────
# GERİ ÇAĞIRMA görünürlüğü
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_geri_cagirma_UI_ya_bildirilir(rs, flow):
    """🔴 `min_supported_version` rollout'u ezer ama UI'ya HİÇ ulaşmıyordu.

    Kullanıcı, cihazının desteklenmeyen bir sürümde olduğunu ve neden ısrarla güncelleme
    istendiğini bilmeli — yoksa bildirimi yok sayar ve geri çağırma amacına ulaşmaz.
    """
    assert "pub zorunlu: bool" in flow, "UpdatePlan geri çağırmayı taşımıyor"
    assert "plan.zorunlu = zorunlu;" in flow, "hesaplanan değer plana yazılmıyor"
    assert '"recall": plan.zorunlu' in rs, "check_runtime_update geri çağırmayı dışarı vermiyor"


def test_geri_cagirmada_mesaj_YUKSELTILIR(ui):
    """Sıradan 'güncelleme var' notu ile güvenlik geri çağırması AYNI görünmemeli."""
    g = _recheck(ui)
    assert "plan.recall" in g, "geri çağırma bayrağı hiç okunmuyor"
    assert g.count("rtRecall") >= 2, "hem indirme hem hazır durumunda yükseltilmiş mesaj olmalı"


def test_geri_cagirma_metni_ne_YAPILACAGINI_soyler(ui):
    """'Desteklenmiyor' demek yetmez; kullanıcı ne yapacağını okumalı."""
    for dil_ipucu in ("KAPATIP AÇIN", "CLOSE AND REOPEN"):
        assert dil_ipucu in ui, f"geri çağırma metni eylem söylemiyor ({dil_ipucu})"
    # Seans sürüyorsa beklemesi gerektiği de yazmalı (kesme YOK).
    assert "Seans sürüyorsa" in ui


def test_i18n_iki_dilde_TAM(ui):
    for anahtar in ("rtReady", "rtRecall"):
        assert ui.count(f"{anahtar}:") == 2, f"`{anahtar}` iki dilde de tanımlı olmalı"


def test_ayni_bildirim_TEKRAR_TEKRAR_basilmaz(ui):
    """6 saatte bir aynı notu yeniden çizmek kullanıcıyı rahatsız eder / odağı çalar.

    ⚠️ Bu test önce yalnız `"sonBildirim" in g` diye bakıyordu ve mutasyon turunda ZAYIF çıktı:
    koruma `if (true)` yapılınca bile değişken fonksiyonun başka yerinde geçtiği için test
    yeşil kalıyordu. Asıl kural KARŞILAŞTIRMADA — her bildirim dalı durum değişimine bağlı olmalı.
    """
    g = _recheck(ui)
    assert g.count("sonBildirim !==") >= 2, (
        "bildirim dalları durum karşılaştırmasına bağlı değil → aynı not her turda yeniden çizilir "
        f"(bulunan karşılaştırma: {g.count('sonBildirim !==')})"
    )
    # Her `notice(` çağrısı ya bir durum kapısının içinde ya da indirme sonucu geri-çağrısında olmalı.
    assert "if (true)" not in g, "durum kapısı sabit `true` ile devre dışı bırakılmış"
