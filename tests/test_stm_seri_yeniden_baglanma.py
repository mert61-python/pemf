# -*- coding: utf-8 -*-
# Author: mertaygn
"""SERİ YENİDEN-BAĞLANMA — kablo çıkıp geri takılınca HAZIRA dönme kapısı.

===============================================================================
SAHİP TALEBİ 2026-09-11
===============================================================================
"stm reconnect algoritması da olsun; seri port kablosu çıktı bobinler offline dönsün,
geri takınca hazıra geri dönebilmeli."

===============================================================================
KAPATILAN YARIŞ (Audit P3 — yıllardır kayıtlı, DOĞRULANMAMIŞ varsayımla açık bırakılmış)
===============================================================================
`serial_conn` kilitsiz paylaşılan bir nonlocal'dı ve `reader` kapanırken KİMLİK KONTROLÜ
YAPMADAN `serial_conn = None` + `close_serial(serial_conn)` çağırıyordu. Sıralama:

    1) kablo çıkar → reader'ın readline()'ı patlar, döngüden çıkar
    2) 3 sn sonra reconnect YENİ bağlantıyı kurar (serial_conn = YENİ)
    3) ESKİ reader thread'i NİHAYET çalışır → close(YENİ) + serial_conn = None

→ Kablo TAKILI, firmware sağlam, ama bağlantı anında düşürülür ve döngü tekrarlar.
Eski koddaki gerekçe ("eski-reader None-ataması YENİ atamadan ÖNCE olur, clobber yok")
bir GARANTİ değil, thread zamanlaması hakkında bir VARSAYIMDI: bir thread `finally`
bloğuna girmeden önce keyfi süre beklemeye zorlanabilir.

Bu dosya, düzeltmeyi zamanlamaya güvenmeden ölçer: yarışı ELLE KURAR.
"""

from __future__ import annotations

import threading

from headless_core import SeriBaglantiDurumu


class _SahteConn:
    """Kapatılıp kapatılmadığını sayan asgari seri-bağlantı taklidi."""

    def __init__(self, ad: str):
        self.ad = ad
        self.is_open = True
        self.kapatma_sayisi = 0

    def close(self) -> None:
        self.kapatma_sayisi += 1
        self.is_open = False

    def __repr__(self) -> str:  # hata mesajları okunur olsun
        return f"<conn {self.ad}>"


# ============================================================================
# ASIL YARIŞ
# ============================================================================


def test_KRITIK_ESKI_reader_YENI_baglantiyi_OLDUREMEZ():
    """⚠️ "Geri takınca hazıra dönmüyor" şikâyetinin ta kendisi.

    MUTASYON: `birak()` içindeki `self._conn is conn` kimlik kontrolünü kaldır
    (koşulsuz `self._conn = None` yap) → KIRMIZI.
    """
    d = SeriBaglantiDurumu()

    eski = _SahteConn("ESKI")
    eski_nesil = d.yerlestir(eski)

    # (1) kablo çıktı: reconnect eski bağlantıyı geçersizler
    d.gecersizle()
    # (2) kablo geri takıldı: YENİ bağlantı kuruldu
    yeni = _SahteConn("YENI")
    d.yerlestir(yeni)

    # (3) ESKİ reader thread'i NİHAYET uyanıp kapanış yapmaya çalışıyor
    benim = d.birak(eski, eski_nesil)

    assert benim is False, "ESKI reader paylasilan durumu SAHIPLENDI -> YENI baglantiyi oldurur"
    assert d.aktif() is yeni, (
        f"YENI baglanti ESKI reader tarafindan DUSURULDU (aktif={d.aktif()!r}) "
        "-> kablo takili ama uygulama 'kopuk' gosterir, dongu tekrarlar"
    )


