# -*- coding: utf-8 -*-
# Author: mertaygn
"""İNTERNETSİZ ÇALIŞMA + ESP DEVRE DIŞI — 2026-09-11 sahip bildirimleri.

===============================================================================
1) "İNTERNET YOKKEN KIRMIZI DOLU EKRAN"
===============================================================================
Sahip: "uygulama internet olmayan makinede çalışmalı (uzaktan erişim hariç). İnternete
bağlı değilken kullanıcı geri bildirimi çok eksik, her yerden kırmızı uyarılar fışkırıyor.
Latte Panda'da düşün: internete bağlı olmasa bile hotspot açabiliyor ve bütün donanım
kusursuz çalışıyor ama kırmızı dolu bir ekran var."

KÖK NEDEN: `apps/backend/services/headless_services._determine_gateway_mode` hotspot AÇIK + internet
YOK durumunu `"offline"` döndürüyor; `api_server` bunu
`gateway = "online" if mode in ("online","hybrid") else "offline"` ile okuyordu →
Dashboard'daki "Bağlantı" rozeti KIRMIZI. Oysa o an hotspot çalışıyor, STM kablolu,
bütün donanım sürülüyor.

⚠️ SINIF: "internet yok" ile "cihaz bozuk" AYNI renge boyanıyordu. Sonuç uyarı körlüğü —
kalıcı kırmızıya alışan operatör GERÇEK arızayı da görmez.

===============================================================================
2) ESP SÖKÜLDÜ — KOD SİLİNMEZ, DEVRE DIŞI KALIR
===============================================================================
Sahip: "espleri sistemden söktüğüm için ESP kodlarını devre dışı bırak ama ASLA SİLME,
ileride tekrar hibrit ESP+STM ya da sadece ESP sistemine dönebilirim."

ÇÖZÜM: tek bayrak `PEMF_ESP_ENABLED` (varsayılan 0). Kod CANLI kalır ve testler onu
`PEMF_ESP_ENABLED=1` ile koşmaya DEVAM EDER — yorum satırına alınsaydı derlenmez/test
edilmez olur ve geri dönüşte sessizce bayatlardı.

===============================================================================
⚠️ BU DOSYA NE ÖLÇMEZ
===============================================================================
"Gösterilen değerler gerçek değil" şikâyeti ARAŞTIRILDI: `PEMF_SIMULATE` saf bir ortam
değişkenidir, bağlantıdan TÜRETİLMEZ — yani internetsizlik uygulamayı sahte veriye
DÜŞÜRMÜYOR. Sensör alanlarının boş görünmesinin sebebi ayrı bir arızaydı (newlib-nano
printf-float, bkz. test_stm_printf_float_kapisi.py). Burada o iddia sınanmaz; aşağıdaki
kapı yalnız "simülasyon bağlantıdan türemez" değişmezini kilitler.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _olay(tur: str, veri: dict):
    return type("O", (), {"event_type": tur, "data": veri})()


@pytest.fixture
def durum():
    """`_live_state`i testten sonra eski hâline döndürür."""
    from servers import live_state

    with live_state._live_state_lock:
        eski = {k: live_state._live_state[k] for k in ("gateway", "mqtt", "internet")}
    yield live_state
    with live_state._live_state_lock:
        live_state._live_state.update(eski)


# ============================================================================
# 1. İNTERNET YOKKEN CİHAZ AĞI "ÇEVRİMDIŞI" SAYILMAZ
# ============================================================================


def test_KRITIK_hotspot_ACIK_internet_YOKKEN_gateway_ONLINE(durum):
    """⚠️ ASIL KAPI — sahanın "kırmızı dolu ekran" şikâyeti tam olarak budur.

    MUTASYON: `cihaz_agi_var` hesabını eski hâline döndür
    (`"online" if mode in ("online","hybrid") else "offline"`) → KIRMIZI.
    """
    from servers import api_server

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "offline", "hotspot_active": True, "internet_connected": False})
    )
    with durum._live_state_lock:
        g, i = durum._live_state["gateway"], durum._live_state["internet"]
    assert g == "online", (
        f"hotspot ACIK ve donanim calisirken cihaz agi '{g}' bildirildi -> arayuz KIRMIZI yanar "
        "ve operator gercek arizayi goremez hale gelir (uyari korlugu)"
    )
    assert i == "offline", "internet durumu AYRI alanda bildirilmeli (notr bilgi)"


def test_KRITIK_internet_ile_cihaz_agi_AYRI_alanlar(durum):
    """İkisi tek alana sıkıştırılırsa arayüz hangisinin bozuk olduğunu SÖYLEYEMEZ."""
    from servers import api_server

    # İnternet VAR, hotspot yok (kablolu klinik ağı).
    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "hybrid", "hotspot_active": False, "internet_connected": True})
    )
    with durum._live_state_lock:
        assert durum._live_state["gateway"] == "online"
        assert durum._live_state["internet"] == "online"


def test_HICBIR_AG_YOKKEN_cihaz_agi_GERCEKTEN_offline(durum):
    """Karşıt kanıt: kural "her zaman online de" diye geçilemesin.

    Hotspot da yok, internet de yok → cihaz ağı GERÇEKTEN çevrimdışıdır ve öyle
    bildirilmelidir (mobil istemciler bağlanamaz).
    """
    from servers import api_server

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "disconnected", "hotspot_active": False, "internet_connected": False})
    )
    with durum._live_state_lock:
        assert durum._live_state["gateway"] == "offline"


def test_snapshot_internet_alanini_TASIR(durum):
    """Arayüz alanı okuyamıyorsa ayrım işe yaramaz."""
    from servers import live_state

    # D5.58 TUR 3: eski gövde atlaması ("snapshot yardimcisi bu surumde yok") kaldırıldı — `_build_ws_snapshot`
    # ürünün WS / dashboard anlık görüntü kaynağıdır; yokluğu ATLAMA değil KIRMIZI (sessiz atlama bu kapıyı kör ederdi).
    assert hasattr(live_state, "_build_ws_snapshot"), (
        "live_state._build_ws_snapshot YOK — WS / dashboard anlık görüntü kaynağı kayboldu"
    )
    anlik = live_state._build_ws_snapshot()
    assert "internet" in anlik, "snapshot `internet` alanini TASIMIYOR -> arayuz notr gosterge cizemez"


# ============================================================================
# 2. ESP DEVRE DIŞI — KOD DURUYOR, DAVRANIŞ KAPALI
# ============================================================================


def test_KRITIK_varsayilan_ESP_KAPALI(monkeypatch):
    """Sahип ESP'leri söktü → varsayılan KAPALI olmalı.

    MUTASYON: varsayılanı `"1"` yap → KIRMIZI (sökülü donanım için MQTT denemeleri
    ve kalıcı sarı rozet geri gelir).
    """
    from servers import live_state

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    assert live_state.esp_etkin() is False


def test_KRITIK_bayrakla_ESP_GERI_GELIR(monkeypatch):
    """⚠️ EN ÖNEMLİ DEĞİŞMEZ: kod SİLİNMEDİ, tek satırlık ayarla geri dönülüyor.

    Sahip: "ileride tekrar hibrit esp stm ya da sadece esp sistemine dönebilirim."
    Bu kapı, devre-dışı bırakmanın geri DÖNÜLEBİLİR olduğunu kanıtlar.
    """
    from servers import live_state

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    assert live_state.esp_etkin() is True


def test_KRITIK_ESP_kapaliyken_MQTT_rozeti_ARIZA_gostermez(durum, monkeypatch):
    """Kurulu olmayan alt sistem için kalıcı sarı/kırmızı rozet = uyarı körlüğü.

    MUTASYON: `mqtt.broker.status` işleyicisindeki `esp_etkin()` dalını sil → KIRMIZI.
    """
    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    api_server._handle_backend_event(_olay("mqtt.broker.status", {"port_open": False, "running": False}))
    with durum._live_state_lock:
        assert durum._live_state["mqtt"] == "devre_disi", (
            "ESP sokulu iken broker durumu ARIZA olarak bildirildi -> kalici alarm"
        )


def test_KRITIK_ESP_ACIKKEN_broker_arizasi_YINE_bildirilir(durum, monkeypatch):
    """Karşıt kanıt: bayrak açıkken gerçek broker arızası GİZLENMEZ."""
    from servers import api_server

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    api_server._handle_backend_event(_olay("mqtt.broker.status", {"port_open": False, "running": False}))
    with durum._live_state_lock:
        assert durum._live_state["mqtt"] == "warning"


def test_KRITIK_ESP_kapaliyken_MQTT_dinleyicisi_BASLAMAZ(monkeypatch):
    """Broker yokken `connect_async` sonsuz yeniden dener → log seli + boşa kaynak.

    MUTASYON: `_start_mqtt_for_api` başındaki `esp_etkin()` kapısını sil → KIRMIZI.
    """
    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    cagrildi = {"paho": False}

    class _SahtePaho:
        def __getattr__(self, _ad):
            cagrildi["paho"] = True
            raise AssertionError("ESP KAPALIYKEN paho.mqtt'ye DOKUNULDU")

    monkeypatch.setitem(sys.modules, "paho.mqtt.client", _SahtePaho())
    api_server._start_mqtt_for_api()
    assert cagrildi["paho"] is False


# ============================================================================
# 3. ESP KAYNAK KODU SİLİNMEDİ (geri dönüş yolu AÇIK)
# ============================================================================


@pytest.mark.parametrize(
    "yol",
    [
        "firmware/esps3_pemf_coil",
        "firmware/esp8266_pemf_coil",
    ],
)
def test_KRITIK_ESP_firmware_kaynagi_DURUYOR(yol):
    """⚠️ Sahip AÇIKÇA "asla silme" dedi. Devre dışı bırakmak SİLMEK DEĞİLDİR.

    MUTASYON: klasörü sil → KIRMIZI. Bu kapı, "temizlik" amaçlı bir sonraki turda
    kaynağın sessizce kaldırılmasını engeller.
    """
    d = KOK / yol
    assert d.is_dir(), f"{yol} SILINMIS -> ESP'ye geri donus yolu kapandi (sahip: 'asla silme')"
    assert any(d.rglob("*.cpp")) or any(d.rglob("*.ino")), f"{yol} bos -> kaynak kaybolmus"


def test_KRITIK_ESP_calisma_zamani_kodu_da_DURUYOR():
    """MQTT/ESP sürüş yolları yorum satırına alınmadı, YERİNDE duruyor."""
    kaynak = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8", errors="replace")
    for isaret in ("_start_mqtt_for_api", "_on_mqtt_message_api", "_mqtt_publish"):
        assert f"def {isaret}" in kaynak, (
            f"`{isaret}` kaldirilmis -> ESP'ye geri donus tek satirlik ayar olmaktan CIKTI"
        )


# ============================================================================
# 4. SİMÜLASYON BAĞLANTIDAN TÜREMEZ (sahte veri kapısı)
# ============================================================================


def test_KRITIK_simulasyon_BAGLANTIDAN_turetilmez():
    """⚠️ Sahip "gösterilen değerler gerçek değil" dedi — bu iddia ARAŞTIRILDI.

    `PEMF_SIMULATE` SAF bir ortam değişkenidir; internet/ağ durumundan TÜRETİLMEZ.
    Yani internetsiz bir klinik makinesi sahte veriye DÜŞMEZ.

    MUTASYON: simülasyon kararına bir ağ koşulu ekle (ör. `or not internet`) → KIRMIZI.
    Sahadaki etki: gerçek donanım bağlıyken uydurma sayılar gösterilir — bu deponun
    en tehlikeli arıza sınıfı.
    """
    import ast

    kaynak = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8", errors="replace")
    agac = ast.parse(kaynak)
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Compare):
            continue
        metin = ast.dump(dugum)
        if "PEMF_SIMULATE" not in metin:
            continue
        # Karşılaştırma YALNIZ ortam değişkeni ile sabit arasında olmalı.
        for yasak in ("internet", "gateway", "wsConnected", "connected", "online"):
            assert yasak not in metin, (
                f"simulasyon karari '{yasak}' ile birlesmis -> baglanti kaybinda SAHTE VERI riski"
            )
    # ⚠️ D5.58 (B-10.131): yukarıdaki tarama yalnız `Compare` düğümlerine bakıyordu — karar
    # `os.environ.get("PEMF_SIMULATE") == "1" or _live_state.get("internet") != "online"` olsa ağ koşulu AYRI bir Compare'de
    # kaldığı için YEŞİLDİ; `!= "0"` (tanımsızken de sim) de YEŞİLDİ (ölçüldü). Artık: (1) PEMF_SIMULATE geçen hiçbir `BoolOp`
    # yok (ek terim / koşul birleşimi yok); (2) sanal donanım döngüsünü başlatan TEK `if` var ve koşulu TAM OLARAK
    # `os.environ.get('PEMF_SIMULATE') == '1'`. Davranış kolu: test_KRITIK_DAVRANIS_baglanti_KOPUKKEN_sim_BASLAMAZ.
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.BoolOp) and "PEMF_SIMULATE" in ast.dump(dugum):
            raise AssertionError(
                f"simulasyon karari baska bir kosulla BIRLESTIRILMIS (satir {dugum.lineno}): {ast.unparse(dugum)}"
            )
    baslatanlar = [
        d
        for d in ast.walk(agac)
        if isinstance(d, ast.If)
        and "_hardware_simulation_loop" in ast.unparse(ast.Module(body=d.body, type_ignores=[]))
    ]
    assert len(baslatanlar) == 1, f"sanal donanim dongusunu baslatan tek `if` bekleniyordu ({len(baslatanlar)})"
    assert ast.unparse(baslatanlar[0].test) == "os.environ.get('PEMF_SIMULATE') == '1'", (
        f"sim karari saf ortam degiskeni degil: {ast.unparse(baslatanlar[0].test)}"
    )
    # ⚠️ D5.58 TUR 2 (çürütme a2 / a3): yukarıdaki kol başlatıcıyı yalnız `If.body` METNİNDE arıyordu — `else` dalında
    # (`if stm == "online": pass` + `else: Thread(target=_hardware_simulation_loop)`) ya da BAŞKA bir işlevde (`def _sim_yedegi():
    # Thread(...)` + STM kopuş olayından çağrı) başlatılan ikinci yol YEŞİLDİ (ölçüldü). Artık: döngü adına modülde TEK başvuru var
    # (tanımı hariç; ad / öznitelik / dizge), o başvuru `_start_background_threads`'in DOĞRUDAN gövdesindeki saf karar `if`'inin
    # GÖVDESİNDE (koşul / `else` değil, iç içe işlev değil) ve başka hiçbir backend modülü adı anmaz (dolaylı başlatma yok).
    hedef_if = baslatanlar[0]
    ebeveyn = {alt: d for d in ast.walk(agac) for alt in ast.iter_child_nodes(d)}
    basvurular = [
        d
        for d in ast.walk(agac)
        if (isinstance(d, ast.Name) and d.id == "_hardware_simulation_loop")
        or (isinstance(d, ast.Attribute) and d.attr == "_hardware_simulation_loop")
        or (isinstance(d, ast.Constant) and d.value == "_hardware_simulation_loop")
    ]
    assert len(basvurular) == 1, (
        "sanal donanim dongusune TEK basvuru (karar if'inin govdesi) bekleniyordu; basvuru satirlari "
        f"{[d.lineno for d in basvurular]} -> ikinci / dolayli baslatma yolu (baglanti kopunca SAHTE VERI riski)"
    )
    d = basvurular[0]
    while d is not hedef_if:
        ust = ebeveyn.get(d)
        assert ust is not None, (
            f"sanal donanim dongusu karar if'inin DISINDA baslatiliyor (satir {basvurular[0].lineno})"
        )
        assert not isinstance(ust, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)), (
            f"sanal donanim dongusu karar if'i icinde IC ICE bir islevden baslatiliyor (satir {basvurular[0].lineno})"
        )
        if ust is hedef_if:
            assert any(d is g for g in hedef_if.body), (
                f"sanal donanim dongusu karar if'inin GOVDESINDE degil (kosul / else dali; satir {basvurular[0].lineno})"
            )
        d = ust
    fonk = ebeveyn.get(hedef_if)
    assert (
        isinstance(fonk, ast.FunctionDef)
        and fonk.name == "_start_background_threads"
        and any(hedef_if is g for g in fonk.body)
    ), f"sim karar if'i `_start_background_threads`'in dogrudan govdesinde degil: {getattr(fonk, 'name', fonk)!r}"
    diger = sorted(
        str(p.relative_to(KOK))
        for p in (KOK / "apps" / "backend").rglob("*.py")
        if p.relative_to(KOK).as_posix() != "apps/backend/servers/api_server.py"
        and "_hardware_simulation_loop" in p.read_text(encoding="utf-8", errors="replace")
    )
    assert not diger, f"sanal donanim dongusunu baska backend modulu aniyor (dolayli baslatma): {diger}"


@pytest.mark.parametrize("deger", [None, "", "0", "1"])
def test_KRITIK_DAVRANIS_baglanti_KOPUKKEN_sim_BASLAMAZ(durum, monkeypatch, deger):
    """D5.58 (B-10.131) davranış kolu: GERÇEK arka plan başlatıcısı (lifespan'ın çağırdığı), bütün bağlantılar
    KOPUKKEN (internet / gateway / mqtt / stm) koşar — sanal donanım döngüsü YALNIZ `PEMF_SIMULATE=1` ile başlar.
    Gerçek daemon AÇILMAZ: Thread kaydedicisi (`test_session_watchdog` deseni). AST kolu adı / biçimi pinler, bu
    kol karar ifadesinin BAŞKA bir yazılışını (yardımcı işlev, ikinci başlatıcı, varsayılan değer) da yakalar.

    MUTASYON: karara `or _live_state.get("internet") != "online"` · `!= "0"` · ikinci başlatıcı → KIRMIZI."""
    import threading
    from types import SimpleNamespace

    from servers import api_server, efield_live

    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve()
    gercek = c._GERCEK_ARKA_PLAN_BASLATICI
    assert callable(gercek), "aparat: conftest gerçek arka plan başlatıcısını kaydetmedi"
    baslatilan: list = []

    class _KayitThread(threading.Thread):
        def start(self):  # daemon AÇILMAZ — yalnız kayıt
            baslatilan.append((self.name, self._target))

    monkeypatch.setattr(api_server, "_threading", SimpleNamespace(Thread=_KayitThread))
    monkeypatch.setattr(api_server, "_bg_threads_started", False)
    monkeypatch.setattr(efield_live, "start_loop", lambda **k: None)
    for alan in ("internet", "gateway", "mqtt", "stm"):
        monkeypatch.setitem(api_server._live_state, alan, "offline")
    if deger is None:
        monkeypatch.delenv("PEMF_SIMULATE", raising=False)
    else:
        monkeypatch.setenv("PEMF_SIMULATE", deger)
    gercek()
    assert baslatilan, "aparat: başlatıcı hiçbir iş parçacığı kaydetmedi (VAKUM)"
    sim = [ad for ad, hedef in baslatilan if hedef is api_server._hardware_simulation_loop]
    if deger == "1":
        assert len(sim) == 1, f"PEMF_SIMULATE=1 iken sanal donanım TEK kez başlamalıydı: {baslatilan}"
    else:
        assert not sim, (
            f"PEMF_SIMULATE={deger!r} iken bağlantı kopuk diye sanal donanım BAŞLADI ({sim}) -> gerçek donanım "
            "yokken/kopukken UYDURMA veri (sahte telemetri) gösterilir"
        )


#: Ortam yazıcıları (`test_pemf_simulate_tek_kaynak._YAZICILAR` + `update`): ürün kodunda HİÇBİR kapsamda (işlev gövdesi dahil)
#: `PEMF_SIMULATE` anahtarıyla çağrılamaz.
_SIM_ANAHTARI = "PEMF_SIMULATE"
_ORTAM_YAZICILARI = frozenset(
    {"setdefault", "pop", "update", "__setitem__", "__delitem__", "putenv", "unsetenv", "setenv", "delenv"}
)


def _sim_anahtari_yazimlari(agac) -> list[str]:
    """Modülde (her kapsamda) `PEMF_SIMULATE` ortam YAZIMI: yazıcı çağrısı (konumsal / anahtar sözcük değeri / sözlük anahtarı /
    `PEMF_SIMULATE=` anahtar sözcüğü), `[...] =` / `del [...]` / `|=` hedefi. Karar yalnız OKUR (`os.environ.get`)."""
    import ast

    def _anahtar(d) -> bool:
        return isinstance(d, ast.Constant) and d.value == _SIM_ANAHTARI

    def _anahtar_tasir(d) -> bool:
        if _anahtar(d):
            return True
        if isinstance(d, ast.Dict):
            return any(k is not None and _anahtar(k) for k in d.keys)
        if isinstance(d, ast.Call):
            return any(kw.arg == _SIM_ANAHTARI for kw in d.keywords) or any(_anahtar_tasir(a) for a in d.args)
        if isinstance(d, (ast.List, ast.Tuple, ast.Set)):
            return any(_anahtar_tasir(e) for e in d.elts)
        if isinstance(d, ast.Starred):
            return _anahtar_tasir(d.value)
        return False

    out = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _ORTAM_YAZICILARI:
            if any(_anahtar_tasir(a) for a in d.args) or any(
                kw.arg == _SIM_ANAHTARI or _anahtar_tasir(kw.value) for kw in d.keywords
            ):
                out.append(f"satır {d.lineno}: {ast.unparse(d)}")
        elif isinstance(d, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            hedefler = d.targets if isinstance(d, (ast.Assign, ast.Delete)) else [d.target]
            if any(isinstance(h, ast.Subscript) and _anahtar(h.slice) for h in hedefler) or (
                isinstance(d, ast.AugAssign) and _anahtar_tasir(d.value)
            ):
                out.append(f"satır {d.lineno}: {ast.unparse(d)}")
    return out


def test_KRITIK_PEMF_SIMULATE_urun_kodunda_YAZILMAZ_D5_58():
    """D5.58 TUR 3 (çürütme 2 a4): TUR 2 kolları sim kararının METNİNİ ve döngünün TEK başvurusunu pinliyordu, karar GİRDİSİNİ
    değil — lifespan'de `if _live_state.get("stm") != "online": os.environ.setdefault("PEMF_SIMULATE", "1")` (STM kopuk diye
    üretim backend'i sanal donanıma geçer; B-10.131'in tam sınıfı) D5.58 kapılarında YEŞİLDİ, yalnız conftest'in hijyen bekçisi
    ERROR verdi (ölçüldü). Artık `apps/backend/**/*.py` ürün kodunda:
      (1) hiçbir kapsamda `PEMF_SIMULATE` ortam YAZIMI yok (`os.environ[...] =`, `setdefault`, `update` (sözlük / anahtar sözcük),
          `putenv`, `pop`, `del`, `|=` …; `pop` / `del` de sayılır — fail-closed);
      (2) KAPALI DÜNYA: `"PEMF_SIMULATE"` dizge sabiti TEK yerde — sim karar `if`'inin `os.environ.get(...)` argümanı (takma ad
          `_AD = "PEMF_SIMULATE"` ile dolaylı yazım da ikinci sabit olur); anahtarın ≥5 karakterlik PARÇASI olan sabit yok
          (`"PEMF_" + "SIMULATE"` birleştirmesi); `PEMF_SIMULATE=` anahtar sözcüğü yok.
    Sim kararı yalnız sunucu / staging / Docker ortam dosyasından gelir (`deploy/*.env`, `docker/*`); ürün onu YAZMAZ.
    Davranış kolu: `test_KRITIK_DAVRANIS_lifespan_PEMF_SIMULATE_YAZMAZ_sim_BASLATMAZ_D5_58`.

    MUTASYON: lifespan'e STM-kopuk koşullu `setdefault` (a4) → KIRMIZI; takma adla `os.environ[_AD] = "1"` → KIRMIZI."""
    import ast

    dosyalar = sorted((KOK / "apps" / "backend").rglob("*.py"))
    assert len(dosyalar) >= 50, f"VAKUM: apps/backend altında yalnız {len(dosyalar)} .py dosyası tarandı"
    yazimlar: list[str] = []
    sabitler: list[tuple[str, int, object]] = []
    parcalar: list[str] = []
    ana = "apps/backend/servers/api_server.py"
    ana_agac = None
    for p in dosyalar:
        yol = p.relative_to(KOK).as_posix()
        agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        if yol == ana:
            ana_agac = agac
        yazimlar += [f"{yol} {y}" for y in _sim_anahtari_yazimlari(agac)]
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                if d.value == _SIM_ANAHTARI:
                    sabitler.append((yol, d.lineno, d))
                elif len(d.value) >= 5 and d.value in _SIM_ANAHTARI:
                    parcalar.append(f"{yol}:{d.lineno} {d.value!r}")
            elif isinstance(d, ast.keyword) and d.arg == _SIM_ANAHTARI:
                yazimlar.append(f"{yol} satır {d.value.lineno}: `{_SIM_ANAHTARI}=` anahtar sözcüğü")
    assert not yazimlar, (
        f"ürün kodu PEMF_SIMULATE YAZIYOR: {yazimlar} -> sim kararı bağlantıdan / çalışma anından türetilebilir (STM kopukken "
        "sanal donanım = SAHTE telemetri). Sim yalnız dağıtım ortam dosyasından istenir."
    )
    assert not parcalar, (
        f"PEMF_SIMULATE anahtarının PARÇASI dizge sabiti: {parcalar} -> birleştirilmiş anahtarla dolaylı yazım taranamaz"
    )
    assert ana_agac is not None, f"aparat: {ana} bulunamadı"
    assert len(sabitler) == 1, (
        f"'PEMF_SIMULATE' sabiti TEK yerde (sim karar okuması) bekleniyordu: {[(y, s) for y, s, _ in sabitler]} -> takma ad / "
        "ikinci okuma-yazma yolu"
    )
    yol, satir, sabit = sabitler[0]
    ebeveyn = {alt: d for d in ast.walk(ana_agac) for alt in ast.iter_child_nodes(d)}
    cagri = ebeveyn.get(sabit)
    karsilastirma = ebeveyn.get(cagri)
    karar = ebeveyn.get(karsilastirma)
    assert (
        yol == ana
        and isinstance(cagri, ast.Call)
        and ast.unparse(cagri.func) == "os.environ.get"
        and cagri.args
        and cagri.args[0] is sabit
        and isinstance(karar, ast.If)
        and karar.test is karsilastirma
        and "_hardware_simulation_loop" in ast.unparse(ast.Module(body=karar.body, type_ignores=[]))
    ), f"tek 'PEMF_SIMULATE' sabiti sim karar if'inin `os.environ.get(...)` okuması değil ({yol}:{satir})"


