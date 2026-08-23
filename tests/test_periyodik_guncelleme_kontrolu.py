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
    """Tanımlanıp hiç çağrılmazsa özellik ölüdür.

    ⚠️ Bu test önce `startUpdateWatch()` ile `tryRuntimeUpdate` satırlarının BİTİŞİK olmasını
    şart koşuyordu ve araya bir yorum eklenince kırıldı (Başlat kapısı eklenirken oldu).
    Bitişiklik bir değişmez DEĞİL; asıl kural "boot'un ağ adımında çağrılıyor olması".
    """
    assert "startUpdateWatch()" in ui, "izleme başlatılmıyor"
    m = re.search(r"async function bootNetwork\(env\) \{(.*?)\n      \}", ui, re.S)
    assert m, "bootNetwork bulunamadı"
    assert "startUpdateWatch()" in m.group(1), "izleme boot'un ağ adımına bağlanmamış"


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


# ─────────────────────────────────────────────────────────────────────────────
# ÇEVRİMDIŞI AÇILIŞ — turun HİÇ başlamadığı yol (denetim 2026-08-23, bulgu C3)
# ─────────────────────────────────────────────────────────────────────────────


def _bootnetwork(ui: str) -> str:
    m = re.search(r"async function bootNetwork\(env\) \{(.*?)\n      \}", ui, re.S)
    assert m, "bootNetwork bulunamadı"
    return m.group(1)


def test_KRITIK_CEVRIMDISI_acilista_da_periyodik_tur_BASLAR(ui):
    """🔴 2026-08-16 düzeltmesinin AÇIK KALAN YARISI.

    `startUpdateWatch()` yalnız `bootNetwork`'ün BAŞARILI dalında (manifest geldikten sonra)
    çağrılıyordu. Çevrimdışı dal ise ondan ÖNCE `return` ediyor. Yani klinik PC'si açılış anında
    internetsizse (router dalgalanması yeterli) `guncellemeTimer` HİÇ kurulmuyor ve **ağ geri
    gelse bile** makine açık kaldığı sürece manifest bir daha çekilmiyordu: ne arka plan
    ön-indirmesi, ne bildirim, ne de `min_supported_version` GERİ ÇAĞIRMASI o cihaza ulaşıyordu.

    Hep-açık + açılışta-çevrimdışı, klinik makinesinin EN OLASI hâlidir — 2026-08-16'da kapatılan
    boşluğun tam olarak aynısı, bir dal ötede.

    ⚠️ Turu çevrimdışı dalda başlatmak güvenlidir: `recheckUpdates` ağ hatasını zaten sessizce
    yutuyor (`catch (_) { return; }`) ve `busy || !baseInstalled` kapısı duruyor.
    """
    g = _bootnetwork(ui)
    kesme = g.find("startKapisiAc();")
    assert kesme > 0, "çevrimdışı dal bulunamadı (startKapisiAc yok)"
    cevrimdisi_dal = g[: g.find("setOffline(false)")]
    assert "startUpdateWatch()" in cevrimdisi_dal, (
        "çevrimdışı açılışta periyodik güncelleme turu HİÇ başlatılmıyor → ağ geri gelse bile "
        "hep-açık makine manifesti bir daha çekmez (geri çağırma dahil ulaşmaz)"
    )


def test_cevrimdisi_dal_yine_de_ERKEN_DONER(ui):
    """Karşı-kanıt: turu eklemek çevrimdışı dalın akışını DEĞİŞTİRMEMELİ.

    Çevrimdışıyken manifest yoktur; dal `return` etmeye devam etmeli, yoksa aşağıdaki
    `manifestRaw = info.raw` tanımsız `info` üzerinde patlar.
    """
    g = _bootnetwork(ui)
    cevrimdisi_dal = g[: g.find("setOffline(false)")]
    assert "return;" in cevrimdisi_dal, "çevrimdışı dal erken dönüşü kaybetmiş"


# ─────────────────────────────────────────────────────────────────────────────
# LAUNCHER GÜNCELLEMESİ de duyurulur (denetim 2026-08-23, bulgular C7 + C4)
# ─────────────────────────────────────────────────────────────────────────────


def _tryselfupdate(ui: str) -> str:
    m = re.search(r"async function trySelfUpdate\(u\)\s*\{(.*?)\n      \}", ui, re.S)
    assert m, "trySelfUpdate bulunamadı"
    return m.group(1)


