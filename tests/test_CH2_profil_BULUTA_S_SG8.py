# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CH2 · S-SG.8 / Y151 — KAYDIN ARAYÜZ PROFİLİ BULUTA TAŞINIR (seans + hasta / denek), CANLI ŞEMA DEĞİŞMEDEN DE ÇALIŞIR.

ÖLÇÜLEN DURUM (taban `4240d3be`): SG.G1 yerelde `treatment_sessions.profil` ve `patients.profil` kolonlarını ekledi, ama bulut senkronu
(`servers/sync_worker.py`) profili TAŞIMIYORDU: PUSH yükünde `profil` yok, PULL INSERT'inde `profil` yok → buluttan inen kayıt hep profilsiz
iniyor ve türetme kuralıyla (SG G1-2) görünüyordu; araştırma profilinde açılmış bir seans başka cihaza / yeniden kuruluma veteriner diye
dönebilirdi. Bulut şemasında da `profil` kolonu yoktu (S-SG.8 [SAHİBE] → Y151: "yayından önce").

SÖZLEŞME:
  a) Şema DEPOYA yazılır (`apps/backend/database/supabase_profil.sql`), canlıya yayın hazırlığında SAHİPLE uygulanır: EKLEMELİ kolonlar
     (`profil text not null default ''`), RPC İMZALARI AYNI (yükteki `profil` anahtarı = isteğe bağlı parametre; eski imza KIRILMAZ,
     yeni aşırı-yük / PGRST203 YOK), boş gelen profil bulutta dolu değeri EZMEZ, bilinmeyen değer '' olur, `_pemf_verify_device` ve
     `where device_id = p_device_id` korumaları AYNEN, rol başına EXECUTE (public'ten revoke YETMEZ), tek işlem + ön koşul kapısı.
  b) `sync_worker` PUSH / PULL profili taşır ve hem ESKİ (bugünkü canlı: kolon yok, upsert yükteki `profil`i yok sayar, resolve satırında
     anahtar yok) hem YENİ şemayla çalışır: veri kaybı yok, senkron durmaz, günlük seli yok.
  c) PULL: profilli bulut kaydı yerelde O profile yazılır; profilsiz kayıt '' kalır (okumada türetilir — SG G1-2); yerel profil buluttan
     gelen BOŞLA ya da PUSH bekleyen yerel değişiklik bayat bulut değeriyle EZİLMEZ.
  d) Yeni şema uygulanınca, önceden profilsiz gönderilmiş kayıtlar BİR KEZ yeniden gönderilir (geri doldurma) ve yakınsar; eski şemada
     (anahtar yok) yeniden gönderme YOKTUR (yoksa her 60 sn'de sonsuz PUSH seli).
CANLIYA İSTEK YOK: bulut `_SahteBulut` ile taklit edilir (SQL dosyasındaki anlamın Python ikizi).
⚠️ MUTASYON: PUSH'tan `profil` silinirse / PULL boşla ezerse / geri doldurma anahtar varlığına bakmazsa / SQL boş-koruması ya da
normalizasyonu silinirse / `authenticated`a grant verilirse ilgili KRİTİK test KIRMIZI.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils.profil import PROFILLER, seans_profili  # noqa: E402

SQL = KOK / "apps" / "backend" / "database" / "supabase_profil.sql"
GERI_AL = KOK / "apps" / "backend" / "database" / "supabase_profil_geri_al.sql"
README = KOK / "apps" / "backend" / "database" / "README.md"


def _govde(yol: Path) -> str:
    """`--` yorumları soyulmuş, küçük harfli SQL (yorumdaki örnek / geri alma metni kapıyı yanıltmasın)."""
    assert yol.exists(), f"beklenen SQL dosyası yok: {yol.relative_to(KOK)}"
    metin = yol.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"--.*$", "", s) for s in metin.splitlines()).lower()


def _fonksiyon(govde: str, ad: str) -> str:
    i = govde.find(f"function public.{ad}(")
    assert i != -1, f"{ad} tanımı yok"
    j = govde.find("end; $$", i)
    assert j != -1, f"{ad} gövdesi kapanmıyor"
    return govde[i : j + 7]


def _bosluksuz(s: str) -> str:
    return re.sub(r"\s+", "", s)