def test_KRITIK_GECERSIZLEME_sonrasi_ayni_conn_bile_YABANCIDIR():
    """Nesil damgası olmadan, aynı nesne yeniden yerleşirse eski reader onu sahiplenirdi.

    MUTASYON: `gecersizle()`de `self._nesil += 1` satırını sil → KIRMIZI.
    """
    d = SeriBaglantiDurumu()
    conn = _SahteConn("A")
    nesil = d.yerlestir(conn)

    d.gecersizle()
    d.yerlestir(conn)  # aynı NESNE yeniden kuruldu (port adı aynı → aynı obje olabilir)

    assert d.birak(conn, nesil) is False, (
        "eski NESIL damgasiyla birakma kabul edildi -> ayni nesne yeniden kurulunca eski reader YENI oturumu oldurur"
    )
    assert d.aktif() is conn, "yeniden kurulan baglanti dusuruldu"


def test_KRITIK_SAHIBI_birakabilir_ve_durum_TEMIZLENIR():
    """Karşıt kanıt: kapı "her zaman False dön" diye geçilemesin.

    Gerçek sahip bıraktığında durum GERÇEKTEN temizlenmeli; aksi halde kopuş hiç
    algılanmaz ve yeniden-bağlanma TETİKLENMEZ (bobinler sonsuza dek 'bağlı' görünür).
    """
    d = SeriBaglantiDurumu()
    conn = _SahteConn("A")
    nesil = d.yerlestir(conn)

    assert d.birak(conn, nesil) is True, "gercek sahip birakamadi -> kopus ALGILANMAZ"
    assert d.aktif() is None, "birakmadan sonra aktif baglanti TEMIZLENMEDI"


def test_KRITIK_birakma_IKI_KEZ_cagrilirsa_ikincisi_YUTULUR():
    """reader `finally` + sender hata dalı aynı bağlantı için art arda gelebilir."""
    d = SeriBaglantiDurumu()
    conn = _SahteConn("A")
    nesil = d.yerlestir(conn)

    assert d.birak(conn, nesil) is True
    assert d.birak(conn, nesil) is False, "ayni baglanti IKI KEZ sahiplenildi"


# ============================================================================
# EŞ-ZAMANLILIK — kilit gerçekten koruyor mu
# ============================================================================


def test_KRITIK_esZAMANLI_birakma_TEK_kazanan_uretir():
    """Aynı bağlantıyı bırakmaya çalışan çok sayıda thread'den YALNIZ BİRİ sahiplenmeli.

    Birden fazla "sahip" çıkarsa `_set_stm_connected(False)` birden çok kez tetiklenir,
    bağlantı iki kez kapatılır ve kapanış/açılış olayları ters sıralanabilir (UI yanlış
    durumda kalır — `_set_stm_connected` yorumundaki kayıtlı arıza).

    ⚠️ BU TEST KİLİDİN GEREKLİLİĞİNİ **KANITLAMAZ** — dürüst olalım. `birak()`taki
    `with self._lock:` kaldırılınca bu test YEŞİL kalıyor (ölçüldü, iki farklı yöntemle:
    `sys.setswitchinterval(1e-6)` ve `__eq__` içinde uyutma). Sebep: `and` kısa devre
    yaptığı için uyku İLK kontrole düşüyor, kararı veren `self._conn is conn` okuması ile
    `self._conn = None` yazması arasında ise yalnız birkaç bytecode var ve CPython onu tek
    GIL diliminde bitiriyor. Yarış GERÇEK ama CPython'da nadir.

    Bu testin GERÇEKTEN ölçtüğü şey: **tek-sahip semantiği** — kimlik/nesil mantığı
    bozulursa (R1/R2/R3 mutasyonları) burası kırmızı olur. Kilit kaldırma mutasyonu ise
    bu depoda HİÇBİR testle yakalanamıyor; gerekçesi
    `test_KRITIK_gecersizleme_sayaci_HER_CAGRIDA_ilerler` docstring'inde.
    """
    d = SeriBaglantiDurumu()
    conn = _SahteConn("A")
    nesil = d.yerlestir(conn)

    kazananlar: list[bool] = []
    kilit = threading.Lock()
    baslat = threading.Barrier(12)

    def calis():
        baslat.wait()
        r = d.birak(conn, nesil)
        with kilit:
            kazananlar.append(r)

    tlar = [threading.Thread(target=calis) for _ in range(12)]
    for t in tlar:
        t.start()
    for t in tlar:
        t.join(timeout=15)

    sahip = sum(1 for k in kazananlar if k)
    assert sahip == 1, (
        f"es-zamanli birakmada {sahip} sahip cikti (1 olmali) -> baglanti iki kez "
        "kapatilir ve kopuk/bagli olaylari ters siralanir (UI yanlis durumda kalir)"
    )


