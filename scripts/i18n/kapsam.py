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
  ..\\python.exe scripts\\i18n\\kapsam.py metin-tarayan          # i18n/metin-tarayan-testler.txt'i yeniden üretir

Muaf metin (dosya `muaf` listesi · `genelMuaf` birebir · `genelMuafDesen` düzenli ifade) tek yerde: `muaf_mi` (K-2 + `katalog.py taban`).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.i18n import ortak  # noqa: E402

DEFTER = "i18n/kapsam.json"
VARSAYILAN_TABAN = ortak.varsayilan_taban()

#: (grup, sıra, kritik, açıklama) — sıra istemdeki T15 sırasıdır; çok dosyalı büyük gruplar alt harfle ~80–200 metne bölünür. TEK DOSYALI
#: büyük gruplar (AiHubScreen ~770, launcher index.html ~420, Legal.tsx ~250, aiDetail ~220) bölünemez → KURALLAR §Büyük dosya: bölüm bölüm,
#: birden çok commit, dosya EN SONDA `tamam`. Küçük gruplar (jeton, yardımcı, NSIS) bir partide komşusuyla birlikte biter.
GRUPLAR = [
    (
        "arayuz-01-ortak-kabuk",
        1,
        False,
        "ortak bileşenler + kabuk (AppShell, bildirim, toast, hata sınırı, sayfa başlıkları, tema)",
    ),
    ("arayuz-02-giris-hesap", 2, False, "giriş / hesap / operatör (+ Supabase dönüş sayfaları)"),
    ("arayuz-03a-ayarlar-ekran", 3, False, "Ayarlar ekranı (SettingsScreen) + dil kartı"),
    (
        "arayuz-03b-ayarlar-bilesen",
        3,
        False,
        "eşleştirme, yedek parolası, sistem bilgisi, ağ geçidi, güncelleme bantları",
    ),
    ("arayuz-04-hasta", 4, False, "hasta ekranı, hasta kapısı, gözlem notu, profil sözlüğü"),
    ("arayuz-05a-kontrol-kritik", 5, True, "kontrol / bobin parametreleri / sürüş kipi / doz göstergeleri (KRİTİK)"),
    (
        "arayuz-05b-guvenlik-kritik",
        5,
        True,
        "ACİL DURDUR, mandal bandı, seans ilerleme, söküm koruması, ana ekran (KRİTİK)",
    ),
    ("arayuz-06a-ai-hub", 6, False, "AiHubScreen (TEK dosya ~770 metin — KURALLAR §Büyük dosya)"),
    ("arayuz-06b-ai-bilesen", 6, False, "AI Pro paneli, hedef / model seçimi, onay / değerlendirme"),
    ("arayuz-06c-ai-etiket", 6, False, "AI sonuç etiketleri (aiDetail — K-7 sunucu eşliği) + AI yardımcıları"),
    ("arayuz-07a-seans-gecmisi", 7, False, "seans geçmişi, seans ayrıntısı, indirme"),
    ("arayuz-07b-ai-gecmisi-kpi", 7, False, "AI geçmişi, KPI panosu"),
    ("arayuz-08-jeton", 8, False, "jeton / abonelik / erişim"),
    ("arayuz-09-yardimci", 9, False, "kalan servis / yardımcı / tür dosyaları"),
    (
        "sunucu-10a-yonlendirici",
        10,
        False,
        "yönlendirici hata iletileri (hasta, geçmiş, seans, kimlik, sistem, güncelleme, jeton)",
    ),
    ("sunucu-10b-ana-sunucu", 10, True, "api_server.py — donanım / seans / ACİL DURDUR iletileri (KRİTİK)"),
    ("sunucu-10c-ai", 10, False, "AI yönlendirici + AI Pro hedef + görüntü alanı iletileri"),
    ("sunucu-10d-ai-rapor", 10, False, "AI rapor öğeleri (ETIKETLER / DEGERLER / BELIRTILER — K-7)"),
    ("sunucu-10e-pdf", 10, False, "PDF raporu, seans durum etiketleri, dışa aktarma"),
    ("sunucu-10f-bildirim-ws", 10, True, "bildirim / WS / STM / firmware / mandal iletileri (KRİTİK)"),
    (
        "sunucu-10g-veritabani",
        10,
        False,
        "veritabanı / şema / yedek / KVKK iletileri (çoğu muaf: iç / günlük / DB değeri)",
    ),
    ("sunucu-10h-servis", 10, False, "servisler, güncelleme, sırlar, kalan yardımcılar (çoğu muaf: iç / günlük)"),
    ("launcher-11a-ui", 11, False, "launcher arayüzü (index.html TEK dosya — mevcut TR/EN sözlüğü kataloğa)"),
    ("launcher-11b-rust-uygulama", 11, False, "launcher Rust iletileri — uygulama (launcher/app/src)"),
    ("launcher-11c-rust-cekirdek", 11, False, "launcher Rust iletileri — çekirdek (launcher/core)"),
    ("launcher-11d-nsis", 11, True, "kurulum sihirbazı iletileri (hooks.nsi — LangString)"),
    ("site-12a-sayfa", 12, False, "site üst menü / alt bilgi / ana sayfa / özellikler / destek / hata sayfaları"),
    (
        "site-12b-indirme-hesap",
        12,
        False,
        "indirme sayfası ve düğmeleri, paket oluşturucu, hesap / giriş / parola sıfırlama",
    ),
    (
        "site-12c-icerik",
        12,
        False,
        "site içerik yapılandırması (config.ts: marka, planlar, özellikler, SSS, menü — modül düzeyi)",
    ),
    ("site-12d-ticari", 12, False, "fiyatlar, ödeme, site işlevleri (api — makine-okur kod → istemcide çeviri)"),
    ("site-12e-yasal", 12, False, "YASAL metinler (EN SON; 'Türkçe metin bağlayıcıdır' notu, hukuki onay sahipte)"),
    ("dema-13", 13, False, "DEMA simülatörü"),
]

