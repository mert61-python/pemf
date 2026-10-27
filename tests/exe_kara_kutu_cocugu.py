# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KARA KUTU ÇOCUĞU (İG-9.48) — `backend_service.main()`'i bir betiğin (build AI kapısı / ürün senaryoları) EXE'ye verdiği
ortam ve argümanlarla AYRI SÜREÇTE koşturur; gerçek sisteme her DOKUNMA denemesini ENGELLER ve SAYAR.

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (adı `test_*` değil, pytest TOPLAMAZ). Çağıran:
`tests/test_exe_kapisi_kara_kutu_yalitimi_IG948.py`.

NEDEN: build AI kapısı ve `urun_senaryolari.py` derlenmiş EXE'yi açar. Ortam kapıları (`test_exe_kapisi_firmware_kapali`,
`test_build_kapisi_yalitimi`) yalnız DEĞİŞKENLERİN değerine bakar; ürünün o değişkenleri GERÇEKTEN onurlandırıp onurlandırmadığını
(ör. başka bir yoldan COM10'a, buluta, ProgramData'ya gidip gitmediğini) görmez. Bu çocuk aynı ortamla ÜRÜNÜN KENDİSİNİ açar.

EXE DERLENMEZ, PORT AÇILMAZ: `backend_service._build_server` sahte bir sunucuyla değişir (uvicorn dinlemez); açılışın geri kalanı
(DB, HeadlessCore + HWSender, bulut senkronu, oto-güncelleme, donanım güncellemesi kurulumu, hotspot, torch, AI ısıtma) GERÇEK
koşar ve `SURE` saniye arka planda yaşar, sonra `main()`'in kendi kapanışı (`_shutdown`) koşar.

