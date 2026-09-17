# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""URUN SENARYOLARI — SEVK EDILEN EXE uzerinde olcum (test suiti DEGIL, onun YERINE de gecmez).

⚠️ NEDEN VAR: 2026-09-13'te birim testler YESILKEN urun hasta gecmisini kaybediyordu —
ucuncu bir yol (sablon kopyalayici) once davraniyordu ve hicbir test o sirayi gormuyordu.
Suit "fonksiyon dogru mu" diye sorar; bu betik "SEVK EDILEN IKILI, GERCEK DISKTE, GERCEK
ACILIS SIRASIYLA dogru mu" diye sorar. Ikisi ayri sorulardir.

⚠️ NASIL OKUNUR: her senaryo bir KANIT satiri basar. "Gecti" yetmez — kanit satiri, kapinin
BEDAVAYA yesillenmedigini de gostermelidir. Bu yuzden takim KARSIT-KANIT senaryolari tasir
(A0, B9b, C0): olculen ozellik KAPALIYKEN olcumun KIRMIZI dondugunu ispatlarlar.

Kullanim:
    python scripts/urun_senaryolari.py [A|B|C|D|HEPSI] [--exe <yol>]

    A  veri yolu (goc, yarim goc, emanet, idempotans, kalicilik)
    B  sunulan urun yuzeyi (arayuz, onbellek, AI hazirligi, kod korumasi, rota yuzeyi)
    C  guvenlik degismezleri (jeton, auth, saglik ucu sizintisi)
    D  bozuk sir dosyasi (fail-closed -> yeni anahtar URETILMEMELI)

EXE yolu: --exe, yoksa PEMF_EXE ortam degiskeni, yoksa depo ici varsayilan build ciktisi.
⚠️ Betik ONCE BAYAT-IKILI NOBETI koşar: EXE kaynaklardan eskiyse olcum ANLAMSIZDIR ve durur.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

GUII = Path(__file__).resolve().parents[1]


def _exe_yolu() -> Path:
    if "--exe" in sys.argv:
        return Path(sys.argv[sys.argv.index("--exe") + 1]).resolve()
    if os.getenv("PEMF_EXE", "").strip():
        return Path(os.environ["PEMF_EXE"]).resolve()
    return GUII / "PEMF_BUILD" / "dist" / "PEMF_Backend" / "PEMF_Backend.exe"


EXE = _exe_yolu()
# ⚠️ Calisma alani DEPO AGACININ DISINDA: senaryolar ACL-kilitli dosyalar ve bozuk sir
# dosyalari uretir; bunlarin depoya ya da kullanicinin gercek veri koküne sizmasi
# istenmez (izolasyon notu: `main` makine anahtar deposunu once/sonra karsilastirir).
CALISMA = Path(tempfile.gettempdir()) / "pemf_urun_senaryo"
TOHUM = CALISMA / "_tohum_duz"

HASTA_DB = "patients.db"
TEDAVI_DB = "pemf_treatment_history.db"

# Korunmasi gereken gruplar (SID ile — Windows Turkce'de grup ADLARI yerellestirilir).
YASAK_SIDLER = {"S-1-5-32-545": "Users", "S-1-5-11": "Authenticated Users", "S-1-1-0": "Everyone"}

SONUCLAR: list[tuple[str, str, bool, str]] = []
TOHUM_SAGLIK: dict = {}
_port = 8200


def kayit(kod: str, baslik: str, gecti: bool, kanit: str) -> None:
    SONUCLAR.append((kod, baslik, gecti, kanit))
    print(f"  {'✓' if gecti else '⛔'} {kod} {baslik}\n      {kanit}")


# ═══════════════════════════════════════════════════════════════════════════════
# ALTYAPI
# ═══════════════════════════════════════════════════════════════════════════════


def bayat_ikili_nobeti() -> None:
    """⚠️ EXE kaynaklardan ESKIYSE butun olcum ANLAMSIZDIR."""
    if not EXE.exists():
        raise SystemExit(
            f"[DUR] EXE yok: {EXE}\n      Once paketleyin (scripts/build_backend_exe.ps1) ya da --exe ile yol verin."
        )
    e = EXE.stat().st_mtime
    izlenen = [
        "database/sqlcipher_util.py",
        "database/treatment_history_db.py",
        "database/patient_database.py",
        "utils/path_utils.py",
        "utils/file_acl.py",
        "utils/runtime_guards.py",
        "servers/api_server.py",
        "servers/ai_router.py",
        "servers/jeton.py",
        "backend_service.py",
    ]
    bayat = [k for k in izlenen if (GUII / k).exists() and (GUII / k).stat().st_mtime > e]
    if bayat:
        raise SystemExit(f"[DUR] EXE BAYAT — sonradan degismis kaynaklar: {bayat}")
    print(f"[nobet] EXE taze ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e))}) -> olcum gecerli\n")


