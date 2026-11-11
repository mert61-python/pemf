# -*- coding: utf-8 -*-
"""KP-2 A4 (Y242) · kapsam dışı bırakma (pragma) etiketleri SAYILI + ölü kod + eski etiketsiz pragma kolları.

Sahip kararı Y242: ölü kod SİLİNİR; gerçekten test edilemeyen satır yalnız GEREKÇELİ etiketle kapsam dışı bırakılır:
`# pragma: no cover — <ETİKET>: <neden>`, ETİKET ∈ {DONANIM, DONMUS, YONETICI, BULUT, SAVUNMA, PLATFORM, ULASILAMAZ}.
Test yazılabilen satıra etiket YASAK — bu yüzden liste SABİT: yeni etiket (sayı artışı), gerekçesiz / bilinmeyen etiketli pragma,
eski biçimli pragma → KIRMIZI. Kapı ürün kodunun tamamını tarar (backend + ai + pemf_gui + tools; testler hariç).
Ayrıca coverage.py'nin KENDİ ayrıştırıcısıyla her etiketin gerçekten dışarıda bıraktığı satırlar ölçülür (etiket blok başındaysa
blok da dışarıda — yanlış satıra konan etiket kör kalmasın).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ETIKETLER = ("DONANIM", "DONMUS", "YONETICI", "BULUT", "SAVUNMA", "PLATFORM", "ULASILAMAZ")
#: coverage.py varsayılan dışarıda bırakma deseni (`coverage.config.DEFAULT_EXCLUDE[0]`; pyproject `exclude_lines` TANIMLAMAZ).
PRAGMA = re.compile(r"#\s*(pragma|PRAGMA)[:\s]?\s*(no|NO)\s*(cover|COVER)")
ETIKETLI = re.compile(r"# pragma: no cover — (?P<etiket>[A-Z]+): (?P<neden>\S.{11,})$")
#: Y242 / KAPSAM.md 8.5 — dosya → (etiket, dışarıda kalması gereken satır sayısı). SABİT (mutant kaynaktan okunmaz). Gerekçeler
#: (etiket satırı ≤ 120 karakter — uzun yorum `ruff format`'ın `except (…)` sarmasına yol açar, satırlar kayar):
#:   api_server :5022 sahipsiz bobin STOP · :5060 AI devralmada eski seans kapatma — `_stop_session_coils` / `_bildir_teyitsiz_stop` /
#:     `_finalize_session_db` hatayı içeride yakalar · history_router :548 toplu silme denetim izi · sync_worker :203 `publish_now`
#:     (Y240 IA.4 sonrası `_publish_device_registry` her Exception'ı yakalar) · :364 `_decrypt_field` çözülemeyeni '[okunamayan kayıt]'
#:   secrets_manager :430 Linux / macOS makine deposu (Windows'ta `os.name` sahtesi gerçek `C:\var\lib\pemf` yazar; :428-429 Windows
#:     kolu test EDİLİR) · hybrid_recommender :735 `__main__` tanıtım girdisi protokol tablosuyla sözcük paylaşmaz (benzer listesi boş)
#:   production_config_manager :34 göreli içe aktarma yedeği · :47 `pemf_gui` kök sys.path'te değilse — yalnız doğrudan betik koşumu
#:   patient_database :1198 (KP-3) arama belirteci boş — boş terim yukarıda döner, `arama_katla` aynı kırpmayı yapar
#:   kamera_kimligi :45 (KP-4 B3; KD-2) `_msmf_kameralar` (66 satır) gerçek Media Foundation aygıt sorgusu (ctypes COM) — sarmalayıcı
#:     `msmf_kameralar` (Windows dışı / hata → []) test EDİLİR; aygıt listesinin kendisi yalnız tezgâhta gerçek kamerayla
BEKLENEN = {
    "ai/hybrid_recommender.py": [("ULASILAMAZ", 2)],
    "apps/backend/database/patient_database.py": [("ULASILAMAZ", 1)],
    "apps/backend/servers/api_server.py": [("SAVUNMA", 2), ("SAVUNMA", 2)],
    "apps/backend/servers/history_router.py": [("SAVUNMA", 2)],
    "apps/backend/servers/sync_worker.py": [("SAVUNMA", 2), ("SAVUNMA", 2)],
    "apps/backend/utils/kamera_kimligi.py": [("DONANIM", 66)],
    "apps/backend/utils/production_config_manager.py": [("ULASILAMAZ", 3), ("ULASILAMAZ", 5)],
    "apps/backend/utils/secrets_manager.py": [("PLATFORM", 8)],
}


def _urun_dosyalari() -> list[str]:
    cikti = subprocess.run(
        ["git", "ls-files", "--", "apps/backend", "ai", "pemf_gui", "tools"],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return sorted(p for p in cikti.splitlines() if p.endswith(".py") and "/tests/" not in f"/{p}")


def _pragmalar() -> dict[str, list[tuple[int, str]]]:
    bulunan: dict[str, list[tuple[int, str]]] = {}
    for rel in _urun_dosyalari():
        for no, satir in enumerate((KOK / rel).read_text(encoding="utf-8").splitlines(), 1):
            if PRAGMA.search(satir):
                bulunan.setdefault(rel, []).append((no, satir))
    return bulunan


def test_KAPI_urun_kodundaki_HER_pragma_GEREKCELI_etiketli_ve_liste_SABIT():
    """Ürün kodundaki her `pragma: no cover` → `— <ETİKET>: <en az 12 karakter neden>` biçiminde ve ETİKET kümede; dosya başına
    etiket listesi BEKLENEN'e EŞİT (yeni etiket / sayı artışı / eski biçim → KIRMIZI)."""
    bulunan = _pragmalar()
    hatali = []
    gercek: dict[str, Counter] = {}
    for rel, satirlar in bulunan.items():
        for no, satir in satirlar:
            m = ETIKETLI.search(satir)
            if not m or m.group("etiket") not in ETIKETLER:
                hatali.append(f"{rel}:{no}: {satir.strip()[:140]}")
                continue
            gercek.setdefault(rel, Counter())[m.group("etiket")] += 1
    assert hatali == [], "gerekçesiz / bilinmeyen etiketli pragma:\n" + "\n".join(hatali)
    beklenen = {rel: Counter(e for e, _ in liste) for rel, liste in BEKLENEN.items()}
    assert gercek == beklenen


