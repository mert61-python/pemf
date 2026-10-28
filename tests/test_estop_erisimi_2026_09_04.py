# Author: mertaygn, cglrgrkn
"""ACİL DURDUR ERİŞİMİ — kaynak sözleşmesi [ekranB-2, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM (denetim): ControlScreen'deki sayfa-içi "TÜM BOBİNLERİ ACİL DURDUR" düğmesi tüm
sekme içeriğinden SONRA duruyordu; Manuel sekmesinde 8 bobin kartının altında ~3000 px derinde
kalıyordu. Bunu telafi ettiği varsayılan kayan `GlobalEmergencyStop` ise yalnız
`running || activeTreatment` iken çizilir ve STM çevrimdışıyken `normalizeStmCoils` bobinleri
`running:false` yaptığı için GİZLENİYORDU → bağlantı koptuğu anda hiçbir ekranda tek dokunuşluk
durdurma yolu kalmıyordu.

SÖZLEŞME:
  1. ControlScreen'de acil durdurma düğmesi SEKME ÇUBUĞUNDAN ÖNCE gelir (kaydırmasız erişim).
  2. GlobalEmergencyStop, STM durumu belirsizken (bir kez çalışır görülmüşse) kendini GİZLEMEZ.
  3. (KI G4) Belirsizlik yorumundaki bobin aralığı kodun bugünkü tek kaynağıyla aynı (`STM_BOBIN_SAYISI` / `stmBobiniMi`).

Davranışsal kanıt: apps/ui/src/components/ui/__tests__/GlobalEmergencyStop.belirsizlik.test.tsx
"""

import pathlib
import re

import capraz
import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_CONTROL = _KOK / "apps" / "ui" / "src" / "screens" / "ControlScreen.tsx"
_GES = _KOK / "apps" / "ui" / "src" / "components" / "ui" / "GlobalEmergencyStop.tsx"


@pytest.fixture(autouse=True)
def _arayuz_kaynagi():
    """D4.04: `apps/ui/` (ACİL DURDUR erişimi) İZLENEN ağaçtır — yoksa atla, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞ.

    Eskiden düz `skipif` idi: klasör taşınınca (09-18 `pf`→`apps/ui` gibi) kapı zorunlu kipte de sessizce atlanıyordu.
    """
    capraz.atla_yoksa("apps/ui/src/screens/ControlScreen.tsx", izlenen=True)
    capraz.atla_yoksa("apps/ui/src/components/ui/GlobalEmergencyStop.tsx", izlenen=True)


