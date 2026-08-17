# Author: mertaygn, cglrgrkn
"""🔴 KIRMIZI ÇİZGİ (TIBBİ GÜVENLİK) — Inno installer, bobinleri güvene ALMADAN kill etmemeli.

DENETİM BULGUSU (2026-08-17). `build_tools/PEMF_Backend_Setup.iss` içindeki `ssInstall` adımı
şu sırayla çalışıyordu:

    Exec('taskkill.exe', '/F /IM PEMF_Backend.exe', ...);   // ← FORCE KILL ÖNCE
    Exec('sc.exe', 'stop PemfBackend', ...);                // ← graceful SONRA

`taskkill /F` = `TerminateProcess`, **sinyalsizdir** → `backend_service.py`'nin sinyal işleyicisi
HİÇ koşmaz → `_safe_stop_outputs` çalışmaz → STM kuyruk-flush ve ESP bobinlerine MQTT STOP
yayınlanmaz. Bobin 1-5 firmware'in ölü-adam devresiyle ≤1500 ms'de düşer; **bobin 6-8'in link
watchdog'u YOKTUR** (`scripts/pemf_teardown.ps1`) → kalan seans süresince (varsayılan 20 dk, AI Pro
yolunda 120 dk'ya kadar) hastanın üzerinde enerjili kalır.

Tetikleyici gerçek ve belgeli: kurulu bir cihazda offline Inno installer'ın ELLE yeniden
çalıştırılması (`offline dağıtım/OKU-README.md` yükseltme yolu; `.iss`'in kendi yorumu kill'i
"(re-install)" için gerekçelendiriyor).

⚠️ ASİMETRİ KASITSIZDI: aynı deponun KALDIRMA yolu sırayı DOĞRU kuruyor
(`scripts/setup_services.ps1`): *"Force-kill'i ÖNCE yaparsak bu graceful bobin-STOP ATLANIR →
bobinler firmware-watchdog'una kadar açık kalır. Bu yüzden önce graceful-dur+bekle, SONRA
remove + force-kill fallback."* NSIS yolu da doğru ve testle kilitli
(`tests/test_kaldirma_yetim_surec_temizligi.py::test_estop_taskkillden_once_gonderilir`).
`.iss` hiçbir testte davranışsal olarak denetlenmiyordu — bu dosya o boşluğu kapatır.

⚠️ Force-kill KALDIRILMAZ: `AppExit Default Restart` + dosya kilitleri yüzünden son çare olarak
gerekli (karşı-kanıt testi aşağıda).
"""

import re
from pathlib import Path

import pytest

ISS = Path(__file__).resolve().parent.parent / "build_tools" / "PEMF_Backend_Setup.iss"


@pytest.fixture(scope="module")
def ssinstall_satirlari():
    """`CurStepChanged` içindeki `if CurStep = ssInstall then` bloğunun satırları."""
    kaynak = ISS.read_text(encoding="utf-8")
    assert "procedure CurStepChanged" in kaynak, "CurStepChanged kayboldu — .iss yapisi degismis"

    satirlar = kaynak.splitlines()
    bas = next(i for i, s in enumerate(satirlar) if re.search(r"CurStep\s*=\s*ssInstall", s))
    # Blok, bir sonraki `else if CurStep` (ya da procedure sonu) ile biter.
    son = next(
        (i for i in range(bas + 1, len(satirlar)) if re.search(r"else\s+if\s+CurStep", satirlar[i])),
        len(satirlar),
    )
    govde = satirlar[bas:son]
    assert govde, "ssInstall blogu bos"
    # ⚠️ YORUM SATIRLARI ATILIR. Aksi halde bu kapı "doğru sırayı ANLATAN bir yorum yazmakla"
    # geçilebilirdi — oysa bu deponun 1 numaralı hata deseni tam olarak "yorum bir şey iddia
    # ediyor, kod başka şey yapıyor". Kapı yalnız YÜRÜTÜLEN ifadelere bakar.
    kod = [s.strip() for s in govde]
    return [s for s in kod if s and not s.startswith("//")]


