# Deep research prompt: best practice for next steps after an enterprise technical validation demo

Paste everything below the line into a deep research tool. Save the answer as `docs/research/best_practice_findings.md` in this repo, then ask Claude to build from it (see "What happens next" at the bottom).

---

## Who this is for and why

I am building a prototype that reads the transcript of an enterprise B2B software sales call right after a technical validation (TV) demo, and recommends at most 3 next steps for the account executive (AE) and solutions consultant (SC). It works in the window between "the technical demo went well" and "the deal moves forward", where deals often stall.

Right now the quality bar for those next steps comes from my own judgment. I want it to come from documented best practice and published evidence instead. Later it will be calibrated on real outcome data (which steps were taken in deals that were won), but that data does not exist yet. Your research is the interim standard.

Be skeptical. Much of the sales literature is vendor content built on correlational data from the vendor's own customers. I need to know which claims are strong and which are marketing.

## What I need you to research

1. **What good looks like after a technical validation demo.** The specific actions that strong enterprise sellers and sales engineers take in the 1 to 10 business days after a technical demo or proof of concept. Cover at least:
   - securing a dated next meeting with the customer, and what to do when the customer defers
   - reaching the economic buyer and absent stakeholders (multithreading), including giving the champion material to carry internally (buyer enablement)
   - mutual action plans or close plans: when to introduce one, and what goes in it
   - closing open technical items: routing them to the right owner with a date the customer hears
   - customer-owned processes (security review, legal, procurement): how to support them without chasing
   - quantifying business value in the customer's own terms, without overclaiming
   - handling implementation-effort concerns and past failed projects
   - handling a named competitor or an incumbent tool
   - recap emails: timing, length and content
   - technical win criteria and exit criteria for a proof of concept
   - customer indecision and fear of a wrong choice (as opposed to preference for the status quo)
2. **What separates a non-obvious next step from a routine one.** Which actions do top performers take that average reps skip? Distinguish them from actions every rep already does.
3. **Anti-patterns.** Actions that look like follow-up but hurt the deal: "just checking in" messages, pushing for a meeting the customer deferred, sending generic collateral, guessing timelines, overstating results.
4. **Frameworks and how they apply to this window.** MEDDPICC, Challenger and the Challenger Customer (mobilizers), Gartner's buyer enablement and sense making research, the JOLT Effect (Dixon and McKenna), mutual action plans, and Command of the Message (Force Management). Say what each actually recommends for this window, not a general summary.
5. **Evidence quality.** Grade every claim you rely on.

## Leads to verify (do not trust these; check the primary source)

I found these through secondary sources and could not reach the originals. For each one, confirm or correct the number, name the primary source, and say what kind of evidence it is.

- Gartner: buying groups of 6 to 10 people, and buyers spend about 17% of buying time meeting suppliers.
- Gartner (2019): 80% of "sense making" sellers closed high-quality, low-regret deals, against 50% for "telling" and 30% for "giving".
- Gartner: buyer enablement material makes a high-quality deal about 2.8 times more likely.
- JOLT Effect (2.5 million sales calls): 40 to 60% of deals stall in no decision, and indecision is the cause about 56% of the time.
- Gong Labs: won deals have about twice as many buyer contacts, and multithreading lifts win rate about 130% on deals over $50K.
- Gong Labs: the fastest deals spend 53% more time on next steps in the first meeting.
- Gong: follow-up within 24 hours, or within 2 hours of the call, improves reply rates or win rates.
- Outreach: mutual action plans associated with about a 26% higher win rate.

## The current playbook (fictional company, Apex)

Each recommended step must cite one of these rules. Tell me which best practices are missing, and which rules are weak or wrong.

- PB-01: send the customer a written recap within 24 hours. Include only what was said.
- PB-02: agree a dated next meeting in the call, or within 2 business days. "We will be in touch" is not a next step.
- PB-03: name the economic buyer by day 5 of TV, with a planned touchpoint before any commercial discussion.
- PB-04: route every unresolved technical item to the SC with an owner and a date the customer heard.
- PB-05: keep at least 2 engaged customer contacts. When an absent stakeholder matters, give the champion something specific to bring to them.
- PB-06: flag a named competitor to deal desk within 1 business day. Answer on the customer's workload, not with general claims.
- PB-07: tie the recap to the customer's own stated outcome. If none was stated, say so internally and ask for it.
- PB-08: log every SC commitment with an owner and a date, including ones said in passing, and tell the customer when it is done.
- PB-09: support customer-owned processes (security review, legal, procurement). Do not send "checking in" messages or push for a meeting the customer deferred.
- PB-10: when a customer raises implementation effort, respond with a realistic onboarding plan with named owners and customer effort by role. Do not guess a timeline.

## The 5 test scenarios (synthetic)