def test_KRITIK_DAVRANIS_lifespan_PEMF_SIMULATE_YAZMAZ_sim_BASLATMAZ_D5_58(monkeypatch):
    """D5.58 TUR 3 (çürütme 2 a4) davranış kolu: GERÇEK lifespan (TestClient), bütün bağlantılar KOPUKKEN ve `PEMF_SIMULATE`
    TANIMSIZKEN girilir. Arka plan başlatıcısı GERÇEĞİYLE (conftest'in kaydettiği) Thread KAYDEDİCİSİ altında koşar (daemon
    açılmaz). Beklenen: başlatıcı çağrıldığı AN env hâlâ tanımsız, lifespan sonunda da tanımsız ve kayıtçıda
    `_hardware_simulation_loop` hedefli iş parçacığı YOK. AST kolunun göremediği yazılışları (hesaplanan anahtar, yardımcı modül)
    lifespan yolunda yakalar. ESP alt sistemi kapalı tutulur → MQTT bağlantı denemesi YOK (1883'e gidilmez); mDNS conftest'te engelli.

    MUTASYON: lifespan'e `if _live_state.get("stm") != "online": os.environ.setdefault("PEMF_SIMULATE", "1")` (a4) → KIRMIZI."""
    import os
    import threading
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from servers import api_server, efield_live, live_state

    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve()
    gercek = c._GERCEK_ARKA_PLAN_BASLATICI
    assert callable(gercek), "aparat: conftest gerçek arka plan başlatıcısını kaydetmedi"
    baslatilan: list = []
    anlik: list = []

    class _KayitThread(threading.Thread):
        def start(self):  # daemon AÇILMAZ — yalnız kayıt
            baslatilan.append((self.name, self._target))

    def _sarici():
        anlik.append(os.environ.get(_SIM_ANAHTARI))
        gercek()

    monkeypatch.setattr(api_server, "_threading", SimpleNamespace(Thread=_KayitThread))
    monkeypatch.setattr(api_server, "_bg_threads_started", False)
    monkeypatch.setattr(api_server, "_start_background_threads", _sarici)
    monkeypatch.setattr(efield_live, "start_loop", lambda **k: None)
    monkeypatch.setattr(live_state, "esp_etkin", lambda: False)
    monkeypatch.setattr(api_server.live_state, "esp_etkin", lambda: False, raising=False)
    for alan in ("internet", "gateway", "mqtt", "stm"):
        monkeypatch.setitem(api_server._live_state, alan, "offline")
    monkeypatch.delenv(_SIM_ANAHTARI, raising=False)
    try:
        with TestClient(api_server.app):
            pass
        sonra = os.environ.get(_SIM_ANAHTARI)
    finally:
        os.environ.pop(_SIM_ANAHTARI, None)  # karar aşağıda; conftest hijyen bekçisi ikinci kez kırmızı yazmasın
    assert anlik, "aparat: lifespan arka plan başlatıcısına ULAŞMADI (VAKUM)"
    assert baslatilan, "aparat: gerçek başlatıcı hiçbir iş parçacığı kaydetmedi (VAKUM)"
    assert anlik == [None] and sonra is None, (
        f"lifespan bağlantılar kopukken PEMF_SIMULATE YAZDI (başlatıcı anında {anlik}, sonunda {sonra!r}) -> STM kopuk diye "
        "üretim backend'i sanal donanıma geçer (SAHTE telemetri)"
    )
    sim = [ad for ad, hedef in baslatilan if hedef is api_server._hardware_simulation_loop]
    assert not sim, f"lifespan bağlantılar kopukken sanal donanım BAŞLATTI: {sim}"


