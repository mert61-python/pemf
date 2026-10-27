# -*- coding: utf-8 -*-
"""I18N-0 · PARTİ ARAÇLARI — `scripts/i18n/{katalog,uygula,uygula_ts.cjs,bayrak,kapsam}.py`: 13-I18N-PARTI oturumları bu araçlarla göçer.

Kilitlenen davranış:
  * katalog: kanonik biçim (denetle yazmaz), eşlik raporu (eksik anahtar / boş / yer tutucu / çoğul / sunucuda `{{dil}}` `{{anahtar}}`),
    iki dilde anahtar ekleme (farklı TR ile üstüne yazmaz), çeviri parçası çıkar / geri al (yer tutucusu farklı İngilizce REDDEDİLİR),
    TR taban karşılaştırması (katalogda ya da muaf olmayan göç öncesi metin = Türkçe gerilemesi);
  * uygula (uçtan uca, `cikar → sablon → uygula`): TR katalog değeri kaynağın BİREBİR metni; Python'da dizgi / f-string → `ceviri.t`,
    modül düzeyi + VARSAYILAN ARGÜMAN (içe aktarmada dil donar) + `dil`/`anahtar` yer tutucusu REDDEDİLİR; TS'de jsx metni / öznitelik /
    şablon → `t(…)`, hook + içe aktarma eklenir, dosyanın tırnak / noktalı virgül biçimi korunur, modül düzeyi + `.map((t) => …)` GÖLGESİ
    + ifadeyle karışık JSX REDDEDİLİR; muaf kararı gerekçe ister ve deftere yazılır;
  * bayrak: `--ac` bütün yüzey sabitlerini + NSIS dil listesini + LangString bloğunu açar, `--kapat` dosyaları BAYT BAYT geri getirir,
    ayrışan yüzeyi `--denetle` yakalar;
  * kapsam: her yüzey dosyası bir gruba düşer, her grubun dosyası var, kritik dosyalar kritik grupta; `uret` durum / muaf / notu korur.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from scripts.i18n import auth_uret, bayrak, kapsam, katalog, launcher_uret, ortak, uygula  # noqa: E402

_NODE = shutil.which("node")
_TS_VAR = any((KOK / a / "node_modules" / "typescript" / "package.json").is_file() for a in ("apps/ui", "apps/web"))
ts_gerekli = pytest.mark.skipif(
    (not (_NODE and _TS_VAR)) and not capraz.ZORUNLU,
    reason="node ya da apps/ui|apps/web node_modules/typescript yok (npm ci)",
)


def _yaz(kok: Path, rel: str, metin: str) -> Path:
    p = kok / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(metin.encode("utf-8"))
    return p


def _json(kok: Path, rel: str) -> dict:
    return json.loads((kok / rel).read_text(encoding="utf-8"))


def _kos(betik: str, *arg: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KOK / "scripts" / "i18n" / betik), *arg], capture_output=True)


# ── katalog ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_bicimle_kanonik_denetle_yazmaz(tmp_path):
    ham = '{"z": "Son", "a": {"y": "İki", "b": "Bir"}}'
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/ornek.json", ham)
    assert katalog.bicimle(tmp_path, ["arayuz"], denetle=True) == [
        "apps/ui/src/i18n/tr/ornek.json",
        "apps/ui/src/i18n/en/ornek.json",
    ]
    assert (tmp_path / "apps/ui/src/i18n/tr/ornek.json").read_text(encoding="utf-8") == ham
    katalog.bicimle(tmp_path, ["arayuz"], denetle=False)
    assert (tmp_path / "apps/ui/src/i18n/tr/ornek.json").read_bytes() == (
        '{\n  "a": {\n    "b": "Bir",\n    "y": "İki"\n  },\n  "z": "Son"\n}\n'.encode("utf-8")
    )
    assert katalog.bicimle(tmp_path, ["arayuz"], denetle=True) == []


def test_esle_sorunlari_yakalar_temiz_katalogda_sessiz(tmp_path):
    tr = {
        "hasta": {
            "eksik": "Yalnız Türkçe",
            "bos": "Dolu",
            "yer": "{{ad}} kaydedildi",
            "seans_one": "{{count}} seans",
            "seans_other": "{{count}} seans",
            "dilli": "Dil: {{dil}}",
        }
    }
    en = {
        "hasta": {
            "bos": "  ",
            "yer": "Saved",
            "seans_one": "{{count}} session",
            "dilli": "Language: {{dil}}",
            "fazla": "Extra",
        }
    }
    _yaz(tmp_path, "apps/backend/i18n/tr.json", json.dumps(tr, ensure_ascii=False))
    _yaz(tmp_path, "apps/backend/i18n/en.json", json.dumps(en, ensure_ascii=False))
    s = "\n".join(katalog.esle(tmp_path, ["sunucu"]))
    for parca in (
        "en'de YOK: hasta.eksik",
        "tr'de YOK: hasta.fazla",
        "en: BOŞ değer: hasta.bos",
        "yer tutucu farklı hasta.yer",
        "çoğul biçimi eksik: hasta.seans_other",
        "['dil'] yer tutucusu yasak",
    ):
        assert parca in s, f"{parca!r} yakalanmadı:\n{s}"
    temiz = {"hasta": {"yer": "{{ad}} kaydedildi", "seans_one": "{{count}} seans", "seans_other": "{{count}} seans"}}
    temiz_en = {"hasta": {"yer": "{{ad}} saved", "seans_one": "{{count}} session", "seans_other": "{{count}} sessions"}}
    _yaz(tmp_path, "apps/backend/i18n/tr.json", json.dumps(temiz, ensure_ascii=False))
    _yaz(tmp_path, "apps/backend/i18n/en.json", json.dumps(temiz_en, ensure_ascii=False))
    assert katalog.esle(tmp_path, ["sunucu"]) == []


def test_anahtar_ekle_iki_dilde_farkli_TR_ustune_yazmaz(tmp_path):
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/backend/i18n/{dil}.json", "{}\n")
    katalog.anahtar_ekle(tmp_path, "sunucu", "hasta.kayit.tamam", "{{ad}} kaydedildi", "{{ad}} saved")
    assert _json(tmp_path, "apps/backend/i18n/tr.json") == {"hasta": {"kayit": {"tamam": "{{ad}} kaydedildi"}}}
    assert _json(tmp_path, "apps/backend/i18n/en.json") == {"hasta": {"kayit": {"tamam": "{{ad}} saved"}}}
    with pytest.raises(SystemExit, match="FARKLI"):
        katalog.anahtar_ekle(tmp_path, "sunucu", "hasta.kayit.tamam", "Başka metin", "Other")
    with pytest.raises(SystemExit, match="yer tutucu"):
        katalog.anahtar_ekle(tmp_path, "sunucu", "hasta.kayit.yeni", "{{ad}} geldi", "arrived")


def test_parca_cikar_geri_al_yer_tutucusu_farkli_ingilizceyi_reddeder(tmp_path):
    _yaz(
        tmp_path,
        "launcher/i18n/tr.json",
        json.dumps({"ui": {"a": "Bir", "b": "{{n}} dosya", "c": "Üç"}}, ensure_ascii=False),
    )
    _yaz(tmp_path, "launcher/i18n/en.json", json.dumps({"ui": {"c": "Three"}}))
    parca = katalog.parca_cikar(tmp_path, "launcher", None, eksik_en=True, boyut=10, aday=None)
    assert [p["anahtar"] for p in parca] == ["ui.a", "ui.b"]
    parca[0]["en"] = "One"
    parca[1]["en"] = "files"  # {{n}} unutuldu
    yazilan, red = katalog.parca_geri_al(tmp_path, parca, "launcher")
    assert yazilan == 1 and len(red) == 1 and "ui.b" in red[0]
    assert _json(tmp_path, "launcher/i18n/en.json") == {"ui": {"a": "One", "c": "Three"}}


def test_taban_katalogda_ya_da_muaf_olmayan_TR_metni_GERILEME(tmp_path):
    taban = {
        "metinler": [
            {
                "yuzey": "sunucu",
                "dosya": "apps/backend/x.py",
                "satir": 1,
                "metin": "Kaydedildi",
                "ham": "Kaydedildi",
                "tur": "donus",
            },
            {
                "yuzey": "sunucu",
                "dosya": "apps/backend/x.py",
                "satir": 2,
                "metin": "Silindi",
                "ham": "Silindi",
                "tur": "donus",
            },
            {
                "yuzey": "sunucu",
                "dosya": "apps/backend/y.py",
                "satir": 1,
                "metin": "Başka",
                "ham": "Başka",
                "tur": "donus",
            },
        ]
    }
    _yaz(tmp_path, "taban.json", json.dumps(taban, ensure_ascii=False))
    _yaz(tmp_path, "apps/backend/i18n/tr.json", json.dumps({"x": {"k": "Kaydedildi"}}, ensure_ascii=False))
    sorun = katalog.taban_karsilastir(tmp_path, ["apps/backend/x.py"], tmp_path / "taban.json")
    assert len(sorun) == 1 and "'Silindi'" in sorun[0]
    defter = {"dosyalar": {"apps/backend/x.py": {"muaf": [{"metin": "Silindi", "gerekce": "iç ileti"}]}}}
    _yaz(tmp_path, "i18n/kapsam.json", json.dumps(defter, ensure_ascii=False))
    assert katalog.taban_karsilastir(tmp_path, ["apps/backend/x.py"], tmp_path / "taban.json") == []


@pytest.mark.parametrize("sonu", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_adalani_ekle_kaynaklar_ts_ve_bos_kataloglar(tmp_path, sonu):
    """autocrlf'li çalışma kopyasında kaynaklar.ts CRLF'dir — ekleme `\\r\\r\\n` (sondaki boşluk, pre-commit kırmızısı) üretmemeli."""
    rel = "apps/ui/src/i18n/kaynaklar.ts"
    _yaz(tmp_path, rel, (KOK / rel).read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\n", sonu))
    katalog.adalani_ekle(tmp_path, "arayuz", "hastaListesi")
    katalog.adalani_ekle(tmp_path, "arayuz", "hastaListesi")  # ikinci kez: değişmez
    ts = (tmp_path / rel).read_bytes().decode("utf-8")
    assert "\r\r" not in ts and all(s == s.rstrip() for s in ts.split(sonu)), "satır sonunda boşluk / yarım CR"
    assert sonu == "\n" or "\n" not in ts.replace("\r\n", ""), "karışık satır sonu"
    assert ts.count('import trHastaListesi from "./tr/hastaListesi.json";') == 1
    assert ts.count('import enHastaListesi from "./en/hastaListesi.json";') == 1
    assert ts.count("  hastaListesi: trHastaListesi,") == 1 and ts.count("  hastaListesi: enHastaListesi,") == 1
    assert (tmp_path / "apps/ui/src/i18n/en/hastaListesi.json").read_text(encoding="utf-8") == "{}\n"


# ── uygula (uçtan uca) ───────────────────────────────────────────────────────────────────────────────────────

_PY = """from fastapi import HTTPException

