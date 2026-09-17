# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""LINUX RUNTIME'IN YOKLUGU ARIZA DEGIL, KARARDIR (2026-09-17).

⚠️ BU DOSYA YEDINCI DENETIM HATASINI KILITLER — hatayi ben yaptim.

`DEPO-DENETIMI-2026-09-15.md` §3.4 "`base-linux.zip` KAYIP" diyordu ve `A4` olarak
yapilacaklar listesine girmisti. OLCULDU, YANLIS:

`launcher/core/src/manifest.rs` kayitli bir SAHIP KARARI tasiyor (2026-08-09, Tier 1) ve
Linux/mac runtime'in YOKLUGUNU kapiyla kilitliyor:

    assert!(!m.runtimes.contains_key(platform::LINUX_X64),
        "linux-x64 manifest'e geri girdi — o platformda rollout freni ve self-update YOK");

Gerekce (kararin kendi metninden): o platformlarda `layers` YOKTU -> rollout freni
calismiyordu ve client self-update'i Windows'a ozeldi -> kurulan cihaz ESKI surumde
KALICI kilitleniyor, bozuk bir yayin geri cekilemiyordu. Client artik "bu platform icin
paket yok" deyip DURUR — sessizce kilitli cihaz kurmaktansa ACIK HATA.

OLCULDU (2026-09-17):
  · `pemf-app-packages/manifest.json` -> `runtimes: []`, `layers` yalniz `win-x64`
  · `pemf-update` deposunun ALTI release'inin hicbirinde Linux varligi yok (0/6)
  · `linux-backend.yml` -> `permissions: contents: read` + yalniz `upload-artifact`,
    yani release'e YAZAMAZ; "workflow'u bir kez kostur" cozumu de yanlisti

⚠️ BULGU NEDEN YANLIS CIKTI: `docs/LAUNCHER_SPEC.md`teki "Linux client sessizce Windows
base.zip indirir" uyarisini GUNCEL sandim. O satir **v1 formatinin** TARIHSEL tuzagini
anlatiyor; hemen altindaki **v2 hedefi** (sessiz fallback yok, sert hata) 08-09'da zaten
uygulanmis. Belgenin "hedef" ile "gerceklesmis durum"u ayirmamasi bu hatayi uretti.

BU KAPININ ISI: iki belgedeki duzeltmenin yerinde kalmasini saglamak. Kapi kirmizi
donerse birisi bayat "KAYIP/yapilacak" tavsiyesini geri getirmis demektir.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_SPEC = KOK / "docs" / "LAUNCHER_SPEC.md"
_DENETIM = KOK / "docs" / "DEPO-DENETIMI-2026-09-15.md"
_MANIFEST_RS = KOK / "launcher" / "core" / "src" / "manifest.rs"
_YEREL_MANIFEST = KOK / "pemf-app-packages" / "manifest.json"


def _rust_kod(p: Path) -> str:
    """Yorumlari ayiklanmis Rust kaynagi — karar metni yorumda da geciyor, iddia KODA pinli."""
    return "\n".join(re.sub(r"//.*$", "", s) for s in p.read_text(encoding="utf-8").splitlines())


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_launcher_linux_YOKLUGUNU_kilitliyor():
    """Sahip karari KODDA duruyor mu? (yorumda degil, gercek `assert!`te)"""
    kod = _rust_kod(_MANIFEST_RS)
    assert "LINUX_X64" in kod, "linux-x64 iddiasi manifest.rs'ten kaybolmus"
    assert re.search(r"assert!\(\s*!\s*m\.runtimes\.contains_key\(platform::LINUX_X64", kod), (
        "linux-x64'un YOKLUGUNU kilitleyen `assert!` kaybolmus -> paket geri sizabilir ve "
        "o platformda rollout freni/self-update olmadan cihaz kilitlenebilir"
    )


def test_KRITIK_SPEC_v1_uyarisini_TARIHSEL_isaretliyor():
    """⚠️ Bu satir bir denetim hatasi uretti; belge artik durumu ACIKCA soylemeli."""
    metin = _SPEC.read_text(encoding="utf-8")
    assert "base-linux.zip" in metin, "SPEC artik konudan soz etmiyor — kapi bayatlamis olabilir"
    assert "TARİHSELDİR" in metin or "TARIHSELDIR" in metin, (
        "LAUNCHER_SPEC'teki v1 uyarisi TARIHSEL oldugu belirtilmemis -> bir sonraki okuyucu "
        "(ve denetim) onu GUNCEL sanar; bu hata 2026-09-15'te tam boyle olustu"
    )
    assert "2026-08-09" in metin, "v2 hedefinin ne zaman gerceklestigi yazili degil"


def test_KRITIK_denetim_A4_bulgusu_YANLIS_isaretli():
    """Bayat 'yapilacak' maddesi listede kalirsa biri yine ugrasir."""
    metin = _DENETIM.read_text(encoding="utf-8")
    assert "BU BULGU YANLIŞTI" in metin, (
        "denetimdeki `base-linux.zip KAYIP` bulgusu duzeltilmemis -> yokluk ARIZA sanilmaya devam eder"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_win_x64_HALA_kurulabilir():
    """⚠️ "Linux yok" dogru; ama WINDOWS da kaybolursa hicbir kurulum yapilamaz.

    Kararin sinirini olcer: cikarilanlar linux/mac, win-x64 DEGIL.
    """
    kod = _rust_kod(_MANIFEST_RS)
    assert re.search(
        r"m\.runtimes\.contains_key\(platform::WIN_X64\)\s*\|\|\s*m\.layers\.contains_key\(platform::WIN_X64\)", kod
    ), "win-x64 kurulabilirlik iddiasi kaybolmus -> Windows'ta hicbir kurulum yapilamazken manifest gecerli sayilabilir"


def test_KARSIT_KANIT_yerel_manifest_KARARLA_tutarli():
    """Belge ve kod bir sey der, uretilen manifest baska bir sey yaparsa kapi bos guvence olur."""
    if not _YEREL_MANIFEST.exists():
        return  # paket agaci yoksa (temiz checkout) olculecek sey yok
    d = json.loads(_YEREL_MANIFEST.read_text(encoding="utf-8"))
    rt = d.get("runtimes", {}) or {}
    assert "linux-x64" not in rt, "yerel manifest linux-x64 DUYURUYOR -> sahip kararina aykiri"
    ly = d.get("layers", {}) or {}
    assert "win-x64" in ly or "win-x64" in rt, (
        "manifest Windows icin NE layers NE runtimes tasiyor -> kurulum yapilamaz"
    )


def test_KARSIT_KANIT_geri_alma_YOLU_yazili():
    """Karar geri alinabilir olmali; nasil yapilacagi yazili degilse karar bir CIKMAZ olur.

    ⚠️ Ozellikle `linux-backend.yml`in bugun release'e YAZAMADIGI kayitli olmali — yoksa
    "workflow'u kostur yeter" sanilir (ben tam bunu onerdim ve YANLISTI).
    """
    metin = _SPEC.read_text(encoding="utf-8")
    assert "linux-backend.yml" in metin, "geri alma yolu (CI ile uretim) yazili degil"
    assert "contents: read" in metin, (
        "workflow'un release'e YAZAMADIGI kayitli degil -> 'bir kez kostur' yanilgisi tekrarlanir"
    )
