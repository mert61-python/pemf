# Author: mertaygn, cglrgrkn
"""D1.09 · B-10.266 — `tools/e2e_full.py`'nin "ESP" diye etiketli kontrolleri GERÇEKTEN ESP yolunu sınar.

Faz 4'te (2026-09-10) bobin 6-7 ESP8266'dan STM'e taşındı; ESP olarak yalnız slot 8 kaldı
(`live_state.ESP_COIL_IDS`). `e2e_full` iki bölümde "tekil ESP bobin (7)" ve "D-3: ESP bobine
freq=5000" diye hâlâ **bobin 7'yi** (STM) sınıyordu; yani ESP/MQTT yolunun çalıştığını kanıtladığını
söyleyen kontroller STM'i ölçüyordu. Ayrıca "ESP komutu MQTT'ye yayinlandi" kontrolü
`... or bool(b7.get("status"))` biçimindeydi — her yanıtta doğru (totoloji).

Araç bir backend başlattığı için testte KOŞTURULMAZ; kapı iki kattır:
  1. AST taraması: ESP etiketli her `check(...)`'in hedef aldığı bobin (önündeki son
     `req(..., "/api/coil/<n>/control")`) ya topolojiden DOĞRUDAN gelir (`esp_l[<sabit>]`,
     `esp_slotlari(...)[<sabit>]`, bunlardan doğrudan atanmış ad, `<bunlar> if … else None`) ya da
     `ESP_COIL_IDS` içindeki bir literaldir; ESP kontrolünde her yanıtta doğru koşul yoktur
     (`or …get("status")` totolojisi; ESP dalında SABİT olan `transport`/"mqtt" alt dizesine tek
     başına bakan koşul). "alt sistem" diyen kontrol CANLI durumu okur.
  2. Davranış: aracın `esp_slotlari`'ı GERÇEK `/api/dashboard-snapshot` yanıtından tam olarak
     `ESP_COIL_IDS`'i üretir (topoloji değişirse araç kendiliğinden izler); `esp_alt_sistemi_acik`
     canlı `mqtt` alanıyla değişir, topolojiyle değil.

⚠️ Bağımsız inceleme (r2): eski tarayıcıda "türevli ad", sağ tarafta türevli bir ADIN GEÇMESİ
demekti — `esp = 7 if esp_l else None` (B-10.266'nın ta kendisi) ESP sayılıyordu; tekil kontrol
`"mqtt" in json.dumps(be).lower()` ile de yeşildi. Yayın kontrolü yalnız `transport`'u okuyordu
(ESP dalında sabit) ve "ESP alt sistemi açık" kontrolü sabit topolojiyi okuyordu.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KAYNAK = KOK / "tools" / "e2e_full.py"
_YOL = re.compile(r"^/api/coil/(\d+)/control$")


def _etiket(dugum) -> str:
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return dugum.value
    if isinstance(dugum, ast.JoinedStr):
        return "".join(v.value for v in dugum.values if isinstance(v, ast.Constant))
    return ""


def _esp_listesi_mi(d, liste: set[str]) -> bool:
    """`esp_slotlari(...)` çağrısı ya da ondan DOĞRUDAN atanmış liste adı."""
    if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "esp_slotlari":
        return True
    return isinstance(d, ast.Name) and d.id in liste


def _esp_ifadesi_mi(d, liste: set[str], tekil: set[str]) -> bool:
    """Bobin numarası topolojiden DOĞRUDAN mı geliyor: `esp_l[<sabit>]`, `esp_slotlari(...)[<sabit>]`,
    ondan doğrudan atanmış ad ya da `<bunlar> if … else None`. Aritmetik, başka çağrı ya da bir dalında
    literal bobin taşıyan koşullu ifade → HAYIR (fail-closed)."""
    if isinstance(d, ast.Subscript):
        return _esp_listesi_mi(d.value, liste) and isinstance(d.slice, ast.Constant) and type(d.slice.value) is int
    if isinstance(d, ast.Name):
        return d.id in tekil
    if isinstance(d, ast.IfExp):
        dallar = (d.body, d.orelse)
        esp_dal = sum(_esp_ifadesi_mi(x, liste, tekil) for x in dallar)
        bos_dal = sum(isinstance(x, ast.Constant) and x.value is None for x in dallar)
        return esp_dal >= 1 and esp_dal + bos_dal == 2
    return False


def _baglamalar(fonk: ast.FunctionDef) -> dict[str, list]:
    """Fonksiyondaki HER ad bağlaması → değer ifadesi. None = değeri izlenemeyen bağlama (parametre,
    for/with hedefi, demet açılımı, artırımlı atama) — o ad topolojiden türemiş SAYILMAZ."""
    b: dict[str, list] = {}

    def _izlenemez(hedef) -> None:
        for e in ast.walk(hedef):
            if isinstance(e, ast.Name):
                b.setdefault(e.id, []).append(None)

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
    return b


def _esp_adlari(fonk: ast.FunctionDef) -> tuple[set[str], set[str]]:
    """(liste adları, tekil bobin adları) — bir ad ancak TÜM bağlamaları topolojiden doğrudan
    geliyorsa sayılır (`esp = esp_l[0]` sonra `esp = 7` → SAYILMAZ). En küçük sabit nokta: kümeler
    yalnız büyür, koşullar kümelerde monoton."""
    bag = _baglamalar(fonk)
    liste: set[str] = set()
    tekil: set[str] = set()
    degisti = True
    while degisti:
        degisti = False
        for ad, degerler in bag.items():
            if ad not in liste and all(v is not None and _esp_listesi_mi(v, liste) for v in degerler):
                liste.add(ad)
                degisti = True
            if ad not in tekil and all(v is not None and _esp_ifadesi_mi(v, liste, tekil) for v in degerler):
                tekil.add(ad)
                degisti = True
    return liste, tekil


def _hedef(yol, liste: set[str], tekil: set[str]):
    """'/api/coil/<n>/control' hedefi: int (literal) · 'ESP' (topolojiden türeyen ad) ·
    None (bobin yolu değil) · '?' (çözülemedi — fail-closed)."""
    if isinstance(yol, ast.Constant) and isinstance(yol.value, str):
        m = _YOL.match(yol.value)
        return int(m.group(1)) if m else None
    if isinstance(yol, ast.JoinedStr):
        kalip = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in yol.values)
        if "/api/coil/" not in kalip:
            return None
        if kalip != "/api/coil/{}/control":
            return "?"
        ifade = next(v.value for v in yol.values if isinstance(v, ast.FormattedValue))
        return "ESP" if _esp_ifadesi_mi(ifade, liste, tekil) else "?"
    return "?"


def _totoloji_mi(kosul) -> bool:
    """`… or bool(x.get("status"))` / `… or x.get("status")` — her yanıtta doğru olan kol."""
    if not (isinstance(kosul, ast.BoolOp) and isinstance(kosul.op, ast.Or)):
        return False
    for kol in kosul.values:
        ic = kol.args[0] if isinstance(kol, ast.Call) and getattr(kol.func, "id", "") == "bool" and kol.args else kol
        if (
            isinstance(ic, ast.Call)
            and isinstance(ic.func, ast.Attribute)
            and ic.func.attr == "get"
            and ic.args
            and isinstance(ic.args[0], ast.Constant)
            and ic.args[0].value == "status"
        ):
            return True
    return False


_YAYIN_SONUCLARI = frozenset({"success", "mqtt_unavailable"})


def _status_okuma_mi(d) -> bool:
    """`x.get("status")` ya da `x["status"]`."""
    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get" and d.args:
        return isinstance(d.args[0], ast.Constant) and d.args[0].value == "status"
    return isinstance(d, ast.Subscript) and isinstance(d.slice, ast.Constant) and d.slice.value == "status"


def _status_karsilastirmalari(d) -> list:
    """`status` okumasını bir değerle karşılaştıran (işleç, öteki taraf) çiftleri."""
    out = []
    for c in ast.walk(d):
        if not isinstance(c, ast.Compare) or len(c.ops) != 1:
            continue
        if _status_okuma_mi(c.left):
            out.append((c.ops[0], c.comparators[0]))
        elif _status_okuma_mi(c.comparators[0]):
            out.append((c.ops[0], c.left))
    return out


def _sabit_degerler(d) -> set:
    if isinstance(d, ast.Constant):
        return {d.value}
    if isinstance(d, (ast.Tuple, ast.List, ast.Set)):
        return {e.value for e in d.elts if isinstance(e, ast.Constant)}
    return set()


def _sabit_kol_mu(kol) -> bool:
    """ESP yanıtında HER ZAMAN doğru olan kol: `status`'u hiç karşılaştırmadan `transport`'a ya da
    "mqtt" alt dizesine bakar (ESP dalı yanıtında `"transport": "mqtt"` SABİT — broker ölüyken de),
    ya da `status in ("success", "mqtt_unavailable")` gibi iki olası sonucu birden kabul eder."""
    karsilastirmalar = _status_karsilastirmalari(kol)
    if not karsilastirmalar:
        return any(
            isinstance(c, ast.Constant)
            and isinstance(c.value, str)
            and (c.value == "transport" or "mqtt" in c.value.lower())
            for c in ast.walk(kol)
        )
    return any(isinstance(op, ast.In) and _YAYIN_SONUCLARI <= _sabit_degerler(o) for op, o in karsilastirmalar)


def _sabit_mi(kosul) -> bool:
    if isinstance(kosul, ast.BoolOp) and isinstance(kosul.op, ast.Or):
        if any(_sabit_kol_mu(k) for k in kosul.values):
            return True
        # `status == "success" or status == "mqtt_unavailable"` — kollar birlikte iki sonucu da kapsar
        esit: set = set()
        for k in kosul.values:
            for op, o in _status_karsilastirmalari(k):
                if isinstance(op, ast.Eq):
                    esit |= _sabit_degerler(o)
        return _YAYIN_SONUCLARI <= esit
    return _sabit_kol_mu(kosul)


def esp_kontrolleri(kaynak: str):
    """[(fonksiyon, satır, etiket, hedef, totoloji_mi)] — yalnız etiketi 'ESP' içeren ve bir bobin
    yoluna bağlı kontroller."""
    agac = ast.parse(kaynak)
    sonuc = []
    for fonk in [d for d in agac.body if isinstance(d, ast.FunctionDef)]:
        liste, tekil = _esp_adlari(fonk)
        cagrilar = sorted(
            (d for d in ast.walk(fonk) if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)),
            key=lambda c: (c.lineno, c.col_offset),
        )
        son_hedef = None
        for c in cagrilar:
            if c.func.id == "req" and len(c.args) >= 2:
                son_hedef = _hedef(c.args[1], liste, tekil)
            elif c.func.id in ("snap", "esp_slotlari"):
                son_hedef = None  # anlık görüntü okundu → sonraki kontrol bobin komutunu değil görüntüyü sınar
            elif c.func.id == "check" and c.args:
                etiket = _etiket(c.args[0])
                if "ESP" in etiket and son_hedef is not None:
                    tot = len(c.args) > 1 and (_totoloji_mi(c.args[1]) or _sabit_mi(c.args[1]))
                    sonuc.append((fonk.name, c.lineno, etiket, son_hedef, tot))
    return sonuc


def alt_sistem_kontrolleri(kaynak: str):
    """[(fonksiyon, satır, etiket, canlı_mı)] — etiketi 'alt sistem' diyen her kontrol; canlı_mı: koşul
    `esp_alt_sistemi_acik(...)` (canlı `mqtt` alanı) çağırıyor mu."""
    sonuc = []
    for fonk in [d for d in ast.parse(kaynak).body if isinstance(d, ast.FunctionDef)]:
        for c in ast.walk(fonk):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "check" and c.args):
                continue
            etiket = _etiket(c.args[0])
            if "alt sistem" not in etiket.lower():
                continue
            canli = len(c.args) > 1 and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "esp_alt_sistemi_acik"
                for n in ast.walk(c.args[1])
            )
            sonuc.append((fonk.name, c.lineno, etiket, canli))
    return sonuc


def _arac(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))  # araç kökü eklerse test sonunda geri gelir
    spec = importlib.util.spec_from_file_location("e2e_full_esp_kapisi", KAYNAK)
    arac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arac)
    return arac


def test_KRITIK_ESP_etiketli_kontroller_ESP_yolunu_hedefler():
    from servers.live_state import ESP_COIL_IDS

    kontroller = esp_kontrolleri(KAYNAK.read_text(encoding="utf-8"))
    assert len(kontroller) >= 4, f"tarayıcı vakumda: yalnız {len(kontroller)} ESP kontrolü bulundu"
    yanlis = [(f, s, e, h) for f, s, e, h, _t in kontroller if not (h == "ESP" or h in ESP_COIL_IDS)]
    assert not yanlis, (
        f"'ESP' etiketli kontroller ESP olmayan bobini sınıyor (ESP_COIL_IDS={sorted(ESP_COIL_IDS)}): {yanlis}"
    )


def test_KRITIK_ESP_kontrollerinde_TOTOLOJI_yok():
    kontroller = esp_kontrolleri(KAYNAK.read_text(encoding="utf-8"))
    tot = [(f, s, e) for f, s, e, _h, t in kontroller if t]
    assert not tot, (
        "ESP kontrolü her yanıtta doğru (`or …get('status')`, ya da status'u karşılaştırmadan yalnız "
        f"`transport`/'mqtt' — ESP dalında SABİT): {tot}"
    )


def test_KRITIK_alt_sistem_kontrolu_CANLI_durumu_okur():
    k = alt_sistem_kontrolleri(KAYNAK.read_text(encoding="utf-8"))
    assert k, "tarayıcı vakumda: 'alt sistem' diyen kontrol bulunamadı"
    sabit = [(f, s, e) for f, s, e, canli in k if not canli]
    assert not sabit, (
        "'alt sistem açık' diyen kontrol canlı durumu (`esp_alt_sistemi_acik`) okumuyor — `esp_slotlari` "
        f"(stm32Driven) SABİT topolojidir, ESP kapalıyken de doğru: {sabit}"
    )


def test_TARAYICI_oz_denetim():
    """Tarayıcı kör değil: literal STM bobini, çözülemeyen ad ve totoloji yakalanır; türevli ad kabul."""
    ornek = '''
def f():
    s, b, _ = req("POST", "/api/coil/7/control", {})
    check("tekil ESP bobin (7)", s == 200)
    check("ESP komutu MQTT'ye yayinlandi", "mqtt" in str(b) or bool(b.get("status")))
    x = 3
    s, b, _ = req("POST", f"/api/coil/{x}/control", {})
    check("ESP x", s == 200)
    s, b, _ = req("POST", "/api/coil/1/control", {})
    esp_l = esp_slotlari(snap())
    check("snapshot: ESP slotu var", bool(esp_l))
    esp = esp_l[0]
    s, b, _ = req("POST", f"/api/coil/{esp}/control", {})
    check(f"ESP ({esp})", s == 200)
    check("ESP yolu", b.get("transport") == "mqtt")
    check("ESP yolu alt dize", "mqtt" in json.dumps(b).lower())
    check("ESP iki sonuc", b.get("status") in ("success", "mqtt_unavailable"))
    check("ESP veya", b.get("transport") == "mqtt" or b.get("status") == "success")
    check("ESP iki esitlik", b.get("status") == "success" or b["status"] == "mqtt_unavailable")
    check("ESP durust", b.get("transport") == "mqtt" and b.get("status") == yayin)
    gizli = 7 if esp_l else None
    s, b, _ = req("POST", f"/api/coil/{gizli}/control", {})
    check("ESP gizli literal", s == 200)
    kayik = esp_l[0] + 0
    s, b, _ = req("POST", f"/api/coil/{kayik}/control", {})
    check("ESP aritmetik", s == 200)
    sonra = esp_l[0]
    sonra = 7
    s, b, _ = req("POST", f"/api/coil/{sonra}/control", {})
    check("ESP yeniden atanan", s == 200)
    kosullu = esp_l[0] if esp_l else None
    s, b, _ = req("POST", f"/api/coil/{kosullu}/control", {})
    check("ESP kosullu None", s == 200)
    for dongu in esp_l:
        s, b, _ = req("POST", f"/api/coil/{dongu}/control", {})
        check("ESP for hedefi", s == 200)
    s, b, _ = req("POST", "/api/hardware/emergency_stop")
    check("E-stop TUM ESP slotlari", s == 200)
'''
    k = esp_kontrolleri(ornek)
    assert [(e, h, t) for _f, _s, e, h, t in k] == [
        ("tekil ESP bobin (7)", 7, False),
        ("ESP komutu MQTT'ye yayinlandi", 7, True),
        ("ESP x", "?", False),
        ("ESP ()", "ESP", False),
        ("ESP yolu", "ESP", True),
        ("ESP yolu alt dize", "ESP", True),
        ("ESP iki sonuc", "ESP", True),
        ("ESP veya", "ESP", True),
        ("ESP iki esitlik", "ESP", True),
        ("ESP durust", "ESP", False),
        ("ESP gizli literal", "?", False),
        ("ESP aritmetik", "?", False),
        ("ESP yeniden atanan", "?", False),
        ("ESP kosullu None", "ESP", False),
        ("ESP for hedefi", "?", False),
    ], k  # anlık görüntü kontrolü (coil/1'den sonra) bobine bağlanmaz; E-stop yolu bobin yolu değil
    alt = alt_sistem_kontrolleri(
        "def g():\n"
        "    check('ESP alt sistemi acik', bool(esp_slotlari(snap())))\n"
        "    check('ESP alt sistemi acik (canli)', esp_alt_sistemi_acik(snap()))\n"
    )
    assert [(e, c) for _f, _s, e, c in alt] == [
        ("ESP alt sistemi acik", False),
        ("ESP alt sistemi acik (canli)", True),
    ], alt


def test_KRITIK_esp_slotlari_GERCEK_snapshottan_ESP_COIL_IDS_uretir(monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server
    from servers.live_state import ESP_COIL_IDS

    arac = _arac(monkeypatch)
    anlik = TestClient(api_server.app, client=("127.0.0.1", 51237)).get("/api/dashboard-snapshot").json()
    assert arac.esp_slotlari(anlik) == sorted(ESP_COIL_IDS), (
        f"aracın ESP slotu türetmesi ürün topolojisiyle ayrıştı: {arac.esp_slotlari(anlik)} != {sorted(ESP_COIL_IDS)}"
    )


def test_KRITIK_esp_alt_sistemi_acik_CANLI_durumla_degisir_topolojiyle_DEGIL(monkeypatch):
    """GERÇEK `/api/dashboard-snapshot`: canlı `mqtt` alanı 'devre_disi' ↔ 'online' iken aracın sinyali
    değişmeli; topoloji (`esp_slotlari`) iki durumda AYNI — yani ayırt eden canlı alandır."""
    from fastapi.testclient import TestClient
    from servers import api_server, live_state

    arac = _arac(monkeypatch)
    istemci = TestClient(api_server.app, client=("127.0.0.1", 51237))
    sonuc = {}
    for durum in ("devre_disi", "online"):
        monkeypatch.setitem(live_state._live_state, "mqtt", durum)
        anlik = istemci.get("/api/dashboard-snapshot").json()
        assert anlik.get("mqtt") == durum, f"aparat: snapshot canlı alanı yansıtmıyor ({anlik.get('mqtt')})"
        sonuc[durum] = (arac.esp_alt_sistemi_acik(anlik), arac.esp_slotlari(anlik))
    assert sonuc["devre_disi"][0] is False and sonuc["online"][0] is True, sonuc
    assert sonuc["devre_disi"][1] == sonuc["online"][1], sonuc


def test_KRITIK_broker_sondasi_URUNUN_sondasiyla_AYNI_hedef(monkeypatch):
    """Aracın yayın beklentisi ürünün `_mqtt_publish` hızlı sondasıyla aynı adrese bakar; erişilemezse
    beklenen sonuç `mqtt_unavailable` olur (ağa çıkılmaz — bağlantı sahte)."""
    import socket

    arac = _arac(monkeypatch)
    cagrilar = []

    class _Soket:
        def close(self):
            return None

    def _baglan(adres, timeout=None):
        cagrilar.append((adres, timeout))
        return _Soket()

    def _reddet(adres, timeout=None):
        cagrilar.append((adres, timeout))
        raise ConnectionRefusedError(adres)

    monkeypatch.setattr(socket, "create_connection", _baglan)
    assert arac.broker_erisilebilir() is True
    monkeypatch.setattr(socket, "create_connection", _reddet)
    assert arac.broker_erisilebilir() is False
    assert cagrilar == [(("127.0.0.1", 1883), 0.3)] * 2, cagrilar
