# -*- coding: utf-8 -*-
# Author: mertaygn
"""SEANSA ÖZEL ALAN KAYDI (masaüstü CSV) — DAVRANIŞSAL kapı.

SAHİP KARARI 2026-09-11: "aktif seans kısmı var en üstte manuel modu başlatınca frekans var
süre var yoğunluk var ordaki yoğunluk değeri stm e bağlı olan SENSÖRDEN GELSİN VE AYNI
ZAMANDA CSV YE KAYDEDİP MASAÜSTÜNE KOYSUN. SEANS ÖZELİNDE OLCAK BU."

Bu dosya YAPISAL değil DAVRANIŞSAL: gerçek `SeansAlanKaydi` çalıştırılır, gerçek dosya
yazılır ve içeriği okunur. Kapının ölçtüğü şey kodun VARLIĞI değil, ÜRETTİĞİ DOSYA.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from servers.seans_alan_kaydi import SeansAlanKaydi, masaustu_dizini


@pytest.fixture()
def kayit(tmp_path, monkeypatch):
    """Masaüstü yerine tmp_path'e yazan taze bir kaydedici."""
    monkeypatch.setattr("servers.seans_alan_kaydi.masaustu_dizini", lambda: (tmp_path, "test"))
    k = SeansAlanKaydi()
    yield k
    k.seans_bitti("test bitti")


