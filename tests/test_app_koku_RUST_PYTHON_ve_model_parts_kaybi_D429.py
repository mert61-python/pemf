# -*- coding: utf-8 -*-
"""D4.29 (B-10.91 · B-10.142) — app-katmanı kök listesi Rust↔Python İKİ YÖNLÜ ve yorum-soyulmuş; `model_parts` kaybı DAVRANIŞLA.

ARIZA 1 (B-10.91): app katmanının sınırı iki kopyada yaşıyor — üretim `build_tools/make_base_zip.py::APP_ROOTS` ve launcher
yükseltme tatbikatı `launcher/core/tests/upgrade_drill.rs::APP_ROOTS`. Rust testi (`tatbikat_sinirlari_URETIMLE_ayni`) TEK YÖNLÜ
(Rust ⊆ Python) ve Python dosyası yoksa `eprintln! + return` ile SESSİZCE geçiyor; Python'da `deploy` ya da
`cloud_mqtt_provision.json` kökünü silen değişikliği HİÇBİR test görmüyordu → o dosyalar deps katmanına kayar: her provizyon /
profil değişikliği kliniklere ~1,4 GB indirtir, app geri alması onları kapsamaz.
ARIZA 2 (B-10.142): `make_manifest`'in `model_parts` sessiz-kayıp kapısını ölçen test yalnız KAYNAK METNİNE bakıyordu
(`'kayip.append(f"model_parts.' in src`); kapı `if False:` olsa da yeşildi.

Bu dosya: (a) Python kökleri AST'den DEĞERLENDİRİLİR (yorumdaki satır sayılmaz), Rust kökleri yorumları soyulmuş kaynaktan okunur
(dosya yoksa FAIL — atlama yok); Rust ⊆ Python ve Python − Rust = AÇIK fark listesi (Rust tatbikatı genişletilince daralır).
(b) GERÇEK `make_manifest` alt süreçte: önceki manifestte olan ve tabloda karşılığı olmayan bir parça profili → çıkış 1, manifest yazılmaz.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
MAKE_BASE_ZIP = KOK / "build_tools" / "make_base_zip.py"
UPGRADE_DRILL = KOK / "launcher" / "core" / "tests" / "upgrade_drill.rs"
MAKE_MANIFEST = KOK / "scripts" / "make_manifest.py"

#: Python'da OLUP Rust tatbikatında HENÜZ olmayan kökler — BİLİNÇLİ ve SÜRELİ fark. Rust const'u ancak cargo ile doğrulanabilir
#: (bu oturumda derleme yasak); launcher oturumu tatbikatı genişlettikçe bu küme DARALIR ve sonunda boş kalır. Kapı iki yönlü:
#: Python'dan bir kök düşerse ya da Python'a yeni kök eklenirse bu küme tutmaz → KIRMIZI (sessiz kayma yok).
RUST_TATBIKATINDA_HENUZ_YOK = frozenset(
    {
        "PEMF_Backend/_internal/data/cloud_mqtt_provision.json",
        "PEMF_Backend/_internal/deploy",
        "PEMF_Backend/_internal/frontend_version.json",
        "PEMF_Backend/setup_services.ps1",
        "PEMF_Backend/start_hotspot.ps1",
        "PEMF_Backend/install_hotspot_task.ps1",
        "PEMF_Backend/pemf_footprint.ps1",
        "PEMF_Backend/pemf_teardown.ps1",
        "PEMF_Backend/pemf_uninstall_all.ps1",
        # I18N-0 (2026-10-19): sunucu çeviri katalogları app katmanında (gerekçe make_base_zip.APP_ROOTS); tatbikat bu kökü henüz
        # kurmuyor — eklenince bu satırı silin.
        "PEMF_Backend/_internal/i18n",
    }
)


def _python_app_roots(kaynak: str) -> set[str]:
    """`APP_ROOTS_FILE`, `ADD_SCRIPTS`, `APP_ROOTS` üst-düzey atamaları AST'den DEĞERLENDİRİLİR (betik import edilmez: üst düzeyde
    paketleme yapar). Yorum satırı AST'de yoktur → yoruma alınmış kök sayılmaz."""
    ad_alani: dict[str, object] = {}
    for d in ast.parse(kaynak).body:
        if isinstance(d, ast.Assign) and len(d.targets) == 1 and isinstance(d.targets[0], ast.Name):
            ad = d.targets[0].id
            if ad in ("APP_ROOTS_FILE", "ADD_SCRIPTS", "APP_ROOTS"):
                kod = compile(ast.Expression(d.value), "<make_base_zip>", "eval")
                ad_alani[ad] = eval(kod, {"__builtins__": {}, **ad_alani})  # noqa: S307 — depodaki sabit liste ifadesi
    assert "APP_ROOTS" in ad_alani, (
        "make_base_zip.py'de APP_ROOTS atamasi bulunamadi (bicim degisti, kapi guncellensin)"
    )
    return set(ad_alani["APP_ROOTS"])  # type: ignore[arg-type]


