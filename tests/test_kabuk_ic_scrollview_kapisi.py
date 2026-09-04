# Author: mertaygn, cglrgrkn
"""KABUK İÇİ EKRANLARDA İÇ DİKEY KAYDIRICI YASAĞI  [S4 adım 3, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM: kabuk (AppShell) zaten tek bir dikey `ScrollView` çiziyor ve o kaydırıcı
`keyboardShouldPersistTaps="handled"` taşıyor. Kabuğun İÇİNDEKİ 8 ekran bir dikey ScrollView daha
açıyordu. Bu iç kaydırıcının yükseklik sınırı olmadığı için kendi kaydırmasını hiç üretmiyordu
(görsel sonuç aynıydı), ama `keyboardShouldPersistTaps` varsayılanı "never" olduğundan klavye
açıkken ilk dokunuş kaydırıcı tarafından yutuluyor, "Kaydet" / "Cihaza Bağlan" düğmeleri İKİ
dokunuş istiyordu (ekranA-7, aihub-6, ekranC-13).

SÖZLEŞME:
  1. Listedeki ekranlarda YATAY OLMAYAN `<ScrollView` bulunmaz.
  2. Kabuğun kaydırıcısı `keyboardShouldPersistTaps` taşımaya devam eder (yasağın dayanağı bu).
  3. Klavye açan modallar kendi kaydırıcılarında `keyboardShouldPersistTaps` taşır — onlar kabuğun
     DIŞINDA (RN Modal kendi penceresi) olduğu için yasağa girmez, ama aynı tuzağa düşmemeli.

⚠️ KAPSAM: Welcome ve Auth ekranları kabuğun DIŞINDADIR (giriş öncesi) → kendi kaydırıcıları kalır.
Yatay çip şeritleri (`horizontal`) ve `nestedScrollEnabled` taşıyan iç listeler de kapsam dışıdır.
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"

# Kabuk İÇİNDE çizilen ekranlar (AppShell children). Yeni ekran eklenirse BURAYA da eklenir.
_KABUK_EKRANLARI = (
    "AiHistoryScreen.tsx",
    "AiHubScreen.tsx",
    "ControlScreen.tsx",
    "DashboardScreen.tsx",
    "KpiDashboardScreen.tsx",
    "PatientScreen.tsx",
    "SensorMonitorScreen.tsx",
    "SettingsScreen.tsx",
    "TreatmentHistoryScreen.tsx",
)

# Klavye açan, kendi penceresinde kaydırıcı taşıyan modallar.
_KLAVYELI_MODALLAR = (
    "ObservationNotesModal.tsx",
    "DevicePairingGuide.tsx",
)

pytestmark = pytest.mark.skipif(
    not (_PF / "components" / "ui" / "AppShell.tsx").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)

# `<ScrollView` açılışı ve kapanış `>` arasındaki tüm prop metni (çok satırlı JSX dahil).
_ACILIS = re.compile(r"<ScrollView\b(.*?)>", re.DOTALL)


def _propslar(src: str):
    """Dosyadaki her `<ScrollView` açılışının prop metnini döndür."""
    return [m.group(1) for m in _ACILIS.finditer(src)]


def test_KRITIK_kabuk_ici_ekranlarda_dikey_scrollview_yok():
    """İç kaydırıcı klavye açıkken ilk dokunuşu yutar → düğmeler iki dokunuş ister."""
    ihlal = []
    for ad in _KABUK_EKRANLARI:
        p = _PF / "screens" / ad
        assert p.exists(), f"ekran bulunamadı: {ad} (liste güncellenmeli)"
        for props in _propslar(p.read_text(encoding="utf-8")):
            if "horizontal" in props or "nestedScrollEnabled" in props:
                continue  # yatay çip şeridi / bilinçli iç liste
            ihlal.append(f"{ad}: <ScrollView{props.strip()[:60]}…")
    assert not ihlal, "Kabuk içi ekranda dikey ScrollView var; kabuk zaten tek kaydırıcı sağlıyor:\n" + "\n".join(ihlal)


def test_kabuk_kaydiricisi_klavye_dokunusunu_gecirir():
    """Yasağın dayanağı: tek kaydırıcı klavye açıkken dokunuşu İLK seferde geçirmeli."""
    src = (_PF / "components" / "ui" / "AppShell.tsx").read_text(encoding="utf-8")
    assert 'keyboardShouldPersistTaps="handled"' in src, (
        "AppShell içerik ScrollView'ı keyboardShouldPersistTaps taşımıyor — iç kaydırıcı yasağı dayanaksız kalır."
    )


def test_klavyeli_modallar_dokunusu_gecirir():
    """Modallar kabuğun dışında kendi penceresinde kaydırır; aynı tuzağa düşmemeli."""
    eksik = []
    for ad in _KLAVYELI_MODALLAR:
        p = _PF / "components" / "domain" / ad
        assert p.exists(), f"modal bulunamadı: {ad} (liste güncellenmeli)"
        for props in _propslar(p.read_text(encoding="utf-8")):
            if "horizontal" in props:
                continue
            if "keyboardShouldPersistTaps" not in props:
                eksik.append(f"{ad}: <ScrollView{props.strip()[:60]}…")
    assert not eksik, (
        "Klavye açan modalın kaydırıcısında keyboardShouldPersistTaps yok (ilk dokunuş yutulur):\n" + "\n".join(eksik)
    )
