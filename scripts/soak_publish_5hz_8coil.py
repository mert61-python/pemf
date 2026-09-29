#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""Generate synthetic 8-coil sensor MQTT load at configurable Hz for soak tests.

⚠️ D0Ö.17 (B-10.218): ürünün MQTT aboneliklerinin TAMAMI `pemf/` ad alanında (api_server
`on_connect`: `pemf/coil/+/sensors|status|events|alarm|ack`, `pemf/gateway|bridge/status`).
Bu ad alanına yayın = CANLI ürüne sahte telemetri: ESP açık bir makinede (1.9.50 sahası) bobinlerin
canlı durumunu ezer ve ESP bayatlık bekçisini tazeler → gerçek sensör kopması MASKELENİR.
Bu yüzden `pemf/` önekli konuya yalnız `--canli-onay` ile yayın yapılır (varsayılan önek hâlâ
`pemf/coil`: bayraksız koşum BAĞLANMADAN reddedilir). Test için ör. `--topic-prefix soak/pemf/coil`.
Çıkış kodu `publish()` sonucuna dayanır: reddedilen yayın varsa ya da hiç yayın yapılamadıysa ≠0.
⚠️ Abonenin (backend'in) mesajı GERÇEKTEN tükettiği ÖLÇÜLMEZ: QoS 0'da broker yayıncıya abone
bilgisi vermez — 0, yalnız "her yayın istemci/broker yolunda kabul edildi" demektir.
"""

import argparse
import json
import math
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit("Missing dependency: paho-mqtt. Install with: pip install paho-mqtt") from exc

#: Ürünün MQTT ad alanı — bu önekle başlayan her konu CANLI sayılır (bkz. modül başlığı).
URUN_AD_ALANI = "pemf"


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
    args, unknown_args = parser.parse_known_args()

    if canli_urun_konusu_mu(args.topic_prefix) and not args.canli_onay:
        print(
            f"[HATA] '{args.topic_prefix}/<n>/sensors' urunun CANLI konusu: ESP acik bir makinede bobinlerin canli "
            "durumunu ezer ve ESP bayatlik bekcisini tazeler (gercek sensor kopmasi maskelenir). Yayin YAPILMADI, "
            "baglanilmadi. Test icin --topic-prefix soak/pemf/coil gibi bir onek verin; canli urune bilerek yuk "
            "bindirmek icin --canli-onay ekleyin.",
            file=sys.stderr,
        )
        return 2

    hz = max(0.5, args.hz)
    coils = max(1, args.coils)
    tick_interval = 1.0 / hz
    progress_sec = max(1, int(args.progress_sec))

    if unknown_args:
        print(f"Ignored extra args: {unknown_args}", flush=True)

    print(
        f"Starting soak publish: host={args.host}:{args.port}, coils={coils}, hz={hz}, duration={args.duration_sec}s",
        flush=True,
    )

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    start = time.perf_counter()
    next_tick = start
    seq = 0
    published = 0
    failed = 0
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
                else:
                    failed += 1
                    if failed == 1:
                        print(f"[HATA] publish reddedildi rc={info.rc} ({topic})", file=sys.stderr, flush=True)

            seq += 1
            next_tick += tick_interval
    except KeyboardInterrupt:
        print("Interrupted by user.", flush=True)

    finally:
        client.loop_stop()
        client.disconnect()

    total_sec = max(0.001, time.perf_counter() - start)
    msg_rate = published / total_sec
    print(f"Published={published} messages in {total_sec:.2f}s ({msg_rate:.1f} msg/s), failed={failed}")
    print("NOT: abonenin (backend) tuketimi OLCULMEDI — QoS 0'da broker abone bilgisi vermez.")
    if failed or not published:
        print(
            f"[HATA] yayin dogrulanamadi: reddedilen={failed}, kabul edilen={published} — soak sonucu GECERSIZ.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
