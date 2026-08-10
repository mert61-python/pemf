# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF uctan-uca duman testi (E2E smoke) - GERCEK backend sureci uzerinde davranis dogrulamasi.

pytest paketi birim/entegrasyon seviyesindedir; bu betik backend'i AYRI BIR SUREC olarak
ayaga kaldirip HTTP uzerinden konusur -> lifespan, arka-plan thread'leri, middleware zinciri
ve router'larin birlikte calismasini sinar.

IZOLASYON (kritik, bozmayin):
  * Alt-port (varsayilan 8123, PEMF_E2E_PORT ile degisir) - uretimdeki 8000'e DOKUNMAZ.
  * Gecici PEMF_DATA_DIR - gercek hasta/tedavi verisine DOKUNMAZ.
  * Yalniz 127.0.0.1'e baglanir.
  * PEMF_SIMULATE=1 -> sanal STM+ESP+8 bobin; DONANIM GEREKMEZ.

Kullanim:  python tools/e2e_smoke.py      (cikis kodu 0 = hepsi gecti)

Kapsam: denetim (2026-08-03) P0/P1/P2 duzeltmelerinin regresyon kilidi - acil-durdurma
kapsami, seans finalize, CORS varsayilani, thread-bombasi siniri, hasta sayfalama, AI Pro
uclari, gecmis/KPI/metrics.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Yollar TASINABILIR: bu dosya guii/tools/ altinda durur.
GUII = Path(__file__).resolve().parent.parent
PY = Path(sys.executable)
# 8000 KULLANILMAZ - kullanicinin calisan ornegine ve gercek verisine dokunmamak icin alt-port.
PORT = int(os.environ.get("PEMF_E2E_PORT", "8123"))
BASE = f"http://127.0.0.1:{PORT}"

_results = []


def check(name, cond, detail=""):
    _results.append((bool(cond), name, detail))
    print(f"  [{'GECTI' if cond else 'KALDI'}] {name}" + (f"  → {detail}" if detail else ""))
    return bool(cond)


def req(method, path, body=None, headers=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {}), dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except Exception:
            return e.code, {"_raw": raw}, dict(e.headers)