# ══ a) SQL DOSYASI ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_sema_EKLEMELI_ve_TEK_ISLEM():
    g = _govde(SQL)
    for tablo in ("treatment_sessions", "patients"):
        assert re.search(
            rf"alter\s+table\s+public\.{tablo}\s+add\s+column\s+if\s+not\s+exists\s+profil\s+text\s+not\s+null\s+default\s+''",
            g,
        ), f"{tablo}.profil EKLEMELİ (if not exists, not null default '') eklenmiyor"
    for yasak in (
        r"drop\s+column",
        r"drop\s+table",
        r"alter\s+column",
        r"\btruncate\b",
        r"delete\s+from",
        r"drop\s+function",
    ):
        assert not re.search(yasak, g), f"eklemeli değil / imza düşürüyor: {yasak!r}"
    assert re.match(r"\s*begin\s*;", g) and re.search(r"commit\s*;\s*$", g), (
        "dosya TEK İŞLEM değil (yarım uygulanabilir)"
    )


def test_KRITIK_on_kosul_kapisi_v2_ve_BILESIK_anahtar_yoksa_DURUR():
    g = _govde(SQL)
    kapi = g[: g.find("alter table")]
    assert "do $$" in kapi, "ön koşul kapısı (DO bloğu) kolonlardan ÖNCE değil"
    assert "_pemf_verify_device" in kapi and "raise exception" in kapi, "v2 (cihaz sırrı) uygulanmamışsa durmuyor"
    assert "treatment_sessions" in kapi and "array['device_id', 'id']" in kapi, (
        "bileşik anahtar (device_id, id) yoksa durmuyor"
    )


@pytest.mark.parametrize(
    "ad,yuk,tablo,cakisma,eski_kolonlar",
    [
        (
            "upsert_session",
            "p_session",
            "treatment_sessions",
            "on conflict (device_id, id) do update set",
            (
                "end_time=excluded.end_time",
                "duration_minutes=excluded.duration_minutes",
                "session_status=excluded.session_status",
            ),
        ),
        (
            "upsert_patient",
            "p_patient",
            "patients",
            "on conflict (id) do update set",
            (
                "name=excluded.name",
                "owner=excluded.owner",
                "vet_contact=excluded.vet_contact",
                "updated_at=excluded.updated_at",
            ),
        ),
    ],
)
def test_KRITIK_upsert_IMZA_AYNI_korumalar_AYNEN_bos_profil_EZMEZ(ad, yuk, tablo, cakisma, eski_kolonlar):
    f = _fonksiyon(_govde(SQL), ad)
    assert f.startswith(f"function public.{ad}(p_device_id text, {yuk} jsonb, p_secret text)"), (
        f"{ad} imzası değişmiş → yeni aşırı-yük (eski çağrılar PGRST203) — profil YÜKTE taşınmalı"
    )
    assert re.search(r"security\s+definer\s+set\s+search_path\s*=\s*public\s+as\s+\$\$", f), (
        "sabit search_path'siz SECURITY DEFINER"
    )
    dogrula = f.find("if not public._pemf_verify_device(p_device_id, p_secret) then")
    assert dogrula != -1 and dogrula < f.find("insert into"), f"{ad}: cihaz sırrı yazmadan ÖNCE doğrulanmıyor"
    assert cakisma in f, f"{ad}: çakışma hedefi değişmiş"
    assert f"where public.{tablo}.device_id = p_device_id" in f, f"{ad}: cross-tenant ezme koruması kaldırılmış"
    sade = _bosluksuz(f)
    for kolon in eski_kolonlar:
        assert kolon in sade, f"{ad}: eski güncelleme kolonu düşmüş: {kolon}"
    assert f"profil=casewhenexcluded.profil<>''thenexcluded.profilelsepublic.{tablo}.profilend" in sade, (
        f"{ad}: buluttan boş gelen profil dolu bulut değerini EZİYOR"
    )
    assert f"lower(btrim(coalesce({yuk}->>'profil','')))" in sade, f"{ad}: profil normalize edilmiyor"
    m = re.search(r"if\s+v_profil\s+not\s+in\s*\(([^)]*)\)\s+then\s+v_profil\s*:=\s*''", f)
    assert m, f"{ad}: bilinmeyen profil '' yapılmıyor"
    assert set(re.findall(r"'([a-z_]+)'", m.group(1))) == set(PROFILLER), (
        "SQL profil kümesi utils/profil.PROFILLER ile AYNI değil"
    )


