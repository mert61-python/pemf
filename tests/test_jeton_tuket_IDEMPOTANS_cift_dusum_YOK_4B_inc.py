# -*- coding: utf-8 -*-
"""4-B İNCELEMESİ 4B-4.1 — çevrimdışı jeton uzlaştırmasında ÇİFT DÜŞÜMÜ önleyen tek güvence SUNUCUDADIR; o güvence kilitli.

D4.23 (`38ff3cbf`, Y24) bağlantı dönünce defteri arka planda gönderir: gönderim başarılı olup defter yeniden yazılamazsa (süreç
kapanışı, disk hatası) kayıtlar defterde KALIR ve sonraki bağlantıda AYNI `istek_id`'lerle yeniden gider. Bunun gerçek ücreti İKİ KEZ
düşmemesini sağlayan yalnız `apps/backend/database/supabase_jetonlar.sql`'dir: `token_ledger` üzerinde `unique (user_id, istek_id)` ve
`jeton_tuket`'in bakiyeye dokunmadan ÖNCE "bu istek işlendi mi" denetimi. İnceleme ölçtü: ikisini silen mutantlar jeton + SQL test
kümesinde (48 dosya, 436 test) YEŞİL kalıyordu → istemcinin "çift düşme yok" sözü kilitsiz bir sunucu değişmezine dayanıyordu.

Ölçüm: (1) SQL metni (yorumlar soyulmuş; D4.26 ayrıştırıcısının `_strip_comments`'i) — tablo kısıtı ve RPC'deki denetimin SIRASI;
(2) davranış: GERÇEK `bakiye_ozeti` / `_jeton_kapisi_karari` / uzlaştırma ipliği, Supabase taşıma katmanı yerine SQL'in ANLAMINI taklit
eden sahte (kullanıcı = JWT `sub`; işlenmiş `(kullanıcı, istek_id)` → `ok` ve düşüm YOK). Karşıt kanıt: aynı senaryo idempotansız
sahteyle çift düşüm GÖSTERİR (ölçüm aracı kör değil). (3) Ö.4-Y8: internetsiz + defter dolu iken serbest uçlar (AI Pro durdurma vb.)
ve /api/ai dışı tedavi / ACİL DURDUR yolları defteri OKUMAZ, uzlaştırmayı tetiklemez, bakiye okumaz (gecikme yok).
2026-10-19 (S-4B.5): defterde yalnız YOLDA KALAN ÖDEME olur (çevrimiçi karar, düşüm o an gönderilemedi) — kayıtlar artık öyle üretilir.
"""

from __future__ import annotations

import base64
import importlib
import json
import re
import threading
import time
from pathlib import Path

import pytest
from test_supabase_sql_invariants import _strip_comments  # noqa: E402  (D4.26 yorum soyucu — tek kaynak)

KOK = Path(__file__).resolve().parents[1]
SQL = KOK / "apps" / "backend" / "database" / "supabase_jetonlar.sql"


def _sql() -> str:
    return re.sub(r"\s+", " ", _strip_comments(SQL.read_text(encoding="utf-8"))).lower()


def _tablo_govdesi(sql: str, tablo: str) -> str:
    m = re.search(r"create table (?:if not exists )?" + re.escape(tablo) + r" \((.*?)\);", sql)
    assert m, f"{tablo} tanımı bulunamadı (ölçüm aracı kör)"
    return m.group(1)


def _fonksiyon_govdesi(sql: str, ad: str) -> str:
    m = re.search(r"create or replace function " + re.escape(ad) + r"\(.*?\$\$(.*?)\$\$", sql)
    assert m, f"{ad} gövdesi bulunamadı (ölçüm aracı kör)"
    return m.group(1)


