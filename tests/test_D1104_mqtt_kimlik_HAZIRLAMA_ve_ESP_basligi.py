# Author: mertaygn, cglrgrkn
"""A-04 · D1.104 — yerel broker kimliğinin HAZIRLANMASI (`utils.mqtt_kimlik`), sır sızıntısı, ESP başlığı, yapısal pinler.

Gerçek-broker davranışı `test_D1104_broker_KIMLIKLI_sahte_ack_TEYIT_SAYILMAZ.py`'de. Bu dosya:
  · `$7$` özeti mosquitto biçiminde ve doğrulanır; hazırlama İDEMPOTENT (yakılmış ESP parolası değişmez); okunamayan depo
    EZİLMEZ; depoda ve CLI çıktısında parola DEĞERİ YOK (değer düzeyinde ölçülür — json metninde değil).
  · Yetki metni: backend ack YAZAMAZ, ESP control YAZAMAZ; ESP'nin yayınladığı / backend'in yayınladığı HER konu yetkide
    (firmware ve backend kaynağından çıkarılır — yeni bir konu yetkisiz kalırsa kimlikli broker onu SESSİZCE düşürür).
  · `_mqtt_credentials` önceliği; ESP açık + hazırlanmamış → uyarı; paketli/Linux yedek yapılandırmasına `include_dir`.
  · Kurulum betiği: `include_dir` SONDA, `conf.d` + yer tutucu parça (boş include_dir'de mosquitto Windows'ta AÇILMAZ).
  · ESP: `MqttKimlik.h` iki sketch'te aynı, `MqttKimlikYerel.h` gitignore'da; başlık ana makinede derlenir (yoksa boş
    kimlik, varsa depodaki ESP kimliği); iki firmware'in yerel bağlantısı kimliği kullanır.
"""

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
FW = KOK / "firmware"


@pytest.fixture
def mk(monkeypatch, tmp_path):
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    mqtt_kimlik._onbellek.clear()
    yield mqtt_kimlik
    mqtt_kimlik._onbellek.clear()


def _c_soy(metin: str) -> str:
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.S)
    return re.sub(r"//[^\n]*", " ", metin)


# ── özet, hazırlama, sır ─────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_ozet7_mosquitto_bicimi_ve_dogrulanir(mk):
    o = mk.ozet7("parola-ornek", tuz=b"\x01" * 12)
    _, tur, sayi, tuz, ozet = o.split("$")
    assert (tur, sayi) == ("7", "101") and base64.b64decode(tuz) == b"\x01" * 12
    assert base64.b64decode(ozet) == hashlib.pbkdf2_hmac("sha512", b"parola-ornek", b"\x01" * 12, 101, 64)
    assert mk.ozet7_dogrula("parola-ornek", o) and not mk.ozet7_dogrula("yanlis", o)


def test_KRITIK_hazirla_IDEMPOTENT_yakilmis_parola_DEGISMEZ(mk, tmp_path):
    r1 = mk.hazirla(tmp_path / "broker")
    k1 = mk.kimlikleri_oku()
    depo1 = Path(r1["depo"]).read_bytes()
    r2 = mk.hazirla(tmp_path / "broker")
    assert r1["depo_olustu"] and not r2["depo_olustu"]
    assert Path(r2["depo"]).read_bytes() == depo1 and mk.kimlikleri_oku() == k1, (
        "ikinci hazırlama parolaları DEĞİŞTİRDİ"
    )
    satirlar = dict(s.split(":", 1) for s in (tmp_path / "broker" / mk.PASSWD_ADI).read_text().split())
    # Y73 (1-H, sahip): kabin CV kimliği (pemf_cv) de üretilir — tests/test_kabin_CV_mqtt_kimligi_pemf_cv_Y73.py.
    assert set(satirlar) == {mk.BACKEND_KULLANICI, mk.ESP_KULLANICI, mk.CV_KULLANICI}
    assert all(mk.ozet7_dogrula(k1[k], satirlar[k]) for k in satirlar), "passwd depodaki parolalarla doğrulanmıyor"
    mk.hazirla(tmp_path / "broker", yenile=True)
    assert mk.kimlikleri_oku() != k1, "--yenile parolaları yenilemedi"


