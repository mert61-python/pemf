# Author: mertaygn, cglrgrkn
"""FREKANS ARTIŞINDA BAYAT DUTY — `g_duty_ticks` yeni periyoda ölçeklenmeli.

DENETİM BULGUSU (2026-08-17). `firmware/main.c` ISR'ında `g_tpp[i]` (periyot uzunluğu) `pending`
uygulanır uygulanmaz güncelleniyor, ama fiili duty tick sayısı `g_duty_ticks[i]` **eski periyodun
ölçeğinde** kalıyordu. `tpp-1` güvenlik klempi ise YALNIZ `if (period_reset)` bloğunun içindedir.

Kök neden tek cümleyle: **`g_duty_ticks` bir TICK SAYISIdır ve yalnız `tpp`'ye göre anlam taşır;
`tpp` değişince yeniden ölçeklenmezse sessizce BAŞKA bir duty oranı demeye başlar.**

Bağımsız iki ISR modeliyle ölçülen iki etki (`ref_ms` her pakette gönderilir → sahadaki hâl):
  (a) bayat `g_duty_ticks >= yeni tpp` → `state = (adj < duty)` her tick'te 1 → IN_A sürekli HIGH:
      1 Hz %50 → 2 Hz geçişinde **1000 ms kesintisiz tek-polarite** (meşru zarf 500 ms → 2×).
  (b) ilk `period_reset`'te klemp duty'yi `tpp-1` (=**%99,8**) yapıyor → bobin, operatörün
      İSTEMEDİĞİ bir duty ile sürülüyor ve aşağı-slew ile 15-19 periyotta iniyor.
      ⚠️ İLK ANALİZİM BURADA YANLIŞTI ve model beni düzeltti: "ilk 500 ms'de dozun 4,78×'i"
      ölçümü aşağı-slew'i de kusur sayıyordu, oysa o rampa KASITLI (inrush/EMI) ve %50→%5
      geçişi enerjiyi AZALTIR. Doğru ve savunulabilir değişmez: **geçiş, duty oranını iki uç
      noktanın (eski oran, yeni hedef) hiçbirinin üstüne çıkarmamalı.** %99,8 ikisini de aşıyor.

Sevk edilen arayüzden erişilebilir (iki yol): `CoilParameterPanel.tsx`'in `isDisabled` koşulunda
`running` YOK (çalışan bobinde Başlat aktif) ve `/api/session/start` çalışan bobinler için hiçbir
interlock uygulamıyor.

⚠️⚠️ BU TESTLERİN SINIRI — DÜRÜST BEYAN: burada koşan şey C kodu DEĞİL, ISR'ın Python modelidir
(`tests/test_firmware_stop_latency.py` ile aynı yaklaşım ve aynı sınır). Model, düzeltmenin
DOĞRU DAVRANIŞINI ve ölçülen sayıları kilitler; C kaynağındaki düzeltmenin varlığını ise ayrı bir
YAPISAL kapı denetler (aşağıda). **Hiçbiri tezgâh doğrulaması değildir** — gerçek donanımda
ölçülmeden yayınlanması önerilmez.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FW = Path(__file__).resolve().parent.parent / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


@pytest.fixture(scope="module")
def src():
    return FW.read_text(encoding="utf-8", errors="replace")


def _sabit(src: str, ad: str) -> float:
    """`#define <ad> <sayi>` değerini main.c'den OKU (kopyalama yok)."""
    m = re.search(rf"#define\s+{ad}\s+.*?([0-9]+(?:\.[0-9]+)?)f?", src, re.DOTALL)
    assert m, f"{ad} main.c'de bulunamadi"
    return float(m.group(1))


# ── ISR modeli ────────────────────────────────────────────────────────────────


