# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.60 (B-3.62 · B-3.67 · B-3.82) — `apps/backend/database/README.md`, Supabase SQL başlık yorumları ve `thdb_*`
karışım başlıkları KODUN BUGÜNKÜ hâlini söyler.

Kusurlar (ölçüldü):
  B-3.62 F4 taşımasından (2026-09-18) beri README ve iki SQL başlığındaki
         `python scripts/supabase_sql.py --dosya database/…` ile `psql -f database/…` komutları hiçbir tek dizinden
         çalışmıyordu (betik kökte, SQL `apps/backend/database/` altında).
  B-3.67 Her karışım başlığının "`self` üzerinden kullandığı ve ANA SINIFTA kalan üyeler" listesi bayattı: ana sınıfta
         olmayan üye sayıyor (ör. `_get_system_setting` `thdb_bakim`de), ana sınıftan kullandıklarını eksik sayıyordu;
         README `recover_stale_active_sessions`ı ana sınıfta gösteriyordu (`thdb_seans`ta).
  B-3.82 README "outbox enqueue tarafı canlıdır" diyordu; üretimde `enqueue_outbox_message`in tek çağıranı
         `SessionManager`dır ve `SessionManager` örneği (`headless_core.session_manager`) hiçbir yerde kullanılmıyor.
         Mekanizma SİLİNMEZ (sahip kararı).

Kapı: (a) belgelerdeki komut yolları depo kökünden çözülür; (b) başlık listeleri AST ölçümüne EŞİT; (c) outbox satırı
AST ölçümüne göre konuşur (ölçüm "canlı" derse "çağıranı YOK" yazamaz, "ölü" derse "canlıdır" yazamaz).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DB = KOK / "apps" / "backend" / "database"
README = DB / "README.md"


# ── (a) komut yolları ─────────────────────────────────────────────────────────
#: `--dosya <yol>`, `psql … -f <yol>` ve kök-göreli `database/<ad>.sql` atıfları (öncesinde `backend/` yoksa).
#: Tur 2 (çürütücü): komutun KENDİ betik yolu (`python <yol>.py`) da — betik yolu kırık komut da hiçbir yerden çalışmaz
#: (eskiden yalnız `--dosya` / `-f` argümanı denetleniyordu; `python tools/supabase_sql.py` kaçıyordu).
_YOL_DESENLERI = (
    re.compile(r"--dosya\s+([^\s`|]+)"),
    re.compile(r"\bpsql\b[^\n`]*?\s-f\s+([^\s`|]+)"),
    re.compile(r"(?<![\w/.])(database/[\w<>*.-]+\.sql)\b"),
    re.compile(r"\bpython[0-9.]*\s+([^\s`|]+\.py)\b"),
)


def _izlenen_sql() -> list[Path]:
    r = subprocess.run(
        ["git", "ls-files", "-z", "--", "apps/backend/database/*.sql"], cwd=KOK, capture_output=True, timeout=60
    )
    assert r.returncode == 0, f"aparat: git ls-files düştü (rc={r.returncode})"
    return [KOK / p for p in r.stdout.decode("utf-8").split("\0") if p]


def _cozulmeyenler(yol: Path) -> list[str]:
    kirik = []
    for no, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), 1):
        for desen in _YOL_DESENLERI:
            for m in desen.finditer(satir):
                hedef = m.group(1).strip("'\"")
                if "/" not in hedef:  # `psql -f dosya.sql` gibi genel yer tutucu — yol değil
                    continue
                if "<" in hedef:  # `database/<dosya>.sql` → desen; en az bir dosyaya uymalı
                    eslesen = list(KOK.glob(re.sub(r"<[^>]+>", "*", hedef)))
                else:
                    eslesen = [KOK / hedef] if (KOK / hedef).is_file() else []
                if not eslesen:
                    kirik.append(f"{yol.relative_to(KOK).as_posix()}:{no}: {hedef}")
    return kirik


def test_KRITIK_database_belgelerindeki_komut_yollari_DEPO_KOKUNDEN_cozulur_D6_60():
    dosyalar = [README, *_izlenen_sql()]
    assert len(dosyalar) > 5, f"aparat: SQL kümesi bulunamadı: {dosyalar}"
    kirik = sorted({k for d in dosyalar for k in _cozulmeyenler(d)})
    assert not kirik, "belgedeki komut / atıf yolu depo kökünden ÇÖZÜLMÜYOR (betik kökte koşar):\n  " + "\n  ".join(
        kirik
    )


