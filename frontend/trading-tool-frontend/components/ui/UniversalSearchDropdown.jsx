'use client';

import { useState, useEffect, useRef } from 'react';

export default function UniversalSearchDropdown({
  label = 'Zoek een item',
  items = [],
  selected = null,
  onSelect,
  placeholder = 'Typ om te zoeken…',
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);

  const wrapperRef = useRef(null);

  // 🔎 Live filter
  useEffect(() => {
    if (!query) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const q = query.toLowerCase();
    const filtered = items.filter(
      (i) =>
        i.display_name.toLowerCase().includes(q) ||
        i.name.toLowerCase().includes(q)
    );

    setResults(filtered);
    setIsOpen(filtered.length > 0);
    setHighlightIndex(-1);
  }, [query, items]);

  // 🔐 Klik buiten → sluiten dropdown
  useEffect(() => {
    function handleOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  // ⌨️ Keyboard navigatie
  const handleKeyDown = (e) => {
    if (!isOpen) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex((prev) =>
        prev < results.length - 1 ? prev + 1 : prev
      );
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((prev) => (prev > 0 ? prev - 1 : prev));
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightIndex >= 0) {
        const item = results[highlightIndex];
        onSelect(item);
        setQuery('');
        setIsOpen(false);
      }
    }

    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  // 🔘 Klik op resultaat
  const handleSelect = (item) => {
    onSelect(item);
    setQuery('');
    setIsOpen(false);
  };

  return (
    <div className="relative mb-4" ref={wrapperRef}>
      {label && (
        <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-200">
          {label}
        </label>
      )}

      <input
        type="text"
        placeholder={placeholder}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => query && results.length > 0 && setIsOpen(true)}
        onKeyDown={handleKeyDown}
        autoComplete="off"
        className="
          w-full p-2 border rounded bg-white dark:bg-gray-800 dark:text-gray-100
          focus:outline-none focus:ring-2 focus:ring-blue-500
        "
      />

      {isOpen && results.length > 0 && (
        <ul
          className="
            absolute left-0 right-0 top-full z-50 max-h-60 overflow-y-auto
            bg-white dark:bg-gray-800 border rounded shadow animate-fade-slide
          "
        >
          {results.map((item, idx) => (
            <li
              key={item.name}
              onClick={() => handleSelect(item)}
              className={`
                p-2 cursor-pointer flex justify-between
                ${highlightIndex === idx
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700'}
              `}
            >
              <span>{item.display_name}</span>
              <span className="text-xs text-gray-400 dark:text-gray-500">
                ({item.name})
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
