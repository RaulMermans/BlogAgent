from __future__ import annotations

import re
import time
import uuid

from blogagent.agents import editor_agent
from blogagent.observability.agentpulse_client import (
    AgentPulseClient,
    current_client,
    use_client,
    use_node,
)
from blogagent.tools.validators import (
    validate_article_package,
    validate_minimum_sources,
    validate_no_unsupported_high_importance_claims,
)
from blogagent.workflow.nodes import (
    _event,
    _propagate_llm_warnings,
    build_evidence_table,
    build_query_contract_node,
    check_external_effects,
    check_publish_contract_node,
    compute_publish_ready_status,
    evaluate_evidence_sufficiency_node,
    evaluate_publishability_node,
    evaluate_quality,
    extract_claims,
    extract_webpages,
    final_validate_quality,
    generate_outline,
    generate_research_questions,
    ground_article_recommendations,
    intake_topic,
    match_citations,
    package_article,
    revise_if_final_validation_failed,
    revise_if_needed,
    run_editorial_polish,
    run_enrichment_search,
    run_fact_check,
    run_web_search,
    score_source_quality,
    score_sources,
    select_skills,
    write_draft,
)
from blogagent.workflow.state import BlogRunState

_MAX_REVISIONS = 1


def _compute_execution_mode(state: BlogRunState) -> str:
    """Derive execution_mode from what providers actually ran.

    Rules:
      mock   — all actual_provider values are "mock" (no live provider succeeded)
      hybrid — at least one live provider succeeded AND at least one stage used mock
      live   — every stage that ran used a live provider; no mock fallback

    This is computed after the pipeline runs, not from env vars, so it reflects
    what actually happened rather than what was configured.
    """
    live_actual = False
    mock_actual = False

    for event in state.provider_events:
        if "actual_provider=" in event:
            # LLM stage event: "editor.research_plan: ... actual_provider=X ..."
            if "actual_provider=mock" in event:
                mock_actual = True
            else:
                live_actual = True
        elif event.startswith("search:"):
            # Search event: "search: provider=X, results=N"
            if "provider=mock" in event:
                mock_actual = True
            else:
                live_actual = True

    if not live_actual:
        return "mock"
    if mock_actual:
        return "hybrid"
    return "live"


# Deterministic pipeline steps run in order before the fact-check / revision cycle.
# run_fact_check is NOT in this list — it is called explicitly in run_pipeline so
# that tests can monkeypatch blogagent.workflow.graph.run_fact_check cleanly.
_PRE_FACTCHECK = [
    intake_topic,
    check_external_effects,  # guardrail — sets state.blocked; short-circuits if True
    build_query_contract_node,  # precise answer contract
    select_skills,  # deterministic skill selection based on intent
    generate_research_questions,
    run_web_search,
    extract_webpages,
    score_sources,
    score_source_quality,  # classify sources as high/medium/low
    build_evidence_table,
    evaluate_evidence_sufficiency_node,  # pre-draft evidence gate
    run_enrichment_search,  # optional second Tavily pass for recommendation topics
    generate_outline,
    write_draft,
    evaluate_quality,  # deterministic quality checks on draft
    revise_if_needed,  # quality-driven revision (at most once)
    final_validate_quality,  # post-revision quality gate
    revise_if_final_validation_failed,  # safety net: final validator can trigger one revision
    extract_claims,
    match_citations,
]


