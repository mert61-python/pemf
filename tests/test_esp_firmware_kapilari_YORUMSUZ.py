# Author: mertaygn, cglrgrkn
"""D1.48 · B-10.122 · B-10.154 · B-10.156 — ESP (8266/S3) firmware kapıları YORUMU SOYULMUŞ kaynakta, tam ifade
ve sabit paritesiyle.

ESP devre dışı ve sökülü ama kod ÖLÜ DEĞİL (Ö.4-Y7: silinmez); ESP dönerse mevcut korumalar kapısız kalmamalı.
⚠️ Y40 (sahip, 2026-10-01): 8266'nın (bobin 8) firmware'indeki **100 °C** termal kesme KALIR; A-47'nin "termal
kesme yok" kararı yalnız STM bobin 1–7 içindir. Bu dosya o eşiği KİLİTLER; YENİ termal kesme EKLENMEZ.

ÖLÇÜLEN KÖRLÜK (plan; kör mutantlar bugün yeşil):
  (a) `esp8266_pemf_coil.ino` termal karşılaştırmasının sağ tarafı sabit sayıya çevrilse (`>= 200.0f`), `#define`
      yoruma alınıp başka bir değer yazılsa, mesaja `(>48°C)` gibi sabit sayı konsa (°C biçimi tanınmıyordu);
  (b) Plan-A süreli durma `>= _duration * 2` (alt-dize araması önekle eşleşiyordu); 8266 PWM yoluna WiFi/MQTT
      durumuna bağlı bir `stop()` eklense (yalnız YORUM aranıyordu);
  (c) S3 DC-yapışma: `SYNC_MISMATCH_STREAK` 8→200 ya da `tol = tpp/50` → `tpp/2` (Python modeli sabitleri ELLE
      kopyalıyordu).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
E8 = KOK / "firmware" / "esp8266_pemf_coil"
S3 = KOK / "firmware" / "esps3_pemf_coil"

#: Y40 — sahibin 8266 termal kesme eşiği (°C). Değiştirilecekse BİLİNÇLİ ve sahip kararıyla.
Y40_KESME_C = 100.0


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def sabit_degeri(kaynak: str, ad: str) -> float | None:
    """`#define AD <sayı>[f|U]` — YORUMU SOYULMUŞ metinden (yorumdaki eski/kopya tanım sayılmaz)."""
    m = re.search(rf"^\s*#define\s+{ad}\s+([0-9]+(?:\.[0-9]+)?)[fFuU]?\b", c_soy(kaynak), re.M)
    return float(m.group(1)) if m else None


#: '48C', '100 C', '>=48°C', '(>48 °C)' — sıcaklık gibi görünen SABİT sayı (biçim belirteci değil).
SICAKLIK_SAYISI = re.compile(r"[0-9]{2,3}\s?(?:°\s?)?C(?![a-zA-Z0-9_])")


def _dize_sabitleri(kaynak: str) -> list[str]:
    return re.findall(r'"((?:[^"\\]|\\.)*)"', c_soy(kaynak))


# ── (a) 8266 termal ─────────────────────────────────────────────────────────


def termal_denetle(ino: str, shared: str) -> None:
    assert sabit_degeri(shared, "TERMAL_KESME_C") == Y40_KESME_C, (
        f"TERMAL_KESME_C (yorum dışı) {sabit_degeri(shared, 'TERMAL_KESME_C')} — Y40: 8266 eşiği {Y40_KESME_C} °C KALIR"
    )
    soy = c_soy(ino)
    assert re.search(r"if\s*\(\s*td\.tempObject\s*>=\s*TERMAL_KESME_C\s*\)", soy), (
        "termal karşılaştırmanın sağ tarafı TERMAL_KESME_C sembolü değil (sabit sayı ya da yorumda)"
    )
    sabitli = [t for t in _dize_sabitleri(ino) if SICAKLIK_SAYISI.search(t)]
    assert sabitli == [], f"mesajda SABİT sıcaklık sayısı (eşik sabitinden türemeli): {sabitli}"


def test_KRITIK_a_8266_termal_esik_Y40_SEMBOLLE_ve_mesajlar_TURETILMIS():
    termal_denetle(_oku(E8 / "esp8266_pemf_coil.ino"), _oku(E8 / "SharedDefs.h"))


# ── (b) süreli durma ve ağdan bağımsızlık ───────────────────────────────────


#: Bağlantı DURUMU belirteçleri (mesaj içeriği değil): bunlara koşullu bir dal bobini durdurmamalı.
_AG_DURUMU = re.compile(r"\bWiFi\b|\bwifi\w*|\bmqtt\w*|\bMqtt\w*|\bisConnected\b|\bconnected\s*\(")
_DURDURMA = re.compile(r"\bstop\s*\(|\bCMD_STOP\b")


def _eslesen_kapanis(s: str, i: int, ac: str, kapa: str) -> int:
    """s[i] == ac → eşleşen kapa'nın indeksi (yorumu soyulmuş metin; dize içi parantez ayrıştırmayı bozmaz sayılır)."""
    d = 0
    for j in range(i, len(s)):
        if s[j] == ac:
            d += 1
        elif s[j] == kapa:
            d -= 1
            if d == 0:
                return j
    return len(s) - 1


