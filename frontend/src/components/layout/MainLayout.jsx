import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import './MainLayout.css';

/**
 * Main application layout wrapping sidebar, top navbar, and core outlet views
 */
const MainLayout = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Mobile drawer open/closed
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false); // Tablet collapsed state

  // Handle responsive design sidebar defaults on window resize
  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      if (width >= 1024) {
        // Desktop default: fully expanded sidebar
        setIsSidebarOpen(false);
        setIsSidebarCollapsed(false);
      } else if (width >= 768 && width < 1024) {
        // Tablet default: collapsed sidebar
        setIsSidebarCollapsed(true);
      } else {
        // Mobile default: drawer overlay (closed initially)
        setIsSidebarCollapsed(false);
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize(); // Execute on initial mount

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  /**
   * Action to toggle sidebar display states depending on current viewport width
   */
  const handleToggleSidebar = () => {
    const width = window.innerWidth;
    if (width >= 768) {
      // Collapse/expand sidebar on desktop and tablet
      setIsSidebarCollapsed(!isSidebarCollapsed);
    } else {
      // Toggle slide-out drawer on mobile
      setIsSidebarOpen(!isSidebarOpen);
    }
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
  };

  return (
    <div className="layout-container">
      <Sidebar
        isOpen={isSidebarOpen}
        isCollapsed={isSidebarCollapsed}
        onClose={handleCloseSidebar}
      />
      <div
        className={`layout-main ${
          isSidebarCollapsed ? 'layout-main-collapsed' : ''
        }`}
      >
        <Navbar onToggleSidebar={handleToggleSidebar} />
        <main className="layout-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default MainLayout;
