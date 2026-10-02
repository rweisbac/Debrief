# Stress report: how far the offline checks and scorers can be trusted

Summary: caught 31 of 61 planted problems; 7 false alarms on 17 clean variants.

Method. Every case starts from a clean, hand-built output (tests/fakes.py for deal_a, and equivalent objects for deal_b, deal_c, deal_x and deal_y built in the harness from verbatim transcript excerpts). Each one plants a single problem. The harness then runs the deterministic checks (`checks.run_artifact` / `checks.run_all`), the rule overrides (`rules.apply`, `rules.enforce_map_agreed`), the schema validators (`validate_assessment`) and the eval scorers (`evals/scoring.py`), the same way `Chain.run` does offline. The model verifier never runs offline, so `verifier` is empty unless a case supplies verdicts. All cases are in tests/stress/test_stress_harness.py. A missed problem or a false alarm is an `xfail(strict=True)` with a `GAP:` reason, so a fix turns it into an XPASS failure and someone has to update the test.

Counting. "Caught" means the expected catcher fired on its own, with no model involved. O4 is counted as caught, but it only works if the model verifier has already flagged the sentence. Two baseline tests check that the clean fixtures pass everything; they are not counted in either total.

Final suite: `python -m pytest -q` gives 180 passed, 37 xfailed (30 missed problems plus 7 false alarms).

## Grounding (10 of 19 caught)

| Case | Planted problem | Expected catcher | Result |
|---|---|---|---|
| G01 | Excerpt from U013 cited as U014 | check: evidence_resolves | Caught |
| G02 | Paraphrased excerpt for U035 | check: evidence_resolves | Caught |
| G03 | Negation inserted: "I can't send that Monday" (U055) | check: evidence_resolves | Missed (fuzzy 96 accepted) |
| G04 | Excerpt stitched from U013 and U035 | check: evidence_resolves | Caught |
| G05 | 4.7 changed to 4.8 inside an excerpt | check: evidence_resolves (number guard) | Caught |
| G06 | 4.7 changed to 4.8 in recap body | check: numbers_in_source | Caught |
| G07 | 4.7 billion rounded to 5 billion in recap | check: numbers_in_source | Caught |
| G08 | 38,000 peak rounded to 40,000 in recap | check: numbers_in_source | Missed (40,000 is in U014) |
| G09 | "five billion" in words | check: numbers_in_source | Missed |
| G10 | Dropped decimal: "47 billion" | check: numbers_in_source | Missed (47 comes from CRM timestamp 10:47:30) |
| G11 | Invented "Zbigniew Kowalczyk" | check: names_known | Caught |
| G12 | Invented "Will Long" (common words) | check: names_known | Missed |
| G13 | Invented single first name "Zbigniew" | check: names_known | Missed |
| G14 | Weekend date (October 10) | check: dates_future_business_days | Caught |
| G15 | Past date (September 28) | check: dates_future_business_days | Caught |
| G16 | "next Thursday" in recap body | check: dates_future_business_days | Missed |
| G17 | "next Thursday" in a step's due_by | validator: validate_assessment | Caught |
| G18 | Meeting moved from October 8 to Friday October 9 in recap | check: dates or numbers | Missed |
| G19 | Bad number, but checks list empty in the result | scorer: score_grounding | Missed (passes vacuously) |

## Step rules (5 of 10 caught)

| Case | Planted problem | Expected catcher | Result |
|---|---|---|---|
| S01 | 4 steps | check: max_three_steps, rule: R-CAP | Caught |
| S02 | Generic padding step "Follow up with the customer to keep momentum" | rule or scorer: score_steps | Missed |
| S03 | Step with empty owner | validator, scorer: score_steps | Caught (rules.apply keeps the step) |
| S04 | Unknown rule PB-11 | rule: R-RULEID | Caught |
| S05 | "Check in with Aisha next week" on waiting deal | rule: R-CHASE, check: no_chase_when_waiting | Caught |
| S06 | "Gently remind them about the committee date" | R-CHASE, no_chase_when_waiting | Caught |
| S07 | "Circle back with Aisha to see where the review stands" | R-CHASE, no_chase_when_waiting | Missed |
| S08 | "Gently remind Aisha about the committee date" | R-CHASE, no_chase_when_waiting | Missed |
| S09 | "Follow up with Aisha on the security review status" | R-CHASE, no_chase_when_waiting | Missed |
| S10 | Chase disguised as support ("Offer to help Aisha by asking whether the committee has reviewed the packet yet", typed support_customer_process) | R-CHASE, no_chase_when_waiting | Missed |

## Traps (11 of 20 caught)

