# -*- coding: utf-8 -*-
"""4B-1.6 — D4.12 yeni bir KRİTİK kalıcı birim getirdi (`/var/lib/dbus` → compose `pemf_kimlik` / `pemf_micro_kimlik`): kritik sırlar
(`sqlcipher_key`) bu kimlikle sarılır. Kullanıcı belgesi (`docker/DOCKER_README.md`) yalnız `pemf_data`'yı ("DB + loglar … kalıcı") anlatıyor,
kimlik birimini HİÇ anmıyor (ölçüldü: depoda kimlik birimini anan belge 0). Veri birimini yedekleyip/taşıyıp kimlik birimini bırakan kurulumda
(ya da `docker volume rm pemf_kimlik`) backend fail-closed `RuntimeError` ile AÇILMAZ (doğru — veri kaybı yok) ama ileti kurtarma yolunu YANLIŞ
söyler: "Doğru makineyi kullanın veya pemf_secrets.json yedeğinden geri yükleyin" — `pemf_secrets.json` zaten veri biriminde ve AYNI kimlikle
sarılı; geri yüklemek çözmez. Doğru yol: kimlik birimini geri yüklemek.

Ölçüm: birim adları compose dosyalarından (PyYAML) TÜRETİLİR; ileti GERÇEK `secrets_manager` Linux dalında kimlik A → B ile üretilir."""

from __future__ import annotations

import importlib.util
from pathlib import Path, PurePosixPath

import pytest
import yaml

_YOL = Path(__file__).with_name("test_docker_KALICI_makine_kimligi_D412.py")
_spec = importlib.util.spec_from_file_location("zz_d412_4b16", _YOL)
d412 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d412)
linux_sm = d412.linux_sm  # fikstür

KOK = d412.KOK


def _birimler() -> dict:
    """{compose dosyası: (veri_birimi, kimlik_birimi)} — backend servisinde /data ve giriş betiğinin kimlik dizinine bağlı ADLI birimler."""
    kimlik_dizini = str(PurePosixPath(d412._kimlik_yolu()).parent)
    sonuc = {}
    for c in d412.COMPOSE_BACKEND:
        doc = yaml.safe_load((KOK / c).read_text(encoding="utf-8"))
        adlar = set((doc.get("volumes") or {}).keys())
        for ad, svc in (doc.get("services") or {}).items():
            veri = kimlik = None
            for v in svc.get("volumes") or []:
                kaynak, _, hedef = str(v).partition(":")
                hedef = hedef.split(":")[0]
                if kaynak in adlar and hedef == "/data":
                    veri = kaynak
                if kaynak in adlar and hedef == kimlik_dizini:
                    kimlik = kaynak
            if veri and kimlik:
                sonuc[c] = (veri, kimlik)
    return sonuc


def test_ONCUL_compose_backend_servisleri_veri_ve_kimlik_birimi_tasir():
    assert len(_birimler()) == 2, (
        f"çıpa: iki compose'un backend servisinde veri + kimlik birimi bulunamadı: {_birimler()}"
    )


def test_KRITIK_DOCKER_README_kimlik_birimini_veriyle_BIRLIKTE_yedeklemeyi_soyler():
    metin = (KOK / "docker" / "DOCKER_README.md").read_text(encoding="utf-8")
    eksik = sorted({k for _, k in _birimler().values() if k not in metin})
    assert not eksik, (
        f"docker/DOCKER_README.md kritik kimlik birimini ANMIYOR: {eksik} — veri birimi tek başına yedeklenir/taşınırsa kritik sırlar "
        "çözülemez ve backend açılmaz; kurtarma yolu belgede yok"
    )
    satirlar = [s for s in metin.splitlines() if any(k in s for _, k in _birimler().values())]
    assert any(v in s for s in satirlar for v, _ in _birimler().values()), (
        "README kimlik birimini anıyor ama veri birimiyle BİRLİKTE yedekleme/taşıma kuralını aynı yerde söylemiyor"
    )


def test_KRITIK_kimlik_degisince_ileti_DOGRU_kurtarma_yolunu_soyler(linux_sm, monkeypatch, tmp_path):
    sm = linux_sm
    a, b = tmp_path / "A" / "machine-id", tmp_path / "B" / "machine-id"
    for p, c in ((a, "a"), (b, "b")):
        p.parent.mkdir()
        p.write_text(c * 32, encoding="utf-8")
    monkeypatch.setattr(sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"), str(a)))
    sm.get_secret("sqlcipher_key")
    monkeypatch.setattr(
        sm, "MAKINE_KIMLIGI_YOLLARI", (str(tmp_path / "yok"), str(b))
    )  # kimlik birimi silindi → yeni kimlik
    sm._cache = None
    with pytest.raises(RuntimeError) as e:
        sm.get_secret("sqlcipher_key")
    ileti = str(e.value)
    assert "ÜRETİLMEDİ" in ileti, "fail-closed ileti değişti (aparat)"
    assert "/var/lib/dbus" in ileti or "kimlik birim" in ileti.lower(), (
        f"Linux/Docker'da kimlik değişince ileti kimlik birimini geri yüklemeyi söylemiyor; yalnız: {ileti[-160:]!r}"
    )
