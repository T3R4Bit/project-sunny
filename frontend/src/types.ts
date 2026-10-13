export interface Message {
  role: 'Keaton' | 'Sunny' | 'system';
  content: string;
}

export interface Project {
  slug: string;
  title: string;
  description: string;
  status: string;
  tags: string[];
  created: string;
}

export interface Session {
  slug: string;
  title: string;
  project_slug: string | null;
  status: string;
  started: string;
  summary?: string;
}
