# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""manifest ÜRETİCİSİ — sessiz bölüm kaybı olmamalı (2026-08-09 denetimi, ENGEL).

ARIZA: `scripts/make_manifest.py` iki bölümü ne ÜRETİYOR ne de TAŞIYORDU:
  • `layers`  → client >=1.9.13 katmanlı paketi okur. Bölüm düşünce tek-parça `runtimes`e geri
                döner: sıradan bir sürümde 71 MB yerine 1,25 GB indirme — HER kullanıcıda.
  • `mobile`  → APK açılışta `versionCode` karşılaştırır. Bölüm düşünce sahadaki TÜM telefonlar
                oto-güncellemeyi kaybeder.
İkisi de manifest her yeniden üretildiğinde sessizce siliniyordu; hiçbir hata görünmüyordu.
Kayıp ancak kimse güncelleme alamayınca fark edilirdi — `launcher` bloğunda aynısı bir kez yaşandı.

Bu dosya, üreticinin ASIL değişmezini kilitler: ÖNCEKİ manifest'te olan bir bölüm, yenisinde
SEBEPSİZ kaybolamaz.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BETIK = Path(__file__).resolve().parent.parent / "scripts" / "make_manifest.py"

ONCEKI = {
    "schema": 2,
    "version": "1.8.0",
    "tag": "client-app-v1.8.0",
    "launcher": {"version": "1.9.15", "url": "https://x/setup.exe", "sha256": "a" * 64, "size": 1},
    "_mobile_note": "APK oto-guncelleme aciklamasi",
    "mobile": {
        "android": {"version": "2.3.7", "versionCode": 14, "url": "https://x/app.apk", "sha256": "b" * 64, "size": 2}
    },
    "layers": {
        "win-x64": {
            "rollout": 100,
            "app": {"url": "https://x/base-app.zip", "sha256": "c" * 64, "size": 3, "kind": "zip"},
            "deps": {"url": "https://x/base-deps.zip", "sha256": "d" * 64, "size": 4, "kind": "zip"},
        }
    },
    "runtimes": {"win-x64": {"url": "https://x/base.zip", "sha256": "e" * 64, "size": 5, "kind": "zip"}},
    "models": {},
    "profiles": {},
    "base": {"url": "https://x/base.zip", "sha256": "e" * 64, "size": 5, "kind": "zip"},
}


