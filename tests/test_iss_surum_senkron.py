# -*- coding: utf-8 -*-
# Author: mertaygn
"""[BLD-6] `.iss` SÜRÜM ETİKETİ ile `VERSION` AYRIŞMASIN.

===============================================================================
ÖLÇÜLEN DURUM (2026-09-13)
===============================================================================
`build_tools/PEMF_Backend_Setup.iss` → `MyAppVersion "1.9.33"`
`guii/VERSION`                       → `1.9.50`
**17 sürüm sessizce ayrışmıştı.**

===============================================================================
NEDEN ÖNEMLİ — "üretim yolu kendini düzeltiyor" YETMEZ
===============================================================================
`build_installer.ps1` derleme sırasında `Sync-ReleaseVersion` ile `.iss`i VERSION'dan
yeniden yazar; o koridordan çıkan kurulum DOĞRU etiketlenir. Ama `.iss` başlığının KENDİ
kullanım adımı **çıplak `iscc.exe` / Inno Setup IDE** yolunu belgeliyor ve o yol
`Sync-ReleaseVersion`ı ATLAR → yeni kod, ESKİ sürüm etiketiyle paketlenir:

· "Program Ekle/Kaldır"da yanlış sürüm görünür (destek çağrısında yanlış teşhis),
· `OutputBaseFilename` yanlış dosya adı üretir (yanlış kurulum dağıtılabilir),
· `UninstallDisplayName` yanlış kalır.

⚠️ SINIF: "ikinci bir koridor var ve o koridorda kural uygulanmıyor". Bu depoda tekrar eden
arıza (bkz. katmanlı paket kör noktası DÖRT yerdeydi). Kapı, koridoru değil **değeri** ölçer:
hangi yoldan derlenirse derlensin `.iss` dosyasındaki etiket doğrudur.

⚠️ ÇIPA `c_soy`la SOYULMAZ — `.iss` bir Pascal/Inno betiği ve yorumları `;` ile başlar;
`c_soy` C/JS için yazıldı. Bunun yerine `#define` satırı REGEX ile, yorum satırları elenerek
aranır (yorum içindeki bir örnek sürüm kapıyı kandırmasın — "yorum kapıyı kandırdı" bu depoda
ALTI kez oldu).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

VERSION_DOSYASI = KOK / "VERSION"
ISS = KOK / "build_tools" / "PEMF_Backend_Setup.iss"

#: `#define MyAppVersion   "1.9.50"` — satır başında (yorum `;` ile başlar, elenir).
_DEFINE = re.compile(r'^\s*#define\s+MyAppVersion\s+"([^"]+)"\s*$')


def _iss_surumu() -> str:
    bulunan: list[str] = []
    for ham in ISS.read_text(encoding="utf-8", errors="replace").splitlines():
        if ham.lstrip().startswith(";"):
            continue  # Inno yorumu — çıpayı kandırmasın
        m = _DEFINE.match(ham)
        if m:
            bulunan.append(m.group(1))
    assert bulunan, "`.iss` dosyasinda #define MyAppVersion BULUNAMADI"
    assert len(bulunan) == 1, f"MyAppVersion BIRDEN COK tanimli: {bulunan} -> hangisi gecerli belirsiz"
    return bulunan[0]


@pytest.fixture(scope="module")
def surumler():
    if not VERSION_DOSYASI.is_file():
        pytest.fail(f"VERSION dosyasi YOK: {VERSION_DOSYASI}")
    if not ISS.is_file():
        pytest.fail(f".iss YOK: {ISS}")
    return VERSION_DOSYASI.read_text(encoding="utf-8").strip(), _iss_surumu()


def test_KRITIK_iss_surumu_VERSION_ile_AYNI(surumler):
    """⚠️ ASIL KAPI.

    MUTASYON: `.iss`teki `MyAppVersion`i eski bir sürüme (ör. "1.9.33") çevir → KIRMIZI.
    """
    version, iss = surumler
    assert iss == version, (
        f".iss surum etiketi ({iss}) VERSION ({version}) ile AYRISMIS -> ciplak iscc.exe / "
        "Inno IDE koridorundan derlenen kurulum YANLIS surumle etiketlenir "
        "(Program Ekle/Kaldir, OutputBaseFilename, destek kaydi). "
        "Duzeltme: .iss icindeki #define MyAppVersion degerini VERSION ile esitle."
    )


def test_surum_bicimi_GECERLI(surumler):
    """Karşıt kanıt: kural "ikisi de boş olsun" diye geçilemesin."""
    version, iss = surumler
    for ad, deger in (("VERSION", version), (".iss", iss)):
        assert re.fullmatch(r"\d+\.\d+\.\d+", deger), f"{ad} surumu gecersiz bicimde: {deger!r}"


def test_KRITIK_ciplak_ISCC_koridoru_UYARILI():
    """Kapı kırmızı olunca insan NE yapacağını bilmeli (bkz. [[hata-mesaji-eylem-soylesin]]).

    MUTASYON: `.iss` başlığındaki uyarı bloğunu sil → KIRMIZI.
    """
    metin = ISS.read_text(encoding="utf-8", errors="replace")
    assert "Sync-ReleaseVersion" in metin, (
        ".iss basligi ciplak-ISCC koridorunun surum etiketini ATLADIGINI soylemiyor -> "
        "o yolu kullanan kisi sessizce yanlis etiketli kurulum uretir"
    )
    assert "VERSION" in metin


def test_build_installer_HALA_senkronluyor():
    """Kapı, üretim yolundaki otomatik düzeltmeyi KALDIRMA gerekçesi değildir.

    MUTASYON: `build_installer.ps1`den `Sync-ReleaseVersion` çağrısını sil → KIRMIZI.
    """
    betik = (KOK / "build_tools" / "build_installer.ps1").read_text(encoding="utf-8", errors="replace")
    assert "Sync-ReleaseVersion -Version" in betik, (
        "build_installer.ps1 artik .iss surumunu VERSION'dan yazmiyor -> iki koridor da korumasiz"
    )
