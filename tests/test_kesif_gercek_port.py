# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KEŞİF KANALLARI PORTU `8000` SABİT YAYINLIYORDU, GERÇEK PORT DİNAMİK (denetim 2026-08-17).

Üç yayıncı da portu sabit `8000` olarak duyuruyordu:
  · mDNS `_pemfvet` kaydı (`servers/api_server` lifespan)
  · `/api/discovery` yanıtı (`servers/system_router`)
  · Bulut cihaz-kaydı satırı (`servers/sync_worker` → Supabase `devices`)

Oysa gerçek port dinamik: launcher boş port arıyor (`find_free_port`) ve `deploy/staging.env`
`8010` veriyor. 8000 MEŞGULKEN telefon YANLIŞ porta bağlanır; `checkHealth` onu eler ve keşif
merdiveni bir sonraki basamağa düşer → ilk bağlanma saniyelerden ~70 sn'ye (subnet taraması) çıkar.

⚠️ VARSAYILAN 8000 KORUNDU: `PEMF_API_PORT` yok/bozuksa yine `8000` dönülür — launcher
`DEFAULT_PORT` ve Supabase RPC'sinin `coalesce(p_api_port, 8000)` sözleşmesi bozulmaz.
"""

import ast
import os
import pathlib

os.environ.pop("PEMF_SIMULATE", None)

import pytest

from servers.auto_discovery import get_api_port

# ── 1) Tek gerçek kaynak: PEMF_API_PORT ──────────────────────────────────────


def test_KRITIK_gercek_port_env_den_okunur(monkeypatch):
    monkeypatch.setenv("PEMF_API_PORT", "8010")
    assert get_api_port() == 8010, "gercek port yok sayiliyor -> telefon YANLIS porta baglanir"


@pytest.mark.parametrize("deger", ["", "   ", "abc", "0", "-1", "70000", "80.5"])
def test_KARSIT_KANIT_bozuk_deger_8000e_duser(monkeypatch, deger):
    """⚠️ SÖZLEŞME: bilinmiyor/bozuksa 8000. Launcher `DEFAULT_PORT` ve Supabase
    `coalesce(p_api_port, 8000)` buna bağlı."""
    monkeypatch.setenv("PEMF_API_PORT", deger)
    assert get_api_port() == 8000, f"bozuk deger {deger!r} icin varsayilan 8000 DEGIL"


def test_KARSIT_KANIT_env_YOKSA_8000(monkeypatch):
    monkeypatch.delenv("PEMF_API_PORT", raising=False)
    assert get_api_port() == 8000


def test_publish_bind_port_env_i_YAZAR(monkeypatch):
    """`publish_bind_host`un kardeşi: gerçekten dinlenen port tek kaynağa yazılmalı.

    ⚠️ `main()` tüm servisi ayağa kaldırdığı için testten çağrılamaz; bu sözleşme tek başına
    sınanabilir olduğu için AYRI fonksiyon (kardeşinde de aynı gerekçe yazılı)."""
    import backend_service as bs

    monkeypatch.delenv("PEMF_API_PORT", raising=False)
    assert bs.publish_bind_port(8123) == 8123
    assert os.environ["PEMF_API_PORT"] == "8123"
    assert get_api_port() == 8123, "yayinlanan port kesif tarafindan OKUNMUYOR"


# ── 2) Üç yayıncı da SABİT 8000 yazmamalı ────────────────────────────────────
#
# ⚠️ `ast` TABANLI: üçü de servis/lifespan/thread içinde çalıştığı için çağrılarak sınanamaz.
# `ast` yorumları ve docstring'i düğüm olarak GÖRMEZ → kapı kendi yorumuyla kandırılamaz.
# ⚠️ Kaynak IMPORT EDİLEN dosyadan okunur (sabit yol değil) — modül taşınırsa kapı kör kalmaz.


def _agac(modul):
    return ast.parse(pathlib.Path(modul.__file__).read_text(encoding="utf-8"))


def test_KRITIK_mDNS_kaydi_SABIT_port_yayinlamaz():
    from servers import api_server

    cagrilar = [
        d
        for d in ast.walk(_agac(api_server))
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "start_mdns"
    ]
    assert cagrilar, "start_mdns cagrisi bulunamadi -> kapi BAYAT"
    for c in cagrilar:
        for kw in c.keywords:
            if kw.arg != "port":
                continue
            assert not isinstance(kw.value, ast.Constant), (
                f"mDNS SABIT port yayinliyor ({getattr(kw.value, 'value', '?')}) -> 8000 mesgulken "
                "telefon YANLIS porta baglanir"
            )


@pytest.mark.parametrize(
    "modul_adi, alan",
    [("servers.system_router", "port"), ("servers.sync_worker", "api_port")],
)
def test_KRITIK_kesif_yaniti_SABIT_port_yayinlamaz(modul_adi, alan):
    """`/api/discovery` ve bulut cihaz-kaydı satırı sabit sayı taşımamalı."""
    import importlib

    mod = importlib.import_module(modul_adi)
    sabitler = []
    for d in ast.walk(_agac(mod)):
        if not isinstance(d, ast.Dict):
            continue
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and k.value == alan and isinstance(v, ast.Constant):
                sabitler.append(v.value)

    assert not sabitler, (
        f"{modul_adi} '{alan}' alanini SABIT yayinliyor ({sabitler}) -> gercek port dinamik "
        "(launcher bos port arar, staging 8010 verir)"
    )


def test_KRITIK_main_gercek_portu_YAYINLAR():
    """`main()` `publish_bind_port`u ÇAĞIRMALI — kardeşi `publish_bind_host` gibi.

    ⚠️ Bu kapı ayrı gerekiyordu: yukarıdaki test fonksiyonu DOĞRUDAN çağırıyor, dolayısıyla
    `main()`teki çağrıyı silen bir mutasyon sessizce geçiyordu (ölçüldü). `main()` tüm servisi
    ayağa kaldırdığı için çalıştırılamaz → `ast`.
    ⚠️ Yorumlar düğüm DEĞİL: "burada publish_bind_port çağrılmalı" yazan bir yorum geçemez."""
    import backend_service as bs

    fnler = [n for n in ast.walk(_agac(bs)) if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert len(fnler) == 1, "main() bulunamadi (yeniden adlandirilmis?) -> kapi KOR kalirdi"

    adlar = {c.func.id for c in ast.walk(fnler[0]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "publish_bind_host" in adlar, "on-kosul: kardes cagri da yok, kapi yanlis yere bakiyor"
    assert "publish_bind_port" in adlar, (
        "main() gercek portu YAYINLAMIYOR -> PEMF_API_PORT bos kalir ve kesif kanallari 8000'e "
        "duser; launcher bos port aradiginda telefon YANLIS porta baglanir"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
