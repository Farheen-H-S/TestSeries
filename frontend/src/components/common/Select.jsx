import './Select.css';

/**
 * Reusable Select Dropdown component
 */
const Select = ({
  label,
  id,
  options = [],
  value,
  onChange,
  error,
  required = false,
  placeholder = 'Select an option',
  className = '',
  ...props
}) => {
  return (
    <div className={`select-container ${error ? 'select-has-error' : ''} ${className}`}>
      {label && (
        <label htmlFor={id} className="select-label">
          {label} {required && <span className="select-required">*</span>}
        </label>
      )}
      <div className="select-wrapper">
        <select
          id={id}
          value={value}
          onChange={onChange}
          required={required}
          className="select-field"
          {...props}
        >
          <option value="" disabled>
            {placeholder}
          </option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      {error && <span className="select-error-msg">{error}</span>}
    </div>
  );
};

export default Select;