def test_KRITIK_okunamayan_depo_EZILMEZ(mk, tmp_path):
    depo = mk.depo_dizini() / mk.DEPO_ADI
    depo.parent.mkdir(parents=True, exist_ok=True)
    depo.write_text('{"pemf_backend": "DPAPI:bozuk", "pemf_esp"', encoding="utf-8")  # yarım yazılmış / bozuk depo
    eski = depo.read_bytes()
    with pytest.raises(RuntimeError):
        mk.hazirla(tmp_path / "broker")
    assert depo.read_bytes() == eski, "okunamayan kimlik deposu EZİLDİ (yakılmış ESP'ler kopardı)"


def test_KRITIK_yenile_STOP_yolu_UYARISI_ve_izin_hatasi_DOSTCA(mk, tmp_path, capsys, monkeypatch):
    """`--yenile`: kimlikli broker eski parolaları bellekte tutar → backend yeni parolaya geçince broker yeniden başlayana
    dek STOP yayınları reddedilir. CLI bunu AÇIKÇA söylemeli (sır basmadan); yazma izni yoksa iz yığını değil eylem."""
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker")]) == 0
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker"), "--yenile"]) == 0
    cikti = capsys.readouterr().out
    assert "UYARI (--yenile)" in cikti and "BAGLANAMAZ" in cikti, f"--yenile STOP yolu uyarısı yok:\n{cikti}"
    assert all(p not in cikti for p in mk.kimlikleri_oku().values()), "--yenile çıktısında parola"

    def _izinsiz(*a, **k):
        raise PermissionError(13, "Erişim engellendi", str(tmp_path / "broker" / mk.PASSWD_ADI))

    monkeypatch.setattr(mk, "hazirla", _izinsiz)
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker")]) == 3
    assert "YONETICI" in capsys.readouterr().out


def test_KRITIK_G31_sonraki_adim_SAHA_modelinde_uygulama_yeniden_baslatilir_Restart_Service_DEGIL(mk, tmp_path, capsys):
    """1-G inceleme G-3.1: sahada (Y36) broker backend'in KENDİ sürecidir (launcher → PEMF_Backend.exe → mosquitto.exe);
    makinedeki Windows `mosquitto` servisi eski kurulumun takılı servisidir. "Restart-Service mosquitto" tek talimat olarak
    sahada kimliği devreye SOKMAZ (backend'in broker'ı yeniden başlamaz) ve eski servisi tetikler. CLI her iki kurulum
    modelini ayrı söylemeli ve doğrulama adımını vermeli."""
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker")]) == 0
    cikti = capsys.readouterr().out
    satirlar = cikti.splitlines()
    saha = [s for s in satirlar if "launcher kurulumu" in s]
    assert saha, f"CLI saha (launcher) kurulumu için yeniden başlatma adımını söylemiyor:\n{cikti}"
    assert "PEMF uygulamasini kapatip yeniden" in cikti and "KULLANMAYIN" in cikti, (
        f"saha adımı uygulamanın yeniden açılmasını ve servisin KULLANILMAMASINI söylemiyor:\n{cikti}"
    )
    servis = [s for s in satirlar if "Restart-Service mosquitto" in s and "servis kurulumu" in s]
    assert servis, f"servis kurulumu (setup_services/NSSM) adımı yok:\n{cikti}"
    assert "BAGLANAMAMALI" in cikti, f"anonim istemcinin bağlanamadığını doğrulama adımı yok:\n{cikti}"


