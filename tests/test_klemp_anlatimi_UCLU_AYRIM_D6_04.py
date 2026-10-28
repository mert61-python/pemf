# -*- coding: utf-8 -*-
"""D6.04 · D6.36 (B-2.18 · B-2.21 · B-11.3) — klemp anlatımı ÜÇLÜ ayrımla yazılsın ve KODLA aynı olsun.

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, 2026-10-28):
  · `servers/entitlement.py` modül docstring'i "Backend safety-limit'leri (freq/duty/48°C) bundan bağımsızdır" diyordu —
    backend'de duty tavanı da 48 °C sınırı da YOK (Y9 · A-47); okuyan, var olmayan bir termal korumaya güvenirdi.
  · `docs/ARCHITECTURE.md`, `apps/backend/controllers/README.md` "duty'nin üst sınırı yoktur, firmware/timer doyurur",
    `utils/stm32_protocol_limits.py` "Firmware/timer output saturates physically at one tick below the period" diyordu —
    D1.101 · Y20'den beri kart kip tavanının üstünü NACK'ler (`DUTY_MAX_BIPOLAR` 0,5 / `DUTY_MAX_UNIPOLAR` 1,0) ve ISR bipolar
    darbeyi `tpp/2 − DDS_BIPOLAR_GAP_TICKS` ile kıstırır (shoot-through). "Duty tavanı yok / firmware doyurur" anlatımı bu
    TAŞIYICI klempin "gereksiz" sanılıp kaldırılmasına davetiyedir.

DOĞRU ÜÇLÜ AYRIM (orkestratör notu D6.04):
  1. Backend'de tedavi safety-clamp'i YOK — STM duty tavanı (`STM32_DUTY_MAX_RATIO = None`) ve sıcaklık eşiği yok (Y9 · A-47).
  2. Protokol-geçerlilik sınırı backend'de VAR ve TAŞIYICI — STM freq 1–25000 Hz, faz 0–360°, ESP freq ≤1000 Hz, AI Pro duty ≤0,50.
  3. Firmware'de shoot-through için duty klempi VAR ve TAŞIYICI.

⚠️ Bu kapı EKLEME yönünde hiçbir şey istemez: termal kesme / duty clamp'i EKLEMEK yasaktır (A-47 · Y9). Kapı yalnız anlatımın
kodla aynı kalmasını ölçer. Sabitler hem testte PİNLİ hem koddan okunur — biri kayarsa kırmızı.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from utils import stm32_protocol_limits as L
from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))

ARCH = KOK / "docs" / "ARCHITECTURE.md"
CTRL = KOK / "apps" / "backend" / "controllers" / "README.md"
KOK_README = KOK / "README.md"
ENT = KOK / "apps" / "backend" / "servers" / "entitlement.py"
LIM = KOK / "apps" / "backend" / "utils" / "stm32_protocol_limits.py"
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"

#: "Duty tavanı yok / firmware doyurur" ve "48 °C sınırı var" anlatımının bilinen biçimleri.
YASAK = (
    re.compile(r"firmware/timer doyurur", re.I),
    re.compile(r"sınırda doyurur", re.I),
    re.compile(r"saturates physically", re.I),
    re.compile(r"duty'nin üst sınırı yoktur", re.I),
    re.compile(r"safety-limit'leri\s*\(freq/duty/48", re.I),
)


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _yorumlar(p: Path) -> str:
    """Python dosyasının YALNIZ `#` yorumları (kod satırı değil)."""
    return "\n".join(s.split("#", 1)[1] for s in _oku(p).splitlines() if s.lstrip().startswith("#"))


def _entitlement_docstring() -> str:
    return ast.get_docstring(ast.parse(_oku(ENT))) or ""


def _gecerli_satir(metin: str, anahtar: str) -> str:
    """`anahtar`ı içeren TEK satır (belge maddesi); yoksa ya da birden çoksa kırmızı."""
    satirlar = [s for s in metin.splitlines() if anahtar in s]
    assert len(satirlar) == 1, f"'{anahtar}' satırı tam 1 kez olmalı, {len(satirlar)} bulundu"
    return satirlar[0]


def test_sabitler_pinli_ve_kodla_ayni():
    # Değerler PİNLİ (kayarsa belge de güncellenmeli).
    assert L.FREQ_MIN_HZ == 1.0
    assert L.FREQ_MAX_HZ == 25000.0
    assert L.ESP_FREQ_MAX_HZ == 1000.0
    assert L.PHASE_MIN_DEG == 0.0 and L.PHASE_MAX_DEG == 360.0
    assert L.AI_PRO_DUTY_MAX_RATIO == 0.50
    assert L.STM32_DUTY_MAX_RATIO is None, "backend STM duty tavanı YOK (Y9) — belge de böyle anlatır"
    c = _oku(MAIN_C)
    assert re.search(r"#define DUTY_MAX_BIPOLAR 0\.5f", c), "firmware bipolar duty tavanı (NACK) 0,5 olmalı"
    assert re.search(r"#define DUTY_MAX_UNIPOLAR 1\.0f", c), "firmware unipolar duty tavanı (NACK) 1,0 olmalı"
    assert "((int32_t)(tpp / 2U) - DDS_BIPOLAR_GAP_TICKS)" in c, "ISR bipolar klempi tpp/2 − GAP olmalı"


@pytest.mark.parametrize(
    "ad,metin",
    [
        ("docs/ARCHITECTURE.md", lambda: _oku(ARCH)),
        ("apps/backend/controllers/README.md", lambda: _oku(CTRL)),
        ("README.md", lambda: _oku(KOK_README)),
        ("entitlement.py docstring", _entitlement_docstring),
        ("stm32_protocol_limits.py yorumları", lambda: _yorumlar(LIM)),
    ],
    ids=["ARCHITECTURE", "controllers-README", "kok-README", "entitlement-doc", "protocol-limits-yorum"],
)
def test_yasak_klemp_anlatimi_YOK(ad, metin):
    m = metin()
    bulunan = [r.pattern for r in YASAK if r.search(m)]
    assert not bulunan, f"{ad}: bayat klemp anlatımı ({bulunan}) — üçlü ayrımla yaz (D6.04)"


def test_entitlement_docstring_48C_ve_duty_sinirini_IDDIA_ETMEZ():
    d = _entitlement_docstring()
    assert not re.search(r"48\s*°?\s*C", d), (
        "entitlement docstring'i 48 °C sınırı iddia etmemeli (A-47: termal kesme YOK)"
    )
    assert "freq/duty" not in d, "entitlement docstring'i backend duty sınırı iddia etmemeli (Y9)"
    for parca in ("protokol", "1–25000 Hz", "≤1000 Hz", "≤0,50", "Y9", "A-47"):
        assert parca.lower() in d.lower(), f"entitlement docstring'i protokol sınırını doğru anlatmalı: '{parca}' yok"


def test_architecture_sinir_cumlesi_SABITLERLE_ayni():
    a = _oku(ARCH)
    satir = _gecerli_satir(a, "Protokol-geçerlilik sınırı")
    beklenen = (
        f"{int(L.FREQ_MIN_HZ)}–{int(L.FREQ_MAX_HZ)} Hz",
        f"{int(L.PHASE_MIN_DEG)}–{int(L.PHASE_MAX_DEG)}°",
        f"≤{int(L.ESP_FREQ_MAX_HZ)} Hz",
        f"≤{L.AI_PRO_DUTY_MAX_RATIO:.2f}".replace(".", ","),
        "STM32_DUTY_MAX_RATIO = None",
        "A-47",
    )
    for b in beklenen:
        assert b in satir, f"ARCHITECTURE protokol-sınırı satırı '{b}' içermeli: {satir[:160]}…"
    fw = _gecerli_satir(a, "Firmware duty sınırı")
    for b in ("TAŞIYICI", "DUTY_MAX_BIPOLAR", "DUTY_MAX_UNIPOLAR", "tpp/2 − DDS_BIPOLAR_GAP_TICKS", "shoot-through"):
        assert b in fw, f"ARCHITECTURE firmware duty satırı '{b}' içermeli"


def test_controllers_readme_firmware_klempini_TASIYICI_anlatir():
    s = _gecerli_satir(_oku(CTRL), "Tedavi güvenlik-sınırı (safety clamp) YOK")
    for b in ("STM32_DUTY_MAX_RATIO = None", "A-47", "TAŞIYICI", "DUTY_MAX_BIPOLAR", "DDS_BIPOLAR_GAP_TICKS"):
        assert b in s, f"controllers/README klemp satırı '{b}' içermeli"


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════
# D6.36 (B-11.3) — "backend'de freq/faz clamp'i yok, firmware satüre eder" anlatımı YOK; protokol sınırı backend'de TAŞIYICI
# ÖLÇÜLEN (HEAD ebf1c3fe): `docs/VERIFICATION.md` §1 "Backend'de freq/duty/sıcaklık clamp'i bilinçli yok; güvenlik firmware'e
# devredilmiş … fiziksel olarak satüre mi ediyor, aşırı-ısınmada kesiyor mu?" · `firmware/README.md` "Python tarafı bilinçli olarak
# duty satüre etmez (firmware doyurur)". Gerçek: `hardware_controller.py` `normalize_frequency_hz` / `normalize_phase_deg`,
# `api_server.py` `normalize_esp_frequency_hz` çağırır (TAŞIYICI — firmware aralık dışını NACK'ler, satüre ETMEZ); termal kesme YOK.
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════

VERIF = KOK / "docs" / "VERIFICATION.md"
FW_README = KOK / "firmware" / "README.md"
HC = KOK / "apps" / "backend" / "controllers" / "hardware_controller.py"
API = KOK / "apps" / "backend" / "servers" / "api_server.py"

YASAK_D636 = YASAK + (
    re.compile(r"freq/duty/sıcaklık \*\*clamp'i bilinçli yok", re.I),
    re.compile(r"firmware(/timer)? doyurur", re.I),
    re.compile(r"aşırı-ısınmada\s+kesiyor\s+mu\?", re.I),  # satır kırılımı da (mutant m4 yaşadı → kol eklendi)
)


def _cagri_sayisi(p: Path, ad: str) -> int:
    agac = ast.parse(_oku(p))
    return sum(
        1
        for d in ast.walk(agac)
        if isinstance(d, ast.Call)
        and (
            (isinstance(d.func, ast.Name) and d.func.id == ad)
            or (isinstance(d.func, ast.Attribute) and d.func.attr == ad)
        )
    )


def _verification_bolum1() -> str:
    m = _oku(VERIF)
    bas = m.index("## ⏳ 1 — ")
    son = m.index("\n## ", bas + 5)
    return m[bas:son]


def test_D6_36_protokol_siniri_cagrilari_backendde_VAR():
    assert _cagri_sayisi(HC, "normalize_frequency_hz") >= 1, (
        "hardware_controller frekans protokol sınırı çağrısı YOK (TAŞIYICI — Y9)"
    )
    assert _cagri_sayisi(HC, "normalize_phase_deg") >= 1, (
        "hardware_controller faz protokol sınırı çağrısı YOK (TAŞIYICI — Y9)"
    )
    assert _cagri_sayisi(API, "normalize_esp_frequency_hz") >= 1, (
        "api_server ESP frekans sınırı çağrısı YOK (TAŞIYICI — 8266 NACK)"
    )


@pytest.mark.parametrize(
    "ad,metin",
    [("VERIFICATION §1", _verification_bolum1), ("firmware/README", lambda: _oku(FW_README))],
    ids=["VERIFICATION-1", "firmware-README"],
)
def test_D6_36_belge_clamp_yok_firmware_satureder_DEMEZ(ad, metin):
    m = re.sub(r"~~.*?~~", " ", metin(), flags=re.S)  # üstü çizili tarihçe hariç
    bulunan = [r.pattern for r in YASAK_D636 if r.search(m)]
    assert not bulunan, f"{ad}: bayat klemp anlatımı ({bulunan}) — protokol sınırı backend'de TAŞIYICI (D6.36)"


def test_D6_36_VERIFICATION_bolum1_protokol_sinirini_ve_firmware_klempini_anar():
    b = _verification_bolum1()
    for parca in (
        "TAŞIYICI",
        "normalize_frequency_hz",
        "normalize_esp_frequency_hz",
        "NACK",
        "DUTY_MAX_BIPOLAR",
        "DDS_BIPOLAR_GAP_TICKS",
        "A-47",
    ):
        assert parca in b, f"VERIFICATION §1 '{parca}' anmalı (D6.36)"