def test_KRITIK_rol_basina_EXECUTE_yalniz_anon():
    g = _govde(SQL)
    for ad, yuk in (("upsert_session", "jsonb"), ("upsert_patient", "jsonb")):
        imza = rf"public\.{ad}\(\s*text\s*,\s*{yuk}\s*,\s*text\s*\)"
        assert re.search(rf"revoke\s+all\s+on\s+function\s+{imza}\s+from\s+public\s*,\s*authenticated\s*;", g), (
            f"{ad}: public VE authenticated yetkisi rol rol geri alınmıyor (revoke from public YETMEZ)"
        )
        assert re.search(rf"grant\s+execute\s+on\s+function\s+{imza}\s+to\s+anon\s*;", g), (
            f"{ad}: cihaz (anon) yetkisi yok"
        )
        for s in re.findall(rf"grant\s+[^;]*{imza}[^;]*;", g):
            assert not re.search(r"\b(public|authenticated|service_role)\b", s.split(" to ", 1)[1]), f"fazla rol: {s}"
    assert "notify pgrst, 'reload schema'" in g, "PostgREST şema önbelleği yenilenmiyor (yeni kolon resolve'da gecikir)"


def test_KRITIK_geri_alma_ESKI_govdeleri_kurar_VERI_SILMEZ():
    g = _govde(GERI_AL)
    assert re.match(r"\s*begin\s*;", g) and re.search(r"commit\s*;\s*$", g), "geri alma TEK İŞLEM değil"
    assert not re.search(r"drop\s+column|drop\s+table|drop\s+function|truncate|delete\s+from", g), (
        "geri alma veri / imza siliyor"
    )
    for ad, tablo in (("upsert_session", "treatment_sessions"), ("upsert_patient", "patients")):
        f = _fonksiyon(g, ad)
        assert "profil" not in f, f"{ad}: geri alma gövdesi hâlâ profil yazıyor"
        assert (
            "_pemf_verify_device(p_device_id, p_secret)" in f and f"where public.{tablo}.device_id = p_device_id" in f
        )
        assert re.search(rf"grant\s+execute\s+on\s+function\s+public\.{ad}\(text,\s*jsonb,\s*text\)\s+to\s+anon\s*;", g)


def test_README_dosyalari_SIRASIYLA_anar():
    metin = README.read_text(encoding="utf-8")
    for ad in ("supabase_profil.sql", "supabase_profil_geri_al.sql"):
        assert re.search(r"(?<![\w.-])" + re.escape(ad) + r"(?![\w.-])", metin), f"README {ad} anmıyor"
    bolum = metin[metin.find("supabase_profil.sql") - 1500 : metin.find("supabase_profil.sql") + 1500]
    assert "seans_kimligi_bilesik_anahtar.sql" in bolum and "supabase_secure_v2.sql" in bolum, (
        "ön koşul sırası yazılı değil"
    )


# ══ b–d) SENKRON — sahte bulut (eski / yeni şema) ════════════════════════════════════════════════════════════════════════════════


class _Sonuc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _SahteBulut:
    """Supabase RPC taklidi — CANLIYA İSTEK YOK.
    `yeni=False`: bugünkü canlı (kolon yok → upsert yükteki `profil`i YOK SAYAR, resolve satırında `profil` anahtarı YOK).
    `yeni=True`: `supabase_profil.sql` sonrası (upsert profili normalize eder, boş gelen dolu değeri EZMEZ; resolve satırında `profil` VAR).
    `sema_yukselt()`: SQL'in canlıya uygulanması — var olan satırlar kolonun varsayılanını ('') alır."""

    def __init__(self, yeni: bool):
        self.yeni = yeni
        self.tablolar: dict = {"upsert_session": {}, "upsert_patient": {}}
        self.cagrilar: list = []

    def sema_yukselt(self):
        self.yeni = True
        for tablo in self.tablolar.values():
            for satir in tablo.values():
                satir.setdefault("profil", "")

    def rpc(self, ad, params=None):
        self.cagrilar.append((ad, params))
        if ad in self.tablolar:
            yuk = params["p_session"] if ad == "upsert_session" else params["p_patient"]
            tablo = self.tablolar[ad]
            eski = tablo.get(str(yuk["id"]))
            satir = {k: v for k, v in yuk.items() if k != "profil"}
            if self.yeni:
                p = str(yuk.get("profil") or "").strip().lower()
                p = p if p in PROFILLER else ""
                satir["profil"] = p or (eski or {}).get("profil", "")
            if eski is None:
                tablo[str(yuk["id"])] = satir
            else:
                eski.update(satir)
            return _Sonuc([])
        if ad == "resolve_sessions":
            return _Sonuc([dict(s) for s in self.tablolar["upsert_session"].values()])
        if ad == "resolve_patients":
            return _Sonuc([dict(s) for s in self.tablolar["upsert_patient"].values()])
        return _Sonuc([])

    def yukler(self, ad):
        return [p["p_session"] if ad == "upsert_session" else p["p_patient"] for a, p in self.cagrilar if a == ad]