def test_KRITIK_depoda_ve_CLI_ciktisinda_parola_DEGERI_YOK(mk, tmp_path, capsys):
    fw = tmp_path / "fw"
    fw.mkdir()
    assert mk.main(["hazirla", "--broker-dizini", str(tmp_path / "broker"), "--firmware", str(fw)]) == 0
    assert mk.main(["durum", "--broker-dizini", str(tmp_path / "broker")]) == 0
    cikti = capsys.readouterr()
    k = mk.kimlikleri_oku()
    depo = (mk.depo_dizini() / mk.DEPO_ADI).read_bytes()
    for ad, parola in k.items():
        assert parola not in cikti.out and parola not in cikti.err, f"{ad} parolası CLI çıktısına yazıldı"
        assert parola.encode() not in depo, f"{ad} parolası depoda DÜZ METİN"
        for f in (tmp_path / "broker").rglob("*"):
            if f.is_file():
                assert parola.encode() not in f.read_bytes(), f"{ad} parolası broker dosyasında düz metin: {f.name}"
    baslik = (fw / mk.YEREL_BASLIK_ADI).read_text(encoding="utf-8")
    assert f'"{k[mk.ESP_KULLANICI]}"' in baslik and k[mk.BACKEND_KULLANICI] not in baslik, (
        "ESP başlığı ESP kimliğini taşımalı, backend parolasını TAŞIMAMALI"
    )


# ── yetki ve konu kapsaması ──────────────────────────────────────────────────────────────────────────────────────────
def _yetki(mk) -> dict:
    kural: dict = {}
    kullanici = None
    for s in mk.acl_metni().splitlines():
        p = s.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "user":
            kullanici = p[1]
            kural[kullanici] = {"read": [], "write": []}
        elif p[0] == "topic":
            assert kullanici, "yetki satırı kullanıcısız (anonime uygulanırdı)"
            kural[kullanici]["readwrite" if p[1] == "readwrite" else p[1]].append(p[2])
    return kural


def _eslesir(desen: str, konu: str) -> bool:
    d, k = desen.split("/"), konu.split("/")
    for i, parca in enumerate(d):
        if parca == "#":
            return True
        if i >= len(k) or (parca != "+" and parca != k[i]):
            return False
    return len(d) == len(k)


def test_KRITIK_yetki_backend_ack_YAZAMAZ_ESP_control_YAZAMAZ_anonim_YOK(mk, tmp_path):
    y = _yetki(mk)
    # Y73 (1-H, sahip): kabin CV kimliği (pemf_cv) — yalnız kendi konusuna yazar; control / ack YAZAMAZ.
    assert set(y) == {mk.BACKEND_KULLANICI, mk.ESP_KULLANICI, mk.CV_KULLANICI}
    assert not any(_eslesir(d, "pemf/coil/8/ack") for d in y[mk.BACKEND_KULLANICI]["write"]), "backend ack YAZABİLİR"
    assert not any(_eslesir(d, "pemf/coil/8/control") for d in y[mk.ESP_KULLANICI]["write"]), "ESP control YAZABİLİR"
    for konu in ("pemf/coil/8/control", "pemf/coil/8/ack", "pemf/coil/8/sensors"):
        assert not any(_eslesir(d, konu) for d in y[mk.CV_KULLANICI]["write"]), f"kabin CV {konu} YAZABİLİR"
    conf = mk.conf_metni(tmp_path)
    assert re.search(r"(?m)^allow_anonymous false$", conf) and "password_file" in conf and "acl_file" in conf


def _firmware_yayin_konulari() -> set:
    konular = set()
    for d in ("esp8266_pemf_coil", "esps3_pemf_coil"):
        for f in (FW / d).glob("*.*"):
            if f.suffix not in (".cpp", ".ino", ".h") or f.name in ("Secrets.h", "MqttKimlikYerel.h"):
                continue
            metin = _c_soy(f.read_text(encoding="utf-8", errors="replace"))
            konular |= {f"pemf/coil/8/{m}" for m in re.findall(r'"pemf/coil/%d/([a-z/]+)"', metin)}
            konular |= {
                f"pemf/coil/8/{m}"
                for m in re.findall(r'"pemf/coil/"\s*\+\s*String\(_coilId\)\s*\+\s*"/([a-z/]+)"', metin)
            }
    return konular