ENGELLENEN VE SAYILAN (hiçbiri gerçeğe ULAŞMAZ — kafessiz tam süitte de):
  * ağ: `alt_surec_ag_bekcisi` (loopback dışı connect / sendto / DNS, sahip portları, açılmamış loopback portu) +
    loopback dışı BIND (LAN dinleyici: güvenlik duvarı uyarısı = görünür pencere);
  * seri port: `serial.Serial.open` (gerçek COM'a hiç ulaşılmaz; açılmak istenen ad kaydedilir);
  * alt süreç: `subprocess.Popen`, `os.system`, `os.startfile`, `_winapi.CreateProcess` (hepsi reddedilir);
  * disk: izin verilen kökler (çağıranın geçici dizini, TEMP) DIŞINA yazma / dizin açma / silme / taşıma reddedilir;
    `--gercek` kökleri (dış ortamın "gerçek" APPDATA / LOCALAPPDATA / PROGRAMDATA / USERPROFILE NÖBETÇİLERİ) altına yazma
    SAYILIR (nöbetçi geçici dizinde olduğu için zararsızdır);
  * kayıt defteri: anahtar açma (yazma erişimli) / oluşturma / değer yazma / silme reddedilir;
  * kimlik kasası: `keyring` kaydedici arka uca bağlanır (gerçek kasaya ASLA gidilmez); ortam null arka uç VERMEDİYSE
    her erişim "kasa" diye sayılır (ürün gerçek kasaya giderdi).
Çıktı: JSON (`kayit` listesi + bekçi kayıtları + seri port adları + açılış izleri)."""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for _yol in (KOK / "tests", KOK, KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

# 1) AĞ — ürün importundan ÖNCE (bekçi socket'i sarar + audit kancası + Proactor).
import alt_surec_ag_bekcisi as ag  # noqa: E402

_kilit = threading.Lock()
KAYIT: list[list[str]] = []
SERI: list[str] = []
IZ: list[str] = []


def _kaydet(tur: str, ayrinti: str) -> None:
    with _kilit:
        if len(KAYIT) < 2000:
            KAYIT.append([tur, ayrinti])


def _argumanlar(argv: list[str]):
    cikti, sure = Path(argv[0]), float(argv[1])
    izinli, gercek, i = [], [], 2
    while i < len(argv) and argv[i] != "--":
        if argv[i] == "--izinli":
            izinli.append(argv[i + 1])
        elif argv[i] == "--gercek":
            gercek.append(argv[i + 1])
        i += 2
    return cikti, sure, izinli, gercek, argv[i + 1 :]


CIKTI, SURE, _IZINLI, _GERCEK, BACKEND_ARGV = _argumanlar(sys.argv[1:])


def _norm(yol) -> str | None:
    try:
        if isinstance(yol, int):
            return None
        yol = os.fsdecode(os.fspath(yol))
    except TypeError:
        return None
    if yol.upper() in ("NUL", "CON", "NUL:", "CONOUT$", "CONIN$") or yol.startswith("\\\\.\\"):
        return None
    return os.path.normcase(os.path.abspath(yol))


def _kok_listesi(yollar) -> list[str]:
    return [os.path.normcase(os.path.abspath(y)).rstrip("\\/") for y in yollar if y]


IZINLI = _kok_listesi(_IZINLI + [os.environ.get("TEMP", ""), os.environ.get("TMP", "")])
GERCEK = _kok_listesi(_GERCEK)


def _altinda(yol: str, kokler: list[str]) -> bool:
    return any(yol == k or yol.startswith(k + os.sep) for k in kokler)


#: Kaynaktan koşumun yorumlayıcı önbelleği (ör. librosa/numba JIT önbelleği `site-packages\<paket>\__pycache__`). Donmuş
#: EXE'de bu yol yoktur; ürünün DIŞ ortama dokunması sayılmaz (yorumlayıcının kendi ağacı).
_YORUMLAYICI = os.path.normcase(os.path.abspath(sys.prefix)).rstrip("\\/")


def _disk_denetle(yol, islem: str) -> None:
    n = _norm(yol)
    if n is None:
        return
    if _altinda(n, [_YORUMLAYICI]) and f"{os.sep}__pycache__" in n:
        return
    if _altinda(n, GERCEK):
        _kaydet("gercek_kok", f"{islem} {n}")  # nöbetçi geçici dizinde — zararsız, ama SAYILIR
        return
    if _altinda(n, IZINLI):
        return
    _kaydet("disk_disi", f"{islem} {n}")
    raise PermissionError(f"KARA KUTU: {islem} {n} reddedildi (izinli kök dışı)")


_VER = re.compile(r'cmd(\.exe)?"? /c "?(command /c |cmd /c )?ver"?$', re.IGNORECASE)
#: pydub'ın içe aktarmada yaptığı salt-okunur araç yoklaması (`ffmpeg -version` / `avconv -version`).
_SURUM_YOKLAMASI = re.compile(r"^(ffmpeg|avconv|ffprobe|avprobe)(\.exe)? -version$", re.IGNORECASE)


def _zararsiz_surec(olay: str, arg) -> bool:
    """Yalnız şu süreçler zararsız sayılır (yine de BAŞLATILMAZ): `platform` modülünün `ver` sorgusu, ses kitaplığının
    `ffmpeg -version` yoklaması ve ürünün KENDİ veri kökündeki (izinli kök) sır dosyalarına `icacls` sıkılaştırması. Diğer her
    süreç (sc / tasklist / mosquitto / powershell / netsh / schtasks / cmdkey …) gerçek sisteme uzanan bir dokunmadır."""
    if olay != "subprocess.Popen" or len(arg) < 2:
        return False
    komut = arg[1]
    metin = komut if isinstance(komut, str) else " ".join(os.fsdecode(os.fspath(x)) for x in komut)
    if _VER.search(metin.strip()) or _SURUM_YOKLAMASI.match(metin.strip()):
        return True
    parca = metin.split()
    if parca and os.path.basename(parca[0]).lower() in ("icacls", "icacls.exe") and len(parca) > 1:
        hedef = _norm(parca[1].strip('"'))
        return hedef is not None and _altinda(hedef, IZINLI) and not _altinda(hedef, GERCEK)
    return False


_YAZMA_BAYRAKLARI = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_KAYIT_YAZMA_ERISIMI = (
    0x0002 | 0x0004 | 0x00010000 | 0x00040000 | 0x00080000
)  # SET_VALUE|CREATE_SUB_KEY|DELETE|WRITE_DAC|WRITE_OWNER


def _kanca(olay: str, arg) -> None:
    if olay == "open":
        yol, kip, bayrak = (list(arg) + [None, None, None])[:3]
        yazma = (isinstance(kip, str) and any(c in kip for c in "wax+")) or (
            isinstance(bayrak, int) and bayrak & _YAZMA_BAYRAKLARI
        )
        if yazma:
            _disk_denetle(yol, "yaz")
        else:
            n = _norm(yol)
            # build makinesinin GERÇEK kökünden ÜRÜN verisi / sırrı okuma (ör. `~/.pemf`, `PEMF_GUI`, `PEMF_System`). Üçüncü
            # taraf kitaplık ayarları (ör. reportlab `~/.reportlab_settings`) ürün verisi değildir, sayılmaz.
            if n is not None and _altinda(n, GERCEK) and "pemf" in n:
                _kaydet("gercek_okuma", n)
    elif olay in ("os.mkdir", "os.remove", "os.rmdir", "shutil.rmtree", "os.truncate"):
        _disk_denetle(arg[0], olay)
    elif olay in ("os.rename", "shutil.copyfile", "shutil.copytree", "shutil.move"):
        _disk_denetle(arg[1], olay)
    elif olay == "sqlite3.connect":
        if arg and isinstance(arg[0], (str, bytes, os.PathLike)) and str(arg[0]) != ":memory:":
            _disk_denetle(arg[0], olay)
    elif olay == "socket.bind":
        adres = arg[1]
        if getattr(arg[0], "family", None) in ag._AILELER and isinstance(adres, tuple) and len(adres) >= 2:
            if not ag._loopback(adres[0] or "0.0.0.0"):
                _kaydet("lan_bind", f"{adres[0] or '*'}:{adres[1]}")
                raise PermissionError(f"KARA KUTU: bind {adres[0]}:{adres[1]} reddedildi (LAN dinleyici)")
    elif olay in ("subprocess.Popen", "os.system", "os.startfile", "os.spawn", "os.exec", "_winapi.CreateProcess"):
        _kaydet("surec" if _zararsiz_surec(olay, arg) else "surec_dis", f"{olay} {arg!r}"[:300])
        raise PermissionError(f"KARA KUTU: {olay} reddedildi (alt süreç)")
    elif olay in ("winreg.CreateKey", "winreg.SetValue", "winreg.DeleteKey", "winreg.DeleteValue"):
        _kaydet("kayit_defteri", f"{olay} {arg[1:2]!r}")
        raise PermissionError(f"KARA KUTU: {olay} reddedildi (kayıt defteri)")
    elif olay == "winreg.OpenKey":
        erisim = arg[2] if len(arg) > 2 else 0
        if isinstance(erisim, int) and erisim & _KAYIT_YAZMA_ERISIMI:
            _kaydet("kayit_defteri", f"{olay} {arg[1]!r} erisim={erisim:#x}")
            raise PermissionError("KARA KUTU: kayıt defteri yazma erişimi reddedildi")


sys.addaudithook(_kanca)

# 1b) UDP "rota sorgusu": `socket(AF_INET, SOCK_DGRAM).connect(("8.8.8.8", 80))` PAKET GÖNDERMEZ — yerel LAN adresini bulmanın
# yaygın yolu (`get_local_ip`). Dış ağ denemesi SAYILMAZ (ayrı kaydedilir) ama yine de reddedilir (ürün yedek yola düşer).
_bekcili_connect = socket.socket.connect


def _udp_rota_ayir(self, adres):
    if (
        self.family in ag._AILELER
        and self.type == socket.SOCK_DGRAM
        and isinstance(adres, tuple)
        and len(adres) >= 2
        and not ag._loopback(adres[0])
    ):
        _kaydet("udp_rota", f"{adres[0]}:{adres[1]}")
        raise OSError(10051, "KARA KUTU: UDP rota sorgusu reddedildi (paket yok)")
    return _bekcili_connect(self, adres)


socket.socket.connect = _udp_rota_ayir

# 2) SERİ PORT — gerçek COM'a hiçbir koşulda ulaşılmaz.
try:
    import serial
    import serial.tools.list_ports as _lp

    def _seri_ac(self):
        SERI.append(str(getattr(self, "port", None) or getattr(self, "portstr", "")))
        raise serial.SerialException(f"KARA KUTU: seri port {self.port!r} açılmadı")

    serial.Serial.open = _seri_ac
    for _ad in ("serialwin32", "serialposix"):
        _m = sys.modules.get(f"serial.{_ad}")
        if _m is not None:
            _m.Serial.open = _seri_ac
    _lp.comports = lambda *a, **k: []
except Exception as _e:  # pyserial yoksa ürün de seri açamaz
    IZ.append(f"seri yamasi kurulamadi: {_e!r}")

# 3) KİMLİK KASASI — kaydedici arka uç (gerçek kasaya ASLA gidilmez).
NULL_KASA = os.environ.get("PYTHON_KEYRING_BACKEND", "").strip().endswith("null.Keyring")
try:
    import keyring
    import keyring.backend
    import keyring.core

    class _KasaKaydedici(keyring.backend.KeyringBackend):
        priority = 99

        def _say(self, islem, servis):
            if not NULL_KASA:
                _kaydet("kasa", f"{islem} {servis}")

        def get_password(self, servis, kullanici):
            self._say("get", servis)
            return None

        def set_password(self, servis, kullanici, parola):
            self._say("set", servis)

        def delete_password(self, servis, kullanici):
            self._say("delete", servis)

        def get_credential(self, servis, kullanici):
            self._say("get_credential", servis)
            return None

    _kasa = _KasaKaydedici()
    keyring.set_keyring(_kasa)
    keyring.core.init_backend = lambda *a, **k: _kasa
    keyring.core.get_keyring = lambda: _kasa
except Exception as _e:
    IZ.append(f"kasa yamasi kurulamadi: {_e!r}")


def _yaz_ve_cik(kod: int, durum: str) -> None:
    with _kilit:
        veri = {
            "durum": durum,
            "kayit": list(KAYIT),
            "ag_engellenen": [list(x) for x in ag.ENGELLENEN],
            "seri": list(SERI),
            "iz": list(IZ),
            "null_kasa": NULL_KASA,
            "is_parcaciklari": sorted({t.name for t in threading.enumerate()}),
        }
    CIKTI.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(kod)


def _bekci_saati() -> None:
    time.sleep(SURE + 150)
    _yaz_ve_cik(3, "ZAMAN_ASIMI")


threading.Thread(target=_bekci_saati, daemon=True, name="kara-kutu-saati").start()


class _SahteSunucu:
    """uvicorn yerine: port AÇMAZ; `SURE` saniye (ya da kapanış istenene dek) arka planın yaşamasını bekler."""

    def __init__(self):
        self.should_exit = False
        self.handle_exit = lambda *a: setattr(self, "should_exit", True)

    def run(self):
        IZ.append("sunucu: run (acilis tamam)")
        bitis = time.monotonic() + SURE
        while time.monotonic() < bitis and not self.should_exit:
            time.sleep(0.2)
        return None


def _ana() -> None:
    try:
        import backend_service as bs

        bs._build_server = lambda app, args: _SahteSunucu()
        rc = bs.main(BACKEND_ARGV)
        IZ.append(f"main dondu rc={rc}")
        _yaz_ve_cik(0, "TAMAM")
    except BaseException:
        IZ.append(traceback.format_exc()[-3000:])
        _yaz_ve_cik(2, "COKTU")


if __name__ == "__main__":
    _ana()
