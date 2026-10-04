# Panel objections

Prep for the Braze Applied AI Architect, go-to-market (GTM), live panel. Every claim carries a label: [repo] file or commit, [eval] results file, [external] finding ID, [inference], [hypothesis]. [CONFIRM] means verify before saying it out loud.

Terms used below: TV is technical validation, the stage where the customer tests the product on their own data. AE is account executive. SC is solutions consultant. CRM is customer relationship management. MAP is mutual action plan.

Eval numbers come from the live run on 2026-10-04: `eval/results.md` (scored by code) and `eval/hand_review.md` (post hoc, 1 reviewer).

---

## 1. Why the post-technical-validation window

**Why they ask.** They want to know if you picked the problem from evidence or from what was easy to build.

**30 second answer.**
The TV window is where the buyer has seen the product work, and the deal still stalls. In the scenario packet I built against, days in TV rose 12, 14, 18 over 3 quarters while other stages stayed flat [repo] `README.md` "Diagnosis".

It is also the moment with the richest raw material: a recorded call full of concerns, promises and names, and no playbook inside the workflow [repo] `README.md` intro.

**90 second backup.**
Outside research points the same way. Dixon and McKenna report no-decision outcomes at 40 to 60% of qualified B2B deals [external] F2, secondary source, [CONFIRM] trace to the HBR original. A Lightspeed survey of 154 startups found 53% of lost deals ended in no action and 39% went silent, against 27% lost to competition [external] F3, [CONFIRM] original survey.

So the biggest loss is indecision after the buyer has seen the product, and the TV call is the last moment everyone was in the room.

I also built Debrief to test my own diagnosis. It logs why reps dismiss each step and maps those reasons to 6 candidate causes, with a pre-declared rule: a cause counts only if it explains 30% of non-actions across at least 20 events [repo] `README.md` "Diagnosis", `src/metrics.py`.

**Evidence.** [repo] `README.md` "Diagnosis"; [external] F2, F3, F4.

**Most likely overclaim.** Saying the days-in-TV trend comes from real company data. It comes from a synthetic scenario packet [repo] `README.md`. Also, win rate falling with days in TV is correlation; weak deals may stall and lose for the same reason [repo] `README.md` "Diagnosis".

**Follow-ups.**
- *How do you know the stall is in the seller's control?* Winsight's vendor study of 120,000+ deals says 71% of stalled deals were [external] F4, a vendor study, so I treat it as directional. Debrief's dismiss reasons are built to measure this per team instead of assuming it.
- *Why not discovery, where deals are won or lost earlier?* Discovery has more tools and coaching already [hypothesis]. TV is where a concrete, recorded technical evaluation exists, which makes grounded output possible.

---

## 2. Is the problem real

**Why they ask.** A prototype on synthetic data invites the question of whether anyone has this pain.

**30 second answer.**
The external numbers say indecision is the biggest single outcome in B2B deals [external] F2, F3. Braze's own posting asks for stakeholder research on handoff failures [external] F1, [CONFIRM] exact wording.

What I have not done is validate it with Braze sellers. That is the first thing I would do.

**90 second backup.**
I want to be precise about what I know. The pain pattern is backed by third-party research, some of it secondary [external] F2, F3, F4.

My prototype runs on 12 synthetic deals plus 15 eval transcripts I wrote [repo] `data/transcripts/`, `eval/data/transcripts/`. So it shows the approach works on realistic material, and says nothing about frequency at Braze.

The product is built to answer "is it real" with data in the first 30 days: card open rate, step act versus dismiss, and the reason behind each dismiss [repo] `README.md` "Measurement".

**Evidence.** [external] F1 to F4; [repo] `README.md` "Measurement", "Known limits".

**Most likely overclaim.** Implying users asked for this. No user research was done [inference] from the repo, which contains none.

**Follow-ups.**
- *Who would you interview first?* 5 AEs and 5 SCs from the Enterprise segment, plus 2 CS managers on the handoff side [hypothesis].
- *What result would make you drop it?* If dismiss reasons show "already done" or "not relevant" dominate after 30 days, the window is handled and I would move upstream [repo] `README.md` decision table.

---

## 3. Why not Gong

