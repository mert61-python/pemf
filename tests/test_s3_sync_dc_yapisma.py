# Author: mertaygn, cglrgrkn
"""S3 FAZ SENKRONU DC-YAPIŞMA KORUMASI — donanım-uyum denetimi HG-3 (2026-08-19).

STM master freq ESP'den çok yüksekse (STM 100 Hz / ESP 1 Hz → 100×), PB1 darbesi ESP'nin her
periyot BAŞINDA gelip s_tick'i sürekli sıfırlar → ESP yarım-periyoda HİÇ ulaşamaz → çıkış tek
polaritede DC'ye YAPIŞIR (bobin ısınması, STM'de termal kesme yok). S3 firmware'ine, ESP doğal
periyodunu tamamlayamadan ardışık SYNC_MISMATCH_STREAK kez erken kilit gelirse sync'i DEVRE DIŞI
bırakan (8266 gibi tek faz) bir kapı eklendi.

Firmware C ISR'ı doğrudan koşulamaz; bu test (a) firmware'deki ALGORİTMAYI Python'da yeniden
kurup senaryoları kanıtlar (test_firmware_frekans_artisi_duty'nin ISR-modeli kültürü) ve
(b) C kaynağının bu algoritmayı + telemetriyi gerçekten içerdiğini doğrular.
"""

from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"
STREAK = 8  # SYNC_MISMATCH_STREAK — C ile aynı


class _SyncModel:
    """firmware syncPulseISR + ddsTimerISR kilit mantığının birebir Python modeli."""

    def __init__(self, tpp: int):
        self.tpp = tpp
        self.tick = 0
        self.natural_wrap = False
        self.early_streak = 0
        self.sync_disabled = False
        self.locked = 0
        self.ignored = 0

    def timer_tick(self):
        """ddsTimerISR: 50 kHz sayaç; tpp'ye ulaşınca doğal wrap."""
        self.tick += 1
        if self.tick >= self.tpp:
            self.tick = 0
            self.natural_wrap = True

    def sync_pulse(self):
        """syncPulseISR: STM PB1 darbesi geldi."""
        if self.sync_disabled:
            return
        tol = self.tpp // 50 + 2
        t = self.tick
        if t <= tol:
            if self.natural_wrap:
                self.early_streak = 0
                self.natural_wrap = False
            else:
                self.early_streak += 1
                if self.early_streak >= STREAK:
                    self.sync_disabled = True
            self.tick = 0
            self.locked += 1
        elif t >= self.tpp - tol:
            self.early_streak = 0
            self.natural_wrap = False
            self.tick = 0
            self.locked += 1
        else:
            self.ignored += 1

    def update_pwm(self, tpp: int):
        """_updatePWM eşdeğeri — latch reset YALNIZ gerçek freq değişiminde (review düzeltmesi).
        Eski koşulsuz reset, aktifken gelen her set_params/keepalive'ın streak'i bölüp latch'in
        hiç oluşmamasına izin veriyordu."""
        freq_changed = tpp != self.tpp
        self.tpp = tpp
        if freq_changed:
            self.sync_disabled = False
            self.early_streak = 0
            self.natural_wrap = False


def test_KRITIK_STM_cok_hizli_sync_DEVRE_DISI():
    """STM 100 Hz / ESP 1 Hz → PB1 her 500 tick'te; ESP tpp=50000 → hiç wrap edemez → sync kapanır."""
    m = _SyncModel(tpp=50000)  # ESP 1 Hz
    stm_periyot_tick = 500  # STM 100 Hz = ESP'nin 500 tick'i
    for _ in range(STREAK + 2):
        for _ in range(stm_periyot_tick):
            m.timer_tick()
        m.sync_pulse()  # STM darbesi — ESP periyot başında (t≈500 << 25000)
    assert m.sync_disabled, "STM çok hızlıyken sync devre dışı KALMADI → DC-yapışma önlenmiyor"


def test_KRITIK_ayni_frekans_sync_AKTIF_kalir():
    """STM ve ESP aynı freq (100 Hz, tpp=500) → darbe ESP wrap'ıyla hizalı → sync aktif kalır."""
    m = _SyncModel(tpp=500)  # ESP 100 Hz
    for _ in range(20):
        for _ in range(500):  # tam bir ESP periyodu → natural_wrap true
            m.timer_tick()
        m.sync_pulse()  # darbe periyot sonunda/başında, ESP wrap yaptı
    assert not m.sync_disabled, "aynı frekansta sync yanlışlıkla devre dışı kaldı (faz kilidi bozuldu)"
    assert m.locked > 0, "aynı frekansta hiç kilit olmadı"


def test_KRITIK_hafif_jitter_sync_AKTIF_kalir():
    """STM biraz erken (jitter, %2) → tolere edilmeli, streak eşiğe ulaşmamalı."""
    m = _SyncModel(tpp=500)
    for _ in range(20):
        for _ in range(495):  # ~%1 erken (jitter)
            m.timer_tick()
        m.sync_pulse()
    assert not m.sync_disabled, "hafif jitter sync'i devre dışı bıraktı (eşik fazla hassas)"


