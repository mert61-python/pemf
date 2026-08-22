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
    """firmware syncPulseISR + ddsTimerISR kilit mantığının birebir Python modeli.

    2. tur [4.3] (2026-08-20): modele `active` eklendi — GERÇEK C'de ddsTimerISR `!s_active`
    iken tick'i İLERLETMEZ (natural_wrap üretilemez) ve düzeltmeyle syncPulseISR pasifken
    darbeyi tamamen YOK SAYAR (ne sayar ne latch'ler). `pasif_darbe_latchler=True` ESKİ
    (kusurlu) C semantiğini modeller — ayrıştırıcı test modelin gerçekten fark ölçtüğünü kanıtlar."""

    def __init__(self, tpp: int, pasif_darbe_latchler: bool = False):
        self.tpp = tpp
        self.tick = 0
        self.natural_wrap = False
        self.early_streak = 0
        self.sync_disabled = False
        self.locked = 0
        self.ignored = 0
        self.active = True  # mevcut testler aktif seansı modeller — davranışları değişmez
        self._pasif_darbe_latchler = pasif_darbe_latchler

    def timer_tick(self):
        """ddsTimerISR: 50 kHz sayaç; tpp'ye ulaşınca doğal wrap. PASİFKEN İLERLEMEZ (gerçek C)."""
        if not self.active:
            return
        self.tick += 1
        if self.tick >= self.tpp:
            self.tick = 0
            self.natural_wrap = True

    def stop(self):
        """_stopPWM eşdeğeri: çıkış kapanır; s_tick/streak/latch DURUMU KALIR (gerçek C)."""
        self.active = False

    def start(self, tpp: int):
        """_beginOutput→_updatePWM eşdeğeri: parametre uygula + aktif et.
        Latch reset yalnız GERÇEK freq değişiminde (update_pwm kuralı aynen)."""
        self.update_pwm(tpp)
        self.active = True

    def sync_pulse(self):
        """syncPulseISR: STM PB1 darbesi geldi."""
        if not self.active and not self._pasif_darbe_latchler:
            return  # [4.3] düzeltmesi: pasifken darbe SAYILMAZ ve LATCH BİRİKMEZ
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


# ── 2. TUR DENETİMİ [4.3] (2026-08-20): LATCH PWM PASİFKEN BİRİKMEZ ─────────────────────────
# Deterministik tetikleyici (çürütme ajanının izlediği dizi): S3, STM bobin-1 çalışırken seansı
# bitirir (_stopPWM: s_active=false, s_tick DONAR — ddsTimerISR pasifken tick'i ilerletmez,
# natural_wrap üretilemez) → boşta gelen HER PB1 darbesi "erken kilit" sayılır → 8 darbede
# s_sync_disabled=true. Aynı frekanslı SONRAKİ seans (AI Pro hep 1 Hz → freqChanged=false →
# latch bilinçli KORUNUR) faz senkronsuz koşar; sync_disabled status'ta raporlansa da backend o
# alanı işlemiyor → sessiz derece kaybı. Yön fail-safe (tek faz, DC yok) ama çok-bobinli faz
# deseni sessizce bozulur. Ek kirlilik: boşta darbeler locked/ignored sayaçlarını da şişiriyordu
# (tezgâh tanılaması yanılır).


def test_KRITIK_PWM_pasifken_darbeler_LATCHI_biriktirmez():
    """Seans biter → STM darbeleri sürer → AYNI frekansla yeni seans: sync AKTİF kalmalı."""
    m = _SyncModel(tpp=50000)  # AI Pro 1 Hz
    # Sağlıklı bir tam periyot + hizalı darbe (seans içi normal akış).
    for _ in range(50000):
        m.timer_tick()
    m.sync_pulse()
    assert not m.sync_disabled

    m.stop()  # seans bitti; STM bobin-1 hâlâ 100 Hz'de PB1 basıyor
    for _ in range(STREAK + 5):
        m.sync_pulse()  # pasifken timer İLERLEMEZ — darbeler tick donmuşken geliyor
    m.start(tpp=50000)  # 2. AI Pro seansı — AYNI freq → freqChanged=false → latch resetlenmez

    assert not m.sync_disabled, (
        "PWM pasifken biriken darbeler latch'i doldurdu — aynı frekanslı sonraki seans faz "
        "senkronsuz koşar (bulgu [4.3]); pasif darbeler HİÇ sayılmamalı"
    )
    # ve seans içinde senkron gerçekten çalışıyor
    for _ in range(50000):
        m.timer_tick()
    m.sync_pulse()
    assert m.locked >= 2 and not m.sync_disabled


def test_KRITIK_pasif_darbeler_TELEMETRIYI_kirletmez():
    """locked/ignored sayaçları tezgâh tanılamasıdır — boşta geçen STM darbeleri onları şişirmemeli."""
    m = _SyncModel(tpp=500)
    m.stop()
    for _ in range(1000):
        m.sync_pulse()
    assert m.locked == 0 and m.ignored == 0, (
        f"pasif darbeler sayaçlara yazıldı (locked={m.locked}, ignored={m.ignored}) — "
        "tezgâhta frekans-uyuşmazlığı tanısı yanılır"
    )


def test_MODEL_AYIRT_EDIYOR_eski_semantik_bosta_latchlerdi():
    """Ayrıştırıcı: ESKİ C semantiği (pasif darbe sayılır) aynı diziyle latch'i DOLDURUR —
    model gerçek farkı ölçüyor, kapı kendi varsayımını doğrulamıyor."""
    m = _SyncModel(tpp=50000, pasif_darbe_latchler=True)
    for _ in range(50000):
        m.timer_tick()
    m.sync_pulse()
    m.stop()
    for _ in range(STREAK + 5):
        m.sync_pulse()
    m.start(tpp=50000)
    assert m.sync_disabled, (
        "model ayrıştırmıyor: eski semantik de latch'lemedi — [4.3] kapısı yanlış şeyi ölçüyor olabilir"
    )


def _c_soy(src: str) -> str:
    import re as _re

    src = _re.sub(r"/\*.*?\*/", " ", src, flags=_re.S)
    src = _re.sub(r"//[^\n]*", " ", src)
    return src


def test_KRITIK_C_syncPulseISR_pasifken_ERKEN_doner():
    """Yapısal kapı (yorum-soyulmuş kaynak): syncPulseISR, streak/latch mantığından ÖNCE
    `!s_active` erken dönüşü içermeli — model bu semantiği varsayıyor."""
    cpp = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    i = cpp.index("static void IRAM_ATTR syncPulseISR()")
    j = cpp.index("static void", i + 10)
    govde = cpp[i:j]
    k = govde.find("!s_active")
    assert k >= 0, (
        "syncPulseISR'da s_active kapısı YOK — PWM pasifken PB1 darbeleri latch'i doldurur, "
        "aynı frekanslı sonraki seans faz senkronsuz koşar (bulgu [4.3])"
    )
    assert k < govde.index("s_early_streak"), "s_active kapısı streak mantığından SONRA — pasif darbeler yine sayılır"


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