def test_KRITIK_ESPnin_HER_konusu_yetkide_yayin_YAZMA_abonelik_OKUMA(mk):
    y = _yetki(mk)[mk.ESP_KULLANICI]
    konular = _firmware_yayin_konulari()
    assert {"pemf/coil/8/control", "pemf/coil/8/ack", "pemf/coil/8/status"} <= konular, (
        f"aparat: konular okunamadı {konular}"
    )
    yetkisiz = [k for k in konular - {"pemf/coil/8/control"} if not any(_eslesir(d, k) for d in y["write"])]
    assert not yetkisiz, f"ESP'nin yayınladığı konu yetkide YOK (kimlikli broker sessizce düşürür): {yetkisiz}"
    assert any(_eslesir(d, "pemf/coil/8/control") for d in y["read"]), "ESP STOP konusunu OKUYAMAZ"
    for k in ("pemf/coil/8/alarm",):  # backend dinliyor; ESP güvenlik alarmı ACİL DURDUR tetikler
        assert any(_eslesir(d, k) for d in y["write"]), f"{k} yetkide yok — alarm→STOP tetikleyicisi kaybolur"


def test_KRITIK_backendin_HER_yayin_konusu_ve_aboneligi_yetkide(mk):
    y = _yetki(mk)[mk.BACKEND_KULLANICI]
    kaynak = ""
    for f in [*(KOK / "apps" / "backend").rglob("*.py")]:
        if "__pycache__" not in f.parts:
            kaynak += f.read_text(encoding="utf-8", errors="replace")
    yayin = set(re.findall(r'_mqtt_publish\(\s*f?"(pemf/[^"]+)"', kaynak))
    assert {"pemf/coil/{coil_id}/control", "pemf/esp32_{coil_id}/command"} <= yayin, f"aparat: {yayin}"
    for desen in yayin:
        for n in range(1, 9):
            konu = re.sub(r"\{[^}]+\}", str(n), desen)
            assert any(_eslesir(d, konu) for d in y["write"]), f"backend yayını yetkide YOK: {konu}"
    abone = set(re.findall(r'client\.subscribe\("(pemf/[^"]+)"\)', kaynak))
    assert "pemf/coil/+/ack" in abone, f"aparat: {abone}"
    for k in abone:
        assert any(_eslesir(d, k.replace("+", "8")) for d in y["read"]), f"backend aboneliği yetkide YOK: {k}"


# ── backend ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_mqtt_credentials_ONCELIGI_hazir_kimlik_operator_anonim(mk, tmp_path, monkeypatch):
    from servers import api_server as api

    monkeypatch.setenv("PEMF_MQTT_USER", "operator_k")
    monkeypatch.setenv("PEMF_MQTT_PASS", "operator_p")
    import utils.secrets_manager as sm

    monkeypatch.setattr(
        sm, "get_secret", lambda k, *a, **kw: {"mqtt_user": "operator_k", "mqtt_pass": "operator_p"}.get(k, "")
    )
    assert api._mqtt_credentials() == ("operator_k", "operator_p"), "hazırlanmamışken operatör kimliği kullanılmadı"
    mk.hazirla(tmp_path / "broker")
    u, p = api._mqtt_credentials()
    assert u == mk.BACKEND_KULLANICI and p == mk.kimlikleri_oku()[mk.BACKEND_KULLANICI], (
        "hazırlanmış kimlik varken backend broker'ın tanımadığı kimliği gönderiyor (STOP yayını reddedilir)"
    )
    monkeypatch.setattr(sm, "get_secret", lambda k, *a, **kw: "")
    (mk.depo_dizini() / mk.DEPO_ADI).unlink()
    mk._onbellek.clear()
    assert api._mqtt_credentials() == (None, None)


