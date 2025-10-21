export interface User {
    email: string;
    first_name: string;
    is_superadmin: boolean;
    role: 'admin' | 'user' | null;
  }