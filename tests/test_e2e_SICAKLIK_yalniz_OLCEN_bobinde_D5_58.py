# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5.58 (B-10.175) KAPISI — e2e araçları sıcaklığı YALNIZ ölçebilen bobinde bekler (ölçülebilirlik tek kaynağı: topoloji).

ARIZA (DENETİM-10 B-10.175): `tools/e2e_full.py` "sicaklik telemetrisi akiyor" kontrolünü STM bobini 1'de (`objectTemp > 0`),
`tools/e2e_smoke.py` herhangi bir çalışan bobinde yapıyordu. STM protokolünde sıcaklık alanı YOK; sim de (2026-09-20'den beri)
STM bobinine sıcaklık UYDURMAZ → kontroller ya hep KALIR ya da biri sim'e STM sıcaklığını geri verirse GEÇER (değişmezi bozmanın
ödülü). Sıra (madde notu): önce B-10.177 (sim kapısı `sensor_data` yayınını da ölçer), sonra bu.

Araçlar backend başlattığı için testte KOŞTURULMAZ — kapı AST'dedir (`test_e2e_full_esp_hedefi_TOPOLOJIDEN` deseni). ETİKETE
BAKILMAZ ve yalnız `check(...)` koşuluna da BAKILMAZ: araç modülündeki HER `objectTemp` okuması taranır (yerel değişkene, yardımcı
işleve, lambdaya ya da "manyetik" etiketli bir kontrole saklansa da). Yalnız görüntü bağlamı atlanır: `check`'in `detail` argümanı
(3. konum / `detail=`) ve `print` / `_konsola_guvenli` argümanları.
  · NÖTR okuma: `<okuma> is None` / `== None` (tek işleç) ya da iki anlık görüntünün karşılaştırması (`<okuma> != <okuma>`) —
    o karşılaştırma `or` ile sıcaklık OKUMAYAN, sabit olmayan bir alternatife bağlıysa (K2 döngü canlılığı: "sıcaklık YA DA manyetik
    alan değişti" sıcaklığın VARLIĞINI gerektirmez). Bunların DIŞINDAKİ her kullanım POZİTİF sıcaklık beklentisidir (`>`, `>=`, `<`,
    `<=`, `!=`, `== <sayı>`, `is not`, `in`, doğruluk değeri `bool(...)`, `float(... or 0)` …; fail-closed).
  · POZİTİF beklenti yalnız ÖLÇEN bobinde: alıcı `coil_of(<anlık>, <ESP kimliği>)` (kimlik `esp_slotlari(...)[<sabit>]` ya da
    `_esp_bobinleri()` / `esp_slotlari(...)` kümesinden DOĞRUDAN gelir) ya da yalnız böyle bağlanan bir ad (`<bu> if … else None`
    dahil), ya da üreteçte `if <…> in <ESP kümesi>` süzgecinden geçen değişken. Adın sağ tarafında ESP çağrısının GEÇMESİ yetmez
    (`coil_of(sn, 1) if esp_slotlari(sn) else None` → ölçen DEĞİL); parametre / lambda argümanı ölçen DEĞİL.
  · Her araçta en az bir kontrol STM (ölçen OLMAYAN) bobinde VAKUMSUZ `objectTemp is None` bekler: kontrol işlev gövdesinde
    KOŞULSUZ (`if` / `for` / `while` / `try` altında değil), alıcı döngü / parametre hedefi değil, beklenti koşulun `and` zincirinde
    DOĞRUDAN (`or` altında / değişken üzerinden / `any(...)` ile sayılmaz); `all(<…> is None for c in L)` ise aynı zincirde
    `bool(L)` / `L` / `len(L) > 0` / `len(L) >= 1` / `len(L) != 0` koruması ŞART (boş kümede `all` koşulsuz GEÇER).
