# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-15: kaldırma kancası YETİM yardımcı süreçleri de öldürmeli.

SAHA SENARYOSU (sahip bildirimi): "kullanıcı aynı makinede kurup silip tekrar kurabilir,
hata vermemeli." Kaldırmanın İKİ yolu var ve YALNIZ BİRİ launcher'dan geçer:

  A) Uygulama içi "Kaldır" düğmesi → main.rs `uninstall()` → `stop_backend_for_teardown()`
     → `backend::kill_stray_backends()` (PEMF_Backend + mosquitto + cloudflared) → uninstall.exe
  B) Windows Ayarlar ▸ Uygulamalar ▸ Kaldır → uninstall.exe DOĞRUDAN. Launcher HİÇ çalışmaz;
     tek temizlik `hooks.nsi`'deki NSIS_HOOK_PREUNINSTALL kancasıdır.

B yolunda kanca yalnız `PEMF_Backend.exe /T` öldürüyordu. `/T` süreç-AĞACINI öldürür → backend
HÂLÂ AYAKTAYSA çocukları da gider. Ama backend daha önce çöktüyse/zorla kapatıldıysa (launcher'ın
`child.kill()`i = TerminateProcess ÇOCUK-AĞACINI öldürmez, bkz. backend.rs:589) mosquitto YETİM
kalır: ebeveyn PID'i ölüdür, hiçbir ağaçta değildir, `/T` onu BULAMAZ. Üç sonucu:
  1) `runtime\\...\\mosquitto.exe` dosya-kilitli → `RMDir /r "$INSTDIR\\runtime"` SESSİZCE başarısız
     (NSIS RMDir hata döndürmez) → kurulum kökü artıkla kalır,
  2) yeniden kurulumda base re-extract kilitli dosyaya çarpar → "os error 32",
  3) yetim broker 1883'ü TUTAR → yeni backend broker'ını bağlayamaz → MQTT ölü → ESP bobinleri
     6-8 ULAŞILAMAZ (STM 1-5 seri porttan çalışır → arıza "yarı çalışan cihaz" gibi görünür).

Bu test A ve B yollarının AYNI süreç listesini temizlediğini zorlar; ikisi bir daha ayrışamaz.
Gerçek depo dosyalarını okur — üretim mantığını KOPYALAMAZ.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
if str(_KOK / "tests") not in sys.path:
    sys.path.insert(0, str(_KOK / "tests"))
import i18n_yardimci as _iy  # noqa: E402  — I18N: hooks iletileri LangString; görünen TR metin katalogdan (ölçüt aynı)

_HOOKS = _KOK / "launcher" / "app" / "windows" / "hooks.nsi"
_BACKEND_RS = _KOK / "launcher" / "core" / "src" / "backend.rs"


def _makensis() -> str | None:
    """NSIS derleyicisini bul (Tauri kendi kopyasını `%LOCALAPPDATA%\\tauri\\NSIS`'e indirir).

    ⚠️ LN L5 (KÖR KAPI): yalıtılmış koşucular sahte LOCALAPPDATA kullanır → bu derleme testi orada sessizce ATLANIYORDU (makro
    gövdelerini derleyen TEK kapı budur). Komşu `test_i18n_launcher_altyapi.py` gibi `PEMF_MAKENSIS` önce okunur."""
    if sys.platform != "win32":
        return None
    yerel = os.environ.get("LOCALAPPDATA")
    adaylar = [Path(os.environ["PEMF_MAKENSIS"])] if os.environ.get("PEMF_MAKENSIS") else []
    if yerel:
        adaylar += [
            Path(yerel) / "tauri" / "NSIS" / "makensis.exe",
            Path(yerel) / "tauri" / "NSIS" / "Bin" / "makensis.exe",
        ]
    adaylar += [
        Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
        Path(r"C:\Program Files\NSIS\makensis.exe"),
    ]
    for a in adaylar:
        if a.is_file():
            return str(a)
    return shutil.which("makensis")


def _yorumsuz(satir: str) -> str:
    """NSIS satır-yorumunu (`;` VE `#`) at. Tırnak (`'` `"` `` ` ``) içindeki işaretler korunur.

    ⚠️ D1.47 (B-10.133): eskiden yalnız `;` (ve yalnız `'` tırnağı) tanınıyordu — NSIS `#`'i de satır yorumu
    sayar; `# nsExec::Exec … taskkill …` biçiminde yoruma alınmış bir kill satırı KOD sayılıp kapı YEŞİL kalıyordu."""
    tirnak = None
    for i, ch in enumerate(satir):
        if tirnak:
            if ch == tirnak:
                tirnak = None
            continue
        if ch in "'\"`":
            tirnak = ch
        elif ch in ";#":
            return satir[:i]
    return satir


@pytest.fixture(scope="module")
def hooks_metni() -> str:
    assert _HOOKS.is_file(), f"kanca dosyası yok: {_HOOKS}"
    return _HOOKS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def preuninstall_satirlari(hooks_metni: str) -> list[str]:
    """NSIS_HOOK_PREUNINSTALL makro gövdesi, yorumlar ayıklanmış."""
    m = re.search(
        r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend",
        hooks_metni,
        re.DOTALL,
    )
    assert m, "NSIS_HOOK_PREUNINSTALL makrosu bulunamadı"
    return [_yorumsuz(s) for s in m.group(1).splitlines()]


_KOKTEN_AD = re.compile(r'SetEnvironmentVariable\(t\s+"PEMF_KALDIRMA_AD",\s*t\s+"([^"]+\.exe)"\)', re.IGNORECASE)


def _kokten_oldurme_satiri_mi(s: str) -> bool:
    """LN L5 · Y71: kökten öldürme satırı — Win32_Process (32-bit kaldırıcıda yol okunabilen tek yol) + ad + KÖK süzgeci + Stop-Process."""
    return (
        "Win32_Process" in s
        and "$$_.Name -eq $$env:PEMF_KALDIRMA_AD" in s
        and "$$_.ExecutablePath.StartsWith($$k" in s
        and "$$env:PEMF_KALDIRMA_KOKU" in s
        and "Stop-Process" in s
    )


