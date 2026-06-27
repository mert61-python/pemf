#!/usr/bin/env python3
"""Generate synthetic 8-coil sensor MQTT load at configurable Hz for soak tests."""

import argparse
import json
import math
import time

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: paho-mqtt. Install with: pip install paho-mqtt"
    ) from exc


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
    args, unknown_args = parser.parse_known_args()

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
                    f"Progress: {elapsed:.1f}s/{args.duration_sec}s, published={published}, rate={approx_rate:.1f} msg/s",
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
                client.publish(topic, payload, qos=0, retain=False)
                published += 1

            seq += 1
            next_tick += tick_interval
    except KeyboardInterrupt:
        print("Interrupted by user.", flush=True)

    finally:
        client.loop_stop()
        client.disconnect()

    total_sec = max(0.001, time.perf_counter() - start)
    msg_rate = published / total_sec
    print(f"Published={published} messages in {total_sec:.2f}s ({msg_rate:.1f} msg/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
