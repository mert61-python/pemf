# Author: mertaygn, cglrgrkn
"""ÖLÜ KOMUT YÜZEYLERİ KALDIRILDI — SET_PARAMS / start_at / SYNC_ALL (sahip kararı 2026-08-20).

Envanter (5-ajanlı tarama, 2026-08-20): depoda HİÇBİR üretici yok — servers/ ve pf/ grep'leri boş;
backend ESP'lere yalnız "start"/"stop" yayınlar. Üç yüzey silinmiş PyQt GUI'nin kalıntısıydı ve
[4.6]'nın latent kusurlarını taşıyordu (8266 checkSyncWait başlangıç dalları `_suresizGecenMs`i
sıfırlamıyor; CMD_SYNC_ALL aktif seansta stop+start ile süresiz-tavanı sıfırlayıp resume sonrası
süreli seansı süresize çeviriyordu). Sahip kararı: backend'e bağlamak değil KALDIRMAK → [4.6]
tetikleyicisiz kalarak kapanır.

KALDIRILANLAR: iki ESP'de set_params/sync_all komut dalları; start_at zamanlanmış-başlangıç
makinesi (8266: PWMStartState/checkSyncWait/isWaiting/_targetTimestampMs/setParams; S3:
_waitingForSync/_syncTargetTime/process-bekleme-bloğu); yalnız-SYNC_ALL-için-var olan broadcast
abonelikleri (S3 `pemf/coil/all/control`, 8266 `pemf/control/all`); enum ölü girdileri.

KALANLAR (karşıt-kanıt — bunlar CANLI ya da sahip listesinde YOK):
  · S3 `UPDATE` dalı — sahip listesinde yok; bugün üreticisiz ama [5.3] korumalı gelecek yüzeyi.
  · STM32 PB1 donanım sync darbesi — AYRI ve CANLI mekanizma (ad benzerliği tuzağı).
  · Backend `sync_warning` (≳50× freq-ayrışma uyarısı) — 2026-08-19 sahip kararı, ilgisiz.
  · mosquitto ACL'lerindeki broadcast izinleri — provizyon regresyon riski yüzünden BİLEREK
    dokunulmadı (kullanılmayan izin; parti kaydında).

⚠️ C bu makinede derlenemez — kapılar yorum-soyulmuş yapısal; REFLASH zaten planlı.
"""

from __future__ import annotations

from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"
E8 = KOK / "firmware" / "esp8266_pemf_coil"
STM = KOK / "firmware" / "stm32_pemf"


def _dosya(p: Path) -> str:
    # 17. parti: STRING-BİLİNÇLİ soyucu — eski regex, string içindeki `//`yi (örn. "https://")
    # yorum sanıp satırın kalanını siliyordu; adversaryal inceleme bunu canlı bir SYNC_ALL
    # dispatch'ini `String("s://")` hilesiyle kapılardan kaçırarak AMPİRİK kanıtladı.
    return c_soy(p.read_text(encoding="utf-8", errors="replace"))


def test_KRITIK_8266_olu_komut_dallari_YOK():
    ino = _dosya(E8 / "esp8266_pemf_coil.ino")
    for olu in ('"set_params"', '"sync_all"', '"start_at"'):
        assert olu not in ino, f"8266 .ino ölü yüzeyi hâlâ taşıyor: {olu} (sahip kararı: kaldır)"
    cc = _dosya(E8 / "CoilController.cpp") + _dosya(E8 / "CoilController.h")
    for olu in ("checkSyncWait", "PWM_START_WAITING", "_targetTimestampMs", "setParams", "CMD_SYNC_ALL"):
        assert olu not in cc, f"8266 zamanlanmış-başlangıç/param makinesi hâlâ duruyor: {olu}"
    sd = _dosya(E8 / "SharedDefs.h")
    assert "CMD_SYNC_ALL" not in sd and "CMD_UPDATE_PARAMS" not in sd, (
        "8266 enum ölü girdileri taşıyor (update dalı 8266'da hiç olmadı; set_params kalktı)"
    )


def test_KRITIK_S3_olu_komut_dallari_YOK():
    nm = _dosya(S3 / "NetworkManager.cpp")
    for olu in ('"SET_PARAMS"', '"SYNC_ALL"', '"start_at"'):
        assert olu not in nm, f"S3 NetworkManager ölü yüzeyi hâlâ taşıyor: {olu}"
    cc = _dosya(S3 / "CoilController.cpp") + _dosya(S3 / "CoilController.h")
    for olu in ("_waitingForSync", "_syncTargetTime", "CMD_SYNC_ALL"):
        assert olu not in cc, f"S3 zamanlanmış-başlangıç makinesi hâlâ duruyor: {olu}"
    assert "CMD_SYNC_ALL" not in _dosya(S3 / "SharedDefs.h"), "S3 enum CMD_SYNC_ALL taşıyor"


def test_KRITIK_broadcast_abonelikleri_YOK():
    """Broadcast konuları yalnız SYNC_ALL içindi (S3 .h yorumu bunu açıkça söylüyordu)."""
    s3nm = _dosya(S3 / "NetworkManager.cpp") + _dosya(S3 / "NetworkManager.h")
    assert "_topicBroadcast" not in s3nm and "coil/all/control" not in s3nm, (
        "S3 broadcast aboneliği duruyor — tek yükü SYNC_ALL idi"
    )
    e8nm = _dosya(E8 / "NetworkManager.cpp") + _dosya(E8 / "NetworkManager.h")
    assert "_globalControlTopic" not in e8nm and "pemf/control/all" not in e8nm, (
        "8266 broadcast aboneliği duruyor — tek yükü sync_all idi (üstelik konu adı S3'le AYRIŞIKTI)"
    )


def test_KARSIT_KANIT_canli_yuzeyler_DURUYOR():
    """Aşırı-silme koruması: canlı komutlar + canlı mekanizmalar yerinde."""
    ino = _dosya(E8 / "esp8266_pemf_coil.ino")
    for canli in ('"start"', '"stop"', '"SELFTEST"', '"status"', '"clear_wifi"'):
        assert canli in ino, f"8266 CANLI komut dalı kayboldu: {canli} (aşırı-silme!)"
    nm = _dosya(S3 / "NetworkManager.cpp")
    for canli in ('cmdStr == "START"', 'cmdStr == "STOP"', 'cmdStr == "UPDATE"', 'cmdStr == "SELFTEST"'):
        assert canli in nm, f"S3 CANLI komut dalı kayboldu: {canli} (aşırı-silme!)"
    assert "PHASE_BELIRTILMEDI" in nm, "[5.3] UPDATE faz nöbetçisi kaldırmayla birlikte kaybolmuş"
    stm = (STM / "Core" / "Src" / "main.c").read_text(encoding="utf-8", errors="replace")
    assert "DDS_SYNC_PULSE_TICKS" in stm, "STM PB1 donanım sync darbesi (CANLI, ilgisiz) silinmiş!"


def test_KARSIT_KANIT_8266_start_stop_makinesi_saglam():
    """start() artık koşulsuz hemen başlar; stop/başlangıç değişmezleri ([1.3] taban dahil) yerinde."""
    cc = _dosya(E8 / "CoilController.cpp")
    assert "void CoilController::start(" in cc and "_applyPWM(_pwmFrequency, _pwmDutyCycle)" in cc, (
        "8266 start yolu zedelendi (aşırı-silme!)"
    )
    assert "NVS_KAYIT_ARALIGI_MS" in cc, "[1.3]/ikiz resume-taban mekanizması kaldırma sırasında zedelendi"
    assert "_suresizGecenMs" in cc, "süresiz-tavan sayacı kayboldu"
