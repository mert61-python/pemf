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

2026-09-10 (saha arızası + sahip kararı): kayıtlı kredi VARKEN tükenme dalı portalı artık HEMEN AÇMAZ;
STA sonsuza kadar denenir ve portal yalnız PROVIZYON_GERI_DONUS (30 dk) KESİNTİSİZ başarısızlıktan sonra
bir kez açılır (`NetworkManager.cpp` tükenme dalı).

D1.49 (B-10.232, B-10.233 · 2026-10-01): bu model eskiden sabitleri ELLE kopyalıyor ve tükenme dalını 08-24
hâliyle (hemen portal) modelliyordu — C'de tükenme koşulu `if (!_portalActive)`'e indirilse (kredi varken
1 dk içinde portal → STA ölür) bu dosya YEŞİL kalıyordu. Artık:
  * süreler `NetworkManager.h`'den okunur (ms → model saniyesi);
  * üç karar koşulu (ilk-retry portalı, tükenme-dalı portalı, portal sökme) YORUMU SOYULMUŞ C'den çıkarılıp
    Python ifadesine çevrilir ve model O ifadeyi değerlendirir — C'de modelin tanımadığı bir terim belirirse
    kapı KIRMIZI olur (model güncellenmeden geçemez);
  * pending-guard öz-testi gerçekten ayırt eder (eskiden hotspot açıkken CONNECTING başarısı portalı kendisi
    kapatıyordu → muhafız açıkken de yeşildi).

Bu dosya 8266 reconnect FSM'ini Python'a taşır (buggy HEAD `bug=True` + fixed `bug=False`) ve
zaman-çizgisi + hotspot-müsaitliği(t) sürerek buggy'nin sonsuza dek offline, fixed'in sınırlı
sürede CONNECTED olduğunu KANITLAR. C'nin bu algoritmayı gerçekten taşıdığını yapısal kapı
(test_esp8266_portal_ozilesme.py) ayrı doğrular.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
_NM_CPP = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp"
_NM_H = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.h"


# ── C kaynağından okuma ────────────────────────────────────────────────────


def _ms_sabiti_sn(h_soy: str, ad: str) -> int:
    """`const unsigned long AD = <ms>[UL];` → saniye (model 1 tick = 1 sn)."""
    m = re.search(rf"\bconst\s+unsigned\s+long\s+{ad}\s*=\s*(\d+)\s*U?L?\s*;", h_soy)
    assert m, f"NetworkManager.h: {ad} (yorum dışı) bulunamadı — model sabitini okuyamıyor"
    ms = int(m.group(1))
    assert ms % 1000 == 0, f"{ad}={ms} ms tam saniye değil — model çözünürlüğü (1 sn) yetmez"
    return ms // 1000


def _kosul_sonrasi(soy: str, bas: int) -> tuple[str, int]:
    """soy[bas:] içindeki ilk `if (` → (dengeli parantez içi koşul, koşul sonu indeksi)."""
    m = re.compile(r"\bif\s*\(").search(soy, bas)
    assert m, "if bulunamadı"
    d, i = 0, m.end() - 1
    for j in range(i, len(soy)):
        d += {"(": 1, ")": -1}.get(soy[j], 0)
        if d == 0:
            return " ".join(soy[i + 1 : j].split()), j
    raise AssertionError("dengesiz parantez")


def _kume_govdesi(soy: str, ac: int) -> str:
    """soy[ac] == '{' → eşleşen '}'e kadar gövde (iç içe bloklar dahil)."""
    d = 0
    for j in range(ac, len(soy)):
        d += {"{": 1, "}": -1}.get(soy[j], 0)
        if d == 0:
            return soy[ac + 1 : j]
    raise AssertionError("dengesiz küme parantezi")


def _kosul_icin(soy: str, isaret: str) -> str:
    """Koşulunda `isaret` geçen TEK `if`in koşulu (birden çok ya da hiç → kapı kırmızı)."""
    bulunan = []
    for m in re.finditer(r"\bif\s*\(", soy):
        kosul, _ = _kosul_sonrasi(soy, m.start())
        if isaret in kosul:
            bulunan.append(kosul)
    assert len(bulunan) == 1, f"`{isaret}` içeren if koşulu {len(bulunan)} adet: {bulunan}"
    return bulunan[0]