def test_KRITIK_jeton_defteri_istek_id_KULLANICI_BASINA_TEKIL():
    govde = _tablo_govdesi(_sql(), "public.token_ledger")
    assert re.search(r"\bunique ?\( ?user_id ?, ?istek_id ?\)", govde), (
        "token_ledger'da (user_id, istek_id) benzersizliği YOK — eşzamanlı iki aynı istek ve çevrimdışı uzlaştırmanın yeniden "
        "gönderimi bakiyeyi İKİ KEZ düşebilir (gerçek ücret)"
    )


def test_KRITIK_jeton_tuket_TEKRAR_istegi_bakiyeye_DOKUNMADAN_doner():
    g = _fonksiyon_govdesi(_sql(), "public.jeton_tuket")
    m = re.search(r"if exists \( ?select 1 from public\.token_ledger (\w+) where (.*?)\) then(.*?)end if;", g)
    assert m, "jeton_tuket'te 'bu istek işlendi mi' (token_ledger exists) denetimi YOK"
    takma, kosul, dal = m.group(1), m.group(2), m.group(3)
    assert f"{takma}.user_id = v_user" in kosul and f"{takma}.istek_id = p_istek_id" in kosul, (
        f"idempotans denetimi kullanıcı + istek_id'ye bağlı değil: {kosul!r}"
    )
    assert "return" in dal and "'ok', true" in dal and "update" not in dal and "insert" not in dal, (
        f"tekrar istek dalı bakiyeye dokunuyor ya da başarı döndürmüyor: {dal!r}"
    )
    ilk_update = g.find("update public.token_balances")
    ilk_kilit = g.find("for update")
    assert -1 < m.start() < ilk_kilit < ilk_update, "idempotans denetimi bakiye kilidinden / düşümden ÖNCE değil"


def test_KARSIT_KANIT_sql_olcucusu_SILINEN_degismezleri_YAKALAR():
    sql = _sql()
    tablo = _tablo_govdesi(sql, "public.token_ledger").replace("unique (user_id, istek_id)", "")
    assert not re.search(r"\bunique ?\( ?user_id ?, ?istek_id ?\)", tablo)
    g = _fonksiyon_govdesi(sql, "public.jeton_tuket")
    g2 = re.sub(r"if exists \( ?select 1 from public\.token_ledger .*?end if;", "", g, count=1)
    assert not re.search(r"if exists \( ?select 1 from public\.token_ledger", g2)


# ── davranış: sahte sunucu SQL'in anlamıyla ────────────────────────────────────────────────────


def _jwt(sub: str) -> str:
    from jwt_test_anahtari import imzali_jwt  # TA T4: GERÇEK ES256 imza (JWKS doğrulaması)

    return imzali_jwt({"sub": sub})


def _sub(token: str) -> str:
    g = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(g + "=" * (-len(g) % 4)))["sub"]


class _Istek:
    def __init__(self, sub: str | None, yol: str):
        self.headers = {"authorization": f"Bearer {_jwt(sub)}"} if sub else {}
        self.url = type("U", (), {"path": yol})()


class SahteSupabase:
    """`jeton_tuket` / `jeton_bakiyem`'in ANLAMI (satır kilidi = Python kilidi). `tekilsiz=True` = idempotans YOK (karşıt kanıt)."""

    def __init__(self, bakiyeler: dict, tekilsiz: bool = False):
        self.bakiye = dict(bakiyeler)
        self.defter: list[tuple[str, str, int]] = []
        self.tekilsiz = tekilsiz
        self.cevrimici = True
        self.odeme_kopuk = (
            False  # okuma gider, DÜŞÜM gitmez (analiz teslim edildi, ağ tam o an koptu → yolda kalan ödeme)
        )
        self.kilit = threading.Lock()

    def bakiye_oku(self, token):
        if not self.cevrimici:
            raise ConnectionError("sahte: cevrimdisi")
        return {"aylik_hak": self.bakiye.get(_sub(token), 0), "satin_alinan": 0, "odeme_modeli": "on_odemeli"}

    def tuket(self, token, **k):
        if not self.cevrimici or self.odeme_kopuk:
            return False
        u, iid, m = _sub(token), str(k.get("istek_id") or ""), int(k.get("miktar") or 0)
        with self.kilit:
            if not self.tekilsiz and any(d[0] == u and d[1] == iid for d in self.defter):
                return True
            if self.bakiye.get(u, 0) < m:
                return False
            self.bakiye[u] -= m
            self.defter.append((u, iid, m))
            return True


