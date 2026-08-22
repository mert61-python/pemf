# Author: mertaygn, cglrgrkn
"""ESP KARDEŞ-BİRİM PARİTESİ — 2. tur denetimi bulguları [5.1] + [5.2] + [5.3] (2026-08-20).

Bu deponun 1 numaralı hata deseni "aynı kural, iki transport — biri uyguluyor öteki uygulamıyor"dur;
S3 ve 8266 kardeş dosyalarında üç sözleşme ayrışması ölçülmüştü (bugün tüketicisiz/latent, ama
S3+8266 REFLASH beklerken kapatmak en ucuz an — alanı okuyacak İLK tüketici yanlış değeri alırdı):

  [5.1] `pwm_remaining_time` AYNI JSON anahtarı iki kardeşte FARKLI BİRİM: 8266 milisaniye,
        S3 saniye yayınlıyordu → bobin 8 için 1000× yanlış kalan-süre.
  [5.2] 8266 `restorePWMState` `_pwmDurationSec`'i geri kurmuyordu → resume sonrası SÜRELİ seans
        status'ta `pwm_duration=0` (= SÜRESİZ nöbetçisi!) raporlanıyordu (S3 loadState doğru kurar).
  [5.3] S3 `CMD_UPDATE_PARAMS` fazı KOŞULSUZ uyguluyordu: parse katmanı `phase` anahtarı YOKKEN
        0 doldurur ([FIX-3]) → fazsız bir set_params çok-bobinli faz desenini sessizce sıfırlardı
        (freq/duty ">0 ise değiştir" korumalıyken faz korumasızdı; 0 meşru faz değeri olduğundan
        çözüm parse'ta AYRI "belirtilmedi" nöbetçisi: PHASE_BELIRTILMEDI=-1).

⚠️ C bu makinede derlenemez — kapılar YORUM-SOYULMUŞ kaynakta yapısal (bu deponun firmware
doğrulama disiplini: [1.3]/[4.3] ile aynı); REFLASH tezgâh adımları VERIFICATION §11-12 oturumunda.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"
E8 = KOK / "firmware" / "esp8266_pemf_coil"


from c_soyucu import c_soy as _c_soy  # 17. parti: string-bilinçli soyucu (yorum-yutma fix'i)


def _govde(soyulmus: str, baslangic: str, bitis: str) -> str:
    """`bitis` bulunamazsa (son fonksiyon) dosya sonuna kadar."""
    i = soyulmus.index(baslangic)
    j = soyulmus.find(bitis, i + len(baslangic))
    return soyulmus[i:j] if j > 0 else soyulmus[i:]


def test_KRITIK_5_1_pwm_remaining_time_iki_kardeste_SANIYE():
    """Aynı JSON anahtarı aynı birimi taşımalı. S3 saniye (referans); 8266 da saniyeye çevirmeli."""
    s3 = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    e8 = _c_soy((E8 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))

    s3_gs = _govde(s3, "PWMState CoilController::getState()", "\nbool ")
    assert "/ 1000UL" in s3_gs, (
        "S3 getState artık saniyeye çevirmiyor — referans taraf değişti, sözleşmeyi yeniden kararlaştır"
    )

    e8_ps = _govde(e8, "void CoilController::populateStatus", "\nunsigned long ")
    i_rt = e8_ps.index("data.pwm_remaining_time")
    atama = e8_ps[i_rt : e8_ps.index(";", i_rt)]
    assert "/ 1000" in atama, (
        f"8266 pwm_remaining_time HAM MİLİSANİYE yayınlıyor ({atama.strip()!r}) — S3 aynı anahtarı "
        "SANİYE yayınlar; alanı okuyacak ilk tüketici bobin 8 için 1000× yanlış kalan-süre görür (bulgu [5.1])"
    )


def test_KRITIK_5_2_8266_restore_pwmDurationSec_gerikurar():
    """Resume sonrası SÜRELİ seans status'ta duration=0 (süresiz nöbetçisi) raporlamamalı —
    S3 loadState `_durationSec`i kalan süreden kurar; 8266 paritesi."""
    e8 = _c_soy((E8 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    govde = _govde(e8, "bool CoilController::restorePWMState()", "\nvoid ")
    m = re.search(r"_pwmDurationSec\s*=", govde)
    assert m, (
        "8266 restorePWMState _pwmDurationSec'i geri KURMUYOR — resume sonrası süreli seans "
        "status'ta pwm_duration=0 (SÜRESİZ nöbetçisi) raporlar, kalan-süreyle çelişir (bulgu [5.2])"
    )
    assert "remaining" in govde[m.start() : m.start() + 200], (
        "geri kurulan değer kalan süreden türetilmiyor (bayat orijinal süre kalan süreyi yanlış gösterir)"
    )


def test_KRITIK_5_3_S3_parse_fazsiz_update_NOBETCI_doldurur():
    """UPDATE'te `phase` anahtarı YOKSA 0 değil PHASE_BELIRTILMEDI dolmalı (0 meşru faz
    değeridir — 'yok' ile karıştırılamaz). START'ta varsayılan 0 KALIR (taze seansın doğal
    başlangıcı) — karşıt-kanıt aşağıda ayrıca. (SET_PARAMS dalı 15. partide sahip kararıyla
    KALDIRILDI — bkz. test_olu_komut_yuzeyleri_kaldirildi.py; kural artık yalnız UPDATE'te.)"""
    sd = (S3 / "SharedDefs.h").read_text(encoding="utf-8", errors="replace")
    assert "#define PHASE_BELIRTILMEDI" in sd, "PHASE_BELIRTILMEDI nöbetçisi tanımsız"

    nm = _c_soy((S3 / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace"))
    update_dali = _govde(nm, 'cmdStr == "UPDATE"', 'cmdStr == "SELFTEST"')
    assert "PHASE_BELIRTILMEDI" in update_dali, (
        "UPDATE dalında fazsız payload hâlâ 0 dolduruyor — fazsız update çok-bobinli "
        "faz desenini sessizce sıfırlar (bulgu [5.3])"
    )


def test_KRITIK_5_3_S3_controller_fazi_yalniz_BELIRTILMISSE_degistirir():
    """CMD_UPDATE_PARAMS: freq/duty gibi faz da 'belirtildiyse değiştir' — koşulsuz atama yasak."""
    cc = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    govde = _govde(cc, "case CMD_UPDATE_PARAMS", "case CMD_SELF_TEST")
    k = govde.find("PHASE_BELIRTILMEDI")
    assert k >= 0, "CMD_UPDATE_PARAMS faz ataması korumasız — fazsız komut fazı 0'a sıfırlar (bulgu [5.3])"
    i_atama = govde.index("_phase =")
    assert k < i_atama, "nöbetçi kontrolü faz atamasından SONRA — koruma etkisiz"


def test_KARSIT_KANIT_5_3_START_fazi_varsayilan_SIFIR_kalir():
    """Taze START'ta faz belirtilmemişse 0 doğru varsayılandır (yeni seans deseni) — nöbetçi
    aşırı-genişleyip start'ı bozmamalı. (SYNC_ALL dalı 15. partide kaldırıldı — yokluğu
    test_olu_komut_yuzeyleri_kaldirildi.py kilitler.)"""
    nm = _c_soy((S3 / "NetworkManager.cpp").read_text(encoding="utf-8", errors="replace"))
    start_dali = _govde(nm, 'cmdStr == "START"', 'cmdStr == "STOP"')
    assert ": 0" in start_dali and "PHASE_BELIRTILMEDI" not in start_dali, (
        "START dalında faz varsayılanı bozuldu — fazsız taze start artık başlayamaz/yanlış başlar"
    )


def test_KARSIT_KANIT_5_2_suresiz_resume_durationSec_SIFIR():
    """Süresiz resume'da `_pwmDurationSec` 0 KALMALI (süresiz sözleşmesi) — [5.2] düzeltmesi
    yalnız süreli dalı doldurur."""
    e8 = _c_soy((E8 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    govde = _govde(e8, "bool CoilController::restorePWMState()", "\nvoid ")
    assert re.search(r"_pwmDurationSec\s*=[^;]*\?[^;]*:\s*0\s*;", govde) or re.search(
        r"state\.duration\s*>\s*0", govde[govde.index("_pwmDurationSec") - 300 : govde.index("_pwmDurationSec") + 300]
    ), "süresiz resume'da durationSec 0 kalacağı görünmüyor — süresiz sözleşme nöbetçisi bozulabilir"
