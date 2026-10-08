import { useState } from 'react';
import { Message } from '../types';
import { api } from '../utils/api';

export function useChat(sessionSlug: string, projectSlug?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');

  async function send(text: string, onFullReply?: (reply: string) => void) {
    if (!text.trim()) return;
    const userMsg: Message = { role: 'Keaton', content: text };
    setMessages(prev => [...prev, userMsg]);
    setStreaming(true);
    setError('');

    try {
      const result = await api.chat(sessionSlug, text, projectSlug);
      const assistantMsg: Message = { role: 'Sunny', content: result.reply || '' };
      setMessages(prev => [...prev, assistantMsg]);
      onFullReply?.(result.reply || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setStreaming(false);
    }
  }

  async function sendStream(
    text: string,
    onChunk: (chunk: string) => void,
    onComplete?: (full: string) => void
  ) {
    if (!text.trim()) return;
    const userMsg: Message = { role: 'Keaton', content: text };
    setMessages(prev => [...prev, userMsg]);
    setStreaming(true);
    setError('');

    try {
      let fullReply = '';
      const assistantMsg: Message = { role: 'Sunny', content: '' };
      setMessages(prev => [...prev, assistantMsg]);

      await api.streamChat(
        sessionSlug,
        text,
        projectSlug,
        (chunk) => {
          fullReply += chunk;
          onChunk?.(chunk);
        },
        () => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'Sunny') {
              updated[updated.length - 1] = { ...last, content: fullReply };
            }
            return updated;
          });
          onComplete?.(fullReply);
        }
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setStreaming(false);
    }
  }

  return { messages, streaming, error, send, sendStream };
}
