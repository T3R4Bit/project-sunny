import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import IntegrationsCard from '../components/IntegrationsCard';

function Row({ k, v, ok }: { k: string; v: React.ReactNode; ok?: boolean }) {
  return (
    <div className="list-row">
      {ok !== undefined && <span className={`dot ${ok ? 'ok' : ''}`} />}
      <span className="grow muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}

export default function AdminPage({ notice }: { notice?: string }) {
  const [s, setS] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.adminStatus().then(setS).catch(e => setError(String(e)));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <div className="sub">Configuration is read from <span className="mono">.env</span> on the server</div>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {s && (
        <div className="grid">
          <IntegrationsCard notice={notice} />
          <section className="card col-6">
            <div className="card-head"><div className="card-title">Claude</div></div>
            <div className="list">
              <Row k="API key" v={s.integrations.claude ? (s.spend.auth_latch ? 'rejected' : 'configured') : 'missing'} ok={s.integrations.claude && !s.spend.auth_latch} />
              <Row k="Fast model" v={<span className="mono">{s.models.fast}</span>} />
              <Row k="Default model" v={<span className="mono">{s.models.default}</span>} />
              <Row k="Deep model" v={<span className="mono">{s.models.deep}</span>} />
              <Row k="Daily cap" v={`$${s.spend.daily.toFixed(3)} of $${s.spend.daily_cap}`} />
              <Row k="Monthly cap" v={`$${s.spend.monthly.toFixed(3)} of $${s.spend.monthly_cap}`} />
            </div>
          </section>


          <section className="card col-6">
            <div className="card-head"><div className="card-title">Agent</div></div>
            <div className="list">
              <Row k="State" v={s.agent.state} ok={s.agent.running} />
              <Row k="Pending tasks" v={s.agent.task_count} />
              <Row k="Batches processed" v={s.agent.batch_stats?.total_processed ?? 0} />
            </div>
          </section>

          <section className="card col-6">
            <div className="card-head"><div className="card-title">Vault</div></div>
            <div className="list">
              <Row k="Path" v={<span className="mono">{s.vault_path}</span>} />
              <Row k="Sync conflicts" v={s.sync_conflicts.length} ok={s.sync_conflicts.length === 0} />
            </div>
            {s.sync_conflicts.length > 0 && (
              <ul className="small mono">{s.sync_conflicts.map((c: any) => <li key={c.path}>{c.path}</li>)}</ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