def _calistir(dizin: Path, *ek):
    # PYTHONIOENCODING: Windows'ta alt süreç stderr'i konsol kod sayfasıyla yazar ve Türkçe
    # karakterler bozulur → hata mesajı hem burada hem CI günlüğünde okunamaz hâle gelirdi.
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [
            sys.executable,
            str(BETIK),
            "--dir",
            str(dizin),
            "--version",
            "1.9.0",
            "--tag",
            "client-app-v1.9.0",
            "--repo",
            "mert61-python/pemf-update",
            *ek,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


@pytest.fixture
def dizin(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps(ONCEKI), encoding="utf-8")
    return tmp_path


def _oku(dizin):
    return json.loads((dizin / "manifest.json").read_text(encoding="utf-8"))


# ── taşıma ───────────────────────────────────────────────────────────────────


def test_KRITIK_mobile_blogu_KAYBOLMAZ(dizin):
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    assert _oku(dizin)["mobile"] == ONCEKI["mobile"], "APK oto-guncellemesi sessizce oldu"


def test_KRITIK_layers_blogu_KAYBOLMAZ(dizin):
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    assert _oku(dizin)["layers"]["win-x64"]["app"] == ONCEKI["layers"]["win-x64"]["app"]
    assert _oku(dizin)["layers"]["win-x64"]["deps"] == ONCEKI["layers"]["win-x64"]["deps"]


def test_launcher_blogu_KAYBOLMAZ(dizin):
    """Zaten korunuyordu — regresyon kapısı."""
    assert _oku(dizin)["launcher"] == ONCEKI["launcher"] or _calistir(dizin).returncode == 0
    assert _oku(dizin)["launcher"] == ONCEKI["launcher"]


def test_aciklama_notlari_korunur(dizin):
    _calistir(dizin)
    assert _oku(dizin)["_mobile_note"] == ONCEKI["_mobile_note"]


# ── üretim ───────────────────────────────────────────────────────────────────


def test_yereldeki_katman_paketlerinden_URETIR(dizin):
    (dizin / "base-app.zip").write_bytes(b"APP" * 100)
    (dizin / "base-deps.zip").write_bytes(b"DEPS" * 100)
    (dizin / "base.zip").write_bytes(b"APP" * 100 + b"DEPS" * 100)  # tek-sürüm kapısı gereği
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    L = _oku(dizin)["layers"]["win-x64"]
    assert L["app"]["url"].endswith("client-app-v1.9.0/base-app.zip"), "URL yeni tag'e bakmiyor"
    assert L["app"]["size"] == 300 and L["deps"]["size"] == 400
    assert L["app"]["sha256"] != ONCEKI["layers"]["win-x64"]["app"]["sha256"], "sha yenilenmedi"


def test_KRITIK_karisik_katman_seti_URETILMEZ(dizin):
    """Yeni `app` + ESKİ `deps` tutarsız bir kurulum demektir (app yeni koda, deps eski
    kütüphanelere bakar). Yalnız biri yerelde varsa diğeri ÖNCEKİNDEN TAŞINMAMALI.

    ⚠️ GÜNCELLENDİ (denetim 2026-08-17): koruduğu değişmez AYNEN duruyor — ESKİ `deps` yeni `app`
    ile karıştırılmıyor. DEĞİŞEN: eskiden bu durumda manifest SESSİZCE yazılıyor ve çıkış 0
    veriliyordu. Yarım set YAYINLANAMAZ: launcher tarafında `deps`/`app` ZORUNLU alan, eksikse
    client TÜM manifesti reddeder ve kayıp o platformla sınırlı kalmaz (kurulum, güncelleme ve
    geri çağırma her platformda durur). Artık manifest YAZILMIYOR ve çıkış 1."""
    (dizin / "base-app.zip").write_bytes(b"APP" * 100)
    (dizin / "base.zip").write_bytes(b"APP" * 100)  # tek-sürüm kapısı gereği
    r = _calistir(dizin)
    assert r.returncode == 1, f"yarim katman seti SESSIZCE yayina gitti: {r.stdout[-400:]}"
    assert "YARIM KATMAN SETI" in r.stderr, f"sebep soylenmedi: {r.stderr[-400:]}"
    assert "deps EKSIK" in r.stderr, f"hangi katmanin eksik oldugu soylenmedi: {r.stderr[-400:]}"
    # ⚠️ ASIL DEĞİŞMEZ hâlâ kilitli: manifest HİÇ YAZILMADIĞI için karışık set üretilmesi
    # zaten imkânsız. (Fixture ÖNCEKİ manifesti bırakıyor — o dosyanın DOKUNULMAMIŞ olduğunu
    # doğruluyoruz: yeni `app` boyutu 300 ise dosya bu koşuda yazılmış demektir.)
    assert _oku(dizin)["layers"]["win-x64"]["app"]["size"] != 300, (
        "manifest YAZILDI: yeni app onceki manifest'e islenmis, yani yarim set yayina gitti"
    )


# ── rollout (yayın kararı, dosyadan türetilemez) ─────────────────────────────


def test_KRITIK_geri_cekilmis_rollout_SIFIRLANMAZ(tmp_path):
    """Bozuk bir yayın `rollout: 0` ile geri çekilir. Yeniden üretimde sessizce 100'e dönerse
    geri çekme bozulur ve hatalı sürüm HERKESE dağıtılır."""
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["layers"]["win-x64"]["rollout"] = 0
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    assert _calistir(tmp_path).returncode == 0
    assert _oku(tmp_path)["layers"]["win-x64"]["rollout"] == 0, "geri cekme sifirlandi"


def test_rollout_bayragiyla_degistirilebilir(dizin):
    assert _calistir(dizin, "--rollout", "25").returncode == 0
    assert _oku(dizin)["layers"]["win-x64"]["rollout"] == 25


def test_gecersiz_rollout_REDDEDILIR(dizin):
    assert _calistir(dizin, "--rollout", "150").returncode == 1


def test_yeni_platformda_rollout_varsayilan_100(dizin):
    (dizin / "base-mac-app.zip").write_bytes(b"A")
    (dizin / "base-mac-deps.zip").write_bytes(b"B")
    (dizin / "base-mac.zip").write_bytes(b"AB")  # tek-sürüm kapısı gereği
    assert _calistir(dizin).returncode == 0
    assert _oku(dizin)["layers"]["mac-arm64"]["rollout"] == 100


# ── sessiz kayıp kapısı ──────────────────────────────────────────────────────


def test_KRITIK_mobile_kaybolacaksa_manifest_YAZILMAZ(tmp_path):
    """Kapının kendisi: bir bölüm kaybolacaksa çıkış kodu 0 dönmemeli — yayın akışı (publish.ps1
    / CI) sıfırı 'başarılı' sayar ve bozuk manifest yayınlanır."""
    onceki = json.loads(json.dumps(ONCEKI))
    onceki.pop("layers")
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    # `mobile` taşınabilir olsun diye betiği CARRY yolundan geçir ama bloğu sil:
    onceki2 = json.loads(json.dumps(onceki))
    onceki2.pop("mobile")
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    # mobile MEVCUT → taşınmalı ve yazılmalı
    assert _calistir(tmp_path).returncode == 0
    assert _oku(tmp_path)["mobile"] == ONCEKI["mobile"]


def test_KRITIK_layers_kaybolursa_HATA_verir(dizin, monkeypatch):
    """`layers` taşıma kodu bir gün bozulursa bu kapı yayını DURDURMALI."""
    # Taşımayı devre dışı bırakmanın açık yolu --drop-missing; onsuz kayıp HATA olmalı.
    # Kaybı modellemek için önceki manifest'te layers VAR ama betiğe bozuk bir bölüm veriyoruz.
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["layers"] = {"win-x64": "BOZUK-TIP"}  # dict değil → taşınamaz
    (dizin / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    r = _calistir(dizin)
    assert r.returncode == 1, "layers kayboldu ama betik 'basarili' dondu"
    assert "layers" in r.stderr


def test_drop_missing_ile_bilerek_silinebilir(dizin):
    # `--drop-missing` hiçbir şey taşımaz → base de yerelde OLMALI (yoksa "hiçbir base paketi
    # bulunamadı" ile zaten durur; o kontrol bu düzeltmeden ÖNCE de vardı).
    (dizin / "base.zip").write_bytes(b"BASE" * 50)
    r = _calistir(dizin, "--drop-missing")
    assert r.returncode == 0, r.stderr[-800:]
    assert not _oku(dizin)["layers"], "acik --drop-missing'e ragmen layers tasindi"


def test_allow_missing_mobile_ile_bilerek_silinebilir(tmp_path):
    onceki = json.loads(json.dumps(ONCEKI))
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    # mobile'ı taşınamaz kıl: önceki manifest'ten çıkar → uyarı yolu
    onceki.pop("mobile")
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    r = _calistir(tmp_path)
    assert r.returncode == 0, r.stderr[-800:]
    assert "mobile" not in _oku(tmp_path)


# ── mevcut davranış korunuyor mu (regresyon) ─────────────────────────────────


def test_runtimes_ve_v1_alanlari_KORUNUR(dizin):
    """⚠️ `runtimes`/`base` ESKİ client'lar (<=1.9.12) için DURMALI — katmanlar onların yerine
    geçmez."""
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    m = _oku(dizin)
    assert m["runtimes"]["win-x64"] == ONCEKI["runtimes"]["win-x64"]
    assert m["base"] == ONCEKI["base"]


def test_launchersiz_manifest_HATA(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"runtimes": {}, "base": ONCEKI["base"]}), encoding="utf-8")
    assert _calistir(tmp_path).returncode == 1


