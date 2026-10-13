import { useEffect, useState, useRef } from 'react';
import { api } from '../utils/api';
import { Session } from '../types';
import { useChat } from '../hooks/useChat';

export default function SessionPage({ sessionId, projectSlug }: { sessionId?: string; projectSlug?: string }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [current, setCurrent] = useState<string | null>(sessionId || null);
  const { messages, streaming, error, send } = useChat(current, projectSlug);
  const [input, setInput] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function loadSessions() {
    try {
      const data: any = projectSlug ? await api.projectSessions(projectSlug) : await api.homeSessions();
      const list: Session[] = Array.isArray(data) ? data : [];
      setSessions(list);
      if (!sessionId) setCurrent(list.find(s => s.status === 'live')?.slug || null);
    } catch {
      setSessions([]);
    }
  }

  useEffect(() => { loadSessions(); }, [projectSlug]);

  async function createSession(title?: string): Promise<string | null> {
    try {
      const created: Session = projectSlug
        ? await api.createProjectSession(projectSlug, { title })
        : await api.createHomeSession(title);
      setSessions(prev => [created, ...prev]);
      setCurrent(created.slug);
      return created.slug;
    } catch (e) {
      alert(String(e));
      return null;
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || streaming) return;
    setInput('');
    // First message with no session open starts one, titled from the message
    const slug = current || await createSession(text.slice(0, 50));
    if (slug) await send(text, slug);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '75vh' }}>
      <div style={{ padding: '8px 0', borderBottom: '2px solid var(--border)', display: 'flex', gap: '8px', alignItems: 'center', overflowX: 'auto' }}>
        <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase' }}>
          {projectSlug ? `${projectSlug}:` : 'Chats:'}
        </span>
        <button className="btn btn-sm" onClick={() => createSession()}>+ New</button>
        {sessions.map(s => (
          <button
            key={s.slug}
            className={`badge ${s.status === 'live' ? 'badge-live' : 'badge-closed'}`}
            style={{ cursor: 'pointer', outline: s.slug === current ? '2px solid var(--text)' : 'none', whiteSpace: 'nowrap' }}
            onClick={() => setCurrent(s.slug)}
            title={s.summary || s.title}
          >
            {s.title || s.slug}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {messages.length === 0 && (
          <div className="empty-state">
            {projectSlug ? `Chat in project "${projectSlug}".` : 'Start a conversation.'}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role === 'Keaton' ? 'user' : ''}`}>
            <div className="role">{m.role}</div>
            <div className="content" style={{ whiteSpace: 'pre-wrap' }}>
              {m.content || (streaming && i === messages.length - 1 ? '…' : '')}
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {error && (
        <div style={{ padding: '8px', background: 'var(--accent-magenta)', color: 'white', fontSize: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: '8px', padding: '8px 0', alignItems: 'flex-end' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          placeholder="Message Sunny..."
          rows={2}
          style={{ flex: 1, resize: 'none' }}
        />
        <button className="btn btn-primary" onClick={handleSend} disabled={streaming}>Send</button>
      </div>
    </div>
  );
}