def _kosu(isr_hz, fullscale, dead, f0, d0, f1, d1, tick_sayisi, olcekle: bool, ref_orani=0.37):
    """ISR'ı modelle; `olcekle=False` = düzeltme ÖNCESİ (bayat tick), `True` = SONRASI.

    Döner: (en uzun kesintisiz A-ON tick, toplam A-ON tick, gözlenen EN YÜKSEK duty ORANI).

    ⚠️ `ref_orani`: `ref_ms` hizalaması tick'i sıfıra ÇEKMEZ —
    `new_tick = ((ref_ms % period_ms) * tpp) / period_ms` genelde periyodun ORTASINDA bir değerdir.
    İlk modellemede tick=0 varsayıldı ve `period_reset` hemen ateşleyip klempi uyguladığı için
    kusur GÖRÜNMÜYORDU (yanlış-yeşil). Gerçekçi hâl: periyot ortasından başlamak.
    """

    def tpp_of(f):
        return int(isr_hz / f)

    def slew_of(f, tpp):
        s = int(tpp / (f * fullscale))
        return max(1, s)

    tpp = tpp_of(f0)
    duty_t = int(d0 * tpp)  # bobin zaten kararlı çalışıyor
    target = duty_t
    slew = slew_of(f0, tpp)
    tick = 0

    # --- parametre değişikliği uygulanır (pending bloğu) ---
    eski_tpp = tpp
    tpp = tpp_of(f1)
    target = int(d1 * tpp)
    slew = slew_of(f1, tpp)
    if olcekle:
        # DÜZELTME: tick sayısını YENİ periyoda ölçekle (oran korunur) + ANINDA klemple.
        if eski_tpp > 0 and tpp != eski_tpp and duty_t > 0:
            duty_t = int((duty_t / eski_tpp) * tpp)
        max_d = max(0, tpp - 1 - int(dead))
        duty_t = min(duty_t, max_d)
    # `ref_ms` hizalaması (sahada her paket taşır) — periyot ORTASI, sıfır DEĞİL.
    tick = int(tpp * ref_orani) % tpp

    en_uzun = 0
    art_arda = 0
    a_on = 0
    en_yuksek_oran = 0.0
    for _ in range(tick_sayisi):
        period_reset = tick == 0
        if period_reset:
            if target <= 0:
                duty_t = 0
            else:
                err = max(-slew, min(slew, target - duty_t))
                duty_t = max(0, duty_t + err)
            max_d = max(0, tpp - 1 - int(dead))
            duty_t = min(duty_t, max_d)

        en_yuksek_oran = max(en_yuksek_oran, duty_t / tpp if tpp else 0.0)

        state = 1 if tick < duty_t else 0
        if state:
            a_on += 1
            art_arda += 1
            en_uzun = max(en_uzun, art_arda)
        else:
            art_arda = 0

        tick += 1
        if tick >= tpp:
            tick = 0
    return en_uzun, a_on, en_yuksek_oran


# ── Etki (a): kesintisiz tek-polarite ────────────────────────────────────────


def test_KRITIK_frekans_artisinda_UZUN_tek_polarite_OLMAZ(src):
    """1 Hz %50 → 2 Hz %50 geçişinde kesintisiz A-ON, meşru zarfı AŞMAMALI."""
    isr = _sabit(src, "DDS_ISR_HZ")
    fs = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    dead = _sabit(src, "DDS_DEAD_TIME_TICKS")

    mesru = int(isr / 2.0 * 0.5)  # 2 Hz %50 → periyot başına 12 500 tick = 250 ms
    en_uzun, _, _ = _kosu(isr, fs, dead, 1.0, 0.5, 2.0, 0.5, int(isr * 2), olcekle=True)

    assert en_uzun <= mesru + 1, (
        f"kesintisiz A-ON {en_uzun} tick ({en_uzun / isr * 1000:.0f} ms) — mesru zarf {mesru} tick "
        f"({mesru / isr * 1000:.0f} ms). Bayat duty tick'i yeni periyodu asiyor → tek yonlu DC."
    )


