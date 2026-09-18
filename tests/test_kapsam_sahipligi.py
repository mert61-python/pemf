# -*- coding: utf-8 -*-
# Author: mertaygn
""" "BENİM / TÜM KLİNİK" KAPSAM SAHİPLİĞİ — sahip bildirimi 2026-09-12.

===============================================================================
NE İSTENDİ
===============================================================================
"klinik ve benim ayrımı düzgün çalışıyor mu incele. sonuçta herkes kendi maili ile
kayıt oluyor ya oraya dikkat edelim."

===============================================================================
DENETİMDE BULUNAN ARIZA
===============================================================================
Arayüzün kuralı: "Benim" = `operator_email` EŞLEŞEN **veya SAHİPSİZ** kayıtlar
(sahipsiz = eski/migrasyon kaydı kaybolmasın). Bu kural, sahiplik GERÇEKTEN yazıldığı
sürece doğrudur.

⚠️ ÖLÇÜLDÜ: otonom seansların DB satırı `operator_email` YAZMADAN açılıyordu
(`api_server.start_ai_session` → `_db.start_session(treatment_mode=mode, target_condition=None)`).
Yani HER AI Pro / AI (Auto) seansı SAHİPSİZ kaydediliyor ve "sahipsiz = benim" kuralı
yüzünden kliniğin HER hekimine "Benim Seanslarım"da görünüyordu. Çok operatörlü bir
klinikte ayrım AI tarafında fiilen YOKTU — sahibin tam olarak dikkat çektiği nokta.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· Manuel seans sahipliği GERÇEKTEN yazılıyor mu (uçtan uca)
· Otonom (AI) seans sahipliği yazılıyor mu — arızanın kendisi
· Sahip SUNUCUDA çözülüyor mu (kanıtsız istemci beyanı sahiplik olmamalı)
· Seans satırı açan HER yol sahiplik taşıyor mu (sınıfın tamamı, tek nokta değil)
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

os.environ.setdefault("PEMF_SIMULATE", "1")

_PF = KOK / "apps" / "ui" / "src"

#: `db.start_session(...)` çağıran üretim dosyaları — seans satırı AÇAN her yol.
#: ⚠️ Yeni bir yol eklenirse bu liste değil, aşağıdaki AST taraması onu kendiliğinden bulur.
SEANS_ACAN_DOSYALAR = ("apps/backend/servers/api_server.py", "apps/backend/servers/session_router.py")


@pytest.fixture
def izole_db(tmp_path, monkeypatch):
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server

    kok = tmp_path / "kapsam_gecmisi"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda: db)
    return db


# ============================================================================
# 1. ⚠️ ASIL KAPI — OTONOM SEANS SAHİPSİZ KALMAZ
# ============================================================================


def test_KRITIK_AI_seansi_SAHIPLI_kaydedilir(izole_db, monkeypatch):
    """MUTASYON: `start_ai_session`daki `operator_email=` argümanını `_db.start_session`
    çağrısından çıkar → KIRMIZI (kayıt sahipsiz olur).

    Sahadaki etki: otonom seanslar kliniğin HER hekimine "Benim Seanslarım"da görünür.
    """
    from servers import api_server

    api_server.start_ai_session(10.0, 25.0, 5, range(1, 3), "AI Pro · Test", operator_email="Hekim@Klinik.COM")
    try:
        seanslar = izole_db.get_session_history(limit=10)
        assert seanslar, "onkosul: AI seansi DB satiri acmadi"
        sahipler = {(s.get("operator_email") or "") for s in seanslar}
        assert "hekim@klinik.com" in sahipler, (
            f"AI seansi SAHIPSIZ kaydedildi: {sahipler} -> 'Benim/Tum Klinik' ayrimi AI tarafinda calismaz"
        )
    finally:
        with api_server._session_lock:
            api_server._active_session["is_active"] = False


def test_KRITIK_sahip_NORMALIZE_edilir(izole_db, monkeypatch):
    """⚠️ Arayüz karşılaştırmayı KÜÇÜK HARFLE yapıyor (`myEmail.toLowerCase()`). DB'ye
    "Hekim@Klinik.COM" yazılırsa eşleşme tutmaz ve hekim KENDİ seansını "Benim
    Seanslarım"da GÖREMEZ — sessiz, tersine bir kayıp.
    """
    from servers import api_server

    api_server.start_ai_session(10.0, 25.0, 5, range(1, 3), "AI · Test", operator_email="  AYNI@X.COM ")
    try:
        sahipler = {(s.get("operator_email") or "") for s in izole_db.get_session_history(limit=10)}
        assert "ayni@x.com" in sahipler, f"sahip normalize edilmedi: {sahipler}"
    finally:
        with api_server._session_lock:
            api_server._active_session["is_active"] = False


def test_bos_sahip_None_yazilir_bos_dizgi_DEGIL(izole_db):
    """Sahip çözülemediğinde kayıt SAHİPSİZ olmalı (eski davranış) — boş dizgi değil,
    çünkü boş dizgi bazı sorgularda "eşleşen sahip" gibi davranabilir."""
    from servers import api_server

    api_server.start_ai_session(10.0, 25.0, 5, range(1, 3), "AI · Test", operator_email="")
    try:
        sahipler = [s.get("operator_email") for s in izole_db.get_session_history(limit=10)]
        assert all(x in (None, "") for x in sahipler), sahipler
    finally:
        with api_server._session_lock:
            api_server._active_session["is_active"] = False


# ============================================================================
# 2. SINIFIN TAMAMI — SEANS AÇAN HER YOL SAHİPLİK TAŞIR
# ============================================================================


def _start_session_cagrilari(bagil: str):
    """`X.start_session(...)` çağrılarını AST'den çıkarır (yorum/metin sayma yok)."""
    agac = ast.parse((KOK / bagil).read_text(encoding="utf-8"))
    for d in ast.walk(agac):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "start_session":
            yield d


