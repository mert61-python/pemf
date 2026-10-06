# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.109 · B-10.11 — OTA host pini AYNASI: backend (`servers/update_manager.py`) ile launcher (`launcher/core/src/net.rs`)
AYNI güven kümesine bağlı.

ÖLÇÜLEN KÖRLÜK (plan m317): iki liste bugün eşit (5 = 5) ama hiçbir kapı eşitliği ÖLÇMÜYORDU — Python listesine yalnız
`mutant-ota.example.net` eklemek mevcut güncelleme testlerini YEŞİL bırakıyordu. İki taraf ayrışırsa biri zayıf kalır:
launcher ile backend farklı sunuculardan "güvenilir" ikili indirir. Oto-firmware indirmesi de (`firmware_manager
.firmware_indir` → `update_manager._validate_installer_url`) bu Python pinine bağlıdır (D1.110).

ÇAPA: Rust kaynağındaki GERÇEK sabit dizisi — `pub const ALLOWED_HOSTS: &[&str] = &[ … ];` bloğu bulunur, blok İÇİNDEKİ
yorumlar (`// …`, `/* … */`) SOYULUR (yoruma alınmış bir host sayılmaz), kalan dize sabitleri okunur. Python tarafı içe
aktarılan modülün GERÇEK nesnesidir (kaynak metni değil). Beklenen depo yolu da iki tarafta aynı olmalı (pin anlamı).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NET_RS = KOK / "launcher" / "core" / "src" / "net.rs"


def _yorumsuz(metin: str) -> str:
    metin = re.sub(r"/\*.*?\*/", "", metin, flags=re.S)
    return re.sub(r"//[^\n]*", "", metin)


def _rust_dizi(ad: str) -> set[str]:
    kaynak = NET_RS.read_text(encoding="utf-8")
    m = re.search(r"\bconst\s+" + re.escape(ad) + r"\s*:\s*&\[&str\]\s*=\s*&\[(.*?)\];", kaynak, flags=re.S)
    assert m, f"ön koşul: net.rs'te `{ad}` sabit dizisi bulunamadı (çapa bayat — ayrıştırıcıyı güncelleyin)"
    return set(re.findall(r'"([^"\\]*)"', _yorumsuz(m.group(1))))


def _rust_dize(ad: str) -> str:
    kaynak = NET_RS.read_text(encoding="utf-8")
    m = re.search(r"\bconst\s+" + re.escape(ad) + r"\s*:\s*&str\s*=\s*\"([^\"\\]*)\"\s*;", kaynak)
    assert m, f"ön koşul: net.rs'te `{ad}` dize sabiti bulunamadı (çapa bayat)"
    return m.group(1)


pytestmark = pytest.mark.skipif(not NET_RS.exists(), reason="launcher kaynağı yok")


def test_KRITIK_ALLOWED_HOSTS_python_rust_KUME_ESIT():
    from servers import update_manager as um

    rust = _rust_dizi("ALLOWED_HOSTS")
    python = set(um._ALLOWED_UPDATE_HOSTS)
    assert len(rust) >= 3, f"ön koşul: Rust listesi ayrıştırılamadı ya da boş: {rust}"
    assert python == rust, (
        f"OTA host pini AYRIŞTI — yalnız Python: {sorted(python - rust)} · yalnız Rust: {sorted(rust - python)}. "
        "İki taraf aynı güven kümesine bağlı olmalı (backend firmware/installer indirmesi ↔ launcher paket indirmesi)."
    )


def test_KRITIK_beklenen_depo_yolu_python_rust_AYNI():
    from servers import update_manager as um

    assert _rust_dize("UPDATE_REPO_PATH") == f"/{um._UPDATE_REPO}/", (
        f"github.com yol pini iki tarafta farklı depoya sabitli: Rust {_rust_dize('UPDATE_REPO_PATH')!r} · "
        f"Python /{um._UPDATE_REPO}/"
    )


def test_KARSIT_ayristirici_YORUMA_alinmis_hostu_SAYMAZ():
    """Aparat: yoruma alınmış bir satır (silinmiş host) kümeye girmemeli — yoksa kapı Rust'ta silinen hostu görmezdi."""
    ornek = 'pub const ALLOWED_HOSTS: &[&str] = &[\n    "a.example",\n    // "b.example",\n    /* "c.example", */ "d.example",\n];'
    m = re.search(r"\bconst\s+ALLOWED_HOSTS\s*:\s*&\[&str\]\s*=\s*&\[(.*?)\];", ornek, flags=re.S)
    assert set(re.findall(r'"([^"\\]*)"', _yorumsuz(m.group(1)))) == {"a.example", "d.example"}