**Why they ask.** Gong already sells call summaries, follow-ups and deal risk agents.

**30 second answer.**
Gong now offers custom agents for follow-ups and deal risk, including a Deal Rescue Agent, with approval gates [external] F7, [CONFIRM] feature names and date. I treat summaries and follow-up emails as commodity, and Debrief includes them only for completeness [repo] `README.md` "What is different here".

The parts I care about are TV-stage playbook rules, SC commitment tracking, and the dismiss-reason diagnostic [repo] `README.md`.

**90 second backup.**
In production I would build on Gong as the source. The production path pulls transcripts from the Gong REST API because the Gong MCP server is read-only and returns no raw transcripts [repo] `README.md` "Production path", [CONFIRM] still true.

What Debrief adds sits on top: every quote is rendered by code from the transcript, every step cites a playbook rule, and approval is blocked when the recap promises something nobody committed to [repo] `src/transcript.py` `render_quote`, `src/chain.py` `_always_blocking`.

If Gong's custom agents can carry those rules, I would rather configure Gong than run a second system [inference].

**Evidence.** [external] F7; [repo] `README.md` "What is different here", "Production path".

**Most likely overclaim.** Saying Gong cannot do something. I have not tested Gong's agents [inference]. Say "I would test whether Gong can carry these rules."

**Follow-ups.**
- *So is Debrief a Gong competitor?* No. It is a layer of rules and checks on top of the call recorder and the CRM.
- *What would you test in Gong first?* Whether a custom agent can be forced to cite a transcript line per claim and to block an uncommitted promise [hypothesis].

---

## 4. Accuracy

**Why they ask.** Hallucinated promises in a customer email are the fastest way to lose rep trust.

**30 second answer.**
Accuracy is enforced in code at 3 layers. Quotes are never model text; code renders them from the transcript. Every cited line must exist and match. Then deterministic checks and a skeptical verifier run before anything can be approved [repo] `src/transcript.py`, `src/checks.py`, `prompts/verify/v1.md`.

On 15 new hard-case transcripts, a blind judge marked 93% of claims supported for both Debrief and a plain Claude call [eval] `eval/results.md`. The difference is what a rep can send: Debrief blocked all 4 recaps that promised something nobody said, and the plain call's emails held 9 such promises with nothing to stop them [eval] `eval/hand_review.md`.

**90 second backup.**
On the repo's own 5 deals, the verifier caught 20 of 20 planted errors and the deterministic checks alone caught 14 of 20, with 0 false alarms on 5 clean drafts [eval] `evals/ablation.md`. Commitment recall was 22 of 23 [eval] `evals/results.md`.

Those 5 deals were also the development set, so I built a fresh eval: 15 transcripts with ambiguous commitments, contradictions, missing stakeholders, a long rambling call and late objections, with gold labels written before any run [repo] `eval/gold_src.py`.

The headline is a tie on factual support, 414 of 443 claims versus 529 of 567, both 93% [eval] `eval/results.md`. Risk recall was 29 of 29 for both, and uncertain items were flagged 23 of 23 versus 22 of 23. Those keyword metrics saturated, so they don't separate the systems.

On commitments, the raw judge count went against Debrief, 23 flags versus 17 [eval] `eval/results.md`. Reading every flag by hand, 16 of Debrief's 23 were recommended steps with a due date, which the judge read as promises; 6 were real. For the plain call, 16 of 17 were real, and 9 of those sat in the customer email [eval] `eval/hand_review.md`.

Where Debrief earns its keep is checkability: all 949 of its citations resolve to a transcript line, so every cited claim can be checked against the exact words. Draft sentences carry no per-sentence citation, so this covers the structured record and the steps [eval] `eval/results.md`. It costs about 8 times more, $0.32 versus $0.04 per call, and takes about 109 seconds versus 26.

I also found 2 failures. A word-count rule labeled 6 of 15 calls "low information" when only 1 was, and 6 of 14 blocked drafts were false alarms from my number and name checks [eval] `eval/hand_review.md`.

Hallucination benchmarks disagree and measure different things [external] F10, so I measure the failure that matters here: a promise or fact that reaches the customer and was never said.

