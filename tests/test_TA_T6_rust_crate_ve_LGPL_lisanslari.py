# -*- coding: utf-8 -*-
"""TA T6 (S-I18N.7 + S-D67.9) · NOTICE (THIRD_PARTY_LICENSES.md): başlatıcının Rust crate'leri + LGPL bileşenleri.

Önce: `launcher/Cargo.lock`taki 437 crate'in HİÇBİRİ atıf listesinde yoktu; `pi-heif` satırı "BSD-3-Clause (sınıflandırıcı: LGPLv3)"
diyerek hangisinin neye uygulandığını söylemiyordu; LGPL bileşenleri (pi-heif ikilileri, soxr, zeroconf) için lisans METNİ ve tam
sürüm KAYNAK bağlantısı yoktu. Kapı: Cargo.lock'ta olup NOTICE'ta (ya da depodaki envanterde) olmayan crate KIRMIZI. Tüm girdiler
depoda (CI'da koşar); kayıt defteri yeniden üretimi yalnız sahte kökle sınanır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import lisans_envanteri_uret as u

KOK = Path(__file__).resolve().parents[1]
NOTICE = KOK / "THIRD_PARTY_LICENSES.md"


def _notice_rust_satirlari(metin: str) -> set[tuple[str, str]]:
    bolum = metin.split(u._RUST_BASLIGI, 1)[1].split("\n### ", 1)[0]
    return {(a, s) for a, s in re.findall(r"^\| `([^`]+)` \| ([^ |]+) \| [^|]+ \|$", bolum, re.M)}


def rust_eksikleri(kilit: Path | None = None, notice: str | None = None) -> list[tuple[str, str]]:
    satirlar = _notice_rust_satirlari(notice if notice is not None else NOTICE.read_text(encoding="utf-8"))
    return [p for p in u.cargo_paketleri(kilit) if p not in satirlar]


def test_KRITIK_Cargo_lock_taki_HER_crate_NOTICE_ta_surumuyle_VAR():
    paketler = u.cargo_paketleri()
    assert len(paketler) >= 400, f"VAKUM: Cargo.lock'tan yalnız {len(paketler)} crate okundu"
    assert not rust_eksikleri(), (
        f"NOTICE'ta olmayan crate(ler) — `python scripts/lisans_envanteri_uret.py --rust-yenile` + üret: {rust_eksikleri()[:20]}"
    )


def test_KRITIK_KARSIT_kilide_YENI_crate_girerse_kapi_KIRMIZI(tmp_path):
    kilit = tmp_path / "Cargo.lock"
    kilit.write_text(
        u._CARGO_KILIDI.read_text(encoding="utf-8")
        + '\n[[package]]\nname = "yeni-crate"\nversion = "9.9.9"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n',
        encoding="utf-8",
    )
    assert rust_eksikleri(kilit) == [("yeni-crate", "9.9.9")]
    # sürüm yükseltmesi de yakalanır (ad aynı, sürüm farklı)
    eski = u.cargo_paketleri()[0]
    kilit.write_text(
        u._CARGO_KILIDI.read_text(encoding="utf-8").replace(
            f'name = "{eski[0]}"\nversion = "{eski[1]}"', f'name = "{eski[0]}"\nversion = "0.0.0-yeni"'
        ),
        encoding="utf-8",
    )
    assert (eski[0], "0.0.0-yeni") in rust_eksikleri(kilit)


def test_calisma_alani_uyeleri_crate_listesine_GIRMEZ_ve_envanter_kilitle_BIREBIR():
    adlar = {a for a, _ in u.cargo_paketleri()}
    assert "pemf-launcher-core" not in adlar and "pemf-vet-client" not in adlar
    env = u.rust_envanteri()
    assert {(a, s) for a, s, _ in env} == set(u.cargo_paketleri()), (
        "depodaki envanter Cargo.lock ile ayrıştı (--rust-yenile)"
    )
    bos = [a for a, _, li in env if not li.strip() or "doğrulanmadı" in li]
    assert not bos, f"lisansı boş / doğrulanmamış crate: {bos}"


def test_NOTICE_ureteci_ile_AYNI_rust_ve_LGPL_bolumleri():
    metin = NOTICE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert u._rust_bolumu() in metin, "Rust bölümü üreteçten farklı — `python scripts/lisans_envanteri_uret.py`"
    assert u._lgpl_bolumu() in metin, "LGPL bölümü üreteçten farklı"


def test_pi_heif_satiri_kaynak_BSD_ikili_LGPLv3_kodlayici_GPL_YOK():
    metin = NOTICE.read_text(encoding="utf-8")
    satir = next(s for s in metin.splitlines() if s.startswith("| `pi-heif` |"))
    for parca in (
        "BSD-3-Clause (kaynak)",
        "LGPL-3.0 (ikili",
        "libheif 1.18.1",
        "libde265 1.0.15",
        "ayrı DLL",
        "kodlayıcı / GPL bileşen YOK",
    ):
        assert parca in satir, f"pi-heif satırında yok: {parca!r} — {satir}"


def test_KRITIK_LGPL_bilesenleri_TAM_SURUM_kaynak_ve_TAM_lisans_metni():
    metin = NOTICE.read_text(encoding="utf-8")
    python_tablosu = dict(re.findall(r"^\| `([a-z0-9_.-]+)` \| ([^ |]+) \|", metin.split("### ", 1)[0], re.M))
    sabit = dict(
        re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", (KOK / "requirements.txt").read_text(encoding="utf-8"), re.M)
    )
    for ad, surum, lisans, kaynak, metinler in u.LGPL_BILESENLERI:
        assert surum in kaynak, f"{ad}: kaynak bağlantısı TAM sürümü ({surum}) taşımıyor: {kaynak}"
        assert kaynak.startswith("https://"), kaynak
        kisa = ad.split(" ")[0]
        if kisa in python_tablosu:
            dagitilan = python_tablosu[kisa] if python_tablosu[kisa] != "—" else sabit.get(kisa, "—")
            assert dagitilan == surum, f"{kisa}: LGPL bölümü {surum}, dağıtılan paket {dagitilan}"
        if "LGPL" in lisans:
            assert metinler, f"{ad}: LGPL metni bağlanmamış"
        for m in metinler:
            assert (KOK / m).is_file() and f"]({m})" in metin, m
    assert {"pi-heif", "soxr", "zeroconf"} <= {a.split(" ")[0] for a, *_ in u.LGPL_BILESENLERI}


def test_lisans_metinleri_TAM_ve_dogru_surum():
    beklenen = {
        "LGPL-2.1.txt": (
            "GNU LESSER GENERAL PUBLIC LICENSE",
            "Version 2.1, February 1999",
            "END OF TERMS AND CONDITIONS",
            25000,
        ),
        "LGPL-3.0.txt": (
            "GNU LESSER GENERAL PUBLIC LICENSE",
            "Version 3, 29 June 2007",
            "permanent authorization for you to choose that",
            7000,
        ),
        "GPL-3.0.txt": ("GNU GENERAL PUBLIC LICENSE", "Version 3, 29 June 2007", "END OF TERMS AND CONDITIONS", 34000),
    }
    for ad, (baslik, surum, son, boyut) in beklenen.items():
        t = (KOK / "licenses" / ad).read_text(encoding="utf-8")
        assert t.lstrip().startswith(baslik) and surum in t[:300] and son in t and len(t) >= boyut, ad
    assert "LESSER" not in (KOK / "licenses" / "GPL-3.0.txt").read_text(encoding="utf-8")[:200]


def test_rust_envanteri_yerel_kayit_defterinden_yenilenir_bulunamayan_DOGRULANMADI(tmp_path):
    kilit = tmp_path / "Cargo.lock"
    kilit.write_text(
        '[[package]]\nname = "uye"\nversion = "1.0.0"\n\n'
        '[[package]]\nname = "aa"\nversion = "1.2.3"\nsource = "registry+https://x"\n\n'
        '[[package]]\nname = "bb"\nversion = "0.1.0"\nsource = "registry+https://x"\n\n'
        '[[package]]\nname = "cc"\nversion = "2.0.0"\nsource = "git+https://x"\n',
        encoding="utf-8",
    )
    kok = tmp_path / "src"
    (kok / "index.crates.io-1" / "aa-1.2.3").mkdir(parents=True)
    (kok / "index.crates.io-1" / "aa-1.2.3" / "Cargo.toml").write_text(
        '[package]\nname = "aa"\nlicense = "MIT OR Apache-2.0"\n', encoding="utf-8"
    )
    (kok / "index.crates.io-1" / "cc-2.0.0").mkdir(parents=True)
    (kok / "index.crates.io-1" / "cc-2.0.0" / "Cargo.toml").write_text(
        '[package]\nname = "cc"\nlicense-file = "LICENSE"\n', encoding="utf-8"
    )
    assert u.rust_envanteri_yenile(kok, kilit) == [
        ("aa", "1.2.3", "MIT OR Apache-2.0"),
        ("bb", "0.1.0", "⚠️ doğrulanmadı"),
        ("cc", "2.0.0", "license-file (crate içi lisans dosyası)"),
    ]


def test_rust_yenile_kipi_JSON_yazar_dogrulanmamis_varsa_1_doner(tmp_path, monkeypatch, capsys):
    hedef = tmp_path / "rust.json"
    monkeypatch.setattr(u, "_RUST_ENVANTERI", hedef)
    monkeypatch.setattr(u, "rust_envanteri_yenile", lambda: [("aa", "1.0.0", "MIT"), ("bb", "2.0.0", "⚠️ doğrulanmadı")])
    monkeypatch.setattr("sys.argv", ["uret", "--rust-yenile"])
    assert u.main() == 1
    assert json.loads(hedef.read_text(encoding="utf-8"))["crateler"] == [
        ["aa", "1.0.0", "MIT"],
        ["bb", "2.0.0", "⚠️ doğrulanmadı"],
    ]
    assert "bb" in capsys.readouterr().out
    monkeypatch.setattr(u, "rust_envanteri_yenile", lambda: [("aa", "1.0.0", "MIT")])
    assert u.main() == 0