def c_kosulu(kosul: str, harita: dict[str, str]) -> Callable[..., bool]:
    """C boolean koşulunu (`&&`, `||`, `!`, `==`) Python'a çevirir. `harita`: C terimi → model adı.

    Haritada OLMAYAN bir C terimi kalırsa AssertionError — C'ye yeni bir koşul eklenirse model sessizce
    eski davranışı sürdürmez."""
    py = " ".join(kosul.split())
    for c_terim in sorted(harita, key=len, reverse=True):
        py = py.replace(c_terim, f" {harita[c_terim]} ")
    py = py.replace("&&", " and ").replace("||", " or ")
    py = re.sub(r"!(?!=)", " not ", py)
    kalan = set(re.findall(r"[A-Za-z_]\w*", py)) - {"and", "or", "not"} - set(harita.values())
    assert not kalan, f"C koşulunda modelin TANIMADIĞI terim: {sorted(kalan)} ← {kosul!r}"
    kod = compile(" ".join(py.split()), "<c-kosulu>", "eval")
    return lambda **d: bool(eval(kod, {"__builtins__": {}}, d))  # noqa: S307 — yalnız harita adları


class CKaynagi:
    """`NetworkManager.{h,cpp}` (yorumsuz) → model sabitleri ve karar koşulları."""

    def __init__(self, h: str, cpp: str):
        hs, cs = c_soy(h), c_soy(cpp)
        self.WIFI_CONNECT_TIMEOUT = _ms_sabiti_sn(hs, "WIFI_CONNECT_TIMEOUT")
        self.PORTAL_TIMEOUT = _ms_sabiti_sn(hs, "PORTAL_TIMEOUT")
        self.PROVIZYON_GERI_DONUS = _ms_sabiti_sn(hs, "PROVIZYON_GERI_DONUS")

        # (1) _reconnectWiFi ilk-retry portalı
        self.ilk_retry_portal = c_kosulu(
            _kosul_icin(cs, "_wifiRetryCount == 1"),
            {"_portalActive": "portal_active", "_wifiRetryCount": "retry_count", "_hasSavedCredentials()": "kredi_var"},
        )

        # (2) tükenme dalı: krediVar / uzunKopus tanımları + hemen ardındaki if
        m = re.search(r"const\s+bool\s+krediVar\s*=\s*([^;]+);\s*const\s+bool\s+uzunKopus\s*=\s*([^;]+);", cs)
        assert m, "tükenme dalı (krediVar/uzunKopus) bulunamadı"
        assert " ".join(m.group(1).split()) == "_hasSavedCredentials()", f"krediVar = {m.group(1)!r}"
        assert " ".join(m.group(2).split()) == "safeMillisDiff(millis(), _staKopusBasiMs) >= PROVIZYON_GERI_DONUS", (
            f"uzunKopus = {m.group(2)!r} — model 'kopuş başından beri geçen ≥ PROVIZYON_GERI_DONUS' varsayıyor"
        )
        kosul, son = _kosul_sonrasi(cs, m.end())
        self.tukenme_portal = c_kosulu(
            kosul, {"_portalActive": "portal_active", "krediVar": "kredi_var", "uzunKopus": "uzun_kopus"}
        )
        govde = _kume_govdesi(cs, cs.index("{", son))
        assert "_startWiFiPortal();" in govde and "_staKopusBasiMs = millis();" in govde, (
            f"tükenme-dalı portal gövdesi beklenen iki deyimi taşımıyor: {govde!r}"
        )
        assert re.search(r"if\s*\(\s*_staKopusBasiMs\s*==\s*0\s*\)\s*\{\s*_staKopusBasiMs\s*=\s*millis\(\);", cs), (
            "kopuş başlangıcı yalnız ilk başarısız turda kurulmuyor — model varsayımı bozuldu"
        )
        bagli = re.search(r"else\s+if\s*\(\s*currentWiFiState\s*\)\s*\{", cs)
        assert bagli and re.search(r"\b_staKopusBasiMs\s*=\s*0\s*;", _kume_govdesi(cs, bagli.end() - 1)), (
            "bağlanınca kopuş sayacı sıfırlanmıyor — model varsayımı bozuldu"
        )

        # (3) update() portal sökme
        self.portal_sok = c_kosulu(
            _kosul_icin(cs, "_portalStartTime) >= PORTAL_TIMEOUT"),
            {
                "_pendingWifiConnect": "pending",
                "_hasSavedCredentials()": "kredi_var",
                "safeMillisDiff(millis(), _portalStartTime) >= PORTAL_TIMEOUT": "sure_doldu",
            },
        )


