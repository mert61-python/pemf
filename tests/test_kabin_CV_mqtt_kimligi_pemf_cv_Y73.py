# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y73 (sahip, S-G8) — hazırlama adımı kabin kamerası MQTT'si için YALNIZ kendi konularına yazabilen ayrı bir `pemf_cv`
kimliği de üretir; kimlik kabin YAML'ının İÇİNE değil, ESP başlığı gibi AYRI dosyaya (`cabin_mqtt_kimlik.yaml`, gitignore)
yazılır; geliştirme aracı (soak yayıncısı) `--kullanici/--parola` alır. Kabin MQTT'si varsayılan KAPALI kalır.

ÖLÇÜLEN KUSUR (1-G §8 #8): kimlikli broker'da (A-04) kabin CV yayıncısının (`ai_hub/cv_ortak/mqtt_publish`) ve
`scripts/soak_publish_5hz_8coil.py`'nin bağlanabileceği bir kimlik YOKTU (yalnız backend + ESP) — tek yol parolayı kabin
YAML'ına elle yazmaktı (sır depoya girer) ya da backend/ESP kimliğini paylaşmak (CV, bobin control'üne yazabilir hâle gelir).

KAPI: GERÇEK `utils.mqtt_kimlik` (izole makine deposu) + GERÇEK `cabin_config.load_cabin_config` + GERÇEK mosquitto 2.0.18
(kurulum betiğinin yapılandırması, rastgele loopback portu): pemf_cv `pemf/coil/state`'e YAZAR, bobin control'üne / ack'e
YAZAMAZ; soak aracının sondası `--kullanici/--parola` ile kimlikli broker'a bağlanır.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import capraz
import mosquitto_aparat as ma
import pytest

KOK = Path(__file__).resolve().parents[1]
#: (profil dizini, profilin kabin YAML'ı). AI-2 C6: v1 `phantom_cv` / `petri_cv` (`cabin_config_example.yaml`) emekli →
#: hocanın v3 / v2'si; YAML'ları v1'in saha kabin çekirdeği + hocanın bölümü (output.mqtt AYNEN).
PROFILLER = (
    ("ai_hub/inference_em_fantom/phantom_cv_v3", "cabin_config_v3.yaml"),
    ("ai_hub/inference_petri_dish/petri_cv_v2", "cabin_config_v2.yaml"),
)
PROFIL_IDLERI = [d.rsplit("/", 1)[1] for d, _ in PROFILLER]


@pytest.fixture
def mk(monkeypatch, tmp_path):
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    mqtt_kimlik._onbellek.clear()
    yield mqtt_kimlik
    mqtt_kimlik._onbellek.clear()


def _acl_bolumu(acl: str, kullanici: str) -> list[str]:
    satirlar, icinde = [], False
    for s in acl.splitlines():
        s = s.strip()
        if s.startswith("user "):
            icinde = s == f"user {kullanici}"
            continue
        if icinde and s.startswith("topic "):
            satirlar.append(s)
    return satirlar


def test_KRITIK_hazirla_pemf_cv_kimligi_ve_YALNIZ_kendi_konulari(mk, tmp_path):
    bd = tmp_path / "broker"
    mk.hazirla(bd)
    k = mk.kimlikleri_oku()
    assert k and k.get("pemf_cv"), f"hazırlama pemf_cv kimliği ÜRETMEDİ: {sorted(k or {})}"
    satirlar = dict(s.split(":", 1) for s in (bd / "pemf_passwd").read_text(encoding="utf-8").splitlines() if s)
    assert mk.ozet7_dogrula(k["pemf_cv"], satirlar["pemf_cv"]), (
        "pemf_cv broker parola dosyasında depodakiyle doğrulanmıyor"
    )
    acl = _acl_bolumu((bd / "pemf_acl").read_text(encoding="utf-8"), "pemf_cv")
    assert acl == ["topic write pemf/coil/state", "topic read pemf/coil/cmd"], (
        f"pemf_cv yetkisi yalnız kendi konuları değil: {acl}"
    )