VARSAYILAN = "Modül düzeyi metin"


def bul(hasta_id, not_metni="Varsayılan argüman metni"):
    if not hasta_id:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    adet = 3
    return f"{adet} seans kaydedildi"


def dil_hatasi(dil):
    return f"Dil kodu geçersiz: {dil}"
"""

_PY_BEKLENEN = """from fastapi import HTTPException
from utils import ceviri

VARSAYILAN = "Modül düzeyi metin"


def bul(hasta_id, not_metni="Varsayılan argüman metni"):
    if not hasta_id:
        raise HTTPException(status_code=404, detail=ceviri.t("ornek.hastaBulunamadi"))
    adet = 3
    return ceviri.t("ornek.seansKaydedildi", adet=adet)


def dil_hatasi(dil):
    return f"Dil kodu geçersiz: {dil}"
"""


def _uctan_uca(
    tmp_path: Path, dosya: str, anahtarlar: dict[str, str], ingilizce: dict[str, str], muaf: dict[str, str]
) -> dict:
    """cikar → sablon → (oturumun düzenlemesi) → uygula; CLI'lar gerçek alt süreçte."""
    assert (
        _kos("cikar.py", "--kok", str(tmp_path), "--dosya", dosya, "--cikti", str(tmp_path / "aday.json")).returncode
        == 0
    )
    assert (
        _kos(
            "uygula.py",
            "--kok",
            str(tmp_path),
            "sablon",
            str(tmp_path / "aday.json"),
            "--cikti",
            str(tmp_path / "eslem.json"),
        ).returncode
        == 0
    )
    eslem = json.loads((tmp_path / "eslem.json").read_text(encoding="utf-8"))
    for i in eslem["islemler"]:
        if i["metin"] in muaf:
            i["karar"], i["gerekce"] = "muaf", muaf[i["metin"]]
        i["anahtar"] = anahtarlar.get(i["metin"], i["anahtar"])
        i["en"] = ingilizce.get(i["metin"], "")
    (tmp_path / "eslem.json").write_text(json.dumps(eslem, ensure_ascii=False), encoding="utf-8")
    r = _kos(
        "uygula.py",
        "--kok",
        str(tmp_path),
        "uygula",
        str(tmp_path / "eslem.json"),
        "--rapor",
        str(tmp_path / "rapor.json"),
    )
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return json.loads((tmp_path / "rapor.json").read_text(encoding="utf-8"))


