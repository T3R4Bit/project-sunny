export interface Message {
  role: 'Keaton' | 'Sunny' | 'system';
  content: string;
}

export interface Project {
  slug: string;
  name: string;
  description: string;
  status: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Session {
  slug: string;
  project_slug: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}