MUTASYON: e2e_full sıcaklık kontrolünü bobin 1'e (`c1.get("objectTemp") > 0`) geri almak → KIRMIZI; ölçen bobinin KİMLİĞİNİ
sabite çevirmek (`coil_of(sn, 1) if esp_slotlari(sn) …`) → KIRMIZI; beklentiyi "manyetik" etiketli kontrole saklamak → KIRMIZI;
D5.58 TUR 2 (çürütme c1 / c2 / c3): `!= 0` işleci → KIRMIZI; beklentiyi yerel değişkene taşımak → KIRMIZI; e2e_smoke'ta
`bool(_stm_calisan)` korumasını silmek → KIRMIZI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
ARACLAR = ["tools/e2e_full.py", "tools/e2e_smoke.py"]
_ESP_KUME_CAGRILARI = frozenset({"esp_slotlari", "_esp_bobinleri"})
_GORUNTU_CAGRILARI = frozenset({"print", "_konsola_guvenli"})
_SICAKLIK_ALANI = "objectTemp"


def _cagri_adi(d) -> str:
    return d.func.id if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) else ""


def _baglamalar(fonk: ast.AST) -> dict[str, list]:
    """Fonksiyondaki her ad bağlaması → değer ifadesi; izlenemeyen bağlama (parametre, for/with/üreteç hedefi, demet
    açılımı, artırımlı atama) None — o ad topolojiden türemiş SAYILMAZ (fail-closed)."""
    b: dict[str, list] = {}

    def _izlenemez(hedef) -> None:
        for e in ast.walk(hedef):
            if isinstance(e, ast.Name):
                b.setdefault(e.id, []).append(None)

    if isinstance(fonk, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for a in fonk.args.posonlyargs + fonk.args.args + fonk.args.kwonlyargs:
            b.setdefault(a.arg, []).append(None)
    for d in ast.walk(fonk):
        if isinstance(d, ast.Assign):
            for h in d.targets:
                if isinstance(h, ast.Name):
                    b.setdefault(h.id, []).append(d.value)
                else:
                    _izlenemez(h)
        elif isinstance(d, ast.AnnAssign) and isinstance(d.target, ast.Name) and d.value is not None:
            b.setdefault(d.target.id, []).append(d.value)
        elif isinstance(d, ast.NamedExpr):
            b.setdefault(d.target.id, []).append(d.value)
        elif isinstance(d, (ast.AugAssign, ast.For, ast.AsyncFor, ast.comprehension)):
            _izlenemez(d.target)
        elif isinstance(d, ast.withitem) and d.optional_vars is not None:
            _izlenemez(d.optional_vars)
        elif isinstance(d, ast.Lambda):
            for a in d.args.posonlyargs + d.args.args + d.args.kwonlyargs:
                b.setdefault(a.arg, []).append(None)
    return b


class _Topoloji:
    """Bir fonksiyon kapsamında ESP (ölçen) türevi ifadeler — en küçük sabit nokta; bir ad ancak TÜM bağlamaları
    türevliyse sayılır."""

    def __init__(self, fonk: ast.AST):
        self.bag = _baglamalar(fonk)
        self.kume: set[str] = set()
        self.kimlik: set[str] = set()
        self.bobin: set[str] = set()
        self.liste: set[str] = set()
        degisti = True
        while degisti:
            degisti = False
            for ad, degerler in self.bag.items():
                for kume, sinama in (
                    (self.kume, self.kume_mi),
                    (self.kimlik, self.kimlik_mi),
                    (self.bobin, self.bobin_mi),
                    (self.liste, self.bobin_listesi_mi),
                ):
                    if ad not in kume and all(v is not None and sinama(v) for v in degerler):
                        kume.add(ad)
                        degisti = True

    def suzgec_hedefleri(self, g: ast.comprehension) -> set[str]:
        """Üreteç hedefinden `if <…hedef…> in <ESP kümesi>` ile süzülen adlar (`not in` SAYILMAZ)."""
        hedefler = {e.id for e in ast.walk(g.target) if isinstance(e, ast.Name)}
        out: set[str] = set()
        for kosul in g.ifs:
            if (
                isinstance(kosul, ast.Compare)
                and len(kosul.ops) == 1
                and isinstance(kosul.ops[0], ast.In)
                and self.kume_mi(kosul.comparators[0])
            ):
                out |= {e.id for e in ast.walk(kosul.left) if isinstance(e, ast.Name)} & hedefler
        return out

    def uretec_olcenleri(self, g: ast.comprehension) -> set[str]:
        """Üreteç gövdesinde ölçen sayılan hedef adları: süzgeçten geçen ya da yalnız ölçen bobinlerden oluşan listeyi dolaşan."""
        out = self.suzgec_hedefleri(g)
        if isinstance(g.target, ast.Name) and self.bobin_listesi_mi(g.iter):
            out.add(g.target.id)
        return out

    def bobin_listesi_mi(self, d) -> bool:
        """Yalnız ölçen bobinlerden oluşan liste: `[c for c in … if <c…> in <ESP kümesi>]` (öğe = süzülen hedef) ya da
        `[coil_of(<anlık>, i) for i in <ESP kümesi>]` ya da doğrudan atanmış ad."""
        if isinstance(d, (ast.ListComp, ast.GeneratorExp)) and len(d.generators) == 1:
            g = d.generators[0]
            if isinstance(d.elt, ast.Name) and d.elt.id in self.suzgec_hedefleri(g):
                return True
            return (
                _cagri_adi(d.elt) == "coil_of"
                and len(d.elt.args) == 2
                and isinstance(g.target, ast.Name)
                and isinstance(d.elt.args[1], ast.Name)
                and d.elt.args[1].id == g.target.id
                and self.kume_mi(g.iter)
            )
        return isinstance(d, ast.Name) and d.id in self.liste

    def kume_mi(self, d) -> bool:
        """ESP bobin kümesi / listesi: `esp_slotlari(...)`, `_esp_bobinleri()`, `sorted(<bunlar>)` ya da doğrudan atanmış ad."""
        if _cagri_adi(d) in _ESP_KUME_CAGRILARI:
            return True
        if _cagri_adi(d) in ("sorted", "list", "set") and len(d.args) == 1:
            return self.kume_mi(d.args[0])
        return isinstance(d, ast.Name) and d.id in self.kume

    def kimlik_mi(self, d) -> bool:
        """Tek ESP bobin kimliği: `<ESP kümesi>[<int sabit>]` ya da doğrudan atanmış ad."""
        if isinstance(d, ast.Subscript):
            return self.kume_mi(d.value) and isinstance(d.slice, ast.Constant) and type(d.slice.value) is int
        return isinstance(d, ast.Name) and d.id in self.kimlik

    def bobin_mi(self, d) -> bool:
        """Ölçen bobin sözlüğü: `coil_of(<anlık>, <ESP kimliği>)`, ondan doğrudan atanmış ad ya da `<bu> if … else None`."""
        if _cagri_adi(d) == "coil_of" and len(d.args) == 2:
            return self.kimlik_mi(d.args[1])
        if isinstance(d, ast.IfExp):
            dallar = (d.body, d.orelse)
            olcen = sum(self.bobin_mi(x) for x in dallar)
            bos = sum(isinstance(x, ast.Constant) and x.value is None for x in dallar)
            return olcen >= 1 and olcen + bos == 2
        return isinstance(d, ast.Name) and d.id in self.bobin


def _sicaklik_alicisi(d):
    """`<alıcı>.get("objectTemp")` ya da `<alıcı>["objectTemp"]` → alıcı düğümü; değilse None."""
    if (
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr == "get"
        and d.args
        and isinstance(d.args[0], ast.Constant)
        and d.args[0].value == _SICAKLIK_ALANI
    ):
        return d.func.value
    if isinstance(d, ast.Subscript) and isinstance(d.slice, ast.Constant) and d.slice.value == _SICAKLIK_ALANI:
        return d.value
    return None


def _olcen_mi(alici, topo: _Topoloji, kapsam: frozenset) -> bool:
    if isinstance(alici, ast.Name) and alici.id in kapsam:
        return True
    return topo.bobin_mi(alici)


def _none_okumasi(k):
    """`<okuma> is None` / `<okuma> == None` (tek işleç; iki yön) → okuma düğümü; değilse None."""
    if not (isinstance(k, ast.Compare) and len(k.ops) == 1 and isinstance(k.ops[0], (ast.Is, ast.Eq))):
        return None
    sol, sag = k.left, k.comparators[0]
    for okuma, oteki in ((sol, sag), (sag, sol)):
        if isinstance(oteki, ast.Constant) and oteki.value is None and _sicaklik_alicisi(okuma) is not None:
            return okuma
    return None


def _sicaklik_okur_mu(d) -> bool:
    return any(_sicaklik_alicisi(x) is not None for x in ast.walk(d))


def _degisim_karsilastirmasi_mi(k, ebeveyn: dict) -> bool:
    """İki anlık görüntünün karşılaştırması (`<okuma> != <okuma>` / `==`), `or` ile sıcaklık OKUMAYAN, sabit OLMAYAN bir
    alternatife bağlı — sıcaklığın VARLIĞINI gerektirmez (yalnız başına ya da `or False` ile POZİTİF sayılır)."""
    if not (isinstance(k, ast.Compare) and len(k.ops) == 1 and isinstance(k.ops[0], (ast.Eq, ast.NotEq))):
        return False
    if _sicaklik_alicisi(k.left) is None or _sicaklik_alicisi(k.comparators[0]) is None:
        return False
    ust = ebeveyn.get(k)
    return (
        isinstance(ust, ast.BoolOp)
        and isinstance(ust.op, ast.Or)
        and any(v is not k and not isinstance(v, ast.Constant) and not _sicaklik_okur_mu(v) for v in ust.values)
    )


def _sicaklik_okumalari(agac: ast.Module):
    """Modüldeki HER `objectTemp` okuması → (okuma, alıcı, topoloji, kapsam, nötr mü). Görüntü bağlamı (check `detail`,
    print) atlanır; işlev sınırında topoloji değişir; lambda argümanı dış adı GÖLGELER; üreteçte süzülen hedef ölçen sayılır,
    aynı adı süzgeçsiz yeniden bağlayan iç üreteç onu KALDIRIR."""
    ebeveyn = {alt: d for d in ast.walk(agac) for alt in ast.iter_child_nodes(d)}
    notr: set = set()
    for k in ast.walk(agac):
        if (okuma := _none_okumasi(k)) is not None:
            notr.add(okuma)
        elif _degisim_karsilastirmasi_mi(k, ebeveyn):
            notr.update((k.left, k.comparators[0]))
    topolar: dict[int, _Topoloji] = {}
    out: list = []

    def _gez(d, topo: _Topoloji, kapsam: frozenset) -> None:
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ic = topolar.setdefault(id(d), _Topoloji(d))
            for x in d.body:
                _gez(x, ic, frozenset())
            return
        if isinstance(d, ast.Lambda):
            a = d.args
            golge = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            _gez(d.body, topo, frozenset(kapsam - golge))
            return
        if isinstance(d, ast.Call) and _cagri_adi(d) in _GORUNTU_CAGRILARI:
            return
        if isinstance(d, ast.Call) and _cagri_adi(d) == "check":
            for x in d.args[:2]:
                _gez(x, topo, kapsam)
            for kw in d.keywords:
                if kw.arg != "detail":
                    _gez(kw.value, topo, kapsam)
            return
        if isinstance(d, (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)):
            ic = set(kapsam)
            for g in d.generators:
                _gez(g.iter, topo, frozenset(ic))
                ic -= {e.id for e in ast.walk(g.target) if isinstance(e, ast.Name)}
                for kosul in g.ifs:
                    _gez(kosul, topo, frozenset(ic))
                ic |= topo.uretec_olcenleri(g)
            for x in [d.key, d.value] if isinstance(d, ast.DictComp) else [d.elt]:
                _gez(x, topo, frozenset(ic))
            return
        alici = _sicaklik_alicisi(d)
        if alici is not None:
            out.append((d, alici, topo, kapsam, d in notr))
        for alt in ast.iter_child_nodes(d):
            _gez(alt, topo, kapsam)

    _gez(agac, _Topoloji(agac), frozenset())
    return out, ebeveyn


def _ve_terimleri(d) -> list:
    if isinstance(d, ast.BoolOp) and isinstance(d.op, ast.And):
        return [t for v in d.values for t in _ve_terimleri(v)]
    return [d]


def _bos_degil_korumasi_mi(u, kume) -> bool:
    """`L` / `bool(L)` / `len(L)` / `len(L) > 0` / `len(L) >= 1` / `len(L) != 0` (L = `all`'un dolaştığı ifade)."""
    hedef = ast.dump(kume)

    def _ayni(x) -> bool:
        return ast.dump(x) == hedef

    if _ayni(u):
        return True
    if _cagri_adi(u) in ("bool", "len") and len(u.args) == 1 and _ayni(u.args[0]):
        return True
    if (
        isinstance(u, ast.Compare)
        and len(u.ops) == 1
        and _cagri_adi(u.left) == "len"
        and len(u.left.args) == 1
        and _ayni(u.left.args[0])
        and isinstance(u.comparators[0], ast.Constant)
        and type(u.comparators[0].value) is int
    ):
        op, n = u.ops[0], u.comparators[0].value
        return (
            (isinstance(op, ast.Gt) and n >= 0)
            or (isinstance(op, ast.GtE) and n >= 1)
            or (isinstance(op, ast.NotEq) and n == 0)
        )
    return False


def _vakumsuz_none_beklentileri(agac: ast.Module, ebeveyn: dict) -> list[str]:
    """STM (ölçen OLMAYAN) bobinde `objectTemp is None` bekleyen VAKUMSUZ kontroller (bkz. modül belgesi)."""

    def _kapsayan_fonksiyon(d):
        while d in ebeveyn:
            d = ebeveyn[d]
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return d
        return agac

    def _kosulsuz_kosar_mi(c) -> bool:
        """`check(...)` işlevin (ya da modülün) DOĞRUDAN gövdesinde bir deyim — `if` / `for` / `while` / `try` altında değil
        (koşul tutmazsa ya da liste boşsa kontrol HİÇ koşmaz, araç yine yeşil biter)."""
        st = ebeveyn.get(c)
        ust = ebeveyn.get(st)
        return (
            isinstance(st, ast.Expr)
            and isinstance(ust, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))
            and any(st is x for x in ust.body)
        )

    def _izlenen_alici_mi(alici, topo: _Topoloji) -> bool:
        """Ad alıcının TÜM bağlamaları atama (döngü / üreteç / parametre hedefi değil)."""
        if isinstance(alici, ast.Name):
            degerler = topo.bag.get(alici.id)
            return bool(degerler) and all(v is not None for v in degerler)
        return True

    topolar: dict[int, _Topoloji] = {}
    out: list[str] = []
    for c in ast.walk(agac):
        if not (isinstance(c, ast.Call) and _cagri_adi(c) == "check" and len(c.args) >= 2):
            continue
        if not _kosulsuz_kosar_mi(c):
            continue
        fonk = _kapsayan_fonksiyon(c)
        topo = topolar.setdefault(id(fonk), _Topoloji(fonk))
        terimler = _ve_terimleri(c.args[1])
        for t in terimler:
            okuma = _none_okumasi(t)
            if okuma is not None:
                alici = _sicaklik_alicisi(okuma)
                if _izlenen_alici_mi(alici, topo) and not _olcen_mi(alici, topo, frozenset()):
                    out.append(f"satır {t.lineno}: {ast.unparse(t)}")
                continue
            if not (
                _cagri_adi(t) == "all"
                and len(t.args) == 1
                and isinstance(t.args[0], (ast.GeneratorExp, ast.ListComp))
                and len(t.args[0].generators) == 1
                and not t.args[0].generators[0].ifs
            ):
                continue
            uretec = t.args[0]
            g = uretec.generators[0]
            okuma = _none_okumasi(uretec.elt)
            if okuma is None or _olcen_mi(_sicaklik_alicisi(okuma), topo, frozenset(topo.uretec_olcenleri(g))):
                continue
            if any(u is not t and _bos_degil_korumasi_mi(u, g.iter) for u in terimler):
                out.append(f"satır {t.lineno}: {ast.unparse(c.args[1])}")
    return out