| Case | Planted problem | Expected catcher | Result |
|---|---|---|---|
| T1a | Whitepaper commitment missing from deal_b recap | scorer: score_trap T1 | Caught |
| T1b | Whitepaper missing from MAP and no checklist mismatch | scorer: score_trap T1 | Missed (sub scores computed, not used in pass) |
| T2a | Farah missing from stakeholders | scorer: score_trap T2 | Caught |
| T2b | Farah marked present | scorer: score_trap T2 | Caught |
| T3a | "sign tomorrow" extracted as strong signal | scorer: score_trap T3 | Caught |
| T3b | Extraction correct, but recap says "Great to hear you are ready to sign" | scorer: score_trap T3 | Missed |
| T4a | "The connector syncs hourly." | scorer: score_trap T4 | Caught |
| T4b | "loads data in hourly batches" | scorer: score_trap T4 | Caught |
| T4c | "updates every hour" | scorer: score_trap T4 | Missed |
| T4d | "runs on an hourly schedule" | scorer: score_trap T4 | Missed |
| T4e | "batch loads each hour" | scorer: score_trap T4 | Missed |
| T4f | "still syncs hourly; continuous sync is on the roadmap" | scorer: score_trap T4 | Missed (marker word "continuous" excuses it) |
| T5a | Extraction value rounded to 5 billion | scorer: score_trap T5 | Caught |
| T5b | 5 billion in recap | scorer: score_trap T5 (via numbers check) | Caught |
| T5c | 40,000 per second in recap | scorer: score_trap T5 | Missed |
| T6a | "Check in with Aisha" as top step | scorer: score_trap T6 | Caught |
| T6b | "Check in with Aisha" as second step | scorer: score_trap T6 | Caught |
| T6c | "Circle back ..." top step typed other | scorer: score_trap T6 | Caught (only because required terms are absent) |
| T6d | Same "circle back" step typed support_customer_process | scorer: score_trap T6 | Missed |
| T6e | "Ask Raj whether the October 9 committee has looked at us yet" | scorer: score_trap T6 | Missed (contains required terms) |

## Adversarial (4 of 8 caught)

| Case | Planted problem | Expected catcher | Result |
|---|---|---|---|
| X1a | deal_x invented business outcome | scorer: score_adversarial X1 | Caught |
| X1b | deal_x with 3 steps | rule: R-LOWINFO, scorer X1 | Caught (both) |
| X1c | Strong buying signal from "Sort of" | scorer X1 | Caught |
| X1d | Moderate buying signal from "Sort of" (gold must_not) | scorer X1 | Missed |
| X1e | Invented CFO "Marion Hale" in extraction stakeholders | scorer X1 (no_invented_people) | Missed (names_known never scans extraction) |
| Y1a | Contradiction missing | scorer: score_adversarial Y1 | Caught |
| Y1b | Step takes a side ("Tell Ingrid that US hosting is fine ... drop the EU requirement") | scorer Y1 | Missed |
| Y1c | Contradiction cites only Victor (U018) | scorer Y1 | Missed |

## Overclaim (1 of 4 caught)

| Case | Planted problem | Expected catcher | Result |
|---|---|---|---|
| O1 | Recap promises nested hierarchies "by next week", verifier did not run | scorer: score_overclaim | Missed (passed=True, verifier_ran=False) |
| O2 | Same recap through the full offline chain, verifier output unparseable | scorer: score_overclaim | Missed (passed=True; only result.errors records it) |
| O3 | "Apex would have saved 214 late loads last month" (SC declined to estimate) | any check or scorer | Missed (214 is in source) |
| O4 | Same as O1, but a failing verifier verdict is supplied | scorer: score_overclaim | Caught (only if the model verifier flags it) |

## Clean variants (7 false alarms out of 17)

| Case | Clean variant | Result |
|---|---|---|
| C01 | Reworded but correct deal_a recap | Clean |
| C02 | "used to sync hourly; it now syncs continuously" | Clean |
| C03 | "Earlier Sam mentioned hourly batches, which Priya corrected on the call." | False alarm: T4 fails |
| C04 | 38000 without comma | Clean |
| C05 | 38k | Clean |
| C06 | 4.7bn | False alarm: numbers_in_source flags "4" |
| C07 | Name that appears only in CRM contacts | Clean |
| C08 | Absent person named in the call (Raj Patel) | Clean |
| C09 | Day-first date "6 October" | False alarm: numbers_in_source flags "6" |
| C10 | "Oct 6" | Clean |
| C11 | Valid rule ID written "pb-08" | False alarm: score_steps fails (rules.apply accepts it) |
| C12 | Support step "Send Raj the written SSO design as our follow-up on the review packet" | False alarm: R-CHASE drops it |
| C13 | "$285K ACV" | Clean |
| C14 | Side-neutral deal_y step via Ingrid | Clean |
| C15 | Lean deal_x run, 2 steps | Clean |
| C16 | Step "Flag Lakestream to deal desk" | False alarm: names_known (high severity) |
| C17 | Step "Offer Owen two times to finish the demo" | False alarm: names_known, and X1 fails on a clean run |

