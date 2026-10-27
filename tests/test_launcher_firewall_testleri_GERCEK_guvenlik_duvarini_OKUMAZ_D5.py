# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 (yardımcı I'nın kapsam dışı bulgusu) — launcher `firewall.rs` testleri GERÇEK Windows güvenlik duvarını OKUMAZ.

ARIZA (ölçüldü, 2026-10-27): `launcher/core/src/firewall.rs` `durum_asla_PANIKLEMEZ` GERÇEK `durum()`u çağırıyordu → her `cargo test`te
(CI `windows-latest` dahil, bu oturumun çekirdek koşuları dahil) gerçek `powershell` ile gerçek `Get-NetFirewallRule` /
`Get-NetFirewallApplicationFilter` koşuyordu (salt-okur, ama Dalga 5 sınıfı: test aparatı gerçek sisteme dokunuyordu; makinenin kural
tablosu test sonucunu belirliyordu). Düzeltme: fail-open sözleşmesi saf yorumlayıcıda (`durum_yorumla`) ve PowerShell'i BAŞLATAMAYAN
program adıyla (`durum_kos("<olmayan>", …)`) ölçülür; betiğin kendisi yalnız `mod golge`de GÖLGE NetSecurity ile koşar.

KAPI (Rust kaynağı `scripts.i18n.cikar._rust_soy(…, dizge_bosalt=True)` ile soyulur — yorumlar VE dizge içerikleri boşluklanır; böylece
iddia metnindeki `durum_icin(…)` dizgesi çağrı sayılmaz, yoruma alınmış çağrı da sayılmaz):
  * `mod tests` bölgesinde `durum(` / `durum_icin(` ÇAĞRISI yalnız `#[cfg(not(windows))]` testlerinde olabilir (orada PowerShell'e gitmez);
  * `durum_kos(` çağrısının program argümanı `powershell` / `pwsh` OLAMAZ (ham metinde, yorum dışı);
  * karşıt: test modülü fail-open kolunu GERÇEKTEN ölçer (`durum_yorumla(` ve `durum_kos(` çağrısı VAR).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import cikar  # noqa: E402

FIREWALL_RS = KOK / "launcher" / "core" / "src" / "firewall.rs"


def _test_bolgesi(metin: str) -> tuple[int, str]:
    m = re.search(r"#\[cfg\(test\)\]\s*mod tests\s*\{", metin)
    assert m, "firewall.rs: `#[cfg(test)] mod tests {` bulunamadı"
    return m.start(), metin[m.start() :]


def _soyulmus_test_bolgesi(ham: str) -> str:
    soy, _ = cikar._rust_soy(ham, dizge_bosalt=True)
    bas, _ = _test_bolgesi(ham)
    return soy[bas:]


def _windows_disi_testler(soy: str) -> set[str]:
    return set(re.findall(r"#\[cfg\(not\(windows\)\)\]\s*#\[test\]\s*fn\s+(\w+)", soy))


def _cagri_ihlalleri(ham: str) -> list[str]:
    soy = _soyulmus_test_bolgesi(ham)
    izinli = _windows_disi_testler(soy)
    ihlal = []
    for m in re.finditer(r"\b(durum|durum_icin)\s*\(", soy):
        once = soy[: m.start()]
        fn = re.findall(r"\bfn\s+(\w+)", once)
        sahip = fn[-1] if fn else "?"
        if sahip in izinli:
            continue
        satir = soy.count("\n", 0, m.start()) + 1
        ihlal.append(
            f"test bölgesi satır {satir}: `{m.group(1)}(` (fn {sahip}) — gerçek PowerShell + gerçek Get-NetFirewallRule"
        )
    return ihlal


def _program_ihlalleri(ham: str) -> list[str]:
    soy = _soyulmus_test_bolgesi(ham)
    _, ham_bolge = _test_bolgesi(ham)
    ihlal = []
    for m in re.finditer(r"\bdurum_kos\s*\(", soy):
        arguman = ham_bolge[m.end() : m.end() + 60]
        if re.match(r'\s*"(?i:powershell|pwsh)(?:\.exe)?"', arguman):
            ihlal.append(f"`durum_kos({arguman.strip()[:30]}…` — gerçek PowerShell")
    return ihlal


def test_KRITIK_firewall_testleri_GERCEK_durum_CAGIRMAZ():
    ham = FIREWALL_RS.read_text(encoding="utf-8")
    ihlal = _cagri_ihlalleri(ham) + _program_ihlalleri(ham)
    assert not ihlal, (
        "launcher firewall.rs testi GERÇEK güvenlik duvarını okuyor (her `cargo test`te gerçek PowerShell + Get-NetFirewallRule — "
        "test aparatı gerçek sisteme). Fail-open kolunu `durum_yorumla` / `durum_kos(\"<olmayan program>\", …)` ile ölç:\n  "
        + "\n  ".join(ihlal)
    )


def test_KARSIT_fail_open_kolu_GERCEKTEN_olculur():
    soy = _soyulmus_test_bolgesi(FIREWALL_RS.read_text(encoding="utf-8"))
    assert re.search(r"\bdurum_yorumla\s*\(", soy), "fail-open yorumlayıcısı (durum_yorumla) hiçbir testte çağrılmıyor"
    assert re.search(r"\bdurum_kos\s*\(", soy), (
        "PowerShell başlatılamayınca fail-open kolu (durum_kos) hiçbir testte ölçülmüyor"
    )


def test_KARSIT_arac_yorumu_ve_dizgeyi_CAGRI_saymaz_windows_disi_teste_izin_verir():
    sentetik = (
        "pub fn durum() -> u8 { 0 }\n"
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    #[test]\n"
        "    fn a() {\n"
        "        // let d = durum();\n"
        '        assert!(true, "beklenen `durum_icin(Some(&exe),api_portu(&root))`");\n'
        "        let _ = durum_kos(\"pemf-olmayan\", None, 8000);\n"
        "    }\n"
        "    #[cfg(not(windows))]\n"
        "    #[test]\n"
        "    fn b() { let _ = durum(); }\n"
        "}\n"
    )
    assert _cagri_ihlalleri(sentetik) == []
    assert _program_ihlalleri(sentetik) == []
    kotu = sentetik.replace("// let d = durum();", "let d = durum();").replace('"pemf-olmayan"', '"powershell"')
    assert len(_cagri_ihlalleri(kotu)) == 1, _cagri_ihlalleri(kotu)
    assert len(_program_ihlalleri(kotu)) == 1, _program_ihlalleri(kotu)