def ag_kosullu_durdurmalar(soy: str) -> list[str]:
    """`if (<ağ durumu>) <gövde>` — gövde (küme ya da tek deyim) bobini durduruyorsa koşulu döndürür."""
    bulunan = []
    for m in re.finditer(r"\bif\s*\(", soy):
        ac = m.end() - 1
        kapa = _eslesen_kapanis(soy, ac, "(", ")")
        kosul = soy[ac + 1 : kapa]
        if not _AG_DURUMU.search(kosul):
            continue
        k = kapa + 1
        while k < len(soy) and soy[k].isspace():
            k += 1
        govde = (
            soy[k : _eslesen_kapanis(soy, k, "{", "}") + 1] if soy[k : k + 1] == "{" else soy[k : soy.find(";", k) + 1]
        )
        if _DURDURMA.search(govde):
            bulunan.append(" ".join(kosul.split()))
    return bulunan


def sureli_denetle(s3: str, e8: str, e8_ino: str) -> None:
    s3s, e8s = c_soy(s3), c_soy(e8)
    assert re.search(
        r"if\s*\(\s*_active\s*&&\s*_hasDuration\s*&&\s*\(\s*millis\(\)\s*-\s*_startTime\s*\)\s*>=\s*_duration\s*\)", s3s
    ), "S3 süreli dal tam ifadesi (wrap-güvenli fark ≥ _duration) yok"
    assert re.search(
        r"if\s*\(\s*safeMillisDiff\(\s*millis\(\)\s*,\s*_pwmStartTime\s*\)\s*>=\s*_pwmDuration\s*\)", e8s
    ), "8266 süreli dal tam ifadesi yok"
    ag_bagli = ag_kosullu_durdurmalar(e8s) + ag_kosullu_durdurmalar(c_soy(e8_ino))
    assert ag_bagli == [], (
        f"8266 PWM yolunda AĞ durumuna bağlı durdurma var (ağ kopunca seans yarıda kalır): {ag_bagli}"
    )


def test_KRITIK_b_sureli_durma_TAM_ifade_ve_8266_PWM_agdan_BAGIMSIZ():
    sureli_denetle(_oku(S3 / "CoilController.cpp"), _oku(E8 / "CoilController.cpp"), _oku(E8 / "esp8266_pemf_coil.ino"))


