# -*- coding: utf-8 -*-
"""CLIENT ↔ FIRMWARE SÜRÜM UYUMU KAPISI — `utils/surum_uyumu` (plan Faz 3 çekirdeği).

Sahip kararı 2026-09-22: firmware güncellemesi OTOMATİK olacak. O zaman "hangi ikili
birlikte çalışır" kararı, hasta başındaki bir cihazda **kendiliğinden yakma** tetikleyecek.
Bu yüzden karar mantığının kendisi burada, donanımsız ve ağsız sınanır.

EN ÖNEMLİ İKİ DEĞİŞMEZ
  · `None` (bilinmiyor) **hiçbir zaman eylem üretmez** — bilinmeyene dayanarak firmware
    yakılmaz. Bu depoda aynı kalıp iki yerde ölçülerek kondu (`uyum_denetle`, `_is_newer`).
  · **Kural listesi boşsa karar `None`'dır.** "Kural yok" ≠ "her şey uyumlu". Aksi hâlde
    bozuk/eksik bir manifest sessizce korumayı kaldırırdı — sahte yeşilin tam tanımı.
"""

from __future__ import annotations

import pytest
from utils.surum_uyumu import (
    BEKLE,
    CLIENT_GERI_AL,
    EYLEM_YOK,
    FIRMWARE_GUNCELLE,
    plan_yap,
    surum_demeti,
    uyumlu_mu,
)

#: Tipik kural: 1.9.50+ client YALNIZ 2.3+ firmware ile çalışır.
KURAL = [{"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.3", "firmwareMax": ""}]
#: İki aralıklı: eski client eski firmware ile, yeni client yeni firmware ile.
IKI_ARALIK = [
    {"clientMin": "1.9.00", "clientMax": "1.9.49", "firmwareMin": "2.0", "firmwareMax": "2.2"},
    {"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.3", "firmwareMax": ""},
]


# ──────────────────────────────────────────────────────────────────────────
# 1) ÜÇ DURUMLU KARAR
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "client,firmware,beklenen,neden",
    [
        ("1.9.51", "2.3", True, "ikisi de aralıkta"),
        ("1.9.50", "2.3", True, "alt sınır DAHİL"),
        ("1.9.49", "2.3", False, "client alt sınırın altında"),
        ("1.9.51", "2.2", False, "firmware alt sınırın altında"),
        ("abc", "2.3", None, "client ayrıştırılamıyor"),
        ("1.9.51", "yok", None, "firmware ayrıştırılamıyor"),
        ("v1.9.51-rc", "2.3", True, "etiketli sürümün sayısal ön-eki alınır"),
    ],
)
def test_KRITIK_uyum_karari(client, firmware, beklenen, neden):
    sonuc, gerekce = uyumlu_mu(client, firmware, KURAL)
    assert sonuc is beklenen, f"{neden}: beklenen {beklenen}, bulunan {sonuc} — {gerekce}"


def test_KRITIK_kural_YOKSA_karar_NONE():
    """🔴 "Kural yok" ≠ "uyumlu". Bozuk manifest sessizce korumayı KALDIRMASIN."""
    sonuc, gerekce = uyumlu_mu("1.9.51", "2.3", [])
    assert sonuc is None, f"boş kuralda {sonuc} döndü — sahte yeşil üretir"
    assert "kural" in gerekce.lower()


def test_iki_aralik_AYRI_AYRI_eslesir():
    """Eski çift de yeni çift de uyumlu; ÇAPRAZ olanlar değil."""
    assert uyumlu_mu("1.9.20", "2.1", IKI_ARALIK)[0] is True
    assert uyumlu_mu("1.9.51", "2.3", IKI_ARALIK)[0] is True
    assert uyumlu_mu("1.9.20", "2.3", IKI_ARALIK)[0] is False, "eski client + yeni fw ÇAPRAZ"
    assert uyumlu_mu("1.9.51", "2.1", IKI_ARALIK)[0] is False, "yeni client + eski fw ÇAPRAZ"


def test_ust_sinir_UYGULANIYOR():
    """Üst sınır yazılmışsa gerçekten sınırlar — yoksa aralık tek yönlü olurdu."""
    k = [{"clientMin": "1.0", "clientMax": "1.5", "firmwareMin": "", "firmwareMax": ""}]
    assert uyumlu_mu("1.4", "9.9", k)[0] is True
    assert uyumlu_mu("1.6", "9.9", k)[0] is False, "üst sınır aşıldı ama uyumlu dendi"


# ──────────────────────────────────────────────────────────────────────────
# 2) PLAN — uyumsuzsa ne yapılır
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_uyumluysa_HICBIR_SEY_yapilmaz():
    p = plan_yap("1.9.51", "2.3", KURAL, yeni_firmware="2.4", onceki_client="1.9.50")
    assert p.eylem == EYLEM_YOK, f"uyumluyken {p.eylem} önerdi — gereksiz yakma RİSKTİR"


