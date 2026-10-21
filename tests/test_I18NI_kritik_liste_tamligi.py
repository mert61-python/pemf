# -*- coding: utf-8 -*-
"""I18NI-A1.3 — T11 sınıfı (bobin enerjileme / durdurma onayı / ACİL DURDUR mandal düğmesi / bayat bağlantı / doz uyarısı / seans-güncelleme
engeli) güvenlik metinleri `i18n/kritik-anahtarlar.json` → `anahtarlar`'da OLMALI. Listede olmayan metin K-5'in "kritik anahtar iki dilde
dolu" denetiminden, "her kritik anahtar için iki dilde jest testi + ekran kanıtı" kuralından ve sahip / hoca onayına çıkan TR / EN
tablosundan (`_inceleme/kritik_tablo.tsv`) KAÇAR.

Ölçüm: `_inceleme/araclar/kritik_eksik_tara.py` + `kritik_adalan_tara.py` + `kritik_ai_tara.py` (desen + ad alanı taraması) → elle sınıflama.
Her satırın kaynağı ve gerekçesi `_inceleme/kritik_eksik.tsv` (ajan A1; rapor DUZELTME-I18N-INCELEME.md). KALICI KAPI (14-I18N-INCELEME):
uçta (göç sonu) 30 / 30 KIRMIZIYDI; liste tamamlandı — bu güvenlik metinlerinden biri kritik listeden düşerse KIRMIZI.

S-I18NI.1: ACİL DURDUR mandal bandının "Sıfırla" düğmesi Ayarlar PWM düğmesinin anahtarını (`ayarlar.bakim.pwmSifirla`) ödünç alıyordu
(KURALLAR §1 "farklı anlam → ayrı anahtar"; PWM düğmesinin adı değişirse mandal düğmesi ve "önce 'Sıfırla'" metni ayrışırdı) → kendi
anahtarı `guvenlik.mandal.sifirla` (TR / EN programla kopyalandı, bayt bayt aynı). Bant YALNIZ `guvenlik.*` anahtarı kullanır.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

# (yuzey, anahtar) — anahtar kökü (çoğulda `_one/_other` olmadan)
EKSIK = [
    # Ayarlar → Donanım Bakım: self-test bobinleri ENERJİLER (hayvan kabinde olmamalı); PWM sıfırlama = tüm çıkışları DURDURMA
    ("arayuz", "ayarlar.bakim.selfTestGovde"),
    ("arayuz", "ayarlar.bakim.selfTestBaslik"),
    ("arayuz", "ayarlar.bakim.selfTestBaslat"),
    ("arayuz", "ayarlar.bakim.selfTestGonderildi"),
    ("arayuz", "ayarlar.bakim.selfTestGonderilemedi"),
    ("arayuz", "ayarlar.bakim.pwmBaslik"),
    ("arayuz", "ayarlar.bakim.pwmGovde"),
    ("arayuz", "ayarlar.bakim.pwmSifirlandi"),
    ("arayuz", "ayarlar.bakim.pwmBasarisiz"),
    # Ayarlar PWM sıfırlama (tüm çıkışları durdurur) onay düğmesi
    ("arayuz", "ayarlar.bakim.pwmSifirla"),
    # ACİL DURDUR mandal bandının "Sıfırla" düğmesi + onay düğmesi (S-I18NI.1: kendi anahtarı) + "Sıfırlanıyor…"
    ("arayuz", "guvenlik.mandal.sifirla"),
    ("arayuz", "guvenlik.mandal.sifirlaniyor"),
    # Aktif seans kartı: bağlantı bayat / veri doğrulanmadı (eşdeğeri `ana.kpi.bayatUyari` LİSTEDE)
    ("arayuz", "seans.kart.bayatBaglanti"),
    ("arayuz", "seans.kart.veriDogrulanmadi"),
    # Doz uyarıları
    ("arayuz", "kontrol.ekran.literaturYok"),
    ("arayuz", "kontrol.emDoz.pikselNotu"),
    ("arayuz", "kontrol.panel.sicaklikYuksekEtiketi"),
    # Sunucu (PDF / CSV / API) seans durumu — arayüzdeki eşleri LİSTEDE (seans.durum.emergency_stopped …)
    ("sunucu", "seans.durum.emergency_stopped"),
    ("sunucu", "seans.durum.hardware_rejected"),
    ("sunucu", "seans.durum.aborted_due_to_power"),
    # Seans sürerken güncelleme / onarım / kaldırma engeli — arayüz eşi `guncelleme.bilgi.seansSuruyor` LİSTEDE
    ("sunucu", "guncelleme.apply.tedaviSuruyor"),
    ("sunucu", "guncelleme.apply.indirmedeTedavi"),
    ("sunucu", "guncelleme.rollback.tedaviSuruyor"),
    ("sunucu", "guncelleme.rollback.indirmedeTedavi"),
    ("launcher", "rust.hata.guncellemeSeansSuruyor"),
    ("launcher", "rust.hata.guncellemeBackendYanitsiz"),
    ("launcher", "rust.hata.kurulumBackendYanitsiz"),
    ("launcher", "rust.hata.onarimSeansSuruyor"),
    ("launcher", "rust.hata.profilKaldirmaSeansSuruyor"),
    ("launcher", "rust.hata.seansBasladiGuncellemeErtelendi"),
    ("launcher", "ui.rtBusy"),
]


def _liste():
    d = json.loads((KOK / "i18n/kritik-anahtarlar.json").read_text(encoding="utf-8"))
    return {(a["yuzey"], a["anahtar"]) for a in d["anahtarlar"]}


def _katalog(yuzey):
    from scripts.i18n import ortak  # K-5'in kendi yükleyicisi

    return ortak.duzlestir(ortak.katalog_yukle(yuzey, "tr"))


@pytest.mark.parametrize("yuzey,anahtar", EKSIK, ids=[f"{y}:{a}" for y, a in EKSIK])
def test_guvenlik_metni_kritik_listede(yuzey, anahtar):
    kat = _katalog(yuzey)
    assert anahtar in kat or f"{anahtar}_one" in kat, f"sonda çürük: {yuzey}:{anahtar} katalogda yok"
    assert (yuzey, anahtar) in _liste(), (
        f"güvenlik metni kritik listede YOK (K-5 / onay tablosu dışı): {yuzey}:{anahtar} = {kat.get(anahtar)!r}"
    )


def test_mandal_bandi_yalniz_guvenlik_anahtarlari():
    """S-I18NI.1: mandal bandı (ACİL DURDUR) başka ekranın anahtarını ödünç almaz — kullandığı her anahtar `guvenlik.` ile başlar."""
    import re

    src = (KOK / "apps/ui/src/components/ui/EstopMandalBandi.tsx").read_text(encoding="utf-8")
    anahtarlar = set(re.findall(r"""\bt\(\s*["']([a-zA-Z0-9_.]+)["']""", src))
    assert {"guvenlik.mandal.sifirla", "guvenlik.mandal.baslik"} <= anahtarlar, anahtarlar
    yabanci = sorted(a for a in anahtarlar if not a.startswith("guvenlik."))
    assert not yabanci, f"mandal bandı başka ekranın anahtarını kullanıyor: {yabanci}"