def test_KARSIT_b_ag_kosulu_TESPIT_eder_ama_komut_kaynakli_stopa_KARISMAZ():
    assert ag_kosullu_durdurmalar("if (!WiFi.isConnected()) coil->stop();") == ["!WiFi.isConnected()"]
    assert ag_kosullu_durdurmalar("if (!mqttClient.connected()) { x = 1; if (coil) { c.type = CMD_STOP; } }") != []
    assert ag_kosullu_durdurmalar('if (strcmp(command, "stop") == 0) { coil->stop(); }') == []
    assert ag_kosullu_durdurmalar("if (WiFi.status() == WL_CONNECTED) { publish(); }") == []


# ── (c) S3 DC-yapışma sabit paritesi ────────────────────────────────────────


def s3_parite_denetle(s3: str) -> None:
    """C sabitleri ↔ `test_s3_sync_dc_yapisma` modeli. Model ayrışırsa DC-yapışma davranış testleri C'yi değil
    kendi kopyasını sınar (ölçülen körlük: STREAK 8→200 ve tol tpp/50→tpp/2 bugün yeşil)."""
    import test_s3_sync_dc_yapisma as model

    streak = sabit_degeri(s3, "SYNC_MISMATCH_STREAK")
    assert streak == model.STREAK, f"C SYNC_MISMATCH_STREAK={streak} ≠ model {model.STREAK}"
    m = re.search(r"uint32_t\s+tol\s*=\s*tpp\s*/\s*(\d+)U?\s*\+\s*(\d+)U?\s*;", c_soy(s3))
    assert m, "S3 tol ifadesi (yorum dışı) bulunamadı"
    c_tol = (int(m.group(1)), int(m.group(2)))
    mm = re.search(r"tol\s*=\s*self\.tpp\s*//\s*(\d+)\s*\+\s*(\d+)", inspect.getsource(model._SyncModel))
    assert mm, "model tol ifadesi bulunamadı"
    assert (int(mm.group(1)), int(mm.group(2))) == c_tol, (
        f"C tol = tpp/{c_tol[0]}+{c_tol[1]} ≠ model tpp//{mm.group(1)}+{mm.group(2)}"
    )


def test_KRITIK_c_S3_DC_yapisma_sabitleri_C_ile_MODEL_AYNI():
    s3_parite_denetle(_oku(S3 / "CoilController.cpp"))


# ── öz-denetim: bellek içi mutantlar ────────────────────────────────────────

_INO = E8 / "esp8266_pemf_coil.ino"
_SHARED = E8 / "SharedDefs.h"


@pytest.mark.parametrize(
    ("ad", "dosya", "eski", "yeni"),
    [
        ("termal_SABIT_SAYI", "ino", "if (td.tempObject >= TERMAL_KESME_C) {", "if (td.tempObject >= 200.0f) {"),
        (
            "define_YORUMDA_baska_deger",
            "shared",
            "#define TERMAL_KESME_C   100.0f",
            "// #define TERMAL_KESME_C   100.0f\n#define TERMAL_KESME_C   120.0f",
        ),
        (
            "mesaj_SABIT_derece",
            "ino",
            '"Start reddedildi: bobin sicak (>=%.0fC), sogumasi bekleniyor"',
            '"Start reddedildi: bobin sicak (>48°C)"',
        ),
    ],
)
def test_ARAC_a_termal_denetleyici_mutantta_KIRMIZI(ad, dosya, eski, yeni):
    ino, shared = _oku(_INO), _oku(_SHARED)
    hedef = ino if dosya == "ino" else shared
    assert hedef.count(eski) == 1, f"çapa {hedef.count(eski)} kez"
    hedef = hedef.replace(eski, yeni)
    with pytest.raises(AssertionError):
        termal_denetle(hedef if dosya == "ino" else ino, hedef if dosya == "shared" else shared)


