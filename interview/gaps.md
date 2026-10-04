# Gaps, ranked by risk

Every [CONFIRM] in the interview files and every objection with weak evidence. Highest risk first: the ones most likely to be probed, or most damaging if wrong.

## Blocking before the panel

1. **The commitment comparison rests on a post hoc hand review.** The scored judge count went against Debrief, 23 to 17 [eval] `eval/results.md`. The reading that only 6 of Debrief's flags are real, against 16 for the baseline, is 1 reviewer's classification after seeing results [eval] `eval/hand_review.md`. If a panelist pushes, lead with the scored tie and the scored loss, then explain the classification. Fix before relying on it: have a second person label the 40 flags blind.
2. **Your GTM years and roles (objection 8).** The posting asks for 6+ years in GTM [external] F1. Nothing in the repo covers your background. Fill it in your own words.
3. **Why you are leaving a Director role (objection 12).** Entirely yours to write. Keep employer details out.
4. **How much you built versus the AI coding tool (objection 8 follow-up).** DECISIONS.md is framed as "where the AI output was wrong" [repo]. Expect this question; have a clear, honest split ready.

## External claims not verified

The network policy in this session blocked every external URL, so none of F1 to F10 was opened.

5. **F7 Gong Custom Agents.** Feature names, "Deal Rescue Agent", approval gates and the June 2026 date. Used in objection 3. Getting a competitor's product wrong in front of a panel is costly.
6. **F1 Braze posting wording.** "Practitioners as users", "trust in live workflows", "stakeholder research on handoff failures", "6+ years GTM plus product shipping". Quote it exactly or paraphrase loosely.
7. **F9 Braze Agent Console and MCP server.** Source is a secondary summary site. You also have not used these products. Objection 9 depends on it.
8. **F2 40 to 60% no decision.** Secondary source; trace to the Dixon and McKenna original (HBR article or "The JOLT Effect") before quoting.
9. **F3 Lightspeed survey.** SaaStr secondary; confirm the 154 startups, 53%, 39%, 27% against the original.
10. **F4 Winsight 71%.** Vendor study; always say "vendor study".
11. **F8 Braze customer and ARR figures.** Not used in the answers. If you use them, check against the press release.
12. **F10 hallucination benchmarks.** Used only to say benchmarks disagree; low risk.

## Eval claims to state carefully

- **Keyword recall and flagging saturated** at 100% or near it for both systems [eval] `eval/results.md`. Do not cite them as evidence Debrief is better.
- **The judge is 1 uncalibrated call** from the same model family as both systems [repo] `eval/prompts/claim_judge_v1.md`.
- **Same author wrote the transcripts, gold labels and both prompts.** The baseline prompt was fixed before results, but it is still 1 person's generic prompt [repo] `eval/prompts/baseline_v1.md`.
- **Debrief ran with the default profile** (best practice off), the same configuration as the recorded runs [repo] `src/config.py`.
- **Wall clock was measured with 4 cases running at once**, so per-case times include contention [repo] `eval/run.py`.

## Repo claims to state carefully

13. **Gong MCP server is read-only and returns no raw transcripts** [repo] `README.md`. Written by the builder; may have changed. Confirm before saying it.
14. **"30 seconds" or "under 60 seconds" for the confirm card.** Design targets only; no user timing exists [repo] `README.md`.
15. **20 of 20 verifier catch rate.** 4 planted error types, 5 deals, 1 run [eval] `evals/ablation.md`. Never call it an accuracy rate.
16. **Pricing used for cost numbers.** `src/config.py` says the cache write rate is an assumption to verify [repo].
17. **The days-in-TV trend (12, 14, 18).** From a synthetic scenario packet, not company data [repo] `README.md`.

## Objections with weak evidence

| Rank | Objection | Why weak |
|---|---|---|
| 1 | 12. Why leave a Director role | No evidence in the repo; all personal |
| 2 | 8. Consultant vs builder | GTM tenure not in the repo; AI-assisted build needs a clear story |
| 3 | 2. Is the problem real | No user research; only external, partly secondary data |
| 4 | 9. Braze's own agent products | Secondary source only; products not used |
| 5 | 4. Accuracy | Supported claims tie at 93%; the commitment advantage is post hoc; keyword metrics saturated |
| 6 | 3. Why not Gong | Gong's features unverified and untested |
| 7 | 5. Adoption | Design only; no user has touched it |
| 8 | 11. First 90 days | Plan is a hypothesis by nature |
| 9 | 6. Success metrics | Well documented, but no metric has data |
| 10 | 7. Security | Redaction not active; otherwise well documented |
| 11 | 10. Agent vs workflow | Strong repo evidence |
| 12 | 1. Why the TV window | Good external support, labeled synthetic internal data |
