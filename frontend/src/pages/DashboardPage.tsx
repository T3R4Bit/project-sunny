import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import Icon from '../components/Icon';
import type { Page } from '../App';

/* ---------- formatting ---------- */

const GB = 1024 ** 3;
function bytes(n?: number | null) {
  if (n == null) return '—';
  if (n >= 1024 ** 4) return `${(n / 1024 ** 4).toFixed(1)} TB`;
  if (n >= GB) return `${(n / GB).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(0)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}
function duration(s?: number | null) {
  if (s == null) return '—';
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}
function ago(iso?: string | null) {
  if (!iso) return '—';
  const t = Date.parse(iso);
  if (isNaN(t) || t < 86400000) return '—';  // Tailscale reports 0001-01-01 for never-seen
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
function systemdTime(v?: string | null) {
  // systemd prints e.g. "Tue 2026-10-13 04:35:51 EDT"; "n/a" or empty when unset
  if (!v || v === 'n/a' || v === '0') return null;
  const m = v.match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : v;
}
const pct = (a?: number | null, b?: number | null) => (a != null && b ? Math.round((a / b) * 100) : null);
const level = (p: number | null, warn = 75, bad = 90) => (p == null ? '' : p >= bad ? 'bad' : p >= warn ? 'warn' : '');
const osLabel = (os: string) => ({ linux: 'Linux', windows: 'Windows', macOS: 'macOS', iOS: 'iOS', android: 'Android' } as Record<string, string>)[os] || os || '—';

/* ---------- small pieces ---------- */

function Card({ title, icon, right, className = 'col-6', children }:
  { title: string; icon: string; right?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={`card ${className}`}>
      <div className="card-head">
        <div className="card-title"><Icon name={icon} size={16} />{title}</div>
        {right}
      </div>
      {children}
    </section>
  );
}

function Meter({ label, value, p, warn, bad }: { label: string; value: string; p: number | null; warn?: number; bad?: number }) {
  return (
    <div className="metric">
      <div className="top"><span className="k">{label}</span><span className="v">{value}</span></div>
      <div className={`meter ${level(p, warn, bad)}`}><i style={{ width: `${p ?? 0}%` }} /></div>
    </div>
  );
}

function Unavailable({ what, error }: { what: string; error?: string }) {
  return <div className="muted small">{what} unavailable{error ? `: ${error}` : ''}</div>;
}

const LINKS = [
  { group: 'Homelab', items: [
    { name: 'TrueNAS', href: 'http://100.123.58.119', device: 'truenas-scale' },
    { name: 'Jellyfin', href: 'http://100.123.58.119:30013', device: 'truenas-scale' },
    { name: 'Tailscale admin', href: 'https://login.tailscale.com/admin/machines' },
  ] },
  { group: 'School', items: [
    { name: 'OWL Express', href: 'https://owlexpress.kennesaw.edu' },
    { name: 'D2L Brightspace', href: 'https://kennesaw.view.usg.edu' },
    { name: 'Outlook', href: 'https://outlook.office.com' },
  ] },
  { group: 'Work', items: [
    { name: 'Gmail', href: 'https://mail.google.com' },
    { name: 'Google Drive', href: 'https://drive.google.com' },
    { name: 'Google Calendar', href: 'https://calendar.google.com' },
    { name: 'Canva', href: 'https://canva.com' },
  ] },
];

/* ---------- page ---------- */

export default function DashboardPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    setRefreshing(true);
    try {
      setData(await api.dashboard());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  if (!data) {
    return (
      <div className="page">
        <div className="page-head"><h1>Dashboard</h1></div>
        {error ? <div className="error-box">{error}</div> : (
          <div className="grid">{[0, 1, 2, 3].map(i => <div key={i} className="card col-6 skeleton" style={{ height: 180 }} />)}</div>
        )}
      </div>
    );
  }

  const host = data.host || {};
  const h = host.host || {};
  const ts = host.tailscale || {};
  const sunny = data.sunny || {};
  const overall = data.overall || { level: 'warn', issues: [] };
  const peersByName: Record<string, any> = {};
  for (const p of ts.peers || []) peersByName[p.name?.toLowerCase()] = p;

  const memUsed = h.mem_total != null ? h.mem_total - h.mem_available : null;
  const memP = pct(memUsed, h.mem_total);
  const diskP = pct(h.disk_used, h.disk_total);
  const swapUsed = h.swap_total != null ? h.swap_total - h.swap_free : null;
  const loadP = h.load && h.cpu_count ? Math.min(100, Math.round((h.load[0] / h.cpu_count) * 100)) : null;
  const devices = [ts.self, ...(ts.peers || [])].filter(Boolean);
  const online = devices.filter((d: any) => d.online).length;
  const mc = host.minecraft || {};
  const spend = sunny.spend || {};

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <div className="sub">
            {h.hostname || 'M-700'} · {host.available ? `updated ${host.age_s ?? '?'}s ago` : 'host collector offline'}
          </div>
        </div>
        <button className="btn btn-sm" onClick={load} disabled={refreshing}>
          <Icon name="refresh" size={15} /> {refreshing ? 'Refreshing' : 'Refresh'}
        </button>
      </div>

      <div className="grid">
        {/* Overall */}
        <div className={`banner col-12 ${overall.level}`}>
          <span className={`dot ${overall.level === 'ok' ? 'ok' : overall.level === 'down' ? 'bad' : 'warn'}`} style={{ marginTop: 6 }} />
          <div className="grow">
            <div className="title">
              {overall.level === 'ok' ? 'All systems operational' : overall.level === 'down' ? 'Something is down' : 'Needs attention'}
            </div>
            {overall.issues?.length > 0 && <ul>{overall.issues.map((i: string) => <li key={i}>{i}</li>)}</ul>}
          </div>
          {error && <span className="pill bad">refresh failed</span>}
        </div>

        {/* Quick stats */}
        <div className="card col-3"><div className="stat"><span className="label">CPU</span>
          <span className="value">{h.cpu_pct ?? '—'}<span className="unit">%</span></span>
          <span className="muted small">load {h.load ? h.load.map((l: number) => l.toFixed(2)).join(' · ') : '—'}</span></div></div>
        <div className="card col-3"><div className="stat"><span className="label">Memory</span>
          <span className="value">{memP ?? '—'}<span className="unit">%</span></span>
          <span className="muted small">{bytes(memUsed)} of {bytes(h.mem_total)}</span></div></div>
        <div className="card col-3"><div className="stat"><span className="label">Tailnet</span>
          <span className="value">{online}<span className="unit">/ {devices.length} online</span></span>
          <span className="muted small truncate">{ts.tailnet || '—'}</span></div></div>
        <div className="card col-3"><div className="stat"><span className="label">Claude spend today</span>
          <span className="value">${(spend.daily ?? 0).toFixed(2)}<span className="unit">/ ${spend.daily_cap}</span></span>
          <span className="muted small">${(spend.monthly ?? 0).toFixed(2)} of ${spend.monthly_cap} this month</span></div></div>

        {/* Server */}
        <Card title="Server" icon="server" className="col-6"
              right={<span className="pill ok">up {duration(h.uptime_s)}</span>}>
          {host.available ? (
            <div className="stack">
              <Meter label="CPU" value={`${h.cpu_pct ?? '—'}% · ${h.cpu_count} cores`} p={h.cpu_pct} />
              <Meter label="Load (1m)" value={h.load ? `${h.load[0].toFixed(2)} / ${h.cpu_count}` : '—'} p={loadP} />
              <Meter label="Memory" value={`${bytes(memUsed)} / ${bytes(h.mem_total)}`} p={memP} warn={85} bad={93} />
              <Meter label="Swap" value={`${bytes(swapUsed)} / ${bytes(h.swap_total)}`} p={pct(swapUsed, h.swap_total)} warn={50} bad={80} />
              <Meter label="Disk /" value={`${bytes(h.disk_used)} / ${bytes(h.disk_total)}`} p={diskP} warn={80} bad={90} />
              <div className="between small muted">
                <span>{h.os} · {h.kernel}</span>
                <span>{h.cpu_temp_c != null ? `${h.cpu_temp_c}°C` : ''}</span>
              </div>
            </div>
          ) : <Unavailable what="Host metrics" error={host.reason} />}
        </Card>

        {/* Services */}
        <Card title="Services" icon="activity" className="col-6">
          {Array.isArray(host.services) ? (
            <div className="list">
              {host.services.map((s: any) => {
                const ok = s.active === 'active';
                const isTimer = s.unit?.endsWith('.timer');
                return (
                  <div className="list-row" key={s.unit}>
                    <span className={`dot ${ok ? 'ok' : s.active === 'activating' ? 'warn' : 'bad'}`} />
                    <div className="grow">
                      <div className="name">{s.name}</div>
                      <div className="meta truncate">
                        {isTimer
                          ? `next ${systemdTime(s.next) || '—'}${systemdTime(s.last_trigger) ? ` · last ${systemdTime(s.last_trigger)}` : ''}`
                          : s.description}
                      </div>
                    </div>
                    <span className={`pill ${ok ? 'ok' : 'bad'}`}>{s.sub || s.active}</span>
                  </div>
                );
              })}
            </div>
          ) : <Unavailable what="Service status" error={host.reason} />}
        </Card>

        {/* Tailscale */}
        <Card title="Tailscale devices" icon="network" className="col-8"
              right={<span className="muted small">{ts.version ? `v${ts.version.split('-')[0]}` : ''}</span>}>
          {ts.peers ? (<>
            <div className="list only-mobile">
              {devices.map((d: any) => (
                <div className="list-row" key={d.dns || d.name}>
                  <span className={`dot ${d.online ? 'ok' : ''}`} />
                  <div className="grow">
                    <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                      <span className="name">{d.name}</span>
                      {d.self && <span className="pill">this server</span>}
                      {d.shared && <span className="pill">shared</span>}
                    </div>
                    <div className="meta truncate">
                      {osLabel(d.os)} · <span className="mono">{d.ip}</span>
                      {!d.self && d.online ? ` · ${d.direct ? 'direct' : 'relay'}` : ''}
                    </div>
                  </div>
                  <span className="muted small">{d.online ? 'online' : ago(d.last_seen)}</span>
                </div>
              ))}
            </div>
            <div className="table-wrap only-desktop">
              <table className="table">
                <thead><tr><th>Device</th><th className="hide-sm">OS</th><th>IP</th><th className="hide-sm">Path</th><th>Last seen</th></tr></thead>
                <tbody>
                  {devices.map((d: any) => (
                    <tr key={d.dns || d.name}>
                      <td>
                        <div className="row">
                          <span className={`dot ${d.online ? 'ok' : ''}`} />
                          <span className="name">{d.name}</span>
                          {d.self && <span className="pill">this server</span>}
                          {d.shared && <span className="pill">shared · {d.owner.split('@')[0]}</span>}
                          {d.exit_node && <span className="pill hide-sm">exit node</span>}
                        </div>
                      </td>
                      <td className="hide-sm muted">{osLabel(d.os)}</td>
                      <td className="mono muted">{d.ip}</td>
                      <td className="hide-sm muted">{d.self ? '—' : d.online ? (d.direct ? 'direct' : `relay ${d.relay}`) : '—'}</td>
                      <td className="muted">{d.online ? 'online' : ago(d.last_seen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>) : <Unavailable what="Tailscale" error={ts.error || host.reason} />}
        </Card>

        {/* Minecraft */}
        <Card title="Minecraft" icon="cube" className="col-4"
              right={<span className={`pill ${mc.online ? 'ok' : 'bad'}`}>{mc.online ? 'online' : 'offline'}</span>}>
          {mc.online ? (
            <div className="stack">
              <div className="stat">
                <span className="label">Players</span>
                <span className="value">{mc.players}<span className="unit">/ {mc.max}</span></span>
              </div>
              {mc.names?.length > 0 && <div className="small">{mc.names.join(', ')}</div>}
              <div className="small muted">{mc.motd}</div>
              <div className="between small muted"><span>Version {mc.version}</span><span>{mc.latency_ms} ms</span></div>
            </div>
          ) : <Unavailable what="Server ping" error={mc.error} />}
        </Card>

        {/* Containers */}
        <Card title="Containers" icon="box" className="col-6">
          {Array.isArray(host.containers) ? (
            <div className="list">
              {host.containers.map((c: any) => (
                <div className="list-row" key={c.name}>
                  <span className={`dot ${c.state === 'running' ? (c.status?.includes('unhealthy') ? 'warn' : 'ok') : 'bad'}`} />
                  <div className="grow">
                    <div className="name">{c.name}</div>
                    <div className="meta truncate">{c.image} · {c.status}</div>
                  </div>
                  <div className="small muted" style={{ textAlign: 'right' }}>
                    <div>{c.cpu}</div><div>{c.mem?.split(' / ')[0]}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : <Unavailable what="Docker" error={host.containers?.error} />}
        </Card>

        {/* Sunny */}
        <Card title="Sunny" icon="sun" className="col-6"
              right={<span className={`pill ${spend.auth_latch ? 'bad' : 'ok'}`}>{spend.auth_latch ? 'API key rejected' : 'healthy'}</span>}>
          <div className="stack">
            <Meter label="Spend today" value={`$${(spend.daily ?? 0).toFixed(3)} / $${spend.daily_cap}`} p={pct(spend.daily, spend.daily_cap)} />
            <Meter label="Spend this month" value={`$${(spend.monthly ?? 0).toFixed(3)} / $${spend.monthly_cap}`} p={pct(spend.monthly, spend.monthly_cap)} />
            <div className="between small">
              <span className="muted">Agent</span>
              <span>{sunny.agent?.state}{sunny.agent?.tasks ? ` · ${sunny.agent.tasks} tasks` : ''}</span>
            </div>
            <div className="between small">
              <span className="muted">Model</span>
              <span className="mono">{sunny.models?.default}</span>
            </div>
            {sunny.recent_commits?.length > 0 && (
              <div>
                <div className="group-label">Recent vault changes</div>
                <div className="list">
                  {sunny.recent_commits.slice(0, 4).map((c: any) => (
                    <div className="list-row" key={c.sha} style={{ padding: '6px 0' }}>
                      <span className="mono muted">{c.sha}</span>
                      <span className="grow truncate small">{c.subject}</span>
                      <span className="muted small">{ago(c.time)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => onNavigate('chat')}>
              <Icon name="chat" size={15} /> Open chat
            </button>
          </div>
        </Card>

        {/* Syncthing */}
        <Card title="Vault sync" icon="sync" className="col-6">
          {host.syncthing?.folders ? (
            <div className="list">
              {host.syncthing.devices.map((d: any) => (
                <div className="list-row" key={d.name}>
                  <span className={`dot ${d.connected ? 'ok' : ''}`} />
                  <span className="grow name">{d.name}</span>
                  <span className="muted small">{d.connected ? d.address : 'disconnected'}</span>
                </div>
              ))}
              {host.syncthing.folders.map((f: any) => (
                <div className="list-row" key={f.id}>
                  <span className={`dot ${f.errors ? 'bad' : f.state === 'idle' ? 'ok' : 'warn'}`} />
                  <div className="grow">
                    <div className="name">{f.id}</div>
                    <div className="meta">{f.files} files · {bytes(f.bytes)}{f.need ? ` · ${f.need} to sync` : ''}</div>
                  </div>
                  <span className="pill">{f.state}</span>
                </div>
              ))}
              {sunny.sync_conflicts > 0 && <div className="error-box">{sunny.sync_conflicts} sync conflict file(s) in the vault</div>}
            </div>
          ) : <Unavailable what="Syncthing" error={host.syncthing?.error} />}
        </Card>

        {/* Backups */}
        <Card title="Backups" icon="archive" className="col-6">
          {host.backups ? (
            <div className="list">
              {[['Sunny vault + DB', host.backups.sunny, 30], ['Minecraft world', host.backups.minecraft, 26]].map(([label, b, maxH]: any) => {
                const ageH = b?.time ? (Date.now() - Date.parse(b.time)) / 3600000 : null;
                return (
                  <div className="list-row" key={label}>
                    <span className={`dot ${ageH == null ? 'bad' : ageH > maxH ? 'warn' : 'ok'}`} />
                    <div className="grow">
                      <div className="name">{label}</div>
                      <div className="meta">{b ? `${b.count} kept${b.size && b.size > 4096 ? ` · latest ${bytes(b.size)}` : ''}` : 'none yet'}</div>
                    </div>
                    <span className="muted small">{b ? ago(b.time) : '—'}</span>
                  </div>
                );
              })}
            </div>
          ) : <Unavailable what="Backups" error={host.reason} />}
        </Card>

        {/* Links */}
        <Card title="Links" icon="link" className="col-12">
          <div className="stack">
            {LINKS.map(g => (
              <div key={g.group}>
                <div className="group-label">{g.group}</div>
                <div className="links">
                  {g.items.map((l: any) => {
                    const peer = l.device ? peersByName[l.device] : null;
                    return (
                      <a key={l.name} className="link-tile" href={l.href} target="_blank" rel="noreferrer">
                        {l.device ? <span className={`dot ${peer?.online ? 'ok' : 'bad'}`} /> : <Icon name="external" size={15} />}
                        <span className="truncate">{l.name}</span>
                      </a>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