_VT = r"(thdb_\w+|patient_database|treatment_history_db|auth_db|sqlcipher_util|kvkk_anonimlestirme|backup_recovery|yedek_dosyasi|headless_db_maintenance|encrypted_import|dongu_disi_yazim)"

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
    (r"^apps/ui/src/(screens/SettingsScreen\.tsx|components/domain/DilSecimKarti\.tsx)$", "arayuz-03a-ayarlar-ekran"),
    (
        r"^apps/ui/src/(components/domain/(BackupPassphraseDialog|DevicePairingGuide|SystemInfoPanel|GatewayStatusPanel|RecoveryCodeBanner|KayitDbBandi|VeriKokuAgBandi|MobileUpdateBanner|MobileUpdateGate|SurumFarkiBanner)\.tsx|services/(pairing|veriTasima|bulutKayit|agTanisi|deviceRegistry|discovery|mobileUpdate|updates)\.ts|hooks/useApkGuncelleme\.ts)",
        "arayuz-03b-ayarlar-bilesen",
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
        r"^apps/ui/src/(screens/TreatmentHistoryScreen\.tsx|components/domain/SessionDetailModal\.tsx|services/(dosyaIndir|topluSilme)\.ts)",
        "arayuz-07a-seans-gecmisi",
    ),
    (
        r"^apps/ui/src/(screens/(AiHistoryScreen|KpiDashboardScreen)\.tsx|utils/(kpiGrafik|uptime)\.ts)",
        "arayuz-07b-ai-gecmisi-kpi",
    ),
    (
        r"^apps/ui/src/(services/jetonBakiye\.ts|config/(entitlement|access|firma)\.ts|context/EntitlementContext\.tsx)",
        "arayuz-08-jeton",
    ),
    (r"^apps/ui/", "arayuz-09-yardimci"),
    (r"^apps/backend/servers/api_server\.py$", "sunucu-10b-ana-sunucu"),
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
    (rf"^apps/backend/(.*/)?{_VT}\.py$", "sunucu-10g-veritabani"),
    (r"^apps/backend/", "sunucu-10h-servis"),
    (r"^launcher/app/ui/", "launcher-11a-ui"),
    (r"^launcher/app/windows/", "launcher-11d-nsis"),
    (r"^launcher/core/", "launcher-11c-rust-cekirdek"),
    (r"^launcher/", "launcher-11b-rust-uygulama"),
    (r"^apps/web/src/pages/Legal\.tsx$", "site-12e-yasal"),
    (r"^apps/web/src/config\.ts$", "site-12c-icerik"),
    (
        r"^apps/web/src/(pages/(Download|ResetPassword|AuthRoute)\.tsx|components/(Download\w*|PackageBuilder|AccountButton)\.tsx|context/(AuthModal|AuthContext)\.tsx|lib/(authHatalari|supabase|download|os|usageStats)\.ts)$",
        "site-12b-indirme-hesap",
    ),
    (r"^apps/web/(api/|src/pages/(Pricing|Odeme)\.tsx|src/lib/)", "site-12d-ticari"),
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
        "genelMuafDesen": eski.get("genelMuafDesen", []),
        "gruplar": [
            {"ad": g, "sira": s, "kritik": k, "aciklama": a, "durum": "bekliyor", "metin": 0, "dosyaSayisi": 0}
            for g, s, k, a in GRUPLAR
        ],
        "dosyalar": dosyalar,
    }
    defter_yaz(kok, d)
    return d


