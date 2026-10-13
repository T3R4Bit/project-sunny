import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import Icon from './Icon';

type Row = { key: string; label: string; configured: boolean; connected?: boolean; locations?: string[] };
type Result = { ok: boolean; detail: string; action?: string } | 'checking';

export default function IntegrationsCard({ notice }: { notice?: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [results, setResults] = useState<Record<string, Result>>({});

  async function check(key: string) {
    setResults(r => ({ ...r, [key]: 'checking' }));
    try {
      const res = await api.checkIntegration(key);
      setResults(r => ({ ...r, [key]: res }));
    } catch (e) {
      setResults(r => ({ ...r, [key]: { ok: false, detail: String(e) } }));
    }
  }

  async function load() {
    const list: Row[] = await api.integrations();
    setRows(list);
    list.filter(r => r.configured).forEach(r => check(r.key));
  }

  useEffect(() => { load().catch(() => setRows([])); }, []);

  async function connectGoogle() {
    const { url } = await api.googleStart();
    window.location.href = url;
  }

  async function disconnectGoogle() {
    if (!confirm('Disconnect Google? Sunny will stop reading your calendar and inbox.')) return;
    await api.googleDisconnect();
    load();
  }

  return (
    <section className="card col-12">
      <div className="card-head">
        <div className="card-title"><Icon name="link" size={16} />Integrations</div>
        <button className="btn btn-sm" onClick={() => rows.filter(r => r.configured).forEach(r => check(r.key))}>
          <Icon name="refresh" size={15} /> Test all
        </button>
      </div>
      {notice && <div className={notice === 'connected' ? 'pill ok' : 'error-box'} style={{ marginBottom: 12 }}>
        {notice === 'connected' ? 'Google connected' : `Google sign-in failed: ${notice}`}
      </div>}
      <div className="list">
        {rows.map(r => {
          const res = results[r.key];
          const checking = res === 'checking';
          const state = !r.configured ? 'off' : checking || !res ? 'pending' : res.ok ? 'ok' : 'bad';
          return (
            <div className="list-row" key={r.key} style={{ alignItems: 'flex-start' }}>
              <span className={`dot ${state === 'ok' ? 'ok' : state === 'bad' ? 'bad' : state === 'pending' ? 'warn' : ''}`} style={{ marginTop: 7 }} />
              <div className="grow">
                <div className="name">{r.label}</div>
                <div className="meta" style={{ whiteSpace: 'normal' }}>
                  {!r.configured ? 'Not configured in .env'
                    : checking ? 'Checking…'
                    : res && typeof res === 'object' ? res.detail : ''}
                </div>
                {r.key === 'weather' && r.locations && r.locations.length > 0 && (
                  <div className="meta">Locations: {r.locations.join(' · ')}</div>
                )}
              </div>
              <div className="row">
                {r.key === 'google' && r.configured && (
                  r.connected
                    ? <button className="btn btn-sm btn-ghost" onClick={disconnectGoogle}>Disconnect</button>
                    : <button className="btn btn-sm btn-primary" onClick={connectGoogle}>Connect Google</button>
                )}
                {r.key === 'google' && r.connected && (
                  <button className="btn btn-sm btn-ghost hide-sm" onClick={connectGoogle}>Reconnect</button>
                )}
                {r.configured && <button className="btn btn-sm" onClick={() => check(r.key)} disabled={checking}>Test</button>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