def test_KRITIK_seans_satiri_acan_HER_yol_sahiplik_tasiyor():
    """⚠️ ARIZA TEK BİR ÇAĞRIDAYDI ama sınıf üç çağrıyı kapsıyor (manuel / AI / fallback).
    Birini elle düzeltmek, dördüncüsünü bir sonraki geliştiriciye bırakırdı.

    Çıpa AST'ye pinli: yorum metni ya da benzer isimli bir fonksiyon kapıyı kandıramaz.

    MUTASYON: herhangi bir `db.start_session(...)` çağrısından `operator_email=` anahtarını
    sil → KIRMIZI.
    """
    eksik = []
    toplam = 0
    for bagil in SEANS_ACAN_DOSYALAR:
        for cagri in _start_session_cagrilari(bagil):
            toplam += 1
            if not any(kw.arg == "operator_email" for kw in cagri.keywords):
                eksik.append(f"{bagil}:{cagri.lineno}")
    assert toplam >= 3, f"onkosul: beklenenden az start_session cagrisi bulundu ({toplam}) -> capa bayatladi"
    assert not eksik, (
        "Seans satiri acan su cagri(lar) SAHIPLIK yazmiyor -> o seanslar 'sahipsiz' olur ve "
        f"kliniginin HER hekimine 'Benim Seanslarim'da gorunur: {eksik}"
    )


def test_KRITIK_sahip_SUNUCUDA_cozulur_istemci_beyani_DEGIL():
    """⚠️ Kanıtsız bir istemci beyanı sahiplik olarak yazılırsa, "Benim Seanslarım" bir
    kimlik iddiası değil, bir dilek listesi olur (ve denetim izi iftiraya döner —
    bkz. `auth.cozumlenmis_operator` gerekçesi).

    MUTASYON: `cozumlenmis_operator(request, payload.operator_email)` yerine doğrudan
    `payload.operator_email` yaz → KIRMIZI.
    """
    src = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "_operator_kimligi = cozumlenmis_operator(request, payload.operator_email)" in src, (
        "seans sahibi artik SUNUCUDA cozulmuyor -> istemci baskasinin adina seans acabilir"
    )
    assert "operator_email=_operator_kimligi or None" in src, "cozumlenmis kimlik DB'ye yazilmiyor"