def sid_listesi(yol: Path) -> list[str]:
    """Dosyanin DACL'indeki kimlikleri SID olarak dondurur (ad degil — yerellestirme tuzagi)."""
    ps = (
        "$a=(Get-Acl -LiteralPath '%s').Access; "
        "foreach($e in $a){ try { "
        "$e.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value "
        "} catch { $e.IdentityReference.Value } }" % str(yol).replace("'", "''")
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
    return [s.strip() for s in r.stdout.splitlines() if s.strip()]


def acl_kilitle(yol: Path) -> bool:
    """Urunun `lock_down_file(keep_current_user=False)` ile yaptiginin AYNISI (senaryo kurulumu)."""
    args = [
        "icacls",
        str(yol),
        "/inheritance:r",
        "/remove:g",
        "*S-1-5-32-545",
        "/remove:g",
        "*S-1-5-11",
        "/grant:r",
        "*S-1-5-18:F",
        "/grant:r",
        "*S-1-5-32-544:F",
    ]
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def acl_geri_ac(hedef: Path) -> None:
    """Kilitlenmis dosyalari temizleyebilmek icin erisimi geri al (dosya SAHIBI biziz)."""
    subprocess.run(
        ["icacls", str(hedef), "/reset", "/T", "/C", "/Q"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    subprocess.run(
        ["icacls", str(hedef), "/grant", f"{os.environ.get('USERNAME', '')}:(OI)(CI)F", "/T", "/C", "/Q"],
        capture_output=True,
        text=True,
        timeout=120,
    )


def sil(yol: Path) -> None:
    if not yol.exists():
        return
    shutil.rmtree(yol, ignore_errors=True)
    if yol.exists():
        acl_geri_ac(yol)
        shutil.rmtree(yol, ignore_errors=True)


def veri_koku(veri: Path) -> Path:
    return veri / "PEMF_GUI"


def kostur(veri: Path, sifreli: bool, ek: dict | None = None, sure: int = 180, saglik_bekle: bool = True):
    """EXE'yi baslat, /api/health yesillenene kadar bekle. (surec, log_yolu, ayakta_mi, port)"""
    global _port
    _port += 1
    port = _port
    ortam = dict(os.environ)
    for k in ("PEMF_KEEP_PLAIN_BACKUP", "PEMF_KEEP_PLAIN_BAK", "PEMF_JETON_ENFORCED"):
        ortam.pop(k, None)
    ortam.update(
        {
            "PEMF_DATA_DIR": str(veri),
            "APPDATA": str(veri),
            "PEMF_ENCRYPT_AT_REST": "1" if sifreli else "0",
            "PEMF_SIMULATE": "1",
            "PEMF_ESP_ENABLED": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    ortam.update(ek or {})
    log = CALISMA / f"_log_{veri.name}_{port}.txt"
    f = log.open("w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(
        [str(EXE), "--port", str(port), "--no-mosquitto-ensure", "--no-headless-services"],
        env=ortam,
        stdout=f,
        stderr=subprocess.STDOUT,
    )
    son = time.monotonic() + sure
    ayakta = False
    while time.monotonic() < son:
        if p.poll() is not None:
            break
        if saglik_bekle:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                    if r.status == 200:
                        ayakta = True
                        break
            except Exception:
                pass
        time.sleep(1.0)
    f.close()
    return p, log, ayakta, port


def durdur(p) -> None:
    try:
        p.terminate()
        p.wait(timeout=30)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def http(port: int, yol: str, yontem: str = "GET", govde=None, zaman: float = 30.0, basliklar=None):
    url = f"http://127.0.0.1:{port}{yol}"
    veri = json.dumps(govde).encode() if govde is not None else None
    istek = urllib.request.Request(url, data=veri, method=yontem)
    if veri is not None:
        istek.add_header("Content-Type", "application/json")
    for k, v in (basliklar or {}).items():
        istek.add_header(k, v)
    try:
        with urllib.request.urlopen(istek, timeout=zaman) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return -1, str(e).encode(), {}


def bicim(yol: Path) -> str:
    if not yol.exists():
        return "YOK"
    return "duz" if yol.read_bytes()[:16].startswith(b"SQLite format 3") else "SQLCipher"


def log_metni(log: Path, veri: Path | None = None) -> str:
    """stdout yakalamasi + URUNUN KENDI log dosyasi.

    ⚠️ ILK YAZIMDA YALNIZ stdout'a bakiyordum ve A5b/A6b KIRMIZI dondu — URUN DEGIL KOSUM
    TAKIMI yanlisti: backend satirlari `<veri>/PEMF_GUI/logs/backend_service.log`a yaziyor.
    "Log'da yok" demeden ONCE urunun log'u NEREYE yazdigini olc.
    """
    parcalar = []
    for y in [log] + ([veri_koku(veri) / "logs" / "backend_service.log"] if veri else []):
        try:
            parcalar.append(y.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return "\n".join(parcalar)


def tohum_uret() -> bool:
    """Bir kez duz DB'ler uret, sonra her senaryo icin KOPYALA (12 acilis tasarrufu).

    ⚠️ SEMA UYDURULMAZ: v1'de `.plain.bak`i elde kurdugum oyuncak semayla (id, patient_name)
    olusturmustum; kurtarma calisti ama urun `session_date` indeksinde patladi. Sema URUNUN
    KENDISINE urettirilir; kayitlar da URUNUN API'sinden girilir.
    """
    sil(TOHUM)
    TOHUM.mkdir(parents=True, exist_ok=True)
    print("[tohum] urun duz-metin DB'lerini uretsin (bir kez)...")
    global TOHUM_SAGLIK
    p, log, ok, port = kostur(TOHUM, sifreli=False)
    if ok:
        http(
            port, "/api/patients", "POST", {"name": "TohumHasta", "species": "Kedi", "breed": "Tekir", "owner": "Olcum"}
        )
        _, g, _h = http(port, "/api/health")
        try:
            TOHUM_SAGLIK = json.loads(g or b"{}")
        except Exception:
            TOHUM_SAGLIK = {}
    durdur(p)
    if not ok:
        print("  [!] tohum: duz acilis basarisiz; son satirlar:")
        print("      " + "\n      ".join(log_metni(log).splitlines()[-8:]))
        return False
    kok = veri_koku(TOHUM)
    # Kurtarilabilirligi ISPATLAYACAK kayitlari URUNUN semasina yaz.
    for db, sql, deger in (
        (
            TEDAVI_DB,
            "INSERT INTO treatment_sessions (patient_name, session_date, start_time, treatment_mode) VALUES (?,?,?,?)",
            ("TohumHasta", "2026-09-17", "16:00:00", "Manuel"),
        ),
    ):
        y = kok / db
        if not y.exists():
            continue
        c = sqlite3.connect(str(y))
        try:
            c.execute(sql, deger)
            c.commit()
        finally:
            c.close()
    dosyalar = sorted(x.name for x in kok.glob("*") if x.is_file())
    print(f"[tohum] hazir: {dosyalar}\n")
    return True


def tohumdan(ad: str) -> Path:
    hedef = CALISMA / ad
    sil(hedef)
    shutil.copytree(TOHUM, hedef)
    return hedef


def bak_dosyalari(kok: Path) -> list[str]:
    return sorted(x.name for x in kok.glob("*.plain.bak*"))


# ═══════════════════════════════════════════════════════════════════════════════
# A GRUBU — VERI YOLU
# ═══════════════════════════════════════════════════════════════════════════════


def grup_a() -> None:
    print("═" * 78)
    print("A GRUBU — VERI YOLU (donmus EXE, izole veri koku)")
    print("═" * 78)

    # ── A0 · KARSIT KANIT: sifreleme KAPALIYKEN saglik ucu "sifreli" DEMEMELI ─
    # Bu olmadan A1'in `atRestEncrypted=True`si hicbir sey kanitlamaz: alan SABIT True
    # donuyor olabilirdi.
    kayit(
        "A0",
        "KARSIT KANIT: sifreleme KAPALI iken /api/health atRestEncrypted=false",
        TOHUM_SAGLIK.get("atRestEncrypted") is False,
        f"tohum (PEMF_ENCRYPT_AT_REST=0) saglik: atRestEncrypted={TOHUM_SAGLIK.get('atRestEncrypted')} "
        f"dbReady={TOHUM_SAGLIK.get('dbReady')}",
    )

    # ── A1 · Sifirdan sifreli kurulum: diskte HIC duz-metin DB olusmamali ──────
    veri = CALISMA / "a1"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    p, log, ok, _ = kostur(veri, sifreli=True)
    durdur(p)
    kok = veri_koku(veri)
    dbler = {d: bicim(kok / d) for d in (HASTA_DB, TEDAVI_DB)}
    baklar = bak_dosyalari(kok)
    kayit(
        "A1",
        "Sifirdan sifreli kurulum -> diskte duz-metin DB YOK",
        ok and all(v == "SQLCipher" for v in dbler.values()) and not baklar,
        f"backend={'ayakta' if ok else 'DUSTU'} | {dbler} | .plain.bak={baklar or 'yok'}",
    )

    # ── A2/A3/A4 · Duz -> sifreli goc, IKI DB, varsayilan politika ────────────
    veri = tohumdan("a2")
    kok = veri_koku(veri)
    once = {d: bicim(kok / d) for d in (HASTA_DB, TEDAVI_DB)}
    p, log, ok, port = kostur(veri, sifreli=True)
    # ⚠️ "SQLCipher basligi" veriyi TASIDIGINI kanitlamaz — icerik URUNDEN okunmali.
    goc_icerik = None
    if ok:
        s, g, _ = http(port, "/api/patients")
        j = json.loads(g or b"{}")
        goc_icerik = (s, [h.get("name") for h in (j.get("data") or [])])
    durdur(p)
    sonra = {d: bicim(kok / d) for d in (HASTA_DB, TEDAVI_DB)}
    kayit(
        "A2",
        "Duz -> SQLCipher goc: HASTA DB",
        once[HASTA_DB] == "duz" and sonra[HASTA_DB] == "SQLCipher",
        f"{HASTA_DB}: {once[HASTA_DB]} -> {sonra[HASTA_DB]}",
    )
    kayit(
        "A3",
        "Duz -> SQLCipher goc: TEDAVI DB (ayni acilis)",
        once[TEDAVI_DB] == "duz" and sonra[TEDAVI_DB] == "SQLCipher",
        f"{TEDAVI_DB}: {once[TEDAVI_DB]} -> {sonra[TEDAVI_DB]}",
    )
    kayit(
        "A3b",
        "Goc VERIYI tasidi (baslik degil, URUN API'sinden okunan icerik)",
        bool(goc_icerik) and goc_icerik[0] == 200 and "TohumHasta" in (goc_icerik[1] or []),
        f"goc SONRASI GET /api/patients -> {goc_icerik}",
    )
    baklar = bak_dosyalari(kok)
    kayit(
        "A4",
        "Varsayilan politika: IKI duz-metin yedek de GUVENLI-SILINDI",
        not baklar,
        f"kalan .plain.bak: {baklar or 'YOK (beklenen)'}",
    )
    a2_veri = veri  # A10 bunu yeniden kullanir

    # ── A5 · Emanet ACIK (kanonik ad) -> IKI yedek de saklanir VE ACL-kilitli ──
    veri = tohumdan("a5")
    kok = veri_koku(veri)
    p, log, ok, _ = kostur(veri, sifreli=True, ek={"PEMF_KEEP_PLAIN_BACKUP": "1"})
    durdur(p)
    baklar = bak_dosyalari(kok)
    # ⚠️ "yasak grup YOK" TEK BASINA HICBIR SEY KANITLAMAZ: bu dizin kullanici profilinde ve
    # oradaki dosyalarda `Users`/`Everyone` ZATEN yoktur — kapi BEDAVAYA yesillenirdi. Kilidin
    # imzasi, `lock_down_file(keep_current_user=False)`in SURECI CALISTIRAN HESABI da cikarmasi.
    # Bu yuzden AYNI DIZINDE kilitlenMEyen bir kontrol dosyasiyla karsilastiriliyor.
    kullanici = os.environ.get("USERNAME", "")
    kontrol = kok / "device_id.txt"
    kontrol_kimlikler = sid_listesi(kontrol) if kontrol.exists() else []
    acl_sonuc = {}
    for b in baklar:
        sidler = sid_listesi(kok / b)
        acl_sonuc[b] = {
            "yasak_grup": sorted(YASAK_SIDLER[s] for s in sidler if s in YASAK_SIDLER),
            "kimlik_sayisi": len(sidler),
        }
    iki_yedek = {f"{HASTA_DB}.plain.bak", f"{TEDAVI_DB}.plain.bak"} <= set(baklar)
    hic_yasak_yok = all(not v["yasak_grup"] for v in acl_sonuc.values()) and bool(acl_sonuc)
    # Kilitli yedekler kontrol dosyasindan DAHA AZ kimlik tasimali (kullanici cikarilmis).
    daraltildi = bool(kontrol_kimlikler) and all(
        v["kimlik_sayisi"] < len(kontrol_kimlikler) for v in acl_sonuc.values()
    )
    kayit(
        "A5",
        "Emanet ACIK (PEMF_KEEP_PLAIN_BACKUP=1) -> IKI yedek saklandi + ACL GERCEKTEN daraltildi",
        iki_yedek and hic_yasak_yok and daraltildi,
        f"yedekler={baklar} | kilitli DACL={acl_sonuc} | "
        f"kontrol device_id.txt kimlik sayisi={len(kontrol_kimlikler)} "
        f"(kullanici '{kullanici}' kontrolde VAR, yedekte YOK olmali)",
    )
    # A5b — log GERCEGI mi soyluyor? (urunun KENDI log dosyasi dahil)
    metin = log_metni(log, veri)
    kayit(
        "A5b",
        "Emanet log'u GERCEGI soyluyor (ACL-kilitli beyani, IKI DB icin ayri etiketle)",
        metin.count("ESCROW saklandı (ACL-kilitli)") >= 2
        and "DB plaintext" in metin
        and "Tedavi DB plaintext" in metin,
        f"'ESCROW ... ACL-kilitli' satir sayisi={metin.count('ESCROW saklandı (ACL-kilitli)')} | "
        f"etiketler: DB={'✓' if 'DB plaintext' in metin else '✗'} "
        f"Tedavi DB={'✓' if 'Tedavi DB plaintext' in metin else '✗'}",
    )

    # ── A6 · ESKI ad hala onurlandiriliyor + uyariyor ─────────────────────────
    veri = tohumdan("a6")
    kok = veri_koku(veri)
    p, log, ok, _ = kostur(veri, sifreli=True, ek={"PEMF_KEEP_PLAIN_BAK": "1"})
    durdur(p)
    baklar = bak_dosyalari(kok)
    metin = log_metni(log, veri)
    # IKI DB de ayri ayri uyarmali — tek uyari, bayragin yalniz bir tarafta okundugu
    # ESKI (ayrisik) davranisla ayni goruntuyu verirdi.
    uyari_sayisi = metin.count("ESKI bir addir")
    uyardi = uyari_sayisi >= 2
    kayit(
        "A6",
        "ESKI ad (PEMF_KEEP_PLAIN_BAK=1) IKI DB icin de onurlandirildi",
        {f"{HASTA_DB}.plain.bak", f"{TEDAVI_DB}.plain.bak"} <= set(baklar),
        f"yedekler={baklar}  (A1 oncesi bu bayrak YALNIZ tedavi DB'sini etkiliyordu)",
    )
    kayit(
        "A6b",
        "ESKI ad uyarisi IKI DB icin de verildi (sessiz kabul degil)",
        uyardi,
        f"'ESKI bir addir' uyari sayisi={uyari_sayisi} (>=2 beklenir: hasta + tedavi)",
    )

    # ── A7 · Yarim goc: HASTA DB toparlandi ───────────────────────────────────
    veri = tohumdan("a7")
    kok = veri_koku(veri)
    db, yedek = kok / HASTA_DB, kok / (HASTA_DB + ".plain.bak")
    shutil.move(str(db), str(yedek))
    boy = yedek.stat().st_size
    p, log, ok, _ = kostur(veri, sifreli=True)
    durdur(p)
    kayit(
        "A7",
        "Yarim goc toparlandi: HASTA DB (db YOK + .plain.bak VAR)",
        ok and db.exists() and bicim(db) == "SQLCipher",
        f"backend={'ayakta' if ok else 'DUSTU'} | {HASTA_DB}: {bicim(db)} "
        f"({db.stat().st_size if db.exists() else 0} B, yedek {boy} B)",
    )

    # ── A8 · Yarim goc + ACL-KILITLI yedek (2026-09-13 saha arizasi) ──────────
    veri = tohumdan("a8")
    kok = veri_koku(veri)
    db, yedek = kok / TEDAVI_DB, kok / (TEDAVI_DB + ".plain.bak")
    shutil.move(str(db), str(yedek))
    kilit_ok = acl_kilitle(yedek)
    sidler_once = [YASAK_SIDLER[s] for s in sid_listesi(yedek) if s in YASAK_SIDLER]
    p, log, ok, _ = kostur(veri, sifreli=True)
    durdur(p)
    metin = log_metni(log, veri)
    kayit(
        "A8",
        "ACL-KILITLI yedekten toparlama (2026-09-13 saha arizasi sinifi)",
        ok and db.exists(),
        f"kilit kuruldu={kilit_ok} (yasak grup: {sidler_once or 'yok'}) | "
        f"backend={'ayakta' if ok else 'DUSTU'} | {TEDAVI_DB}: {bicim(db)} | "
        f"log'da 'gevsetildikten sonra': {'VAR' if 'gevsetildikten sonra' in metin else 'yok (ilk denemede gecti)'}",
    )

    # ── A9 · Onceki yedek SILINMEZ, kenara alinir ─────────────────────────────
    veri = tohumdan("a9")
    kok = veri_koku(veri)
    db = kok / TEDAVI_DB
    eski = kok / (TEDAVI_DB + ".plain.bak")
    shutil.copy2(str(db), str(eski))  # db VAR + .plain.bak VAR  -> toparlama TETIKLENMEZ
    imza = eski.stat().st_size
    p, log, ok, _ = kostur(veri, sifreli=True)
    durdur(p)
    kenara = [b for b in bak_dosyalari(kok) if b.startswith(f"{TEDAVI_DB}.plain.bak.")]
    kayit(
        "A9",
        "Onceki duz-metin yedek SILINMEDI -> zaman damgali ada alindi",
        bool(kenara),
        f"kenara alinan: {kenara or 'YOK'} (kaynak {imza} B) | tum yedekler: {bak_dosyalari(kok)}",
    )

    # ── A10 · Idempotans: sifreli DB ile iki kez daha ac ──────────────────────
    kok = veri_koku(a2_veri)
    boy_once = {d: (kok / d).stat().st_size for d in (HASTA_DB, TEDAVI_DB) if (kok / d).exists()}
    ayakta = []
    for i in range(2):
        p, log, ok, _ = kostur(a2_veri, sifreli=True)
        durdur(p)
        ayakta.append(ok)
    sonra_b = {d: bicim(kok / d) for d in (HASTA_DB, TEDAVI_DB)}
    yeni_bak = bak_dosyalari(kok)
    kayit(
        "A10",
        "Idempotans: sifreli DB ile 2 yeniden acilis -> yeniden-goc YOK",
        all(ayakta) and all(v == "SQLCipher" for v in sonra_b.values()) and not yeni_bak,
        f"acilislar={ayakta} | {sonra_b} | yeni .plain.bak={yeni_bak or 'yok'} | ilk boyutlar={boy_once}",
    )

    # ── A11 · Uctan uca kalicilik: API ile yaz -> yeniden baslat -> oku ───────
    veri = CALISMA / "a11"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    p, log, ok, port = kostur(veri, sifreli=True)
    yazildi = None
    if ok:
        s, g, _ = http(
            port,
            "/api/patients",
            "POST",
            {"name": "KaliciHasta", "species": "Kedi", "breed": "Tekir", "owner": "Olcum"},
        )
        yazildi = (s, json.loads(g or b"{}").get("patient_id", ""))
    durdur(p)
    kok = veri_koku(veri)
    hasta_bicim = bicim(kok / HASTA_DB)
    p2, log2, ok2, port2 = kostur(veri, sifreli=True)
    okundu = None
    if ok2:
        s2, g2, _ = http(port2, "/api/patients")
        j = json.loads(g2 or b"{}")
        adlar = [h.get("name") for h in (j.get("data") or [])]
        okundu = (s2, adlar)
    durdur(p2)
    basarili = bool(yazildi and yazildi[0] == 200 and okundu and "KaliciHasta" in (okundu[1] or []))
    kayit(
        "A11",
        "Uctan uca kalicilik: sifreli DB'ye yaz -> yeniden baslat -> oku",
        basarili and hasta_bicim == "SQLCipher",
        f"yazma={yazildi} | dosya bicimi={hasta_bicim} | yeniden okuma={okundu}",
    )

    # ── A12 · Bayat `.enc.tmp` artigi SAGLAM db'nin uzerine YAZILMAMALI ───────
    # Goc, `.enc.tmp` -> `db` diye ikinci bir tasima yapar. Onceki turdan kalan bir
    # `.enc.tmp` (surec o pencerede oldu) sonraki aciliste KORU DB'yi ezerse klinik
    # gecmisi bayat/bos bir kopyayla degisir.
    veri = tohumdan("a12")
    kok = veri_koku(veri)
    db = kok / HASTA_DB  # icerigi API'den okunabilen DB secildi
    tuzak = kok / (HASTA_DB + ".enc.tmp")
    c = sqlite3.connect(str(tuzak))  # icerigi ALAKASIZ, bayat bir dosya
    c.execute("CREATE TABLE bayat (x INTEGER)")
    c.commit()
    c.close()
    saglam_boy, tuzak_boy = db.stat().st_size, tuzak.stat().st_size
    p, log, ok, port = kostur(veri, sifreli=True)
    icerik = None
    if ok:
        s, g, _ = http(port, "/api/patients")
        icerik = [h.get("name") for h in (json.loads(g or b"{}").get("data") or [])]
    durdur(p)
    kayit(
        "A12",
        "Bayat `.enc.tmp` artigi SAGLAM hasta DB'sini EZMEDI",
        ok and db.exists() and "TohumHasta" in (icerik or []),
        f"tuzak={HASTA_DB}.enc.tmp ({tuzak_boy} B) | acilis={'ayakta' if ok else 'DUSTU'} | "
        f"{HASTA_DB}: {bicim(db)} ({saglam_boy} -> {db.stat().st_size if db.exists() else 0} B) | "
        f"hastalar={icerik}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B GRUBU — SUNULAN URUN YUZEYI (tek backend)
# ═══════════════════════════════════════════════════════════════════════════════


def grup_b() -> None:
    print("═" * 78)
    print("B GRUBU — SUNULAN URUN YUZEYI (tek backend)")
    print("═" * 78)
    veri = CALISMA / "b"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    p, log, ok, port = kostur(veri, sifreli=True)
    if not ok:
        kayit("B0", "backend acilisi", False, f"backend DUSTU; log={log}")
        durdur(p)
        return
    try:
        # ── B1 · Ana React arayuzu GERCEKTEN sunuluyor ────────────────────────
        s, govde, bas = http(port, "/")
        html = govde.decode("utf-8", "replace")
        import re as _re

        # ⚠️ ILK YAZIMDA `/assets/` (Vite deseni) ARIYORDUM ve B1 KIRMIZI dondu — URUN
        # DEGIL KOSUM TAKIMI yanlisti: bu arayuz bir Expo web paketi, varliklar
        # `/_expo/static/js/web/...` altinda. Deseni VARSAYMA, sunulan belgeden TOPLA.
        varliklar = _re.findall(r'(?:src|href)="(/[^"]+\.(?:js|css))"', html)
        varlik_durum = []
        for v in varliklar[:3]:
            vs, vg, vb = http(port, v)
            varlik_durum.append((v.rsplit("/", 1)[-1], vs, len(vg)))
        kayit(
            "B1",
            "Ana React arayuzu sunuluyor (denetim 'olu' demisti)",
            s == 200
            and "text/html" in bas.get("content-type", "")
            and bool(varlik_durum)
            and all(d[1] == 200 for d in varlik_durum),
            f"GET / -> {s} ({len(govde)} B) | index'teki varliklar: {varlik_durum}",
        )

        # ── B2 · Simulator sunuluyor ──────────────────────────────────────────
        s2, g2, b2 = http(port, "/simulator/")
        kayit(
            "B2",
            "DEMA simulatoru sunuluyor (denetim 'ayri depoya' demisti)",
            s2 == 200 and "text/html" in b2.get("content-type", ""),
            f"GET /simulator/ -> {s2} ({len(g2)} B, {b2.get('content-type', '-')})",
        )

        # ── B3 · Onbellek politikasi ──────────────────────────────────────────
        idx_cc = bas.get("cache-control", "")
        varlik_cc = ""
        if varliklar:
            _, _, vb = http(port, varliklar[0])
            varlik_cc = vb.get("cache-control", "")
        kayit(
            "B3",
            "Onbellek politikasi: index no-store, hash'li varlik immutable",
            "no-store" in idx_cc and "immutable" in varlik_cc,
            f"/ -> '{idx_cc}' | {varliklar[0].rsplit('/', 1)[-1] if varliklar else '-'} -> '{varlik_cc}'",
        )

        # ── B4/B5/B6/B7 · derin hazirlik ──────────────────────────────────────
        s4, g4, _ = http(port, "/api/ai/hazirlik?derin=1", zaman=600)
        j = json.loads(g4 or b"{}")
        kayit(
            "B4",
            "Derin AI hazirligi (gercek import — olu-dogmus modulu yakalar)",
            s4 == 200 and j.get("hazir") == j.get("toplam") and j.get("toplam", 0) > 0,
            f"hazir {j.get('hazir')}/{j.get('toplam')} | eksik={j.get('eksik')}",
        )

        yuklemeler = {}
        for m in j.get("moduller", []):
            yuklemeler.setdefault(m.get("yukleme", "?"), []).append(m.get("modul"))
        duz_py = yuklemeler.get("py", [])
        kayit(
            "B5",
            "Kod korumasi: sevk edilen hicbir AI modulu duz .py degil",
            not duz_py and bool(j.get("moduller")),
            f"yukleme bicimleri: { {k: len(v) for k, v in yuklemeler.items()} } | duz .py: {duz_py or 'YOK'}",
        )

        pip = j.get("pip_yasagi", {})
        kayit("B6", "Calisma-ani pip yasagi URUNDE etkin", bool(pip.get("etkin")), f"pip_yasagi={pip}")

        xai = j.get("xai", {})
        # ⚠️ ILK YAZIMDA `all(v for v in xai.values())` diyordum -> `em_ref_stats_eksik: []`
        # (BOS LISTE = "eksik YOK" = IYI haber) kapiyi KIRMIZI yapiyordu. Kapi, urunun
        # kendi ozet alanina (`hazir`) pinlendi.
        kayit(
            "B6b",
            "XAI zinciri URUNDE cozuluyor",
            isinstance(xai, dict) and xai.get("hazir") is True and not xai.get("em_ref_stats_eksik"),
            f"xai={json.dumps(xai, ensure_ascii=False)[:200]}",
        )

        # ── B7 · Arastirma AI Pro kapisi -> 409 (bobin SURULMEZ) ──────────────
        s7, g7, _ = http(port, "/api/ai/pro/propose", "POST", {"model": "fantom", "organ_id": 0})
        d7 = json.loads(g7 or b"{}").get("detail", "")
        kayit(
            "B7",
            "Arastirma AI Pro kapisi URUNDE 409 -> bobin surulmez (A2 ertelemesinin dayanagi)",
            s7 == 409 and "bobin sürülmez" in str(d7),
            f"POST /api/ai/pro/propose (model=fantom) -> {s7} | detay: ...{str(d7)[-60:]}",
        )

        s7b, g7b, _ = http(port, "/api/ai/pro/propose", "POST", {"model": "petri", "organ_id": 0})
        kayit(
            "B7b",
            "Ayni kapi ikinci arastirma saglayicisinda da kapali (petri)",
            s7b == 409,
            f"POST /api/ai/pro/propose (model=petri) -> {s7b}",
        )

        ar = j.get("arastirmaAiPro", {})
        kayit(
            "B7c",
            "Bayrak durumu tanilama ucundan GORULUYOR (sahada 'neden acilmiyor' sorusu)",
            isinstance(ar, dict) and ar.get("acik") is False,
            f"arastirmaAiPro={json.dumps(ar, ensure_ascii=False)[:160]}",
        )

        # ── B9 · Sevk edilen ikili KENDI surumunu dogru soyluyor ──────────────
        sh, sg, _ = http(port, "/api/health")
        sj = json.loads(sg or b"{}")
        paket_surum = (EXE.parent / "_internal" / "VERSION").read_text(encoding="utf-8").strip()
        kayit(
            "B9",
            "Saglik ucu sevk edilen PAKETIN surumunu soyluyor",
            sj.get("version") == paket_surum,
            f"/api/health version={sj.get('version')} | _internal/VERSION={paket_surum}",
        )
        # ⚠️ ILK YAZIMDA `buildId` DOLU OLSUN diye dayatiyordum ve B9 KIRMIZI dondu — URUN
        # DEGIL KOSUM TAKIMI yanlisti. `get_build_id()` degeri launcher'in gecirdigi
        # `PEMF_BASE_SHA`dan okur ve YOKSA BOS DONER: "launcher'siz calistirmada uydurma
        # deger URETILMEZ". EXE'yi dogrudan actigim icin bos olmasi DOGRU davranis.
        # Dogru olcum IKI YONLU: burada uydurmamali, C9'da gecirilen sha'yi raporlamali.
        kayit(
            "B9b",
            "Launcher'siz acilista buildId UYDURULMUYOR (bos donuyor)",
            sj.get("buildId") is None,
            f"PEMF_BASE_SHA verilmedi -> buildId={sj.get('buildId')} (None beklenir; "
            "dolu olsaydi 'hangi ikili' sorusuna SAHTE cevap verilirdi)",
        )

        kayit(
            "B10",
            "Saglik ucu at-rest sifrelemeyi ve DB hazirligini DOGRU raporluyor",
            sj.get("atRestEncrypted") is True and sj.get("dbReady") is True,
            f"atRestEncrypted={sj.get('atRestEncrypted')} dbReady={sj.get('dbReady')} "
            f"(karsit kanit A0: sifreleme kapaliyken False)",
        )

        # ── B11 · Jeton SERBEST listesindeki her yol URUNDE GERCEKTEN var ─────
        # ⚠️ 2026-09-08'de bu listede `/api/ai/pro/frame` yaziyordu — BOYLE BIR ROTA HIC
        # OLMADI. Esleme tutmayinca her kare ucretli sinifa dusuyordu. Kaynak listesi
        # URUNUN sundugu rota yuzeyine karsi olculur.
        import re as _re2

        blok = _re2.search(
            r"_SERBEST_AI_UCLARI:\s*frozenset\s*=\s*frozenset\(\s*\{(.*?)\}\s*\)",
            (GUII / "servers" / "jeton.py").read_text(encoding="utf-8"),
            _re2.S,
        )
        serbest = _re2.findall(r'"([^"]+)"', blok.group(1)) if blok else []
        so, go, _ = http(port, "/openapi.json", zaman=60)
        rotalar = set(json.loads(go or b"{}").get("paths", {}).keys())
        olu = [y for y in serbest if y not in rotalar]
        kayit(
            "B11",
            "Jeton SERBEST listesindeki her yol URUNUN rota yuzeyinde VAR (olu girdi yok)",
            bool(serbest) and bool(rotalar) and not olu,
            f"serbest liste={len(serbest)} yol | urun rotasi={len(rotalar)} | OLU girdi: {olu or 'YOK'}",
        )
    finally:
        durdur(p)

    # ── B8 · Log'a sir DEGERI sizmiyor ────────────────────────────────────────
    metin = log_metni(log, veri)
    kok = veri_koku(veri)
    sir_dosyasi = kok / "pemf_secrets.json"
    sizan = []
    if sir_dosyasi.exists():
        try:
            sirlar = json.loads(sir_dosyasi.read_text(encoding="utf-8"))
        except Exception:
            sirlar = {}
        for ad, deger in sirlar.items() if isinstance(sirlar, dict) else []:
            d = deger.get("value") if isinstance(deger, dict) else deger
            if isinstance(d, str) and len(d) >= 12 and d in metin:
                sizan.append(ad)  # ⚠️ DEGER ASLA BASILMAZ — yalniz ADI
    kayit(
        "B8",
        "Sir DEGERLERI backend log'una sizmiyor",
        not sizan,
        f"sir dosyasi={'VAR' if sir_dosyasi.exists() else 'YOK'} | log {len(metin)} B | sizan alan: {sizan or 'YOK'}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C GRUBU — GUVENLIK DEGISMEZLERI
# ═══════════════════════════════════════════════════════════════════════════════


def grup_c() -> None:
    print("═" * 78)
    print("C GRUBU — GUVENLIK DEGISMEZLERI (jeton zorlamasi ACIK)")
    print("═" * 78)
    veri = CALISMA / "c"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    # ⚠️ `PEMF_JETON_OFFLINE_TAVAN=0` SART: cevrimdisi tavan (varsayilan 50) olmasa kapi ilk
    # ~50 istegi ZATEN gecirirdi ve C1-C4 "kapilanmiyor" derken aslinda HICBIR SEY olcmezdi.
    p, log, ok, port = kostur(
        veri,
        sifreli=True,
        ek={"PEMF_JETON_ENFORCED": "1", "PEMF_JETON_OFFLINE_TAVAN": "0", "PEMF_JETON_BORC_TAVANI": "0"},
    )
    if not ok:
        kayit("C-ACILIS1", "backend acilisi (jeton zorlamasi ACIK)", False, f"backend DUSTU; log={log}")
        durdur(p)
        return
    try:
        # ── C0 · KARSIT KANIT: kapi GERCEKTEN reddedebiliyor mu? ──────────────
        sc0, gc0, _ = http(port, "/api/ai/disease", "POST", {})
        kayit(
            "C0",
            "KARSIT KANIT: jeton kapisi ucretli analizi GERCEKTEN reddediyor (402)",
            sc0 == 402,
            f"POST /api/ai/disease -> {sc0} | {gc0[:110].decode('utf-8', 'replace')} "
            "(bu 402 gelmezse asagidaki C1-C4 hicbir sey kanitlamaz)",
        )

        s1, g1, _ = http(port, "/api/hardware/emergency_stop", "POST", {})
        kayit(
            "C1",
            "Jeton zorlamasi ACIKKEN acil durdurma KAPILANMIYOR",
            s1 == 200,
            f"POST /api/hardware/emergency_stop -> {s1} | yanit: {g1[:120].decode('utf-8', 'replace')}",
        )

        s2, g2, _ = http(port, "/api/session/stop", "POST", {})
        kayit(
            "C2",
            "Jeton zorlamasi ACIKKEN seans DURDURMA kapilanmiyor",
            s2 in (200, 400, 409),
            f"POST /api/session/stop -> {s2} (402/403 OLMAMALI) | {g2[:120].decode('utf-8', 'replace')}",
        )

        s3, g3, _ = http(port, "/api/ai/pro/stop", "POST", {})
        kayit(
            "C3",
            "Jeton zorlamasi ACIKKEN AI Pro seans durdurma kapilanmiyor",
            s3 not in (402, 403),
            f"POST /api/ai/pro/stop -> {s3} | {g3[:120].decode('utf-8', 'replace')}",
        )

        s4, g4, _ = http(port, "/api/ai/hazirlik")
        kayit(
            "C4", "Jeton zorlamasi ACIKKEN tanilama ucu (hazirlik) serbest", s4 == 200, f"GET /api/ai/hazirlik -> {s4}"
        )
    finally:
        durdur(p)

    # ── C5/C6 · auth ZORUNLU iken tunel istegi ────────────────────────────────
    # ⚠️ 127.0.0.1 istekleri auth-MUAF (masaustu kisayolu calissin diye). Uzak istek
    # `cf-connecting-ip` ile taklit edilir — yoksa olcum "auth aciktan gecti" der ve
    # YANILTIR.
    veri = CALISMA / "c2"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    p, log, ok, port = kostur(veri, sifreli=True, ek={"PEMF_REQUIRE_AUTH": "1"})
    if not ok:
        kayit("C-ACILIS2", "backend acilisi (auth ZORUNLU)", False, f"backend DUSTU; log={log}")
        durdur(p)
        return
    try:
        uzak = {"cf-connecting-ip": "203.0.113.7", "cf-ray": "olcum"}
        s5, g5, _ = http(port, "/api/patients", basliklar=uzak)
        kayit(
            "C5",
            "auth ZORUNLU: tunelden token'siz hasta verisi REDDEDILIYOR",
            s5 in (401, 403),
            f"GET /api/patients (cf-connecting-ip ile) -> {s5}",
        )

        s5b, g5b, _ = http(port, "/api/patients")
        kayit(
            "C5b",
            "Ayni uc YERELDEN serbest (masaustu kisayolu kirilmiyor)",
            s5b == 200,
            f"GET /api/patients (yerel) -> {s5b}",
        )

        s6, g6, _ = http(port, "/api/hardware/emergency_stop", "POST", {}, basliklar=uzak)
        kayit(
            "C6",
            "auth ZORUNLU olsa da ACIL DURDURMA muaf (fail-safe)",
            s6 == 200,
            f"POST /api/hardware/emergency_stop (tunelden) -> {s6}",
        )

        s6b, g6b, _ = http(port, "/api/v1/hardware/emergency_stop", "POST", {}, basliklar=uzak)
        kayit(
            "C6b",
            "Acil durdurma /api/v1 takma adinda da muaf (401 regresyonu geri gelmedi)",
            s6b == 200,
            f"POST /api/v1/hardware/emergency_stop (tunelden) -> {s6b}",
        )
    finally:
        durdur(p)

    # ── C7/C8 · Saglik ucu SIZDIRMIYOR (launcher nonce + cihaz kimligi) ───────
    # ⚠️ TIBBI GEREKCE (denetim 2026-08-04 P2 #13): launcher, portu gercekten BACKEND'in mi
    # tuttugunu nonce ile dogrular. Nonce tunele sizarsa portu kapan bir surec kendini
    # backend gibi gosterebilir; kapanista gonderilen E-stop O SURECE gider, "basarili"
    # gorunur ve GERCEK bobinler HASTANIN UZERINDE calismaya devam eder.
    veri = CALISMA / "c3"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    nonce = "OLCUM-NONCE-4f8c1e"
    sahte_sha = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    p, log, ok, port = kostur(veri, sifreli=True, ek={"PEMF_HEALTH_NONCE": nonce, "PEMF_BASE_SHA": sahte_sha})
    if not ok:
        kayit("C-ACILIS3", "backend acilisi (saglik nonce icin)", False, f"backend DUSTU; log={log}")
        durdur(p)
        return
    try:
        uzak = {"cf-connecting-ip": "203.0.113.7", "cf-ray": "olcum"}
        _, gl, _ = http(port, "/api/health")
        _, gu, _ = http(port, "/api/health", basliklar=uzak)
        jl, ju = json.loads(gl or b"{}"), json.loads(gu or b"{}")
        kayit(
            "C7",
            "Launcher nonce'u YALNIZ loopback'e yansiyor (tunele SIZMIYOR)",
            jl.get("launcherNonce") == nonce and ju.get("launcherNonce") is None,
            f"yerel launcherNonce={'ESLESTI' if jl.get('launcherNonce') == nonce else jl.get('launcherNonce')} | "
            f"tunelden={ju.get('launcherNonce')} (None olmali)",
        )
        kayit(
            "C7b",
            "Aktif-seans bayragi da tunele sizmiyor",
            jl.get("sessionActive") is not None and ju.get("sessionActive") is None,
            f"yerel sessionActive={jl.get('sessionActive')} | tunelden={ju.get('sessionActive')}",
        )
        kayit(
            "C8",
            "Cihaz kimligi + eslesme kodu tunele sizmiyor (bulut yetki anahtari)",
            bool(jl.get("deviceId")) and ju.get("deviceId") is None and ju.get("pairingCode") is None,
            f"yerel deviceId={'DOLU' if jl.get('deviceId') else 'BOS'} | "
            f"tunelden deviceId={ju.get('deviceId')} pairingCode={ju.get('pairingCode')}",
        )

        # ── C9 · Launcher sha'si GECILDIGINDE buildId raporlanir (B9b'nin oteki yuzu) ──
        kayit(
            "C9",
            "Launcher paket sha'si gecilince buildId RAPORLANIYOR (12 hane)",
            jl.get("buildId") == sahte_sha[:12],
            f"PEMF_BASE_SHA verildi -> buildId={jl.get('buildId')} "
            f"(beklenen {sahte_sha[:12]}) | B9b: verilmeyince None | "
            f"not: tunelden de buildId={ju.get('buildId')} — bu alan bilerek loopback'e "
            "kapatilmamis (paket kimligi sir degil, deviceId/nonce gibi YETKI tasimiyor)",
        )
    finally:
        durdur(p)


# ═══════════════════════════════════════════════════════════════════════════════
# D GRUBU — SIR DOSYASI FAIL-CLOSED (yanlis davranis = TIBBI KAYIT KALICI KAYBI)
# ═══════════════════════════════════════════════════════════════════════════════


def grup_d() -> None:
    print("═" * 78)
    print("D GRUBU — BOZUK SIR DOSYASI (yeni anahtar uretilirse TUM sifreli veri okunamaz olur)")
    print("═" * 78)

    veri = CALISMA / "d"
    sil(veri)
    veri.mkdir(parents=True, exist_ok=True)
    # 1) Saglam sifreli kurulum + bir hasta
    p, log, ok, port = kostur(veri, sifreli=True)
    if ok:
        http(port, "/api/patients", "POST", {"name": "AnahtarTanigi", "species": "Kedi"})
    durdur(p)
    kok = veri_koku(veri)
    sir = kok / "pemf_secrets.json"
    if not ok or not sir.exists():
        kayit(
            "D0",
            "on kosul: sifreli kurulum + sir dosyasi",
            False,
            f"acilis={'ayakta' if ok else 'DUSTU'} | sir dosyasi={'VAR' if sir.exists() else 'YOK'}",
        )
        return
    db_imza_once = (kok / HASTA_DB).stat().st_size
    sir_imza_once = sir.read_bytes()

    # ── D1 · Sir dosyasi BOZUK -> yeni anahtar URETILMEZ, dosya EZILMEZ ───────
    sir.write_text("{ bu gecerli json DEGIL", encoding="utf-8")
    p, log, ok1, port1 = kostur(veri, sifreli=True)
    durdur(p)
    metin = log_metni(log, veri)
    karantina = sorted(x.name for x in kok.glob("pemf_secrets.json.corrupt.*"))
    yeni_sir = sir.exists() and sir.read_bytes() != b"{ bu gecerli json DEGIL"
    kayit(
        "D1",
        "BOZUK sir dosyasi -> YENI ANAHTAR URETILMEDI, bozuk kopya karantinaya alindi",
        bool(karantina) and not yeni_sir and "YENI URETILMEDI" in metin,
        f"karantina={karantina or 'YOK'} | pemf_secrets.json yeniden yazildi mi={yeni_sir} | "
        f"log'da 'YENI URETILMEDI': {'VAR' if 'YENI URETILMEDI' in metin else 'YOK'}",
    )
    kayit(
        "D1b",
        "Sifreli hasta DB'si BOZULMADI/EZILMEDI",
        (kok / HASTA_DB).exists() and (kok / HASTA_DB).stat().st_size >= db_imza_once,
        f"{HASTA_DB}: {bicim(kok / HASTA_DB)} ({db_imza_once} -> "
        f"{(kok / HASTA_DB).stat().st_size if (kok / HASTA_DB).exists() else 0} B)",
    )

    # ── D2 · Sir dosyasi YOK + karantina kaniti VAR -> yine URETILMEZ ─────────
    # ⚠️ Fail-closed ilk yazimda YALNIZ ILK CAGRIYI kapsiyordu: dosya kenara alindigi icin
    # SONRAKI acilis "taze kurulum" sanip yeni anahtar uretiyordu (denetim 2026-08-17).
    if sir.exists():
        sir.unlink()
    p, log, ok2, port2 = kostur(veri, sifreli=True)
    durdur(p)
    metin2 = log_metni(log, veri)
    kayit(
        "D2",
        "Sir dosyasi YOK + karantina kaniti VAR -> hala YENI ANAHTAR URETILMEDI",
        not sir.exists() and "karantina kaniti VAR" in metin2,
        f"pemf_secrets.json yeniden dogdu mu={sir.exists()} | "
        f"log'da 'karantina kaniti VAR': {'VAR' if 'karantina kaniti VAR' in metin2 else 'YOK'}",
    )

    # ── D3 · Operatorun CIKIS YOLU acik (kalici tugla uretmedik) ─────────────
    for q in kok.glob("pemf_secrets.json.corrupt.*"):
        q.unlink()
    p, log, ok3, port3 = kostur(veri, sifreli=True)
    durdur(p)
    kayit(
        "D3",
        "Karantina kaldirilinca cihaz NORMAL aciliyor (kalici tugla degil)",
        ok3 and sir.exists(),
        f"acilis={'ayakta' if ok3 else 'DUSTU'} | pemf_secrets.json yeniden uretildi={sir.exists()} | "
        f"(eski anahtar {len(sir_imza_once)} B kopyayla AYNI olmak zorunda DEGIL — veri kaybi "
        "operatorun bilincli secimi)",
    )


# ═══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    # ⚠️ `sys.argv[1]` YETMEZ: `--exe <yol>` once gelirse grup adi orada degildir ve
    # betik sessizce HEPSI'ni kosardi. Bayrak OLMAYAN ilk argumani al.
    _bayraklar = {"--exe"}
    _serbest = []
    _atla = False
    for a in sys.argv[1:]:
        if _atla:
            _atla = False
            continue
        if a in _bayraklar:
            _atla = True
            continue
        if a.startswith("-"):
            continue
        _serbest.append(a)
    hangi = (_serbest[0] if _serbest else "HEPSI").upper()
    if hangi not in ("A", "B", "C", "D", "HEPSI"):
        raise SystemExit(f"[DUR] bilinmeyen grup: {hangi!r} (A|B|C|D|HEPSI)")
    bayat_ikili_nobeti()
    CALISMA.mkdir(parents=True, exist_ok=True)

    # ⚠️ Anahtar zinciri `PEMF_DATA_DIR` ile IZOLE DEGIL: makine anahtar deposu (keyring)
    # okuma sirasinda ONCE gelir. Olcumden ONCE bos oldugu dogrulandi; SONRA da bakilacak —
    # urun oraya yazarsa sahibin gercek anahtarini ezme sinifi dogar.
    baslangic = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "cmdkey /list | Select-String -Pattern 'PEMF_GUI' | Measure-Object | % Count",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    print(f"[izolasyon] olcum ONCESI makine anahtar deposunda PEMF_GUI kaydi: {baslangic}\n")

    if hangi in ("A", "HEPSI"):
        if not tohum_uret():
            print("[DUR] tohum uretilemedi")
            return 1
        grup_a()
    if hangi in ("B", "HEPSI"):
        grup_b()
    if hangi in ("C", "HEPSI"):
        grup_c()
    if hangi in ("D", "HEPSI"):
        grup_d()

    bitis = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "cmdkey /list | Select-String -Pattern 'PEMF_GUI' | Measure-Object | % Count",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()

    print("\n" + "═" * 78)
    print("OZET")
    print("═" * 78)
    gecen = sum(1 for *_, g, _k in SONUCLAR if g)
    for kod, baslik, g, _k in SONUCLAR:
        print(f"  {'✓' if g else '⛔'}  {kod:5s} {baslik}")
    print(f"\n  {gecen}/{len(SONUCLAR)} senaryo GECTI")
    print(
        f"  [izolasyon] makine anahtar deposu: once={baslangic} sonra={bitis} "
        f"({'DEGISMEDI' if baslangic == bitis else '⛔ DEGISTI — INCELE'})"
    )
    return 0 if gecen == len(SONUCLAR) else 1


if __name__ == "__main__":
    raise SystemExit(main())