def test_KRITIK_eski_depo_YUKSELTILIR_backend_ESP_parolalari_DEGISMEZ(mk, tmp_path):
    from utils.secrets_manager import _enc

    depo = Path(mk._depo_yolu())
    depo.parent.mkdir(parents=True, exist_ok=True)
    eski = {"pemf_backend": "B" * 32, "pemf_esp": "E" * 32}
    depo.write_text(json.dumps({**{a: _enc(p, critical=True) for a, p in eski.items()}, "surum": 1}), encoding="utf-8")
    mk._onbellek.clear()
    r = mk.hazirla(tmp_path / "broker")
    k = mk.kimlikleri_oku()
    assert {a: k[a] for a in eski} == eski, "yükseltmede yakılmış backend/ESP parolası DEĞİŞTİ (A-18)"
    assert k.get("pemf_cv") and not r["depo_olustu"], f"eski depoya pemf_cv eklenmedi: {sorted(k)} / {r}"


def test_KRITIK_kabin_kimligi_YAN_DOSYAYA_yazilir_CLI_SIR_basmaz(mk, tmp_path, capsys):
    kabin = tmp_path / "kabin"
    kabin.mkdir()
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker"), "--kabin", str(kabin)]) == 0
    cikti = capsys.readouterr().out
    import yaml

    yan = yaml.safe_load((kabin / "cabin_mqtt_kimlik.yaml").read_text(encoding="utf-8"))
    parola = mk.kimlikleri_oku()["pemf_cv"]
    assert yan == {"username": "pemf_cv", "password": parola}, (
        f"kabin yan dosyası beklenen kimliği taşımıyor: {sorted(yan)}"
    )
    assert str(kabin / "cabin_mqtt_kimlik.yaml") in cikti, "CLI kabin dosyasının yolunu söylemiyor"
    for deger in mk.kimlikleri_oku().values():
        assert deger not in cikti, "CLI çıktısında PAROLA DEĞERİ var (sır sızıntısı)"


@pytest.mark.parametrize("profil", PROFILLER, ids=PROFIL_IDLERI)
def test_KRITIK_cabin_config_kimligi_YAN_DOSYADAN_okur_YAML_acigi_ustun(tmp_path, profil):
    from ai_hub.cv_ortak.cabin_config import load_cabin_config

    dizin, yaml_adi = profil
    ornek = (KOK / dizin / yaml_adi).read_text(encoding="utf-8")
    yml = tmp_path / "kabin.yaml"
    yml.write_text(ornek, encoding="utf-8")
    assert load_cabin_config(yml).output.mqtt_username is None, "aparat: yan dosya yokken kimlik çıktı"
    (tmp_path / "cabin_mqtt_kimlik.yaml").write_text("username: pemf_cv\npassword: gizli-deger-1\n", encoding="utf-8")
    out = load_cabin_config(yml).output
    assert (out.mqtt_username, out.mqtt_password) == ("pemf_cv", "gizli-deger-1"), (
        "yan dosyadaki kabin kimliği okunmadı"
    )
    yml.write_text(
        ornek.replace("username: null", 'username: "elle"').replace("password: null", 'password: "p2"'),
        encoding="utf-8",
    )
    out = load_cabin_config(yml).output
    assert (out.mqtt_username, out.mqtt_password) == ("elle", "p2"), "YAML'daki açık kimlik yan dosyaya EZİLDİ"


@pytest.mark.parametrize("profil", PROFILLER, ids=PROFIL_IDLERI)
def test_KRITIK_kabin_MQTT_varsayilan_KAPALI_YAMLda_SIR_YOK_yan_dosya_GITIGNORE(profil):
    import yaml

    dizin, yaml_adi = profil
    mq = yaml.safe_load((KOK / dizin / yaml_adi).read_text(encoding="utf-8"))["output"]["mqtt"]
    assert mq["enabled"] is False, f"{dizin}: kabin MQTT'si varsayılan AÇIK"
    assert mq.get("username") is None and mq.get("password") is None, f"{dizin}: profil YAML'ı kimlik taşıyor"
    r = subprocess.run(["git", "check-ignore", "-q", f"{dizin}/cabin_mqtt_kimlik.yaml"], cwd=str(KOK))
    if r.returncode == 128:
        pytest.skip("git deposu değil")
    assert r.returncode == 0, f"{dizin}/cabin_mqtt_kimlik.yaml gitignore'da DEĞİL (kabin parolası commit edilebilir)"


