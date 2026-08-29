# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""BULUT CİHAZ SIRRI VERİ KÖKÜ YENİLENİNCE KAYBOLMAZ — denetim 2026-08-28 #02 (kalıcı çözüm).

KÖK NEDEN: KALICILIK ASİMETRİSİ (ölçüldü).
  * `device_id` NIC MAC'inden türetilir → veri kökü silinse de AYNI değer geri gelir.
  * `device_registry_secret` rastgele üretilir ve YALNIZ veri kökündeki `pemf_secrets.json`da
    yaşardı → veri kökü yenilenince KAYBOLUR, yenisi doğardı.
Buluttaki TOFU mührü `(device_id, secret_hash)` çiftine bağlı olduğundan sonuç deterministikti:
birincil anahtar AYNI, sır FARKLI → KALICI `secret_mismatch`. Saha ölçümü: cihaz 13 gün buluta
yazamadı, uzaktan bağlanan "cihaz bulunamadı" gördü (cihaz açık ve internete bağlıydı).

ÇÖZÜM (sahip kararı): sır veri kökünün DIŞINDA, makine kapsamlı bir dosyada tutulur.

⚠️ BU DOSYA ÜÇ DAVRANIŞI BİRLİKTE KİLİTLER — biri olmadan diğerleri anlamsız:
  1. Veri kökü yenilenince sır AYNI kalır (bulgunun düzeltmesi).
  2. Makine deposu da silinince (KVKK) sır DEĞİŞİR — bulut yazma yetkisi geride KALMAZ.
     Bu, seçilen yolun KVKK ödünleşiminin karşılığıdır; `pemf_footprint.ps1`teki
     `device_identity.json` kalemi olmadan (1) tek başına yetki sızıntısıdır.
  3. Ortam değişkeni (`PEMF_DEVICE_REGISTRY_SECRET`) her ikisini de EZER (operatör kontrolü).

⚠️ HER TUR AYRI SÜREÇTE koşar: modül-içi önbellek ilk ölçümü YANILTMIŞTI (aynı süreçte
"3. tur"da da eski sır dönüyordu, düzeltme çalışıyor sanılmıştı).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]

_TUR_BETIGI = """
import sys, os, hashlib
sys.path.insert(0, r"{kok}")
os.environ["PEMF_DATA_DIR"] = sys.argv[1]
os.environ["PEMF_DEVICE_IDENTITY_DIR"] = sys.argv[2]
if len(sys.argv) > 3 and sys.argv[3]:
    os.environ["PEMF_DEVICE_REGISTRY_SECRET"] = sys.argv[3]
else:
    os.environ.pop("PEMF_DEVICE_REGISTRY_SECRET", None)
from utils.secrets_manager import get_secret
print(hashlib.sha256(get_secret("device_registry_secret").encode()).hexdigest()[:16])
"""


