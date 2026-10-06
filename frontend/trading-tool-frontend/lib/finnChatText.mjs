export function parseFinnChatText(value) {
  const text = String(value ?? "").replace(/^#{1,3} +([^\n]+)$/gm, "**$1**");
  // FINN may use either Markdown emphasis form around a setup name. Keep
  // unmatched stars and spaced multiplication signs as ordinary text.
  const parts = text.split(/(\*\*[^*\s\n](?:[^*\n]*?[^*\s\n])?\*\*|\*[^*\s\n](?:[^*\n]*?[^*\s\n])?\*)/g);
  return parts.filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**")
      ? { text: part.slice(2, -2), bold: true }
      : part.startsWith("*") && part.endsWith("*")
      ? { text: part.slice(1, -1), bold: true }
      : { text: part, bold: false }
  );
}