**Evidence.** [eval] `evals/ablation.md`, `evals/results.md`, `eval/results.md`; [repo] `src/transcript.py` `resolve_evidence`.

**Most likely overclaim.** Saying Debrief is more accurate than a plain call. On supported claims it tied [eval] `eval/results.md`. The "6 versus 16 real overstatements" split is my own post hoc reading, not a scored metric [eval] `eval/hand_review.md`. Also never quote 20 of 20 as an accuracy rate; it is 4 planted error types on 5 drafts, 1 run each [eval] `evals/ablation.md`.

**Follow-ups.**
- *What is the false alarm cost?* deal_b's recap was blocked by a likely false alarm in run 2 [eval] `evals/results.md`, DECISIONS D-15. I would track flagged drafts a rep then sends unedited as the false alarm rate.
- *Why trust a model to judge a model?* I would not without hand labels. The repo keeps the judge labeled uncalibrated until a hand-labeled test split exists [repo] `evals/judges.py`.

---

## 5. Adoption by sellers

**Why they ask.** Sales tools die from non-use.

**30 second answer.**
I designed for under 60 seconds of AE effort. The agent pre-fills 4 fields from the call, and the AE confirms or corrects them on a Slack card [repo] `README.md` "Post-demo capture".

I replaced an in-call checklist because reps are presenting during the call, not typing [repo] DECISIONS D-16, commit `4a80342`.

**90 second backup.**
Confidence decides how much the rep sees. Fields at or above 0.90 collapse; below that, the rep gets one-tap menus [repo] `src/config.py`, `src/capture.py`.

That confidence is computed in code. The model's own number is capped when nothing in the call supports the value, when the CRM disagrees, or when a date was never said [repo] `src/capture.py` `score`.

Adoption is measured from day 1: card opened within 24 hours, steps acted on or dismissed, edit ratio on drafts [repo] `README.md` "Measurement". The first thing I expect to break is reps ignoring the card, and the signal is `card_ignored_24h` [repo] `README.md` "What breaks first".

**Evidence.** [repo] DECISIONS D-16, `src/capture.py`, `README.md` "Measurement".

**Most likely overclaim.** Saying it takes 30 seconds. That is a design target. No rep has used it, and the Slack app was tested against a fake API only [repo] `README.md` "Production path".

**Follow-ups.**
- *What if the top reps don't need it?* Expected. The cohort data in the packet shows middle and bottom reps touch deals 1.1 and 0.7 times in 14 days versus 2.3 [repo] `README.md`. They are the target.
- *How do you avoid notification fatigue?* Nudges run on a business-hours clock and `nudge_sent` without `nudge_acted_on` is tracked as a failure signal [repo] `src/nudges.py`, `README.md`.

---

## 6. Success metrics

**Why they ask.** They want leading indicators, honest causality, and a stop rule.

**30 second answer.**
At 30 days, the headline is a customer-confirmed dated next step within 2 business days, plus recap reply rate within 5 business days [repo] `README.md` "Measurement".

At 90 days, days in TV per arm from a staggered rollout by pod, so treated and not-yet-treated teams are compared in the same weeks [repo] `README.md`.

**90 second backup.**
Days in TV is computed as a Kaplan-Meier median with open deals censored, so deals still running don't bias it [repo] `src/metrics.py`, DECISIONS D-03.

Win rate is reported but labeled correlational and underpowered at 90 days, since it is a 2 to 3 quarter outcome [repo] `README.md`.

Every threshold in the decision table is marked as a proposal to agree with sales leadership, with scale, fix and stop rules [repo] `README.md`. The pitfalls I plan around: early adopters are the best reps, touch counts can be gamed, and novelty fades [repo] `README.md` "Pitfalls".

**Evidence.** [repo] `README.md` "Measurement", `src/metrics.py`.

**Most likely overclaim.** Implying any of these metrics has moved. None has; there are no users [repo] `README.md` "No metric target is ever shown as a result".

**Follow-ups.**
- *What would make you stop?* Steps dismissed as not relevant above the agreed rate, or cards ignored at 24 hours trending up [repo] `README.md` decision table.
- *How do you handle contamination?* Treated and untreated pods sharing Slack channels is a named pitfall; rollout is by pod to limit it [repo] `README.md`.

