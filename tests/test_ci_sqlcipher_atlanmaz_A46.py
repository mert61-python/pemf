# -*- coding: utf-8 -*-
"""A-46 · D2.07 (B-3.47) — CI'DA sqlcipher3 ATLANAMAZ.

SAHİP KARARI A-46: "sqlcipher3 kurulamazsa CI KIRMIZI olur; şifreleme/kurtarma testleri sessizce atlanmaz."

ÖLÇÜLEN ARIZA (2026-10-06, 2-A). `.github/workflows/tests.yml`:
  · Linux işinde kurulum `pip install sqlcipher3-binary || pip install sqlcipher3 || echo "... duz-metin
    yoluyla kosulacak"` idi → kurulum düşse de iş sürüyordu.
  · Windows işinde sqlcipher3 HİÇ kurulmuyordu ("wheel yok" varsayımı; ürün Windows'ta sqlcipher3==0.6.2
    tekerleğiyle paketlenir — requirements.txt).
  · Şifreleme / göç / karantina kapılarının çoğu `importorskip("sqlcipher3")` / `skipif(... is None)` ile
    korunuyor → CI-Windows eşdeğerinde (sqlcipher3 içe aktarılamaz) bu kapılar ATLANIYOR ve iş YEŞİL bitiyordu.
    Örnek: karantina bütçesini 1 denemeye indiren mutant, dosyanın tamamı atlandığı için YEŞİLDİ.

BU DOSYA CI'I ÇALIŞTIRMAZ (A-43: hiçbir şey itilmez). İki şeyi kilitler:
  1. İş akışı TANIMI: backend işinde (YS1b · Y320: yalnız `windows-latest`) sqlcipher3 kurulur ve İÇE AKTARILARAK doğrulanır (düşüş yok);
     test adımı junit üretir; ardından `scripts/ci_sqlcipher_atlama_kapisi.py` aynı dosyayla koşar.
  2. Sayaç betiğinin DAVRANIŞI: "sqlcipher" nedenli atlama (harf duyarsız) → 1; yoksa 0; junit yok/boş → 2.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[1]
IS_AKISI = KOK / ".github" / "workflows" / "tests.yml"
BETIK = KOK / "scripts" / "ci_sqlcipher_atlama_kapisi.py"

#: Kurulumu SESSİZCE yutan biçimler.
_DUSUSLER = (re.compile(r"\|\|\s*echo\b"), re.compile(r"\|\|\s*true\b"), re.compile(r"\|\|\s*exit\s+0\b"))
#: matrix `os` → `runner.os`
_ISLETIM = {"ubuntu-latest": "Linux", "windows-latest": "Windows"}


def _backend():
    return yaml.safe_load(IS_AKISI.read_text(encoding="utf-8"))["jobs"]["backend"]


def _kapsar(adim: dict, isletim: str) -> bool:
    """Adımın `if:` koşulu bu işletim sisteminde koşar mı? (Yalnız iş akışındaki basit biçimler.)"""
    kosul = str(adim.get("if", "")).strip()
    # YS1g: junit eseri adımı `if: always()` — her işletim sisteminde (kırmızıda da) koşar.
    if not kosul or kosul in ("always()", "${{ always() }}"):
        return True
    m = re.fullmatch(r"runner\.os\s*(==|!=)\s*'(\w+)'", kosul)
    assert m, f"tanınmayan adım koşulu (kapı genişletilmeli): {kosul!r}"
    return (m.group(2) == isletim) == (m.group(1) == "==")


def _isletimler() -> list[str]:
    os_listesi = _backend()["strategy"]["matrix"]["os"]
    return [_ISLETIM[o] for o in os_listesi]


def test_KRITIK_windows_isinde_sqlcipher3_KURULUR_ICE_AKTARILIR_dusus_YOK():
    """MUTASYON: Windows kurulum adımını silmek · kuruluma `|| echo …` düşüşü koymak · içe aktarma doğrulamasını silmek ·
    `continue-on-error: true` → KIRMIZI. (YS1b · Y320: Linux işi kalktı — matris yalnız `windows-latest`.)"""
    adimlar = _backend()["steps"]
    isletimler = _isletimler()
    assert set(isletimler) == {"Windows"}, f"backend matrisi yalnız windows-latest olmalı (Y320): {isletimler}"
    for isletim in isletimler:
        kurulum = [
            (i, a)
            for i, a in enumerate(adimlar)
            if _kapsar(a, isletim) and re.search(r"pip install[^\n]*\bsqlcipher3\b", str(a.get("run", "")))
        ]
        assert kurulum, f"{isletim} işinde sqlcipher3 KURULMUYOR -> şifreleme/göç/karantina kapıları CI'da atlanır"
        test_adimi = next(
            i for i, a in enumerate(adimlar) if _kapsar(a, isletim) and "pytest tests" in str(a.get("run", ""))
        )
        for i, adim in kurulum:
            run = str(adim.get("run", ""))
            assert i < test_adimi, f"{isletim}: sqlcipher3 kurulumu test adımından SONRA"
            assert not any(d.search(run) for d in _DUSUSLER), (
                f"{isletim}: sqlcipher3 kurulumu SESSİZCE yutuluyor (A-46): {run!r}"
            )
            assert adim.get("continue-on-error") is not True, f"{isletim}: kurulum adımı continue-on-error"
            assert re.search(r"from sqlcipher3 import dbapi2|import sqlcipher3", run), (
                f"{isletim}: kurulum bağlayıcıyı İÇE AKTARARAK doğrulamıyor — pip 'başarılı' deyip bağlayıcı "
                f"yüklenemezse kapılar yine atlanır: {run!r}"
            )


def test_KRITIK_test_adimi_JUNIT_uretir_ve_atlama_kapisi_ARDINDAN_kosar():
    """MUTASYON: atlama kapısı adımını silmek · junit argümanını kaldırmak · kapıya başka dosya vermek → KIRMIZI."""
    adimlar = _backend()["steps"]
    for isletim in _isletimler():
        testler = [
            (i, a) for i, a in enumerate(adimlar) if _kapsar(a, isletim) and "pytest tests" in str(a.get("run", ""))
        ]
        assert len(testler) == 1, f"{isletim}: tam olarak bir test adımı bekleniyordu, bulunan {len(testler)}"
        i_test, test = testler[0]
        m = re.search(r"--junitxml[= ](\S+)", str(test["run"]))
        assert m, f"{isletim}: test adımı junit ÜRETMİYOR -> atlama sayılamaz"
        junit = m.group(1)
        kapi = [
            (i, a)
            for i, a in enumerate(adimlar)
            if i > i_test
            and _kapsar(a, isletim)
            and re.search(
                r"scripts/ci_sqlcipher_atlama_kapisi\.py\s+" + re.escape(junit) + r"\b", str(a.get("run", ""))
            )
        ]
        assert kapi, f"{isletim}: test adımından SONRA '{junit}' ile sqlcipher atlama kapısı KOŞMUYOR"
        assert all(a.get("continue-on-error") is not True for _, a in kapi), (
            f"{isletim}: atlama kapısı continue-on-error"
        )


def _sqlcipher3_pini(yol: Path) -> str | None:
    m = re.search(r"^sqlcipher3==([0-9][0-9.]*)", yol.read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else None


def test_KRITIK_sqlcipher3_test_ortaminda_ve_CI_isinde_URETIM_SURUMUYLE_kurulur():
    """2-A inceleme (sahip isteği 2026-10-07): sqlcipher3 `requirements-test.txt`te YOKTU — yalnız o dosyayı kuran yerel
    ortamda şifreleme/göç/karantina/kurtarma kapıları sessizce atlanıyordu; CI'ın Linux kurulumu da sürümsüzdü
    (`sqlcipher3-binary || sqlcipher3`) → ürünün SQLCipher sürümünden farklı bir kitaplıkla koşabiliyordu.
    MUTASYON: test gereksiniminden pini silmek · Linux kurulumunu sürümsüz/başka paketle yapmak → KIRMIZI."""
    uretim = _sqlcipher3_pini(KOK / "requirements.txt")
    assert uretim, "requirements.txt'te sqlcipher3 SABİT sürümü yok -> kapı KÖR"
    assert _sqlcipher3_pini(KOK / "requirements-test.txt") == uretim, (
        f"requirements-test.txt sqlcipher3'ü üretim sürümüyle ({uretim}) KURMUYOR -> yerel koşu kapıları sessizce atlar"
    )
    adimlar = _backend()["steps"]
    for isletim in _isletimler():
        satirlar = [
            s
            for a in adimlar
            if _kapsar(a, isletim)
            for s in str(a.get("run", "")).splitlines()
            if re.search(r"pip install[^\n]*\bsqlcipher3", s)
        ]
        assert satirlar, f"{isletim}: sqlcipher3 kurulum satırı yok"
        for s in satirlar:
            paketler = re.findall(r"\bsqlcipher3(?:-binary)?(?:==[0-9][0-9.]*)?", re.sub(r"--only-binary\s+\S+", "", s))
            assert paketler and all(p == f"sqlcipher3=={uretim}" for p in paketler), (
                f"{isletim}: sqlcipher3 ÜRETİM SÜRÜMÜYLE ({uretim}) kurulmuyor: {s.strip()!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════════════════
# SAYAÇ BETİĞİNİN DAVRANIŞI (alt süreç YOK — modül içe aktarılır, `main` çağrılır)
# ═══════════════════════════════════════════════════════════════════════════════════════


def _betik():
    spec = importlib.util.spec_from_file_location("ci_sqlcipher_atlama_kapisi_d207", BETIK)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _junit(yol: Path, durumlar: list[tuple[str, str | None]]) -> Path:
    """durumlar: (test adı, atlama nedeni ya da None=geçti)."""
    parcalar = ['<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">']
    for ad, neden in durumlar:
        if neden is None:
            parcalar.append(f'<testcase classname="tests.t" name="{ad}" time="0.1"/>')
        else:
            parcalar.append(
                f'<testcase classname="tests.t" name="{ad}" time="0"><skipped type="pytest.skip" '
                f'message="{neden}">t.py:1: {neden}</skipped></testcase>'
            )
    parcalar.append("</testsuite></testsuites>")
    yol.write_text("".join(parcalar), encoding="utf-8")
    return yol


def test_KRITIK_sqlcipher_nedenli_ATLAMA_varsa_kapi_KIRMIZI(tmp_path, capsys):
    """MUTASYON: harf duyarlı arama (`neden.lower()` kaldırılır) · her zaman 0 dönmek → KIRMIZI."""
    b = _betik()
    kucuk = _junit(tmp_path / "a.xml", [("t1", None), ("t2", "sqlcipher3 yok — gercek baglayici kolu")])
    buyuk = _junit(tmp_path / "b.xml", [("t1", None), ("t2", "SQLCipher binding YOK")])
    assert b.main([str(kucuk)]) == 1, "sqlcipher3 nedenli atlama SAYILMADI -> CI yine YEŞİL biter"
    assert b.main([str(buyuk)]) == 1, "büyük harfli 'SQLCipher' nedeni SAYILMADI (harf duyarsız olmalı)"
    assert "KIRMIZI" in capsys.readouterr().out


def test_KARSIT_ilgisiz_atlamalar_kapiyi_DUSURMEZ(tmp_path):
    """Kapı "her atlama kırmızı"ya kaymasın: model ağırlığı / test girdisi atlamaları CI'da beklenir."""
    b = _betik()
    xml = _junit(tmp_path / "c.xml", [("t1", None), ("t2", "petri test girdisi yok"), ("t3", "torch yok (CI)")])
    assert b.main([str(xml)]) == 0


def test_KRITIK_junit_YOK_ya_da_BOS_ise_kapi_KOR_sayilir(tmp_path):
    """Test adımı koşmadıysa (junit yok/boş/bozuk) kapı 'tamam' DEMEZ (çıkış 2). MUTASYON: boş kontrolü silmek → KIRMIZI."""
    b = _betik()
    assert b.main([str(tmp_path / "olmayan.xml")]) == 2
    assert b.main([str(_junit(tmp_path / "bos.xml", []))]) == 2
    (tmp_path / "bozuk.xml").write_text("<testsuites><testsuite", encoding="utf-8")
    assert b.main([str(tmp_path / "bozuk.xml")]) == 2