def test_KRITIK_yeni_frekans_sync_YENIDEN_dener():
    """Uyumsuzlukta kapanan sync, freq uyumlu hâle gelince yeniden etkinleşmeli (_updatePWM reset)."""
    m = _SyncModel(tpp=50000)
    for _ in range(STREAK + 2):
        for _ in range(500):
            m.timer_tick()
        m.sync_pulse()
    assert m.sync_disabled
    m.update_pwm(tpp=500)  # yeni FREKANS — artık STM ile aynı → latch sıfırlanır
    assert not m.sync_disabled
    for _ in range(20):
        for _ in range(500):
            m.timer_tick()
        m.sync_pulse()
    assert not m.sync_disabled, "freq uyumlu hâle gelince sync yeniden etkinleşmedi"


def test_KRITIK_ayni_freq_keepalive_LATCHI_BOZAMAZ():
    """⚠️ Adversaryal review bulgusu: eski koşulsuz reset'te, aktifken sık gelen AYNI-freq
    set_params/keepalive komutu streak'i sürekli 0'a çekip DC-yapışma latch'inin OLUŞMASINI
    engelliyordu (güvenlik katmanı komut kadansına bağımlıydı). Düzeltme: reset yalnız gerçek
    freq değişiminde → aynı-freq re-komut latch birikimini BÖLEMEZ."""
    m = _SyncModel(tpp=50000)  # ESP 1 Hz, STM 100 Hz → DC-yapışma rejimi
    for _ in range(STREAK + 2):
        for _ in range(500):
            m.timer_tick()
        m.sync_pulse()
        m.update_pwm(tpp=50000)  # her darbe arasında AYNI-freq keepalive (en kötü kadans)
    assert m.sync_disabled, "aynı-freq keepalive latch'i böldü → DC-yapışma koruması komut kadansıyla etkisizleşiyor"


def test_KRITIK_farkli_freq_komutu_latch_sifirlar_AMA_yeniden_birikir():
    """Karşıt-kanıt: freq DEĞİŞİRSE reset meşru (yeniden dene); uyumsuzluk sürerse latch geri gelir."""
    m = _SyncModel(tpp=50000)
    for _ in range(STREAK + 2):
        for _ in range(500):
            m.timer_tick()
        m.sync_pulse()
    assert m.sync_disabled
    m.update_pwm(tpp=25000)  # freq değişti (1→2 Hz) ama STM hâlâ 100 Hz → yine uyumsuz
    assert not m.sync_disabled  # meşru yeniden deneme
    # Sayaç periyot ORTASINDA kaldığından darbeler önce 'ignored' dalına düşer (ESP serbest koşar,
    # DC YOK — güvenli ara evre); darbe kilit penceresine girince DC rejimi başlar ve latch birikir.
    # tpp=25000, darbe=500 tick → pencereye ulaşma ~46 darbe + STREAK → bolca 100 iterasyon.
    for _ in range(100):
        for _ in range(500):
            m.timer_tick()
        m.sync_pulse()
    assert m.sync_disabled, "uyumsuzluk sürerken latch yeniden oluşmadı"


def test_KARSIT_KANIT_C_kaynagi_algoritma_ve_telemetri_ICERIR():
    """C kaynağı kapı + reset + telemetri zincirini gerçekten içeriyor mu."""
    cpp = (S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    assert "s_sync_disabled" in cpp and "s_natural_wrap" in cpp and "s_early_streak" in cpp
    assert "SYNC_MISMATCH_STREAK" in cpp
    # ddsTimerISR wrap'ta natural_wrap set ediyor
    assert "s_natural_wrap = true" in cpp, "doğal wrap bayrağı set edilmiyor"
    # _updatePWM'de reset (yeniden deneme) — docstring değil GERÇEK fonksiyon tanımı
    i = cpp.index("void CoilController::_updatePWM")
    govde = cpp[i : i + 2200]
    assert "s_sync_disabled = false" in govde, "_updatePWM'de sync reset yok (kalıcı kapanır)"
    # ⚠️ review düzeltmesi: reset KOŞULSUZ olamaz — freqChanged guard'ı şart (keepalive latch'i bozmasın)
    assert "freqChanged" in govde and "if (freqChanged)" in govde, (
        "_updatePWM reset'i koşulsuz — aynı-freq keepalive DC-yapışma latch'ini etkisizleştirir"
    )
    # telemetri zinciri
    assert "bool syncDisabled()" in (S3 / "CoilController.h").read_text(encoding="utf-8", errors="replace")
    assert "syncDisabled" in (S3 / "SharedDefs.h").read_text(encoding="utf-8", errors="replace")
    assert 'doc["sync_disabled"]' in (S3 / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace")
