# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.E10 · 1-C bağımsız inceleme i6-F-1 — ESP `command_id` biçimleri × FIRMWARE ve açılış mutabakatı STOP'u.

Firmware DERLENMEZ (Ö.4-Y7: ESP kodu silinmez, değişmez — yalnız OKUNUR). Tampon boyutları ve kopya / kıyas / yankı /
tekrar-önbelleği mantığı C KAYNAĞINDAN okunur: aşağıdaki ÇAPALAR kaynakta birebir (boşluk esnek) aranır — firmware
değişirse kapı KIRMIZI olur, sessizce bayatlamaz. Aynı semantik (strlcpy / strncpy / strcmp) Python'da yeniden üretilir.

i6-F-1 (ölçüldü): backend'in çökme-kurtarma STOP'u (`backend_service._start_startup_reconcile`) SABİT kimlik
`startup_reconcile_{bobin}` kullanıyordu. 8266 tekrar önbelleği (8 girdilik halka, yalnız ESP açılışında sıfırlanır) aynı
kimlikli STOP'u UYGULAMAZ, yalnız ACK(success=true) yeniden gönderir → önceki süreç seans ortasında öldüyse (taskkill /F)
yeni sürecin açılış STOP'u yutulur, bobin ENERJİLİ kalır, firmware "durdu" ACK'i döner (araya ≤7 komut girdiyse).
DÜZELTME: açılış kimliği süreç başına benzersiz (`startup_reconcile_{bobin}_{ms}`; ≤ S3 sınırı).

⚠️ Y48 (sahip, 1-G): 8266 artık aynı kimlikli STOP'u YENİDEN UYGULAR (STOP idempotent; firmware değişti — kod silinmedi,
yakma ESP dönüşünde). Çapa ve model buna göre güncellendi; davranış GERÇEK kaynaktan kesilen aparatla da ölçülür
(`test_esp8266_ayni_kimlikli_STOP_YENIDEN_uygulanir_Y48.py`). Benzersiz açılış kimliği (i6-F-1) yine doğru ve korunur.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time as _time
import types
from pathlib import Path

import pytest
from topoloji import ESP_BOBIN

KOK = Path(__file__).resolve().parents[1]
FW8266 = KOK / "firmware" / "esp8266_pemf_coil"
FWS3 = KOK / "firmware" / "esps3_pemf_coil"
BACKEND = KOK / "apps" / "backend"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _tek(desen: str, metin: str, ad: str, bayrak=0):
    m = re.findall(desen, metin, bayrak)
    assert len(m) == 1, f"CAPA '{ad}': {len(m)} eslesme (firmware/backend degismis olabilir)"
    return m[0]


