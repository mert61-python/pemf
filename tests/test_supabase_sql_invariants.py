# Author: mertaygn, cglrgrkn
"""Denetim 2026-08-04 (P3): Supabase SQL şemasının güvenlik değişmezleri.

Bulut tarafı bu üründe kimlik doğrulama, cihaz kaydı ve (secure_v2 ile) hasta/seans verisi
taşır; istemciler `anon` anahtarıyla bağlanır. Güvenlik tamamen ÜÇ değişmeze dayanıyor:

  1. Her tabloda RLS AÇIK olmalı. Kapalıysa `anon` anahtarı — ki mobil uygulamanın içinde,
     yani saldırganın elinde — tabloyu doğrudan okur/yazar.
  2. `anon`/`authenticated` rollerine TABLO üzerinde doğrudan GRANT verilmemeli; erişim yalnız
     SECURITY DEFINER RPC'leri üzerinden olmalı (device_id sunucu tarafında zorlanır).
  3. Her SECURITY DEFINER fonksiyonu SABİT `search_path` ile tanımlanmalı. Aksi halde arayan,
     `search_path`'ini değiştirip fonksiyonun çağırdığı adları KENDİ şemasındaki sahte
     nesnelere yönlendirebilir ve kodu tablo-sahibi yetkisiyle çalıştırır (klasik Postgres
     ayrıcalık yükseltmesi).

Denetim sırasında ÜÇÜ DE sağlanıyordu — bu test bir düzeltme değil, SÜRÜKLENME KAPISIDIR:
yeni bir tablo RLS'siz eklenirse ya da yeni bir RPC search_path'siz yazılırsa burada patlar.
SQL'i çalıştırmaz (canlı Postgres gerektirmez); metinsel/yapısal denetim yapar.
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
# ⚠️ İKİ DİZİN. Kapı başlangıçta yalnız `database/`e bakıyordu; 2026-08-09 denetiminde eklenen
# `supabase/upsert_device_envanter.sql` bu yüzden HİÇ denetlenmedi ve içinde üretimi kıracak bir
# imza çakışması vardı (dağıtımdan önce elle yakalandı). Yeni SQL'in nereye konacağı sabit
# değilse, kapı da tek bir dizine bakmamalı.
_SQL_DIRS = [_KOK / "database", _KOK / "supabase"]


def _sql_files() -> list[Path]:
    return sorted(p for d in _SQL_DIRS if d.is_dir() for p in d.glob("*.sql"))


def _strip_comments(text: str) -> str:
    """`--` satır yorumlarını at (yorumdaki 'SECURITY DEFINER' gibi ifadeler yanlış-pozitif yapar)."""
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def sql_bodies() -> dict[str, str]:
    files = _sql_files()
    if not files:
        pytest.skip(f"SQL şeması yok: {[str(d) for d in _SQL_DIRS]}")
    return {f.name: _strip_comments(f.read_text(encoding="utf-8", errors="replace")) for f in files}


def test_her_tabloda_rls_acik(sql_bodies):
    """RLS kapalı bir tablo, uygulamaya gömülü `anon` anahtarıyla doğrudan okunur/yazılır."""
    for name, body in sql_bodies.items():
        low = body.lower()
        tables = set(re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)", low))
        rls = set(re.findall(r"alter\s+table\s+(?:public\.)?([a-z_0-9]+)\s+enable\s+row\s+level\s+security", low))
        eksik = tables - rls
        assert not eksik, (
            f"{name}: RLS ACILMAMIS tablo(lar): {sorted(eksik)} — uygulamaya gomulu anon "
            f"anahtariyla dogrudan erisilebilir."
        )


def test_anon_rollerine_dogrudan_tablo_yetkisi_verilmiyor(sql_bodies):
    """Erişim yalnız SECURITY DEFINER RPC'lerinden olmalı (device_id sunucuda zorlanır).

    ⚠️ DENETİM 2026-08-04 (P2): kapsam iki yönden DARDI:
      (a) tablo kümesi DOSYA BAŞINA kuruluyordu; oysa projenin fiilî deseni "yeni .sql dosyası"
          (secure_v2 tabloları önceki dosyalarda tanımlı) → yeni bir dosyadaki grant hiç
          eşleşmezdi. Küme artık TÜM dosyaların birleşimi.
      (b) Supabase'de bu yetkinin verilmesinin EN yaygın biçimi olan
          `grant ... on all tables in schema public to anon` ve `alter default privileges`
          regex'e hiç uymuyordu → tamamen görünmezdi.
    """
    tum_tablolar: set[str] = set()
    for body in sql_bodies.values():
        tum_tablolar |= set(
            re.findall(
                r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)",
                body.lower(),
            )
        )
    assert tum_tablolar, "hic tablo bulunamadi — regex/dosya duzeni degismis olabilir"

    for name, body in sql_bodies.items():
        low = body.lower()
        # (b) Toplu yetkilendirme — tek başına yeterli sebep.
        for m in re.finditer(r"grant\s+[^;]*?\bon\s+all\s+tables\s+in\s+schema\s+\w+\s+to\s+([a-z_, ]+)", low):
            if "anon" in m.group(1) or "authenticated" in m.group(1):
                pytest.fail(
                    f"{name}: `GRANT ... ON ALL TABLES IN SCHEMA ... TO {m.group(1).strip()}` — "
                    f"TUM tablolara dogrudan erisim, RLS/device_id zorlamasini baypas eder."
                )
        for m in re.finditer(r"alter\s+default\s+privileges[^;]*?\bgrant\s+[^;]*?\bto\s+([a-z_, ]+)", low):
            if "anon" in m.group(1) or "authenticated" in m.group(1):
                pytest.fail(
                    f"{name}: `ALTER DEFAULT PRIVILEGES ... TO {m.group(1).strip()}` — "
                    f"BUNDAN SONRA olusturulacak her tabloya otomatik erisim verir."
                )
        # (a) Tekil tablo grant'i — kume artik TUM dosyalardan.
        for perms, obj, roles in re.findall(
            r"grant\s+([a-z, ]+?)\s+on\s+(?:table\s+)?(?:public\.)?([a-z_0-9.]+)\s+to\s+([a-z_, ]+)",
            low,
        ):
            if obj in tum_tablolar and ("anon" in roles or "authenticated" in roles):
                pytest.fail(
                    f"{name}: `{obj}` tablosuna DOGRUDAN grant ({perms.strip()} -> {roles.strip()}). "
                    f"RPC disi erisim RLS/device_id zorlamasini baypas eder."
                )


def test_security_definer_fonksiyonlari_sabit_search_path_kullanir(sql_bodies):
    """search_path sabitlenmezse arayan, fonksiyonun cozdugu adlari kacirabilir (yetki yukseltme)."""
    bulunan = 0
    for name, body in sql_bodies.items():
        low = body.lower()
        for m in re.finditer(r"security\s+definer", low):
            bulunan += 1
            # Tanım satırının devamında (aynı ifade içinde) `set search_path` gelmeli.
            # ⚠️ DENETİM 2026-08-04 (P3): sabit 240 karakterlik pencere BİR SONRAKİ fonksiyonun
            # tanımına TAŞABİLİYORDU → `set search_path` içermeyen bir SECURITY DEFINER,
            # komşusunun `search_path`'ini görüp "geçmiş" sayılabilirdi. Pencereyi ifadenin
            # kendi sonuna (gövde başlangıcı `as $$` ya da `;`) kadar kırp.
            _adaylar = [x for x in (low.find("as $$", m.start()), low.find(";", m.start())) if x != -1]
            _son = min(_adaylar + [m.start() + 240])
            pencere = low[m.start() : _son]
            satir_bas = low.rfind("\n", 0, m.start()) + 1
            satir = body[satir_bas : body.find("\n", m.start())].strip()
            assert "search_path" in pencere, f"{name}: SABIT search_path'siz SECURITY DEFINER -> {satir[:100]!r}"
    # ⚠️ DENETİM 2026-08-04 (P3): eşik 6'ydı ve TAM SINIRDAYDI — en güvenlik-kritik dosya olan
    # `supabase_secure_v2.sql` (6 SECURITY DEFINER) KOMPLE silinse bile kalan 6 fonksiyon eşiği
    # geçerdi ve test "hâlâ koruyorum" der gibi yeşil kalırdı. Eşik gerçek sayıya çekildi ve
    # güvenlik-kritik dosyaların VARLIĞI ayrıca şart koşuldu.
    assert bulunan >= 12, (
        f"beklenenden az SECURITY DEFINER bulundu ({bulunan}) — dosyalar tasinmis/silinmis olabilir, "
        f"bu test sessizce anlamsizlasir."
    )
    eksik = {"supabase_devices.sql", "supabase_patients.sql", "supabase_secure_v2.sql"} - set(sql_bodies)
    assert not eksik, f"guvenlik-kritik SQL dosya(lari) EKSIK: {sorted(eksik)}"


# ═══════════════════════════════════════════════════════════════════════════════════════════
# İMZA ÇAKIŞMASI (2026-08-10'da dağıtımdan ÖNCE yakalandı)
#
# `supabase/upsert_device_envanter.sql` ilk hâlinde `create or replace function
# public.upsert_device(...11 parametre...)` diyordu. PostgreSQL fonksiyonları (ad + argüman
# tipleri) ile anahtarlar: bu ifade yayındaki 7-parametreli fonksiyonu DEĞİŞTİRMEZ, yanına
# İKİNCİSİNİ EKLER. Sonrasında 7 argümanlı her çağrı — geriye-uyum yolu ve güncellenmemiş her
# backend — iki adaya birden uyar → PostgREST PGRST203 → heartbeat kırılır, uzaktan erişim ölür.
#
# Hata SAHADA, cihazlar sustuğunda görünürdü. Bu yüzden kural metin düzeyinde kilitlenir.
# ═══════════════════════════════════════════════════════════════════════════════════════════

_FN_TANIM = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+(?:public\.)?(\w+)\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)


def _parametre_sayisi(ham: str) -> int:
    """Parametre listesindeki virgülle ayrılmış üst-düzey öğe sayısı (varsayılanlar dâhil)."""
    ham = ham.strip()
    if not ham:
        return 0
    derinlik, n = 0, 1
    for c in ham:
        if c == "(":
            derinlik += 1
        elif c == ")":
            derinlik -= 1
        elif c == "," and derinlik == 0:
            n += 1
    return n


def _dusurme_var_mi(govde: str, fn: str) -> bool:
    """Bu dosya `fn`in eski imzalarını GERÇEKTEN düşürüyor mu?

    ⚠️ İlk hâli `pg_proc` + fonksiyon adı geçmesini yeterli sayıyordu — ama dosyanın SONUNDAKİ
    "tek imza kaldı mı?" DOĞRULAMA bloğu da tam olarak bu ikisini içeriyor. Sonuç: düşürme adımı
    silinse bile kapı yeşil kalıyordu (mutasyon turunda ölçüldü). `drop function` ifadesinin
    KENDİSİ aranmalı; doğrulama saymamalı.
    """
    low = govde.lower()
    if "drop function" not in low:
        return False
    if re.search(rf"drop\s+function[^;]*\b{re.escape(fn)}\b", low):
        return True  # düz: drop function ... fn(...)
    # Dinamik katalog süpürmesi: pg_proc üzerinde proname='<fn>' + execute'lu drop
    return "pg_proc" in low and f"'{fn}'" in low


def test_KRITIK_ayni_RPC_farkli_arite_ile_tanimlaniyorsa_ESKISI_DUSURULUR(sql_bodies):
    """Aynı RPC iki farklı parametre sayısıyla tanımlanıyorsa, YENİ (geniş) imzayı getiren dosya
    eski imzaları DÜŞÜRMELİ. Aksi hâlde iki aşırı-yükleme birlikte yaşar ve az-argümanlı çağrılar
    belirsiz kalır (PGRST203) — üstelik yalnız SAHADA, heartbeat sustuğunda görünen bir arıza.

    ⚠️ "Başka bir dosyada drop var" YETMEZ: dosyalar ayrı ayrı ve farklı zamanlarda çalıştırılır.
    Düşürme, yeni imzayı getiren betiğin İÇİNDE olmalı ki tek başına çalıştırıldığında da güvenli
    olsun."""
    ariteler: dict[str, dict[str, set[int]]] = {}
    for ad, govde in sql_bodies.items():
        for m in _FN_TANIM.finditer(govde):
            fn = m.group(1).lower()
            ariteler.setdefault(fn, {}).setdefault(ad, set()).add(_parametre_sayisi(m.group(2)))

    for fn, dosyalar in ariteler.items():
        hepsi = set().union(*dosyalar.values())
        if len(hepsi) <= 1:
            continue  # tek arite → çakışma yok
        enis = max(hepsi)
        getirenler = [ad for ad, ar in dosyalar.items() if enis in ar]
        for ad in getirenler:
            assert _dusurme_var_mi(sql_bodies[ad], fn), (
                f"{ad}: `{fn}` en genis imzayi ({enis} parametre) getiriyor ama eski imzalari "
                f"DUSURMUYOR. Depoda su ariteler var: {sorted(hepsi)}. PostgreSQL ikinci bir "
                f"asiri-yukleme yaratir; az-argumanli cagrilar PGRST203 ile olur."
            )


def test_envanter_SQL_i_bcrypt_modelini_KORUR(sql_bodies):
    """İkinci kusur: envanter dosyasının ilk hâli sırrı DÜZ METİN karşılaştırıyordu
    (`device_secret` sütunu). Yayındaki v2 bcrypt kullanır (`secret_hash` + `crypt`). Envanter
    eklemek bir güvenlik modeli değişikliği DEĞİLDİR."""
    govde = sql_bodies.get("upsert_device_envanter.sql")
    if not govde:
        pytest.skip("envanter SQL'i yok")
    low = govde.lower()
    assert "secret_hash" in low and "crypt(" in low, "envanter SQL'i bcrypt modelini terk etmis"
    assert "d.device_secret" not in low and "devices.device_secret" not in low, (
        "duz-metin `device_secret` karsilastirmasi geri gelmis"
    )
    assert "grant execute on function public.upsert_device" in low, (
        "yeni imza icin `grant execute ... to anon` YOK — cihaz fonksiyonu cagiramaz"
    )


def test_KRITIK_jeton_defterindeki_tur_kisiti_CIHAZIN_gonderdiklerini_KAPSAR(sql_bodies):
    """8. parti: kullandikca-ode eklendiginde `servers/jeton.py` tuketimi `tur="kullandikca"`
    ile gonderiyordu ama `token_ledger.tur` CHECK kisiti bu degeri TANIMIYORDU. Sonuc: RPC
    check-ihlaliyle patlar ve TUKETIM KAYBOLUR (kullanici bedava analiz yapar; ya da daha
    kotusu, cevrimdisi uzlastirma sonsuza dek basarisiz doner).

    Bu, deponun 1 numaralı hata deseninin sema yuzeyi: ayni sozluk iki yerde, biri guncellenir.
    Kapi: cihazin gonderebilecegi HER `tur` degeri kisit listesinde olmalidir.
    """
    govde = sql_bodies.get("supabase_jetonlar.sql")
    if not govde:
        pytest.skip("jeton SQL'i yok")

    m = re.search(r"tur\s+text\s+not\s+null\s+check\s*\(\s*tur\s+in\s*\(([^)]*)\)", govde, re.S)
    assert m, "token_ledger.tur CHECK kisiti bulunamadi"
    izinli = set(re.findall(r"'([^']+)'", m.group(1)))

    # Cihaz tarafinin GERCEKTEN gonderdigi turler — kaynaktan okunur, elle yazilmaz.
    jeton_py = (_KOK / "servers" / "jeton.py").read_text(encoding="utf-8", errors="replace")
    gonderilen = set(re.findall(r'tur\s*=\s*"([a-z_]+)"', jeton_py))
    assert gonderilen, "servers/jeton.py icinde tur= gonderimi bulunamadi (test kor kalmis)"

    eksik = gonderilen - izinli
    assert not eksik, (
        f"CIHAZ su turleri gonderiyor ama SQL kisiti kabul ETMIYOR: {sorted(eksik)}. "
        f"Kisit listesi: {sorted(izinli)}. RPC check-ihlaliyle patlar, tuketim kaybolur."
    )


def test_KRITIK_jeton_tuket_KULLANDIKCA_dali_yetersiz_kapisindan_ONCE_gelir(sql_bodies):
    """8. parti mutasyonu M17 KACMISTI: `jeton_tuket` icindeki kullandikca-ode dali silinse
    hicbir test kirmizi olmuyordu. Oysa dal kalkarsa PAYG uyeler `sebep='yetersiz'` alir —
    yani "onden odeme yok" diye satilan uyelik, bakiyesi 0 oldugu icin HIC calismaz.

    Sira da onemli: dal, yetersiz-bakiye kapisindan ONCE gelmeli. Sonra gelirse kapi once
    reddeder ve dala hic ulasilmaz (sessiz olu kod).
    """
    govde = sql_bodies.get("supabase_jetonlar.sql")
    if not govde:
        pytest.skip("jeton SQL'i yok")

    dal = govde.find("odeme_modeli = 'kullandikca'")
    assert dal > -1, (
        "jeton_tuket icinde kullandikca-ode dali YOK — onden odemesiz uyelik bakiye 0 oldugu "
        "icin 'yetersiz' alir ve hic calismaz"
    )
    kapi = govde.find("'sebep', 'yetersiz'")
    assert kapi > -1, "yetersiz-bakiye kapisi kayboldu (on-odemeli plan artik sinirsiz)"
    assert dal < kapi, (
        "kullandikca dali yetersiz-bakiye kapisindan SONRA geliyor → kapi once reddeder, dal olu kod olur"
    )
    # Dal, tuketimi borca YAZMALI; yalnizca 'ok' donup kaydi dusurmek bedava kullanim demektir.
    kesit = govde[dal : dal + 800]
    assert "kullandikca_borc" in kesit and "insert into public.token_ledger" in kesit, (
        "kullandikca dali borcu artirmiyor ya da deftere yazmiyor → tuketim FATURALANAMAZ"
    )
