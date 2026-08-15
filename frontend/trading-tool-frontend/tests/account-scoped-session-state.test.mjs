import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const assetProviderSource = await readFile(
  new URL("../app/providers/AssetProvider.tsx", import.meta.url),
  "utf8",
);
const loginSource = await readFile(
  new URL("../app/(public)/login/page.jsx", import.meta.url),
  "utf8",
);
const registerSource = await readFile(
  new URL("../app/(public)/register/page.jsx", import.meta.url),
  "utf8",
);

test("stores selected asset per authenticated user instead of a shared browser key", () => {
  assert.match(assetProviderSource, /selectedAsset:\$\{normalized\}/);
  assert.match(assetProviderSource, /localStorage\.getItem\(userStorageKey\)/);
  assert.match(assetProviderSource, /localStorage\.setItem\(userStorageKey,\s*normalized\)/);
});

test("post-auth redirects prefer the server-side active asset for completed onboarding users", () => {
  assert.match(loginSource, /status\?\.active_asset/);
  assert.match(loginSource, /\/asset\?symbol=\$\{encodeURIComponent\(activeAsset\)\}/);
  assert.match(registerSource, /status\?\.active_asset/);
  assert.match(registerSource, /\/asset\?symbol=\$\{encodeURIComponent\(activeAsset\)\}/);
});
