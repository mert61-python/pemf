# Author: mertaygn, cglrgrkn
"""mqtt_publish.py — MQTT 3.1.1 publisher (paho-mqtt).

ESP32-S3 broker (HiveMQ veya yerel mosquitto) -> tezde paper 8 mimarisi.

Topic'ler (config.output):
  pemf/coil/state   (state report)     -> publish edilen
  pemf/coil/cmd     (komut)            -> subscribe (opsiyonel donanim feedback)

QoS 1, TLS 1.2 plani (production), lab ortaminda QoS 0/1 + plain.
"""
from __future__ import annotations
import json
import time
from typing import Any

try:
    import paho.mqtt.client as mqtt
    _HAS_PAHO = True
except ImportError:                                # pragma: no cover
    _HAS_PAHO = False

from .cabin_config import OutputCfg


def _build_client(out_cfg: OutputCfg) -> "mqtt.Client":
    if not _HAS_PAHO:
        raise SystemExit(
            "paho-mqtt eksik. Yukle: pip install paho-mqtt>=2.0"
        )
    client = mqtt.Client(
        client_id=out_cfg.mqtt_client_id,
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    if out_cfg.mqtt_username:
        client.username_pw_set(out_cfg.mqtt_username, out_cfg.mqtt_password)
    if out_cfg.mqtt_tls:
        import ssl
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED,
                       tls_version=ssl.PROTOCOL_TLSv1_2)
    return client


def _compact_payload(result: dict) -> dict[str, Any]:
    """Bobin sayisini azalt — sadece ortalama duty/faz + en yakin bolge."""
    cancer = result.get("tumor_regions", [])
    healthy = result.get("healthy_regions", [])

    def avg_DP(regs: list[dict]) -> tuple[list[float], list[float]]:
        if not regs:
            return [0.0] * 7, [0.0] * 7
        D = [sum(r["D"][i] for r in regs) / len(regs) for i in range(7)]
        P = [sum(r["P"][i] for r in regs) / len(regs) for i in range(7)]
        return D, P

    D_c, P_c = avg_DP(cancer)
    D_h, P_h = avg_DP(healthy)
    return {
        "ts": result.get("timestamp", time.time()),
        "cabin_id": result.get("cabin_id"),
        "method": result.get("method"),
        "n_tumor": len(cancer),
        "n_healthy": len(healthy),
        "cabin_pose": {
            "marker_id": result.get("cabin_pose", {}).get("marker_id"),
            "tvec_mm": result.get("cabin_pose", {}).get("tvec_mm"),
            "reproj_err_px": result.get("cabin_pose", {})
                                  .get("reproj_error_px"),
        },
        "coil_detection": result.get("coil_detection", {}),
        "tumor": {
            "D": [round(x, 4) for x in D_c],
            "P": [round(x, 2) for x in P_c],
            "centroids_cabin_mm": [
                [round(c, 2) for c in r["centroid_cabin_mm"]]
                for r in cancer[:5]],
        },
        "healthy": {
            "D": [round(x, 4) for x in D_h],
            "P": [round(x, 2) for x in P_h],
            "centroids_cabin_mm": [
                [round(c, 2) for c in r["centroid_cabin_mm"]]
                for r in healthy[:5]],
        },
    }


def publish_result(out_cfg: OutputCfg, result_dict: dict,
                   *, compact: bool = True, quiet: bool = False) -> bool:
    """PipelineResult.to_dict() iceriklerini MQTT broker'a gonder.

    Returns: True basarili, False hata
    """
    if not _HAS_PAHO:
        if not quiet:
            print("[MQTT] paho-mqtt yuklu degil, atlandi.")
        return False
    client = _build_client(out_cfg)
    try:
        client.connect(out_cfg.mqtt_broker, out_cfg.mqtt_port,
                       keepalive=out_cfg.mqtt_keepalive)
    except OSError as e:
        if not quiet:
            print(f"[MQTT] Connect HATA: {e}")
        return False

    payload = _compact_payload(result_dict) if compact else result_dict
    msg = client.publish(out_cfg.mqtt_topic_state,
                         payload=json.dumps(payload, default=str),
                         qos=out_cfg.mqtt_qos, retain=False)
    msg.wait_for_publish(timeout=5.0)
    ok = msg.is_published()
    client.disconnect()
    if not quiet:
        size = len(json.dumps(payload, default=str))
        print(f"[MQTT] -> {out_cfg.mqtt_broker}:{out_cfg.mqtt_port} "
              f"topic={out_cfg.mqtt_topic_state} qos={out_cfg.mqtt_qos} "
              f"{size}B {'OK' if ok else 'FAIL'}")
    return bool(ok)


def subscribe_cmd(out_cfg: OutputCfg, callback) -> "mqtt.Client":
    """ESP32 -> pipeline geri-yayim (cmd / sensor feedback) icin abone ol.

    callback signature: callback(topic: str, payload: dict)
    """
    if not _HAS_PAHO:
        raise SystemExit("paho-mqtt eksik")
    client = _build_client(out_cfg)

    def on_message(c, _userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {"raw": msg.payload.hex()}
        callback(msg.topic, data)

    client.on_message = on_message
    client.connect(out_cfg.mqtt_broker, out_cfg.mqtt_port,
                   keepalive=out_cfg.mqtt_keepalive)
    client.subscribe(out_cfg.mqtt_topic_cmd, qos=out_cfg.mqtt_qos)
    client.loop_start()
    return client
