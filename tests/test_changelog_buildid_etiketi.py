# Author: mertaygn, cglrgrkn
"""CHANGELOG `buildId` ETİKETİ — 2. tur denetimi bulgu [5.5] (2026-08-20).

ÖLÇÜLEN DURUM: 1.9.16 ve 1.9.17 girdileri "Paket kimliği (buildId)" diye base.zip (monolith)
sha'sını ilan ediyordu. Oysa katmanlı kurulumda launcher `PEMF_BASE_SHA` olarak APP katmanının
sha'sını geçirir (install.rs: paketler.app boş değilse app; flow.rs base kaydını siler) →
sahadaki TÜM güncel cihazlar `/api/health`te app-katmanı sha'sını raporlar. Destek, CHANGELOG'un
"buildId" dediği değeri sahada ARAYAMAZ (ya da sahadan gelen kimliği CHANGELOG'da bulamaz) —
"hangi ikili sahada" sorusu yanlış cevaplanır. Mevcut CI kapısı yalnız base sha'nın METİNDE
geçmesini kilitlediği için ayrışmayı göremiyordu.

SÖZLEŞME: en üstteki app girdisinin `buildId` etiketi = manifest `layers.win-x64.app.sha256`in
ilk 12 hanesi (cihazın GERÇEKTEN raporladığı değer). base.zip sha'sı ayrıca yazılabilir ama
`buildId` diye ETİKETLENEMEZ.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def test_KRITIK_en_ustteki_buildId_sahadaki_kimlikle_AYNI():
    manifest = json.loads((KOK / "pemf-app-packages" / "manifest.json").read_text(encoding="utf-8"))
    saha_buildid = manifest["layers"]["win-x64"]["app"]["sha256"][:12]

    ch = (KOK / "CHANGELOG.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Paket kimliği \(`buildId`[^)]*\):\s*`([0-9a-f]{12})`", ch)
    assert m, "CHANGELOG'da 'Paket kimliği (buildId...)' satırı bulunamadı — biçim değişti, kapıyı güncelle"
    assert m.group(1) == saha_buildid, (
        f"CHANGELOG buildId `{m.group(1)}` ≠ sahadaki cihazların raporladığı `{saha_buildid}` "
        f"(katmanlı kurulumda buildId = app-katmanı sha'sı; base.zip sha'sını buildId diye "
        f"etiketlemek destek eşleştirmesini kırar — bulgu [5.5])"
    )
