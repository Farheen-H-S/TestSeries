import './Badge.css';

/**
 * Reusable Badge component for status indicators
 * @param {string} status - status text ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')
 */
const Badge = ({ status = 'PENDING', className = '' }) => {
  const normalizedStatus = status.toUpperCase();
  
  // Create user-friendly labels
  const labelMap = {
    PENDING: 'Pending',
    PROCESSING: 'Processing',
    COMPLETED: 'Completed',
    FAILED: 'Failed',
  };

  const displayLabel = labelMap[normalizedStatus] || status;
  const statusClass = normalizedStatus.toLowerCase();

  return (
    <span className={`badge badge-${statusClass} ${className}`}>
      {displayLabel}
    </span>
  );
};

export default Badge;
