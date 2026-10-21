# -*- coding: utf-8 -*-
"""I18NI-A1.4 — ACİL DURDUR yazıları HER yerde çeviri sisteminden BAĞIMSIZ (`kritikMetin` + `useKritikDil`), yalnız yüzen düğmede değil.

K-5 `test_K5_ACIL_DURDUR_dugmesi_kritik_deseni_kullanir_react_i18nexte_baglanmaz` YALNIZ `GlobalEmergencyStop.tsx`'i okur. Ana Ekran
(`DashboardScreen`), Kontrol (`ControlScreen` "TÜM BOBİNLERİ ACİL DURDUR") ve seans kartı (`SessionProgressCard`) ACİL DURDUR düğmeleri bugün
`kritikMetin` kullanıyor; ama `kritikMetin("guvenlik.acilDurdur.x")` → `t("guvenlik.acilDurdur.x")` dönüşü HİÇBİR kapıda kırmızı değil
(ölçüldü: 3 mutant, 865–869 jest + 38 pytest YEŞİL — o ekranların "katalog bozuk" testleri yalnız `i18n.exists`'i sahteler; `t()` onu
kullanmaz). Üründe katalog bozukken `t()` ham anahtar ("guvenlik.acilDurdur.dugme") basar.

Kapı (statik, AST yerine yorum soyulmuş kaynak): `apps/ui/src` (testler + `i18n/kritik.ts` hariç) içinde `guvenlik.acilDurdur.*` anahtarı
YALNIZ `kritikMetin(` ile çağrılır; `kritikMetin` kullanan her bileşen dosyası `useKritikDil(` ile dile abone olur (KURALLAR §8).
HEAD'de YEŞİL; mutant (herhangi bir ACİL DURDUR yazısı `t()` / `i18n.t()` / `<Trans>`'a döner) KIRMIZI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import ortak  # noqa: E402

UI = KOK / "apps" / "ui" / "src"
ANAHTAR = re.compile(r"guvenlik\.acilDurdur\.[A-Za-z0-9_]+")


def _yorumsuz(src: str) -> str:
    # Dizgi farkında soyucu (I18NI-A2.5): `re.sub(r"/\*.*?\*/", …, re.S)` dizgideki `/*`'ı (AiHubScreen `'image/*'`) yorum sayıp sonraki
    # KODU yutardı — o bölgedeki bir ACİL DURDUR `t()` dönüşü bu kapıdan da kaçardı (orkestratör yeniden üretiminde düzeltildi).
    return ortak.ts_yorumsuz(src)


def _dosyalar():
    for p in sorted(UI.rglob("*.ts*")):
        if "__tests__" in p.parts or p.name == "kritik.ts" or p.suffix not in (".ts", ".tsx"):
            continue
        yield p


def _kullanimlar():
    out = []
    for p in _dosyalar():
        kod = _yorumsuz(p.read_text(encoding="utf-8"))
        for m in ANAHTAR.finditer(kod):
            onu = kod[max(0, m.start() - 40) : m.start()]
            out.append((p, m.group(0), onu))
    return out


def test_KARSIT_tarayici_kor_degil():
    u = _kullanimlar()
    dosyalar = {p.name for p, _, _ in u}
    assert {
        "GlobalEmergencyStop.tsx",
        "SessionProgressCard.tsx",
        "DashboardScreen.tsx",
        "ControlScreen.tsx",
    } <= dosyalar, dosyalar
    assert len(u) >= 15, len(u)


def test_acil_durdur_anahtari_yalniz_kritikMetin_ile():
    kotu = []
    for p, anahtar, onu in _kullanimlar():
        if not re.search(r"kritikMetin\(\s*[\"']$", onu):
            kotu.append(f"{p.relative_to(KOK).as_posix()}: {anahtar} ← …{onu[-30:]!r}")
    assert not kotu, (
        "ACİL DURDUR yazısı çeviri sistemine (t / i18n.t / Trans) bağlanmış — katalog bozukken ham anahtar:\n"
        + "\n".join(kotu)
    )


@pytest.mark.parametrize(
    "rel",
    [
        "components/ui/GlobalEmergencyStop.tsx",
        "components/domain/SessionProgressCard.tsx",
        "screens/DashboardScreen.tsx",
        "screens/ControlScreen.tsx",
    ],
)
def test_acil_durdur_cizen_bilesen_useKritikDil_ile_abone(rel):
    kod = _yorumsuz((UI / rel).read_text(encoding="utf-8"))
    assert "kritikMetin(" in kod and "useKritikDil(" in kod, rel