def test_KRITIK_karar_YOKSA_hicbir_sey_yapilmaz():
    """🔴 Bilinmeyene dayanarak firmware YAKILMAZ."""
    p = plan_yap("bozuk", "2.2", KURAL, yeni_firmware="2.3", onceki_client="1.9.49")
    assert p.eylem == EYLEM_YOK, f"karar None iken {p.eylem} önerdi"


def test_KRITIK_ILERI_gitmek_geri_almaya_TERCIH_EDILIR():
    """Kullanıcı zaten yeni client'ı istemiştir; ikisi de mümkünse ileri git."""
    p = plan_yap("1.9.51", "2.2", IKI_ARALIK, yeni_firmware="2.3", onceki_client="1.9.20")
    assert p.eylem == FIRMWARE_GUNCELLE and p.hedef_surum == "2.3", p.gerekce


def test_KRITIK_ileri_gidilemezse_CLIENT_GERI_ALINIR():
    """Sahip: *"client güncellenip stm güncellenmezse client geri dönebilmeli"*."""
    p = plan_yap("1.9.51", "2.1", IKI_ARALIK, yeni_firmware="", onceki_client="1.9.20")
    assert p.eylem == CLIENT_GERI_AL and p.hedef_surum == "1.9.20", p.gerekce


def test_KRITIK_ne_ileri_ne_geri_varsa_BEKLE():
    """⚠️ "Uyumsuz hâliyle devam et" diye bir eylem ÜRETİLMEZ."""
    p = plan_yap("1.9.51", "2.1", IKI_ARALIK)
    assert p.eylem == BEKLE, p.gerekce


@pytest.mark.parametrize("bayrak", ["stm_bagli", "internet"])
def test_KRITIK_STM_yok_ya_da_internet_yoksa_BEKLE(bayrak):
    """⚠️ Sessizce geçilmez: durum GÖRÜNÜR kalır (fail-quiet ≠ fail-silent)."""
    p = plan_yap("1.9.51", "2.2", KURAL, yeni_firmware="2.3", **{bayrak: False})
    assert p.eylem == BEKLE, f"{bayrak}=False iken {p.eylem} önerdi — yakma denenmemeliydi"
    assert p.gerekce, "gerekçe boş — destek mühendisi neden beklendiğini okuyamaz"


def test_plan_ASLA_bilinmeyen_eylem_uretmez():
    """Çağıran taraf bilinmeyen bir dizeye dallanmasın."""
    gecerli = {EYLEM_YOK, FIRMWARE_GUNCELLE, CLIENT_GERI_AL, BEKLE}
    denemeler = [
        ("1.9.51", "2.3", {}),
        ("1.9.51", "2.1", {}),
        ("x", "y", {}),
        ("1.9.51", "2.1", {"yeni_firmware": "2.3"}),
        ("1.9.51", "2.1", {"onceki_client": "1.9.20"}),
        ("1.9.51", "2.1", {"stm_bagli": False}),
        ("1.9.51", "2.1", {"internet": False}),
    ]
    for c, f, ek in denemeler:
        assert plan_yap(c, f, IKI_ARALIK, **ek).eylem in gecerli


# ──────────────────────────────────────────────────────────────────────────
# 3) TEK KAYNAK — sürüm semantiği ayrışmasın
# ──────────────────────────────────────────────────────────────────────────


def test_semantik_update_manager_ILE_AYNI():
    """`surum_demeti` ile `update_manager._vtuple` AYNI şeyi görmeli.

    İkisi ayrışırsa client güncelleme yolu bir sürümü "yeni" sayarken uyum kararı onu
    başka aralığa koyar. Bu depoda `_DB_ERROR` demetleri tam böyle sessizce ayrışmıştı.
    """
    from servers.update_manager import _vtuple

    for s in ("1.9.51", "v2.3", "1.9.51-rc2", "2", "abc", "", "1.a.3"):
        assert surum_demeti(s) == _vtuple(s), f"{s!r}: {surum_demeti(s)} != {_vtuple(s)}"


def test_ACIL_DURDURMA_bu_modulden_ETKILENMEZ():
    """⚠️ Bu modül yalnız PLAN üretir; seansı/E-stop'u engelleyen bir çıktısı YOKTUR.

    Kayıtlı ilke: *"bir tıbbi cihazın uzaktan ACİL DURDURMASINI sürüm eşleşmesine bağlamak
    kabul edilemez"*. Kapı, modülün yüzeyine pinli: yasak sözcükler dışa açılmamalı.
    """
    import utils.surum_uyumu as m

    disa_acik = {a for a in dir(m) if not a.startswith("_")}
    yasak = {"estop", "emergency", "seans_engelle", "session_block", "acil_durdur"}
    assert not (disa_acik & yasak), f"bu modül durdurma yüzeyi açmış: {disa_acik & yasak}"
