import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {
  getTraderTypeOptions,
  getTimeframeOptions,
  getAssetFocusOptions,
  getGoalOptions,
  getExperienceLevelOptions,
  getRiskProfileOptions,
  getBehaviorFlagOptions,
  serializeTraderProfilePreferences,
} from "../lib/traderProfileOptions.js";

const nl = JSON.parse(
  fs.readFileSync(path.join(process.cwd(), "dictionaries/nl.json"), "utf8")
);
const en = JSON.parse(
  fs.readFileSync(path.join(process.cwd(), "dictionaries/en.json"), "utf8")
);
const de = JSON.parse(
  fs.readFileSync(path.join(process.cwd(), "dictionaries/de.json"), "utf8")
);
const i18nSource = fs.readFileSync(path.join(process.cwd(), "lib/i18n.ts"), "utf8");
const providerSource = fs.readFileSync(
  path.join(process.cwd(), "app/providers/I18nProvider.tsx"),
  "utf8"
);

const canonicalPattern = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;
const timeframePattern = /^(?:\d+[mhdw]|1m)$/;

function assertCanonicalArray(values, pattern = canonicalPattern) {
  for (const value of values) {
    assert.match(value, pattern);
  }
}

test("NL renders Dutch trader profile labels", () => {
  const traderTypeMap = Object.fromEntries(
    getTraderTypeOptions(nl).map((option) => [option.value, option.label])
  );
  const goalMap = Object.fromEntries(
    getGoalOptions(nl).map((option) => [option.value, option.label])
  );
  const behaviorMap = Object.fromEntries(
    getBehaviorFlagOptions(nl).map((option) => [option.value, option.label])
  );

  assert.equal(traderTypeMap.swing_trader, "Swing trader");
  assert.equal(goalMap.wealth_building, "Vermogen opbouwen");
  assert.equal(behaviorMap.takes_profit_too_early, "Winst te vroeg nemen");
});

test("EN renders English trader profile labels", () => {
  const traderTypeMap = Object.fromEntries(
    getTraderTypeOptions(en).map((option) => [option.value, option.label])
  );
  const goalMap = Object.fromEntries(
    getGoalOptions(en).map((option) => [option.value, option.label])
  );
  const behaviorMap = Object.fromEntries(
    getBehaviorFlagOptions(en).map((option) => [option.value, option.label])
  );

  assert.equal(traderTypeMap.swing_trader, "Swing trader");
  assert.equal(goalMap.wealth_building, "Build wealth");
  assert.equal(behaviorMap.takes_profit_too_early, "Take profit too early");
});

test("auth dictionaries expose locale-specific login and reset copy", () => {
  assert.equal(nl.auth.forgotPassword, "Wachtwoord vergeten?");
  assert.equal(en.auth.forgotPassword, "Forgot password?");
  assert.equal(de.auth.forgotPassword, "Passwort vergessen?");
  assert.equal(nl.auth.sessionExpired, "Je sessie is verlopen. Log opnieuw in om verder te gaan.");
  assert.equal(en.auth.sessionExpired, "Your session has expired. Please sign in again.");
  assert.equal(de.auth.resetPasswordTitle, "Neues Passwort festlegen");
});

test("third locale dictionary can be registered without component changes", () => {
  assert.equal(de.common.language, "Language");
  assert.match(i18nSource, /SUPPORTED_LOCALES = \["nl", "en", "de"\]/);
  assert.match(i18nSource, /LOCALE_TO_FINN_LANGUAGE/);
  assert.match(providerSource, /nl,\s+en,\s+de,/m);
});

test("locale infrastructure has a default fallback and generic locale lookup", () => {
  assert.match(i18nSource, /DEFAULT_LOCALE: Locale = "nl"/);
  assert.match(i18nSource, /export function getLocaleValue/);
  assert.match(i18nSource, /if \(values\[normalizedLocale\] !== undefined\)/);
});

test("serialized trader profile payload keeps canonical keys only", () => {
  const payload = serializeTraderProfilePreferences({
    trader_types: ["swing_trader"],
    primary_timeframes: ["4h", "1d"],
    asset_focus: ["bitcoin", "stocks"],
    investment_goals_list: ["wealth_building", "capital_preservation"],
    experience_levels: ["intermediate"],
    risk_profiles: ["balanced"],
    behavior_flags: ["fomo", "takes_profit_too_early"],
  });

  assert.deepEqual(payload, {
    trader_types: ["swing_trader"],
    trader_type: "swing_trader",
    primary_timeframes: ["4h", "1d"],
    asset_focus: ["bitcoin", "stocks"],
    investment_goals_list: ["wealth_building", "capital_preservation"],
    investment_goals: "wealth_building",
    experience_levels: ["intermediate"],
    experience_level: "intermediate",
    risk_profiles: ["balanced"],
    risk_profile: "balanced",
    behavior_flags: ["fomo", "takes_profit_too_early"],
  });
});

test("profile option values stay canonical and labels stay translated", () => {
  const optionGroups = [
    getTraderTypeOptions(nl),
    getTimeframeOptions(nl),
    getAssetFocusOptions(nl),
    getGoalOptions(nl),
    getExperienceLevelOptions(nl),
    getRiskProfileOptions(nl),
    getBehaviorFlagOptions(nl),
    getTraderTypeOptions(en),
    getTimeframeOptions(en),
    getAssetFocusOptions(en),
    getGoalOptions(en),
    getExperienceLevelOptions(en),
    getRiskProfileOptions(en),
    getBehaviorFlagOptions(en),
  ];

  for (const options of optionGroups) {
    for (const option of options) {
      if (!timeframePattern.test(option.value)) {
        assert.notEqual(option.value, option.label);
      }
    }
  }

  assertCanonicalArray(getTraderTypeOptions(nl).map((option) => option.value));
  assertCanonicalArray(getAssetFocusOptions(nl).map((option) => option.value));
  assertCanonicalArray(getGoalOptions(nl).map((option) => option.value));
  assertCanonicalArray(getExperienceLevelOptions(nl).map((option) => option.value));
  assertCanonicalArray(getRiskProfileOptions(nl).map((option) => option.value));
  assertCanonicalArray(getBehaviorFlagOptions(nl).map((option) => option.value));
  assertCanonicalArray(
    getTimeframeOptions(nl).map((option) => option.value),
    timeframePattern
  );
});
