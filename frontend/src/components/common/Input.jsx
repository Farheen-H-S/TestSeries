import './Input.css';

/**
 * Reusable Input text field component
 */
const Input = ({
  label,
  id,
  type = 'text',
  placeholder,
  value,
  onChange,
  error,
  required = false,
  className = '',
  ...props
}) => {
  return (
    <div className={`input-container ${error ? 'input-has-error' : ''} ${className}`}>
      {label && (
        <label htmlFor={id} className="input-label">
          {label} {required && <span className="input-required">*</span>}
        </label>
      )}
      <input
        type={type}
        id={id}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        required={required}
        className="input-field"
        {...props}
      />
      {error && <span className="input-error-msg">{error}</span>}
    </div>
  );
};

export default Input;
