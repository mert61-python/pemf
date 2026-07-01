import shutil
from pathlib import Path

# Define source and target directories
base_dir = Path(__file__).parent
target_dir = base_dir / "pemf_gui" / "resources"

# Create a mapping of file types to target directories
file_mapping = {
    '.ico': target_dir / 'icons',
    '.png': target_dir / 'images',
    '.jpg': target_dir / 'images',
    '.jpeg': target_dir / 'images',
    '.svg': target_dir / 'images',
    '.qss': target_dir / 'styles',
    '.xlsx': target_dir / 'templates',
    '.xls': target_dir / 'templates',
    '.xlsm': target_dir / 'templates',
    '.xltx': target_dir / 'templates',
    '.xltm': target_dir / 'templates',
    '.xlsb': target_dir / 'templates',
    '.xlam': target_dir / 'templates',
}

def copy_files(src_dir, dest_dir, extensions):
    """Copy files with given extensions from src_dir to dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for ext in extensions:
        for file_path in src_dir.glob(f'*{ext}'):
            try:
                shutil.copy2(file_path, dest_dir)
            except Exception as e:
                pass  # Silent error handling


def main():
    # Copy files from root directory
    for ext, target in file_mapping.items():
        copy_files(base_dir, target, [ext])
    
    # Copy files from gui_images directory
    gui_images_dir = base_dir / "gui_images"
    if gui_images_dir.exists():
        copy_files(gui_images_dir, target_dir / "images", ['.png', '.jpg', '.jpeg', '.svg'])
    
    # Copy test images
    test_images_dir = base_dir / "test_images"
    if test_images_dir.exists():
        copy_files(test_images_dir, target_dir / "images", ['.png', '.jpg', '.jpeg', '.svg'])
    


if __name__ == "__main__":
    main()