# ── FIRMWARE CAPALARI (yalniz OKUNUR) ───────────────────────────────────────────────────────────────────────────
_8266_CAPALARI = {
    # isCommandProcessed: bos kimlik islenmemis sayilir; 8 girdinin her biri strcmp ile TAM kiyaslanir.
    "isCommandProcessed": r"bool isCommandProcessed\(const char\* command_id\) \{\s*if \(strlen\(command_id\) == 0\) \{\s*"
    r"return false;\s*\}\s*for \(int i = 0; i < CMD_CACHE_SIZE; i\+\+\) \{\s*if \(strcmp\(commandIdCache\[i\], command_id\) == 0\) \{\s*"
    r"return true;",
    # addCommandToCache: bos kimlik eklenmez; strlcpy(…, sizeof(commandIdCache[0])) = 47 karakter + NUL; halka.
    "addCommandToCache": r"void addCommandToCache\(const char\* command_id\) \{\s*if \(strlen\(command_id\) == 0\) return;\s*"
    r"strlcpy\(commandIdCache\[cacheIndex\], command_id, sizeof\(commandIdCache\[0\]\)\);\s*"
    r"cacheIndex = \(cacheIndex \+ 1\) % CMD_CACHE_SIZE;",
    # gelen kimlik static char command_id[64]'e strlcpy edilir.
    "kimlik_kopya": r"const char\* cmdIdStr = doc\[\"command_id\"\] \| \"\";\s*strlcpy\(command_id, cmdIdStr, sizeof\(command_id\)\);\s*"
    r"const bool isStop = \(strcmp\(command, \"stop\"\) == 0\);",
    # TEKRAR (Y48): STOP dışı tekrar sessizce YUTULUR (dönülür); STOP tekrarı aşağıdaki NORMAL yoldan YENİDEN uygulanır;
    # yeni kimlik önbelleğe eklenir, tekrar EKLENMEZ.
    "tekrar_dali": r"if \(isCommandProcessed\(command_id\)\) \{\s*LOG_PRINTF\(\"\[CMD\] Duplicate command: %s\\n\", command_id\);\s*"
    r"if \(!isStop\) \{\s*return;\s*\}\s*\} else \{\s*addCommandToCache\(command_id\);\s*\}",
    # STOP'un bobini durduran dali (tekrar dalindan SONRA gelir).
    "stop_dali": r"\} else if \(strcmp\(command, \"stop\"\) == 0\) \{\s*if \(coil\) \{\s*ControlCommand cmd;\s*"
    r"cmd\.type = CMD_STOP;\s*coil->handleCommand\(cmd\);",
    # hiz siniri STOP'a uygulanmaz; onbellege ekleme hiz denetiminden ONCE.
    "hiz_siniri": r"if \(!isStop && !commandRateLimiter\.allowCommand\(command\)\) \{",
}
_S3_CAPALARI = {
    # S3: 1..35 karakter kopyalanir, >=36 → kimlik BOSALTILIR (komut yine kuyruga girer, ACK gitmez).
    "s3_kimlik": r"if \(strlen\(cmd_id\) > 0 && strlen\(cmd_id\) < 36\) \{\s*strncpy\(cmd\.command_id, cmd_id, 35\);\s*"
    r"cmd\.command_id\[35\] = '\\0';\s*\} else \{\s*cmd\.command_id\[0\] = '\\0';\s*\}\s*"
    r"// Komutu kuyru[^\n]*\n\s*BaseType_t qResult = xQueueSend\(commandQueue, &cmd, 0\);",
}


def _capalari_dogrula() -> dict:
    ino = _oku(FW8266 / "esp8266_pemf_coil.ino")
    nm_s3 = _oku(FWS3 / "NetworkManager.cpp")
    yer = {}
    for ad, desen in _8266_CAPALARI.items():
        m = list(re.finditer(desen, ino))
        assert len(m) == 1, f"8266 capasi '{ad}' {len(m)} kez eslesti — model kaynakla UYUSMUYOR"
        yer[ad] = m[0].start()
    assert yer["tekrar_dali"] < yer["hiz_siniri"] < yer["stop_dali"], "8266 siralama capasi: tekrar → hiz → stop"
    for ad, desen in _S3_CAPALARI.items():
        m = list(re.finditer(desen, nm_s3))
        assert len(m) == 1, f"S3 capasi '{ad}' {len(m)} kez eslesti"
    return yer


