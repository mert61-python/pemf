# -*- coding: utf-8 -*-
"""CT3 (istem 66) — META KAPI: YS2 a'nın AI Pro sürüş muhasebesi testler arası SIZMAZ (conftest
`_ai_pro_surus_muhasebesi_sizmaz`).

ÖLÇÜLEN (ilk GitHub koşusu, critical-path-tests 46088377503 @ 6d1ebb75, xdist 4 işçi): `test_seans_ortasi_SURE_KALAN_sure_Y5_D170::
test_KRITIK_Y5_KISALTMA_seans_KALAN_sureyle_biter_kayit_GERCEK_sureyi_yazar` KIRMIZI — "kayıt GERÇEK süreyi yazmalı (15 dk):
durum='stopped' süre=0"; yerel CT1 / CT2 tam koşularında (farklı işçi dağılımı) yeşil. Kök neden: `servers.ai_pro_surus_muhasebesi.
_kayitlar` (anahtar = `db_session_id`) modül-geneldir; AI Pro döngüsünü (`basla`) koşturup seansı tek kapanış yolundan
(`_finalize_session_db` / `/session/stop`) kapatmayan test kaydı BIRAKIR. Aynı süreçte sonraki testin TAZE DB'sindeki seans da
`id=1` alır → kapanışta bayat kayıt "hiç sürülmedi" sayılır → Manuel seans "Durduruldu · 0 dk · doz 0" yazılır.

KAPI (dosya içi SIRA — pytest dosyayı yukarıdan aşağı koşar): 1. kol döngünün yaptığını yapar (`basla(1)`) ve kapatmadan çıkar;
2. kol temiz başlamalı ve kimlik 1'in kapanışı DÜZELTİLMEMELİ (Manuel seans aynen "completed"). Tek başına koşulduğunda da anlamlı.
"""

from __future__ import annotations

_BASTA: dict = {}


def test_1_SIZDIRAN_kol_AI_Pro_dongusu_basla_cagirip_KAPATMADAN_cikar():
    from servers import ai_pro_surus_muhasebesi as m

    with m._kilit:
        _BASTA["kayitlar"] = dict(m._kayitlar)
    m.basla(1)  # `ai_router._ai_pro_loop` seans başı (db_session_id 1 = taze test DB'sinin ilk seansı)
    assert _BASTA["kayitlar"] == {}, f"aparat: test zaten muhasebe kaydıyla başladı: {_BASTA}"


def test_2_SONRAKI_test_TEMIZ_baslar_MANUEL_seans_kapanisi_DUZELTILMEZ():
    from servers import ai_pro_surus_muhasebesi as m

    with m._kilit:
        kalan = dict(m._kayitlar)
    assert kalan == {}, (
        f"önceki testin bıraktığı AI Pro sürüş muhasebesi bu teste SIZDI: {kalan} — taze DB'deki seans aynı kimliği alır, "
        "kapanışı 'stopped · 0 dk' yazılır (sıraya bağlı kırmızı)"
    )
    assert m.kapanis_duzeltmesi(1, "completed") is None, "muhasebesi olmayan (Manuel) seansın kapanışı düzeltildi"