def _ilk_indeks(satirlar, desen):
    return next((i for i, s in enumerate(satirlar) if re.search(desen, s, re.IGNORECASE)), None)


def test_KRITIK_graceful_durdurma_taskkillden_ONCE_gelir(ssinstall_satirlari):
    """🔴 Graceful servis durdurma HER ZAMAN force-kill'den önce.

    Graceful yol: `sc stop` / `nssm stop` → NSSM Ctrl+C (`AppStopMethodConsole 15000`) →
    backend signal-handler → bobin STOP + STM kuyruk-flush.
    """
    graceful = _ilk_indeks(ssinstall_satirlari, r"(sc\.exe|nssm).*stop|stop\s+PemfBackend")
    assert graceful is not None, "ssInstall'da graceful servis durdurma YOK — bobinler enerjili oldurulur."
    kill = _ilk_indeks(ssinstall_satirlari, r"taskkill")
    assert kill is not None, "taskkill satiri yok (kaldirilmis?) — karsit-kanit testine bakin"
    assert graceful < kill, (
        f"graceful durdurma (satir {graceful}) İLK taskkill'den (satir {kill}) SONRA geliyor. "
        "`taskkill /F` sinyalsizdir → _safe_stop_outputs CALISMAZ → ESP bobinleri 6-8 "
        "(link-watchdog'u YOK) hastanin uzerinde enerjili kalir."
    )


def test_KRITIK_graceful_ile_forcekill_ARASINDA_bekleme_var(ssinstall_satirlari):
    """🔴 `sc stop` ASENKRONDUR — beklemeden kill etmek graceful'ü yarıda keser.

    `setup_services.ps1` kaldırma yolunda servis STOPPED olana kadar 40x500 ms bekliyor. Kurulum
    yolunda da bir üst-sınırlı bekleme olmalı; yoksa sıra doğru olsa bile `taskkill` graceful
    kapanışla YARIŞIR ve bobin STOP'u yine kaybedilebilir.
    """
    graceful = _ilk_indeks(ssinstall_satirlari, r"(sc\.exe|nssm).*stop|stop\s+PemfBackend")
    kill = _ilk_indeks(ssinstall_satirlari, r"taskkill")
    assert graceful is not None and kill is not None
    arada = " ".join(ssinstall_satirlari[graceful:kill])
    assert re.search(r"Sleep\s*\(", arada, re.IGNORECASE), (
        "graceful durdurma ile taskkill arasinda BEKLEME yok → `sc stop` asenkron oldugu icin "
        "force-kill graceful bobin-STOP'u yarida keser."
    )


def test_force_kill_FALLBACK_olarak_KORUNUR_karsit_kanit(ssinstall_satirlari):
    """Karşı-kanıt: force-kill KALDIRILMAMALI.

    `setup_services.ps1:302` servisi `AppExit Default Restart` ile kuruyor ve cloudflared/mosquitto
    `{app}`'i kilitleyebilir. Graceful başarısız/asılıysa `[Files]` kopyalaması kilitli-EXE hatasına
    düşer. Yani doğru düzeltme "kill'i sil" değil, "kill'i graceful'ün ARKASINA al".
    """
    assert _ilk_indeks(ssinstall_satirlari, r"taskkill") is not None, (
        "force-kill fallback kaldirilmis — kilitli dosya yuzunden kurulum yarim kalabilir"
    )


def test_kaldirma_yolu_ZATEN_dogru_referans_karsit_kanit():
    """Karşı-kanıt/çıpa: kaldırma yolu graceful sırayı zaten uyguluyor ve asimetri kasıtsızdı.

    Bu test, düzeltmenin "yeni bir politika" değil **var olan değişmezin kurulum yoluna taşınması**
    olduğunu belgeler. `setup_services.ps1` gerekçesi kaybolursa burada görünür.
    """
    ps1 = (Path(__file__).resolve().parent.parent / "scripts" / "setup_services.ps1").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "graceful bobin-STOP ATLANIR" in ps1, (
        "setup_services.ps1'deki graceful-sira gerekcesi kaybolmus — .iss duzeltmesinin capasi bu"
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