def firmware_sabitleri() -> dict:
    ino = _oku(FW8266 / "esp8266_pemf_coil.ino")
    nm8 = _oku(FW8266 / "NetworkManager.cpp")
    nm8h = _oku(FW8266 / "NetworkManager.h")
    nm_s3 = _oku(FWS3 / "NetworkManager.cpp")
    sd_s3 = _oku(FWS3 / "SharedDefs.h")
    ino_s3 = _oku(FWS3 / "esps3_pemf_coil.ino")
    s = {
        "e8266_id_tampon": int(_tek(r"static char command_id\[(\d+)\];", ino, "8266 command_id[]")),
        "e8266_komut_tampon": int(_tek(r"static char command\[(\d+)\];", ino, "8266 command[]")),
        "e8266_onbellek_say": int(_tek(r"const int CMD_CACHE_SIZE = (\d+);", ino, "CMD_CACHE_SIZE")),
        "e8266_onbellek_tampon": int(_tek(r"static char commandIdCache\[CMD_CACHE_SIZE\]\[(\d+)\];", ino, "cache[]")),
        "e8266_payload_tampon": int(_tek(r"static const size_t MQTT_PAYLOAD_SIZE = (\d+);", nm8h, "MQTT_PAYLOAD_SIZE")),
        "e8266_json_doc": int(_tek(r"static StaticJsonDocument<(\d+)> jsonDoc;", ino, "jsonDoc")),
        "s3_sinir": int(_tek(r"strlen\(cmd_id\) > 0 && strlen\(cmd_id\) < (\d+)\)", nm_s3, "S3 strlen<")),
        "s3_id_tampon": int(_tek(r"char command_id\[(\d+)\];", sd_s3, "S3 command_id[]")),
        "s3_ack_tampon": int(_tek(r"char ack_cmd_id\[(\d+)\];", sd_s3, "S3 ack_cmd_id[]")),
        "s3_ack_kopya": int(_tek(r"strncpy\(ackMsg\.ack_cmd_id, cmd\.command_id, (\d+)\);", ino_s3, "S3 ack strncpy")),
    }
    govde = nm8[nm8.index("void NetworkManager::sendCommandAck") :]
    govde = govde[: govde.index("\n}\n")]
    s["e8266_ack_tampon"] = int(_tek(r"static char jsonBuffer\[(\d+)\];", govde, "8266 ack jsonBuffer"))
    s["e8266_ack_bicim"] = _tek(r'PSTR\("(\{.*?\})"\)', govde, "8266 ack bicim", re.S).replace('\\"', '"')
    return s


def _strlcpy(metin: str, boyut: int) -> str:
    return metin[: max(0, boyut - 1)]


class Esp8266Modeli:
    """`processControlCommand` (esp8266_pemf_coil.ino) — kimlik kopyasi, tekrar onbellegi, hiz siniri, start/stop
    ve ACK. Termal kilit / aralik dogrulamasi bu olcumlerin senaryosunda tetiklenmez (backend gecerli deger yollar)."""

    def __init__(self, sab: dict):
        self.sab = sab
        self.onbellek = [""] * sab["e8266_onbellek_say"]  # static → acilista sifir (ESP YENIDEN BASLAYINCA bosalir)
        self.indeks = 0
        self.aktif = False
        self.acklar: list = []
        self.uygulanan: list = []
        self.yutulan: list = []
        self.dusen: list = []
        self._hiz: list = []

    def _islendi_mi(self, cid: str) -> bool:
        return len(cid) > 0 and any(e == cid for e in self.onbellek)

    def _ekle(self, cid: str) -> None:
        if not cid:
            return
        self.onbellek[self.indeks] = _strlcpy(cid, self.sab["e8266_onbellek_tampon"])
        self.indeks = (self.indeks + 1) % self.sab["e8266_onbellek_say"]

    def _hiz_izni(self, komut: str, t_ms: float) -> bool:
        ayni = sum(1 for (t, k) in self._hiz if t_ms - t < 10000 and k == komut)
        if ayni >= 5:
            return False
        if len(self._hiz) >= 20:
            self._hiz.pop(0)
        self._hiz.append((t_ms, komut))
        return True

    def mesaj(self, yuk: str, t_ms: float = 0.0) -> None:
        ham = yuk.encode("utf-8")
        if len(ham) >= self.sab["e8266_payload_tampon"]:  # _mqttCallbackHelper KIRPAR → yarim JSON
            ham = ham[: self.sab["e8266_payload_tampon"] - 1]
        try:
            doc = json.loads(ham.decode("utf-8", errors="ignore"))
        except ValueError:
            self.dusen.append(yuk)
            return
        komut = _strlcpy(str(doc.get("command", "")), self.sab["e8266_komut_tampon"])
        cid = _strlcpy(str(doc.get("command_id", "")), self.sab["e8266_id_tampon"])
        dur = komut == "stop"
        if self._islendi_mi(cid):
            if not dur:
                self.yutulan.append((komut, cid))
                return
            # Y48: aynı kimlikli STOP aşağıdaki NORMAL yoldan YENİDEN uygulanır; önbelleğe yeniden eklenmez
        else:
            self._ekle(cid)
        if not dur and not self._hiz_izni(komut, t_ms):
            if cid:
                self.acklar.append((cid, False))
            return
        if komut == "start":
            duty = doc.get("duty")
            if duty is not None and float(duty) < 1.0:
                self.aktif = False
                self.uygulanan.append(("stop(duty<1)", cid))
                if cid:
                    self.acklar.append((cid, True))
                return
            self.aktif = True
            basari = True
        elif dur:
            self.aktif = False
            basari = True
        else:
            if cid:
                self.acklar.append((cid, False))
            return
        self.uygulanan.append((komut, cid))
        if cid:
            self.acklar.append((cid, basari))


