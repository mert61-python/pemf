# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YAYIN CI KAPISI (istem 66 CT2 a · Y326 katman 1) — uç commit'in GitHub CI durumu yeşil değilse yayın DURUR.

`scripts/ci_sozlesmesi.json` → `gerekli_isler` (TEK liste; CT3 dal koruması da bunu kullanır). Uç commit'in check-run'ları
`gh api repos/<depo>/commits/<sha>/check-runs` ile okunur; her ad için EN SON check-run (yeniden koşu yeni kayıt açar) değerlendirilir:
  · gerekli iş hiç koşmadı / sürüyor / başarısız → DUR (iş adı + bağlantı)
  · yol süzgeçli iş (`kosulluysa_gerekli`) koştuysa yeşil olmalı; koşmadıysa engel değil
  · gece tam koşusunun (cron) son sonucu kırmızıysa UYARI (yayın commit'ine durum yazmaz — gerekli DEĞİL)
ÇIKIŞ: 0 = yeşil · 1 = DUR · 2 = durum OKUNAMADI (gh yok / oturum yok / ağ) — fail-closed, yayın yine DURUR.
Kullanım: python scripts/ci_durum.py [--sha <commit>] [--depo <sahip/ad>]   (yayın betikleri: scripts/yayin_ci_kapisi.ps1)
Testler için: --checks-json / --gece-json (gh yanıtının yerine dosya).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SOZLESME = KOK / "scripts" / "ci_sozlesmesi.json"
YESIL = {"success"}


def sozlesme_oku(yol: Path = SOZLESME) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def _gh(args: list[str]) -> str:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("gh (GitHub CLI) bulunamadı — kurun ve `gh auth login` ile giriş yapın")
    r = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api düştü (çıkış {r.returncode}): {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def check_runlari_getir(depo: str, sha: str) -> list[dict]:
    cikti = _gh(
        [
            "api",
            "--paginate",
            f"repos/{depo}/commits/{sha}/check-runs?per_page=100",
            "--jq",
            ".check_runs[] | {id, name, status, conclusion, html_url}",
        ]
    )
    return [json.loads(s) for s in cikti.splitlines() if s.strip()]


def gece_son_kosu(depo: str, dosya: str) -> dict | None:
    cikti = _gh(
        [
            "api",
            f"repos/{depo}/actions/workflows/{dosya}/runs?per_page=1&status=completed",
            "--jq",
            ".workflow_runs[0] | {conclusion, html_url, head_sha, created_at}",
        ]
    )
    s = cikti.strip()
    return json.loads(s) if s and s != "null" else None


def en_sonlar(kosular: list[dict]) -> dict[str, dict]:
    """ad → en son check-run (en büyük kimlik; yeniden koşu yeni kimlik alır)."""
    son: dict[str, dict] = {}
    for k in kosular:
        ad = k.get("name", "")
        if ad not in son or int(k.get("id", 0)) > int(son[ad].get("id", 0)):
            son[ad] = k
    return son


def degerlendir(sozlesme: dict, kosular: list[dict], gece: dict | None) -> tuple[list[str], list[str], list[str]]:
    """→ (dur_nedenleri, uyarilar, yesiller)."""
    son = en_sonlar(kosular)
    dur, uyari, yesil = [], [], []
    for g in sozlesme["gerekli_isler"]:
        ad = g["ad"]
        k = son.get(ad)
        if k is None:
            dur.append(f"GEREKLİ iş KOŞMADI: '{ad}' ({g['is_akisi']}) — bu commit GitHub'a push'lanıp CI'ı bitirmeli")
        elif k.get("status") != "completed":
            dur.append(f"GEREKLİ iş SÜRÜYOR: '{ad}' ({k.get('status')}) — bitmesini bekleyin: {k.get('html_url', '')}")
        elif k.get("conclusion") not in YESIL:
            dur.append(f"GEREKLİ iş YEŞİL DEĞİL: '{ad}' = {k.get('conclusion')} — {k.get('html_url', '')}")
        else:
            yesil.append(ad)
    for g in sozlesme.get("kosulluysa_gerekli", []):
        k = son.get(g["ad"])
        if k is None:
            uyari.append(f"'{g['ad']}' bu commit'te koşmadı (yol süzgeci — alan değişmedi)")
        elif k.get("status") != "completed":
            dur.append(f"iş SÜRÜYOR: '{g['ad']}' — bitmesini bekleyin: {k.get('html_url', '')}")
        elif k.get("conclusion") not in YESIL:
            dur.append(f"koşan iş YEŞİL DEĞİL: '{g['ad']}' = {k.get('conclusion')} — {k.get('html_url', '')}")
        else:
            yesil.append(g["ad"])
    if gece is None:
        uyari.append("gece tam koşusu (gece.yml) henüz hiç bitmedi — sonucu bilinmiyor")
    elif gece.get("conclusion") not in YESIL:
        uyari.append(
            f"GECE tam koşusu KIRMIZI ({gece.get('conclusion')}, {gece.get('created_at', '')}) — yayını durdurmaz ama "
            f"bakın: {gece.get('html_url', '')}"
        )
    return dur, uyari, yesil


def _konsol_utf8(akislar=None) -> None:
    for akis in akislar or (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=KOK, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def main(argv: list[str] | None = None) -> int:
    _konsol_utf8()
    ap = argparse.ArgumentParser(description="Yayın CI kapısı — uç commit'in gerekli CI işleri yeşil mi?")
    ap.add_argument("--sha", help="varsayılan: git HEAD")
    ap.add_argument("--depo", help="varsayılan: ci_sozlesmesi.json → depo")
    ap.add_argument("--sozlesme", type=Path, default=SOZLESME)
    ap.add_argument("--checks-json", type=Path, help="test: gh check-runs yanıtı yerine (JSON satırları ya da liste)")
    ap.add_argument("--gece-json", type=Path, help="test: gece son koşu yanıtı yerine ('null' = hiç yok)")
    a = ap.parse_args(argv)
    sozlesme = sozlesme_oku(a.sozlesme)
    depo = a.depo or sozlesme["depo"]
    sha = a.sha or _git("rev-parse", "HEAD")
    if not sha:
        print("!!! uç commit okunamadı (git rev-parse HEAD) — yayın DURDU")
        return 2
    try:
        if a.checks_json:
            metin = a.checks_json.read_text(encoding="utf-8").strip()
            kosular = json.loads(metin) if metin.startswith("[") else [json.loads(s) for s in metin.splitlines() if s]
        else:
            kosular = check_runlari_getir(depo, sha)
        if a.gece_json:
            g = a.gece_json.read_text(encoding="utf-8").strip()
            gece = None if g in ("", "null") else json.loads(g)
        else:
            gece = gece_son_kosu(depo, sozlesme["gece"]["dosya"])
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        print(f"!!! CI durumu OKUNAMADI: {e} — yayın DURDU (fail-closed)")
        return 2
    dur, uyari, yesil = degerlendir(sozlesme, kosular, gece)
    print(f"CI durumu · {depo}@{sha[:12]} · yeşil {len(yesil)} / gerekli {len(sozlesme['gerekli_isler'])}")
    for s in yesil:
        print(f"  ✓ {s}")
    for s in uyari:
        print(f"  UYARI: {s}")
    for s in dur:
        print(f"  ✗ {s}")
    if dur:
        print("!!! YAYIN DURDU — uç commit'in GitHub CI'ı yeşil değil (yukarıdaki işler). Önce CI'ı yeşile getirin.")
        return 1
    print("CI kapısı: tamam (gerekli işlerin hepsi yeşil)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