#: D5.58 TUR 3b (çürütme 3 a5 / a5b): AST kolu yalnız `apps/backend/**`'u tarıyordu — backend'in ÇALIŞMA ANINDA içe aktardığı depo
#: kökü modülleri (`pemf_gui/config.py`: `database/patient_database.py` onu modül düzeyinde içe aktarır; `ai_hub`, `ai_service`,
#: `build_tools` PyInstaller kancaları …) kapsam DIŞIYDI. Geliştirme ağaçları hariç: çalışma anında backend'e GİRMEZLER; sim'i
#: kendi başlattıkları backend alt sürecine env ile verirler (`tools/e2e_ortam.py`, `scripts/urun_senaryolari.py`).
_GELISTIRME_AGACLARI = ("tests/", "tools/", "scripts/", "training_archive/")


def _izlenen_calisma_agaci_py() -> list[Path]:
    """İzlenen (`git ls-files`) çalışma ağacı .py dosyaları, geliştirme ağaçları hariç. İzlenmeyen derleme çıktısı (`PEMF_BUILD/dist`
    — ürün kaynağının KOPYALARI) ve yerel dosyalar bilerek dışarıda: kapı temiz ağacı ölçer. git yoksa / düşerse KIRMIZI (atlama yok)."""
    import subprocess

    r = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "*.py"], cwd=KOK, capture_output=True, timeout=120
    )
    assert r.returncode == 0, f"aparat: git ls-files başarısız (rc={r.returncode}): {r.stderr[-500:]!r}"
    adlar = [a for a in r.stdout.decode("utf-8").split("\0") if a and not a.startswith(_GELISTIRME_AGACLARI)]
    return [KOK / a for a in adlar if (KOK / a).is_file()]


