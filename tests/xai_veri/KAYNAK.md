# tests/xai_veri — AI-1 XAI kapılarının küçük girdileri ve kâhinleri

Her dosya: kaynak · kaynağın SHA-256'sı · üretim · bu dosyanın SHA-256'sı. Kaynaklar git dışı (`ai_hub/PEMF_AI_Test_Girdileri/`
`.gitignore`'da) ya da hocanın 2026-10 paketinde (`degisenler.zip`, SHA-256 `0285b1d969f8…d420`); testler temiz klonda da koşsun diye
küçültülmüş kopyalar burada.

| Dosya | Kaynak | Kaynak SHA-256 | Üretim | Dosya SHA-256 |
|---|---|---|---|---|
| `termal_saglikli_03a_224.png` | `ai_hub/PEMF_AI_Test_Girdileri/03a_Termal_saglikli.jpg` (= hoca `xai_test_girdileri/thermal/Healthy/1.0_Thermal_Image.jpg`, bayt-aynı) | `6c92eb6e7fb6146080b7aba1e0187198c323d00a0a36f07fcd79ab5b56732e87` | PIL `convert("RGB").resize((224, 224), BILINEAR)` → kayıpsız PNG (model girdisi kaynakla bayt-aynı: ürün de 224'e aynı yöntemle küçültür) | `5a316b831f080694094f21cad876996caf83f4b73b052c2126b3683b71ff95bd` |
| `termal_hasta_03b_224.png` | `ai_hub/PEMF_AI_Test_Girdileri/03b_Termal_hasta.jpg` (= hoca `…/Sick/47.0_Thermal_Image.jpg`) | `ff1634ac88d53ae9024f046c1beeae8a2712d1ecc0413734c349125df9b891ba` | aynı | `4dbd69519ebb946cd5ddb6caea1f553147616718098ebfa320f53d21142f342a` |
