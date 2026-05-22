

def _render_report_html(
    *,
    target: dict[str, Any],
    summary_card: dict[str, Any],
    sections: list[dict[str, Any]],
    perspective_cards: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> str:
    bullet_items = "".join(f"<li>{escape(str(item))}</li>" for item in list(summary_card.get("bullets") or []))
    section_html = "".join(
        (
            f"<section class='section'>"
            f"<h2>{escape(str(section.get('title') or ''))}</h2>"
            f"<p>{escape(str(section.get('narrative') or ''))}</p>"
            f"<div class='evidence'>Evidence: {escape(', '.join(str(item) for item in list(section.get('evidence_ids') or [])))}</div>"
            f"</section>"
        )
        for section in sections
    )
    cards_html = "".join(
        (
            "<div class='card'>"
            f"<h3>{escape(str(card.get('title') or ''))}</h3>"
            f"<strong>{escape(str(card.get('value') or '-'))}</strong>"
            f"<p>{escape(str(card.get('note') or ''))}</p>"
            "</div>"
        )
        for card in perspective_cards
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8' />"
        f"<title>{escape(str(target.get('name') or target.get('code') or 'Stock Analysis'))}</title>"
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f7fb;color:#0f172a;"
        "margin:0;padding:36px;} .wrap{max-width:1120px;margin:0 auto;} .hero{padding:28px;border-radius:24px;"
        "background:linear-gradient(135deg,#fef7ed,#eff6ff);box-shadow:0 16px 48px rgba(15,23,42,.08);} h1{margin:0 0 8px;"
        "font-size:34px;} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin:22px 0;}"
        ".card,.section{background:#fff;border:1px solid rgba(148,163,184,.18);border-radius:20px;padding:18px;"
        "box-shadow:0 12px 36px rgba(15,23,42,.06);} .sections{display:grid;gap:16px;margin-top:18px;} .evidence{margin-top:10px;"
        "font-size:12px;color:#475569;} ul{margin:10px 0 0 18px;} .manifest{margin-top:18px;font-size:12px;color:#475569;}"
        "</style></head><body><div class='wrap'><div class='hero'>"
        f"<div class='eyebrow'>{escape(str(target.get('code') or ''))} / 机构风格个股分析</div>"
        f"<h1>{escape(str(target.get('name') or target.get('code') or ''))}</h1>"
        f"<p>{escape(str(summary_card.get('subtitle') or ''))}</p>"
        f"<ul>{bullet_items}</ul>"
        "</div><div class='grid'>"
        f"{cards_html}</div><div class='sections'>{section_html}</div>"
        f"<div class='manifest'>Manifest: {escape(str(manifest))}</div>"
        "</div></body></html>"
    )


def _build_report_bundle(
    assembled: dict[str, Any],
    synthesis: dict[str, Any],
    gap_report: dict[str, Any],
    artifact_ids: dict[str, str],
    *,
    status: str,
) -> dict[str, Any]:
    target = dict(assembled.get("target") or {})
    perspective_cards = _perspective_cards(assembled, gap_report)
    summary_card = _build_summary_card(assembled, synthesis, gap_report)
    manifest = _build_manifest(
        run_id=str(assembled.get("run_id") or ""),
        code=str(target.get("code") or ""),
        task=str(synthesis.get("task") or ""),
        status=status,
        artifact_ids=artifact_ids,
        gap_report=gap_report,
    )
    standalone_html = _render_report_html(
        target=target,
        summary_card=summary_card,
        sections=list(synthesis.get("sections") or []),
        perspective_cards=perspective_cards,
        manifest=manifest,
    )
    return {
        "run_id": assembled.get("run_id"),
        "code": target.get("code"),
        "task": synthesis.get("task"),
        "summary_card": summary_card,
        "one_paragraph_digest": synthesis.get("digest"),
        "perspective_cards": perspective_cards,
        "sections": list(synthesis.get("sections") or []),
        "standalone_html": standalone_html,
        "manifest": manifest,
    }


def _orchestrated_summary(
    *,
    run_id: str,
    task: str,
    status: str,
    assembled: dict[str, Any],
    stages: list[dict[str, Any]],
    evidence_pack: dict[str, Any] | None,
    gap_report: dict[str, Any] | None,
    agent_review: dict[str, Any] | None,
    synthesis: dict[str, Any] | None,
    report_bundle: dict[str, Any] | None,
    artifact_ids: dict[str, str],
    trade_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_stage = next((stage["stage"] for stage in reversed(stages) if stage.get("status")), "requested")
    target = dict(assembled.get("target") or {})
    result = {
        "task": task,
        "status": status,
        "steps": stages,
        "summary": {
            "run_id": run_id,
            "code": target.get("code"),
            "name": target.get("name") or assembled.get("name"),
            "market": assembled.get("market", "cn"),
            "current_stage": current_stage,
            "report_ready": bool(report_bundle),
            "digest": (report_bundle or {}).get("one_paragraph_digest") or (synthesis or {}).get("digest"),
            "gap_count": len(list((gap_report or {}).get("critical_missing") or []))
            + len(list((gap_report or {}).get("non_critical_missing") or [])),
            "artifact_ids": artifact_ids,
            "resource_uris": {
                "latest_stock": f"resource://stock/{target.get('code')}/deep-analysis" if target.get("code") else None,
                "summary": f"resource://analysis-run/{run_id}/summary",
                "report": f"resource://analysis-run/{run_id}/report",
            },
            "updated_at": _utcnow_iso(),
        },
        "run_id": run_id,
        "code": target.get("code"),
        "name": target.get("name") or assembled.get("name"),
        "market": assembled.get("market", "cn"),
        "analysis_input": assembled,
        "analysis_evidence": evidence_pack,
        "analysis_gap_report": gap_report,
        "analysis_agent_review": agent_review,
        "analysis_synthesis": synthesis,
        "analysis_report_bundle": report_bundle,
        "trade_plan": trade_plan,
    }
    return result


async def _rebuild_report_from_artifacts(run_id: str) -> dict[str, Any]:
    summary_artifact, input_artifact, gap_artifact, synthesis_artifact = await asyncio.gather(
        get_artifact_async(run_id),
        get_artifact_async(_artifact_id(run_id, "input")),
        get_artifact_async(_artifact_id(run_id, "gaps")),
        get_artifact_async(_artifact_id(run_id, "synthesis")),
    )
    if not summary_artifact or not input_artifact or not synthesis_artifact:
        raise ValueError(f"missing rebuild prerequisites for run_id={run_id}")

    assembled = dict(input_artifact.get("payload") or {})
    gap_report = dict((gap_artifact or {}).get("payload") or {})
    synthesis = dict(synthesis_artifact.get("payload") or {})
    artifact_ids = {
        "run": run_id,
        "input": _artifact_id(run_id, "input"),
        "gaps": _artifact_id(run_id, "gaps"),
        "synthesis": _artifact_id(run_id, "synthesis"),
        "report": _artifact_id(run_id, "report"),
    }
    report_bundle = _build_report_bundle(
        assembled,
        synthesis,
        gap_report,
        artifact_ids,
        status="completed",
    )
    await _persist_artifact(
        artifact_id=_artifact_id(run_id, "report"),
        artifact_type="analysis_report_bundle",
        code=str(assembled.get("code") or ""),
        run_id=run_id,
        task=str(assembled.get("task") or "rebuild_report"),
        payload=report_bundle,
    )
    summary_payload = dict(summary_artifact.get("payload") or {})
    summary_payload["analysis_report_bundle"] = report_bundle
    summary_payload["summary"] = dict(summary_payload.get("summary") or {})
    summary_payload["summary"]["report_ready"] = True
    summary_payload["summary"]["updated_at"] = _utcnow_iso()
    await _persist_artifact(
        artifact_id=run_id,
        artifact_type="analysis_run_summary",
        code=str(assembled.get("code") or ""),
        run_id=run_id,
        task=str(assembled.get("task") or "rebuild_report"),
        payload=summary_payload,
    )
    return summary_payload