# ============================================================================
# ÇAĞRI YERİ — GERÇEK `_hw_sender_worker` (D1.54 · B-1.15)
# ============================================================================


def test_KRITIK_GERCEK_HWSender_ESKI_okuyucu_YENI_baglantiyi_DUSUREMEZ(monkeypatch):
    """D1.54 · B-1.15 — kapı ÇAĞRI YERİNİ ölçer (09-11 saha şikâyetinin kökü).

    Bu dosyadaki diğer testler `SeriBaglantiDurumu`'nu TEK BAŞINA sınar; `reader`'ın `finally`'sindeki
    çağrı yerini görmezler. Ölçüldü (plan tv-F4_2): `benim = baglanti.birak(conn, nesil)` satırı koşulsuz
    `baglanti.gecersizle(); benim = True` yapılınca (M1) ya da tarihî hâle döndürülünce (M1b: paylaşılan
    bağlantıyı kimliksiz kapatıp bırakmak) hepsi YEŞİL kalıyordu.

    Burada GERÇEK `_hw_sender_worker` koşar; sahte olan yalnız taşıma (TEK ERİŞİMLİ: önceki bağlantı açıkken
    port yeniden açılamaz — Windows COM portu gibi), modülün `socket`'i ve durum bildirimi kaydedicisi.
    Yarış zamanlamaya bırakılmaz, ELLE kurulur:
      1) ESKİ okuyucu `readline()` içinde bekletilir (kablo çekildi ama okuyucu henüz uyanmadı),
      2) kablo çekilir → gönderici portun numaralandırmadan düştüğünü görür, ESKİ bağlantıyı düşürür,
      3) yeniden bağlanma YENİ bağlantıyı kurar ve onun okuyucusunu başlatır,
      4) ESKİ okuyucu ANCAK ŞİMDİ uyanır ve `finally`'ye girer.
    İddia: YENİ bağlantı paylaşılan durumda kalır, açık kalır, kapatılmaz ve "STM kopuk" bildirilmez.
    """
    import queue
    import socket as _gercek_socket
    import time
    import types

    import headless_core as hcm

    d = types.SimpleNamespace(acilan=[], kapanan=[], stm=[], baglanti=[], kablo_cekildi=False)
    eski_okumada = threading.Event()
    eski_uyan = threading.Event()

    class _GozlemciBaglanti(hcm.SeriBaglantiDurumu):
        def __init__(self):
            super().__init__()
            d.baglanti.append(self)

    class _Conn:
        def __init__(self, ad: str):
            self.ad = ad
            self.port = "COM_TEST"
            self.is_open = True

        def readline(self):
            if self.ad == "ESKI":
                eski_okumada.set()
                eski_uyan.wait(10)
                raise OSError("test: kablo cekildi — ESKI okuyucu GEC uyandi")
            time.sleep(0.02)
            return b""

        def write(self, _b):
            pass

        def close(self):
            self.is_open = False

        def __repr__(self) -> str:
            return f"<conn {self.ad} acik={self.is_open}>"

    class _Tasima:
        def __init__(self, *a, **k):
            pass

        def open_and_handshake(self, stop_event=None, on_line=None):
            if any(c.is_open for c in d.acilan):
                return None  # tek erişim: önceki tutamak kapanmadan port açılamaz
            c = _Conn("ESKI" if not d.acilan else f"YENI{len(d.acilan)}")
            d.acilan.append(c)
            return types.SimpleNamespace(serial=c)

        def close_serial(self, c):
            d.kapanan.append(c)
            c.close()

        def port_hala_var(self, _port):
            if d.kablo_cekildi:  # tek seferlik: çekilen kablo bir sonraki numaralandırmada geri gelir
                d.kablo_cekildi = False
                return False
            return True

    def _soket_yok(*_a, **_k):
        raise OSError("test: UDP soketi kurulmaz")

    monkeypatch.setattr(hcm, "SeriBaglantiDurumu", _GozlemciBaglanti)
    monkeypatch.setattr(hcm, "Stm32SerialTransport", _Tasima)
    monkeypatch.setattr(hcm, "_PORT_CHECK_S", 0.05)
    monkeypatch.setattr(
        hcm,
        "socket",
        types.SimpleNamespace(
            socket=_soket_yok,
            AF_INET=_gercek_socket.AF_INET,
            SOCK_DGRAM=_gercek_socket.SOCK_DGRAM,
            SOL_SOCKET=_gercek_socket.SOL_SOCKET,
            SO_BROADCAST=_gercek_socket.SO_BROADCAST,
        ),
    )
    core = hcm.HeadlessCore.__new__(hcm.HeadlessCore)
    core.logger = __import__("logging").getLogger("test-seri-yeniden-baglanma-cagri-yeri")
    core._hw_sender_stop = threading.Event()
    core._hw_send_queue = queue.Queue()
    core._set_stm_connected = lambda v: d.stm.append(v)
    core._handle_stm_line = lambda *a, **k: None

    def bekle(kosul, sure=8.0):
        son = time.monotonic() + sure
        while time.monotonic() < son and not kosul():
            time.sleep(0.01)
        return kosul()

    t = threading.Thread(target=core._hw_sender_worker, daemon=True, name="test-HWSender-cagri-yeri")
    t.start()
    try:
        assert bekle(lambda: d.acilan and eski_okumada.is_set()), f"aparat: ESKI baglanti/okuyucu kurulmadi {d}"
        eski = d.acilan[0]
        baglanti = d.baglanti[0]
        assert baglanti.aktif() is eski

        d.kablo_cekildi = True
        assert bekle(lambda: eski in d.kapanan), "aparat: kablo cekildi ama gonderici ESKI baglantiyi dusurmedi"
        # `yerlestir(YENİ)` ile "bağlı" bildirimi arasında kısa bir pencere var → ikisi birlikte beklenir.
        assert bekle(lambda: len(d.acilan) == 2 and baglanti.aktif() is d.acilan[1] and d.stm[-1:] == [True]), (
            f"aparat: yeniden baglanma YENI baglantiyi kurmadi / 'bagli' bildirmedi {d}"
        )
        yeni = d.acilan[1]
        stm_yeni_sonrasi = len(d.stm)

        eski_uyan.set()  # ESKİ okuyucu ANCAK ŞİMDİ uyanır → finally
        assert bekle(lambda: d.kapanan.count(eski) >= 2), (
            "aparat: ESKI okuyucu finally'ye girmedi (kendi conn'unu kapatmadi)"
        )
        time.sleep(0.3)

        # ⚠️ Ölçümler çalışan DURDURULMADAN yakalanır: kapanışta çalışan son bağlantıyı (YENİ) meşru olarak
        # geçersizleyip kapatır — durdurduktan sonra bakmak her koşulda "kapatıldı" görür (aparat hatası).
        aktif = baglanti.aktif()
        yeni_acik = yeni.is_open
        kapanan = list(d.kapanan)
        sonraki_bildirim = d.stm[stm_yeni_sonrasi:]
        canli = t.is_alive()
    finally:
        eski_uyan.set()
        core._hw_sender_stop.set()
        t.join(3)

    assert aktif is yeni, (
        f"ESKI okuyucu YENI baglantiyi paylasilan durumdan DUSURDU (aktif={aktif!r}) — "
        "kablo takili ve firmware saglam ama uygulama 'kopuk' gosterir, dongu tekrarlar (09-11 saha sikayeti)"
    )
    assert yeni_acik and yeni not in kapanan, f"ESKI okuyucu YENI baglantiyi KAPATTI ({yeni!r}, kapanan={kapanan})"
    assert False not in sonraki_bildirim, (
        f"ESKI okuyucu YENI baglanti kurulduktan sonra 'STM kopuk' bildirdi {sonraki_bildirim} — "
        "bobinler arayuzde offline gorunur, STM seansi durdurulur"
    )
    assert canli, "HWSender oldu"


