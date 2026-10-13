import { ReactNode } from 'react';
import Icon from './Icon';
import type { Page } from '../App';

const NAV: { page: Page; label: string; icon: string }[] = [
  { page: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
  { page: 'chat', label: 'Chat', icon: 'chat' },
  { page: 'projects', label: 'Projects', icon: 'folder' },
  { page: 'search', label: 'Search', icon: 'search' },
  { page: 'settings', label: 'Settings', icon: 'settings' },
];

export default function Layout({
  current,
  onNavigate,
  onLogout,
  children,
}: {
  current: Page;
  onNavigate: (page: Page) => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  const isActive = (p: Page) => current === p || (p === 'chat' && current === 'session');

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><Icon name="sun" size={17} /></span>
          Sunny
        </div>
        {NAV.map(n => (
          <button key={n.page} className={`nav-item ${isActive(n.page) ? 'active' : ''}`} onClick={() => onNavigate(n.page)}>
            <Icon name={n.icon} /> {n.label}
          </button>
        ))}
        <div className="spacer" />
        <button className="nav-item" onClick={onLogout}>
          <Icon name="logout" /> Log out
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark"><Icon name="sun" size={17} /></span>
            Sunny
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onLogout} aria-label="Log out">
            <Icon name="logout" size={19} />
          </button>
        </header>
        {children}
      </div>

      <nav className="tabbar">
        {NAV.map(n => (
          <button key={n.page} className={`nav-item ${isActive(n.page) ? 'active' : ''}`} onClick={() => onNavigate(n.page)}>
            <Icon name={n.icon} size={20} />
            {n.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