def c_kaynagi() -> CKaynagi:
    return CKaynagi(
        _NM_H.read_text(encoding="utf-8", errors="replace"), _NM_CPP.read_text(encoding="utf-8", errors="replace")
    )


C = c_kaynagi()


class Esp8266WifiFsm:
    """firmware/esp8266_pemf_coil/NetworkManager.cpp update()+_checkWiFiConnection()+_reconnectWiFi()
    WiFi durum-makinesinin davranışsal Python modeli (1 sn = 1 tick).

    bug=True  → 08-24 öncesi HEAD semantiği (ilk retry KOŞULSUZ portal + portal timeout YOK).
    bug=False → BUGÜNKÜ C: karar koşulları ve süreler `CKaynagi`'ndan (yorumsuz C) gelir.

    Aşırı-düzeltme mutasyonu için iki muhafız ayrı kapatılabilir:
      edit2_saved_guard=False   → kredi YOKKEN de portal timeout ateşler (provizyon bozulur).
      edit2_pending_guard=False → kullanıcı submit ederken portal yankılanır.
    """

    WIFI_CONNECT_TIMEOUT = C.WIFI_CONNECT_TIMEOUT
    PORTAL_TIMEOUT = C.PORTAL_TIMEOUT
    PROVIZYON_GERI_DONUS = C.PROVIZYON_GERI_DONUS

    def __init__(
        self,
        *,
        saved_count: int,
        hotspot: Callable[[int], bool],
        bug: bool = False,
        start_connected: bool = False,
        edit2_saved_guard: bool = True,
        edit2_pending_guard: bool = True,
        c: CKaynagi = C,
    ):
        self.saved = saved_count  # geçerli kayıtlı kredi sayısı
        self.hotspot = hotspot  # callable(t)->bool: kayıtlı ağ o an erişilebilir mi
        self.bug = bug
        self.edit2_saved_guard = edit2_saved_guard
        self.edit2_pending_guard = edit2_pending_guard
        self.c = c

        self.t = 0
        self.connected = start_connected
        self.portal_active = False
        self.portal_start = 0
        self.wifi_state = "IDLE"  # IDLE | CONNECTING
        self.retry_count = 0
        self.cred_index = 0
        self.connect_start = 0
        self.pending = False  # _pendingWifiConnect
        self.sta_kopus_basi: int | None = None  # _staKopusBasiMs (0 = None)
        # boot firstConnectionAttempt: yalnız bağlı-değil başlarsak anlamlı
        self.first_attempt = not start_connected
        self.portal_opened_ever = False
        self.portal_acilis_anlari: list[int] = []
        self.teardown_count = 0  # portal timeout kaç kez portalı söktü (churn ölçer)

    # --- yardımcılar ---
    def _has_saved(self) -> bool:
        return self.saved > 0

    def _open_portal(self):
        # _startWiFiPortal(): WiFi.mode(WIFI_AP) STA'yı öldürür
        self.portal_active = True
        self.portal_start = self.t
        self.portal_opened_ever = True
        self.portal_acilis_anlari.append(self.t)
        self.connected = False

    def _begin_connecting(self):
        self.wifi_state = "CONNECTING"
        self.connect_start = self.t
        self.cred_index = 0

    # --- update() bir tick ---
    def update(self):
        # (1) portal bloğu — EDIT-2 kredi-kapılı timeout (koşul C'den)
        if self.portal_active and not self.bug:
            pending = self.pending if self.edit2_pending_guard else False
            kredi = self._has_saved() if self.edit2_saved_guard else True
            if self.c.portal_sok(
                pending=pending, kredi_var=kredi, sure_doldu=(self.t - self.portal_start) >= self.PORTAL_TIMEOUT
            ):
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
                    if not self.bug:
                        if self.sta_kopus_basi is None:
                            self.sta_kopus_basi = self.t
                        uzun = (self.t - self.sta_kopus_basi) >= self.PROVIZYON_GERI_DONUS
                        if self.c.tukenme_portal(
                            portal_active=self.portal_active, kredi_var=self._has_saved(), uzun_kopus=uzun
                        ):
                            self._open_portal()
                            self.sta_kopus_basi = self.t  # geri-dönüş sayacını sıfırla
            return

        if current:
            self.sta_kopus_basi = None  # C: bağlanınca `_staKopusBasiMs = 0`
            return

        # bağlı değil + portal yok → reconnect (C'de 5 sn throttle; modelde her tick)
        if not self.portal_active:
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
        elif self.c.ilk_retry_portal(
            portal_active=self.portal_active, retry_count=self.retry_count, kredi_var=self._has_saved()
        ):
            # EDIT-1: ilk retry portal AÇMA — kayıtlı ağ varsa önce dene; yoksa portal aç
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
    fixed STA'yı denemeyi sürdürür (portal açmaz) ve hotspot dönünce bağlanır."""
    saved, hs = 1, _blip(10, 70)
    buggy = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=True, start_connected=True)
    buggy.run(500)
    assert not buggy.connected, "buggy: uzun kesintide de sonsuza offline kalmalı"

    fixed = Esp8266WifiFsm(saved_count=saved, hotspot=hs, bug=False, start_connected=True)
    fixed.run(500)
    assert fixed.connected, "fixed: STA denemesiyle sınırlı sürede toparlamalı (sonsuz DEĞİL)"
    assert not fixed.portal_opened_ever, "fixed: 60 sn'lik kesintide portal açılmamalı (30 dk geri dönüş)"


