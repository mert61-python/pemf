# Author: mertaygn, cglrgrkn
"""ESP8266 WiFi PORTAL ÖZ-İYİLEŞME — 3. tur denetimi bulgu B2 (2026-08-24).

ÖLÇÜLEN DURUM: çalışırken-kopuş (running-disconnect) yolunda _reconnectWiFi(), kayıtlı ağları
DENEMEDEN ilk yeniden-denemede KOŞULSUZ portal açıyor (WiFi.mode(WIFI_AP) → STA ölür). Portal
timeout'u da bilerek kaldırıldığından (:136-137), hotspot ~40 sn düşüp geri gelse bile cihaz
SONSUZA DEK AP-only'de kilitli kalıyor: reconnect `!_portalActive` ile kapılı → STA bir daha
denenmez. Klinikte hotspot/gateway PC reboot'unda coil sessizce çevrimdışı kalır.

DÜZELTME (S3-paritesi): (EDIT-1) ilk retry'de portal açmayı kayıtlı-kredi kontrolüne kapıla —
kayıtlı ağ VARSA önce onları dene; YOKSA (ilk kurulum) portalı hemen aç. Krediler GERÇEKTEN
tükenince portalı aç. (EDIT-2) SINIRLI portal-timeout'u geri koy — ama YALNIZ kayıtlı kredi
varken; kredi yokken portal süresiz açık kalır (sahip kararı korunur). Kullanıcı submit ederken
(_pendingWifiConnect) portal sökülmez.

Bu dosya 8266 reconnect FSM'ini Python'a taşır (buggy HEAD `bug=True` + fixed `bug=False`) ve
zaman-çizgisi + hotspot-müsaitliği(t) sürerek buggy'nin sonsuza dek offline, fixed'in sınırlı
sürede CONNECTED olduğunu KANITLAR. C'nin bu algoritmayı gerçekten taşıdığını yapısal kapı
(test_esp8266_portal_ozilesme.py) ayrı doğrular.
"""

from __future__ import annotations

from typing import Callable


