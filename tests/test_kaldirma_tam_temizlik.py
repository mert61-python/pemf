# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KALDIRMA ARKASINDA YETİM ARTEFAKT BIRAKMAZ — kaldırma denetimi 2026-08-29.

Client kaldırıldıktan sonra makine denetlendi. Kurulum dizinleri, servisler, süreçler,
zamanlanmış görevler ve kayıt defteri TEMİZDİ; hasta verisi (KVKK) doğru şekilde korunmuştu.
İki artefakt geride kaldı:

  1. **Güvenlik duvarı kuralları** — `PEMF Backend API` + `PEMF UDP Discovery` makinede kaldı ve
     artık VAR OLMAYAN bir exe'yi işaret ediyordu. Kök neden: kuralı EKLEYEN kod vardı
     (`firewall::ekleme_betigi`), SİLEN kod HİÇ YAZILMAMIŞTI. NSIS kancasının kendi notu bunu
     "ayrı ADMIN 'PEMF Backend' uninstaller'ının işi" sayıyordu — ama backend'i CLIENT kuruyor;
     o ayrı admin kurulumu hiç yapılmamış bir makinede kurallar HİÇBİR kaldırıcıya ait değildi.
  2. **`%LOCALAPPDATA%\\PEMF_System`** (hotspot.log) — ayak izi tanımında `Kvkk=$false`, yani
     tıbbi veri DEĞİL ve silinmeliydi; hiçbir kaldırma yolu ona dokunmuyordu.

⚠️ İkisi de "temiz kaldırma" iddiasını zedeliyordu ve hiçbir teste takılmamıştı: mevcut kapılar
kaldırmanın SİLDİKLERİNİ kilitliyor, SİLMEDİKLERİNİ kimse ölçmüyordu.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_FIREWALL_RS = _KOK / "launcher" / "core" / "src" / "firewall.rs"
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_HOOKS = _KOK / "launcher" / "app" / "windows" / "hooks.nsi"
_FOOTPRINT = _KOK / "scripts" / "pemf_footprint.ps1"


# ── 1) Firewall: eklenen her kuralın SİLİNEN karşılığı olmalı ────────────────


def test_KRITIK_firewall_SILME_betigi_VAR():
    """Kural ekleyen kodun silen karşılığı olmadan 'temiz kaldırma' mümkün değil."""
    kaynak = _FIREWALL_RS.read_text(encoding="utf-8")
    assert "pub fn silme_betigi" in kaynak, (
        "firewall kuralı EKLENİYOR ama SİLEN kod yok → kaldırmadan sonra yetim kural kalır"
    )


def test_KRITIK_eklenen_HER_kural_silme_betiginde_de_VAR():
    """Yeni bir kural eklenip silme listesine yazılmazsa aynı sızıntı tekrar eder."""
    kaynak = _FIREWALL_RS.read_text(encoding="utf-8")
    sabitler = re.findall(r'pub const (KURAL_\w+): &str = "([^"]+)"', kaynak)
    assert sabitler, "kural adı sabitleri bulunamadı (çıpa kaymış olabilir)"

    def _govde(ad: str) -> str:
        i = kaynak.find(f"pub fn {ad}")
        assert i != -1, f"{ad} yok"
        j = kaynak.find("\n}", i)
        return kaynak[i:j]

    silme = _govde("silme_betigi")
    for sabit, deger in sabitler:
        assert sabit in silme, f"'{deger}' kuralı ekleniyor ama silme betiğinde YOK → kaldırmadan sonra geride kalır"


def test_KRITIK_kaldirma_akisi_firewall_temizligini_CAGIRIYOR():
    """⚠️ ZAYIF-ÇIPA KORUMASI: silme betiği var olabilir ama ÇAĞRILMIYORSA hiçbir şey değişmez."""
    kaynak = _MAIN_RS.read_text(encoding="utf-8")
    i = kaynak.find("async fn uninstall(")
    assert i != -1, "uninstall komutu bulunamadı"
    govde = kaynak[i : i + 3000]
    assert "silme_betigi" in govde, "kaldırma akışı firewall temizliğini çağırmıyor → kurallar makinede kalır"


def test_KRITIK_firewall_temizligi_kaldirmayi_DUSURMEZ():
    """Kullanıcı UAC'yi reddederse kaldırma NORMAL devam etmeli.

    Yetim bir firewall kuralı, kaldırmanın yarıda kesilmesini haklı çıkarmaz."""
    kaynak = _MAIN_RS.read_text(encoding="utf-8")
    i = kaynak.find("silme_betigi")
    assert i != -1
    pencere = kaynak[max(0, i - 400) : i + 400]
    assert "if let Err" in pencere or "let _ =" in pencere, (
        "firewall temizliğinin hatası YUTULMUYOR — UAC reddedilirse kaldırma düşer"
    )
    assert "?;" not in pencere.split("silme_betigi")[1][:120], (
        "firewall temizliği `?` ile yayılıyor → hata kaldırmayı düşürür"
    )