---

## 7. Security and customer data

**Why they ask.** Transcripts contain customer names, systems and commercial terms.

**30 second answer.**
Nothing is sent to a customer automatically; the notifier refuses any recipient outside internal roles [repo] `src/adapters.py` `FileNotifier`. Consent and retention inherit from the call recorder [repo] `README.md` "Production path".

The prototype uses only synthetic data, and I used no employer or client data [repo] `README.md`.

**90 second backup.**
Logged prompts and outputs redact person names, emails and phone numbers when presidio is installed. Nothing sent to the model is redacted, because the model needs names to ground claims [repo] `src/llm.py` `_redactor`.

Presidio failed to install in the build environment, so log redaction is currently a no-op [repo] DECISIONS D-04. In production I would pin it in the container image and test it.

Refusals are logged and surfaced, never silently retried on another model [repo] DECISIONS D-02. For Braze, data residency and where the model runs would be questions for security before a pilot [inference].

**Evidence.** [repo] `src/adapters.py`, `src/llm.py`, DECISIONS D-02, D-04, `README.md` "Production path".

**Most likely overclaim.** Saying logs are redacted. They are redacted only if presidio is installed, and it is not [repo] DECISIONS D-04.

**Follow-ups.**
- *Would you send transcripts to a third-party model?* Only under the company's approved model contract and retention terms [inference]; that is a security review decision.
- *What about customer data inside transcripts?* Retention follows the recorder's window or shorter; structured records stay with the opportunity [repo] `README.md`.

---

## 8. Consultant versus builder (role asks for 6+ years in GTM)

**Why they ask.** The posting asks for 6+ years of GTM experience plus shipping product [external] F1, [CONFIRM] exact wording.

**30 second answer.**
[CONFIRM] your years and roles in GTM. On the building side, Debrief is something I shipped end to end: 34 commits, a 4-stage chain, 337 passing tests, and 2 recorded runs on live model output [repo] git log, `python -m pytest -q`, `README.md` "Current status".

**90 second backup.**
The decisions log shows how I build. When an offline-tested schema failed on the first live call with "compiled grammar is too large", I split extraction into 2 calls and added a regression test [repo] commit `25aceaa`.

When the first recorded run showed weak steps and a forced deal state, I logged it, changed the prompt and a rule, and recorded run 2 with before and after numbers, including the regressions [repo] commit `d9327d1`, DECISIONS D-15.

When research showed my own "doable in 10 minutes" rule penalized the best steps, I reversed it behind a switch instead of overwriting the recorded baseline [repo] commit `0302e54`, DECISIONS D-17.

**Evidence.** [repo] git log, DECISIONS.md; [external] F1.

**Most likely overclaim.** Saying you wrote every line by hand. The repo was built with an AI coding assistant, and DECISIONS.md is framed as "where the AI output was wrong" [repo] DECISIONS.md intro. Own that directly: you set the design, reviewed every step and corrected the AI.

**Follow-ups.**
- *What did the AI get wrong that you caught?* A fuzzy quote match let "5 billion" pass for "4.7 billion"; numbers now must match exactly [repo] DECISIONS D-06.
- *How much was you versus the tool?* [CONFIRM] your own split. The decisions, reversals and eval design are documented per entry in DECISIONS.md.

---

## 9. Why not build on Braze's own agent products

**Why they ask.** Braze has an Agent Console and an MCP server [external] F9, [CONFIRM], secondary summary.

**30 second answer.**
I would. Debrief has no agent framework by design; it is 4 fixed stages in plain Python, and its parts are adapters [repo] DECISIONS "Things I chose not to build", `src/adapters.py`.

That makes the rules and checks portable to whatever runtime Braze already supports internally [inference].

**90 second backup.**
I have not used Braze Agent Console or the Braze MCP server [CONFIRM]. From the public summary, they are built for marketing and customer engagement workflows [external] F9.

The question I would ask the Braze team is whether those products are meant for internal GTM workflows too. If yes, the Debrief pieces that matter, evidence resolution, deterministic checks and approval gates, move over as code [inference].