def test_KRITIK_periyodik_tur_LAUNCHER_guncellemesini_de_gorur(ui):
    """🔴 C7 — 6 saatlik tur YALNIZ runtime planına bakıyordu.

    `fetch_profiles` `update` alanını da döndürüyor (ve o alan YALNIZ gerçekten yeni bir launcher
    sürümü varsa dolar) ama `recheckUpdates` onu HİÇ okumuyordu. `trySelfUpdate` ise yalnız
    `bootNetwork` içinde, sayfa yüklenirken BİR KEZ koşuyor. Sonuç: haftalarca kapatılmayan klinik
    makinesinde yeni launcher yayını (rollout %100 olsa bile) ne uygulanır ne de BİLDİRİLİR —
    runtime için 2026-08-16'da kapatılan boşluğun launcher katmanındaki aynısı.

    ⚠️ ÇÖZÜM KURULUM DEĞİL BİLDİRİM: turun kendi sözleşmesi "güncelleme UYGULANMAZ; yalnız indirir
    ve bildirir" diyor (kurulum backend'i durdurur ve süren seansı keserdi). Bu yüzden burada
    aranan `trySelfUpdate` çağrısı DEĞİL, kullanıcıya bir bildirimdir.
    """
    g = _recheck(ui)
    assert "info.update" in g, (
        "periyodik tur launcher güncellemesini HİÇ değerlendirmiyor — hep-açık klinik makinesi "
        "yeni launcher yayınını ne alır ne duyar (bulgu C7)"
    )
    # ⚠️ Pencereyle değil DOĞRUDAN çağrıyla ölç: uzun açıklama yorumları ilk `info.update`
    # geçişini kaplıyor ve sabit genişlikli bir pencere yorumun içinde kalıyordu (ilk yazımda
    # doğru kodu yanlış-KIRMIZI gösterdi).
    assert "luReady" in g, "launcher güncellemesi görülüyor ama kullanıcıya SÖYLENMİYOR (bildirim metni çağrılmıyor)"
    assert re.search(r"if\s*\(info\.update", g), "bildirim gerçek bir koşula bağlı değil"
    # ⚠️ Kurulum YAPILMAMALI: tur sırasında yeniden başlatmak süren seansı keserdi.
    # ⚠️ ÇAĞRI biçimini ara, kelimeyi değil: açıklama yorumunda fonksiyonun ADI geçebilir
    # (ve geçiyor — ilk yazımda kendi yorumuma takıldı).
    assert "trySelfUpdate(" not in g, (
        "periyodik tur launcher KURULUMUNU tetikliyor — uygulama seans ortasında yeniden başlar "
        "(turun kendi sözleşmesi bunu yasaklıyor)"
    )


def test_KRITIK_otomatik_kurulum_kapaliyken_SESSIZ_kalinmaz(ui):
    """C4 — `auto === false` dalı hiçbir bildirim üretmeden `return false` yapıyordu.

    Oysa Rust tarafının yorumları bunun aksini iddia ediyor (`main.rs`: "`false` ise UI SESSİZ
    kurulumu ATLAR ama bildirimi gösterir"; `install.rs`: "bildirim kalır ama sessiz kurulum
    DURUR"). Gerçekte hiçbir yerde bildirim yoktu: deneme sınırı dolduğunda ya da rollout dilimi
    açılmamışken cihaz launcher güncellemesini bir daha ASLA otomatik almıyor ve kullanıcı bunu
    hiçbir yerden öğrenemiyordu — üstelik güncelleme zincirini YÖNETEN bileşen o.
    """
    g = _tryselfupdate(ui)
    i = g.find("u.auto === false")
    assert i > 0, "auto=false dalı bulunamadı"
    # Aynı gerekçe: pencere yerine dalın SONUNA kadar bak (yorumlar pencereyi yutuyordu).
    dal = g[i : i + 900]
    assert "luReady" in dal, (
        "otomatik kurulum kapalıyken kullanıcıya HİÇBİR ŞEY söylenmiyor — klinik, güncelleme "
        "zincirini yöneten bileşenin eski sürümde çakılı kaldığını öğrenemez (bulgu C4)"
    )


def test_launcher_bildirim_metni_IKI_DILDE(ui):
    assert ui.count("luReady:") == 2, "launcher güncelleme bildirimi iki dilde tanımlı değil"
