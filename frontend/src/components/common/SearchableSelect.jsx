import { useState, useRef, useEffect, useMemo } from 'react';
import './SearchableSelect.css';

/**
 * Reusable Searchable Select Dropdown component
 * Features:
 * - Type-to-filter options
 * - Arrow keys (Up/Down) navigation
 * - Enter to select, Escape to close
 * - Click outside to close
 */
const SearchableSelect = ({
  label,
  id,
  options = [], // Expected: [{ value, label, ... }]
  value,
  onChange, // Callback receiving { target: { name, value } } to match standard forms
  name,
  error,
  required = false,
  placeholder = 'Select an option',
  disabled = false,
  className = '',
  onCreateOption = null, // Optional callback: (text) => void
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  // Synchronize search term with initial selection or changes
  const selectedOption = options.find((opt) => opt.value === value);

  useEffect(() => {
    if (selectedOption) {
      setSearchTerm(selectedOption.label);
    } else {
      setSearchTerm('');
    }
  }, [value, selectedOption]);

  // Helper to normalize strings: trim, collapse spaces, lowercase
  const normalizeText = (text) => {
    if (!text) return '';
    return text.trim().toLowerCase().replace(/\s+/g, ' ');
  };

  const normalizedSearch = normalizeText(searchTerm);

  // Filter options based on search term (using normalized comparison), startsWith matches first
  const filteredOptions = useMemo(() => {
    if (!normalizedSearch) return options;
    const startsWithMatches = [];
    const containsMatches = [];
    
    options.forEach((opt) => {
      const optNormalized = normalizeText(opt.label);
      if (optNormalized.startsWith(normalizedSearch)) {
        startsWithMatches.push(opt);
      } else if (optNormalized.includes(normalizedSearch)) {
        containsMatches.push(opt);
      }
    });
    
    return [...startsWithMatches, ...containsMatches];
  }, [options, normalizedSearch]);

  // Check if an exact normalized match already exists in options
  const hasExactMatch = options.some((opt) => normalizeText(opt.label) === normalizedSearch);

  // Compute canCreate once
  const canCreate = !!(onCreateOption && normalizedSearch && !hasExactMatch);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        closeDropdown();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [searchTerm, selectedOption]);

  const openDropdown = () => {
    if (disabled) return;
    setIsOpen(true);
    setHighlightedIndex(-1);
    // Focus and select all text to make it easy to clear/type
    if (inputRef.current) {
      inputRef.current.select();
    }
  };

  const closeDropdown = () => {
    setIsOpen(false);
    // If closed without selecting, revert text back to selected option label or empty
    if (selectedOption) {
      setSearchTerm(selectedOption.label);
    } else {
      setSearchTerm('');
    }
  };

  const selectOption = (option) => {
    if (onChange) {
      onChange({ target: { name, value: option.value } });
    }
    setSearchTerm(option.label);
    setIsOpen(false);
  };

  const handleInputChange = (e) => {
    setSearchTerm(e.target.value);
    if (!isOpen) {
      setIsOpen(true);
    }
    setHighlightedIndex(0);
  };

  const handleKeyDown = (e) => {
    if (disabled) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        setHighlightedIndex((prev) =>
          prev < filteredOptions.length - 1 ? prev + 1 : 0
        );
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (isOpen) {
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : filteredOptions.length - 1
        );
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (isOpen && highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
        selectOption(filteredOptions[highlightedIndex]);
      } else if (isOpen && filteredOptions.length === 0 && canCreate) {
        onCreateOption(searchTerm.trim());
        closeDropdown();
      } else if (!isOpen) {
        setIsOpen(true);
      }
    } else if (e.key === 'Escape') {
      closeDropdown();
      if (inputRef.current) {
        inputRef.current.blur();
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className={`search-select-container ${error ? 'search-select-has-error' : ''} ${
        disabled ? 'search-select-disabled' : ''
      } ${className}`}
    >
      {label && (
        <label htmlFor={id} className="search-select-label">
          {label} {required && <span className="search-select-required">*</span>}
        </label>
      )}

      <div className="search-select-wrapper">
        <input
          ref={inputRef}
          type="text"
          id={id}
          value={searchTerm}
          onChange={handleInputChange}
          onFocus={openDropdown}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="search-select-field"
          autoComplete="off"
        />
        
        {/* Dropdown Toggle Indicator */}
        <span className="search-select-arrow" onClick={openDropdown}>
          <svg
            className={`arrow-icon ${isOpen ? 'arrow-icon-open' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </span>

        {/* Dropdown List */}
        {isOpen && (
          <ul className="search-select-options">
            {filteredOptions.length > 0 ? (
              filteredOptions.map((option, idx) => {
                const isSelected = option.value === value;
                const isHighlighted = idx === highlightedIndex;
                return (
                  <li
                    key={option.value}
                    onClick={() => selectOption(option)}
                    className={`search-select-option-item ${
                      isSelected ? 'option-selected' : ''
                    } ${isHighlighted ? 'option-highlighted' : ''}`}
                  >
                    <div className="option-content">
                      <span className="option-label">{option.label}</span>
                      {option.sublabel && (
                        <span className="option-sublabel">{option.sublabel}</span>
                      )}
                    </div>
                  </li>
                );
              })
            ) : canCreate ? (
              <li
                onClick={() => {
                  onCreateOption(searchTerm.trim());
                  closeDropdown();
                }}
                className="search-select-option-item option-highlighted"
              >
                <div className="option-content">
                  <span className="option-label">No chapter found.</span>
                  <span className="option-sublabel" style={{ fontWeight: 600, color: 'var(--accent-color)', marginTop: '0.125rem' }}>
                    Create "{searchTerm.trim()}"?
                  </span>
                </div>
              </li>
            ) : (
              <li className="search-select-no-results">No options match search</li>
            )}
          </ul>
        )}
      </div>
      {error && <span className="search-select-error-msg">{error}</span>}
    </div>
  );
};

export default SearchableSelect;
