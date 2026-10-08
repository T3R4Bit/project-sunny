import { useEffect, useState } from 'react';
import { api } from '../utils/api';
import { Project } from '../types';

import type { Page } from '../App';

export default function ProjectsPage({ onNavigate }: { onNavigate: (page: Page, props?: { sessionId?: string; projectSlug?: string }) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.projects()
      .then((data: any) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  async function create() {
    const name = prompt('Project name:');
    if (!name) return;
    try {
      await api.createProject({ name, description: '', tags: [] });
      const updated = await api.projects();
      setProjects(Array.isArray(updated) ? updated : []);
    } catch (e) {
      alert(String(e));
    }
  }

  async function remove(slug: string) {
    if (!confirm(`Delete project "${slug}"?`)) return;
    try {
      await api.deleteProject(slug);
      const updated = await api.projects();
      setProjects(Array.isArray(updated) ? updated : []);
    } catch (e) {
      alert(String(e));
    }
  }

  if (loading) return <div className="card"><div className="mono">Loading projects...</div></div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2>Projects</h2>
        <button className="btn btn-sm btn-primary" onClick={create}>+ New Project</button>
      </div>

      {projects.length === 0 ? (
        <div className="empty-state">No projects yet. Create one to get started.</div>
      ) : (
        <div>
          {projects.map(p => (
            <div key={p.slug} className="list-item">
              <div>
                <div style={{ fontWeight: 600, cursor: 'pointer' }} onClick={() => onNavigate('session', { projectSlug: p.slug })}>
                  {p.name}
                </div>
                <div className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {p.slug} · {p.tags.join(', ') || 'untagged'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span className={`badge ${p.status === 'active' ? 'badge-live' : 'badge-closed'}`}>{p.status}</span>
                <button className="btn btn-sm" onClick={() => onNavigate('session', { projectSlug: p.slug })}>
                  Chat
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(p.slug)}>
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