class Esp8266WifiFsm:
    """firmware/esp8266_pemf_coil/NetworkManager.cpp update()+_checkWiFiConnection()+_reconnectWiFi()
    WiFi durum-makinesinin davranışsal Python modeli (1 sn = 1 tick).

    bug=True  → HEAD semantiği (ilk retry KOŞULSUZ portal + portal timeout YOK).
    bug=False → düzeltme (EDIT-1 kayıtlı-kredi kapısı + EDIT-2 kredi-kapılı portal timeout).

    Aşırı-düzeltme mutasyonu için iki muhafız ayrı kapatılabilir:
      edit2_saved_guard=False   → kredi YOKKEN de portal timeout ateşler (provizyon bozulur).
      edit2_pending_guard=False → kullanıcı submit ederken portal yankılanır.
    """

    WIFI_CONNECT_TIMEOUT = 30  # C: WIFI_CONNECT_TIMEOUT (30 sn)
    PORTAL_TIMEOUT = 300  # C: PORTAL_TIMEOUT (5 dk)

    def __init__(
        self,
        *,
        saved_count: int,
        hotspot: Callable[[int], bool],
        bug: bool = False,
        start_connected: bool = False,
        edit2_saved_guard: bool = True,
        edit2_pending_guard: bool = True,
    ):
        self.saved = saved_count  # geçerli kayıtlı kredi sayısı
        self.hotspot = hotspot  # callable(t)->bool: kayıtlı ağ o an erişilebilir mi
        self.bug = bug
        self.edit2_saved_guard = edit2_saved_guard
        self.edit2_pending_guard = edit2_pending_guard

        self.t = 0
        self.connected = start_connected
        self.portal_active = False
        self.portal_start = 0
        self.wifi_state = "IDLE"  # IDLE | CONNECTING
        self.retry_count = 0
        self.cred_index = 0
        self.connect_start = 0
        self.pending = False  # _pendingWifiConnect
        # boot firstConnectionAttempt: yalnız bağlı-değil başlarsak anlamlı
        self.first_attempt = not start_connected
        self.portal_opened_ever = False
        self.teardown_count = 0  # portal timeout kaç kez portalı söktü (churn ölçer)

    # --- yardımcılar ---
    def _has_saved(self) -> bool:
        return self.saved > 0

    def _open_portal(self):
        # _startWiFiPortal(): WiFi.mode(WIFI_AP) STA'yı öldürür
        self.portal_active = True
        self.portal_start = self.t
        self.portal_opened_ever = True
        self.connected = False

    def _begin_connecting(self):
        self.wifi_state = "CONNECTING"
        self.connect_start = self.t
        self.cred_index = 0

    # --- update() bir tick ---
    def update(self):
        # (1) portal bloğu — EDIT-2 kredi-kapılı timeout
        if self.portal_active and not self.bug:
            pend_ok = (not self.pending) if self.edit2_pending_guard else True
            saved_ok = self._has_saved() if self.edit2_saved_guard else True
            if pend_ok and saved_ok and (self.t - self.portal_start) >= self.PORTAL_TIMEOUT:
                # portal sök → sonraki tick reconnect kayıtlı ağları yeniden dener
                self.portal_active = False
                self.wifi_state = "IDLE"
                self.retry_count = 0
                self.teardown_count += 1

        # (2) ortam: bağlıyken hotspot düşerse link kopar
        if self.connected and not self.hotspot(self.t):
            self.connected = False

        # (3) _checkWiFiConnection
        self._check_wifi()
        self.t += 1

    def _check_wifi(self):
        current = self.connected

        # boot firstConnectionAttempt: _tryConnectToSavedWiFi → CONNECTING (portal AÇMAZ)
        if self.first_attempt and not current:
            self.first_attempt = False
            self._begin_connecting()
            return

        # CONNECTING çözümü
        if self.wifi_state == "CONNECTING":
            if self.hotspot(self.t):
                # ilişkilendirme başarılı
                self.connected = True
                self.wifi_state = "IDLE"
                self.retry_count = 0
                self.cred_index = 0
                if self.portal_active:
                    self.portal_active = False
            elif (self.t - self.connect_start) >= self.WIFI_CONNECT_TIMEOUT:
                self.cred_index += 1
                if self.cred_index < self.saved:
                    self.connect_start = self.t  # sonraki kredi
                else:
                    # tüm krediler tükendi
                    self.wifi_state = "IDLE"
                    if not self.bug and not self.portal_active:
                        # EDIT-1 tükenme dalı: krediler gerçekten bitti → portalı aç
                        self._open_portal()
            return

        # bağlı değil + portal yok → reconnect (C'de 5 sn throttle; modelde her tick)
        if not current and not self.portal_active:
            self._reconnect()

    def _reconnect(self):
        if self.wifi_state != "IDLE":
            return
        self.retry_count += 1
        if self.bug:
            # HEAD: ilk retry KOŞULSUZ portal
            if not self.portal_active and self.retry_count == 1:
                self._open_portal()
                return
        else:
            # EDIT-1: ilk retry portal AÇMA — kayıtlı ağ varsa önce dene; yoksa portal aç
            if not self.portal_active and self.retry_count == 1 and not self._has_saved():
                self._open_portal()
                return
        if self.portal_active:
            return
        # kayıtlı ağları dene
        self._begin_connecting()

    # --- koşturucu ---
    def run(self, ticks: int):
        for _ in range(ticks):
            self.update()


def _blip(down_start: int, down_end: int) -> Callable[[int], bool]:
    """hotspot [down_start, down_end) aralığında DÜŞÜK, dışında AÇIK."""
    return lambda t: not (down_start <= t < down_end)


# ── SENARYO 1: çalışırken kısa hotspot kesintisi (klinik gateway blip) ─────────────────────────
def test_KRITIK_B2_calisirken_kopus_buggy_SONSUZA_offline_fixed_toparlar():
    """Cihaz bağlıyken hotspot t=10..30 (20 sn) düşer. Buggy: ilk retry portal açar, STA ölür,
    hotspot dönse de SONSUZA DEK offline. Fixed: kayıtlı ağı yeniden dener, hotspot dönünce bağlanır."""
    saved, hs = 1, _blip(10, 30)
    buggy = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=True, start_connected=True)
    buggy.run(300)
    assert not buggy.connected, "buggy modelde cihaz toparladı — model bug'ı ÜRETMİYOR (kapı anlamsız)"
    assert buggy.portal_active, "buggy: ilk retry portalı açmalıydı (kök neden)"

    fixed = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=False, start_connected=True)
    fixed.run(300)
    assert fixed.connected, "fixed: hotspot dönünce kayıtlı ağa yeniden bağlanmalıydı (B2 kök düzeltme)"
    assert not fixed.portal_opened_ever, "fixed: kısa blip'te portal hiç açılmamalı (kayıtlı ağ denenmeli)"


