# Author: mertaygn, cglrgrkn
"""ESP8266 MQTT BROKER GERİ-DÖNÜŞ (failback) — 3. tur denetimi bulgu B3 (2026-08-24).

ÖLÇÜLEN DURUM: 8266 yerel Mosquitto'ya bağlanamayınca buluta (HiveMQ) geçiyor ama YEREL BROKER
GERİ GELDİĞİNDE ona DÖNMÜYOR:
  • _reconnectMQTT cloud-başarı dalı _localRetryCount'u SIFIRLAMIYOR → sayaç MAX'ta (3) takılınca
    yerel branch (`_localRetryCount < MQTT_LOCAL_MAX_RETRIES`) bir daha DENENMEZ.
  • Çift-başarısızlık (ikisi de down) dalında da reset yok → sayaç 3'te kalır, Mosquitto dönse
    bile yalnız bulut denenir.
  • Bulut'a bağlıyken yerel broker'ı yoklayan (probe) bir geri-dönüş sürücüsü YOK.
Sonuç: klinik LAN'i kısa düşüp dönse cihaz kalıcı olarak buluta yaslanır (gereksiz WAN bağımlılığı,
E-stop/komut gecikmesi, TLS heap yükü). S3 kardeşinde bu pariteler (probe + sayaç reset) VAR.

DÜZELTME (S3-paritesi, kadans yeniden-yazımı YOK): (1) update() bağlı-dalında broker==CLOUD iken
15 sn'de bir yerel broker'a plain probe; başarılıysa _mqttClient.disconnect()+_localRetryCount=0 →
sonraki reconnect yerel'i ÖNCE dener. (2) çift-başarısızlık sonrası _localRetryCount=0. (3)
cloud-başarı dalında _localRetryCount=0.

Bu dosya (a) 8266 MQTT FSM'ini Python'a taşıyıp buggy'nin sonsuza cloud/None, fixed'in Mosquitto
dönünce LOCAL olduğunu KANITLAR ve (b) C kaynağının probe + iki reset'i gerçekten taşıdığını
yapısal kapıyla doğrular. C bu makinede DERLENEMEZ → dogrulanabilir=YAPISAL_MODEL; REFLASH+tezgah
(failover→failback + BearSSL heap headroom) ZORUNLU.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
NM = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp"


# ═══════════════════════ (A) DAVRANIŞSAL FSM MODELİ ════════════════════════════════════════════
class Esp8266MqttFsm:
    """firmware/esp8266_pemf_coil _reconnectMQTT + update() bağlı-dalı MQTT broker FSM modeli.

    bug=True  → HEAD (probe yok + reset'ler yok). bug=False → düzeltme (3 hunk).
    Aşırı-düzeltme mutasyonu için ayrı toggle'lar:
      probe_only_when_cloud=False → LOCAL'deyken de probe (sağlıklı yereli koparır).
      probe_requires_local_up=False → yoklama başarısız olsa da disconnect (cloud churn).
    """

    MAX_LOCAL_RETRIES = 3
    PROBE_INTERVAL = 15

    def __init__(
        self,
        *,
        local_up: Callable[[int], bool],
        cloud_up: Callable[[int], bool],
        bug: bool = False,
        wifi_up: Callable[[int], bool] = lambda t: True,
        fix_probe: bool = True,
        fix_double_reset: bool = True,
        fix_cloud_reset: bool = True,
        probe_only_when_cloud: bool = True,
        probe_requires_local_up: bool = True,
        start_broker: str = "NONE",
    ):
        self.local_up = local_up
        self.cloud_up = cloud_up
        self.wifi_up = wifi_up
        self.bug = bug
        self.fix_probe = fix_probe
        self.fix_double_reset = fix_double_reset
        self.fix_cloud_reset = fix_cloud_reset
        self.probe_only_when_cloud = probe_only_when_cloud
        self.probe_requires_local_up = probe_requires_local_up

        self.broker = start_broker  # NONE | LOCAL | CLOUD
        self.connected = start_broker in ("LOCAL", "CLOUD")
        self.local_retry = 0
        self.t = 0
        self.last_probe = -10_000
        self.probe_count = 0
        self.probe_disconnect_count = 0  # probe kaç kez aktif bağlantıyı kopardı (churn ölçer)

    def _reconnect_mqtt(self):
        if self.connected:
            return
        if not self.wifi_up(self.t):
            self.local_retry = 0
            return
        # 1. yerel dene (max 3)
        if self.local_retry < self.MAX_LOCAL_RETRIES:
            if self.local_up(self.t):
                self.broker = "LOCAL"
                self.local_retry = 0
                self.connected = True
                return
            self.local_retry += 1
        # 2. bulut
        if self.cloud_up(self.t):
            self.broker = "CLOUD"
            self.connected = True
            if not self.bug and self.fix_cloud_reset:
                self.local_retry = 0  # hunk-3: cloud-başarı reset
            return
        # ikisi de başarısız
        if not self.bug and self.fix_double_reset:
            self.local_retry = 0  # hunk-2: çift-başarısızlık reset

    def update(self):
        if not self.connected:
            self._reconnect_mqtt()
            self.t += 1
            return
        # bağlı: transport düşerse link kopar (broker değeri C'de korunur)
        if self.broker == "LOCAL" and not self.local_up(self.t):
            self.connected = False
            self.t += 1
            return
        if self.broker == "CLOUD" and not self.cloud_up(self.t):
            self.connected = False
            self.t += 1
            return
        # hunk-1: probe (yalnız fixed)
        if not self.bug and self.fix_probe:
            broker_ok = (self.broker == "CLOUD") if self.probe_only_when_cloud else True
            if broker_ok and (self.t - self.last_probe) >= self.PROBE_INTERVAL:
                self.last_probe = self.t
                self.probe_count += 1
                yoklama = self.local_up(self.t) if self.probe_requires_local_up else True
                if yoklama:
                    self.connected = False  # _mqttClient.disconnect()
                    self.local_retry = 0
                    self.probe_disconnect_count += 1
        self.t += 1

    def run(self, ticks: int):
        for _ in range(ticks):
            self.update()


def _up_from(tick: int) -> Callable[[int], bool]:
    return lambda t: t >= tick


# ── SENARYO A: Mosquitto kısa süre kapalı, bulut hep açık → dönünce YERELE geç ─────────────────
def test_KRITIK_B3_yerel_donunce_LOCALe_gecer_buggy_sonsuza_CLOUD():
    local, cloud = _up_from(3), (lambda t: True)
    buggy = Esp8266MqttFsm(local_up=local, cloud_up=cloud, bug=True)
    buggy.run(80)
    assert buggy.broker == "CLOUD", "buggy modelde cihaz LOCAL'e döndü — model bug'ı ÜRETMİYOR"

    fixed = Esp8266MqttFsm(local_up=local, cloud_up=cloud, bug=False)
    fixed.run(80)
    assert fixed.broker == "LOCAL", (
        "yerel broker döndüğü hâlde cihaz CLOUD'da kaldı — probe+cloud-reset geri-dönüşü sağlamadı (B3)"
    )


# ── SENARYO B: ikisi de kapalı, sonra YALNIZ Mosquitto döner → LOCAL ───────────────────────────
def test_KRITIK_B3_cift_basarisizlik_sonra_yerel_LOCAL_buggy_sonsuza_NONE():
    local, cloud = _up_from(10), (lambda t: False)
    buggy = Esp8266MqttFsm(local_up=local, cloud_up=cloud, bug=True)
    buggy.run(80)
    assert buggy.broker != "LOCAL" and not buggy.connected, (
        "buggy modelde çift-başarısızlıktan sonra yerel'e bağlandı — model bug'ı üretmiyor "
        "(sayaç MAX'ta takılı kalmalıydı)"
    )

    fixed = Esp8266MqttFsm(local_up=local, cloud_up=cloud, bug=False)
    fixed.run(80)
    assert fixed.broker == "LOCAL" and fixed.connected, (
        "çift-başarısızlık sonrası sayaç MAX'ta takıldı, Mosquitto dönse de yerel denenmedi (B3 hunk-2)"
    )


# ── KARŞIT-KANIT: sağlıklı LOCAL korunur ───────────────────────────────────────────────────────
def test_KARSIT_KANIT_B3_saglikli_LOCAL_koparilmaz():
    """Probe yalnız broker==CLOUD iken; çalışan yerel bağlantı 15 sn'de bir koparılmamalı."""
    m = Esp8266MqttFsm(local_up=lambda t: True, cloud_up=lambda t: True, bug=False, start_broker="LOCAL")
    m.run(60)
    assert m.broker == "LOCAL" and m.connected, "sağlıklı LOCAL bağlantı probe tarafından koparıldı"
    assert m.probe_count == 0, "broker LOCAL iken probe ateşledi (yalnız CLOUD'da olmalı)"


# ── KARŞIT-KANIT: yerel düşük + yalnız bulut → STABİL cloud (Plan-A aynası) ─────────────────────
def test_KARSIT_KANIT_B3_yerel_dusukken_cloud_STABIL():
    """Yerel gerçekten down + yalnız bulut var → E-stop bulut aynası (Plan-A) korunur; probe
    başarısız → disconnect YOK → cihaz cloud'da STABİL kalır (çırpınma yok)."""
    m = Esp8266MqttFsm(local_up=lambda t: False, cloud_up=lambda t: True, bug=False)
    m.run(120)
    assert m.broker == "CLOUD" and m.connected, "yerel düşükken bulut bağlantısı çırpındı (Plan-A ihlali)"
    assert m.probe_count > 0, "probe hiç ateşlemedi (senaryo geçersiz)"
    assert m.probe_disconnect_count == 0, (
        "yerel down iken probe bağlantıyı kopardı — başarılı-yoklama şartı yok; cloud çırpınır"
    )


# ── AŞIRI-DÜZELTME MUTASYONLARI ────────────────────────────────────────────────────────────────
def test_MUTASYON_probe_broker_kapisi_dusunce_saglikli_LOCAL_koparilir():
    """Mut: probe'un broker==cloud kapısı düşerse LOCAL'deyken de yoklama+disconnect → sağlıklı
    yerel koparılır. Bu mutasyonda 'saglikli_LOCAL' koruması KIRILMALI."""
    m = Esp8266MqttFsm(
        local_up=lambda t: True, cloud_up=lambda t: True, bug=False, start_broker="LOCAL", probe_only_when_cloud=False
    )
    m.run(60)
    # broker-kapısı KAPALIYKEN LOCAL'de probe ATEŞLER → guard'ın (açıkken) sağlıklı yereli koruduğu
    # kanıtlanır. Guard AÇIK sürümde (test_KARSIT_KANIT_B3_saglikli_LOCAL_koparilmaz) probe_count==0.
    assert m.probe_count > 0, (
        "broker-kapısı kapalıyken bile LOCAL'de probe ateşlemedi — guard'ın sağlıklı yereli koruduğu kanıtlanamaz"
    )


def test_MUTASYON_probe_kosulsuz_disconnect_cloud_cirpinir():
    """Mut: probe başarılı-yoklama şartı olmadan disconnect ederse (koşulsuz) yerel down + yalnız
    bulut senaryosunda cloud çırpınır. Bu mutasyonda 'yerel_dusukken_cloud_STABIL' KIRILMALI."""
    m = Esp8266MqttFsm(local_up=lambda t: False, cloud_up=lambda t: True, bug=False, probe_requires_local_up=False)
    m.run(120)
    # koşulsuz disconnect → yerel down olsa bile her probe cloud'u koparır → STABİL-cloud değişmezi
    # (probe_disconnect_count==0) ihlal edilir. Doğru sürümde bu sayaç 0'dır.
    assert m.probe_disconnect_count > 0, (
        "koşulsuz-disconnect mutasyonu bağlantıyı hiç koparmadı — STABİL-cloud korumasını ayırt etmiyor"
    )


# ═══════════════════════ (B) YAPISAL KAPI (c_soy) ══════════════════════════════════════════════
def _kaynak() -> str:
    return c_soy(NM.read_text(encoding="utf-8", errors="replace"))


def _update_govde(soy: str) -> str:
    a = soy.index("void NetworkManager::update()")
    b = soy.index("void NetworkManager::setMqttCallback", a)
    return soy[a:b]


def _reconnect_govde(soy: str) -> str:
    a = soy.index("void NetworkManager::_reconnectMQTT()")
    b = soy.index("void NetworkManager::sendCommandAck", a)
    return soy[a:b]


def test_KRITIK_B3_update_probe_icerir():
    govde = _update_govde(_kaynak())
    assert "_activeBroker == BROKER_CLOUD" in govde, (
        "update() bağlı-dalında broker==CLOUD probe kapısı yok — yerel geri-dönüş sürücüsü eksik (B3 hunk-1)"
    )
    assert "probeClient.connect(_localMqttHost" in govde, (
        "update() yerel broker'a plain probe (probeClient.connect) içermiyor"
    )
    assert "_mqttClient.disconnect()" in govde, (
        "probe başarılı yoklamada _mqttClient.disconnect() ile geri-dönüşü tetiklemiyor"
    )
    # ⚠️ adversaryal C-inceleme BLOCKER'ı: probe connect KISA timeout'la çağrılmalı; yoksa yerel
    # sessizce down iken varsayılan 5 sn'lik connect kooperatif loop'u bloklar → BULUT E-stop geciker.
    st = govde.find("probeClient.setTimeout(")
    cn = govde.find("probeClient.connect(")
    assert st >= 0, (
        "probe connect'i kısa timeout'la sınırlamıyor (probeClient.setTimeout yok) — yerel sessiz-drop'ta "
        "connect kooperatif loop'u ~5 sn bloklar, bulut E-stop aynası geciker (B3 blocker)"
    )
    assert st < cn, "setTimeout, connect'ten SONRA — bloklamayı sınırlamıyor"


def test_KRITIK_B3_reconnect_iki_reset_dogru_pozisyonda():
    govde = _reconnect_govde(_kaynak())
    cloud = govde.index("_connectToCloudBroker()")
    pub = govde.index('publishEvent("mqtt_connected", "HiveMQ', cloud)
    ret_bulut = govde.index("return;", pub)
    # (i) cloud-başarı reset: _connectToCloudBroker çağrısı ile HiveMQ publishEvent arası
    ara = govde[cloud:pub]
    assert "_localRetryCount = 0" in ara, (
        "cloud-başarı dalında _localRetryCount=0 yok — sayaç MAX'ta takılınca yerel bir daha denenmez (B3 hunk-3)"
    )
    # (ii) çift-başarısızlık reset: cloud if-bloğu/return'DEN SONRA
    son = govde[ret_bulut:]
    assert "_localRetryCount = 0" in son, (
        "çift-başarısızlık (her iki broker down) sonrası _localRetryCount=0 yok — sayaç 3'te takılır, "
        "Mosquitto dönse bile yerel denenmez (B3 hunk-2)"
    )


def test_KARSIT_KANIT_B3_probe_bobin_durdurmaz():
    """Regresyon sentineli: MQTT geri-dönüş yolları PWM/bobin durdurmaz (Plan-A değişmezi)."""
    soy = _kaynak()
    for bolge, ad in ((_update_govde(soy), "update"), (_reconnect_govde(soy), "_reconnectMQTT")):
        for yasak in ("stopPWM", "coilStop", ".stopOutput", "safeStopCoils"):
            assert yasak not in bolge, f"{ad} bölgesinde yasak bobin-durdurma '{yasak}' (Plan-A ihlali)"