@pytest.fixture
def j(tmp_path, monkeypatch):
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    mod = importlib.import_module("servers.jeton")
    monkeypatch.setattr(mod, "JETON_ENFORCED", True)
    monkeypatch.setattr(mod, "_son_uzlastirma", None, raising=False)
    yield mod
    t = getattr(mod, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)


def _bagla(j, monkeypatch, sb):
    monkeypatch.setattr(j, "_bakiye_satiri_oku", sb.bakiye_oku)
    monkeypatch.setattr(j, "_tuketim_gonder_canli", sb.tuket)


def _bekle(j):
    t = getattr(j, "_son_uzlastirma", None)
    if t is not None:
        t.join(timeout=10)
        assert not t.is_alive(), "uzlaştırma ipliği bitmedi"


def _defter(j):
    p = j._defter_yolu()
    return json.loads(p.read_text(encoding="utf-8") or "[]") if p.exists() else []


ANALIZ = "/api/ai/vision/ornek_analiz"  # goruntu sınıfı (1 jeton)


def _yolda_kalan_odemeler(j, sb, sub, n):
    """n analiz çevrimiçi karar alır ve teslim edilir; düşüm ağ kopukluğuyla gönderilemez → defterde n yolda kalan ödeme."""
    sb.odeme_kopuk = True
    for _ in range(n):
        j._jeton_kapisi_karari(_Istek(sub, ANALIZ))
    _bekle(j)  # kopukken başlamış uzlaştırma bitsin (bağlantı "dönünce" eski iplik göndermesin)
    sb.odeme_kopuk = False


def test_KRITIK_baglanti_donunce_ESZAMANLI_tetikler_CIFT_DUSMEZ(j, monkeypatch):
    sb = SahteSupabase({"A": 10, "B": 10})
    _bagla(j, monkeypatch, sb)
    _yolda_kalan_odemeler(j, sb, "A", 3)
    assert len(_defter(j)) == 3
    hatalar: list[str] = []

    def _kos(f):
        try:
            f()
        except Exception as e:
            hatalar.append(repr(e))

    ip = [
        threading.Thread(target=_kos, args=(lambda: j.bakiye_ozeti(_Istek("A", "/api/jeton/bakiye")),)),
        threading.Thread(target=_kos, args=(lambda: j._jeton_kapisi_karari(_Istek("A", ANALIZ)),)),
        threading.Thread(target=_kos, args=(lambda: j.bakiye_ozeti(_Istek("B", "/api/jeton/bakiye")),)),
    ]
    for t in ip:
        t.start()
    for t in ip:
        t.join(10)
    _bekle(j)
    for _ in range(3):  # tek uçuş: süren varken başlamayan tetik bir sonraki bağlantı anında uzlaşır
        if not _defter(j):
            break
        j.bakiye_ozeti(_Istek("A", "/api/jeton/bakiye"))
        _bekle(j)
    assert not hatalar, hatalar
    assert _defter(j) == [], f"defter uzlaşmadı: {_defter(j)}"
    a = [d for d in sb.defter if d[0] == "A"]
    assert len(a) == 4 and len({d[1] for d in a}) == 4, f"A: {a}"  # 3 yolda kalan + 1 çevrimiçi
    assert sb.bakiye == {"A": 6, "B": 10}, sb.bakiye