def test_KARSIT_yol_denetimi_KIRIK_yolu_yakalar_D6_60(tmp_path):
    ornek = tmp_path / "ornek.md"
    ornek.write_text(
        "`python scripts/supabase_sql.py --dosya database/<dosya>.sql --yaz`\n"
        "psql -v ON_ERROR_STOP=1 -f database/supabase_devices.sql \"$URL\"\n"
        "`python scripts/supabase_sql.py --dosya apps/backend/database/supabase_jetonlar.sql --yaz`\n"
        "`python tools/supabase_sql.py --denetim`\n",
        encoding="utf-8",
    )
    sonuc = []
    for no, satir in enumerate(ornek.read_text(encoding="utf-8").splitlines(), 1):
        for desen in _YOL_DESENLERI:
            sonuc += [(no, m.group(1)) for m in desen.finditer(satir)]
    assert (1, "database/<dosya>.sql") in sonuc and (2, "database/supabase_devices.sql") in sonuc
    assert (3, "apps/backend/database/supabase_jetonlar.sql") in sonuc
    assert (4, "tools/supabase_sql.py") in sonuc and not (KOK / "tools" / "supabase_sql.py").is_file(), (
        "aparat: kırık betik yolu (`python tools/…py`) yakalanmadı"
    )
    assert not any(no == 3 and y == "database/supabase_jetonlar.sql" for no, y in sonuc), (
        "aparat: doğru yolun kuyruğu ayrı atıf sayıldı"
    )