def s3_kimlik(cid: str, sab: dict) -> str:
    """S3 `_processIncomingCommand`: 1..(sinir-1) karakter → aynen; aksi → BOS (komut yine islenir, ACK GITMEZ)."""
    return cid[: sab["s3_sinir"] - 1] if 0 < len(cid) < sab["s3_sinir"] else ""


# ── BACKEND KIMLIK BICIMLERI (kaynaktan; eksik bicim kalirsa KIRMIZI) ────────────────────────────────────────────
_MS = "9" * 13  # 13 haneli epoch-ms (2286'ya kadar)
_BICIMLER = [
    (
        "apps/backend/servers/api_server.py",
        "{on_ek}_{coil_id}_{int(time.time() * 1000)}_{next(_komut_sira) % 1_000_000}",
    ),
    ("apps/backend/servers/api_server.py", "estop_{coil_id}_{int(_t.time() * 1000)}_{next(_estop_sira)}"),
    ("apps/backend/servers/api_server.py", "stale_{cid}_{int(time.time() * 1000)}"),
    ("apps/backend/servers/api_server.py", "{id_prefix}_{i}_{int(time.time() * 1000)}"),
    ("apps/backend/servers/api_server.py", "reconcile_{coil_id}_{int(time.time() * 1000)}"),
    ("apps/backend/servers/api_server.py", "estopcloud_{cid}_{int(time.time() * 1000)}"),
    ("apps/backend/servers/api_server.py", "stop_{coil_id}_{int(_t.time() * 1000)}"),
    # D1.83/D1.84 (1-D): `aipro_` START'ı kalktı (6-7 STM'e); `ai_stop_` artık `_komut_kimligi("ai_stop", …)` (sıra ekli).
    ("apps/backend/backend_service.py", "service_stop_{coil_id}_{int(time.time() * 1000)}"),
    ("apps/backend/backend_service.py", "startup_reconcile_{_cid}_{int(_t.time() * 1000)}"),
]
_ID_SATIRI = re.compile(r'(command_id|komut_id|cid = f|return f"\{on_ek\})')


def _kaynak_bicimlerini_topla() -> tuple[set, set, set]:
    """(f-dize kimlik sablonlari, _komut_kimligi on ekleri, _esp_control_broadcast on ekleri)."""
    sablonlar, on_ekler, yayin_ekleri = set(), set(), set()
    for p in sorted(BACKEND.rglob("*.py")):
        metin = _oku(p)
        for satir in metin.splitlines():
            if not _ID_SATIRI.search(satir):
                continue
            for m in re.finditer(r'f"([^"\n]*)"', satir):
                ic = m.group(1)
                if "/" in ic or "." in ic.replace("time.time", "").replace("_t.time", ""):
                    continue  # konu adi / dosya adi
                if "{" in ic and ("time() * 1000)" in ic or ic.startswith("startup_reconcile_")):
                    sablonlar.add((str(p.relative_to(KOK)).replace("\\", "/"), ic))
        on_ekler |= set(re.findall(r'_komut_kimligi\("([A-Za-z_]+)"', metin))
        yayin_ekleri |= set(re.findall(r'_esp_control_broadcast\("[A-Za-z_]+", "([A-Za-z_]+)"\)', metin))
    return sablonlar, on_ekler, yayin_ekleri