@pytest.mark.parametrize("tekilsiz", [False, True], ids=["sql_idempotans_VAR", "KARSIT_sql_idempotans_YOK"])
def test_KRITIK_gonderim_sonrasi_defter_yazilamazsa_YENIDEN_gonderim_CIFT_DUSMEZ(j, monkeypatch, tekilsiz):
    sb = SahteSupabase({"A": 10}, tekilsiz=tekilsiz)
    _bagla(j, monkeypatch, sb)
    _yolda_kalan_odemeler(j, sb, "A", 2)
    gercek_yaz = j.JetonYoneticisi._defteri_yaz
    durum = {"dusur": True}

    def _yaz(self, kayitlar):
        if durum["dusur"] and len(kayitlar) < 2:  # uzlaştırmanın "gönderilenleri düş" yazımı
            durum["dusur"] = False
            return  # çökme: yazım hiç olmadı
        return gercek_yaz(self, kayitlar)

    monkeypatch.setattr(j.JetonYoneticisi, "_defteri_yaz", _yaz)
    j.bakiye_ozeti(_Istek("A", "/api/jeton/bakiye"))
    _bekle(j)
    assert len(_defter(j)) == 2, "ölçüm aracı: çökme benzetimi devreye girmedi"
    j.bakiye_ozeti(_Istek("A", "/api/jeton/bakiye"))
    _bekle(j)
    assert _defter(j) == []
    if tekilsiz:
        assert sb.bakiye["A"] == 6, f"karşıt kanıt: idempotansız sunucuda çift düşüm görülmeliydi ({sb.bakiye})"
    else:
        assert sb.bakiye["A"] == 8, f"ÇİFT DÜŞÜM: {sb.bakiye} (beklenen 8)"


def test_KRITIK_internetsiz_ve_defter_doluyken_SERBEST_ve_TEDAVI_uclari_deftere_ve_aga_DOKUNMAZ(j, monkeypatch):
    """Ö.4-Y8: zorlama açık, internet YOK (analiz 402 `cevrimdisi`), defterde yolda kalan ödeme → serbest AI uçları ve /api/ai dışı
    tedavi / ACİL DURDUR yolları kapıya girmez: defter okunmaz, uzlaştırma tetiklenmez, bakiye okunmaz (asılı ağ bile gecikme yaratmaz)."""
    sb = SahteSupabase({"A": 10})
    _bagla(j, monkeypatch, sb)
    _yolda_kalan_odemeler(j, sb, "A", 2)
    assert len(_defter(j)) == 2, "ölçüm aracı: defter dolmadı"
    sb.cevrimici = False
    with pytest.raises(Exception) as e:
        j._jeton_kapisi_karari(_Istek("A", ANALIZ))
    assert getattr(e.value, "status_code", None) == 402, "ölçüm aracı: internetsiz analiz 402 almalı"
    sayac = {"oku": 0, "tetik": 0, "bakiye": 0}
    gercek_oku = j.JetonYoneticisi._defteri_oku

    def _oku(self):
        sayac["oku"] += 1
        return gercek_oku(self)

    def _bakiye(_t):
        sayac["bakiye"] += 1
        time.sleep(2)
        raise ConnectionError("asili ag")

    monkeypatch.setattr(j.JetonYoneticisi, "_defteri_oku", _oku)
    monkeypatch.setattr(j, "_uzlastirmayi_tetikle", lambda _t: sayac.__setitem__("tetik", sayac["tetik"] + 1))
    monkeypatch.setattr(j, "_bakiye_satiri_oku", _bakiye)
    yollar = sorted(j._SERBEST_AI_UCLARI) + [
        "/api/emergency_stop",
        "/api/session/stop",
        "/api/coils/1/stop",
        "/api/stm/estop",
    ]
    for yol in yollar:
        t0 = time.perf_counter()
        assert j._jeton_kapisi_karari(_Istek("A", yol)) is None
        assert time.perf_counter() - t0 < 0.5, f"{yol} gecikti"
    assert sayac == {"oku": 0, "tetik": 0, "bakiye": 0}, sayac
