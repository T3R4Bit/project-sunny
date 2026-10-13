import { useEffect, useState, useRef } from 'react';
import { api } from '../utils/api';
import { Session } from '../types';
import { useChat } from '../hooks/useChat';
import Icon from '../components/Icon';

export default function SessionPage({ sessionId, projectSlug }: { sessionId?: string; projectSlug?: string }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [current, setCurrent] = useState<string | null>(sessionId || null);
  const { messages, streaming, error, send } = useChat(current, projectSlug);
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
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
    inputRef.current?.focus();
  }

  return (
    <div className="page">
      <div className="page-head" style={{ marginBottom: 12 }}>
        <div>
          <h1>{projectSlug ? projectSlug : 'Chat'}</h1>
          <div className="sub">{projectSlug ? 'Project conversation' : 'Talk to Sunny'}</div>
        </div>
        <button className="btn btn-sm" onClick={() => { setCurrent(null); inputRef.current?.focus(); }}>
          <Icon name="plus" size={15} /> New chat
        </button>
      </div>

      {sessions.length > 0 && (
        <div className="chips" style={{ marginBottom: 12 }}>
          {sessions.map(s => (
            <button
              key={s.slug}
              className={`chip ${s.slug === current ? 'active' : ''}`}
              onClick={() => setCurrent(s.slug)}
              title={s.summary || s.title}
            >
              <span className={`dot ${s.status === 'live' ? 'ok' : ''}`} style={{ width: 6, height: 6, boxShadow: 'none' }} />
              <span className="truncate">{s.title || s.slug}</span>
            </button>
          ))}
        </div>
      )}

      <div className="chat">
        <div className="chat-scroll">
          {messages.length === 0 && (
            <div className="empty">
              <div className="brand-mark" style={{ width: 44, height: 44, margin: '0 auto 12px', borderRadius: 12 }}>
                <Icon name="sun" size={24} />
              </div>
              {current ? 'No messages yet.' : 'Start a new conversation.'}
            </div>
          )}
          {messages.map((m, i) => {
            const me = m.role === 'Keaton';
            const pending = streaming && i === messages.length - 1 && !m.content;
            return (
              <div key={i} className={`msg ${me ? 'me' : ''}`}>
                <div className="avatar">{me ? 'K' : <Icon name="sun" size={16} />}</div>
                <div className="bubble">
                  {pending ? <span className="typing"><i /><i /><i /></span> : m.content}
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>

        {error && <div className="error-box" style={{ marginBottom: 8 }}>{error}</div>}

        <div className="composer">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
            }}
            placeholder="Message Sunny…"
            rows={1}
          />
          <button className="btn btn-primary btn-icon" onClick={handleSend} disabled={streaming || !input.trim()} aria-label="Send">
            <Icon name="send" size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}