**Evidence.** [external] F9; [repo] `src/adapters.py`, DECISIONS "Things I chose not to build".

**Most likely overclaim.** Describing what Braze's agent products do in detail. You have only a secondary summary [external] F9.

**Follow-ups.**
- *What would block porting?* Whether the runtime lets you enforce structured output with a schema and block approval on a failed check [hypothesis].
- *Would you use MCP for the CRM?* The production path already names Salesforce Hosted MCP for the CRM [repo] `README.md` "Production path".

---

## 10. Agent versus workflow

**Why they ask.** They want to see you choose autonomy where it earns its cost.

**30 second answer.**
Debrief is a workflow on purpose. The control flow is known in advance, so an agent framework would add risk without adding capability [repo] DECISIONS "Things I chose not to build".

The model does judgment inside fixed steps: extract, assess, draft, verify [repo] `src/chain.py`.

**90 second backup.**
Each step has a schema, an effort level and at most 1 retry, and only on a truncated output or a failed check [repo] `src/llm.py`, `src/config.py`. Rules in code override the model when it breaks a policy, and every override is logged [repo] `src/rules.py`.

That makes behavior testable: 337 tests run with no network, using a replay cache keyed on the exact request [repo] `src/llm.py` `replay_key`.

Where I would add agency: chasing a missing answer across systems, like checking whether a promised whitepaper went out. Even then, a human approves anything that reaches the customer [inference].

**Evidence.** [repo] `src/chain.py`, `src/rules.py`, `src/llm.py`.

**Most likely overclaim.** Calling Debrief an agent in the interview. Its own docs say no agent framework [repo] `CLAUDE.md`.

**Follow-ups.**
- *When does a workflow become an agent?* When the next step depends on what the last tool returned and can't be listed in advance [inference].
- *Cost per run?* Mean $0.409 per debrief in run 2, range $0.199 to $0.550 [repo] `README.md` "Cost and latency".

---

## 11. First 90 days

**Why they ask.** They want a plan that starts with users and ends with something shipped.

**30 second answer.**
Days 1 to 30: listen. Shadow AEs and SCs, review 20 recent post-TV deals, and map where handoffs fail, which the posting asks for [external] F1, [CONFIRM].

Days 31 to 60: ship 1 narrow workflow to 1 pod with measurement on. Days 61 to 90: read the data against pre-declared rules, then scale, fix or stop [hypothesis].

**90 second backup.**
The narrow workflow would likely be SC commitment capture and loop closure: promises said in passing, tracked with a due date and closed back to the SC [repo] `README.md` "What is different here". It is small and easy to verify.

Measurement would follow the repo's plan: adoption at 30 days, a dated next step within 2 business days as the leading metric, and a staggered rollout for anything causal [repo] `README.md` "Measurement".

I would also run the eval on 20 real, consented transcripts with labels from the sellers themselves [hypothesis], since my current gold labels are my own [repo] `README.md` "Known limits".

**Evidence.** [external] F1; [repo] `README.md`.

**Most likely overclaim.** Promising specific results by day 90. Win rate is a 2 to 3 quarter outcome [repo] `README.md`.

**Follow-ups.**
- *What if sellers say they don't need it?* Then the interviews did their job, and I pick the handoff failure they do name.
- *Who are your partners?* Sales ops for CRM fields, security for data, enablement for the playbook [inference].

---

## 12. Why leave a Director role

**Why they ask.** Fit and motivation, and whether you will be happy as an individual builder.

**30 second answer.**
[CONFIRM] your own reason. A grounded version: "I want to be closer to building. Debrief showed me how much I enjoy shipping working systems and measuring them honestly."

**90 second backup.**
[CONFIRM] Keep it about the work, with no employer details. The posting combines GTM practitioners as users with shipping product [external] F1, which matches what I built in Debrief [repo].

**Evidence.** [external] F1; [repo] the project itself.

**Most likely overclaim.** Overstating scope or team size from the current role. Say only what you can stand behind.

**Follow-ups.**
- *Will you miss managing people?* [CONFIRM] your answer.
- *What would you want to own?* [CONFIRM] your answer; a natural fit is the evaluation and trust layer for GTM AI tools [inference].
