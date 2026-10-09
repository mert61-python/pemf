# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.80 (B-3.13 · B-3.52; = O-2A.3 / O-A2-1.c) — sır dosyasının OKUMA İZNİ hatası "bozuk dosya" sayılmaz; dizin
sertleştirmesi önbellek denetiminden SONRA ve geri çekilmeli koşar.

B-3.13: `_load` HER okuma istisnasını "BOZUK" sayıp `pemf_secrets.json`u `.corrupt.<zaman>` adına taşıyordu. Yükseltilmemiş
(launcher) süreçte dosyanın DACL'i süreci dışarıda bırakınca (ör. başka hesabın/servisin kilidi) okuma `PermissionError`
(WinError 5) verir; dosya SAĞLAM olduğu hâlde, üst dizin yazılabilir olduğundan (FILE_DELETE_CHILD) yeniden adlandırma
TUTAR → sonraki her açılışta "karantina kanıtı var" → cihaz yönetici ACL'yi düzeltip karantina dosyasını elle geri koyana
dek AÇILMAZ ve ileti yanlış eylem önerir ("yedekten geri yükleyin"). Artık: izin/G-Ç hatası → dosyaya dokunulmaz,
`RuntimeError` "erişim reddedildi" + doğru eylem; JSON gerçekten bozuksa bugünkü kenara alma SÜRER (Karar 6).

B-3.52: `_ensure_dir_hardened` önbellek denetiminden ÖNCE koşuyordu; sertleştirme başarısızken (LocalSystem'de D-3.1 yüzünden
bugün etkin) HER `get_secret` küresel kilit altında `icacls` (10 sn zaman aşımı) çağırıyordu. Artık önbellek doluysa hiç
denenmez; başarısız denemeden sonra 60 sn geri çekilir.

Arıza GERÇEK biçimiyle kurulur: dosyanın/dizinin DACL'i `icacls` ile VAR OLAN başka bir SID'e (S-1-5-19 LOCAL SERVICE)
verilir — süreç gerçek `PermissionError` (WinError 5) alır; `finally`de `icacls /reset` ve erişimin geri geldiği ölçülür.
İkinci Windows hesabı / grup OLUŞTURULMAZ. Taklit istisna sınıfı (ör. `FileExistsError`) kapıyı kör bırakır (2-A A2-1.4).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL (icacls) yalnız Windows")

_YABANCI_SID = "*S-1-5-19"  # NT AUTHORITY\LOCAL SERVICE — her Windows'ta VAR; test süreci bu SID değil


def _icacls(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["icacls", *[str(a) for a in args]], capture_output=True, text=True, timeout=60)


def _gecerli_doc() -> dict:
    return {
        "_comment": "test",
        "_version": 1,
        "auto": {"api_token": "SAHTE-API-TOKEN-D280"},
        "operator": {"tunnel_hostname": "sahte.ornek"},
        "embedded": {},
    }


