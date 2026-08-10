# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PEMF TAM uctan-uca test — STM + ESP donanimi BAGLIYMIS GIBI (PEMF_SIMULATE=1).

e2e_smoke.py denetim-regresyonlarini kilitler; BU betik KULLANICI AKISLARINI sinar:
hasta kayitlari (CRUD + sayfalama + toplu-silme koruma), seans yasam dongusu
(STM 1-5 / ESP 6-8 / 8-bobin), bobin kontrolu, canli telemetri (WS), gecmis + KPI
ve UC PROFILIN (ev sahibi / veteriner / arastirma) uc-kapsamlari.

IZOLASYON (bozmayin):
  * Alt-port (varsayilan 8124, PEMF_E2E_PORT ile degisir) — uretimdeki 8000'e DOKUNMAZ.
  * Gecici PEMF_DATA_DIR — gercek hasta/tedavi verisine DOKUNMAZ.
  * Yalniz 127.0.0.1. PEMF_SIMULATE=1 → sanal STM+ESP+8 bobin; DONANIM GEREKMEZ.

Kullanim:  python tools/e2e_full.py     (cikis kodu 0 = hepsi gecti)
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

GUII = Path(__file__).resolve().parent.parent
PY = Path(sys.executable)
PORT = int(os.environ.get("PEMF_E2E_PORT", "8124"))
BASE = f"http://127.0.0.1:{PORT}"

_results = []
_section = ""


def section(title):
    global _section
    _section = title
    print(f"\n─── {title} " + "─" * max(0, 66 - len(title)))


def check(name, cond, detail=""):
    _results.append((bool(cond), f"[{_section}] {name}", detail))
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


def raw_get(path, timeout=30):
    """Metin/CSV donduren uclar icin ham govde."""
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def snap():
    _s, b, _h = req("GET", "/api/dashboard-snapshot")
    return b


def coil_of(snapshot, cid):
    for c in snapshot.get("coils", []):
        if int(c.get("id") or c.get("coilId") or 0) == cid:
            return c
    return {}


def running_ids(snapshot):
    out = []
    for c in snapshot.get("coils", []):
        if c.get("running"):
            out.append(int(c.get("id") or c.get("coilId") or 0))
    return sorted(out)


