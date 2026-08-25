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
        self.awaiting_acquire = False  # E4: seans başı/freq değişimi → ilk darbe faz kilidini EDİNİR
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
        Latch reset yalnız GERÇEK freq değişiminde (update_pwm kuralı aynen).
        E4: _beginOutput edinimi KOŞULSUZ armlar (aynı-freq restart freqChanged=false olsa da)."""
        self.update_pwm(tpp)
        self.awaiting_acquire = True  # _beginOutput'taki koşulsuz arm
        self.active = True

    def sync_pulse(self):
        """syncPulseISR: STM PB1 darbesi geldi."""
        if not self.active and not self._pasif_darbe_latchler:
            return  # [4.3] düzeltmesi: pasifken darbe SAYILMAZ ve LATCH BİRİKMEZ
        if self.sync_disabled:
            return
        if self.awaiting_acquire:
            # E4: İLK-DARBE FAZ EDİNİMİ — darbe nerede gelirse gelsin s_tick=0 ile kilidi EDİN.
            # Kapılardan SONRA (HG-3/[4.3] korunur); tolerans dalından ÖNCE (orta-periyot da edinir).
            self.awaiting_acquire = False
            self.natural_wrap = False
            self.early_streak = 0
            self.tick = 0
            self.locked += 1
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
            self.awaiting_acquire = True  # E4: yeni frekans → faz kilidini yeniden EDİN


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


# ── 3. TUR DENETİMİ [E4] (2026-08-24): İLK-DARBE FAZ EDİNİMİ ────────────────────────────────
# s_tick yalnız iki ISR'da yazılır ve START'ta HİÇBİR ortak epoch'a hizalanmaz. STM main.c ref_ms
# epoch-hizasını ESP'de taklit edemeyiz (ortak saat yok) → ESP fazını YALNIZ PB1 darbesinden
# öğrenebilir. Mevcut tolerans dalı yalnız periyot SINIRINA yakın (±%2) darbeyi kilitler; AYNI
# frekanslı ama SABİT faz-ofsetli STM/ESP çifti (darbe periyot ORTASINDA) tolerans penceresine
# HİÇ giremez → darbe hep 'ignored' → faz kilidi ASLA kurulmaz → komut edilen çok-bobin faz
# deseni yanlış uygulanır (klinik çıktı hatası; DC-yapışma değil ama faz superpozisyonu bozuk).
# Düzeltme: seans başı (_beginOutput KOŞULSUZ) ve freq değişimi (_updatePWM freqChanged) →
# s_awaiting_acquire armlanır; İLK darbe nerede gelirse gelsin s_tick=0 ile faz kilidini EDİNİR,
# sonra tolerans dalı kilidi SÜRDÜRÜR. Edinim s_sync_disabled/!s_active kapılarından SONRA →
# HG-3 DC-yapışma latch'ini ve [4.3] pasif-darbe korumasını BOZMAZ.


def test_KRITIK_E4_ayni_freq_sabit_ofset_ILK_darbede_kilitlenir():
    """STM ve ESP AYNI frekans (1 Hz, tpp=50000) ama SABİT faz ofseti: PB1 hep periyot ORTASINDA
    (t≈30000). Edinim OLMADAN darbe hep 'ignored' → ESP faz kilidini HİÇ kuramaz. Edinimle ilk
    darbede s_tick=0 → anında kilit. (Edinimsiz model bu testte tick≠0 ile RED verir.)"""
    m = _SyncModel(tpp=50000)
    m.start(tpp=50000)  # yeni seans başı → _beginOutput KOŞULSUZ edinim armlar (freqChanged=false)
    for _ in range(30000):  # ESP'yi periyot ortasına getir
        m.timer_tick()
    assert m.tick == 30000  # ön-doğrulama: darbe gerçekten periyot ortasında gelecek
    m.sync_pulse()
    assert m.tick == 0, (
        "ilk PB1 darbesi faz kilidini EDİNMEDİ (s_tick sıfırlanmadı) — aynı frekanslı sabit-ofsetli "
        "çift periyot ortasında sonsuza dek 'ignored' kalır, komut edilen faz deseni yanlış (E4)"
    )
    assert m.locked >= 1, "edinim kilidi telemetride sayılmadı"


def test_KRITIK_E4_edinim_sonrasi_ayni_freq_STABIL_kilitli_kalir():
    """Edinim faz penceresine SOKAR; sonrasında aynı-freq çift tolerans dalıyla kilitli kalmalı,
    DC-yapışma latch'i YANLIŞ tetiklenmemeli (edinim sonrası doğal wrap normal akar)."""
    m = _SyncModel(tpp=50000)
    m.start(tpp=50000)
    for _ in range(30000):
        m.timer_tick()
    m.sync_pulse()  # EDİNİM: tick=0
    # Sonraki periyotlar: STM aynı freq → her ~tpp tick'te bir darbe, ESP wrap'la hizalı gelir.
    for _ in range(10):
        for _ in range(50000):
            m.timer_tick()
        m.sync_pulse()
    assert not m.sync_disabled, "edinim sonrası aynı-freq çift DC-yapışma sandı (yanlış disable)"
    assert m.locked >= 11, "edinim sonrası tolerans kilidi sürmedi"


