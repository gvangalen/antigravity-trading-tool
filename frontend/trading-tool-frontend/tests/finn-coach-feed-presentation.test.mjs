import assert from "node:assert/strict";
import test from "node:test";

import { coachFeedPresentation, coachFeedTime } from "../lib/finnCoachFeedPresentation.mjs";

const copy = {
  today: "Vandaag", yesterday: "Gisteren",
  noPaperOrder: "Er is geen Paper-order geplaatst.",
  paperWaitReason: "Geen Paper-order geplaatst: {reason}",
};

test("Paper bot wait stays brief and shows a saved reason when present", () => {
  const item = { event_type: "bot_decision", subject_type: "bot",
    title: "Je BTC-bot wacht · Paper", description: "Lange standaardtekst.",
    evidence: { action: "hold", reasons: ["Score lager dan de ingestelde grens"] } };
  assert.deepEqual(coachFeedPresentation(item, copy), {
    title: "Je BTC-bot wacht", badge: "Paper",
    description: "Geen Paper-order geplaatst: Score lager dan de ingestelde grens",
  });
  assert.equal(coachFeedPresentation({ ...item, evidence: { action: "hold", reasons: [] } }, copy).description,
    "Er is geen Paper-order geplaatst.");
});

test("the feed time uses the same bot activity moment as sorting", () => {
  const time = coachFeedTime({ created_at: "2026-11-19T08:00:00Z",
    activity_at: "2026-11-20T00:03:00Z" }, "nl", copy, Date.parse("2026-11-20T12:00:00Z"));
  assert.equal(time.value, "2026-11-20T00:03:00.000Z");
  assert.match(time.label, /^Vandaag · /);
});