def _en_uzun(sablon: str, on_ek: str = "", bobin: int = 8, sira_hane: int = 6) -> str:
    s = sablon
    s = s.replace("{on_ek}", on_ek).replace("{id_prefix}", on_ek)
    for yer in ("{coil_id}", "{cid}", "{_cid}", "{i}"):
        s = s.replace(yer, str(bobin))
    s = s.replace("{int(time.time() * 1000)}", _MS).replace("{int(_t.time() * 1000)}", _MS)
    s = s.replace("{next(_komut_sira) % 1_000_000}", "9" * 6)
    s = s.replace("{next(_estop_sira)}", "9" * sira_hane)
    assert "{" not in s, f"cozulmemis yer tutucu: {s}"
    return s


def test_KRITIK_TUM_kimlik_bicimleri_FIRMWARE_tamponlarina_sigar_ve_ACK_yankisi_AYNIDIR():
    """MERCEK 1 — her bicimin EN UZUN degeri x 8266 (command_id[64], onbellek[48], ACK json[256]) x S3 (<36)."""
    _capalari_dogrula()
    sab = firmware_sabitleri()
    bulunan, on_ekler, yayin_ekleri = _kaynak_bicimlerini_topla()
    beklenen = set(_BICIMLER)
    assert bulunan == beklenen, f"kaynakta LISTEDE OLMAYAN/eksik kimlik bicimi: {sorted(bulunan ^ beklenen)}"
    assert on_ekler == {"react", "react_batch", "sess", "telafi", "stop", "ai_stop"}, on_ekler
    assert yayin_ekleri == {"selftest", "reset"}, yayin_ekleri

    from servers.live_state import ESP_COIL_IDS, STM_COIL_IDS

    en_buyuk_bobin = max(set(range(1, 9)) | set(ESP_COIL_IDS) | set(STM_COIL_IDS))
    satirlar, sorunlar = [], []
    for dosya, sablon in sorted(_BICIMLER):
        ekler = [""]
        if sablon.startswith("{on_ek}"):
            ekler = sorted(on_ekler)
        elif sablon.startswith("{id_prefix}"):
            ekler = sorted(yayin_ekleri)
        for ek in ekler:
            cid = _en_uzun(sablon, ek, en_buyuk_bobin, sira_hane=9)
            e8266 = _strlcpy(cid, sab["e8266_id_tampon"])
            onbellek_etkin = len(e8266) <= sab["e8266_onbellek_tampon"] - 1
            ack_json = (
                sab["e8266_ack_bicim"]
                .replace("%d", str(en_buyuk_bobin), 1)
                .replace("%s", e8266, 1)
                .replace("%s", "false", 1)
                .replace("%lu", "4294967295", 1)
            )
            s3 = s3_kimlik(cid, sab)
            satir = (
                f"{len(cid):>3} | {cid:<40} | 8266 kopya={'AYNI' if e8266 == cid else 'KESILDI'} "
                f"onbellek={'ETKIN' if onbellek_etkin else 'KOR'} ack_json={len(ack_json)}/{sab['e8266_ack_tampon']} "
                f"| S3={'AYNI' if s3 == cid else 'BOSALTILDI (ACK YOK)'} | {dosya}"
            )
            satirlar.append(satir)
            if e8266 != cid or not onbellek_etkin or len(ack_json) >= sab["e8266_ack_tampon"] or s3 != cid:
                sorunlar.append(satir)
    # E-stop sira ekinin S3'u asacagi hane sayisi (mod'suz sayac)
    taban = len(_en_uzun("estop_{coil_id}_{int(_t.time() * 1000)}_{next(_estop_sira)}", "", en_buyuk_bobin, 0))
    estop_esik_hane = (sab["s3_sinir"] - 1) - taban  # S3 en cok s3_sinir-1 karakter kabul eder → bu kadar hane sigar
    # START yuku boyutu (8266 MQTT_PAYLOAD_SIZE kirpmasi): en kotu sayi gosterimi 24 karakter
    en_kotu_sayi = -1.7976931348623157e308
    yukler = {}
    for ek in ("react", "react_batch", "sess"):
        yuk = {
            "command": "start",
            "command_id": _en_uzun("{on_ek}_{coil_id}_{int(time.time() * 1000)}_{next(_komut_sira) % 1_000_000}", ek),
            "freq": en_kotu_sayi,
            "duty": en_kotu_sayi,
            "phase": en_kotu_sayi,
            "duration": 9999999999,
        }
        yukler[ek] = len(json.dumps(yuk))
    # D1.83/D1.84: AI Pro artık ESP START yayınlamaz (`aipro_` yükü yok).
    # ArduinoJson 6 havuzu (ESP8266: slot 16 bayt; const char* girdi → anahtar+deger dizeleri kopyalanir)
    en_uzun_start = _en_uzun(
        "{on_ek}_{coil_id}_{int(time.time() * 1000)}_{next(_komut_sira) % 1_000_000}", "react_batch"
    )
    havuz = 6 * 16 + sum(len(k) + 1 for k in ("command", "command_id", "freq", "duty", "phase", "duration"))
    havuz += len("start") + 1 + len(en_uzun_start) + 1

    assert not sorunlar, "SIGMAYAN / KESILEN / ACK'SIZ kalan kimlik:\n" + "\n".join(sorunlar)
    assert estop_esik_hane >= 10
    assert max(yukler.values()) < sab["e8266_payload_tampon"], yukler
    assert havuz <= sab["e8266_json_doc"], havuz


