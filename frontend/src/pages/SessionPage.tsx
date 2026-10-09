import { useEffect, useState, useRef } from 'react';
import { api } from '../utils/api';
import { Session } from '../types';
import { useChat } from '../hooks/useChat';

export default function SessionPage({ sessionId, projectSlug }: { sessionId?: string; projectSlug?: string }) {
  const { messages, streaming, error, send, sendStream } = useChat(sessionId || 'home', projectSlug);
  const [input, setInput] = useState('');
  const [streamingMode, setStreamingMode] = useState(false);
  const [currentReply, setCurrentReply] = useState('');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [newSessionTitle, setNewSessionTitle] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const isHome = !sessionId && !projectSlug;

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentReply]);

  async function handleSend() {
    if (!input.trim()) return;
    const text = input;
    setInput('');
    setCurrentReply('');

    if (streamingMode) {
      await sendStream(text, (chunk) => setCurrentReply(prev => prev + chunk));
    } else {
      await send(text);
    }
  }

  async function createSession() {
    try {
      if (isHome) {
        const result: any = await api.createHomeSession();
        setSessions(prev => [result, ...prev]);
      } else if (projectSlug) {
        const result: any = await api.createProjectSession(projectSlug, { title: newSessionTitle || undefined });
        setSessions(prev => [result, ...prev]);
        setNewSessionTitle('');
      }
    } catch (e) {
      alert(String(e));
    }
  }

  async function loadSessions() {
    try {
      if (isHome) {
        const data: any = await api.homeSessions();
        setSessions(Array.isArray(data) ? data : []);
      } else if (projectSlug) {
        const data: any = await api.projectSessions(projectSlug);
        setSessions(Array.isArray(data) ? data : []);
      }
    } catch {
      setSessions([]);
    }
  }

  useEffect(() => { loadSessions(); }, [isHome, projectSlug]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '70vh' }}>
      {/* Session list header */}
      {sessions.length > 0 && (
        <div style={{ padding: '8px 0', borderBottom: '2px solid var(--border)', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase' }}>Sessions:</span>
          {sessions.map(s => (
            <span key={s.slug} className={`badge ${s.status === 'open' ? 'badge-live' : 'badge-closed'}`}>
              {s.slug.split('-').slice(-1)[0]}
            </span>
          ))}
          <button className="btn btn-sm" onClick={createSession}>+ New</button>
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {messages.length === 0 && !streaming && (
          <div className="empty-state">
            {isHome ? 'Start a conversation.' : projectSlug ? `Chat in project "${projectSlug}".` : ''}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role === 'Keaton' ? 'user' : ''}`}>
            <div className="role">{m.role}</div>
            <div className="content">{m.content}</div>
          </div>
        ))}
        {streaming && (
          <div className="chat-message">
            <div className="role">Sunny</div>
            <div className="content">{currentReply || '…'}</div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '8px', background: 'var(--accent-magenta)', color: 'white', fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Input */}
      <div style={{ display: 'flex', gap: '8px', padding: '8px 0', alignItems: 'flex-end' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          placeholder="Type a message..."
          rows={1}
          style={{ flex: 1, resize: 'none' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <button className="btn btn-primary" onClick={handleSend}>Send</button>
          <label style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input type="checkbox" checked={streamingMode} onChange={e => setStreamingMode(e.target.checked)} />
            Stream
          </label>
        </div>
      </div>
    </div>
  );
}
