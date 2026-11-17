# -*- coding: utf-8 -*-
"""KP-5 C9 / D10 (sahip Y279, 12-11) · istemci (jest) + site (vitest) kapsam dışı bırakma ETİKETLERİ SAYILI — backend Y242 deseni.

Sahip kararı: test yazılamayan (ULAŞILAMAZ) satır yalnız GEREKÇELİ etiketle kapsam dışı bırakılır; savunma kodu SİLİNMEZ; test
yazılabilen satıra etiket YASAK. Biçim (tek satır, JS / TS blok yorumu):
    /* istanbul ignore <next|if|else|file> -- <ETİKET>: <neden> */
ETİKET ∈ {ULASILAMAZ, SAVUNMA, PLATFORM}:
  ULASILAMAZ — dal yapısal olarak girilemez (aynı koşulla pasif / çizilmeyen düğme, her değeri karşılanan `switch` / sözlük),
  SAVUNMA    — çağrılan işlevin SÖZLEŞMESİ fırlatmaz / reddetmez (hatayı içeride yakalar, `fallback` döner); kol yalnız sözleşme
               bozulursa çalışır (sahte ile kurmak olmayan bir durumu test etmek olur),
  PLATFORM   — test ortamı ilkeli olarak koşturamaz (jest `import()`).
Liste SABİT: yeni etiket (sayı artışı), gerekçesiz / bilinmeyen etiket, `v8 ignore` / `c8 ignore` (tek biçim istanbul) → KIRMIZI.
Hem jest (babel-plugin-istanbul) hem vitest (`@vitest/coverage-v8` 4.1.10, ast-v8-to-istanbul) bu ipucunu uygular (KP-5 ölçtü).
Kapı ürün kodunun tamamını tarar (apps/ui/src · apps/ui/app · apps/web/src · apps/web/api; testler hariç).
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ETIKETLER = ("ULASILAMAZ", "SAVUNMA", "PLATFORM")
#: Herhangi bir kapsam ipucu (biçimi ne olursa olsun) — sayılır.
IPUCU = re.compile(r"\b(istanbul|v8|c8)\s+ignore\b")
#: Kabul edilen tek biçim.
ETIKETLI = re.compile(
    r"/\* istanbul ignore (?P<tur>next|if|else|file) -- (?P<etiket>[A-Z]+): (?P<neden>\S[^*]{11,}?) \*/"
)
#: KP-5 C9 / D10 — dosya → [(tür, ETİKET)] SABİT (mutant kaynaktan okunmaz). Gerekçeler etiketin kendisinde (satır içi).
BEKLENEN: dict[str, list[tuple[str, str]]] = {
    # C9 istemci (KP-4 B1 ölçümü + KP-5 yeniden ölçüm; satır içi gerekçe etiketin kendisinde)
    "apps/ui/src/components/domain/AiProPanel.tsx": [
        ("if", "ULASILAMAZ"),
        ("if", "ULASILAMAZ"),
        ("if", "SAVUNMA"),
        ("next", "SAVUNMA"),  # KP-7 B: getClientInstanceId reddetmez
        ("next", "SAVUNMA"),  # KP-7 B: apiPost fırlatmaz (AI Pro durdurma)
        ("if", "ULASILAMAZ"),  # KP-7 B2: approveAndStart — öneri yalnız kimliğiyle, pencere yalnız öneriyle
        ("if", "ULASILAMAZ"),  # KP-7 B2: rejectProposal — aynı
    ],
    # KP-7 B2 (madde 7): işleyici korumaları düğmenin disabled / çizim koşuluyla AYNI
    "apps/ui/src/components/domain/KabinKalibrasyonuKarti.tsx": [("if", "ULASILAMAZ")] * 9,
    "apps/ui/src/components/domain/KabinKamerasiKarti.tsx": [("if", "ULASILAMAZ")]
    * 2,  # KP-7 B2: tara / seç kilitliyken pasif
    "apps/ui/src/components/domain/ObservationNotesModal.tsx": [("next", "ULASILAMAZ")],
    "apps/ui/src/components/domain/OperatorSwitcher.tsx": [("if", "ULASILAMAZ")] * 3,  # KP-7 B2: PIN / ad korumaları
    "apps/ui/src/components/domain/SessionDetailModal.tsx": [("next", "SAVUNMA"), ("if", "ULASILAMAZ")],
    "apps/ui/src/components/domain/SurusKipiSecici.tsx": [("next", "SAVUNMA")],
    "apps/ui/src/components/ui/JetonRozeti.tsx": [("next", "SAVUNMA")],
    "apps/ui/src/components/ui/NotificationCenter.tsx": [("next", "SAVUNMA")],
    "apps/ui/src/hooks/useSessionControl.ts": [("if", "ULASILAMAZ")],
    "apps/ui/src/screens/AiHubScreen.tsx": [
        ("next", "ULASILAMAZ"),
        ("next", "SAVUNMA"),
        ("if", "ULASILAMAZ"),
        ("if", "ULASILAMAZ"),
        ("if", "ULASILAMAZ"),
        ("next", "SAVUNMA"),
    ],
    "apps/ui/src/screens/ControlScreen.tsx": [
        ("if", "ULASILAMAZ"),
        ("next", "SAVUNMA"),
    ],  # KP-7 B: stopSession reddetmez
    "apps/ui/src/screens/SettingsScreen.tsx": [("next", "SAVUNMA")],
    "apps/ui/src/services/apiClient.ts": [("next", "ULASILAMAZ")],
    "apps/ui/src/services/desktopSession.ts": [("next", "SAVUNMA")],
    # KP-7 B2: yeniden bağlanma zinciri — çağıranlar aynı korumadan geçer / kapatma zamanlayıcıları temizler
    "apps/ui/src/services/wsClient.ts": [("if", "ULASILAMAZ"), ("if", "ULASILAMAZ")],
    # KP-7 B (madde 7): setStoredDeviceId ×2 · discoverMdns reddetmez
    "apps/ui/src/services/discovery.ts": [("next", "SAVUNMA"), ("next", "SAVUNMA"), ("next", "SAVUNMA")],
    # KP-7 B (madde 7): kayitliHemen · hafif yoklama reddetmez
    "apps/ui/src/context/LiveDataContext.tsx": [("next", "SAVUNMA"), ("next", "SAVUNMA")],
    "apps/ui/src/services/updates.ts": [("next", "SAVUNMA")],
    "apps/ui/src/tembelEkranlar.ts": [("file", "PLATFORM")],
    "apps/ui/src/theme/fonts.ts": [("next", "SAVUNMA")],
    # D10 site
    "apps/web/src/components/AppScreenshots.tsx": [("if", "ULASILAMAZ")],
    "apps/web/src/components/DownloadStats.tsx": [("next", "SAVUNMA")],
    "apps/web/src/lib/usageStats.ts": [("if", "SAVUNMA")],
    "apps/web/src/pages/Pricing.tsx": [("if", "ULASILAMAZ")],
}


def _urun_dosyalari() -> list[str]:
    cikti = subprocess.run(
        # izlenmeyen YENİ dosya da (commit öncesi kapıda) sayılır
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "apps/ui/src",
            "apps/ui/app",
            "apps/web/src",
            "apps/web/api",
        ],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return sorted(
        p
        for p in cikti.splitlines()
        if p.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
        and "/__tests__/" not in p
        and not re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", p)
    )


def _etiketler() -> tuple[dict[str, list[tuple[str, str]]], list[str]]:
    bulunan: dict[str, list[tuple[str, str]]] = {}
    sorun: list[str] = []
    for yol in _urun_dosyalari():
        for no, satir in enumerate((KOK / yol).read_text(encoding="utf-8").splitlines(), 1):
            if not IPUCU.search(satir):
                continue
            m = ETIKETLI.search(satir)
            if not m or m.group("etiket") not in ETIKETLER:
                sorun.append(f"{yol}:{no}: biçimsiz / bilinmeyen etiket: {satir.strip()[:140]}")
                continue
            bulunan.setdefault(yol, []).append((m.group("tur"), m.group("etiket")))
    return bulunan, sorun


def test_KRITIK_istemci_site_etiketleri_GEREKCELI_ve_SAYILI():
    bulunan, sorun = _etiketler()
    assert not sorun, (
        "gerekçesiz / biçimsiz kapsam ipucu (biçim: /* istanbul ignore <tür> -- ETİKET: neden */):\n" + "\n".join(sorun)
    )
    fazla = {y: v for y, v in bulunan.items() if Counter(v) != Counter(BEKLENEN.get(y, []))}
    eksik = {y: v for y, v in BEKLENEN.items() if y not in bulunan}
    assert not fazla and not eksik, (
        "etiket listesi DEĞİŞTİ — yeni ULAŞILAMAZ satır BİLİNÇLİ eklenir (test yazılabilen satıra etiket YASAK):\n"
        f"  beklenenden farklı: {fazla}\n  kaybolan: {eksik}"
    )


def test_etiket_toplami_ve_sinif_dagilimi_SABIT():
    toplam = Counter(e for v in BEKLENEN.values() for _, e in v)
    # KP-5 kapanış: 27 = ULASILAMAZ 13 + SAVUNMA 13 + PLATFORM 1 (sayı yalnız BİLİNÇLİ değişir)
    assert toplam == Counter({"ULASILAMAZ": 31, "SAVUNMA": 21, "PLATFORM": 1}), (
        toplam
    )  # KP-7 B: SAVUNMA 13 → 21 · B2: ULASILAMAZ 13 → 31
    assert set(toplam) <= set(ETIKETLER)


def test_KARSIT_desen_bicimsiz_ipuclarini_yakalar(tmp_path):
    for kotu in (
        "/* istanbul ignore next */",
        "// istanbul ignore next -- ULASILAMAZ: satır yorumu biçimi kabul edilmez",
        "/* v8 ignore next -- ULASILAMAZ: v8 ipucu tek biçim değil */",
        "/* istanbul ignore next -- BILINMEYEN: bilinmeyen sınıf adı kabul edilmez */",
        "/* istanbul ignore next -- ULASILAMAZ: kısa */",
    ):
        m = ETIKETLI.search(kotu)
        assert IPUCU.search(kotu) and (not m or m.group("etiket") not in ETIKETLER), kotu
    iyi = "/* istanbul ignore if -- SAVUNMA: çağrılan işlev hiçbir yolda reddetmez (fallback) */"
    m = ETIKETLI.search(iyi)
    assert m and m.group("etiket") == "SAVUNMA" and m.group("tur") == "if"
