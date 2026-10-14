# -*- coding: utf-8 -*-
"""ARAYÜZ PROFİLİNE GÖRE KAYIT AYRIMI — SG.G1 / G2 (sahip gözlemi 2026-10-13).

Sahip: "raporlar seans geçmişi vs de ayrılmalı profillere göre … klinikle araştırma modunun alakası yok" + "araştırma modunun ai analiz
geçmişinde veteriner modunun ai analizi geçmişi de görünüyor". Profil (Ev Sahibi / Veteriner / Araştırma) yalnız ARAYÜZ kipidir
(`UserModeContext`; bilinçli olarak KALICI DEĞİL) ve herkese AÇIKTIR — bu modül erişim kapısı DEĞİL, veri ve görünüm ayrımıdır:
  · istemci etkin profili her istekte `X-PEMF-Profil` başlığıyla bildirir (`apiClient.authHeaders`);
  · YENİ kayıt (seans, AI analizi, hasta / denek) profiliyle yazılır (AI Pro kararları listelenmez → seansına bağlı, kolon YOK);
  · liste / rapor / KPI uçları başlık VARSA profile göre SÜZER — başlık göndermeyen eski istemci (sahadaki / telefondaki yayınlanmış
    APK) bugünkü gibi süzgeçsiz görür (kırılmaz);
  · silme / toplu silme kapsamı GENİŞLEMEZ — profil süzgeci kapsamı yalnız DARALTIR (Y104 / Y109 / Y131 aynen).
ESKİ kayıt (profili boş) TÜRETİLİR (veri DEĞİŞTİRİLMEZ, okumada hesaplanır → geri alınabilir): AI analizi → kendi `mode`u, yoksa
modülün profili (arayüzün tek kaynağı `apps/ui/src/screens/AiHubScreen.tsx::ALL_MODULES.modes`; sürüklenme kapısı
`tests/test_profil_ayrimi_SG_G1_G2.py`); seans → araştırma AI Pro sağlayıcısı (fantom / petri) ise araştırma, değilse veteriner;
hasta → veteriner VE ev sahibi (hangisinde oluşturulduğu bilinmez; araştırmaya düşmez — S-SG.7).
⚠️ YAPRAK MODÜL: yalnız stdlib (depo-içi import YOK) — veritabanı katmanı ve uçlar içe aktarır.
"""

from __future__ import annotations

VETERINER = "veterinarian"
ARASTIRMA = "researcher"
EV_SAHIBI = "pet_owner"
PROFILLER = (VETERINER, ARASTIRMA, EV_SAHIBI)
PROFIL_BASLIGI = "X-PEMF-Profil"

#: Araştırma profilinin AI modülleri — `AiHubScreen.ALL_MODULES` içinde `modes: ["researcher"]` olanlar (kapı ikisini karşılaştırır).
#: Kayda yazılan `module_id` aynı kimliklerdir (`logAiResult({ moduleId })`).
ARASTIRMA_AI_MODULLERI = frozenset(
    {"em_fantom", "em_petri", "kidney_rna", "kidney_disease", "kidney_ct", "histopath", "cell_scratch"}
)
#: Araştırma AI Pro sağlayıcılarının seans `treatment_mode` önekleri (`ai_router` /pro/start: f"AI Pro · {sağlayıcı.title}";
#: `ai_pro_hedef.FantomSaglayici.title` = "Fantom Tümör", `PetriSaglayici.title` = "Petri Kuyu").
ARASTIRMA_SEANS_ONEKLERI = ("AI Pro · Fantom", "AI Pro · Petri")
#: Profili boş ESKİ hasta / denek kaydının göründüğü profiller (S-SG.7).
ESKI_HASTA_PROFILLERI = frozenset({VETERINER, EV_SAHIBI})


def gecerli_profil(deger) -> str | None:
    """Bilinen bir profil adı mı? (boş / bilinmeyen → None)."""
    d = str(deger or "").strip().lower()
    return d if d in PROFILLER else None


def istek_profili(request) -> str | None:
    """İsteğin bildirdiği etkin profil (`X-PEMF-Profil`); yoksa / bozuksa None → süzgeç YOK (eski istemci, bugünkü davranış)."""
    try:
        return gecerli_profil(request.headers.get(PROFIL_BASLIGI))
    except Exception:
        return None


def ai_kaydi_profili(mode, module_id) -> str:
    """AI analiz kaydının profili: kayda yazılan `mode` geçerliyse o; değilse modülden türetilir (bilinmeyen → veteriner)."""
    p = gecerli_profil(mode)
    if p:
        return p
    return ARASTIRMA if str(module_id or "").strip() in ARASTIRMA_AI_MODULLERI else VETERINER


def seans_profili(profil, treatment_mode) -> str:
    """Seans kaydının profili: yazılmış profil geçerliyse o; değilse araştırma AI Pro seansı → araştırma, değilse veteriner."""
    p = gecerli_profil(profil)
    if p:
        return p
    m = str(treatment_mode or "")
    return ARASTIRMA if any(m.startswith(o) for o in ARASTIRMA_SEANS_ONEKLERI) else VETERINER


def hasta_profilde_mi(profil_alani, istenen: str) -> bool:
    """Hasta / denek kaydı istenen profilde görünür mü? Yazılmış profil → yalnız o; boş (eski) → `ESKI_HASTA_PROFILLERI`."""
    p = gecerli_profil(profil_alani)
    return (p == istenen) if p else (istenen in ESKI_HASTA_PROFILLERI)


def sqlite_islevleri(conn) -> None:
    """SQL süzgeçlerinde kullanılan işlevleri bağlantıya kaydeder (`pemf_ai_profil`, `pemf_seans_profil`) — süzgeç SQL'de koşar,
    böylece sayfalama (`before_id` / `LIMIT`) süzülmüş kümeyle tutarlı kalır."""
    conn.create_function("pemf_ai_profil", 2, ai_kaydi_profili)
    conn.create_function("pemf_seans_profil", 2, seans_profili)
