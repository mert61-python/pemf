# web_static/ — Eski Statik Arayüz Kaynakları · **LEGACY / KULLANILMIYOR**

React'e geçmeden önceki **elle yazılmış vanilla JS/CSS** arayüzün kalıntısı (`css/main.css`, `js/main.js`, ~Haziran 2026).

- **Bugünkü durum:** Hiçbir Python dosyası buraya referans vermiyor (`api_server.py` yalnız `/simulator` ve `/` = `frontend/dist`'i mount eder). **Ölü.**
- **Yerine geçen:** React arayüz — [`../pf/`](../pf/README.md) → [`../frontend/dist`](../frontend/README.md).
- Silinmeden referans olarak bırakıldı; runtime'ı etkilemez.

---
İlgili: [proje geneli](../README.md) · [güncel arayüz: pf/](../pf/README.md)
