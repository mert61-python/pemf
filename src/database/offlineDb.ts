import * as SQLite from 'expo-sqlite';
import { createClient } from '@supabase/supabase-js';
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';
import { Platform } from 'react-native';

// SUPABASE CONFIG (Change these to your real project settings)
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || 'https://your-project.supabase.co';
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || 'your-anon-key';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// Web platformunda wa-sqlite ve OPFS hatalarını önlemek için SQLite'ı devre dışı bırakıyoruz
const isWeb = Platform.OS === 'web';
const db: any = isWeb ? null : SQLite.openDatabaseSync('pemf_offline.db');

export const initOfflineDb = () => {
  if (isWeb) return;
  db.execSync(`
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
      updated_at TEXT NOT NULL,
      sync_status INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      patient_id TEXT,
      session_date TEXT,
      duration_minutes INTEGER,
      target_condition TEXT,
      frequency_hz REAL,
      intensity_mt REAL,
      pulse_duration_ms INTEGER,
      sync_status INTEGER DEFAULT 0
    );
  `);
  console.log('✅ Offline Database Initialized');
};

// ── PATIENT FUNCTIONS ──

export const addPatient = (patient: any) => {
  const id = patient.id || uuidv4();
  const now = new Date().toISOString();
  
  if (isWeb) {
    console.log('Web platform: SQLite bypassed for addPatient');
    return id;
  }
  
  db.runSync(
    `INSERT INTO patients (id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at, sync_status) 
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)`,
    [
      id, patient.name, patient.species || '', patient.breed || '', 
      patient.age || '', patient.weight || '', patient.owner || '', 
      patient.vet_contact || '', now, now
    ]
  );
  return id;
};

export const getPatients = () => {
  if (isWeb) return [];
  return db.getAllSync('SELECT * FROM patients ORDER BY created_at DESC');
};

// ── SYNC LOGIC ──

export const syncWithCloud = async () => {
  if (isWeb) return true;
  console.log('🔄 Syncing local data with Supabase...');
  try {
    // 1. PUSH local unsynced patients
    const unsyncedPatients = db.getAllSync('SELECT * FROM patients WHERE sync_status = 0');
    
    for (const patient of unsyncedPatients) {
      const { error } = await supabase
        .from('patients')
        .upsert({
          id: (patient as any).id,
          name: (patient as any).name,
          species: (patient as any).species,
          breed: (patient as any).breed,
          age: (patient as any).age,
          weight: (patient as any).weight,
          owner: (patient as any).owner,
          vet_contact: (patient as any).vet_contact,
          created_at: (patient as any).created_at,
          updated_at: (patient as any).updated_at
        });
        
      if (!error) {
        db.runSync('UPDATE patients SET sync_status = 1 WHERE id = ?', [(patient as any).id]);
      } else {
        console.error('Supabase Push Error (patients):', error);
      }
    }

    // 2. PULL remote updates (Simple fetch, for a real app consider 'updated_at' cursor)
    const { data: remotePatients, error: pullError } = await supabase
      .from('patients')
      .select('*');
      
    if (!pullError && remotePatients) {
      for (const rp of remotePatients) {
        // Upsert into SQLite
        db.runSync(
          `INSERT OR REPLACE INTO patients (id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at, sync_status) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`,
          [rp.id, rp.name, rp.species, rp.breed, rp.age, rp.weight, rp.owner, rp.vet_contact, rp.created_at, rp.updated_at]
        );
      }
    }

    console.log('✅ Sync Complete');
    return true;
  } catch (err) {
    console.error('❌ Sync Failed:', err);
    return false;
  }
};