def _rust_yorumsuz(src: str) -> str:
    """Rust kaynağından `//` ve (iç içe) `/* */` yorumlarını SOYAR; dize ("..."/ham r#"..."#) ve karakter ('x') sabitlerini korur."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            derinlik, i = 1, i + 2
            while i < n and derinlik:
                if src.startswith("/*", i):
                    derinlik, i = derinlik + 1, i + 2
                elif src.startswith("*/", i):
                    derinlik, i = derinlik - 1, i + 2
                else:
                    i += 1
            continue
        m = re.match(r'r(#*)"', src[i:])
        if m and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")):
            son = '"' + m.group(1)
            j = src.find(son, i + len(m.group(0)))
            j = n if j < 0 else j + len(son)
            out.append(src[i:j])
            i = j
            continue
        if c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            out.append(src[i : j + 1])
            i = j + 1
            continue
        m = re.match(r"'(\\.|[^\\'\n])'", src[i:])
        if m:
            out.append(m.group(0))
            i += len(m.group(0))
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _rust_app_roots(kaynak: str) -> set[str]:
    yorumsuz = _rust_yorumsuz(kaynak)
    m = re.search(r"const\s+APP_ROOTS\s*:\s*&\[\s*&str\s*\]\s*=\s*&\[(.*?)\];", yorumsuz, re.S)
    assert m, "upgrade_drill.rs'de `const APP_ROOTS: &[&str] = &[...]` bulunamadi (bicim degisti, kapi guncellensin)"
    return set(re.findall(r'"((?:\\.|[^"\\])*)"', m.group(1)))


# ── ölçücü kendi karşıt vakalarıyla ──────────────────────────────────────────────────────────


def test_olcucu_rust_yorum_soyucu_KARSIT_vakalarla_KANITLI():
    ornek = """
    // const APP_ROOTS: &[&str] = &["SAHTE"];
    const APP_ROOTS: &[&str] = &[
        "A", // "YORUMDAKI_DIZE"
        /* "BLOK" /* ic ice "IC" */ "HALA_BLOK" */
        "http://dize//icinde",
        // "YORUMA_ALINMIS",
    ];
    let c = '"'; let l: Foo<'_> = x; let h = r#"ham // yorum degil"#;
    """
    assert _rust_app_roots(ornek) == {"A", "http://dize//icinde"}
    yorumsuz = _rust_yorumsuz(ornek)
    assert "ham // yorum degil" in yorumsuz, "ham dize icindeki // yorum sanildi"
    assert "YORUMA_ALINMIS" not in yorumsuz and "HALA_BLOK" not in yorumsuz and "SAHTE" not in yorumsuz


def test_olcucu_python_degerlendirici_KARSIT_vakalarla_KANITLI():
    ornek = (
        "APP_ROOTS_FILE = 'P/_app_roots.json'\n"
        "ADD_SCRIPTS = ['a.ps1']\n"
        "APP_ROOTS = [\n    'P/x',\n    # 'P/YORUMDA',\n    APP_ROOTS_FILE,\n] + ['P/' + s for s in ADD_SCRIPTS]\n"
    )
    assert _python_app_roots(ornek) == {"P/x", "P/_app_roots.json", "P/a.ps1"}


# ── (a) iki yönlü eşitlik ───────────────────────────────────────────────────────────────────


def test_KRITIK_upgrade_drill_YOKSA_FAIL_atlanmaz():
    """Rust testi Python dosyası yoksa `eprintln! + return` ile geçiyordu; bu kapı karşı dosya yoksa ATLAMAZ, düşer."""
    assert UPGRADE_DRILL.is_file(), f"{UPGRADE_DRILL} yok — tasindiysa yol guncellensin (atlama YOK)"
    assert MAKE_BASE_ZIP.is_file(), f"{MAKE_BASE_ZIP} yok"


def test_KRITIK_app_kokleri_RUST_PYTHON_iki_yonlu():
    py = _python_app_roots(MAKE_BASE_ZIP.read_text(encoding="utf-8"))
    rs = _rust_app_roots(UPGRADE_DRILL.read_text(encoding="utf-8"))
    assert len(rs) >= 5 and len(py) >= 10, f"vakum: rust={len(rs)} python={len(py)}"
    assert rs <= py, f"Rust tatbikatinda olup URETIMDE olmayan kok(ler): {sorted(rs - py)} — tatbikat kurgu dogruluyor"
    fark = py - rs
    assert fark == RUST_TATBIKATINDA_HENUZ_YOK, (
        "app-katmani koku Rust/Python arasinda SESSIZCE kaydi.\n"
        f"  uretimden DUSEN (deps'e kayar, ~1,4 GB indirme): {sorted(RUST_TATBIKATINDA_HENUZ_YOK - fark - rs)}\n"
        f"  uretime YENI eklenen (tatbikata da ekleyin ya da bu listeye gerekceyle yazin): {sorted(fark - RUST_TATBIKATINDA_HENUZ_YOK)}\n"
        f"  tatbikata eklenmis (bu listeyi DARALTIN): {sorted(RUST_TATBIKATINDA_HENUZ_YOK & rs)}"
    )


# ── (b) model_parts sessiz kaybı — davranış ──────────────────────────────────────────────────

ONCEKI = {
    "schema": 2,
    "version": "1.9.50",
    "tag": "client-app-v1.9.50",
    "launcher": {"version": "1.9.51", "url": "https://x/setup.exe", "sha256": "a" * 64, "size": 1},
    "layers": {
        "win-x64": {
            "rollout": 100,
            "app": {"url": "https://x/v1.9.50/base-app.zip", "sha256": "c" * 64, "size": 3, "kind": "zip"},
            "deps": {"url": "https://x/v1.9.41/base-deps.zip", "sha256": "d" * 64, "size": 4, "kind": "zip"},
        }
    },
    "runtimes": {},
    "models": {},
    "profiles": {},
}


def _manifest(dizin: Path, onceki: dict, *ek: str) -> subprocess.CompletedProcess:
    (dizin / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [
            sys.executable,
            str(MAKE_MANIFEST),
            "--dir",
            str(dizin),
            "--version",
            "1.9.52",
            "--tag",
            "client-app-v1.9.52",
            "--repo",
            "mert61-python/pemf-update",
            *ek,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )


def test_KRITIK_tabloda_olmayan_parca_profili_SESSIZ_KAYBOLMAZ(tmp_path):
    """Önceki manifestte `model_parts.vet` var, `PARCA_ASSETS`te karşılığı yok (tablodan silinmiş/yeniden adlandırılmış) → bayraksız
    koşu çıkış 1, manifest YAZILMAZ, hangi profilin kaybolduğu söylenir (launcher ≥1.9.39 sahte güncelleme tetiklerdi)."""
    onceki = {
        **ONCEKI,
        "model_parts": {"vet": [{"url": "https://x/vet-2.zip", "sha256": "f" * 64, "size": 9, "kind": "zip"}]},
    }
    r = _manifest(tmp_path, onceki)
    assert r.returncode == 1, f"model_parts.vet SESSIZCE dustu (rc={r.returncode})\n{r.stderr[-1200:]}"
    assert "model_parts.vet" in r.stderr, r.stderr[-1200:]
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == onceki, (
        "hata verdigi halde manifest YAZILDI"
    )


def test_KARSIT_tablodaki_parca_yerelde_yoksa_TASINIR(tmp_path):
    """Ölçücü kör değil: tabloda olan `model_parts.research` (yerelde parça yok) taşınır → çıkış 0, aynı girdi."""
    parca = {"url": "https://x/client-app-v1.9.27/research-2.zip", "sha256": "e" * 64, "size": 7, "kind": "zip"}
    r = _manifest(tmp_path, {**ONCEKI, "model_parts": {"research": [parca]}})
    assert r.returncode == 0, r.stderr[-1200:]
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["model_parts"]["research"] == [parca]


@pytest.mark.parametrize("bayrak", ["--drop-missing"])
def test_KARSIT_acik_dusurme_bayragi_kayip_kapisini_ATLAR(tmp_path, bayrak):
    """`--drop-missing` bilinçli düşürme yoludur: kayıp kapısı koşmaz (çıkış 1 burada yalnız 'kurulabilir paket yok'tan gelebilir →
    yerelde katman çifti verilir)."""
    import zipfile

    with zipfile.ZipFile(tmp_path / "base-app.zip", "w") as z:
        z.writestr("PEMF_Backend/PEMF_Backend.exe", b"EXE")
        z.writestr("PEMF_Backend/_app_roots.json", b"{}")
    with zipfile.ZipFile(tmp_path / "base-deps.zip", "w") as z:  # 4B-2.2: deps katmanı da açılabilir zip olmalı
        z.writestr("PEMF_Backend/_internal/deps.bin", b"DEPS")
    onceki = {
        **ONCEKI,
        "model_parts": {"vet": [{"url": "https://x/vet-2.zip", "sha256": "f" * 64, "size": 9, "kind": "zip"}]},
    }
    r = _manifest(tmp_path, onceki, bayrak)
    assert r.returncode == 0, r.stderr[-1200:]
    assert "model_parts" not in json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
