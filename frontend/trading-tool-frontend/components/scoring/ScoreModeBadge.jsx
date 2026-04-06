"use client";

export default function ScoreModeBadge({ mode }) {
  const labels = {
    standard: "Standard",
    contrarian: "Contrarian",
    custom: "Custom",
  };

  const classes = {
    standard: "badge-standard",
    contrarian: "badge-contrarian",
    custom: "badge-custom",
  };

  return (
    <span className={`badge ${classes[mode] || "badge-standard"}`}>
      {labels[mode] || "Standard"}
    </span>
  );
}
