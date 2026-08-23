# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PROFIL PAKETI KURULUM KOKUNDEKI DURUM DOSYALARINI EZEMEZ (denetim 2026-08-23, bulgu C1).

⚠️ BU LISTE UC KEZ ESKIDI — kapi bu yuzden ADLARI DEGIL, KAYNAGI olcuyor.

Profil (model) zip'leri `install_root`'a acilir. `extract.rs::PROFILE_FORBIDDEN_TOP` hangi ust-duzey
girdilerin EZILEMEYECEGINI sayar. Liste 2026-08-04'te (#104) kurulmus, sonra iki kez genisletilmis
(selfupdate_attempt.json, auth_session.bin) — ama 2026-08-08/09'da eklenen UC durum dosyasi
(`installed_packages.json`, `install_id.txt`, `backup_dir.txt`) ve UC sahneleme dizini
(`runtime.new/old/bozuk`) hic islenmemisti.

EN AGIRI `installed_packages.json`: `pending_updates` "bayat mi guncel mi" kararini TAM ondan okur
(`flow.rs::read_installed_packages` → sha karsilastirmasi). Kok seviyeye manifest sha'larini iceren
bir kopya koyan profil zip'i cihazi sonsuza dek "guncel" gosterir — **`min_supported_version` GERI
CAGIRMASI dahil** hicbir runtime yamasi bir daha uygulanmaz (`zorunlu` bayragi yalniz rollout
erken-donusunu ezer, sha kiyasini DEGIL). Yani bobin-guvenligi duzeltmesi tasiyan bir yayin o
cihaza HIC ULASMAZ ve kullaniciya hicbir belirti yansimaz.

`runtime.old` ise GERI DONUS YOLUDUR: ezilirse saglik kapisi dustugunde donulecek surum yok olur.

SOZLESME: kurulum kokundeki HER girdi ya yasak-listede olmali ya da ACIKCA mesru sayilmali.
Tek mesru istisna `ai_models` — profil paketlerinin hedefi zaten orasi.

⚠️ NEDEN IZIN-LISTESI DEGIL: `extract.rs`'in kendi yorumu (#104) kati bir `ai_models/` onek
zorunlulugunun "mesru bir paketi kirabilecegini" soyleyip yasak-listeyi bilerek secmis. O karara
dokunulmadi; bunun yerine listenin ESKIMESI engellendi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_EXTRACT = _KOK / "launcher" / "core" / "src" / "extract.rs"
_INSTALL = _KOK / "launcher" / "core" / "src" / "install.rs"
_FLOW = _KOK / "launcher" / "core" / "src" / "flow.rs"
_NSI = _KOK / "launcher" / "app" / "windows" / "hooks.nsi"

# Profil paketlerinin MESRU hedefi — yasak-listede OLMAMALI.
_MESRU_HEDEF = {"ai_models"}


def _yasak_liste() -> set[str]:
    """`extract.rs`'in fiilen uyguladigi yasak liste (kaynak neyse o)."""
    src = _EXTRACT.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"PROFILE_FORBIDDEN_TOP[^=]*=\s*(?:&)?\[(.*?)\];", src, re.S)
    assert m, "PROFILE_FORBIDDEN_TOP bulunamadi — bicim degismis olabilir"
    return {x.lower() for x in re.findall(r'"([^"]+)"', m.group(1))}


def _kok_girdileri() -> set[str]:
    """Kurulum kokunde GERCEKTEN yasayan girdiler — kodun kendisinden turetilir."""
    girdiler: set[str] = set()
    for dosya in (_INSTALL, _FLOW):
        src = dosya.read_text(encoding="utf-8", errors="replace")
        girdiler |= set(re.findall(r'install_root\.join\("([^"]+)"\)', src))
    assert len(girdiler) > 8, f"kok girdileri cikarilamadi ({girdiler}) — desen degismis olabilir"
    return girdiler


