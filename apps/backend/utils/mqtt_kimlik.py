# Author: mertaygn, cglrgrkn
"""A-04 · D1.104 — yerel MQTT broker KİMLİĞİ ("hazırlanınca kimlikli").

SORUN (D-2.1): yerel broker anonimdi (`allow_anonymous true`). LAN'daki herhangi bir istemci `pemf/coil/<n>/control`'a
abone olup E-stop'un `command_id`'sini görebiliyor ve `pemf/coil/<n>/ack`'e `{success:true}` yayınlayarak bekleyen
E-stop'u "ESP ONAYLADI" gösterebiliyordu — bobin durmamışken operatörün "elle kontrol edin" uyarısı bastırılır.

MODEL:
  · `hazirla` (ESP dönüşünde, ağ geçidi makinesinde): makine deposuna (`mqtt_kimlik.json`; DPAPI LOCAL_MACHINE /
    makine anahtarı; veri kökünden BAĞIMSIZ → veri kökü yenilense de ESP'ye yakılan parola geçerli kalır) backend ve ESP
    için iki rastgele parola yazar (YOKSA üretir, VARSA KORUR) ve broker dizinine `pemf_passwd` ($7$ PBKDF2-SHA512,
    mosquitto 2.x biçimi) + `pemf_acl` + `conf.d/pemf_kimlik.conf` (`allow_anonymous false`) üretir; `--firmware DİZİN`
    verilirse ESP için `MqttKimlikYerel.h` (gitignore) yazar. Taban broker yapılandırmaları (kurulum betiği, paketli
    yedek, Linux) `conf.d`'yi SONDA içerir → kimlik parçası anonimi ezer (mosquitto 2.0.18'de ölçüldü).
  · Hazırlanmamış sistem BUGÜNKÜ gibidir: broker anonim, backend kimlik göndermez → hiçbir STOP yolu değişmez.
  · Yetki (ACL): backend YALNIZ `pemf/coil/+/control` + eski `pemf/esp32_<n>/command` YAZAR, `pemf/#` OKUR — ack
    YAZAMAZ; ESP yalnız `pemf/coil/+/{status,sensors,events,ack,alarm,system/#}` YAZAR ve control OKUR — control YAZAMAZ;
    anonim HİÇBİR ŞEY. ⇒ ack yalnız ESP kimliğinden gelebilir; backend ayrıca ack'i komutun BOBİN konusuna bağlar
    (`api_server._resolve_ack`). Tek ESP kimliği (bobin başına değil): S3'ün bobin kimliği BLE ile değişebilir; bobin
    başına kimlik yanlış eşleşirse ACL STOP aboneliğini sessizce reddederdi (sahip sorusu: bobin başına kimlik).
  · ⚠️ Sır değeri hiçbir çıktıya/loga yazılmaz: CLI yalnız yol ve durum basar; ESP başlığı yalnız istenen dizine yazılır.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_KULLANICI = "pemf_backend"
ESP_KULLANICI = "pemf_esp"
#: Y73 (sahip, S-G8): kabin kamerası (CV) MQTT yayıncısı — YALNIZ kendi konularına yazar (bobin control / ack YAZAMAZ).
CV_KULLANICI = "pemf_cv"
#: Kabin CV konuları (`output.mqtt` — kedi `ai_hub/inference_cat_organ/cabin_config_example.yaml`, AI-2'den beri petri
#: `petri_cv_v2/cabin_config_v2.yaml` ve fantom `phantom_cv_v3/cabin_config_v3.yaml`): durum YAYINI + (isteğe bağlı) komut ABONELİĞİ.
#: ⚠️ Kimlikli broker'da `pemf/coil/cmd`'ye YAZMA yetkisi olan rol YOK (geri besleme kanalı kullanılmıyor); durumu backend
#: (`pemf/#` okur) görür, ESP göremez (kabin MQTT'si varsayılan KAPALI).
CV_YAZMA_KONULARI = ("pemf/coil/state",)
CV_OKUMA_KONULARI = ("pemf/coil/cmd",)
#: Y73: kabin kimliği kabin YAML'ının İÇİNE değil YANINDAKİ ayrı dosyaya (ESP başlığı gibi; gitignore) yazılır.
KABIN_KIMLIK_ADI = "cabin_mqtt_kimlik.yaml"
DEPO_ADI = "mqtt_kimlik.json"
PASSWD_ADI = "pemf_passwd"
ACL_ADI = "pemf_acl"
CONF_DIZINI = "conf.d"
CONF_ADI = "pemf_kimlik.conf"
YEREL_BASLIK_ADI = "MqttKimlikYerel.h"
PBKDF2_TUR = 101  # mosquitto_passwd 2.x varsayılanı ($7$)
# Eski konu `pemf/esp32_<n>/command` bir seviyenin PARÇASI olduğundan `+` joker kabul etmez → açık liste.
ESP_BOBINLERI = range(1, 9)
# `alarm`: bugünkü firmware yayınlamıyor ama backend dinliyor ve ESP güvenlik alarmı ACİL DURDUR tetikler — yetkiden
# düşerse o STOP tetikleyicisi kimlikli broker'da SESSİZCE kaybolurdu.
ESP_YAZMA_KONULARI = ("status", "sensors", "events", "ack", "alarm")


def depo_dizini() -> Path:
    """Makine-düzeyi kimlik deposu dizini — bulut cihaz sırrıyla AYNI yer (`PEMF_DEVICE_IDENTITY_DIR` ile yönlenir)."""
    from utils.secrets_manager import _cihaz_kimlik_deposu

    return _cihaz_kimlik_deposu()


def varsayilan_broker_dizini() -> Path:
    """Windows: `%ProgramData%\\PEMF_System\\mosquitto` (= kurulum betiğinin `$MosqDataRoot`); Linux: `<depo>/mosquitto`."""
    return depo_dizini() / "mosquitto"


def _depo_yolu() -> Path:
    return depo_dizini() / DEPO_ADI


# Süreç içi önbellek (yol, mtime_ns) → kimlikler: STOP yayını başına dosya okuma + DPAPI çözme maliyeti eklenmesin
# (Ö.4-Y8: durdurma geciktirilmez). Depo değişirse (yeniden hazırlama) mtime değişir → yeniden okunur.
_onbellek: dict = {}


def kimlikleri_oku() -> dict[str, str] | None:
    """Hazırlanmışsa {kullanıcı: parola}; değilse None. Okunamayan depo → None + UYARI (sessiz düşme yok)."""
    p = _depo_yolu()
    try:
        st = p.stat()
    except OSError:
        return None
    anahtar = (str(p), st.st_mtime_ns, st.st_size)
    if _onbellek.get("anahtar") == anahtar:
        return dict(_onbellek["kimlikler"])
    try:
        from utils.secrets_manager import _dec

        ham = json.loads(p.read_text(encoding="utf-8"))
        kimlikler = {k: _dec(str(ham[k])) for k in (BACKEND_KULLANICI, ESP_KULLANICI)}
        if CV_KULLANICI in ham:  # Y73 öncesi depolarda yok (hazırlama ekler; parolalar değişmez)
            kimlikler[CV_KULLANICI] = _dec(str(ham[CV_KULLANICI]))
        if not all(kimlikler.values()):
            raise ValueError("boş parola")
    except Exception as e:
        logger.warning("MQTT kimlik deposu okunamadı (%s): %s", p, type(e).__name__)
        return None
    _onbellek.update(anahtar=anahtar, kimlikler=dict(kimlikler))
    return kimlikler


def backend_kimligi() -> tuple[str | None, str | None]:
    k = kimlikleri_oku()
    return (BACKEND_KULLANICI, k[BACKEND_KULLANICI]) if k else (None, None)


def hazirlandi_mi(broker_dizini: Path | None = None) -> bool:
    """Depo okunabilir VE broker kimlik parçası yerinde. ⚠️ DOSYAYA bakar, çalışan broker'a DEĞİL (O-3.1) — broker'ın
    gerçekte anonim kabul edip etmediği `broker_anonim_kabul_ediyor_mu` ile ölçülür."""
    bd = Path(broker_dizini) if broker_dizini else varsayilan_broker_dizini()
    return kimlikleri_oku() is not None and (bd / CONF_DIZINI / CONF_ADI).is_file()


def broker_anonim_kabul_ediyor_mu(host: str, port: int, zaman_asimi: float = 2.0) -> bool | None:
    """O-3.1: ÇALIŞAN broker kimliksiz (anonim) bağlantıyı KABUL EDİYOR mu? Broker'ın GERÇEK yapılandırmasını ölçer:
    kullanıcı adı OLMAYAN MQTT 3.1.1 CONNECT → CONNACK dönüş kodu. True = kabul (anonim) · False = reddedildi (4/5:
    kimlik zorunlu) · None = ölçülemedi (broker yok / yanıt yok / beklenmeyen yanıt). Kabulde DISCONNECT ile kapanır;
    hiçbir konuya abone olmaz, yayın yapmaz."""
    istemci = f"pemf_sonda_{os.getpid() % 100000}".encode("ascii")
    # Değişken başlık: protokol adı "MQTT", seviye 4, bayrak 0x02 (temiz oturum, kullanıcı adı/parola YOK), keepalive 10.
    govde = b"\x00\x04MQTT\x04\x02\x00\x0a" + len(istemci).to_bytes(2, "big") + istemci
    try:
        with socket.create_connection((host, int(port)), timeout=zaman_asimi) as s:
            s.settimeout(zaman_asimi)
            s.sendall(b"\x10" + bytes([len(govde)]) + govde)
            yanit = b""
            while len(yanit) < 4:
                parca = s.recv(4 - len(yanit))
                if not parca:
                    break
                yanit += parca
            if len(yanit) < 4 or yanit[0] != 0x20 or yanit[1] != 0x02:
                return None
            if yanit[3] == 0:
                try:
                    s.sendall(b"\xe0\x00")  # DISCONNECT
                except OSError:
                    pass
                return True
            return False if yanit[3] in (4, 5) else None
    except OSError:
        return None


def ozet7(parola: str, tuz: bytes | None = None, tur: int = PBKDF2_TUR) -> str:
    """mosquitto 2.x `$7$` biçimi: `$7$<tur>$<b64 tuz>$<b64 PBKDF2-HMAC-SHA512(parola, tuz, tur, 64)>`."""
    tuz = os.urandom(12) if tuz is None else tuz
    ozet = hashlib.pbkdf2_hmac("sha512", parola.encode("utf-8"), tuz, tur, 64)
    return f"$7${tur}${base64.b64encode(tuz).decode('ascii')}${base64.b64encode(ozet).decode('ascii')}"


def ozet7_dogrula(parola: str, kayit: str) -> bool:
    try:
        _, tur, tur_sayi, tuz_b64, ozet_b64 = kayit.split("$")
        if tur != "7":
            return False
        tuz = base64.b64decode(tuz_b64)
        beklenen = base64.b64decode(ozet_b64)
        olan = hashlib.pbkdf2_hmac("sha512", parola.encode("utf-8"), tuz, int(tur_sayi), len(beklenen))
        return hmac.compare_digest(olan, beklenen)
    except Exception:
        return False


def acl_metni() -> str:
    satir = [
        "# PEMF yerel broker yetkileri (A-04 / D1.104) - utils.mqtt_kimlik uretir; elle duzenlemeyin.",
        "# Anonim istemcinin yetkisi YOK (allow_anonymous false). Backend ack YAZAMAZ; ESP control YAZAMAZ.",
        "",
        f"user {BACKEND_KULLANICI}",
        "topic read pemf/#",
        "topic write pemf/coil/+/control",
    ]
    satir += [f"topic write pemf/esp32_{n}/command" for n in ESP_BOBINLERI]
    satir += ["", f"user {ESP_KULLANICI}", "topic read pemf/coil/+/control"]
    satir += [f"topic write pemf/coil/+/{k}" for k in ESP_YAZMA_KONULARI]
    satir += ["topic write pemf/coil/+/system/#"]
    # Y73: kabin CV — YALNIZ kendi konuları (bobin control / ack / telemetri YAZAMAZ).
    satir += ["", f"user {CV_KULLANICI}"]
    satir += [f"topic write {k}" for k in CV_YAZMA_KONULARI]
    satir += [f"topic read {k}" for k in CV_OKUMA_KONULARI]
    satir += [""]
    return "\n".join(satir)


def passwd_metni(kimlikler: dict[str, str]) -> str:
    return "".join(f"{k}:{ozet7(p)}\n" for k, p in sorted(kimlikler.items()))


def conf_metni(broker_dizini: Path) -> str:
    bd = Path(broker_dizini).as_posix()
    return (
        "# PEMF yerel broker KIMLIGI (A-04 / D1.104) - utils.mqtt_kimlik uretir. Taban yapilandirma bu dizini SONDA\n"
        "# icerir; buradaki allow_anonymous false tabandaki true'yu EZER.\n"
        "allow_anonymous false\n"
        f"password_file {bd}/{PASSWD_ADI}\n"
        f"acl_file {bd}/{ACL_ADI}\n"
    )


def firmware_basligi(kullanici: str, parola: str) -> str:
    # token_urlsafe parolası yalnız [A-Za-z0-9_-] içerir → C dizesinde kaçış gerekmez (yine de doğrulanır).
    for deger in (kullanici, parola):
        if not deger or any(c in deger for c in '"\\\n\r'):
            raise ValueError("kimlik C dizesine guvenle yazilamaz")
    return (
        "/* PEMF yerel MQTT broker kimligi (A-04 / D1.104) - `utils.mqtt_kimlik hazirla` URETTI.\n"
        " * ⚠️ SIR ICERIR: git'e GIRMEZ (.gitignore), derlemeden sonra build makinesinden silin. */\n"
        "#pragma once\n"
        f'#define PEMF_YEREL_MQTT_KULLANICI "{kullanici}"\n'
        f'#define PEMF_YEREL_MQTT_PAROLA "{parola}"\n'
    )


def kabin_kimlik_metni(kullanici: str, parola: str) -> str:
    """Y73: kabin YAML'ının YANINA yazılan kimlik dosyası (`cabin_config` okur; YAML'daki açık kimlik üstündür)."""
    for deger in (kullanici, parola):
        if not deger or any(c in deger for c in "\"\\\n\r:#'"):
            raise ValueError("kabin kimligi YAML'a guvenle yazilamaz")
    return (
        "# PEMF kabin CV MQTT kimligi (A-04 / Y73) - `utils.mqtt_kimlik hazirla --kabin` URETTI.\n"
        "# ⚠️ SIR ICERIR: git'e GIRMEZ (.gitignore). Kabin MQTT'si YAML'da (output.mqtt.enabled) varsayilan KAPALI.\n"
        f'username: "{kullanici}"\n'
        f'password: "{parola}"\n'
    )


def _yaz(yol: Path, metin: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".tmp")
    with open(gecici, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    os.replace(gecici, yol)


def _broker_dosyalarini_yaz(bd: Path, kimlikler: dict[str, str]) -> None:
    """Depodaki kimliklerden broker dosyaları (passwd + ACL + conf.d parçası) — depoya DOKUNMAZ."""
    _yaz(bd / PASSWD_ADI, passwd_metni(kimlikler))
    _yaz(bd / ACL_ADI, acl_metni())
    _yaz(bd / CONF_DIZINI / CONF_ADI, conf_metni(bd))


def hazirla(broker_dizini: Path | None = None, firmware_dizinleri=(), yenile: bool = False, kabin_dizinleri=()) -> dict:
    """Kimlik deposu (yoksa üret; VARSA KORU — yakılmış ESP parolası geçerli kalır) + broker dosyaları + istenen ESP
    başlıkları + istenen kabin kimlik dosyaları (Y73). Y73 öncesi depoya (backend + ESP) `pemf_cv` EKLENİR — mevcut
    parolalar DEĞİŞMEZ. Dönüş: yol/durum raporu — SIR İÇERMEZ."""
    bd = Path(broker_dizini) if broker_dizini else varsayilan_broker_dizini()
    kimlikler = None if yenile else kimlikleri_oku()
    depo_olustu = False
    from utils.secrets_manager import _enc

    if kimlikler is None:
        if _depo_yolu().exists() and not yenile:
            raise RuntimeError(
                "kimlik deposu VAR ama okunamiyor - yakilmis ESP parolalari bozulmasin diye DURDU "
                "(bilerek yenilemek: --yenile; ESP'ler yeniden yakilmali)"
            )
        kimlikler = {k: secrets.token_urlsafe(24) for k in (BACKEND_KULLANICI, ESP_KULLANICI, CV_KULLANICI)}
        kayit = {k: _enc(v, critical=True) for k, v in kimlikler.items()}
        kayit["surum"] = 1
        _yaz(_depo_yolu(), json.dumps(kayit, ensure_ascii=False, indent=2) + "\n")
        _onbellek.clear()
        depo_olustu = True
    elif CV_KULLANICI not in kimlikler:
        # Y73 yükseltmesi: yalnız yeni anahtar eklenir; mevcut şifreli değerler AYNEN kalır (yeniden şifrelenmez).
        kayit = json.loads(_depo_yolu().read_text(encoding="utf-8"))
        kimlikler[CV_KULLANICI] = secrets.token_urlsafe(24)
        kayit[CV_KULLANICI] = _enc(kimlikler[CV_KULLANICI], critical=True)
        _yaz(_depo_yolu(), json.dumps(kayit, ensure_ascii=False, indent=2) + "\n")
        _onbellek.clear()
    _broker_dosyalarini_yaz(bd, kimlikler)
    basliklar = []
    for fd in firmware_dizinleri:
        hedef = Path(fd) / YEREL_BASLIK_ADI
        _yaz(hedef, firmware_basligi(ESP_KULLANICI, kimlikler[ESP_KULLANICI]))
        basliklar.append(str(hedef))
    kabinler = []
    for kd in kabin_dizinleri:
        hedef = Path(kd) / KABIN_KIMLIK_ADI
        _yaz(hedef, kabin_kimlik_metni(CV_KULLANICI, kimlikler[CV_KULLANICI]))
        kabinler.append(str(hedef))
    return {
        "depo": str(_depo_yolu()),
        "depo_olustu": depo_olustu,
        "broker_dizini": str(bd),
        "basliklar": basliklar,
        "kabinler": kabinler,
    }


def parcayi_onar(broker_dizini: Path | None = None) -> str:
    """Y71 (sahip, S-G6): kaldır-kur sonrası kimlik deposu VAR ama broker dosyaları (`conf.d` parçası, `pemf_passwd`,
    `pemf_acl`) EKSİKSE hepsini depodaki AYNI parolalarla yeniden yazar (yenileme YOK — A-18: rotasyon yok; ESP'ye
    yakılmış kimlik geçerli kalır). Depoya DOKUNMAZ (Y73 öncesi depoya `pemf_cv` eklemek de açık hazırlamanın işi).
    Broker'ı BAŞLATMAZ/yeniden başlatmaz — o `MosquittoSupervisor`'ın işi.

    Dönüş: "hazir" (dosyalar yerinde) · "onarildi" · "hazirlanmamis" (depo yok — bugünkü anonim kip, DOKUNULMAZ) ·
    "okunamadi" (depo var ama okunamıyor — EZİLMEZ) · "yazilamadi" (izin vb.; anonim kalır, günlüğe yazılır)."""
    bd = Path(broker_dizini) if broker_dizini else varsayilan_broker_dizini()
    if all((bd / ad).is_file() for ad in (PASSWD_ADI, ACL_ADI, f"{CONF_DIZINI}/{CONF_ADI}")):
        return "hazir"
    if not _depo_yolu().is_file():
        return "hazirlanmamis"
    kimlikler = kimlikleri_oku()
    if kimlikler is None:
        logger.warning(
            "Y71: MQTT kimlik deposu VAR ama okunamiyor - broker kimlik parcasi YAZILMADI (depo ezilmez): %s", bd
        )
        return "okunamadi"
    try:
        _broker_dosyalarini_yaz(bd, kimlikler)
    except Exception as e:
        logger.warning(
            "Y71: broker kimlik parcasi yeniden yazilamadi (%s) - broker ANONIM kalir: %s", type(e).__name__, bd
        )
        return "yazilamadi"
    logger.warning("Y71: kaldir-kur sonrasi broker kimlik parcasi YOKTU - ayni parolalarla yeniden yazildi: %s", bd)
    return "onarildi"


def durum(broker_dizini: Path | None = None) -> dict:
    bd = Path(broker_dizini) if broker_dizini else varsayilan_broker_dizini()
    return {
        "depo": str(_depo_yolu()),
        "depo_var": _depo_yolu().is_file(),
        "depo_okunur": kimlikleri_oku() is not None,
        "broker_dizini": str(bd),
        "kimlik_parcasi": (bd / CONF_DIZINI / CONF_ADI).is_file(),
        "passwd": (bd / PASSWD_ADI).is_file(),
        "acl": (bd / ACL_ADI).is_file(),
        "kabin_kimligi": CV_KULLANICI in (kimlikleri_oku() or {}),
    }


def main(argv: list[str] | None = None) -> int:
    """`PEMF_Backend.exe --mqtt-kimlik hazirla|durum ...` (ya da `python -m utils.mqtt_kimlik ...`). Çıktı ASCII; SIR YOK."""
    ap = argparse.ArgumentParser(prog="PEMF_Backend.exe --mqtt-kimlik", description="Yerel MQTT broker kimligi (A-04)")
    alt = ap.add_subparsers(dest="komut", required=True)
    h = alt.add_parser("hazirla", help="kimlik deposu + broker dosyalari (+ ESP basligi)")
    h.add_argument("--broker-dizini", default=None, help="varsayilan: <makine deposu>/mosquitto")
    h.add_argument(
        "--firmware", action="append", default=[], help="MqttKimlikYerel.h yazilacak dizin (tekrarlanabilir)"
    )
    h.add_argument(
        "--kabin",
        action="append",
        default=[],
        help=f"kabin CV kimligi ({KABIN_KIMLIK_ADI}) yazilacak dizin = kabin YAML'inin dizini (tekrarlanabilir; Y73)",
    )
    h.add_argument(
        "--yenile",
        action="store_true",
        help="YALNIZ bozuk depo kurtarmasi: parolalari YENIDEN uret (ESP'ler yeniden yakilmali; broker yeniden "
        "baslayana dek backend baglanamaz)",
    )
    d = alt.add_parser("durum", help="hazirlik durumu (sir basmaz)")
    d.add_argument("--broker-dizini", default=None)
    a = ap.parse_args(argv)
    if a.komut == "durum":
        for k, v in durum(a.broker_dizini).items():
            print(f"{k}: {v}")
        return 0
    try:
        r = hazirla(a.broker_dizini, a.firmware, a.yenile, kabin_dizinleri=a.kabin)
    except RuntimeError as e:
        print(f"HATA: {e}")
        return 2
    except PermissionError as e:
        print(f"HATA: yazma izni yok ({e.filename}) - komutu YONETICI olarak calistirin.")
        return 3
    if a.yenile:
        # ⚠️ Kimlikli broker ESKİ parolaları bellekte tutar: backend yeni parolaya hemen geçer → broker yeniden başlayana dek
        # backend'in STOP yayınları REDDEDİLİR. Yenileme yalnız bozuk depo kurtarmasıdır (A-18: rotasyon YOK).
        print("UYARI (--yenile): broker yeniden baslatilana kadar backend BAGLANAMAZ (ESP STOP yolu kapali) -")
        print("  bobinler DURMUSKEN uygulayin, HEMEN ardindan ESP'leri yeni baslikla yakip broker'i yeniden baslatin.")
    print(f"kimlik deposu: {r['depo']} ({'OLUSTURULDU' if r['depo_olustu'] else 'korundu - parolalar AYNI'})")
    print(f"broker dosyalari: {r['broker_dizini']} ({PASSWD_ADI}, {ACL_ADI}, {CONF_DIZINI}/{CONF_ADI})")
    for b in r["basliklar"]:
        print(f"ESP basligi (SIR ICERIR - derleyip silin): {b}")
    for k in r["kabinler"]:
        print(f"Kabin CV kimligi (SIR ICERIR - git'e girmez; kabin MQTT'si YAML'da varsayilan KAPALI): {k}")
    print("SONRAKI ADIM (sira onemli): 1) ESP'leri bu baslikla derleyip yakin (bobinler durmusken);")
    # ⚠️ 1-G inceleme G-3.1: sahada (Y36) broker backend'in KENDİ sürecidir (launcher → PEMF_Backend.exe →
    # mosquitto.exe); oradaki Windows `mosquitto` servisi ESKİ kurulumun takılı servisidir, backend'in broker'ı DEĞİL.
    # `Restart-Service mosquitto` sahada kimliği devreye SOKMAZ ve o eski servisi tetikler.
    print("  2) SONRA broker'i yeniden baslatin - kimlik ancak o zaman devreye girer:")
    print("     * launcher kurulumu (saha): broker backend'in KENDI surecidir -> PEMF uygulamasini kapatip yeniden")
    print(
        "       acin (bobinler durmusken). 'Restart-Service mosquitto' KULLANMAYIN: o servis backend'in broker'i DEGIL."
    )
    print("     * servis kurulumu (setup_services / NSSM): Restart-Service mosquitto.")
    print("  3) dogrulayin: kimliksiz (anonim) istemci broker'a BAGLANAMAMALI.")
    print(
        "Not: basliksiz (eski) ESP firmware'i kimlikli broker'a BAGLANAMAZ; makine yeniden baslarsa broker kimlikli acilir."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