def _taskkill_hedefleri(satirlar: list[str]) -> list[str]:
    """Sırayla öldürme hedefleri (küçük harf): `taskkill /IM <ad>` ve LN L5'in KÖKTEN öldürmesi (ad ortam değişkeniyle verilir, ardından
    gelen PowerShell satırı yalnız `$INSTDIR` altındaki o adlı süreci durdurur — ad ancak o satır VARSA hedef sayılır)."""
    hedefler = []
    bekleyen = None
    for s in satirlar:
        for m in re.finditer(r"/IM\s+(\S+?\.exe)", s, re.IGNORECASE):
            hedefler.append(m.group(1).lower())
        m = _KOKTEN_AD.search(s)
        if m:
            bekleyen = m.group(1).lower()
        elif bekleyen and _kokten_oldurme_satiri_mi(s):
            hedefler.append(bekleyen)
            bekleyen = None
    return hedefler


def _rust_artakalan_listesi(metin: str) -> list[tuple[str, bool]]:
    """`kill_stray_backends()`'in Windows kolundaki liste — TEK KAYNAK `backend::ARTAKALAN_SURECLER` [(imaj, ağaçla mı)].

    LN L3 · Y82: liste adlandırılmış sabite taşındı (backend AĞAÇSIZ — yakıcı `STM32_Programmer_CLI` çocuğu ölmesin); eskiden
    `kill_stray_backends` gövdesindeki `for image in [...]` dizisiydi ve hepsi `/T` ile öldürülüyordu."""
    govde = re.search(r"pub fn kill_stray_backends\([^)]*\)(.*?)\n\}", metin, re.DOTALL)
    assert govde, "kill_stray_backends() bulunamadı (backend.rs yeniden mi adlandırıldı?)"
    assert re.search(r"for \(image, agac\) in ARTAKALAN_SURECLER\b", govde.group(1)), (
        "kill_stray_backends() listeyi `ARTAKALAN_SURECLER`den okumuyor — iki kaldırma yolunun tek kaynağı kayboldu"
    )
    dizi = re.search(r"pub const ARTAKALAN_SURECLER: \[\(&str, bool\); \d+\] =\s*\[(.*?)\];", metin, re.DOTALL)
    assert dizi, "ARTAKALAN_SURECLER sabiti ayrıştırılamadı"
    cift = re.findall(r'\(\s*"([^"]+\.exe)"\s*,\s*(true|false)\s*\)', dizi.group(1))
    assert cift, "ARTAKALAN_SURECLER boş çıktı"
    return [(a.lower(), b == "true") for a, b in cift]


@pytest.fixture(scope="module")
def rust_surec_adlari() -> list[str]:
    """`kill_stray_backends()` Windows kolundaki imaj listesi — TEK KAYNAK."""
    return [a for a, _ in _rust_artakalan_listesi(_BACKEND_RS.read_text(encoding="utf-8"))]


# ─────────────────────────────────────────────────────────────────────────────
# ASIL REGRESYON: yetim yardımcı süreçler kaldırmada öldürülüyor mu?
# ─────────────────────────────────────────────────────────────────────────────


def test_kanca_yetim_mosquittoyu_oldurur(preuninstall_satirlari):
    """Yetim mosquitto öldürülmezse: runtime kilitli + 1883 dolu → yeniden kurulum bozulur."""
    hedefler = _taskkill_hedefleri(preuninstall_satirlari)
    assert "mosquitto.exe" in hedefler, (
        "PREUNINSTALL mosquitto.exe'yi öldürmüyor. Backend önceden çökmüşse mosquitto YETİMDİR "
        "ve `/IM PEMF_Backend.exe /T` onu bulamaz → runtime dosya-kilitli kalır, 1883 dolu kalır, "
        "yeniden kurulumda 'os error 32' + ESP bobinleri 6-8 ulaşılamaz."
    )


def test_kanca_yetim_cloudflaredi_oldurur(preuninstall_satirlari):
    """cloudflared de runtime/ altındaki kendi ikilisini kilitler (aynı yetim mekanizması)."""
    hedefler = _taskkill_hedefleri(preuninstall_satirlari)
    assert "cloudflared.exe" in hedefler, (
        "PREUNINSTALL cloudflared.exe'yi öldürmüyor → runtime\\cloudflared.exe kilitli kalır."
    )


def test_backend_mosquittodan_ONCE_oldurulur(preuninstall_satirlari):
    """SIRA hasta-etkili: MosquittoSupervisor broker'ı ölü görürse YENİDEN BAŞLATIR.

    `apps/backend/services/headless_services.py::_monitor_loop` `ensure_running` iken broker'ı diriltir.
    Önce mosquitto öldürülürse supervisor (hâlâ yaşayan backend içinde) onu geri getirir ve
    kilit/port sorunu AYNEN kalır — kanca "başarılı" görünür. Backend ÖNCE ölmeli.
    """
    hedefler = _taskkill_hedefleri(preuninstall_satirlari)
    assert "pemf_backend.exe" in hedefler, "PREUNINSTALL backend'i hiç öldürmüyor"
    assert hedefler.index("pemf_backend.exe") < hedefler.index("mosquitto.exe"), (
        f"Öldürme sırası YANLIŞ: {hedefler}. Backend mosquitto'dan ÖNCE gelmeli, aksi halde "
        "MosquittoSupervisor broker'ı yeniden başlatır ve temizlik hiçbir işe yaramaz."
    )


def test_iki_kaldirma_yolu_ayni_surecleri_temizler(preuninstall_satirlari, rust_surec_adlari):
    """A yolu (launcher düğmesi) ile B yolu (Ayarlar ▸ Uygulamalar) AYNI listeyi temizlemeli.

    Bu testin asıl değeri: birine yeni bir yardımcı süreç eklenip diğerinin unutulmasını
    engeller. Regresyon tam olarak böyle doğmuştu.
    """
    kanca = set(_taskkill_hedefleri(preuninstall_satirlari))
    rust = set(rust_surec_adlari)
    eksik = rust - kanca
    assert not eksik, (
        f"`kill_stray_backends()` şunları öldürüyor ama NSIS kancası ÖLDÜRMÜYOR: {sorted(eksik)}. "
        "Kullanıcı Ayarlar ▸ Uygulamalar'dan kaldırdığında launcher hiç çalışmaz → bu süreçler "
        "hayatta kalır. İki liste birebir aynı tutulmalı."
    )


