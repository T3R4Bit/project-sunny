import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import { Project } from '../types';
import Icon from '../components/Icon';
import type { Page } from '../App';

const slugify = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

export default function ProjectsPage({ onNavigate }: { onNavigate: (page: Page, props?: { sessionId?: string; projectSlug?: string }) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    try {
      const data: any = await api.projects();
      setProjects(Array.isArray(data) ? data : []);
    } catch {
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = title.trim();
    if (!t) return;
    setError('');
    try {
      await api.createProject({ slug: slugify(t), title: t, tags: [] });
      setTitle('');
      refresh();
    } catch (err) {
      setError(err instanceof Error && err.message.startsWith('409') ? 'A project with that name already exists' : String(err));
    }
  }

  async function remove(p: Project) {
    if (!confirm(`Delete project "${p.title}"? Its files stay in the vault's git history.`)) return;
    try {
      await api.deleteProject(p.slug);
      refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <div className="sub">{projects.length} project{projects.length === 1 ? '' : 's'}</div>
        </div>
      </div>

      <form className="row" style={{ marginBottom: 16 }} onSubmit={create}>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="New project name" />
        <button className="btn btn-primary" type="submit" disabled={!title.trim()}>
          <Icon name="plus" size={15} /> Create
        </button>
      </form>
      {error && <div className="error-box" style={{ marginBottom: 16 }}>{error}</div>}

      {loading ? (
        <div className="grid">{[0, 1, 2].map(i => <div key={i} className="card col-4 skeleton" style={{ height: 110 }} />)}</div>
      ) : projects.length === 0 ? (
        <div className="card empty">No projects yet. Create one above to give Sunny a place to keep context.</div>
      ) : (
        <div className="grid">
          {projects.map(p => (
            <div key={p.slug} className="card col-4 stack" style={{ gap: 10 }}>
              <div className="between">
                <div className="row" style={{ minWidth: 0 }}>
                  <Icon name="folder" />
                  <h3 className="truncate">{p.title}</h3>
                </div>
                <span className={`pill ${p.status === 'active' ? 'ok' : ''}`}>{p.status}</span>
              </div>
              <div className="muted small truncate">{p.tags.length ? p.tags.join(' · ') : p.slug}</div>
              <div className="row">
                <button className="btn btn-sm grow" onClick={() => onNavigate('session', { projectSlug: p.slug })}>
                  <Icon name="chat" size={15} /> Open chat
                </button>
                <button className="btn btn-sm btn-danger btn-icon" onClick={() => remove(p)} aria-label="Delete project">
                  <Icon name="trash" size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
