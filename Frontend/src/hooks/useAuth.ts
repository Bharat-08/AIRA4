// src/hooks/useAuth.ts
import { useState, useEffect } from 'react';
import type { User } from '../types';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await fetch('http://localhost:8000/me', {
          credentials: 'include',
        });
        if (!response.ok) throw new Error('Not authenticated');
        const userData: User = await response.json();
        setUser(userData);
      } catch (err) {
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    fetchUser();
  }, []);

  return { user, isLoading };
}