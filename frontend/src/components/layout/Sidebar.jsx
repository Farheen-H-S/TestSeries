import { NavLink } from 'react-router-dom';
import { FiHome, FiUpload, FiDatabase, FiFileText, FiBookOpen } from 'react-icons/fi';
import './Sidebar.css';

/**
 * Sidebar navigation component
 * @param {boolean} isOpen - sidebar open state (for mobile drawer)
 * @param {boolean} isCollapsed - sidebar collapsed state (for tablet)
 * @param {function} onClose - function to close drawer (mobile)
 */
const Sidebar = ({ isOpen, isCollapsed, onClose }) => {
  const navItems = [
    { path: '/', name: 'Home', icon: <FiHome /> },
    { path: '/subjects', name: 'Subjects', icon: <FiBookOpen /> },
    { path: '/upload', name: 'Upload Paper', icon: <FiUpload /> },
    { path: '/question-bank', name: 'Question Bank', icon: <FiDatabase /> },
    { path: '/generate', name: 'Generate Paper', icon: <FiFileText /> },
  ];

  return (
    <>
      {/* Mobile Sidebar overlay */}
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}

      <aside
        className={`sidebar ${isCollapsed ? 'sidebar-collapsed' : ''} ${
          isOpen ? 'sidebar-open' : ''
        }`}
      >
        <div className="sidebar-brand">
          <span className="brand-text">Test Series</span>
        </div>

        <nav className="sidebar-nav">
          <ul>
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className={({ isActive }) =>
                    `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
                  }
                  onClick={onClose}
                >
                  <span className="sidebar-link-icon">{item.icon}</span>
                  {!isCollapsed && <span className="sidebar-link-name">{item.name}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
