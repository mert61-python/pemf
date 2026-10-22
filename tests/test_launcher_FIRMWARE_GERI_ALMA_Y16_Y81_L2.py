# Author: mertaygn, cglrgrkn
"""LN L2 · Y16 + Y81 (D1.119) — launcher, backend `firmwareGuncelleme.istemciGeriAlinmali == true` iken (ve YALNIZ o zaman) yeni
client'ı sağlık kapılı GERİ ALIR.

Davranış kolu Rust'ta (`launcher/core/src/backend.rs` testleri): `firmware_karari_govdeden` yalnız JSON `true`'da `GeriAl` döner
(`uyum: null`, "hedef sürümü bildirmedi", alan yok, `null`, dizge / sayı → geri alma YOK); `firmware_kararini_bekle` karar gelene kadar
yoklar, eski backend'de hemen, bütçe dolunca `Bilinmiyor` döner.

Bu dosya KABLOLAMAYI ölçer (Rust uygulama crate'inde `apply_runtime_update` gerçek süreç öldürdüğü için — `kill_stray_backends` —
davranışsal olarak koşturulamaz): `main.rs` YORUMSUZ okunur (`rs_soyucu`), `start_backend` Ok kolunun ÜST düzeyinde
  (1) `if backend::firmware_kararini_bekle(port, …) == backend::FirmwareKarari::GeriAl {` VAR, dbReady dalından SONRA, onaydan
      (`guncellemeyi_onayla` — `runtime.old` silinir) ÖNCE;
  (2) bloğu `return Ok(firmware_uyumsuz_geri_al(child, port, …))` döner;
  (3) `firmware_uyumsuz_geri_al` sırası: E-stop'lu söküm (`stop_backend_for_teardown`) → deneme sayacı (`geri_almayi_kaydet`) →
      eski sürüme dönüş (`guncellemeyi_geri_al`) → `kod: Some(KOD_FIRMWARE_UYUMSUZ)` + katalog nedeni;
  (4) arayüz `rolled_back` + `kod === "firmware_uyumsuz"` → `rtRollbackFirmware` notu (iki dilde katalogda).
Her denetleyicinin mutantı AYNI dosyada KIRMIZI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from launcher_onay_karari import _Kaynak, db_kapisi_denetle
from rs_soyucu import ifade_deseni

KOK = Path(__file__).resolve().parents[1]
MAIN_RS = KOK / "launcher" / "app" / "src" / "main.rs"
INDEX = KOK / "launcher" / "app" / "ui" / "index.html"
KATALOG = KOK / "launcher" / "i18n"

FW_IF = (
    "if backend::firmware_kararini_bekle(port, backend::FIRMWARE_KARAR_BUTCESI, FIRMWARE_KARAR_YOKLAMA)"
    " == backend::FirmwareKarari::GeriAl {"
)
FW_DON = "return Ok(firmware_uyumsuz_geri_al(child, port, &root2, &manifest_raw, &geri, bellek2.clone()));"
ONAYLA = "flow::guncellemeyi_onayla(&root2, &geri);"


def firmware_kapisi_denetle(src: str) -> None:
    k, (obas, oson), (_ib, db_son) = db_kapisi_denetle(src)
    fw = k.tek(obas, oson, FW_IF, "start_backend Ok kolu (firmware kararı)")
    fbas, fson = k.blok(fw, FW_IF)
    k.tek(fbas, fson, FW_DON, "firmware GeriAl dalı")
    onay = k.tek(obas, oson, ONAYLA, "start_backend Ok kolu")
    assert db_son < fw < onay, "firmware kararı dbReady dalından SONRA ve onaydan (runtime.old silinir) ÖNCE değil"


def yardimci_sirasi_denetle(src: str) -> None:
    k = _Kaynak(src)
    bas_ifade = "fn firmware_uyumsuz_geri_al("
    es = list(ifade_deseni(bas_ifade).finditer(k.soy))
    assert len(es) == 1, f"`{bas_ifade}` {len(es)} kez"
    acilis = k.soy.index("{", es[0].end())
    from rs_soyucu import blok_sonu

    bas, son = acilis + 1, blok_sonu(k.maske, acilis)
    sokum = k.tek(bas, son, "stop_backend_for_teardown(Some((child, port)), root, bellek);", "yardımcı")
    kaydet = k.tek(bas, son, "flow::geri_almayi_kaydet(root, manifest_raw);", "yardımcı")
    geri = k.tek(bas, son, "flow::guncellemeyi_geri_al(root, geri)", "yardımcı")
    # `kod` / `sebep` dönülen yapı değişmezinin İÇİNDE (üst düzeyde değil) — gövdede ara.
    m_kod = ifade_deseni("kod: Some(KOD_FIRMWARE_UYUMSUZ),").search(k.soy, bas, son)
    m_sebep = ifade_deseni('sebep: pemf_launcher_core::dil::t("rust.hata.guncellemeFirmwareUyumsuz"),').search(
        k.soy, bas, son
    )
    assert m_kod and m_sebep, "geri alma sonucu neden kodunu / katalog nedenini taşımıyor"
    assert sokum < kaydet < geri < m_kod.start(), "sıra E-stop'lu söküm → deneme sayacı → geri dönüş değil"
    assert re.search(r'const\s+KOD_FIRMWARE_UYUMSUZ\s*:\s*&str\s*=\s*"firmware_uyumsuz"\s*;', k.soy), (
        "neden kodu sabiti yok / farklı"
    )


def arayuz_denetle(html: str) -> None:
    i = html.index('if (status === "rolled_back") {')
    blok = html[i : i + 700]
    assert re.search(
        r'r\.kod\s*===\s*"firmware_uyumsuz"\s*\?\s*t\(\)\.rtRollbackFirmware\s*:\s*t\(\)\.rtRollback', blok
    ), "rolled_back kolu firmware uyumsuzluğunda ayrı notu göstermiyor (genel 'Yeni sürüm açılamadı' yanlış olur)"


@pytest.fixture(scope="module")
def main_rs() -> str:
    return MAIN_RS.read_text(encoding="utf-8")


def test_KRITIK_L2_firmware_geri_alma_SAGLIK_KAPISINDA_onaydan_ONCE(main_rs):
    firmware_kapisi_denetle(main_rs)


def test_KRITIK_L2_geri_alma_yardimcisi_ESTOP_sokum_sayac_geri_donus_sirasinda(main_rs):
    yardimci_sirasi_denetle(main_rs)


def test_KRITIK_L2_arayuz_firmware_nedenini_AYRI_notla_gosterir_iki_dilde():
    arayuz_denetle(INDEX.read_text(encoding="utf-8"))
    for dil in ("tr", "en"):
        k = json.loads((KATALOG / f"{dil}.json").read_text(encoding="utf-8"))
        assert k["ui"].get("rtRollbackFirmware", "").strip(), f"{dil}: ui.rtRollbackFirmware boş"
        assert k["rust"]["hata"].get("guncellemeFirmwareUyumsuz", "").strip(), (
            f"{dil}: rust.hata.guncellemeFirmwareUyumsuz boş"
        )
    tr = json.loads((KATALOG / "tr.json").read_text(encoding="utf-8"))["ui"]["rtRollbackFirmware"]
    assert "açılamadı" not in tr and "teknik destek" in tr, f"TR not yanlış / eylem söylemiyor: {tr}"


_FW_IF_SATIRI = "                if backend::firmware_kararini_bekle(port, backend::FIRMWARE_KARAR_BUTCESI, FIRMWARE_KARAR_YOKLAMA)\n"
_MUTANTLAR = [
    (
        "fw_kapisi_YOK",
        firmware_kapisi_denetle,
        [(_FW_IF_SATIRI + "                    == backend::FirmwareKarari::GeriAl\n", "                if false\n")],
    ),
    (
        "fw_kapisi_TERS",
        firmware_kapisi_denetle,
        [
            (
                "                    == backend::FirmwareKarari::GeriAl\n",
                "                    != backend::FirmwareKarari::GeriAl\n",
            )
        ],
    ),
    (
        "fw_kapisi_ONAYDAN_SONRA",
        firmware_kapisi_denetle,
        [
            ("                flow::guncellemeyi_onayla(&root2, &geri);\n", ""),
            (_FW_IF_SATIRI, "                flow::guncellemeyi_onayla(&root2, &geri);\n" + _FW_IF_SATIRI),
        ],
    ),
    (
        "yardimci_ESTOPSUZ",
        yardimci_sirasi_denetle,
        [("    stop_backend_for_teardown(Some((child, port)), root, bellek);\n", "    drop(child);\n")],
    ),
    ("yardimci_SAYACSIZ", yardimci_sirasi_denetle, [("    flow::geri_almayi_kaydet(root, manifest_raw);\n", "")]),
    (
        "yardimci_KODSUZ",
        yardimci_sirasi_denetle,
        [("        kod: Some(KOD_FIRMWARE_UYUMSUZ),\n", "        kod: None,\n")],
    ),
]


@pytest.mark.parametrize("ad,denetleyici,degisiklikler", _MUTANTLAR, ids=[m[0] for m in _MUTANTLAR])
def test_KRITIK_L2_denetleyici_mutantta_KIRMIZI(main_rs, ad, denetleyici, degisiklikler):
    src = main_rs.replace("\r\n", "\n")
    for eski, yeni in degisiklikler:
        assert src.count(eski) == 1, f"mutant çapası {src.count(eski)} kez: {eski[:70]!r}"
        src = src.replace(eski, yeni)
    with pytest.raises(AssertionError):
        denetleyici(src)


def test_KRITIK_L2_arayuz_denetleyicisi_mutantta_KIRMIZI():
    html = INDEX.read_text(encoding="utf-8")
    mutant = html.replace('r.kod === "firmware_uyumsuz" ? t().rtRollbackFirmware : t().rtRollback', "t().rtRollback")
    assert mutant != html
    with pytest.raises(AssertionError):
        arayuz_denetle(mutant)
