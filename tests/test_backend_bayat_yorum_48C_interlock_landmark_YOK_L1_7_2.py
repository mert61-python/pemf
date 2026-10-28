# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""L1-7.2 (backend kolu) + i2-F-9 / i3-F-9 (backend) — var olmayan korumayı / kaldırılmış yolu anlatan bayat yorumlar YOK.

ÖLÇÜLEN (HEAD ebf1c3fe): `ai_router.py:699` "(freq/duty/48°C safety-limit'lerine DOKUNMAZ.)" — dokunulmayacak bir 48 °C sınırı
VARMIŞ gibi; `api_server.py:3333` "(clamp + seans + interlock)" — tedavi clamp'i YOK (Y9), termal interlock YOK (A-47);
`ai_router.py:504-505` "auto_adjust (donanım biofeedback) mikroservis modunda çekirdekte kalır" — D1.88'den beri 428;
`api_server.py` dört yerde "landmark (auto_adjust) her istekte çağırır" — `start_ai_session`ın bugün TEK çağıranı AI Pro
(`ai_router.py` `tur="ai_pro"`). "Yorum kapıyı kandırdı" sınıfı: sonraki denetimde var olmayan korumaya güvenilir.
Kod değişmedi (`ast.dump` önce = sonra); bu kapı yalnız METNİ pinler: yasak ifade YOK (tüm backend .py) + doğru ifade VAR.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
_BACKEND = KOK / "apps" / "backend"

#: Bayat (yanlış) iddialar — HİÇBİR backend .py dosyasında geçmemeli.
_YASAK = (
    (r"48\s*°C safety-limit'lerine DOKUNMAZ", "48 °C güvenlik sınırı VARMIŞ gibi (A-47: yok)"),
    (r"clamp \+ seans \+ interlock", "tedavi clamp'i (Y9) ve termal interlock (A-47) VARMIŞ gibi"),
    (r"auto_adjust \(donanım biofeedback\) mikroservis modunda çekirdekte kalır", "auto_adjust D1.88'den beri 428"),
    (r"landmark (auto_adjust )?her istekte (çağırır|cagirir)\b", "landmark D1.88'den beri start_ai_session çağırmaz"),
    (r"landmark surusu bobin 1-8'i 30 dk enerjiler →", "AI (Auto) landmark sürüşü D1.88'de kaldırıldı"),
)

#: Doğru iddialar — yerinde OLMALI (yorum silinip boş bırakılırsa da kırmızı).
_GEREKLI = (
    ("servers/ai_router.py", "48 °C termal kesme / interlock hiçbir katmanda YOK, A-47"),
    ("servers/ai_router.py", "`auto_adjust` yukarıda 428 ile reddedildi"),
    ("servers/api_server.py", "tedavi clamp'i YOK — Y9 · termal interlock YOK — A-47"),
    ("servers/api_server.py", "D1.88'e kadar landmark her"),
)


def test_bayat_48C_interlock_landmark_iddiasi_backendde_YOK():
    bulunan = []
    for yol in sorted(_BACKEND.rglob("*.py")):
        metin = yol.read_text(encoding="utf-8", errors="replace")
        # Satıra bölünmüş yorum cümlesi de yakalansın ("# … her" + "# istekte çağırır"): yorum devamı tek satıra birleştirilir.
        duz = re.sub(r"\n[ \t]*#[ \t]*", " ", metin)
        for desen, neden in _YASAK:
            for m in re.finditer(desen, duz):
                bulunan.append(f"{yol.relative_to(KOK).as_posix()}: {m.group(0)!r} — {neden}")
    assert not bulunan, "bayat / yanlış iddia:\n  " + "\n  ".join(bulunan)


def test_dogru_iddia_YERINDE():
    eksik = [f"{d}: {s!r}" for d, s in _GEREKLI if s not in (_BACKEND / d).read_text(encoding="utf-8")]
    assert not eksik, "gerçeği söyleyen yorum yok:\n  " + "\n  ".join(eksik)


def test_bayat_iddia_SATIR_KIRILIMINDA_ve_HARF_DEGISIMINDE_de_YOK():
    """Tur 2 kolu (çürütücü — yorum / dize içine taşıma, önek genellemesi): aynı yasak iddia DOCSTRING içinde satıra bölünmüş
    ("… Landmark her (satır sonu) istekte çağırır") ya da harfi değişmiş ("… safety-limit'lerine dokunmaz") hâlde de yakalanır —
    yorum devamı birleştirildikten sonra TÜM boşluk tek boşluğa indirilir ve desenler harf-duyarsız aranır."""
    bulunan = []
    for yol in sorted(_BACKEND.rglob("*.py")):
        metin = yol.read_text(encoding="utf-8", errors="replace")
        duz = " ".join(re.sub(r"\n[ \t]*#[ \t]*", " ", metin).split())
        for desen, neden in _YASAK:
            for m in re.finditer(desen, duz, flags=re.IGNORECASE):
                bulunan.append(f"{yol.relative_to(KOK).as_posix()}: {m.group(0)!r} — {neden}")
    assert not bulunan, "bayat / yanlış iddia (satır kırılımı / harf değişimi):\n  " + "\n  ".join(bulunan)