def main():
    data_dir = Path(tempfile.mkdtemp(prefix="pemf_e2e_"))
    env = dict(os.environ)
    env.update(
        {
            "PEMF_SIMULATE": "1",  # sanal STM+ESP+8 bobin + sensör
            "PEMF_DATA_DIR": str(data_dir),  # İZOLE veri dizini
            "PEMF_API_HOST": "127.0.0.1",
            "PEMF_API_PORT": str(PORT),
            "PEMF_HEADLESS": "1",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_LOG_DIR": str(data_dir / "logs"),
            # Gomulu Python dagitimi (._pth) betik dizinini sys.path'e eklemiyor → acikca ver.
            "PYTHONPATH": str(GUII),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("PEMF_REQUIRE_AUTH", None)  # LAN muaf → token'sız test
    env.pop("PEMF_CORS_ORIGINS", None)  # varsayılan CORS davranışını sına
    env.pop("PEMF_MASK_HISTORY_PII", None)

    log = open(data_dir / "backend.out", "wb")
    print(f"Backend baslatiliyor (port {PORT}, veri {data_dir}) ...")
    # Gomulu Python dagitiminda python310._pth IZOLE mod acar → PYTHONPATH YOK SAYILIR ve
    # betik dizini sys.path'e girmez ("No module named 'controllers'"). Uretimde sorun degil
    # (frozen EXE her seyi bundle'lar); kaynaktan calistirirken yolu acikca ekleyen bir
    # bootstrap ile baslat (tests/conftest.py ile ayni desen).
    boot = (
        "import sys, runpy; "
        f"sys.path.insert(0, r'{GUII}'); "
        f"runpy.run_path(r'{GUII / 'backend_service.py'}', run_name='__main__')"
    )
    proc = subprocess.Popen(
        [str(PY), "-c", boot, "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(GUII),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        ready = False
        for _ in range(120):
            if proc.poll() is not None:
                break
            try:
                s, b, _h = req("GET", "/api/health", timeout=3)
                if s == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ready:
            print("BACKEND ACILMADI — son 40 satir log:")
            print((data_dir / "backend.out").read_text("utf-8", "replace")[-4000:])
            return 1
        print("Backend hazir.\n")
        run_scenarios()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        log.close()

    ok = sum(1 for p, _, _ in _results if p)
    print(f"\n{'=' * 70}\nSONUC: {ok}/{len(_results)} gecti")
    for p, n, d in _results:
        if not p:
            print(f"  KALDI: {n}  {d}")
    return 0 if ok == len(_results) else 1


def run_scenarios():
    # ── 1) Health: yeni cloudRegistry alani (P2 TOFU gorunurlugu) ──────────────
    s, h, _ = req("GET", "/api/health")
    check("health 200", s == 200)
    check("health.cloudRegistry alani var (P2 TOFU gorunurlugu)", "cloudRegistry" in h, str(h.get("cloudRegistry")))

    # ── 2) CORS varsayilani: internet kokeni yetkilendirilmemeli (P0) ──────────
    _s, _b, hdr = req("GET", "/api/health", headers={"Origin": "http://evil.example.com"})
    check(
        "CORS: internet kokeni ACAO ALMAZ (P0)",
        hdr.get("access-control-allow-origin") is None,
        str(hdr.get("access-control-allow-origin")),
    )
    _s, _b, hdr2 = req("GET", "/api/health", headers={"Origin": "http://192.168.1.50:8123"})
    check(
        "CORS: LAN kokeni CALISIR (regresyon degil)",
        hdr2.get("access-control-allow-origin") == "http://192.168.1.50:8123",
        str(hdr2.get("access-control-allow-origin")),
    )

    # ── 3) Thread-bombasi: 20k bobin listesi SINIRDA reddedilmeli (P1) ─────────
    s, _b, _ = req("POST", "/api/session/start", {"coil_ids": [6] * 20000, "duration_minutes": 1})
    check("start: 20k coil_ids 422 (P1 thread-bombasi)", s == 422, f"HTTP {s}")

    # ── 4) Seans yasam dongusu + normalize ────────────────────────────────────
    s, b, _ = req(
        "POST",
        "/api/session/start",
        {
            "patient_name": "E2E-Minnos",
            "operator_name": "Dr E2E",
            "mode": "Manuel",
            "frequency": 50.0,
            "duty": 25.0,
            "duration_minutes": 5,
            "coil_ids": [1, 1, 2, 2, 7],  # tekrarli → dedup beklenir
        },
    )
    check("session/start 200", s == 200, f"HTTP {s}")
    sess = b.get("session", {})
    check("start: coil_ids dedup edildi", sess.get("coil_ids") == [1, 2, 7], str(sess.get("coil_ids")))
    check("start: db_session_id acildi", bool(sess.get("db_session_id")), str(sess.get("db_session_id")))
    check("start: start_mono (monotonic watchdog, P2) kuruldu", sess.get("start_mono") is not None)
    db_sid = sess.get("db_session_id")

    # ── 5) Simule telemetri birikimi ──────────────────────────────────────────
    time.sleep(6)
    s, snap, _ = req("GET", "/api/dashboard-snapshot")
    coils = snap.get("coils", [])
    running = [c for c in coils if c.get("running")]
    check("sim: bobinler calisiyor gorunuyor", len(running) >= 1, f"{len(running)} bobin")
    check("sim: sicaklik telemetrisi akiyor", any(float(c.get("objectTemp") or 0) > 0 for c in running))

    # ── 6) ACIL DURDURMA: ESP 6-8'in HEPSI + sessionCoilIds (P0 #2) ───────────
    s, es, _ = req("POST", "/api/hardware/emergency_stop")
    check("emergency_stop 200", s == 200, f"HTTP {s}")
    estopped = {r.get("coilId") for r in es.get("mqttResults", [])}
    check(
        "E-STOP: ESP 6,7,8'in HEPSI durduruldu (P0 — dar seans kapsami YOK SAYILDI)",
        estopped == {6, 7, 8},
        str(sorted(estopped)),
    )
    check(
        "E-STOP: sessionCoilIds denetim izi var (P0)",
        es.get("sessionCoilIds") == [1, 2, 7],
        str(es.get("sessionCoilIds")),
    )
    check("E-STOP: seans kapatildi", es.get("status") in ("success", "partial"), es.get("status"))

    # ── 7) Seans DB'de KAPANDI mi (P2 finalize) ───────────────────────────────
    time.sleep(2)
    s, hist, _ = req("GET", "/api/history/?limit=20")
    # /api/history/ DOGRUDAN dizi doner (sarmalayici dict yok).
    rows = hist if isinstance(hist, list) else (hist.get("data") or hist.get("sessions") or [])
    row = next((r for r in rows if r.get("id") == db_sid), None)
    check("history: E-STOP sonrasi seans DB'de bulunuyor", row is not None, f"db_sid={db_sid} n={len(rows)}")
    if row:
        check(
            "history: seans 'active' KALMADI (P2 finalize)",
            row.get("session_status") == "completed",
            str(row.get("session_status")),
        )
        check(
            "history: PII maskelenmedi (sahip karari — varsayilan KAPALI)",
            row.get("patient_name") == "E2E-Minnos",
            str(row.get("patient_name")),
        )

    # ── 8) Not kaydi GERCEK sureyi EZMEMELI (P1) ──────────────────────────────
    if row:
        gercek = row.get("duration_minutes")
        s, nb, _ = req(
            "POST",
            "/api/session/notes",
            {
                "notes": "E2E gozlem",
                "duration_minutes": 999,  # PLANLANAN sure gonder
                "frequency": 50.0,
                "intensity": 2.0,
            },
        )
        check("notes 200", s == 200, f"HTTP {s}")
        time.sleep(1)
        _s, hist2, _ = req("GET", "/api/history/?limit=20")
        rows2 = hist2 if isinstance(hist2, list) else (hist2.get("data") or hist2.get("sessions") or [])
        row2 = next((r for r in rows2 if r.get("id") == db_sid), None)
        check(
            "notes: GERCEK sure korundu (P1 — 999 ile EZILMEDI)",
            row2 and row2.get("duration_minutes") == gercek,
            f"once={gercek} sonra={row2.get('duration_minutes') if row2 else '?'}",
        )

    # ── 9) Hasta sayfalama SQL'de (P2) ────────────────────────────────────────
    for i in range(5):
        req("POST", "/api/patients", {"name": f"E2E-Hasta{i}", "species": "Kedi"})
    s, p1, _ = req("GET", "/api/patients?limit=2&offset=0")
    s2, p2, _ = req("GET", "/api/patients?limit=2&offset=2")
    check("patients: sayfa boyutu uygulandi (P2)", len(p1.get("data", [])) == 2, str(len(p1.get("data", []))))
    check("patients: total tam sayim", (p1.get("total") or 0) >= 5, str(p1.get("total")))
    n1 = {x.get("name") for x in p1.get("data", [])}
    n2 = {x.get("name") for x in p2.get("data", [])}
    check("patients: sayfalar ortusmuyor", n1.isdisjoint(n2), f"{n1} vs {n2}")

    # ── 10) AI Pro baslat/durdur (kamera yok → zarifce reddetmeli) ────────────
    s, ai, _ = req("POST", "/api/ai/pro/start", {"organ_id": 2, "duration_minutes": 5})
    check("ai/pro/start yanit veriyor (cokme yok)", s in (200, 409, 422, 503), f"HTTP {s}")
    s, _b, _ = req("POST", "/api/ai/pro/stop")
    check("ai/pro/stop 200 (bobin 1-8 STOP kapsami P1)", s == 200, f"HTTP {s}")

    s, _b, _ = req("POST", "/api/ai/pro/start", {"organ_id": 9, "duration_minutes": 5})
    check("ai/pro: desteklenmeyen organ 422", s == 422, f"HTTP {s}")

    # ── 11) KPI + metrics + istatistik uclari ayakta ──────────────────────────
    for path, ad in (
        ("/api/history/statistics", "istatistik"),
        ("/api/gateway/status", "gateway"),
        ("/api/system/info", "system info"),
    ):
        try:
            st, _bb, _hh = req("GET", path)
            check(f"{ad} ucu 200", st == 200, f"HTTP {st}")
        except Exception as e:
            check(f"{ad} ucu 200", False, str(e)[:80])
    # /metrics Prometheus TEXT dondurur (JSON degil) → ham oku
    try:
        with urllib.request.urlopen(BASE + "/metrics", timeout=10) as r:
            body = r.read().decode("utf-8", "replace")
        check("prometheus metrics ucu 200 + text", r.status == 200 and "#" in body, f"{len(body)} bayt")
    except Exception as e:
        check("prometheus metrics ucu 200 + text", False, str(e)[:80])

    # ── 12) Acil durdurma AUTH-MUAF kalmali (fail-safe) ───────────────────────
    s, _b, _ = req("POST", "/api/hardware/emergency_stop")
    check("E-STOP tekrar cagrilabilir (idempotent, fail-safe)", s == 200, f"HTTP {s}")


if __name__ == "__main__":
    sys.exit(main())