def _tur(veri_koku: Path, depo: Path, env_sirri: str = "") -> str:
    """Sırrı TEMİZ bir süreçte çöz (modül önbelleği ölçümü kirletmesin)."""
    betik = _TUR_BETIGI.format(kok=str(_KOK))
    r = subprocess.run(
        [sys.executable, "-c", betik, str(veri_koku), str(depo), env_sirri],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, f"tur başarısız: {r.stderr[-600:]}"
    return r.stdout.strip().splitlines()[-1]


@pytest.fixture()
def ortam(tmp_path):
    depo = tmp_path / "makine_deposu"
    depo.mkdir()
    return depo


def test_KRITIK_veri_koku_yenilenince_sir_AYNI_kalir(tmp_path, ortam):
    """Bulgunun düzeltmesi: kaldır-kur sonrası TOFU mührü bozulmamalı."""
    kok1, kok2 = tmp_path / "kok1", tmp_path / "kok2"
    kok1.mkdir()
    kok2.mkdir()

    ilk = _tur(kok1, ortam)
    assert (ortam / "device_identity.json").is_file(), (
        "makine deposu YAZILMADI — sır yalnız veri kökünde kalır, bir sonraki yenilemede kaybolur"
    )
    yeni_kok = _tur(kok2, ortam)
    assert ilk == yeni_kok, (
        "veri kökü yenilenince sır DEĞİŞTİ → bulut mührü bozulur, cihaz kalıcı olarak "
        "'secret_mismatch' alır (bulgunun ta kendisi)"
    )


def test_KRITIK_KVKK_silmesi_yetkiyi_GERIDE_BIRAKMAZ(tmp_path, ortam):
    """Seçilen yolun ödünleşiminin karşılığı: makine deposu da silinirse sır DEĞİŞMELİ.

    Aksi hâlde "cihazı kaldırdım" diyen klinikte bulut YAZMA YETKİSİ makinede kalır."""
    kok1, kok2 = tmp_path / "k1", tmp_path / "k2"
    kok1.mkdir()
    kok2.mkdir()

    ilk = _tur(kok1, ortam)
    (ortam / "device_identity.json").unlink()  # KVKK silmesi
    sonra = _tur(kok2, ortam)
    assert ilk != sonra, "makine deposu silindiği hâlde ESKİ sır geri geldi — yetki geride kaldı"


def test_KRITIK_MEVCUT_kurulumdaki_sir_depoya_TASINIR(tmp_path, ortam):
    """⚠️ GERİYE DÖNÜK KURTARMA — bu olmadan çözüm SAHADAKİ cihazları korumaz.

    Mevcut kurulumlarda sır zaten veri kökünde DOLU olduğu için migrate/üret yoluna hiç
    girilmez; yani depoya hiç yazılmaz ve ilk kaldır-kur döngüsünde sır yine kaybolurdu.
    `get_secret` artık veri kökünden okuduğu sırrı, depoda yoksa oraya da taşır.
    """
    kok = tmp_path / "mevcut_kurulum"
    kok.mkdir()

    # 1) Sırrı YALNIZ veri köküne yaz (eski dünya: depo boş)
    ilk = _tur(kok, ortam)
    depo_dosyasi = ortam / "device_identity.json"
    depo_dosyasi.unlink()  # eski kurulum simülasyonu: depo YOK, veri kökü DOLU
    assert not depo_dosyasi.exists()

    # 2) Normal bir okuma — migrasyonu tetiklemeli
    okunan = _tur(kok, ortam)
    assert okunan == ilk, "okuma sırrı değiştirdi (olmamalı)"
    assert depo_dosyasi.is_file(), (
        "mevcut kurulumun sırrı makine deposuna TAŞINMADI → sahadaki cihazlar korunmuyor, "
        "ilk kaldır-kur döngüsünde arıza geri gelir"
    )

    # 3) Artık veri kökü yenilense de sır korunmalı
    yeni_kok = tmp_path / "yenilenmis"
    yeni_kok.mkdir()
    assert _tur(yeni_kok, ortam) == ilk, "taşımadan sonra bile sır korunmadı"


def test_ortam_degiskeni_HER_IKISINI_de_ezer(tmp_path, ortam):
    """Operatör kontrolü korunur: `PEMF_DEVICE_REGISTRY_SECRET` en üstte."""
    kok = tmp_path / "k"
    kok.mkdir()
    _tur(kok, ortam)  # depoyu doldur
    zorlanan = "operatorun-verdigi-sir-1234567890"
    kok2 = tmp_path / "k2"
    kok2.mkdir()
    assert _tur(kok2, ortam, zorlanan) == hashlib.sha256(zorlanan.encode()).hexdigest()[:16]


def test_ayni_kok_ikinci_kez_AYNI_sirri_verir(tmp_path, ortam):
    """Karşıt-kanıt: sıradan davranış bozulmadı (her çağrıda yeni sır üretilmiyor)."""
    kok = tmp_path / "k"
    kok.mkdir()
    assert _tur(kok, ortam) == _tur(kok, ortam)


# ── Statik sözleşmeler ───────────────────────────────────────────────────────


def test_KRITIK_kayit_makine_deposuna_BAGLI():
    """⚠️ ZAYIF-ÇIPA KORUMASI: yardımcılar var olabilir ama `_REGISTRY` onları kullanmıyorsa
    hiçbir şey değişmez."""
    from utils.secrets_manager import _REGISTRY, _bulut_sirri_oku, _bulut_sirri_uret

    _bolum, _dpapi, uretec, eski = _REGISTRY["device_registry_secret"]
    assert uretec is _bulut_sirri_uret, "üreteç makine deposuna yazmıyor → sır yine kaybolur"
    assert eski is _bulut_sirri_oku, "eski-kaynak okuyucusu makine deposuna bakmıyor"


def test_KRITIK_depo_VERI_KOKUNUN_DISINDA():
    """Depo veri kökünün altındaysa çözüm hiçbir işe yaramaz (aynı silmede gider)."""
    from utils.secrets_manager import _cihaz_kimlik_deposu, _data_dir

    depo = str(_cihaz_kimlik_deposu()).lower()
    kok = str(_data_dir()).lower()
    assert not depo.startswith(kok), f"depo ({depo}) veri kökünün ({kok}) İÇİNDE — kök yenilenince gider"


def test_KRITIK_teardown_KVKK_kaleminde():
    """Ödünleşimin karşılığı sevk edilmeli: KVKK silmesi bulut yetkisini de götürmeli."""
    ps = (_KOK / "scripts" / "pemf_footprint.ps1").read_text(encoding="utf-8")
    satirlar = [s for s in ps.splitlines() if "device_identity.json" in s and not s.strip().startswith("#")]
    assert satirlar, (
        "footprint'te `device_identity.json` kalemi YOK → sır KVKK silmesinden sonra makinede "
        "kalır ve bulut yazma yetkisi geride bırakılır"
    )
    assert any("Kvkk = $true" in s for s in satirlar), (
        f"kalem KVKK dışı işaretlenmiş — 'cihazı kaldırdım' diyen klinikte yetki kalır: {satirlar}"
    )


def test_depo_yazimi_GLOBAL_ACL_bayragini_TUKETMEZ():
    """⚠️ Ölçülen tuzak: `_ensure_dir_hardened` süreç-geneli bir bayrak kullanıyor; burada
    çağrılırsa ASIL sır dizininin sertleştirmesi bir daha DENENMEZ. Ayrıca kilitlenecek dizin
    `PEMF_System` KÖKÜ olurdu (logs/mosquitto/hotspot.json orada)."""
    import inspect

    from utils.secrets_manager import _kimlik_deposu_yaz

    kaynak = inspect.getsource(_kimlik_deposu_yaz)
    etkin = [s for s in kaynak.splitlines() if "_ensure_dir_hardened" in s and not s.strip().startswith("#")]
    assert not etkin, f"makine deposu yazımı global ACL bayrağını tüketiyor: {etkin}"


def test_depo_okuma_HICBIR_KOSULDA_patlamaz(tmp_path, monkeypatch):
    """Bozuk/erişilemez depo, sır çözümünü DÜŞÜRMEMELİ (yalnız uyarır)."""
    import utils.secrets_manager as sm

    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / "device_identity.json").write_text("{bu json degil", encoding="utf-8")
    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(bozuk))
    assert sm._kimlik_deposu_oku() == ""


def test_depo_yazimi_HICBIR_KOSULDA_patlamaz(monkeypatch):
    """Yazılamayan depo (izin yok) akışı KESMEMELİ."""
    import utils.secrets_manager as sm

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", os.path.join(os.sep, "olmayan_kok_12345", "alt"))
    sm._kimlik_deposu_yaz("deneme-degeri")  # istisna fırlatırsa test kırmızı
