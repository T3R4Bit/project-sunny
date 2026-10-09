import { useState } from 'react';
import { api } from '../utils/api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('hybrid');
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.search(query, mode);
      setResults(Array.isArray(data) ? data : []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>Search</h2>
      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
        <select value={mode} onChange={e => setMode(e.target.value)}>
          <option value="hybrid">Hybrid (RFM)</option>
          <option value="keyword">Keyword (FTS5)</option>
          <option value="semantic">Semantic (Vectors)</option>
        </select>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') search(); }}
          placeholder="Search the vault..."
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" onClick={search} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
      <div style={{ marginTop: '16px' }}>
        {results.map((r, i) => (
          <div key={i} className="list-item">
            <div style={{ flex: 1 }}>
              <div className="mono">{r.path}</div>
              <div style={{ fontSize: 13 }}>{r.snippet || r.text || ''}</div>
              {r.score !== undefined && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  score: {r.score.toFixed(4)}
                </div>
              )}
            </div>
            <div className="badge badge-live">{r.kind}</div>
          </div>
        ))}
        {results.length === 0 && query && <div className="empty-state">No results.</div>}
      </div>
    </div>
  );
}
