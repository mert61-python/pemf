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
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    alınmalı (`confirmed=false` yalnız gövdede görünür). Günlük `%APPDATA%\\PEMF_GUI\\logs`
    altına: KVKK gereği client-kaldırmanın ASLA silmediği veri kökü → iz kaldırmadan sonra da
    okunabilir. Yazma, port-okumasıyla aynı `SetShellVarContext current … all` dansını izlemeli
    (`all` bağlamında $APPDATA ProgramData'ya çözümlenir → dosya yanlış yere/yazılamaz).
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
    assert any("PEMF_GUI" in s for s in ara[acilis : acilis + 1]), (
        "Günlük %APPDATA%\\PEMF_GUI altında değil → client-kaldırma silebilir ya da dizin yok."
    )
    oncesi = ara[:acilis]
    sonrasi = ara[acilis:]
    assert "SetShellVarContext current" in oncesi and "SetShellVarContext all" in sonrasi, (
        "Günlük yazımı `SetShellVarContext current` … `all` dansı olmadan yapılıyor: `all` bağlamında "
        "$APPDATA = C:\\ProgramData → yanlış dizin/izin yok; ve geri çevrilmezse kaldırıcının geri "
        "kalanı yanlış bağlamda koşar."
    )
    yazim = next(s for s in sonrasi if s.startswith("FileWrite"))
    assert "$0" in yazim and "$1" in yazim and "$2" in yazim, (
        f"Günlük satırı eksik ({yazim!r}): port ($2), nsExec dönüşü ($0) ve çıktı ($1) hepsi yazılmalı."
    )
    assert any(s.startswith("MessageBox") and "ELLE" in s for s in ara), (
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
    """`POST /api/hardware/emergency_stop` için tek-amaçlı HTTP taklidi (gerçek yanıt şeması)."""

    def __init__(self, confirmed: bool):
        self.istekler: list[tuple[str, str]] = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                stub.istekler.append(("POST", self.path))
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
    assert stub.istekler == [("POST", "/api/hardware/emergency_stop")], (
        f"Beklenen tek POST /api/hardware/emergency_stop; gelen: {stub.istekler}"
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
    assert stub.istekler == [("POST", "/api/hardware/emergency_stop")]
    assert rc == 0, f"confirmed=true için çıkış 0 beklenir, {rc} geldi (çıktı: {cikti!r})"
    assert cikti.startswith("OK") and "confirmed=True" in cikti, f"Çıktı 'OK … confirmed=True' olmalı: {cikti!r}"
    assert "\n" not in cikti, f"Çıktı TEK satır olmalı (günlük satırı bozulur): {cikti!r}"
