import { useLocation } from 'react-router-dom';
import { FiMenu } from 'react-icons/fi';
import './Navbar.css';

/**
 * Top Navbar component displaying the current page title
 * @param {function} onToggleSidebar - toggle handler for the navigation sidebar
 */
const Navbar = ({ onToggleSidebar }) => {
  const location = useLocation();

  /**
   * Helper to map route pathname to page title
   */
  const getPageTitle = (pathname) => {
    if (pathname === '/') return 'Home';
    if (pathname === '/upload') return 'Upload Paper';
    if (pathname.startsWith('/processing/')) return 'Processing Paper';
    if (pathname.startsWith('/review/')) return 'Review Paper';
    // if (pathname === '/question-bank') return 'Question Bank';
    if (pathname === '/generate') return 'Generate Practice Paper';
    if (pathname.startsWith('/practice-paper/')) return 'Practice Paper';
    return 'Test Series';
  };

  const title = getPageTitle(location.pathname);

  return (
    <header className="navbar">
      <button
        className="navbar-toggle-btn"
        onClick={onToggleSidebar}
        aria-label="Toggle Sidebar"
      >
        <FiMenu />
      </button>
      <h2 className="navbar-title">{title}</h2>
    </header>
  );
};

export default Navbar;