# ── SENARYO 1b: 30 dk geri dönüş (2026-09-10 C davranışı, D1.49) ──────────────────────────────
def test_KRITIK_D149_kredi_varken_portal_ancak_30_dk_KESINTISIZ_basarisizliktan_sonra_acilir():
    """Kayıtlı kredi var, hotspot HİÇ gelmiyor. Bugünkü C: krediler her tükenişinde portal AÇILMAZ (STA ölmez);
    ilk başarısız turdan PROVIZYON_GERI_DONUS sonra BİR KEZ açılır, PORTAL_TIMEOUT sonra sökülür."""
    m = Esp8266WifiFsm(saved_count=1, hotspot=lambda t: False, bug=False, start_connected=False)
    m.run(m.PROVIZYON_GERI_DONUS)
    assert not m.portal_opened_ever, (
        f"portal {m.portal_acilis_anlari} anında açıldı — kredi varken {m.PROVIZYON_GERI_DONUS} sn dolmadan portal "
        "AP-only'ye geçip STA'yı öldürür (hotspot dönse de göremez; 2026-09-10 saha arızası)"
    )
    m.run(m.PORTAL_TIMEOUT + 4 * m.WIFI_CONNECT_TIMEOUT)
    assert len(m.portal_acilis_anlari) == 1, f"30 dk geri dönüşte portal tam BİR kez açılmalı: {m.portal_acilis_anlari}"
    ilk_tukenme = m.WIFI_CONNECT_TIMEOUT
    assert m.portal_acilis_anlari[0] - ilk_tukenme >= m.PROVIZYON_GERI_DONUS
    assert m.teardown_count == 1 and not m.portal_active, "kredi varken portal PORTAL_TIMEOUT sonunda sökülmeli"


def test_KARSIT_D149_ara_baglanti_kopus_sayacini_SIFIRLAR():
    """Kesinti arada bağlanırsa sayaç baştan sayar: 25 dk düşük + 1 dk açık + 25 dk düşük → portal AÇILMAZ."""
    yirmi_bes = 25 * 60
    hs = lambda t: yirmi_bes <= t < yirmi_bes + 60  # noqa: E731
    m = Esp8266WifiFsm(saved_count=1, hotspot=hs, bug=False, start_connected=False)
    m.run(2 * yirmi_bes + 60)
    assert not m.portal_opened_ever, f"ara bağlantıya rağmen portal açıldı: {m.portal_acilis_anlari}"


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
def _portal_acik_pending(**kw) -> Esp8266WifiFsm:
    """Portal açık + bağlı değil + kullanıcı submit ediyor; hotspot KAPALI → portalı yalnız TIMEOUT sökebilir
    (hotspot açık olsaydı CONNECTING başarısı portalı kendisi kapatır, muhafızı sınamazdı — D1.49)."""
    # start_connected=True → first_attempt=False (boot connect yolu portalı otomatik kapatmasın)
    m = Esp8266WifiFsm(saved_count=1, hotspot=lambda t: False, bug=False, start_connected=True, **kw)
    m.connected = False
    m.wifi_state = "IDLE"
    m.portal_active = True
    m.portal_start = 0
    m.pending = True
    m.t = 0
    return m


