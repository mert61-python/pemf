# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.15 (B-10.97) — `soak_http_ws` bellek sızıntısını ÖLÇEMEDİĞİNDE "TEMIZ" demiyor.

ARIZA: psutil yoksa ya da `PEMF_Backend` süreci bulunamazsa RSS 0 okunuyordu; oran 0 → sonuç
"TEMIZ" / 0 (bellek sızıntısı hiç ölçülmeden). Tek örnekte de 0 dönüyordu. RSS ölçülemezken ısınma
beklemesi 180 sn boşuna dönüyordu (ölçülemeyen şey oturmaz). Veri kökünü çözen ölü import D0Ö.19
(`a7a2b48`) ile düzeldi (kapı: `test_f4_rapor_soak_betikleri_CALISIYOR`).

KAPI: GERÇEK `main()`, sahte backend (`sahte_soak_backend`) + sahte psutil (hedef portu dinleyen süreç
YOK): "RSS OLCULMEDI" ve ≠0, TEMIZ DEĞİL; tek örnek → 1 ve "karar VERILEMEDI"; RSS ölçülemezken ısınma
beklenmez.
MUTASYON: RSS=0'da denetimi atlayıp TEMIZ dönmek → KIRMIZI.

⚠️ D0Ö.15 ek (bağımsız inceleme tur 4):
  · RSS süreci ADA göre seçiliyordu (`pemf_backend*`) — `--port` ile bağı yoktu. Hedef `python.exe`
    (kaynaktan dev backend) iken makinede başka bir PEMF_Backend koşuyorsa RSS O süreçten okunur, hedef
    ölçülmeden TEMIZ/0 çıkardı. Artık `--port`u LISTEN eden PID okunur; bulunamazsa ÖLÇÜLMEDİ.
  · Neden + eylem söylenir (psutil yok → `pip install psutil`; portu dinleyen süreç görülemedi);
    jeton ASCII `RSS OLCULMEDI` (günlükte tek jetonla aranabilir).
  · Ölçülmeyen RSS özet satırında "0.0 -> 0.0 MB (%+0.0)" diye ÖLÇÜLMÜŞ gibi basılmaz.
  · Isınma beklemesinin kendisi (254 → 2310 MB oturması) karşıt kanıtla pinlenir.
"""

from __future__ import annotations

import re
import sys
from types import SimpleNamespace

import pytest
from betik_alt_sureci import betik_modulu
from sahte_soak_backend import SahteBackend, kos, sahte_psutil, soak_modulu


def _ozet(cikti: str) -> str:
    """Kullanıcının GÖRDÜĞÜ karar bölümü. D0Ö.15 ek-2 (tur 5): koşu başındaki 'RSS OLCULEMIYOR … RSS
    OLCULMEDI olur' uyarısı karar satırı yerine iddiaları karşılıyordu (sabit anahtar alt-dize tuzağı)."""
    return cikti.split("=== OZET ===", 1)[1] if "=== OZET ===" in cikti else ""


def _sayac(metin: str, ad: str) -> int:
    m = re.search(rf"\b{ad} (\d+)", metin)
    assert m, f"'{ad} <n>' yok:\n{metin[-600:]}"
    return int(m.group(1))


def _kos(monkeypatch, capsys, psutil_fn, **kw) -> tuple[int, str, SahteBackend]:
    """`psutil_fn(hedef_port)` → sahte psutil (ya da None: psutil YOK)."""
    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend("tut")
    monkeypatch.setitem(sys.modules, "psutil", psutil_fn(sunucu.port))
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port, **kw)
    finally:
        sunucu.kapat()
    return rc, cikti, sunucu