For each scenario, give the next steps that best practice says should come first, ranked, at most 3. Also give the steps that would be routine or wrong.

1. **Halvorsen Freight (logistics, $285K).** The technical demo went well. Outcome stated: catch late loads while dispatch can still reroute. The COO (economic buyer, owns the budget) was absent but a 45 minute session with her is booked for Oct 8. She was burned by an 8 month past project and will ask about time to value. One open item: row level access for a partner hierarchy, with the SC committed to a Tuesday date. No competitor.
2. **Meridian Health Partners (healthcare, $420K).** The technical result was good, but SSO is open: the customer's identity provider sends nested claims and the product supports only flat claims today, with no general availability date for nested claims. A workaround needs a customer token change through their own security review (6 to 8 weeks). Nothing moves until the vendor security committee approves (meets Oct 9). They need a complete packet before then: questionnaire, SOC 2 report, encryption details, and a written SSO design. The security reviewer was absent. No next meeting was agreed.
3. **Corvid Retail Group (retail, $310K).** The champion is not the decision maker. The head of data engineering raised implementation effort politely as "timing", but the real driver is a painful past migration (4 months, lost 2 engineers). The marketing team already uses a competitor, Lakestream, and the champion's boss will ask why not extend it. The CFO approves anything over $250K and was mentioned once in passing. The champion asked for a pricing range. The customer deferred: "let us digest this, we'll be in touch".
4. **Pinecrest Insurance (insurance, $140K).** A low-information call. The data architect left early and was lukewarm ("sort of"). No business outcome was stated. One small open item on two column data types. No next meeting.
5. **Atlas Biologics (life sciences, $230K).** Outcome stated: scientists decide the next run the same afternoon, taking a week or more out of each screening campaign. IT and compliance disagree internally on EU-only versus US hosting, and compliance is looking for a legal memo. The champion will take it to her VP (unnamed) once hosting is settled. No next meeting was agreed.

## Output format (required)

Use these 6 sections, in this order, with these headings. I will parse sections 3, 4 and 5.

### 1. Summary
Up to 10 bullets: what best practice says about this window, and the 3 most important things the playbook gets wrong or misses.

### 2. Evidence table
One row per claim you rely on. Columns: claim; primary source (author, title, year, link); evidence type (independent research, analyst survey, vendor data from its own customers, practitioner opinion); causal or correlational; strength (strong, moderate, weak); notes.

### 3. Best practice rules
A list of rules in this exact form, so they can become playbook rules:

```
- id: BP-01
  rule: one sentence, an action a rep can take
  when_it_applies: the trigger in the call that makes it relevant
  why: one sentence with the evidence
  evidence_ids: [rows from section 2]
  strength: strong | moderate | weak
  maps_to_playbook: PB-0X, or "missing"
```

### 4. Rubric for judging a recommended next step
5 to 8 criteria a grader can apply to one recommended step. For each: name, a pass or fail definition, one example that passes and one that fails (from this domain), and the evidence behind it. Say whether "doable in under 10 minutes" and "a typical AE would not do it unprompted" are good criteria or should be replaced.

### 5. Reference answers for the 5 scenarios
For each scenario:

```
- scenario: Halvorsen Freight
  must_have_steps:
    - step: one sentence
      rule: BP-0X or PB-0X
      why_first: one sentence
  good_optional_steps: [...]
  routine_steps: [steps a typical rep does anyway, so they add little]
  wrong_steps: [anti-patterns for this scenario, with the reason]
  deal_state: one of ready_to_advance, open_technical_gap, missing_stakeholder, competitive_risk, waiting_on_customer, low_information, with one sentence why
```

### 6. Open questions
Where the evidence is thin or conflicts, and what outcome data would settle it (for example: which steps, taken within how many days, correlate with the deal advancing).

## Rules for the answer

- Never present a correlation as a cause. Say "associated with" unless the study design supports a causal claim.
- Prefer primary sources. When only a vendor blog is available, say so and mark the claim weak.
- Do not invent statistics. If you cannot find a number, say so.
- Keep each rule and step to one sentence a sales rep can act on.

---

## What happens next (for me, not the research tool)

Once `docs/research/best_practice_findings.md` is in the repo, Claude will:

1. Add the missing best practice rules to the playbook (`data/playbook.md`, new rule IDs) so the tool can recommend them.
2. Rewrite the judge as `prompts/judge/v2.md` using the research rubric, with its pass and fail examples.
3. Turn section 5 into reference answers (`data/reference_steps/`) and add a score for whether the tool's steps cover the must-have steps, so "correct next steps" is measured directly and not only by the judge.
4. Use the reference answers to check the judge: if the judge passes steps the research calls routine or wrong, the judge is miscalibrated.
5. Re-record and report before and after, as in DECISIONS D-15.

These are research-based labels, not outcome data. They stand in until real won and lost deals can be labeled.
