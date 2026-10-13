import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import Icon from './Icon';

function timeOf(e: any) {
  if (e.all_day) return 'All day';
  return new Date(e.start).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export default function BriefCard({ onSettings }: { onSettings: () => void }) {
  const [brief, setBrief] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.brief().then(setBrief).catch(e => setError(String(e)));
  }, []);

  async function refresh() {
    setBusy(true);
    setError('');
    try {
      setBrief(await api.refreshBrief());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  }

  const s = brief?.sections || {};
  const ok = (k: string) => s[k]?.status === 'ok';
  const notes = Object.entries(s).filter(([, v]: any) => v.status !== 'ok' && v.note).map(([k, v]: any) => ({ k, ...v }));

  return (
    <section className="card col-12 brief">
      <div className="card-head">
        <div className="card-title"><Icon name="sun" size={16} />Daily brief</div>
        <div className="row">
          {brief?.generated_at && (
            <span className="muted small hide-sm">
              {brief.stale ? `from ${brief.date_label}` : `${new Date(brief.generated_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}
            </span>
          )}
          <button className="btn btn-sm" onClick={refresh} disabled={busy}>
            <Icon name="refresh" size={15} /> {busy ? 'Writing…' : brief?.summary ? 'Refresh' : 'Generate'}
          </button>
        </div>
      </div>

      {error && <div className="error-box" style={{ marginBottom: 10 }}>{error}</div>}

      {!brief ? (
        <div className="skeleton" style={{ height: 60 }} />
      ) : !brief.summary ? (
        <div className="muted">No brief yet. It's written automatically each morning, or generate one now.</div>
      ) : (
        <div className="stack">
          {brief.stale && <span className="pill warn" style={{ alignSelf: 'flex-start' }}>Today's brief isn't ready yet; showing {brief.date_label}</span>}
          <p className="brief-text">{brief.summary}</p>

          <div className="brief-grid">
            {ok('weather') && s.weather.data.map((w: any) => (
              <div className="brief-tile" key={w.location}>
                <div className="label">{w.location}</div>
                <div className="big">{w.now_f}°</div>
                <div className="small muted">H {w.high_f}° · L {w.low_f}° · {w.rain_chance}% rain</div>
                <div className="small" style={{ textTransform: 'capitalize' }}>{w.condition}</div>
              </div>
            ))}
            {ok('health') && (
              <div className="brief-tile">
                <div className="label">Garmin</div>
                <div className="big">{s.health.data.sleep_hours ?? '—'}<span className="unit">h sleep</span></div>
                <div className="small muted">
                  {s.health.data.sleep_score != null && `score ${s.health.data.sleep_score} · `}
                  {s.health.data.steps_yesterday != null && `${s.health.data.steps_yesterday.toLocaleString()} steps`}
                </div>
                {s.health.data.resting_hr != null && <div className="small">Resting HR {s.health.data.resting_hr}</div>}
              </div>
            )}
          </div>

          {ok('calendar') && (
            <div>
              <div className="group-label">Today</div>
              {s.calendar.data.length === 0 ? <div className="muted small">Nothing on the calendar.</div> : (
                <div className="list">
                  {s.calendar.data.map((e: any, i: number) => (
                    <div className="list-row" key={i}>
                      <span className="mono muted" style={{ minWidth: 64 }}>{timeOf(e)}</span>
                      <div className="grow">
                        <div className="name truncate">{e.title}</div>
                        {e.location && <div className="meta truncate">{e.location}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {ok('email') && (
            <div>
              <div className="group-label">Inbox · {s.email.data.unread} unread</div>
              {s.email.data.important.length > 0 && (
                <div className="list">
                  {s.email.data.important.map((m: any, i: number) => (
                    <div className="list-row" key={i}>
                      <span className="name truncate" style={{ maxWidth: '35%' }}>{m.from}</span>
                      <span className="grow truncate muted">{m.subject}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {notes.length > 0 && (
            <div className="row small muted" style={{ flexWrap: 'wrap' }}>
              {notes.map(n => <span key={n.k} className={`pill ${n.status === 'error' ? 'bad' : ''}`} title={n.note}>{n.k}: {n.status === 'error' ? 'failed' : 'not set up'}</span>)}
              <button className="btn btn-ghost btn-sm" onClick={onSettings}>Set up integrations</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