# ── TEK SÜRÜM, TEK YAZILIM (2026-08-09 denetimi, ENGEL) ──────────────────────
# Sahada ÖLÇÜLDÜ: yayındaki base.zip ile base-app+base-deps 53 dosyada farklıydı
# (`PEMF_Backend.exe` dahil). Sebep: katmanlar her sürümde üretiliyordu ama tek-parça base.zip
# yalnız `--monolith` ile üretildiği için ESKİ build'den kalıyordu. Sonuç: client <=1.9.12
# base.zip'ten ESKİ backend'i, >=1.9.13 layers'tan YENİ backend'i kuruyordu — aynı sürüm
# numarası altında iki farklı yazılım. Tıbbi cihazda bir arızanın hangi kodda olduğu bilinemez.


def test_KRITIK_taze_katman_bayat_base_ile_YAYINLANMAZ(dizin):
    (dizin / "base-app.zip").write_bytes(b"YENI-APP")
    (dizin / "base-deps.zip").write_bytes(b"YENI-DEPS")
    # base.zip yerelde YOK → önceki manifest'ten taşınacaktı (bayat).
    r = _calistir(dizin)
    assert r.returncode == 1, "taze katman + bayat base yayinlandi (iki farkli yazilim)"
    assert "İKİ FARKLI" in r.stderr or "IKI FARKLI" in r.stderr


def test_taze_katman_TAZE_base_ile_yayinlanir(dizin):
    (dizin / "base-app.zip").write_bytes(b"YENI-APP")
    (dizin / "base-deps.zip").write_bytes(b"YENI-DEPS")
    (dizin / "base.zip").write_bytes(b"YENI-APPYENI-DEPS")
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    m = _oku(dizin)
    assert m["runtimes"]["win-x64"]["url"].endswith("client-app-v1.9.0/base.zip")
    assert m["layers"]["win-x64"]["app"]["url"].endswith("client-app-v1.9.0/base-app.zip")