# ── GERÇEK broker ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def broker(mk, tmp_path):
    if ma.ikili() is None:
        capraz.atla("mosquitto ikilisi yok (Linux CI) — Windows CI aynı kapıyı paketteki 2.0.18 ile koşar")
    veri = tmp_path / "makine" / "mosquitto"
    mk.hazirla()  # varsayılan broker dizini = <makine>/mosquitto = kurulumun $MosqDataRoot'u
    port = ma.bos_port()
    b = ma.Broker(ma.kurulum_yapilandirmasi(port, veri), tmp_path / "b", port).basla()
    istemciler: list = []
    try:
        yield {"port": port, "k": mk.kimlikleri_oku(), "istemciler": istemciler}
    finally:
        ma.kapat(*istemciler)
        b.dur()


def _istemci(o, kullanici):
    c, rc = ma.istemci(o["port"], kullanici, o["k"][kullanici], ad=kullanici)
    assert c is not None, f"aparat: {kullanici} bağlanamadı (rc={rc})"
    o["istemciler"].append(c)
    return c


def test_KRITIK_GERCEK_broker_pemf_cv_STATEe_yazar_CONTROL_ve_ACKe_YAZAMAZ(broker):
    gozcu = _istemci(broker, "pemf_backend")
    alinan: list = []
    gozcu.on_message = lambda _c, _u, m: alinan.append((m.topic, m.payload.decode("utf-8", "replace")))
    gozcu.subscribe([("pemf/coil/state", 1), ("pemf/coil/8/control", 1), ("pemf/coil/8/ack", 1)])
    time.sleep(0.4)
    cv = _istemci(broker, "pemf_cv")
    cv.publish("pemf/coil/state", '{"kaynak":"cv"}', qos=1)
    cv.publish("pemf/coil/8/control", '{"command":"start","command_id":"cv_sahte"}', qos=1)
    cv.publish("pemf/coil/8/ack", '{"command_id":"cv_ack","success":true}', qos=1)
    time.sleep(0.8)
    yukler = [y for _t, y in alinan]
    assert any('"kaynak":"cv"' in y for y in yukler), f"pemf_cv kendi konusuna (state) yazamadı: {alinan}"
    assert not any("cv_sahte" in y for y in yukler), "pemf_cv bobin CONTROL konusuna YAZABİLDİ"
    assert not any("cv_ack" in y for y in yukler), "pemf_cv ACK konusuna YAZABİLDİ (E-stop onayı sahtelenir)"


def test_KRITIK_GERCEK_broker_soak_sondasi_kullanici_parola_ile_BAGLANIR(broker):
    sys.path.insert(0, str(KOK / "scripts"))
    try:
        import soak_publish_5hz_8coil as soak
    finally:
        sys.path.remove(str(KOK / "scripts"))
    tuketici = _istemci(broker, "pemf_backend")
    tuketici.subscribe("pemf/coil/+/sensors", qos=1)
    time.sleep(0.4)
    kimliksiz = soak.tuketim_sondasi("127.0.0.1", broker["port"], "pemf/coil/0/sensors")
    assert kimliksiz.startswith("OLCULEMEDI"), f"aparat: kimliksiz sonda kimlikli broker'da {kimliksiz!r}"
    kimlikli = soak.tuketim_sondasi(
        "127.0.0.1", broker["port"], "pemf/coil/0/sensors", kullanici="pemf_esp", parola=broker["k"]["pemf_esp"]
    )
    assert kimlikli == "VAR", (
        f"soak sondası --kullanici/--parola ile kimlikli broker'da tüketiciyi ölçemedi: {kimlikli!r}"
    )