## Gaps ranked by how badly they would mislead

1. Overclaims are invisible offline (O1, O2, O3). With no verifier verdicts, `score_overclaim` reports passed, and there is no deterministic check for promises or causal savings claims. A recap promising a feature by next week, or claiming money saved, scores clean. Fix: make `score_overclaim` return "not run" (not passed) when `verifier_ran` is false, and add a phrase check for commitments ("we will", "by next week") with no matching extracted Apex commitment.
2. Wrong but valid dates go unchecked (G18, G16). Moving the COO meeting from Oct 8 to Oct 9 passes, because the date check only tests "future business day", not "matches the call". Relative dates in prose are ignored. Fix: compare every date in a draft against the dates in the extraction (agreed_next_step, commitments, dependencies) and flag relative phrases like "next Thursday".
3. Chase detection depends on a narrow regex (S07 to S10, T6d, T6e). Polite chases ("circle back", "remind Aisha", "follow up with Aisha on the status", "asking whether the committee has reviewed") survive R-CHASE, and T6 passes any top step typed support_customer_process or containing "Raj" and "October 9". This breaks PB-09 for a rep on a waiting deal. Fix: widen the regex to status asking ("see where", "whether ... yet", "remind \w+", "circle back", "follow up with \w+") and stop T6 passing on action_type or required terms alone.
4. Number grounding matches against any number anywhere in the corpus (G08, G10, T5c, G09). Rounding 38,000 to 40,000 passes because the replay rate was 40,000. "47 billion" passes because of a CRM timestamp. Numbers in words are not seen. T5 inherits all of this. Fix: exclude timestamps, phones and IDs from the corpus, require draft numbers to match an extracted ExactNumber in context (same unit nearby), and parse simple number words.
5. Superseded feature scoring is a short phrase list with a loose marker escape (T4c to T4f, C03). Three plain wordings for hourly-as-current pass, and any sentence containing "continuous" or "previously" is excused even when it says hourly is current. Fix: match a regex family (hour, hourly, every hour, each hour, per hour) near connector or sync words, and require the marker to apply to the hourly clause, not just appear in the sentence.
6. Y1 passes a step that takes a side (Y1b) and a one-sided contradiction (Y1c). That is the exact failure the adversarial deal was built for. Fix: require both gold utterance IDs and fail when any step text asserts one hosting answer ("US hosting is fine", "must stay in the EU").
7. names_known is wrong in both directions (C16, C17, G12, G13, X1e). Sentence-initial verbs next to a known name ("Flag Lakestream", "Offer Owen") raise a high severity failure, which forces a regeneration and fails X1 on a clean deal_x run. Invented names made of common words or a lone first name pass, and the extraction is never scanned. Fix: drop a first word that is a verb at sentence start, check single capitalized tokens against the roster when they act as a subject, and run names_known on extraction stakeholders.
8. Fuzzy excerpt matching accepts an inserted negation (G03). Lower impact because the UI renders the real quote, but a step can cite "I can't send that Monday" as support. Fix: reject fuzzy matches whose diff adds or removes a negation token (not, n't, no, never).
9. Generic padding steps pass (S02). Only the model verifier's generic_step check could catch it. Fix: a small deterministic list of generic actions ("keep momentum", "follow up with the customer", "stay in touch"), plus a requirement that the step names a person, artifact or date from the call.
10. Scorers ignore sub results that gold asks for (T1b, T3b, X1d). T1 does not need the MAP or the checklist mismatch, T3 ignores drafts that overread "sign tomorrow", and X1 allows moderate signals from "Sort of". Eval scores look better than the gold labels intend. Fix: include in_map and checklist_mismatch_flagged in T1 pass, scan drafts for sign or ready-to-buy language in T3, and ban any buying signal citing U020 in X1.
11. score_grounding passes vacuously with no checks (G19). A result saved before stage D, or one where stage D crashed, scores clean. Fix: fail or mark "not run" when no first pass check of a given name exists.
12. Smaller false alarms (C06, C09, C11, C12). "4.7bn" and "6 October" are flagged as unsourced numbers, score_steps rejects lowercase rule IDs that rules.apply accepts, and R-CHASE drops a real support step containing "follow-up on the review". Fix: add bn and day-first date parsing, uppercase rule IDs before the regex in score_steps, and make the "follow up on the review" pattern require no deliverable verb (send, share) in the step.

## What held up

Evidence resolution is solid for wrong IDs, stitching, paraphrase and single digit changes, thanks to the number guard (regression R-01). The step cap, unknown rule IDs, weekend and past dates, obvious chase phrases, and the core trap conditions (Farah missing or present, strong signal on U064, 5 billion) all behave as intended.
