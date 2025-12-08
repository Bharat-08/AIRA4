// Frontend/src/api/users.ts

export interface Teammate {
    user_id: string;
    name: string;
    email: string;
  }
  
  /**
   * Fetches all users for the recommendation dropdown.
   * Calls the backend endpoint /api/users/teammates
   */
  export const getTeammates = async (): Promise<Teammate[]> => {
    try {
      const res = await fetch('/api/users/teammates', {
        credentials: 'include', // Important for passing the session cookie
        headers: {
          'Content-Type': 'application/json',
        },
      });
  
      if (!res.ok) {
        console.warn('Failed to fetch teammates', res.status);
        return [];
      }
  
      const data = await res.json();
      return data;
    } catch (error) {
      console.error('Error fetching teammates:', error);
      return [];
    }
  };