def test_KRITIK_AI_PRO_sahibi_ONAY_MUHRUNDEN_gelir():
    """⚠️ Otonom sürüşün sahibi, onu ONAYLAYAN hekimdir (sorumluluğu üstlenen kişi).
    İstemci gövdesinden ayrı bir alan okumak "başkasının adına seans açma"yı mümkün kılardı;
    organ/süre/model zaten aynı gerekçeyle mühürden okunuyor.

    MUTASYON: `operator_email=str(_onay.get("operator") or "")`i `payload.operator_email`e
    çevir → KIRMIZI (payload'da öyle bir alan bile yok).
    """
    src = (KOK / "apps" / "backend" / "servers" / "ai_router.py").read_text(encoding="utf-8")
    assert 'operator_email=str(_onay.get("operator") or "")' in src, "AI Pro seans sahibi onay muhrunden OKUNMUYOR"


# ============================================================================
# 3. ARAYÜZ — İKİ EKRAN AYNI KURALI UYGULUYOR MU
# ============================================================================


@pytest.mark.skipif(not (_PF / "screens").exists(), reason="apps/ui/ kaynak agaci yok")
def test_KRITIK_kapsam_filtresi_kucuk_harf_KIYASI_yapiyor():
    """⚠️ DB'de sahip küçük harfe normalize ediliyor; arayüz de öyle kıyaslamalı. Biri
    değişirse hekim kendi kayıtlarını GÖREMEZ (sessiz kayıp, hata mesajı yok).
    """
    from c_soyucu import c_soy

    # ⚠️ ÇIPA GERÇEK KIYASA PİNLİ. İlk yazımda yalnız "toLowerCase()" aranıyordu ve mutasyonla
    # ölçüldü (2026-09-12): sahip kıyası ham bırakılınca kapı YEŞİL kaldı, çünkü o çağrı
    # dosyada BAŞKA yerlerde de (myEmail hesabı) geçiyor. Kapı artık sahiplik okumasının
    # KENDİSİNİ ölçer.
    KIYAS = 'operator_email || "").toLowerCase()'
    for bagil in (
        "screens/TreatmentHistoryScreen.tsx",
        "utils/patientScope.ts",
    ):
        src = c_soy((_PF / bagil).read_text(encoding="utf-8"))
        assert KIYAS in src, f"{bagil}: sahiplik kiyasi kucuk harfe indirilmiyor -> hekim KENDI kaydini goremez"

    # ⚠️ KOPYA KURAL YASAĞI: sahiplik kıyasını KENDİ yazan ekran, `patientScope` ile
    # sessizce ayrışır ve "Benim / Tüm Klinik" ekrandan ekrana FARKLI davranır — sahibin
    # "düzgün çalışıyor mu?" sorusunun tam konusu.
    # ⚠️ Denetimde ÜÇÜNCÜ kopya bulundu (AiHistoryScreen); ilk birleştirme onu atlamıştı.
    # ⚠️ İKİ MEŞRU GEÇİT: `inScope(` doğrudan kullanım, `kapsamda(` ise ANALİZ kayıtlarına
    # özgü adlandırılmış sarmalayıcı (kendisi de `inScope`a devreder — bkz. utils/sonAnaliz.ts).
    # Ayrı ad, `/ai/log` süzgecini hasta süzgecinden ayırt edebilmek için gerekliydi:
    # tek ada pinli kapı, PatientScreen'de HASTA süzmesi yüzünden mutasyonda yeşil kalıyordu.
    for ekran in ("screens/PatientScreen.tsx", "screens/AiHistoryScreen.tsx"):
        src = c_soy((_PF / ekran).read_text(encoding="utf-8"))
        assert KIYAS not in src, f"{ekran} sahiplik kiyasini KENDI yaziyor -> patientScope ile sessizce ayrisir"
        assert ("inScope(" in src) or ("kapsamda(" in src), (
            f"{ekran} tek kaynak kapsam gecidini (inScope/kapsamda) kullanmiyor"
        )