def _bulut_seans(sid, mod, **ek):
    satir = {
        "id": sid,
        "device_id": "ch2-cihaz",
        "session_date": "2026-10-15",
        "start_time": "2026-10-15T10:00:00",
        "end_time": "2026-10-15T10:30:00",
        "duration_minutes": 30,
        "treatment_mode": mod,
        "session_status": "completed",
        "created_at": "2026-10-15T10:00:00",
    }
    satir.update(ek)
    return satir


def _isci(bulut, monkeypatch):
    from servers.sync_worker import CloudSyncWorker

    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    w = CloudSyncWorker("", "")
    w.client = bulut
    w.patient_sync_enabled = True
    w.device_id = "ch2-cihaz"
    return w


def _seans_db(temp_app_data):
    from database.treatment_history_db import get_treatment_db

    return get_treatment_db(temp_app_data)


def _hasta_db(temp_app_data):
    from database.patient_database import PatientDatabase

    return PatientDatabase(str(temp_app_data / "patients.db"))


def _seans(db, sid):
    with db._get_connection() as c:
        r = c.execute("SELECT profil, sync_status FROM treatment_sessions WHERE id=?", (sid,)).fetchone()
    return (r[0], r[1]) if r else None


def _hasta(db, pid):
    with db._get_connection() as c:
        r = c.execute("SELECT profil, sync_status FROM patients WHERE id=?", (pid,)).fetchone()
    return (r[0], r[1]) if r else None


@pytest.mark.parametrize("yeni", [False, True], ids=["ESKI_sema", "YENI_sema"])
def test_KRITIK_PUSH_seans_ve_hasta_profili_TASIR_eski_kayit_BOS_gider(yeni, temp_app_data, monkeypatch):
    sdb, hdb = _seans_db(temp_app_data), _hasta_db(temp_app_data)
    s_ars = sdb.start_session("AI Pro · Fantom Tümör", operator_name="Vet", patient_name="D1", profil="researcher")
    s_eski = sdb.start_session("Manual", operator_name="Vet", patient_name="Boncuk")  # SG öncesi gibi: profil ''
    h_ev = hdb.add_patient({"name": "Pamuk", "species": "kedi", "profil": "pet_owner"})
    bulut = _SahteBulut(yeni)
    w = _isci(bulut, monkeypatch)
    w._sync_sessions(sdb)
    w._sync_patients(hdb)
    seans_yukleri = {str(y["id"]): y for y in bulut.yukler("upsert_session")}
    assert seans_yukleri[str(s_ars)].get("profil") == "researcher", "PUSH seans profilini TAŞIMIYOR"
    assert seans_yukleri[str(s_eski)].get("profil") == "", (
        "profilsiz eski seans TÜRETİLMİŞ değerle gönderildi (veri değiştirilmez)"
    )
    hasta_yukleri = {str(y["id"]): y for y in bulut.yukler("upsert_patient")}
    assert hasta_yukleri[h_ev].get("profil") == "pet_owner", "PUSH hasta profilini TAŞIMIYOR"
    assert _seans(sdb, s_ars)[1] == 1 and _hasta(hdb, h_ev)[1] == 1, "PUSH başarılı ama senkron işareti konmadı"


