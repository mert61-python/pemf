# -*- coding: utf-8 -*-
"""I18N-P1 · SUNUCU 10b (KRİTİK) — ana sunucu bildirimleri İKİ DİLLİ + HTTP iletileri istek dilinde.

Bildirim arka plan iş parçacığında doğar (MQTT / STM seri / bekçi) → dili o an bilinmez: `_bildir(uret)` iki dilde üretir;
`message` HER ZAMAN Türkçe (bayt bayt eski metin — eski istemci / günlük / denetim), `mesajlar` = {tr, en} (arayüz kendi dilini seçer).
Sunucu metnine göre dallanma YOK (KURALLAR §4.9): arayüz `mesajlar` alanına bakar, yoksa `message`e düşer.

GERÇEK: `live_state._bildir` + `api_server._bildir_teyitsiz_stop` + `_on_mqtt_disconnect_api` + gerçek uçlar (TestClient); sahte yalnız WS yayını yakalayıcı.
⚠️ Beklenen Türkçe metinler BURADA sabittir (üründen okunmaz; eski f-string çıktısıdır). MUTASYON: katalog TR değeri değişirse / `ceviri.t` ham metne
dönerse / `_bildir` `mesajlar`ı düşürürse KIRMIZI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

# (anahtar, parametreler, ESKİ Türkçe çıktı — bayt bayt)
BILDIRIMLER = [
    ("bildirim.alanKaydiYazildi", {"name": "a.csv"}, "📄 Seans alan kaydı masaüstüne yazıldı: a.csv"),
    ("bildirim.alanKaydiBasladi", {"yol": "C:\\x\\a.csv"}, "📄 Seans alan kaydı başladı: C:\\x\\a.csv"),
    ("bildirim.alanKaydiAcilamadi", {}, "⚠️ Seans alan kaydı (CSV) açılamadı — tedavi etkilenmedi"),
    ("bildirim.sistemBaglandi", {}, "Sistem bağlantısı kuruldu"),
    ("bildirim.sistemKesildi", {}, "Sistem bağlantısı kesildi"),
    (
        "bildirim.aiProPlandanCikti",
        {"coil": 3},
        "Bobin 3 AI Pro planından çıkarıldı — operatör durdurdu; seans sonuna kadar AI Pro bu bobini sürmez, diğer bobinler sürüyor.",
    ),
    (
        "bildirim.telemetriYanitYokStop",
        {"coil": 7},
        "⚠️ Bobin 7 telemetrisi yanıt vermiyor — bağlantı kesildi sayıldı, STOP gönderildi",
    ),
    (
        "bildirim.telemetriYanitYokStopYok",
        {"coil": 7},
        "⚠️ Bobin 7 telemetrisi yanıt vermiyor — bağlantı kesildi sayıldı; STOP GÖNDERİLEMEDİ (broker erişilemiyor) — bobin HÂLÂ ENERJİLİ olabilir, elle kontrol edin",
    ),
    (
        "bildirim.asiriSicaklik",
        {"coil": 6, "atype": "overtemp"},
        "🌡️ Bobin 6 kartı AŞIRI SICAKLIK bildirdi (overtemp) — yalnız bobin 6 durduruldu; diğer bobinler sürüyor. Bobini kontrol edin.",
    ),
    ("bildirim.stopDogrulanamadiEk", {}, " ⚠️ Bu bobinin STOP'u DOĞRULANAMADI."),
    ("bildirim.selfTestBasarisiz", {"coil": "2", "ayrinti": "ADC"}, "🚨 Bobin 2 self-test BAŞARISIZ — ADC"),
    ("bildirim.selfTestGecti", {"coil": "2"}, "Bobin 2 self-test: geçti"),
    ("bildirim.selfTestAtlandi", {"coil": "2"}, "Bobin 2 self-test: atlandı (PWM pasif)"),
    (
        "bildirim.termalKesme",
        {"coil": "4", "ayrinti": " (61.2C)"},
        "🔥 Bobin 4 YEREL TERMAL KESME — PWM cihaz tarafından durduruldu (61.2C); 45°C altına soğuyunca start serbest",
    ),
    (
        "bildirim.termalKesme",
        {"coil": "4", "ayrinti": ""},
        "🔥 Bobin 4 YEREL TERMAL KESME — PWM cihaz tarafından durduruldu; 45°C altına soğuyunca start serbest",
    ),
    ("bildirim.termalKilit", {"coil": "4", "ayrinti": ""}, "⚠️ Bobin 4 sıcak: start reddedildi — soğuması bekleniyor"),
    ("bildirim.termalSogudu", {"coil": "4"}, "✅ Bobin 4 soğudu — start yeniden serbest"),
    ("bildirim.komutReddetti", {"coil": "4", "sebep": "CRC"}, "⚠️ Bobin 4 komutu REDDETTİ — CRC"),
    ("bildirim.sebepYok", {}, "sebep bildirilmedi"),
    ("bildirim.bobinKesildi", {"coil": "6"}, "⚠️ Bobin 6 bağlantısı kesildi"),
    ("bildirim.bobinBaglandi", {"coil": "6"}, "✅ Bobin 6 bağlandı"),
    (
        "bildirim.bobinAlarm",
        {"coil": "6", "atype": "overcurrent"},
        "🚨 Bobin 6 ALARM (overcurrent) — seans güvenlik için durduruldu",
    ),
    (
        "bildirim.mandalStmKopma",
        {},
        '🔒 Bobin çalışırken STM32 bağlantısı koptu — ACİL DURDUR mandalı kuruldu. Bobinleri kontrol edin; yeniden başlatmak için önce "Sıfırla".',
    ),
    (
        "bildirim.mandalStmWatchdog",
        {},
        '🔒 Bobin çalışırken STM32 watchdog zaman aşımı — ACİL DURDUR mandalı kuruldu. Bobinleri kontrol edin; yeniden başlatmak için önce "Sıfırla".',
    ),
    ("bildirim.stmKoptuSeansDurdu", {}, "⚠️ STM32 bağlantısı koptu — seans güvenlik için durduruldu"),
    (
        "bildirim.akimGuvenilmez",
        {"coil": 2},
        "⚠️ Bobin 2: Akım ölçümü bu bobinde güvenilir değil — doz kaydına akım yazılmadı.",
    ),
    (
        "bildirim.mlxDustu",
        {"coil": 6},
        # ODD B-6 (ODK-B 18-11): "Bobin 6 manyetik alan sensörü" → "Alan sensörü (MLX, kartta kanal 6)" (TR DEĞİŞTİ — bulgunun kendisi)
        "⚠️ Alan sensörü (MLX, kartta kanal 6) veri göndermiyor — kart sensörü yeniden arıyor. Düzelmezse sensör kablosunu çıkarıp "
        "yeniden takın ya da kartın gücünü kesip yeniden bağlayın.",
    ),
    (
        "bildirim.mlxGeriGeldi",
        {"coil": 6},
        "Alan sensörü (MLX, kartta kanal 6) yeniden bağlandı — alan ölçümü sürüyor.",
    ),
    (
        "bildirim.alanDogrulanamadi",
        {"coil": 2},
        # Y306 (madde 6, TR DEĞİŞTİ): MLX bir bobinin değil KABİNİN sensörü — "Bobin N alan sensörü" → "Kabin sensörü (MLX, kartta kanal N)".
        "⚠️ Kabin sensörü (MLX, kartta kanal 2) doğrulanamadı — ölçülen alan (mT) gösterilmiyor ve kayda yazılmıyor. Teknik desteğe bildirin (kod: FW-ALAN).",
    ),
    (
        "bildirim.alanDoygun",
        {"coil": 2},
        "⚠️ Kabin sensörünün (MLX, kartta kanal 2) ölçtüğü alan sensör aralığını AŞTI (±24,6 mT) — gösterilen mT GÜVENİLMEZ (taşma sarar, değer DÜŞÜK görünebilir)",
    ),
    ("bildirim.stmWatchdogSeansDurdu", {}, "⚠️ STM32 watchdog zaman aşımı — seans güvenlik için durduruldu"),
    (
        "bildirim.stmWatchdogSeanssiz",
        {},
        "⚠️ STM32 watchdog zaman aşımı — bobin çıkışları durduruldu (aktif seans yoktu)",
    ),
    (
        "bildirim.teyitsizStop",
        {"kaynak": "Sahipsiz bobin durdurması", "bobinler": [2, 5]},
        "⚠️ Sahipsiz bobin durdurması: bobin(ler) [2, 5] için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da bobinleri elle kontrol edin.",
    ),
    (
        "bildirim.startReddedildiSonraki",
        {"coil": 7},
        "⚠️ Bobin 7: önceki start komutu reddedildi — sonraki komut geçerli; durumu panelden doğrulayın",
    ),
    ("bildirim.startReddedildi", {"coil": 7}, "⚠️ Bobin 7: start komutu cihaz tarafından REDDEDİLDİ — bobin ÇALIŞMIYOR"),
    ("bildirim.kosuKaydiDuzeltildi", {}, "; koşu kaydı düzeltildi"),
    (
        "bildirim.startOnayYok",
        {"coil": 7},
        "⚠️ Bobin 7: start onayı gelmedi — bobinin gerçekten çalıştığını panelden kontrol edin",
    ),
    (
        "bildirim.estopEspReddetti",
        {"coil": 7},
        "⚠️ Bobin 7: acil durdurma komutu ESP tarafından REDDEDİLDİ — bobini elle kontrol edin",
    ),
    ("bildirim.estopEspOnayYok", {"coil": 7}, "⚠️ Bobin 7: acil durdurma ESP onayı GELMEDİ — bobini elle kontrol edin"),
    (
        "bildirim.beklenmedikCalisiyordu",
        {"coil": 7},
        "⚠️ Bobin 7 beklenmedik şekilde çalışıyordu — güvenlik durdurması gönderildi",
    ),
    ("bildirim.acilDurdurUygulandi", {}, "Acil durdurma uygulandı"),
    (
        "bildirim.kapanisMandal",
        {},
        '🔒 Uygulama seans / bobin çalışırken kapatıldı — bobinler durduruldu, ACİL DURDUR mandalı kuruldu. Yeniden başlatmadan önce bobinleri kontrol edin ve "Sıfırla".',
    ),
    (
        "bildirim.mandalSifirlandi",
        {},
        "Acil durdurma mandalı SIFIRLANDI — bobinler başlatılmadı; tedavi için başlatmayı ayrıca verin.",
    ),
    (
        "donanim.uyari.fazSenkron",
        {"hz": 120.0, "coil": 6, "esp_freq": 2.0},
        "STM bobin-1 120.0 Hz çalışırken bobin 6 için 2.0 Hz istendi (≥50× ayrışma) — faz senkronu kilitlenmez, S3 DC-koruma latch'i devreye girebilir. Faz gerekmiyorsa sorun değil; gerekiyorsa frekansları yaklaştırın.",
    ),
    (
        "donanim.uyari.fazSenkronKisa",
        {"hz": 120.0, "coil": 6, "esp_freq": 2.0},
        "STM bobin-1 120.0 Hz çalışırken bobin 6 için 2.0 Hz istendi (≥50× ayrışma) — faz senkronu kilitlenmez.",
    ),
    (
        "seans.uyari.espErisilemez",
        {"esp_coils": [6, 7]},
        "Sistem bağlantısı yok — ESP bobinleri [6, 7] aktif OLMAYABİLİR (STM bobinleri çalışıyor).",
    ),
    (
        "seans.uyari.stopDogrulanamadi",
        {"bobinler": "1, 2"},
        "Bobin 1, 2 için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın.",
    ),
    (
        "seans.hata.stopDogrulanamadi",
        {"neden": "Seans hazırlığı sırasında hata oluştu; seans BAŞLATILMADI"},
        "Seans hazırlığı sırasında hata oluştu; seans BAŞLATILMADI. Sürülen bobinlerin STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. ACİL DURDUR'a basın ya da cihazın fiziksel güç düğmesini kullanın.",
    ),
    ("seans.hata.nedenVe", {"neden": "A", "ek": "b"}, "A ve b"),
    ("seans.hata.hazirlikNeden", {}, "Seans hazırlığı sırasında hata oluştu; seans BAŞLATILMADI"),
    ("seans.hata.hazirlikEk", {}, "bobinlere STOP gönderildi. Yeniden deneyin; sürerse teknik desteğe başvurun."),
    ("seans.hata.surusNeden", {}, "Bobin sürüşü sırasında hata oluştu; seans BAŞLATILMADI"),
    ("seans.hata.surusEk", {}, "sürülen bobinler durduruldu. Bağlantıyı kontrol edip yeniden deneyin."),
    (
        "seans.hata.sifirHz",
        {},
        "Frekans 0 Hz = DURDURMA (A-05): bobinler durduruldu, seans BAŞLATILMADI. Frekans girin.",
    ),
    (
        "seans.hata.kayitAcilamadi",
        {},
        "Tedavi kaydı açılamadı — seans BAŞLATILMADI; birkaç saniye sonra yeniden deneyin",
    ),
    (
        "seans.hata.kayitDbAcilamadi",
        {},
        "Tıbbi kayıt veritabanı açılamadı; seans başlatılamaz. Tedavi kaydı tutulamayacağı için işlem güvenli değildir. Cihazı yeniden başlatın, sorun sürerse teknik desteğe başvurun.",
    ),
    ("seans.hata.kayitDbNeden", {"sebep": "göç"}, " Neden: göç"),
    ("seans.hata.baslatilamazNeden", {"sebep": "Disk boş alanı kritik"}, "Seans başlatılamaz: Disk boş alanı kritik"),
    ("seans.hata.guncellemeSuruyor", {}, "Güncelleme uygulanıyor; işlem bitene kadar yeni seans başlatılamaz."),
    ("seans.hata.zatenAktif", {}, "Zaten aktif bir seans var."),
    ("seans.hata.baslatmaSurerkenDurduruldu", {}, "Seans başlatma sürerken durduruldu; bu seans BAŞLATILMADI."),
    ("seans.mesaj.baslatmaDurduruldu", {}, "Seans başlatma sırasında durduruldu (bobinler açılmadı)."),
    ("seans.mesaj.aktifYokStop", {}, "Aktif seans yok. Çalışan bobin kalmasın diye STOP gönderildi."),
    ("seans.mesaj.durduruldu", {}, "Seans durduruldu."),
    ("sistem.hata.kapanisYalnizYerel", {}, "Kapanış durdurması yalnız bu bilgisayardaki launcher'dan çağrılabilir."),
    ("sistem.hata.kapanisJson", {}, 'Kapanış durdurması JSON gövde ister: {"onay": true}.'),
    ("sistem.hata.kapanisOnay", {}, 'Kapanış durdurması onay ister: {"onay": true}.'),
    ("sistem.hata.sifirlaJson", {}, 'Sıfırla yalnız JSON gövdeyle yapılabilir: {"onay": true}.'),
    ("sistem.hata.sifirlaOnay", {}, 'Sıfırla bilinçli onay ister: {"onay": true}.'),
    ("donanim.hata.sayiGecersiz", {"ad": "duty"}, "Geçersiz 'duty': sonlu bir sayı olmalı."),
    (
        "donanim.hata.tamSayiGecersiz",
        {"ad": "coil_id", "alt": 1, "ust": 8},
        "Geçersiz 'coil_id': 1..8 arasında TAM sayı olmalı.",
    ),
    (
        "donanim.hata.unipolarDizisi",
        {"n": 5, "ilk": 1, "son": 5, "gelen": 3},
        "unipolar dizisi 5 elemanli olmali (bobin 1-5), 3 geldi",
    ),
    ("hata.beklenmeyen", {}, "Sunucu hatası (beklenmeyen)."),
    ("hata.gecersizIstek", {}, "Geçersiz istek verisi."),
    ("hata.authKatmani", {}, "Auth katmani kullanilamiyor"),
    ("hata.apiAnahtari", {}, "Gecersiz veya eksik API anahtari (X-API-Key)"),
    ("hata.cokIstek", {}, "Cok fazla istek, biraz bekleyin"),
    ("pdf.ai.baslik", {"modul": "Petri"}, "Yapay Zekâ Analizi — Petri"),
    ("pdf.ai.rapor", {}, "YAPAY ZEKÂ ANALİZ RAPORU"),
    ("pdf.ai.ozet", {}, "Hayvan sahibi ve veteriner hekim için özet"),
    ("pdf.ai.dipnot", {}, "Bu rapor PEMF Vet uygulamasında yapay zekâ ile oluşturuldu."),
    (
        "yedek.hata.geriYuklemeSuruyor",
        {},
        "Geri yükleme bu cihazda sürüyor — bitince kayıtlar görünür. İşlemi tekrarlamayın ve uygulamayı yeniden başlatmayın; birkaç dakika sonra Seans Geçmişi'ni yenileyin.",
    ),
    (
        "yedek.hata.seansSurerkenGeriYukleme",
        {},
        "Tedavi seansı sürüyor — geri yükleme cihazdaki tüm tedavi kayıtlarını değiştirir (süren seansın kaydı da silinirdi); önce seansı durdurun. Hiçbir kayıt değişmedi.",
    ),
    (
        "yedek.hata.geriYuklemeOnay",
        {},
        'Bu cihazda zaten kayıt var. Geri yükleme bu cihazdaki TÜM tedavi kayıtlarını (seanslar, bobin koşuları, sensör verisi, seans olayları, AI analizleri) SİLER ve yedektekilerle değiştirir. Hasta kartları SİLİNMEZ: yedekte olmayan hastaların kartı kalır ama bu cihazdaki seans ve analiz geçmişleri silinir. Onaylamak için {"confirm":"REPLACE_ALL"} gönderin.',
    ),
    (
        "yedek.uyari.yedekteOlmayan",
        {"count": 3},
        "Yedekte olmayan 3 hastanın kartı korundu; bu hastaların bu cihazdaki seans ve analiz geçmişi geri yüklemeyle silindi (yedekte yoktu).",
    ),
    (
        "yedek.uyari.kartAktarilamadi",
        {"count": 2},
        "2 hastanın kartı içe aktarılamadı (hasta veritabanı yazılamadı) — tedavi geçmişi geri yüklendi ama bu hastaların kartı yok; sorun giderilince aynı yedeği yeniden geri yükleyin.",
    ),
]


@pytest.mark.parametrize(
    "anahtar,parametre,eski_tr", BILDIRIMLER, ids=[f"{b[0]}-{i}" for i, b in enumerate(BILDIRIMLER)]
)
def test_TR_bayt_bayt_eski_metin_EN_ingilizce(anahtar, parametre, eski_tr):
    from utils import ceviri

    assert ceviri.t(anahtar, dil="tr", **parametre) == eski_tr
    en = ceviri.t(anahtar, dil="en", **parametre)
    assert en != eski_tr or not TR_HARF.search(eski_tr)
    # İngilizce metinde Türkçe harf KALMAZ (parametre değerleri hariç — burada TR parametre yok)
    sadece_metin = en
    for v in parametre.values():
        sadece_metin = sadece_metin.replace(str(v), "")
    assert not TR_HARF.search(sadece_metin), (anahtar, en)


def test_kritik_ACIL_DURDUR_ve_STOP_cumleleri_iki_dilde_ayni_anlami_tasir():
    from utils import ceviri

    for anahtar, parametre in (
        ("bildirim.teyitsizStop", {"kaynak": "x", "bobinler": [1]}),
        ("seans.uyari.stopDogrulanamadi", {"bobinler": "1"}),
        ("seans.hata.stopDogrulanamadi", {"neden": "x"}),
    ):
        assert "ACİL DURDUR'a basın" in ceviri.t(anahtar, dil="tr", **parametre)
        en = ceviri.t(anahtar, dil="en", **parametre)
        assert "Press EMERGENCY STOP" in en and "could NOT be VERIFIED" in en and "STILL BE RUNNING" in en
    # mandal bildirimleri: "Sıfırla" ↔ arayüzdeki "Reset" düğmesi
    for anahtar in ("bildirim.mandalStmKopma", "bildirim.mandalStmWatchdog", "bildirim.kapanisMandal"):
        assert '"Sıfırla"' in ceviri.t(anahtar, dil="tr")
        en = ceviri.t(anahtar, dil="en")
        assert '"Reset"' in en and "EMERGENCY STOP latch" in en
    assert "RESET" in ceviri.t("bildirim.mandalSifirlandi", dil="en") and "emergency stop latch" in ceviri.t(
        "bildirim.mandalSifirlandi", dil="en"
    )
    assert ceviri.t("bildirim.acilDurdurUygulandi", dil="en") == "Emergency stop applied"


# ── zarf: `_bildir` → `message` TR + `mesajlar` {tr, en} ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def yayin(monkeypatch):
    from servers import live_state

    giden = []
    monkeypatch.setattr(live_state, "_ws_broadcast_sync", lambda m: giden.append(m))
    yield giden


def test_bildir_message_Turkce_mesajlar_iki_dilde(yayin):
    from servers import live_state
    from utils import ceviri

    live_state._bildir(lambda d: ceviri.t("bildirim.sistemKesildi", dil=d), "warning")
    (m,) = yayin
    assert m["type"] == "notification"
    n = m["data"]
    assert n["message"] == "Sistem bağlantısı kesildi" and n["level"] == "warning"
    assert n["mesajlar"] == {"tr": "Sistem bağlantısı kesildi", "en": "System connection lost"}
    # canlı durumdaki kayıt da aynı zarfı taşır (yeni WS bağlantısının ilk anlık görüntüsü)
    assert live_state._live_state["notifications"][0]["mesajlar"]["en"] == "System connection lost"


def test_eski_cagri_mesajlar_olmadan_ayni_zarf(yayin):
    from servers import live_state

    live_state._push_notification("düz metin", "info")
    n = yayin[0]["data"]
    assert n["message"] == "düz metin" and "mesajlar" not in n


def test_mqtt_kopma_bildirimi_gercek_islevden_iki_dilde(yayin):
    from servers import api_server

    api_server._on_mqtt_disconnect_api(None, None, 1)
    n = yayin[0]["data"]
    assert n["message"] == "Sistem bağlantısı kesildi"
    assert n["mesajlar"]["en"] == "System connection lost"


def test_teyitsiz_stop_bildirimi_kaynak_iki_dilde_gunluk_TR(yayin):
    from servers import api_server
    from utils import ceviri

    api_server._bildir_teyitsiz_stop([5, 2], lambda d: ceviri.t("bildirim.kaynak.sureDoldu", dil=d))
    n = yayin[0]["data"]
    assert n["level"] == "error"
    assert n["message"] == (
        "⚠️ Süre doldu — otomatik durdurma: bobin(ler) [2, 5] için donanım STOP'u DOĞRULANAMADI — HÂLÂ ÇALIŞIYOR olabilirler. "
        "ACİL DURDUR'a basın ya da bobinleri elle kontrol edin."
    )
    assert n["mesajlar"]["tr"] == n["message"]
    assert n["mesajlar"]["en"] == (
        "⚠️ Time is up — automatic stop: the hardware STOP could NOT be VERIFIED for coil(s) [2, 5] — they may STILL BE RUNNING. "
        "Press EMERGENCY STOP or check the coils by hand."
    )
    # düz metin kaynak (eski çağıran) de çalışır
    yayin.clear()
    api_server._bildir_teyitsiz_stop([1], "Elle kaynak")
    assert yayin[0]["data"]["message"].startswith("⚠️ Elle kaynak: bobin(ler) [1]")
    # boş liste SESSİZ
    yayin.clear()
    api_server._bildir_teyitsiz_stop([], "x")
    assert yayin == []


# ── gerçek uçlar: istek dili ─────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


def test_dogrulama_zarfi_ve_donanim_hazir_degil_istek_dilinde(istemci):
    # 422 doğrulama zarfı (ara katman dışı işleyici → dil `istekten_dil`)
    tr = istemci.post("/api/session/start", json={"frequency": "abc"})
    assert tr.status_code == 422 and tr.json()["detail"] == "Geçersiz istek verisi."
    en = istemci.post("/api/session/start", json={"frequency": "abc"}, headers={"X-PEMF-Dil": "en"})
    assert en.status_code == 422 and en.json()["detail"] == "The request data is invalid."
    # Accept-Language YOK SAYILIR (KURALLAR §4.9)
    al = istemci.post("/api/session/start", json={"frequency": "abc"}, headers={"Accept-Language": "en-US"})
    assert al.json()["detail"] == "Geçersiz istek verisi."


def test_ara_katman_json_govdesi_TR_bayt_bayt_ayni():
    from servers import api_server
    from utils import ceviri

    assert api_server._json_detay(ceviri.t("hata.authKatmani", dil="tr")) == '{"detail":"Auth katmani kullanilamiyor"}'
    assert (
        api_server._json_detay(ceviri.t("hata.apiAnahtari", dil="tr"))
        == '{"detail":"Gecersiz veya eksik API anahtari (X-API-Key)"}'
    )
    assert api_server._json_detay(ceviri.t("hata.cokIstek", dil="tr")) == '{"detail":"Cok fazla istek, biraz bekleyin"}'
    assert (
        api_server._json_detay(ceviri.t("hata.apiAnahtari", dil="en"))
        == '{"detail":"Invalid or missing API key (X-API-Key)"}'
    )


def test_sabit_mesaj_islevleri_istek_dilinde():
    from servers import api_server
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set("en")
    try:
        assert api_server.sifir_hz_seans_mesaji().startswith("Frequency 0 Hz = STOP (A-05)")
        assert "NOT STARTED" in api_server.kayit_acilamadi_mesaji()
        assert "restore" in api_server.geri_yukleme_suruyor()
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert api_server.sifir_hz_seans_mesaji().startswith("Frekans 0 Hz = DURDURMA (A-05)")


# ── STM kart reddi ailesi: duty reddi metni (TR bayt bayt; EN İngilizce; mandal EYLEMİ Türkçe KALIR) ─────────────────────────────────


def _nack(bobin, istenen, tavan, kip):
    return f"-> STM_NACK: RANGE coil={bobin} field=duty value_milli={istenen} max_milli={tavan} kip={kip}"


def test_duty_reddi_metni_TR_bayt_bayt_EN_ingilizce():
    from servers import live_state as ls

    m = _nack(1, 800, 500, "bipolar")
    assert ls.stm_duty_reddi_metni(m, dil="tr") == (
        "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. "
        "Duty'yi %50 veya altına indirip yeniden başlatın (ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın)."
    )
    assert ls.stm_duty_reddi_metni(m, "seans DURDURULDU", sifirla=True, dil="tr") == (
        "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi; seans DURDURULDU. "
        "Duty'yi %50 veya altına indirin (ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın), sonra 'Sıfırla'ya basın ve yeniden başlatın."
    )
    assert ls.stm_duty_reddi_metni(_nack(6, 1255, 1000, "unipolar"), dil="tr") == (
        "Bobin 6 tek yönlü kipte en fazla %100 çalışabilir; %125,5 kabul edilmedi. Duty'yi %100 veya altına indirip yeniden başlatın."
    )
    assert ls.stm_duty_reddi_metni(m, "the session was STOPPED", sifirla=True, dil="en") == (
        "Coil 1 can run at most 50% in two-way mode; 80% was not accepted; the session was STOPPED. "
        "Lower the duty to 50% or below (or set this coil to Unipolar in ⚡ Drive Mode), then press 'Reset' and start again."
    )
    # ondalık ayracı dile göre: TR virgül, EN nokta
    assert "125.5%" in ls.stm_duty_reddi_metni(_nack(6, 1255, 1000, "unipolar"), dil="en")
    assert ls.stm_duty_reddi_metni("-> STM_NACK: CRC", dil="en") == ""


def test_duty_reddi_mandal_EYLEMI_istek_dili_EN_olsa_da_TURKCE_kalir():
    """`_stm_red_aktif_seansi_durdur` mandal eylemini `dil="tr"` ile alır: yazı DEĞİŞMEZ (ACİL DURDUR mandal bandı)."""
    from servers import live_state as ls
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set("en")
    try:
        assert ls.stm_duty_reddi_metni(_nack(1, 800, 500, "bipolar"), sifirla=True, dil="tr").startswith(
            "Bobin 1 çift yönlü kipte"
        )
        assert ls.stm_duty_reddi_metni(_nack(1, 800, 500, "bipolar"), sifirla=True).startswith(
            "Coil 1 can run at most"
        )  # dil yok = etkin dil
    finally:
        ceviri.istek_dili_var.reset(jeton)
    import inspect

    from servers import api_server

    kaynak = inspect.getsource(api_server._stm_red_aktif_seansi_durdur)
    assert 'stm_duty_reddi_metni(ham, sifirla=True, dil="tr")' in kaynak, "mandal EYLEM metni Türkçe'ye sabitlenmemiş"
    assert "_duty_eylem or STM_RED_MESAJI" in kaynak, "mandal eylem yedeği (sabit TR) değişmiş"


def test_duty_reddi_bildirimi_STM_seri_is_parcaciginda_iki_dilde(yayin, monkeypatch):
    from servers import api_server

    monkeypatch.setattr(api_server.state, "hardware", None, raising=False)
    # seansız ilk kez: bildirim = duty metni + "STM bobin çıkışları durduruldu" (durdurulamadıysa sonuç eki YOK)
    monkeypatch.setattr(api_server, "_stm_red_aktif_seansi_durdur", lambda ham: False)
    monkeypatch.setattr(api_server, "_stm_nack_bastir", lambda ham: False)
    api_server._stm_duty_reddini_isle(_nack(1, 800, 500, "bipolar"), True)
    n = yayin[0]["data"]
    assert n["message"].startswith(
        "⛔ Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. Duty'yi %50 veya altına indirip"
    )
    assert n["mesajlar"]["en"].startswith(
        "⛔ Coil 1 can run at most 50% in two-way mode; 80% was not accepted. Lower the duty to 50%"
    )
    assert n["level"] == "error"


def test_komut_red_metni_TR_sabitle_AYNI_EN_ingilizce():
    from utils import ceviri, stm32_kimlik

    assert ceviri.t("firmware.komutRed", dil="tr") == stm32_kimlik.KOMUT_RED_METNI  # tek kaynak çifti (sabit ↔ katalog)
    assert stm32_kimlik.komut_red_metni("tr") == stm32_kimlik.KOMUT_RED_METNI
    en = stm32_kimlik.komut_red_metni("en")
    assert "FW-PAKET" in en and "technical support" in en and not TR_HARF.search(en)


def test_firmware_uyumsuz_seans_reddi_istek_dilinde(monkeypatch):
    """Gerçek uç yolu değil, işlev: `stm_red_mesaji` + 409 gövdeleri."""
    from servers import api_server
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set("en")
    try:
        assert api_server.stm_red_mesaji().startswith("The device board is rejecting commands")
        assert ceviri.t("seans.hata.baslatilmadiNeden", neden=api_server.stm_red_mesaji()).startswith(
            "The session was NOT STARTED: The device board"
        )
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert api_server.stm_red_mesaji() == api_server.STM_RED_MESAJI
