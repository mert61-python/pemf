"""report_html.py — XAI ciktilarini tek HTML raporda topla (klinik/sunum icin).

PEMF vendoring sertlestirmesi (2026-08-26, Faz 1.1):
  - TUM kullanici-kaynakli metinler (baslik, sinif adlari, etiketler, extra_info)
    html.escape ile kacislanir — hasta adi/serbest metin PII/XSS tasiyabilir.
  - embed=True icin max_embed_bytes tavani: sifreli AI-gecmisi/istemci tarafinda
    sessiz on-MB'lik blob olusmasin; asilirsa ACIK ValueError.
"""
from __future__ import annotations
import base64
import html as _html
from pathlib import Path


def _img_data_uri(path: Path) -> str:
    """PNG/JPG -> data URI (HTML icine embed)."""
    b = Path(path).read_bytes()
    ext = Path(path).suffix.lower().lstrip(".") or "png"
    return f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii')}"


def _esc(v) -> str:
    """Kullanici-kaynakli her deger HTML'e girmeden kacislanir (PII/XSS)."""
    return _html.escape(str(v), quote=True)


def build_report(out_path: str | Path, *,
                  title: str,
                  input_image: str | Path,
                  prediction: dict,
                  cam_images: dict[str, str | Path],
                  extra_info: dict | None = None,
                  embed: bool = True,
                  max_embed_bytes: int = 12_000_000) -> Path:
    """Tek sayfali HTML rapor uret.

    Args:
        out_path:     yazilacak .html yolu
        title:        raporun ust basligi
        input_image:  orijinal goruntu yolu
        prediction:   {"top_1_class": ..., "top_1_prob": ..., "top_k": [...]}
        cam_images:   {"HiRes-CAM (VGG19)": "path/to/cam.png", ...}
        extra_info:   opsiyonel {"model": ..., "device": ..., "note": ...}
        embed:        True -> gorseller data URI olarak embed; False -> ilgili yollari
                      relative olarak link'le
        max_embed_bytes: embed=True'da gomulecek gorsellerin toplam ham bayt tavani;
                      asilirsa ValueError (sessiz dev HTML yerine acik hata).

    Returns: yazilan .html Path.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if embed:
        toplam = sum(Path(p).stat().st_size
                     for p in [input_image, *cam_images.values()])
        if toplam > max_embed_bytes:
            raise ValueError(
                f"XAI raporu gomme tavanini asiyor: {toplam} B > {max_embed_bytes} B "
                "(max_embed_bytes ile artirilabilir; buyuk batch'lerde embed=False + "
                "rapor-klasoru dagitimi tercih edin)")

    def _src(p):
        if embed:
            return _img_data_uri(p)
        return str(Path(p).resolve().relative_to(out_path.parent.resolve()))

    top_k = prediction.get("top_k") or []
    top1  = _esc(prediction.get("top_1_class", "?"))
    top1p = float(prediction.get("top_1_prob", 0.0))

    info_html = ""
    if extra_info:
        info_html = "<ul>" + "".join(
            f"<li><b>{_esc(k)}</b>: {_esc(v)}</li>" for k, v in extra_info.items()) + "</ul>"

    topk_html = "<ol>" + "".join(
        f"<li><b>{_esc(t['class'])}</b> — {float(t['prob']):.4f}</li>" for t in top_k
    ) + "</ol>"

    cams_html = ""
    for label, p in cam_images.items():
        cams_html += (f'<figure style="display:inline-block;margin:8px;">'
                       f'<img src="{_src(p)}" style="max-width:420px;'
                       f'border:1px solid #ccc;">'
                       f'<figcaption style="text-align:center;font-family:sans-serif;'
                       f'font-size:13px;color:#333;">{_esc(label)}</figcaption></figure>')

    html = f"""<!doctype html>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
  body{{font-family: system-ui, sans-serif; margin: 24px; color:#222; max-width:1400px;}}
  h1{{border-bottom: 2px solid #333;padding-bottom:6px;}}
  h2{{margin-top:24px;color:#0057b7;}}
  .pred{{background:#f4f6fa;padding:12px 16px;border-radius:6px;font-size:15px;}}
  img.input{{max-width:520px;border:1px solid #999;}}
  figure{{margin:0;}}
</style>
<h1>{_esc(title)}</h1>
<h2>Girdi Goruntu</h2>
<img class="input" src="{_src(input_image)}">
<h2>Tahmin</h2>
<div class="pred">
  <b>Top-1:</b> {top1} — <b>{top1p:.4f}</b>
  {info_html}
  <b>Top-K:</b>
  {topk_html}
</div>
<h2>XAI Aciklamalar</h2>
{cams_html}
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
