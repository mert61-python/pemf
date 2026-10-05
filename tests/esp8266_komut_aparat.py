# Author: mertaygn, cglrgrkn
"""ESP8266 `processControlCommand` ANA MAKİNE aparatı (1-G · Y48). ⚠️ pytest TOPLAMAZ (`test_` ön eki yok).

`firmware/esp8266_pemf_coil/esp8266_pemf_coil.ino` TEK çeviri birimi olarak derlenemez (WiFi/MQTT/portal + `Secrets.h`).
Komut yolu GERÇEK kaynaktan BAYT BAYT KESİLİR: tekrar önbelleği global'leri (`CMD_CACHE_SIZE` … `cacheIndex`),
`isCommandProcessed`, `addCommandToCache`, `processControlCommand` → `komut_dilim.inc` (her birinin TAM bir kez
bulunması şart; kesim C sözdizimine duyarlı: dize/karakter/yorum içindeki ayraçlar sayılmaz). Gerçek `SharedDefs.h`,
`SensorManager.cpp/.h`, `CoilController.h` bildirimi bayt bayt kopyalanır (sha256). Model/senaryo:
`tests/firmware_host/esp8266/komut_kosum.cpp` başlığı.

⚠️ `Secrets.h`, gerçek `NetworkManager.cpp/.h` ve `.ino`'nun geri kalanı DERLENMEZ, OKUNMAZ (Ö.4-Y6).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import esp8266_sensor_aparat as _sa

INO = _sa.FW / "esp8266_pemf_coil.ino"
_FONKSIYONLAR = (
    "bool isCommandProcessed(const char* command_id) {",
    "void addCommandToCache(const char* command_id) {",
    "void processControlCommand(JsonDocument& doc) {",
)
_GLOBAL_BAS = "const int CMD_CACHE_SIZE = "
_GLOBAL_SON = "static int cacheIndex = 0;"


def _govde_sonu(metin: str, ac: int) -> int:
    """`ac` = ilk `{` konumu → eşleşen `}` sonrası konum. Dize, karakter ve yorum içindeki ayraçlar sayılmaz."""
    derinlik, i, n = 0, ac, len(metin)
    while i < n:
        c = metin[i]
        if metin.startswith("//", i):
            i = metin.index("\n", i)
            continue
        if metin.startswith("/*", i):
            i = metin.index("*/", i) + 2
            continue
        if c in "\"'":
            j = i + 1
            while metin[j] != c:
                j += 2 if metin[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            derinlik += 1
        elif c == "}":
            derinlik -= 1
            if derinlik == 0:
                return i + 1
        i += 1
    raise AssertionError("aparat: kapanış ayracı bulunamadı")


def dilim(metin: str) -> str:
    parcalar = []
    g0 = metin.index(_GLOBAL_BAS)
    assert metin.count(_GLOBAL_BAS) == 1 and metin.count(_GLOBAL_SON) == 1, "aparat: önbellek global'leri tekil değil"
    parcalar.append(metin[g0 : metin.index(_GLOBAL_SON) + len(_GLOBAL_SON)])
    for imza in _FONKSIYONLAR:
        assert metin.count(imza) == 1, f"aparat: '{imza}' {metin.count(imza)} kez bulundu (1 beklenir)"
        bas = metin.index(imza)
        parcalar.append(metin[bas : _govde_sonu(metin, bas + len(imza) - 1)])
    return "\n\n".join(parcalar) + "\n"


def derle(dizin: Path) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    ham = INO.read_bytes()
    kesit = dilim(ham.decode("utf-8"))
    (dizin / "komut_dilim.inc").write_text(
        f"/* esp8266_pemf_coil.ino sha256 {hashlib.sha256(ham).hexdigest()} — BAYT BAYT dilim (aparat) */\n" + kesit,
        encoding="utf-8",
    )
    return _sa._derle(
        dizin,
        ("SharedDefs.h", "SensorManager.h", "SensorManager.cpp", "CoilController.h"),
        ["SensorManager.cpp", (_sa.TAKIM / "komut_kosum.cpp").as_posix()],
        "komut_kosum",
    )


def kos(exe: Path, senaryo: str, dizin: Path, ad: str = "komut") -> list[tuple]:
    """→ olay listesi: ("C", tür, f, d, s) · ("A", kimlik, başarı) · ("E", tür) · ("S", etkin)."""
    yol = dizin / f"{ad}.txt"
    yol.write_text(senaryo, encoding="ascii")
    r = subprocess.run([str(exe), str(yol)], timeout=120, **_sa._METIN)
    assert r.returncode == 0 and r.stdout.rstrip().endswith("SON"), f"koşum takımı rc={r.returncode}: {r.stderr[-500:]}"
    olaylar = []
    for s in r.stdout.splitlines():
        p = s.split()
        if not p or p[0] == "SON":
            continue
        if p[0] == "C":
            olaylar.append(("C", p[1], int(p[2]), int(p[3]), int(p[4])))
        elif p[0] == "A":
            olaylar.append(("A", p[1], p[2] == "1"))
        elif p[0] == "E":
            olaylar.append(("E", p[1]))
        elif p[0] == "S":
            olaylar.append(("S", p[1] == "1"))
    return olaylar
