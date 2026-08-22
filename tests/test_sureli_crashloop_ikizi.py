# Author: mertaygn, cglrgrkn
"""SÜRELİ seans crash-loop İKİZİ — 2. tur denetimi açık bulgusu, sahip onayıyla kapatıldı (2026-08-20).

[1.3]/F2 turu SÜRESİZ moda resume TABANI getirdi (her resume NVS_KAYIT_ARALIGI_MS taban sayılır,
hemen kalıcılaşır) ama SÜRELİ resume'a taban BİLEREK uygulanmamıştı (klinik semantik değişikliği →
sahip kararı). Ölçülen ikiz delik: süreli seansta `elapsed` yalnız periyodik kayıtla (30 sn) büyür;
<30 sn periyotlu çök-diril döngüsünde HİÇBİR periyodik kayıt koşamaz → `remaining` her resume'da
aynı kalır → 20 dk'lık seans patolojik brown-out döngüsünde SÜRESİZ sürer (bobin çevrim başına
~20-30 sn enerjili; termal kesme son sınır). Sahip onayı 2026-08-20: taban süreli dala da uygulanır.

DÜZELTME (iki kardeş, aynı sözleşme): resume'da kalan-süre hesabına devralınan elapsed'in üstüne
BİR KAYIT ARALIĞI (NVS_KAYIT_ARALIGI_MS — periyodik kayıtla TEK KAYNAK) eklenir; taban dahil süre
dolmuşsa resume HİÇ yapılmaz (fail-safe: bobin kapalı kalır). Resume-anı kaydı zaten
`duration=KALAN, elapsed≈0` yazdığından (8266 savePWMState / S3 _beginOutput→forceSaveState,
her ikisi bu dosyada modellenir) taban otomatik kalıcılaşır → döngü her çevrimde ≥30 sn kısalır.
Yön FAIL-SAFE: seans resume başına EN FAZLA bir aralık ERKEN biter; UZAMASI artık imkânsız.
Yan kazanç: 8266 boot-anı EEPROM.commit tekrarı artık süre/30sn çevrimle SINIRLI (aşınma yolu kapandı).

⚠️ C bu makinede derlenemez — davranış Python modeliyle (kayıt sözleşmesi birebir), kaynak
yorum-soyulmuş yapısal kapılarla kilitlenir; tezgâh adımı VERIFICATION §14.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"
E8 = KOK / "firmware" / "esp8266_pemf_coil"

ARALIK_MS = 30_000  # NVS_KAYIT_ARALIGI_MS (SharedDefs.h — iki kardeşte aynı değer, testte sabitlenir)


from c_soyucu import c_soy as _c_soy  # 17. parti: string-bilinçli soyucu


def _govde(soyulmus: str, baslangic: str, bitis: str) -> str:
    i = soyulmus.index(baslangic)
    j = soyulmus.find(bitis, i + len(baslangic))
    return soyulmus[i:j] if j > 0 else soyulmus[i:]


# ---------------------------------------------------------------------------
# DAVRANIŞ MODELİ — iki kardeşin resume+kayıt sözleşmesi (kaynakla birebir):
#   resume: kalan = duration - (elapsed + TABAN); kalan<=0 → resume YOK
#   resume-anı kaydı: duration=KALAN, elapsed=0  (8266 savePWMState: state.duration=_pwmDuration,
#   state.elapsed=millis-_pwmStartTime≈0 · S3 saveState: durationSec=_durationSec, elapsedMs≈0)
# ---------------------------------------------------------------------------


def _resume(state: dict, taban_uygula: bool) -> dict | None:
    if not state["active"]:
        return None
    if state["duration_ms"] > 0:
        devralinan = state["elapsed_ms"] + (ARALIK_MS if taban_uygula else 0)
        if devralinan >= state["duration_ms"]:
            return None  # süre doldu → bobin KAPALI kalır (fail-safe)
        kalan = state["duration_ms"] - devralinan
        return {"active": True, "duration_ms": kalan, "elapsed_ms": 0}
    # süresiz dal bu modelin dışında ([1.3]/F2 zaten kapattı) — ayrı karşıt-kanıtla kilitli
    return {"active": True, "duration_ms": 0, "elapsed_ms": 0}


def _crash_dongusu(duration_ms: int, cevrim_ms: int, taban_uygula: bool, max_cevrim: int = 100_000):
    """<ARALIK periyotlu çök-diril: her çevrimde resume olur, periyodik kayıt KOŞAMAZ
    (cevrim_ms < ARALIK_MS) → bir sonraki boot resume-anı kaydını okur. Biten çevrim no'su
    ya da None (hiç bitmedi) döner."""
    assert cevrim_ms < ARALIK_MS, "senaryo tanımı: periyodik kayıt koşamayan döngü"
    state = {"active": True, "duration_ms": duration_ms, "elapsed_ms": 0}
    for i in range(max_cevrim):
        state = _resume(state, taban_uygula)
        if state is None:
            return i
    return None


def test_KRITIK_model_tabanSIZ_sureli_seans_HIC_bitmiyor_tabanLI_sinirli():
    """Bulgunun kendisi + düzeltmenin kanıtı tek modelde: 20 dk seans, 20 sn'lik çök-diril."""
    assert _crash_dongusu(20 * 60_000, 20_000, taban_uygula=False) is None, (
        "modelde tabansız döngü bitti — model bulguyu artık temsil etmiyor, senaryoyu yeniden türet"
    )
    biten = _crash_dongusu(20 * 60_000, 20_000, taban_uygula=True)
    assert biten is not None and biten <= (20 * 60_000) // ARALIK_MS, (
        f"tabanlı döngü {biten} çevrimde bitmedi/geç bitti — taban kalıcılaşmıyor demektir"
    )