def test_ikisi_de_bayatsa_yayinlanir(dizin):
    """Yalnız manifest'i yeniden üretmek (ör. rollout değiştirmek) engellenmemeli — bu durumda
    base ve katmanlar ZATEN aynı eski yayındandır, tutarsızlık yoktur."""
    assert _calistir(dizin).returncode == 0


def test_baska_platformun_bayat_basei_ENGEL_DEGIL(dizin):
    """win-x64 tazelenirken mac/linux'un taşınması normaldir (ayrı runner'larda üretilirler)."""
    (dizin / "base-app.zip").write_bytes(b"A")
    (dizin / "base-deps.zip").write_bytes(b"B")
    (dizin / "base.zip").write_bytes(b"AB")
    r = _calistir(dizin)
    assert r.returncode == 0, r.stderr[-800:]
    # win-x64 tazelendi, mac/linux hiç dokunulmadı → kapı yalnız TAZELENEN platformu denetler.
    assert _oku(dizin)["runtimes"]["win-x64"]["url"].endswith("client-app-v1.9.0/base.zip")


# ── LAUNCHER SELF-UPDATE GERİ ÇEKME (2026-08-09 denetimi, Tier 1) ────────────
# Runtime katmanlarında kademeli dağıtım/geri çekme freni vardı ama GÜNCELLEMEYİ YÖNETEN
# bileşende yoktu: launcher self-update'i sürüm yeniyse koşulsuz, sessizce ve %100'e
# uygulanıyordu. Bozuk bir client yayını sahadaki HER cihaza gider ve dönüş yolu kalmaz —
# yeni launcher artık eskisini çalıştırmıyor.


def test_KRITIK_launcher_rollout_SIFIRA_cekilebilir(dizin):
    r = _calistir(dizin, "--launcher-rollout", "0")
    assert r.returncode == 0, r.stderr[-800:]
    assert _oku(dizin)["launcher"]["rollout"] == 0, "bozuk client yayini geri cekilemiyor"


def test_launcher_rollout_diger_alanlari_KORUR(dizin):
    _calistir(dizin, "--launcher-rollout", "10")
    L = _oku(dizin)["launcher"]
    assert L["rollout"] == 10
    assert L["version"] == ONCEKI["launcher"]["version"], "surum kayboldu"
    assert L["sha256"] == ONCEKI["launcher"]["sha256"], "sha kayboldu"


def test_launcher_rollout_VERILMEZSE_dokunmaz(dizin):
    """Sıradan bir yayında launcher bloğu AYNEN taşınmalı."""
    _calistir(dizin)
    assert _oku(dizin)["launcher"] == ONCEKI["launcher"]


def test_gecersiz_launcher_rollout_REDDEDILIR(dizin):
    assert _calistir(dizin, "--launcher-rollout", "150").returncode == 1


def test_launcher_ve_runtime_rollout_AYRI_kararlardir(dizin):
    """Runtime'ı %100 tutarken client yayınını durdurabilmek gerekir (ya da tersi)."""
    r = _calistir(dizin, "--rollout", "100", "--launcher-rollout", "0")
    assert r.returncode == 0, r.stderr[-800:]
    m = _oku(dizin)
    assert m["layers"]["win-x64"]["rollout"] == 100
    assert m["launcher"]["rollout"] == 0


# ── PLATFORM ÇIKARMA (2026-08-09 denetimi, Tier 1 — sahip kararı) ────────────
# mac/linux paketleri bayattı, `layers` (rollout freni) yoktu ve client self-update'i Windows'a
# özeldi → o platformlara kurulan cihaz ESKİ sürümde KİLİTLİ kalıyor ve bozuk bir yayın geri
# çekilemiyordu. Site zaten "Yakında" diyordu; manifest'in hâlâ paket sunması tutarsızdı.
# Client'ın "bu platform için paket yok" deyip DURMASI, sessizce kilitli cihaz kurmasından iyidir.


def _mac_linuxlu(tmp_path):
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["runtimes"]["mac-arm64"] = {"url": "https://x/base-mac.zip", "sha256": "f" * 64, "size": 7, "kind": "zip"}
    onceki["runtimes"]["linux-x64"] = {"url": "https://x/base-linux.zip", "sha256": "9" * 64, "size": 8, "kind": "zip"}
    onceki["base_mac"] = onceki["runtimes"]["mac-arm64"]
    onceki["base_linux"] = onceki["runtimes"]["linux-x64"]
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    return tmp_path


