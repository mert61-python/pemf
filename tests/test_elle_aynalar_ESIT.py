# -*- coding: utf-8 -*-
"""D4.33 · P3 (DENETIM-12 §3.2) — ELLE eş tutulan 7 kopya için AYNA kapıları (yapı değişmez).

Birleştirme dil sınırı yüzünden yapılamıyor (TS↔Python, HTML/JS↔Rust, YAML↔requirements). Bu dosya yapıyı DEĞİŞTİRMEZ:
her alt kapı iki (ya da daha çok) kopyanın değerini KAYNAKTAN okur ve eşitliğini ister — bugün YEŞİL, kopyalardan biri
ayrışınca YALNIZ ilgili alt test KIRMIZI. Literal pinlenmez (değer değişebilir; eşitlik değişmez).

  a  launcher UI `invoke("…")` adları ⊆ Rust `generate_handler!` (ana blok) — ad düşerse UI çağrısı SESSİZCE başarısız
  b  Supabase proje ref'i + publishable anahtar, takipli dosyalar — ⚠️ DEĞER BASILMAZ (Y6 / A-14): yalnız SHA-256 öneki
  c  yedek parolası `MIN_PAROLA` TS ↔ Python
  d  CKD asgari kural `CKD_MIN_ALAN` + `CKD_CEKIRDEK` TS ↔ Python
  e  `LOOPBACK_HOSTS` iki TS dosyası
  f  ruff sürüm pini: lint.yml · pre-commit rev · requirements-dev · myenv-requirements
  g  yasal künye: arayüz `FIRMA` ↔ site `COMPANY`

Okuma: `git ls-files -z` (quotePath tuzağı yok) + BAYT okuma ve UTF-8 çözme (cp1254 tuzağı yok). Vakum eşikleri: a ≥20 ad;
b ≥5 dosya; c–g tanım TAM 1. Kendi riski: yorumda kalmış eski kopya sahte kırmızı yapabilir — tanımlar tanım biçimiyle
(`export const X =`, `X = `) aranır, yorum satırları sayılmaz.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from functools import lru_cache
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _izlenen() -> tuple[str, ...]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, timeout=120)
    assert r.returncode == 0, f"git ls-files düştü (rc={r.returncode})"
    return tuple(x.decode("utf-8") for x in r.stdout.split(b"\x00") if x)


def _oku(rel: str) -> str:
    assert rel in _izlenen(), f"ayna kopyası İZLENMİYOR ya da taşındı: {rel}"
    return (KOK / rel).read_bytes().decode("utf-8")


def _tek(desen: str, metin: str, ad: str, bayrak: int = re.M) -> re.Match:
    bulunan = list(re.finditer(desen, metin, bayrak))
    assert len(bulunan) == 1, f"{ad}: tanım TAM 1 olmalı, {len(bulunan)} bulundu (vakum/çift tanım)"
    return bulunan[0]


def _ts_dizgi_listesi(govde: str) -> list[str]:
    return re.findall(r"""["']([^"']*)["']""", govde)


# ── a) launcher UI invoke ⊆ Rust generate_handler! ──────────────────────────────────────────────────────


def _rust_komutlari() -> list[set[str]]:
    rust = _oku("launcher/app/src/main.rs")
    bloklar = []
    for m in re.finditer(r"generate_handler!\[(.*?)\]", rust, re.S):
        govde = re.sub(r"//[^\n]*", "", m.group(1))
        bloklar.append({a.strip() for a in govde.split(",") if a.strip()})
    return bloklar


def test_a_launcher_UI_invoke_adlari_RUST_generate_handler_listesinde():
    ui = _oku("launcher/app/ui/index.html")
    adlar = set(re.findall(r"""\binvoke\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""", ui))
    assert len(adlar) >= 20, f"VAKUM: UI'da yalniz {len(adlar)} invoke adi"
    bloklar = _rust_komutlari()
    assert bloklar, "Rust'ta generate_handler! blogu bulunamadi"
    ana = max(bloklar, key=len)
    assert len(ana) >= 20, f"VAKUM: ana generate_handler! blogunda yalniz {len(ana)} ad"
    eksik = sorted(adlar - ana)
    assert not eksik, (
        f"UI'nin cagirdigi komut(lar) Rust generate_handler! listesinde YOK (cagri SESSIZCE duser): {eksik}"
    )


# ── b) Supabase ref + publishable anahtar — DEĞER BASILMAZ ────────────────────────────────────────────────

_REF = re.compile(rb"https://([a-z0-9]{20})\.supabase\.co")
# 4A-3.1 (A3 incelemesi): launcher'ın ÜRÜN sabiti `PROJECT_REF` (auth.rs → `expected_host()`) URL biçimini taşımaz; yalnız
# https deseniyle auth.rs `#[cfg(test)]` vektörleri üzerinden "görülüyordu" — sabit ayrışınca kapı YEŞİL kalıyordu.
_REF_SABIT = re.compile(rb"""(?i)project_ref[^"'\n]{0,24}["']([a-z0-9]{20})["']""")
_REF_URUN_SABITI = "launcher/core/src/auth.rs"
_ANAHTAR = re.compile(rb"sb_publishable_[A-Za-z0-9_\-]{10,}")


def _oz(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:10]


def test_b_supabase_ref_ve_publishable_anahtar_TUM_kopyalarda_AYNI():
    """Sır değeri ASLA basılmaz (Y6 / A-14): ileti yalnız dosya adı ve SHA-256 öneki taşır."""
    ref_oz: dict[str, set[str]] = {}
    anahtar_oz: dict[str, set[str]] = {}
    sabit_dosya: set[str] = set()
    for rel in _izlenen():
        if "node_modules" in rel or rel.endswith((".png", ".jpg", ".zip", ".exe", ".onnx", ".pt", ".pdf", ".ico")):
            continue
        p = KOK / rel
        try:
            if p.stat().st_size > 4_000_000:
                continue
            b = p.read_bytes()
        except OSError:
            continue
        for m in _REF.finditer(b):
            ref_oz.setdefault(_oz(m.group(1)), set()).add(rel)
        for m in _REF_SABIT.finditer(b):
            ref_oz.setdefault(_oz(m.group(1)), set()).add(rel)
            sabit_dosya.add(rel)
        for m in _ANAHTAR.finditer(b):
            anahtar_oz.setdefault(_oz(m.group(0)), set()).add(rel)
    ref_dosya = set().union(*ref_oz.values()) if ref_oz else set()
    anahtar_dosya = set().union(*anahtar_oz.values()) if anahtar_oz else set()
    assert len(ref_dosya) >= 5 and len(anahtar_dosya) >= 5, (
        f"VAKUM: ref {len(ref_dosya)} / anahtar {len(anahtar_dosya)} dosyada bulundu"
    )
    assert _REF_URUN_SABITI in sabit_dosya, (
        f"VAKUM: launcher URUN sabiti PROJECT_REF {_REF_URUN_SABITI} icinde bulunamadi (ad/bicim degisti mi?)"
    )
    ozet = lambda d: {k: sorted(v) for k, v in d.items()}  # noqa: E731
    assert len(ref_oz) == 1, f"Supabase proje ref'i kopyalarda FARKLI (SHA-256 oneki -> dosyalar): {ozet(ref_oz)}"
    assert len(anahtar_oz) == 1, (
        f"publishable anahtar kopyalarda FARKLI (SHA-256 oneki -> dosyalar): {ozet(anahtar_oz)}"
    )


# ── c) MIN_PAROLA TS ↔ Python ─────────────────────────────────────────────────────────────────────────────


def test_c_yedek_parolasi_MIN_PAROLA_TS_ile_PYTHON_AYNI():
    ts = _tek(
        r"^export const MIN_PAROLA\s*=\s*(\d+)\s*;",
        _oku("apps/ui/src/components/domain/BackupPassphraseDialog.tsx"),
        "TS MIN_PAROLA",
    )
    py = _tek(r"^MIN_PAROLA\s*=\s*(\d+)\s*$", _oku("apps/backend/utils/data_export.py"), "Python MIN_PAROLA")
    assert int(ts.group(1)) == int(py.group(1)), f"MIN_PAROLA ayristi: TS {ts.group(1)} != Python {py.group(1)}"


# ── d) CKD asgari kural TS ↔ Python ──────────────────────────────────────────────────────────────────────


def test_d_CKD_asgari_kural_TS_ile_PYTHON_AYNI():
    ts = _oku("apps/ui/src/utils/ckdOnKontrol.ts")
    py = _oku("apps/backend/utils/klinik_asgari.py")
    ts_min = _tek(r"^export const CKD_MIN_ALAN\s*=\s*(\d+)\s*;", ts, "TS CKD_MIN_ALAN").group(1)
    py_min = _tek(r"^CKD_MIN_ALAN\s*=\s*(\d+)\s*$", py, "Python CKD_MIN_ALAN").group(1)
    ts_cek = _ts_dizgi_listesi(_tek(r"^export const CKD_CEKIRDEK\s*=\s*\[([^\]]*)\]", ts, "TS CKD_CEKIRDEK").group(1))
    py_cek = _ts_dizgi_listesi(_tek(r"^CKD_CEKIRDEK\s*=\s*\(([^)]*)\)", py, "Python CKD_CEKIRDEK").group(1))
    assert len(py_cek) >= 3, f"VAKUM: Python CKD_CEKIRDEK {py_cek}"
    assert int(ts_min) == int(py_min), f"CKD_MIN_ALAN ayristi: TS {ts_min} != Python {py_min}"
    assert sorted(ts_cek) == sorted(py_cek), f"CKD_CEKIRDEK ayristi: TS {ts_cek} != Python {py_cek}"


# ── e) LOOPBACK_HOSTS iki TS dosyası ─────────────────────────────────────────────────────────────────────


def _loopback(rel: str) -> list[str]:
    # ⚠️ DENETIM-12'nin kendi hatası: `[^\]]*` deseni "[::1]" içindeki `]`de erken kesiyordu → sahte kırmızı. Gövde `])`a kadar.
    m = _tek(r"^const LOOPBACK_HOSTS\s*=\s*new Set\(\[(.*?)\]\)\s*;", _oku(rel), f"{rel} LOOPBACK_HOSTS")
    return _ts_dizgi_listesi(m.group(1))


def test_e_LOOPBACK_HOSTS_iki_TS_kopyasinda_AYNI():
    a = _loopback("apps/ui/src/services/desktopSession.ts")
    b = _loopback("apps/ui/src/services/supabaseAuth.ts")
    assert len(a) >= 3, f"VAKUM: {a}"
    assert sorted(a) == sorted(b), f"LOOPBACK_HOSTS ayristi: desktopSession {a} != supabaseAuth {b}"


# ── f) ruff sürüm pini (4 yer) ───────────────────────────────────────────────────────────────────────────


def test_f_ruff_surum_pini_DORT_yerde_AYNI():
    lint = _tek(r"pip install ruff==(\d+\.\d+\.\d+)", _oku(".github/workflows/lint.yml"), "lint.yml ruff").group(1)
    dev = _tek(r"^ruff==(\d+\.\d+\.\d+)", _oku("requirements-dev.txt"), "requirements-dev ruff").group(1)
    myenv = _tek(r"^ruff==(\d+\.\d+\.\d+)", _oku("build_tools/myenv-requirements.txt"), "myenv ruff").group(1)
    pc = _tek(
        r"repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?(\d+\.\d+\.\d+)",
        _oku(".pre-commit-config.yaml"),
        "pre-commit ruff rev",
    ).group(1)
    pinler = {
        "lint.yml": lint,
        "requirements-dev.txt": dev,
        "myenv-requirements.txt": myenv,
        ".pre-commit-config.yaml": pc,
    }
    assert len(set(pinler.values())) == 1, f"ruff pini ayristi: {pinler}"


# ── g) yasal künye: arayüz FIRMA ↔ site COMPANY ──────────────────────────────────────────────────────────

#: arayüz alanı → site alanı (DENETIM-12: 8 alan). `adres` = site `address` + " / " + `city` (türetilmiş, ayrıca).
_KUNYE_ESLEME = {
    "urun": "brandName",
    "unvan": "legalName",
    "tel": "phone",
    "eposta": "email",
    "mersis": "mersis",
    "vkn": "taxNo",
    "ticaretSicil": "tradeRegistry",
    "vergiDairesi": "taxOffice",
}


def _ts_nesne(metin: str, ad: str) -> dict[str, str]:
    govde = _tek(rf"^export const {ad}\s*=\s*\{{(.*?)^\}}\s*as const", metin, ad, re.M | re.S).group(1)
    govde = re.sub(r"^\s*//[^\n]*", "", govde, flags=re.M)
    return {k: v for k, _, v in re.findall(r"""^\s*([A-Za-z]+)\s*:\s*(["'])(.*?)\2\s*,""", govde, re.M)}


def test_g_yasal_kunye_ARAYUZ_ile_SITE_AYNI():
    firma = _ts_nesne(_oku("apps/ui/src/config/firma.ts"), "FIRMA")
    site = _ts_nesne(_oku("apps/web/src/config.ts"), "COMPANY")
    eksik = [k for k in _KUNYE_ESLEME if k not in firma] + [v for v in _KUNYE_ESLEME.values() if v not in site]
    assert not eksik, f"kunye alani bulunamadi (ad degisti mi?): {eksik}"
    farkli = {k: (firma[k], site[v]) for k, v in _KUNYE_ESLEME.items() if firma[k] != site[v]}
    assert not farkli, f"yasal kunye arayuz <-> site AYRISTI (arayuz, site): {farkli}"
    assert firma.get("adres") == f"{site.get('address')} / {site.get('city')}", (
        f"adres ayristi: arayuz {firma.get('adres')!r} != site {site.get('address')!r} / {site.get('city')!r}"
    )