def test_duzeltme_ONCESI_model_uzun_tek_polarite_URETIR_capa(src):
    """Çıpa: modelin kusuru GERÇEKTEN üretebildiğini gösterir (yoksa yukarıdaki test boş olurdu)."""
    isr = _sabit(src, "DDS_ISR_HZ")
    fs = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    dead = _sabit(src, "DDS_DEAD_TIME_TICKS")

    mesru = int(isr / 2.0 * 0.5)
    en_uzun, _, _ = _kosu(isr, fs, dead, 1.0, 0.5, 2.0, 0.5, int(isr * 2), olcekle=False)

    assert en_uzun > mesru, (
        "model, duzeltme kapatilinca da uzun tek-polarite uretmiyor → yukaridaki test ANLAMSIZ. "
        f"olculen: {en_uzun}, mesru: {mesru}"
    )


# ── Etki (b): ilk 500 ms'de doz aşımı ────────────────────────────────────────


@pytest.mark.parametrize("f1,d1", [(100.0, 0.25), (100.0, 0.05), (50.0, 0.25), (4.0, 0.5)])
def test_KRITIK_gecis_duty_orani_IKI_UCTAN_da_YUKSEGE_cikmaz(src, f1, d1):
    """Doğru değişmez: geçiş sırasında duty oranı, ESKİ ve YENİ hedefin ikisini de AŞMAMALI.

    ⚠️ NEDEN "ilk 500 ms dozu" DEĞİL: aşağı-slew KASITLIDIR (`main.c` yorumu: "Enerjiyi ARTIRAN
    yön hâlâ sınırlıdır (inrush/EMI koruması)") ve %50'den %5'e inmek zaten enerji AZALTIR — orada
    bir "aşım" yoktur. İlk modellemem 500 ms'lik doz penceresi ölçüyordu ve bu meşru rampayı kusur
    sanıyordu. Gerçek kusur: klemp duty'yi `tpp-1` (=%99,8) yapıp iki uç noktanın da ÜSTÜNE
    çıkarıyordu — yani bobin, hiç istenmemiş bir duty ile sürülüyordu."""
    isr = _sabit(src, "DDS_ISR_HZ")
    fs = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    dead = _sabit(src, "DDS_DEAD_TIME_TICKS")

    tavan = max(0.5, d1)  # eski oran %50, yeni hedef d1
    _, _, en_yuksek = _kosu(isr, fs, dead, 1.0, 0.5, f1, d1, int(isr * 1), olcekle=True)

    assert en_yuksek <= tavan + 0.01, (
        f"gecis sirasinda duty %{en_yuksek * 100:.1f}'e cikti; iki uc nokta %{0.5 * 100:.0f} ve "
        f"%{d1 * 100:.0f}. Hicbiri istenmedi → hekimin girdigi parametreye sadakat kaybi."
    )


def test_duzeltme_ONCESI_model_duty_asimi_URETIR_capa(src):
    """Çıpa: klempin duty'yi ~%99,8'e çıkardığını modelde gösterir."""
    isr = _sabit(src, "DDS_ISR_HZ")
    fs = _sabit(src, "DDS_SLEW_FULLSCALE_S")
    dead = _sabit(src, "DDS_DEAD_TIME_TICKS")

    _, _, en_yuksek = _kosu(isr, fs, dead, 1.0, 0.5, 100.0, 0.05, int(isr * 1), olcekle=False)

    assert en_yuksek > 0.9, (
        f"model duzeltme kapaliyken duty'yi ~%99,8'e cikarmiyor (olculen %{en_yuksek * 100:.1f}) "
        "→ yukaridaki degismez testi ANLAMSIZ olurdu"
    )


# ── Yapısal kapı: C kaynağında düzeltme GERÇEKTEN var mı? ────────────────────


