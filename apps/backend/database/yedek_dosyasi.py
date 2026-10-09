# -*- coding: utf-8 -*-
"""Yedek DOSYASININ kendisi — tedavi ve hasta DB'sinin `create_backup`ı ve bakım döngüsünün rotasyonu/tazeliği için TEK kaynak (2-D).

⚠️ D2.61 (B-3.70): başarısız bir yedek denemesi hedefte 0 baytlık (ya da yarım) dosya BIRAKIYORDU — iki DB'de de. SQLite yedek
API'si hata verince yazdığını geri alır ama hedef dosya zaten oluşmuştur [ÖLÇTÜM 2-D sondası: disk dolu → 0 B; şifreli kaynak →
düz hedef `TypeError` → 0 B]. Bu artık, rotasyonda sağlam bir yedeğin yuvasını alır ve "son yedek ne zaman" denetimini kandırır.

⚠️ D2.63 (B-3.20): yedek SON ADA doğrudan yazılmaz. Önce `<ad>.yazim.tmp`ye yazılır (rotasyon deseni `*.db` ile EŞLEŞMEZ), açılarak
doğrulanır (`PRAGMA quick_check`), ancak sonra `os.replace` ile son ada taşınır. Yazım ortasında süreç ölürse son adda yarım dosya
kalmaz; doğrulama düşerse son ad hiç oluşmaz. Rotasyon / tazelik de yalnız `yedek_acilir_mi` olan dosyaları sayar.

⚠️ D2.51 (B-3.22 · Y11 · A-32 · A-45): yedek aileleri hesapları (`auth_users`) ve SIRSIZ ayarları (`config`, `system_settings`) da
kapsar; rotasyon (yerel ve makine dışı) YALNIZ `yedek_ailesi` adını tanıdığı dosyalara dokunur. Yedekler tek dosyalık rollback-günlüğü
(DELETE) kipinde yazılır — WAL başlıklı yedek her açılışta yanına `-wal`/`-shm` açıyordu; SQLite WAL ağ dosya sistemlerinde çalışmaz.
Kapılar: tests/test_at_rest_bayragi_ve_yarim_yedek_D261.py · tests/test_yerel_yedek_penceresi_KORUNUR_D263.py ·
tests/test_offsite_ROTASYON_ve_yedek_KAPSAMI_D251_Y11_A32_A45.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3

_log = logging.getLogger(__name__)

#: Yazım sırasındaki geçici ad eki — `pemf_*_*.db` rotasyon desenine UYMAZ (yarım dosya hiçbir zaman "yedek" sayılmaz).
GECICI_EK = ".yazim.tmp"
_SQLITE_BASLIK = b"SQLite format 3\x00"

#: ⚠️ D2.51: yedek ailesi → uzantı. Bu kurulumun ürettiği (ve rotasyonun SİLEBİLECEĞİ) tek ad biçimi
#: `pemf_<aile>_<YYYYMMDD_HHMMSS><uzantı>`; başka her dosya (kullanıcı dosyası, elle alınmış kopya, zarf, not) yok sayılır.
YEDEK_AILELERI = {
    "treatment_history": ".db",
    "patients": ".db",
    "auth_users": ".db",
    "config": ".json",
    "system_settings": ".json",
}
_YEDEK_ADI = re.compile(r"pemf_([a-z_]+)_(\d{8}_\d{6})(\.db|\.json)")

#: Ayar yedeğinden ayıklanan anahtar ADLARI (A-32 "SIR hariç"): parola / jeton / API anahtarı / özel anahtar / kimlik bilgisi.
#: ⚠️ D2-2.1 (2-D incelemesi): `key` ile BİTEN adlar (kodun config.json'dan OKUDUĞU `supabase_key` dahil) ve kısa sır adları da.
_SIR_ANAHTARI = re.compile(
    r"pass|parola|sifre|şifre|secret|token|api_?key|private|credential|^user(name)?$"
    r"|key$|authorization|bearer|cookie|jwt|(^|_)(pin|pwd|otp|psk|salt|hmac|kod|kodu)($|_)",
    re.IGNORECASE,
)


def yedek_ailesi(ad: str):
    """`ad` bu kurulumun ürettiği bir yedek adıysa ailesini, değilse None döndürür (tam eşleşme, büyük/küçük harf duyarlı)."""
    m = _YEDEK_ADI.fullmatch(ad)
    if m is None or YEDEK_AILELERI.get(m.group(1)) != m.group(3):
        return None
    return m.group(1)


def gecici_yol(yol: str) -> str:
    return f"{yol}{GECICI_EK}"


def basarisiz_yedegi_kaldir(yol: str, logger) -> None:
    """Başarısız yedek denemesinin bıraktığı dosyayı (ve `-journal` / `-wal` / `-shm` eşlerini) kaldırır.

    Yalnız denemenin KENDİ yazdığı (geçici) dosyaya çağrılır. Silinen dosya veri taşımaz: kaynak DB yerinde ve sağlamdır. Hata
    YÜKSELTMEZ; kaldırılamazsa WARNING yazar — artığın varlığı operatörden saklanmaz."""
    for ek in ("", "-journal", "-wal", "-shm"):
        p = f"{yol}{ek}"
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            logger.warning("Basarisiz yedek artigi kaldirilamadi: %s — elle silin.", p, exc_info=True)


def yedek_acilir_mi(yol, sqlcipher_mod=None, anahtar: str = "", tam: bool = False) -> bool:
    """Dosya bir veritabanı olarak AÇILIYOR mu: boş değil, şeması okunuyor (şifreliyse verilen anahtarla); `tam` ise
    `PRAGMA quick_check` 'ok'. ASLA istisna atmaz.

    SQLite başlığı yoksa dosya şifrelidir: anahtar ya da bağlayıcı verilmemişse AÇILAMAZ sayılır (bilinmiyor ≠ geçerli)."""
    try:
        if os.path.getsize(yol) == 0:
            return False
        with open(yol, "rb") as f:
            duz = f.read(len(_SQLITE_BASLIK)) == _SQLITE_BASLIK
    except OSError:
        return False
    if not duz and (not anahtar or sqlcipher_mod is None):
        return False
    c = None
    try:
        c = sqlite3.connect(str(yol)) if duz else sqlcipher_mod.connect(str(yol))
        if not duz:
            c.execute("PRAGMA key='{}'".format(anahtar.replace("'", "''")))
        if int(c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]) <= 0:
            return False
        if tam:
            r = c.execute("PRAGMA quick_check").fetchone()
            return bool(r) and str(r[0]).strip().lower() == "ok"
        return True
    except Exception:
        # Yoklama: açılmaması BEKLENEN bir sonuçtur (çağıran WARNING/ERROR yazar); nedeni yine de saklanmaz.
        _log.debug("Yedek acilamadi / dogrulanamadi: %s", yol, exc_info=True)
        return False
    finally:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


def yedek_yaz(src_conn, yol: str, baglayici, anahtar: str, logger) -> None:
    """`src_conn`ın çevrimiçi yedeğini `yol`a GEÇİCİ AD → DOĞRULAMA → `os.replace` sırasıyla yazar. Başarısızlıkta istisna
    YÜKSELİR, son ad oluşmaz / önceden varsa DEĞİŞMEZ, geçici dosya kaldırılır.

    `baglayici`: hedefi açacak modül (`sqlite3` ya da sqlcipher3); `anahtar` boş değilse hedefe `PRAGMA key` uygulanır ve
    doğrulama aynı anahtarla yapılır."""
    gecici = gecici_yol(yol)
    basarisiz_yedegi_kaldir(gecici, logger)  # önceki çökmeden kalmış aynı adlı geçici (bizim artığımız)
    dst = None
    tamam = False
    try:
        dst = baglayici.connect(gecici)
        if anahtar:
            dst.execute("PRAGMA key='{}'".format(anahtar.replace("'", "''")))
        src_conn.backup(dst)
        # ⚠️ D2.51: yedek API'si kaynağın WAL başlığını (18-19 = 2) da kopyalıyordu → yedeği her açan (rotasyon doğrulaması, makine
        # dışı hedef, geri yükleme) yanına `-wal`/`-shm` açıyordu [ÖLÇTÜM 2-D sondası]. Yedek tek dosyalık DELETE kipine alınır;
        # geri yüklenen DB'yi uygulama açılışta yine WAL'a geçirir (üç DB de bağlantıda `journal_mode=WAL` yapar).
        kip = dst.execute("PRAGMA journal_mode=DELETE").fetchone()
        if not kip or str(kip[0]).lower() != "delete":
            logger.warning(
                "Yedek DELETE kipine alinamadi (kip=%s): %s — yedek gecerli, ama acilisinda -wal/-shm acar.", kip, yol
            )
        dst.commit()
        dst.close()
        dst = None
        if not yedek_acilir_mi(gecici, baglayici if anahtar else None, anahtar, tam=True):
            raise RuntimeError(f"yazilan yedek DOGRULANAMADI (acilmiyor / quick_check basarisiz): {gecici}")
        os.replace(gecici, yol)
        tamam = True
    finally:
        if dst is not None:
            try:
                dst.close()
            except Exception:
                pass
        if not tamam:
            basarisiz_yedegi_kaldir(gecici, logger)


def _kapat(*baglantilar) -> None:
    for c in baglantilar:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


def duz_dbyi_yedekle(kaynak: str, yol: str, sqlcipher_mod, anahtar: str, logger) -> None:
    """⚠️ D2.51 (A-32): DÜZ (şifresiz) bir SQLite DB'sinin — operatör hesapları `auth_users.db` — doğrulanmış yedeği.

    `anahtar` doluysa (şifreli kurulum) yedek O ANAHTARLA ŞİFRELİ yazılır: kaynak bellekte tutarlı bir anlık görüntüye alınır, oradan
    SQLCipher `sqlcipher_export` ile şifreli geçici dosyaya aktarılır. Kaynak düz olsa da yedeği makine dışına düz GİTMEZ (e-posta +
    6 haneli PIN özeti çevrimdışı kaba kuvvete açıktır). Anahtar boşsa (düz kurulum) `yedek_yaz` ile düz yedek. Geçici ad → doğrulama
    → `os.replace`; başarısızlıkta istisna YÜKSELİR, son ad oluşmaz. Geri yükleme: `sifreli_yedegi_duze_coz`."""
    if not anahtar:
        src = sqlite3.connect(str(kaynak), timeout=10.0)
        try:
            yedek_yaz(src, yol, sqlite3, "", logger)
        finally:
            _kapat(src)
        return
    gecici = gecici_yol(yol)
    basarisiz_yedegi_kaldir(gecici, logger)
    src = bellek = None
    tamam = False
    try:
        src = sqlcipher_mod.connect(str(kaynak), timeout=10.0)  # düz kaynak: anahtar UYGULANMAZ
        bellek = sqlcipher_mod.connect(":memory:")
        src.backup(bellek)
        _kapat(src)
        src = None
        bellek.execute("ATTACH DATABASE ? AS yedek KEY ?", (gecici, anahtar))
        bellek.execute("SELECT sqlcipher_export('yedek')")
        bellek.execute("DETACH DATABASE yedek")
        _kapat(bellek)
        bellek = None
        if not yedek_acilir_mi(gecici, sqlcipher_mod, anahtar, tam=True):
            raise RuntimeError(f"sifreli hesap yedegi DOGRULANAMADI: {gecici}")
        os.replace(gecici, yol)
        tamam = True
    finally:
        _kapat(src, bellek)
        if not tamam:
            basarisiz_yedegi_kaldir(gecici, logger)


def sifreli_yedegi_duze_coz(yedek: str, cikti: str, sqlcipher_mod, anahtar: str, logger) -> None:
    """⚠️ D2.51 (A-32): `duz_dbyi_yedekle`nin şifreli çıktısını düz SQLite'a çözer — geri yükleme (`tools/kurtarma.py
    --hesap-yedegi`). `cikti` VARSA dokunulmaz (istisna). Geçici ad → `sqlite3` ile doğrulama → `os.replace`; yanlış anahtar ya da
    bozuk yedek → istisna, çıktı OLUŞMAZ."""
    if os.path.exists(cikti):
        raise FileExistsError(f"cikti zaten var, uzerine yazilmaz: {cikti}")
    gecici = gecici_yol(cikti)
    basarisiz_yedegi_kaldir(gecici, logger)
    c = None
    tamam = False
    try:
        c = sqlcipher_mod.connect(str(yedek))
        c.execute("PRAGMA key='{}'".format(anahtar.replace("'", "''")))
        c.execute("ATTACH DATABASE ? AS duz KEY ''", (gecici,))
        c.execute("SELECT sqlcipher_export('duz')")
        c.execute("DETACH DATABASE duz")
        _kapat(c)
        c = None
        if not yedek_acilir_mi(gecici, tam=True):
            raise RuntimeError(f"cozulen hesap yedegi DOGRULANAMADI: {gecici}")
        os.replace(gecici, cikti)
        tamam = True
    finally:
        _kapat(c)
        if not tamam:
            basarisiz_yedegi_kaldir(gecici, logger)


def sirsiz_ayarlar(veri, sir_yollari=frozenset()):
    """⚠️ D2.51 (A-32 "SIR dosyaları hariç"): ayar sözlüğünün SIRSIZ kopyası ve ayıklanan noktalı yolların listesi.

    Ayıklanır: `sir_yollari`ndaki yollar (config yöneticisinin şifrelediği anahtarlar), adı sır gibi görünen anahtarlar (`_SIR_ANAHTARI`)
    ve `enc:` önekli (config şifreli) her değer. Şifreli değer de ayıklanır: makine dışında işe yaramaz, anahtarı (`.pemf_key`) yedeğe
    girmez. Geri yüklemede bu alanlar yeniden girilir."""
    ayiklanan = []

    def _gez(d, yol):
        if isinstance(d, dict):
            temiz = {}
            for k, v in d.items():
                tam = f"{yol}.{k}" if yol else str(k)
                if tam in sir_yollari or _SIR_ANAHTARI.search(str(k)) or (isinstance(v, str) and v.startswith("enc:")):
                    ayiklanan.append(tam)
                    continue
                temiz[k] = _gez(v, tam)
            return temiz
        if isinstance(d, list):
            liste = []
            for i, x in enumerate(d):
                if isinstance(x, str) and x.startswith("enc:"):
                    ayiklanan.append(f"{yol}[{i}]")
                    continue
                liste.append(_gez(x, f"{yol}[{i}]"))
            return liste
        return d

    return _gez(veri, ""), ayiklanan


def json_yedegi_gecerli_mi(yol) -> bool:
    """JSON yedeği AÇILIYOR mu: boş değil, kökü sözlük olan geçerli JSON. ASLA istisna atmaz."""
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return isinstance(json.load(f), dict)
    except Exception:
        _log.debug("JSON yedegi acilamadi / gecersiz: %s", yol, exc_info=True)
        return False


def json_yedegi_yaz(veri: dict, yol: str, logger) -> None:
    """⚠️ D2.51: ayar yedeği — GEÇİCİ AD → fsync → geri okuyup EŞİTLİK doğrulaması → `os.replace`. Başarısızlıkta istisna YÜKSELİR,
    son ad oluşmaz, geçici kaldırılır."""
    gecici = gecici_yol(yol)
    basarisiz_yedegi_kaldir(gecici, logger)
    tamam = False
    try:
        with open(gecici, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(veri, ensure_ascii=False, indent=2, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        with open(gecici, "r", encoding="utf-8") as f:
            if json.load(f) != veri:
                raise RuntimeError(f"ayar yedegi geri okunamadi / esit degil: {gecici}")
        os.replace(gecici, yol)
        tamam = True
    finally:
        if not tamam:
            basarisiz_yedegi_kaldir(gecici, logger)
