# Memo for the deck-building agent: Debrief, backwards and forwards

To: the agent building the interview deck
From: the builder of the Debrief prototype
Date: 2026-10-03

Read this whole memo before writing a slide. It tells you what the tool is, how every part works, which numbers are real, which screens are samples, and the framing rules the deck must follow. When this memo and your instincts disagree, follow the memo. When something is not in this memo, do not invent it; leave a placeholder and flag it.

## 1. Ground rules for the deck (non-negotiable)

1. **Everything is synthetic.** Apex (the selling company), its customers, people, competitors, playbook and release cards are fictional. Say "synthetic data, fictional company" on any slide that shows product screens or numbers. Never use a real company, customer or employer name.
2. **It is a prototype.** Say "prototype". Do not say it is deployed, piloted or used by reps.
3. **Never present a target as a result.** Thresholds such as "70% of cards opened" are proposals to agree with sales leadership, not outcomes.
4. **Never claim causation.** Research findings are "associated with", not "drives" or "causes". Most evidence is analyst surveys and vendor data from the vendor's own customers.
5. **Label samples.** Some screens show hand-written sample captures. Each screen in section 10 says what is real. Carry that label onto the slide (a small footnote is enough).
6. **Small samples.** Recorded output is 1 run per deal on 5 synthetic deals. Present numbers as "on 5 synthetic deals, one run each", never as a percentage alone.
7. **Humans approve everything.** Nothing is sent to a customer automatically. Say this once, clearly.
8. **Writing style.** Plain sales language, no AI jargon (say "the agent pre-fills", not "LLM extraction pipeline"). Sentence case headings. No em dashes. Short sentences.

## 2. The one-line pitch

After every technical validation demo, Debrief turns the call into the next best steps, tied to researched best practice, and asks the AE for 30 seconds of judgment in Slack.

Longer version (for a speaker note): deals stall after technical validation because nobody owns the window between "the demo went well" and "the customer decided". Debrief puts a playbook inside that window, inside the tools reps already use (Slack and the CRM), and it measures whether the playbook is followed and why not.

## 3. The problem it addresses

From the interview scenario packet (treat these as given facts about fictional Apex):
- Days in technical validation (TV) rose 12, 14, 18 over Q1 to Q3 while other stages stayed flat.
- Win rate falls with days in TV (68%, 41%, 36%). This is correlational and may run in reverse: weak deals both stall and lose.
- Touches in the 14 days after a demo: top quartile AEs 2.3, middle 50% 1.1, bottom quartile 0.7. Touch counts can reflect deal quality, not just rep behavior.
- A follow-up guide exists in Confluence and AEs do not use it.
- The SC summary document is completed about 60% of the time, and nothing flows to post-sales.

From the best practice research (section 7):
- 40% to 60% of deals are lost to customers who intend to buy but never act ("no decision"), and indecision is behind 56% of those losses (Dixon and McKenna, 2.5 million calls; correlational; the authors sell training).
- Buyers spend about 17% of buying time with suppliers; most persuasion happens without the rep (Gartner).
- Buying groups are 5 to 16 people; 74% show unhealthy conflict; groups that reach consensus are 2.5 times as likely to report a high-quality deal (Gartner 2025 survey of 632 buyers; correlational).

The tension to name on a slide: the tool is both a helper and a diagnostic. It does not assume why deals stall. It is built to tell 6 candidate causes apart (section 6.7).

## 4. Who uses it

- **AE (account executive):** gets the confirm card and the debrief card in Slack, approves the recap.
- **SC (solutions consultant):** gets their own commitments and open technical items, confirms the call record, gets a note on what mattered when the deal moves.
- **Sales manager:** gets one coaching question per deal, not a scorecard.
- **CSM (customer success):** gets a handoff brief built from what was captured at TV.
- **RevOps / leadership:** gets the measurement view and the decision table.

## 5. End to end, in order

