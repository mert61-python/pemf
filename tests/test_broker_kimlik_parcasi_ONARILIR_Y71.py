# Author: mertaygn, cglrgrkn
"""Y71 (sahip, S-G6) — kaldır-kur sonrası kimlik deposu VAR ama broker kimlik parçası (`conf.d`) YOKSA backend açılışta
parçayı AYNI parolalarla yeniden yazar; broker zaten çalışıyorsa YALNIZ backend'in KENDİ broker sürecini (Windows servisi
DEĞİL) bobinler dururken — açılışta — yeniden başlatır. Parola DEĞİŞMEZ (A-18: rotasyon yok); ESP'ye yakılmış kimlik
geçerli kalır; okunamayan depo EZİLMEZ.

ÖLÇÜLEN KUSUR (1-G §8 #9): kaldır-kur `conf.d`'yi ve broker dosyalarını siler, makine deposu (`mqtt_kimlik.json`) kalır.
Açılışta parça yeniden kurulmuyordu → broker ANONİM açılıyor (sahte ack E-stop onayını taklit edebilir — D-2.1), ESP'ler
kimlikle bağlanmaya çalışıyor; tek çare elle `--mqtt-kimlik hazirla` + yeniden başlatma.

KAPI: GERÇEK `MosquittoSupervisor.start()` (izleme döngüsü dahil) + GERÇEK `utils.mqtt_kimlik`; sahte olan yalnız broker
ikilisi (boş dosya + taban yapılandırma), süreç başlatma (`subprocess.Popen` kayıtçısı — gerçek mosquitto ÇALIŞMAZ), port
durumu ve süreç listesi. Ağa çıkılmaz.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Toolhelp32 / QueryFullProcessImageNameW yalnız Windows")
def test_KRITIK_surec_yollari_GERCEK_Windows_APIsiyle_kendi_surecini_YOLUYLA_bulur():
    """Aparatın sahtelediği `_surec_yollari`nın kendisi: GERÇEK ctypes çağrısı test sürecini doğru ikili yoluyla bulmalı —
    yoksa sahada "kendi broker'ımız" hiç tanınmaz (yeniden başlatma sessizce olmaz)."""
    from services import headless_services as hs

    bulunan = dict(hs._surec_yollari(Path(sys.executable).name))
    assert os.getpid() in bulunan, f"test süreci listede yok: {sorted(bulunan)[:10]}"
    assert hs._ayni_dosya(bulunan[os.getpid()], sys.executable), (bulunan[os.getpid()], sys.executable)
    assert all(yol == "" or Path(yol).name.lower() == Path(sys.executable).name.lower() for yol in bulunan.values())


class _Olaylar:
    def publish(self, *a, **k):
        pass


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from services import headless_services as hs
    from utils import mqtt_kimlik

    monkeypatch.setenv("PEMF_DEVICE_IDENTITY_DIR", str(tmp_path / "makine"))
    mqtt_kimlik._onbellek.clear()
    kur = tmp_path / "kurulum"
    kur.mkdir()
    exe = kur / "mosquitto.exe"
    exe.write_bytes(b"")
    (kur / "mosquitto.conf").write_text("listener 1883 0.0.0.0\nallow_anonymous true\n", encoding="utf-8")
    durum = {"port": False, "servis": False, "servis_calisiyor": False, "surecler": [], "popen": [], "sonlandir": []}
    durum["kontrol"] = 0  # `_check_service_status` çağrı sayısı ≈ izleme döngüsü turu (check_once başına bir)
    kilit = threading.Lock()

    def servis_durumu(_self):
        with kilit:
            durum["kontrol"] += 1
        return {"service_exists": durum["servis"], "running": durum["servis_calisiyor"], "pid": None}

    def popen(args, **_k):
        with kilit:
            durum["popen"].append(list(args))
            durum["port"] = True
        return object()

    def sonlandir(_self, pid):
        with kilit:
            durum["sonlandir"].append(pid)
            durum["port"] = False

    monkeypatch.setattr(hs.subprocess, "Popen", popen)
    monkeypatch.setattr(hs, "_is_tcp_port_open", lambda h, p, timeout=2.0: durum["port"])
    monkeypatch.setattr(hs.MosquittoSupervisor, "_find_mosquitto_exe", lambda self: exe)
    monkeypatch.setattr(hs.MosquittoSupervisor, "_check_service_status", servis_durumu)
    monkeypatch.setattr(hs.MosquittoSupervisor, "_read_version", lambda self, p: "")
    # Y71 yardımcıları (önce-kırmızıda henüz YOK → raising=False: davranış ölçülsün, aparat hatası değil)
    monkeypatch.setattr(hs, "_surec_yollari", lambda ad: list(durum["surecler"]), raising=False)
    monkeypatch.setattr(hs.MosquittoSupervisor, "_sureci_sonlandir", sonlandir, raising=False)
    bd = mqtt_kimlik.varsayilan_broker_dizini()
    yield {"hs": hs, "mk": mqtt_kimlik, "bd": bd, "exe": exe, "durum": durum}
    mqtt_kimlik._onbellek.clear()


def _kaldir_kur(bd: Path) -> None:
    """Kaldır-kur: broker dosyaları ve conf.d gider, makine deposu KALIR."""
    for ad in ("pemf_passwd", "pemf_acl", "pemf_calisma.conf"):
        (bd / ad).unlink(missing_ok=True)
    parca = bd / "conf.d"
    for p in parca.glob("*"):
        p.unlink()
    if parca.exists():
        parca.rmdir()


def _kos(o, sure: float = 4.0, popen_bekle: int = 1):
    sup = o["hs"].MosquittoSupervisor(
        port=18830, interval_seconds=0.05, ensure_running=True, start_mdns=False, event_bus=_Olaylar()
    )
    sup.start()
    son = time.monotonic() + sure
    while time.monotonic() < son and len(o["durum"]["popen"]) < popen_bekle:
        time.sleep(0.05)
    time.sleep(0.3)
    sup.stop()
    return sup


def _conf_metni(args: list[str]) -> str:
    assert "-c" in args, f"broker yapılandırmasız başlatıldı: {args}"
    return Path(args[args.index("-c") + 1]).read_text(encoding="utf-8")


def _parolalar_dogrulanir(mk, bd: Path, kimlikler: dict) -> bool:
    satirlar = dict(s.split(":", 1) for s in (bd / "pemf_passwd").read_text(encoding="utf-8").splitlines() if s)
    return all(mk.ozet7_dogrula(p, satirlar[k]) for k, p in kimlikler.items())


def test_KRITIK_kaldir_kur_sonrasi_parca_AYNI_parolalarla_yazilir_broker_ILK_acilista_kimlikli(ortam):
    mk, bd = ortam["mk"], ortam["bd"]
    mk.hazirla(bd)
    kimlikler, depo = mk.kimlikleri_oku(), Path(mk._depo_yolu()).read_bytes()
    _kaldir_kur(bd)
    assert not (bd / "conf.d" / "pemf_kimlik.conf").exists()

    _kos(ortam)

    assert (bd / "conf.d" / "pemf_kimlik.conf").is_file(), (
        "kaldır-kur sonrası kimlik parçası açılışta YENİDEN KURULMADI — broker anonim açılır (sahte ack E-stop onayı)"
    )
    assert Path(mk._depo_yolu()).read_bytes() == depo and mk.kimlikleri_oku() == kimlikler, "kimlik deposu DEĞİŞTİ"
    assert (bd / "pemf_acl").is_file() and _parolalar_dogrulanir(mk, bd, kimlikler), (
        "broker parola dosyası depodaki AYNI parolalarla doğrulanmıyor — ESP'ye yakılmış kimlik geçersiz kalır (A-18)"
    )
    ilk = ortam["durum"]["popen"][0]
    assert f"include_dir {(bd / 'conf.d').as_posix()}" in _conf_metni(ilk), (
        f"broker İLK açılışta kimlik parçasını içermiyor (anonim pencere): {ilk}"
    )


def test_KRITIK_calisan_KENDI_broker_yeniden_baslatilir_YABANCI_surece_dokunulmaz(ortam):
    mk, bd, d = ortam["mk"], ortam["bd"], ortam["durum"]
    mk.hazirla(bd)
    _kaldir_kur(bd)
    d["port"] = True  # önceki backend'in AYRIK broker'ı hâlâ 1883'te (anonim yapılandırmayla)
    d["surecler"] = [(4242, str(ortam["exe"])), (777, r"C:\Program Files\mosquitto\mosquitto.exe")]

    _kos(ortam)

    assert d["sonlandir"] == [4242], (
        f"sonlandırılan süreçler {d['sonlandir']} — yalnız backend'in KENDİ broker'ı (4242) yeniden başlatılmalı; "
        "çalışan anonim broker kimliği devreye SOKMAZ"
    )
    assert d["popen"] and f"include_dir {(bd / 'conf.d').as_posix()}" in _conf_metni(d["popen"][0]), (
        f"broker kimlikli yapılandırmayla yeniden BAŞLATILMADI: {d['popen']}"
    )


def test_KARSIT_WINDOWS_SERVISI_yeniden_baslatilmaz_parca_yine_yazilir(ortam):
    mk, bd, d = ortam["mk"], ortam["bd"], ortam["durum"]
    mk.hazirla(bd)
    _kaldir_kur(bd)
    d.update(port=True, servis=True, servis_calisiyor=True, surecler=[(4242, str(ortam["exe"]))])

    _kos(ortam, sure=1.5, popen_bekle=99)

    assert (bd / "conf.d" / "pemf_kimlik.conf").is_file(), "servis kurulumunda da parça yeniden yazılmalı"
    assert d["sonlandir"] == [] and d["popen"] == [], (
        f"Windows SERVİSİ backend'in broker'ı DEĞİL — sonlandır {d['sonlandir']}, başlat {d['popen']}"
    )


def test_KARSIT_depo_YOKSA_hicbir_sey_yazilmaz_anonim_kip_AYNEN(ortam):
    bd, d = ortam["bd"], ortam["durum"]

    _kos(ortam)

    assert not (bd / "conf.d").exists() and not (bd / "pemf_passwd").exists(), "hazırlanmamış sistemde kimlik UYDURULDU"
    assert d["popen"] and "include_dir" not in _conf_metni(d["popen"][0]), "hazırlanmamış broker anonim kalmalı (A)"


def test_KARSIT_okunamayan_depo_EZILMEZ_parca_yazilmaz(ortam):
    mk, bd = ortam["mk"], ortam["bd"]
    mk.hazirla(bd)
    _kaldir_kur(bd)
    Path(mk._depo_yolu()).write_text("{bozuk", encoding="utf-8")
    mk._onbellek.clear()
    bozuk = Path(mk._depo_yolu()).read_bytes()

    _kos(ortam)

    assert Path(mk._depo_yolu()).read_bytes() == bozuk, (
        "okunamayan kimlik deposu EZİLDİ (yakılmış ESP parolaları gider)"
    )
    assert not (bd / "conf.d" / "pemf_kimlik.conf").exists(), "okunamayan depodan parça yazıldı (yeni parola = uydurma)"


def test_KRITIK_onarim_YALNIZ_acilista_izleme_dongusu_yeniden_baslatmaz(ortam):
    """Onarım + yeniden başlatma bobinler dururken (açılış) yapılır; izleme döngüsü çalışırken TEKRARLAMAZ."""
    mk, bd, d = ortam["mk"], ortam["bd"], ortam["durum"]
    mk.hazirla(bd)
    _kaldir_kur(bd)
    sup = ortam["hs"].MosquittoSupervisor(
        port=18830, interval_seconds=0.05, ensure_running=True, start_mdns=False, event_bus=_Olaylar()
    )
    sup.start()
    try:
        son = time.monotonic() + 4.0
        while time.monotonic() < son and not d["popen"]:
            time.sleep(0.05)
        assert (bd / "conf.d" / "pemf_kimlik.conf").is_file(), "aparat: açılış onarımı olmadı"
        _kaldir_kur(bd)  # çalışırken parça yine kaybolsa bile…
        d["surecler"] = [(4242, str(ortam["exe"]))]
        # ⚠️ Süreye değil DÖNGÜ TURUNA bağlı: ilk başlatma `time.sleep(1)` içinde beklerken döngü tur atmaz (süre penceresi
        # ilk turda bu yüzden KÖRDÜ — m6 mutantı yeşil kalıyordu). Silmeden sonra en az 10 tur görülene dek beklenir.
        tur0, son = d["kontrol"], time.monotonic() + 6.0
        while time.monotonic() < son and d["kontrol"] - tur0 < 10:
            time.sleep(0.05)
        assert d["kontrol"] - tur0 >= 10, f"aparat: izleme döngüsü {d['kontrol'] - tur0} tur attı"
    finally:
        sup.stop()
    assert d["sonlandir"] == [] and len(d["popen"]) == 1, (
        f"izleme döngüsü broker'ı yeniden başlattı (sonlandır {d['sonlandir']}, başlat {len(d['popen'])}) — "
        "çalışırken (bobin sürülüyor olabilir) yeniden başlatma YOK"
    )
