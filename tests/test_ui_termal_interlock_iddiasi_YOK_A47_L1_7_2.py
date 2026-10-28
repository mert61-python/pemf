# -*- coding: utf-8 -*-
"""L1-7.2 (UI kolu) + i2-F-9 (UI) · A-47 + Y2 — arayüz kaynağı VAR OLMAYAN bir termal korumayı ("interlock", "48 °C'de durdurma
komutu gider") ANLATMAZ.

ÖLÇÜLEN (HEAD `ebf1c3fe`): `apps/ui/src/screens/KpiDashboardScreen.tsx:472-473` "Gerçek termal koruma … (bobin başına interlock,
`CoilParameterPanel`)" ve `apps/ui/src/screens/__tests__/kpiSicaklikDurustlugu.test.tsx:25-27` "interlock bobin BAŞINA çalışır … `>48` eşiğini
geçer ve durdurma komutu gider". GERÇEK: `CoilParameterPanel.tsx:22-27` + `:225` — 48 °C üstü YALNIZ görsel uyarı, istek GÖNDERİLMEZ
(sahip kararı A-47 + Y2; hiçbir katmanda termal kesme yok). Yanlış güvence sınıfı: bir sonraki denetimi / geliştiriciyi var olmayan
korumaya güvendirir ("yorum kapıyı kandırdı" ailesi).

KAPI: (1) yasak iddia YOK — `apps/ui/src` altındaki her TS/TSX dosyasında "interlock" geçen satır ±1 satırlık penceresinde termal bağlam
(termal / °C / sıcaklık / 48 / thermal) TAŞIMAZ (oturum çatışması anlamındaki "409 interlock" serbest); "durdurma komutu gider" + 48 birlikte
geçmez. (2) doğru iddia VAR — iki dosya A-47'yi ve "OTOMATİK TERMAL KORUMA YOK"u söyler; `CoilParameterPanel`'in görsel eşik sabiti 48.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
UI = KOK / "apps" / "ui" / "src"
KPI = UI / "screens" / "KpiDashboardScreen.tsx"
KPI_TEST = UI / "screens" / "__tests__" / "kpiSicaklikDurustlugu.test.tsx"
PANEL = UI / "components" / "domain" / "CoilParameterPanel.tsx"

_TERMAL = re.compile(r"termal|thermal|°C|sıcaklık|sicaklik|\b48\b", re.IGNORECASE)


def _ui_dosyalari():
    for p in sorted(UI.rglob("*")):
        if p.suffix in (".ts", ".tsx") and "node_modules" not in p.parts:
            yield p


def test_KRITIK_ui_kaynaginda_TERMAL_interlock_iddiasi_YOK():
    """MUTASYON: KPI yorumuna (ya da herhangi bir UI dosyasına) "termal koruma … interlock" geri yazılırsa KIRMIZI."""
    taranan = 0
    ihlal = []
    for p in _ui_dosyalari():
        satirlar = p.read_text(encoding="utf-8").splitlines()
        taranan += 1
        for i, s in enumerate(satirlar):
            if "interlock" not in s.lower():
                continue
            pencere = " ".join(satirlar[max(0, i - 1) : i + 2])
            if _TERMAL.search(pencere):
                ihlal.append(f"{p.relative_to(KOK).as_posix()}:{i + 1}: {s.strip()[:120]}")
    assert taranan > 100, f"aparat: apps/ui/src altında yalnız {taranan} TS/TSX dosyası tarandı (vakum)"
    assert not ihlal, (
        "arayüz kaynağı VAR OLMAYAN termal interlock'u anlatıyor (A-47 + Y2: 48 °C üstü yalnız görsel uyarı, otomatik durdurma YOK):\n"
        + "\n".join(ihlal)
    )


def test_KRITIK_48_derecede_DURDURMA_KOMUTU_GIDER_iddiasi_YOK():
    """MUTASYON: "`>48` eşiğini geçer ve durdurma komutu gider" geri yazılırsa KIRMIZI (interlock sözcüğü olmadan da)."""
    for p in (KPI, KPI_TEST, PANEL):
        metin = p.read_text(encoding="utf-8")
        for i, s in enumerate(metin.splitlines()):
            if re.search(r"durdurma komutu gider", s, re.IGNORECASE):
                raise AssertionError(
                    f"{p.name}:{i + 1}: 48 °C'de durdurma komutu gittiği iddiası (A-47: GİTMEZ): {s.strip()[:120]}"
                )


def test_dogru_iddia_VAR_A47_otomatik_termal_koruma_YOK():
    for p in (KPI, KPI_TEST):
        metin = p.read_text(encoding="utf-8")
        assert "OTOMATİK TERMAL KORUMA YOK" in metin and "A-47" in metin, (
            f"{p.name}: A-47 gerçeği (otomatik termal koruma YOK, 48 °C üstü yalnız görsel uyarı) yazılı değil"
        )
    assert re.search(r"const\s+SICAKLIK_UYARI_ESIGI_C\s*=\s*48\s*;", PANEL.read_text(encoding="utf-8")), (
        "CoilParameterPanel görsel uyarı eşiği (48 °C) bulunamadı — yorumların andığı sabit değişmiş"
    )


# TUR 2 (çürütücü kolu): aynı yanlış güvence "interlock" / "durdurma komutu gider" sözcükleri OLMADAN da yazılabilir — "48 °C üstünde bobin otomatik
# olarak durdurulur" KPI yorumunda YAŞIYORDU (mutant `cur172_n1`). Olumlu kip (durdurulur / kesilir / durur / keser; automatically stops / shuts
# down / cuts off) + ±1 satırda termal bağlam → iddia. Olumsuz kip ("durdurulmaz", "otomatik durdurma YOK / KALDIRILDI") desene girmez.
_OTOMATIK_KESME = re.compile(
    r"(?:otomatik|kendiliğinden)\s+(?:olarak\s+)?(?:durdurul(?:ur|uyor)|kesil(?:ir|iyor)|dur(?:ur|uyor)\b|keser\b|kesiyor)"
    r"|durdurma\s+komutu\s+(?:gider|gönderilir)"
    r"|(?:automatically|auto-?)\s*(?:stops?|shuts?\s+(?:down|off)|cuts?\s+off)",
    re.IGNORECASE,
)


def test_KRITIK_ui_kaynaginda_OTOMATIK_termal_DURDURMA_iddiasi_YOK_es_anlamlilar():
    taranan, ihlal = 0, []
    for p in _ui_dosyalari():
        satirlar = p.read_text(encoding="utf-8").splitlines()
        taranan += 1
        for i, s in enumerate(satirlar):
            if not _OTOMATIK_KESME.search(s):
                continue
            pencere = " ".join(satirlar[max(0, i - 1) : i + 2])
            if _TERMAL.search(pencere):
                ihlal.append(f"{p.relative_to(KOK).as_posix()}:{i + 1}: {s.strip()[:120]}")
    assert taranan > 100, f"aparat: yalnız {taranan} TS/TSX dosyası tarandı (vakum)"
    assert not ihlal, (
        "arayüz kaynağı 48 °C'de OTOMATİK durdurma anlatıyor (A-47 + Y2: YOK, yalnız görsel uyarı):\n"
        + "\n".join(ihlal)
    )


def test_KARSIT_KANIT_otomatik_kesme_deseni_OLUMSUZU_yakalamaz():
    assert _OTOMATIK_KESME.search("48 °C üstünde bobin otomatik olarak durdurulur")
    assert _OTOMATIK_KESME.search("the coil automatically stops above 48 °C")
    assert not _OTOMATIK_KESME.search("48 °C'de otomatik durdurma/engelleme KALDIRILDI")
    assert not _OTOMATIK_KESME.search("istek gönderilmez, seans engellenmez / durdurulmaz")
    assert not _OTOMATIK_KESME.search("Otomatik durdurma YOK (sahip kararı)")
