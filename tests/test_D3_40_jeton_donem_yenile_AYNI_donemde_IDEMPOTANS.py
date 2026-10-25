# Author: mertaygn, cglrgrkn
"""D3.40 (B-7.4) — `jeton_donem_yenile` aynı dönem için yinelenen teslimde harcanan hakkı SIFIRLAMAZ (statik SQL kapısı).

ÖLÇÜLEN (HEAD): RPC her çağrıda `donem_basi = now()` ile dönemi baştan kuruyordu — iyzico'nun yeniden teslimi ya da callback +
webhook'un ilk ACTIVE'i abonenin o dönemde harcadığı hakkı geri veriyordu. Ödeme yolu FREE_MODE'da UYKUDA; canlı Supabase'e
DOKUNULMADI — dosya canlıya sahip tarafından uygulanır (rapor [SAHİBE]). plpgsql burada koşturulamaz → gövde metni ölçülür.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _govde() -> str:
    sql = (KOK / "apps" / "backend" / "database" / "supabase_jetonlar.sql").read_text(encoding="utf-8")
    m = re.search(r"create or replace function public\.jeton_donem_yenile\(.*?\$\$(.*?)\$\$;", sql, re.S | re.I)
    assert m, "jeton_donem_yenile bulunamadı"
    return re.sub(r"--[^\n]*", "", m.group(1))


def test_KRITIK_D3_40_taze_donemde_ayni_hakla_cagri_ETKISIZ_ve_yazimdan_ONCE():
    g = _govde()
    i = g.find("if exists")
    assert i >= 0, "dönem idempotans koruması yok"
    koruma = g[i : g.find("end if;", i)]
    for parca in (
        "b.user_id = p_user",
        "b.aylik_hak = p_aylik_hak",
        "b.donem_sonu > now() + interval '20 days'",
        "return;",
    ):
        assert parca in koruma, f"koruma eksik: {parca}"
    assert i < g.find("insert into public.token_balances") and i < g.find("insert into public.token_ledger"), (
        "koruma yazımdan SONRA"
    )


def test_KARSIT_D3_40_yenileme_ve_plan_degisikligi_YINE_yeni_donem_acar():
    g = _govde()
    assert "donem_basi = now()" in g and "aylik_hak = excluded.aylik_hak" in g
