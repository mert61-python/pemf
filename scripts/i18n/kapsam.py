# -*- coding: utf-8 -*-
"""I18N KAPSAM DEFTERİ (`i18n/kapsam.json`) — göçün TEK GERÇEĞİ (T15).

Defter yüzeylerin BÜTÜN kaynak dosyalarını kapsar. Dosya başına: yüzey, grup, sıra, durum (`bekliyor` | `tamam` | `muaf`), metin sayısı
(göç öncesi TR tabanından), kritik mi, `muaf` listesi (metin + gerekçe), `birlesikIstisna` listesi (önce / sonra), not.
Parti bir grubu bitirince grubun ve dosyalarının durumunu AYNI commit'te `tamam` yapar (`isaretle`) → KESİNTİ'de yarım grup belli olur.
K-2 (`tests/test_i18n_sabit_metin_K2.py`) `tamam` dosyada kullanıcıya görünen sabit metin bırakmaz; `k2Kapsam: "hepsi"` olunca (göç bitti)
`bekliyor` dosya kalmamalı.

Kullanım:
  ..\\python.exe scripts\\i18n\\kapsam.py uret [--taban YOL]    # yeni dosyaları ekler, var olanların durum / muaf / notunu KORUR
  ..\\python.exe scripts\\i18n\\kapsam.py durum                  # grup tablosu + SIRADAKİ grup
  ..\\python.exe scripts\\i18n\\kapsam.py isaretle <grup> tamam   # grup + dosyaları (muaf dosyalar muaf kalır)
  ..\\python.exe scripts\\i18n\\kapsam.py dosya <yol> <tamam|bekliyor|muaf> [--gerekce "…"]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import ortak  # noqa: E402

DEFTER = "i18n/kapsam.json"
VARSAYILAN_TABAN = ortak.varsayilan_taban()

#: (grup, sıra, kritik, açıklama) — sıra istemdeki T15 sırasıdır; büyük gruplar alt harfle bölünür.
GRUPLAR = [
    (
        "arayuz-01-ortak-kabuk",
        1,
        False,
        "ortak bileşenler + kabuk (AppShell, bildirim, toast, hata sınırı, sayfa başlıkları, tema)",
    ),
    ("arayuz-02-giris-hesap", 2, False, "giriş / hesap / operatör (+ Supabase dönüş sayfaları)"),
    ("arayuz-03-ayarlar", 3, False, "ayarlar, eşleştirme, sistem bilgisi, güncelleme bantları"),
    ("arayuz-04-hasta", 4, False, "hasta ekranı, hasta kapısı, gözlem notu, profil sözlüğü"),
    ("arayuz-05a-kontrol-kritik", 5, True, "kontrol / bobin parametreleri / sürüş kipi / doz göstergeleri (KRİTİK)"),
    (
        "arayuz-05b-guvenlik-kritik",
        5,
        True,
        "ACİL DURDUR, mandal bandı, seans ilerleme, söküm koruması, ana ekran (KRİTİK)",
    ),
    (
        "arayuz-06a-ai-hub",
        6,
        False,
        "AiHubScreen (tek dosya, ~770 metin — bir oturumda bitmezse alt bölümlere: KURALLAR §Büyük dosya)",
    ),
    ("arayuz-06b-ai-bilesen", 6, False, "AI Pro paneli, hedef / model seçimi, onay / değerlendirme"),
    ("arayuz-06c-ai-etiket", 6, False, "AI sonuç etiketleri (aiDetail — K-7 sunucu eşliği) + AI yardımcıları"),
    ("arayuz-07-rapor-gecmis-kpi", 7, False, "seans / AI geçmişi, seans ayrıntısı, KPI, indirme"),
    ("arayuz-08-jeton", 8, False, "jeton / abonelik / erişim"),
    ("arayuz-09-yardimci", 9, False, "kalan servis / yardımcı / tür dosyaları"),
    (
        "sunucu-10a-yonlendirici",
        10,
        False,
        "yönlendirici hata iletileri (hasta, geçmiş, seans, kimlik, sistem, güncelleme, jeton)",
    ),
    ("sunucu-10b-api-server", 10, True, "api_server.py — donanım / seans / ACİL DURDUR iletileri (KRİTİK)"),
    ("sunucu-10c-ai", 10, False, "AI yönlendirici + AI Pro hedef + görüntü alanı iletileri"),
    ("sunucu-10d-ai-rapor", 10, False, "AI rapor öğeleri (ETIKETLER / DEGERLER / BELIRTILER — K-7)"),
    ("sunucu-10e-pdf", 10, False, "PDF raporu, seans durum etiketleri, dışa aktarma"),
    ("sunucu-10f-bildirim-ws", 10, True, "bildirim / WS / STM / firmware / mandal iletileri (KRİTİK)"),
    (
        "sunucu-10g-diger",
        10,
        False,
        "veritabanı, servisler, güncelleme, kalan yardımcılar (çoğu muaf: iç / günlük / DB değeri)",
    ),
    ("launcher-11a-ui", 11, False, "launcher arayüzü (index.html — mevcut TR/EN sözlüğü kataloğa)"),
    ("launcher-11b-rust", 11, False, "launcher Rust iletileri (main.rs + core)"),
    ("launcher-11c-nsis", 11, True, "kurulum sihirbazı iletileri (hooks.nsi — LangString)"),
    ("site-12a-sayfa", 12, False, "site üst menü / alt bilgi / ana sayfa / özellikler / indirme / destek bileşenleri"),
    ("site-12b-ticari", 12, False, "fiyatlar, ödeme, hesap, site işlevleri (api — makine-okur kod → istemcide çeviri)"),
    ("site-12c-yasal", 12, False, "YASAL metinler (EN SON; 'Türkçe metin bağlayıcıdır' notu, hukuki onay sahipte)"),
    ("dema-13", 13, False, "DEMA simülatörü"),
]

#: (düzenli ifade, grup) — İLK eşleşen kazanır. Yollar depo-göreli.
KURALLAR = [
    (r"^apps/ui/src/i18n/", "arayuz-01-ortak-kabuk"),
    (
        r"^apps/ui/src/components/ui/(GlobalEmergencyStop|EstopMandalBandi|KendiDurdurmaKontrolu)\.tsx$",
        "arayuz-05b-guvenlik-kritik",
    ),
    (r"^apps/ui/src/components/ui/JetonRozeti\.tsx$", "arayuz-08-jeton"),
    (
        r"^apps/ui/(app/|src/PemfApp\.tsx|src/components/ui/|src/components/visual/|src/components/UpgradeModal\.tsx|src/config/sayfaBasliklari\.ts|src/theme/|src/context/(AppNavContext|ShellLayoutContext|UserModeContext)\.tsx)",
        "arayuz-01-ortak-kabuk",
    ),
    (
        r"^apps/ui/(auth-pages/|src/screens/(AuthScreen|WelcomeScreen)\.tsx|src/components/domain/(HesapMenusu|OperatorSwitcher)\.tsx|src/context/(AuthContext|OperatorContext)\.tsx|src/services/(authApi|supabaseAuth|hesapGecisi|hesapDeposu|desktopSession)\.ts)",
        "arayuz-02-giris-hesap",
    ),
    (
        r"^apps/ui/src/(screens/SettingsScreen\.tsx|components/domain/(DilSecimKarti|BackupPassphraseDialog|DevicePairingGuide|SystemInfoPanel|GatewayStatusPanel|RecoveryCodeBanner|KayitDbBandi|VeriKokuAgBandi|MobileUpdateBanner|MobileUpdateGate|SurumFarkiBanner)\.tsx|services/(pairing|veriTasima|bulutKayit|agTanisi|deviceRegistry|discovery|mobileUpdate|updates)\.ts|hooks/useApkGuncelleme\.ts)",
        "arayuz-03-ayarlar",
    ),
    (
        r"^apps/ui/src/(screens/PatientScreen\.tsx|components/domain/(PatientGate|ObservationNotesModal)\.tsx|utils/(hastaGuncelleme|patientScope|profilSozlugu|aramaNormalize)\.ts)",
        "arayuz-04-hasta",
    ),
    (
        r"^apps/ui/src/(screens/ControlScreen\.tsx|components/domain/(CoilParameterPanel|CoilCard|SurusKipiSecici|EFieldBar|EmDozSatiri)\.tsx|services/(therapyLimits|bobinGorunurlugu)\.ts|utils/(bobinGucu|olculenAlan|yogunlukGosterimi)\.ts)",
        "arayuz-05a-kontrol-kritik",
    ),
    (
        r"^apps/ui/src/(screens/(DashboardScreen|SensorMonitorScreen|DemaSimulatorScreen)\.tsx|components/domain/(SessionProgressCard|StmUyumBandi)\.tsx|hooks/(useSessionControl|useTeardownGuard|useStmBelirsiz|useDonanimCalisiyor)\.ts|services/emergencyStop\.ts|context/LiveDataContext\.tsx)",
        "arayuz-05b-guvenlik-kritik",
    ),
    (r"^apps/ui/src/screens/AiHubScreen\.tsx$", "arayuz-06a-ai-hub"),
    (
        r"^apps/ui/src/components/domain/(AiProPanel|AiSpecApprovalModal|AiReviewControls|PemfKapisiKutusu|TakipGrafigi)\.tsx$|^apps/ui/src/components/domain/(aipro/|aiProProfilleri\.ts)",
        "arayuz-06b-ai-bilesen",
    ),
    (
        r"^apps/ui/src/utils/(aiDetail|aiHataDetayi|canliKare|ckdOnKontrol|sesYukleme|gorselSahneSayfalari|kameraKutusu|zoomMerdiveni|sonAnaliz|takipSerisi)\.ts$",
        "arayuz-06c-ai-etiket",
    ),
    (
        r"^apps/ui/src/(screens/(TreatmentHistoryScreen|AiHistoryScreen|KpiDashboardScreen)\.tsx|components/domain/SessionDetailModal\.tsx|utils/(kpiGrafik|uptime)\.ts|services/(dosyaIndir|topluSilme)\.ts)",
        "arayuz-07-rapor-gecmis-kpi",
    ),
    (
        r"^apps/ui/src/(services/jetonBakiye\.ts|config/(entitlement|access|firma)\.ts|context/EntitlementContext\.tsx)",
        "arayuz-08-jeton",
    ),
    (r"^apps/ui/", "arayuz-09-yardimci"),
    (r"^apps/backend/servers/api_server\.py$", "sunucu-10b-api-server"),
    (
        r"^apps/backend/servers/(ai_router|ai_pro_hedef|ai_client)\.py$|^apps/backend/utils/(image_domain|klinik_asgari|ses_kalitesi)\.py$",
        "sunucu-10c-ai",
    ),
    (r"^apps/backend/utils/ai_rapor_ogeleri\.py$", "sunucu-10d-ai-rapor"),
    (r"^apps/backend/utils/(pdf_report_generator|seans_durum|data_export)\.py$", "sunucu-10e-pdf"),
    (
        r"^apps/backend/servers/(\w+_router|auth|entitlement|jeton|silme_yetkisi|operator_tokens|ai_approval)\.py$|^apps/backend/utils/ceviri\.py$",
        "sunucu-10a-yonlendirici",
    ),
    (
        r"^apps/backend/(servers/(live_state|seans_alan_kaydi|sensor_kaydedici|firmware_manager|efield_live|coil_run_tracker|session_state)\.py|headless_core\.py|controllers/|utils/(estop_mandali|stm32_\w+|stm_yakma|surum_uyumu|panel_yayin|mqtt_kimlik|mt_duzeltme|akim_olcumu|firmware_yakma_penceresi)\.py)",
        "sunucu-10f-bildirim-ws",
    ),
    (r"^apps/backend/", "sunucu-10g-diger"),
    (r"^launcher/app/ui/", "launcher-11a-ui"),
    (r"^launcher/app/windows/", "launcher-11c-nsis"),
    (r"^launcher/", "launcher-11b-rust"),
    (r"^apps/web/src/(pages/Legal\.tsx|config\.ts)$", "site-12c-yasal"),
    (r"^apps/web/(api/|src/pages/(Pricing|Odeme)\.tsx|src/lib/|src/context/)", "site-12b-ticari"),
    (r"^apps/web/", "site-12a-sayfa"),
    (r"^dema-terapi-simülatörü/", "dema-13"),
]
_GRUP = {g[0]: g for g in GRUPLAR}


def grup_bul(dosya: str) -> str:
    for desen, grup in KURALLAR:
        if re.search(desen, dosya):
            return grup
    raise SystemExit(f"grup kuralı yok: {dosya}")


def defter_oku(kok: Path) -> dict:
    p = kok / DEFTER
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def defter_yaz(kok: Path, d: dict) -> None:
    gruplar = d.get("gruplar", [])
    for g in gruplar:
        dosyalar = [k for k, v in d["dosyalar"].items() if v["grup"] == g["ad"]]
        g["dosyaSayisi"] = len(dosyalar)
        g["metin"] = sum(d["dosyalar"][k].get("metin", 0) for k in dosyalar)
        durumlar = {d["dosyalar"][k]["durum"] for k in dosyalar}
        g["durum"] = "tamam" if durumlar <= {"tamam", "muaf"} else "bekliyor"
    d["dosyalar"] = dict(sorted(d["dosyalar"].items(), key=lambda kv: (_GRUP[kv[1]["grup"]][1], kv[1]["grup"], kv[0])))
    (kok / DEFTER).parent.mkdir(parents=True, exist_ok=True)
    (kok / DEFTER).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def uret(kok: Path, taban_yolu: Path) -> dict:
    eski = defter_oku(kok)
    taban = json.loads(taban_yolu.read_text(encoding="utf-8")) if taban_yolu.exists() else {"metinler": []}
    say = Counter(m["dosya"] for m in taban["metinler"])
    dosyalar = {}
    for y in ortak.YUZEYLER:
        for f in ortak.yuzey_dosyalari(y, kok):
            g = grup_bul(f)
            onceki = eski.get("dosyalar", {}).get(f, {})
            kayit = {
                "yuzey": y,
                "grup": g,
                "sira": _GRUP[g][1],
                "durum": onceki.get("durum", "bekliyor"),
                "metin": say.get(f, 0),
                "kritik": _GRUP[g][2],
                "muaf": onceki.get("muaf", []),
                "birlesikIstisna": onceki.get("birlesikIstisna", []),
                "not": onceki.get("not", ""),
            }
            dosyalar[f] = kayit
    d = {
        "aciklama": eski.get("aciklama")
        or "I18N KAPSAM DEFTERİ — göçün TEK GERÇEĞİ (T15). Araç: scripts/i18n/kapsam.py. Durum: bekliyor | tamam | muaf. Parti grubu "
        "bitirince grubun ve dosyalarının durumunu AYNI commit'te `tamam` yapar. K-2 tamam dosyada sabit metin bırakmaz.",
        "surum": 1,
        "k2Kapsam": eski.get("k2Kapsam", "tamam-dosyalar"),
        "genelMuaf": eski.get("genelMuaf", []),
        "gruplar": [
            {"ad": g, "sira": s, "kritik": k, "aciklama": a, "durum": "bekliyor", "metin": 0, "dosyaSayisi": 0}
            for g, s, k, a in GRUPLAR
        ],
        "dosyalar": dosyalar,
    }
    defter_yaz(kok, d)
    return d


def durum_tablosu(d: dict) -> str:
    satir = [f"{'sıra':>4} {'grup':30} {'durum':9} {'metin':>6} {'dosya':>5} kritik"]
    sirada = None
    for g in d["gruplar"]:
        satir.append(
            f"{g['sira']:>4} {g['ad']:30} {g['durum']:9} {g['metin']:>6} {g['dosyaSayisi']:>5} {'EVET' if g['kritik'] else ''}"
        )
        if sirada is None and g["durum"] != "tamam" and g["dosyaSayisi"]:
            sirada = g["ad"]
    satir.append(f"SIRADAKİ GRUP: {sirada or '— (göç tamam)'}")
    return "\n".join(satir)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="I18N kapsam defteri")
    ap.add_argument("--kok")
    alt = ap.add_subparsers(dest="komut", required=True)
    u = alt.add_parser("uret")
    u.add_argument("--taban", default=str(VARSAYILAN_TABAN))
    alt.add_parser("durum")
    i = alt.add_parser("isaretle")
    i.add_argument("grup")
    i.add_argument("durum", choices=["tamam", "bekliyor"])
    f = alt.add_parser("dosya")
    f.add_argument("yol")
    f.add_argument("durum", choices=["tamam", "bekliyor", "muaf"])
    f.add_argument("--gerekce", default="")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    if a.komut == "uret":
        d = uret(kok, Path(a.taban))
        print(durum_tablosu(d))
        return 0
    d = defter_oku(kok)
    if a.komut == "durum":
        print(durum_tablosu(d))
        return 0
    if a.komut == "isaretle":
        if a.grup not in _GRUP:
            raise SystemExit(f"bilinmeyen grup: {a.grup}")
        for k, v in d["dosyalar"].items():
            if v["grup"] == a.grup and v["durum"] != "muaf":
                v["durum"] = a.durum
    if a.komut == "dosya":
        v = d["dosyalar"].get(a.yol)
        if not v:
            raise SystemExit(f"defterde yok: {a.yol} (önce `kapsam.py uret`)")
        if a.durum == "muaf" and not a.gerekce.strip():
            raise SystemExit("muaf dosya GEREKÇE ister (--gerekce)")
        v["durum"] = a.durum
        if a.gerekce:
            v["not"] = a.gerekce
    defter_yaz(kok, d)
    print(durum_tablosu(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
