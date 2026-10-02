"""Debrief: Streamlit prototype. Synthetic data, fictional company.

Run with `make demo` (replay mode, sample cards enabled, no network).
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from src import blockkit, config, events, metrics, record_store, service
from src.adapters import FileCRMSource, FileGongSource, FileNotifier
from src.handoff import brief
from src.transcript import load_transcript

BANNER = "Synthetic data, fictional company."
ROLES = ["AE", "SC", "Sales manager", "CSM", "Measurement"]
CHECKLIST_FIELDS = {"dated_next_step": "Dated next step agreed with the customer",
                    "stakeholder_to_add": "Named stakeholder to add",
                    "business_outcome": "Customer's stated business outcome",
                    "sc_commitment": "Any commitment the SC made"}

st.set_page_config(page_title="Debrief", page_icon=":memo:", layout="wide")
crm_source, gong, notifier = FileCRMSource(), FileGongSource(), FileNotifier()

# Sidebar

with st.sidebar:
    st.markdown("## Debrief")
    st.caption(BANNER)
    role = st.radio("Role", ROLES, key="role")
    deal_id = st.selectbox("Deal", service.DEALS, format_func=lambda d: crm_source.deal(d)["account"], key="deal")
    hours = st.slider("Simulate time: hours since the demo ended", 0, 192, 0, key="hours",
                      help="Moves the clock forward so you can see reminders fire. Reminders only go out on "
                           "business days between 08:00 and 18:00 local time.")
    if st.button("Reset demo", help="Clears events, statuses, checklist entries and messages from this session."):
        record_store.reset_demo_state()
        if notifier.outbox.exists():
            notifier.outbox.unlink()
        for k in list(st.session_state):
            if k not in ("role", "deal"):
                del st.session_state[k]
        st.rerun()
    st.caption(f"Setup: {config.MODE} mode.")

st.info(BANNER)

crm = crm_source.deal(deal_id)
activity = gong.activity(deal_id)
transcript = load_transcript(deal_id)
record, source = service.load_debrief(deal_id)
end = service.demo_end(crm)
generated = service.card_generated(deal_id)
now = end + timedelta(hours=hours) if generated else end - timedelta(minutes=10)
pv = ",".join(f"{k}:{v}" for k, v in sorted((record or {}).get("prompt_versions", {}).items()))

if record and source == "sample":
    st.warning(record["sample_label"])


def log(name: str, role_name: str, **props) -> None:
    events.log(name, role_name, deal_id, pv, ts=now.isoformat(), **props)


def assessment() -> dict:
    return ((record or {}).get("artifacts", {}).get("assessment") or {}).get("current") or {}


def messages_for(role_key: str, deal: str | None = None) -> list[dict]:
    return [m for m in reversed(notifier.read_all()) if m["role"] == role_key and (deal is None or m["deal_id"] == deal)]


# Callbacks (run before the next render, so the page always shows the latest state)

def on_dismiss(step: int, reason: str) -> None:
    log("step_dismissed", "ae", step=step, reason=reason)


def on_action(step: int, action: str) -> None:
    log("step_action_taken", "ae", step=step, action=action)
    sent = events.list_events(deal_id, "nudge_sent")
    acted = events.list_events(deal_id, "nudge_acted_on")
    if sent and len(acted) < len(sent):
        log("nudge_acted_on", "ae", kind=sent[-1]["kind"])
    st.session_state["action_panel"] = (deal_id, step, action)


def on_expand(step: int) -> None:
    if st.session_state.get(f"why_{deal_id}_{step}"):
        log("step_expanded", "ae", step=step)


def on_outcome(outcome: str) -> None:
    msg = service.report_outcome(record, crm, outcome, now, "ae", notifier)
    st.session_state["outcome_msg"] = (outcome, msg)


# AE view

def checklist_view() -> None:
    st.subheader(f"Close the demo: {crm['account']}")
    st.caption(f"Demo in progress. Scheduled end {crm['demo']['scheduled_end'][11:16]}. Fill these before you "
               f"leave the call; each takes one line.")
    saved = record_store.load_checklist(deal_id)
    discovery = crm["discovery_notes"].get("stated_business_outcome", "")
    with st.form(f"checklist_{deal_id}"):
        values = {
            "dated_next_step": st.text_input(CHECKLIST_FIELDS["dated_next_step"], saved.get("dated_next_step", {}).get("value", ""),
                                             placeholder="For example: Thu Oct 8, 2pm, session with the COO"),
            "stakeholder_to_add": st.text_input(CHECKLIST_FIELDS["stakeholder_to_add"],
                                                saved.get("stakeholder_to_add", {}).get("value", ""),
                                                placeholder="Name and role"),
            "business_outcome": st.text_area(CHECKLIST_FIELDS["business_outcome"],
                                             saved.get("business_outcome", {}).get("value", discovery),
                                             help="Prefilled from discovery notes. Edit if the customer said it differently."),
            "sc_commitment": st.text_input(CHECKLIST_FIELDS["sc_commitment"], saved.get("sc_commitment", {}).get("value", ""),
                                           placeholder="What the SC promised, and by when"),
        }
        if st.form_submit_button("Save checklist"):
            if not events.list_events(deal_id, "demo_checklist_started"):
                log("demo_checklist_started", "ae")
            for field, value in values.items():
                if value.strip():
                    record_store.save_checklist_field(deal_id, field, value.strip(), now.isoformat())
            st.success("Saved.")
    filled = record_store.load_checklist(deal_id)
    st.caption(f"{len(filled)} of 4 filled.")
    if st.button("End demo and build the card", type="primary", disabled=record is None):
        for field, entry in filled.items():
            if datetime.fromisoformat(entry["filled_at"]) <= end:
                log("demo_checklist_filled_before_call_end", "ae", field=field)
        service.generate_card(deal_id, record, end, pv)
        st.rerun()
    if record is None:
        st.info("No debrief is available for this deal yet. See the README to generate one (make record), or start "
                "the app with sample cards (make demo).")


def step_card(i: int, step: dict, status: dict) -> None:
    lead = "Most important" if i == 0 else f"Step {i + 1}"
    done = status.get(i)
    with st.container(border=True):
        text = f"**{lead}:** {step['action']}"
        if done and done["status"] == "dismissed":
            text = f"~~{step['action']}~~  \nDismissed: {done['detail']}"
        elif done:
            text += "  \nDone: action taken"
        st.markdown(text)
        meta = [f"Owner: {step['owner']}", f"Due: {step['due_by'] or 'no date'}", f"Playbook {step['playbook_rule_id']}"]
        if step.get("release_card_id"):
            meta.append(f"Use {step['release_card_id']}")
        st.caption(" | ".join(meta))
        if st.toggle("Why this step", key=f"why_{deal_id}_{i}", on_change=on_expand, args=(i,)):
            st.markdown(step["why"])
            for ev in step.get("evidence", [])[:2]:
                q = transcript.render_quote(ev["utterance_id"])  # quote text comes from the transcript, not the model
                st.markdown(f"> {q['text']}\n>\n> {q['speaker']}, {q['title']}, at {q['timestamp']}")
        cols = st.columns([1.6, 1.1, 1.7, 1.1, 0.9])
        cols[0].button(blockkit.ACTION_LABELS.get(step["action_type"], "Open"), key=f"act_{deal_id}_{i}", type="primary",
                       disabled=bool(done), on_click=on_action, args=(i, step["action_type"]))
        for col, (key, label) in zip(cols[1:], events.DISMISS_REASONS.items()):
            col.button(label, key=f"dis_{deal_id}_{i}_{key}", disabled=bool(done), on_click=on_dismiss, args=(i, key))


def action_panel() -> None:
    panel = st.session_state.get("action_panel")
    if not panel or panel[0] != deal_id:
        return
    _, i, action = panel
    step = assessment()["next_steps"][i]
    with st.container(border=True):
        if action == "book_meeting":
            ex = record.get("extraction") or {}
            when = ex.get("agreed_next_step", {}).get("date") or step["due_by"] or "pick a date"
            contacts = ", ".join(c["name"] for c in crm["contacts"])
            st.markdown("**Invite draft (not sent)**")
            st.code(f"To: {contacts}\nWhen: {when}\nSubject: {crm['account']} and Apex: next step\n\n{step['action']}",
                    language=None)
        else:
            st.markdown(f"**Opened:** {step['action']}")
            st.caption("The drafts are in the tabs below. Nothing goes to the customer until you approve and send it.")


def recap_tab() -> None:
    art = record["artifacts"].get("recap_email") or {}
    cur = art.get("current")
    if art.get("refused"):
        st.error("The draft could not be written for this call (the request was declined). Write this one by hand.")
        return
    if not cur:
        st.error("No recap draft. " + art.get("error", ""))
        return
    blocked = bool(art.get("needs_review"))
    if blocked:
        st.error("Needs review before sending. Flagged:")
        for f in art.get("flagged", []):
            st.markdown(f"- :red[{f}]")
    elif art.get("regenerated"):
        st.caption("This draft was rewritten once after a check flagged the first version.")
        with st.expander("First version and what was flagged"):
            st.write(art.get("findings", []))
            st.text(art["original"]["body"])
    st.text_input("Subject", cur["subject"], key=f"subj_{deal_id}")
    edited = st.text_area("Email", cur["body"], height=320, key=f"body_{deal_id}")
    st.caption(f"Customer value line: {cur['customer_value_line']}")
    approved = bool(events.list_events(deal_id, "draft_approved"))
    sent = bool(events.list_events(deal_id, "draft_marked_sent"))
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Approve and copy", type="primary", disabled=blocked or approved, key=f"approve_{deal_id}"):
        ratio = events.edit_ratio(cur["body"], edited)
        if ratio > 0:
            log("draft_edited", "ae", artifact="recap_email", edit_ratio=ratio)
        log("draft_approved", "ae", artifact="recap_email", edit_ratio=ratio)
        st.session_state[f"approved_text_{deal_id}"] = edited
        st.rerun()
    if c2.button("Regenerate", key=f"regen_{deal_id}"):
        st.info("Regenerating is switched off in this demo, so the draft stays as it is. Edit it directly above.")
    if c3.button("Reject draft", key=f"reject_{deal_id}", disabled=approved):
        log("draft_rejected", "ae", artifact="recap_email")
        st.toast("Draft rejected. Write this one by hand.")
    if c4.button("Mark as sent", key=f"sent_{deal_id}", disabled=not approved or sent):
        text = st.session_state.get(f"approved_text_{deal_id}", edited)
        ratio = events.edit_ratio(cur["body"], text)
        log("draft_marked_sent", "ae", artifact="recap_email", edit_ratio=ratio)
        if ratio == 0:
            log("draft_sent_unedited", "ae", artifact="recap_email")
        st.rerun()
    if approved:
        st.code(st.session_state.get(f"approved_text_{deal_id}", edited), language=None)
        st.caption("Approved. Copy it into your email. " + ("Marked as sent." if sent else "Mark as sent once it goes out."))


def summary_tab() -> None:
    art = record["artifacts"].get("internal_summary") or {}
    s = art.get("current")
    if not s:
        st.error("No internal summary. " + art.get("error", ""))
        return
    if art.get("needs_review"):
        st.error("Needs review: " + "; ".join(art.get("flagged", [])))
    st.markdown(f"**{s['deal_state_line']}**  \n{s['customer_value_line']}")
    for key, label in [("what_we_validated", "What we validated"), ("integration_patterns", "Integration approach"),
                       ("objections_and_answers", "Objections and answers"), ("open_items", "Open items"),
                       ("commitments", "Commitments"), ("stakeholders", "Stakeholders"),
                       ("competitive_notes", "Competitive notes"), ("risks", "Risks")]:
        st.markdown(f"**{label}**")
        st.markdown("\n".join(f"- {x}" for x in s[key]) or "- None")


def map_tab() -> None:
    art = record["artifacts"].get("mutual_action_plan") or {}
    m = art.get("current")
    if not m:
        st.error("No action plan. " + art.get("error", ""))
        return
    st.caption(m["customer_value_line"])
    st.dataframe(pd.DataFrame([{"Milestone": r["milestone"], "Customer owner": r["customer_owner"],
                                "Apex owner": r["apex_owner"], "Target date": r["target_date"] or "to agree",
                                "Status": r["status"]} for r in m["rows"]]), hide_index=True, width="stretch")
    st.caption("Only rows the customer agreed to in the call, with a line from the transcript behind them, are marked agreed.")


def meddpicc_tab() -> None:
    med = record.get("meddpicc") or {}
    st.dataframe(pd.DataFrame([{"Field": k.replace("_", " "), "Status": v["status"], "What we know": v["summary"]}
                               for k, v in med.items()]), hide_index=True, width="stretch")
    st.caption("Built from the call record by fixed rules. Unknown fields are candidates for next steps.")


def checklist_tab() -> None:
    st.markdown("**Filled in this session**")
    filled = record_store.load_checklist(deal_id)
    for key, label in CHECKLIST_FIELDS.items():
        entry = filled.get(key)
        when = ""
        if entry:
            when = "before the call ended" if datetime.fromisoformat(entry["filled_at"]) <= end else "after the call"
        st.markdown(f"- {label}: {entry['value'] + ' (' + when + ')' if entry else 'not filled'}")
    st.markdown("**As logged in CRM for this call** (what the call record was checked against)")
    for key, label in CHECKLIST_FIELDS.items():
        st.markdown(f"- {label}: {crm['close_the_demo'][key]['value'] or 'blank'}")
    mismatches = (record.get("extraction") or {}).get("checklist_mismatches", [])
    if mismatches:
        st.markdown("**Mismatches with the call**")
        for m in mismatches:
            st.markdown(f"- {CHECKLIST_FIELDS.get(m['field'], m['field'])}: logged \"{m['logged_value'] or 'blank'}\", "
                        f"the call says: {m['transcript_says']}")


def ae_view() -> None:
    if not generated:
        checklist_view()
        return
    if not events.list_events(deal_id, "card_opened"):
        log("card_opened", "ae")
    service.tick_nudges(record, crm, activity, now, notifier)
    for m in messages_for("ae", deal_id)[:2]:
        st.warning(f"Reminder: {m['payload']['text']}")
    a = assessment()
    st.subheader(f"Debrief: {crm['account']}")
    st.markdown(f"**{blockkit.STATE_LABELS.get(a.get('deal_state'), a.get('deal_state', ''))}.** {a.get('deal_state_why', '')}")
    status = service.step_status(deal_id)
    for i, step in enumerate(a.get("next_steps", [])[:3]):
        step_card(i, step, status)
    if not a.get("next_steps"):
        st.caption("No steps cleared the bar for this call. That is on purpose: nothing generic is shown.")
    action_panel()
    if a.get("watch_items"):
        st.markdown("**Watch**\n" + "\n".join(f"- {w['summary']}" + (f" (use {w['release_card_id']})" if w["release_card_id"] else "")
                                              for w in a["watch_items"]))
    open_items = (record.get("extraction") or {}).get("open_technical_items", [])
    if open_items:
        st.markdown("**Open**\n" + "\n".join(f"- {o['summary']} (owner: {o['owner']})" for o in open_items))
    cost = record.get("cost_usd")
    st.caption(("Sample card: no cost" if cost is None else f"Cost for this debrief: ${cost:.4f}")
               + f" | Record saved | Source: {source}")
    payload = blockkit.card(record, transcript, crm)
    blockkit.save(payload)
    with st.expander("Slack card (Block Kit JSON, also saved to assets/ae_card_blockkit.json)"):
        st.json(payload, expanded=False)

    st.markdown("**How did this deal move?**")
    cols = st.columns(5)
    for col, (key, label) in zip(cols, [("advanced", "Mark advanced"), ("stalled", "Mark stalled"),
                                        ("closed_won", "Mark closed won"), ("closed_lost", "Mark closed lost")]):
        col.button(label, key=f"out_{deal_id}_{key}", on_click=on_outcome, args=(key,))
    if cols[4].button("Log a customer reply", key=f"reply_{deal_id}"):
        log("customer_reply_received", "ae")
        st.toast("Reply logged.")
    msg = st.session_state.get("outcome_msg")
    if msg:
        st.success(f"Status: {service.OUTCOMES[msg[0]]}." + (" The SC got a note about what mattered." if msg[1] else ""))

    tabs = st.tabs(["Recap email", "Internal summary", "Mutual action plan", "MEDDPICC", "Close-the-demo checklist"])
    with tabs[0]:
        recap_tab()
    with tabs[1]:
        summary_tab()
    with tabs[2]:
        map_tab()
    with tabs[3]:
        meddpicc_tab()
    with tabs[4]:
        checklist_tab()


# SC view

def sc_view() -> None:
    st.subheader(f"Call record: {crm['account']}")
    if not record:
        st.info("No record for this deal yet.")
    else:
        ex = record.get("extraction") or {}
        st.caption("This replaces the SC summary doc. Fix anything wrong, then confirm with one click.")
        orig_c = pd.DataFrame([{"Who": c["who"], "What": c["what"], "By when": c["by_when"]} for c in ex.get("commitments", [])])
        orig_o = pd.DataFrame([{"Open item": o["summary"], "Owner": o["owner"]} for o in ex.get("open_technical_items", [])])
        c = st.data_editor(orig_c, num_rows="dynamic", key=f"sc_c_{deal_id}", width="stretch", hide_index=True)
        o = st.data_editor(orig_o, num_rows="dynamic", key=f"sc_o_{deal_id}", width="stretch", hide_index=True)
        confirmed = bool(events.list_events(deal_id, "record_confirmed_by_sc"))
        if st.button("Confirm record", type="primary", disabled=confirmed):
            edits = int(not c.equals(orig_c)) + int(not o.equals(orig_o))
            events.log("record_confirmed_by_sc", "sc", deal_id, pv, ts=now.isoformat(), tables_edited=edits)
            st.rerun()
        if confirmed:
            st.success("Confirmed.")
        st.markdown("**Your commitments**")
        done = {e.get("commitment") for e in events.list_events(deal_id, "next_step_completed")}
        for item in service.sc_commitments(record, crm, deal_id):
            cols = st.columns([4, 1])
            cols[0].markdown(f"- {item['what']}" + (f" (due {item['due']})" if item["due"] else "") + (" , done" if item["what"] in done else ""))
            if cols[1].button("Mark done", key=f"done_{deal_id}_{item['what']}", disabled=item["what"] in done):
                events.log("next_step_completed", "sc", deal_id, pv, ts=now.isoformat(), commitment=item["what"])
                st.rerun()
    st.subheader("Close-the-loop inbox")
    msgs = messages_for("sc")
    if not msgs:
        st.caption("Nothing yet. When an AE marks a deal advanced or stalled, you get a note on what mattered.")
    for m in msgs:
        account = crm_source.deal(m["deal_id"])["account"]
        with st.container(border=True):
            st.caption(f"{account} | {m['kind'].replace('_', ' ')}")
            st.text(m["payload"]["text"])


# Sales manager view

def manager_view() -> None:
    service.mark_ignored_cards(now)
    rows = service.manager_rows(now)
    st.subheader("Recent TV demos")
    visible = ["Account", "AE", "Deal state", "Hours since demo", "Dated next step agreed in the call",
               "Customer replies", "Status", "Source"]
    st.dataframe(pd.DataFrame(rows)[visible], hide_index=True, width="stretch")
    st.caption(f"Hours are measured at the simulated time for the selected deal ({now:%a %b %d %H:%M}).")
    st.subheader("Coaching prompts")
    st.caption("Questions to ask in your next 1:1, one per deal. Not a scorecard.")
    for r in rows:
        st.markdown(f"- **{r['Account']}**: {service.coaching_prompt(r)}")
    for m in messages_for("manager")[:3]:
        st.warning(m["payload"]["text"])
    st.subheader("Touches in the 14 days after the demo (from the scenario packet)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Top quartile AEs", "2.3")
    c2.metric("Middle 50%", "1.1")
    c3.metric("Bottom quartile", "0.7")
    st.caption("Touch counts may reflect deal quality as much as rep behavior: weak deals get fewer touches and also "
               "lose. Use these to start a conversation, not to rank reps.")


# CSM view

def csm_view() -> None:
    won = [d for d in service.DEALS if record_store.deal_status(d) == "closed_won"]
    st.subheader("CS handoff brief")
    st.caption("Phase 2 preview. Built from what was captured at the TV demo.")
    if not won:
        st.info("No closed won deals yet. In the AE view, use Mark closed won.")
        return
    pick = st.selectbox("Closed won deal", won, format_func=lambda d: crm_source.deal(d)["account"])
    rec, _ = service.load_debrief(pick, allow_run=False)
    if not rec:
        st.info("No call record for this deal.")
        return
    key = f"viewed_{pick}"
    if not st.session_state.get(key):
        events.log("handoff_brief_viewed", "csm", pick, ts=now.isoformat())
        st.session_state[key] = True
    b = brief(rec, crm_source.deal(pick))
    st.markdown(f"### {b['account']}  \n*{b['label']}*")
    st.markdown(f"**Champion:** {b['champion']}  \n**Business outcome they stated:** {b['business_outcome']}")
    for key2, label in [("stakeholders", "Stakeholders"), ("objections_and_resolutions", "Objections and how they were resolved"),
                        ("open_technical_items", "Open technical items"), ("integration_patterns", "Integration approach"),
                        ("commitments", "Commitments made in the sale"), ("risks", "Risks"), ("meddpicc_gaps", "Gaps after TV"),
                        ("suggested_first_30_days", "Suggested first 30 days")]:
        st.markdown(f"**{label}**\n" + "\n".join(f"- {x}" for x in b[key2]))


# Measurement view

def measurement_view() -> None:
    st.subheader("Events logged in this session")
    ev = events.list_events()
    if ev:
        df = pd.DataFrame(ev)
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.caption("No events yet. Use the AE view to generate some.")

    st.subheader("Why steps were not acted on (this session)")
    counts = metrics.Counter(e["reason"] for e in ev if e["name"] == "step_dismissed")
    counts["card_unopened"] = sum(1 for d in service.DEALS if events.list_events(d, "card_generated")
                                  and not events.list_events(d, "card_opened"))
    st.dataframe(pd.DataFrame(metrics.diagnose(counts)), hide_index=True, width="stretch")
    st.caption(f"Pre-declared rule: a cause counts as real only if it explains at least "
               f"{int(metrics.CAUSE_RULE_SHARE * 100)}% of non-actions with at least {metrics.CAUSE_RULE_MIN_EVENTS} events. "
               f"A single session never meets it.")

    st.subheader("Synthetic example data: what the 30 day readout would look like")
    sim = metrics.simulate_events()
    st.caption("Synthetic example data from a seeded simulator. Not results.")
    st.dataframe(pd.DataFrame(metrics.diagnose(sim["signals"])), hide_index=True, width="stretch")
    cohort = metrics.touches_14d_by_cohort(sim["demos"])
    st.dataframe(pd.DataFrame([{"Cohort": k.replace("_", " "), "Baseline (packet)": v["baseline"],
                                "Synthetic example": v["current"], "Demos": v["n"]} for k, v in cohort.items()]),
                 hide_index=True, width="stretch")

    st.subheader("Decision table")
    st.caption("Thresholds are proposed, to agree with sales leadership. Current values are synthetic example data.")
    st.dataframe(pd.DataFrame([{"Metric": r["metric"], "Baseline": r["baseline"], "Scale if": r["scale_if"],
                                "Fix if": r["fix_if"], "Stop if": r["stop_if"],
                                "Current (synthetic example)": r["current_value"]}
                               for r in metrics.decision_table(sim["current"])]), hide_index=True, width="stretch")

    st.subheader("Metric definitions")
    for fn in [metrics.debrief_coverage, metrics.opened_within_24h, metrics.checklist_filled_before_end,
               metrics.recap_sent_within_24h, metrics.sc_confirmed_within_1bd, metrics.low_edit_send_rate,
               metrics.step_outcomes, metrics.diagnose, metrics.dated_next_step_within_2bd,
               metrics.recap_reply_rate_5bd, metrics.touches_14d_by_cohort, metrics.hours_to_first_touch,
               metrics.kaplan_meier, metrics.tv_days_by_arm, metrics.win_rate_by_tv_band]:
        st.markdown(f"- **{fn.__name__.replace('_', ' ')}**: {inspect.getdoc(fn)}")


VIEWS = {"AE": ae_view, "SC": sc_view, "Sales manager": manager_view, "CSM": csm_view, "Measurement": measurement_view}
VIEWS[role]()
