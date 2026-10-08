import { useState } from 'react';
import { api } from '../utils/api';

export function useAuth() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  async function check() {
    try {
      const status = await api.status();
      setAuthenticated(status.authenticated || false);
    } catch {
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  }

  async function login(username: string, password: string) {
    await api.login(username, password);
    setAuthenticated(true);
  }

  async function logout() {
    await api.logout();
    setAuthenticated(false);
  }

  if (loading) check();

  return { authenticated, loading, login, logout, check };
}