def muaf_mi(defter: dict, dosya: str, metin: str) -> bool:
    """Metin bu dosyada muaf mı: dosyanın `muaf` listesi · `genelMuaf` (birebir; ürün adı, birim, kod belirteci) · `genelMuafDesen`
    (tam eşleşen düzenli ifade; ör. CSS sınıfı). Muaf dosya (`durum: muaf`) bütünüyle muaftır. Tek kaynak: K-2 ve `katalog.py taban`."""
    kayit = defter.get("dosyalar", {}).get(dosya, {})
    if kayit.get("durum") == "muaf":
        return True
    if any(x.get("metin") == metin for x in kayit.get("muaf", [])):
        return True
    if any(x.get("metin") == metin for x in defter.get("genelMuaf", [])):
        return True
    return any(re.fullmatch(x["desen"], metin) for x in defter.get("genelMuafDesen", []))


#: Kaynak METNİ tarayan pytest kapıları: test bir yüzey dosyasını adıyla anıyor VE dosya içeriği okuyor. Parti bir dosyayı taşırken
#: buradan o dosyayı anan testleri bulur ve `tests/i18n_yardimci.py` ile çevirir (zayıflatmadan; her çevrilen kapıya iki mutant).
METIN_TARAYAN = "i18n/metin-tarayan-testler.txt"
_OKUMA = re.compile(r"\.read_text\(|\.read_bytes\(|\bopen\(|\.open\(")


def metin_tarayan_testler(kok: Path) -> list[tuple[str, list[str], bool]]:
    """[(test, [andığı yüzey dosyaları], çevrildi mi)] — çevrildi: `i18n_yardimci` kullanıyor."""
    kaynaklar = sorted({f for y in ortak.YUZEYLER for f in ortak.yuzey_dosyalari(y, kok)})
    ad_sayisi = Counter(f.rsplit("/", 1)[-1] for f in kaynaklar)
    testler = subprocess.run(
        ["git", "-C", str(kok), "-c", "core.quotepath=off", "ls-files", "-z", "tests"], capture_output=True, check=True
    ).stdout.decode("utf-8")
    sonuc = []
    for t in sorted(x for x in testler.split("\0") if x.endswith(".py") and "/test_" in "/" + x):
        metin = (kok / t).read_text(encoding="utf-8", errors="replace").replace("\\", "/")
        if not _OKUMA.search(metin):
            continue
        andigi = []
        for f in kaynaklar:
            parca = f.split("/")
            # tam yol > son iki parça > (yalnız eşsizse) dosya adı — `App.tsx` / `index.html` gibi ortak adlar yanlış eşleşmesin
            if (
                f in metin
                or "/".join(parca[-2:]) in metin
                or (ad_sayisi[parca[-1]] == 1 and re.search(rf"\b{re.escape(parca[-1])}\b", metin))
            ):
                andigi.append(f)
        if andigi:
            sonuc.append((t, andigi, "i18n_yardimci" in metin))
    return sonuc


def metin_tarayan_yaz(kok: Path) -> int:
    satirlar = [
        "# I18N — kaynak METNİ tarayan pytest kapıları (T13). ÜRETİLİR: `python scripts/i18n/kapsam.py metin-tarayan` — elle düzenlemeyin.",
        "# Biçim: <test> [ÇEVRİLDİ]? :: <andığı yüzey dosyaları>. Parti bir dosyayı taşırken: grep \"<dosya yolu>\" i18n/metin-tarayan-testler.txt",
        "# → listelenen her testi `tests/i18n_yardimci.py` ile çevir (KURALLAR §Metin tarayan kapı) — ZAYIFLATMA, SİLME; iki mutant.",
    ]
    liste = metin_tarayan_testler(kok)
    for t, andigi, cevrildi in liste:
        satirlar.append(f"{t}{' [ÇEVRİLDİ]' if cevrildi else ''} :: {' '.join(andigi)}")
    (kok / METIN_TARAYAN).parent.mkdir(parents=True, exist_ok=True)
    (kok / METIN_TARAYAN).write_bytes(("\n".join(satirlar) + "\n").encode("utf-8"))
    return len(liste)


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
    alt.add_parser("metin-tarayan")
    a = ap.parse_args(argv)
    kok = Path(a.kok).resolve() if a.kok else ortak.KOK
    if a.komut == "uret":
        d = uret(kok, Path(a.taban))
        print(durum_tablosu(d))
        return 0
    if a.komut == "metin-tarayan":
        print(f"[OK] {metin_tarayan_yaz(kok)} test → {METIN_TARAYAN}")
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