def test_KRITIK_PEMF_SIMULATE_KAPALI_DUNYA_tum_calisma_agacinda_D5_58():
    """D5.58 TUR 3b (çürütme 3 a5b): `pemf_gui/config.py`'de (apps/backend DIŞI, ama backend'in içe aktardığı) çağrılmayan
    `def _gelistirici_sim_ac(): os.environ.setdefault("PEMF_SIMULATE", "1")` D5.58 kapı listesinde YEŞİLDİ (34 passed; ölçüldü) —
    işlev bir istek / iş parçacığı yolundan çağrılırsa canlı. Artık KAPALI DÜNYA çalışma ağacının tamamında (izlenen .py, geliştirme
    ağaçları hariç; vakum ≥150 dosya + çapalar): `"PEMF_SIMULATE"` dizge sabiti / `PEMF_SIMULATE=` anahtar sözcüğü YALNIZ
    `apps/backend/servers/api_server.py`'de, TEK yerde (sim karar okuması — biçimini `test_KRITIK_PEMF_SIMULATE_urun_kodunda_YAZILMAZ_D5_58`
    pinler); anahtarın ≥5 karakterlik PARÇASI olan sabit yok (birleştirme / f-dizge). Ayrıştırılamayan dosya da KIRMIZI (taranamayan
    dosya kapıyı kör eder).

    MUTASYON: `pemf_gui/config.py`'ye çağrılmayan işlevde `setdefault` (a5b) → KIRMIZI; aynı yere içe aktarma anında yazım (a5) →
    KIRMIZI (davranış kolu: `test_KRITIK_DAVRANIS_api_server_ICE_AKTARILINCA_PEMF_SIMULATE_YAZILMAZ_D5_58`)."""
    import ast

    dosyalar = _izlenen_calisma_agaci_py()
    taranan = {p.relative_to(KOK).as_posix() for p in dosyalar}
    assert len(dosyalar) >= 150, f"VAKUM: çalışma ağacında yalnız {len(dosyalar)} izlenen .py tarandı"
    capalar = {"apps/backend/servers/api_server.py", "apps/backend/database/patient_database.py", "pemf_gui/config.py"}
    assert capalar <= taranan, f"VAKUM: çapa dosyaları taranmadı: {sorted(capalar - taranan)}"
    yerler: list[str] = []
    parcalar: list[str] = []
    ayrismayan: list[str] = []
    for p in dosyalar:
        yol = p.relative_to(KOK).as_posix()
        try:
            agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            ayrismayan.append(f"{yol}: {e.msg} (satır {e.lineno})")
            continue
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                if d.value == _SIM_ANAHTARI:
                    yerler.append(f"{yol}:{d.lineno}")
                elif len(d.value) >= 5 and d.value in _SIM_ANAHTARI:
                    parcalar.append(f"{yol}:{d.lineno} {d.value!r}")
            elif isinstance(d, ast.keyword) and d.arg == _SIM_ANAHTARI:
                yerler.append(f"{yol}:{d.value.lineno} (`{_SIM_ANAHTARI}=` anahtar sözcüğü)")
    assert not ayrismayan, f"çalışma ağacında AYRIŞTIRILAMAYAN .py (taranamadı — kapı kör): {ayrismayan}"
    assert not parcalar, (
        f"PEMF_SIMULATE anahtarının PARÇASI dizge sabiti: {parcalar} -> birleştirilmiş anahtarla dolaylı yazım taranamaz"
    )
    disarida = [y for y in yerler if not y.startswith("apps/backend/servers/api_server.py:")]
    assert not disarida and len(yerler) == 1, (
        f"PEMF_SIMULATE sabiti sim kararı DIŞINDA da geçiyor: {yerler} — backend'in içe aktardığı bir modül (apps/backend dışı "
        "dahil) sim kararını yazabilir / türetebilir (STM kopukken sanal donanım = SAHTE telemetri)"
    )


