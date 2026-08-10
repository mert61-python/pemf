# Author: mertaygn, cglrgrkn
"""DENETIM P3: ProductionConfigManager — atomik yazım + sahte 'enc:' şifreleme guard'ı."""


def _mgr(tmp_path, monkeypatch):
    from utils import production_config_manager as pcm

    m = pcm.ProductionConfigManager.__new__(pcm.ProductionConfigManager)
    m._config = {}
    m._cipher = None  # şifreleme KURULAMAMIŞ senaryo
    m._get_app_data_dir = lambda: tmp_path
    return pcm, m


def test_no_fake_enc_prefix_when_cipher_unavailable(tmp_path, monkeypatch):
    """Şifreleme yoksa 'enc:' öneki EKLENMEMELİ (yanlış güvence).

    Hata: önek koşulsuz ekleniyordu; _encrypt_value cipher yokken değeri OLDUĞU GİBİ döndürdüğü
    için diske "enc:<DÜZ METİN>" yazılıyordu. Dosyayı inceleyen biri sırrı şifreli sanar,
    _decrypt_value de cipher yokken değeri aynen döndürdüğü için hata hiç yüzeye çıkmazdı.
    """
    import inspect

    pcm, m = _mgr(tmp_path, monkeypatch)

    # Ön koşul: cipher yokken _encrypt_value değeri AYNEN döndürür (mevcut davranış).
    assert m._encrypt_value("GIZLI-DEGER") == "GIZLI-DEGER"

    # Fix'in özü: tam da bu durumda 'enc:' öneki EKLENMEMELİ.
    src = inspect.getsource(pcm.ProductionConfigManager.set)
    assert "if self._cipher and _enc != value:" in src, "'enc:' öneki yalnız GERÇEKTEN şifrelendiyse eklenmeli"
    assert "'enc:' + self._encrypt_value(value)" not in src, "koşulsuz önek ekleme geri gelmemeli (yanlış güvence)"


def test_config_save_is_atomic(tmp_path):
    """config.json atomik yazılmalı: tmp + fsync + os.replace (truncate-then-write DEĞİL).

    Hata: güç kesintisi veya eş-zamanlı iki kaydetme dosyayı YARIM/BOŞ bırakabiliyordu →
    tüm kullanıcı ayarları sessizce kaybolurdu.
    """
    import inspect

    from utils import production_config_manager as pcm

    src = (
        inspect.getsource(pcm.ProductionConfigManager.save_config)
        if hasattr(pcm.ProductionConfigManager, "save_config")
        else ""
    )
    if not src:  # metod adı farklıysa modül genelinde ara
        src = inspect.getsource(pcm)
    assert "os.replace(tmp_path, user_config_path)" in src, "atomik takas kullanılmalı"
    assert "os.fsync(" in src, "replace'ten önce diske indirilmeli"
    assert "_SAVE_LOCK" in src, "eş-zamanlı kaydetmeler serileştirilmeli"