def test_KRITIK_RSS_OLCULEMEZSE_TEMIZ_DEMEZ(monkeypatch, capsys):
    rc, cikti, sunucu = _kos(monkeypatch, capsys, lambda port: sahte_psutil("python.exe", 80.0))  # port dinlenmez
    ozet = _ozet(cikti)
    assert rc != 0 and "TEMIZ" not in cikti, f"RSS hiç ölçülmeden TEMIZ/0 (B-10.97, rc={rc}):\n{cikti[-800:]}"
    assert "RSS OLCULMEDI" in ozet and "RSS: OLCULMEDI" in ozet, f"karar bölümünde 'RSS OLCULMEDI' yok:\n{ozet}"
    assert "0.0 -> 0.0" not in cikti, f"ölçülmeyen RSS ölçülmüş %0 gibi basıldı:\n{cikti[-800:]}"
    bas = cikti.split("soak basladi", 1)[0]
    assert "KARAR VEREMEZ" in bas, f"koşunun RSS için karar veremeyeceği BAŞTA söylenmedi:\n{bas[-800:]}"
    # D0Ö.15 ek-2: ön-uçuş tek başına bir /ws yükseltmesi yapar — soak İZLEYİCİSİ ayrıca pinlenir.
    assert sunucu.ws_yukseltme_sayisi() >= 2 and _sayac(ozet, "baglanti") >= 1, f"soak /ws izleyicisi yok:\n{ozet}"


def test_KRITIK_RSS_HEDEF_PORTU_dinleyen_surecten_okunur(monkeypatch, capsys):
    """Hedef (python.exe, dev backend) sızdırıyor; makinede BAŞKA portta kararlı bir PEMF_Backend var.

    Ada göre seçen eski betik kararlı olanı okuyup TEMIZ/0 derdi — hedef hiç ölçülmeden."""

    def _psutil(port):
        # D0Ö.15 ek-2 (tur 5): ÇELDİRİCİ ÖNCE listelenir — gerçek psutil'de sıra keyfidir; hedef hep ilk
        # olsaydı "ilk LISTEN'i al" (port filtresi yok) mutantı bu kapıdan geçerdi.
        return sahte_psutil(
            "PEMF_Backend.exe", 500.0, port=port + 1, digerleri=(("python.exe", lambda n: 100.0 * 2**n, port),)
        )

    rc, cikti, _ = _kos(monkeypatch, capsys, _psutil)
    assert rc == 1 and "TEMIZ" not in cikti, f"hedefin sızıntısı görülmedi (rc={rc}):\n{cikti[-800:]}"
    assert "SIZINTI" in cikti, f"RSS hedef portu dinleyen süreçten okunmadı:\n{cikti[-800:]}"
    # D0Ö.22+15 ek-4 (tur 7): özetteki KAYNAK da çeldiriciyle ölçülür — yalnız bildirim port süzgecini kaybederse
    # (ada ya da ilk LISTEN'e göre seçerse) özet 4242'yi söylerken RSS 4243'ten okunurdu; iki kapı da yeşildi.
    assert "RSS kaynagi: PID 4243 (python.exe)" in _ozet(cikti), f"özette hedefin kaynağı yok:\n{_ozet(cikti)}"


def test_KRITIK_hedef_portu_dinleyen_surec_YOKSA_RSS_OLCULMEDI(monkeypatch, capsys):
    """Yalnız BAŞKA portta bir PEMF_Backend var: hedefin RSS'i ÖLÇÜLMEDİ (onunki değil)."""
    rc, cikti, _ = _kos(monkeypatch, capsys, lambda port: sahte_psutil("PEMF_Backend.exe", 500.0, port=port + 1))
    ozet = _ozet(cikti)
    assert rc == 1 and "TEMIZ" not in cikti, f"başka sürecin RSS'i hedefinki sayıldı (rc={rc}):\n{cikti[-800:]}"
    # Neden KARAR SATIRININ kendisinde (özetteki "RSS kaynagi" satırı da nedeni taşır; iddia onunla karşılanmasın).
    assert re.search(r"RSS OLCULMEDI — [^\n]*dinleyen", ozet), f"karar satırında neden söylenmedi:\n{ozet}"


