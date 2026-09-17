export function normalizeSearchTerm(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .trim();
}

export function matchesSearchQuery(query, terms = []) {
  const normalizedQuery = normalizeSearchTerm(query);
  return Boolean(normalizedQuery) && terms.some(
    (term) => normalizeSearchTerm(term).includes(normalizedQuery),
  );
}