def _oku(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def test_KRITIK_control_ekraninda_estop_sekme_cubugundan_ONCE():
    """Düğme sekme içeriğinin ALTINDA kalırsa Manuel sekmesinde ~3000 px kaydırma gerekir."""
    src = _oku(_CONTROL)
    estop = src.find("styles.emergencyBtn")
    tabbar = src.find("styles.tabBar")
    assert estop != -1, "ControlScreen'de acil durdurma düğmesi (styles.emergencyBtn) YOK"
    assert tabbar != -1, "ControlScreen'de sekme çubuğu (styles.tabBar) bulunamadı"
    assert estop < tabbar, (
        "ACİL DURDUR düğmesi sekme çubuğundan SONRA çiziliyor → sekme içeriğinin altında kalır "
        "(Manuel sekmesinde 8 bobin kartı ≈ 3000 px). Düğmeyi tab bar'ın ÜSTÜNE taşıyın."
    )


def test_KRITIK_kayan_estop_stm_belirsizken_gizlenmez():
    """`!running && !active` erken-dönüşü belirsizlik (ve D1.E04 teyitsizlik) durumunu da kapsamamalı.

    D1.E03 (1-E): belirsizlik kuralı TEK kaynağa taşındı (`hooks/useStmBelirsiz.ts`; kabuk söküm kapısı da kullanır) —
    GES onu çağırır, kalıcılık (kilit) kancadadır. Davranışsal kapı: `GlobalEmergencyStop.belirsizlik.test.tsx` (jest)."""
    src = _oku(_GES)
    kanca = _oku(_KOK / "apps" / "ui" / "src" / "hooks" / "useStmBelirsiz.ts")
    assert "useStmBelirsiz(snapshot)" in src, "GlobalEmergencyStop STM belirsizliğini hiç okumuyor"
    assert "stmBelirsiz" in kanca and "setKilit(true)" in kanca, (
        "Kalıcılık (bir kez çalışır görüldüyse düğme kalır) kaldırılmış: kancada kilit yok"
    )
    assert "if (!running && !active && !belirsiz && !teyitsiz) return null;" in src, (
        "Erken dönüş belirsizlik/teyitsizlik durumunu KAPSAMIYOR → STM koptuğunda düğme yine gizlenir"
    )


def test_belirsizlik_etiketi_nedenini_soyler():
    """Operatör düğmenin neden sayaçsız çıktığını görmeli.

    I18N-0: metin kataloğa taşındı — ölçüt GEVŞEMEDİ, yer değiştirdi (`tests/i18n_yardimci.py`): düğme belirsizlik anahtarını KULLANIYOR,
    TR değeri nedeni BİREBİR söylüyor, EN değeri boş değil.

    Yardımcı İŞLEV İÇİNDE içe aktarılır: D404 meta kapısı bu dosyayı yalnız `capraz.py` + `c_soyucu.py` ile asgari bir ağaca kopyalar
    (izlenen ağaç YOK → autouse fikstürü düşmeli); modül düzeyi içe aktarma orada TOPLAMA hatası verip kapıyı bozuyordu (ölçüldü,
    I18N-0 kapanış tam süiti)."""
    import i18n_yardimci as iy

    iy.metin_kapisi(
        "apps/ui/src/components/ui/GlobalEmergencyStop.tsx",
        "guvenlik.acilDurdur.dugmeBaglantiYok",
        "🚨 ACİL DURDUR (bağlantı yok)",
    )


def test_KI_G4_belirsizlik_yorumu_bobin_araligi_kodla_ayni():
    """KI G4 (22 A3a G4): GES belirsizlik yorumu "`normalizeStmCoils` 1-5 numaralı bobinleri `running:false` yapar … WiFi
    bobinleri (6-8)" diyordu — D5.42'den beri STM aralığı TEK kaynaktan (`bobinGorunurlugu.STM_BOBIN_SAYISI`, `stmBobiniMi`) 1..7, ESP
    yuvası kapalı (Ö.4-Y7). Yorumdaki aralık kodun bugünkü değeriyle AYNI olmalı: eski aralık YOK, tek kaynak adı ve DEĞERİ yorumda,
    `normalizeStmCoils`'un yüklemi gerçekten `stmBobiniMi` (davranış değişmez — yalnız yorum)."""
    src = _oku(_GES)
    bas = src.find("HASTA GÜVENLİĞİ — [ekranB-2")
    son = src.find("const belirsiz = useStmBelirsiz(snapshot);")
    assert 0 <= bas < son, "GES belirsizlik yorumu / çağrısı bulunamadı (yapı değişti)"
    yorum = src[bas:son]
    for eski in (r"\b1\s*[-–]\s*5\b", r"\b6\s*[-–]\s*8\b", r"WiFi\s+bobin"):
        assert not re.search(eski, yorum), f"bayat bobin aralığı yorumda duruyor ({eski}): {yorum[:300]!r}"
    gorunurluk = _oku(_KOK / "apps" / "ui" / "src" / "services" / "bobinGorunurlugu.ts")
    m = re.search(r"export const STM_BOBIN_SAYISI = (\d+);", gorunurluk)
    assert m, "bobinGorunurlugu.STM_BOBIN_SAYISI bulunamadı"
    y = re.search(r"STM_BOBIN_SAYISI`?\s*=\s*(\d+)", yorum)
    assert y, "yorum STM aralığını tek kaynağın adı ve değeriyle söylemiyor (`STM_BOBIN_SAYISI` = N)"
    assert y.group(1) == m.group(1), f"yorum STM_BOBIN_SAYISI = {y.group(1)} diyor, kod {m.group(1)}"
    assert "stmBobiniMi" in yorum, "yorum STM yüklemini (`stmBobiniMi`) anmıyor"
    ctx = _oku(_KOK / "apps" / "ui" / "src" / "context" / "LiveDataContext.tsx")
    g = re.search(r"function isStmCoil\(coilId: number\): boolean \{(.*?)\n\}", ctx, re.S)
    assert g and g.group(1).strip() == "return stmBobiniMi(coilId);", (
        "normalizeStmCoils'un yüklemi artık `stmBobiniMi` değil — yorum kodla AYNI değil"
    )
