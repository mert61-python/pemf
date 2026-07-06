"""ai_hub.inference_em_fantom — Fantom (phantom_cv) EM alan çıkarım paketi.

PhantomPredictor: BiLSTM_XXL_Raw ONNX (R²=0.9955), girdi(6) x,y,z,organ_id,
achieved_B,duty_sum -> D1-7, P1-7, E_healthy/E_cancer/E_avg.
phantom_cv: sentetik böbrek fantom fotoğrafından tümör tespiti + 3B koordinat
+ PhantomPredictor besleme (klasik CV, headless-güvenli).
"""
