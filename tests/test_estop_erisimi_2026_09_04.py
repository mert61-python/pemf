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

Davranışsal kanıt: pf/src/components/ui/__tests__/GlobalEmergencyStop.belirsizlik.test.tsx
"""

import pathlib

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_CONTROL = _KOK / "pf" / "src" / "screens" / "ControlScreen.tsx"
_GES = _KOK / "pf" / "src" / "components" / "ui" / "GlobalEmergencyStop.tsx"

pytestmark = pytest.mark.skipif(
    not _CONTROL.exists() or not _GES.exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)


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
    """`!running && !active` erken-dönüşü belirsizlik durumunu da kapsamamalı."""
    src = _oku(_GES)
    assert "stmBelirsiz" in src, "GlobalEmergencyStop STM belirsizliğini hiç okumuyor"
    assert "belirsizKilit" in src, "Kalıcılık (bir kez çalışır görüldüyse düğme kalır) kaldırılmış: `belirsizKilit` yok"
    assert "if (!running && !active && !belirsiz) return null;" in src, (
        "Erken dönüş belirsizlik durumunu KAPSAMIYOR → STM koptuğunda düğme yine gizlenir"
    )


def test_belirsizlik_etiketi_nedenini_soyler():
    """Operatör düğmenin neden sayaçsız çıktığını görmeli."""
    assert "bağlantı yok" in _oku(_GES), "Belirsizlik durumunda etiket nedenini söylemiyor ('bağlantı yok' ibaresi yok)"