def test_KRITIK_DAVRANIS_api_server_ICE_AKTARILINCA_PEMF_SIMULATE_YAZILMAZ_D5_58():
    """D5.58 TUR 3b (çürütme 3 a5): `pemf_gui/config.py` modül gövdesinde `os.environ.setdefault("PEMF_SIMULATE", "1")` (backend onu
    içe aktarma ANINDA yükler) D5.58 kollarında YEŞİLDİ — AST kolu `apps/backend/**` dışını görmüyordu, lifespan kolu env'i lifespan'den
    ÖNCE siler; yalnız conftest hijyen bekçisi YANLIŞ teşhisle ("toplama / fixture bıraktı") kırmızı veriyordu. TAZE alt süreçte (env'de
    anahtar YOK) `servers.api_server` içe aktarılır → sonrasında anahtar hâlâ YOK. Hesaplanan anahtar / `chr()` hilesi gibi AST'nin
    göremediği içe aktarma anı yazımlarını da yakalar.
    Aparat: yalnız İÇE AKTARMA (lifespan / ağ / port YOK). Alt süreç pytest sürecinin İZOLE env'ini miras alır (conftest: veri kökü /
    APPDATA / makine kimliği oturum temp'inde, python-keyring null) — koşmadan ÖNCE doğrulanır; alt süreç de aynı APPDATA'yı görmeli.

    MUTASYON: `pemf_gui/config.py` modül gövdesine `setdefault` (a5) → KIRMIZI."""
    import ast
    import os
    import subprocess

    c = sys.modules.get("conftest")
    assert c is not None and Path(c.__file__).resolve() == (Path(__file__).parent / "conftest.py").resolve()
    veri = os.environ.get("PEMF_DATA_DIR", "")
    gercek = getattr(c, "_ORIJINAL_APPDATA", None)
    assert (
        veri
        # conftest'in iki yalıtım biçimi: test başına `<tmp_path>/_izole_appdata`, oturum tabanı `pemf_test_veri_*` (temp)
        and (Path(veri).name == "_izole_appdata" or Path(veri).name.startswith("pemf_test_veri_"))
        and not (gercek and Path(gercek).resolve() in (Path(veri).resolve(), *Path(veri).resolve().parents))
        and os.environ.get("APPDATA") == veri
        and Path(os.environ.get("PEMF_DEVICE_IDENTITY_DIR", "")).parent == Path(veri)
        and os.environ.get("PYTHON_KEYRING_BACKEND") == "keyring.backends.null.Keyring"
    ), "aparat: alt süreç İZOLE env miras almıyor (conftest veri kökü / makine kimliği / kasa yalıtımı yok) — koşulmadı"
    kod = (
        "import os, sys\n"
        f"sys.path[:0] = [{str(KOK / 'apps' / 'backend')!r}, {str(KOK)!r}]\n"
        f"once = os.environ.get({_SIM_ANAHTARI!r})\n"
        "import servers.api_server\n"
        f"print('SONUC=' + repr((once, os.environ.get({_SIM_ANAHTARI!r}), os.environ.get('APPDATA'))))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != _SIM_ANAHTARI}
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-c", kod],
        cwd=str(KOK),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC=")]
    assert r.returncode == 0 and satir, (
        f"aparat: alt süreç servers.api_server'ı içe aktaramadı (rc={r.returncode}): {r.stderr[-1500:]}"
    )
    once, sonra, appdata = ast.literal_eval(satir[-1][len("SONUC=") :])
    assert appdata == veri, f"aparat: alt süreç izole APPDATA'yı görmedi ({appdata!r} ≠ {veri!r})"
    assert once is None, f"aparat: alt süreç PEMF_SIMULATE={once!r} ile başladı (env süzülmedi)"
    assert sonra is None, (
        f"servers.api_server İÇE AKTARILINCA PEMF_SIMULATE yazıldı ({sonra!r}) — sim kararı lifespan'den ÖNCE, içe aktarılan bir "
        "modülde kuruluyor (üretimde STM kopukken / koşulsuz sanal donanım = SAHTE telemetri)"
    )


def test_KRITIK_ESP_kapaliyken_MQTT_PUBLISH_hic_denenmez(monkeypatch):
    """⚠️ TEK BOĞAZ NOKTASI: bütün ESP komutları `_mqtt_publish`ten geçer.

    Kapı burada olmazsa her komut (manuel, seans, AI, E-stop, reconcile, selftest) sökülü
    donanım için soket probu açar ve `_kaydet_esp_komut_niyeti` ile BAYAT niyet biriktirir.
    O niyet, ileride `PEMF_ESP_ENABLED=1` ile dönüldüğünde reconcile'ı yanlış tetikler.

    ⚠️ "False döndü" YETMEZ — broker yokken zaten False döner. Bu kapı DENENMEDİĞİNİ ölçer:
    soket açılmamalı ve niyet yazılmamalı.

    MUTASYON: `_mqtt_publish` başındaki `esp_etkin()` kapısını sil → KIRMIZI.
    """
    import socket as _socket

    from servers import api_server

    monkeypatch.delenv("PEMF_ESP_ENABLED", raising=False)
    izler = {"soket": 0, "niyet": 0}

    def _soket_yasak(*a, **k):
        izler["soket"] += 1
        raise OSError("baglanti yok")

    monkeypatch.setattr(_socket, "create_connection", _soket_yasak)
    monkeypatch.setattr(
        api_server, "_kaydet_esp_komut_niyeti", lambda *a, **k: izler.__setitem__("niyet", izler["niyet"] + 1)
    )

    sonuc = api_server._mqtt_publish("pemf/coil/8/control", {"command": "stop"})

    assert sonuc is False, "ESP kapaliyken 'gonderildi' denildi -> gonderilmemis komut teyit edildi"
    assert izler["soket"] == 0, "ESP kapaliyken SOKET acildi -> kapi calismiyor"
    assert izler["niyet"] == 0, "ESP kapaliyken NIYET kaydedildi -> geri donuste bayat reconcile"


def test_KRITIK_ESP_ACIKKEN_publish_GERCEKTEN_denenir(monkeypatch):
    """Karşıt kanıt: bayrak açıkken yol kapanmamalı (geri dönüş GERÇEKTEN çalışmalı)."""
    import socket as _socket

    from servers import api_server

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    izler = {"soket": 0}

    def _soket_sayac(*a, **k):
        izler["soket"] += 1
        raise OSError("broker yok")

    monkeypatch.setattr(_socket, "create_connection", _soket_sayac)
    api_server._mqtt_publish("pemf/coil/8/control", {"command": "stop"})
    assert izler["soket"] == 1, "ESP ACIKKEN publish denenmedi -> geri donus yolu KOPUK"


# ============================================================================
# 4. DONMUŞ "İNTERNET YOK" ROZETİ + YALAN YEŞİL "İnternet Bağlantısı"
#    (sahip bildirimi 2026-09-12: "makinede internet olmasına rağmen yok diyor")
# ============================================================================
#
# ÖLÇÜLEN GERÇEK: çalışan backend `/api/dashboard-snapshot` → `"internet":"online"`
# derken ekrandaki rozet "İnternet yok — uzaktan erişim kapalı" yazıyordu ve AYNI
# ekranda "İnternet Bağlantısı: Aktif" satırı yeşildi. İkisi AYNI şeyi ölçmüyordu:
#
#   · Rozet   → WS `snapshot.internet`. `internet` HESAPLANIYOR ama `gateway_status`
#               yayınının İÇİNE KONMUYORDU → ilk snapshot'tan sonra ASLA güncellenmiyor.
#               `network.status` olayı da YALNIZ DEĞİŞİMDE yayınlandığı için değer
#               sonsuza dek donuyordu (başlangıç değeri: "offline").
#   · Satır   → `/gateway/status.networkOnline`, içinde `or gateway_state == "online"
#               or mqtt_state == "online"` vardı. `gateway` hotspot/herhangi bir mod
#               açıkken online, `mqtt` ise 127.0.0.1'deki yerel mosquitto → satır
#               kablo çekili olsa bile YEŞİL. Yani "Kapalı" diyemiyordu.
#
# ⚠️ SINIF: yalan-yeşil, yalan-kırmızıdan DAHA tehlikelidir — operatörün bakacağı satır
# odur ve "internet var" dediği için uzaktan erişim arızası hiç aranmaz.


def test_KRITIK_gateway_status_yayini_INTERNET_TASIR(durum, monkeypatch):
    """⚠️ ASIL KAPI — donmuş rozetin kökü.

    `internet` yayının içinde gitmezse arayüz onu YALNIZ ilk snapshot'ta görür;
    sonraki her değişim SESSİZCE kaybolur.

    MUTASYON: `_ws_broadcast_sync` çağrısındaki `"internet": ...` anahtarını sil → KIRMIZI.
    """
    from servers import api_server

    yayinlar: list[dict] = []
    monkeypatch.setattr(api_server, "_ws_broadcast_sync", lambda m: yayinlar.append(m))

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "hybrid", "hotspot_active": False, "internet_connected": True})
    )

    kapsayan = [m for m in yayinlar if m.get("type") == "gateway_status"]
    assert kapsayan, "network.status olayi gateway_status YAYINLAMADI"
    veri = kapsayan[-1].get("data", {})
    assert "internet" in veri, (
        "gateway_status yayini `internet` TASIMIYOR -> arayuzdeki rozet ilk snapshot'ta "
        "donar; internet sonradan gelse/gitse bile ASLA guncellenmez"
    )
    assert veri["internet"] == "online"


