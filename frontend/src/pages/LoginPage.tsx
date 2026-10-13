import { useState } from 'react';
import { api } from '../utils/api';

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password.trim()) return;
    setLoading(true);
    setError('');
    try {
      await api.login(password);
      onLogin();
    } catch (err) {
      setError(err instanceof Error && err.message.startsWith('429') ? 'Too many attempts. Wait a few minutes.' : 'Wrong password');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh' }}>
      <div className="card" style={{ width: '100%', maxWidth: '360px' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '24px' }}>Sunny Login</h2>
        <form onSubmit={handleSubmit}>
          <input type="text" name="username" value="keaton" autoComplete="username" readOnly hidden />
          <div style={{ marginBottom: '16px' }}>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              autoFocus
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