1. **The call ends.** The Gong transcript arrives. Debrief runs automatically (polling or a Gong webhook). It skips calls that are not in the TV stage and never runs the same transcript twice.
2. **The debrief is built (7 model calls).** The agent reads the transcript plus CRM context and produces a call record, a deal state, at most 3 ranked next steps, and 3 drafts (recap email, internal summary, mutual action plan). A skeptical verifier checks the drafts.
3. **The confirm card is pre-filled (1 more call).** 4 fields of AE judgment, each with a confidence and the line from the call it rests on.
4. **Slack:** the AE gets the confirm card first, then the debrief card. The SC gets their own card.
5. **The AE confirms (target under 60 seconds).** Fields the agent is sure of are already confirmed; the AE taps to correct the rest and presses Confirm all.
6. **After confirm:** the confirmed fields are written to the CRM opportunity; the AE sees the next best steps, the recap draft to approve, and a stakeholder map. With the live model connected, a correction rebuilds the steps and drafts.
7. **Over time:** business-hours nudges, SC loop closure when the deal moves, a CS handoff brief at closed won, and the measurement plan.

## 6. How each part works

### 6.1 The confirm card ("confirm, don't write")

The 4 fields:
- **Priority and why now:** the buyer's real priority and the trigger for acting now, 25 words or fewer.
- **Champion and economic buyer:** champion strong, unclear or absent (plus a name); economic buyer named yes, no or unclear (plus a name).
- **Top risk:** one of budget, timeline, competitor, security review, integration, no urgency, other (with a one-line note).
- **Next step:** the step the customer agreed to, with the date said in the call, or empty.

Confidence is computed in code, not taken from the model. The model's own probability is the starting point, then capped:
- no basis in the call: 0
- no line cited, or a cited line that does not match the transcript: at most 0.4
- inferred rather than said: at most 0.75
- the CRM disagrees on the champion or economic buyer: at most 0.6
- top risk "other": at most 0.6
- a next step date nobody said: at most 0.5, and never auto-confirmed

Routing:
- At or above 0.90: "Confirmed by agent", collapsed, with an Edit button.
- Below 0.90: "Needs your call", with one-tap menus or an edit box.
- Champion and top risk are judgment calls: always asked for each AE's first 20 demos.
- 10% of confident fields are asked anyway as a spot check. Reason: an AE rarely reopens a collapsed field, so without spot checks the error rate among auto-confirmed fields would look better than it is.

Every confirm is stored as labeled examples (agent value, confidence, AE value, corrected or not). The dashboard shows per-field accuracy, calibration by confidence bucket (does 90% mean 90%?), auto-confirm rate, questions per meeting (target: trending from 4 toward 1 or 2), median seconds to confirm, and a threshold simulator.

The confirm card replaced an earlier design: a 4-line checklist the AE filled during the call. That was unrealistic (reps are presenting, not typing).

### 6.2 Next best steps

- At most 3, ranked. Fewer is normal; padding is never allowed.
- Each step names an owner, a due date, the playbook rule it follows, and a quote from the call. Quotes are rendered by code from the transcript; the model never writes quote text that reaches the screen.
- Deal state is one of: ready to advance, open technical gap, missing stakeholder, competitive risk, waiting on customer, low information.
- Deterministic rules run after the model and every change is logged: a step citing a rule that does not exist is dropped; evidence that does not match the transcript is removed; a call with little customer talk is marked low information with at most 2 steps; a deal is set to waiting on customer only when a customer-owned blocker has no date and Apex owes nothing; chasing steps are dropped on waiting deals; never more than 3 steps.

### 6.3 Drafts

- **Recap email:** only what was said, every Apex commitment with its date, no quotation marks (exact quotes are shown separately from the transcript), never promises anything not committed, never repeats a feature the call corrected. Best practice version: under 120 words, written so the champion can forward it unedited.
- **Internal summary:** replaces the SC summary doc.
- **Mutual action plan:** a row can be "agreed" only with a line from the call behind it; otherwise it is "proposed".

### 6.4 Guardrails (why the output can be trusted)

