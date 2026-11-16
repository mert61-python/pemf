# -*- coding: utf-8 -*-
"""KP-6 · madde 14 KAPISI — arayüz jest testlerinde KURULU pakete `jest.mock(…, { virtual: true })` YOK.

ÖLÇÜLEN (KP-5 15-11, KP-6 15-11 kök neden): `LiveDataContext.BE1.yenidenBaglanma` "(b) kayıtlı adres BAYAT" ve `KP3-discovery-merdiven`in
mDNS testleri YALNIZ tam jest listesinde (339 yol, `--maxWorkers=2`) aralıklı KIRMIZI. Kök neden jest-resolve 29.7.0
`Resolver.getModuleID`: kimlik önbelleğinin anahtarı `from + ad`, ama üretilen kimlik ÇAĞIRAN dosyanın `_virtualMocks` kaydına göre
değişir (sanal mock varsa çıplak ad, yoksa gerçek yol) ve çözümleyici bir işçideki TÜM test dosyalarınca PAYLAŞILIR. `react-native-zeroconf`
gerçek bağımlılıkken iki dosya onu `virtual: true` ile, `KP2_SettingsScreen_native` ise sanal olmadan sahteliyordu → Settings aynı işçide
ÖNCE koşunca `discovery.ts`in `require`ı gerçek-yol kimliğini önbellekten alıp sanal sahteyi KAÇIRIYOR, gerçek modül (yerel modül yok) mDNS'i
null yapıyordu. Belirlenimci kanıt (`--runInBand`, sıra dizici): Settings → BE1 → KP3 = 5 KIRMIZI; BE1 → KP3 → Settings = 47 / 47 yeşil.

KAPI: apps/ui altındaki her `jest.mock("<ad>", …, { virtual: true })` için <ad> `apps/ui/package.json` bağımlılığı (dependencies /
devDependencies) OLMAMALI — kurulu paket sanal OLMADAN sahtelenir (kimlik her dosyada aynı gerçek yol). Kör olmasın diye: tarama kendi
ayrıştırıcısını sentetik kaynakla sınar ve bilinen sanal OLMAYAN sahteleri (üç `react-native-zeroconf` dosyası) BULDUĞUNU iddia eder.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
UI = KOK / "apps" / "ui"
_MOCK = re.compile(r"\bjest\.mock\(\s*([\"'])([^\"']+)\1")
_SANAL = re.compile(r"\bvirtual\s*:\s*true\b")


def _cagri_metni(kaynak: str, bas: int) -> str:
    """`jest.mock(` açılışından eşleşen kapanış parantezine kadar KOD: yorumlar atılır, dizge / şablon içerikleri boşaltılır (içlerindeki
    parantez ve "virtual: true" sayılmaz)."""
    i = kaynak.index("(", bas)
    derinlik, n, kod = 0, len(kaynak), []
    while i < n:
        c = kaynak[i]
        if c in "\"'`":
            j = i + 1
            while j < n and kaynak[j] != c:
                j += 2 if kaynak[j] == "\\" else 1
            kod.append(c + c)
            i = j + 1
            continue
        if kaynak.startswith("//", i):
            i = kaynak.find("\n", i)
            i = n if i < 0 else i
            continue
        if kaynak.startswith("/*", i):
            k = kaynak.find("*/", i + 2)
            i = n if k < 0 else k + 2
            continue
        kod.append(c)
        if c == "(":
            derinlik += 1
        elif c == ")":
            derinlik -= 1
            if derinlik == 0:
                break
        i += 1
    return "".join(kod)


def sahteler(kaynak: str) -> list[tuple[str, bool]]:
    """Kaynaktaki her `jest.mock("<ad>", …)` → (ad, sanal mı)."""
    return [(m.group(2), bool(_SANAL.search(_cagri_metni(kaynak, m.start())))) for m in _MOCK.finditer(kaynak)]


def _bagimliliklar() -> set[str]:
    pj = json.loads((UI / "package.json").read_text(encoding="utf-8"))
    return set(pj.get("dependencies", {})) | set(pj.get("devDependencies", {}))


def _test_kaynaklari() -> list[Path]:
    return sorted(
        p
        for uz in ("*.ts", "*.tsx", "*.js")
        for p in UI.rglob(uz)
        if "node_modules" not in p.parts and "jest.mock(" in p.read_text(encoding="utf-8", errors="replace")
    )


def test_ayristirici_SANAL_ve_SANAL_OLMAYAN_sahteyi_ayirir():
    kaynak = (
        'jest.mock("a-paket", () => ({ f: ")" /* ) */ }), { virtual: true });\n'
        "jest.mock('b-paket', () => {\n  // virtual: true burada YORUM\n  return { g: `(${1})` };\n});\n"
        'jest.mock("./yerel", () => ({}), {\n  virtual: true,\n});\n'
        'jest.mock("c-paket", () => ({ s: "virtual: true" }));\n'
    )
    assert sahteler(kaynak) == [("a-paket", True), ("b-paket", False), ("./yerel", True), ("c-paket", False)]


def test_KRITIK_kurulu_pakete_SANAL_jest_mock_YOK():
    bag = _bagimliliklar()
    assert "react-native-zeroconf" in bag, "aparat: package.json okunamadı / bağımlılık listesi boş"
    dosyalar = _test_kaynaklari()
    assert len(dosyalar) >= 100, f"tarama kör: yalnız {len(dosyalar)} jest.mock'lu dosya bulundu"
    ihlal, zeroconf_sanalsiz = [], []
    for p in dosyalar:
        for ad, sanal in sahteler(p.read_text(encoding="utf-8", errors="replace")):
            if sanal and ad in bag:
                ihlal.append(f"{p.relative_to(KOK).as_posix()}: {ad}")
            if ad == "react-native-zeroconf" and not sanal:
                zeroconf_sanalsiz.append(p.name)
    assert not ihlal, (
        "KURULU pakete `virtual: true` jest.mock — jest-resolve'un işçi içi paylaşılan modül kimliği önbelleği sıraya bağlı olarak sahteyi "
        "kaçırır (madde 14). `{ virtual: true }`yi kaldırın:\n" + "\n".join(ihlal)
    )
    assert len(zeroconf_sanalsiz) >= 3, (
        f"bilinen sanalsız zeroconf sahteleri bulunamadı (ayrıştırıcı kör?): {zeroconf_sanalsiz}"
    )
