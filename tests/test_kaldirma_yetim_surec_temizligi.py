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

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_HOOKS = _KOK / "launcher" / "app" / "windows" / "hooks.nsi"
_BACKEND_RS = _KOK / "launcher" / "core" / "src" / "backend.rs"


def _makensis() -> str | None:
    """NSIS derleyicisini bul (Tauri kendi kopyasını `%LOCALAPPDATA%\\tauri\\NSIS`'e indirir)."""
    if sys.platform != "win32":
        return None
    yerel = os.environ.get("LOCALAPPDATA")
    adaylar = []
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
    """NSIS satır-yorumunu (`;`) at. Tırnak içindeki `;` korunur."""
    disarida = True
    for i, ch in enumerate(satir):
        if ch == "'":
            disarida = not disarida
        elif ch == ";" and disarida:
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


def _taskkill_hedefleri(satirlar: list[str]) -> list[str]:
    """Sırayla `taskkill /IM <ad>` hedefleri (küçük harf)."""
    hedefler = []
    for s in satirlar:
        for m in re.finditer(r"/IM\s+(\S+?\.exe)", s, re.IGNORECASE):
            hedefler.append(m.group(1).lower())
    return hedefler


@pytest.fixture(scope="module")
def rust_surec_adlari() -> list[str]:
    """`kill_stray_backends()` Windows kolundaki imaj listesi — TEK KAYNAK."""
    metin = _BACKEND_RS.read_text(encoding="utf-8")
    govde = re.search(r"pub fn kill_stray_backends\(\)(.*?)\n\}", metin, re.DOTALL)
    assert govde, "kill_stray_backends() bulunamadı (backend.rs yeniden mi adlandırıldı?)"
    dizi = re.search(r'for image in \[(.*?)\]', govde.group(1), re.DOTALL)
    assert dizi, "kill_stray_backends() içindeki imaj dizisi ayrıştırılamadı"
    adlar = re.findall(r'"([^"]+\.exe)"', dizi.group(1))
    assert adlar, "imaj dizisi boş çıktı"
    return [a.lower() for a in adlar]


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

    `services/headless_services.py::_monitor_loop` `ensure_running` iken broker'ı diriltir.
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


# ─────────────────────────────────────────────────────────────────────────────
# NSIS'e ÖZGÜ DEĞİŞMEZLER — burada bir hata sessizdir, bu yüzden test edilir.
# ─────────────────────────────────────────────────────────────────────────────


def test_her_nsexec_cagrisinin_donus_kodu_atilir(preuninstall_satirlari):
    """Yığın dengesi: `nsExec::Exec` dönüş kodunu yığına İTER; Pop edilmezse kayıt sızar.

    Dosyanın kendi yorumları bunu belgeliyor: atlanan bir Pop, sonraki `Pop $2/$1/$0`'ların
    ORİJİNAL kayıtlar yerine bu dönüşü yüklemesine yol açar → kaldırıcı kayıtları bozuk
    değerlerle sürdürür. Derleyici bunu YAKALAMAZ.
    """
    kod = [s for s in preuninstall_satirlari if s.strip()]
    for i, satir in enumerate(kod):
        if "nsExec::Exec" not in satir:
            continue
        sonraki = kod[i + 1].strip() if i + 1 < len(kod) else ""
        assert sonraki.startswith("Pop "), (
            f"nsExec::Exec sonrası Pop yok (satır: {satir.strip()!r}, sonraki: {sonraki!r}). "
            "Dönüş kodu yığında kalır ve kayıt geri-yüklemesini bozar."
        )


def test_push_pop_dengesi_korunur(preuninstall_satirlari):
    """Makro yığını nötr bırakmalı: Pop = Push + nsExec::Exec."""
    kod = [s.strip() for s in preuninstall_satirlari]
    push = sum(1 for s in kod if re.match(r"^Push\s+\$", s))
    pop = sum(1 for s in kod if re.match(r"^Pop\s+\$", s))
    exec_ = sum(1 for s in kod if "nsExec::Exec" in s)
    assert pop == push + exec_, (
        f"Yığın dengesiz: Push={push}, nsExec::Exec={exec_}, Pop={pop} "
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
