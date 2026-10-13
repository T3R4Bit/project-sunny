import { useState } from 'react';
import { api } from '../utils/api';
import Icon from '../components/Icon';

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
    <div className="login-wrap">
      <form className="card login-card stack" onSubmit={handleSubmit}>
        <div className="row" style={{ gap: 12, marginBottom: 6 }}>
          <span className="brand-mark" style={{ width: 40, height: 40, borderRadius: 10 }}><Icon name="sun" size={22} /></span>
          <div>
            <h1 style={{ fontSize: 20 }}>Sunny</h1>
            <div className="muted small">Sign in to continue</div>
          </div>
        </div>
        <input type="text" name="username" value="keaton" autoComplete="username" readOnly hidden />
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          autoFocus
        />
        {error && <div className="error-box">{error}</div>}
        <button className="btn btn-primary w-full" type="submit" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
