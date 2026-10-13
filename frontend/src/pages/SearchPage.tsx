import { useState } from 'react';
import { api } from '../utils/api';
import Icon from '../components/Icon';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.search(query, 'keyword');
      setResults(Array.isArray(data) ? data : []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Search</h1>
          <div className="sub">Chats, projects and notes in the vault</div>
        </div>
      </div>

      <form className="row" style={{ marginBottom: 20 }} onSubmit={search}>
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search the vault…" autoFocus />
        <button className="btn btn-primary" type="submit" disabled={loading || !query.trim()}>
          <Icon name="search" size={15} /> {loading ? 'Searching' : 'Search'}
        </button>
      </form>

      {results && results.length === 0 && <div className="card empty">No results for "{query}".</div>}
      {results && results.length > 0 && (
        <div className="card">
          <div className="list">
            {results.map((r, i) => (
              <div key={i} className="list-row" style={{ alignItems: 'flex-start' }}>
                <div className="grow">
                  <div className="row">
                    <span className="mono truncate">{r.path}</span>
                    {r.project && <span className="pill">{r.project}</span>}
                  </div>
                  <div className="small" style={{ color: 'var(--text-2)', marginTop: 4 }}>{r.snippet || r.text || ''}</div>
                </div>
                <span className="pill">{r.kind}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
