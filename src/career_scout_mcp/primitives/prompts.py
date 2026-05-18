"""MCP prompts — user-invokable templates for guided LLM workflows.

Two prompts:

- tune_rubric            — aggregates recent tagged mismatches +
                           current rubric, returns a prompt asking the
                           LLM to suggest rubric refinements grounded
                           in specific cases.
- analyze_digest_trends  — fetches recent scoring history, returns a
                           prompt asking the LLM to identify patterns
                           backed by counts/percentages.

Design choices defended:

- Prompts return formatted strings, not list-of-messages. FastMCP
  supports both; the string form keeps the wire contract simple and
  lets the calling client compose conversation structure as it sees
  fit.

- Prompts pull live data at invocation time. They're not static
  templates — they query the DB for current mismatches and history, so
  the LLM sees actual state, not a stale snapshot embedded in the
  prompt at build time.

- Prompts do NOT call the LLM themselves. They produce text the MCP
  client uses to seed a conversation with whatever LLM it's configured
  against. Decoupled from scoring/client.py — clients can use Claude,
  GPT-4, or anything else for these workflows.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from career_scout_mcp.scoring.rubric import load_current_rubric
from career_scout_mcp.storage import queries


async def tune_rubric(limit: int = 20) -> str:
    """Produce a prompt asking the LLM to suggest rubric refinements.

    Aggregates the most recent N tagged mismatches and the current
    rubric, then asks the LLM to identify scoring-pattern problems and
    propose specific rubric language changes grounded in those cases.
    """
    rubric = load_current_rubric()
    mismatches = await queries.list_tagged_mismatches(limit=limit)

    if not mismatches:
        return (
            "No tagged mismatches recorded. Use the tag_mismatched_score "
            "tool to record cases where the AI's score does not match "
            "operator judgment, then re-invoke this prompt for "
            "refinement suggestions."
        )

    mismatch_block = "\n".join(
        f"- Posting {m.posting_id}: expected band {m.expected_band!r}. "
        f"Reason: {m.reason}"
        for m in mismatches
    )

    return (
        f"# Rubric Refinement Task\n\n"
        f"You are reviewing a scoring rubric used to assess job-posting "
        f"fit for a candidate. The operator has flagged {len(mismatches)} "
        f"recent scores as mismatches against their judgment. Your "
        f"task: identify what scoring patterns are systematically wrong "
        f"and propose specific rubric refinements.\n\n"
        f"## Current rubric ({rubric.version})\n\n"
        f"{rubric.text}\n\n"
        f"## Tagged mismatches\n\n"
        f"{mismatch_block}\n\n"
        f"## Output\n\n"
        f"For each pattern you identify across the mismatches:\n"
        f"1. Describe the pattern (1-2 sentences).\n"
        f"2. Quote the rubric section that produced the wrong scores.\n"
        f"3. Propose a specific rewording, scoring band shift, or new "
        f"criterion. Be concrete.\n\n"
        f"Do not propose generic 'be more careful' refinements. Each "
        f"suggestion must trace to specific mismatches above."
    )


async def analyze_digest_trends(limit: int = 100) -> str:
    """Produce a prompt asking the LLM to analyze scoring history trends."""
    scores = await queries.get_scores_history(limit=limit)

    if not scores:
        return (
            "No scoring history available. Score postings via the "
            "rescore_posting tool, then re-invoke this prompt for trend "
            "analysis."
        )

    score_block = "\n".join(
        f"- {s.scored_at} {s.posting_id} score={s.score} "
        f"band={s.score_band} (model={s.model}, rubric={s.rubric_version})"
        for s in scores
    )

    return (
        f"# Digest Trend Analysis Task\n\n"
        f"Analyze the last {len(scores)} scoring records and identify "
        f"trends across:\n"
        f"- Score distribution (how many high/mid/low, is it skewed?)\n"
        f"- Temporal patterns (trending higher or lower over time?)\n"
        f"- Model and rubric-version drift (do different model/rubric "
        f"combinations produce systematically different scores?)\n\n"
        f"## Scoring history\n\n"
        f"{score_block}\n\n"
        f"## Output\n\n"
        f"3-5 bullet points summarizing the most notable trends, each "
        f"backed by a specific count or percentage. Avoid vague claims "
        f"like 'scores are generally good' — every observation must be "
        f"grounded in the data above."
    )


def register_prompts(mcp: FastMCP) -> None:
    """Register all prompts on the given FastMCP instance."""
    mcp.prompt()(tune_rubric)
    mcp.prompt()(analyze_digest_trends)
