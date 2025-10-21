// src/types/user.ts
export interface User {
    email: string;
    name: string;
    is_superadmin: boolean;
    role: 'admin' | 'user' | null;
  }