def _yakici_korunur_ihlalleri(backend_rs: str, hooks_metni: str) -> list[str]:
    """LN L3 · Y82 (sahip): oto-firmware yakıcısı (`STM32_Programmer_CLI`, backend'in ÇOCUĞU) hiçbir kapanış yolunda öldürülmez —
    backend AĞAÇSIZ (`/T` yok), yakıcı hiçbir öldürme listesinde yok. İki yol: launcher `ARTAKALAN_SURECLER` + NSIS PREUNINSTALL."""
    sorun = []
    rust = dict(_rust_artakalan_listesi(backend_rs))
    if rust.get("pemf_backend.exe") is not False:
        sorun.append(f"launcher: PEMF_Backend.exe AĞAÇLA öldürülüyor ({rust}) — yakıcı çocuk süreç ölür")
    if any("stm32_programmer" in a for a in rust):
        sorun.append("launcher: STM32_Programmer_CLI öldürme listesinde")
    for s in _pre(hooks_metni):
        if re.search(r"/IM\s+PEMF_Backend\.exe", s, re.I) and re.search(r"(?<![\w/])/T\b", s):
            sorun.append(f"NSIS: backend AĞAÇLA öldürülüyor: {s.strip()}")
        if re.search(r"stm32_programmer", s, re.I) and "taskkill" in s.lower():
            sorun.append(f"NSIS: yakıcı öldürülüyor: {s.strip()}")
    return sorun


def _pre(hooks_metni: str) -> list[str]:
    m = re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b(.*?)!macroend", hooks_metni, re.DOTALL)
    assert m, "NSIS_HOOK_PREUNINSTALL makrosu bulunamadı"
    return [_yorumsuz(s) for s in m.group(1).splitlines()]


def test_KRITIK_L3_yakici_hicbir_kapanis_yolunda_OLDURULMEZ_backend_AGACSIZ():
    sorun = _yakici_korunur_ihlalleri(_BACKEND_RS.read_text(encoding="utf-8"), _HOOKS.read_text(encoding="utf-8"))
    assert not sorun, "\n".join(sorun)


@pytest.mark.parametrize(
    "ad,hedef,eski,yeni",
    [
        ("rust_agacla", "rs", '[("PEMF_Backend.exe", false),', '[("PEMF_Backend.exe", true),'),
        (
            "rust_yakici_listede",
            "rs",
            '("cloudflared.exe", true)]',
            '("cloudflared.exe", true), ("STM32_Programmer_CLI.exe", true)]',
        ),
        ("nsis_agacla", "nsi", "'taskkill /F /IM PEMF_Backend.exe'", "'taskkill /F /IM PEMF_Backend.exe /T'"),
    ],
)
def test_KRITIK_L3_yakici_kapisi_mutantta_KIRMIZI(ad, hedef, eski, yeni):
    rs = _BACKEND_RS.read_text(encoding="utf-8").replace("\r\n", "\n")
    nsi = _HOOKS.read_text(encoding="utf-8").replace("\r\n", "\n")
    kaynak = rs if hedef == "rs" else nsi
    assert kaynak.count(eski) == 1, f"{ad}: mutant çapası {kaynak.count(eski)} kez"
    if hedef == "rs":
        rs = rs.replace(eski, yeni)
    else:
        nsi = nsi.replace(eski, yeni)
    assert _yakici_korunur_ihlalleri(rs, nsi), f"{ad}: kapı mutantı GÖRMEDİ"


def _kendi_broker_ihlalleri(backend_rs: str, hooks_metni: str) -> list[str]:
    """LN L5 · Y71 (sahip): kapanışta / kaldırmada yalnız KENDİ mosquitto'muz (ikilisi kurulum kökü altında) öldürülür — sahadaki eski
    kurulumun mosquitto SERVİSİ ve yabancı broker'lar ADLA öldürülmez. İki yol: launcher `kill_stray_backends(kok)` + NSIS PREUNINSTALL."""
    sorun = []
    rs = backend_rs.replace("\r\n", "\n")
    sabit = re.search(r"pub const YALNIZ_KOKTEN_OLDURULEN: \[&str; \d+\] = \[(.*?)\];", rs)
    if not sabit or '"mosquitto.exe"' not in sabit.group(1):
        sorun.append("launcher: mosquitto.exe `YALNIZ_KOKTEN_OLDURULEN`de değil (adla öldürülür)")
    govde = re.search(r"pub fn kill_stray_backends\(kok: &Path\)(.*?)\n\}", rs, re.DOTALL)
    if not govde:
        sorun.append("launcher: `kill_stray_backends(kok: &Path)` yok — kök bilinmeden 'kendi' süreç ayırt edilemez")
    else:
        g = govde.group(1)
        if not re.search(
            r"if YALNIZ_KOKTEN_OLDURULEN\.contains\(&image\) \{\s*for pid in kok_altindaki_pidler\(&surec_yollari\(image\), kok\)",
            g,
        ):
            sorun.append("launcher: kökten öldürme dalı yok / süzgeçsiz")
        if not re.search(r"kok_altindaki_pidler\(&surec_yollari\(image\), kok\)[^}]*?\"/PID\"", g, re.DOTALL):
            sorun.append("launcher: kökten seçilen süreç PID ile öldürülmüyor")
    pre = _pre(hooks_metni)
    for s in pre:
        if re.search(r"/IM\s+mosquitto\.exe", s, re.I):
            sorun.append(f"NSIS: mosquitto ADLA öldürülüyor: {s.strip()}")
    if "mosquitto.exe" not in _taskkill_hedefleri(pre):
        sorun.append(
            "NSIS: kendi mosquitto'muz hiç öldürülmüyor (kökten öldürme satırı yok / süzgeçsiz) — dosya kilidi kalır"
        )
    if not any(re.search(r'SetEnvironmentVariable\(t\s+"PEMF_KALDIRMA_KOKU",\s*t\s+"\$INSTDIR"\)', s) for s in pre):
        sorun.append("NSIS: kök ($INSTDIR) PowerShell'e verilmiyor")
    return sorun


def test_KRITIK_L5_yalniz_KENDI_mosquitto_oldurulur_eski_SERVIS_e_dokunulmaz():
    sorun = _kendi_broker_ihlalleri(_BACKEND_RS.read_text(encoding="utf-8"), _HOOKS.read_text(encoding="utf-8"))
    assert not sorun, "\n".join(sorun)


