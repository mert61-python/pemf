#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""Generate synthetic 8-coil sensor MQTT load at configurable Hz for soak tests.

⚠️ D0Ö.17 (B-10.218): ürünün MQTT aboneliklerinin TAMAMI `pemf/` ad alanında (api_server
`on_connect`: `pemf/coil/+/sensors|status|events|alarm|ack`, `pemf/gateway|bridge/status`).
Bu ad alanına yayın = CANLI ürüne sahte telemetri: ESP açık bir makinede (1.9.50 sahası) bobinlerin
canlı durumunu ezer ve ESP bayatlık bekçisini tazeler → gerçek sensör kopması MASKELENİR.
Bu yüzden `pemf/` önekli konuya yalnız `--canli-onay` ile yayın yapılır (varsayılan önek hâlâ
`pemf/coil`: bayraksız koşum BAĞLANMADAN reddedilir).

⚠️ TÜKETİM ÖLÇÜLÜR (D0Ö.17 ek): QoS 0 yükü broker'dan abone bilgisi almaz — "yayın kabul edildi"
tüketim DEĞİLDİR. Ayrı bir MQTT v5 istemcisi başta ve sonda TEK bir QoS 1 sonda yayınlar; broker
konuya abone yoksa PUBACK'te 16 (No matching subscribers) döner. Başta tüketici YOKSA ya da bu
ÖLÇÜLEMEZSE (broker v5 desteklemiyor, PUBACK gelmedi) yük HİÇ basılmaz. Yük QoS 0 kalır.
D0Ö.17 ek-2: 16 göndermek MAY olduğu için önce abonesi olmayan RASTGELE bir konu sondalanır
(kalibrasyon, `soak-kalibrasyon/<hex>/0/sensors`); orada 16 gelmezse sonuç ÖLÇÜLEMEZ ve ileti NEDENİ
söyler (D0Ö.17 ek-3): 0 = broker abonesizliği bildirmiyor ya da kalibrasyon konusuyla DA eşleşen KÖK düzeyinde
joker abone var (`#`, `+/#`, `+/+/+/sensors`) · bağlanamadı = broker kapalı / `--host`/`--port` · PUBACK yok =
broker MQTT v5 konuşmuyor YA DA bağlantıyı reddetti (kimlik: betik kimlik göndermez) · 135 = ACL reddi.
⚠️ Kalibrasyon YALNIZ kalibrasyon konusuyla da eşleşen jokerleri yakalar (D0Ö.17 ek-4): ad alanı jokeri (ör.
`mosquitto_sub -t "pemf/#"`, docs/PEMF_SISTEM_RAPORU.md) ya da sonraki seviyeleri sabit kök jokeri
(`+/coil/+/sensors`) kalibrasyon konusunu kapsamaz — `--canli-onay`da ürün ABONE DEĞİLKEN (backend kapalı ya da
ESP devre dışı: HEAD varsayılanı) böyle bir izleyici açıksa sonda sahte 'VAR' der (tüketen ürün değil izleyicidir).
Sonda `<önek>/0/sensors`e gider: ürün bobin 0'ı yok sayar, abonelik filtresi yine eşleşir —
tüketici bu yüzden `<önek>/+/sensors` (ya da `<önek>/#`) filtresiyle abone olmalıdır; kök `#` ile abone
olan izleyici kalibrasyon konusunu da tüketir → ÖLÇÜLEMEZ (3).