def test_uygula_python_ucten_uca(tmp_path):
    dosya = "apps/backend/servers/ornek.py"
    _yaz(tmp_path, dosya, _PY)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/backend/i18n/{dil}.json", "{}\n")
    _yaz(tmp_path, "i18n/kapsam.json", '{"dosyalar": {}}\n')
    rapor = _uctan_uca(
        tmp_path,
        dosya,
        {"Hasta bulunamadı": "ornek.hastaBulunamadi", "{{adet}} seans kaydedildi": "ornek.seansKaydedildi"},
        {"Hasta bulunamadı": "Patient not found"},
        {"Modül düzeyi metin": "iç sabit (örnek)"},
    )
    assert (tmp_path / dosya).read_text(encoding="utf-8") == _PY_BEKLENEN
    nedenler = {r["metin"]: r["neden"] for r in rapor["reddedilen"]}
    assert "modül düzeyi" in nedenler["Varsayılan argüman metni"]  # varsayılan argüman içe aktarmada değerlendirilir
    assert "çakışır" in nedenler["Dil kodu geçersiz: {{dil}}"]
    assert _json(tmp_path, "apps/backend/i18n/tr.json") == {
        "ornek": {"hastaBulunamadi": "Hasta bulunamadı", "seansKaydedildi": "{{adet}} seans kaydedildi"}
    }
    assert _json(tmp_path, "apps/backend/i18n/en.json") == {"ornek": {"hastaBulunamadi": "Patient not found"}}
    assert _json(tmp_path, "i18n/kapsam.json")["dosyalar"][dosya]["muaf"] == [
        {"metin": "Modül düzeyi metin", "gerekce": "iç sabit (örnek)"}
    ]


def test_uygula_muaf_karari_gerekcesiz_DURUR(tmp_path):
    eslem = {"islemler": [{"dosya": "a.py", "satir": 1, "metin": "X", "karar": "muaf", "gerekce": " "}]}
    with pytest.raises(SystemExit, match="gerekçesiz"):
        uygula.uygula(tmp_path, eslem)


_TSX = """import React from "react";
import { Text, View } from "react-native";

const BASLIK = "Modül düzeyi başlık";

export function Kart({ ad }: { ad: string }) {
  const liste = ["a"];
  return (
    <View accessibilityLabel="Kart alanı">
      <Text>Hasta kaydı</Text>
      <Text>{`Merhaba ${ad}, hoş geldiniz`}</Text>
      {liste.map((t) => (
        <Text key={t}>Gölgeli metin</Text>
      ))}
      <Text>Toplam: {ad}</Text>
    </View>
  );
}
"""

_TSX_BEKLENEN = """import React from "react";
import { Text, View } from "react-native";
import { useTranslation } from "react-i18next";

const BASLIK = "Modül düzeyi başlık";

export function Kart({ ad }: { ad: string }) {
  const { t } = useTranslation();
  const liste = ["a"];
  return (
    <View accessibilityLabel={t("kart.alan")}>
      <Text>{t("kart.hastaKaydi")}</Text>
      <Text>{t("kart.merhaba", { ad })}</Text>
      {liste.map((t) => (
        <Text key={t}>Gölgeli metin</Text>
      ))}
      <Text>Toplam: {ad}</Text>
    </View>
  );
}
"""