def run_pipeline(topic: str) -> BlogRunState:
    state = BlogRunState(topic=topic, run_id=str(uuid.uuid4()))
    telemetry = AgentPulseClient.from_env(run_id=state.run_id)
    # execution_mode starts as "mock" and is updated after the pipeline finishes.

    with use_client(telemetry):
        telemetry.start_run(
            input_summary=topic,
            metadata={"topic_length": len(topic), "execution_mode": "pending"},
        )
        try:
            for step in _PRE_FACTCHECK:
                state = _execute_step(state, step)
                if state.blocked:
                    state.execution_mode = _compute_execution_mode(
                        state
                    )  # type: ignore[assignment]
                    state.run_trace = [f"✗ Blocked: {state.block_reason[:120]}"]
                    telemetry.fail_run(
                        error=state.block_reason,
                        metadata={"blocked": True, "step": step.__name__},
                    )
                    return state

            # Initial fact-check.
            state = _execute_step(state, run_fact_check)

            # Revision loop — runs at most _MAX_REVISIONS times.
            if (
                state.fact_check_report is not None
                and not state.fact_check_report.passed
                and state.revision_count < _MAX_REVISIONS
            ):
                assert state.outline is not None
                node_id = "revise_article"
                client = current_client()
                if client:
                    client.node_started(node_id)
                t0 = time.monotonic()
                try:
                    with use_node(node_id):
                        llm_result = editor_agent.revise_article(
                            topic=state.topic,
                            draft=state.draft,
                            fact_check_report=state.fact_check_report,
                            citation_matches=state.citation_matches,
                        )
                    state.stage_timings[node_id] = round(time.monotonic() - t0, 3)
                    if client:
                        client.node_completed(
                            node_id,
                            latency_ms=_elapsed_ms(t0),
                            metadata={"blocked": state.blocked},
                        )
                except Exception as exc:  # noqa: BLE001
                    state.stage_timings[node_id] = round(time.monotonic() - t0, 3)
                    if client:
                        client.emit_event(
                            "node_failed",
                            node_id=node_id,
                            status="failed",
                            metadata={"error": f"{type(exc).__name__}: {exc}"},
                        )
                    raise
                from blogagent.workflow.nodes import _llm_event  # noqa: PLC0415

                if (
                    llm_result.is_mock
                    and llm_result.configured_provider != "mock"
                    and llm_result.error
                ):
                    state.revision_status = "failed_structured_output"
                    state.revision_summary = (
                        "Revision failed structured output; using original draft."
                    )
                    _event(state, _llm_event("editor.revision", llm_result))
                    _propagate_llm_warnings(state, "editor.revision", llm_result)
                else:
                    state.draft = llm_result.data.revised_markdown
                    state.revision_summary = llm_result.data.revision_summary
                    state.revision_count += 1
                    state.revision_status = "completed"

                    _event(state, _llm_event("editor.revision", llm_result))
                    _propagate_llm_warnings(state, "editor.revision", llm_result)

                    # Re-run claim extraction, citation matching, and fact-check post-revision.
                    state = _execute_step(state, extract_claims)
                    state = _execute_step(state, match_citations)
                    state = _execute_step(state, run_fact_check)

            # Publishability evaluation — runs after fact-check cycle.
            state = _execute_step(
                state,
                evaluate_publishability_node,
                timing_name="evaluate_publishability",
            )

            # Publish contract — deterministic final truth check before polish.
            state = _execute_step(
                state,
                check_publish_contract_node,
                timing_name="check_publish_contract",
            )

            # Editorial polish — runs at most once, when publishability or contract requires it.
            state = _execute_step(state, run_editorial_polish)

            # Post-article recommendation grounding — extracts and matches recommendations from
            # the final (polished) article text to source evidence.  Runs after polish so the
            # grounding proof reflects the final published text, not an intermediate draft.
            state = _execute_step(state, ground_article_recommendations)

            # Re-run contract after polish + grounding to reflect any improvements.
            state = _execute_step(
                state,
                check_publish_contract_node,
                timing_name="check_publish_contract_post_polish",
            )

            state = _execute_step(state, package_article)

            # Compute publish readiness status (uses publish contract as final authority).
            state = _execute_step(state, compute_publish_ready_status)

            # Compute execution_mode from what actually ran.
            state.execution_mode = _compute_execution_mode(state)  # type: ignore[assignment]

            # Build agent run trace for UI display.
            state.run_trace = _build_run_trace(state)

            _emit_final_observability(state)
            telemetry.complete_run(
                output_summary=state.publish_ready_status or "completed",
                metadata={
                    "execution_mode": state.execution_mode,
                    "blocked": state.blocked,
                    "revision_count": state.revision_count,
                    "source_count": len(state.source_scores),
                },
            )
            return state
        except Exception as exc:
            telemetry.fail_run(error=f"{type(exc).__name__}: {exc}")
            raise


