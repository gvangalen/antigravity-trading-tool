import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { logoutSession } from "../lib/api/logoutSession.mjs";

const dictionaries = Object.fromEntries(
  ["nl", "en", "de"].map((locale) => [
    locale,
    JSON.parse(fs.readFileSync(`dictionaries/${locale}.json`, "utf8")),
  ]),
);

const params = {
  logoutUrl: "/api/auth/logout",
  meUrl: "/api/auth/me",
  headers: { "X-CSRF-Token": "csrf-value" },
  refreshToken: null,
  verifyBrowser: true,
};

test("logout succeeds only after the server rejects the browser session", async () => {
  const requests = [];
  const result = await logoutSession({
    ...params,
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return url === params.logoutUrl ? { ok: true } : { status: 401 };
    },
  });

  assert.equal(result.success, true);
  assert.equal(requests[0].url, params.logoutUrl);
  assert.equal(requests[0].options.headers["X-CSRF-Token"], "csrf-value");
  assert.equal(requests[1].url, params.meUrl);
  assert.equal(requests[1].options.cache, "no-store");
});

test("a rejected logout or surviving cookie cannot be reported as signed out", async () => {
  const rejected = await logoutSession({
    ...params,
    fetchImpl: async () => ({ ok: false, status: 403 }),
  });
  assert.equal(rejected.success, false);

  const surviving = await logoutSession({
    ...params,
    fetchImpl: async (url) => url === params.logoutUrl
      ? { ok: true }
      : { ok: true, status: 200 },
  });
  assert.equal(surviving.success, false);
});

test("native logout passes its refresh token for revocation", async () => {
  let request;
  const result = await logoutSession({
    ...params,
    refreshToken: "native-refresh-token",
    verifyBrowser: false,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return { ok: true };
    },
  });
  assert.equal(result.success, true);
  assert.equal(request.url, params.logoutUrl);
  assert.deepEqual(JSON.parse(request.options.body), { refresh_token: "native-refresh-token" });
});

test("onboarding labels and failure feedback exist in every locale", () => {
  const usedKeys = [
    ["app/(protected)/bot/page.jsx", /\bbotGuideCopy\.?([A-Za-z][A-Za-z0-9_]*)/g, ["botPage", "onboardingGuide"]],
    ["app/onboarding/page.jsx", /\bonboardingPageCopy\?\.([A-Za-z][A-Za-z0-9_]*)/g, ["traderProfile", "onboardingPage"]],
    ["components/onboarding/OnboardingBanner.jsx", /\bbannerCopy\?\.([A-Za-z][A-Za-z0-9_]*)/g, ["traderProfile", "onboardingBanner"]],
  ];
  for (const dictionary of Object.values(dictionaries)) {
    assert.ok(dictionary.finnWorkspace.onboardingHeader.eyebrow);
    assert.ok(dictionary.finnWorkspace.onboardingHeader.flowLabel);
    for (const [file, pattern, path] of usedKeys) {
      const source = fs.readFileSync(file, "utf8");
      const section = path.reduce((value, key) => value[key], dictionary);
      for (const [, key] of source.matchAll(pattern)) {
        assert.ok(section[key], `${file}: ${key}`);
      }
    }
    assert.ok(dictionary.traderProfile.profilePage.logoutFailed);
    assert.ok(dictionary.ui.avatarMenu.logoutFailed);
  }
  const nl = dictionaries.nl;
  assert.equal(nl.finnWorkspace.pages.onboarding.eyebrow, "Startprotocol");
  assert.equal(nl.finnWorkspace.steps.onboarding[0].label, "Profiel");
  assert.equal(nl.traderProfile.analysisOnboardingStep.title, "Voeg je eerste analysebasis toe");
  assert.equal(nl.botPage.onboardingGuide.createStepTitle, "1. Bot aanmaken");
  assert.equal(dictionaries.en.botPage.onboardingGuide.createStepTitle, "1. Create bot");
  assert.equal(dictionaries.de.botPage.onboardingGuide.createStepTitle, "1. Bot erstellen");
});
