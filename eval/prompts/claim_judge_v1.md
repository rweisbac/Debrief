Task: you are grading a post-call summary written by an unknown system. Ignore the Apex playbook guidance above except as product facts. Judge only against the transcript, the CRM record and the release cards.

Break the output into atomic factual claims about the call, the people, the deal or the plan. One claim per fact. Include claims inside emails and plans. Skip greetings, sign-offs and pure formatting. Recommended actions count as claims only for the facts they assert (for example "send the SOC 2 report Sanjay asked for" asserts that Sanjay asked for it).

For each claim:
- claim: the claim in 25 words or fewer.
- category: concern, risk, commitment, next_step, or other.
- supported: true only if a transcript line or the CRM record states it, or it follows directly from them. A paraphrase is fine. A firmer, sooner, broader or more certain version of what was said is not supported.
- utterance_ids: the transcript lines that support it, or empty.
- overstated_commitment: true when the claim says someone committed or agreed to something they did not, or states a hedged or conditional statement as firm, or attaches a date nobody said. False otherwise.
- flagged_uncertain: true when the output itself marks the claim as uncertain, disputed, conditional, unconfirmed or open.
- why: 25 words or fewer.

Be strict and consistent. Do not reward length or style.