- Deterministic checks on every draft: evidence resolves, numbers appear in the sources, names are real, dates were said in the call, no savings or ROI claims, quoted text exists in the transcript.
- A skeptical verifier (a second model call told to assume mistakes) checks for overstated commitments, overstated buying signals, uncommitted promises, superseded features and generic steps.
- A high-severity finding triggers one rewrite. If it still fails, the draft is marked "needs review" and cannot be approved in one tap.
- An uncommitted promise in the customer recap always blocks approval, whatever severity the verifier gives it.
- Refusals are logged and surfaced, never silently retried.

### 6.5 The stakeholder map

Computed by code from the call record and the confirmed champion. Stance is "supportive" only for the confirmed champion and "concerned" only for someone with an open concern from the call; everyone else is "unknown". Stance is never guessed from tone. An absent economic buyer gets "brief through the champion before any commercials"; other absent decision makers get "a 1 page brief through the champion"; someone mentioned only in passing gets no action.

### 6.6 MEDDPICC, nudges, loop closure, handoff

- **MEDDPICC** is computed in code from the call record (no model call); unknown fields read "Unknown after TV demo". Known weakness: some rules are generous (a booked meeting marks decision process as known).
- **Nudges:** no customer touch 24 hours after the demo, a gentle reminder; 48 hours, a stronger reminder plus a coaching prompt for the manager; an SC commitment past due, a reminder to the SC. Only on business days, 08:00 to 18:00 local, at most 1 per deal per day. When the deal is waiting on the customer, no-touch nudges are replaced by one prompt about what the customer's process needs. Never "check in".
- **Loop closure:** when the AE marks a deal advanced or stalled, the SC gets a note on which objections and answers mattered.
- **CS handoff:** at closed won, the CSM gets champion, stated outcome, objections and answers, open items, commitments, MEDDPICC gaps and a suggested first 30 days.
- **Manager view:** one coaching question per deal by deal state (for example, waiting on customer: "Ask what the customer's process needs from us, not when they will decide").

### 6.7 The diagnostic: why steps are not taken

Every step has one-tap dismiss reasons: already done, waiting on customer, not relevant, no time. With ignored cards and unopened cards, these map to 6 candidate causes of post-demo inaction:
- (a) the AE does not know the next step
- (b) the AE is waiting on the customer
- (c) the AE has no capacity
- (d) nobody inspects the post-demo window
- (e) weak commercial judgment after TV
- (f) the deal is weak; nothing to do

Pre-declared rule: a cause counts as real only if it explains at least 30% of non-actions with at least 20 events.

### 6.8 Measurement plan