def test_KRITIK_psutil_YOKSA_eylemi_SOYLER(monkeypatch, capsys):
    rc, cikti, _ = _kos(monkeypatch, capsys, lambda port: None)  # import psutil → ImportError
    ozet = _ozet(cikti)
    assert rc == 1 and "RSS OLCULMEDI" in ozet, f"(rc={rc}):\n{cikti[-800:]}"
    assert re.search(r"RSS OLCULMEDI — [^\n]*pip install psutil", ozet), f"karar satırında eylem yok:\n{ozet}"
    assert "RSS kaynagi: YOK" in ozet, f"özette RSS kaynağı (YOK + neden) basılmadı:\n{ozet}"


def test_KRITIK_veri_koku_REDDI_on_ucus_gibi_cikis_2(monkeypatch, capsys):
    """D0Ö.15 ek-2 (tur 5): `_veri_koku` soak BAŞLAMADAN düşerse (path_utils yüklenemez) bu da bir ön-uçuş
    reddidir — docstring sözleşmesi '2 = ön-uçuş reddi'; dize SystemExit eskiden 1 veriyordu ('en az bir
    neden' ile karışıyordu)."""
    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend("tut")
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0, port=sunucu.port))

    def _dusen_kok():
        raise SystemExit("HATA: utils.path_utils yuklenemedi (sahte) — veri koku bulunamaz")

    monkeypatch.setattr(m, "_veri_koku", _dusen_kok)
    try:
        rc, cikti = kos(m, monkeypatch, capsys, sunucu.port)
    finally:
        sunucu.kapat()
    assert rc == 2 and "soak basladi" not in cikti, f"veri kökü reddi ön-uçuş gibi değil (rc={rc}):\n{cikti}"
    # D0Ö.22+15 ek-3 (tur 6): NEDEN pinli — önceki her ön-uçuş reddi (health/HTTP/WS) de rc 2 + "soak basladi"
    # yok verir, kapı yanlış sebeple yeşil kalabilirdi; neden artık stdout'ta da (`> log` günlüğü).
    assert "Veri koku belirlenemedi" in cikti and "utils.path_utils yuklenemedi (sahte)" in cikti, (
        f"veri kökü reddinin nedeni stdout'ta yok:\n{cikti}"
    )


@pytest.mark.parametrize("hata", [PermissionError, FileNotFoundError, NotADirectoryError])
def test_KRITIK_veri_koku_OSError_da_EYLEMLI_on_ucus_reddi(monkeypatch, tmp_path, hata):
    """D0Ö.22+15 ek-3 (tur 6): `get_app_data_directory()` kökü mkdir'ler; izin/yol hatası (OSError) SystemExit'e
    çevrilmiyor, soak traceback + çıkış 1 ile bitiyordu ('en az bir neden' ile karışır). Artık eylem söyleyen
    SystemExit → `main` bunu ön-uçuş reddi (2) sayar. Gerçek kök OLUŞTURULMAZ: ürün çağrısı yamalı, PROGRAMDATA tmp.
    D0Ö.22+15 ek-4 (tur 7): yalnız PermissionError sınanıyordu — `except PermissionError` daraltması yeşildi;
    olmayan sürücü (FileNotFoundError) ve dosya engeli (NotADirectoryError) da aynı sınıf."""
    import utils.path_utils as pu

    m = betik_modulu("soak_http_ws")
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))

    def _acilamaz():
        raise hata(13, "d0o: kok acilamadi", str(tmp_path / "kisitli" / "PEMF_GUI"))

    monkeypatch.setattr(pu, "get_app_data_directory", _acilamaz)
    with pytest.raises(SystemExit) as e:
        m._veri_koku()
    assert isinstance(e.value.code, str) and "APPDATA yazilabilir mi" in e.value.code, f"eylem yok: {e.value.code!r}"
    assert hata.__name__ in e.value.code, f"neden (hata türü) yok: {e.value.code!r}"