def test_KAPI_her_etiket_coverage_ayristiricisinda_BEKLENEN_satiri_disarida_birakir():
    """coverage.py `PythonParser` (varsayılan desen) ile: her etiketli satır dışarıda ve dışarıda kalan satır sayısı BEKLENEN'deki
    gibi (blok başındaki etiket bloğu kapsar; yanlış satıra konan etiket tek satırda kalır → KIRMIZI)."""
    from coverage.python import PythonParser

    for rel, liste in BEKLENEN.items():
        kaynak = (KOK / rel).read_text(encoding="utf-8")
        p = PythonParser(text=kaynak, filename=str(KOK / rel), exclude=PRAGMA.pattern)
        p.parse_source()
        disarida = set(p.raw_excluded) | set(p.excluded)
        etiket_satirlari = [no for no, s in enumerate(kaynak.splitlines(), 1) if PRAGMA.search(s)]
        assert len(etiket_satirlari) == len(liste), rel
        for no, (_, adet) in zip(etiket_satirlari, liste):
            blok = sorted(s for s in p.excluded if no <= s < no + adet + 1)
            assert no in disarida, f"{rel}:{no} dışarıda değil"
            assert blok == list(range(no, no + adet)), f"{rel}:{no} dışarıda kalan {blok} (beklenen {adet} satır)"


def test_OLU_KOD_auth_get_api_token_PEMF_API_TOKEN_ortamini_TEK_kez_okur():
    """Y242: `servers/auth.py` `get_api_token` içindeki ikinci `PEMF_API_TOKEN` okuması (SecretsManager düşünce) ÖLÜYDÜ — aynı koşul
    ilk satırlarda erken döner ve arada ortamı yazan kod yok → silindi. Kapı: işlevde `os.getenv("PEMF_API_TOKEN"…)` TEK."""
    kaynak = (KOK / "apps/backend/servers/auth.py").read_text(encoding="utf-8")
    islev = next(d for d in ast.parse(kaynak).body if isinstance(d, ast.FunctionDef) and d.name == "get_api_token")
    okumalar = [
        n
        for n in ast.walk(islev)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "getenv"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "PEMF_API_TOKEN"
    ]
    assert len(okumalar) == 1


def test_auth_ortam_jetonu_YOK_ve_kasa_DUSERSE_jeton_dosyasindan_okunur(monkeypatch, tmp_path):
    """Ölü kod silindikten sonra davranış: PEMF_API_TOKEN boş + SecretsManager istisna → (eski ölü ortam okuması olmadan) doğrudan
    jeton dosyası yolu: dosyadaki değer döner."""
    import utils.secrets_manager as sm
    from servers import auth

    dosya = tmp_path / "api_token.txt"
    dosya.write_text("dosyadaki-jeton-degeri\n", encoding="utf-8")
    monkeypatch.setattr(auth, "_token", None)
    monkeypatch.delenv("PEMF_API_TOKEN", raising=False)
    monkeypatch.setattr(sm, "get_secret", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kasa yok")))
    monkeypatch.setattr(auth, "_token_file", lambda: dosya)
    assert auth.get_api_token() == "dosyadaki-jeton-degeri"


def test_tedavi_db_keyring_paketi_YOKSA_modul_yuklenir_keyring_None(monkeypatch):
    """KP-2 A4 (eski etiketsiz pragma kaldırıldı — kol test edilebilir): `keyring` içe aktarılamıyor → `treatment_history_db`'nin
    üst düzey `try: import keyring` deyimi `keyring = None` bırakır (eski anahtar yolu keyring adımını atlar). Deyim ürünün KENDİ
    kaynağından GERÇEK satır numaralarıyla derlenip kopya ad alanında koşar (modül yeniden yüklenmez; KP-1 IA.3 tekniği)."""
    from database import treatment_history_db as thdb

    kaynak = Path(thdb.__file__).read_text(encoding="utf-8")
    deyim = next(
        d
        for d in ast.parse(kaynak).body
        if isinstance(d, ast.Try) and "import keyring" in ast.get_source_segment(kaynak, d)
    )
    kod = compile(ast.Module(body=[deyim], type_ignores=[]), thdb.__file__, "exec", dont_inherit=True)
    monkeypatch.setitem(sys.modules, "keyring", None)
    ad_alani: dict = {}
    exec(kod, ad_alani)  # noqa: S102 — ürünün KENDİ kaynağı, kopya ad alanında
    assert "keyring" in ad_alani and ad_alani["keyring"] is None
