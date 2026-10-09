import { useEffect, useState } from 'react';
import { api } from '../utils/api';

export default function AdminPage() {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.adminStatus()
      .then(setStatus)
      .catch(() => setStatus({ error: 'Unable to load admin status' }))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="card"><div className="mono">Loading admin...</div></div>;
  if (status?.error) return <div className="card" style={{ borderLeft: '3px solid var(--accent-magenta)' }}>{status.error}</div>;

  return (
    <div>
      <h2>Admin</h2>
      <div className="card" style={{ marginTop: '16px' }}>
        <div className="mono">
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
            {JSON.stringify(status, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
