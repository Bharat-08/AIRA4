// src/types/role.ts

export type RoleStatus = 'open' | 'close' | 'deprioritized';

export interface Role {
  id: string;
  title: string;
  location: string;
  created_at: string;
  updated_at: string;
  
  // --- UPDATED: Renamed to summary (from description) to reflect parsed summary ---
  summary: string;
  
  // --- NEW FIELD: Stores the full, editable JD content (from jd_text) ---
  full_content: string; 
  
  experience: string;
  
  // --- UPDATED: Corrected to plural for consistency with API ---
  key_requirements: string[];

  candidateStats: {
    liked: number;
    contacted: number;
  };
  status: RoleStatus;
}