def test_KRITIK_gecersizleme_sayaci_HER_CAGRIDA_ilerler():
    """Nesil sayacı eş zamanlı çağrılarda da MONOTON ve eksiksiz ilerlemeli.

    `self._nesil += 1` (oku-değiştir-yaz) kaybederse iki farklı oturum AYNI damgayı alır →
    eski bir reader yeni bağlantıyı kendi sanıp KAPATIR; "geri takınca hazıra dönmüyor"
    arızasının daha sinsi biçimi.

    ⚠️ DÜRÜSTLÜK NOTU — BU TEST KİLİDİN GEREKLİLİĞİNİ KANITLAMAZ.
    `gecersizle()`deki `with self._lock:` kaldırılıp 8 thread × 3000 artırma koşuldu:
    **tek bir artış bile kaybolmadı**, test yeşil kaldı. CPython'da `INPLACE_ADD +
    STORE_ATTR` dizisi pratikte tek GIL diliminde bitiyor. Aynı sonuç `birak()` için de
    ölçüldü (hem `setswitchinterval(1e-6)` hem `__eq__` içinde uyutma denendi).

    Yani: **bu depoda kilit kaldırma mutasyonu davranışsal olarak TESPİT EDİLEMİYOR.**
    Kilitler yine de duruyor çünkü atomiklik CPython'un uygulama detayıdır, dil garantisi
    DEĞİLDİR (free-threading/PyPy'de kaybolur) ve maliyeti sıfıra yakındır. Bunu "mutasyon
    kırmızı" diye raporlamak YANLIŞ olurdu.

    Bu testin gerçekten ölçtüğü: sayaç mantığının kendisi (ilerletmeyi silen bir
    değişiklik — R2 mutasyonu — burada ve tek-sahip testinde KIRMIZI olur).
    """
    import sys as _sys

    d = SeriBaglantiDurumu()
    THREAD, TUR = 8, 3000

    eski_aralik = _sys.getswitchinterval()
    _sys.setswitchinterval(1e-6)
    try:

        def calis():
            for _ in range(TUR):
                d.gecersizle()

        tlar = [threading.Thread(target=calis) for _ in range(THREAD)]
        for t in tlar:
            t.start()
        for t in tlar:
            t.join(timeout=60)
    finally:
        _sys.setswitchinterval(eski_aralik)

    beklenen = THREAD * TUR
    assert d._nesil == beklenen, (
        f"nesil sayaci {d._nesil} != {beklenen} -> {beklenen - d._nesil} artis KAYBOLDU; "
        "iki oturum ayni damgayi alir ve eski reader YENI baglantiyi kapatir"
    )


