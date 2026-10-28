# -*- coding: utf-8 -*-
"""L1-7.2 (firmware kolu · A-47) — STM firmware yorumları var olmayan 48 °C istemci interlock'una / "NTC bayrağını aç" önerisine dayanmaz.

ÖLÇÜLEN (HEAD ebf1c3fe): `firmware/stm32_pemf/Core/Src/main.c:1056` "Kalan tek otomatik katman arayüzdeki 48 °C istemci interlock'udur",
`:1063` "NTC'ler bağlanınca 1 yapıp tezgahta doğrulayın", `:1327` "48 °C istemci interlock'u (CoilParameterPanel.tsx:21,143) buna
bagimlidir"; `Core/Inc/pemf_sensor.h:35` "Kalan tek otomatik katman arayüzdeki 48 °C istemci interlock'udur" ↔ A-47 (2026-09-29): istemci
48 °C interlock'u da KALDIRILDI (`apps/ui/src/components/domain/CoilParameterPanel.tsx` — yalnız görsel uyarı). Okuyan, var olmayan bir
otomatik korumaya güvenirdi. Kod DEĞİŞMEDİ (önişlemci çıktısı önce = sonra); bu kapı yalnız YORUM METNİNİ pinler.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
CORE = KOK / "firmware" / "stm32_pemf" / "Core"

#: Bayat (yanlış) iddialar — STM firmware kaynaklarının HİÇBİRİNDE geçmemeli.
YASAK = (
    (
        r"Kalan tek otomatik katman arayüzdeki 48 °C istemci interlock'udur",
        "48 °C istemci interlock'u VARMIŞ gibi (A-47: kaldırıldı)",
    ),
    (r"48 °C istemci interlock'u \(CoilParameterPanel", "48 °C istemci interlock'u VARMIŞ gibi (A-47)"),
    (r"NTC'ler bağlanınca 1 yap", "NTC bayrağını açma önerisi (A-47: termal kesme YAPILMAYACAK)"),
)


def _kaynaklar() -> list[Path]:
    return sorted(p for p in CORE.rglob("*") if p.suffix in (".c", ".h"))


def test_firmware_yorumlari_bayat_48C_interlock_IDDIASI_TASIMAZ():
    kaynaklar = _kaynaklar()
    assert len(kaynaklar) >= 5, f"aparat: firmware kaynakları bulunamadı ({len(kaynaklar)})"
    bulunan = []
    for p in kaynaklar:
        metin = p.read_text(encoding="utf-8", errors="replace")
        for desen, neden in YASAK:
            if re.search(desen, metin):
                bulunan.append(f"{p.relative_to(KOK).as_posix()}: {neden}")
    assert not bulunan, "bayat firmware yorumu:\n  " + "\n  ".join(bulunan)


def test_firmware_yorumlari_A47_gercegini_SOYLER():
    main = (CORE / "Src" / "main.c").read_text(encoding="utf-8")
    sensor = (CORE / "Inc" / "pemf_sensor.h").read_text(encoding="utf-8")
    assert "HİÇBİR katmanda" in main and "A-47 (sahip, 2026-09-29" in main, "main.c HG-1 bloğu A-47 gerçeğini söylemeli"
    assert "SICAKLIK_UYARI_ESIGI_C" in main and "SICAKLIK_UYARI_ESIGI_C" in sensor, (
        "yorumlar görsel uyarı sabitini anmalı"
    )
    assert "⛔ A-47: NTC termal kesme YAPILMAYACAK" in main, "main.c NTC bloğu A-47 kapanışını söylemeli"