@pytest.mark.parametrize(
    "ad,hedef,eski,yeni",
    [
        (
            "rust_adla",
            "rs",
            'pub const YALNIZ_KOKTEN_OLDURULEN: [&str; 1] = ["mosquitto.exe"];',
            'pub const YALNIZ_KOKTEN_OLDURULEN: [&str; 1] = ["yok.exe"];',
        ),
        (
            "rust_suzgecsiz",
            "rs",
            "for pid in kok_altindaki_pidler(&surec_yollari(image), kok) {",
            "for pid in surec_yollari(image).iter().map(|(p, _)| *p) {",
        ),
        (
            "nsis_adla",
            "nsi",
            "  Pop $0\n  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM cloudflared.exe /T'",
            "  Pop $0\n  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM mosquitto.exe /T'\n  Pop $0\n  nsExec::Exec /TIMEOUT=30000 'taskkill /F /IM cloudflared.exe /T'",
        ),
        (
            "nsis_suzgecsiz",
            "nsi",
            " -and $$_.ExecutablePath.StartsWith($$k, [StringComparison]::OrdinalIgnoreCase)",
            "",
        ),
        ("nsis_koksuz", "nsi", 't "PEMF_KALDIRMA_KOKU", t "$INSTDIR"', 't "PEMF_KALDIRMA_KOKU", t "C:\\"'),
    ],
)
def test_KRITIK_L5_kendi_broker_kapisi_mutantta_KIRMIZI(ad, hedef, eski, yeni):
    rs = _BACKEND_RS.read_text(encoding="utf-8").replace("\r\n", "\n")
    nsi = _HOOKS.read_text(encoding="utf-8").replace("\r\n", "\n")
    kaynak = rs if hedef == "rs" else nsi
    assert kaynak.count(eski) == 1, f"{ad}: mutant çapası {kaynak.count(eski)} kez"
    if hedef == "rs":
        rs = rs.replace(eski, yeni)
    else:
        nsi = nsi.replace(eski, yeni)
    assert _kendi_broker_ihlalleri(rs, nsi), f"{ad}: kapı mutantı GÖRMEDİ"


def _ps_kok_oldurme_komutu(hooks_metni: str) -> str:
    """hooks.nsi'deki kökten öldürme satırının PowerShell `-Command` metni (NSIS `$$` → `$` çözülmüş) — üretim satırının KENDİSİ."""
    for s in _pre(hooks_metni):
        if _kokten_oldurme_satiri_mi(s):
            m = re.search(r"-Command \"(.*)\"'\s*$", s.rstrip())
            assert m, f"-Command metni ayrıştırılamadı: {s.strip()[:120]}"
            assert "$INSTDIR" not in m.group(1) and "$(" not in m.group(1), "komutta NSIS değişkeni / LangString kaldı"
            return m.group(1).replace("$$", "$")
    raise AssertionError("kökten öldürme satırı yok")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows süreç / WMI sondası")