def _satirlar(yol: Path) -> list[list[str]]:
    with io.open(yol, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def test_KRITIK_seans_basinca_CSV_olusur_ve_baslik_tasir(kayit, tmp_path):
    yol = kayit.seans_basladi("SEANS-1", {"patient_name": "Karabaş", "intensity": 3.5})
    assert yol is not None and yol.exists(), "CSV olusmadi"
    assert yol.parent == tmp_path
    satirlar = _satirlar(yol)
    duz = [",".join(s) for s in satirlar]
    assert any("SEANS-1" in s for s in duz), "seans kimligi dosyada YOK"
    assert any("Karabaş" in s for s in duz), "hasta adi dosyada YOK"
    # Reçete yoğunluğu ölçümle KARIŞMASIN diye AYRI ve ETİKETLİ durmalı.
    assert any("recete_yogunluk_mt" in s for s in duz), "recete yogunlugu etiketli olarak YOK"
    # ⚠️ ÇIPA TAM LİSTEYE PİNLENMEZ (2026-09-11): işaretli eksen uçları (x_min/x_max/…)
    # eklenince tam eşitlik kırıldı — oysa davranış bozulmamıştı. Sütunlar SONA eklenir
    # (eski dosyalarla açılabilirlik), o yüzden ÖNEK olarak eşleriz: eski sütunların
    # varlığı ve SIRASI korunmalı, yeni sütun eklemek serbest.
    bas = next((s for s in satirlar if s and s[0] == "zaman"), None)
    assert bas is not None, "sutun basligi YOK"
    assert bas[:6] == ["zaman", "gecen_sn", "bobin", "alan_mt", "ornek", "doygun"], (
        f"eski sutunlarin sirasi DEGISTI: {bas[:6]} — eski CSV okuyucular kirilir"
    )


def test_KRITIK_olcumler_SATIR_SATIR_yazilir_sonda_toplu_DEGIL(kayit):
    """Backend seans ortasında çökerse o ana kadarki ölçüm KALMALI.

    ⚠️ Bu deponun kayıtlı arızalarından biri "yalnız sonda yazılıyordu, çökünce hiçbir şey
    kalmıyordu" idi. Kapı, kayıt AÇIKKEN dosyanın diskte dolu olduğunu ölçer.
    """
    yol = kayit.seans_basladi("SEANS-2", {})
    kayit.olcum(6, 1.234, 400, False)
    kayit.olcum(6, 2.500, 398, False)
    # ⚠️ `seans_bitti` CAGRILMADAN okunur — akis hala aciktir.
    satirlar = _satirlar(yol)
    veri = [s for s in satirlar if s and s[0] and not s[0].startswith("#") and s[0] != "zaman"]
    assert len(veri) == 2, f"olcumler diske ANINDA yazilmiyor (bulunan {len(veri)}) -> cokusde KAYBOLUR"
    assert veri[0][2] == "6" and veri[0][3] == "1.234"
    assert veri[1][3] == "2.5"


def test_KRITIK_zirve_SEANS_BOYU_en_buyuk(kayit):
    kayit.seans_basladi("SEANS-3", {})
    for v in (1.0, 8.4, 2.2, 0.1):
        kayit.olcum(6, v, 400, False)
    assert kayit.zirve() == pytest.approx(8.4), "seans tepesi EN BUYUK olcum degil"
    assert kayit.son_deger() == pytest.approx(0.1), "son deger takip edilmiyor"


def test_KRITIK_OLCUM_YOKKEN_zirve_NONE_sifir_DEGIL(kayit):
    """⚠️ 0.0 döndürmek "ölçtük, alan yok" demektir; ölçmediysek None demeliyiz.

    Bu deponun tekrarlayan arızası: ölçülmeyen alanın 0.0 başlangıç değeri aşağı akışta
    "ölçüldü" olarak kaydediliyor ve PDF'e "0.0 ölçüldü" yazdırıyordu.

    MUTASYON: `SeansAlanKaydi.__init__`de `self._zirve = 0.0` yap → KIRMIZI.
    """
    kayit.seans_basladi("SEANS-4", {})
    assert kayit.zirve() is None, "olcum YOKKEN zirve 0.0 -> asagi akis '0.0 mT olculdu' diye kaydeder"
    assert kayit.son_deger() is None


def test_KRITIK_seans_yokken_olcum_YUTULUR(kayit):
    """Boştaki cihazın okuduğu alan bir seansa ait DEĞİLDİR."""
    kayit.olcum(6, 5.0, 400, False)
    assert kayit.zirve() is None, "seans YOKKEN olcum birikiyor -> bir sonraki seansa SIZAR"


def test_KRITIK_yeni_seans_ONCEKININ_tepesini_TASIMAZ(kayit):
    kayit.seans_basladi("SEANS-5", {})
    kayit.olcum(6, 9.9, 400, False)
    assert kayit.zirve() == pytest.approx(9.9)
    kayit.seans_basladi("SEANS-6", {})
    assert kayit.zirve() is None, "onceki seansin tepesi yeni seansa SIZDI"


def test_KRITIK_NaN_ve_sonsuz_SUZULUR(kayit):
    """⚠️ Bozuk bir sayı `max()` ile seans tepesine yerleşirse bir daha ASLA düşmez.

    MUTASYON: `deger != deger` süzgecini kaldır → KIRMIZI (zirve NaN olur).
    """
    kayit.seans_basladi("SEANS-7", {})
    kayit.olcum(6, 2.0, 400, False)
    kayit.olcum(6, float("nan"), 400, False)
    kayit.olcum(6, float("inf"), 400, False)
    z = kayit.zirve()
    assert z == pytest.approx(2.0), f"bozuk sayi zirveye yerlesti: {z}"


def test_KRITIK_bitiste_OZET_yazilir_ve_yol_doner(kayit):
    kayit.seans_basladi("SEANS-8", {})
    kayit.olcum(6, 4.0, 400, True)
    yol = kayit.seans_bitti("operator durdurdu")
    assert yol is not None and yol.exists()
    duz = [",".join(s) for s in _satirlar(yol)]
    assert any("seans_tepe_mt,4.0" in s for s in duz), "ozet satirinda seans tepesi YOK"
    assert any("operator durdurdu" in s for s in duz), "bitis sebebi YAZILMIYOR"
    # Doygunluk gorulduyse dosyanin KENDISI uyarmali (CSV baska makinede acilir).
    assert any("GUVENILMEZ" in s for s in duz), "doygunluk uyarisi dosyaya YAZILMIYOR"


def test_KRITIK_bitis_IKI_KEZ_cagrilabilir(kayit):
    """Dört ayrı stop yolu var; ikisi arka arkaya gelirse patlamamalı."""
    kayit.seans_basladi("SEANS-9", {})
    assert kayit.seans_bitti("bir") is not None
    assert kayit.seans_bitti("iki") is None, "kapali kayit tekrar kapaniyor -> ozet IKI KEZ yazilir"


def test_KRITIK_SERVIS_HESABINDA_masaustune_yazmaz(monkeypatch, tmp_path):
    """⚠️ LocalSystem profilinde "Desktop" sahibin göremeyeceği bir yerdir.

    Backend Windows servisi olarak da koşabiliyor. CSV sessizce
    `C:\\Windows\\System32\\config\\systemprofile\\Desktop`a yazılırsa sahip dosyayı ASLA
    bulamaz ve "kaydetmedi" der.

    MUTASYON: `masaustu_dizini`deki `systemprofile` kontrolünü kaldır → KIRMIZI.
    """
    monkeypatch.setattr("os.path.expanduser", lambda _p: r"C:\Windows\System32\config\systemprofile")
    dizin, gerekce = masaustu_dizini()
    assert "systemprofile" not in str(dizin).lower(), (
        f"servis hesabinda masaustune yaziliyor ({dizin}) -> sahip dosyayi goremez"
    )
    assert "servis" in gerekce, "gerekce bildirimde gosterilebilecek sekilde donmuyor"


def test_KRITIK_dosya_acilamazsa_SEANS_ENGELLENMEZ(monkeypatch, tmp_path):
    """CSV bir kolaylıktır; dolu disk yüzünden tedavi başlamaması kabul edilemez."""
    monkeypatch.setattr("servers.seans_alan_kaydi.masaustu_dizini", lambda: (tmp_path / "yok" / "asla", "test"))
    k = SeansAlanKaydi()
    yol = k.seans_basladi("SEANS-10", {})
    assert yol is None, "acilamayan kayit None dondurmeli"
    k.olcum(6, 1.0, 400, False)  # patlamamali
    assert k.zirve() is None