# ── MERCEK 2 — ACILIS MUTABAKATI (backend_service) x 8266 TEKRAR ONBELLEGI ──────────────────────────────────────


def _surec_acilisi(bs, yayin) -> list:
    """GERCEK `backend_service._start_startup_reconcile` — yeni bir backend surecinin acilisi (3 sn uykusu dahil).
    Sahte api_server: aktif seans yok, STM yok; `_mqtt_publish` = olcum kancasi (ag yok)."""
    sahte = types.SimpleNamespace(
        _session_lock=threading.Lock(),
        _active_session={"is_active": False},
        state=types.SimpleNamespace(hardware=None),
        _mqtt_publish=yayin,
    )
    once = {t.ident for t in threading.enumerate()}
    bs._start_startup_reconcile(sahte, logging.getLogger("kapi_i6"))
    yeni = [t for t in threading.enumerate() if t.name == "startup-reconcile" and t.ident not in once]
    assert len(yeni) == 1, "aparat: startup-reconcile is parcacigi bulunamadi"
    yeni[0].join(timeout=8.0)
    assert not yeni[0].is_alive(), "aparat: startup-reconcile 8 sn'de bitmedi"
    return yeni


@pytest.fixture()
def esp_ortami(monkeypatch):
    import servers.api_server as api
    from servers import coil_run_tracker as crt

    monkeypatch.setenv("PEMF_ESP_ENABLED", "1")
    monkeypatch.setattr(api, "_push_notification", lambda msg, sev="info": None)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda m: None)
    monkeypatch.setattr(api, "_reconcile_esp_calisiyor", lambda *a, **k: None)
    monkeypatch.setattr(api, "_RL_REMOTE_MAX", 0, raising=True)
    monkeypatch.setattr(crt, "_db_session_id_getter", lambda: None)
    _capalari_dogrula()
    esp = Esp8266Modeli(firmware_sabitleri())
    iz: list = []

    def _yayin(topic, payload):
        iz.append((topic, dict(payload)))
        m = re.fullmatch(r"pemf/coil/(\d+)/control", topic)
        if m and int(m.group(1)) == int(ESP_BOBIN):
            esp.mesaj(json.dumps(payload), _time.monotonic() * 1000.0)
        return True

    monkeypatch.setattr(api, "_mqtt_publish", _yayin)
    yield api, esp, iz, _yayin
    with api._session_lock:
        api._active_session["is_active"] = False


