# Author: mertaygn, cglrgrkn
"""D6.06 (B-4.27) + D6.34 (B-9.6) — dağıtım belgeleri broker kimliğini A-04 kararıyla AYNI anlatır.

KUSUR (ölçüldü, HEAD `ebf1c3fe`): `deploy/README.md` §6 güvenlik kontrol listesi "Klinik MQTT: `allow_anonymous=false` +
`PEMF_MQTT_USER/PASS`" ve `deploy/device.env` "üretimde SET EDİN + allow_anonymous=false" diyordu. Gerçek (A-04 · D1.104): broker
TABANI anonimdir (üç üretici + ağ geçidi belgesi `allow_anonymous true`), kimlik ESP dönüşünde `PEMF_Backend.exe --mqtt-kimlik hazirla`
ile gelir (kimlik parçası / satır içi yönergeler anonimi ezer); tabana `allow_anonymous false` yazmak kimliksiz ESP firmware'ini
broker'dan koparır (bobin 8'in STOP yolu). `PEMF_MQTT_USER/PASS` broker'ı kimlikli YAPMAZ — yalnız hazırlanmamışken backend'in
gönderdiği operatör kimliğidir (`api_server._mqtt_credentials`).

KAPI: (1) üç broker üreticisinin (+ ağ geçidi belgesi) yorum dışı TABAN değeri okunur; (2) `deploy/` altındaki HİÇBİR belge tabana
`allow_anonymous=false` talimatı vermez (yorum satırı da talimattır — `.env` belgeleri yorumla anlatır); (3) README §6 MQTT satırı
tabanın anonim olduğunu, hazırlama komutunu ve `PEMF_MQTT_USER/PASS`'ın broker'ı kimlikli yapmadığını söyler — üreticilerden biri
tabanı değiştirirse (1) KIRMIZI olur ve belge yeniden yazılmak zorundadır.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _yorumsuz(metin: str) -> list[str]:
    return [s.strip() for s in metin.splitlines() if s.strip() and not s.lstrip().startswith("#")]


def _ps_conf(betik: str) -> str:
    m = re.search(r'\$conf = @"\r?\n(.*?)\r?\n"@', (KOK / "scripts" / betik).read_text(encoding="utf-8-sig"), re.S)
    assert m, f"aparat: {betik} içinde $conf bloğu yok"
    return m.group(1)


def _taban_anonim_degerleri() -> dict[str, list[str]]:
    kaynaklar = {
        "scripts/setup_services.ps1": _ps_conf("setup_services.ps1"),
        "scripts/install_mosquitto_service.ps1": _ps_conf("install_mosquitto_service.ps1"),
        "bin/mosquitto/mosquitto.conf": (KOK / "bin" / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8"),
        "config/mosquitto/mosquitto.conf": (KOK / "config" / "mosquitto" / "mosquitto.conf").read_text(
            encoding="utf-8"
        ),
    }
    return {
        ad: [s.split(None, 1)[1].strip() for s in _yorumsuz(m) if s.split(None, 1)[0] == "allow_anonymous"]
        for ad, m in kaynaklar.items()
    }


def _readme_mqtt_satiri() -> str:
    readme = re.sub(r"<!--.*?-->", "", (KOK / "deploy" / "README.md").read_text(encoding="utf-8"), flags=re.S)
    bolum = readme.split("## 6) Güvenlik kontrol listesi", 1)
    assert len(bolum) == 2, "README §6 güvenlik kontrol listesi yok"
    madde = re.split(r"\n(?=- \[ \] )", bolum[1].split("\n## ", 1)[0])
    mqtt = [m for m in madde if m.startswith("- [ ] Klinik MQTT")]
    assert len(mqtt) == 1, f"§6'da tek 'Klinik MQTT' maddesi olmalı: {len(mqtt)}"
    return re.sub(r"\s+", " ", mqtt[0])


def test_KRITIK_broker_TABANI_anonim_dort_kaynakta_AYNI():
    degerler = _taban_anonim_degerleri()
    assert all(v == ["true"] for v in degerler.values()), (
        f"broker tabanının allow_anonymous değeri değişti: {degerler} — A-04 belgeleri (deploy/README §6, device.env) "
        "bu kapıyla birlikte YENİDEN yazılmalı"
    )


def test_KRITIK_deploy_belgeleri_tabana_allow_anonymous_false_TALIMATI_vermez():
    yasak = re.compile(r"allow_anonymous\s*=\s*false", re.I)
    bulunan = [
        f"{p.relative_to(KOK).as_posix()}:{i}: {s.strip()}"
        for p in sorted((KOK / "deploy").iterdir())  # D6.34: profil (.env) yorumları da talimattır
        if p.is_file() and p.suffix in (".md", ".env", ".txt")
        for i, s in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if yasak.search(s)
    ]
    assert not bulunan, (
        "deploy/ belgesi tabana `allow_anonymous=false` talimatı veriyor — kimliksiz ESP broker'a bağlanamaz (bobin 8 STOP yolu); "
        f"A-04: kimlik `--mqtt-kimlik hazirla` ile gelir: {bulunan}"
    )


def test_KRITIK_README_MQTT_maddesi_A04_GERCEGINI_soyler():
    satir = _readme_mqtt_satiri()
    for gerekli, neden in (
        ("anonim", "tabanın anonim olduğu söylenmiyor"),
        ("--mqtt-kimlik hazirla", "kimliği getiren tek adım (hazırlama komutu) yok"),
        ("PEMF_MQTT_USER/PASS", "operatör kimliğinin rolü anlatılmıyor"),
        ("YAPMAZ", "`PEMF_MQTT_USER/PASS`'ın broker'ı kimlikli YAPMADIĞI söylenmiyor"),
        ("allow_anonymous false", "tabana yazılmaması gereken yönerge adıyla anılmıyor"),
    ):
        assert gerekli in satir, f"README §6 MQTT maddesi: {neden}: {satir}"
    assert re.search(r"allow_anonymous false`?\s*\*{0,2}yazmayın", satir, re.I), (
        f"'allow_anonymous false' yasağı yok: {satir}"
    )


def test_KRITIK_device_env_MQTT_blogu_A04_GERCEGINI_soyler():
    """D6.34: profil `PEMF_MQTT_USER/PASS` satırlarının hemen üstündeki açıklama bloğu (yorum = talimat) A-04 gerçeğini söyler."""
    satirlar = (KOK / "deploy" / "device.env").read_text(encoding="utf-8").splitlines()
    i = next((n for n, s in enumerate(satirlar) if re.match(r"#?\s*PEMF_MQTT_USER=", s.strip())), None)
    assert i is not None, "aparat: device.env'de PEMF_MQTT_USER satırı yok"
    blok = []
    for s in reversed(satirlar[:i]):
        if not s.strip().startswith("#"):
            break
        blok.insert(0, s.strip().lstrip("#").strip())
    metin = " ".join(blok)
    for gerekli, neden in (
        ("ANONİM", "tabanın anonim olduğu söylenmiyor"),
        ("--mqtt-kimlik hazirla", "kimliği getiren adım yok"),
        ("YAPMAZ", "PEMF_MQTT_USER/PASS'ın broker'ı kimlikli YAPMADIĞI söylenmiyor"),
    ):
        assert gerekli in metin, f"device.env MQTT bloğu: {neden}: {metin!r}"
