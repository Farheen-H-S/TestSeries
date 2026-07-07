import './Card.css';

/**
 * Reusable Card container component
 */
const Card = ({ children, className = '', onClick, ...props }) => {
  return (
    <div
      className={`card ${onClick ? 'card-interactive' : ''} ${className}`}
      onClick={onClick}
      {...props}
    >
      {children}
    </div>
  );
};

export default Card;