def test_KRITIK_i6F1_ikinci_ACILIS_mutabakati_STOP_u_8266_tekrar_onbelleginde_YUTULMAZ(esp_ortami):
    """Olcum: surec#1 acilisi → (bobine 1 START) → surec#1 COKER (taskkill /F: `_safe_stop_outputs` kosmaz) →
    surec#2 acilisi. Acilis mutabakatinin TEK isi tam bu durumda kosan ESP bobinini durdurmaktir (audit #15).
    Kimlik eskiden `startup_reconcile_{bobin}` SABİTti → 8266 önbelleğindeyse STOP UYGULANMAZ ama ACK(true) gider;
    düzeltmeyle süreç başına benzersiz (ms eki) → ikinci açılışın STOP'u uygulanır."""
    import backend_service as bs
    from fastapi.testclient import TestClient

    api, esp, iz, yayin = esp_ortami
    _surec_acilisi(bs, yayin)  # surec#1
    on_ek = f"startup_reconcile_{ESP_BOBIN}"
    assert esp.aktif is False and any(k == "stop" and c.startswith(on_ek) for k, c in esp.uygulanan)
    c = TestClient(api.app)
    r = c.post(
        f"/api/coil/{ESP_BOBIN}/control", json={"start": True, "freq": 100, "duty": 50, "phase": 0, "duration": 600}
    )
    assert r.status_code == 200, r.text[:200]
    api._resolve_ack(r.json()["command_id"], True)
    assert esp.aktif is True, "aparat: START modele ulasmadi"
    # surec#1 coker (STOP gonderilmez), surec#2 acilir:
    yutulan_once = len(esp.yutulan)
    _surec_acilisi(bs, yayin)
    yutulan = esp.yutulan[yutulan_once:]
    son_ack = [a for a in esp.acklar if a[0].startswith(on_ek)]
    assert esp.aktif is False, (
        f"surec#2 acilis mutabakati STOP'u 8266 tekrar onbelleginde YUTULDU (uygulanmadi) — bobin ENERJILI kaldi; "
        f"firmware buna ACK(success=true) dondu: yutulan={yutulan}, ack={son_ack[-1:]}"
    )


@pytest.mark.parametrize("araya_giren", [1, 4, 7, 8])
def test_KRITIK_i6F1_acilis_STOP_u_ARAYA_GIREN_KOMUT_SAYISINDAN_bagimsiz_UYGULANIR(esp_ortami, araya_giren):
    """Kapsam olcumu (model + GERCEK `_komut_kimligi` kimlikleri): iki acilis arasinda k komut. Onbellek 8 girdilik
    halka → k <= 7 ise ikinci acilis STOP'u yutulur. (k=8 KARSIT KANIT: model STOP'u UYGULAR — model korce kirmizi
    vermez.) Sonuc `.inceleme/kayit/mercek2_k_tarama.txt`e eklenir."""
    import backend_service as bs

    api, esp, iz, yayin = esp_ortami
    _surec_acilisi(bs, yayin)
    for n in range(araya_giren):
        cid = api._komut_kimligi("react", int(ESP_BOBIN))
        esp.mesaj(
            json.dumps({"command": "start", "command_id": cid, "freq": 100, "duty": 50, "duration": 60}), n * 3000.0
        )
    assert esp.aktif is True
    _surec_acilisi(bs, yayin)
    if araya_giren >= 8:
        assert esp.aktif is False  # karsit kanit: girdi halkadan dustu → STOP uygulandi
    else:
        assert esp.aktif is False, f"k={araya_giren}: acilis STOP'u YUTULDU (bobin enerjili, ACK true)"