ÇIKIŞ KODU: 0 = her yük yayını istemci kuyruğuna KABUL edildi VE sondalar başta/sonda tüketici
VAR dedi · 1 = reddedilen yayın ya da hiç yayın yok · 2 = onaysız canlı önek · 3 = tüketici YOK /
ÖLÇÜLEMEDİ. Test için bir önek (ör. `soak/pemf/coil`) VE o konuya abone bir tüketici gerekir.
"""

import argparse
import json
import math
import sys
import threading
import time
import uuid

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit("Missing dependency: paho-mqtt. Install with: pip install paho-mqtt") from exc

#: Ürünün MQTT ad alanı — bu önekle başlayan her konu CANLI sayılır (bkz. modül başlığı).
URUN_AD_ALANI = "pemf"
#: MQTT 5.0 §3.4.2.1 PUBACK reason code: "No matching subscribers".
ABONE_YOK_KODU = 16
#: MQTT 5.0 PUBACK reason code: "Not authorized" (ACL reddi).
YETKISIZ_KODU = 135
SONDA_ZAMAN_ASIMI_S = 5.0


def canli_urun_konusu_mu(onek: str) -> bool:
    """`{onek}/<n>/sensors` konuları ürünün `pemf/` ad alanına mı düşer? (MQTT konusu harf duyarlı.)"""
    return onek.split("/", 1)[0] == URUN_AD_ALANI


def build_payload(coil_id: int, seq: int, now_ts: float) -> str:
    phase = (seq / 20.0) + coil_id
    payload = {
        "coil_id": str(coil_id),
        "timestamp": now_ts,
        "object_temp": round(36.5 + 1.2 * math.sin(phase), 2),
        "ambient_temp": round(24.0 + 0.8 * math.sin(phase / 2.0), 2),
        "magnetic_field": round(8.0 + 4.0 * math.sin(phase * 1.4), 2),
        "current": round(1.2 + 0.3 * math.cos(phase * 1.1), 2),
        "sensors_ok": True,
        "temp_sensor_ok": True,
        "magnetic_sensor_ok": True,
        "current_sensor_ok": True,
        "pwm_active": True,
        "pwm_frequency": 40,
        "pwm_duty_cycle": 55,
    }
    return json.dumps(payload, ensure_ascii=True)


def tuketim_sondasi(host: str, port: int, konu: str, kullanici: str | None = None, parola: str | None = None) -> str:
    """Konuya ABONE (tüketici) var mı? → "VAR" / "YOK" / "OLCULEMEDI: <sebep>".

    Ayrı bir MQTT v5 istemcisi TEK bir QoS 1 sonda yayınlar ve PUBACK reason code'unu okur
    (0 = eşleşen abone var, 16 = yok). Cevap gelmezse ya da başka bir kod gelirse sonuç
    ÖLÇÜLEMEDİ'dir — "var" SAYILMAZ. Y73: kimlikli broker'da (A-04) `kullanici`/`parola` ile bağlanır.
    """
    sonuc: dict = {}
    olay = threading.Event()

    def _on_publish(client, userdata, mid, reason_code=None, properties=None):
        sonuc["kod"] = getattr(reason_code, "value", reason_code)
        olay.set()

    try:
        sonda = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        if kullanici:
            sonda.username_pw_set(kullanici, parola)
        sonda.on_publish = _on_publish
        sonda.connect(host, port, keepalive=30)
        sonda.loop_start()
    except Exception as e:
        return f"OLCULEMEDI: sonda baglanamadi ({type(e).__name__}: {e})"
    try:
        info = sonda.publish(konu, build_payload(0, -1, time.time()), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return f"OLCULEMEDI: sonda yayini reddedildi rc={info.rc}"
        if not olay.wait(SONDA_ZAMAN_ASIMI_S):
            return f"OLCULEMEDI: {SONDA_ZAMAN_ASIMI_S:.0f} sn icinde PUBACK gelmedi (broker v5 destekliyor mu?)"
        kod = sonuc.get("kod")
        if kod == 0:
            return "VAR"
        if kod == ABONE_YOK_KODU:
            return "YOK"
        return f"OLCULEMEDI: PUBACK reason code {kod}"
    finally:
        try:
            sonda.loop_stop()
            sonda.disconnect()
        except Exception:
            pass


def kalibrasyon_nedeni(sonuc: str) -> str:
    """Kalibrasyon sondası 'YOK' dışında ne döndüyse GERÇEK nedeni ve eylemi.

    D0Ö.17 ek-3 (tur 6): ileti her sonuçta sabit "abonesizliği bildirmiyor ya da joker abone var" diyordu —
    en sık hata olan KAPALI broker yanlış nedenle bildiriliyordu (gerçek neden yalnız tırnak içindeydi).
    """
    if sonuc == "VAR":
        return (
            "broker abonesizligi (16) bildirmiyor ya da kalibrasyon konusuyla da eslesen KOK duzeyinde joker bir "
            "abone var (`#`, `+/#`)"
        )
    if sonuc.startswith("OLCULEMEDI: sonda baglanamadi"):
        return "broker'a baglanilamadi — broker calisiyor mu, --host/--port dogru mu?"
    if sonuc.startswith("OLCULEMEDI: ") and "PUBACK gelmedi" in sonuc:
        # D0Ö.17 ek-4 (tur 7): kimlik isteyen broker (allow_anonymous false) CONNECT'i reddeder, PUBACK hiç gelmez —
        # betik kimlik göndermediği için bu durum "v5 değil" diye YANLIŞ nedenle bildiriliyordu.
        return (
            "PUBACK gelmedi — broker MQTT v5 konusuyor mu, ya da baglantiyi reddetti mi (kimlik gerekli mi? "
            "allow_anonymous false / password_file; bu betik kimlik gondermez)?"
        )
    if sonuc == f"OLCULEMEDI: PUBACK reason code {YETKISIZ_KODU}":
        return f"PUBACK {YETKISIZ_KODU} (yetkisiz) — broker ACL'si sonda yayinini reddediyor"
    return "beklenmeyen sonda sonucu"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish synthetic sensor data for soak testing")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--hz", type=float, default=5.0, help="Per-coil publish rate")
    parser.add_argument("--coils", type=int, default=8)
    parser.add_argument("--duration-sec", type=int, default=300)
    parser.add_argument("--progress-sec", type=int, default=5, help="Progress print interval")
    parser.add_argument("--topic-prefix", default="pemf/coil")
    parser.add_argument(
        "--canli-onay",
        action="store_true",
        help="urunun CANLI 'pemf/' konularina yayini ACIKCA onayla (ESP acik makinede canli durumu ezer)",
    )
    # Y73 (sahip, S-G8): kimlikli yerel broker (A-04) — yayin yetkisi olan bir rolun kimligi (or. ESP: pemf_esp; parola
    # ESP basligindan). Verilmezse anonim baglanir (hazirlanmamis broker).
    parser.add_argument("--kullanici", default=None, help="MQTT kullanici adi (kimlikli broker)")
    parser.add_argument("--parola", default=None, help="MQTT parolasi (kimlikli broker)")
    args, unknown_args = parser.parse_known_args()

    if canli_urun_konusu_mu(args.topic_prefix) and not args.canli_onay:
        print(
            f"[HATA] '{args.topic_prefix}/<n>/sensors' urunun CANLI konusu: ESP acik bir makinede bobinlerin canli "
            "durumunu ezer ve ESP bayatlik bekcisini tazeler (gercek sensor kopmasi maskelenir). Yayin YAPILMADI, "
            "baglanilmadi. Test icin --topic-prefix soak/pemf/coil gibi bir onek VE o konuya abone bir tuketici "
            "(or. mosquitto_sub) kullanin; canli urune bilerek yuk bindirmek icin --canli-onay ekleyin.",
            file=sys.stderr,
        )
        return 2

    hz = max(0.5, args.hz)
    coils = max(1, args.coils)
    tick_interval = 1.0 / hz
    progress_sec = max(1, int(args.progress_sec))
    # D0Ö.17 ek-2 (tur 5): sonda bobin 1'e DEĞİL bobin 0'a — aynı `<önek>/+/sensors` filtresiyle eşleşir
    # (abone ölçümü aynı) ama ürün bobin 0'ı damga/kayıt/durum yazımından ÖNCE yok sayar (`api_server`
    # sensör işleyicisi `0 <= coil_index < 8`). `--canli-onay`da canlı bobin 1'e sahte telemetri basılmaz.
    sonda_konusu = f"{args.topic_prefix}/0/sensors"

    if unknown_args:
        print(f"Ignored extra args: {unknown_args}", flush=True)

    # D0Ö.17 ek-2: KALİBRASYON — MQTT 5 §3.4.2.1'de abonesizlikte 16 göndermek MAY; 16 yerine 0 dönen broker
    # ya da kalibrasyon konusuyla da eşleşen KÖK düzeyinde joker (`#`, `+/#`) bir abone ürün konusunda SAHTE 'VAR' üretir. Kimsenin abone
    # olmadığı rastgele bir konu (ürün ad alanı DIŞI) önce sondalanır: orada 'YOK' gelmiyorsa tüketim
    # ÖLÇÜLEMEZ. ⚠️ Ad alanı jokeri (`pemf/#`) kalibrasyon konusunu KAPSAMAZ (modül başlığı).
    kalibrasyon = tuketim_sondasi(
        args.host, args.port, f"soak-kalibrasyon/{uuid.uuid4().hex}/0/sensors", args.kullanici, args.parola
    )
    print(f"Tuketim sondasi kalibrasyonu (rastgele konu): {kalibrasyon}", flush=True)
    if kalibrasyon != "YOK":
        print(
            f"[HATA] TUKETIM OLCULEMEZ: kalibrasyon sondasi (abonesi olmayan rastgele konu) '{kalibrasyon}' dedi — "
            f"{kalibrasyon_nedeni(kalibrasyon)}. Soak YAPILMADI.",
            file=sys.stderr,
        )
        return 3

    # D0Ö.17 ek: TÜKETİCİ yoksa yük boşluğa gider — soak hiçbir şey ölçmez; başlamadan söyle.
    bastaki = tuketim_sondasi(args.host, args.port, sonda_konusu, args.kullanici, args.parola)
    print(f"Tuketim sondasi (basta, {sonda_konusu}): {bastaki}", flush=True)
    if bastaki != "VAR":
        print(
            f"[HATA] TUKETICI {'YOK' if bastaki == 'YOK' else 'OLCULEMEDI'} — yuk bosluga gider, soak YAPILMADI.",
            file=sys.stderr,
        )
        return 3

    print(
        f"Starting soak publish: host={args.host}:{args.port}, coils={coils}, hz={hz}, duration={args.duration_sec}s",
        flush=True,
    )

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    if args.kullanici:
        client.username_pw_set(args.kullanici, args.parola)
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    start = time.perf_counter()
    next_tick = start
    seq = 0
    published = 0
    failed = 0
    son_info = None
    next_progress = progress_sec

    try:
        while True:
            now = time.perf_counter()
            elapsed = now - start
            if elapsed >= args.duration_sec:
                break

            if elapsed >= next_progress:
                approx_rate = published / max(0.001, elapsed)
                print(
                    f"Progress: {elapsed:.1f}s/{args.duration_sec}s, published={published}, failed={failed}, "
                    f"rate={approx_rate:.1f} msg/s",
                    flush=True,
                )
                next_progress += progress_sec

            sleep_for = next_tick - now
            if sleep_for > 0:
                time.sleep(sleep_for)

            wall_now = time.time()
            for coil in range(1, coils + 1):
                topic = f"{args.topic_prefix}/{coil}/sensors"
                payload = build_payload(coil, seq, wall_now)
                # D0Ö.17: dönüş OKUNUR — eskiden bağlantı kopsa da (rc=MQTT_ERR_NO_CONN) sayılıp 0 dönülüyordu.
                info = client.publish(topic, payload, qos=0, retain=False)
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    published += 1
                    son_info = info
                else:
                    failed += 1
                    if failed == 1:
                        print(f"[HATA] publish reddedildi rc={info.rc} ({topic})", file=sys.stderr, flush=True)

            seq += 1
            next_tick += tick_interval
    except KeyboardInterrupt:
        print("Interrupted by user.", flush=True)

    finally:
        # rc=0 yalnız istemci KUYRUĞUNA kabul: son yayının sokete yazılmasını sınırlı süre bekle
        # (paho: loop_stop gönderimi garanti etmez).
        bekle = getattr(son_info, "wait_for_publish", None)
        if bekle is not None:
            try:
                bekle(timeout=5)
            except Exception:
                pass
        client.loop_stop()
        client.disconnect()

    total_sec = max(0.001, time.perf_counter() - start)
    msg_rate = published / total_sec
    print(f"Published={published} messages in {total_sec:.2f}s ({msg_rate:.1f} msg/s), failed={failed}")
    sondaki = tuketim_sondasi(args.host, args.port, sonda_konusu, args.kullanici, args.parola)
    print(f"Tuketim sondasi (sonda): {sondaki}", flush=True)
    kod = 0
    if failed or not published:
        print(
            f"[HATA] yayin dogrulanamadi: reddedilen={failed}, kabul edilen={published} — soak sonucu GECERSIZ.",
            file=sys.stderr,
        )
        kod = 1
    if sondaki != "VAR":
        print(
            f"[HATA] soak sonunda TUKETICI {'YOK' if sondaki == 'YOK' else 'OLCULEMEDI'} (tuketici kosu sirasinda "
            "dustu mu?) — soak sonucu GECERSIZ.",
            file=sys.stderr,
        )
        kod = kod or 3
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
