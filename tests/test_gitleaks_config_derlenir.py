# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GITLEAKS YAPILANDIRMASI DERLENEBILIR OLMALI (2026-08-22, yayin sirasinda bulundu).

OLCULEN ARIZA. 2. tur denetimi [2.2] icin `.gitleaks.toml`a iki ozel kural eklenmisti:
dusuk-entropili WiFi/MQTT parolalari varsayilan kurallarca yakalanmiyordu ve `git add -A` o
sinifi PUBLIC depoya tasiyabiliyordu. Kurallardan birinin `path` deseninde ayrac sinifi TEK
ters-bolukle yazilmisti. TOML literal dizesi ('''...''') kacis islemez; Go'ya kapanis
parantezi KACIRILMIS bir karakter sinifi ulasiyor, sinif hic kapanmiyor ve
`regexp.MustCompile` PANIK ediyor.

SONUC: gitleaks HER calismada cokuyordu. Yani sir tarama kapisi — eklendigi gunden beri —
HIC TARAMADI. Hem pre-commit kancasi hem CI ayni config'i okudugu icin iki kapi da olmustu.
Panik `git commit` ciktisinda bir Go yigin izi olarak goruluyordu; commit dusuyordu ama
"sizinti yok" gibi degil, "kanca hatasi" gibi. Yayin icin commit atilana kadar fark edilmedi.

DERS: bir GUVENLIK KAPISININ CALISTIGI, kapinin VARLIGINDAN ayri olarak dogrulanmalidir.
Yapilandirmayi eklemek yetmez; yuklenip derlendigini de olcmek gerekir.

Bu dosya: (1) her kural/allowlist deseninin derlendigini, (2) gitleaks ikilisi bulunabiliyorsa
config'i GERCEKTEN yukleyip cokmedigini olcer.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import gitleaks_ikili
import pytest

_KOK = Path(__file__).resolve().parents[1]
_CONFIG = _KOK / ".gitleaks.toml"

# TOML literal dizeleri: regex = '''...'''  /  path = '''...'''  /  liste ogeleri
_DESEN = re.compile(r"^\s*(?:regex|path)\s*=\s*'''(.*?)'''\s*$", re.M | re.S)
_LISTE_OGE = re.compile(r"^\s*'''(.*?)''',\s*$", re.M | re.S)


def _desenler() -> list[tuple[int, str]]:
    metin = _CONFIG.read_text(encoding="utf-8")
    bulunan: list[tuple[int, str]] = []
    for m in list(_DESEN.finditer(metin)) + list(_LISTE_OGE.finditer(metin)):
        satir = metin[: m.start()].count("\n") + 1
        bulunan.append((satir, m.group(1)))
    return bulunan


def test_KRITIK_her_desen_DERLENIR():
    """Dengesiz parantez/karakter sinifi hem Go'da hem Python'da patlar — vekil olarak yeterli."""
    desenler = _desenler()
    assert desenler, ".gitleaks.toml icinde hic desen bulunamadi (ayristirici bozulmus olabilir)"

    hatali = []
    for satir, desen in desenler:
        try:
            re.compile(desen)
        except re.error as e:
            hatali.append(f"  satir {satir}: {e}  ->  {desen}")

    assert not hatali, (
        "gitleaks yapilandirmasinda DERLENMEYEN desen(ler) var. Gitleaks bunlarda PANIK eder ve "
        "HICBIR SEY TARAMAZ — kapi sessizce olur:\n" + "\n".join(hatali)
    )


