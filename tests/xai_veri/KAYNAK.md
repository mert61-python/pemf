# tests/xai_veri — AI-1 XAI kapılarının küçük girdileri ve kâhinleri

Her dosya: kaynak · kaynağın SHA-256'sı · üretim · bu dosyanın SHA-256'sı. Kaynaklar git dışı (`ai_hub/PEMF_AI_Test_Girdileri/`
`.gitignore`'da) ya da hocanın 2026-10 paketinde (`degisenler.zip`, SHA-256 `0285b1d969f8…d420`); testler temiz klonda da koşsun diye
küçültülmüş kopyalar burada.

| Dosya | Kaynak | Kaynak SHA-256 | Üretim | Dosya SHA-256 |
|---|---|---|---|---|
| `termal_saglikli_03a_224.png` | `ai_hub/PEMF_AI_Test_Girdileri/03a_Termal_saglikli.jpg` (= hoca `xai_test_girdileri/thermal/Healthy/1.0_Thermal_Image.jpg`, bayt-aynı) | `6c92eb6e7fb6146080b7aba1e0187198c323d00a0a36f07fcd79ab5b56732e87` | PIL `convert("RGB").resize((224, 224), BILINEAR)` → kayıpsız PNG (model girdisi kaynakla bayt-aynı: ürün de 224'e aynı yöntemle küçültür) | `5a316b831f080694094f21cad876996caf83f4b73b052c2126b3683b71ff95bd` |
| `termal_hasta_03b_224.png` | `ai_hub/PEMF_AI_Test_Girdileri/03b_Termal_hasta.jpg` (= hoca `…/Sick/47.0_Thermal_Image.jpg`) | `ff1634ac88d53ae9024f046c1beeae8a2712d1ecc0413734c349125df9b891ba` | aynı | `4dbd69519ebb946cd5ddb6caea1f553147616718098ebfa320f53d21142f342a` |
| `retikulosit_04a.jpg` | `ai_hub/PEMF_AI_Test_Girdileri/04a_Retikulosit.jpg` (= hoca `xai_test_girdileri/reticulocytes/000045.jpg`, bayt-aynı) | `49f4bc478cbb7d33c7279678f0d85ca69dd9ec9400cfeafb1a0b667b511bafca` | aynen kopya (300×300) | `49f4bc478cbb7d33c7279678f0d85ca69dd9ec9400cfeafb1a0b667b511bafca` |
| `bt_tas_07a.jpg` | `ai_hub/PEMF_AI_Test_Girdileri/07a_BobrekCT_tas.jpg` | `a37bffa47a79e5e2bdb1d168d113ed71faba5700028efcc918ebf3525573751b` | aynen kopya (512×512) | `a37bffa47a79e5e2bdb1d168d113ed71faba5700028efcc918ebf3525573751b` |
| `yara_0H_kesit_640x600.png` | `ai_hub/PEMF_AI_Test_Girdileri/12a_YaraKapanma_0H.tif` (= atadaki `inference_paper_dilek_hoca/test_data/CONTROL-0 H.tif`, bayt-aynı) | `f7a2d59c040310ef428491b5dae7d6a78e5aa31fd28c343a44a2f62baa627079` | `cv2.imread` → satır 300:900, sütun 0:640 (sol kenar dahil: kenara değen hücreler) → PNG (sıkıştırma 9) | `fb86641093ea51ddb07cbafb161d29345bcc561e3d11e5229764ebbb0b377af9` |
| `ses_agri_10c.mp3` | `ai_hub/PEMF_AI_Test_Girdileri/10c_KediSesi_agri.mp3` | `674e7178b6ed65907bd7c344cdec1ba067dd02e0ffee6f7e95624aee24a701c1` | aynen kopya (bugünkü Grad-CAM++ bu örnekte BOŞ harita veriyordu) | `674e7178b6ed65907bd7c344cdec1ba067dd02e0ffee6f7e95624aee24a701c1` |