def test_KRITIK_B2_pending_submit_sirasinda_portal_sokulmez():
    """_pendingWifiConnect=true (kullanıcı Android portalından SSID/parola gönderiyor) iken portal
    timeout ATEŞLENMEZ; pending bitince sökülebilir."""
    m = _portal_acik_pending()
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
    """Mut-B: EDIT-2 pending-guard düşerse kullanıcı submit ederken portal sökülür → yankılanma.
    D1.49: senaryo `test_KRITIK_B2_pending_submit_sirasinda_portal_sokulmez` ile AYNI (yalnız muhafız farklı)."""
    m = _portal_acik_pending(edit2_pending_guard=False)
    m.run(400)
    assert m.teardown_count >= 1 and not m.portal_active, (
        "pending-guard KAPALIYKEN bile portal ayakta kaldı — mutasyon koruma testini ayırt etmiyor"
    )


# ── D1.49 öz-denetim: model C'yi gerçekten okuyor mu ───────────────────────────────────────────


def test_D149_sabitler_C_den_okunur():
    assert (C.WIFI_CONNECT_TIMEOUT, C.PORTAL_TIMEOUT, C.PROVIZYON_GERI_DONUS) == (30, 300, 1800), (
        "NetworkManager.h süreleri değişti — bilinçliyse bu pin ve senaryo süreleri güncellenir"
    )


@pytest.mark.parametrize(
    ("ad", "eski", "yeni"),
    [
        ("tukenme_HER_ZAMAN_portal", "if (!_portalActive && (!krediVar || uzunKopus)) {", "if (!_portalActive) {"),
        (
            "tukenme_uzun_kopus_YOK",
            "if (!_portalActive && (!krediVar || uzunKopus)) {",
            "if (!_portalActive && (!krediVar)) {",
        ),
        ("sokme_PENDING_YOK", "if (!_pendingWifiConnect && _hasSavedCredentials() &&", "if (_hasSavedCredentials() &&"),
        ("sokme_KREDI_YOK", "if (!_pendingWifiConnect && _hasSavedCredentials() &&", "if (!_pendingWifiConnect &&"),
        (
            "ilk_retry_KREDI_YOK",
            "if (!_portalActive && _wifiRetryCount == 1 && !_hasSavedCredentials()) {",
            "if (!_portalActive && _wifiRetryCount == 1) {",
        ),
    ],
)
def test_ARAC_D149_C_mutanti_MODEL_davranisini_degistirir(ad, eski, yeni):
    """Bellek içi C mutantı → model (aynı senaryolar) farklı davranır → ilgili senaryo kırmızıya döner."""
    h, cpp = _NM_H.read_text(encoding="utf-8"), _NM_CPP.read_text(encoding="utf-8")
    assert cpp.count(eski) == 1, f"çapa {cpp.count(eski)} kez"
    mc = CKaynagi(h, cpp.replace(eski, yeni))

    def senaryolar(c):
        a = Esp8266WifiFsm(saved_count=1, hotspot=lambda t: False, bug=False, c=c)
        a.run(c.PROVIZYON_GERI_DONUS + c.PORTAL_TIMEOUT + 4 * c.WIFI_CONNECT_TIMEOUT)
        b = _portal_acik_pending(c=c)
        b.run(400)
        k = Esp8266WifiFsm(saved_count=0, hotspot=lambda t: False, bug=False, c=c)
        k.run(1000)
        s = Esp8266WifiFsm(saved_count=1, hotspot=_blip(10, 30), bug=False, start_connected=True, c=c)
        s.run(300)
        return (
            a.portal_acilis_anlari,
            a.teardown_count,
            b.portal_active,
            k.teardown_count,
            s.portal_opened_ever,
            s.connected,
        )

    assert senaryolar(mc) != senaryolar(C), f"{ad}: C mutantı modelin davranışını değiştirmedi — model C'yi okumuyor"


def test_ARAC_D149_tanimsiz_C_terimi_KIRMIZI():
    h, cpp = _NM_H.read_text(encoding="utf-8"), _NM_CPP.read_text(encoding="utf-8")
    eski = "if (!_portalActive && (!krediVar || uzunKopus)) {"
    with pytest.raises(AssertionError, match="TANIMADIĞI"):
        CKaynagi(h, cpp.replace(eski, "if (!_portalActive && (!krediVar || uzunKopus || _yeniBayrak)) {"))