def test_KRITIK_gitleaks_config_i_GERCEKTEN_yukluyor(tmp_path):
    """Vekil degil, GERCEK olcum: gitleaks ikilisi bu config'le calisip cokmuyor mu?

    ⚠️ D3.02 (2026-10-10): ikili `tests/gitleaks_ikili.py` ile bulunur (PEMF_GITLEAKS / PATH / pre-commit
    onbellegi); yoksa varsayilan kipte ATLANIR, zorunlu kipte (CI: PEMF_GITLEAKS_ZORUNLU=1) DUSER. Eskiden yalniz
    PATH + HOME onbellegi arandigi icin CI'da, temiz klonda ve yalitilmis koşucuda hep atlaniyordu. Bos dizin
    artik depo icinde (`tests/__gitleaks_bos__`) DEGIL, tmp_path'te.
    """
    ikili = gitleaks_ikili.gerekli()
    r = subprocess.run(
        [ikili, "detect", "--config", str(_CONFIG), "--no-git", "--no-banner", "-s", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=180,
    )

    cikti = (r.stdout or "") + (r.stderr or "")
    assert "panic:" not in cikti.lower(), (
        "gitleaks config'i yuklerken PANIK etti — kapi calismiyor demektir:\n" + cikti[:1200]
    )
    assert "MustCompile" not in cikti, "regex derleme hatasi (MustCompile):\n" + cikti[:1200]


def test_KARSIT_KANIT_ozel_kurallar_HALA_YERINDE():
    """Asiri-genisleme korumasi: 'derlensin' diye kurallari SILMEK de testi yesil yapardi.
    [2.2] kapisinin iki kurali duruyor mu?"""
    metin = _CONFIG.read_text(encoding="utf-8")
    for kural in ("pemf-firmware-secrets-h-gercek-deger", "pemf-firmware-config-json-gercek-deger"):
        assert kural in metin, f"[2.2] kurali kaybolmus: {kural}"


def test_KARSIT_KANIT_muafiyet_DAR_kalir():
    """Kapinin kendi test fikstürü muaf tutuldu; muafiyet dizin geneline genisletilmemeli —
    aksi hâlde `tests/` altina konan GERCEK bir sir de sessizce gecerdi."""
    metin = _CONFIG.read_text(encoding="utf-8")
    m = re.search(r"paths\s*=\s*\[(.*?)\]", metin, re.S)
    assert m, "allowlist paths blogu bulunamadi"
    for oge in re.findall(r"'''(.*?)'''", m.group(1)):
        assert not oge.strip().rstrip("/").endswith(("tests", "tests/.*", "tests/*")), (
            f"muafiyet TUM tests/ dizinini kapsiyor: {oge!r} — dosya bazinda dar tutun"
        )


def test_KARSIT_KANIT_gitleaksignore_COMMIT_PINLI():
    """.gitleaksignore YALNIZ commit-pinli parmak izi içerebilir. Yol/desen bazlı genel
    satır, GELECEKTEKİ gerçek bir sızıntıyı da sessizce geçirirdi (2026-08-26: 7 tarihî
    şablon yanlış-pozitifi için eklendi — hepsi git-show ile tek tek doğrulandı)."""
    dosya = _CONFIG.parent / ".gitleaksignore"
    assert dosya.exists(), ".gitleaksignore silinmiş — dispatch tam-tarih taraması yine kırmızıya döner"
    desen = re.compile(r"^[0-9a-f]{40}:[^:]+:[^:]+:\d+$")
    for i, satir in enumerate(dosya.read_text(encoding="utf-8").splitlines(), 1):
        s = satir.strip()
        if not s or s.startswith("#"):
            continue
        assert desen.match(s), (
            f".gitleaksignore:{i} commit-pinli değil: {s!r} — "
            "yalnız <40-hex>:<dosya>:<kural>:<satır> biçimi kabul (genel muafiyet YASAK)"
        )


# ═══════════════════════════════════════════════════════════════════════════════════════════
# TURKCE "API" CARPISMASI — bayrak muafiyeti (2026-09-15)
# ═══════════════════════════════════════════════════════════════════════════════════════════
# OLCULEN ARIZA: `git commit` sirasinda gitleaks `apps/backend/servers/api_server.py` icinde
# `generic-api-key` bulgusu verdi. "Sir" sandigi sey `PEMF_ESP_ENABLED=1` — belgelenmis bir
# calisma-zamani bayragi, depoda 10+ takipli dosyada zaten acikca duruyor.
#
# KOK NEDEN YALITILDI (tahmin edilmedi): varsayilan kural `<anahtar-kelime>: <deger>` arar ve
# anahtar-kelime listesinde `API` vardir. TURKCE BUYUK HARFLI METINDE bu kelimelerin ICINDE
# gecer — K-API-LANIYOR, K-API-SI, K-API-LI... Bayragin kendisi (ciplak, backtickli, tek
# basina) SIFIR bulgu verdi; bulgu YALNIZ onune Turkce bir kelime konunca cikti.
#
# Bu yuzden muafiyet DEGERIN BICIMINE verildi, kelimeye ya da dosyaya DEGIL. Asagidaki iki
# test o daralmayi kilitler: birincisi bayragin gectigini, ikincisi ayni Turkce baglamda
# GERCEK gorunumlu bir sirrin HALA yakalandigini olcer.


def _bulgu_sayisi(tmp_path: Path, icerik: str) -> int:
    """Verilen metni gecici bir .py dosyasina yazip depo config'iyle tarar (ikili: tests/gitleaks_ikili.py, D3.02)."""
    ikili = gitleaks_ikili.gerekli()
    kaynak = tmp_path / "ornek.py"
    kaynak.write_text(icerik, encoding="utf-8")
    rapor = tmp_path / "rapor.json"
    subprocess.run(
        [
            ikili,
            "detect",
            "--config",
            str(_CONFIG),
            "--no-git",
            "--no-banner",
            "-s",
            str(kaynak),
            "--report-format",
            "json",
            "--report-path",
            str(rapor),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if not rapor.exists():
        return 0
    import json as _json

    return len(_json.loads(rapor.read_text(encoding="utf-8") or "[]"))


# Turkce "API" tasiyan gercek bir yorum baglami — arizanin ta kendisi.
_TR_BAGLAM = "# ESP KODU SILINMIYOR, YALNIZ KAPILANIYOR: `{deger}` ile eski davranis\n"


def test_KRITIK_PEMF_bayragi_TURKCE_baglamda_YANLIS_ALARM_uretmez(tmp_path):
    """`PEMF_*=<tek rakam>` bir bayraktir, sir degildir. Muafiyet kalkarsa bu KIRMIZI olur.

    Olculdu: ayni icerik VARSAYILAN config'le 1 bulgu, depo config'iyle 0 bulgu veriyor —
    yani yesillik muafiyetten geliyor, kuralin kendisinin kor olmasindan degil.
    """
    n = _bulgu_sayisi(tmp_path, _TR_BAGLAM.format(deger="PEMF_ESP_ENABLED=1"))
    assert n == 0, (
        "belgelenmis bir calisma-zamani bayragi 'sizinti' sayildi — bu sinif her Turkce "
        "buyuk harfli 'KAPI...' kelimesinde tekrarlar ve kapiyi gurultuye bogarak "
        "GERCEK bulgulari gorunmez kilar"
    )


# ⚠️ ASIRI-GENISLEME KARSIT-KANITLARI. Her ikisi de OLCULEREK secildi: varsayilan config bu
# iki degeri de YAKALIYOR (1 bulgu). Yani testler gitleaks'in zaten gormedigi bir seyi degil,
# GERCEKTEN gorduugu bir seyi muafiyetin gizleyip gizlemedigini sinar.
#
# ⚠️ ILK YAZIMDA YANLIS ORNEK SECILMISTI: `PEMF_MQTT_PASS=s3cr3t-...` — varsayilan config bunu
# ZATEN yakalamiyor (gitleaks'in durak-kelime suzgeci "pass" iceren degerleri eler). O ornekle
# yazilan bir karsit-kanit, muafiyet SINIRSIZ genisletilse bile yesil kalirdi.
@pytest.mark.parametrize(
    "deger, neden",
    [
        (
            "PEMF_ESP_ENABLED=aB3xK9mQ2vL7pR4tN8w",
            "ayni PEMF_ oneki ama deger RAKAM DEGIL — muafiyet onekle sinirli kalmali",
        ),
        (
            "PEMF_ESP_ENABLED=12345678901234",
            "ayni onek, deger rakam ama COK HANELI — muafiyet TEK haneyle sinirli kalmali; "
            "bu sinirlama olmadan 14 haneli bir PIN/kod da 'bayrak' sayilirdi",
        ),
    ],
)
def test_KARSIT_KANIT_bayrak_muafiyeti_GERCEK_SIRRI_gecirmez(tmp_path, deger, neden):
    n = _bulgu_sayisi(tmp_path, _TR_BAGLAM.format(deger=deger))
    assert n >= 1, f"muafiyet COK GENIS: {neden}"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# D3.02 (B-10.48 · A-69, 2026-10-10) — CI gitleaks ikilisini SABİT rev'den kurar ve testleri ZORUNLU kipte koşar
# ═══════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_CI_gitleaks_ikilisini_KURAR_ve_testleri_ZORUNLU_kosar():
    """CI pytest işi gitleaks'i kurmuyordu → özel kural testleri hep ATLANIYORDU (docstring "CI'da pre-commit indirir"
    diyordu, CI ölçümü tersini gösterdi). Artık: kurulum adımı pytest'ten ÖNCE, pytest adımlarında zorunlu kip."""
    yaml = pytest.importorskip("yaml", reason="pyyaml yok")
    adimlar = yaml.safe_load((_KOK / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))["jobs"][
        "backend"
    ]["steps"]
    kur = [i for i, a in enumerate(adimlar) if "pre-commit install-hooks" in str(a.get("run", ""))]
    pyt = [i for i, a in enumerate(adimlar) if "pytest tests" in str(a.get("run", ""))]
    assert kur, "CI backend işinde gitleaks'i kuran `pre-commit install-hooks` adımı YOK"
    assert pyt and max(kur) < min(pyt), f"kurulum adımı pytest'ten SONRA ({kur} / {pyt})"
    for i in pyt:
        env = adimlar[i].get("env") or {}
        assert str(env.get(gitleaks_ikili.ZORUNLU_ORTAM)) == "1", (
            f"pytest adımı '{adimlar[i].get('name')}' {gitleaks_ikili.ZORUNLU_ORTAM}=1 taşımıyor — ikili yoksa ATLAR"
        )
    cfg = (_KOK / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert re.search(r"repo:\s*https://github\.com/gitleaks/gitleaks\s+rev:\s*v\d+\.\d+\.\d+\s", cfg), (
        "pre-commit gitleaks rev'i SABİT sürüm (vX.Y.Z) değil — CI ikilisi kayabilir"
    )


def test_KARSIT_KANIT_bulucu_ACIK_yol_bozuksa_baska_ikiliye_DUSMEZ_ve_kipler(monkeypatch, tmp_path):
    """`PEMF_GITLEAKS` bozuk yolsa SESSİZCE PATH/önbelleğe düşülmez (yanlış sürüm ölçülmesin); zorunlu kip DÜŞER,
    varsayılan kip ATLAR. Dış ortam her iki bayrağın da tersine kurulur (koşucu maskelemesin)."""
    monkeypatch.setenv("PEMF_GITLEAKS", str(tmp_path / "olmayan_gitleaks.exe"))
    assert gitleaks_ikili.bul() is None
    monkeypatch.setattr(gitleaks_ikili.capraz, "ZORUNLU", False)

    def _sonuc() -> str:
        # ⚠️ `pytest.raises(fail.Exception)` bir ATLAMAYI yakalamaz, atlama dışarı sızar ve testi SKIPPED yapar —
        # mutant ("zorunlu ortamı yok say") kırmızı değil atlanmış görünürdü (ölçüldü). İki sonuç da AÇIKÇA yakalanır.
        try:
            gitleaks_ikili.gerekli()
        except pytest.fail.Exception as e:
            return f"DUSTU: {e}"
        except pytest.skip.Exception as e:
            return f"ATLADI: {e}"
        return "IKILI-BULUNDU"

    monkeypatch.setenv(gitleaks_ikili.ZORUNLU_ORTAM, "1")
    assert _sonuc().startswith("DUSTU: zorunlu kip"), _sonuc()
    monkeypatch.setenv(gitleaks_ikili.ZORUNLU_ORTAM, "0")
    assert _sonuc().startswith("ATLADI:") and "indirme YAPILMAZ" in _sonuc(), _sonuc()
    sahte = tmp_path / "gitleaks.exe"
    sahte.write_bytes(b"")
    monkeypatch.setenv("PEMF_GITLEAKS", str(sahte))
    assert gitleaks_ikili.bul() == str(sahte)