def test_KRITIK_ESKI_sema_senkron_DURMAZ_yeniden_gonderme_SELI_YOK(temp_app_data, monkeypatch, caplog):
    sdb, hdb = _seans_db(temp_app_data), _hasta_db(temp_app_data)
    sid = sdb.start_session("Manual", operator_name="Vet", patient_name="Boncuk", profil="veterinarian")
    pid = hdb.add_patient({"name": "Pamuk", "species": "kedi", "profil": "veterinarian"})
    bulut = _SahteBulut(yeni=False)
    w = _isci(bulut, monkeypatch)
    caplog.set_level(logging.WARNING, logger="servers.sync_worker")
    caplog.clear()  # kurucunun "URL / anahtar yok" uyarısı ölçüme girmez — yalnız senkron turları
    for _ in range(4):
        w._sync_sessions(sdb)
        w._sync_patients(hdb)
    assert len(bulut.yukler("upsert_session")) == 1 and len(bulut.yukler("upsert_patient")) == 1, (
        "eski şemada her turda yeniden PUSH (60 sn'de bir sonsuz sel)"
    )
    assert _seans(sdb, sid) == ("veterinarian", 1) and _hasta(hdb, pid) == ("veterinarian", 1), (
        "yerel profil / işaret bozuldu"
    )
    sel = [r.getMessage() for r in caplog.records if r.name == "servers.sync_worker" and r.levelno >= logging.WARNING]
    assert not sel, f"eski şemada senkron uyarı / hata yazıyor: {sel}"


def test_KRITIK_YENI_sema_uygulaninca_GERI_DOLDURMA_bir_kez_ve_YAKINSAR(temp_app_data, monkeypatch):
    sdb, hdb = _seans_db(temp_app_data), _hasta_db(temp_app_data)
    sid = sdb.start_session("AI Pro · Petri Kuyu", operator_name="Vet", patient_name="K1", profil="researcher")
    pid = hdb.add_patient({"name": "Denek 1", "species": "fare", "profil": "researcher"})
    bulut = _SahteBulut(yeni=False)
    w = _isci(bulut, monkeypatch)
    w._sync_sessions(sdb)
    w._sync_patients(hdb)  # eski şemada gönderildi → bulutta profil YOK
    bulut.sema_yukselt()  # sahip SQL'i canlıya uyguladı → satırlar profil='' aldı
    for _ in range(4):
        w._sync_sessions(sdb)
        w._sync_patients(hdb)
    assert bulut.tablolar["upsert_session"][str(sid)]["profil"] == "researcher", "bulut seans profili geri DOLMADI"
    assert bulut.tablolar["upsert_patient"][pid]["profil"] == "researcher", "bulut hasta profili geri DOLMADI"
    assert len(bulut.yukler("upsert_session")) == 2 and len(bulut.yukler("upsert_patient")) == 2, (
        "geri doldurma tam BİR yeniden gönderim olmalı (yakınsamıyor ya da hiç yok)"
    )
    assert _seans(sdb, sid) == ("researcher", 1) and _hasta(hdb, pid) == ("researcher", 1)


def test_KRITIK_YARIM_sema_kolon_var_upsert_eski_SEL_YOK(temp_app_data, monkeypatch):
    """Savunma: kolon eklenmiş ama fonksiyon eski kalmış (dosya tek işlem; yine de elle yarım uygulanırsa) → profil bulutta hep boş görünür.
    Geri doldurma kayıt başına süreç ömründe BİR kez denenir; her turda yeniden PUSH seli OLMAZ."""
    sdb = _seans_db(temp_app_data)
    sid = sdb.start_session("Manual", operator_name="Vet", patient_name="Boncuk", profil="pet_owner")
    bulut = _SahteBulut(yeni=False)  # upsert profili YAZMAZ ...
    w = _isci(bulut, monkeypatch)
    w._sync_sessions(sdb)
    asil = bulut.rpc

    def _rpc(ad, params=None):
        sonuc = asil(ad, params)
        if ad == "resolve_sessions":
            for s in sonuc.data:
                s.setdefault("profil", "")  # ... ama kolon VAR (resolve taşır, hep boş)
        return sonuc

    bulut.rpc = _rpc
    for _ in range(5):
        w._sync_sessions(sdb)
    assert len(bulut.yukler("upsert_session")) <= 2, (
        f"yarım şemada PUSH seli: {len(bulut.yukler('upsert_session'))} gönderim"
    )
    assert _seans(sdb, sid)[0] == "pet_owner"


