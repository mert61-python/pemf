# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-3 B1 / B4 (istem 38 + 41 C · Y242): `launcher/app/src/main.rs` kapsam sınıfları — SAYAN kapı.

`launcher/app/kapsam_siniflari.json`: main.rs'in HER üst düzey işlevi tam bir sınıfta — T (test edilebilir) · Y (yeniden düzenleme gerekir) ·
S (sınırda: pencere / Tauri çalışma zamanı / gerçek platform API'si — test edilemez) · K (kapsanıyor). Kural (Y242): test yazılabilen satıra
S YASAK; her S "neden" + "neden T / Y değil" taşır; S listesi SAYILIR (yeni S sessizce eklenemez). Rust'ta satır pragması yok ve
`#[coverage(off)]` rustc 1.98.1'de kararlı değil (E0658, KP-3'te ölçüldü) → S ölçümden DIŞLANMAZ; bu kapı sınıflamanın güncel ve gerekçeli
kalmasını kilitler. main.rs'e yeni işlev eklenince ya da S değişince bu dosya ve JSON birlikte güncellenir.
"""

import json
import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"
_SINIF = _KOK / "launcher" / "app" / "kapsam_siniflari.json"
# KP-3 B4 ölçümü (d45d9cf2): 44 S işlevi. Değişiklik BİLİNÇLİ olmalı — sayı burada ve JSON'da birlikte değişir.
BEKLENEN_S = 44


def _islevler() -> list[str]:
    satirlar = _MAIN.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    test_bas = next(i for i, s in enumerate(satirlar) if s.startswith("#[cfg(test)]"))
    return [m.group(1) for s in satirlar[:test_bas] if (m := re.match(r"^(?:pub )?(?:async )?fn (\w+)", s))]


def _veri() -> dict:
    return json.loads(_SINIF.read_text(encoding="utf-8"))


def test_KRITIK_main_rs_HER_ust_duzey_islev_TAM_BIR_sinifta():
    islevler = _islevler()
    assert len(islevler) >= 90, f"VAKUM: main.rs'te yalnız {len(islevler)} üst düzey işlev bulundu"
    assert len(islevler) == len(set(islevler)), (
        "aynı adlı iki üst düzey işlev (cfg kolları?) — ayrıştırıcı / sınıf belirsiz"
    )
    sinif = _veri()["islevler"]
    eksik = sorted(set(islevler) - set(sinif))
    fazla = sorted(set(sinif) - set(islevler))
    assert not eksik, f"main.rs'e SINIFSIZ işlev eklendi (T / Y / S / K seçin, S ise gerekçe): {eksik}"
    assert not fazla, f"sınıf listesinde main.rs'te OLMAYAN işlev (silindi / adı değişti): {fazla}"
    assert {v["sinif"] for v in sinif.values()} <= {"T", "Y", "S", "K"}


def test_KRITIK_S_ve_Y_GEREKCELI_S_sayisi_SAYILIR():
    v = _veri()
    s = {a: x for a, x in v["islevler"].items() if x["sinif"] == "S"}
    assert len(s) == v["s_sayisi"] == BEKLENEN_S, (
        f"S sayısı değişti: JSON {len(s)} / s_sayisi {v['s_sayisi']} / kapı {BEKLENEN_S} — yeni S BİLİNÇLİ eklenir (Y242)"
    )
    gerekcesiz = [
        a
        for a, x in s.items()
        if len(x.get("neden", "").strip()) < 15 or len(x.get("neden_T_Y_degil", "").strip()) < 15
    ]
    assert not gerekcesiz, f"gerekçesiz S: {gerekcesiz}"
    y_gerekcesiz = [
        a for a, x in v["islevler"].items() if x["sinif"] in ("Y", "T") and len(x.get("neden", "").strip()) < 10
    ]
    assert not y_gerekcesiz, f"gerekçesiz Y / T: {y_gerekcesiz}"


def test_S_listesi_GUVENLIK_yollarini_ICERMEZ():
    """Kapanış / ACİL DURDUR / güncelleme güvenlik yolları S (test edilemez) diye kapatılamaz — Y (davranış koruyan ayrım, sahip onayıyla)."""
    sinif = _veri()["islevler"]
    for ad in (
        "stop_backend_for_teardown",
        "stop_tracked_backend",
        "yakma_bitene_kadar_bekle",
        "firmware_uyumsuz_geri_al",
        "apply_runtime_update",
        "apply_self_update",
    ):
        assert sinif[ad]["sinif"] == "Y", f"{ad} güvenlik / güncelleme yolu — S olamaz"
