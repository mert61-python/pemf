# Author: mertaygn, cglrgrkn
def test_pdf_notes_escape_blocks_ssrf_and_bad_markup(temp_app_data, monkeypatch):
    """DENETIM P1 regresyonu: PDF'e giden serbest metin ReportLab mini-XML'i olarak YORUMLANMAMALI.

    (1) <img src="http://..."> → ReportLab TIMEOUT'SUZ dış istek atıyordu (SSRF + threadpool
        kilitlenmesi). (2) '<b>kalın' gibi kapanmamış etiket ValueError fırlatıp o seansın PDF'ini
        KALICI olarak 500 yapıyordu.
    """
    from utils import pdf_report_generator as prg

    if not prg.REPORTLAB_AVAILABLE:
        import pytest

        pytest.skip("reportlab yok")

    # Dış kaynak çözümlemesi tamamen kapalı olmalı
    import reportlab.rl_config as rc

    assert rc.trustedHosts == [], "dış host çözümlemesi kapalı olmalı"
    assert rc.trustedSchemes == [], "http/file şemaları kapalı olmalı"

    # Kaçırma: markup veri olarak kalır, ayrıştırıcıya komut olarak gitmez
    assert prg._esc('<img src="http://10.0.0.9:81/x.png"/>') == '&lt;img src="http://10.0.0.9:81/x.png"/&gt;'
    assert prg._esc("<b>kalın") == "&lt;b&gt;kalın"
    assert prg._esc(None) == ""

    # Kaçırılmış metin ReportLab tarafından SORUNSUZ ayrıştırılmalı (eskiden ValueError'dı)
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph

    st = getSampleStyleSheet()["Normal"]
    Paragraph(prg._esc("<b>kapanmamış <img src='http://x/y.png'/>"), st)
