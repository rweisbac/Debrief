# Hand review of the judge's flags and Debrief's blocks

Synthetic data, fictional companies. Done after scoring, on 2026-10-04, by 1 reviewer (Claude, in the session that built the eval), reading each flagged claim against its transcript. It is a post hoc reading; it does not change any number in `results.md`. Debrief and the baseline were not changed.

## Overstated or fabricated commitments (metric c)

The judge flagged 23 Debrief claims and 17 baseline claims. Each was sorted into 1 of 3 kinds.

| Kind | Debrief | Baseline |
|---|---|---|
| Real overstatement: a commitment, date, owner or offer nobody said | 6 | 16 |
| Recommendation or proposed plan row with an owner and due date, which the judge read as a commitment | 16 | 1 |
| Pedantic | 1 | 0 |
| Total flagged | 23 | 17 |

Where the baseline's 16 real overstatements sit: 9 are new offers or promises written into the customer email on the rep's behalf (e02, e03, e04, e05, e07, e10, e11, e13, e14). The baseline has no gate, so a rep could send them as written.

Debrief's 6 real overstatements: e02 (an invented due date on a real write-up, "Sofia promised the parser run" when she said "no promises", and a partial-export offer in the recap), e05 (the plan names Nia as owner of items she never took), e07 (an invented date on the recap), e11 (an access-controls view Sam never offered). The e02 recap offer was blocked by the promise gate before approval (block B1 below).

Why Debrief has 16 of the second kind: its next steps and plan rows carry an owner and a due date by design (`prompts/assess_and_recommend/v2.md`, `prompts/draft_mutual_action_plan/v1.md`). The judge prompt counts "a date nobody said" as overstated, and it did not separate a recommendation from a claim about the call. Several are marked "proposed" in the output.

## Debrief drafts blocked for review (needs review)

14 artifacts across 9 of 15 cases were blocked from one-tap approval.

| Kind | Count | Blocks |
|---|---|---|
| Real catch | 6 | B1 e02 recap, uncommitted partial-export offer. B3 e03 recap, uncommitted pricing promise. B4 e04 recap, "maybe" turned into a promised write-up for the CISO. B6 e06 summary, reversed the close date conflict. B10 e11 plan, assigned deliverables nobody committed to. B13 e15 recap, follow-up promise Nora never made. |
| Real catch plus a false alarm | 2 | B11 e12 summary, Oct 30 came from the CRM checklist, not the call; "one" flagged as a number. B14 e15 summary, unsaid dates; "one" flagged as a number. |
| False alarm | 6 | B2 e02 "two" and "next week". B5 e06 "Budget:" read as a name. B7 e08 "one". B8 e08 "1" and "one". B9 e11 "Deferral:" read as a name. B12 e13 the 2 second target and a CRM date. |

The same e04 overstatement appears in both systems. Debrief's recap was blocked (B4). The baseline's email reads "we'll send a one-page summary on audit logging and unblinded-data access that you can forward", with nothing stopping it.

## Deal state overridden by the low-information rule

R-LOWINFO (`src/rules.py`) sets the state to low_information and cuts steps to 2 when a call has fewer than 8 customer turns of 8 or more words. It fired on 6 of 15 cases (e04, e09, e10, e12, e13, e15). Only e09 is a low-information call by design. On e13 it replaced open_technical_gap on a call with a dated review meeting and a measured latency risk; on e15 it replaced competitive_risk after the CFO raised term and build vs buy objections. These transcripts are shorter than the repo's own (17 to 29 turns, except e05 at 83), which is what trips the rule.

## Traps checked by reading both outputs

| Case | Trap | Debrief | Baseline |
|---|---|---|---|
| e10 | SC said nested claims "next quarter"; release card says no announced date | Flagged it and recommends telling Fatima it is unconfirmed | Flagged it; email avoids the claim |
| e10 | Hourly sync corrected to continuous | Reports the correction | Reports the correction |
| e13 | Dedicated cluster latency not measured | Marked unmeasured | Marked as an expectation, not a measurement |
| e04 | "Maybe" to a CISO write-up | Overstated in the recap, then blocked | Overstated in the email, not blocked |