def test_KRITIK_B2_uzun_kesinti_fixed_SINIRLI_surede_toparlar():
    """Hotspot t=10..70 (60 sn, tek connect penceresini aşar) düşer. Buggy sonsuza offline;
    fixed portal-timeout backstop'uyla SINIRLI sürede toparlar (portal 5 dk → saved-retry)."""
    saved, hs = 1, _blip(10, 70)
    buggy = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=True, start_connected=True)
    buggy.run(500)
    assert not buggy.connected, "buggy: uzun kesintide de sonsuza offline kalmalı"

    fixed = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=False, start_connected=True)
    fixed.run(500)
    assert fixed.connected, "fixed: portal-timeout döngüsüyle sınırlı sürede toparlamalı (sonsuz DEĞİL)"


# ── SENARYO 2: kayıtlı kredi YOK (ilk kurulum / provizyon) ─────────────────────────────────────
def test_KRITIK_B2_kredi_yoksa_portal_SURESIZ_acik_kalir():
    """Kayıtlı kredi yok → portal açılır ve AÇIK KALIR (döngü YOK). :136-137 kaldırma-kararının
    asıl amacı korunur: gerçek provizyon ihtiyacında portal timeout ATEŞLENMEZ."""
    fixed = Esp8266WifiFsm(saved_count=0, hotspot=lambda t: False, bug=False, start_connected=False)
    fixed.run(1000)  # PORTAL_TIMEOUT(300)'ün 3 katı
    assert fixed.portal_opened_ever, "kredi yokken portal hiç açılmadı"
    assert fixed.teardown_count == 0, (
        f"kredi yokken portal {fixed.teardown_count} kez söküldü (churn) — ilk kurulum provizyonu "
        "kesintiye uğrar; saved-guard portalı süresiz açık TUTMALI"
    )


# ── SENARYO 3: kullanıcı submit ederken portal yankılanmaz ─────────────────────────────────────
def test_KRITIK_B2_pending_submit_sirasinda_portal_sokulmez():
    """_pendingWifiConnect=true (kullanıcı Android portalından SSID/parola gönderiyor) iken portal
    timeout ATEŞLENMEZ; pending bitince sökülebilir."""
    # start_connected=True → first_attempt=False (boot connect yolu portalı otomatik kapatmasın);
    # sonra portal-aktif + bağlı-değil + pending durumunu elle kur.
    m = Esp8266WifiFsm(saved_count=1, hotspot=lambda t: False, bug=False, start_connected=True)
    m.connected = False
    m.wifi_state = "IDLE"
    m.portal_active = True
    m.portal_start = 0
    m.pending = True
    m.t = 0
    m.run(400)  # PORTAL_TIMEOUT çoktan geçti
    assert m.portal_active, "pending submit sırasında portal söküldü — kullanıcı yapılandırması yankılanır"
    assert m.teardown_count == 0, "pending sırasında teardown sayıldı"

    m.pending = False
    m.run(5)  # timeout zaten geçmiş → hemen sökülür
    assert not m.portal_active, "pending bitince portal timeout yine de sökülmeli"


# ── AŞIRI-DÜZELTME MUTASYONLARI (muhafızları kapatınca koruma testleri KIRMIZI olmalı) ──────────
def test_MUTASYON_saved_guard_kapali_kredi_yok_provizyonu_BOZAR():
    """Mut-A: EDIT-2 saved-guard düşerse kredi yokken de portal sökülür → provizyon portalı yok yere
    kapanır. Bu mutasyonda senaryo-2 koruması KIRILMALI (portal artık açık KALMAZ)."""
    m = Esp8266WifiFsm(
        saved_count=0, hotspot=lambda t: False, bug=False, start_connected=False, edit2_saved_guard=False
    )
    m.run(1000)
    assert m.teardown_count > 0, (
        "saved-guard KAPALIYKEN bile portal hiç sökülmedi — mutasyon koruma testini ayırt etmiyor; "
        "guard'ın gerçekten senaryo-2 churn'ünü önlediği kanıtlanamaz"
    )


def test_MUTASYON_pending_guard_kapali_submit_yankilanir():
    """Mut-B: EDIT-2 pending-guard düşerse kullanıcı submit ederken portal sökülür → yankılanma."""
    m = Esp8266WifiFsm(saved_count=1, hotspot=lambda t: True, bug=False, edit2_pending_guard=False)
    m.portal_active = True
    m.portal_start = 0
    m.pending = True
    m.t = 0
    m.run(400)
    assert not m.portal_active, (
        "pending-guard KAPALIYKEN bile portal ayakta kaldı — mutasyon koruma testini ayırt etmiyor"
    )
