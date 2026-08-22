# Author: mertaygn, cglrgrkn
"""MQTT client_id BENZERSIZLIGI — sabit kimligin iki gercek arizasina karsi regresyon kilidi.

MQTT sozlesmesi: ayni client_id ile yeni baglanti gelirse broker ONCEKI oturumu dusurur.
Eskiden kimlikler sabitti ("api_server_ws_listener" / "api_server_pub"):

  1) DINLEYICI — yeniden baslatma/OTA penceresinde eski surec brokerde bir sure yasadigi icin
     iki taraf birbirini surekli dusuruyordu → bitmeyen "Sistem baglantisi kesildi/kuruldu"
     bildirimi + o sure boyunca ESP telemetri boslugu.
  2) YAYINCI — acil-durdurma ESP bobinlerine PARALEL yayin yapar (ThreadPoolExecutor, bobin
     basina 2 publish). Ucu de ayni kimligi kullandigindan broker yalniz sonuncuyu tutar →
     STOP komutu kaybolabilir. HASTA GUVENLIGI yolu.
"""

import concurrent.futures as cf
import os
import re

os.environ.pop("PEMF_SIMULATE", None)  # testlerde sim loop baslatma


def _cid(role):
    from servers.api_server import _mqtt_client_id

    return _mqtt_client_id(role)


def test_listener_id_is_process_scoped():
    """Dinleyici kimligi SUREC basina sabit ama surecler arasi FARKLI (PID icerir)."""
    a, b = _cid("ws"), _cid("ws")
    assert a == b, "ayni surecte dinleyici kimligi degismemeli (gereksiz reconnect)"
    assert str(os.getpid()) in a, f"kimlik PID icermeli: {a}"
    assert a != "api_server_ws_listener", "sabit kimlige geri donulmus"


def test_publisher_id_unique_per_call():
    """Her publish AYRI istemci acar → kimlik cagri basina benzersiz olmali."""
    ids = [_cid("pub") for _ in range(50)]
    assert len(set(ids)) == 50, "yayinci kimlikleri tekrar ediyor (broker baglantiyi dusurur)"
    assert all(i != "api_server_pub" for i in ids)


def test_publisher_id_unique_under_concurrency():
    """Acil-durdurma deseni: es-zamanli yayinlarda da carpisma OLMAMALI."""
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        ids = list(ex.map(lambda _: _cid("pub"), range(64)))
    assert len(set(ids)) == 64, "es-zamanli yayinci kimlikleri carpisiyor"


def test_ids_are_broker_safe():
    """MQTT 3.1 doneminden kalma brokerlar client_id'yi <=23 karakter + [A-Za-z0-9-_] ister."""
    for cid in (_cid("ws"), _cid("pub")):
        assert len(cid) <= 23, f"kimlik cok uzun ({len(cid)}): {cid}"
        assert re.fullmatch(r"[A-Za-z0-9_-]+", cid), f"gecersiz karakter: {cid}"


def test_emergency_stop_still_reaches_every_esp_coil(monkeypatch):
    """Kimlik degisikligi acil-durdurma kapsamini BOZMAMALI: 6,7,8'in hepsine yayin gider
    ve her yayin FARKLI bir client_id kullanir."""
    from servers import api_server

    seen = []

    def _fake_publish(topic, payload):
        seen.append((topic, api_server._mqtt_client_id("pub")))
        return True

    monkeypatch.setattr(api_server, "_mqtt_publish", _fake_publish)
    res = api_server._emergency_stop_all(reason="test", mode="Test")

    coils = {
        int(m.group(1))
        for t, _ in seen
        for m in [re.search(r"/(?:coil|esp32_)(\d+)", t.replace("esp32_", "esp32_"))]
        if m
    }
    assert {6, 7, 8} <= coils, f"tum ESP bobinlerine STOP gitmedi: {sorted(coils)}"
    cids = [c for _, c in seen]
    assert len(set(cids)) == len(cids), "acil-durdurma yayinlarinda kimlik tekrari var"
    assert res is not None


# ── [3.3] E-STOP BULUT AYNASI (2. tur denetimi; duzeltme 2026-08-22) ─────────────────────────
# estop-cloud rolu surec-sabit kimlik aliyordu (pemf_estop-cloud_{pid}). Iki gercek sorun:
#   1) CIFTE TETIK: E-stop iki kez pesipese tetiklenirse (panik aninda gercekci) iki ayna
#      oturumu HiveMQ'ya AYNI kimlikle baglanir → broker ilkini DUSURUR → ucustaki STOP
#      publish'leri kaybolabilir. Yayinci ('pub') icin cozulen arizanin birebir aynisi,
#      yalniz BULUT yolunda — ve bu rol test kapsami DISINDAYDI.
#   2) UZUNLUK: "pemf_estop-cloud_" 17 karakter; Linux pid_max=4194304 (7 hane) ile kimlik
#      24 karaktere tasar → MQTT 3.1 donemi brokerlarin 23 sinirini asar, baglanti REDDEDILIR
#      → ayna sessizce hic calismaz.


def test_KRITIK_estop_cloud_id_cagri_basina_benzersiz():
    """Cifte tetikte iki ayna oturumu birbirini dusurmemeli → kimlik cagriya ozgu olmali."""
    ids = [_cid("estop-cloud") for _ in range(50)]
    assert len(set(ids)) == 50, (
        "estop-cloud kimlikleri tekrar ediyor — cifte E-stop tetiginde broker onceki ayna "
        "oturumunu dusurur, ucustaki STOP kaybolabilir (denetim [3.3])"
    )


def test_KRITIK_estop_cloud_id_es_zamanli_carpismaz():
    """Gercek desen: iki tetik AYRI thread'lerden gelir (asyncio.to_thread)."""
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        ids = list(ex.map(lambda _: _cid("estop-cloud"), range(64)))
    assert len(set(ids)) == 64, "es-zamanli estop-cloud kimlikleri carpisiyor"


def test_KRITIK_estop_cloud_id_7_haneli_PID_de_broker_sinirinda(monkeypatch):
    """Linux pid_max=4194304: kimlik EN KOTU pid'de de <=23 kalmali, yoksa ayna hic baglanamaz."""
    import servers.api_server as api

    monkeypatch.setattr(api.os, "getpid", lambda: 4194304)
    for role in ("ws", "pub", "estop-cloud"):
        cid = api._mqtt_client_id(role)
        assert len(cid) <= 23, f"{role}: 7-haneli PID'de kimlik {len(cid)} karakter: {cid}"
        assert re.fullmatch(r"[A-Za-z0-9_-]+", cid), f"{role}: gecersiz karakter: {cid}"