def test_KRITIK_esZAMANLI_yerlestirme_ve_birakma_TUTARLI_kalir():
    """Yerleştirme/bırakma karışık akarken aktif bağlantı asla "yabancı" olmamalı."""
    d = SeriBaglantiDurumu()
    hatalar: list[str] = []

    def dongu(i: int):
        for _ in range(200):
            c = _SahteConn(f"c{i}")
            n = d.yerlestir(c)
            if d.birak(c, n):
                if d.aktif() is c:
                    hatalar.append("birakilan baglanti HALA aktif")

    tlar = [threading.Thread(target=dongu, args=(i,)) for i in range(6)]
    for t in tlar:
        t.start()
    for t in tlar:
        t.join(timeout=15)

    assert not hatalar, f"tutarsizlik: {hatalar[:3]}"


# ============================================================================
# KABLO ÇIKTI TESPİTİ — port numaralandırması
# ============================================================================


def test_KRITIK_kaybolan_port_KOPUK_sayilir(monkeypatch):
    """USB çekilince COM portu numaralandırmadan düşer → kopuş ANINDA görülür.

    ⚠️ Sessizlik bekçisi KULLANILAMAZ: boştayken keep-alive gönderilmez
    (`hardware_controller._tick`: `need_send = any_running or ...`) ve firmware de ilk
    paketten sonra ping'i keser → UART tamamen sessizdir, "satır gelmedi" YANLIŞ tetikler.

    ⚠️⚠️ NUMARALANDIRMA **ENJEKTE EDİLİR** — ORTAMA GÜVENİLMEZ (2026-09-11, CI iki kez kırmızı):
    1. tur: test GERÇEK `comports()`a dayanıyordu. CI koşucusunda **pyserial YOK**
       (`requirements-test.txt` onu içermiyor) → `port_hala_var` fail-open ile `True` döndü
       → "var olmayan port False döner" iddiası kırıldı.
    2. tur: "düzeltme" olarak `from serial.tools import list_ports` yazdım — bu sefer
       **testin kendisi** `ModuleNotFoundError: No module named 'serial'` ile düştü.
       Bir ortam varsayımını başka bir ortam varsayımıyla değiştirmiştim.

    Doğrusu: `port_hala_var` içindeki import TEMBELDİR, o yüzden `sys.modules`a SAHTE bir
    `serial.tools.list_ports` koymak yeter. Kapı artık pyserial KURULU OLSA DA OLMASA DA
    aynı şeyi ölçer — MANTIĞI, makinenin donanımını/paketlerini değil.
    (Bu deponun kayıtlı "ortam varsayımı → ÇOĞUNLUK" sınıfı.)
    """
    import sys
    import types

    from utils.stm32_transport import Stm32SerialTransport

    class _Port:
        def __init__(self, d):
            self.device = d

    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: [_Port("COM3"), _Port("COM10")]
    tools = types.ModuleType("serial.tools")
    tools.list_ports = lp
    kok = types.ModuleType("serial")
    kok.tools = tools
    monkeypatch.setitem(sys.modules, "serial", kok)
    monkeypatch.setitem(sys.modules, "serial.tools", tools)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", lp)

    t = Stm32SerialTransport(None)
    assert t.port_hala_var("COM10") is True, "listede OLAN port kopuk sayildi"
    assert t.port_hala_var("com10") is True, "buyuk/kucuk harf duyarli -> Windows'ta yanlis kopus"
    assert t.port_hala_var("COM_OLMAYAN_999") is False, "listede OLMAYAN port 'duruyor' dendi"