def test_KRITIK_internet_GIDERSE_de_yayinlanir(durum, monkeypatch):
    """Karşıt kanıt: kural "hep online yaz" diye geçilemesin."""
    from servers import api_server

    yayinlar: list[dict] = []
    monkeypatch.setattr(api_server, "_ws_broadcast_sync", lambda m: yayinlar.append(m))

    api_server._handle_backend_event(
        _olay("network.status", {"gateway_mode": "offline", "hotspot_active": True, "internet_connected": False})
    )
    veri = [m for m in yayinlar if m.get("type") == "gateway_status"][-1]["data"]
    assert veri["internet"] == "offline"
    # ...ve cihaz ağı yine de ONLINE kalmalı (uyarı körlüğü kapısı, yukarıdaki kuralla birlikte)
    assert veri["gateway"] == "online"


def test_KRITIK_networkOnline_INTERNETI_olcer_cihaz_agini_DEGIL(monkeypatch):
    """⚠️ YALAN YEŞİL KAPISI.

    Hotspot açık / yerel mosquitto çalışıyor ama internet YOK: "İnternet Bağlantısı"
    satırı "Kapalı" demek ZORUNDA.

    MUTASYON: `networkOnline` ifadesine `or gateway_state == "online"` (ya da
    `or mqtt_state == "online"`) geri ekle → KIRMIZI.
    """
    import asyncio

    from servers import api_server, system_router

    class _Cekirdek:
        def get_service_status(self):
            return {
                "mosquitto": {"running": True, "port_open": True},
                "network": {"internet_connected": False, "hotspot_active": True},
            }

    monkeypatch.setattr(api_server.state, "core", _Cekirdek(), raising=False)
    with api_server._live_state_lock:
        eski = dict(api_server._live_state)
        api_server._live_state["gateway"] = "online"
        api_server._live_state["mqtt"] = "online"
    try:
        sonuc = asyncio.run(system_router.gateway_status())
    finally:
        with api_server._live_state_lock:
            api_server._live_state.update(eski)

    assert sonuc["networkOnline"] is False, (
        "internet YOKKEN 'Internet Baglantisi' satiri YESIL gosterildi -> yalan guvence; "
        "operator uzaktan erisim arizasini hic aramaz"
    )
    # Karşıt kanıt: cihaz ağı bilgisi KAYBOLMADI, ayrı alanda duruyor.
    assert sonuc["bridgeConnected"] is True
    assert sonuc["hotspotActive"] is True


