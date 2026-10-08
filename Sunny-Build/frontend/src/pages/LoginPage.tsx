import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

export default function LoginPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    setError('');
    try {
      await login(username, password);
      onNavigate('home');
    } catch {
      setError('Invalid credentials');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh' }}>
      <div className="card" style={{ width: '100%', maxWidth: '360px' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '24px' }}>Sunny Login</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <input
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Username"
              autoComplete="username"
              autoFocus
            />
          </div>
          <div style={{ marginBottom: '16px' }}>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
            />
          </div>
          {error && (
            <div style={{ padding: '8px', background: 'var(--accent-magenta)', color: 'white', fontSize: 13, marginBottom: '16px' }}>
              {error}
            </div>
          )}
          <button className="btn btn-primary w-full" type="submit" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  );
}
