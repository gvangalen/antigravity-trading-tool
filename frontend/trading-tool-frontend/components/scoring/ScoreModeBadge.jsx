"use client";

export default function ScoreModeBadge({ mode }) {
  const labels = {
    standard: "Standaard",
    contrarian: "Contrair",
    custom: "Aangepast",
  };

  const classes = {
    standard: "badge-standard",
    contrarian: "badge-contrarian",
    custom: "badge-custom",
  };

  return (
    <span className={`badge ${classes[mode] || "badge-standard"}`}>
      {labels[mode] || "Standaard"}
    </span>
  );
}