def test_model_ayristirici_kayit_kontrati_bozulursa_yakalar():
    """Ayrıştırıcı: resume-anı kaydı KALAN yerine ORİJİNAL süreyi yazsaydı (elapsed=0 ile)
    taban etkisi her çevrimde silinir, döngü yine bitmezdi — model bu farkı görüyor."""
    state = {"active": True, "duration_ms": 20 * 60_000, "elapsed_ms": 0}
    for _ in range(50):
        yeni = _resume(state, taban_uygula=True)
        if yeni is None:
            break
        # bozuk kontrat: duration'ı ilk değere geri yaz (kalıcılaşma yok)
        state = {"active": True, "duration_ms": 20 * 60_000, "elapsed_ms": 0}
    else:
        return  # 50 çevrimde bitmedi — bozuk kontratın bitiremeyeceğini gösterdik
    raise AssertionError("bozuk kayıt kontratı döngüyü bitirdi — ayrıştırıcı anlamsızlaşmış")


def test_KARSIT_KANIT_tek_resume_kaybi_en_fazla_bir_aralik():
    """Fail-safe zarfı: normal tek kesinti (çevrim > aralık senaryosu değil, tek resume) —
    seans EN FAZLA bir aralık erken biter, daha fazla DEĞİL."""
    state = {"active": True, "duration_ms": 10 * 60_000, "elapsed_ms": 4 * 60_000}
    yeni = _resume(state, taban_uygula=True)
    assert yeni is not None
    kayip = (10 * 60_000 - 4 * 60_000) - yeni["duration_ms"]
    assert kayip == ARALIK_MS, f"tek resume kaybı {kayip}ms — tam bir aralık olmalı (ne az ne çok)"


# ---------------------------------------------------------------------------
# YAPISAL KAPILAR — yorum-soyulmuş kaynakta düzeltmenin varlığı
# ---------------------------------------------------------------------------


def test_KRITIK_S3_loadState_sureli_dala_taban_ekli():
    """S3 loadState: kalanMs hesabı devralınan elapsedMs'in üstüne NVS_KAYIT_ARALIGI_MS eklemeli.

    17. parti sertleştirmesi (adversaryal test-gaming bulgusu): eski kapı yalnız token VARLIĞINA
    bakıyordu — `+`→`-` işaret-çevirme mutasyonu (her resume süreyi 30 sn UZATIR: kusurun beteri)
    ve token'ı bir LOG string'ine taşıma mutasyonu YEŞİL kalıyordu (ampirik kanıtlandı). Artık
    TAM İFADE pinli: hem toplama yönü hem çıkarmanın kalanMs'e uygulanışı kilitli."""
    cc = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    govde = _govde(cc, "void CoilController::loadState()", "\nvoid ")
    i0 = govde.index("s.durationSec > 0")
    i1 = govde.index("_durationSec = ", i0)
    sureli_dal = govde[i0:i1]
    assert re.search(
        r"kalanMs\s*=\s*\(long\)\s*s\.durationSec\s*\*\s*1000L\s*-\s*"
        r"\(long\)\s*\(\s*s\.elapsedMs\s*\+\s*NVS_KAYIT_ARALIGI_MS\s*\)",
        sureli_dal,
    ), (
        "S3 süreli resume tabanı TAM İFADE olarak yok/bozulmuş — <30 sn crash-loop'ta kalan süre "
        "hiç azalmaz ya da (işaret ters çevrildiyse) her resume'da UZAR (sahip-onaylı ikiz düzeltmesi)"
    )


def test_KRITIK_8266_restore_sureli_dala_taban_ekli():
    """8266 restorePWMState: remaining hesabı devralınan elapsed'in üstüne NVS_KAYIT_ARALIGI_MS
    eklemeli — 17. parti sertleştirmesi: TAM İFADE pinli (S3 kardeşiyle aynı gerekçe)."""
    cc = _c_soy((E8 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    govde = _govde(cc, "bool CoilController::restorePWMState()", "\nvoid ")
    i0 = govde.index("state.duration > 0")
    i1 = govde.index("_pwmFrequency = state.frequency", i0)
    sureli_dal = govde[i0:i1]
    assert re.search(r"devralinan\s*=\s*state\.elapsed\s*\+\s*NVS_KAYIT_ARALIGI_MS", sureli_dal), (
        "8266 süreli resume tabanı TAM İFADE olarak yok/bozulmuş (ikiz düzeltmesi)"
    )
    assert re.search(r"remaining\s*=\s*state\.duration\s*-\s*devralinan", sureli_dal), (
        "taban remaining hesabına uygulanmıyor — token başka yerde duruyor olabilir (gaming koruması)"
    )


def test_KARSIT_KANIT_suresiz_taban_mekanizmasi_DOKUNULMAMIS():
    """[1.3]/F2'nin süresiz tabanı iki kardeşte aynen durmalı — ikiz düzeltmesi onu bozamaz."""
    s3 = _c_soy((S3 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    e8 = _c_soy((E8 / "CoilController.cpp").read_text(encoding="utf-8", errors="replace"))
    assert re.search(r"s\.durationSec\s*==\s*0\s*\)\s*\?\s*\(\s*s\.elapsedMs\s*\+\s*NVS_KAYIT_ARALIGI_MS", s3), (
        "S3 süresiz resume tabanı ([1.3]) kaybolmuş/değişmiş"
    )
    assert re.search(r"state\.duration\s*==\s*0\s*\)\s*\?\s*\(\s*state\.elapsed\s*\+\s*NVS_KAYIT_ARALIGI_MS", e8), (
        "8266 süresiz resume tabanı ([1.3]) kaybolmuş/değişmiş"
    )
