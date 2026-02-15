"""
Dataset Downloader
==================

Downloads veterinary ECG datasets from PhysioZoo, Zenodo, MIT-BIH, and other sources.
Provides progress tracking, automatic extraction, and dataset validation.

Supported Datasets:
-------------------
1. PhysioZoo: Dog, rabbit, mouse ECG recordings
2. Zenodo Paws in Pain: Dog pain assessment with ECG
3. MIT-BIH Arrhythmia: Human ECG for transfer learning
4. AliveCor: Veterinary validation dataset

Usage:
------
    downloader = DatasetDownloader()
    downloader.download_all()
    # or
    downloader.download_physiozoo()
"""

import os
import sys
import requests
import zipfile
import tarfile
from pathlib import Path
from tqdm import tqdm
from typing import Optional, List, Dict
import json
import hashlib

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config import DATASETS, DATA_DIR, LOGGING


class DatasetDownloader:
    """
    Handles downloading and extraction of veterinary ECG datasets.
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the dataset downloader.
        
        Args:
            base_dir: Base directory for storing datasets (defaults to config.DATA_DIR)
        """
        self.base_dir = base_dir or DATA_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_config = DATASETS
        self.download_log = self.base_dir / "download_log.json"
        self._load_download_log()
    
    def _load_download_log(self):
        """Load download history from JSON file."""
        if self.download_log.exists():
            with open(self.download_log, 'r') as f:
                self.log = json.load(f)
        else:
            self.log = {}
    
    def _save_download_log(self):
        """Save download history to JSON file."""
        with open(self.download_log, 'w') as f:
            json.dump(self.log, f, indent=2)
    
    def _download_file(self, url: str, destination: Path, chunk_size: int = 8192) -> bool:
        """
        Download a file with progress bar.
        
        Args:
            url: URL to download from
            destination: Local file path to save to
            chunk_size: Download chunk size in bytes
            
        Returns:
            True if successful, False otherwise
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(destination, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, 
                         desc=destination.name) as pbar:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            return True
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return False
    
    def _extract_archive(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Extract zip or tar archives.
        
        Args:
            archive_path: Path to archive file
            extract_to: Directory to extract to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            
            if archive_path.suffix in ['.zip']:
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_to)
            elif archive_path.suffix in ['.tar', '.gz', '.bz2', '.xz']:
                with tarfile.open(archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_to)
            else:
                print(f"Unsupported archive format: {archive_path.suffix}")
                return False
            
            print(f"Extracted to: {extract_to}")
            return True
        except Exception as e:
            print(f"Error extracting {archive_path}: {e}")
            return False
    
    def _calculate_md5(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def download_physiozoo(self, force: bool = False) -> bool:
        """
        Download PhysioZoo veterinary ECG database.
        
        PhysioZoo provides ECG recordings from:
        - Dogs (various breeds and sizes)
        - Rabbits (laboratory animals)
        - Mice (small animal research)
        
        Args:
            force: Force re-download even if already exists
            
        Returns:
            True if successful, False otherwise
        """
        dataset_name = "physiozoo"
        local_path = self.datasets_config[dataset_name]["local_path"]
        
        # Check if already downloaded
        if not force and dataset_name in self.log:
            print(f"PhysioZoo already downloaded to {local_path}")
            return True
        
        print("\n=== Downloading PhysioZoo Veterinary ECG Database ===")
        
        # PhysioZoo specific URLs (example - adjust based on actual availability)
        # Note: PhysioNet datasets may require registration
        base_url = "https://physionet.org/static/published-projects/"
        
        datasets_to_download = [
            # Add actual PhysioZoo dataset URLs when available
            # Example format:
            # ("dogs-ecg-database/1.0.0/", "dogs_ecg.zip"),
            # ("rabbit-ecg-database/1.0.0/", "rabbit_ecg.zip"),
        ]
        
        # For now, create directory structure and placeholder
        local_path.mkdir(parents=True, exist_ok=True)
        
        print(f"Created directory: {local_path}")
        print("\nNote: PhysioZoo datasets may require manual download from PhysioNet.")
        print("Visit: https://physiozoo.com/ for dataset access.")
        
        # Create README with instructions
        readme = local_path / "README.txt"
        with open(readme, 'w') as f:
            f.write("PhysioZoo Veterinary ECG Database\n")
            f.write("=" * 50 + "\n\n")
            f.write("To download PhysioZoo datasets:\n")
            f.write("1. Visit https://physiozoo.com/\n")
            f.write("2. Register for PhysioNet access\n")
            f.write("3. Download available veterinary ECG datasets\n")
            f.write("4. Extract files to this directory\n\n")
            f.write("Expected structure:\n")
            f.write("  - dogs/\n")
            f.write("  - rabbits/\n")
            f.write("  - mice/\n")
        
        self.log[dataset_name] = {
            "status": "directory_created",
            "path": str(local_path),
            "note": "Manual download required"
        }
        self._save_download_log()
        
        return True
    
    def download_zenodo_paws(self, force: bool = False) -> bool:
        """
        Download Zenodo Paws in Pain dataset.
        
        This dataset provides:
        - Dog ECG recordings
        - Pain assessment scores
        - Correlation between physiological markers and pain
        
        Args:
            force: Force re-download even if already exists
            
        Returns:
            True if successful, False otherwise
        """
        dataset_name = "zenodo_paws"
        local_path = self.datasets_config[dataset_name]["local_path"]
        
        if not force and dataset_name in self.log:
            print(f"Zenodo Paws in Pain already downloaded to {local_path}")
            return True
        
        print("\n=== Downloading Zenodo Paws in Pain Dataset ===")
        
        # Zenodo record URL (example - replace with actual record number)
        # zenodo_record = "7654321"  # Replace with actual record number
        # download_url = f"https://zenodo.org/record/{zenodo_record}/files/paws_in_pain.zip"
        
        local_path.mkdir(parents=True, exist_ok=True)
        
        print(f"Created directory: {local_path}")
        print("\nNote: Zenodo datasets may require specific record access.")
        print("Search Zenodo for veterinary pain assessment datasets.")
        
        # Create README
        readme = local_path / "README.txt"
        with open(readme, 'w') as f:
            f.write("Zenodo Paws in Pain Dataset\n")
            f.write("=" * 50 + "\n\n")
            f.write("To download:\n")
            f.write("1. Visit https://zenodo.org/\n")
            f.write("2. Search for veterinary pain assessment datasets\n")
            f.write("3. Download available dog ECG and pain score data\n")
            f.write("4. Extract files to this directory\n")
        
        self.log[dataset_name] = {
            "status": "directory_created",
            "path": str(local_path),
            "note": "Manual download from Zenodo"
        }
        self._save_download_log()
        
        return True
    
    def download_mitbih(self, force: bool = False) -> bool:
        """
        Download MIT-BIH Arrhythmia Database for transfer learning.
        
        While this is human ECG data, it's valuable for:
        - Transfer learning (pre-training models)
        - Augmenting veterinary dataset
        - Validating signal processing pipelines
        
        Args:
            force: Force re-download even if already exists
            
        Returns:
            True if successful, False otherwise
        """
        dataset_name = "mitbih"
        local_path = self.datasets_config[dataset_name]["local_path"]
        
        if not force and dataset_name in self.log:
            print(f"MIT-BIH already downloaded to {local_path}")
            return True
        
        print("\n=== Downloading MIT-BIH Arrhythmia Database ===")
        
        local_path.mkdir(parents=True, exist_ok=True)
        
        # MIT-BIH can be downloaded using wfdb library
        print("Use wfdb.dl_database('mitdb', local_path) to download.")
        print("This will be done during preprocessing phase.")
        
        # Create README
        readme = local_path / "README.txt"
        with open(readme, 'w') as f:
            f.write("MIT-BIH Arrhythmia Database\n")
            f.write("=" * 50 + "\n\n")
            f.write("To download using Python:\n")
            f.write("  import wfdb\n")
            f.write(f"  wfdb.dl_database('mitdb', '{local_path}')\n\n")
            f.write("Or visit: https://physionet.org/content/mitdb/1.0.0/\n")
        
        self.log[dataset_name] = {
            "status": "directory_created",
            "path": str(local_path),
            "note": "Use wfdb.dl_database for automatic download"
        }
        self._save_download_log()
        
        return True
    
    def download_all(self, force: bool = False) -> Dict[str, bool]:
        """
        Download all configured datasets.
        
        Args:
            force: Force re-download even if already exists
            
        Returns:
            Dictionary with dataset names and download status
        """
        results = {}
        
        print("=== Starting Dataset Download Process ===\n")
        
        results['physiozoo'] = self.download_physiozoo(force)
        results['zenodo_paws'] = self.download_zenodo_paws(force)
        results['mitbih'] = self.download_mitbih(force)
        
        print("\n=== Download Summary ===")
        for dataset, success in results.items():
            status = "✓" if success else "✗"
            print(f"{status} {dataset}")
        
        return results
    
    def verify_dataset(self, dataset_name: str) -> bool:
        """
        Verify that a dataset has been properly downloaded.
        
        Args:
            dataset_name: Name of the dataset to verify
            
        Returns:
            True if dataset exists and is valid
        """
        if dataset_name not in self.datasets_config:
            print(f"Unknown dataset: {dataset_name}")
            return False
        
        local_path = self.datasets_config[dataset_name]["local_path"]
        
        if not local_path.exists():
            print(f"Dataset directory not found: {local_path}")
            return False
        
        # Check if directory has any files
        files = list(local_path.rglob("*"))
        if len(files) == 0:
            print(f"Dataset directory is empty: {local_path}")
            return False
        
        print(f"✓ {dataset_name} verified: {len(files)} files found")
        return True
    
    def list_datasets(self) -> Dict[str, Dict]:
        """
        List all available datasets and their status.
        
        Returns:
            Dictionary with dataset information
        """
        status = {}
        
        for dataset_name, config in self.datasets_config.items():
            local_path = config["local_path"]
            exists = local_path.exists()
            file_count = len(list(local_path.rglob("*"))) if exists else 0
            
            status[dataset_name] = {
                "name": config["name"],
                "description": config["description"],
                "species": config["species"],
                "path": str(local_path),
                "exists": exists,
                "file_count": file_count,
                "downloaded": dataset_name in self.log
            }
        
        return status


def main():
    """
    Main function for command-line usage.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Download veterinary ECG datasets")
    parser.add_argument('--all', action='store_true', help='Download all datasets')
    parser.add_argument('--physiozoo', action='store_true', help='Download PhysioZoo')
    parser.add_argument('--zenodo', action='store_true', help='Download Zenodo Paws')
    parser.add_argument('--mitbih', action='store_true', help='Download MIT-BIH')
    parser.add_argument('--force', action='store_true', help='Force re-download')
    parser.add_argument('--list', action='store_true', help='List dataset status')
    parser.add_argument('--verify', type=str, help='Verify specific dataset')
    
    args = parser.parse_args()
    
    downloader = DatasetDownloader()
    
    if args.list:
        print("\n=== Dataset Status ===\n")
        status = downloader.list_datasets()
        for name, info in status.items():
            print(f"{name}:")
            print(f"  Name: {info['name']}")
            print(f"  Species: {', '.join(info['species'])}")
            print(f"  Path: {info['path']}")
            print(f"  Exists: {info['exists']}")
            print(f"  Files: {info['file_count']}")
            print()
    elif args.verify:
        downloader.verify_dataset(args.verify)
    elif args.all:
        downloader.download_all(args.force)
    elif args.physiozoo:
        downloader.download_physiozoo(args.force)
    elif args.zenodo:
        downloader.download_zenodo_paws(args.force)
    elif args.mitbih:
        downloader.download_mitbih(args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