@pytest.mark.parametrize(
    ("ad", "dosya", "eski", "yeni"),
    [
        ("S3_IKI_KAT_sure", "s3", "(millis() - _startTime) >= _duration)", "(millis() - _startTime) >= _duration * 2)"),
        ("8266_IKI_KAT_sure", "e8", "_pwmStartTime) >= _pwmDuration)", "_pwmStartTime) >= _pwmDuration * 2)"),
        (
            "8266_AG_BAGLI_stop",
            "e8",
            "void CoilController::_checkPWMDuration() {",
            "void CoilController::_checkPWMDuration() {\n    if (!WiFi.isConnected()) { stop(); return; }",
        ),
        (
            "8266_ino_MQTT_kopunca_CMD_STOP",
            "ino",
            "void cleanup() {",
            "void agBekci() {\n    if (!network->isConnected()) {\n        ControlCommand c; c.type = CMD_STOP; coil->handleCommand(c);\n    }\n}\n\nvoid cleanup() {",
        ),
    ],
)
def test_ARAC_b_sureli_denetleyici_mutantta_KIRMIZI(ad, dosya, eski, yeni):
    kaynak = {"s3": _oku(S3 / "CoilController.cpp"), "e8": _oku(E8 / "CoilController.cpp"), "ino": _oku(_INO)}
    assert kaynak[dosya].count(eski) == 1, f"çapa {kaynak[dosya].count(eski)} kez"
    kaynak[dosya] = kaynak[dosya].replace(eski, yeni)
    with pytest.raises(AssertionError):
        sureli_denetle(kaynak["s3"], kaynak["e8"], kaynak["ino"])


@pytest.mark.parametrize(
    ("eski", "yeni"),
    [
        ("#define SYNC_MISMATCH_STREAK 8U", "#define SYNC_MISMATCH_STREAK 200U"),
        ("uint32_t tol = tpp / 50U + 2U;", "uint32_t tol = tpp / 2U + 2U;"),
    ],
    ids=["STREAK_200", "tol_yari_periyot"],
)
def test_ARAC_c_parite_denetleyici_mutantta_KIRMIZI(eski, yeni):
    s3 = _oku(S3 / "CoilController.cpp")
    assert s3.count(eski) == 1
    with pytest.raises(AssertionError):
        s3_parite_denetle(s3.replace(eski, yeni))


# ── 1-B bağımsız inceleme (i3): EYLEM kapısı — koşul değil, durdurma DEYİMİ ─────────────────────────────
#
# (a)/(b) kolları yalnız `if` İFADELERİNİ pinliyordu: Y40 termal dalındaki `coil->stop();` ya da 8266 süreli
# daldaki `stop();` yoruma alınınca (karşılaştırma ve kilit yerinde, bobin DURMUYOR) 29 ESP kapı dosyası 264/264
# YEŞİLDİ; `_pwmActive && _pwmDuration > 0` dış koşulu da hiçbir testte kalmamıştı. Artık dengeli küme
# ayrıştırıcıyla gövdelerde durdurma deyimi ve döngüden çağrı aranır.


def _govde(soy: str, desen: str, bas: int = 0) -> tuple[str, int]:
    """`desen` (sonu `{`) ile başlayan ilk bloğun gövdesi ve gövde başı dizini (yorumsuz metinde)."""
    m = re.compile(desen).search(soy, bas)
    assert m, f"blok bulunamadı: {desen}"
    ac = m.end() - 1
    assert soy[ac] == "{", desen
    return soy[ac + 1 : _eslesen_kapanis(soy, ac, "{", "}")], ac + 1


def _deyim_var(govde: str, deyim: str) -> bool:
    return re.search(r"(?:^|[;{}\s])" + re.escape(deyim), govde) is not None


def termal_eylem_denetle(ino: str) -> None:
    soy = c_soy(ino)
    sensor, _ = _govde(soy, r"if\s*\(\s*td\.temp_sensor_ok\s*\)\s*\{")
    termal, _ = _govde(sensor, r"if\s*\(\s*td\.tempObject\s*>=\s*TERMAL_KESME_C\s*\)\s*\{")
    aktif, _ = _govde(termal, r"if\s*\(\s*coil->isActive\(\)\s*\)\s*\{")
    assert _deyim_var(aktif, "coil->stop();"), "Y40 termal dalında bobini DURDURAN `coil->stop();` (yorum dışı) YOK"
    assert _deyim_var(termal, "g_thermalLock = true;"), "Y40 termal kilidi (`g_thermalLock = true;`) YOK"


