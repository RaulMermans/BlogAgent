import streamlit as st

from blogagent.tools.article_presentation import (
    get_publish_status_label,
    get_visible_article_markdown,
    is_evidence_report_article,
)
from blogagent.workflow.graph import run_pipeline, validate_final_state

st.set_page_config(page_title="BlogAgent", layout="wide")
st.title("BlogAgent")
st.caption(
    "Source-aware editorial agent. "
    "Mock mode is default — no API keys required. "
    "Optional Tavily search: set BLOGAGENT_SEARCH_PROVIDER=tavily + TAVILY_API_KEY. "
    "Optional LLM calls: set BLOGAGENT_LLM_PROVIDER=anthropic or openai + API key, "
    "and BLOGAGENT_USE_LLM_EDITOR=true and/or BLOGAGENT_USE_LLM_FACTCHECK=true. "
    "No external publishing available in MVP."
)

topic = st.text_input("Topic", placeholder="e.g. The history of the internet")
tone_label = st.selectbox(
    "Tone",
    [
        "Auto",
        "Editorial Magazine",
        "Practical Buying Guide",
        "Expert Analyst",
        "Personal Blog",
        "Luxury / Premium",
        "Luxury Editorial",
        "SEO Neutral",
        "SEO Practical",
        "Minimalist",
    ],
)
tone_ids = {
    "Auto": None,
    "Editorial Magazine": "editorial_magazine",
    "Practical Buying Guide": "practical_buying_guide",
    "Expert Analyst": "expert_analyst",
    "Personal Blog": "personal_blog",
    "Luxury / Premium": "luxury_premium",
    "Luxury Editorial": "luxury_editorial",
    "SEO Neutral": "seo_neutral",
    "SEO Practical": "seo_practical",
    "Minimalist": "minimalist",
}

if st.button("Run pipeline") and topic.strip():
    # Clear any results shown for a previous topic before starting a new run,
    # so a failed/blocked run never leaves a stale article or status visible.
    for key in ("last_run_state", "last_run_topic"):
        st.session_state.pop(key, None)

    with st.spinner("Running pipeline..."):
        state = run_pipeline(topic.strip(), tone_profile_id=tone_ids[tone_label])

    st.session_state["last_run_state"] = state
    st.session_state["last_run_topic"] = topic.strip()

if "last_run_state" in st.session_state:
    state = st.session_state["last_run_state"]
    errors = validate_final_state(state)

    if errors:
        st.error("Validation errors:\n" + "\n".join(f"- {e}" for e in errors))
    elif state.final_article_package:
        pkg = state.final_article_package
        visible_markdown = get_visible_article_markdown(pkg.article_markdown)
        status_label = get_publish_status_label(state.publish_ready_status, pkg.article_markdown)

        st.success(f"Pipeline complete. Run ID: `{pkg.run_id}`")
        if state.tone_profile:
            st.caption(f"Tone: {state.tone_profile.get('label', 'Auto')}")

        if is_evidence_report_article(pkg.article_markdown):
            st.info(f"Status: {status_label}")
        elif state.publish_ready_status == "publish_ready":
            st.success(f"Status: {status_label}")
        elif state.publish_ready_status == "publish_ready_with_editorial_review":
            st.warning(f"Status: {status_label}")
        else:
            st.error(f"Status: {status_label}")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Article")
            st.markdown(visible_markdown)

        with col2:
            with st.expander("Sources", expanded=True):
                for s in pkg.source_list:
                    st.write(f"- [{s.title}]({s.url}) — `{s.domain}`")

            with st.expander("Fact-Check Report"):
                report = pkg.fact_check_report
                st.metric("Total claims", report.total_claims)
                st.metric("Supported", report.supported_count)
                st.metric("Unsupported", report.unsupported_count)
                if report.blocking_issues:
                    st.error("\n".join(report.blocking_issues))

            with st.expander("Revision summary"):
                st.write(pkg.revision_summary)

            with st.expander("Debug / Raw JSON"):
                st.caption(f"Internal publish_ready_status: `{state.publish_ready_status}`")
                st.json(pkg.model_dump())