def test_KRITIK_veri_koku_TARANAMAZSA_da_EYLEMLI_on_ucus_reddi(monkeypatch, tmp_path):
    """D0Ö.22+15 ek-4 (tur 7): aday taraması sarılı değildi — listelenemeyen bir kök (ör. ACL'li
    %PROGRAMDATA%\\PEMF_System) `is_dir`/`glob`'da PermissionError atıp yine traceback + 1 veriyordu."""
    import pathlib

    import utils.path_utils as pu

    m = betik_modulu("soak_http_ws")
    pd = tmp_path / "pd"
    monkeypatch.setenv("PROGRAMDATA", str(pd))
    monkeypatch.setattr(pu, "get_app_data_directory", lambda: tmp_path / "kullanici" / "PEMF_GUI")
    gercek_is_dir = pathlib.Path.is_dir

    def _is_dir(self):
        if "PEMF_System" in str(self):
            raise PermissionError(13, "d0o: listelenemez", str(self))
        return gercek_is_dir(self)

    monkeypatch.setattr(pathlib.Path, "is_dir", _is_dir)
    with pytest.raises(SystemExit) as e:
        m._veri_koku()
    assert isinstance(e.value.code, str) and "taranamadi (PermissionError" in e.value.code, f"{e.value.code!r}"


def test_KRITIK_veri_koku_RET_SATIRI_cp1254_KONSOLDA_da_cikis_2(monkeypatch):
    """D0Ö.22+15 ek-4 (tur 7): ret NEDENİ (istisna metni + yol) stdout'a da basılıyor; cp1254'e yönlendirilmiş
    (katı) stdout'ta cp1254 dışı bir karakter UnicodeEncodeError ile ret satırını ve çıkış 2'yi düşürüyordu
    (traceback + 1). Kapı gerçek `main`i cp1254-katı bir stdout ile koşturur.

    ⚠️ D0Ö.22+15 ek-5 (tur 7 kontrolü): `capsys` İSTENMEZ — capsys + `monkeypatch.setattr(sys, "stdout", …)`
    birlikteyken söküm sırası (önce capsys, sonra monkeypatch) `sys.stdout`'u KAPANMIŞ capsys akışına geri
    yüklüyordu; varsayılan yakalama bunu maskeliyor, `pytest -s`'te sonraki testler ve pytest'in özeti bozuluyordu."""
    import io

    m = soak_modulu(monkeypatch)
    sunucu = SahteBackend("tut")
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", 500.0, port=sunucu.port))

    def _dusen_kok():
        raise SystemExit("HATA: veri koku acilamadi (PermissionError: Журнал) — sahte")

    monkeypatch.setattr(m, "_veri_koku", _dusen_kok)
    ham = io.BytesIO()
    konsol = io.TextIOWrapper(ham, encoding="cp1254", errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stdout", konsol)
    monkeypatch.setattr(
        sys, "argv", ["soak_http_ws.py", "--port", str(sunucu.port), "--dakika", "0.06", "--aralik", "1.0"]
    )
    try:
        rc = m.main()
    finally:
        sunucu.kapat()
    konsol.flush()
    cikti = ham.getvalue().decode("cp1254")
    assert rc == 2, f"cp1254 konsolda ret satırı çıkışı bozdu (rc={rc})"
    assert "Veri koku belirlenemedi" in cikti and "?????" in cikti, f"ret satırı basılmadı/kodlanmadı:\n{cikti}"


@pytest.mark.parametrize(
    ("hata_kodu", "tur"),
    [
        ("raise RuntimeError('d0o: bozuk kurulum')", "RuntimeError"),
        # D0Ö.22+15 ek-4 (tur 7): gerçek Windows örneği ImportError'dur (ModuleNotFoundError DEĞİL) — eski kod onu
        # yakalıyor ama "yuklu degil / pip install" (yanlış eylem) diyordu; `except ImportError` mutantı yeşildi.
        ("raise ImportError('DLL load failed while importing _psutil_windows: d0o')", "ImportError"),
    ],
    ids=["runtimeerror", "dll_importerror"],
)
def test_KRITIK_BOZUK_psutil_importu_RSS_OLCULEMEZ_nedeni_olur(monkeypatch, tmp_path, hata_kodu, tur):
    """D0Ö.22+15 ek-3 (tur 6): kurulu ama bozuk psutil'in import hatası traceback + çıkış 1 veriyordu (RuntimeError)
    ya da yanlış eylem söylüyordu (DLL = ImportError → "yuklu degil"). Artık "RSS ölçülemez" nedeni + doğru eylem."""
    (tmp_path / "psutil.py").write_text(hata_kodu + "\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "psutil", raising=False)
    m = betik_modulu("soak_http_ws")
    surec, neden = m._port_sureci(1)
    assert surec is None and f"psutil yuklenemedi ({tur}" in neden, f"bozuk psutil nedeni yok: {neden!r}"
    assert "force-reinstall" in neden and "yuklu degil" not in neden, f"eylem yanlış: {neden!r}"


def test_KRITIK_tek_ornekte_cikis_SIFIR_DEGIL(monkeypatch, capsys):
    rc, cikti, _ = _kos(
        monkeypatch, capsys, lambda port: sahte_psutil("PEMF_Backend.exe", 500.0, port=port), dakika=0.03, aralik=30.0
    )
    # D0Ö.15 ek: yalnız "≠0" değil — ön-uçuş (rc=2) gibi başka bir erken çıkış bu kapıyı yeşil tutmasın.
    assert rc == 1, f"tek örnekle karar verilemez ama çıkış {rc} (B-10.97):\n{cikti[-600:]}"
    assert "soak basladi" in cikti and "karar VERILEMEDI" in cikti, f"tek-örnek dalı değil:\n{cikti[-600:]}"
    # D0Ö.22 ek: erken dönüş yolunda da WS sayaçları basılır (eskiden bu yolda WS özeti hiç yoktu).
    assert "baglanti" in cikti and "KOPMA" in cikti, f"tek örnek yolunda WS özeti yok:\n{cikti[-600:]}"


def _sahte_saat(m, monkeypatch) -> list[float]:
    saat = {"t": 0.0}
    uykular: list[float] = []

    def _uyu(sn):
        uykular.append(sn)
        saat["t"] += sn

    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=lambda: saat["t"], sleep=_uyu))
    return uykular


