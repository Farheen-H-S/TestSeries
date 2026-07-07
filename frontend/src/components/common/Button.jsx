import './Button.css';

/**
 * Reusable Button component
 * @param {string} type - button type html ('button', 'submit', 'reset')
 * @param {string} variant - visual variant ('primary', 'secondary', 'outline', 'text')
 * @param {boolean} disabled - whether button is disabled
 * @param {function} onClick - click handler
 * @param {string} tooltip - optional generic tooltip to show when disabled or active
 * @param {React.ReactNode} children - button text/elements
 */
const Button = ({
  type = 'button',
  variant = 'primary',
  disabled = false,
  onClick,
  tooltip,
  children,
  className = '',
  ...props
}) => {
  return (
    <button
      type={type}
      className={`btn btn-${variant} ${disabled ? 'btn-disabled' : ''} ${className}`}
      disabled={disabled}
      onClick={disabled ? undefined : onClick}
      data-tooltip={tooltip}
      {...props}
    >
      {children}
    </button>
  );
};

export default Button;