_TS_ANAHTAR = {
    "Kart alanı": "kart.alan",
    "Hasta kaydı": "kart.hastaKaydi",
    "Merhaba {{ad}}, hoş geldiniz": "kart.merhaba",
}


@ts_gerekli
def test_uygula_tsx_ucten_uca_arayuz_bicimi(tmp_path):
    dosya = "apps/ui/src/components/Kart.tsx"
    _yaz(tmp_path, dosya, _TSX)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/kart.json", "{}\n")
    rapor = _uctan_uca(tmp_path, dosya, _TS_ANAHTAR, {"Hasta kaydı": "Patient record"}, {})
    assert (tmp_path / dosya).read_text(encoding="utf-8") == _TSX_BEKLENEN
    nedenler = {r["metin"]: r["neden"] for r in rapor["reddedilen"]}
    assert "modül düzeyi" in nedenler["Modül düzeyi başlık"]
    assert "GÖLGELEYEN" in nedenler["Gölgeli metin"]
    assert "karışık JSX" in nedenler["Toplam:"]
    assert _json(tmp_path, "apps/ui/src/i18n/tr/kart.json") == {
        "alan": "Kart alanı",
        "hastaKaydi": "Hasta kaydı",
        "merhaba": "Merhaba {{ad}}, hoş geldiniz",
    }
    assert _json(tmp_path, "apps/ui/src/i18n/en/kart.json") == {"hastaKaydi": "Patient record"}


@ts_gerekli
def test_uygula_tsx_site_bicimi_tek_tirnak_noktali_virgulsuz(tmp_path):
    dosya = "apps/web/src/components/Kart.tsx"
    kaynak = _TSX.replace('"react"', "'react'").replace('"react-native"', "'react-native'").replace(";\n", "\n")
    _yaz(tmp_path, dosya, kaynak)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/web/src/i18n/{dil}/kart.json", "{}\n")
    _uctan_uca(tmp_path, dosya, _TS_ANAHTAR, {}, {})
    sonuc = (tmp_path / dosya).read_text(encoding="utf-8")
    assert "import { useTranslation } from 'react-i18next'\n" in sonuc
    assert "  const { t } = useTranslation()\n" in sonuc
    assert "accessibilityLabel={t('kart.alan')}" in sonuc and "{t('kart.merhaba', { ad })}" in sonuc


@ts_gerekli
def test_uygula_tsx_t_zaten_varsa_ikinci_hook_EKLENMEZ(tmp_path):
    dosya = "apps/ui/src/components/Kart.tsx"
    kaynak = _TSX_BEKLENEN.replace('<Text>{t("kart.hastaKaydi")}</Text>', "<Text>Yeni satır</Text>")
    _yaz(tmp_path, dosya, kaynak)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/kart.json", "{}\n")
    _uctan_uca(tmp_path, dosya, {"Yeni satır": "kart.yeniSatir"}, {}, {})
    sonuc = (tmp_path / dosya).read_text(encoding="utf-8")
    assert sonuc.count("useTranslation()") == 1 and sonuc.count("react-i18next") == 1
    assert '<Text>{t("kart.yeniSatir")}</Text>' in sonuc


# ── bayrak ───────────────────────────────────────────────────────────────────────────────────────────────────

_BAYRAK_DOSYALARI = (
    *bayrak.TS_SABITLERI,
    bayrak.RS_SABITI,
    bayrak.PY_SABITI,  # I18NI-A3.4: sunucunun istek dışı dili
    bayrak.ANA,
    launcher_uret.TAURI_CONF,
    launcher_uret.HOOKS_YOLU,
    launcher_uret.JS_YOLU,
    "launcher/i18n/tr.json",
    "launcher/i18n/en.json",
    # I18N-P1: auth sayfaları kataloğu bayrakla birlikte üretilir (`auth_uret.py`) — kaynağı (authSayfa) + üretilen dosya
    auth_uret.JS_YOLU,
    "apps/ui/src/i18n/tr/authSayfa.json",
    "apps/ui/src/i18n/en/authSayfa.json",
)


def test_bayrak_depoda_tutarli():
    """Depo değeri BİLİNÇLİ pin: 14-I18N-INCELEME İngilizce seçeneğini AÇTI (2026-10-21). Kapatmak sahip / yayın kararıdır (`bayrak.py --kapat`
    + bu satır); bayrağın yanlışlıkla kapanması ya da yüzeylerin ayrışması burada KIRMIZI."""
    assert bayrak.denetle(KOK) == []
    assert bayrak.ana_deger(KOK) is True