@pytest.fixture()
def sm(tmp_path, monkeypatch):
    from utils import secrets_manager as _sm

    veri = tmp_path / "PEMF_GUI"
    veri.mkdir()
    monkeypatch.setattr(_sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(_sm, "_cache", None)
    monkeypatch.setattr(_sm, "_dir_hardened", True)  # dizin sertleştirmesi bu kollarda konu DEĞİL (D/E/F ayrıca ölçer)
    return _sm


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_KRITIK_okuma_IZNI_reddedilince_dosya_YERINDE_kalir_ve_erisim_reddedildi_denir_D280(sm, tmp_path):
    """Dosyanın DACL'i süreci dışarıda bırakır (yalnız LOCAL SERVICE); üst dizin sürecin elinde. Bugün: "okunamadi/BOZUK …
    bozuk kopya .corrupt olarak saklandi, yedekten geri yukleyin" (yeniden adlandırma tutmasa bile — ölçüldü). Beklenen: eylem
    söyleyen `PermissionError` "erişim reddedildi" (tür BİLEREK OSError ailesi: çağıranlar `RuntimeError`'ı "çözülemez/brick"
    diye sınıflar); dosya AYNI yerde, AYNI baytlarla; `.corrupt.*` YOK; önbellek dolmaz."""
    p = tmp_path / "PEMF_GUI" / "pemf_secrets.json"
    p.write_text(json.dumps(_gecerli_doc()), encoding="utf-8")
    once = _sha(p)
    r = _icacls(p, "/inheritance:r", "/grant:r", f"{_YABANCI_SID}:(F)")
    assert r.returncode == 0, f"aparat: DACL kurulamadı: {r.stdout}{r.stderr}"
    try:
        with pytest.raises(PermissionError):
            p.read_bytes()  # aparat kanıtı: süreç dosyayı GERÇEKTEN okuyamıyor (WinError 5)
        with pytest.raises(PermissionError) as exc:
            sm._load()
        assert "erişim reddedildi" in str(exc.value).lower(), f"ileti erişim reddini söylemiyor: {exc.value}"
        assert "yedekten" not in str(exc.value).lower(), "ileti yanlış eylem öneriyor (dosya bozuk değil)"
        assert not list(p.parent.glob("pemf_secrets.json.corrupt.*")), "SAĞLAM sır dosyası BOZUK sayılıp kenara alındı"
    finally:
        for q in p.parent.glob("pemf_secrets.json*"):  # kenara alınmış kopya da kilitli DACL taşır — geride bırakma
            _icacls(q, "/reset")
    assert p.exists(), "sır dosyası yerinde değil"
    assert _sha(p) == once, "sır dosyasının baytları değişti"
    assert sm._cache is None, "okunamayan dosya için önbellek dolduruldu (boş belge kalıcı sanılır)"


def _kendi_sid() -> str:
    r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip().split(",")[-1].strip().strip('"')


def test_KRITIK_okunamayan_ama_SILINEBILEN_sir_dosyasi_yeniden_ADLANDIRILMAZ_D280(sm, tmp_path):
    """B-3.13'ün yeniden adlandırma belirtisi GERÇEK ACL ile: dosyanın DACL'i süreç hesabına yalnız DELETE verir (okuma
    YOK) — okuma WinError 5 verir, yeniden adlandırma TUTAR. Bugün sağlam dosya `.corrupt.<zaman>` adına taşınır ve sonraki
    her açılış "karantina kanıtı var" ile kalıcı kapalı kalır. Beklenen: dosya yerinde, `.corrupt.*` YOK."""
    p = tmp_path / "PEMF_GUI" / "pemf_secrets.json"
    p.write_text(json.dumps(_gecerli_doc()), encoding="utf-8")
    once = _sha(p)
    sid = _kendi_sid()
    assert sid.startswith("S-1-"), f"aparat: süreç SID'i okunamadı: {sid!r}"
    r = _icacls(p, "/inheritance:r", "/grant:r", f"{_YABANCI_SID}:(F)", "/grant:r", f"*{sid}:(D)")
    assert r.returncode == 0, f"aparat: DACL kurulamadı: {r.stdout}{r.stderr}"
    try:
        with pytest.raises(PermissionError):
            p.read_bytes()  # aparat kanıtı: okuma GERÇEKTEN reddediliyor
        with pytest.raises(PermissionError) as exc:
            sm._load()
        assert "erişim reddedildi" in str(exc.value).lower(), f"ileti erişim reddini söylemiyor: {exc.value}"
        karantina = list(p.parent.glob("pemf_secrets.json.corrupt.*"))
        assert not karantina, f"SAĞLAM sır dosyası BOZUK sayılıp kenara alındı: {[q.name for q in karantina]}"
    finally:
        for q in p.parent.glob("pemf_secrets.json*"):
            _icacls(q, "/reset")
    assert p.exists() and _sha(p) == once, "sır dosyası yerinde değil ya da baytları değişti"


def test_KARSIT_yarim_yazilmis_sir_dosyasi_hala_KARANTINAYA_alinir_D280(sm, tmp_path):
    """Karşıt: içerik gerçekten BOZUK (yazım yarıda kalmış JSON) → bugünkü fail-closed kenara alma AYNEN (Karar 6)."""
    p = tmp_path / "PEMF_GUI" / "pemf_secrets.json"
    metin = json.dumps(_gecerli_doc())
    p.write_text(metin[: len(metin) // 2], encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        sm._load()
    assert "bozuk" in str(exc.value).lower()
    assert list(p.parent.glob("pemf_secrets.json.corrupt.*")), "bozuk dosya kenara alınmadı"


def test_KRITIK_ikinci_hesap_DIZIN_listelenemez_EYLEM_soyleyen_hata_dosyaya_dokunulmaz_D280(sm, tmp_path):
    """İkinci Windows hesabı benzetimi: veri dizininin DACL'i yalnız LOCAL SERVICE → `Path.exists()` bile WinError 5 verir.
    Bugün ham `[WinError 5] Erişim engellendi: …` (ne olduğu / ne yapılacağı yok). Beklenen: `PermissionError` "erişim
    reddedildi" + eylem (çağıranların sınıflaması: OKUNAMADI/YAZILAMADI — Karar 6); dosya ve dizine dokunulmaz."""
    d = tmp_path / "PEMF_GUI"
    p = d / "pemf_secrets.json"
    p.write_text(json.dumps(_gecerli_doc()), encoding="utf-8")
    once = _sha(p)
    r = _icacls(d, "/inheritance:r", "/grant:r", f"{_YABANCI_SID}:(OI)(CI)(F)")
    assert r.returncode == 0, f"aparat: dizin DACL'i kurulamadı: {r.stdout}{r.stderr}"
    try:
        with pytest.raises(PermissionError):
            p.exists()  # aparat kanıtı
        with pytest.raises(PermissionError) as exc:
            sm._load()
        assert "erişim reddedildi" in str(exc.value).lower(), f"ileti erişim reddini söylemiyor: {exc.value}"
        assert "yapılacak" in str(exc.value).lower(), f"ileti eylem söylemiyor: {exc.value}"
    finally:
        _icacls(d, "/reset", "/T", "/C")
    assert sorted(x.name for x in d.iterdir()) == ["pemf_secrets.json"], (
        "dizinde yeniden adlandırma / yeni dosya oluştu"
    )
    assert _sha(p) == once


@pytest.fixture()
def sertlestirme(tmp_path, monkeypatch):
    """Dizin sertleştirmesi HEP başarısız (icacls düşer — LocalSystem'de D-3.1 hâli); çağrı sayısı kaydedilir."""
    import utils.file_acl as fa
    from utils import secrets_manager as _sm

    veri = tmp_path / "PEMF_GUI"
    veri.mkdir()
    (veri / "pemf_secrets.json").write_text(json.dumps(_gecerli_doc()), encoding="utf-8")
    monkeypatch.setattr(_sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(_sm, "_cache", None)
    monkeypatch.setattr(_sm, "_dir_hardened", False)
    if hasattr(_sm, "_sertlestirme_sonraki"):
        monkeypatch.setattr(_sm, "_sertlestirme_sonraki", 0.0)
    cagrilar = []

    def _dir_kilidi(path, keep_current_user=True):
        cagrilar.append(str(path))
        return False

    monkeypatch.setattr(fa, "lock_down_dir", _dir_kilidi)
    monkeypatch.setattr(fa, "lock_down_file", lambda *a, **k: True)
    return _sm, cagrilar


def test_KRITIK_onbellek_doluyken_sertlestirme_HER_get_secretta_denenmez_D280(sertlestirme, monkeypatch):
    """Sertleştirme başarısızken 50 `get_secret` (önbellek ilk okumadan sonra dolu) → en çok 1 `lock_down_dir`.
    Geri çekilme bu kolda SIFIR: iki katman örtüşür (ölçüldü — geri çekilme açıkken "sertleştirme önbellek denetiminden
    ÖNCE" mutantı YEŞİL kalıyordu); burada YALNIZ önbellek-önce kuralı ölçülür."""
    sm, cagrilar = sertlestirme
    monkeypatch.setattr(sm, "_SERTLESTIRME_GERI_CEKILME_SN", 0.0, raising=False)
    for _ in range(50):
        assert sm.get_secret("tunnel_hostname", generate=False) == "sahte.ornek"
    assert len(cagrilar) <= 1, f"önbellek doluyken sertleştirme {len(cagrilar)} kez denendi (her get_secret icacls)"


def test_KRITIK_basarisiz_sertlestirme_GERI_CEKILIR_ard_arda_yazimlar_icacls_firtinasi_yapmaz_D280(sertlestirme):
    """Sertleştirme başarısızken 5 ardışık `set_secret` (geri çekilme penceresi içinde) → en çok 1 deneme.
    Deneme `os.replace`'ten ÖNCE yapılır; yeni yazılan dosyayı tarayan AV/indeksleyici takası anlık reddedebilir (ölçüldü:
    20 hızlı yazımın birinde WinError 5) — o yazım düşse de sayım geçerlidir, bu yüzden yalnız `PermissionError` tolere edilir."""
    sm, cagrilar = sertlestirme
    for i in range(5):
        try:
            sm.set_secret("tunnel_hostname", f"h{i}.ornek")
        except PermissionError:
            pass
    assert len(cagrilar) <= 1, f"başarısız sertleştirme {len(cagrilar)} kez yeniden denendi (geri çekilme yok)"


def test_KARSIT_geri_cekilme_SURESI_dolunca_sertlestirme_YENIDEN_denenir_D280(sertlestirme, monkeypatch):
    """Karşıt: geri çekilme kalıcı kapatma DEĞİL — süre dolunca bir sonraki yazım yeniden dener (≥2 deneme)."""
    sm, cagrilar = sertlestirme
    sm.set_secret("tunnel_hostname", "a.ornek")
    simdi = time.monotonic()
    monkeypatch.setattr(sm.time, "monotonic", lambda: simdi + 3600.0)
    sm.set_secret("tunnel_hostname", "b.ornek")
    assert len(cagrilar) >= 2, f"geri çekilme süresi dolduktan sonra sertleştirme yeniden denenmedi ({len(cagrilar)})"


def test_KRITIK_O_A2_1_b_ayni_erisim_reddi_gunlugu_DOLDURMAZ_sayar_ve_ozetler_D280(sm, tmp_path, monkeypatch, caplog):
    """O-A2-1.b: ikinci hesap kipinde erişim reddi her `get_secret`te (Y43 denemeleri + çağıranlar) yükselir; günlük 5 sn'de
    onlarca aynı satırla doluyordu (ölçüldü: 43 + 28 + 14). Aynı neden 10 kez → tek ERROR satırı; süre dolunca basılan satır
    aradaki bastırılmış tekrar sayısını söyler (bilgi kaybolmaz). Davranış (hata yükselmesi) her çağrıda AYNEN sürer."""
    import logging

    monkeypatch.setattr(sm, "_tekrar_gunluk", {})
    d = tmp_path / "PEMF_GUI"
    (d / "pemf_secrets.json").write_text(json.dumps(_gecerli_doc()), encoding="utf-8")
    r = _icacls(d, "/inheritance:r", "/grant:r", f"{_YABANCI_SID}:(OI)(CI)(F)")
    assert r.returncode == 0, f"aparat: dizin DACL'i kurulamadı: {r.stdout}{r.stderr}"
    try:
        with caplog.at_level(logging.ERROR, logger="utils.secrets_manager"):
            for _ in range(10):
                with pytest.raises(PermissionError):
                    sm._load()
            ilk = [x for x in caplog.records if "pemf_secrets.json OKUNAMADI" in x.getMessage()]
            assert len(ilk) == 1, f"aynı erişim reddi {len(ilk)} kez günlüğe basıldı (tekrar kısıtlaması yok)"
            simdi = time.monotonic()
            monkeypatch.setattr(sm.time, "monotonic", lambda: simdi + 3600.0)
            with pytest.raises(PermissionError):
                sm._load()
            son = [x.getMessage() for x in caplog.records if "pemf_secrets.json OKUNAMADI" in x.getMessage()]
            assert len(son) == 2 and "9 kez daha" in son[-1], (
                f"süre dolunca bastırılan tekrar sayısı söylenmedi: {son[-1:]}"
            )
    finally:
        _icacls(d, "/reset", "/T", "/C")
