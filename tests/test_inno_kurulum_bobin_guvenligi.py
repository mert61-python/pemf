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


# ─────────────────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-08-23 (P0) — SIRA DOĞRUYDU AMA SERVİS YOKKEN GRACEFUL HİÇ KOŞMUYORDU
# ─────────────────────────────────────────────────────────────────────────────────────────
#
# 2026-08-17 düzeltmesi force-kill'i graceful'ün ARKASINA aldı ve yukarıdaki testler bunu
# kilitliyor. Ama graceful yol `if ResultCode <> 1060 then` (= "servis KURULU mu?") bloğunun
# İÇİNDE; force-kill blok DIŞINDA ve KOŞULSUZ. LAUNCHER dağıtımı olan bir makinede `PemfBackend`
# servisi YOKTUR → `sc query` 1060 döner → graceful blok TAMAMEN atlanır → geriye yalnız sinyalsiz
# `taskkill /F` kalır. Yani bobin-STOP'a giden tek yol servise bağlıydı ve launcher kurulumlarında
# hiç çalışmıyordu; yukarıdaki SIRA testleri bu yolu göremez (ikisi de "graceful < kill" der).
#
# Kardeş NSIS yolu bunu doğru yapıyor (`launcher/app/windows/hooks.nsi`): backend.port'u okur,
# portu doğrular, `/api/hardware/emergency_stop`a POST atar, ~1800 ms bekler, SONRA taskkill.
# `.iss`'te `emergency_stop` HİÇ geçmiyordu.


def _iss_kaynak() -> str:
    return ISS.read_text(encoding="utf-8")


# ⚠️ E-stop bir YORDAMA sarili (kod tekrari olmasin diye). Bu yuzden kapi IKI HALKAYI birden
# olcer: (a) ssInstall yordami KOSULSUZ cagiriyor mu, (b) yordam gercekten E-stop gonderiyor mu.
# Yalniz birine bakmak, bosaltilmis bir yordami ya da cagrilmayan bir korumayi yesil gosterirdi.
_ESTOP_CAGRI = r"PemfBobinleriGuveneAl\s*\(\s*\)"


def _estop_yordami() -> str:
    """`PemfBobinleriGuveneAl` ve yardimcilarinin gövdesi (ilk tanimdan CurStepChanged'e kadar)."""
    k = _iss_kaynak()
    bas = k.find("procedure PemfEstopPortaGonder")
    son = k.find("procedure CurStepChanged")
    assert bas > 0 and son > bas, "E-stop yordamlari bulunamadi — .iss yapisi degismis"
    return k[bas:son]


def test_KRITIK_ESTOP_servis_YOKKEN_de_gonderilir(ssinstall_satirlari):
    """🔴 E-stop, servis varlığı kontrolüne KOŞULLU OLAMAZ.

    Launcher dağıtımında servis yoktur; E-stop `if ResultCode <> 1060` bloğunun içine konursa
    tam da korunması gereken senaryoda hiç çalışmaz. Bu yüzden servis sorgusundan ÖNCE gelmeli.
    """
    estop = _ilk_indeks(ssinstall_satirlari, _ESTOP_CAGRI)
    assert estop is not None, (
        "ssInstall'da donanim E-stop'u YOK — launcher kurulumu olan makinede (servis yok) "
        "graceful blok atlanir ve backend SINYALSIZ oldurulur: ESP bobinleri 6-8 "
        "(link-watchdog'u YOK) seans suresince HASTANIN UZERINDE enerjili kalir"
    )
    servis_sorgusu = _ilk_indeks(ssinstall_satirlari, r"query\s+PemfBackend")
    assert servis_sorgusu is not None, "servis sorgusu bulunamadi — .iss yapisi degismis"
    assert estop < servis_sorgusu, (
        f"E-stop (satir {estop}) servis sorgusundan (satir {servis_sorgusu}) SONRA geliyor → "
        "servis-yok yolunda kosullu kalma riski. E-stop KOSULSUZ ve EN BASTA olmali."
    )


def test_KRITIK_ESTOP_taskkillden_ONCE_gelir(ssinstall_satirlari):
    estop = _ilk_indeks(ssinstall_satirlari, _ESTOP_CAGRI)
    kill = _ilk_indeks(ssinstall_satirlari, r"taskkill")
    assert estop is not None and kill is not None
    assert estop < kill, "E-stop force-kill'den SONRA — bobinler enerjili oldurulur"


def test_KRITIK_ESTOP_yordami_GERCEKTEN_gonderiyor():
    """Ikinci halka: cagri var ama yordam bosaltilmissa koruma yoktur."""
    g = _estop_yordami()
    assert "emergency_stop" in g, "E-stop yordami `/api/hardware/emergency_stop` CAGIRMIYOR — cagri var ama koruma BOS"
    assert "Invoke-RestMethod" in g, "E-stop HTTP istegi yapilmiyor"


