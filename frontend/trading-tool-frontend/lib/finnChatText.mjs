export function parseFinnChatText(value) {
  const text = String(value ?? "").replace(/^#{1,3} +([^\n]+)$/gm, "**$1**");
  const parts = text.split(/(\*\*[^*\n]+\*\*)/g);
  return parts.filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**")
      ? { text: part.slice(2, -2), bold: true }
      : { text: part, bold: false }
  );
}
