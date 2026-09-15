# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DUZ-METIN YEDEK EMANET BAYRAGI TEK YERDE OKUNMALI (2026-09-15).

OLCULEN ARIZA. Goc kodu iki dosyaya kopyalanmis ve kopyalar AYNI politikayi IKI FARKLI
ortam degiskeninden okuyordu:

    database/sqlcipher_util.py       -> PEMF_KEEP_PLAIN_BACKUP   (hasta DB'si)
    database/treatment_history_db.py -> PEMF_KEEP_PLAIN_BAK      (tedavi + AI gecmisi)

SONUC: emanet isteyen operator bayragi set eder, IKI veritabanindan YALNIZ BIRINDE ise
yarar. Digeri sessizce duz-metin yedegi guvenli-siler. Hangisinin hangisi oldugu ne
belgede ne log'da yazili. Tersi de dogru: emaneti KAPATMAK isteyen biri yalniz birini
kapatir ve diger DB'nin TUM PII'sinin duz-metin kopyasi diskte KALIR.

⚠️ BU, DENETIMIN "kopya kod ariza dogurur" IDDIASININ KANITIDIR (docs/DEPO-DENETIMI-
2026-09-15.md §2.3). Teorik degil: iki isim zamanla AYRISMIS ve kimse gormemis.

⚠️ KAPI DURUMU OLCULDU: mevcut testler yalniz `PEMF_KEEP_PLAIN_BAK`i taniyordu
(test_at_rest_encryption_rollout.py, test_kalan_davranissal.py). `PEMF_KEEP_PLAIN_BACKUP`
icin SIFIR test vardi — yani iki isimden biri tamamen kapisizdi.

⚠️ BU KAPININ ILK TASARIMI YANLISTI (ayni oturumda duzeltildi). Once "HER IKI dosya da
AYNI adi OKUSUN" diye yazilmisti. O sozlesme, ismin ayrismasini engeller ama kopyayi
KORUR — ve dogru duzeltmeyi (tek yardimci + iki cagiran) KIRMIZI yapardi. Yani kapi,
cozumun kendisini yasaklayan bir kapiydi. Sozlesme "TEK YERDE okunur, digerleri CAGIRIR"
olarak degistirildi.

SOZLESME:
  · Bayrak `database/` altinda TEK dosyada okunur: sqlcipher_util.py (ortak yardimci).
  · Yardimci HEM kanonik HEM eski adi okur (eski ad geriye-uyum; sahada set edilmis
    olabilir, sessizce yok saymak emanet bekleyen birinin verisini siler).
  · treatment_history_db bayragi KENDI okumaz — yardimciyi CAGIRIR.
  · VARSAYILAN "0" = guvenli-sil (sahip karari 2026-08-08: .plain.bak TUM duz-metin
    PII'yi tasir ve SQLCipher'i baypas eder; disk calinirsa at-rest garantisi COKER).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_DB_DIZIN = _KOK / "database"
_SQLCIPHER = _DB_DIZIN / "sqlcipher_util.py"
_TEDAVI = _DB_DIZIN / "treatment_history_db.py"

#: Kanonik ad.
_KANONIK = "PEMF_KEEP_PLAIN_BACKUP"
#: Eski ad — okunmaya devam eder (geriye uyum), uyari loglanir.
_ESKI = "PEMF_KEEP_PLAIN_BAK"
#: Ortak yardimcinin adi. Iki goc yolu da bunu cagirir.
_YARDIMCI = "duz_metin_yedegi_emanete_al_mi"


def _kaynak(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _modul_sabitleri(agac: ast.Module) -> dict[str, str]:
    """Modul duzeyindeki `AD = "dize"` atamalari.

    ⚠️ GEREKLI: dogru duzeltme bayrak adlarini SABITE tasidi
    (`os.getenv(DUZ_METIN_YEDEK_BAYRAGI, "0")`). Yalniz `ast.Constant` arayan bir okuyucu
    o cagriyi GORMEZ ve kapi, kod dogruyken KIRMIZI kalir. (Ilk yazimda tam bu oldu.)
    """
    d: dict[str, str] = {}
    for n in agac.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            for h in n.targets:
                if isinstance(h, ast.Name):
                    d[h.id] = n.value.value
    return d


def _getenv_cagrilari(p: Path) -> list[tuple[str, str | None]]:
    """(ortam_degiskeni_adi, varsayilan) ciftleri — AST ile, sabitler COZULEREK.

    ⚠️ AST ZORUNLU: iki dosya da bayrak adini ACIKLAMA YORUMLARINDA ve log METINLERINDE
    defalarca aniyor. Ham metin aramasi, `os.getenv` cagrisi SILINSE BILE yesil kalirdi —
    bu deponun tekrar eden sinifi ("yorum kapiyi kandirdi").
    """
    agac = ast.parse(_kaynak(p))
    sabitler = _modul_sabitleri(agac)
    out: list[tuple[str, str | None]] = []
    for n in ast.walk(agac):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        f = n.func
        tanindi = False
        if isinstance(f, ast.Attribute):
            if f.attr == "getenv" and isinstance(f.value, ast.Name) and f.value.id == "os":
                tanindi = True
            elif f.attr == "get" and isinstance(f.value, ast.Attribute) and f.value.attr == "environ":
                tanindi = True
        if not tanindi:
            continue
        ilk = n.args[0]
        if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
            ad = ilk.value
        elif isinstance(ilk, ast.Name) and ilk.id in sabitler:
            ad = sabitler[ilk.id]
        else:
            continue
        vars_ = None
        if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
            vars_ = n.args[1].value
        out.append((ad, vars_))
    return out


def _getenv_okumalari(p: Path) -> set[str]:
    return {ad for ad, _ in _getenv_cagrilari(p)}


def _cagrilan_adlar(p: Path) -> set[str]:
    """Dosyada CAGRILAN fonksiyon adlari (AST; yorum/dize degil)."""
    adlar: set[str] = set()
    for n in ast.walk(ast.parse(_kaynak(p))):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                adlar.add(f.id)
            elif isinstance(f, ast.Attribute):
                adlar.add(f.attr)
    return adlar


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1) ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_emanet_bayragi_database_altinda_TEK_dosyada_okunur():
    """Iki yer okuyorsa isimler ayrisabilir — nitekim ayristilar."""
    okuyanlar = {p.name for p in sorted(_DB_DIZIN.glob("*.py")) if any("KEEP_PLAIN" in a for a in _getenv_okumalari(p))}
    assert okuyanlar == {_SQLCIPHER.name}, (
        f"Emanet bayragini okuyan dosyalar: {sorted(okuyanlar) or 'hicbiri'} — "
        f"YALNIZ {_SQLCIPHER.name} olmali (ortak yardimci). Birden fazla yer okursa "
        "adlar zamanla ayrisir ve operator bayragi set ettiginde veritabanlarindan "
        "yalniz biri etkilenir. 2026-09-15'te tam bu oldu."
    )


def test_KRITIK_yardimci_HEM_kanonik_HEM_eski_adi_okur():
    okunan = _getenv_okumalari(_SQLCIPHER)
    assert _KANONIK in okunan, f"kanonik ad ({_KANONIK}) okunmuyor"
    assert _ESKI in okunan, (
        f"eski ad ({_ESKI}) artik okunmuyor — sahada o bayragi set etmis biri sessizce "
        "emanetini kaybeder. Gecis, okumayi BIRAKARAK degil UYARARAK yapilir."
    )


def test_KRITIK_tedavi_yolu_ORTAK_yardimciyi_CAGIRIR():
    """treatment_history_db kendi okumayi birakip yardimciya gecmeli — yoksa 'tek dosyada
    okunur' testi, emanet dalini SILEREK de yesil yapilabilirdi."""
    assert _YARDIMCI in _cagrilan_adlar(_TEDAVI), (
        f"{_TEDAVI.name} ortak yardimciyi ({_YARDIMCI}) CAGIRMIYOR — emanet karari bu "
        "yolda ya kayboldu ya da yeniden yerel bir kopyaya baglandi"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2) KARSIT-KANITLAR — "tek yerde okunur"u ucuza yesil yapmanin yollarini kapat
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("yol", [_SQLCIPHER, _TEDAVI], ids=["sqlcipher_util", "treatment_history_db"])
def test_KARSIT_KANIT_emanet_dali_SILINMEDI(yol: Path):
    """⚠️ Emanet yolunu TAMAMEN kaldirmak da 'tek dosyada okunur' testini yesil yapardi.

    Emanet, anahtar kaybinda geri donusu olan tek kopyadir; dali silmek sessiz bir
    yetenek kaybi olurdu. Iki yolda da ACL-kilitli escrow adiminin durdugunu olcer.
    """
    assert "lock_down_file" in _cagrilan_adlar(yol), (
        f"{yol.name}: ACL-kilitli escrow adimi (lock_down_file) KAYBOLMUS — emanet yolu "
        "kaldirilmis demektir. Korumasiz escrow kabul edilemez ama escrow'u tamamen "
        "silmek de anahtar kaybinda geri donusu yok eder."
    )


def test_KARSIT_KANIT_varsayilan_GUVENLI_SIL_kalir():
    """Varsayilani "1" yapmak butun testleri yesil birakip at-rest garantisini COKERTIRDI."""
    cagrilar = {ad: vars_ for ad, vars_ in _getenv_cagrilari(_SQLCIPHER) if "KEEP_PLAIN" in ad}
    assert set(cagrilar) == {_KANONIK, _ESKI}, (
        f"beklenen iki ad okunmuyor: {sorted(cagrilar)} — kapi KOR kalmasin diye "
        "okuma bicimi degistiyse bu testi guncelleyin"
    )
    for ad, varsayilan in cagrilar.items():
        assert varsayilan == "0", (
            f"{ad} varsayilani {varsayilan!r} — '0' olmali. Varsayilan emanet demek, "
            "her klinikte TUM PII'nin duz-metin kopyasinin diskte kalmasi demektir "
            "(sahip karari 2026-08-08)."
        )


def test_KRITIK_bayrak_device_env_ile_TASINIR():
    """Servis (NSSM) ortami `deploy/device.env`ten yazilir ve etkilesimli kullanicinin
    ortamini MIRAS ALMAZ -> satir yoksa bayrak servis kurulumunda hic ulasilamaz.

    ⚠️ Launcher'in dogurdugu backend icin durum FARKLI ve bu ayrim olculdu:
    `launcher/core/src/backend.rs` haritayi `cmd.env(k, v)` ile uygular ve `env_clear()`
    YOKTUR -> orada ortam miras alinir. Yani bu, "launcher bayragi gecirmiyor" sinifi
    DEGILDIR; eksik olan yalniz servis yoludur.
    """
    metin = (_KOK / "deploy" / "device.env").read_text(encoding="utf-8")
    satirlar = [s.strip() for s in metin.splitlines() if s.strip().startswith(f"{_KANONIK}=")]
    assert satirlar == [f"{_KANONIK}=0"], (
        f"deploy/device.env satiri beklenen halde degil: {satirlar or 'YOK'}. "
        f"'{_KANONIK}=0' olmali — varsayilan guvenli-sil (sahip karari 2026-08-08)."
    )


def test_KARSIT_KANIT_yardimci_GERCEKTEN_goc_yolunda_cagrilir():
    """⚠️ Yardimciyi tanimlayip HIC CAGIRMAMAK da testleri yesil yapardi.

    `migrate_to_encrypted_if_needed` govdesinde cagrildigini AST ile dogrular — modul
    duzeyinde duran bir tanim, goc anindaki karari etkilemez.
    """
    agac = ast.parse(_kaynak(_SQLCIPHER))
    for n in ast.walk(agac):
        if isinstance(n, ast.FunctionDef) and n.name == "migrate_to_encrypted_if_needed":
            ic = {x.func.id for x in ast.walk(n) if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)}
            assert _YARDIMCI in ic, (
                f"{_YARDIMCI} goc fonksiyonunun ICINDE cagrilmiyor — emanet karari goc aninda alinmiyor demektir"
            )
            return
    pytest.fail("migrate_to_encrypted_if_needed bulunamadi — kapi kor kaldi")