def test_KRITIK_ESTOP_ile_kill_arasinda_BEKLEME_var():
    """MQTT publish + STM seri-kuyruk flush zaman ister; NSIS ikizi 1800 ms bekliyor.

    Bekleme yordamin ICINDE (gonderimden hemen sonra) — cagri doner donmez taskkill kosabilir,
    yani beklemeyi cagri yerine degil gonderim yerine bagli olmali.
    """
    g = _estop_yordami()
    m = re.search(r"Sleep\s*\(\s*(\d+)", g, re.IGNORECASE)
    assert m, "E-stop yordaminda bekleme YOK — bobin STOP'u yolda kesilir"
    assert int(m.group(1)) >= 1500, (
        f"bekleme cok kisa ({m.group(1)} ms) — backend'in STM flush deadline'i 1,5 sn (NSIS ikizi 1800 ms bekliyor)"
    )


def test_KRITIK_port_DOGRULANIR_karsit_kanit():
    """⚠️ `backend.port` KULLANICI-YAZILABİLİR bir dizindedir (%LOCALAPPDATA%).

    Ham içerik doğrudan bir PowerShell komut dizesine gömülürse (a) içine tırnak/`;` sokan biri
    keyfi komut çalıştırabilir, (b) satır sonu (CR/LF) URL'yi bozar → E-stop SESSİZCE başarısız
    olur ama taskkill YİNE çalışır. NSIS ikizi bu yüzden `IntOp` ile sayıya çevirip 1-65535
    aralığını denetliyor; Pascal tarafında da aynı denetim olmalı.
    """
    k = _iss_kaynak()
    assert re.search(r"StrToIntDef|StrToInt", k), (
        "port SAYIYA cevrilmeden kullaniliyor — ham dosya icerigi komut dizesine gomulur "
        "(komut enjeksiyonu + CR/LF ile sessiz basarisizlik)"
    )
    assert re.search(r"65535", k), "port araligi (1-65535) denetlenmiyor"


def test_KALDIRMA_yolunda_da_ESTOP_var_karsit_kanit():
    """Kaldırma yolu da aynı değişmeze tabi: orada da backend öldürülüyor."""
    k = _iss_kaynak()
    kaldirma = k[k.find("CurUninstallStepChanged") :] if "CurUninstallStepChanged" in k else ""
    if not kaldirma or "taskkill" not in kaldirma:
        pytest.skip(".iss kaldirma yolunda taskkill yok — kapsam disi")
    assert "emergency_stop" in kaldirma, (
        "kaldirma yolunda backend oldurulurken E-stop YOK — kurulum yolu duzeltilip kaldirma "
        "unutulmus (bu deponun 1 numarali hata deseni)"
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))


# ─────────────────────────────────────────────────────────────────────────────────────────
# DAGITIM MESAJI DOGRU DOSYAYI ISARET ETMELI (denetim 2026-08-23)
# ─────────────────────────────────────────────────────────────────────────────────────────
#
# ⚠️ OLCULEN ARIZA: `build_installer.ps1` derleme sonunda operatore "Kurulum dosyasi: X" diyordu
# ve X'i `Get-ChildItem Output -Filter *.exe | Select-Object -First 1` ile seciyordu. Dosyalar
# ALFABETIK geldigi icin bu, Output/ icindeki EN ESKI kurulumdur. 1.9.20 derlendikten sonra betik
# gercekten "PEMFBackendSetup_device_v1.9.14.exe" yazdi.
#
# Bu bir kozmetik mesaj hatasi DEGIL: mesaji izleyen operator klinige, o gun eklenen bobin
# E-stop duzeltmesinden ONCEKI bir kurulumu gonderirdi. Yani bu dosyadaki P0 duzeltmesi
# dagitim adiminda sessizce KAYBOLABILIRDI.


def test_KRITIK_dagitim_mesaji_BU_KOSUDA_uretileni_gosterir():
    ps1 = (Path(__file__).resolve().parent.parent / "build_tools" / "build_installer.ps1").read_text(
        encoding="utf-8", errors="replace"
    )
    # Secim SURUME bagli olmali; klasordeki ilk dosyaya DEGIL.
    assert not re.search(r'Get-ChildItem\s+\$InnoOutputDir\s+-Filter\s+"\*\.exe"', ps1), (
        "kurulum dosyasi Output/ icindeki ILK .exe ile seciliyor (alfabetik) — operatore ESKI "
        "bir kurulumu dagitmasi soylenir; o kurulumda bobin E-stop duzeltmesi OLMAYABILIR"
    )
    assert "$BeklenenAd" in ps1 and "$AppVersion" in ps1, "beklenen dosya adi surumden turetilmiyor"
    # Uretilmediyse SESSIZ gecmemeli.
    assert re.search(r"if\s*\(-not\s+\$SetupExe\)\s*\{[^}]*Write-Fail", ps1, re.S), (
        "beklenen kurulum dosyasi yoksa betik SESSIZCE geciyor — 'basarili' gorunup dosya uretilmemis olabilir"
    )