def test_MODEL_AYIRT_EDIYOR_E4_edinimsiz_orta_darbe_kilit_KURAMAZ():
    """Ayrıştırıcı: edinim ARMLANMADAN (start çağrılmadan, doğrudan active) periyot-ortası darbe
    kilit KURAMAZ — mevcut tolerans davranışı. E4 kapısı yeni yeteneği ölçüyor, tolerans dalını
    değil; kapı kendi varsayımını doğrulamıyor."""
    m = _SyncModel(tpp=50000)
    m.active = True  # start() ÇAĞIRMADAN → awaiting_acquire FALSE kalır
    for _ in range(30000):
        m.timer_tick()
    m.sync_pulse()
    assert m.tick == 30000 and m.ignored == 1 and m.locked == 0, (
        "edinim armlanmadan orta darbe kilitledi — model tolerans ile edinimi AYIRMIYOR"
    )


def test_KRITIK_C_syncPulseISR_edinim_kapilardan_SONRA_tolerans_ONCE():
    """Yapısal kapı (yorum-soyulmuş kaynak): edinim dalı !s_active + s_sync_disabled kapılarından
    SONRA (HG-3/[4.3] bozulmasın) AMA tolerans (tol) mantığından ÖNCE (orta-periyot darbe hâlâ
    ignored'a düşmeden edinsin)."""
    cpp = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    i = cpp.index("static void IRAM_ATTR syncPulseISR()")
    j = cpp.index("static void", i + 10)
    govde = cpp[i:j]
    a = govde.find("!s_active")
    d = govde.find("s_sync_disabled")
    e = govde.find("s_awaiting_acquire")
    tol = govde.find("tol")
    assert e >= 0, "syncPulseISR'da s_awaiting_acquire edinim dalı YOK (E4)"
    assert 0 <= a < e and 0 <= d < e, (
        "edinim dalı !s_active / s_sync_disabled kapılarından ÖNCE — pasif ya da uyumsuz seansta "
        "yanlış edinim; HG-3 DC-yapışma latch'i ve [4.3] pasif-darbe koruması BOZULUR"
    )
    assert 0 <= e < tol, (
        "edinim dalı tolerans (tol) mantığından SONRA — orta-periyot darbe yine 'ignored'a düşer, "
        "edinim hiç çalışmaz (E4 etkisiz)"
    )


def test_KARSIT_KANIT_C_edinim_iki_yerde_armlanir():
    """Edinim seans başında (_beginOutput KOŞULSUZ) ve freq değişiminde (_updatePWM freqChanged)
    armlanmalı — biri eksikse aynı-freq restart / freq değişimi faz edinemez."""
    cpp = (S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace")
    i = cpp.index("void CoilController::_beginOutput")
    bg = cpp[i : i + 1400]
    assert "s_awaiting_acquire = true" in bg, (
        "_beginOutput seans başında edinimi armlamıyor — AI Pro aynı-freq (1 Hz) yeniden başlatmada "
        "freqChanged=false, faz HİÇ yeniden edinilemez (E4)"
    )
    k = cpp.index("void CoilController::_updatePWM")
    ug = cpp[k : k + 2200]
    fc = ug.index("if (freqChanged)")
    blok = ug[fc : ug.index("}", fc)]
    assert "s_awaiting_acquire = true" in blok, (
        "_updatePWM freqChanged bloğunda edinim armlanmıyor — mid-seans freq değişiminde faz yeniden edinilmez (E4)"
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
