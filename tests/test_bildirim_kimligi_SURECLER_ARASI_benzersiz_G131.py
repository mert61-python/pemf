# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""1-G inceleme G-13.1 — bildirim kimliği backend YENİDEN BAŞLAYINCA tekrarlanmaz (Y64 açılış bildirimi görünür kalır).

ÖLÇÜLEN KUSUR (inceleme, `6cb8841`): arayüz yerel "okundu" işaretini bildirim KİMLİĞİNE göre oturum boyu saklar ve her
snapshot'a uygular (`apps/ui/src/context/LiveDataContext.tsx` `readIdsRef` / `applyLocalReads`, #46 — aynı backend'e yeniden
bağlanmada rozet dirilmesin). Backend'in sayacı (`live_state._notif_counter`) her süreçte 0'dan başlıyordu → arayüz AÇIKKEN
backend yeniden başlayınca yeni süreçteki bildirimler önceki oturumda okunmuş kimlikleri (1, 2, …) alıp OKUNMUŞ sayılıyordu.
Jest sondası (gerçek `LiveDataProvider`, "Test Suites: 1 passed"): üç bildirim → "tümünü okundu" → backend yeniden başladı →
yeni süreçteki Y64 bildirimi ("Mandal dosyası yazılamadı … geri gelecek") kimlik 1 ile gelir → okunmamış rozeti **0** (sahibin
Y64'te istediği açılış uyarısı rozetsiz kalır); süreçler arası benzersiz kimlikle **1**.

SÖZLEŞME: iki ardışık backend sürecinin bildirim kimlikleri ÇAKIŞMAZ (sonraki süreçteki her kimlik öncekilerin hepsinden
büyük); süreç içinde kimlik 1'er artar (P3 kilit sözleşmesi aynen); kimlik JS Number'da kesin (< 2^53, tür `number` aynı).
GERÇEK `servers.live_state._push_notification` iki AYRI Python sürecinde koşar (yeniden başlatma); çocukta ağ bekçisi.
"""

from __future__ import annotations

import json
from pathlib import Path

from betik_alt_sureci import kostur, yalitik_ortam

KOK = Path(__file__).resolve().parents[1]
TESTLER = Path(__file__).resolve().parent
BACKEND = KOK / "apps" / "backend"

_COCUK = r"""
import sys
sys.path.insert(0, {testler!r})
import alt_surec_ag_bekcisi as _ag
sys.path.remove({testler!r})
import json
sys.path[:0] = [{kok!r}, {backend!r}]
from servers import live_state
for k in range({adet}):
    live_state._push_notification("sonda %d" % k, "info")
with live_state._live_state_lock:
    kimlikler = [n["id"] for n in reversed(live_state._live_state["notifications"])]
print("SONUC=" + json.dumps({{"kimlikler": kimlikler, "ag": list(_ag.ENGELLENEN)}}))
"""


def _surec(tmp_path: Path, ad: str, adet: int) -> list:
    dizin = tmp_path / ad
    dizin.mkdir()
    betik = dizin / "cocuk.py"
    betik.write_text(
        _COCUK.format(testler=str(TESTLER), kok=str(KOK), backend=str(BACKEND), adet=adet), encoding="utf-8"
    )
    r = kostur([str(betik)], cwd=dizin, env=yalitik_ortam(dizin / "ev"), sure=180)
    satir = [s for s in r.stdout.splitlines() if s.startswith("SONUC=")]
    assert satir, f"cocuk surec sonuc vermedi (rc={r.returncode}): {r.stdout[-800:]} {r.stderr[-1500:]}"
    sonuc = json.loads(satir[-1][len("SONUC=") :])
    assert sonuc["ag"] == [], f"cocuk surec aga cikmaya calisti: {sonuc['ag']}"
    return sonuc["kimlikler"]


def test_KRITIK_G131_bildirim_kimligi_backend_YENIDEN_BASLAYINCA_onceki_kimliklerle_CAKISMAZ(tmp_path):
    once = _surec(tmp_path, "once", 5)
    sonra = _surec(tmp_path, "sonra", 3)
    assert once == list(range(once[0], once[0] + 5)), f"aparat/P3: süreç içinde kimlik 1'er artmalı: {once}"
    assert sonra == list(range(sonra[0], sonra[0] + 3)), f"aparat/P3: süreç içinde kimlik 1'er artmalı: {sonra}"
    assert min(sonra) > max(once), (
        f"backend yeniden başlayınca bildirim kimlikleri TEKRARLANDI (önceki süreç {once}, sonraki {sonra}) — arayüz "
        "yerel okundu işaretini kimliğe göre uyguladığı için yeni bildirimler (Y64 açılış uyarısı dahil) OKUNMUŞ görünür"
    )
    assert all(isinstance(k, int) and 0 < k < 2**53 for k in once + sonra), f"kimlik JS Number'da kesin değil: {sonra}"