def _execute_step(
    state: BlogRunState,
    step,
    *,
    timing_name: str | None = None,
) -> BlogRunState:
    node_id = timing_name or step.__name__
    client = current_client()
    if client:
        client.node_started(node_id, metadata={"step": step.__name__})
    t0 = time.monotonic()
    try:
        with use_node(node_id):
            new_state = step(state)
        new_state.stage_timings[node_id] = round(time.monotonic() - t0, 3)
        if client:
            client.node_completed(
                node_id,
                latency_ms=_elapsed_ms(t0),
                metadata={"blocked": new_state.blocked},
            )
        return new_state
    except Exception as exc:  # noqa: BLE001
        state.stage_timings[node_id] = round(time.monotonic() - t0, 3)
        if client:
            client.emit_event(
                "node_failed",
                node_id=node_id,
                status="failed",
                metadata={"step": step.__name__, "error": f"{type(exc).__name__}: {exc}"},
            )
        raise


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _emit_final_observability(state: BlogRunState) -> None:
    client = current_client()
    if client is None:
        return

    if state.evidence_sufficiency:
        client.eval_completed(
            "evidence_sufficiency",
            {
                "eval_name": "Evidence Sufficiency",
                "eval_type": "factuality",
                "passed": state.evidence_sufficiency.get("sufficient"),
                "score": state.evidence_sufficiency.get("score"),
                "findings": state.evidence_sufficiency.get("missing", []),
            },
        )
    if state.quality_evaluation:
        client.eval_completed(
            "quality_evaluation",
            {
                "eval_name": "Quality Evaluation",
                "eval_type": "quality",
                "passed": state.quality_evaluation.get("passes"),
                "score": state.quality_evaluation.get("score"),
                "findings": state.quality_evaluation.get("defects", []),
            },
        )
    if state.fact_check_report:
        client.eval_completed(
            "fact_check",
            {
                "eval_name": "Fact Check",
                "eval_type": "factuality",
                "passed": state.fact_check_report.passed,
                "score": None,
                "findings": state.fact_check_report.blocking_issues,
                "total_claims": state.fact_check_report.total_claims,
                "unsupported_count": state.fact_check_report.unsupported_count,
            },
        )
    if state.publishability_evaluation:
        client.eval_completed(
            "publishability",
            {
                "eval_name": "Publishability",
                "eval_type": "quality",
                "passed": state.publishability_evaluation.get("publish_ready"),
                "score": state.publishability_evaluation.get("score"),
                "findings": state.publishability_evaluation.get("defects", []),
            },
        )
    if state.publish_contract:
        client.eval_completed(
            "publish_contract",
            {
                "eval_name": "Publish Contract",
                "eval_type": "schema",
                "passed": state.publish_contract.get("passes"),
                "score": state.publish_contract.get("score_cap"),
                "findings": state.publish_contract.get("defects", []),
            },
        )
    if state.final_article_package:
        size = len(state.final_article_package.article_markdown.encode("utf-8"))
        client.artifact_created(
            {
                "artifact_type": "article_markdown",
                "artifact_ref": f"run:{state.run_id}:final_article",
                "artifact_size_bytes": size,
                "title": state.final_article_package.title,
            }
        )