def test_KRITIK_WINDOWSUN_KENDI_kurallarina_DOKUNULMAZ():
    """⚠️ KAPSAM SINIRI — "temiz kaldırma" adına fazlasını silmek YANLIŞ olur.

    Bu makinede ölçüldü: kaldırmadan sonra kalan kurallar `pemf_backend.exe`, `mosquitto.exe`,
    `cloudflared.exe` adlıydı — grup boş, ad = exe adı. Bunlar Windows'un, program ilk kez
    dinlemeye başladığında gösterdiği "erişime izin ver" penceresinde KULLANICININ onayıyla
    oluşturduğu kurallardır. Bizim adlandırdığımız kurallar (`PEMF Backend API` /
    `PEMF UDP Discovery`) o makinede hiç oluşmamıştı.

    Silme betiği YALNIZ kendi adlandırdığımız kuralları hedeflemeli:
      * bunlar kullanıcının kendi kararıdır,
      * `firewall.rs::durum_betigi` onları GEÇERLİ izin sayar (yanlış alarm düzeltmesi
        2026-08-11) — silmek, kullanıcıyı gereksiz bir "engelli" uyarısına geri sokar,
      * yeniden kurulumda aynı yol için kural hâlâ geçerlidir (tekrar sormaz).
    """
    kaynak = _FIREWALL_RS.read_text(encoding="utf-8")
    i = kaynak.find("pub fn silme_betigi")
    assert i != -1
    govde = kaynak[i : kaynak.find("\n}", i)]
    for tehlikeli in ("-Program", "$exe", "Get-NetFirewallApplicationFilter"):
        assert tehlikeli not in govde, (
            f"silme betiği PROGRAM bazlı eşleşme kullanıyor ('{tehlikeli}') → Windows'un "
            f"kullanıcı onaylı kurallarını da siler (kapsam aşımı)"
        )
    assert "DisplayName" in govde, "silme betiği ada göre hedeflemiyor"


# ── 2) Per-user PEMF_System artığı ───────────────────────────────────────────


def test_KRITIK_per_user_PEMF_System_siliniyor():
    """Ayak izi bu yolu KVKK-dışı işaretliyor; kaldırma onu silmeli."""
    hooks = _HOOKS.read_text(encoding="utf-8", errors="replace")
    assert re.search(r'RMDir\s+/r\s+"\$LOCALAPPDATA\\PEMF_System"', hooks), (
        r"%LOCALAPPDATA%\PEMF_System kaldırmada silinmiyor → hotspot.log gibi artıklar kalır"
    )


def test_ayak_izi_bu_yolu_KVKK_DISI_sayiyor():
    """Karşıt-kanıt: silmek doğru mu? Ayak izi tanımı tıbbi veri DEMİYORSA doğru."""
    fp = _FOOTPRINT.read_text(encoding="utf-8", errors="replace")
    satir = next((s for s in fp.splitlines() if "AppData\\Local\\PEMF_System" in s), None)
    assert satir, "ayak izinde per-user PEMF_System kalemi yok"
    assert "Kvkk = $false" in satir, (
        f"bu yol KVKK kapsamında işaretlenmiş — silmek TIBBİ VERİ KAYBI olurdu: {satir.strip()}"
    )


# ── 3) Korunması gerekenler KORUNUYOR (karşıt-kanıt) ─────────────────────────


@pytest.mark.parametrize("yol", [r"$APPDATA\PEMF_GUI", r"ProgramData\PEMF_System\PEMF_GUI"])
def test_KRITIK_hasta_verisi_kaldirmada_SILINMIYOR(yol):
    """⚠️ Hasta kaydı kaldırmada ASLA silinmez (KVKK + sahip kararı)."""
    hooks = _HOOKS.read_text(encoding="utf-8", errors="replace")
    silme_satirlari = [
        s for s in hooks.splitlines() if re.match(r"\s*(RMDir|Delete)\b", s) and not s.strip().startswith(";")
    ]
    ihlal = [s.strip() for s in silme_satirlari if yol in s]
    assert not ihlal, f"KALDIRMA HASTA VERİSİNİ SİLİYOR: {ihlal}"


def test_KRITIK_bulut_kimligi_kaldirmada_SILINMIYOR():
    """`device_identity.json` sıradan kaldırmada KALMALI (denetim #02 kalıcı çözümü).

    Silinirse yeniden kurulumda bulut mührü bozulur ve 31 gün süren arıza geri gelir."""
    hooks = _HOOKS.read_text(encoding="utf-8", errors="replace")
    silme_satirlari = [
        s for s in hooks.splitlines() if re.match(r"\s*(RMDir|Delete)\b", s) and not s.strip().startswith(";")
    ]
    ihlal = [s.strip() for s in silme_satirlari if "device_identity" in s or "PEMF_System\\PEMF_GUI" in s]
    assert not ihlal, f"kaldırma bulut kimliğini siliyor → yeniden kurulumda secret_mismatch geri gelir: {ihlal}"