def test_KRITIK_pending_blogu_duty_tickI_YENI_periyoda_olcekler(src):
    """`pending` uygulanırken `g_duty_ticks` yeniden ölçeklenip klemplenmeli.

    ⚠️ Bu, model testlerinin KAPATAMADIĞI boşluk: model C kodunu değil kendini koşturur. Bu kapı
    düzeltmenin kaynakta durduğunu denetler.
    ⚠️ YORUM SATIRLARI ATILIR — aksi halde kusuru AÇIKLAYAN bir yorum düzeltme sanılabilir ya da
    tersine, doğru deseni anlatan bir yorumla kapı geçilebilirdi.
    """
    # ⚠️ SIRA ÖNEMLİ: yorumlar ÖNCE atılır, sınırlar SONRA bulunur. Aksi halde açıklama
    # yorumlarında geçen `if (period_reset)` metni bitiş çıpası sanılıp blok YARIDA kesiliyordu
    # (ilk yazımda tam bu oldu). Kapı yalnız YÜRÜTÜLEN satırlara bakar.
    kodsuz = "\n".join(s for s in src.splitlines() if not s.strip().startswith(("*", "/*", "//")))
    bas = kodsuz.index("if (g_shadow.pending)")
    son = kodsuz.index("if (period_reset)", bas)
    blok = kodsuz[bas:son]

    assert "g_duty_ticks" in blok, (
        "`pending` blogu `g_duty_ticks`e HIC dokunmuyor → tick sayisi ESKI periyodun olceginde "
        "kalir ve `tpp-1` klempi yalniz `period_reset` icinde oldugu icin bir periyot boyunca "
        "tek-polarite DC surus olusur (olculdu: 1 Hz -> 2 Hz'de 1000 ms)."
    )
    assert "eski_tpp" in blok or "old_tpp" in blok, (
        "yeniden olcekleme icin ESKI tpp saklanmiyor → yalniz klemplemek etki (b)'yi (ilk 500 ms'de "
        "4,78x doz asimi) COZMEZ; oran korunmalidir."
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))


def test_TEZGAH_DOGRULAMASI_UYARISI_sessizce_KAYBOLAMAZ():
    """⚠️ `[FIX-1c]` C kodunda VARSA, tezgâh doğrulama prosedürü de belgede DURMAK ZORUNDA.

    Bu düzeltme gerçek donanımda ÖLÇÜLMEDİ: koşan şey C kodu değil, ISR'ın Python modelidir.
    Böyle bir kaydın en tehlikeli yanı SESSİZCE KAYBOLMASIDIR — bir sonraki geliştirici yeşil bir
    süit görüp "doğrulanmış" sanır ve tıbbi cihazı tezgâh ölçümü olmadan yayınlar. Bu kapı, uyarının
    ve ölçüm prosedürünün `docs/VERIFICATION.md`de kalmasını zorunlu kılar.

    ⚠️ Ölçüt METİN ARAMASI ama kandırılamaz biçimde kurulu: burada aranan şey bir KOD DESENİ değil,
    bir BELGE BÖLÜMÜNÜN VARLIĞI. "Doğru deseni anlatan bir yorum yazarak" geçmek anlamsızdır —
    geçmenin tek yolu prosedürü gerçekten belgede tutmaktır.
    ⚠️ Kapı, düzeltme C kaynağından KALDIRILIRSA kendiliğinden susar (o zaman uyarının konusu da
    kalmaz) — yani belgeyi gereksiz yere kilitlemez.
    """
    fw = FW.read_text(encoding="utf-8", errors="replace")
    if "[FIX-1c]" not in fw:
        pytest.skip("firmware duzeltmesi kaldirilmis → tezgah uyarisinin konusu kalmadi")

    belge = Path(__file__).resolve().parent.parent / "docs" / "VERIFICATION.md"
    assert belge.exists(), "docs/VERIFICATION.md YOK"
    metin = belge.read_text(encoding="utf-8", errors="replace")

    eksik = [
        p
        for p in (
            "[FIX-1c]",  # hangi düzeltmeden söz ettiği
            "TEZGÂHTA ÖLÇÜLMEDİ",  # açık uyarı
            "1 Hz → 100 Hz",  # asıl ölçüm vakası
            "250 ms",  # kabul ölçütü
            "IKI UC" if "IKI UC" in metin else "HİÇBİRİNİ",  # doğru değişmez (oran ölçütü)
        )
        if p not in metin
    ]
    assert not eksik, (
        f"docs/VERIFICATION.md'de tezgah dogrulama prosedurunun parcalari EKSIK: {eksik}. "
        "Bu uyari sessizce kaybolursa bir sonraki gelistirici yesil suiti 'dogrulanmis' sanip "
        "tibbi cihazi tezgah olcumu olmadan yayinlar."
    )