- 30 days, adoption: debriefs per eligible demo, card opened within 24 hours, recap sent within 24 hours, SC record confirmed within 1 business day (against today's 60%), drafts sent with little editing, steps acted on vs dismissed vs ignored, confirm time and questions per meeting.
- 30 days, leading impact: customer-confirmed dated next step within 2 business days; reply rate to the recap within 5 business days.
- 90 days: days in TV per arm, from a staggered rollout by pod (treated vs not-yet-treated pods in the same weeks, matched on segment, deal size band and AE tenure). Win rate is a 2 to 3 quarter outcome and is reported as correlational.
- A decision table gives "scale if / fix if / stop if" thresholds for each metric. All thresholds are proposals.
- Pitfalls named up front: early adopters are the best reps, touch counts can be gamed, novelty fades, quarter-end seasonality, contamination through shared Slack channels.

### 6.9 Where it lives (integrations)

- **Slack:** interactive cards (menus, edit modals, buttons) through a signed interactions endpoint. Built and tested against a fake Slack API; not yet connected to a real workspace. Without interactivity configured, posted cards fall back to a link to the same card on the web.
- **CRM:** confirmed fields are written to the opportunity: NextStep (standard) plus custom fields Why_Now__c, Champion_Status__c, Champion__c, Economic_Buyer_Identified__c, Economic_Buyer__c, Top_Risk__c, Top_Risk_Note__c, Next_Step_Date__c. In the prototype this writes to a file; the production path is Salesforce Hosted MCP or the REST API.
- **Gong:** transcripts via the Gong REST API (the Gong MCP server is read-only and does not return raw transcripts). File-backed in the prototype.
- **Web:** the same confirm card on the web for anyone not in Slack, and the dashboard.

## 7. The best practice research behind the steps

A deep research pass (stored verbatim in `docs/research/best_practice_findings.md`) graded every claim by evidence type and strength. Core finding: the strongest next steps after a TV demo help the customer's buying group decide without the rep in the room. In order:
1. remove the specific blocker to the customer's next internal decision;
2. give the champion forwardable material for each absent decision maker;
3. turn open items into dated, owned commitments the customer can see.
Strength: moderate; an inference from surveys and vendor data, not from controlled trials.

What the research changed:
- **Playbook v2: 16 rules.** PB-01 to PB-10 amended, PB-11 to PB-16 added:
  - PB-11: a deferral gets one useful asset and a check-in date the customer can change, not a chase.
  - PB-12: a draft mutual action plan once the economic buyer is known.
  - PB-13: confirm the technical win in writing against the agreed success criteria.
  - PB-14: indecision gets a clear recommendation, fewer options and a risk reducer.
  - PB-15: internal disagreement gets the same neutral facts on both sides.
  - PB-16: a low-information call is re-qualified before more SC time.
  Plus an explicit list of routine steps that never count on their own (send the recap, send the invite, update CRM, raise an internal flag).
- **The grading rubric, R1 to R8:** grounded in this call; targets the binding constraint; buyer-enabling (forwardable); owned and dated; honest and bounded (no roadmap dates, no guessed timelines); respects the customer's process; adds beyond routine hygiene; feasible within 10 business days. Acceptable when R1, R2, R4, R5 and R6 pass; strong when R3 and R7 also pass.
- The research rejected two of the old grader's criteria: "doable in 10 minutes" penalizes the highest-value steps, and "a typical AE would not do it unprompted" cannot be observed.
- **Reference answers:** for each of the 5 scenarios, the research's must-have, optional, routine and wrong steps. These score the tool directly.

Key evidence (with honest strength), for a sources slide:
- Sense-making reps: 80% of customers completed high-quality, low-regret purchases, against 50% (telling) and 30% (giving). Gartner, more than 1,000 B2B customers, 2019; HBR 2022. Correlational, moderate.
- Following up within 24 hours associated with a 14% higher win rate (Gong, 103,600 deals). Vendor data, weak to moderate. The popular "within 2 hours" claim has no primary source.
- Mutual action plans "26% higher win rate" (Outreach): vendor data with strong selection bias; the same vendor also says 13%. Weak.
- Won deals have about twice as many buyer contacts (Gong). Vendor data; reverse causality likely.

## 8. The numbers (all synthetic, one run per deal)

Recorded output (run 2, 2026-10-03, before the best practice rebuild):

| Measure | Result | How to say it |
|---|---|---|
| Commitments captured, including ones said in passing | 22 of 23 | The strongest number. SC promises said in passing rarely reach the CRM today. |
| Deal state matches the hand label | 4 of 5 | Up from 3 of 5 in run 1 after fixing a rule. |
| Open technical items found | 8 of 10 | Up from 6 of 10 in run 1. |
| Must-have best practice steps covered | 10 of 15 | Keyword match against the research's reference answers, so a floor. Before the rebuild. |
| Steps matching a known wrong move | 0 | No chasing, no guessed timelines, no taking sides. |
| Grounding problems reaching a draft a rep could approve in one tap | 0 | Bad numbers or dates were rewritten or blocked for review. |
| Planted errors caught, with vs without the verifier | 20 vs 14 of 20 | The verifier earns its cost. 0 false alarms on 5 clean drafts. |
| Cost per debrief | $0.41 mean ($0.20 to $0.55) | Sonnet 5.5 rates; 7 to 10 model calls per debrief. |
| Model time per debrief | 105 seconds summed (56 to 135) | Wall clock was not measured. |

The old grader (run 1 to run 2) passed 1 of 13 then 4 of 11 steps. Do not lead with this: the research showed that grader used the wrong criteria. If asked, say so plainly: "the first grader penalized substantial steps, so we rebuilt it from research".

Regressions to be ready for: deal B's recap was blocked by a likely false alarm (the stricter promise gate); commitment recall dipped from 23 of 23 to 22 of 23; one trap check on deal B regressed.

Not measured yet (say "next"):
- the best practice version (playbook v2, steps v3, recap v3, grader v2). It is built and tested but not recorded. The recording attempt on 2026-10-03 was rejected on the first call because the API account's credit balance was too low; nothing was spent and nothing changed.
- capture accuracy on the 12 deals (the seed script and ground truth are ready).
- the grader checked against the research's reference answers.

## 9. What is real, what is mocked, what is a sample

- **Real:** the code for every step; recorded model output for 5 deals (run 2); every check, rule and score; 337 automated tests.
- **Mocked:** Gong, Salesforce and Slack are file-backed or faked. The calendar invite is a stub. "Mark as sent" is a button, not an email integration.
- **Samples:** 2 hand-written confirm-card captures (Halvorsen Freight and Meridian Health), labeled as samples and scored by the real code.
- **Simulated:** the dashboard's "simulated AE responses" view (empty until capture output is recorded).
- **Synthetic data:** 12 transcripts. The 5 debrief deals contain planted traps; 7 shorter ones (3 per bucket with the originals) cover clear next step, non-committal, hidden blocker and ambiguous calls. Ground truth was written by the builder and needs an independent review.

The 12 deals (fictional):
- Halvorsen Freight (logistics, $285K): clear champion, COO meeting booked.
- Meridian Health Partners (healthcare, $420K): SSO gap, security committee gates everything.
- Corvid Retail Group (retail, $310K): incumbent competitor, migration fear, customer deferred.
- Pinecrest Insurance (insurance, $140K): low information.
- Atlas Biologics (life sciences, $230K): IT and compliance disagree on hosting.
- Brightwater Utilities, Larkspur Hotels: clear next step.
- Ferro Manufacturing: polite but non-committal.
- Quill Media (security review), Marlow Retail Bank (spending freeze): hidden blocker.
- Saltmarsh Foods, Thornbury Council: ambiguous or conflicting.

## 10. Screens available (in `docs/screenshots/`)

Each line: file, what it shows, what is real. Put the "what is real" label on the slide.
- `10_slack_confirm_card_halvorsen.png`: the Slack confirm card; 2 fields confirmed by the agent, 2 need the AE. Sample capture, real scoring code, Slack preview of the posted message.
- `11_slack_confirm_card_meridian.png`: a murky call where all 4 need the AE, including "not found in the call" for the next step. Sample capture, real code.
- `12_phone_confirm_card_meridian_one_edit.png`: the web card on a phone with one tap correction. Sample capture.
- `13_phone_confirm_card_halvorsen.png`: the web card on a phone before confirming. Sample capture.
- `14_slack_confirmed_card_halvorsen.png`: the Slack card after Confirm all, with the next best step. Sample capture plus recorded step.
- `15_slack_debrief_card_halvorsen.png`: the Slack debrief card with deal state, ranked steps, quotes and act or dismiss buttons. Recorded model output (run 2).
- `16_capture_dashboard.png`: the capture dashboard. Holds only 2 confirms made while taking screenshots; label it "illustrative".
- `17_after_confirm_next_best_steps.png`: next best steps with owner, date, rule and quote. Recorded model output (run 2), before the best practice rebuild.
- `18_after_confirm_recap_draft.png`: the recap draft with Approve and copy. Recorded model output (run 2).
- `19_after_confirm_stakeholder_map.png`: the stakeholder map. Computed by code from the recorded call record.
- `20_after_confirm_written_to_crm.png`: the CRM fields written on confirm. Confirmed sample values, file-backed CRM.
- `01` to `07`: the earlier Streamlit screens from run 1 (AE, SC, manager and measurement views). Use only for the manager and measurement story; the AE flow is better told with 10 to 20.

A web page with these screens and slide-ready copy: https://claude.ai/artifact/B4cqwow93w4AYx3gg4LWVY (private to its owner).

## 11. Suggested deck outline (about 12 slides)

1. **Title:** Debrief: the next best step after a technical demo, confirmed in 30 seconds. Prototype, synthetic data.
2. **The problem:** days in TV 12, 14, 18; deals lost to indecision, not competitors (40% to 60% no decision); buyers decide mostly without the rep.
3. **The diagnosis, not an assumption:** 6 candidate causes, and how the tool tells them apart.
4. **What Debrief does:** the 4 moments (call ends, AE confirms, next steps arrive, loop closes).
5. **Confirm, don't write:** screen 10, plus how confidence is earned (computed, capped, spot-checked).
6. **When the call is murky:** screen 11 or 12.
7. **Next best steps tied to best practice:** screen 17, plus the playbook and rubric in one line each.
8. **Drafts a rep can trust:** screen 18 and the guardrails (quotes from the transcript, verifier, approval blocked on an uncommitted promise).
9. **Who to reach:** screen 19.
10. **Fits the tools reps already use:** screens 15 and 20 (Slack and CRM).
11. **Evidence so far:** the run 2 table (section 8), honestly framed.
12. **How we would know it works:** measurement plan, staggered pod rollout, decision table, pitfalls.
13. **What is next:** record the best practice version, check the grader against the reference answers, pilot by pod.

## 12. Questions a skeptical panel will ask, with short answers

- **Why not just use Gong or Agentforce summaries?** Summaries and follow-up emails are commodity, and Debrief treats them that way. It adds steps tied to a researched playbook, commitment capture and loop closure, a 30 second judgment capture that writes the CRM, and a diagnostic for why deals stall.
- **How do you know the steps are right?** Today, against the research's reference answers (10 of 15 must-haves before the rebuild, 0 wrong moves). In a pilot, by which step types, taken within 5 business days, are associated with the deal reaching the next stage within 30 days.
- **Isn't the model's confidence made up?** Yes, so it is not used alone. It is capped by checks the code can verify, and spot checks plus the calibration table show whether 90% means 90%.
- **You wrote the test and the answer key.** True for the synthetic labels, which is why the reference answers come from independent research and why the ground truth is flagged for independent review. Real calibration comes from AE corrections and deal outcomes.
- **What if AEs ignore it?** The events show it (cards not opened in 24 hours, confirm time, dismiss reasons), and each has a pre-agreed decision rule.
- **Does anything reach a customer automatically?** No. Every customer-facing draft needs approval, and approval is blocked when the verifier finds an uncommitted promise or a date nobody said.
- **What does it cost?** About $0.41 per debrief on the recorded runs.
- **What breaks first?** Checks flagging good drafts (watch drafts approved unedited after a flag); steps feeling generic (watch "not relevant" dismissals); cards not opened (watch 24 hour opens); nudges becoming noise (nudges without action).

## 13. Glossary

- **TV (technical validation):** the sales stage where the customer tests the product on their own data.
- **AE / SC / CSM:** account executive / solutions consultant / customer success manager.
- **Economic buyer (EB):** the person who signs or owns the budget.
- **Champion:** the customer person actively moving the deal internally.
- **MAP (mutual action plan):** a shared plan of milestones, owners and dates on both sides.
- **MEDDPICC:** a qualification checklist (metrics, economic buyer, decision criteria, decision process, paper process, identify pain, champion, competition).
- **Playbook rule (PB-01 to PB-16):** the rule a next step follows.
- **Release card (RC-xx):** a short note on current product behavior, used so steps never repeat a superseded feature.
- **Verifier:** a second model call that checks the drafts and assumes mistakes.
- **Replay mode:** the prototype replays recorded model output so demos and tests never call the API.

## 14. Where to look in the repo

- `README.md`: overview, how to run, measurement, production path, known limits.
- `DECISIONS.md`: every place the AI output was wrong and what changed (D-01 to D-17).
- `docs/research/best_practice_findings.md`: the research.
- `data/playbook_v2.md`: the 16 rules.
- `evals/results.md`, `evals/reference_results.md`, `evals/ablation.md`: the numbers.
- `docs/screenshots/`: the screens.
