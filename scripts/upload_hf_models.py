import os
import sys
from huggingface_hub import HfApi, login

def main():
    print("=" * 60)
    print("PEMF GUI - Hugging Face Model Yükleme Aracı")
    print("=" * 60)

    # Token production kodunda sabit durmaz; ortam değişkeninden okunur.
    token = (
        os.environ.get("PEMF_HF_TOKEN")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    )
    if not token:
        print("✗ Hugging Face token bulunamadı. PEMF_HF_TOKEN, HF_TOKEN veya HUGGINGFACE_HUB_TOKEN ayarlayın.")
        return
    try:
        login(token=token)
        print("✓ Hugging Face girişi başarılı.")
    except Exception as e:
        print(f"✗ Giriş başarısız: {e}")
        return
    
    api = HfApi()
    repo_id = "Mertaygn61/PEMF-AI-Models"
    
    # Repoyu oluştur (zaten varsa hata vermez)
    try:
        api.create_repo(repo_id=repo_id, repo_type="model", exist_ok=True, private=True)
        print(f"✓ Repo kontrol edildi: {repo_id} (Private Model Repo)")
    except Exception as e:
        print(f"✗ Repo oluşturma hatası: {e}")
        return

    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Yüklenecek klasörler
    search_dirs = [
        os.path.join(project_dir, 'dr_calisma', 'dr_calisma', 'inference'),
        os.path.join(project_dir, 'ealanai'),
        os.path.join(project_dir, 'ai', 'models', 'checkpoints')
    ]
    
    uploaded_count = 0
    total_size_mb = 0

    print("\nModeller aranıyor ve yükleniyor...")
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        
        for root, _, files in os.walk(d):
            # Eğitim veya analiz sonuçlarını atla
            if 'training' in root.split(os.sep) or 'figures' in root.split(os.sep):
                continue

            for file in files:
                if file.endswith(('.onnx', '.pt', '.pth')):
                    local_path = os.path.join(root, file)
                    size_mb = os.path.getsize(local_path) / (1024 * 1024)
                    
                    # 1 MB'den küçükse muhtemelen test/dummy modeldir, yine de yükleyelim ama uyaralım
                    if size_mb < 0.1:
                        continue

                    # Repo içindeki yolu proje dizinine göre izafi yap
                    relative_path = os.path.relpath(local_path, project_dir)
                    repo_path = relative_path.replace('\\', '/')
                    
                    print(f"→ Yükleniyor: {repo_path} ({size_mb:.1f} MB)")
                    try:
                        api.upload_file(
                            path_or_fileobj=local_path,
                            path_in_repo=repo_path,
                            repo_id=repo_id,
                            repo_type="model",
                            commit_message=f"Upload {file}"
                        )
                        print(f"  ✓ Başarılı.")
                        uploaded_count += 1
                        total_size_mb += size_mb
                    except Exception as e:
                        print(f"  ✗ Hata: {e}")

    print("=" * 60)
    print(f"İşlem Tamamlandı! Toplam {uploaded_count} model ({total_size_mb:.1f} MB) yüklendi.")
    print("Artık bu modeller EXE içine gömülmek yerine internetten indirilecek.")

if __name__ == "__main__":
    main()