def _cozumle(kaynak: str) -> tuple[list[str], list[str]]:
    """(pozitif sıcaklık beklentisi ölçen OLMAYAN bobinde olan okumalar, STM'de VAKUMSUZ `objectTemp is None` bekleyen kontroller)."""
    agac = ast.parse(kaynak)
    okumalar, ebeveyn = _sicaklik_okumalari(agac)
    ihlal: list[str] = []
    for okuma, alici, topo, kapsam, notr in okumalar:
        if notr or _olcen_mi(alici, topo, kapsam):
            continue
        ifade, d = okuma, okuma
        while d in ebeveyn and isinstance(ebeveyn[d], ast.expr):
            d = ebeveyn[d]
            if isinstance(d, ast.Compare):
                ifade = d
                break
        else:
            ifade = ebeveyn.get(okuma, okuma) if isinstance(ebeveyn.get(okuma), ast.expr) else okuma
        ihlal.append(f"satır {okuma.lineno}: {ast.unparse(ifade)}")
    return ihlal, _vakumsuz_none_beklentileri(agac, ebeveyn)


@pytest.mark.parametrize("yol", ARACLAR)
def test_KRITIK_D558_e2e_sicaklik_YALNIZ_olcen_bobinde_beklenir(yol):
    kaynak = (KOK / yol).read_text(encoding="utf-8")
    assert "objectTemp" in kaynak and "check(" in kaynak, f"{yol}: sıcaklık / check çıpası yok — kapı vakumda"
    ihlal, none_bekleyen = _cozumle(kaynak)
    assert not ihlal, (
        f"{yol}: sıcaklık ÖLÇEMEYEN bobinde bekleniyor (STM protokolünde sıcaklık alanı YOK; ölçen bobin topolojiden — "
        f"`esp_slotlari` / `_esp_bobinleri` — türemeli): {ihlal}"
    )
    assert none_bekleyen, (
        f"{yol}: hiçbir kontrol STM bobininde VAKUMSUZ `objectTemp is None` beklemiyor (uydurma sıcaklık yakalanmaz; "
        "`all(...)` boş kümede de GEÇER — aynı `and` zincirinde `bool(<liste>)` koruması gerekir)"
    )


