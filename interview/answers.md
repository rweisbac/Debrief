# Answers, ready to paste

Spoken versions. Labels stay in so you know what each line rests on; drop them when speaking. Fill every [CONFIRM] before the panel. Full context, overclaim warnings and follow-ups are in `objections.md`.

## Opening, 30 seconds

Debrief covers the window right after a technical validation demo, when the buyer has seen the product work and the deal still stalls. [repo] `README.md`

It reads the call and the CRM record, then gives the rep at most 3 next steps, each tied to a playbook rule and a line from the call, plus drafts a human approves. [repo] `src/schemas.py`, `src/chain.py`

Every quote is rendered by code from the transcript, and approval is blocked when a draft promises something nobody said. [repo] `src/transcript.py`, `src/chain.py`

## 1. Why the post-technical-validation window

The TV window is where deals stall after the buyer has already seen the product work. In my scenario packet, days in TV rose 12, 14, 18 over 3 quarters while other stages stayed flat. [repo] `README.md`, synthetic packet

Outside research says indecision, more than competitors, is the biggest outcome in qualified B2B deals: 40 to 60% no decision. [external] F2, [CONFIRM] HBR original

The TV call is the last time everyone was in the room, and it is recorded, so the output can be grounded line by line.

## 2. Is the problem real

The pattern is well supported outside: 53% of lost deals in a 154-startup survey ended in no action, 27% in competition. [external] F3, [CONFIRM]

I have not validated it with Braze sellers yet. The product measures it in 30 days through dismiss reasons, with a rule declared up front: a cause counts only if it explains 30% of non-actions across 20 or more events. [repo] `README.md`, `src/metrics.py`

## 3. Why not Gong

Gong now ships custom agents for follow-ups and deal risk, with approval gates. [external] F7, [CONFIRM]

I treat summaries and follow-up emails as commodity. What Debrief adds is TV-stage playbook rules, SC commitment tracking, and checks that block approval. [repo] `README.md`

In production, Gong is the source of transcripts, and I would test whether Gong's own agents can carry these rules before running a second system. [repo] `README.md` "Production path", [inference]

## 4. Accuracy

Accuracy is enforced in code. Quotes come from the transcript table, every cited line has to exist and match, and a skeptical verifier runs before approval. [repo] `src/transcript.py`, `prompts/verify/v1.md`

On the repo's 5 deals, the verifier caught 20 of 20 planted errors, 14 of 20 without it, with 0 false alarms on 5 clean drafts. [eval] `evals/ablation.md`

I tested it against a plain Claude call on 15 new hard-case transcripts. On factual support they tied: a blind judge marked 93% of claims supported for both. [eval] `eval/results.md`

The difference is what can reach a customer. Debrief blocked all 4 recaps that promised something nobody said. The plain call's emails held 9 of those, with nothing to stop them. [eval] `eval/hand_review.md`

It also lost on some things. It costs about 8 times more, and a word-count rule mislabeled 5 calls as low information. [eval] `eval/README.md`

These are 1-run results on synthetic data with an uncalibrated judge, so I read them as direction.

## 5. Adoption by sellers

The rep confirms 4 pre-filled fields on a Slack card instead of typing notes during the call. [repo] DECISIONS D-16

Confidence is computed in code, so a field is only collapsed when the call supports it. [repo] `src/capture.py`

Adoption is measured from day 1, and the first failure I watch for is cards ignored after 24 hours. [repo] `README.md`

## 6. Success metrics

At 30 days: a customer-confirmed dated next step within 2 business days, and recap reply rate. [repo] `README.md`

At 90 days: days in TV per arm from a staggered rollout by pod, as a censored median. Win rate stays labeled correlational until 2 to 3 quarters pass. [repo] `README.md`, `src/metrics.py`

Every threshold is a proposal to agree with sales leadership, with scale, fix and stop rules.

## 7. Security and customer data

Nothing reaches a customer without a human; the notifier refuses any outside recipient. [repo] `src/adapters.py`

Consent and retention follow the call recorder. The prototype uses synthetic data only. [repo] `README.md`

Log redaction exists in code but needs presidio, which is not installed yet, so I would fix that before any pilot. [repo] DECISIONS D-04

## 8. Consultant versus builder

[CONFIRM] your GTM years and roles.

On building: I shipped Debrief end to end, 34 commits, 337 passing tests and 2 recorded runs on live model output. [repo] git log, pytest, `README.md`

I also logged every place the AI coding tool got it wrong and how I fixed it, including reversing my own rule when research showed it penalized the best steps. [repo] DECISIONS.md D-17

## 9. Why not build on Braze's own agent products

I would. Debrief is plain Python with adapters and no agent framework, so its rules and checks can move to whatever runtime Braze supports. [repo] DECISIONS.md, `src/adapters.py`

I have not used the Braze Agent Console or MCP server yet, so that is the first thing I would learn. [external] F9, [CONFIRM]

## 10. Agent versus workflow

Debrief is a workflow on purpose. The steps are known in advance, so an agent would add risk without adding capability. [repo] DECISIONS.md

The model does judgment inside fixed steps, and code overrides it when it breaks a rule. [repo] `src/rules.py`

## 11. First 90 days

Days 1 to 30: shadow AEs and SCs and map where handoffs fail. [external] F1, [hypothesis]

Days 31 to 60: ship 1 narrow workflow, likely SC commitment tracking, to 1 pod with measurement on. [hypothesis]

Days 61 to 90: read the data against rules declared up front, then scale, fix or stop.

## 12. Why leave a Director role

[CONFIRM] your own reason, in your words, with no employer details.

## Closing, 15 seconds

The part I would bring to Braze is the trust layer: grounding every claim in a source line, blocking promises nobody made, and measuring honestly, including the failures. [repo] `src/transcript.py`, `src/chain.py`, DECISIONS.md
