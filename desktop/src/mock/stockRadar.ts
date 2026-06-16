const mockStockRadarRun = {
  run_id: "radar_mock_20260608",
  mode: "dry_run",
  status: "completed",
  started_at: "2026-06-08T14:35:00+08:00",
  completed_at: "2026-06-08T14:36:00+08:00",
  summary: { candidate_count: 2, tier_counts: { alert: 1, watch: 1 }, docs_scanned: 18 },
  degraded_flags: ["llm_unavailable_rules_only", "late_session_volume_disabled", "rss_feeds_not_configured"],
  metadata: { no_trade_instructions: true }
};

const mockStockRadarCandidates = [
  {
    candidate_id: "radar_cand_mock_001",
    run_id: mockStockRadarRun.run_id,
    symbol: "300750",
    stock_name: "CATL",
    tier: "alert",
    radar_score: 84.5,
    event_id: "radar_evt_mock_001",
    event_type: "ai_compute_cooperation",
    direction: "positive",
    summary: "Official announcement matched AI compute cooperation keywords; source is Tier-A CNINFO.",
    source_doc_uids: ["cninfo:mock:001"],
    source_chain: [{ provider: "cninfo", source_tier: "tier_a", url: "https://static.cninfo.com.cn/finalpage/mock.pdf" }],
    extraction: { themes: ["AI", "compute"], confidence: 0.74, llm_status: "unavailable", status: "provisional" },
    confirmations: { late_session_volume: { status: "disabled" }, dragon_tiger: { status: "degraded" } },
    risk_flags: [],
    push_status: "pending"
  },
  {
    candidate_id: "radar_cand_mock_002",
    run_id: mockStockRadarRun.run_id,
    symbol: "600000",
    stock_name: "PF Bank",
    tier: "watch",
    radar_score: 66.0,
    event_id: "radar_evt_mock_002",
    event_type: "buyback",
    direction: "positive",
    summary: "Buyback announcement entered the observation pool; funding confirmation is unavailable.",
    source_doc_uids: ["cninfo:mock:002"],
    source_chain: [{ provider: "cninfo", source_tier: "tier_a", url: "https://static.cninfo.com.cn/finalpage/mock2.pdf" }],
    extraction: { themes: ["buyback"], confidence: 0.68, llm_status: "unavailable", status: "provisional" },
    confirmations: { fund_flow: { status: "degraded" }, late_session_volume: { status: "disabled" } },
    risk_flags: [],
    push_status: "pending"
  }
];

export function stockRadarPayload() {
  const digest = [
    "AIASK Stock Radar Digest",
    "run=radar_mock_20260608 status=completed",
    "300750 CATL 84.5 alert ai_compute_cooperation: Official announcement matched AI compute cooperation keywords",
    "600000 PF Bank 66 watch buyback: Buyback announcement entered the observation pool"
  ].join("\n");
  return {
    status: "completed",
    configured: true,
    latest_run: mockStockRadarRun,
    counts: { alert: 1, watch: 1 },
    candidates: mockStockRadarCandidates,
    digest_preview: digest,
    push_logs: [{ push_id: "radar_push_mock", channel: "preview", status: "preview", candidate_count: 2, created_at: "2026-06-08T14:36:10+08:00" }]
  };
}

export function stockRadarCandidatesPayload(filters: Record<string, unknown> = {}) {
  const tier = String(filters.tier || "");
  const candidates = tier ? mockStockRadarCandidates.filter((item) => item.tier === tier) : mockStockRadarCandidates;
  return { status: "ready", candidates, count: candidates.length };
}