def test_KRITIK_ESP_acik_HAZIRLANMAMIS_broker_acilista_UYARILIR(mk, tmp_path, monkeypatch, caplog):
    """⚠️ O-3.1 (1-H): uyarı artık DOSYAYA değil ÇALIŞAN broker'a bağlı (kimliksiz CONNECT'in CONNACK'i). Bu kapı iki uç
    hâli korur: hazırlanmamış + broker ANONİM kabul ediyor → "KIMLIKSIZ" (+ ESP dönüş listesi); hazırlanmış + broker kimlik
    istiyor → sahte uyarı YOK. Ara hâller (hazırlanmış ama broker anonim, ölçülemeyen broker, hazırlanmamış ama broker
    kimlik istiyor): tests/test_broker_KIMLIKSIZ_uyarisi_CALISAN_brokerdan_O31.py."""
    import threading
    import time

    from servers import api_server as api
    from test_broker_KIMLIKSIZ_uyarisi_CALISAN_brokerdan_O31 import _SahteBroker

    class _Sahte:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, ad):
            return lambda *a, **k: None

    import paho.mqtt.client as pm

    monkeypatch.setattr(pm, "Client", _Sahte)
    monkeypatch.setattr(api, "_mqtt_client_api", getattr(api, "_mqtt_client_api", None))
    monkeypatch.setattr(api, "_SONDA_DENEME", 2)
    monkeypatch.setattr(api, "_SONDA_ARALIK_S", 0.05)
    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")

    def _kos(rc):
        broker = _SahteBroker(rc)
        monkeypatch.setattr(api, "_YEREL_BROKER", ("127.0.0.1", broker.port))
        try:
            with caplog.at_level("WARNING"):
                api._start_mqtt_for_api()
                son = time.monotonic() + 5.0
                while time.monotonic() < son and any(t.name == "BrokerKimlikSondasi" for t in threading.enumerate()):
                    time.sleep(0.05)
        finally:
            broker.kapat()

    _kos(0)
    assert any("KIMLIKSIZ" in r.getMessage() and "hazirla" in r.getMessage() for r in caplog.records), (
        "ESP açık + hazırlanmamış + anonim broker → uyarı (ESP dönüş listesiyle) yok"
    )
    caplog.clear()
    mk.hazirla()
    _kos(5)
    assert not any("KIMLIKSIZ" in r.getMessage() for r in caplog.records), (
        "hazırlanmış + kimlikli broker'da sahte uyarı"
    )


def test_KRITIK_paketli_yedek_yapilandirmaya_kimlik_SONDA_eklenir(mk, tmp_path):
    from services.headless_services import MosquittoSupervisor

    taban = tmp_path / "taban.conf"
    taban.write_text("listener 1883 0.0.0.0\nallow_anonymous true\n", encoding="utf-8")
    s = MosquittoSupervisor.__new__(MosquittoSupervisor)
    assert s._kimlik_dahil_conf(taban) == taban, "hazırlanmamışken taban değiştirildi"
    mk.hazirla()
    calisma = s._kimlik_dahil_conf(taban)
    metin = calisma.read_text(encoding="utf-8").strip().splitlines()
    parca = (mk.varsayilan_broker_dizini() / mk.CONF_DIZINI).as_posix()
    assert metin[-1] == f"include_dir {parca}", f"kimlik parçası SONDA değil: {metin[-3:]}"
    kendi = tmp_path / "kendi.conf"
    kendi.write_text("listener 1883\nallow_anonymous false\npassword_file /x/y\n", encoding="utf-8")
    assert s._kimlik_dahil_conf(kendi) == kendi, (
        "kendi password_file'ı olan tabana parça eklendi (yinelenen password_file)"
    )


