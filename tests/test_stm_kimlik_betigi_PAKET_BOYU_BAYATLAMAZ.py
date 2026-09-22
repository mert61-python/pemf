# -*- coding: utf-8 -*-
# Author: mertaygn
"""Operatöre gösterilen paket boyu KAYNAKLA aynı kalsın — `scripts/stm_firmware_kimligi.py`.

BULGU (2026-09-22, donanım runbook'u türetilirken ölçüldü): betik operatöre **120 bayt**
diyordu; gerçek paket **121 bayt** (2026-09-11'de `unipolar_maskesi` baytı eklendi).

NEDEN ÖNEMLİ — bu betik SAHA TEŞHİS ARACI:
Ürünün KENDİ hata mesajı (`apps/backend/utils/stm32_kimlik.py`) firmware uyumsuzluğunda
operatörü bu betiğe yönlendiriyor. Operatör "bağlı ama hiçbir bobin başlamıyor" arızasında
bunu koşuyor ve ekranda yazan sayıya göre karar veriyor. Yanlış sayı → yanlış teşhis.

⚠️ `scripts/*.py` PAKETE GİRMEZ ama bu betik sahada ELLE koşturulur; paketlenmemiş olması
onu önemsiz yapmaz.

ÇIPA: sayı kaynaktan TÜRETİLMELİ (`STM_PAKET_BOYU`), elle yazılmamalı. Bu kapı hem
türetildiğini hem de belgelenen değerin doğru olduğunu ölçer.

⚠️ KARŞIT KANIT ŞART: eski firmware'in beklediği **88 bayt** TARİHSEL bir olgudur ve
DEĞİŞMEZ. Onu da "kaynaktan türet" diye değiştiren bir düzeltme teşhisi bozar.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils.stm32_transport import STM_PAKET_BOYU  # noqa: E402

BETIK = KOK / "scripts" / "stm_firmware_kimligi.py"


def _kaynak() -> str:
    return BETIK.read_text(encoding="utf-8")


def test_betik_var():
    assert BETIK.is_file(), f"teşhis betiği yok: {BETIK}"


def test_KRITIK_paket_boyu_KAYNAKTAN_turetiliyor():
    """Sayı elle yazılırsa protokol değişiminde SESSİZCE bayatlar — bir kez oldu.

    ⚠️ ÇIPA ADA DEĞİL **IMPORT'A** PİNLİ. İlk yazımda `"STM_PAKET_BOYU" in kaynak` diye
    bakıyordu; mutasyon import'u yerel `STM_PAKET_BOYU = 121` atamasına çevirince dize
    yerinde kaldı ve KAPI YEŞİL GEÇTİ. Yerel atama tam olarak kaçınmak istediğimiz şeydir:
    elle yazılmış sayı.
    """
    k = _kaynak()
    assert re.search(r"from\s+utils\.stm32_transport\s+import\s+.*STM_PAKET_BOYU", k), (
        "betik paket boyunu `utils.stm32_transport`tan IMPORT etmiyor. Elle yazılan sayı "
        "2026-09-11'de 120'de kalmıştı (gerçek 121) ve operatöre yanlış gösterildi."
    )
    assert not re.search(r"^\s*STM_PAKET_BOYU\s*=", k, re.M), (
        "betikte YEREL `STM_PAKET_BOYU = ...` ataması var — import'u gölgeleyip sayıyı yeniden elle yazmaktır"
    )


#: ESKİ (5 bobinli) firmware'in düzeni — TARİHSEL olgu, protokolle birlikte DEĞİŞMEZ.
#: 88 = toplam paket · 84 = CRC'nin hesaplandığı veri bölümü (88 − 4).
#: ⚠️ Bunları "güncelle" diye değiştirmek teşhisin ayırt edici bilgisini yok eder.
#: (Bu küme kapının İLK yazımında eksikti; 84 yanlışlıkla "bayat" sayıldı — ölçüt kusuruydu.)
ESKI_FIRMWARE_DUZENI = {88, 84}


def test_KRITIK_operatore_gosterilen_sayi_DOGRU():
    """Ekrana/belgeye yazılan 'yeni firmware' paket boyu = STM_PAKET_BOYU."""
    k = _kaynak()
    # "NNN bayt" biçimindeki TÜM sayılar; eski firmware düzeni hariç hepsi güncel boy olmalı.
    sayilar = {int(m) for m in re.findall(r"\b(\d{2,4})\s*bayt", k)}
    sayilar -= ESKI_FIRMWARE_DUZENI
    yanlis = {s for s in sayilar if s != STM_PAKET_BOYU}
    assert not yanlis, f"betikte güncel olmayan paket boyu geçiyor: {sorted(yanlis)} (kaynak: {STM_PAKET_BOYU})"


def test_KRITIK_crc_ofseti_DOGRU():
    """CRC alanı, veri bölümünün hemen ardındadır: STM_PAKET_BOYU - 4."""
    k = _kaynak()
    beklenen = STM_PAKET_BOYU - 4
    ofsetler = {int(m) for m in re.findall(r"(\d{2,4})\.\s*ofset", k)}
    yanlis = {o for o in ofsetler if o != beklenen}
    assert not yanlis, f"yanlış CRC ofseti: {sorted(yanlis)} (beklenen {beklenen})"


def test_karsit_kanit_ESKI_firmware_88_KORUNUR():
    """88, eski 5-bobinli firmware'in gerçeğidir — "güncelleme" diye silinmemeli.

    ⚠️ OPERATÖRÜN GÖRDÜĞÜ SATIRA bakılır, dosyanın tamamına değil. İlk yazımda dosya
    genelinde arıyordu; mutasyon sayıyı EKRAN çıktısından silince docstring tablosundaki
    kopya kapıyı YEŞİL BIRAKTI — oysa teşhisi okuyan kişi ekrana bakar.
    """
    k = _kaynak()
    ekran = [s for s in k.splitlines() if "ESKI FIRMWARE YUKLU" in s]
    assert ekran, "eski-firmware ekran satırı kayboldu"
    assert any("88" in s for s in ekran), (
        "operatöre gösterilen satırda 88 bayt yok — teşhisin ayırt edici bilgisi bu; "
        f"onsuz betik 'eski mi yeni mi' sorusunu cevaplayamaz. Görülen: {ekran!r}"
    )


def test_karsit_kanit_kapi_GERCEK_sayiya_bakiyor():
    """Kapının kendi ölçütü doğru mu: bugünkü kaynak 121 vermeli (7 bobin)."""
    assert STM_PAKET_BOYU == 121, (
        f"paket boyu beklenmedik: {STM_PAKET_BOYU}. Protokol değiştiyse bu kapı ve "
        "betik birlikte güncellenmeli — sessizce geçmemeli."
    )