# ── (b) karışım başlıkları ────────────────────────────────────────────────────
def _sinif_tanimlari(yol: Path) -> dict[str, set[str]]:
    sonuc = {}
    for dugum in ast.parse(yol.read_text(encoding="utf-8")).body:
        if not isinstance(dugum, ast.ClassDef):
            continue
        tanim = set()
        for alt in dugum.body:
            if isinstance(alt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                tanim.add(alt.name)
            elif isinstance(alt, ast.Assign):
                tanim |= {h.id for h in alt.targets if isinstance(h, ast.Name)}
            elif isinstance(alt, ast.AnnAssign) and isinstance(alt.target, ast.Name):
                tanim.add(alt.target.id)
        for alt in ast.walk(dugum):  # `self.x = …`
            hedefler = (
                alt.targets
                if isinstance(alt, ast.Assign)
                else [alt.target]
                if isinstance(alt, (ast.AnnAssign, ast.AugAssign))
                else []
            )
            for h in hedefler:
                for e in ast.walk(h):
                    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == "self":
                        tanim.add(e.attr)
        sonuc[dugum.name] = tanim
    return sonuc


def _self_kullanimlari(yol: Path) -> set[str]:
    return {
        e.attr
        for e in ast.walk(ast.parse(yol.read_text(encoding="utf-8")))
        if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == "self"
    }


_BASLIK = re.compile(r"`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler:(.*?)(?:\n\s*\n|\"\"\")", re.S)


def _karisimlar() -> list[Path]:
    return sorted(DB.glob("thdb_*.py"))


@pytest.mark.parametrize("yol", _karisimlar(), ids=lambda p: p.stem)
def test_KRITIK_karisim_basligindaki_ANA_SINIF_uyeleri_OLCUME_esit_D6_60(yol):
    ana = _sinif_tanimlari(DB / "treatment_history_db.py")["TreatmentHistoryDB"]
    kendi = set().union(*_sinif_tanimlari(yol).values())
    olcum = sorted(u for u in _self_kullanimlari(yol) - kendi if u in ana)
    m = _BASLIK.search(yol.read_text(encoding="utf-8"))
    assert m, f"{yol.name}: başlıkta 'ANA SINIFTA kalan uyeler' listesi yok"
    baslik = sorted(set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", m.group(1))))
    assert baslik == olcum, (
        f"{yol.name} başlığı bayat — ana sınıfta OLMAYAN / kullanılmayan: {sorted(set(baslik) - set(olcum))}; "
        f"ana sınıftan kullanılıp başlıkta EKSİK: {sorted(set(olcum) - set(baslik))}"
    )


def test_aparat_karisim_kumesi_TAM_D6_60():
    adlar = {p.stem for p in _karisimlar()}
    assert {"thdb_seans", "thdb_telemetri", "thdb_pii", "thdb_outbox", "thdb_sema", "thdb_bakim"} <= adlar, adlar


def test_README_ana_sinif_satiri_YALNIZ_ana_sinif_uyelerini_anar_D6_60():
    ana = _sinif_tanimlari(DB / "treatment_history_db.py")["TreatmentHistoryDB"]
    satir = next(
        s for s in README.read_text(encoding="utf-8").splitlines() if s.startswith("| `treatment_history_db.py` |")
    )
    adlar = set(re.findall(r"`([a-z_][a-z0-9_]+)`", satir)) - {"treatment_history_db.py", "get_treatment_db", "thdb_"}
    adlar = {a for a in adlar if not a.startswith("thdb_")}
    disarida = sorted(a for a in adlar if a not in ana)
    assert not disarida, (
        f"README 'treatment_history_db.py' satırı ana sınıfta OLMAYAN üyeyi ana sınıfta gösteriyor: {disarida}"
    )


# ── (c) outbox ────────────────────────────────────────────────────────────────
def _uretim_py() -> list[Path]:
    r = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=KOK, capture_output=True, timeout=60)
    assert r.returncode == 0
    return [KOK / p for p in r.stdout.decode("utf-8").split("\0") if p and not p.startswith(("tests/", "tools/"))]


def _enqueue_canli_mi(dosyalar: list[Path], kok: Path) -> tuple[bool, list[str]]:
    """Üretimde outbox'a YENİ ileti girebilir mi: SessionManager DIŞINDA bir `enqueue_outbox_message` çağrısı ya da
    SessionManager örneğinin kullanımı (okunan `.session_manager` özniteliği / `session_manager` adı / kurulum)
    var mı."""
    kanit = []
    for yol in dosyalar:
        try:
            agac = ast.parse(yol.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = yol.relative_to(kok).as_posix()
        sm_dosyasi = rel.endswith("database/session_manager.py")
        siniflar = [d for d in ast.walk(agac) if isinstance(d, ast.ClassDef)]
        sm_govdesi = {id(x) for c in siniflar if c.name == "SessionManager" for x in ast.walk(c)}
        for d in ast.walk(agac):
            if (
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "enqueue_outbox_message"
            ):
                if not (sm_dosyasi and id(d) in sm_govdesi):
                    kanit.append(f"{rel}:{d.lineno} enqueue_outbox_message (SessionManager dışı)")
            if sm_dosyasi:
                continue
            if isinstance(d, ast.Attribute) and d.attr == "session_manager" and isinstance(d.ctx, ast.Load):
                kanit.append(f"{rel}:{d.lineno} .session_manager okunuyor")
            if isinstance(d, ast.Name) and d.id == "session_manager" and isinstance(d.ctx, ast.Load):
                kanit.append(f"{rel}:{d.lineno} session_manager adı okunuyor")
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "SessionManager":
                kanit.append(f"{rel}:{d.lineno} SessionManager(...) kuruluyor")
    return bool(kanit), kanit


def test_KRITIK_README_outbox_satiri_URETIM_OLCUMUNE_uyar_D6_60():
    canli, kanit = _enqueue_canli_mi(_uretim_py(), KOK)
    satir = next(
        s for s in README.read_text(encoding="utf-8").splitlines() if "outbox" in s and s.lstrip().startswith("- ")
    )
    assert "SİLİNMEZ" in satir or "silme" in satir.casefold(), (
        f"README outbox satırı mekanizmanın korunduğunu söylemiyor: {satir}"
    )
    if canli:
        assert "çağıranı YOK" not in satir, f"README outbox enqueue'su ÖLÜ diyor ama üretimde canlı: {kanit[:5]}"
    else:
        assert not re.search(r"enqueue tarafı canl", satir, re.I), (
            "README outbox enqueue tarafı 'canlı' diyor; üretimde çağıranı YOK"
        )
        assert "çağıranı YOK" in satir, f"README outbox satırı enqueue'nun bugün ÖLÜ olduğunu söylemiyor: {satir}"


@pytest.mark.parametrize(
    "kaynak, beklenen",
    [
        ("def f(core):\n    core.session_manager.start_session()\n", ".session_manager okunuyor"),
        ("def f(db):\n    db.enqueue_outbox_message(topic='t', payload='{}')\n", "SessionManager dışı"),
        (
            "from database.session_manager import SessionManager\nsm = SessionManager('x')\n",
            "SessionManager(...) kuruluyor",
        ),
    ],
    ids=["oznitelik_okuma", "dogrudan_enqueue", "kurulum"],
)
def test_KARSIT_outbox_olcumu_CANLI_kullanimi_yakalar_D6_60(tmp_path, kaynak, beklenen):
    sahte = tmp_path / "apps" / "backend" / "x.py"
    sahte.parent.mkdir(parents=True)
    sahte.write_text(kaynak, encoding="utf-8")
    canli, kanit = _enqueue_canli_mi([sahte], tmp_path)
    assert canli and any(beklenen in k for k in kanit), kanit
