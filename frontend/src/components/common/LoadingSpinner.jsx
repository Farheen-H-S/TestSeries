import './LoadingSpinner.css';

/**
 * Reusable LoadingSpinner component
 */
const LoadingSpinner = ({ size = 'medium', className = '' }) => {
  return (
    <div className={`spinner-container ${className}`}>
      <div className={`spinner spinner-${size}`} />
      <span className="spinner-sr-only">Loading...</span>
    </div>
  );
};

export default LoadingSpinner;
