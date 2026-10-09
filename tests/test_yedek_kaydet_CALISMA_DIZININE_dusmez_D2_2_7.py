# -*- coding: utf-8 -*-
"""D2-2.7 (2-D incelemesi A2 · K6) — E01 `kaydet`: kliniğin TAMAMININ şifreli yedeği masaüstü bulunamayınca backend'in ÇALIŞMA DİZİNİNE
yazılıp "oluşturuldu ve doğrulandı" denmez. [KARAR — önerilen seçenek]

ÖLÇÜLEN KUSUR [ÖLÇTÜM sonda k6, GERÇEK `masaustu_dizini`]: kullanıcı evinde `Desktop` yokken (yönlendirilmiş Bilinen Klasör) ve servis
hesabında (`systemprofile` — NSSM LocalSystem kurulumu, A-11) dosya `Path.cwd()`e düşüyor: launcher backend'i `<kurulum>\\runtime\\
PEMF_Backend` çalışma diziniyle başlatır (`launcher/core/src/backend.rs:470-474`), runtime güncellemesi o dizini `runtime.old`a taşıyıp
sağlık kapısından sonra SİLER (`install.rs:517-520`), kaldırma `remove_install` kökü siler (`install.rs:1376-1382`); NSSM'de çalışma dizini
`AppDirectory` (= exe/kurulum dizini, `scripts/setup_services.ps1:408`). Yanıt 200 `dogrulandi=True`, arayüz tostu "Yedek oluşturuldu ve
doğrulandı: …\\runtime\\PEMF_Backend\\pemf-vet-yedek-….pemfbak" — operatör yedeği olduğunu sanır, ilk güncellemede yedek yok olur.

ÖNERİLEN (a): masaüstü bulunamazsa `%PUBLIC%\\Desktop` (Ortak Masaüstü — oturum açan her kullanıcının masaüstünde görünür; güncelleme /
kaldırma dokunmaz); o da yoksa YAZILMAZ (500 "yedek OLUŞTURULMADI"). Alternatifler: (b) her durumda reddet (409) ve arayüz indirmeye düşsün
(arayüz kolu gerekir); (c) veri kökünde `Disa_Aktarim\\` (güncellemeden etkilenmez, tam temizlik siler); (d) bugünkü gibi + tostta uyarı.
Kapı seçenekten bağımsız DEĞİŞMEZİ ölçer: dosya çalışma dizinine yazılmaz ve orada "doğrulandı" denmez.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from veri_tasima_aparati import PAROLA, cihaz_kur, doldur, istekler, kapat, uclari_bagla


@pytest.fixture
def k(tmp_path, monkeypatch):
    from servers import api_server as api
    from servers import seans_alan_kaydi as sak

    monkeypatch.setattr(sak, "masaustu_dizini", sak._orijinal_masaustu_dizini)  # ÜRÜN mantığı
    tdb, hdb = cihaz_kur(monkeypatch, tmp_path / "veri")
    uclari_bagla(monkeypatch, tdb, hdb)
    doldur(tdb, hdb, ["Mia"], seans_basi=1)
    calisma = tmp_path / "kurulum" / "runtime" / "PEMF_Backend"
    calisma.mkdir(parents=True)
    monkeypatch.chdir(calisma)
    ortak = tmp_path / "Public"
    (ortak / "Desktop").mkdir(parents=True)
    monkeypatch.setenv("PUBLIC", str(ortak))  # gerçek C:\Users\Public'e ASLA yazılmaz
    try:
        yield type(
            "K", (), {"api": api, "tmp": tmp_path, "calisma": calisma, "ortak": ortak / "Desktop", "mp": monkeypatch}
        )
    finally:
        kapat(tdb, hdb)


@pytest.mark.parametrize("ev_turu", ["masaustu_yok", "servis_hesabi"])
def test_KRITIK_D2_2_7_masaustu_yokken_tum_klinik_yedegi_CALISMA_DIZININE_yazilmaz(k, ev_turu):
    ev = k.tmp / ("Windows/System32/config/systemprofile" if ev_turu == "servis_hesabi" else "ev")
    ev.mkdir(parents=True)
    k.mp.setenv("USERPROFILE", str(ev))
    (r,) = istekler(k.api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
    g = r.json()
    calismada = sorted(p.name for p in k.calisma.iterdir())
    assert not calismada, (
        f"{ev_turu}: tüm-klinik yedeği backend ÇALIŞMA DİZİNİNE yazıldı ({calismada}) — runtime güncellemesi/kaldırma onu siler; "
        f"yanıt {r.status_code} dogrulandi={g.get('dogrulandi')} yol={g.get('yol')}"
    )
    if r.status_code == 200:
        yol = Path(g["yol"])
        assert yol.parent == k.ortak and yol.is_file(), f"yedek beklenmeyen yerde: {yol}"


def test_KARSIT_D2_2_7_masaustu_VARSA_bugunku_gibi_kullanici_masaustune(k):
    ev = k.tmp / "ev_masaustlu"
    (ev / "Desktop").mkdir(parents=True)
    k.mp.setenv("USERPROFILE", str(ev))
    (r,) = istekler(k.api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
    assert r.status_code == 200 and Path(r.json()["yol"]).parent == ev / "Desktop"
    assert list(k.ortak.iterdir()) == [] and list(k.calisma.iterdir()) == []


def test_KRITIK_D2_2_7_ORTAK_masaustu_de_YOKSA_yazilmaz_ve_OLUSTURULMADI_der(k):
    """Orkestratör eki (2-D incelemesi): masaüstü bulunamaz VE Ortak Masaüstü de yoksa yedek HİÇBİR yere yazılmaz, yanıt 500 "OLUŞTURULMADI".
    Bu kol yukarıdaki testte koşmuyordu: aparat Ortak Masaüstü'nü hep kuruyordu ("ortak yoksa çalışma dizinine yaz" mutantı yeşil kalıyordu —
    ölçüldü)."""
    import shutil

    shutil.rmtree(k.ortak)
    ev = k.tmp / "ev_masaustusuz"
    ev.mkdir(parents=True)
    k.mp.setenv("USERPROFILE", str(ev))
    (r,) = istekler(k.api.app, [("POST", "/api/data/export", {"passphrase": PAROLA, "kaydet": True}, None)])
    calismada = sorted(p.name for p in k.calisma.iterdir())
    assert not calismada, (
        f"Ortak Masaüstü yokken yedek ÇALIŞMA DİZİNİNE yazıldı ({calismada}); yanıt {r.status_code} {r.text[:200]}"
    )
    assert r.status_code == 500 and "OLUŞTURULMADI" in r.json().get("detail", ""), f"{r.status_code} {r.text[:200]}"