# ── Karşıt kanıt: tarayıcının kendisi (sentetik kaynak) ──────────────────────────────────────────────────────────


def _sentetik(govde: str) -> str:
    return "def f(sn, running):\n" + "".join(f"    {s}\n" for s in govde.strip().splitlines())


_STM_LISTESI = 'st = [c for c in running if int(c["id"]) not in _esp_bobinleri()]\n'


@pytest.mark.parametrize(
    "govde, ihlal_beklenir",
    [
        # ölçen bobin topolojiden — yeşil
        (
            'o = coil_of(sn, esp_slotlari(sn)[0]) if esp_slotlari(sn) else None\ncheck("x", o is None or float(o.get("objectTemp") or 0) > 0)',
            False,
        ),
        (
            'e = _esp_bobinleri()\ncheck("x", any(float(c.get("objectTemp") or 0) > 0 for c in running if int(c.get("id")) in e))',
            False,
        ),
        # kimlik SABİT ama sağ tarafta ESP çağrısı geçiyor — ölçen DEĞİL
        ('o = coil_of(sn, 1) if esp_slotlari(sn) else None\ncheck("x", float(o.get("objectTemp") or 0) > 0)', True),
        # bobin 1 / herhangi bir çalışan / `not in` süzgeci / etiket "sicaklik" içermiyor
        ('c1 = coil_of(sn, 1)\ncheck("manyetik", float(c1.get("objectTemp") or 0) > 0)', True),
        ('check("x", any(float(c.get("objectTemp") or 0) > 0 for c in running))', True),
        (
            'e = _esp_bobinleri()\ncheck("x", any(float(c.get("objectTemp") or 0) > 0 for c in running if c["id"] not in e))',
            True,
        ),
        ('check("x", coil_of(sn, 2)["objectTemp"] is not None)', True),
        # ad bir kez ESP'den, bir kez sabitten bağlanıyor — ölçen DEĞİL
        (
            'o = coil_of(sn, esp_slotlari(sn)[0])\no = coil_of(sn, 3)\ncheck("x", float(o.get("objectTemp") or 0) > 0)',
            True,
        ),
        # yalnız ölçen bobinlerden oluşan liste — yeşil; `not in` ile kurulan (STM) liste — ihlal
        (
            'ol = [c for c in running if int(c["id"]) in _esp_bobinleri()]\ncheck("x", all(float(c.get("objectTemp") or 0) > 0 for c in ol))',
            False,
        ),
        (
            _STM_LISTESI + 'check("x", any(float(c.get("objectTemp") or 0) > 0 for c in st))',
            True,
        ),
        # TUR 2 (çürütme c1): POZİTİF işleç listesi DIŞINDAKİ kullanımlar da beklentidir
        ('c1 = coil_of(sn, 1)\ncheck("x", float(c1.get("objectTemp") or 0) != 0)', True),
        ('c1 = coil_of(sn, 1)\ncheck("x", c1.get("objectTemp") == 24.0)', True),
        ('c1 = coil_of(sn, 1)\ncheck("x", bool(c1.get("objectTemp")))', True),
        ('c1 = coil_of(sn, 1)\ncheck("x", c1.get("objectTemp") in (24.0, 25.0))', True),
        # TUR 2 (çürütme c2): yerel değişken / anahtar sözcüklü koşul / lambda üzerinden DOLAYLI beklenti
        ('c1 = coil_of(sn, 1)\nv = float(c1.get("objectTemp") or 0) > 0\ncheck("x", v)', True),
        ('c1 = coil_of(sn, 1)\ncheck("x", cond=float(c1.get("objectTemp") or 0) > 0)', True),
        ('check("x", (lambda c: float(c.get("objectTemp") or 0) > 0)(coil_of(sn, 1)))', True),
        # görüntü bağlamı (detail / print) beklenti DEĞİL
        ('c1 = coil_of(sn, 1)\ncheck("x", True, f"{c1.get(\'objectTemp\')} C")', False),
        ('c1 = coil_of(sn, 1)\ncheck("x", True, detail=str(c1.get("objectTemp")))', False),
        ('c1 = coil_of(sn, 1)\nprint(c1.get("objectTemp"))', False),
        # iki anlık görüntü: sıcaklık OKUMAYAN alternatifle `or` → nötr; yalnız başına / sabit alternatifle → beklenti
        (
            'a = sn\ncheck("x", sum(1 for c, d in zip(a, running) if c.get("objectTemp") != d.get("objectTemp") or c.get("magneticMt") != d.get("magneticMt")) > 0)',
            False,
        ),
        (
            'c1 = coil_of(sn, 1)\nc2 = coil_of(running, 1)\ncheck("x", c1.get("objectTemp") != c2.get("objectTemp"))',
            True,
        ),
        (
            'c1 = coil_of(sn, 1)\nc2 = coil_of(running, 1)\ncheck("x", c1.get("objectTemp") != c2.get("objectTemp") or False)',
            True,
        ),
    ],
)
def test_KARSIT_KANIT_tarayici_olcen_bobini_TOPOLOJIDEN_ayirir(govde, ihlal_beklenir):
    ihlal, _ = _cozumle(_sentetik(govde))
    assert bool(ihlal) is ihlal_beklenir, f"tarayıcı yanlış sınıfladı: {govde!r} → {ihlal}"


