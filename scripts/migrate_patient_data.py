"""
Patient Database Migration Script
Migrates patient data from JSON to SQLite

Usage:
    python migrate_patient_data.py [json_file] [db_file]
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def migrate_patients(json_file: str, db_file: str) -> None:
    """
    Migrate patient data from JSON to SQLite database.
    
    Args:
        json_file: Path to the source JSON file (patients.json)
        db_file: Path to the target SQLite database (patients.db)
    """
    json_path = Path(json_file)
    db_path = Path(db_file)
    
    # Check if JSON file exists
    if not json_path.exists():
        print(f"❌ JSON file not found: {json_path}")
        print("No migration needed - starting fresh.")
        return
    
    # Load JSON data
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        patients = data.get('patients', [])
        print(f"📄 Found {len(patients)} patients in JSON file")
        
        if not patients:
            print("No patients to migrate.")
            return
    
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        return
    except Exception as e:
        print(f"❌ Error reading JSON: {e}")
        return
    
    # Create SQLite database
    try:
        with sqlite3.connect(db_path) as conn:
            # Enable WAL mode
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            
            cursor = conn.cursor()
            
            # Create table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    species TEXT,
                    breed TEXT,
                    age TEXT,
                    weight TEXT,
                    owner TEXT,
                    vet_contact TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Create indexes
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_patient_name 
                ON patients(name)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_patient_owner 
                ON patients(owner)
            ''')
            
            # Migrate data
            migrated = 0
            skipped = 0
            
            for patient in patients:
                try:
                    # Check if patient already exists
                    cursor.execute('SELECT id FROM patients WHERE id = ?', (patient['id'],))
                    if cursor.fetchone():
                        print(f"⏭️  Patient already exists: {patient.get('name', 'Unknown')} (ID: {patient['id']})")
                        skipped += 1
                        continue
                    
                    # Insert patient
                    cursor.execute('''
                        INSERT INTO patients 
                        (id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        patient.get('id', ''),
                        patient.get('name', ''),
                        patient.get('species', ''),
                        patient.get('breed', ''),
                        patient.get('age', ''),
                        patient.get('weight', ''),
                        patient.get('owner', ''),
                        patient.get('vet_contact', ''),
                        patient.get('created_at', datetime.now().isoformat()),
                        patient.get('updated_at', datetime.now().isoformat())
                    ))
                    
                    print(f"✅ Migrated: {patient.get('name', 'Unknown')} (ID: {patient['id']})")
                    migrated += 1
                
                except Exception as e:
                    print(f"❌ Failed to migrate patient {patient.get('name', 'Unknown')}: {e}")
                    continue
            
            conn.commit()
            
            # Summary
            print("\n" + "="*50)
            print("✅ Migration completed!")
            print(f"   - Migrated: {migrated} patients")
            print(f"   - Skipped: {skipped} patients")
            print(f"   - Total in database: {migrated + skipped} patients")
            print("="*50)
            
            # Backup original JSON
            if migrated > 0:
                backup_path = json_path.with_suffix('.json.backup')
                json_path.rename(backup_path)
                print(f"\n📦 Original JSON backed up to: {backup_path}")
    
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
        return
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
        db_file = sys.argv[2] if len(sys.argv) > 2 else 'patients.db'
    else:
        # Default paths
        json_file = 'patients.json'
        db_file = 'patients.db'
    
    print("="*50)
    print("PEMF Patient Database Migration")
    print("="*50)
    print(f"Source JSON: {json_file}")
    print(f"Target DB:   {db_file}")
    print("="*50)
    print()
    
    migrate_patients(json_file, db_file)


if __name__ == '__main__':
    main()
