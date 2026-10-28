# -*- coding: utf-8 -*-
"""SON-A3.51 · A-47 — yayın adayının KULLANICIYA GİDEN sürüm notları var olmayan bir termal korumayı anlatmaz ve kaldırılan 48 °C otomatik
durdurmasını söyler.

ÖLÇÜLEN (HEAD `8b002fc0`, 22-SON A3b): `CHANGELOG.md` aday `## app 1.9.51` girdisi (`15aa121b`, 2026-09-11 — A-47'den ÖNCE yazıldı; YH D1
`b9bac7e6` başlığı bu girdiyi adayın notu olarak benimser) "yan bobinlerdeki tek otomatik sıcaklık koruması da (arayüzdeki 48 °C eşiği) ölçüm
ulaşmadığı için çalışamıyordu" der. GERÇEK: 1.9.50 istemcisi (`9749d5d1:pf/src/components/domain/CoilParameterPanel.tsx:21,146-157`
`SAFE_TEMP_CUTOFF = 48` → "bobin otomatik durduruldu") 48 °C'de bobini durduruyordu; aday sürümde bu A-47 + Y2 ile TÜM katmanlardan kaldırıldı
(`kontrol.json` `sicaklikUyari`: "otomatik durdurma yok"). Yani not, sahada 1.9.50 → 1.9.51 güncellemesiyle KAYBOLAN bir korumayı "sensör
düzeltmesiyle yeniden çalışan" koruma gibi sunuyor; kaldırılış hiçbir notta (CHANGELOG, `docs/surum_notlari.json`) yok. Mevcut A-47 metin
kapıları (UI / backend / firmware / site) CHANGELOG ve sürüm notlarını taramıyordu.

KAPI: (1) yasak iddia YOK — `CHANGELOG.md`'nin YAYINLANMAMIŞ (`YAYINLANMADI` / `YAYIN ADAYI` başlıklı) bölümleri + A-47'nin ilk sürümü
`app 1.9.51` bölümü (yayınlanınca başlığı tarihe döner; notu yine doğru kalmalı) + `docs/surum_notlari.json` app 1.9.51 (TR + EN) cümle
cümle: termal koruma / otomatik sıcaklık koruması / 48 °C'de durdurulur iddiası olumsuzlanmadan geçmez. (2) doğru iddia VAR — aynı
bölüm ve iki dilli not 48 °C otomatik durdurmasının KALDIRILDIĞINI söyler. YAYINLANMIŞ geçmiş bölümler taranmaz (o günün gerçeği).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CHANGELOG = KOK / "CHANGELOG.md"
NOTLAR = KOK / "docs" / "surum_notlari.json"
#: A-47 (48 °C otomatik durdurma kaldırıldı) sahaya İLK bu sürümle çıkar — sabit (versions.json ilerlese de bu sürümün notu doğru kalmalı).
A47_ILK_SURUM = "1.9.51"
#: Kanal başlığı ` — `dan ÖNCE (test_version_visibility `_buildid_bulgulari` ile aynı kural): "## launcher 1.9.52 … (app 1.9.51 ile
#: birlikte)" başlığı app bölümü DEĞİLDİR.
_A47_BASLIK = re.compile(r"^##[^\n—]*\bapp\s+" + re.escape(A47_ILK_SURUM) + r"\b")

# Olumlu termal koruma iddiası (TR + EN). Olumsuz kip aşağıdaki _OLUMSUZ ile ayrılır.
_IDDIA = re.compile(
    r"(otomatik|tek)\s+(sıcaklık|termal|ısı)\s+koruma"
    r"|termal\s+(koruma|kesme|interlock|kilit)"
    r"|sıcaklık\s+(koruması|kesmesi)"
    r"|48\s*°C[^.]{0,80}?(koruma|kesme|durdurulur|durdurur|kesilir|kilitlenir)"
    r"|(koruma|kesme)\w*[^.]{0,40}?48\s*°C"
    r"|(automatic|thermal|temperature)\s+(protection|cut-?off|shut-?down|interlock)"
    r"|(stops?|shuts?\s+down|cuts?\s+off)\s+(the\s+coil\s+)?automatically[^.]{0,40}?48\s*°C",
    re.IGNORECASE,
)
_OLUMSUZ = re.compile(
    r"\byok(tur)?\b|kaldırıl|uygulanmaz|durdurulmaz|durdurmaz|bulunmaz"
    r"|\bno\s+(longer|automatic)\b|\bremoved\b|\bnot\s+(stop|cut|shut)|\bdoes\s+not\b|\bdoesn't\b",
    re.IGNORECASE,
)
# Doğru iddia: 48 °C + otomatik durdurma + olumsuz (TR) / removed-no longer (EN).
_DOGRU_TR = re.compile(
    r"48\s*°C[^.]{0,120}?otomatik[^.]{0,40}?durdur\w*[^.]{0,60}?(kaldırıl|\byok\b)"
    r"|otomatik[^.]{0,40}?durdur\w*[^.]{0,60}?(kaldırıl|\byok\b)[^.]{0,120}?48\s*°C",
    re.IGNORECASE,
)
_DOGRU_EN = re.compile(
    r"(automatic\w*[^.]{0,40}?stop\w*[^.]{0,80}?(removed|no longer)|no longer[^.]{0,40}?stop\w*[^.]{0,40}?automatic)[^.]{0,80}?48\s*°C"
    r"|48\s*°C[^.]{0,120}?(automatic\w*[^.]{0,40}?stop\w*[^.]{0,80}?(removed|no longer))",
    re.IGNORECASE,
)


def _bolumler(metin: str) -> list[tuple[str, str]]:
    """`## ` başlıklı bölümler: [(başlık, gövde)]. HTML yorumu (`<!-- … -->`) okura GÖRÜNMEZ → düşülür (doğru iddia yorumda saklanamaz)."""
    metin = re.sub(r"<!--.*?-->", "", metin, flags=re.S)
    parcalar = re.split(r"^(## [^\n]*)\n", metin, flags=re.M)
    return [(parcalar[i], parcalar[i + 1]) for i in range(1, len(parcalar) - 1, 2)]


def _aday_bolumleri(metin: str) -> list[tuple[str, str]]:
    return [(b, g) for b, g in _bolumler(metin) if re.search(r"YAYINLANMADI|YAYIN ADAYI", b) or _A47_BASLIK.search(b)]


def _cumleler(metin: str) -> list[str]:
    duz = re.sub(r"\s+", " ", metin)
    return [c.strip() for c in re.split(r"(?<=[.!?])\s+|\s*---\s*", duz) if c.strip()]


def yanlis_iddialar(metin: str) -> list[str]:
    return [c for c in _cumleler(metin) if _IDDIA.search(c) and not _OLUMSUZ.search(c)]


def _app_notu() -> dict:
    kayit = (json.loads(NOTLAR.read_text(encoding="utf-8")).get("app") or {}).get(A47_ILK_SURUM)
    assert isinstance(kayit, dict), f"docs/surum_notlari.json: app {A47_ILK_SURUM} notu yok"
    return kayit


def test_KRITIK_aday_CHANGELOG_ve_surum_notunda_TERMAL_KORUMA_iddiasi_YOK():
    """MUTASYON: aday bölüme "otomatik sıcaklık koruması (48 °C eşiği)" ya da EN notta "thermal protection" yazılırsa KIRMIZI."""
    aday = _aday_bolumleri(CHANGELOG.read_text(encoding="utf-8"))
    assert any(_A47_BASLIK.search(b) for b, _ in aday), (
        f"aparat: CHANGELOG'da '## app {A47_ILK_SURUM}' bölümü bulunamadı (vakum)"
    )
    ihlal = [f"{b[:60]} :: {c[:200]}" for b, g in aday for c in yanlis_iddialar(g)]
    notu = _app_notu()
    ihlal += [
        f"surum_notlari app {A47_ILK_SURUM} {alan} :: {c[:200]}"
        for alan in ("notes", "notes_en")
        for c in yanlis_iddialar(notu.get(alan, ""))
    ]
    assert not ihlal, (
        "aday sürüm notu VAR OLMAYAN termal korumayı anlatıyor (A-47 + Y2: bobin 1–7'de otomatik sıcaklık durdurması YOK, 48 °C üstü yalnız "
        "uyarı):\n" + "\n".join(ihlal)
    )


def test_KRITIK_A47_ilk_surum_notu_48C_OTOMATIK_DURDURMANIN_KALDIRILDIGINI_soyler():
    """1.9.50 istemcisi 48 °C'de bobini durduruyordu; 1.9.51 durdurmuyor → güncelleyen klinik bunu sürüm notundan öğrenmeli (TR + EN)."""
    bolum = [g for b, g in _bolumler(CHANGELOG.read_text(encoding="utf-8")) if _A47_BASLIK.search(b)]
    assert len(bolum) == 1, f"CHANGELOG'da '## app {A47_ILK_SURUM}' bölümü tek değil: {len(bolum)}"
    assert _DOGRU_TR.search(re.sub(r"\s+", " ", bolum[0])), (
        f"CHANGELOG app {A47_ILK_SURUM}: 48 °C otomatik durdurmanın KALDIRILDIĞI yazmıyor (1.9.50'de vardı — sessiz güvenlik davranışı değişikliği)"
    )
    notu = _app_notu()
    assert _DOGRU_TR.search(notu.get("notes", "")), (
        f"surum_notlari app {A47_ILK_SURUM} TR: 48 °C otomatik durdurma kaldırıldı yazmıyor"
    )
    assert _DOGRU_EN.search(notu.get("notes_en", "")), (
        f"surum_notlari app {A47_ILK_SURUM} EN: automatic 48 °C stop removed yazmıyor"
    )


