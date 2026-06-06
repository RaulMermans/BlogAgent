import streamlit as st

from blogagent.workflow.graph import run_pipeline, validate_final_state

st.set_page_config(page_title="BlogAgent", layout="wide")
st.title("BlogAgent")
st.caption(
    "Source-grounded editorial agent. "
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
        "SEO Neutral",
    ],
)
tone_ids = {
    "Auto": None,
    "Editorial Magazine": "editorial_magazine",
    "Practical Buying Guide": "practical_buying_guide",
    "Expert Analyst": "expert_analyst",
    "Personal Blog": "personal_blog",
    "Luxury / Premium": "luxury_premium",
    "SEO Neutral": "seo_neutral",
}

if st.button("Run pipeline") and topic.strip():
    with st.spinner("Running pipeline..."):
        state = run_pipeline(topic.strip(), tone_profile_id=tone_ids[tone_label])

    errors = validate_final_state(state)

    if errors:
        st.error("Validation errors:\n" + "\n".join(f"- {e}" for e in errors))
    elif state.final_article_package:
        pkg = state.final_article_package
        st.success(f"Pipeline complete. Run ID: `{pkg.run_id}`")
        if state.tone_profile:
            st.caption(f"Tone: {state.tone_profile.get('label', 'Auto')}")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Article")
            st.markdown(pkg.article_markdown)

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

            with st.expander("Raw JSON"):
                st.json(pkg.model_dump())
