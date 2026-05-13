from __future__ import annotations

from blogagent.workflow.state import ArticlePackage, CitationStatus, ClaimImportance


def validate_article_package(package: ArticlePackage) -> list[str]:
    errors: list[str] = []
    if not package.article_markdown.strip():
        errors.append("article_markdown is empty")
    if not package.source_list:
        errors.append("source_list is empty")
    if package.fact_check_report is None:
        errors.append("fact_check_report is missing")
    if not package.revision_summary.strip():
        errors.append("revision_summary is empty")
    if not package.title.strip():
        errors.append("title is empty")
    if not package.slug.strip():
        errors.append("slug is empty")
    return errors


def validate_minimum_sources(package: ArticlePackage, minimum: int = 3) -> list[str]:
    count = len(package.source_list)
    if count < minimum:
        return [f"source_list has {count} sources; minimum is {minimum}"]
    return []


def validate_no_unsupported_high_importance_claims(package: ArticlePackage) -> list[str]:
    errors: list[str] = []
    for match in package.claim_support_statuses:
        if (
            match.claim.importance == ClaimImportance.high
            and match.status == CitationStatus.unsupported
        ):
            errors.append(f"Unsupported high-importance claim: {match.claim.text!r}")
    return errors