def test_KARSIT_KANIT_yardimci_islev_PARAMETRESI_olcen_sayilmaz():
    """TUR 2 (çürütme c2): beklenti modül düzeyinde bir yardımcı işleve taşınırsa (alıcı parametre) — ihlal."""
    kaynak = (
        "def _sicak(c):\n"
        '    return float(c.get("objectTemp") or 0) > 0\n'
        "def f(sn):\n"
        '    check("x", _sicak(coil_of(sn, 1)))\n'
    )
    ihlal, _ = _cozumle(kaynak)
    assert ihlal, "yardımcı işleve taşınan sıcaklık beklentisi YAKALANMADI"


@pytest.mark.parametrize(
    "govde, sayilir",
    [
        ('c1 = coil_of(sn, 1)\ncheck("x", c1.get("objectTemp") is None)', True),
        ('c1 = coil_of(sn, 1)\ncheck("x", True and c1.get("objectTemp") is None)', True),
        # TUR 2 (çürütme c3): `all` boş kümede koşulsuz GEÇER — koruma ŞART
        (_STM_LISTESI + 'check("x", all(c.get("objectTemp") is None for c in st))', False),
        (_STM_LISTESI + 'check("x", bool(st) and all(c.get("objectTemp") is None for c in st))', True),
        (_STM_LISTESI + 'check("x", len(st) > 0 and all(c.get("objectTemp") is None for c in st))', True),
        (_STM_LISTESI + 'check("x", all(c.get("objectTemp") is None for c in st) and len(st) >= 1)', True),
        (_STM_LISTESI + 'check("x", len(st) >= 0 and all(c.get("objectTemp") is None for c in st))', False),
        (_STM_LISTESI + 'check("x", bool(running) and all(c.get("objectTemp") is None for c in st))', False),
        (_STM_LISTESI + 'check("x", bool(st) or all(c.get("objectTemp") is None for c in st))', False),
        (_STM_LISTESI + 'check("x", bool(st) and any(c.get("objectTemp") is None for c in st))', False),
        # `or` altında / değişken üzerinden — sayılmaz
        ('c1 = coil_of(sn, 1)\ncheck("x", c1.get("objectTemp") is None or True)', False),
        ('c1 = coil_of(sn, 1)\nv = c1.get("objectTemp") is None\ncheck("x", v)', False),
        # döngü / koşul altında (liste boşsa ya da koşul tutmazsa kontrol HİÇ koşmaz) — sayılmaz
        (_STM_LISTESI + 'for c in st:\n    check("x", c.get("objectTemp") is None)', False),
        ('c1 = coil_of(sn, 1)\nif esp_slotlari(sn):\n    check("x", c1.get("objectTemp") is None)', False),
        ('check("x", coil_of(sn, 1).get("objectTemp") is None)', True),
        # ÖLÇEN bobinde `is None` STM beklentisi DEĞİL
        ('o = coil_of(sn, esp_slotlari(sn)[0])\ncheck("x", o.get("objectTemp") is None)', False),
        (
            'ol = [c for c in running if int(c["id"]) in _esp_bobinleri()]\ncheck("x", bool(ol) and all(c.get("objectTemp") is None for c in ol))',
            False,
        ),
    ],
)
def test_KARSIT_KANIT_none_beklentisi_STM_de_ve_VAKUMSUZ_sayilir(govde, sayilir):
    _, none_bekleyen = _cozumle(_sentetik(govde))
    assert bool(none_bekleyen) is sayilir, f"`is None` beklentisi yanlış sayıldı: {govde!r} → {none_bekleyen}"
