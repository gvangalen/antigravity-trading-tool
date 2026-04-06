export function formatNumber(num) {
  return num >= 1e9 ? `${(num / 1e9).toFixed(2)}B`
    : num >= 1e6 ? `${(num / 1e6).toFixed(2)}M`
    : num?.toLocaleString() ?? '-';
}

export function setText(el, text) {
  if (!el) return;
  el.textContent = text;
  if (typeof text === 'string' && text.includes('%')) {
    el.style.color = text.includes('-') ? 'red' : 'green';
  }
}

export function showError(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.style.color = 'red';
}

export function addMacroRow(tableRef) {
  if (!tableRef?.current) return;
  const table = tableRef.current;
  const row = table.insertRow();
  row.innerHTML = `
    <td><input type="text" placeholder="Naam Indicator"></td>
    <td>Laden...</td>
    <td>N/A</td>
    <td>N/A</td>
    <td>N/A</td>
    <td><button class="btn-remove">❌</button></td>
  `;
  updateRemoveButtons();
}

export function updateRemoveButtons() {
  document.querySelectorAll(".btn-remove").forEach(button => {
    button.removeEventListener("click", removeRow);
    button.addEventListener("click", removeRow);
  });
}

export function removeRow(event) {
  event.target.closest("tr")?.remove();
}
