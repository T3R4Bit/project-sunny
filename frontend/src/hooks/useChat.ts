import { useEffect, useState } from 'react';
import { Message } from '../types';
import { api } from '../utils/api';

export function useChat(sessionSlug: string | null, projectSlug?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');

  // Load the recorded turns whenever the selected session changes
  useEffect(() => {
    setMessages([]);
    setError('');
    if (!sessionSlug) return;
    let cancelled = false;
    api.session(sessionSlug, projectSlug)
      .then((data: { turns?: Message[] }) => { if (!cancelled) setMessages(data.turns || []); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load session'); });
    return () => { cancelled = true; };
  }, [sessionSlug, projectSlug]);

  async function send(text: string, slug = sessionSlug) {
    if (!text.trim() || !slug) return;
    setMessages(prev => [...prev, { role: 'Keaton', content: text }, { role: 'Sunny', content: '' }]);
    setStreaming(true);
    setError('');

    const appendToReply = (chunk: string) =>
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        updated[updated.length - 1] = { ...last, content: last.content + chunk };
        return updated;
      });

    try {
      await api.streamChat(slug, text, projectSlug, appendToReply);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setStreaming(false);
    }
  }

  return { messages, streaming, error, send };
}
