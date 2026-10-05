# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y64 (sahip, 1-F S-F4) — açılış yoklaması mandal dosyasını YAZILAMAZ bulursa ekran bildirimi AÇILIŞTA gönderilir.

ÖLÇÜLEN KUSUR (1-F açık madde 6; 1-G önce-kırmızı `f65402b`): `estop_mandali.kalicilik_kur` açılışta HİÇBİR ŞEY
YAZMADAN dosyanın salt-okunur olduğunu ya da yerinde dizin bulunduğunu görüyor (`_yazim_yoklamasi`) ama yalnız günlüğe
yazıyordu. Operatör bunu ilk ACİL DURDUR ya da Sıfırla'ya dek bilmiyordu (Y59 bildirimi o anlara bağlı); bant "önceki
oturumda ACİL DURDUR — sıfırlanmadı" derken nedeni görünmüyordu.

SÖZLEŞME (sahip Y64): açılışta Y59'un metniyle ekran bildirimi — "Mandal dosyası yazılamadı (<yol>) — yeniden başlatmada
mandal [geri gelecek / KORUNMAYACAK]; dosya iznini düzeltin." Diskte KURULU mandal (Sıfırla yazamayacak → her açılışta geri
gelir) → "geri gelecek" — dosyanın yerinde DİZİN de böyledir: okunamayan dosya mandalı KURAR (Y56) ve Sıfırla onu silemez;
kurulu değil (salt-okunur `aktif:false`: ACİL DURDUR'un mandalı yazılamayacak) → "KORUNMAYACAK". Dosyaya YAZILMAZ (içerik +
mtime aynı); ACİL DURDUR akışı değişmez. ACL reddi yazmadan görülemez (Y64: onu ilk E-stop/Sıfırla söyler) → yazılabilir
görünen dosyada bildirim YOK (karşıt).

GERÇEK açılış: AYRI Python süreci ürünün açılış bağlantısını (`backend_service._wire_api_server`) koşar; bildirim, sonradan
bağlanan ekranın aldığı WS anlık görüntüsünde (`_build_ws_snapshot()["notifications"]`) aranır. Çocukta ağ bekçisi.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"
_DOSYA = "estop_mandali.json"

_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json
sys.path[:0] = [{kok!r}, {backend!r}]
from types import SimpleNamespace
import backend_service
from servers import live_state
from utils import estop_mandali
backend_service._wire_api_server(SimpleNamespace(app_data_dir={veri!r}))
_anlik = live_state._build_ws_snapshot()
print("SONUC=" + json.dumps({{"bildirimler": [n.get("message", "") for n in _anlik.get("notifications") or []],
                             "durum": estop_mandali.durum(), "ag": list(_ag.ENGELLENEN)}}, ensure_ascii=False))
"""


def _acilis(veri: Path, tmp_path: Path) -> dict:
    betik = tmp_path / "acilis.py"
    betik.write_text(
        _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), veri=str(veri)), encoding="utf-8"
    )
    r = kostur([str(betik)], cwd=tmp_path, env=yalitik_ortam(tmp_path / "ev"), sure=180)
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC=")]
    assert satir, f"cocuk surec sonuc vermedi (rc={r.returncode}): {r.stdout[-800:]} {r.stderr[-1500:]}"
    sonuc = json.loads(satir[-1][len("SONUC=") :])
    assert sonuc["ag"] == [], f"cocuk surec aga cikmaya calisti: {sonuc['ag']}"
    return sonuc


def _mandal_bildirimi(sonuc: dict) -> list:
    return [m for m in sonuc["bildirimler"] if "Mandal dosyası yazılamadı" in m]


def _iz(yol: Path):
    return (yol.read_bytes(), yol.stat().st_mtime_ns)


def test_KRITIK_Y64_salt_okunur_KURULU_dosya_ACILISTA_bildirilir_geri_gelecek(tmp_path):
    veri = tmp_path / "veri"
    veri.mkdir()
    dosya = veri / _DOSYA
    dosya.write_text(json.dumps({"aktif": True, "neden": "manual"}), encoding="utf-8")
    os.chmod(dosya, stat.S_IREAD)
    try:
        once = _iz(dosya)
        s = _acilis(veri, tmp_path)
        assert s["durum"].get("aktif") is True, f"aparat: diskteki mandal yüklenmedi: {s['durum']}"
        b = _mandal_bildirimi(s)
        assert b, f"açılışta mandal dosyası YAZILAMAZ görünüyor ama ekran bildirimi YOK: {s['bildirimler']}"
        assert str(dosya) in b[0] and "geri gelecek" in b[0] and "dosya iznini düzeltin" in b[0], b[0]
        assert _iz(dosya) == once, "açılış yoklaması mandal dosyasına YAZDI (Y64: dosyaya yazılmaz)"
    finally:
        os.chmod(dosya, stat.S_IREAD | stat.S_IWRITE)


def test_KRITIK_Y64_dosyanin_yerinde_DIZIN_ACILISTA_bildirilir_geri_gelecek(tmp_path):
    """Dizin okunamaz → mandal KURULU başlar (Y56); Sıfırla yazamaz → her açılışta geri gelir."""
    veri = tmp_path / "veri"
    (veri / _DOSYA).mkdir(parents=True)
    s = _acilis(veri, tmp_path)
    assert s["durum"].get("aktif") is True, f"aparat: okunamayan dosya mandalı kurmadı (Y56): {s['durum']}"
    b = _mandal_bildirimi(s)
    assert b, f"mandal dosyasının yerinde dizin var ama açılışta bildirim YOK: {s['bildirimler']}"
    assert str(veri / _DOSYA) in b[0] and "geri gelecek" in b[0], b[0]


def test_KRITIK_Y64_salt_okunur_BOS_mandal_ACILISTA_bildirilir_KORUNMAYACAK(tmp_path):
    """Kurulu olmayan, salt-okunur dosya: ilk ACİL DURDUR'un mandalı diske yazılamaz → yeniden başlatmada KORUNMAZ."""
    veri = tmp_path / "veri"
    veri.mkdir()
    dosya = veri / _DOSYA
    dosya.write_text(json.dumps({"aktif": False, "neden": ""}), encoding="utf-8")
    os.chmod(dosya, stat.S_IREAD)
    try:
        once = _iz(dosya)
        s = _acilis(veri, tmp_path)
        assert s["durum"].get("aktif") is False, f"aparat: kurulu olmayan mandal kuruldu: {s['durum']}"
        b = _mandal_bildirimi(s)
        assert b, f"salt-okunur mandal dosyası açılışta bildirilmedi: {s['bildirimler']}"
        assert str(dosya) in b[0] and "KORUNMAYACAK" in b[0], b[0]
        assert _iz(dosya) == once, "açılış yoklaması mandal dosyasına YAZDI (Y64: dosyaya yazılmaz)"
    finally:
        os.chmod(dosya, stat.S_IREAD | stat.S_IWRITE)


def test_KARSIT_Y64_yazilabilir_dosyada_ACILIS_bildirimi_YOK(tmp_path):
    veri = tmp_path / "veri"
    veri.mkdir()
    (veri / _DOSYA).write_text(json.dumps({"aktif": False, "neden": ""}), encoding="utf-8")
    s = _acilis(veri, tmp_path)
    assert not _mandal_bildirimi(s), f"yazılabilir dosyada sahte 'yazılamadı' bildirimi: {s['bildirimler']}"
