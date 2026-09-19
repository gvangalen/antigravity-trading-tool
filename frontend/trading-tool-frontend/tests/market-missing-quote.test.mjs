import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

for (const component of ["MarketLiveCard.jsx", "MarketTerminalHUD.jsx"]) {
  test(`${component} does not present missing market movement as zero`, () => {
    const source = fs.readFileSync(
      path.join(root, "components/market", component),
      "utf8",
    );

    assert.doesNotMatch(source, /change_24h\s*\|\|\s*0/);
    assert.match(source, /hasPriceChange/);
    assert.match(source, /priceChange\.toFixed\(2\).*:\s*["']—["']/s);
  });
}