def sureli_eylem_denetle(s3: str, e8: str) -> None:
    e8s, s3s = c_soy(e8), c_soy(s3)
    kontrol, _ = _govde(e8s, r"void\s+CoilController::_checkPWMDuration\s*\(\s*\)\s*\{")
    dis, _ = _govde(kontrol, r"if\s*\(\s*_pwmActive\s*&&\s*_pwmDuration\s*>\s*0\s*\)\s*\{")
    sure, _ = _govde(
        dis, r"if\s*\(\s*safeMillisDiff\(\s*millis\(\)\s*,\s*_pwmStartTime\s*\)\s*>=\s*_pwmDuration\s*\)\s*\{"
    )
    assert _deyim_var(sure, "stop();"), "8266 süreli dalında `stop();` (yorum dışı) YOK — süre dolunca bobin durmaz"
    guncelle, _ = _govde(e8s, r"void\s+CoilController::update\s*\(\s*\)\s*\{")
    assert _deyim_var(guncelle, "_checkPWMDuration();"), "8266 update() süre denetimini ÇAĞIRMIYOR"
    sure3, _ = _govde(
        s3s,
        r"if\s*\(\s*_active\s*&&\s*_hasDuration\s*&&\s*\(\s*millis\(\)\s*-\s*_startTime\s*\)\s*>=\s*_duration\s*\)\s*\{",
    )
    assert _deyim_var(sure3, "_stopPWM();"), "S3 süreli dalında `_stopPWM();` (yorum dışı) YOK"


def test_KRITIK_Y40_termal_kesme_EYLEMI_coil_stop():
    termal_eylem_denetle(_oku(_INO))


def test_KRITIK_sureli_durma_EYLEMI_8266_ve_S3():
    sureli_eylem_denetle(_oku(S3 / "CoilController.cpp"), _oku(E8 / "CoilController.cpp"))


@pytest.mark.parametrize(
    ("dosya", "eski", "yeni"),
    [
        ("ino", "                    coil->stop();\n", "                    // coil->stop();\n"),
        ("ino", "                g_thermalLock = true;\n", "                // g_thermalLock = true;\n"),
        (
            "e8",
            "            stop();  // stop() içinde EEPROM'a kaydedilir",
            "            // stop();  // stop() içinde EEPROM'a kaydedilir",
        ),
        ("e8", "    _checkPWMDuration();\n", "    // _checkPWMDuration();\n"),
        ("s3", 'durduruluyor");\n        _stopPWM();', 'durduruluyor");\n        // _stopPWM();'),
    ],
    ids=[
        "termal_stop_YORUM",
        "termal_kilit_YORUM",
        "8266_sure_stop_YORUM",
        "8266_update_cagri_YORUM",
        "s3_sure_stop_YORUM",
    ],
)
def test_ARAC_eylem_denetleyicisi_mutantta_KIRMIZI(dosya, eski, yeni):
    kaynak = {"ino": _oku(_INO), "e8": _oku(E8 / "CoilController.cpp"), "s3": _oku(S3 / "CoilController.cpp")}
    metin = kaynak[dosya].replace("\r\n", "\n")
    assert metin.count(eski) == 1, f"ÇAPA ÇÜRÜDÜ (kapı değil aparat): {eski!r} {metin.count(eski)} kez"
    kaynak[dosya] = metin.replace(eski, yeni)
    with pytest.raises(AssertionError) as hata:
        termal_eylem_denetle(kaynak["ino"]) if dosya == "ino" else sureli_eylem_denetle(kaynak["s3"], kaynak["e8"])
    assert "blok bulunamadı" not in str(hata.value), f"mutant bloğu bozdu, eylem denetimi değil: {hata.value}"