#: `/api/ai/log` ÇAĞIRAN her ekran — uç operatör süzgeci DESTEKLEMEZ.
#: ⚠️ Bu liste denetimde (2026-09-12, ikinci geçiş) doğdu: ev sahibi eklentileri için eklenen
#: İKİ yeni çağrı (`PatientScreen` son-analiz özeti, `AiHubScreen` "kaldığın yerden" şeridi)
#: süzgeci ATLAMIŞTI ve "Benim Hastalarım" kartının altında BAŞKA hekimin analizi görünüyordu.
AI_LOG_CAGIRAN_EKRANLAR = (
    "screens/AiHistoryScreen.tsx",
    "screens/PatientScreen.tsx",
    "screens/AiHubScreen.tsx",
)


@pytest.mark.skipif(not (_PF / "screens").exists(), reason="apps/ui/ kaynak agaci yok")
def test_KRITIK_ai_log_cagiran_HER_ekran_KAPSAM_suzuyor():
    """⚠️ `/api/ai/log` OPERATÖR SÜZGECİ DESTEKLEMEZ — tüm kliniğin analizlerini döndürür.
    Süzmeyen her çağrı, kapsam ayrımını O EKRANDA delen bir sızıntıdır.

    Kapı YAPISALDIR: ucu çağıran bir dosya `inScope(` kullanmıyorsa KIRMIZI. Böylece
    "yeni bir ekran ekledim, süzmeyi unuttum" sessizce geçemez.

    MUTASYON: herhangi bir ekrandan `inScope(` süzgecini kaldır → KIRMIZI.
    """
    from c_soyucu import c_soy

    eksik = []
    for ekran in AI_LOG_CAGIRAN_EKRANLAR:
        src = c_soy((_PF / ekran).read_text(encoding="utf-8"))
        if "/ai/log" not in src:
            eksik.append(f"{ekran}: onkosul kayboldu (/ai/log cagrisi yok) -> capa bayat")
            continue
        # ⚠️ ÇIPA `kapsamda(`YA PİNLİ, `inScope(`E DEĞİL. Mutasyonla ölçüldü (2026-09-12):
        # `PatientScreen` HASTA süzmesi için zaten `inScope` kullanıyor, bu yüzden ANALİZ
        # süzgeci silinse bile kapı YEŞİL kalıyordu. `kapsamda` analiz kayıtlarına özgü,
        # adlandırılmış geçittir (bkz. utils/sonAnaliz.ts).
        if "kapsamda(" not in src:
            eksik.append(f"{ekran}: /ai/log cagiriyor ama KAPSAM SUZMUYOR")
    assert not eksik, "AI analiz gecmisi kapsam sizintisi: " + " | ".join(eksik)


@pytest.mark.skipif(not (_PF / "utils").exists(), reason="apps/ui/ kaynak agaci yok")
def test_KRITIK_EV_SAHIBI_tum_klinige_CIKAMAZ():
    """⚠️ KVKK kapısı (2026-08-08): ev sahibi profili "Tüm Klinik" kapsamına asla çıkamaz —
    sekme gizli olsa bile mantık `patientScope.effectiveScope`te kilitli.

    MUTASYON: `effectiveScope`u `return istenen` yap → KIRMIZI.
    """
    from c_soyucu import c_soy

    src = c_soy((_PF / "utils" / "patientScope.ts").read_text(encoding="utf-8"))
    assert 'return isExpert || isResearcher ? istenen : "mine";' in src, (
        "ev sahibi profili 'Tum Klinik' kapsamina cikabilir hale gelmis (KVKK kapisi)"
    )
