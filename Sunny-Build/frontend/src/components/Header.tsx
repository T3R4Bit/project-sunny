import { useAuth } from '../hooks/useAuth';

export default function Header({
  currentPage,
  onNavigate,
  onLogout,
}: {
  currentPage: string;
  onNavigate: (page: string) => void;
  onLogout: () => void;
}) {
  useAuth(); // for auth state

  return (
    <header className="header">
      <h1>Sunny</h1>
      <nav className="nav">
        <a href="#" className={currentPage === 'home' ? 'active' : ''} onClick={e => { e.preventDefault(); onNavigate('home'); }}>
          Home
        </a>
        <a href="#" className={currentPage === 'projects' ? 'active' : ''} onClick={e => { e.preventDefault(); onNavigate('projects'); }}>
          Projects
        </a>
        <a href="#" className={currentPage === 'search' ? 'active' : ''} onClick={e => { e.preventDefault(); onNavigate('search'); }}>
          Search
        </a>
        <a href="#" className={currentPage === 'admin' ? 'active' : ''} onClick={e => { e.preventDefault(); onNavigate('admin'); }}>
          Admin
        </a>
      </nav>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="btn btn-sm" onClick={onLogout}>Logout</button>
      </div>
    </header>
  );
}
