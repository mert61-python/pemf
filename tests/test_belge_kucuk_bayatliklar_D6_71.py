# -*- coding: utf-8 -*-
"""D6.71 (B-11.23) — belgelerdeki küçük bayatlıkların en keskinleri geri gelmesin (yer tutucu · kayan satır başvurusu · ESP / 48 °C).

ÖLÇÜLEN (HEAD ebf1c3fe): `docs/arsiv/responsive-denetim-2026-09-04.md:9` doldurulmamış `{IKINCI_CUMLE}` yer tutucusu;
`docs/ARIZA-LISTESI.md:175` `api_server.py:2451` (sembol `from ai.hybrid_recommender import …` bugün başka satırda — kayan satır
başvurusu); `docs/SAHA-ISLERI-REHBERI.md:7` "Önerilen sıra: B-1 → …" (B-1 = ESP32-S3 reflash; ESP KAPALI — `live_state.py`
`PEMF_ESP_ENABLED` varsayılanı "0"); `docs/arastirma-ai-pro-fantom-petri-plani.md:382-383, :713` "backend freq/duty/48 °C güvenlik
sınırı" (backend'de tedavi duty / 48 °C sınırı YOK — Y9 · A-47). Üstü çizili (`~~…~~`) tarihçe sayılmaz.

⚠️ Kapı bilinçli DAR: her `dosya.py:NNN` başvurusunu her kod kaydırmasında kırmızı yapmak belgeyi gürültüye boğar (plan "uyandırır"
notu) — yalnız SEMBOLLE eşlenen satır başvurusu ölçülür.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from utils.path_utils import kaynak_kokunu_bul

KOK = Path(kaynak_kokunu_bul(__file__))
#: `deploy/README.md` `{REMOTE_ADDR}` IIS değişkenidir (karşıt vaka — yer tutucu değil).
YER_TUTUCU_MUAF = {("deploy/README.md", "{REMOTE_ADDR}")}


def _cizgisiz(md: str) -> str:
    return re.sub(r"~~.*?~~", " ", md, flags=re.S)


def _md_dosyalari() -> list[str]:
    cikti = subprocess.run(["git", "-C", str(KOK), "ls-files", "-z", "*.md"], capture_output=True, check=True).stdout
    return [p for p in cikti.decode("utf-8").split("\0") if p]


def test_KRITIK_doldurulmamis_SABLON_yer_tutucusu_YOK():
    dosyalar = _md_dosyalari()
    assert len(dosyalar) > 50, f"aparat: izlenen .md bulunamadı ({len(dosyalar)})"
    bulunan = []
    for yol in dosyalar:
        p = KOK / yol
        if not p.exists():
            continue  # silinmiş ama indekste — ölçülecek metin yok
        metin = p.read_text(encoding="utf-8", errors="replace")
        # kod çitleri ve satır içi kod (`{ KAV_BEHAVIOR_MODAL }` gibi gerçek import'lar) yer tutucu DEĞİLDİR
        metin = re.sub(r"`[^`\n]*`", " ", re.sub(r"```.*?```", " ", metin, flags=re.S))
        for m in re.finditer(r"\{[A-Z_]{6,}\}", metin):
            if (yol, m.group(0)) not in YER_TUTUCU_MUAF:
                bulunan.append(f"{yol}: {m.group(0)}")
    assert not bulunan, "doldurulmamış şablon yer tutucusu:\n  " + "\n  ".join(bulunan)


def test_KRITIK_satir_basvurusu_SEMBOLLE_eslesir_hybrid_recommender():
    api = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8").splitlines()
    ariza = _cizgisiz((KOK / "docs" / "ARIZA-LISTESI.md").read_text(encoding="utf-8"))
    for satir in ariza.splitlines():
        if "hybrid_recommender" not in satir:
            continue
        for m in re.finditer(r"api_server\.py:(\d+)", satir):
            n = int(m.group(1))
            if "2026-09-19'da :" in satir[max(0, m.start() - 20) : m.start() + 5]:
                continue  # tarihli kayıt biçimi ("2026-09-19'da :2451")
            hedef = api[n - 1] if 0 < n <= len(api) else ""
            assert "hybrid_recommender" in hedef, (
                f"ARIZA-LISTESI `api_server.py:{n}` diyor ama o satırda hybrid_recommender YOK (kayan satır başvurusu) — sembolle anın"
            )


def test_KRITIK_ESP_kapaliyken_saha_sirasi_ESP_reflash_ile_BASLAMAZ():
    ls = (KOK / "apps" / "backend" / "servers" / "live_state.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PEMF_ESP_ENABLED", "0") == "1"' in ls, (
        "aparat: ESP varsayılanı değişti — kapıyı bilinçli güncelleyin"
    )
    rehber = _cizgisiz((KOK / "docs" / "SAHA-ISLERI-REHBERI.md").read_text(encoding="utf-8"))
    sira = [s for s in rehber.splitlines() if s.startswith("**Önerilen sıra:**")]
    assert len(sira) == 1, "SAHA-ISLERI-REHBERI 'Önerilen sıra' satırı tek olmalı"
    assert not re.search(r"\bB-1\s*→", sira[0]), f"ESP KAPALIYKEN sıra ESP32-S3 reflash (B-1) ile başlıyor: {sira[0]!r}"


def test_KRITIK_arastirma_plani_backend_48C_sinirini_IDDIA_ETMEZ():
    plan = _cizgisiz((KOK / "docs" / "arastirma-ai-pro-fantom-petri-plani.md").read_text(encoding="utf-8"))
    assert not re.search(r"backend\s+freq/duty/48\s*°C", plan), (
        "plan backend'de 48 °C / duty sınırı VARMIŞ gibi yazıyor (Y9 · A-47)"
    )