def test_KRITIK_RSS_OLCULEMEZKEN_isinma_BEKLENMEZ(monkeypatch):
    m = betik_modulu("soak_http_ws")
    monkeypatch.setitem(sys.modules, "psutil", sahte_psutil("python.exe", 80.0))
    uykular = _sahte_saat(m, monkeypatch)
    m._rss_oturmasini_bekle(8082, azami_sn=30.0)
    assert not uykular, f"RSS ölçülemezken {sum(uykular):.0f} sn ısınma beklendi (ölçülemeyen şey oturmaz)"


def test_KARSIT_KANIT_olculebilir_RSS_te_isinma_BEKLENIR_ve_OTURMUS_deger_doner(monkeypatch):
    """D0Ö.15 ek: ısınmayı atlayan mutant (koşulsuz erken dönüş) tüm kapılarda yeşil kalıyordu — oysa
    254 MB'lık health-anı değeri taban alınırsa AI ısınması (→ 2310 MB, +%809) SIZINTI sanılır."""
    m = betik_modulu("soak_http_ws")
    seri = [254.0, 2310.0, 2310.0, 2310.0, 2310.0, 2310.0]
    monkeypatch.setitem(
        sys.modules, "psutil", sahte_psutil("PEMF_Backend.exe", lambda n: seri[min(n, len(seri) - 1)], port=8082)
    )
    uykular = _sahte_saat(m, monkeypatch)
    oturmus = m._rss_oturmasini_bekle(8082, azami_sn=180.0, kararli_tur=3)
    assert oturmus == 2310.0, f"oturmuş RSS değil ısınma-öncesi değer döndü: {oturmus}"
    assert sum(uykular) >= 15.0, f"ısınma beklenmedi ({sum(uykular):.0f} sn)"