def _build_run_trace(state: BlogRunState) -> list[str]:
    """Build a human-readable agent run trace from pipeline state."""
    trace: list[str] = []

    # Intent
    if state.is_recommendation:
        intent = "recommendation"
    elif state.is_financial:
        intent = "financial"
    else:
        intent = "factual"
    trace.append(f"✓ Intent: {intent}")

    # Requested count
    if state.requested_count is not None:
        trace.append(f"✓ Requested count: {state.requested_count}")

    if state.query_contract:
        qc = state.query_contract
        trace.append(
            "✓ Query contract: "
            f"{qc.get('task_type')} / {qc.get('domain')} / {qc.get('answer_entity_type')}"
        )

    # Skills
    if state.selected_skills:
        trace.append(f"✓ Skills: {', '.join(state.selected_skills)}")

    # Search
    search_event = next((e for e in state.provider_events if e.startswith("search:")), None)
    if search_event:
        trace.append(f"✓ {search_event}")

    # Source quality
    if state.source_quality_scores:
        high = sum(1 for s in state.source_quality_scores if s.get("quality") == "high")
        medium = sum(1 for s in state.source_quality_scores if s.get("quality") == "medium")
        low = sum(1 for s in state.source_quality_scores if s.get("quality") == "low")
        trace.append(f"✓ Source quality: {high} high, {medium} medium, {low} low")

    # Draft provider
    draft_event = next((e for e in state.provider_events if "editor.draft" in e), None)
    if draft_event:
        m = re.search(r"actual_provider=(\S+)", draft_event)
        provider_name = m.group(1) if m else "unknown"
        is_fallback = "fallback=true" in draft_event
        if is_fallback:
            trace.append("⚠ Draft fallback: mock (live provider unavailable)")
        else:
            completed_fields = "structured_output_completed_missing_fields" in draft_event
            note = " (metadata synthesised from article)" if completed_fields else ""
            trace.append(f"✓ Draft: {provider_name}{note}")

    # Quality evaluation
    if state.quality_evaluation:
        ev = state.quality_evaluation
        symbol = "✓" if ev.get("passes") else "⚠"
        defect_count = len(ev.get("defects", []))
        top_n_defects = [d for d in ev.get("defects", []) if d.get("type") == "top_n_mismatch"]
        detail = ""
        if top_n_defects:
            detail = ", top-N mismatch"
        elif defect_count:
            detail = f", {defect_count} defect(s)"
        trace.append(
            f"{symbol} Quality evaluator: score={ev.get('score', 0)}/100 "
            f"{'passed' if ev.get('passes') else 'failed'}{detail}"
        )

    # Revision — match only actual revision event prefixes, not quality_eval events
    # that happen to contain "revision" (e.g. "revision_required=False").
    revision_events = [
        e
        for e in state.provider_events
        if (
            "editor.quality_revision:" in e
            or "editor.revision:" in e
            or "editor.final_validation_revision:" in e
        )
    ]

    if revision_events:
        last_rev = revision_events[-1]
        m_rev = re.search(r"actual_provider=(\S+)", last_rev)
        rev_provider = m_rev.group(1) if m_rev else "mock"
        summary = (state.revision_summary or "").lower()
        if "fallback=true" in last_rev and (
            "json parse failed" in last_rev.lower()
            or "structured output" in summary
            or state.revision_status == "failed_structured_output"
        ):
            trace.append("⚠ Revision: failed structured output — using original draft")
        elif "fallback=true" in last_rev and rev_provider == "mock":
            trace.append("⚠ Revision: fallback to mock — unresolved defects may remain")
        else:

            if "editor.final_validation_revision:" in last_rev:
                rev_trigger = "triggered by final validator"
            else:
                rev_trigger = "triggered by quality evaluator"

            evidence_keywords = ("limit", "support", "count")
            if "evidence" in summary and any(k in summary for k in evidence_keywords):
                trace.append(
                    "✓ Revision: completed — reduced count due to evidence limits "
                    f"({rev_trigger})"
                )
            elif any(kw in summary for kw in ("top_n", "top-n", "count", "recommendation")):
                trace.append(
                    f"✓ Revision: completed — fixed top-N mismatch ({rev_trigger})"
                )
            else:
                trace.append(f"✓ Revision: completed — {rev_provider} ({rev_trigger})")

        if state.final_validation_status == "failed":
            trace.append(
                "⚠ Revision: completed but final validation still found unresolved issues"
            )
    elif state.revision_count == 0:
        qe = state.quality_evaluation or {}
        if qe.get("revision_required"):
            trace.append("⚠ Revision: skipped — revision limit already reached")
        else:
            trace.append(
                "✓ Revision: skipped — quality evaluator passed and final validation passed"
            )
    else:
        # revision_count > 0 but no matching event (edge case)
        trace.append(f"✓ Revision: completed (x{state.revision_count})")

    # Final validation
    fv_status = state.final_validation_status or "passed"
    if fv_status == "failed":
        high_defects = [
            d for d in state.final_validation_defects if d.get("severity") == "high"
        ]
        defect_msgs = "; ".join(d.get("type", "?") for d in high_defects[:2])
        trace.append(
            f"⚠ Final validation: failed — {defect_msgs or 'high-severity issues remain'}"
        )
        trace.append("⚠ Generated with unresolved quality issues.")
    elif fv_status == "passed_with_warnings":
        if state.evidence_limited_count_accepted:
            trace.append("⚠ Final validation: passed with evidence-limited count")
        else:
            trace.append("⚠ Final validation: passed with warnings")
    else:
        trace.append("✓ Final validation: passed")

    # Candidate ledger quality
    if state.is_recommendation and state.entity_candidate_ledger:
        ledger = state.entity_candidate_ledger
        ledger_quality = ledger.get("table_quality", "")
        ledger_usable = ledger.get("usable_count", 0)
        ledger_rejected = ledger.get("rejected_count", 0)
        requested_c = state.requested_count
        if ledger_quality == "strong":
            trace.append(
                f"✓ Candidate ledger: strong — {ledger_usable} usable"
                + (f" / {requested_c} requested" if requested_c else "")
            )
        elif ledger_quality == "limited":
            trace.append(
                f"⚠ Candidate ledger: limited — {ledger_usable} usable"
                + (f" / {requested_c} requested" if requested_c else "")
                + f", {ledger_rejected} rejected"
            )
        elif ledger_quality == "failed":
            issues = ledger.get("quality_issues", [])
            issue_str = issues[0] if issues else "quality gate failed"
            trace.append(
                f"⚠ Candidate ledger: failed — {issue_str[:80]}"
            )

    # Draft candidate compliance
    if state.is_recommendation and state.draft_candidate_compliance:
        dc = state.draft_candidate_compliance
        allowed_c = dc.get("allowed_count", 0)
        recommended_c = dc.get("recommended_count", 0)
        requested_c = state.requested_count
        if dc.get("passes"):
            trace.append(
                f"✓ Draft compliance: {recommended_c}/{requested_c or allowed_c} "
                "allowed candidates used"
            )
        else:
            trace.append(
                f"⚠ Draft compliance: failed — article used {recommended_c}"
                + (f"/{requested_c}" if requested_c else "")
                + f" required candidates (allowed={allowed_c})"
            )

    # Answer count snapshot
    if state.is_recommendation and state.answer_count_snapshot:
        snap = state.answer_count_snapshot
        snap_status = snap.get("count_status", "")
        snap_requested = snap.get("requested_count")
        snap_allowed = snap.get("allowed_candidates_count", 0)
        snap_article = snap.get("article_entities_count", 0)
        snap_grounded = snap.get("grounded_entities_count", 0)
        if snap_status == "satisfied":
            trace.append(
                f"✓ Count status: satisfied — {snap_article}/{snap_requested or snap_allowed} "
                f"(grounded={snap_grounded})"
            )
        elif snap_status == "evidence_limited":
            trace.append(
                f"⚠ Count status: evidence_limited — {snap_article} of "
                f"{snap_requested} requested (allowed={snap_allowed})"
            )
        elif snap_status == "failed":
            failure_reason = snap.get("failure_reason", "count mismatch")
            if "draft_candidate_compliance" in (failure_reason or ""):
                trace.append(
                    f"⚠ Count status: failed — draft_candidate_compliance_failed "
                    f"({snap_allowed} allowed, {snap_article} in article, "
                    f"{snap_requested} requested)"
                )
            else:
                trace.append(
                    f"⚠ Count status: failed — {snap_article}/{snap_requested} "
                    f"(allowed={snap_allowed})"
                )

    # Recommendation grounding (post-article)
    if state.is_recommendation and state.recommendation_candidates_summary:
        cs = state.recommendation_candidates_summary
        article_count = cs.get("article_recommendations_count")
        grounded_count = cs.get("grounded_recommendations_count")
        usable = cs.get("usable_count", 0)
        unmatched = cs.get("unmatched_names", [])
        requested = state.requested_count

        validated_count = len(state.validated_candidates)
        if requested is not None:
            if validated_count >= requested:
                trace.append(f"✓ Validated candidates: {validated_count} usable")
            else:
                trace.append(
                    f"⚠ Validated candidates: {validated_count}/{requested} usable"
                    + (" — evidence-limited" if state.evidence_limited_mode else "")
                )

        if article_count is not None:
            # Post-article grounding data is available
            if grounded_count == article_count and article_count > 0:
                trace.append(
                    f"✓ Article recommendations: {article_count} detected, "
                    f"{grounded_count} grounded in source evidence"
                )
            elif article_count > 0:
                trace.append(
                    f"⚠ Article recommendations: {article_count} detected, "
                    f"{grounded_count} grounded, {len(unmatched)} unsupported"
                )
                if unmatched:
                    trace.append(
                        f"⚠ Unsupported recommendations: {', '.join(unmatched[:3])}"
                    )
            else:
                trace.append("⚠ Article recommendations: none detected in final article")

            if requested is not None:
                symbol = "✓" if usable >= requested else "⚠"
                trace.append(f"{symbol} Usable recommendations: {usable}/{requested}")
        else:
            # Only pre-draft evidence candidates available
            if requested is not None:
                symbol = "✓" if usable >= requested else "⚠"
                trace.append(
                    f"{symbol} Usable recommendations (evidence): {usable}/{requested}"
                )
            else:
                trace.append(f"✓ Usable recommendations (evidence): {usable}")

    if state.recommendation_audit:
        audit = state.recommendation_audit
        article = audit.get("article_recommendations_count", 0)
        grounded = audit.get("grounded_recommendations_count", 0)
        unsupported = audit.get("unsupported_recommendations", [])
        section_false = audit.get("section_heading_false_positives", [])
        if audit.get("passes"):
            trace.append(
                f"✓ Article audit: {article} article recommendations, "
                f"{grounded} allowed, 0 unsupported"
            )
        else:
            trace.append(
                f"⚠ Article audit: {article} article recommendations, "
                f"{grounded} allowed, {len(unsupported)} unsupported"
            )
            if section_false:
                trace.append(
                    "⚠ Article audit: rejected section heading false positive: "
                    f"{section_false[0]}"
                )

    # Evidence sufficiency
    if state.evidence_sufficiency:
        es = state.evidence_sufficiency
        action = es.get("recommended_action", "proceed")
        supported = es.get("supported_count", 0)
        requested = es.get("requested_count")
        if action == "evidence_limited":
            trace.append(
                f"⚠ Evidence sufficiency: limited, {supported}"
                + (f"/{requested}" if requested else "")
                + " usable recommendations"
            )
        elif action == "search_more" or state.search_pass_count > 1:
            trace.append(
                f"✓ Evidence sufficiency: enriched — {supported}"
                + (f"/{requested}" if requested else "")
                + " usable recommendations"
            )
        else:
            trace.append(f"✓ Evidence sufficiency: {es.get('score', 0)}/100")

    # Enrichment search
    if state.search_pass_count > 1:
        enrichment_event = next(
            (e for e in state.provider_events if e.startswith("enrichment_search:")), None
        )
        if enrichment_event:
            import re as _re  # noqa: PLC0415

            m = _re.search(r"new_sources=(\d+)", enrichment_event)
            new_srcs = m.group(1) if m else "?"
            trace.append(
                f"✓ Enrichment search: {len(state.enrichment_queries)} queries, "
                f"+{new_srcs} sources"
            )

    # Publishability evaluation
    if state.publishability_evaluation:
        pe = state.publishability_evaluation
        score = pe.get("score", 0)
        polish = pe.get("polish_required", False)
        symbol = "✓" if pe.get("publish_ready") else "⚠"
        trace.append(
            f"{symbol} Publishability: {score}/100" + (", polish needed" if polish else "")
        )

    # Publish contract
    if state.publish_contract:
        pc = state.publish_contract
        contract_status = pc.get("status", "")
        n_defects = len(pc.get("defects", []))
        score_cap = pc.get("score_cap")
        cap_note = f" (score capped at {score_cap})" if score_cap else ""
        if contract_status == "publish_ready":
            trace.append(f"✓ Publish contract: passed{cap_note}")
        elif contract_status == "publish_ready_with_warnings":
            trace.append(
                "⚠ Publish contract: publish_ready_with_warnings — "
                f"{n_defects} issue(s){cap_note}"
            )
        else:
            trace.append(
                "⚠ Publish contract: draft_only_not_publish_ready — "
                f"{n_defects} issue(s){cap_note}"
            )

    # Editorial polish
    if state.polish_summary:
        trace.append("✓ Editorial polish: completed")
    elif state.publishability_evaluation and state.publishability_evaluation.get("polish_required"):
        trace.append("⚠ Editorial polish: skipped (mock mode — no LLM configured)")

    # Final publish status
    pub_status = state.publish_ready_status
    if pub_status == "publish_ready":
        trace.append("✓ Final status: publish_ready")
    elif pub_status == "publish_ready_with_warnings":
        trace.append("⚠ Final status: publish_ready_with_warnings")
    elif pub_status == "draft_only_not_publish_ready":
        trace.append("⚠ Final status: draft_only_not_publish_ready")

    # Packaged
    trace.append("✓ Packaged article")

    return trace


def validate_final_state(state: BlogRunState) -> list[str]:
    if state.final_article_package is None:
        return ["final_article_package is None"]
    pkg = state.final_article_package
    errors: list[str] = []
    errors.extend(validate_article_package(pkg))
    errors.extend(validate_minimum_sources(pkg))
    errors.extend(validate_no_unsupported_high_importance_claims(pkg))
    return errors