def test_KRITIK_platform_CIKARILIR(tmp_path):
    d = _mac_linuxlu(tmp_path)
    r = _calistir(d, "--drop-platform", "mac-arm64", "--drop-platform", "linux-x64")
    assert r.returncode == 0, r.stderr[-800:]
    m = _oku(d)
    assert "mac-arm64" not in m["runtimes"] and "linux-x64" not in m["runtimes"]
    assert "base_mac" not in m and "base_linux" not in m, "v1 anahtarlari kaldi — eski client yine kurar"


def test_cikarma_DIGER_platformu_bozmaz(tmp_path):
    """`--drop-missing`ten farkı bu: yalnız seçilen platform gider, Windows taşınmaya devam eder."""
    d = _mac_linuxlu(tmp_path)
    assert _calistir(d, "--drop-platform", "mac-arm64").returncode == 0
    m = _oku(d)
    assert m["runtimes"]["win-x64"] == ONCEKI["runtimes"]["win-x64"], "windows paketi bozuldu"
    assert m["layers"]["win-x64"]["app"] == ONCEKI["layers"]["win-x64"]["app"]
    assert "linux-x64" in m["runtimes"], "istenmeyen platform da silindi"


def test_KRITIK_sessiz_kayip_kapisi_ACIK_cikarmayi_ENGELLEMEZ(tmp_path):
    """Tier 0.9 kapısı 'önceden vardı, şimdi yok' durumunu HATA sayar. Açık bayrak, bilinçli
    kaldırmanın sanktioned yoludur — yoksa kaldırma hiç yapılamazdı."""
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["layers"]["mac-arm64"] = {
        "rollout": 100,
        "app": {"url": "https://x/m-app.zip", "sha256": "1" * 64, "size": 1, "kind": "zip"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    r = _calistir(tmp_path, "--drop-platform", "mac-arm64")
    assert r.returncode == 0, r.stderr[-800:]
    assert "mac-arm64" not in _oku(tmp_path)["layers"]


def test_olmayan_platformu_cikarmak_ZARARSIZ(dizin):
    assert _calistir(dizin, "--drop-platform", "solaris-sparc").returncode == 0
    assert _oku(dizin)["runtimes"]["win-x64"] == ONCEKI["runtimes"]["win-x64"]


def test_cikarma_launcher_ve_mobile_bloklarini_KORUR(tmp_path):
    d = _mac_linuxlu(tmp_path)
    _calistir(d, "--drop-platform", "mac-arm64", "--drop-platform", "linux-x64")
    m = _oku(d)
    assert m["launcher"] == ONCEKI["launcher"]
    assert m["mobile"] == ONCEKI["mobile"]


# ── GERİ ÇAĞIRMA EŞİĞİ (2026-08-09 denetimi, Tier 2) ────────────────────────
# `rollout: 0` yalnız YENİ dağıtımı durdurur; sahadaki cihaza dokunmaz. Bir bobin-güvenliği
# hatası bulunduğunda asıl gereken MEVCUT kurulumları güncellemeye ZORLAMAKTIR.


def test_KRITIK_min_supported_version_yazilir(dizin):
    r = _calistir(dizin, "--min-supported-version", "1.9.16")
    assert r.returncode == 0, r.stderr[-800:]
    assert _oku(dizin)["min_supported_version"] == "1.9.16"


def test_KRITIK_yururlukteki_geri_cagirma_SESSIZCE_KALKMAZ(tmp_path):
    """Yeniden üretim, aktif bir geri çağırmayı kaldırırsa etkilenen klinikler sessizce
    eski sürümde kalır — geri çağırmanın tüm anlamı gider."""
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["min_supported_version"] = "1.9.16"
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    assert _calistir(tmp_path).returncode == 0
    assert _oku(tmp_path)["min_supported_version"] == "1.9.16", "geri cagirma sessizce kalkti"


def test_bos_deger_geri_cagirmayi_KALDIRIR(tmp_path):
    onceki = json.loads(json.dumps(ONCEKI))
    onceki["min_supported_version"] = "1.9.16"
    (tmp_path / "manifest.json").write_text(json.dumps(onceki), encoding="utf-8")
    assert _calistir(tmp_path, "--min-supported-version", "").returncode == 0
    assert "min_supported_version" not in _oku(tmp_path)


def test_verilmezse_alan_EKLENMEZ(dizin):
    assert _calistir(dizin).returncode == 0
    assert "min_supported_version" not in _oku(dizin)