def test_KRITIK_PULL_profilli_kayit_O_PROFILE_profilsiz_kayit_TURETILIR(temp_app_data, monkeypatch):
    sdb, hdb = _seans_db(temp_app_data), _hasta_db(temp_app_data)
    bulut = _SahteBulut(yeni=True)
    bulut.tablolar["upsert_session"] = {
        "901": _bulut_seans(901, "Manual", profil="researcher"),
        "902": _bulut_seans(902, "Manual", profil="RESEARCHER "),
        "903": _bulut_seans(903, "Manual", profil="admin"),
        "904": _bulut_seans(904, "AI Pro · Fantom Tümör"),  # eski şema satırı: anahtar YOK
    }
    w = _isci(bulut, monkeypatch)
    w._sync_sessions(sdb)
    assert _seans(sdb, 901)[0] == "researcher", "buluttan inen profilli seans o profile YAZILMADI"
    assert _seans(sdb, 902)[0] == "researcher", "bulut profili normalize edilmedi"
    assert _seans(sdb, 903)[0] == "", "bilinmeyen bulut profili yerele yazıldı"
    assert _seans(sdb, 904)[0] == "" and seans_profili(_seans(sdb, 904)[0], "AI Pro · Fantom Tümör") == "researcher", (
        "profilsiz (eski şema) kayıt TÜRETME kuralıyla görünmüyor"
    )
    assert seans_profili(_seans(sdb, 903)[0], "Manual") == "veterinarian"
    # hasta: kendi anahtarıyla şifreli ad (cross-tenant korumasından geçsin) + profil
    pid = hdb.add_patient({"name": "Pamuk", "species": "kedi", "profil": "pet_owner"})
    bulut.tablolar["upsert_patient"] = {}
    w._sync_patients(hdb)  # PUSH → bulutta pet_owner
    with hdb._get_connection() as c:
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
        c.commit()
    w._sync_patients(hdb)  # PULL → yeniden iner
    assert _hasta(hdb, pid) == ("pet_owner", 1), "buluttan inen hasta profili yazılmadı"


@pytest.mark.parametrize("yeni", [False, True], ids=["ESKI_sema_anahtar_yok", "YENI_sema_bos"])
def test_KRITIK_yerel_profil_buluttan_gelen_BOSLA_EZILMEZ(yeni, temp_app_data, monkeypatch):
    sdb, hdb = _seans_db(temp_app_data), _hasta_db(temp_app_data)
    sid = sdb.start_session("Manual", operator_name="Vet", patient_name="Boncuk", profil="pet_owner")
    pid = hdb.add_patient({"name": "Pamuk", "species": "kedi", "profil": "pet_owner"})
    bulut = _SahteBulut(yeni=False)
    w = _isci(bulut, monkeypatch)
    w._sync_sessions(sdb)
    w._sync_patients(hdb)
    if yeni:
        bulut.sema_yukselt()
        w._profil_geri_doldurulan_seans.add(str(sid))  # geri doldurma zaten denendi → saf "ezme" kolunu ölç
        w._profil_geri_doldurulan_hasta.add(pid)
    w._sync_sessions(sdb)
    w._sync_patients(hdb)
    assert _seans(sdb, sid)[0] == "pet_owner", "yerel seans profili buluttan gelen boşla EZİLDİ"
    assert _hasta(hdb, pid)[0] == "pet_owner", "yerel hasta profili buluttan gelen boşla EZİLDİ"


def test_PUSH_bekleyen_yerel_profil_BAYAT_bulut_degeriyle_EZILMEZ(temp_app_data, monkeypatch):
    sdb = _seans_db(temp_app_data)
    sid = sdb.start_session("Manual", operator_name="Vet", patient_name="Boncuk", profil="researcher")
    bulut = _SahteBulut(yeni=True)
    bulut.tablolar["upsert_session"][str(sid)] = _bulut_seans(sid, "Manual", profil="pet_owner")
    w = _isci(bulut, monkeypatch)
    asil = bulut.rpc

    def _rpc(ad, params=None):
        if ad == "upsert_session":
            raise RuntimeError("ag yok")
        return asil(ad, params)

    bulut.rpc = _rpc
    w._sync_sessions(sdb)  # PUSH düştü → yerel 0 (bekliyor); PULL bayat 'pet_owner' getirdi
    assert _seans(sdb, sid) == ("researcher", 0), "PUSH bekleyen yerel profil bayat bulut değeriyle EZİLDİ"


def test_canliya_istek_YOK_istemci_kurulmaz(monkeypatch):
    from servers.sync_worker import CloudSyncWorker

    w = CloudSyncWorker("", "")
    assert w.client is None and w._ensure_client() is False, (
        "URL / anahtar yokken istemci kuruldu (canlıya istek yolu açık)"
    )
