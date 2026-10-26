import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = await readFile(new URL("../components/scoring/IndicatorConfigModal.jsx", import.meta.url), "utf8");

test("indicator explanation and summary use the localized name", () => {
  const roleModelSource = source.match(/function getRoleModel\([\s\S]*?\n}\n\nexport default function/)?.[0]
    .replace(/\n\nexport default function$/, "");
  assert.ok(roleModelSource);
  const getRoleModel = runInNewContext(`${roleModelSource}\ngetRoleModel`, {
    normalizeIndicatorName: (name) => name,
    getIndicatorLabel: (name, copy) => {
      assert.ok(copy, "role model must pass localized copy to the label resolver");
      return copy.indicatorNames[name];
    },
  });
  const copy = {
    thisWorkflow: "deze analyse",
    indicatorNames: { macd_hist_pct: "MACD-histogram (%)" },
    roles: { generic: {
      description: "Uitleg over {indicator}",
      whenQuestion: "Wanneer?",
      always: { label: "Altijd" },
      interpretationQuestion: "Hoe?",
      standard: { label: "Normaal" },
      contrarian: { label: "Omgekeerd" },
      recommendation: "Past bij {profile}",
    } },
  };
  const role = getRoleModel("technical", "macd_hist_pct", {}, copy);
  assert.equal(role.description, "Uitleg over MACD-histogram (%)");
  assert.equal(role.summaryLabel, "MACD-histogram (%)");
});