def test_KRITIK_L5_nsis_satiri_GERCEKTE_yalniz_KOKTEKI_sureci_durdurur(tmp_path):
    """Sonda: aynı adlı iki süreç (kopya cmd.exe, `pause` ile bekler) — biri `$INSTDIR` benzeri kökte, biri kardeş dizinde (sahadaki
    servisin yerini tutar). hooks.nsi'deki satır kaldırıcının bağlamı gibi 32-bit PowerShell'le (SysWOW64 varsa) koşturulur: yalnız
    kökteki ölür. Yalnız bu testin başlattığı sondalar hedeflenir (ad sürece özgü); gerçek mosquitto / backend'e dokunulmaz."""
    komut = _ps_kok_oldurme_komutu(_HOOKS.read_text(encoding="utf-8"))
    sistem = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    ps = sistem / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not ps.is_file():
        ps = sistem / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ad = f"pemf_l5_ps_sonda_{os.getpid()}.exe"
    taban = tmp_path.resolve()  # uzun yol — WMI ExecutablePath uzun yol döner (8.3 kısa adlı TEMP'te de tutsun)
    kok = taban / "PEMF Vet Client"
    kardes = taban / "PEMF Vet Client2"
    sondalar = []
    try:
        # [0] kökte hedef ad · [1] kardeş dizinde aynı ad · [2] kökte BAŞKA ad (kökteki her süreç değil, yalnız o ad)
        for d, a in (
            (kok / "runtime" / "bin", ad),
            (kardes / "bin", ad),
            (kok / "runtime" / "baska", f"pemf_l5_ps_baska_{os.getpid()}.exe"),
        ):
            d.mkdir(parents=True)
            shutil.copy(sistem / "System32" / "cmd.exe", d / a)
            sondalar.append(
                subprocess.Popen(
                    [str(d / a), "/d", "/c", "pause"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        time.sleep(0.5)
        ortam = {**os.environ, "PEMF_KALDIRMA_KOKU": str(kok), "PEMF_KALDIRMA_AD": ad}
        r = subprocess.run(
            [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", komut],
            env=ortam,
            capture_output=True,
            text=True,
            timeout=120,
        )
        time.sleep(0.5)
        assert sondalar[0].poll() is not None, (
            f"kökteki süreç DURDURULMADI (rc={r.returncode} {r.stderr[-400:]!r}) — dosya kilidi kalır"
        )
        assert sondalar[1].poll() is None, (
            "kök DIŞINDAKİ aynı adlı süreç durduruldu — sahadaki eski mosquitto servisi de ölürdü"
        )
        assert sondalar[2].poll() is None, "kökteki BAŞKA adlı süreç durduruldu — ad süzgeci yok"
    finally:
        for p in sondalar:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)


# ─────────────────────────────────────────────────────────────────────────────
# NSIS'e ÖZGÜ DEĞİŞMEZLER — burada bir hata sessizdir, bu yüzden test edilir.
# ─────────────────────────────────────────────────────────────────────────────


def _nsexec_itme_sayisi(satir: str) -> int:
    """Bir satırdaki nsExec çağrısının yığına ittiği öğe sayısı (0 = nsExec çağrısı değil).

    `nsExec::Exec` / `ExecToLog` → 1 (dönüş kodu); `nsExec::ExecToStack` → 2 (dönüş kodu + çıktı).
    Denetim 2026-09-06: E-stop çağrısı ExecToStack'e geçti — çıktı da yığındadır, İKİ Pop ister.
    """
    if "nsExec::ExecToStack" in satir:
        return 2
    if "nsExec::Exec" in satir:
        return 1
    return 0


def test_her_nsexec_cagrisinin_donus_kodu_atilir(preuninstall_satirlari):
    """Yığın dengesi: `nsExec::Exec` dönüş kodunu yığına İTER; Pop edilmezse kayıt sızar.

    Dosyanın kendi yorumları bunu belgeliyor: atlanan bir Pop, sonraki `Pop $2/$1/$0`'ların
    ORİJİNAL kayıtlar yerine bu dönüşü yüklemesine yol açar → kaldırıcı kayıtları bozuk
    değerlerle sürdürür. Derleyici bunu YAKALAMAZ. `ExecToStack` İKİ öğe iter → iki ardışık Pop.
    """
    kod = [s for s in preuninstall_satirlari if s.strip()]
    for i, satir in enumerate(kod):
        itme = _nsexec_itme_sayisi(satir)
        if not itme:
            continue
        for k in range(1, itme + 1):
            sonraki = kod[i + k].strip() if i + k < len(kod) else ""
            assert sonraki.startswith("Pop "), (
                f"nsExec çağrısı yığına {itme} öğe itiyor ama {k}. Pop yok "
                f"(satır: {satir.strip()[:80]!r}, sonraki: {sonraki!r}). "
                "Dönüş/çıktı yığında kalır ve kayıt geri-yüklemesini bozar."
            )


def test_push_pop_dengesi_korunur(preuninstall_satirlari):
    """Makro yığını nötr bırakmalı: Pop = Push + Σ nsExec itmeleri (Exec=1, ExecToStack=2).

    FileOpen/FileWrite/FileClose yığına DOKUNMAZ (tutamaç bir kayıtta tutulur), sayılmaz.
    """
    kod = [s.strip() for s in preuninstall_satirlari]
    push = sum(1 for s in kod if re.match(r"^Push\s+\$", s))
    pop = sum(1 for s in kod if re.match(r"^Pop\s+\$", s))
    exec_ = sum(_nsexec_itme_sayisi(s) for s in kod)
    assert pop == push + exec_, (
        f"Yığın dengesiz: Push={push}, nsExec itmeleri={exec_}, Pop={pop} "
        f"(beklenen Pop={push + exec_}). Kaldırıcı bozuk kayıt değerleriyle devam eder."
    )


def test_kanca_dosyasi_bicimi_korunur():
    """NSIS biçim değişmezleri: BOM YOK + satır sonları KARIŞIK değil.

    Bu dosya `Unicode true` OLMADAN include edilir; başına bir BOM girerse NSIS onu KAYNAK
    METİN olarak ayrıştırır ve derleme kırılır. Windows araçları ve düzenleyiciler sessizce
    BOM ekleme eğilimindedir — bu yüzden değişmez teste bağlanır. (BOM depodaki blob'un bir
    parçasıdır, checkout ayarlarından etkilenmez.)

    ⚠️ Burada bir zamanlar "yalnız-LF" iddiası vardı ve YANLIŞTI: depoda `.gitattributes` yok
    ve `core.autocrlf=true` yaygın (bu makinede de öyle) → git, checkout'ta LF'i CRLF'e çevirir.
    Yani satır sonu depo değişmezi DEĞİL, checkout yapılandırmasının türevidir; iddia CI'da
    (windows-latest) ya da temiz bir klonda sebepsiz kırmızı verirdi. NSIS zaten ikisini de
    kabul eder. Gerçek olan değişmez KARIŞIK satır sonu olmaması — o, dosyanın yarısını bir
    araçla düzenleyip diğer yarısını başka bir araçla düzenlemenin izidir.
    """
    ham = _HOOKS.read_bytes()
    assert not ham.startswith(b"\xef\xbb\xbf"), (
        "hooks.nsi'ye UTF-8 BOM girmiş — NSIS bunu kaynak metin sanar, derleme kırılır."
    )
    crlf = ham.count(b"\r\n")
    lf_toplam = ham.count(b"\n")
    yalin_lf = lf_toplam - crlf
    assert crlf == 0 or yalin_lf == 0, (
        f"hooks.nsi'de KARIŞIK satır sonu var (CRLF={crlf}, yalın LF={yalin_lf}). "
        "Dosya tek bir kuralla yazılmalı; karışım düzenleme araçlarının çakıştığını gösterir."
    )


@pytest.mark.skipif(_makensis() is None, reason="makensis yok (Windows + Tauri/NSIS gerekir)")
def test_kanca_gercekten_nsis_ile_derlenir(tmp_path):
    """Yapısal denetim yetmez: kanca GERÇEKTEN derlenmeli.

    Yukarıdaki testler metin ayrıştırır — sözdizimi hatası, kapanmamış `${If}`, bilinmeyen
    komut gibi şeyleri GÖREMEZ. Bozuk bir kanca ancak client paketlenirken patlar (uzun bir
    Rust+npm build'inin en sonunda) ya da daha kötüsü, kaldırma sırasında sahada.
    Tauri şablonunun bağlamını taklit edip `makensis` ile gerçekten derliyoruz.
    """
    nsi = tmp_path / "derleme_testi.nsi"
    hooks = str(_HOOKS).replace("\\", "\\\\")
    nsi.write_text(
        f"Unicode true\nOutFile \"{str(tmp_path / 'cikti.exe')}\"\n".replace("\\", "\\\\")
        + 'Name "hooks derleme testi"\n'
        "RequestExecutionLevel user\n"
        '!include "LogicLib.nsh"\n'
        # Tauri installer.nsi'nin tanımladığı globaller — hooks.nsi bunlara güvenir.
        "Var UpdateMode\n"
        "Var DeleteAppDataCheckboxState\n"
        f'!include "{hooks}"\n'
        "Section\nSectionEnd\n"
        # Kancalar KALDIRICI bağlamında çalışır; ikisini de orada genişlet.
        "Section \"Uninstall\"\n"
        "  !insertmacro NSIS_HOOK_PREUNINSTALL\n"
        "  !insertmacro NSIS_HOOK_POSTUNINSTALL\n"
        "SectionEnd\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [_makensis(), "/V2", str(nsi)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    assert r.returncode == 0, f"hooks.nsi DERLENMİYOR (makensis çıkış {r.returncode}):\n{r.stdout}\n{r.stderr}"
    # Gözden geçirme 2026-09-06: derleme "yeşil" ama UYARILI olabilir ve uyarı DAVRANIŞI değiştirir.
    # makensis, `'...'` dizgesindeki PowerShell `$(...)` alt-ifadelerini LangString sanır (6040) ve
    # çalışma zamanında BOŞ dizgeye çözer → kaldırıcı fiilen "OK status= confirmed= t=" / "FAIL="
    # gönderir: E-stop günlüğü/uyarısı teşhis değerini yitirir. Bilinmeyen `$x` (6000) da aynı
    # kökten gelir. hooks.nsi'de PowerShell'in her `$`'ı `$$` ile kaçırılmalı (yalnız port `$2` kalır).
    uyarilar = [s for s in (r.stdout + r.stderr).splitlines() if "6040" in s or "6000" in s]
    assert not uyarilar, (
        "makensis hooks.nsi'yi UYARIYLA derledi — `$(...)` LangString / bilinmeyen `$x` olarak yutuluyor; "
        "derlenmiş kaldırıcı PowerShell'e EKSİK komut gönderir. hooks.nsi'deki PowerShell `$` işaretlerini "
        "`$$` yap:\n" + "\n".join(uyarilar)
    )


def test_estop_taskkillden_once_gonderilir(preuninstall_satirlari):
    """🔴 KIRMIZI ÇİZGİ (TIBBİ GÜVENLİK): E-stop HER ZAMAN kill'den önce.

    `taskkill /F` sinyalsizdir → backend'in graceful bobin-STOP'u ÇALIŞMAZ. ESP bobinleri 6-8'in
    firmware link-watchdog'u YOKTUR; tek durdurma yolu broker'a ulaşan STOP publish'idir. Yeni
    bir kill satırı E-stop'un ÜSTÜNE eklenirse bobinler hastanın üzerinde enerjili kalır.
    """
    kod = [s.strip() for s in preuninstall_satirlari]
    estop = next((i for i, s in enumerate(kod) if "emergency_stop" in s), None)
    assert estop is not None, "E-stop POST'u kaybolmuş — hasta güvenliği değişmezi"
    ilk_kill = next((i for i, s in enumerate(kod) if "taskkill" in s), None)
    assert ilk_kill is not None, "taskkill satırı yok"
    assert estop < ilk_kill, (
        f"E-stop (satır {estop}) İLK taskkill'den (satır {ilk_kill}) SONRA geliyor. "
        "Bobinler enerjili öldürülür — ESP bobinleri 6-8'in watchdog'u YOKTUR."
    )


# ─────────────────────────────────────────────────────────────────────────────
# DENETİM 2026-09-06: E-stop SONUCU OKUNMALI, GÜNLÜKLENMELİ, RAPORLANMALI.
#
# Bulgu (iki bağımsız gözden geçirici): E-stop `nsExec::Exec` + `Pop $0` (dönüş ATILIYOR) +
# PowerShell `| Out-Null ... catch {}` ile gönderiliyordu. powershell engelli ("error"), 20 sn
# aşımı ("timeout"), bayat port (bağlantı reddi), backend >10 sn asılı, backend "confirmed=false"
# döndü — HEPSİ başarılı E-stop ile birebir aynı görünüyordu; kaldırıcı "gönderiliyor…" basıp
# taskkill /F'e geçiyordu ve hiçbir yere iz yazmıyordu. Launcher çökmüş + backend yetimken bu,
# sert kill'den önceki TEK bobin-durdurma noktasıdır.
# ─────────────────────────────────────────────────────────────────────────────

_ESTOP_GUNLUK = "uninstall_estop.log"


def _estop_satiri(kod: list[str]) -> tuple[int, str]:
    i = next((i for i, s in enumerate(kod) if "emergency_stop" in s and "nsExec::" in s), None)
    assert i is not None, "E-stop nsExec çağrısı bulunamadı — hasta güvenliği değişmezi"
    return i, kod[i]


def test_estop_sonucu_yigindan_okunur_ve_gunluklenir(preuninstall_satirlari):
    """Yapısal kapı: E-stop çağrısı ExecToStack + iki Pop + kill'den ÖNCE kalıcı günlük satırı.

    `nsExec::Exec` dönüş kodunu atmak = her başarısızlığı başarı gibi göstermek. Çıktı da
    alınmalı (`confirmed=false` yalnız gövdede görünür). Günlük GERÇEK veri kökünün (`$PEMF_VeriKoku`
    — PREUNINSTALL başında çözülür) `logs` dizinine: KVKK gereği client-kaldırmanın ASLA silmediği
    kök → iz kaldırmadan sonra da okunabilir.

    ⚠️ LN L7 · D2.67 / D2.77: burası eskiden `%APPDATA%\\PEMF_GUI` + `SetShellVarContext current … all`
    dansını ŞART koşuyordu — yanlış öncül: Tauri `un.onInit` currentUser'da `current` kurar, `all`'a
    dönmek şablonun kısayol silmesini tüm-kullanıcılar dizinine yönlendiriyor ve makine-geneli kökteki
    kurulumda iz yanlış klasöre gidiyordu. Artık mutlak gerçek kök + PREUNINSTALL'da `all` YOK.
    """
    kod = [s.strip() for s in preuninstall_satirlari]
    estop, satir = _estop_satiri(kod)
    assert "nsExec::ExecToStack" in satir, (
        "E-stop `nsExec::Exec` ile gönderiliyor → dönüş kodu ve yanıt gövdesi ATILIR; powershell "
        "engelli/zaman aşımı/bağlantı reddi/confirmed=false hepsi BAŞARI gibi görünür. "
        "`nsExec::ExecToStack` kullan, dönüşü ve çıktıyı Pop'la, günlükle ve raporla."
    )
    assert "Out-Null" not in satir and "catch {}" not in satir, (
        "PowerShell tek-satırı hâlâ sonucu yutuyor (`Out-Null` / boş `catch {}`) — yanıt "
        "`confirmed` alanını ve istisna mesajını RAPORLAMALI (exit 0/1/2)."
    )
    # Gözden geçirme 2026-09-06: kaçırılmamış `$(` NSIS'te LangString'dir → derlenmiş kaldırıcıda BOŞ.
    ciplak = re.findall(r"(?<!\$)\$\([^)]*\)", satir)
    assert not ciplak, (
        f"E-stop satırında kaçırılmamış PowerShell alt-ifadesi var: {ciplak} — makensis bunları LangString "
        "sanıp boş dizgeye çözer, günlük 'OK status= confirmed= t=' olur. `$$(...)` yaz "
        "(test_kanca_gercekten_nsis_ile_derlenir uyarı kapısı da bunu ölçer)."
    )
    ilk_kill = next(i for i, s in enumerate(kod) if "taskkill" in s)
    ara = kod[estop + 1 : ilk_kill]
    gunluk = [s for s in ara if s.startswith("FileWrite") or (s.startswith("FileOpen") and _ESTOP_GUNLUK in s)]
    assert any(s.startswith("FileOpen") for s in gunluk) and any(s.startswith("FileWrite") for s in gunluk), (
        f"E-stop ile taskkill arasında `{_ESTOP_GUNLUK}` günlük yazımı (FileOpen+FileWrite) YOK. "
        "Kaldırıcı log yazmaz; E-stop sonucu kaldırmadan sonra hiçbir yerden okunamaz."
    )
    acilis = next(i for i, s in enumerate(ara) if s.startswith("FileOpen") and _ESTOP_GUNLUK in s)
    assert "$PEMF_VeriKoku\\logs\\" in ara[acilis], (
        f"Günlük GERÇEK veri kökü ($PEMF_VeriKoku) altında değil: {ara[acilis]!r} — makine-geneli kökte iz yanlış klasöre gider."
    )
    assert not any(re.match(r"SetShellVarContext\s+all\b", s, re.I) for s in kod), (
        "PREUNINSTALL `SetShellVarContext all` kullanıyor — Tauri'nin bağlamı (currentUser → current) bozulur: kısayollar "
        "silinmez, `$APPDATA` ProgramData'ya çözülür (LN L7 · D2.67 / D2.77)."
    )
    sonrasi = ara[acilis:]
    yazim = next(s for s in sonrasi if s.startswith("FileWrite"))
    assert "$0" in yazim and "$1" in yazim and "$2" in yazim, (
        f"Günlük satırı eksik ({yazim!r}): port ($2), nsExec dönüşü ($0) ve çıktı ($1) hepsi yazılmalı."
    )
    # I18N-0: ileti `$(PEMF_…)` LangString'i — kullanıcının gördüğü TR metin katalogdan (EN boşsa açılmaz → kırmızı).
    assert any(s.startswith("MessageBox") and "ELLE" in _iy.gorunur_satir(s, "launcher") for s in ara), (
        "Doğrulanamayan E-stop etkileşimli kaldırmada kullanıcıya SÖYLENMİYOR — "
        "'bobinleri ELLE kontrol edin' MessageBox'ı (Silent/UpdateMode dışı) eklenmeli."
    )
    assert not any(s.startswith("Abort") or s.startswith("Quit") for s in ara), (
        "E-stop bloğu kaldırmayı DURDURUYOR — kaldırma hiçbir koşulda engellenmez, yalnız uyarır."
    )


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _estop_komutu(preuninstall_satirlari: list[str], port: int) -> str:
    """hooks.nsi'deki GERÇEK -Command metni, NSIS `$2` (port) yerine verilen port."""
    _, satir = _estop_satiri([s.strip() for s in preuninstall_satirlari])
    m = re.search(r'-Command "(.*)"\'\s*$', satir)
    assert m, f"E-stop satırında -Command \"...\" ayrıştırılamadı: {satir[:120]!r}"
    komut = m.group(1)
    # NSIS dizge-kaçışı: `$$` → `$`. PowerShell'in `$r`, `$($r.status)`, `$true` gibi her `$`'ı
    # hooks.nsi'de `$$` yazılmalıdır — aksi halde makensis `$(...)`'ı LangString sanır, boş dizgeye
    # çözer ve DERLENMİŞ kaldırıcı "OK status= confirmed= t=" gönderir (gözden geçirme 2026-09-06,
    # gerçek derlemeyle ölçüldü). Bu test makensis'in GÖRDÜĞÜ metni koşturur, ham metni değil.
    komut = komut.replace("$$", "$")
    assert "$2" in komut, "komutta NSIS port kaydı `$2` yok — port artık nereden geliyor?"
    return komut.replace("$2", str(port))


class _EstopStub:
    """Backend'in bobin durdurma uçları için tek-amaçlı HTTP taklidi (gerçek yanıt şeması: `_emergency_stop_all`).

    2026-10-18: `kapanis_var=False` → eski backend: `/api/hardware/kapanis_durdur` YOK (405); `kapanis_yavas=True` → kapanış
    ucu 2,3 sn sonra 500 (asılı/meşgul backend). İstek gövdeleri `govdeler`de."""

    def __init__(self, confirmed: bool, kapanis_var: bool = True, kapanis_yavas: bool = False):
        self.istekler: list[tuple[str, str]] = []
        self.govdeler: list[tuple[str, str, bytes]] = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                stub.istekler.append(("POST", self.path))
                n = int(self.headers.get("Content-Length") or 0)
                stub.govdeler.append(
                    (self.path, self.headers.get("Content-Type") or "", self.rfile.read(n) if n else b"")
                )
                if not kapanis_var and self.path.endswith("/kapanis_durdur"):
                    self.send_response(405)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if kapanis_yavas and self.path.endswith("/kapanis_durdur"):
                    time.sleep(2.3)
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                govde = json.dumps(
                    {
                        "status": "success" if confirmed else "partial",
                        "confirmed": confirmed,
                        "stmStopped": True,
                        "mqttResults": [],
                        "reason": "manual",
                        "sessionCoilIds": [1, 2],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def do_GET(self):  # noqa: N802
                stub.istekler.append(("GET", self.path))
                self.send_response(405)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def kapat(self):
        self.srv.shutdown()
        self.srv.server_close()


def _kapali_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _komutu_kos(komut: str) -> tuple[int, str]:
    r = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", komut],
        capture_output=True,
        timeout=90,
    )
    # powershell boruya OEM (Türkçe makinede cp857) yazar; nsExec bu yüzden /OEM ile çağırır.
    cikti = (r.stdout + r.stderr).decode("cp857", errors="replace").strip()
    return r.returncode, cikti


@pytest.mark.skipif(_powershell() is None, reason="pwsh/powershell yok")
def test_estop_tek_satiri_confirmed_false_ise_cikis_2(preuninstall_satirlari):
    """DAVRANIŞ: backend 200 döndü ama `confirmed=false` → çıkış 2 + çıktıda confirmed=False.

    Bu durum eskiden `Out-Null` ile yutuluyordu: STM ya da ESP yolu doğrulanamamış olsa da
    kaldırıcı "başarılı" görünürdü. Gerçek uç `{status, confirmed, …}` döndürür (api_server.py
    `_emergency_stop_all`); taklit aynı şemayı kullanır.
    """
    stub = _EstopStub(confirmed=False)
    try:
        rc, cikti = _komutu_kos(_estop_komutu(preuninstall_satirlari, stub.port))
    finally:
        stub.kapat()
    # 2026-10-18: önce kapanış ucu (boşta kapanış "önceki oturumda ACİL DURDUR" mandalı YAZMAZ); yanıt verdiyse ACİL DURDUR çağrılmaz.
    assert stub.istekler == [("POST", "/api/hardware/kapanis_durdur")], (
        f"Beklenen tek POST /api/hardware/kapanis_durdur; gelen: {stub.istekler}"
    )
    assert rc == 2, f"confirmed=false için çıkış 2 beklenir, {rc} geldi (çıktı: {cikti!r})"
    assert cikti.startswith("OK") and "confirmed=False" in cikti, (
        f"Çıktı 'OK … confirmed=False' içermeli, günlük/DetailPrint bunu gösterir: {cikti!r}"
    )


@pytest.mark.skipif(_powershell() is None, reason="pwsh/powershell yok")
def test_estop_tek_satiri_baglanti_yoksa_cikis_1_ve_FAIL(preuninstall_satirlari):
    """DAVRANIŞ: bayat port / backend ölü (bağlantı reddi) → çıkış 1 + çıktı FAIL ile başlar.

    Eskiden boş `catch {}` idi: bağlantı reddi de "gönderildi" gibi görünürdü.
    """
    rc, cikti = _komutu_kos(_estop_komutu(preuninstall_satirlari, _kapali_port()))
    assert rc == 1, f"bağlantı reddi için çıkış 1 beklenir, {rc} geldi (çıktı: {cikti!r})"
    assert cikti.startswith("FAIL"), f"Çıktı FAIL ile başlamalı (istisna mesajı günlüğe gider): {cikti!r}"
    assert len(cikti) > len("FAIL="), "FAIL var ama istisna mesajı yok — günlük neyi teşhis edecek?"


@pytest.mark.skipif(_powershell() is None, reason="pwsh/powershell yok")
def test_estop_tek_satiri_confirmed_true_ise_cikis_0_OK(preuninstall_satirlari):
    """DAVRANIŞ: 200 + confirmed=true → çıkış 0 + 'OK' (MessageBox gösterilmez, günlük OK yazar)."""
    stub = _EstopStub(confirmed=True)
    try:
        rc, cikti = _komutu_kos(_estop_komutu(preuninstall_satirlari, stub.port))
    finally:
        stub.kapat()
    assert stub.istekler == [("POST", "/api/hardware/kapanis_durdur")]
    assert rc == 0, f"confirmed=true için çıkış 0 beklenir, {rc} geldi (çıktı: {cikti!r})"
    assert cikti.startswith("OK uc=1") and "confirmed=True" in cikti, (
        f"Çıktı 'OK uc=1 … confirmed=True' olmalı: {cikti!r}"
    )
    assert "\n" not in cikti, f"Çıktı TEK satır olmalı (günlük satırı bozulur): {cikti!r}"
    yol, tur, govde = stub.govdeler[0]
    assert "application/json" in tur and json.loads(govde) == {"onay": True}, (
        f"kapanış ucuna bilinçli onay gövdesi gitmedi (tür={tur!r}, gövde={govde!r}) — backend 415/400 döner"
    )


@pytest.mark.skipif(_powershell() is None, reason="pwsh/powershell yok")
def test_estop_tek_satiri_ESKI_backendde_kapanis_ucu_YOKSA_ACIL_DURDUR_ucuna_duser(preuninstall_satirlari):
    """🔴 TIBBİ GÜVENLİK (2026-10-18): kapanış ucu yoksa (eski backend: 405) AYNI porta operatörün ACİL DURDUR ucu — bobin
    durdurma kaldırmada hiçbir yolda AZALMAZ. Çıktı hangi ucun kullanıldığını söyler (`uc=2`)."""
    stub = _EstopStub(confirmed=True, kapanis_var=False)
    try:
        rc, cikti = _komutu_kos(_estop_komutu(preuninstall_satirlari, stub.port))
    finally:
        stub.kapat()
    assert stub.istekler == [("POST", "/api/hardware/kapanis_durdur"), ("POST", "/api/hardware/emergency_stop")], (
        stub.istekler
    )
    assert rc == 0 and cikti.startswith("OK uc=2") and "confirmed=True" in cikti, f"rc={rc} çıktı={cikti!r}"


@pytest.mark.skipif(_powershell() is None, reason="pwsh/powershell yok")
def test_estop_tek_satiri_kapanis_ucu_YAVAS_HTTP_hatasinda_ACIL_DURDUR_ucuna_duser(preuninstall_satirlari):
    """🔴 TIBBİ GÜVENLİK (18K K2 — launcher L4 `durdur_iste` ikizi): kapanış ucu ≥ 2 sn sonra HTTP HATASI döndüyse (500) backend
    YANIT VERDİ — uç "yok" sayılır, operatörün ACİL DURDUR ucu denenir (launcher `ureq::Error::Status` → `UcYok`). Eskiden (2026-10-18)
    burada "ikinci istek YOK" pinleniyordu ve "launcher ikizi" deniyordu — launcher'da öyle DEĞİLDİ (ölçüldü 18K). 2 sn eşiği yalnız
    YANITSIZ hatalarda (zaman aşımı) geçerli: o karşıt `test_18K_K1_nsis_estop_VARSAYILAN_port.py` sessiz dinleyici vakasında."""
    stub = _EstopStub(confirmed=True, kapanis_yavas=True)
    try:
        rc, cikti = _komutu_kos(_estop_komutu(preuninstall_satirlari, stub.port))
    finally:
        stub.kapat()
    assert stub.istekler == [("POST", "/api/hardware/kapanis_durdur"), ("POST", "/api/hardware/emergency_stop")], (
        f"yavaş HTTP hatasından sonra ACİL DURDUR ucu denenmedi: {stub.istekler}"
    )
    assert rc == 0 and cikti.startswith("OK uc=2"), f"rc={rc} çıktı={cikti!r}"