def test_KARSIT_arac_olumlu_iddiayi_yakalar_olumsuzu_ve_YAYINLANMIS_gecmisi_gecirir():
    """Aracın kör olmadığı sentetik girdiyle: olumlu iddia (TR / EN) yakalanır; olumsuz kip ve yayınlanmış geçmiş bölüm serbest."""
    assert yanlis_iddialar("Yan bobinlerdeki tek otomatik sıcaklık koruması da (arayüzdeki 48 °C eşiği) çalışamıyordu.")
    assert yanlis_iddialar("The coil has thermal protection at 48 °C.")
    assert yanlis_iddialar("48 °C üstünde bobin otomatik olarak durdurulur.")
    assert not yanlis_iddialar("48 °C'de otomatik durdurma KALDIRILDI; yalnız uyarı çıkar, seans durdurulmaz.")
    assert not yanlis_iddialar("Automatic coil stop at 48 °C has been removed; only a warning is shown.")
    ch = (
        "## launcher 9.9.9 · mobile 9.9.9 — YAYIN ADAYI (YAYINLANMADI; app 1.9.51 ile birlikte)\n\nmetin\n\n"
        f"## app {A47_ILK_SURUM} — YAYINLANMADI\n\nTermal koruma 48 °C'de bobini keser.\n\n"
        "## app 1.9.48 — 2026-09-11\n\nArayüzdeki 48 °C termal koruma bobini durdurur.\n"
    )
    aday = _aday_bolumleri(ch)
    assert [b.split(" — ")[0] for b, _ in aday] == ["## launcher 9.9.9 · mobile 9.9.9", f"## app {A47_ILK_SURUM}"], aday
    assert [b for b, _ in _bolumler(ch) if _A47_BASLIK.search(b)] == [f"## app {A47_ILK_SURUM} — YAYINLANMADI"], (
        "launcher başlığındaki '(app 1.9.51 ile birlikte)' app bölümü sayıldı"
    )
    assert [c for _, g in aday for c in yanlis_iddialar(g)] == ["Termal koruma 48 °C'de bobini keser."]
    tarihli = ch.replace(f"## app {A47_ILK_SURUM} — YAYINLANMADI", f"## app {A47_ILK_SURUM} — 2026-11-01")
    assert len(_aday_bolumleri(tarihli)) == 2, (
        "A-47'nin ilk sürümü yayınlanıp başlığı tarihe dönünce taramadan ÇIKMAMALI"
    )
