# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KVKK METNİ İLE YAZILIM AYNI ŞEYİ SÖYLÜYOR MU (2026-08-09 denetimi, Tier 3).

ARIZA: KVKK Aydınlatma Metni'nde **yurt dışına aktarım başlığı yoktu**. Oysa hesap verileri
(Supabase Auth) ve cihaz kayıt defteri (60 sn'de bir heartbeat) fiilen yurt dışındaki bir
işleyiciye gidiyor, site de yurt dışında barındırılıyor. Aktarımın varlığını söylemeyen bir
aydınlatma metni, ilgili kişiyi KVKK m.11'de tanınan "aktarıldığı üçüncü kişileri bilme"
hakkından yoksun bırakır.

⚠️ Bu dosya HUKUKİ NİTELEME YAPMAZ. Yaptığı tek şey, metindeki **ölçülebilir** iddiaların
koddaki davranışla uyuşup uyuşmadığını sınamaktır. Hukuki metin ile yazılım ayrışırsa ikisinden
biri yanlıştır — ve hangi yönde ayrıştığı burada görünür.

Kilitlenen iddialar:
  1) "Hasta ve seans kayıtları yurt dışına aktarılmaz … varsayılan olarak kapalı"
     → `PEMF_CLOUD_PATIENT_SYNC` varsayılanı KAPALI olmalı.
  2) Metinde sayılan cihaz-kayıt alanları, gerçekten gönderilen alan kümesiyle örtüşmeli
     (yeni bir alan eklenip metne yazılmazsa, aydınlatma eksik kalır).
     D2.06: gönderilen küme AST ile çıkarılır (girintiden bağımsız; `_surum_alanlari` ve RPC `p_secret` dahil),
     eşlemesi olmayan YENİ alan doğrudan KIRMIZI.
  3) D2.06 (A-38): §6 Saklama Süresi maddeleri yazılımın DEVREDEKİ varsayılanlarını söyler (sensör, doz, olay,
     maskeleme, anonimleştirme); madde/süre yoksa FAIL. Maskeleme opt-in anlatılır, geçmiş PII maskesi varsayılan KAPALI.
