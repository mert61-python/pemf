# Author: mertaygn, cglrgrkn
"""STM main.c İKİ KOPYADA BAYT-BAYT AYNI KALMALI — sessiz firmware ayrışması sınıfı.

NEDEN VAR: `firmware/main.c` kanoniktir (belgeler/denetimler ona referans verir); CubeIDE
proje kopyası `firmware/stm32_pemf/Core/Src/main.c` de derlemenin okuduğu ağaçtır. İki kopya
tam olarak `frontend/` olayındaki gibi sessizce ayrışabilir (o olayda ikinci kopya 15 commit
geride kaldı ve düzeltmeler pakete HİÇ ulaşmadı — bkz. test_frontend_tek_kaynak.py). Üstelik
bu ayrışma bir kez GERÇEKTEN yaşandı: masaüstündeki proje main.c'si 24 Haziran'da donmuş,
depodaki 17 Ağustos denetim düzeltmelerini hiç almamıştı (2026-08-18'de ölçüldü, takas edildi).

KURAL: main.c değişecekse İKİSİ BİRDEN değişir. Bu kapı ayrışmayı push'tan önce kırar.

⚠️ Ayrıca: CubeMX "Generate Code" proje kopyasındaki main.c'yi İSKELETLE EZER (dosyada USER
CODE işaretçisi yok — elle yazılmış). O kaza da bu kapıya takılır: ezilen kopya kanonikle
eşleşmez ve test adıyla söyler.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
KANONIK = KOK / "firmware" / "main.c"
PROJE = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.skipif(not PROJE.exists(), reason="stm32_pemf proje kopyası bu çalışma kopyasında yok")
def test_KRITIK_stm_main_iki_kopyada_BAYT_BAYT_AYNI():
    assert KANONIK.exists(), "kanonik firmware/main.c yok"
    assert _sha(KANONIK) == _sha(PROJE), (
        "firmware/main.c ile firmware/stm32_pemf/Core/Src/main.c AYRIŞTI. main.c değişecekse "
        "İKİSİ BİRDEN güncellenir (kural 2026-08-19). Muhtemel sebepler: yalnız birine yazılan "
        "düzeltme, ya da CubeMX 'Generate Code'un proje kopyasını iskeletle ezmesi. Kanonik "
        "kaynak firmware/main.c'dir — doğru içeriği oradan proje kopyasına kopyalayın "
        "(ya da düzeltme proje tarafında yapıldıysa tersini)."
    )


@pytest.mark.skipif(not PROJE.exists(), reason="stm32_pemf proje kopyası bu çalışma kopyasında yok")
def test_KARSIT_KANIT_kapi_bos_gecmiyor():
    """Dosyalar gerçek ve anlamlı — boş/iskelet dosya eşitliği 'geçti' sayılmasın."""
    icerik = KANONIK.read_text(encoding="utf-8", errors="replace")
    assert len(icerik.splitlines()) > 1000, "kanonik main.c küçülmüş — iskeletle mi ezildi?"
    assert "PEMF_ForceAllCoilOutputsLow" in icerik, (
        "güvenlik fonksiyonu kaybolmuş — bu main.c denetim düzeltmeli sürüm DEĞİL"
    )
    assert "USER CODE BEGIN" not in icerik, (
        "main.c CubeMX iskeletine dönmüş (USER CODE işaretçileri belirdi) — elle yazılmış "
        "1509 satırlık firmware 'Generate Code' ile ezilmiş olabilir"
    )


def test_KRITIK_build_ciktisi_Debug_izlenmiyor():
    """Kaynak-değil kuralı: CubeIDE Debug/ çıktısı (31 MB) depoya sızmamalı."""
    ch = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf/Debug"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    assert not ch.stdout.strip(), (
        f"Debug/ build çıktısı izleniyor: {ch.stdout.splitlines()[:3]} — .gitignore kuralı "
        "(firmware/stm32_pemf/Debug/) düşmüş olabilir."
    )
    # karşıt-kanıt: proje kaynağı GERÇEKTEN izleniyor (kural fazla geniş değil)
    ch2 = subprocess.run(
        ["git", "ls-files", "--", "firmware/stm32_pemf"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert len(ch2.stdout.splitlines()) > 90, (
        "stm32_pemf kaynağı izlenmiyor/eksik — gitignore kuralı projeyi de yutmuş olabilir"
    )