def test_KRITIK_backend_exe_mqtt_kimlik_ALT_KOMUTU_sunucu_baslatmaz(monkeypatch):
    import backend_service as bs
    from utils import mqtt_kimlik

    cagri: list = []
    monkeypatch.setattr(mqtt_kimlik, "main", lambda av: cagri.append(av) or 0)
    monkeypatch.setattr(bs, "build_arg_parser", lambda: (_ for _ in ()).throw(AssertionError("sunucu yolu koştu")))
    assert bs.main(["--mqtt-kimlik", "durum"]) == 0 and cagri == [["durum"]]


# ── kurulum, iz, firmware ────────────────────────────────────────────────────────────────────────────────────────────
def test_KRITIK_kurulum_include_dir_SONDA_conf_d_ve_YER_TUTUCU_olusur():
    import mosquitto_aparat as ma

    ps = (KOK / "scripts" / "setup_services.ps1").read_text(encoding="utf-8")
    conf = ma.kurulum_yapilandirmasi(1883, Path("C:/V"), ps)
    yonerge = [s.split()[0] for s in conf.splitlines() if s.strip() and not s.lstrip().startswith("#")]
    assert yonerge[-1] == "include_dir" and conf.rstrip().endswith("include_dir C:/V/conf.d"), (
        "kurulum yapılandırmasında include_dir SONDA değil — kimlik parçası anonimi ezemez"
    )
    assert yonerge.index("allow_anonymous") < len(yonerge) - 1
    i_dizin = ps.index('New-Item -ItemType Directory -Force -Path "$MosqDataRoot\\conf.d"')
    i_yer = ps.index("00_pemf_taban.conf")
    i_yaz = ps.index('Set-Content -Path "$MosqDataRoot\\mosquitto.conf"')
    assert i_dizin < i_yer < i_yaz, (
        "conf.d + yer tutucu, yapılandırma yazılmadan ÖNCE oluşturulmalı (boş dizinde broker açılmaz)"
    )


def test_KRITIK_kimlik_deposu_SIRADAN_kaldirmada_KALIR_KVKK_silmesinde_GIDER():
    fp = (KOK / "scripts" / "pemf_footprint.ps1").read_text(encoding="utf-8")
    m = re.search(r"Path = 'C:\\ProgramData\\PEMF_System\\mqtt_kimlik\.json';\s*Owner = '\w+';\s*Kvkk = \$(\w+)", fp)
    assert m and m.group(1) == "true", "mqtt_kimlik.json izde yok ya da sıradan kaldırmada silinir (ESP'ler kopar)"


def test_KRITIK_ESP_basligi_iki_sketchte_AYNI_yerel_baslik_GITIGNORE():
    a, b = (FW / "esp8266_pemf_coil" / "MqttKimlik.h"), (FW / "esps3_pemf_coil" / "MqttKimlik.h")
    assert a.read_bytes() == b.read_bytes(), "MqttKimlik.h iki sketch'te farklı"
    for d in ("esp8266_pemf_coil", "esps3_pemf_coil"):
        r = subprocess.run(
            ["git", "check-ignore", "-q", f"firmware/{d}/MqttKimlikYerel.h"], cwd=str(KOK), capture_output=True
        )
        if r.returncode == 128:
            pytest.skip("git deposu değil")
        assert r.returncode == 0, f"firmware/{d}/MqttKimlikYerel.h gitignore'da DEĞİL (ESP parolası commit edilebilir)"


