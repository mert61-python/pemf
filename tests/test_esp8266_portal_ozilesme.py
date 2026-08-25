# Author: mertaygn, cglrgrkn
"""ESP8266 WiFi PORTAL ÖZ-İYİLEŞME — YAPISAL KAPI (3. tur denetimi bulgu B2, 2026-08-24).

C bu Windows makinede DERLENEMEZ; davranışı test_esp8266_portal_ozilesme_model.py Python FSM'i
kanıtlar. Bu dosya C KAYNAĞININ o algoritmayı gerçekten taşıdığını doğrular (yorum-soyulmuş,
string-bilinçli c_soy ile — HEAD'de :136-137 yorumunda 'timeout' KELİMESİ geçiyor; çıplak arama
tuzağı, o yüzden KOD-token'larına + TAM İFADE'ye pinlenir).

Kapılar (HEAD'de KIRMIZI):
  (a) EDIT-2: update() portal bloğu SINIRLI timeout içerir (PORTAL_TIMEOUT + _portalStartTime +
      _hasSavedCredentials + _pendingWifiConnect muhafızları + softAPdisconnect sökme).
  (b) EDIT-1: _reconnectWiFi ilk-retry portal-açması _hasSavedCredentials ile KAPILI; tükenme
      dalı ayrıca _startWiFiPortal çağırır (reconnect gövdesinde ≥2 çağrı).
  (c) _hasSavedCredentials() gerçekten TANIMLI.
  (d) PLAN-A REGRESYON SENTİNELİ (yeşil kalır): öz-iyileşme yollarında PWM/bobin-durdurma YOK
      (ağ-kaybı→deadman sahip kararıyla REDDEDİLDİ).
"""

from __future__ import annotations

from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
NM = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp"


def _kaynak() -> str:
    return c_soy(NM.read_text(encoding="utf-8", errors="replace"))


def _update_portal_blok(soy: str) -> str:
    """update() portal bloğunu DAR çıpala: handleClient() → izleyen MQTT bölümü (lastMqttState)."""
    a = soy.index("_portalStatusServer.handleClient()")
    b = soy.index("lastMqttState", a)
    return soy[a:b]


def _reconnect_govde(soy: str) -> str:
    a = soy.index("void NetworkManager::_reconnectWiFi()")
    b = soy.index("bool NetworkManager::_tryConnectToSavedWiFi()", a)
    return soy[a:b]


# ── (a) EDIT-2: portal bloğu sınırlı timeout ───────────────────────────────────────────────────
def test_KRITIK_B2_portal_blogu_kredi_kapili_timeout_icerir():
    blok = _update_portal_blok(_kaynak())
    assert "PORTAL_TIMEOUT" in blok, (
        "update() portal bloğu PORTAL_TIMEOUT kapısı içermiyor — portal süresiz açık, hotspot dönse "
        "bile cihaz AP-only'de kilitli kalır (B2 EDIT-2)"
    )
    assert "_portalStartTime" in blok, "portal timeout _portalStartTime'a dayanmıyor"
    assert "_hasSavedCredentials" in blok, (
        "portal timeout kredi-kapılı DEĞİL — kredi yokken de portalı söker, ilk kurulum provizyonu bozulur"
    )
    assert "_pendingWifiConnect" in blok, (
        "portal timeout _pendingWifiConnect muhafızı içermiyor — kullanıcı submit ederken portal yankılanır"
    )
    assert "softAPdisconnect" in blok, "portal timeout dalında gerçek AP-sökme (softAPdisconnect) yok"


# ── (b) EDIT-1: ilk-retry kredi-kapılı + tükenmede portal ──────────────────────────────────────
def test_KRITIK_B2_ilk_retry_portal_kredi_kapili():
    govde = _reconnect_govde(_kaynak())
    k = govde.index("_wifiRetryCount == 1")
    # ilk-retry portal-açma koşulunu içeren dar dilim (koşuldan sonraki blok başına kadar)
    dilim = govde[k : govde.index("{", k) + 1]
    assert "_hasSavedCredentials" in dilim, (
        "ilk-retry portal-açması KOŞULSUZ (_hasSavedCredentials kapısı yok) — çalışırken-kopuşta "
        "kayıtlı ağlar denenmeden portal açılır, STA ölür, cihaz sonsuza AP-only (B2 EDIT-1 kök neden)"
    )


def test_KRITIK_B2_tukenmede_portal_acilir():
    govde = _reconnect_govde(_kaynak())
    n = govde.count("_startWiFiPortal(")
    assert n >= 2, (
        f"_reconnectWiFi gövdesinde yalnız {n} _startWiFiPortal çağrısı var — tükenme dalı (tüm "
        "kayıtlı ağlar başarısız) portalı AÇMIYOR; EDIT-1 ile ilk-retry açması ertelendiği için "
        "krediler bitince provizyon portalı hiç açılmaz (B2)"
    )


# ── (c) _hasSavedCredentials tanımlı ───────────────────────────────────────────────────────────
def test_KRITIK_B2_hasSavedCredentials_tanimli():
    ham = NM.read_text(encoding="utf-8", errors="replace")
    assert "bool NetworkManager::_hasSavedCredentials()" in ham, (
        "_hasSavedCredentials() tanımlı değil — EDIT-1/EDIT-2 kapıları çağıramaz"
    )


# ── (d) PLAN-A regresyon sentineli (yeşil kalır) ───────────────────────────────────────────────
def test_KARSIT_KANIT_B2_oz_iyilesme_yolunda_PWM_stop_yok():
    soy = _kaynak()
    blok = _update_portal_blok(soy)
    govde = _reconnect_govde(soy)
    for bolge, ad in ((blok, "portal-timeout"), (govde, "_reconnectWiFi")):
        for yasak in ("stopPWM", "coilStop", "_coilController", ".stopOutput", "safeStopCoils"):
            assert yasak not in bolge, (
                f"{ad} bölgesinde yasak çağrı '{yasak}' — ağ-kaybı→PWM/bobin durdurma sahip kararıyla "
                "REDDEDİLDİ (Plan-A deadman değişmezi); öz-iyileşme bobine DOKUNMAMALI"
            )


def test_KARSIT_KANIT_B2_wifi_slot_kapasitesi_degismedi():
    """B2 çakışmayı slot daraltarak 'çözmemeli'; 5-ağ kapasitesi ve manuel stride korunmalı."""
    ham = (KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.h").read_text(encoding="utf-8", errors="replace")
    assert "MAX_WIFI_CREDENTIALS = 5" in ham, "kayıtlı-ağ kapasitesi 5'ten düşürülmüş (kapasite regresyonu)"