"""

import ast
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
LEGAL = KOK / "apps/web" / "src" / "pages" / "Legal.tsx"


@pytest.fixture(scope="module")
def metin():
    if not LEGAL.exists():
        pytest.skip("apps/web kaynagi yok")
    return LEGAL.read_text(encoding="utf-8")


# ── metin gerçekten aktarımı anlatıyor mu ───────────────────────────────────


def test_KRITIK_yurt_disina_aktarim_basligi_VAR(metin):
    assert "Yurt Dışına Aktarım" in metin, (
        "KVKK metninde yurt disina aktarim basligi YOK — fiili aktarim beyan edilmiyor"
    )


def test_aktarim_ALICILARI_adlandirilir(metin):
    bolum = metin.split("Yurt Dışına Aktarım", 1)[1].split("<H2>6.", 1)[0]
    for alici in ("Supabase", "Vercel", "iyzico"):
        assert alici in bolum, f"aktarim bolumunde alici '{alici}' adlandirilmamis"


def test_m9_dayanagi_ANILIR(metin):
    assert "m.9" in metin.split("Yurt Dışına Aktarım", 1)[1][:2000], "aktarim bolumu KVKK m.9'a atif yapmiyor"


# ── metin ile kod aynı şeyi mi söylüyor ─────────────────────────────────────


def test_KRITIK_hasta_bulut_syncı_GERCEKTEN_kapali():
    """Metin "hasta ve seans kayıtları yurt dışına aktarılmaz … varsayılan kapalı" diyor.
    Varsayılan bir gün açılırsa metin YANLIŞ BEYAN hâline gelir."""
    src = (KOK / "apps" / "backend" / "servers" / "sync_worker.py").read_text(encoding="utf-8")
    m = re.search(
        r'patient_sync_enabled\s*=\s*os\.environ\.get\(\s*"PEMF_CLOUD_PATIENT_SYNC"\s*,\s*"([^"]*)"\s*\)\s*==\s*"1"',
        src,
    )
    assert m, "PEMF_CLOUD_PATIENT_SYNC varsayilani okunamadi (kod degismis olabilir)"
    assert m.group(1) != "1", (
        "hasta/seans bulut sync'i VARSAYILAN ACIK olmus — KVKK metni 'aktarilmaz' diyor, "
        "yazilim aktariyor. Ikisinden biri duzeltilmeli."
    )


def test_KRITIK_hasta_syncı_KAPALIYKEN_RPC_YOLUNA_GIRILMEZ(monkeypatch):
    """Davranışsal kanıt (kaynak-metin değil): senkron döngüsünün bir turu koşturulur ve
    hasta/seans gönderme yollarına HİÇ girilmediği doğrulanır. Cihaz kayıt defteri yayını ise
    beklenen davranıştır — metin onu zaten beyan ediyor."""
    monkeypatch.delenv("PEMF_CLOUD_PATIENT_SYNC", raising=False)
    from servers import sync_worker

    w = sync_worker.CloudSyncWorker(supabase_url="", supabase_key="", interval_sec=1)
    assert w.patient_sync_enabled is False, "bayrak varsayilan ACIK"

    girilen = []
    monkeypatch.setattr(w, "_ensure_client", lambda: True)
    monkeypatch.setattr(w, "_publish_device_registry", lambda: (girilen.append("device"), w.stop_event.set(), True)[-1])
    monkeypatch.setattr(w, "_sync_patients", lambda *a: girilen.append("patients"))
    monkeypatch.setattr(w, "_sync_sessions", lambda *a: girilen.append("sessions"))
    # DB açılışları döngünün başında; gerçek dosyaya dokunmasın.
    monkeypatch.setattr(sync_worker, "get_patient_database", lambda *a, **k: object())
    monkeypatch.setattr(sync_worker, "get_treatment_db", lambda *a, **k: object())

    w._sync_loop()
    assert "patients" not in girilen and "sessions" not in girilen, (
        f"hasta/seans yoluna GIRILDI: {girilen} — KVKK metni 'aktarilmaz' diyor"
    )
    assert "device" in girilen, "cihaz kayit defteri yayini da durmus (uzaktan erisim kirilir)"


def test_bayrak_ACILINCA_hasta_yolu_calisir(monkeypatch):
    """Karşı-kanıt: test "hiç çağrılmıyor"u bayrak yüzünden mi yoksa yol ölü olduğu için mi
    görüyor? Bayrağı açınca yola girilmeli — yoksa üstteki test boş güvence olurdu."""
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    from servers import sync_worker

    w = sync_worker.CloudSyncWorker(supabase_url="", supabase_key="", interval_sec=1)
    girilen = []
    monkeypatch.setattr(w, "_ensure_client", lambda: True)
    monkeypatch.setattr(w, "_publish_device_registry", lambda: True)
    monkeypatch.setattr(w, "_sync_patients", lambda *a: (girilen.append("patients"), w.stop_event.set()))
    monkeypatch.setattr(w, "_sync_sessions", lambda *a: girilen.append("sessions"))
    monkeypatch.setattr(sync_worker, "get_patient_database", lambda *a, **k: object())
    monkeypatch.setattr(sync_worker, "get_treatment_db", lambda *a, **k: object())

    w._sync_loop()
    assert "patients" in girilen, "bayrak acikken bile hasta yoluna girilmedi — test bos guvence"


# ── D2.06 (B-10.137 · B-10.138 · A-38): gönderilen alan kümesi ve saklama süreleri KODDAN türetilir ─────────────────────
# Eski iki kapı kördü (ölçüldü — 9 mutantın 9'unda yeşil): cihaz alanları 16 boşluk girintiye bağlı bir düzenli ifadeyle
# toplanıp yalnız ÖNCEDEN bilinen anahtarlara bakılıyordu (yeni bir anahtar ya da `_surum_alanlari`na eklenen alan görünmüyordu);
# saklama kapısı metinde "365" yoksa ATLANIYOR, varsa `apps/backend/database/` içinde herhangi bir "365" geçmesini yeterli sayıyordu.
# Şimdi: (a) `_publish_device_registry` içindeki HER sözlük anahtarı (RPC `p_` öneki soyulur) + `**_surum_alanlari()`nın ürettiği HER
# anahtar AST ile çıkarılır; her biri metindeki karşılığa eşlenmeli, eşlemesi olmayan YENİ alan doğrudan KIRMIZI. (b) Devrede olan
# saklama varsayılanları (headless bakımın `_retain_days(...)` çağrıları, ayar ucunun `_PII_VARSAYILAN_GUN`'ü, günlük bakımın
# anonimleştirme eşiği) AST ile okunur ve §6'daki `data-saklama` maddelerinde aynı sayı aranır; madde/süre yoksa SKIP değil FAIL.
# (c) Geçmiş PII maskesi (`PEMF_MASK_HISTORY_PII`) varsayılanı KAPALI pinlenir — metin maskelemeyi "opt-in" anlatır (Ö.4: varsayılan-açık
# maske GERİ EKLENMEZ).

_SYNC = KOK / "apps" / "backend" / "servers" / "sync_worker.py"
_HEADLESS = KOK / "apps" / "backend" / "services" / "headless_db_maintenance.py"
_ROUTER = KOK / "apps" / "backend" / "servers" / "system_router.py"
_PII = KOK / "apps" / "backend" / "database" / "thdb_pii.py"
_API = KOK / "apps" / "backend" / "servers" / "api_server.py"
_KVKK = KOK / "apps" / "backend" / "services" / "kvkk_anonimlestirme.py"

#: Gönderilen alan → metinde geçmesi gereken Türkçe karşılık. YENİ alan eklenince buraya VE metne yazılmadan kapı geçmez.
_CIHAZ_KARSILIK = {
    "device_id": "cihaz kimliği",
    "name": "cihaz kimliği ve adı",
    "tunnel_url": "uzaktan erişim adresi",
    "local_ip": "yerel IP",
    "api_port": "port",
    "pairing_code": "eşleştirme kodu",
    "last_seen": "son görülme",
    "app_version": "yazılım sürüm",
    "launcher_version": "yazılım sürüm",
    "base_sha": "yazılım sürüm",
    "at_rest_encrypted": "şifreleme",
    "secret": "doğrulama anahtarı",
}


def _fonksiyon(agac, ad):
    bulunan = [n for n in ast.walk(agac) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == ad]
    assert len(bulunan) == 1, f"{ad} kaynakta {len(bulunan)} kez bulundu (kod değişmiş — kapı kör kalmasın)"
    return bulunan[0]


def _surum_anahtarlari(agac) -> set:
    """`_surum_alanlari`: `out["x"] = …` ve `for anahtar, env in (("x", "ENV"), …): out[anahtar] = …` anahtarları."""
    fn = _fonksiyon(agac, "_surum_alanlari")
    dongu_degerleri: dict = {}
    for d in ast.walk(fn):
        if isinstance(d, ast.For) and isinstance(d.target, ast.Tuple) and isinstance(d.iter, (ast.Tuple, ast.List)):
            for i, hedef in enumerate(d.target.elts):
                if isinstance(hedef, ast.Name):
                    dongu_degerleri.setdefault(hedef.id, set()).update(
                        e.elts[i].value
                        for e in d.iter.elts
                        if isinstance(e, ast.Tuple) and isinstance(e.elts[i], ast.Constant)
                    )
    anahtarlar = set()
    for d in ast.walk(fn):
        if isinstance(d, ast.Assign):
            for t in d.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "out":
                    if isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str):
                        anahtarlar.add(t.slice.value)
                    elif isinstance(t.slice, ast.Name):
                        anahtarlar |= dongu_degerleri.get(t.slice.id, set())
    return anahtarlar


def _gonderilen_cihaz_alanlari() -> set:
    agac = ast.parse(_SYNC.read_text(encoding="utf-8"))
    fn = _fonksiyon(agac, "_publish_device_registry")
    alanlar, surum_acilir = set(), False
    for d in ast.walk(fn):
        if isinstance(d, ast.Dict):
            for k, v in zip(d.keys, d.values):
                if k is None:  # **ifade
                    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "_surum_alanlari":
                        surum_acilir = True
                    continue
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    alanlar.add(k.value[2:] if k.value.startswith("p_") else k.value)
    assert surum_acilir, "araç: yükte `**_surum_alanlari()` bulunamadı (kod değişmiş)"
    alanlar |= _surum_anahtarlari(agac)
    return alanlar


def _cihaz_maddesi(metin: str) -> str:
    bolum = metin.split("Yurt Dışına Aktarım", 1)[1].split("<H2>6.", 1)[0]
    maddeler = [m for m in re.findall(r"<li>(.*?)</li>", bolum, re.S) if "Cihaz kayıt defteri verileri" in m]
    assert len(maddeler) == 1, "metinde tek bir 'Cihaz kayıt defteri verileri' maddesi olmalı"
    return re.sub(r"\s+", " ", maddeler[0])


def test_KRITIK_gonderilen_HER_cihaz_alani_metinde_KARSILIGINI_bulur(metin):
    """MUTASYON: yüke yeni anahtar (`"mac_adresi": …`) ya da `_surum_alanlari`na yeni alan (farklı girintide) → KIRMIZI."""
    gonderilen = _gonderilen_cihaz_alanlari()
    assert {"device_id", "pairing_code", "app_version", "secret"} <= gonderilen, f"araç kör: {sorted(gonderilen)}"
    eslemesiz = sorted(gonderilen - set(_CIHAZ_KARSILIK))
    assert not eslemesiz, (
        f"buluta gönderilen YENİ cihaz alanı/alanları: {eslemesiz} — aydınlatma metnine (§5.1 'Cihaz kayıt defteri verileri') "
        "yazılmadan ve bu kapının eşlemesine eklenmeden geçemez (A-38: metin fiili işlemeyi anlatır)"
    )
    madde = _cihaz_maddesi(metin).lower()
    eksik = sorted(a for a in gonderilen if _CIHAZ_KARSILIK[a].lower() not in madde)
    assert not eksik, f"gönderilen ama metinde anlatılmayan cihaz alan(lar)ı: {eksik}"


def _retain_varsayilanlari() -> dict:
    """Headless bakımın `_retain_days("PEMF_RETAIN_X_DAYS", N)` çağrıları → {ENV: N} (üretimdeki asıl silici)."""
    agac = ast.parse(_HEADLESS.read_text(encoding="utf-8"))
    sonuc = {}
    for d in ast.walk(_fonksiyon(agac, "_run_maintenance")):
        if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "_retain_days" and len(d.args) == 2:
            ad, varsayilan = d.args
            if isinstance(ad, ast.Constant) and isinstance(varsayilan, ast.Constant):
                sonuc[ad.value] = int(varsayilan.value)
    return sonuc


def _modul_sabiti(yol, ad):
    for d in ast.parse(yol.read_text(encoding="utf-8")).body:
        if isinstance(d, ast.Assign) and any(isinstance(t, ast.Name) and t.id == ad for t in d.targets):
            return d.value.value
    raise AssertionError(f"{yol.name}: {ad} bulunamadı (kod değişmiş)")


def _anonimlestirme_esigi() -> int:
    """Üretimdeki anonimleştirme eşiği: D2.54'ten beri günlük bakım `services.kvkk_anonimlestirme.tur`u çağırır, eşik o modülün
    `ESIK_GUN`ü. Günlük döngüde sabit eşikli eski `anonymize_inactive_patients(<gün>)` çağrısı KALMAMALI (iki eşik = metin birine yanlış)."""
    esik = int(_modul_sabiti(_KVKK, "ESIK_GUN"))
    api = ast.parse(_API.read_text(encoding="utf-8"))
    sabit = {
        int(d.args[0].value)
        for d in ast.walk(api)
        if isinstance(d, ast.Call)
        and getattr(d.func, "attr", "") == "anonymize_inactive_patients"
        and d.args
        and isinstance(d.args[0], ast.Constant)
    }
    assert not sabit, f"günlük döngüde sabit eşikli eski anonimleştirme çağrısı var: {sabit}"
    dongu = _fonksiyon(api, "_daily_maintenance_loop")
    assert any(
        isinstance(d, ast.ImportFrom) and any(a.name == "kvkk_anonimlestirme" for a in d.names) for d in ast.walk(dongu)
    ), "günlük bakım döngüsü services.kvkk_anonimlestirme'yi çağırmıyor (araç: üretimdeki eşik okunamaz)"
    return esik


def test_KRITIK_A06_anonimlestirme_ONAYLI_anlatilir(metin):
    """D2.54 · A-06: anonimleştirme operatör onayına bağlı — §6 'anonim' maddesi bunu söylemeli. MUTASYON: metinden onay düşer → KIRMIZI."""
    madde = _saklama_maddeleri(metin)["anonim"]
    assert "onay" in madde, f"§6 'anonim' maddesi klinik onayını söylemiyor: {madde!r}"


def _saklama_maddeleri(metin: str) -> dict:
    bolum = metin.split("<H2>6. Saklama Süresi</H2>", 1)[1].split("<H2>7.", 1)[0]
    return {k: re.sub(r"\s+", " ", v) for k, v in re.findall(r'<li data-saklama="(\w+)">(.*?)</li>', bolum, re.S)}


def test_KRITIK_saklama_sureleri_metinde_DEVREDEKI_kod_varsayilanlariyla_AYNI(metin):
    """MUTASYON: headless varsayılanlarından biri (sensör / doz / olay / PII) ya da anonimleştirme eşiği değişir → KIRMIZI.
    Metinde madde ya da süre yoksa ATLANMAZ — FAIL."""
    v = _retain_varsayilanlari()
    beklenen = {
        "sensor": v["PEMF_RETAIN_SENSOR_DAYS"],
        "doz": v["PEMF_RETAIN_DOSE_DAYS"],
        "olay": v["PEMF_RETAIN_EVENT_DAYS"],
        "maskeleme": v["PEMF_RETAIN_PII_DAYS"],
        "anonim": _anonimlestirme_esigi(),
    }
    maddeler = _saklama_maddeleri(metin)
    eksik = sorted(set(beklenen) - set(maddeler))
    assert not eksik, f"§6 Saklama Süresi'nde madde YOK: {eksik} (yazılım bu süreleri uyguluyor — A-38)"
    for anahtar, gun in beklenen.items():
        assert f"{gun} gün" in maddeler[anahtar], (
            f"§6 '{anahtar}' maddesi kodun uyguladığı {gun} günü söylemiyor: {maddeler[anahtar]!r}"
        )


def test_KRITIK_A07_kritik_olaylar_SURESIZ_anlatilir(metin):
    """D2.50 · A-07: yazılım kritik seans olaylarını (`KRITIK_OLAY_TURLERI` — ACİL DURDUR dahil) süresiz saklıyorsa §6 'olay' maddesi
    bunu SÖYLEMELİ (A-38). MUTASYON: kod kritik listeyi boşaltır ya da metin 'SÜRESİZ'i düşürür → KIRMIZI."""
    agac = ast.parse((KOK / "apps" / "backend" / "database" / "thdb_seans.py").read_text(encoding="utf-8"))
    turler = [
        tuple(e.value for e in d.value.elts)
        for d in ast.walk(agac)
        if isinstance(d, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "KRITIK_OLAY_TURLERI" for t in d.targets)
        and isinstance(d.value, (ast.Tuple, ast.List))
    ]
    assert len(turler) == 1 and "emergency_stop" in turler[0], (
        f"kritik olay listesi okunamadı / ACİL DURDUR yok: {turler}"
    )
    madde = _saklama_maddeleri(metin)["olay"]
    assert "SÜRESİZ" in madde and "Acil durdurma" in madde, (
        f"§6 'olay' maddesi kritik olayların süresiz olduğunu söylemiyor: {madde!r}"
    )


def test_KRITIK_maskeleme_suresi_ayar_ucu_ve_bakimda_AYNI():
    """Ayarlar ekranının gösterdiği varsayılan (`_PII_VARSAYILAN_GUN`) ile bakımın uyguladığı aynı olmalı — biri değişirse metin
    ikisinden birine göre yanlış olur. MUTASYON: `_PII_VARSAYILAN_GUN = 180` → KIRMIZI."""
    assert int(_modul_sabiti(_ROUTER, "_PII_VARSAYILAN_GUN")) == _retain_varsayilanlari()["PEMF_RETAIN_PII_DAYS"]


def test_KRITIK_A09_maskeleme_onayi_SUREYE_bagli_anlatilir(metin):
    """D2.55 · A-09: onay yalnız verildiği süreye geçerli; süre değişince yeniden sorulur. Metin bunu söylemeli ve kod onayı süreyle
    sormalı (`pii_onayi_var_mi(gun)`) — biri geri dönerse KIRMIZI. Davranış kapısı: tests/test_pii_onayi_SUREYE_ve_KAPSAMA_bagli_A09_D255.py"""
    madde = _saklama_maddeleri(metin)["maskeleme"]
    assert "yeniden onay" in madde and "süre değiştirilirse" in madde, (
        f"maskeleme maddesi A-09 yeniden onayını anlatmıyor: {madde!r}"
    )
    fn = _fonksiyon(ast.parse(_PII.read_text(encoding="utf-8")), "pii_onayi_var_mi")
    assert [a.arg for a in fn.args.args] == ["self", "gun"], (
        "kod onayı süreden bağımsız soruyor — metin A-09 için yanlış olur"
    )


def test_KRITIK_maskeleme_OPT_IN_anlatilir_ve_gecmis_PII_maskesi_VARSAYILAN_KAPALI(metin):
    """Ö.4 / sahip kararı (bellek `pemf-history-pii-mask-opt-in`): maskeleme varsayılan KAPALI ve klinik ONAYI olmadan başlamaz.
    Metin bunu söylemeli; `_redact_pii`'nin `PEMF_MASK_HISTORY_PII` varsayılanı "0" kalmalı. MUTASYON: varsayılan "1" → KIRMIZI."""
    madde = _saklama_maddeleri(metin)["maskeleme"]
    assert "varsayılan olarak KAPALI" in madde and "onay" in madde, f"maskeleme maddesi opt-in'i anlatmıyor: {madde!r}"
    fn = _fonksiyon(ast.parse(_PII.read_text(encoding="utf-8")), "_redact_pii")
    varsayilanlar = [
        d.args[1].value
        for d in ast.walk(fn)
        if isinstance(d, ast.Call)
        and getattr(d.func, "attr", "") == "getenv"
        and d.args
        and isinstance(d.args[0], ast.Constant)
        and d.args[0].value == "PEMF_MASK_HISTORY_PII"
    ]
    assert varsayilanlar == ["0"], f"PEMF_MASK_HISTORY_PII varsayılanı KAPALI ('0') değil: {varsayilanlar}"
