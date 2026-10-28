# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.55 (B-10.197 · B-10.198 · B-10.265) — tools/ belgesi, simülatörün açılış günlüğü / docstring'i ve sniffer teşhisi KAYNAKLA aynı.

Kusur: simülatör açılışta "Paket boyutu: 121 byte (88-byte binary + CRC32)" ve "GUI sabit COM10 modundayken socket simulator
kullanılmaz" yazıyordu; docstring 88 baytlık 5 bobinlik paketi ve `apps/backend/utils/stm32_simulator.py` yolunu anlatıyordu;
`tools/README.md` "GUI şu an COM10'a kilitli" diyordu — oysa `stm32_transport` `PEMF_STM_PORT=socket://…`'u `serial_for_url` ile açar.
`com_sniffer` sessizliği "firmware STM_READY göndermiyordur veya USB CDC init çağrılmamış" diye teşhis ediyordu — kart ST-Link VCP →
USART3 konuşur (USB CDC yok) ve banner yalnız ilk pakete kadar (`g_pwm_started == 0`) basılır.

⛔ Simülatör / sniffer ÇALIŞTIRILMAZ (COM / dinleyici YOK): `run_server` sahte soketle çağrılır (bind / listen no-op, accept ilk
çağrıda KeyboardInterrupt) — gerçek soket açılmaz; sniffer yalnız kaynak metniyle ölçülür.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import tools.organize_resources as org
import tools.stm32_simulator as sim

KOK = Path(__file__).resolve().parent.parent
README = KOK / "tools" / "README.md"
SNIFFER = KOK / "tools" / "com_sniffer.py"
TRANSPORT = KOK / "apps" / "backend" / "utils" / "stm32_transport.py"
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


class _SahteSoket:
    """bind / listen no-op; accept ilk çağrıda KeyboardInterrupt → run_server açılış günlüğünü basıp döngüden çıkar."""

    def __init__(self, *a, **k):
        pass

    def setsockopt(self, *a):
        pass

    def bind(self, adres):
        self.adres = adres

    def listen(self, n):
        pass

    def accept(self):
        raise KeyboardInterrupt


def test_KRITIK_simulator_acilis_gunlugu_PKT_SIZE_ve_socket_yolunu_soyler_D6_55(monkeypatch, caplog):
    monkeypatch.setattr(sim.socket, "socket", _SahteSoket)
    with caplog.at_level(logging.INFO, logger="STM32Sim"):
        sim.run_server("127.0.0.1", 0)
    metin = "\n".join(r.getMessage() for r in caplog.records)
    sayilar = {int(x) for x in re.findall(r"(\d+)[- ]?(?:byte|bayt)", metin)}
    assert sayilar == {sim.PKT_SIZE}, (
        f"açılış günlüğü PKT_SIZE ({sim.PKT_SIZE}) dışında bayt sayısı söylüyor: {sayilar}\n{metin}"
    )
    assert "PEMF_STM_PORT=socket://" in metin, (
        f"açılış günlüğü backend'in simülatöre nasıl bağlanacağını söylemiyor:\n{metin}"
    )
    assert not re.search(r"COM10 modunda|kilitli|kullanılmaz", metin), (
        f"açılış günlüğü socket yolunun KULLANILAMADIĞINI söylüyor:\n{metin}"
    )


def test_KRITIK_simulator_docstring_ve_bilgi_iletisi_KAYNAKLA_ayni_D6_55(capsys):
    doc = sim.__doc__ or ""
    assert not re.search(r"\b88[- ]?(?:byte|bayt)", doc), "docstring eski 88 baytlık paketi anlatıyor"
    assert f"Toplam: {sim.PKT_SIZE} bayt" in doc and f"float[{sim.NUM_COILS}]" in doc, (
        "docstring paket toplamı / bobin sayısı kaynaktan farklı"
    )
    assert "apps/backend/utils/stm32_simulator.py" not in doc and "tools/stm32_simulator.py" in doc, (
        "docstring betiğin yolunu yanlış söylüyor"
    )
    sim.set_gui_port("127.0.0.1", 5100)
    cikti = capsys.readouterr().out
    assert "PEMF_STM_PORT=socket://127.0.0.1:5100" in cikti and "kilitli" not in cikti, cikti


def test_KRITIK_tools_README_iddialari_kodla_ayni_D6_55():
    rd = README.read_text(encoding="utf-8")
    tr = TRANSPORT.read_text(encoding="utf-8")
    # Kodun gerçeği: transport socket:// portu serial_for_url ile açar → README "COM10'a kilitli / socket no-op" diyemez
    assert "serial_for_url" in tr and "socket://" in tr, "ölçüt değişti: stm32_transport socket:// desteği bulunamadı"
    assert not re.search(r"COM10'a kilitli|set_gui_port. no-op", rd), "tools/README hâlâ 'COM10'a kilitli' diyor"
    assert "PEMF_STM_PORT" in rd and "socket://127.0.0.1:5100" in rd, (
        "tools/README simülatöre bağlanma yolunu söylemiyor"
    )
    # organize_resources hedefi betiğin dizinine göre (tools/pemf_gui/resources)
    hedef = org.target_dir.resolve().relative_to(KOK.resolve()).as_posix()
    satir = next(s for s in rd.splitlines() if "`organize_resources.py`" in s)
    assert hedef + "/" in satir, f"README organize_resources hedefi ({hedef}) yanlış: {satir}"
    # ESP sim yolu metni diskte
    for yol in re.findall(r"`(\.\./[^`]+\.py)`", rd):
        assert (README.parent / yol).resolve().exists(), f"tools/README olmayan yol gösteriyor: {yol}"


def test_KRITIK_com_sniffer_sessizlik_teshisi_firmware_banner_kosuluyla_AYNI_D6_55():
    main_c = MAIN_C.read_text(encoding="utf-8", errors="replace")
    assert re.search(r"if \(g_pwm_started == 0 && \(current_time - last_ping_ms >= 2000U\)\)", main_c), (
        "ölçüt değişti: firmware banner koşulu (g_pwm_started == 0) bulunamadı"
    )
    dizgeler = [
        n.value
        for n in ast.walk(ast.parse(SNIFFER.read_text(encoding="utf-8")))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    dizgeler += [
        "".join(p.value for p in n.values if isinstance(p, ast.Constant))
        for n in ast.walk(ast.parse(SNIFFER.read_text(encoding="utf-8")))
        if isinstance(n, ast.JoinedStr)
    ]
    metin = "\n".join(dizgeler)
    if "MX_USB_DEVICE_Init" not in main_c:
        assert "USB CDC" not in metin and "MX_USB_DEVICE_Init" not in metin, (
            "sniffer firmware'de olmayan USB CDC'yi teşhis ediyor"
        )
    assert re.search(r"ilk paket", metin) and re.search(r"RESET", metin), (
        "sniffer sessizliği 'banner yalnız ilk pakete kadar basılır → kartı resetleyin' diye açıklamıyor"
    )
