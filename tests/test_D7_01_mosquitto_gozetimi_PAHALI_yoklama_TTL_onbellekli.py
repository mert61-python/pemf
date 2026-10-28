# Author: mertaygn, cglrgrkn
"""D7.01 (B-4.20) — `MosquittoSupervisor` pahalı (alt süreç) yoklamalarını TTL ile önbellekler (`NetworkStatusService._cached_poll` deseni).

KUSUR (ölçüldü, HEAD `ebf1c3fe`): izleme döngüsü 10 sn'de bir `check_once` koşar; her turda `mosquitto -h` (sürüm), `sc query
mosquitto` ve servis yoksa `tasklist` alt süreci başlatılır → günde 17 280–25 920 kısa ömürlü süreç (servis kayıtlıyken 2, değilken 3 /
tur). Sürüm ikili değişmedikçe, servisin YOKLUĞU ve yalnız gösterilen süreç kimliği saniyeler mertebesinde değişmez.

⚠️ GÜVENLİK SINIRI (bilinçli): KAYITLI Windows servisinin ÇALIŞMA durumu (`sc query` RUNNING) ÖNBELLEKLENMEZ — Windows'ta otoriter
`running` odur; önbelleklenseydi çöken broker'ın yeniden başlatılması TTL kadar gecikir (ESP STOP yolu) ve `net start` sonrası
teyit eski değeri okuyup geri çekilmeye (backoff) düşerdi. Linux'ta birim TANIMI (`is-enabled`) önbelleklenir, `is-active` taze.
Durum değiştiren eylemden (`net start`, broker süreci başlatma) sonra önbellek boşaltılır.

Sahte EN ALT katta: modül `_run_command` (alt süreç koşucusu) sayaçlı sahteyle, saat örneğe ENJEKTE (`_saat`) — gerçek süreç / ağ YOK
(`_is_tcp_port_open` sahte; loopback'e bağlanılmaz).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

TTL = 60.0  # beklenen değer testte PİNLİ (kapı sabiti mutasyon hedefinden okunmaz)


class _Kosucu:
    def __init__(self, servis: bool = False, calisiyor: bool = True):
        self.cagri: list[tuple[str, ...]] = []
        self.servis = servis
        self.calisiyor = calisiyor

    def __call__(self, args, timeout: int = 5):
        self.cagri.append(tuple(str(a) for a in args))
        a0 = Path(str(args[0])).name.lower()
        if a0 == "sc":
            if not self.servis:
                return subprocess.CompletedProcess(args, 1060, "", "")
            durum = "4  RUNNING" if self.calisiyor else "1  STOPPED"
            return subprocess.CompletedProcess(
                args, 0, f"SERVICE_NAME: mosquitto\n        STATE              : {durum}\n", ""
            )
        if a0 == "tasklist":
            return subprocess.CompletedProcess(
                args, 0, "mosquitto.exe                 4242 Console    1     9.000 K\n", ""
            )
        if a0 == "systemctl":
            if args[1] == "is-enabled":
                return subprocess.CompletedProcess(
                    args, 0 if self.servis else 1, "enabled\n" if self.servis else "", ""
                )
            return subprocess.CompletedProcess(args, 0, "active\n" if self.calisiyor else "inactive\n", "")
        if len(args) > 1 and args[1] == "-h":
            return subprocess.CompletedProcess(args, 3, "mosquitto version 2.0.18\n", "")
        raise AssertionError(f"beklenmeyen alt süreç: {args}")

    def say(self, ad: str) -> int:
        return sum(
            1 for c in self.cagri if (Path(c[0]).name.lower() == ad) or (ad == "-h" and len(c) > 1 and c[1] == "-h")
        )


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    from services import headless_services as hs

    exe = tmp_path / "bin" / "mosquitto.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    kos = _Kosucu()
    saat = [1000.0]
    monkeypatch.setattr(hs, "_run_command", kos)
    monkeypatch.setattr(hs, "_is_tcp_port_open", lambda h, p, timeout=2.0: True)
    monkeypatch.setattr(hs.MosquittoSupervisor, "_find_mosquitto_exe", lambda self: exe)

    class _Olaylar:
        def publish(self, *a, **k):
            pass

    sup = hs.MosquittoSupervisor(
        port=18831, interval_seconds=10.0, ensure_running=False, start_mdns=False, event_bus=_Olaylar()
    )
    sup._saat = lambda: saat[0]
    return {"hs": hs, "sup": sup, "kos": kos, "saat": saat, "exe": exe, "mp": monkeypatch}


def _windows(o):
    o["mp"].setattr(o["hs"].platform, "system", lambda: "Windows")


def test_KRITIK_TTL_icinde_art_arda_durum_sorgusu_ALT_SURECI_bir_kez_baslatir(ortam):
    _windows(ortam)
    sup, kos = ortam["sup"], ortam["kos"]
    for _ in range(5):
        ortam["saat"][0] += 10.0 if kos.cagri else 0.0
        st = sup.check_once()
    assert ortam["saat"][0] - 1000.0 < TTL
    assert (kos.say("-h"), kos.say("sc"), kos.say("tasklist")) == (1, 1, 1), (
        f"TTL içinde 5 durum sorgusu {kos.say('-h')} × `mosquitto -h`, {kos.say('sc')} × `sc query`, {kos.say('tasklist')} × "
        "`tasklist` başlattı — beklenen 1 / 1 / 1 (günde ~17 280–25 920 kısa ömürlü süreç)"
    )
    assert st["version"] == "mosquitto version 2.0.18" and st["pid"] == 4242 and st["running"] is True


def test_KRITIK_TTL_dolunca_YENIDEN_yoklanir(ortam):
    _windows(ortam)
    sup, kos = ortam["sup"], ortam["kos"]
    sup.check_once()
    ortam["saat"][0] += TTL - 1.0
    sup.check_once()
    assert (kos.say("-h"), kos.say("sc"), kos.say("tasklist")) == (1, 1, 1), "TTL dolmadan yeniden yoklandı"
    ortam["saat"][0] += 2.0
    sup.check_once()
    assert (kos.say("-h"), kos.say("sc"), kos.say("tasklist")) == (2, 2, 2), (
        f"TTL dolduktan sonra yeniden yoklanmadı: {kos.say('-h')} / {kos.say('sc')} / {kos.say('tasklist')}"
    )


def test_KRITIK_GUVENLIK_kayitli_servisin_CALISMA_durumu_ONBELLEKLENMEZ(ortam):
    """Servis kayıtlıyken `running` her turda TAZE: çöken broker hemen görülür (yeniden başlatma gecikmez)."""
    _windows(ortam)
    sup, kos = ortam["sup"], ortam["kos"]
    kos.servis, kos.calisiyor = True, True
    assert sup.check_once()["running"] is True
    ortam["saat"][0] += 1.0
    kos.calisiyor = False
    st = sup.check_once()
    assert st["running"] is False, (
        "kayıtlı servis DURDU ama durum önbellekten 'çalışıyor' okundu — yeniden başlatma TTL kadar gecikir"
    )
    assert kos.say("sc") == 2 and kos.say("-h") == 1 and kos.say("tasklist") == 0, (
        kos.say("sc"),
        kos.say("-h"),
        kos.say("tasklist"),
    )


def test_KRITIK_surum_onbellegi_IKILI_degisince_tazelenir(ortam):
    _windows(ortam)
    sup, kos, exe = ortam["sup"], ortam["kos"], ortam["exe"]
    sup.check_once()
    exe.write_bytes(b"MZ-yeni-surum")  # boyut değişti (güncelleme / onarım ikiliyi yeniledi)
    ortam["saat"][0] += 1.0
    sup.check_once()
    assert kos.say("-h") == 2, "ikili değişti ama sürüm önbellekten okundu"


def test_KRITIK_durum_degistiren_eylemden_sonra_onbellek_BOSALIR(ortam):
    """Broker süreci başlatıldıktan sonra servis yokluğu / süreç kimliği yeniden okunur (eski pid / yokluk TTL boyunca kalmaz)."""
    _windows(ortam)
    hs, sup, kos = ortam["hs"], ortam["sup"], ortam["kos"]
    ortam["mp"].setattr(hs.MosquittoSupervisor, "_kimlik_dahil_conf", lambda self, taban: taban)
    ortam["mp"].setattr(hs.subprocess, "Popen", lambda *a, **k: object())
    sup.check_once()
    assert (kos.say("sc"), kos.say("tasklist")) == (1, 1)
    assert sup._launch_broker_process() is True
    assert (kos.say("sc"), kos.say("tasklist")) == (2, 2), (
        f"broker başlatıldıktan sonraki durum sorgusu önbellekten okundu: sc {kos.say('sc')}, tasklist {kos.say('tasklist')}"
    )


def test_KRITIK_linux_birim_TANIMI_onbellekli_is_active_TAZE(ortam):
    ortam["mp"].setattr(ortam["hs"].platform, "system", lambda: "Linux")
    sup, kos = ortam["sup"], ortam["kos"]
    kos.servis, kos.calisiyor = True, True
    sup.check_once()
    ortam["saat"][0] += 1.0
    kos.calisiyor = False
    sup.check_once()
    tanim = sum(1 for c in kos.cagri if c[:2] == ("systemctl", "is-enabled"))
    etkin = sum(1 for c in kos.cagri if c[:2] == ("systemctl", "is-active"))
    assert (tanim, etkin) == (1, 2), f"systemd birim tanımı {tanim} kez, etkinlik {etkin} kez yoklandı (beklenen 1 / 2)"