def test_KRITIK_iki_firmware_yerel_baglantisi_KIMLIGI_kullanir():
    e8 = _c_soy((FW / "esp8266_pemf_coil" / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace"))
    s3 = _c_soy((FW / "esps3_pemf_coil" / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace"))
    for ad, metin in (("8266", e8), ("S3", s3)):
        assert '#include "MqttKimlik.h"' in metin, f"{ad}: MqttKimlik.h içerilmiyor"
    i = e8.index("bool NetworkManager::_connectToLocalBroker()")
    govde = e8[i : e8.index("bool NetworkManager::_connectToCloudBroker()")]
    assert re.search(
        r"_mqttClient\.connect\(\s*clientId\s*,\s*PEMF_YEREL_MQTT_KULLANICI\s*,\s*PEMF_YEREL_MQTT_PAROLA", govde
    ), "8266 yerel bağlantısı kimliği göndermiyor"
    j = s3.index("bool PemfNetworkManager::_connectToLocalBroker()")
    g3 = s3[j : s3.index("bool PemfNetworkManager::_connectToCloudBroker()")]
    assert re.search(r"hazirKimlik\s*\?\s*PEMF_YEREL_MQTT_KULLANICI\s*:\s*DEFAULT_LOCAL_MQTT_USER", g3), (
        "S3 yerel bağlantısı hazırlanmış kimliği ÖNCELİKLİ kullanmıyor"
    )


def test_KRITIK_ESP_basligi_ana_makinede_DERLENIR_yoksa_bos_varsa_depodaki_ESP_kimligi(mk, tmp_path):
    from firmware_host_aparat import derleyici_gerekli

    tur, arac = derleyici_gerekli()
    dizin = tmp_path / "derle"
    dizin.mkdir()
    (dizin / "MqttKimlik.h").write_bytes((FW / "esp8266_pemf_coil" / "MqttKimlik.h").read_bytes())
    # FNV-1a 32: değerin kendisi BASILMAZ (yalnız uzunluk + özet) — ESP başlığı sır taşır.
    (dizin / "k.cpp").write_text(
        '#include <stdio.h>\n#include <string.h>\n#include "MqttKimlik.h"\n'
        "static unsigned f(const char*s){unsigned h=2166136261u;while(*s){h^=(unsigned char)*s++;h*=16777619u;}return h;}\n"
        'int main(){printf("%u %u %u %u\\n",(unsigned)strlen(PEMF_YEREL_MQTT_KULLANICI),f(PEMF_YEREL_MQTT_KULLANICI),'
        "(unsigned)strlen(PEMF_YEREL_MQTT_PAROLA),f(PEMF_YEREL_MQTT_PAROLA));return 0;}\n",
        encoding="ascii",
    )

    def _derle_kos() -> list[int]:
        exe = dizin / ("k.exe" if sys.platform == "win32" else "k")
        if tur == "msvc":
            bat = dizin / "d.bat"
            bat.write_text(
                f'@echo off\r\ncall "{arac}" >nul || exit /b 91\r\ncl /nologo /W3 k.cpp /Fe:k.exe\r\n', encoding="ascii"
            )
            r = subprocess.run(
                ["cmd", "/c", str(bat)], cwd=str(dizin), capture_output=True, text=True, errors="replace"
            )
        else:
            r = subprocess.run(["g++", "k.cpp", "-o", "k"], cwd=str(dizin), capture_output=True, text=True)
        assert r.returncode == 0, f"derlenmedi: {(r.stdout or '')[-800:]}"
        return [int(x) for x in subprocess.run([str(exe)], capture_output=True, text=True).stdout.split()]

    def _fnv(s: str) -> int:
        h = 2166136261
        for c in s.encode():
            h = ((h ^ c) * 16777619) & 0xFFFFFFFF
        return h

    assert _derle_kos() == [0, _fnv(""), 0, _fnv("")], "başlıksız derlemede kimlik boş değil"
    mk.hazirla(tmp_path / "broker", firmware_dizinleri=[dizin])
    k = mk.kimlikleri_oku()
    beklenen = [len(mk.ESP_KULLANICI), _fnv(mk.ESP_KULLANICI), len(k[mk.ESP_KULLANICI]), _fnv(k[mk.ESP_KULLANICI])]
    assert _derle_kos() == beklenen, "üretilen başlık derlemede depodaki ESP kimliğini vermiyor"
