"""Gold labels for the 15 eval transcripts, written by hand before any system was run on them.

Synthetic data, fictional companies. Run: python eval/gold_src.py
Writes eval/gold/<id>.json with every anchor resolved to an utterance ID. An anchor that matches
no utterance, or more than one, is an error.

Fields per case:
- concerns: what a customer stakeholder said worries them
- risks: open technical or deal risks that are not closed at the end of the call
- commitments: things someone clearly said they would do (firm)
- non_commitments: hedged or conditional statements that must NOT be reported as firm commitments
- uncertain: items a good output should flag as uncertain, disputed or unconfirmed
- next_steps: what a strong AE would do next (reference only)
- agreed_next_step: whether the customer agreed a dated next meeting or action (None = not scored)

keywords: a list of groups. A text matches when every group has at least one of its "|" terms
(case-insensitive substring). Used to score free text from both systems the same way.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.transcript import load_transcript, normalize  # noqa: E402

OUT = ROOT / "eval" / "gold"
TRANSCRIPTS = ROOT / "eval" / "data" / "transcripts"


def K(*groups: str) -> list[list[str]]:
    return [g.split("|") for g in groups]


def item(id_, summary, anchors, keywords, **extra):
    return {"id": id_, "summary": summary, "anchors": anchors, "keywords": keywords, **extra}


def com(id_, who, side, what, by_when, anchors, keywords):
    return item(id_, what, anchors, keywords, who=who, side=side, by_when=by_when)


G: dict[str, dict] = {}

G["e01"] = dict(
    hard_cases=[], scenario="Clean call, champion books the CFO, dated next meeting.",
    agreed_next_step={"exists": True, "date": "2026-10-06"},
    concerns=[item("C1", "Load on the order database", ["hammered the order database"], K("order database|load")),
              item("C2", "Needs cost per store and overstock reduction for the CFO", ["I need the cost per store"],
                   K("cost per store|overstock|business case"))],
    risks=[],
    commitments=[com("M1", "Hannah Ortiz", "apex", "Send business case numbers", "2026-10-02",
                     ["I'll send it by Friday the 2nd"], K("business case|cost per store|overstock")),
                 com("M2", "Maya Lindqvist", "customer", "Book 30 minutes with Priscilla, the CFO", "2026-10-06",
                     ["I'll set up 30 minutes with her"], K("priscilla|cfo")),
                 com("M3", "Devon Clarke", "apex", "Send the change feed setup doc", "2026-09-28",
                     ["I'll send you the setup doc today"], K("setup doc|change feed|runbook"))],
    non_commitments=[], uncertain=[],
    next_steps=[item("N1", "Business case numbers to Maya by Oct 2", [], K("business case|cost per store|overstock")),
                item("N2", "Prepare the Oct 6 CFO meeting with Priscilla", [], K("priscilla|cfo")),
                item("N3", "Send the setup doc for the runbook", [], K("setup doc|change feed|runbook"))])

G["e02"] = dict(
    hard_cases=["ambiguous_commitments"], scenario="Every customer action is hedged. No dated next step.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "Lineage through dynamic stored procedures", ["Most of them are dynamic"], K("stored procedure"))],
    risks=[item("R1", "Lineage for dynamic stored procedures is unproven", ["Most of them are dynamic"],
                K("stored procedure"))],
    commitments=[com("M1", "Ben Adeyemi", "apex", "Send a recap today", "2026-09-29", ["I'll send a recap today"],
                     K("recap")),
                 com("M2", "Sofia Russo", "apex", "Write up the stored procedure question for Tamsin", "",
                     ["I'll write up the stored procedure question"], K("write up|written|write-up"))],
    non_commitments=[
        item("H1", "Sofia: see if a couple of procedures can run through the parser, no promises", ["No promises on timing"],
             K("parser")),
        item("H2", "Gregor: try to dig up the data dictionary, maybe next week", ["I'll try to dig it up"],
             K("data dictionary")),
        item("H3", "Tamsin: might loop in procurement, needs her manager", ["I might be able to loop in procurement"],
             K("procurement")),
        item("H4", "Gregor: reconnect maybe the week after next, no hold", ["Maybe the week after next"],
             K("reconnect|week after next"))],
    uncertain=[item("U1", "Data dictionary timing", ["Sometime next week, maybe"], K("data dictionary")),
               item("U2", "Procurement loop-in needs manager approval", ["I'd have to ask my manager first"],
                    K("procurement")),
               item("U3", "No dated next meeting", ["Not yet. Let me see how things shake out"],
                    K("reconnect|next meeting|calendar|hold|week after next"))],
    next_steps=[item("N1", "Recap that lists the hedged asks as open, with no invented dates", [], K("recap")),
                item("N2", "Make the data dictionary ask specific and easy", [], K("data dictionary")),
                item("N3", "Written stored procedure ask with sample request", [], K("stored procedure"))])

G["e03"] = dict(
    hard_cases=["contradictory_statements"], scenario="VP Ops and IT director disagree on seats, residency and freshness.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "Dispatch needs real time", ["Real time is non negotiable for us"], K("real time|real-time")),
              item("C2", "IT expects 400 seats, not 50", ["we're looking at 400 seats in year one"], K("400")),
              item("C3", "Canadian contracts require data in Canada", ["Our Canadian contracts say shipment data stays in Canada"],
                   K("canad")),
              item("C4", "Late load alerts by text or paging tool", ["Can they go to text message?"], K("text|paging|sms"))],
    risks=[item("R1", "Canadian data residency is unresolved", ["Our Canadian contracts say shipment data stays in Canada"],
                K("canad|residency")),
           item("R2", "Scope and seat count disputed, 50 vs 400", ["we're looking at 400 seats in year one"], K("400")),
           item("R3", "Freshness requirement disputed, real time vs daily", ["daily refresh would be enough"],
                K("daily"))],
    commitments=[com("M1", "Omar Haddad", "apex", "Check Canadian residency with the hosting team", "2026-10-01",
                     ["come back by Thursday, October 1st"], K("canad|residency")),
                 com("M2", "Leah Brennan", "apex", "Show pricing for both 50 and 400 seats", "",
                     ["We can show both"], K("pricing|price"))],
    non_commitments=[item("H1", "A Canadian region is on the roadmap, not available", ["Canadian region on the roadmap"],
                          K("canadian region|roadmap"))],
    uncertain=[item("U1", "Seat count disagreement", ["I don't think finance needs this"], K("400|seat")),
               item("U2", "Residency disagreement", ["That's not what I was told"], K("canad|residency")),
               item("U3", "Freshness disagreement", ["For IT maybe. Dispatch needs real time"], K("daily|real time|real-time"))],
    next_steps=[item("N1", "Residency answer by Oct 1 to both, with their legal", [], K("residency|canad")),
                item("N2", "Resolve seat scope with the champion; price both", [], K("400"), ),
                item("N3", "Confirm freshness needs per use case", [], K("daily|freshness"))])

G["e04"] = dict(
    hard_cases=["missing_stakeholder"], scenario="The CISO who must sign off is absent; economic buyer unknown.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "CISO will ask about audit trail and unblinded access", ["Audit trail and who can see unblinded data"],
                   K("okafor|ciso")),
              item("C2", "Roll back a bad load", ["Can we roll back a bad load?"], K("roll back|rollback|restore")),
              item("C3", "Time boxed unblinding", ["Can the role be time boxed?"], K("expir|time box|time-box|interim"))],
    risks=[item("R1", "CISO sign off required, timing unknown", ["I can't move this without Dr. Okafor"],
                K("okafor|ciso")),
           item("R2", "Commercial process and economic buyer unknown", ["Honestly I'm not sure yet"],
                K("procurement|r and d|r&d|threshold|economic buyer"))],
    commitments=[com("M1", "Wes Hollis", "customer", "Send the data dictionary", "", ["I can send over the data dictionary"],
                     K("data dictionary")),
                 com("M2", "Marta Kowal", "apex", "Send a recap this afternoon", "2026-09-30",
                     ["I'll send a recap this afternoon"], K("recap"))],
    non_commitments=[item("H1", "Simone said maybe to a write-up for the CISO", ["Maybe. She doesn't read long documents though"],
                          K("okafor|ciso", "write|brief|summary|one page|one-page"))],
    uncertain=[item("U1", "CISO availability", ["Her calendar is a disaster"], K("okafor|ciso")),
               item("U2", "Approval threshold and buyer unknown", ["I don't know the threshold this year"],
                    K("threshold|procurement|r and d|r&d"))],
    next_steps=[item("N1", "Short brief on audit reads and unblinded access for Simone to forward", [], K("okafor|ciso")),
                item("N2", "Ask who owns budget and the approval threshold", [], K("threshold|procurement|r and d|r&d|budget")),
                item("N3", "Recap", [], K("recap"))])

G["e05"] = dict(
    hard_cases=["long_rambling_call", "objection_buried"], scenario="83 turns of tangents; privacy concern buried mid call.",
    agreed_next_step={"exists": None, "date": ""},
    concerns=[item("C1", "Privacy team may not allow joining viewing logs to opted out subscribers",
                   ["The privacy team has been making noise about consent data"], K("consent|privacy|opted out|opt out")),
              item("C2", "Burned by a past vendor that overpromised real time", ["real time meant every six hours"],
                   K("vendor")),
              item("C3", "Agency must only see aggregates", ["The agency should only see aggregate numbers"],
                   K("agency|aggregate")),
              item("C4", "Handling of late events", ["I want to see how you handle late events"], K("late event")),
              item("C5", "Some segments live in spreadsheets", ["Some of them are defined in spreadsheets"],
                   K("spreadsheet"))],
    risks=[item("R1", "Consent rules may block the attribution use case", ["it might kill the whole attribution piece"],
                K("consent|privacy")),
           item("R2", "Budget sits with Ann; planning is in November", ["I need to talk to Ann about budget"],
                K("ann|november|budget")),
           item("R3", "Spreadsheet segments need manual refresh", ["it's just a manual refresh"], K("spreadsheet|manual"))],
    commitments=[com("M1", "Ryan Castellano", "apex", "One pager for Ann", "2026-10-07",
                     ["I'll get that to you by Wednesday, October 7th"], K("one pager|one-pager|summary")),
                 com("M2", "Nia Oduya", "apex", "Send dedupe config and a note on late events", "2026-10-02",
                     ["I'll send the dedupe config"], K("dedupe")),
                 com("M3", "Karen Ibsen", "customer", "Send the list of 60 segments", "",
                     ["I'll send over the list of our 60 segments"], K("segment"))],
    non_commitments=[item("H1", "Fantasy league: I'll think about it", ["I'll think about it"], K("fantasy"))],
    uncertain=[item("U1", "Consent issue could be nothing or could block attribution", ["It might be nothing"],
                    K("consent|privacy")),
               item("U2", "Doug's support is qualified by the last vendor experience", ["take that with a grain of salt"],
                    K("last vendor|grain of salt|qualif|liked the last"))],
    next_steps=[item("N1", "One pager for Ann by Oct 7", [], K("ann", "one pager|one-pager|summary")),
                item("N2", "Raise the consent question with the privacy team early", [], K("consent|privacy")),
                item("N3", "Dedupe config and late events note", [], K("dedupe"))])

G["e06"] = dict(
    hard_cases=["objection_buried"], scenario="Positive call; EU-only legal rule and a spend freeze surface in the last minute.",
    agreed_next_step={"exists": None, "date": ""},
    concerns=[item("C1", "Legal will not accept a processor storing data outside the EU", ["won't accept a processor"],
                   K("eu|frankfurt")),
              item("C2", "CFO froze new software spend until Q2", ["our CFO froze new software spend"],
                   K("freeze|froze|second quarter|q2|april"))],
    risks=[item("R1", "EU residency needs contract wording in writing", ["They'll want that in writing"], K("eu|frankfurt")),
           item("R2", "Spend freeze makes a contract before April unlikely", ["a contract before April is unlikely"],
                K("freeze|froze|april|second quarter|q2")),
           item("R3", "Exception path via historian replacement is unconfirmed", ["It might replace the old historian license"],
                K("historian"))],
    commitments=[com("M1", "Milan Horak", "customer", "Get controller access sorted", "2026-10-09",
                     ["I'll get the controller access sorted"], K("controller")),
                 com("M2", "Jonas Weber", "apex", "Send the pilot plan with success criteria", "2026-10-05",
                     ["I'll send the pilot plan"], K("pilot plan|success criteria"))],
    non_commitments=[item("H1", "Petra would have to check with finance", ["I'd have to check with finance"], K("finance")),
                     item("H2", "Historian replacement is a maybe", ["It might replace the old historian license"],
                          K("historian"))],
    uncertain=[item("U1", "Exception process is unclear", ["Maybe, if it replaces something we already pay for"],
                    K("exception|historian")),
               item("U2", "Contract timing after the freeze", ["a contract before April is unlikely"],
                    K("april|second quarter|q2|freeze|froze"))],
    next_steps=[item("N1", "EU hosting wording from compliance, in writing for legal", [], K("eu|frankfurt", "compliance|wording|legal|writing")),
                item("N2", "Build the historian replacement case for an exception", [], K("historian")),
                item("N3", "Pilot plan by Oct 5", [], K("pilot plan"))])

G["e07"] = dict(
    hard_cases=[], scenario="Security review gates the deal, with dates the customer gave.",
    agreed_next_step={"exists": None, "date": ""},
    concerns=[item("C1", "Support access control", ["What about support access?"], K("support access")),
              item("C2", "Needs SOC 2 and pen test summary", ["I'll need the SOC 2 report"], K("soc 2|pen test"))],
    risks=[item("R1", "Security review gates progress; documents due Oct 14 for the Oct 22 board",
                ["If I have everything by October 14th"], K("review board|security review|board|october 14|oct 14"))],
    commitments=[com("M1", "Andre Silva", "apex", "Send SOC 2 and pen test summary", "2026-10-01",
                     ["I'll send both today"], K("soc 2|pen test")),
                 com("M2", "Andre Silva", "apex", "Send the data flow diagram", "2026-10-09",
                     ["I'll do the data flow diagram"], K("data flow")),
                 com("M3", "Sanjay Iyer", "customer", "Send the security questionnaire", "2026-10-01",
                     ["I'll send the questionnaire today"], K("questionnaire")),
                 com("M4", "Monica Reyes", "customer", "Bring in Daniel from finance after the board", "",
                     ["I'll bring in Daniel from finance"], K("daniel"))],
    non_commitments=[], uncertain=[],
    next_steps=[item("N1", "Complete packet by Oct 14", [], K("data flow|packet|questionnaire")),
                item("N2", "Prepare for finance with Daniel after the board", [], K("daniel|finance"))])

G["e08"] = dict(
    hard_cases=[], scenario="Lakestream incumbent; dated review before the renewal.",
    agreed_next_step={"exists": True, "date": "2026-10-14"},
    concerns=[item("C1", "Why add Apex next to Lakestream", ["the question is why add Apex"], K("lakestream")),
              item("C2", "All in cost including the add on", ["all in costs"], K("cost"))],
    risks=[item("R1", "Lakestream incumbent with renewal on Oct 20", ["Lakestream renewal conversation"],
                K("lakestream")),
           item("R2", "Comparison depends on Tobias sending volumes", ["About a week after Tobias sends the volumes"],
                K("volume"))],
    commitments=[com("M1", "Tobias Lund", "customer", "Send event volumes per hour", "2026-10-01",
                     ["I'll send them tomorrow"], K("volume")),
                 com("M2", "Lena Fischer", "apex", "Build the workload cost comparison", "",
                     ["I'll build the comparison once I have the volumes"], K("comparison|side by side")),
                 com("M3", "Isaac Morgan", "apex", "Send the invite for Oct 14", "", ["I'll send the invite"],
                     K("invite|october 14|oct 14|2026-10-14"))],
    non_commitments=[], uncertain=[item("U1", "Comparison timing depends on the volumes", ["About a week after"], K("volume"))],
    next_steps=[item("N1", "Workload comparison including the add on before Oct 14", [], K("comparison|side by side|side-by-side")),
                item("N2", "Flag Lakestream to deal desk", [], K("deal desk")),
                item("N3", "Land the comparison before the Oct 20 renewal", [], K("october 20|oct 20|renewal"))])

G["e09"] = dict(
    hard_cases=["missing_stakeholder"], scenario="One IT contact who does not decide; very little said.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[],
    risks=[item("R1", "No decision maker identified", ["I'm not really the one who decides"],
                K("decide|decision|operations"))],
    commitments=[com("M1", "Kofi Mensah", "apex", "Send the load summary", "", ["I'll send the load summary"],
                     K("summary"))],
    non_commitments=[],
    uncertain=[item("U1", "Who owns the decision", ["Probably operations. I'm not sure who"], K("operations|decision|decides"))],
    next_steps=[item("N1", "Ask Hugo for the operations owner", [], K("operations")),
                item("N2", "Send the load summary", [], K("summary"))])

G["e10"] = dict(
    hard_cases=["ambiguous_commitments"], scenario="SC promises nested claims next quarter; release card says no GA date.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "Nested claim SSO is the gate", ["SSO first please. That's the gate for us"], K("nested|sso")),
              item("C2", "Needs it in writing for the architecture board", ["I'll need that in writing"],
                   K("architecture board|writing|written"))],
    risks=[item("R1", "Nested claims are not GA and have no announced date", ["nested claims are coming next quarter"],
                K("nested")),
           item("R2", "Architecture board on Nov 3 needs a design and a date", ["next on November 3rd"],
                K("architecture board|november 3"))],
    commitments=[com("M1", "Ana Petrov", "apex", "Send the written SSO design", "2026-10-09",
                     ["I'll send the SSO design by Friday, October 9th"], K("design")),
                 com("M2", "Ana Petrov", "apex", "Get the exact date for nested claims", "",
                     ["I'll get you the exact date"], K("nested|date"))],
    non_commitments=[item("H1", "Nested claims next quarter is hearsay, not a commitment", ["That's what I've heard"],
                          K("next quarter")),
                     item("H2", "Preview program access was assumed, not confirmed", ["I'm sure"], K("preview"))],
    uncertain=[item("U1", "Nested claims timing", ["Next quarter, is that committed?"], K("nested"))],
    next_steps=[item("N1", "Correct the next quarter claim with the identity team before the design goes out", [],
                     K("nested", "identity team|correct|no announced|no ga|private preview|not committed|no general")),
                item("N2", "SSO design by Oct 9, including a flat claim option", [], K("design"))],
    traps=["Hourly connector sync was corrected to continuous at U017; hourly must not appear as current."])

G["e11"] = dict(
    hard_cases=["missing_stakeholder"], scenario="Enthusiastic contact, no commitment; budget owner not engaged.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "Privacy officer will review access controls", ["Our privacy officer will want to see that"],
                   K("privacy"))],
    risks=[item("R1", "Provost owns budget and is not engaged", ["The provost owns the budget"], K("provost|abernathy")),
           item("R2", "Technology committee timing unknown", ["I think they meet once a semester"], K("committee"))],
    commitments=[com("M1", "Sam Okoro", "apex", "Send retention dashboard screenshots", "",
                     ["I'll send the retention dashboard screenshots"], K("screenshot"))],
    non_commitments=[item("H1", "Champion enthusiasm is not an action", ["I'll absolutely champion this"],
                          K("champion")),
                     item("H2", "Eventually meet the provost, no date", ["Eventually, sure"], K("abernathy|provost"))],
    uncertain=[item("U1", "Committee timing unknown", ["I'm honestly not sure"], K("committee")),
               item("U2", "Enthusiasm without a decision path", ["I'm going to tell everyone about it"],
                    K("enthusias|no commitment|not a decision|no decision"))],
    next_steps=[item("N1", "Give Elise something specific for Dr. Abernathy", [], K("abernathy|provost")),
                item("N2", "Find the committee date and process", [], K("committee")),
                item("N3", "Access control material for the privacy officer", [], K("privacy"))])

G["e12"] = dict(
    hard_cases=["contradictory_statements", "ambiguous_commitments"], scenario="CDO says sign by month end, then concedes board approval.",
    agreed_next_step={"exists": None, "date": ""},
    concerns=[item("C1", "Board technology committee approval over 300 thousand", ["Anything over 300 thousand did last year"],
                   K("board|committee")),
              item("C2", "Mid term endorsements not shown", ["mid term endorsements"], K("endorsement"))],
    risks=[item("R1", "Close depends on board timing, November vs month end", ["They meet in November"],
                K("board|november")),
           item("R2", "Mid term endorsement handling unproven", ["That wasn't in the demo"], K("endorsement"))],
    commitments=[com("M1", "Rosa Medina", "apex", "Send a recording of mid term endorsements", "2026-10-06",
                     ["send a recording by Tuesday, October 6th"], K("endorsement")),
                 com("M2", "Victor Hayes", "apex", "Send the order form and a recap", "2026-10-01",
                     ["I'll send the order form and a recap today"], K("order form"))],
    non_commitments=[item("H1", "Sign by end of month is conditional on an exception", ["We'll sign by end of month"],
                          K("end of month", "sign")),
                     item("H2", "Approval before November is uncertain", ["I think I can get it approved before that"],
                          K("approv", "before"))],
    uncertain=[item("U1", "Close timing", ["but I'm not certain"], K("end of month|november|board"))],
    next_steps=[item("N1", "Support the board path or exception", [], K("board|committee")),
                item("N2", "Endorsements recording by Oct 6", [], K("endorsement")),
                item("N3", "Order form without treating the close date as firm", [], K("order form"))])

G["e13"] = dict(
    hard_cases=[], scenario="Latency risk with exact numbers; dated results review.",
    agreed_next_step={"exists": True, "date": "2026-10-12"},
    concerns=[item("C1", "99th percentile latency 3.8 seconds is too slow", ["3.8 seconds is too slow"],
                   K("3.8|99th|p99|latency")),
              item("C2", "Vessel estimates arrive in an old message format", ["over an old message format"],
                   K("format|port community"))],
    risks=[item("R1", "Latency over 2 seconds at p99; dedicated cluster unmeasured", ["I haven't measured it"],
                K("latency|99th|p99|3.8")),
           item("R2", "Message format unknown", ["I haven't seen that format"], K("format"))],
    commitments=[com("M1", "Mateo Ruiz", "apex", "Run the latency test on a dedicated cluster and send results",
                     "2026-10-08", ["send you the results by Thursday, October 8th"], K("dedicated")),
                 com("M2", "Yuki Tanaka", "customer", "Send a sample message file", "2026-10-02",
                     ["I'll send one today"], K("sample")),
                 com("M3", "Olivia Grant", "apex", "Send the invite for Oct 12", "", ["Booked. I'll send the invite"],
                     K("invite|october 12|oct 12|2026-10-12"))],
    non_commitments=[], uncertain=[item("U1", "Dedicated cluster latency is unknown", ["I won't give you a number"],
                                        K("dedicated"))],
    next_steps=[item("N1", "Dedicated test by Oct 8 against the 2 second target", [], K("dedicated")),
                item("N2", "Assess the message format sample", [], K("format|sample"))],
    traps=["Do not present dedicated cluster latency as a result; it was not measured."])

G["e14"] = dict(
    hard_cases=[], scenario="EU hosting fine; key policy may not allow a cloud key service.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "Contract wording on support access", ["We'll need the contract wording on support access"],
                   K("support access|wording")),
              item("C2", "On premises HSM today; cloud keys may not be allowed", ["We use an on premises HSM today"],
                   K("hsm|key")),
              item("C3", "Bad merges", ["we've been burned by bad merges before"], K("merge"))],
    risks=[item("R1", "Key policy may not allow a cloud key service", ["I'm not sure it does"], K("hsm|key service|cloud key|policy")),
           item("R2", "Group security office timing unknown", ["I don't control their timeline"], K("group security"))],
    commitments=[com("M1", "Elena Varga", "apex", "Confirm support access wording with compliance", "2026-10-07",
                     ["send it by Wednesday, October 7th"], K("wording|support access")),
                 com("M2", "Elena Varga", "apex", "Send the encryption whitepaper", "2026-10-01", ["I'll send it today"],
                     K("whitepaper"))],
    non_commitments=[],
    uncertain=[item("U1", "Key policy", ["I'll have to check whether our policy allows"], K("hsm|key|policy")),
               item("U2", "Group security timeline", ["I don't control their timeline"], K("group security"))],
    next_steps=[item("N1", "Whitepaper today, framed for the group security office", [], K("whitepaper")),
                item("N2", "Support access wording by Oct 7", [], K("wording|support access")),
                item("N3", "Give Matteo what group security needs on cloud keys", [], K("group security"))])

G["e15"] = dict(
    hard_cases=["missing_stakeholder", "objection_buried"], scenario="CFO joins in the last minute with term and build vs buy objections.",
    agreed_next_step={"exists": False, "date": ""},
    concerns=[item("C1", "3 year minimum term, quarterly in arrears", ["Quarterly in arrears only"],
                   K("three year|3 year|3-year|quarterly|arrears")),
              item("C2", "Cost comparison against building in house", ["a cost comparison against building it ourselves"],
                   K("build")),
              item("C3", "Stream backup behavior", ["What happens when the stream backs up?"], K("back up|backs up|outage|catch up")),
              item("C4", "Custom fields in case export", ["Does case export support our custom fields?"], K("custom field"))],
    risks=[item("R1", "Payment terms conflict with standard terms", ["Quarterly in arrears only"], K("arrears|quarterly|three year|3 year")),
           item("R2", "Build vs buy comparison required before signing", ["nothing gets signed this year"], K("build")),
           item("R3", "Custom fields untested", ["I'd want to test it on your case tool"], K("custom field"))],
    commitments=[com("M1", "Zara Ahmed", "customer", "Send the custom field list", "2026-10-03",
                     ["I'll send it tomorrow"], K("field")),
                 com("M2", "Ravi Shah", "apex", "Test custom fields once the list arrives", "",
                     ["I'll test the custom fields"], K("custom field")),
                 com("M3", "Nora Quinn", "apex", "Check terms with deal desk", "",
                     ["I'll need to check that with our deal desk"], K("deal desk"))],
    non_commitments=[item("H1", "Talk next week is not a dated next step", ["Let's talk next week"], K("next week"))],
    uncertain=[item("U1", "Next step undated", ["Let's talk next week"], K("next week")),
               item("U2", "CFO concedes in-house build may not work but still needs the comparison", ["Maybe not"],
                    K("build"))],
    next_steps=[item("N1", "Take the terms to deal desk", [], K("deal desk")),
                item("N2", "Build vs buy comparison for Helen", [], K("build")),
                item("N3", "Test custom fields", [], K("custom field"))])


def resolve(case_id: str, gold: dict) -> dict:
    t = load_transcript(case_id, TRANSCRIPTS)
    out = dict(gold, deal_id=case_id, _note="Synthetic data, fictional company. Hand labels written before any run.")
    for key in ("concerns", "risks", "commitments", "non_commitments", "uncertain", "next_steps"):
        for it in out[key]:
            ids = []
            for a in it["anchors"]:
                hits = [u.id for u in t.utterances if normalize(a) in normalize(u.text)]
                if len(hits) != 1:
                    raise SystemExit(f"{case_id} {key} {it['id']}: anchor {a!r} matched {hits}")
                ids.append(hits[0])
            it["utterance_ids"] = ids
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    totals = {k: 0 for k in ("concerns", "risks", "commitments", "non_commitments", "uncertain", "next_steps")}
    for cid, g in G.items():
        r = resolve(cid, g)
        (OUT / f"{cid}.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
        for k in totals:
            totals[k] += len(r[k])
    print(f"{len(G)} cases", totals)