def test_KRITIK_numaralandirma_PATLARSA_fail_open(monkeypatch):
    """⚠️ pyserial yoksa / izin hatası varsa "koptu" DEME — çalışan bağlantıyı düşürürdü.

    Bu tam olarak CI koşucusunun durumu (pyserial kurulu değil) ve üretimde de olabilir.
    """
    import sys
    import types

    from utils.stm32_transport import Stm32SerialTransport

    lp = types.ModuleType("serial.tools.list_ports")

    def _patla():
        raise OSError("numaralandirma yapilamadi")

    lp.comports = _patla
    tools = types.ModuleType("serial.tools")
    tools.list_ports = lp
    kok = types.ModuleType("serial")
    kok.tools = tools
    monkeypatch.setitem(sys.modules, "serial", kok)
    monkeypatch.setitem(sys.modules, "serial.tools", tools)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", lp)

    t = Stm32SerialTransport(None)
    assert t.port_hala_var("COM10") is True, (
        "numaralandirma patlayinca KOPUK denildi -> calisan baglanti bosuna dusurulur"
    )


def test_KRITIK_SANAL_portlar_kopuk_SAYILMAZ():
    """⚠️ `socket://` (stm32_simulator) / `loop://` / `rfc2217://` OS port listesinde YOKTUR.

    Onları "kayboldu" saymak simülatör tabanlı testleri ve uzak-seri köprüyü ANINDA
    koparırdı — kapının kendisi bir arıza kaynağı olurdu.
    """
    from utils.stm32_transport import Stm32SerialTransport

    t = Stm32SerialTransport(None)
    for sanal in ("socket://127.0.0.1:5100", "loop://", "rfc2217://host:1234"):
        assert t.port_hala_var(sanal) is True, f"sanal port kopuk sayildi: {sanal}"


def test_KRITIK_numaralandirilamazsa_FAIL_OPEN():
    """ "Bilmiyorum"u "koptu" saymak çalışan bağlantıyı boşuna düşürürdü."""
    from utils.stm32_transport import Stm32SerialTransport

    t = Stm32SerialTransport(None)
    assert t.port_hala_var(None) is True, "port adi bilinmiyorken KOPUK denildi"
