# Author: mertaygn, cglrgrkn
"""D1.09 · B-10.266 — `tools/e2e_full.py`'nin "ESP" diye etiketli kontrolleri GERÇEKTEN ESP yolunu sınar.

Faz 4'te (2026-09-10) bobin 6-7 ESP8266'dan STM'e taşındı; ESP olarak yalnız slot 8 kaldı
(`live_state.ESP_COIL_IDS`). `e2e_full` iki bölümde "tekil ESP bobin (7)" ve "D-3: ESP bobine
freq=5000" diye hâlâ **bobin 7'yi** (STM) sınıyordu; yani ESP/MQTT yolunun çalıştığını kanıtladığını
söyleyen kontroller STM'i ölçüyordu. Ayrıca "ESP komutu MQTT'ye yayinlandi" kontrolü
`... or bool(b7.get("status"))` biçimindeydi — her yanıtta doğru (totoloji).

Araç bir backend başlattığı için testte KOŞTURULMAZ; kapı iki kattır:
  1. AST taraması: ESP etiketli her `check(...)`'in hedef aldığı bobin (önündeki son
     `req(..., "/api/coil/<n>/control")`) ya `esp_slotlari(...)`'ndan türeyen bir ad ya da
     `ESP_COIL_IDS` içindeki bir literaldir; ESP kontrolünde `or …get("status")` totolojisi yoktur.
  2. Davranış: aracın `esp_slotlari`'ı GERÇEK `/api/dashboard-snapshot` yanıtından tam olarak
     `ESP_COIL_IDS`'i üretir (topoloji değişirse araç kendiliğinden izler).
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


def _esp_turevli_adlar(fonk: ast.FunctionDef) -> set[str]:
    """`esp_slotlari(...)` çağrısından (doğrudan ya da türevli bir addan) değer alan adlar."""
    adlar: set[str] = set()
    degisti = True
    while degisti:
        degisti = False
        for d in ast.walk(fonk):
            if not isinstance(d, ast.Assign):
                continue
            kaynak_esp = any(
                (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "esp_slotlari")
                or (isinstance(n, ast.Name) and n.id in adlar)
                for n in ast.walk(d.value)
            )
            if kaynak_esp:
                for h in d.targets:
                    if isinstance(h, ast.Name) and h.id not in adlar:
                        adlar.add(h.id)
                        degisti = True
    return adlar


def _hedef(yol, esp_adlari):
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
        return "ESP" if isinstance(ifade, ast.Name) and ifade.id in esp_adlari else "?"
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


def esp_kontrolleri(kaynak: str):
    """[(fonksiyon, satır, etiket, hedef, totoloji_mi)] — yalnız etiketi 'ESP' içeren ve bir bobin
    yoluna bağlı kontroller."""
    agac = ast.parse(kaynak)
    sonuc = []
    for fonk in [d for d in agac.body if isinstance(d, ast.FunctionDef)]:
        esp_adlari = _esp_turevli_adlar(fonk)
        cagrilar = sorted(
            (d for d in ast.walk(fonk) if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)),
            key=lambda c: (c.lineno, c.col_offset),
        )
        son_hedef = None
        for c in cagrilar:
            if c.func.id == "req" and len(c.args) >= 2:
                son_hedef = _hedef(c.args[1], esp_adlari)
            elif c.func.id in ("snap", "esp_slotlari"):
                son_hedef = None  # anlık görüntü okundu → sonraki kontrol bobin komutunu değil görüntüyü sınar
            elif c.func.id == "check" and c.args:
                etiket = _etiket(c.args[0])
                if "ESP" in etiket and son_hedef is not None:
                    tot = len(c.args) > 1 and _totoloji_mi(c.args[1])
                    sonuc.append((fonk.name, c.lineno, etiket, son_hedef, tot))
    return sonuc


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
    assert not tot, f"ESP kontrolü her yanıtta doğru (`or …get('status')`): {tot}"


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
    s, b, _ = req("POST", "/api/hardware/emergency_stop")
    check("E-stop TUM ESP slotlari", s == 200)
'''
    k = esp_kontrolleri(ornek)
    assert [(e, h, t) for _f, _s, e, h, t in k] == [
        ("tekil ESP bobin (7)", 7, False),
        ("ESP komutu MQTT'ye yayinlandi", 7, True),
        ("ESP x", "?", False),
        ("ESP ()", "ESP", False),
    ], k  # anlık görüntü kontrolü (coil/1'den sonra) bobine bağlanmaz; E-stop yolu bobin yolu değil


def test_KRITIK_esp_slotlari_GERCEK_snapshottan_ESP_COIL_IDS_uretir(monkeypatch):
    from fastapi.testclient import TestClient
    from servers import api_server
    from servers.live_state import ESP_COIL_IDS

    monkeypatch.setattr(sys, "path", list(sys.path))  # araç kökü eklerse test sonunda geri gelir
    spec = importlib.util.spec_from_file_location("e2e_full_esp_kapisi", KAYNAK)
    arac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arac)
    anlik = TestClient(api_server.app, client=("127.0.0.1", 51237)).get("/api/dashboard-snapshot").json()
    assert arac.esp_slotlari(anlik) == sorted(ESP_COIL_IDS), (
        f"aracın ESP slotu türetmesi ürün topolojisiyle ayrıştı: {arac.esp_slotlari(anlik)} != {sorted(ESP_COIL_IDS)}"
    )