def test_KRITIK_kok_durum_dosyalarinin_HEPSI_yasak_listede():
    """🔴 ASIL KAPI: yeni bir durum dosyasi eklenip listeye islenmezse BURASI kirmizi verir."""
    eksik = sorted(g for g in _kok_girdileri() if g not in _MESRU_HEDEF and g.lower() not in _yasak_liste())
    assert not eksik, (
        f"kurulum kokundeki su girdiler profil paketi tarafindan EZILEBILIR: {eksik}\n"
        "  · installed_packages.json ezilirse cihaz sonsuza dek 'guncel' gorunur — GERI CAGIRMA dahil\n"
        "    hicbir yama ulasmaz;\n"
        "  · install_id.txt ezilirse cihaz kademeli yayin diliminde sabitlenebilir;\n"
        "  · runtime.old ezilirse saglik kapisi dustugunde DONULECEK SURUM kalmaz.\n"
        "extract.rs::PROFILE_FORBIDDEN_TOP listesine ekleyin."
    )


def test_KARSIT_KANIT_profil_hedefi_ai_models_YASAKLANMAZ():
    """Kapi asiri genislemesin: profil paketleri `ai_models/` altina yazabilmeli, yoksa
    profil kurulumunun kendisi olurdu."""
    assert "ai_models" not in _yasak_liste(), (
        "ai_models yasaklanmis — profil paketleri kendi hedeflerine yazamaz, profil kurulumu OLUR"
    )


def test_KRITIK_yasak_liste_bosaltilamaz():
    """Listenin VARLIGI degil DOLULUGU olculur (bosaltmak sessizce korumayi kaldirirdi)."""
    liste = _yasak_liste()
    for zorunlu in ("runtime", "cache", "installed_profiles.json", "backend.port"):
        assert zorunlu in liste, f"`{zorunlu}` yasak listeden DUSMUS — #104 korumasi geriledi"


def test_KALDIRMA_listesi_ile_ES_tutulur():
    """`hooks.nsi` silme listesi ile ayni kume — dosyanin kendi kurali bunu sart kosuyor
    ("Yeni bir durum dosyasi eklenirse BURAYA da eklenmeli (ayni kume:
    extract.rs::PROFILE_FORBIDDEN_TOP)").

    ⚠️ Es-tutma TEK YONLUDUR: kaldirmanin silmesi gereken her KOK DOSYASI listede olmali.
    Dizinler (`runtime`, `cache`, `ai_models`) NSIS'te `RMDir /r` ile ayri satirlarda gectigi
    ve `auth_session.bin` gibi bazi girdiler `install_root.join` ile uretilmedigi icin kume
    kok girdilerinden turetilir.
    """
    nsi = _NSI.read_text(encoding="utf-8", errors="replace")
    kok = _kok_girdileri()
    # Yalniz DOSYA girdileri (uzantili) — dizinler RMDir /r ile ayri ele aliniyor.
    dosyalar = sorted(g for g in kok if "." in g and not g.startswith("runtime."))
    eksik = [d for d in dosyalar if d not in nsi]
    assert not eksik, (
        f"hooks.nsi kaldirma listesi eskimis: {eksik} — ozyinelemesiz `RMDir \"$INSTDIR\"` "
        "bos olmayan dizinde BASARISIZ olur ve kurulum koku artikla geride kalir "
        "(ayni hata 2026-08-04, 08-06 ve 08-23'te uc kez tekrarlandi)"
    )


@pytest.mark.parametrize("sahne", ["runtime.new", "runtime.old", "runtime.bozuk"])
def test_SAHNELEME_dizinleri_kaldirmada_SILINIR(sahne):
    """Kesintiden kalan sahneleme dizinleri (her biri <=1,19 GB) hicbir yolla silinmiyordu."""
    nsi = _NSI.read_text(encoding="utf-8", errors="replace")
    assert f'RMDir /r "$INSTDIR\\{sahne}"' in nsi, (
        f"{sahne} kaldirmada silinmiyor — 'Uygulama verisini sil' isaretli olsa bile GB'larca "
        "artik diskte kalir ve kurulum koku silinemez"
    )