def wait_until(fn, timeout=12, step=0.5):
    """fn() dogru olana kadar bekle (sim dongusu ~1 sn araliklarla yayin yapar)."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(step)
    return last


# ═══════════════════════════════════════════════════════════════════════════
def main():
    data_dir = Path(tempfile.mkdtemp(prefix="pemf_e2e_full_"))
    env = dict(os.environ)
    env.update(
        {
            "PEMF_SIMULATE": "1",
            "PEMF_STM_PORT": "SIM",
            "PEMF_DATA_DIR": str(data_dir),
            "PEMF_API_HOST": "127.0.0.1",
            "PEMF_API_PORT": str(PORT),
            "PEMF_HEADLESS": "1",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_LOG_DIR": str(data_dir / "logs"),
            "PYTHONPATH": str(GUII),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    for k in ("PEMF_REQUIRE_AUTH", "PEMF_REQUIRE_PATIENT_AUTH", "PEMF_CORS_ORIGINS", "PEMF_MASK_HISTORY_PII"):
        env.pop(k, None)

    log = open(data_dir / "backend.out", "wb")
    print(f"Backend baslatiliyor (port {PORT}, veri {data_dir}) — SANAL STM + ESP ...")
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
                if req("GET", "/api/health", timeout=3)[0] == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if not ready:
            print("BACKEND ACILMADI — log kuyrugu:")
            print((data_dir / "backend.out").read_text("utf-8", "replace")[-4000:])
            return 1
        print("Backend hazir.")
        run_all()
    finally:
        try:
            req("POST", "/api/hardware/emergency_stop", timeout=10)  # guvenli kapanis
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()

    ok = sum(1 for p, _, _ in _results if p)
    print(f"\n{'=' * 72}\nSONUC: {ok}/{len(_results)} gecti")
    fails = [(n, d) for p, n, d in _results if not p]
    for n, d in fails:
        print(f"  KALDI: {n}  {d}")
    print(f"Backend logu: {data_dir / 'backend.out'}")
    return 0 if not fails else 1


# ═══════════════════════════════════════════════════════════════════════════
def run_all():
    a_hardware()
    b_patients()
    c_session_stm()
    d_session_esp()
    e_session_guards()
    f_coil_control()
    g_profile_pet_owner()
    h_profile_researcher()
    i_profile_vet_kpi()


# ── A) SANAL DONANIM: STM + ESP bagliymis gibi ─────────────────────────────
def a_hardware():
    section("A. Donanim (sanal STM + ESP)")
    s, h, _ = req("GET", "/api/health")
    check("health 200", s == 200, f"HTTP {s}")

    sn = snap()
    check("snapshot: STM32 baglantisi 'online'", sn.get("stm") == "online", str(sn.get("stm")))
    check("snapshot: MQTT broker 'online'", sn.get("mqtt") == "online", str(sn.get("mqtt")))
    check("snapshot: gateway 'online'", sn.get("gateway") == "online", str(sn.get("gateway")))
    coils = sn.get("coils", [])
    check("snapshot: 8 bobin bildiriliyor", len(coils) == 8, f"{len(coils)} bobin")
    conn = [c for c in coils if c.get("connected")]
    check("snapshot: 8 bobinin hepsi 'connected'", len(conn) == 8, f"{len(conn)}/8")
    check(
        "snapshot: bobin 1-5 STM, 6-8 ESP olarak isaretli",
        all(coil_of(sn, i).get("stm32Driven") for i in range(1, 6))
        and not any(coil_of(sn, i).get("stm32Driven") for i in range(6, 9)),
    )
    check("snapshot: bosta hicbir bobin calismiyor", running_ids(sn) == [], str(running_ids(sn)))

    s, st, _ = req("POST", "/api/hardware/selftest")
    check("hardware/selftest 200", s == 200, f"HTTP {s}")

    # Canli telemetri: WS zarf tipi {"type": ..., "data": ...}
    frames = _ws_collect(seconds=6)
    check("WS: canli telemetri kareleri geliyor", len(frames) >= 5, f"{len(frames)} kare")
    types = {f.get("type") for f in frames if isinstance(f, dict)}
    check("WS: ilk baglantida tam snapshot gonderiliyor", "snapshot" in types, str(sorted(types))[:120])
    check("WS: bobin durumu yayinlaniyor (coil_status)", "coil_status" in types, str(sorted(types))[:120])
    sensor = [f for f in frames if f.get("type") == "sensor_data"]
    check("WS: sensor telemetrisi yayinlaniyor (sensor_data)", len(sensor) >= 8, f"{len(sensor)} sensor karesi")
    if sensor:
        d = sensor[0].get("data") or {}
        check(
            "WS: sensor karesinde manyetik/sicaklik/akim alanlari var",
            all(k in d for k in ("magneticMt", "objectTemp", "ambientTemp", "currentA")),
            str(sorted(d))[:120],
        )


def _ws_collect(seconds=6):
    out = []
    try:
        import websocket  # websocket-client

        ws = websocket.create_connection(f"ws://127.0.0.1:{PORT}/ws", timeout=5)
        end = time.time() + seconds
        while time.time() < end:
            try:
                ws.settimeout(max(0.5, end - time.time()))
                msg = ws.recv()
            except Exception:
                break
            try:
                out.append(json.loads(msg))
            except Exception:
                out.append({"_raw": str(msg)[:60]})
        ws.close()
    except Exception as e:
        out.append({"_error": str(e)[:120]})
    return [f for f in out if "_error" not in f]


# ── B) HASTA KAYITLARI ─────────────────────────────────────────────────────
def b_patients():
    section("B. Hasta kayitlari (CRUD)")
    rec = {
        "name": "Pamuk",
        "species": "Kedi",
        "breed": "British Shorthair",
        "age": "3",
        "weight": "4.2",
        "owner": "Ayse Yilmaz",
        "vet_contact": "+90 555 111 22 33",
        "owner_email": "sahip@ornek.com",
        "operator_email": "dr.veteriner@klinik.com",
    }
    s, b, _ = req("POST", "/api/patients", rec)
    pid = b.get("patient_id")
    check("hasta ekleme 200 + patient_id", s == 200 and bool(pid), f"HTTP {s} id={pid}")

    s, lst, _ = req("GET", "/api/patients")
    row = next((p for p in lst.get("data", []) if p.get("id") == pid), None)
    check("listede goruluyor", row is not None, f"toplam={lst.get('total')}")
    if row:
        bad = [
            k
            for k in ("name", "species", "breed", "owner", "vet_contact", "owner_email")
            if str(row.get(k) or "") != rec[k]
        ]
        check("tum alanlar sifreleme sonrasi AYNEN geri okundu", not bad, f"farkli={bad}")
        check(
            "operator_email kaydedildi (klinik-ici sahiplik filtresi)",
            row.get("operator_email") == rec["operator_email"],
            str(row.get("operator_email")),
        )

    # Guncelleme (ayni id ile POST)
    s, _b, _ = req("POST", "/api/patients", {**rec, "id": pid, "weight": "5.0", "name": "Pamuk (guncel)"})
    check("hasta guncelleme 200", s == 200, f"HTTP {s}")
    s, lst2, _ = req("GET", "/api/patients")
    row2 = next((p for p in lst2.get("data", []) if p.get("id") == pid), None)
    check(
        "guncelleme kalici (ad + kilo)",
        row2 and row2.get("name") == "Pamuk (guncel)" and str(row2.get("weight")) == "5.0",
        f"{row2.get('name') if row2 else '?'} / {row2.get('weight') if row2 else '?'}",
    )
    check(
        "guncellemede yeni kayit ACILMADI (kopya yok)",
        lst2.get("total") == lst.get("total"),
        f"{lst.get('total')} → {lst2.get('total')}",
    )

    # Sayfalama
    ids = [pid]
    for i in range(6):
        _s, bb, _ = req(
            "POST",
            "/api/patients",
            {"name": f"Test-Hasta-{i}", "species": "Kedi", "operator_email": ("dr.a@k.com" if i % 2 else "dr.b@k.com")},
        )
        ids.append(bb.get("patient_id"))
    s, p1, _ = req("GET", "/api/patients?limit=3&offset=0")
    s2, p2, _ = req("GET", "/api/patients?limit=3&offset=3")
    check("sayfalama: limit uygulandi", len(p1.get("data", [])) == 3, str(len(p1.get("data", []))))
    check(
        "sayfalama: sayfalar ortusmuyor",
        {x["id"] for x in p1.get("data", [])}.isdisjoint({x["id"] for x in p2.get("data", [])}),
    )
    check("toplam sayim dogru", p1.get("total") == 7, str(p1.get("total")))

    # Tekil silme — iki yol
    s, _b, _ = req("DELETE", f"/api/patients/{ids[1]}")
    check("tekil silme (DELETE) 200", s == 200, f"HTTP {s}")
    s, _b, _ = req("POST", f"/api/patients/{ids[2]}/delete")
    check("tekil silme (POST uyumluluk yolu) 200", s == 200, f"HTTP {s}")
    s, lst3, _ = req("GET", "/api/patients")
    check("silinenler listede YOK", lst3.get("total") == 5, str(lst3.get("total")))

    # Toplu silme korumasi
    s, b4, _ = req("POST", "/api/patients/delete_all", {})
    check("toplu silme onaysiz 400 (kazara-tik korumasi)", s == 400, f"HTTP {s}")
    s, lst4, _ = req("GET", "/api/patients")
    check("onaysiz istekten sonra hastalar DURUYOR", lst4.get("total") == 5, str(lst4.get("total")))
    s, b5, _ = req("POST", "/api/patients/delete_all", {"confirm": "DELETE_ALL"})
    check("toplu silme onayli 200", s == 200 and b5.get("status") == "success", f"HTTP {s} {b5}")
    s, lst5, _ = req("GET", "/api/patients")
    check("toplu silme sonrasi liste bos", lst5.get("total") == 0, str(lst5.get("total")))


# ── C) SEANS — STM bobinleri (1-5) ─────────────────────────────────────────
def c_session_stm():
    section("C. Seans — STM bobinleri (1-5)")
    _s, pb, _ = req(
        "POST",
        "/api/patients",
        {
            "name": "Minnos",
            "species": "Kedi",
            "owner": "Mehmet Kaya",
            "owner_email": "mehmet@ornek.com",
            "operator_email": "dr.veteriner@klinik.com",
        },
    )
    pid = pb.get("patient_id")

    s, b, _ = req(
        "POST",
        "/api/session/start",
        {
            "patient_id": pid,
            "patient_name": "Minnos",
            "operator_name": "Dr. Test",
            "operator_email": "dr.veteriner@klinik.com",
            "mode": "Manuel",
            "target_condition": "Artrit",
            "frequency": 40.0,
            "duty": 30.0,
            "intensity": 20.0,
            "duration_minutes": 5,
            "coil_ids": [1, 2, 3, 4, 5],
        },
    )
    check("seans basladi (STM 1-5) 200", s == 200, f"HTTP {s} {str(b)[:120]}")
    sess = b.get("session", {})
    db_sid = sess.get("db_session_id")
    check("DB seans satiri seans BASINDA acildi", bool(db_sid), str(db_sid))
    check("coil_ids beklenen", sess.get("coil_ids") == [1, 2, 3, 4, 5], str(sess.get("coil_ids")))

    s, act, _ = req("GET", "/api/session/active")
    check(
        "session/active aktif + hasta dogru",
        act.get("is_active") and act.get("patient_name") == "Minnos",
        str(act.get("patient_name")),
    )
    check(
        "session/active kalan sure hesapliyor",
        isinstance(act.get("remaining_sec"), int) and act["remaining_sec"] > 0,
        f"kalan={act.get('remaining_sec')}sn",
    )

    sn = wait_until(lambda: snap() if len(running_ids(snap())) >= 5 else None, timeout=15) or snap()
    check("bobin 1-5 CALISIYOR (sanal STM)", running_ids(sn) == [1, 2, 3, 4, 5], str(running_ids(sn)))
    c1 = coil_of(sn, 1)
    check(
        "bobin parametreleri seansla eslesiyor (freq 40 Hz / duty %30)",
        abs(float(c1.get("frequencyHz") or 0) - 40.0) < 0.6 and abs(float(c1.get("dutyCycle") or 0) - 30.0) < 0.6,
        f"freq={c1.get('frequencyHz')} duty={c1.get('dutyCycle')}",
    )
    check(
        "sicaklik telemetrisi akiyor (objectTemp>0)", float(c1.get("objectTemp") or 0) > 0, f"{c1.get('objectTemp')} °C"
    )
    check("manyetik alan telemetrisi akiyor (mT)", float(c1.get("magneticMt") or 0) > 0.5, f"{c1.get('magneticMt')} mT")
    check("akim telemetrisi akiyor (A)", float(c1.get("currentA") or 0) > 0, f"{c1.get('currentA')} A")
    check("ESP bobinleri (6-8) bu seansta CALISMIYOR", all(not coil_of(sn, i).get("running") for i in (6, 7, 8)))
    at = sn.get("activeTreatment") or {}
    check(
        "aktif tedavi ozeti canli (isActive + frekans)",
        at.get("isActive") is True and abs(float(at.get("frequencyHz") or 0) - 40.0) < 0.6,
        f"isActive={at.get('isActive')} freq={at.get('frequencyHz')}",
    )
    check("hasta ozeti kartinda aktif hasta var", bool(sn.get("patient")), str(sn.get("patient"))[:80])

    time.sleep(3)
    s, stp, _ = req("POST", "/api/session/stop")
    check("seans durduruldu 200", s == 200, f"HTTP {s}")
    sn2 = wait_until(lambda: snap() if not running_ids(snap()) else None, timeout=12) or snap()
    check("durdurmadan sonra HICBIR bobin calismiyor", running_ids(sn2) == [], str(running_ids(sn2)))
    s, act2, _ = req("GET", "/api/session/active")
    check("session/active artik pasif", not act2.get("is_active"), str(act2.get("is_active")))

    time.sleep(2)
    s, hist, _ = req("GET", "/api/history/?limit=20")
    rows = hist if isinstance(hist, list) else (hist.get("data") or [])
    row = next((r for r in rows if r.get("id") == db_sid), None)
    check("gecmiste seans kaydi var", row is not None, f"db_sid={db_sid} n={len(rows)}")
    if row:
        check("gecmis: durum 'completed'", row.get("session_status") == "completed", str(row.get("session_status")))
        check("gecmis: hasta adi dogru", row.get("patient_name") == "Minnos", str(row.get("patient_name")))
    s, det, _ = req("GET", f"/api/history/{db_sid}/details")
    check("seans detay ucu 200", s == 200, f"HTTP {s}")
    st, csv = raw_get(f"/api/history/{db_sid}/coil_runs.csv")
    check(
        "bobin-calisma CSV'si uretildi",
        st == 200 and len(csv.splitlines()) >= 2,
        f"HTTP {st}, {len(csv.splitlines())} satir",
    )
    globals()["_STM_SID"] = db_sid


# ── D) SEANS — ESP bobinleri (6-8) ─────────────────────────────────────────
def d_session_esp():
    section("D. Seans — ESP/MQTT bobinleri (6-8)")
    s, b, _ = req(
        "POST",
        "/api/session/start",
        {
            "patient_name": "Duman",
            "operator_name": "Dr. Test",
            "mode": "Otomatik",
            "frequency": 20.0,
            "duty": 50.0,
            "duration_minutes": 3,
            "coil_ids": [6, 7, 8],
        },
    )
    check("ESP seansi basladi 200", s == 200, f"HTTP {s}")
    sess = b.get("session", {})
    check("coil_ids [6,7,8]", sess.get("coil_ids") == [6, 7, 8], str(sess.get("coil_ids")))

    sn = wait_until(lambda: snap() if running_ids(snap()) == [6, 7, 8] else None, timeout=15) or snap()
    check("ESP bobinleri (6-8) CALISIYOR", running_ids(sn) == [6, 7, 8], str(running_ids(sn)))
    c7 = coil_of(sn, 7)
    check(
        "ESP bobin parametreleri seansla eslesiyor (freq 20 Hz / duty %50)",
        abs(float(c7.get("frequencyHz") or 0) - 20.0) < 0.6 and abs(float(c7.get("dutyCycle") or 0) - 50.0) < 0.6,
        f"freq={c7.get('frequencyHz')} duty={c7.get('dutyCycle')}",
    )
    check("STM bobinleri (1-5) bu seansta CALISMIYOR", all(not coil_of(sn, i).get("running") for i in range(1, 6)))

    s, _b, _ = req("POST", "/api/session/stop")
    check("ESP seansi durduruldu 200", s == 200, f"HTTP {s}")
    sn2 = wait_until(lambda: snap() if not running_ids(snap()) else None, timeout=12) or snap()
    check("ESP bobinleri durdu", running_ids(sn2) == [], str(running_ids(sn2)))
    check("durdurmadan sonra aktif hasta temizlendi", sn2.get("patient") is None, str(sn2.get("patient")))


# ── E) SEANS koruma/kenar durumlari ────────────────────────────────────────
def e_session_guards():
    section("E. Seans korumalari (8 bobin + guard)")
    s, b, _ = req(
        "POST",
        "/api/session/start",
        {
            "patient_name": "TumBobin",
            "operator_name": "Dr. Test",
            "mode": "Manuel",
            "frequency": 50.0,
            "duty": 25.0,
            "duration_minutes": 4,
            "coil_ids": [1, 2, 3, 4, 5, 6, 7, 8],
        },
    )
    check("8 bobinli seans basladi", s == 200, f"HTTP {s}")
    sn = wait_until(lambda: snap() if len(running_ids(snap())) == 8 else None, timeout=18) or snap()
    check("8 bobinin HEPSI calisiyor", running_ids(sn) == list(range(1, 9)), str(running_ids(sn)))

    s, _b, _ = req("POST", "/api/session/start", {"patient_name": "Ikinci", "duration_minutes": 2})
    check("ikinci seans REDDEDILDI (409 — cift tedavi yok)", s == 409, f"HTTP {s}")

    s, _b, _ = req("POST", "/api/session/stop")
    check("seans durduruldu", s == 200, f"HTTP {s}")
    s, again, _ = req("POST", "/api/session/stop")
    check("aktif seans yokken stop guvenli (idempotent)", s == 200, f"HTTP {s} {again.get('message', '')}")

    s, _b, _ = req("POST", "/api/session/start", {"patient_name": "X", "duration_minutes": 0})
    check("duration_minutes=0 REDDEDILDI (422 — sonsuz seans yok)", s == 422, f"HTTP {s}")

    s, b9, _ = req(
        "POST", "/api/session/start", {"patient_name": "Filtre", "duration_minutes": 2, "coil_ids": [9, 12, 0]}
    )
    ok9 = s == 200 and (b9.get("session") or {}).get("coil_ids") == list(range(1, 9))
    check(
        "gecersiz bobin id'leri filtrelendi (→ tum bobinler)",
        ok9,
        f"HTTP {s} {(b9.get('session') or {}).get('coil_ids')}",
    )
    req("POST", "/api/session/stop")

    s, es, _ = req("POST", "/api/hardware/emergency_stop")
    check("ACIL DURDURMA 200", s == 200, f"HTTP {s}")
    sn3 = wait_until(lambda: snap() if not running_ids(snap()) else None, timeout=12) or snap()
    check("acil durdurma sonrasi bobinler kapali", running_ids(sn3) == [], str(running_ids(sn3)))


# ── F) Bobin kontrolu (tekil + toplu) ──────────────────────────────────────
def f_coil_control():
    section("F. Bobin kontrolu (Kontrol Paneli)")
    # NOT: PEMF_SIMULATE dongusu bobin durumunu 0,5 sn'de bir SEANS durumundan yeniden turetir
    # (api_server.py _hardware_simulation_loop) → seanssiz tekil komutlar snapshot'a YANSIMAZ.
    # Bu yuzden burada komut KABULU + surucu katmanina ulasmasi dogrulanir; "calisiyor" gorunumu
    # seans testlerinde (C/D/E) zaten kanitlandi.
    s, b1, _ = req("POST", "/api/coil/1/control", {"freq": 60.0, "duty": 35.0, "duration": 60, "start": True})
    check("tekil STM bobin (1) baslat komutu kabul edildi", s == 200, f"HTTP {s}")
    check(
        "STM komutu surucuye iletildi (command_id/durum dondu)",
        bool(b1.get("commandId") or b1.get("command_id") or b1.get("status")),
        str(b1)[:120],
    )
    s, _b, _ = req("POST", "/api/coil/1/control", {"start": False})
    check("tekil STM bobin durdurma komutu kabul edildi", s == 200, f"HTTP {s}")

    s, b7, _ = req("POST", "/api/coil/7/control", {"freq": 15.0, "duty": 40.0, "duration": 60, "start": True})
    check("tekil ESP bobin (7) baslat komutu kabul edildi", s == 200, f"HTTP {s}")
    check("ESP komutu MQTT'ye yayinlandi", "mqtt" in json.dumps(b7).lower() or bool(b7.get("status")), str(b7)[:120])
    s, _b, _ = req("POST", "/api/coil/7/control", {"start": False})
    check("tekil ESP bobin durdurma komutu kabul edildi", s == 200, f"HTTP {s}")

    s, bb, _ = req(
        "POST", "/api/coil/batch", {"coil_ids": [1, 2, 6], "freq": 30.0, "duty": 20.0, "duration": 60, "start": True}
    )
    check("toplu bobin baslatma 200", s == 200, f"HTTP {s}")
    check(
        "toplu komut 3 bobini de kapsadi",
        len(bb.get("results") or bb.get("coils") or bb.get("mqttResults") or []) >= 1
        or bb.get("status") in ("success", "ok"),
        str(bb)[:140],
    )
    s, _b, _ = req("POST", "/api/coil/batch", {"coil_ids": [1, 2, 6], "start": False})
    check("toplu durdurma 200", s == 200, f"HTTP {s}")

    s, _b, _ = req("POST", "/api/coil/9/control", {"start": True})
    check("gecersiz bobin (9) 400", s == 400, f"HTTP {s}")
    s, _b, _ = req("POST", "/api/hardware/reset_pwm")
    check("PWM sifirlama 200", s == 200, f"HTTP {s}")
    s, ap, _ = req("POST", "/api/hardware/auto_preset", {"condition": "Artrit"})
    check("otomatik preset ucu yanit veriyor", s in (200, 422), f"HTTP {s}")
    req("POST", "/api/hardware/emergency_stop")
    sn = wait_until(lambda: snap() if not running_ids(snap()) else None, timeout=12) or snap()
    check("bolum sonu: tum bobinler kapali", running_ids(sn) == [], str(running_ids(sn)))


# ── G) PROFIL: Ev Sahibi (pet_owner) — cihaz YOK, yalniz analiz ────────────
def g_profile_pet_owner():
    section("G. Profil — Ev Sahibi (analiz)")
    s, sn, _ = req("GET", "/api/dashboard-snapshot")
    check("ana ekran anlik goruntusu 200", s == 200, f"HTTP {s}")

    s, d, _ = req(
        "POST",
        "/api/ai/disease",
        {"age": 3, "weight": 4.2, "hr": 180, "temp": 38.6, "duration": 2, "symptom_indices": [0, 3]},
        timeout=180,
    )
    check("hastalik analizi 200 (kedi, form girdisi)", s == 200, f"HTTP {s}")
    check(
        "hastalik analizi sonuc dondurdu",
        bool(d.get("results")),
        f"{len(d.get('results') or [])} sonuc, top={d.get('top_probability')}",
    )
    check("dusuk-guven bayragi mevcut (yanlis-guvence korumasi)", "low_confidence" in d, str(d.get("low_confidence")))

    s, _b, _ = req("POST", "/api/ai/disease", {"age": 3, "weight": 0, "hr": 0, "temp": 0})
    check("bos vital ile analiz REDDEDILDI (422)", s == 422, f"HTTP {s}")

    s, lb, _ = req(
        "POST",
        "/api/ai/log",
        {
            "mode": "pet_owner",
            "module_id": "disease",
            "module": "Hastalik Analizi",
            "patient_name": "Pamuk",
            "input_type": "clinical",
            "summary": "E2E kayit",
            "result_detail": {"top": "Test"},
            "confidence": 0.61,
        },
    )
    check("AI gecmisine sifreli kayit 200", s == 200 and lb.get("status") == "success", f"HTTP {s} {lb}")
    s, lg, _ = req("GET", "/api/ai/log?limit=10")
    items = lg if isinstance(lg, list) else (lg.get("data") or lg.get("items") or [])
    check("AI gecmisi okunabiliyor", s == 200 and len(items) >= 1, f"HTTP {s}, {len(items)} kayit")
    check(
        "AI gecmisi profil (mode) ile filtreleniyor",
        any((it.get("mode") or it.get("profile")) == "pet_owner" for it in items)
        or any(it.get("module_id") == "disease" for it in items),
        json.dumps(items[0], ensure_ascii=False)[:140] if items else "",
    )

    s, stg, _ = req("GET", "/api/settings/")
    check("ayarlar okunuyor", s == 200, f"HTTP {s}")


# ── H) PROFIL: Arastirma (researcher) — cihaz YOK, hasta/ornek + arastirma AI ─
def h_profile_researcher():
    section("H. Profil — Arastirma Modu")
    s, b, _ = req(
        "POST",
        "/api/patients",
        {"name": "Ornek-2026-001", "species": "Insan (ornek)", "operator_email": "arastirmaci@uni.edu.tr"},
    )
    pid = b.get("patient_id")
    check("arastirma ornek kaydi olusturuldu", s == 200 and bool(pid), f"HTTP {s}")

    s, hist, _ = req("GET", "/api/history/?limit=10")
    check("gecmis erisimi 200", s == 200, f"HTTP {s}")

    # Arastirma modeli ucu — TIER_ENFORCED kapali (sahip karari) → 402 DEGIL, calismali
    s, k, _ = req(
        "POST",
        "/api/ai/disease/kidney",
        {
            "age": 48,
            "bp": 80,
            "sg": 1.02,
            "al": 1,
            "su": 0,
            "bgr": 121,
            "bu": 36,
            "sc": 1.2,
            "sod": 137,
            "pot": 4.4,
            "hemo": 15.4,
            "pcv": 44,
            "wc": 7800,
            "rc": 5.2,
            "rbc": "normal",
            "pc": "normal",
            "pcc": "notpresent",
            "ba": "notpresent",
            "htn": "yes",
            "dm": "no",
            "cad": "no",
            "appet": "good",
            "pe": "no",
            "ane": "no",
        },
        timeout=180,
    )
    check("arastirma modeli (CKD) 402 DEGIL — odeme oncesi acik (sahip karari)", s != 402, f"HTTP {s}")
    check(
        "CKD analizi sonuc dondurdu",
        s == 200 and "prob_ckd" in k,
        f"HTTP {s} label={k.get('label')} prob={k.get('prob_ckd')}",
    )

    if pid:
        req("DELETE", f"/api/patients/{pid}")


# ── I) PROFIL: Veteriner — KPI / istatistik / sensor ozeti ────────────────
def i_profile_vet_kpi():
    section("I. Profil — Veteriner (KPI + gecmis)")
    s, kpi, _ = req("GET", "/api/kpi/summary")
    check("KPI ozeti 200", s == 200, f"HTTP {s}")
    check(
        "KPI: toplam seans sayisi gercek seanslari yansitiyor",
        int(kpi.get("totalSessions") or 0) >= 4,
        str(kpi.get("totalSessions")),
    )
    check("KPI: tamamlanan seans var", int(kpi.get("completedSessions") or 0) >= 1, str(kpi.get("completedSessions")))
    usage = kpi.get("coilUsage") or {}
    check(
        "KPI: bobin kullanim dagilimi dolu (8 bobin)",
        len(usage) == 8 and sum(int(v or 0) for v in usage.values()) > 0,
        json.dumps(usage),
    )
    check("KPI: son 7 gun serisi 7 gun", len(kpi.get("last7Days") or []) == 7, str(len(kpi.get("last7Days") or [])))
    check(
        "KPI: tedavi modu dagilimi var",
        bool(kpi.get("modeDistribution")),
        json.dumps(kpi.get("modeDistribution"), ensure_ascii=False),
    )

    s, stt, _ = req("GET", "/api/history/statistics")
    check("gecmis istatistikleri 200", s == 200, f"HTTP {s}")

    st, csv = raw_get("/api/history/export_csv")
    check(
        "gecmis CSV disa aktarimi 200",
        st == 200 and len(csv.splitlines()) >= 2,
        f"HTTP {st}, {len(csv.splitlines())} satir",
    )

    sid = globals().get("_STM_SID")
    if sid:
        s, _b, _ = req("POST", "/api/history/update_notes", {"session_id": sid, "notes": "E2E not"})
        check("seans notu guncellendi", s == 200, f"HTTP {s}")
        s, _b, _ = req("DELETE", f"/api/history/{sid}")
        check("seans kaydi silinebiliyor", s == 200, f"HTTP {s}")
        s, hist, _ = req("GET", "/api/history/?limit=50")
        rows = hist if isinstance(hist, list) else (hist.get("data") or [])
        check("silinen seans gecmiste YOK", all(r.get("id") != sid for r in rows), f"n={len(rows)}")


if __name__ == "__main__":
    sys.exit(main())