def test_networkOnline_internet_VARKEN_dogru(monkeypatch):
    """Karşıt kanıt: kural "hep False dön" diye geçilemesin."""
    import asyncio

    from servers import api_server, system_router

    class _Cekirdek:
        def get_service_status(self):
            return {
                "mosquitto": {"running": False, "port_open": False},
                "network": {"internet_connected": True, "hotspot_active": False},
            }

    monkeypatch.setattr(api_server.state, "core", _Cekirdek(), raising=False)
    with api_server._live_state_lock:
        eski = dict(api_server._live_state)
        api_server._live_state["gateway"] = "offline"
        api_server._live_state["mqtt"] = "offline"
    try:
        sonuc = asyncio.run(system_router.gateway_status())
    finally:
        with api_server._live_state_lock:
            api_server._live_state.update(eski)

    assert sonuc["networkOnline"] is True


def test_KRITIK_ag_durumu_DEGISMESE_DE_yeniden_yayinlanir(monkeypatch):
    """⚠️ KAYBOLAN TEK OLAY = KALICI YANLIŞ ARAYÜZ.

    `NetworkStatusService`, `HeadlessCore.__init__` içinde — yani
    `api_server._register_event_bus_handlers()` çağrılmadan ÖNCE — başlar. İlk
    `network.status` olayı işleyici kaydolmadan düşerse ve ağ durumu bir daha
    değişmezse, olay BİR DAHA ASLA yayınlanmaz: `_live_state["internet"]` başlangıç
    değerinde ("offline") donar ve makine internete bağlıyken bile rozet "İnternet yok"
    der. Ölçülen saha durumu tam olarak buydu.

    MUTASYON: `or son is None or (simdi - son) >= self.YENIDEN_YAYIN_S` koşulunu sil
    (yalnız `previous != status` bırak) → KIRMIZI.
    """
    import time as _time

    from services.headless_services import NetworkStatusService

    servis = NetworkStatusService(interval_seconds=0.01)
    yayinlar: list[str] = []
    monkeypatch.setattr(servis, "_publish", lambda tur, veri: yayinlar.append(tur))
    # Ölçümleri SABİTLE: durum hiç değişmeyecek, tek tetikleyici zaman olmalı.
    monkeypatch.setattr(servis, "_check_internet", lambda: True)
    monkeypatch.setattr(servis, "_check_hotspot", lambda: {"active": False, "ssid": "", "ip": "", "clients": 0})
    monkeypatch.setattr(servis, "_get_network_ips", lambda: {"ethernet": None, "wifi": None})
    monkeypatch.setattr("services.headless_services._is_tcp_port_open", lambda *a, **k: False)

    servis.check_once()
    assert yayinlar == ["network.status"], "ilk olcum yayinlanmadi"

    # Durum DEĞİŞMEDİ → yakın zamanda tekrar yayınlanmamalı (yayın seli olmasın).
    servis.check_once()
    assert len(yayinlar) == 1, "durum degismeden GEREKSIZ yayin yapildi (yayin seli)"

    # ...ama tazeleme aralığı dolduğunda yeniden yayınlanmalı.
    sahte_an = _time.monotonic() + servis.YENIDEN_YAYIN_S + 1.0
    monkeypatch.setattr("services.headless_services.time.monotonic", lambda: sahte_an)
    servis.check_once()
    assert len(yayinlar) == 2, (
        "ag durumu degismedigi icin BIR DAHA hic yayinlanmadi -> kaydolmayi kacirmis bir "
        "isleyici icin arayuz SONSUZA DEK yanlis kalir"
    )