def test_bayrak_ac_hepsini_acar_kapat_BAYT_BAYT_geri_getirir(tmp_path):
    for rel in _BAYRAK_DOSYALARI:
        _yaz(tmp_path, rel, "")
        shutil.copyfile(KOK / rel, tmp_path / rel)
    # autocrlf'li çalışma kopyası taklidi: ana kaynak CRLF — geri dönüş satır sonunu da korumalı.
    ana = tmp_path / bayrak.ANA
    ana.write_bytes(ana.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    # I18NI-A3.8: depo bayrağı AÇIKSA (bayrağı açan commit'ten sonra) geçici kopya önce KAPALI başlangıca indirilir — test depo durumunu
    # VARSAYMAZ (ajan ölçümü: açıkken bu test kırmızıydı); açık başlangıçtan dönüş aşağıdaki karşıt testte.
    if bayrak.ana_deger(tmp_path):
        assert bayrak.main(["--kapat", "--kok", str(tmp_path)]) == 0
    once = {rel: (tmp_path / rel).read_bytes() for rel in _BAYRAK_DOSYALARI}
    assert bayrak.main(["--ac", "--kok", str(tmp_path)]) == 0
    degerler = bayrak.yuzey_degerleri(tmp_path)
    assert all(degerler[y] is True for y in (*bayrak.TS_SABITLERI, bayrak.RS_SABITI, bayrak.PY_SABITI)), degerler
    assert degerler[launcher_uret.TAURI_CONF] == ["Turkish", "English"]
    hooks = (tmp_path / launcher_uret.HOOKS_YOLU).read_text(encoding="utf-8")
    assert ' 1033 "' in hooks and ' 1055 "' in hooks  # İngilizce + Türkçe LangString
    assert "var EN_ACIK = true;" in (tmp_path / auth_uret.JS_YOLU).read_text(
        encoding="utf-8"
    )  # auth sayfaları bayrakla açıldı
    assert bayrak.main(["--kapat", "--kok", str(tmp_path)]) == 0
    farkli = [rel for rel in _BAYRAK_DOSYALARI if (tmp_path / rel).read_bytes() != once[rel]]
    assert farkli == [], f"--kapat dosyaları geri getirmedi: {farkli}"


def test_bayrak_kapat_hepsini_kapatir_ac_BAYT_BAYT_geri_getirir(tmp_path):
    """I18NI-A3.8 karşıt yön: AÇIK başlangıçtan `--kapat` her yüzeyi kapatır (NSIS yalnız Türkçe), `--ac` dosyaları bayt bayt geri getirir."""
    for rel in _BAYRAK_DOSYALARI:
        _yaz(tmp_path, rel, "")
        shutil.copyfile(KOK / rel, tmp_path / rel)
    ana = tmp_path / bayrak.ANA
    ana.write_bytes(ana.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    if not bayrak.ana_deger(tmp_path):
        assert bayrak.main(["--ac", "--kok", str(tmp_path)]) == 0
    once = {rel: (tmp_path / rel).read_bytes() for rel in _BAYRAK_DOSYALARI}
    assert bayrak.main(["--kapat", "--kok", str(tmp_path)]) == 0
    degerler = bayrak.yuzey_degerleri(tmp_path)
    assert all(degerler[y] is False for y in (*bayrak.TS_SABITLERI, bayrak.RS_SABITI, bayrak.PY_SABITI)), degerler
    assert degerler[launcher_uret.TAURI_CONF] == ["Turkish"]
    hooks = (tmp_path / launcher_uret.HOOKS_YOLU).read_text(encoding="utf-8")
    assert ' 1033 "' not in hooks and ' 1055 "' in hooks  # yalnız Türkçe LangString (yüklenmemiş dile tablo yazılmaz)
    assert "var EN_ACIK = false;" in (tmp_path / auth_uret.JS_YOLU).read_text(encoding="utf-8")
    assert bayrak.main(["--ac", "--kok", str(tmp_path)]) == 0
    farkli = [rel for rel in _BAYRAK_DOSYALARI if (tmp_path / rel).read_bytes() != once[rel]]
    assert farkli == [], f"--ac dosyaları geri getirmedi: {farkli}"


def test_bayrak_ayrisan_yuzeyi_denetle_YAKALAR(tmp_path):
    for rel in _BAYRAK_DOSYALARI:
        _yaz(tmp_path, rel, "")
        shutil.copyfile(KOK / rel, tmp_path / rel)
    p = tmp_path / "apps/web/src/i18n/bayrak.ts"
    # I18NI-A3.8: depo değerinin TERSİNE çevrilir (bayrak açık ya da kapalı — durum varsayılmaz)
    simdi, ters = ("true", "false") if bayrak.ana_deger(KOK) else ("false", "true")
    p.write_text(p.read_text(encoding="utf-8").replace(f"= {simdi}", f"= {ters}"), encoding="utf-8")
    sorun = bayrak.denetle(tmp_path)
    assert len(sorun) == 1 and "apps/web/src/i18n/bayrak.ts" in sorun[0]


# ── kapsam ───────────────────────────────────────────────────────────────────────────────────────────────────

_ONEK = {"arayuz": "arayuz-", "sunucu": "sunucu-", "launcher": "launcher-", "site": "site-", "dema": "dema-"}


def test_kapsam_her_yuzey_dosyasi_kendi_yuzeyinin_grubunda_her_grup_dolu():
    dolu = set()
    for y in ortak.YUZEYLER:
        for f in ortak.yuzey_dosyalari(y):
            g = kapsam.grup_bul(f)
            assert g.startswith(_ONEK[y]), f"{f} ({y}) → {g}"
            dolu.add(g)
    bos = [g for g, *_ in kapsam.GRUPLAR if g not in dolu]
    assert bos == [], f"dosyası olmayan grup (kural yazım hatası?): {bos}"


@pytest.mark.parametrize(
    "dosya,grup",
    [
        ("apps/ui/src/components/ui/GlobalEmergencyStop.tsx", "arayuz-05b-guvenlik-kritik"),
        ("apps/ui/src/screens/ControlScreen.tsx", "arayuz-05a-kontrol-kritik"),
        ("apps/backend/servers/api_server.py", "sunucu-10b-ana-sunucu"),
        ("launcher/app/windows/hooks.nsi", "launcher-11d-nsis"),
        ("apps/web/src/pages/Legal.tsx", "site-12e-yasal"),
    ],
)
def test_kapsam_kritik_ve_yasal_dosyalar_dogru_grupta(dosya, grup):
    assert (KOK / dosya).is_file(), dosya
    assert kapsam.grup_bul(dosya) == grup
    assert kapsam._GRUP[grup][2] == (
        grup
        in {"arayuz-05a-kontrol-kritik", "arayuz-05b-guvenlik-kritik", "sunucu-10b-ana-sunucu", "launcher-11d-nsis"}
    )


def test_kapsam_uret_durumu_korur_isaretle_muafi_bozmaz(tmp_path):
    for rel in ("apps/backend/servers/a_router.py", "apps/backend/servers/b_router.py", "apps/backend/x.py"):
        _yaz(tmp_path, rel, "x = 1\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    taban = tmp_path / "taban.json"
    taban.write_text(json.dumps({"metinler": [{"dosya": "apps/backend/x.py"}] * 2}), encoding="utf-8")
    d = kapsam.uret(tmp_path, taban)
    assert d["dosyalar"]["apps/backend/x.py"]["metin"] == 2
    assert {k: v["grup"] for k, v in d["dosyalar"].items()} == {
        "apps/backend/servers/a_router.py": "sunucu-10a-yonlendirici",
        "apps/backend/servers/b_router.py": "sunucu-10a-yonlendirici",
        "apps/backend/x.py": "sunucu-10h-servis",
    }
    assert (
        kapsam.main(["--kok", str(tmp_path), "dosya", "apps/backend/servers/b_router.py", "muaf", "--gerekce", "iç"])
        == 0
    )
    assert kapsam.main(["--kok", str(tmp_path), "isaretle", "sunucu-10a-yonlendirici", "tamam"]) == 0
    d = kapsam.uret(tmp_path, taban)  # yeniden üretim kararları KORUR
    durum = {k: v["durum"] for k, v in d["dosyalar"].items()}
    assert durum == {
        "apps/backend/servers/a_router.py": "tamam",
        "apps/backend/servers/b_router.py": "muaf",
        "apps/backend/x.py": "bekliyor",
    }
    assert {g["ad"]: g["durum"] for g in d["gruplar"]}["sunucu-10a-yonlendirici"] == "tamam"
    with pytest.raises(SystemExit, match="GEREKÇE"):
        kapsam.main(["--kok", str(tmp_path), "dosya", "apps/backend/x.py", "muaf"])


def test_kapsam_muaf_mi_dosya_genel_desen_ve_muaf_dosya():
    defter = {
        "genelMuaf": [{"metin": "PEMF Vet", "gerekce": "ürün"}],
        "genelMuafDesen": [{"desen": r"btn-\w+", "gerekce": "CSS"}],
        "dosyalar": {
            "a.tsx": {"durum": "tamam", "muaf": [{"metin": "İç ad", "gerekce": "iç"}]},
            "b.tsx": {"durum": "muaf", "not": "altyapı"},
        },
    }
    assert kapsam.muaf_mi(defter, "a.tsx", "İç ad") and not kapsam.muaf_mi(defter, "c.tsx", "İç ad")
    assert kapsam.muaf_mi(defter, "c.tsx", "PEMF Vet") and kapsam.muaf_mi(defter, "c.tsx", "btn-primary")
    assert not kapsam.muaf_mi(defter, "c.tsx", "btn-primary ve metin")  # desen TAM eşleşmeli
    assert kapsam.muaf_mi(defter, "b.tsx", "Her şey")


def test_kapsam_metin_tarayan_listesi_bilinen_kapilari_bulur():
    liste = {t: (andigi, cevrildi) for t, andigi, cevrildi in kapsam.metin_tarayan_testler(KOK)}
    andigi, cevrildi = liste["tests/test_kaldirma_yetim_surec_temizligi.py"]
    assert "launcher/app/windows/hooks.nsi" in andigi and cevrildi
    andigi, cevrildi = liste["tests/test_D191_dema_simulator_A37_tanitim_etiketi_iddiasiz.py"]
    # dema-13 göçünden SONRA kapı GÖRÜNEN metin yardımcısını kullanır → "çevrildi" (göç öncesi: not cevrildi)
    assert "dema-terapi-simülatörü/src/App.tsx" in andigi and cevrildi
    assert len(liste) >= 150, len(liste)


@ts_gerekli
def test_uygula_tsx_CRLF_cok_satirli_jsx_metni_ve_html_varligi(tmp_path):
    """autocrlf'li çalışma kopyası (CRLF): eklenen hook / içe aktarma CRLF; çok satırlı JSX metni yalnız-boşluk satırı BIRAKMAZ (JsxText
    getStart baştaki boşluğu atlar); `&quot;` katalogda çözülmüş (React'in çizdiği gibi)."""
    dosya = "apps/ui/src/components/Kart.tsx"
    satirlar = [
        'import React from "react";',
        'import { Text } from "react-native";',
        "",
        "export function Kart() {",
        "  return (",
        "    <Text>",
        "      Uzun bir açıklama",
        "      iki satırda &quot;tırnaklı&quot;.",
        "    </Text>",
        "  );",
        "}",
        "",
    ]
    _yaz(tmp_path, dosya, "\r\n".join(satirlar))
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/kart.json", "{}\n")
    _uctan_uca(tmp_path, dosya, {'Uzun bir açıklama iki satırda "tırnaklı".': "kart.aciklama"}, {}, {})
    beklenen = [
        'import React from "react";',
        'import { Text } from "react-native";',
        'import { useTranslation } from "react-i18next";',
        "",
        "export function Kart() {",
        "  const { t } = useTranslation();",
        "  return (",
        "    <Text>",
        '      {t("kart.aciklama")}',
        "    </Text>",
        "  );",
        "}",
        "",
    ]
    assert (tmp_path / dosya).read_bytes().decode("utf-8") == "\r\n".join(beklenen)
    assert _json(tmp_path, "apps/ui/src/i18n/tr/kart.json") == {"aciklama": 'Uzun bir açıklama iki satırda "tırnaklı".'}


def test_uygula_python_CRLF_ice_aktarma_satir_sonu_dosyaninki(tmp_path):
    dosya = "apps/backend/servers/ornek.py"
    _yaz(tmp_path, dosya, _PY.replace("\n", "\r\n"))
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/backend/i18n/{dil}.json", "{}\n")
    _yaz(tmp_path, "i18n/kapsam.json", '{"dosyalar": {}}\n')
    _uctan_uca(tmp_path, dosya, {"Hasta bulunamadı": "ornek.hastaBulunamadi"}, {}, {})
    b = (tmp_path / dosya).read_bytes()
    assert b.count(b"\n") == b.count(b"\r\n"), "karışık satır sonu"
    assert b"\r\nfrom utils import ceviri\r\n" in b


_TSX_KANCA = """import React, { useCallback } from "react";
import { Text } from "react-native";

export function Liste({ basarisiz, ad }: { basarisiz: number; ad: string }) {
  const kaydet = useCallback(async () => {
    goster(`${basarisiz} hasta AKTARILAMADI`);
    goster(`${ad} kaydedildi`);
  }, [basarisiz, ad]);
  const bos = useCallback(() => goster("Boş liste"), []);
  return <Text onPress={kaydet}>{bos.name}</Text>;
}
"""


@ts_gerekli
def test_uygula_tsx_kanca_bagimliligi_yer_adi_ve_cogul(tmp_path):
    """useCallback içindeki metin çevrilince dizisine `t` eklenir (yoksa dil değişince eski `t` kapalı kalır); `yerAdlari` yer tutucuyu
    anlamlı adla değiştirir (çağrı + katalog); `cogul` → `_one` / `_other`, çağrı `count` ile."""
    dosya = "apps/ui/src/components/Liste.tsx"
    _yaz(tmp_path, dosya, _TSX_KANCA)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/liste.json", "{}\n")
    assert (
        _kos("cikar.py", "--kok", str(tmp_path), "--dosya", dosya, "--cikti", str(tmp_path / "aday.json")).returncode
        == 0
    )
    assert (
        _kos(
            "uygula.py",
            "--kok",
            str(tmp_path),
            "sablon",
            str(tmp_path / "aday.json"),
            "--cikti",
            str(tmp_path / "e.json"),
        ).returncode
        == 0
    )
    e = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    ayar = {
        "{{basarisiz}} hasta AKTARILAMADI": {
            "anahtar": "liste.aktarilamadi",
            "yerAdlari": {"basarisiz": "count"},
            "cogul": True,
            "en": {
                "one": "{{count}} patient could NOT be imported",
                "other": "{{count}} patients could NOT be imported",
            },
        },
        "{{ad}} kaydedildi": {
            "anahtar": "liste.kaydedildi",
            "yerAdlari": {"ad": "hastaAdi"},
            "en": "{{hastaAdi}} saved",
        },
        "Boş liste": {"anahtar": "liste.bos", "en": "Empty list"},
    }
    for i in e["islemler"]:
        i.update(ayar[i["metin"]])
    (tmp_path / "e.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    r = _kos("uygula.py", "--kok", str(tmp_path), "uygula", str(tmp_path / "e.json"))
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    s = (tmp_path / dosya).read_text(encoding="utf-8")
    assert 'goster(t("liste.aktarilamadi", { count: basarisiz }));' in s
    assert 'goster(t("liste.kaydedildi", { hastaAdi: ad }));' in s
    assert "}, [basarisiz, ad, t]);" in s, "useCallback bağımlılığına t eklenmedi"
    assert 'useCallback(() => goster(t("liste.bos")), [t]);' in s, "boş bağımlılık dizisine t eklenmedi"
    tr, en = _json(tmp_path, "apps/ui/src/i18n/tr/liste.json"), _json(tmp_path, "apps/ui/src/i18n/en/liste.json")
    assert tr == {
        "aktarilamadi_one": "{{count}} hasta AKTARILAMADI",
        "aktarilamadi_other": "{{count}} hasta AKTARILAMADI",
        "bos": "Boş liste",
        "kaydedildi": "{{hastaAdi}} kaydedildi",
    }
    assert en["aktarilamadi_one"].startswith("{{count}} patient ") and en["kaydedildi"] == "{{hastaAdi}} saved"


def test_taban_yer_tutucu_adi_ve_birlesik_parca_KENDI_anahtarinda(tmp_path):
    """Göçte meşru dönüşümler gerileme sayılmaz: yer tutucu yeniden adlandırma (`{{days}}` → `{{gun}}`) ve şablon / birleşik cümlenin
    parçası (`' seans kaydı '`) dosyanın KENDİ kullandığı anahtarın TR değerinde. Aynı parça BAŞKA dosyanın anahtarındaysa karşılanmaz."""
    metinler = [
        {
            "yuzey": "arayuz",
            "dosya": "apps/ui/src/A.tsx",
            "satir": 1,
            "metin": "{{days}} gün sonra silinir",
            "ham": "{{days}} gün sonra silinir",
            "tur": "sablon",
        },
        {
            "yuzey": "arayuz",
            "dosya": "apps/ui/src/A.tsx",
            "satir": 2,
            "metin": "seans kaydı",
            "ham": " seans kaydı ",
            "tur": "jsx-metin",
        },
        {
            "yuzey": "arayuz",
            "dosya": "apps/ui/src/B.tsx",
            "satir": 1,
            "metin": "seans kaydı",
            "ham": " seans kaydı ",
            "tur": "jsx-metin",
        },
    ]
    _yaz(tmp_path, "taban.json", json.dumps({"metinler": metinler}, ensure_ascii=False))
    _yaz(
        tmp_path,
        "apps/ui/src/i18n/tr/x.json",
        json.dumps(
            {
                "sil": "{{gun}} gün sonra silinir",
                "bekleyen_one": "{{count}} seans kaydı bekliyor",
                "bekleyen_other": "{{count}} seans kaydı bekliyor",
            },
            ensure_ascii=False,
        ),
    )
    _yaz(tmp_path, "apps/ui/src/A.tsx", 'export const A = () => t("x.sil") + t("x.bekleyen", { count: 2 });\n')
    _yaz(tmp_path, "apps/ui/src/B.tsx", "export const B = () => null;\n")
    sorun = katalog.taban_karsilastir(tmp_path, ["apps/ui/src/A.tsx", "apps/ui/src/B.tsx"], tmp_path / "taban.json")
    assert len(sorun) == 1 and "B.tsx" in sorun[0], sorun


def test_uygula_python_COK_SATIRLI_fstring_ifadesi_konumdan_bagimsiz(tmp_path):
    """Python 3.10'da çok satırlı f-string içindeki ifade konumları yanlış — kaynak dilimi bozuk kod üretiyordu (PDF altbilgisi);
    argüman `ast.unparse` ile yazılır, sonuç derlenir ve ifade AYNEN taşınır."""
    import ast as _ast

    dosya = "apps/backend/servers/rapor.py"
    kaynak = (
        "from datetime import datetime\n\n\n"
        "def altbilgi(n):\n"
        '    metin = f"""\n'
        "    Toplam {n} seans.\n"
        "    Rapor tarihi: {datetime.now().strftime('%d/%m/%Y')}\n"
        '    """\n'
        "    return metin\n"
    )
    _yaz(tmp_path, dosya, kaynak)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/backend/i18n/{dil}.json", "{}\n")
    _yaz(tmp_path, "i18n/kapsam.json", '{"dosyalar": {}}\n')
    assert (
        _kos("cikar.py", "--kok", str(tmp_path), "--dosya", dosya, "--cikti", str(tmp_path / "aday.json")).returncode
        == 0
    )
    assert (
        _kos(
            "uygula.py",
            "--kok",
            str(tmp_path),
            "sablon",
            str(tmp_path / "aday.json"),
            "--cikti",
            str(tmp_path / "e.json"),
        ).returncode
        == 0
    )
    e = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert len(e["islemler"]) == 1
    e["islemler"][0].update({"anahtar": "rapor.altbilgi", "yerAdlari": {"deger2": "tarih"}})
    (tmp_path / "e.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    assert _kos("uygula.py", "--kok", str(tmp_path), "uygula", str(tmp_path / "e.json")).returncode == 0
    agac = _ast.parse((tmp_path / dosya).read_text(encoding="utf-8"))  # bozuk kod → SyntaxError
    cagri = next(n for n in _ast.walk(agac) if isinstance(n, _ast.Call) and _ast.unparse(n.func) == "ceviri.t")
    assert {k.arg: _ast.unparse(k.value) for k in cagri.keywords} == {
        "n": "n",
        "tarih": "datetime.now().strftime('%d/%m/%Y')",
    }
    assert _json(tmp_path, "apps/backend/i18n/tr.json")["rapor"]["altbilgi"].count("{{tarih}}") == 1


# ── bileşen / hook DIŞI işlev (I18N-P1): `i18n.t` + `import i18n from "i18next"` ────────────────────────────────

_TS_YARDIMCI = """import { apiGet } from "@/services/apiClient";

export function hataMetni(n: number): string {
  if (n === 404) return "Hasta bulunamadı";
  return `Sunucu hatası (${n})`;
}

export const SABIT = "Modül düzeyi başlık";
"""


@ts_gerekli
def test_uygula_ts_bilesen_disi_islev_i18n_t_ve_import(tmp_path):
    dosya = "apps/ui/src/services/hata.ts"
    _yaz(tmp_path, dosya, _TS_YARDIMCI)
    for dil in ("tr", "en"):
        _yaz(tmp_path, f"apps/ui/src/i18n/{dil}/hata.json", "{}\n")
    rapor = _uctan_uca(
        tmp_path,
        dosya,
        {"Hasta bulunamadı": "hata.hastaBulunamadi", "Sunucu hatası ({{n}})": "hata.sunucu"},
        {"Hasta bulunamadı": "Patient not found"},
        {},
    )
    sonuc = (tmp_path / dosya).read_text(encoding="utf-8")
    assert 'import i18n from "i18next";' in sonuc and sonuc.count("import i18n") == 1
    assert 'return i18n.t("hata.hastaBulunamadi");' in sonuc
    assert 'return i18n.t("hata.sunucu", { n });' in sonuc
    assert "useTranslation" not in sonuc and "const { t }" not in sonuc  # bileşen DEĞİL: hook eklenmez
    nedenler = {r["metin"]: r["neden"] for r in rapor["reddedilen"]}
    assert "modül düzeyi" in nedenler.get("Modül düzeyi başlık", "")
    assert _json(tmp_path, "apps/ui/src/i18n/tr/hata.json") == {
        "hastaBulunamadi": "Hasta bulunamadı",
        "sunucu": "Sunucu hatası ({{n}})",
    }
