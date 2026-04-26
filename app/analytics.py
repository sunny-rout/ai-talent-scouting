"""
Analytics dashboard computation.
All KPI, chart, and table calculations live here — keeps the route handler thin.
"""
from __future__ import annotations

import json as _json
from app.models import ConversationResult, MatchResult
from app.state import AppState


def _interest_from_conv(state: AppState, candidate_id: str) -> float:
    conv = state.conversations.get(candidate_id)
    if not conv:
        return 0.0
    if isinstance(conv, ConversationResult):
        ia = conv.interest_analysis
        return getattr(ia, "total", 0.0) if ia else 0.0
    # Raw dict (restored from DB before upgrade)
    if isinstance(conv, dict):
        return conv.get("interest_analysis", {}).get("total", 0.0)
    return 0.0


def compute_analytics(state: AppState) -> dict:
    """
    Compute all analytics data for the dashboard.
    Returns a dict of template variables ready to be passed to Jinja2.
    """
    match_results = state.match_results
    conversations = state.conversations

    if not match_results:
        return {"no_data": True}

    # ── KPIs ──────────────────────────────────────────────────────────
    match_scores = [r.match_score for r in match_results]
    interest_scores = [_interest_from_conv(state, r.candidate.id) for r in match_results]
    engaged_ids = [cid for cid, c in conversations.items() if c]

    avg_match = round(sum(match_scores) / len(match_scores), 1)
    avg_interest = round(sum(interest_scores) / len(match_scores), 1)
    shortlisted = sum(1 for s in match_scores if s >= 70)

    # ── Score-bucket histogram (match scores) ─────────────────────────
    buckets = [0, 0, 0, 0, 0]  # 0-20, 21-40, 41-60, 61-80, 81-100
    for s in match_scores:
        buckets[min(int(s // 20), 4)] += 1

    # ── Tier breakdown (doughnut) ─────────────────────────────────────
    tiers = [0, 0, 0, 0]  # Excellent, Good, Fair, Low
    for s in match_scores:
        if s >= 80:
            tiers[0] += 1
        elif s >= 60:
            tiers[1] += 1
        elif s >= 40:
            tiers[2] += 1
        else:
            tiers[3] += 1

    # ── Scatter: match vs interest ────────────────────────────────────
    scatter = [
        {"x": round(r.match_score, 1),
         "y": round(_interest_from_conv(state, r.candidate.id), 1),
         "label": r.candidate.name}
        for r in match_results
    ]

    # ── Top skill gaps ────────────────────────────────────────────────
    gap_counts: dict[str, int] = {}
    for r in match_results:
        for g in (r.skill_gaps or []):
            gap_counts[g] = gap_counts.get(g, 0) + 1
    top_gaps = sorted(gap_counts.items(), key=lambda x: -x[1])[:8]

    # ── Funnel ────────────────────────────────────────────────────────
    funnel = [
        {"label": "Evaluated",     "count": len(match_results)},
        {"label": "Match ≥ 60%",   "count": sum(1 for s in match_scores if s >= 60)},
        {"label": "Engaged",       "count": len(engaged_ids)},
        {"label": "Interest ≥ 70", "count": sum(1 for s in interest_scores if s >= 70)},
        {"label": "Shortlisted",   "count": shortlisted},
    ]

    # ── Top candidates table ──────────────────────────────────────────
    top_candidates = sorted(
        [
            {
                "name":     r.candidate.name,
                "title":    r.candidate.title,
                "company":  r.candidate.company,
                "match":    round(r.match_score, 1),
                "interest": round(_interest_from_conv(state, r.candidate.id), 1),
                "combined": round(r.match_score * 0.6 + _interest_from_conv(state, r.candidate.id) * 0.4, 1),
                "engaged":  r.candidate.id in engaged_ids,
            }
            for r in match_results
        ],
        key=lambda x: -x["combined"]
    )[:10]

    return {
        "no_data":         False,
        "total":           len(match_results),
        "avg_match":       avg_match,
        "avg_interest":    avg_interest,
        "engaged_count":   len(engaged_ids),
        "shortlisted":     shortlisted,
        "bucket_data":     _json.dumps(buckets),
        "tier_data":       _json.dumps(tiers),
        "scatter_data":   _json.dumps(scatter),
        "gap_labels":      _json.dumps([g[0] for g in top_gaps]),
        "gap_counts":      _json.dumps([g[1] for g in top_gaps]),
        "funnel":          funnel,
        "top_candidates":  top_candidates,
    }