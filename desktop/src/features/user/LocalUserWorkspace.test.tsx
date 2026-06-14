import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetMockApiState } from "../../mockApi";
import { AiaskApi } from "../../services/aiaskApi";
import { LocalUserWorkspace } from "./LocalUserWorkspace";

const props = {
  endpoint: "mock://aiask",
  apiToken: "test-token",
  controlToken: "mock-control-token",
  userId: "local",
  profileName: "Local Operator",
  onProfileChange: vi.fn()
};

async function seedUserAudit() {
  const api = new AiaskApi({
    endpoint: props.endpoint,
    apiToken: props.apiToken,
    controlToken: props.controlToken
  });
  await api.recordEvents({
    user_id: "local",
    session_id: "sess_mock",
    page_key: "workbench",
    route: "/workbench",
    event_type: "page_view",
    payload: { api_key: "secret", safe: "ok" }
  });
  await api.recordFeedback({
    user_id: "local",
    session_id: "sess_mock",
    target_type: "page",
    target_id: "workbench",
    feedback_type: "thumbs_up",
    rating: 5,
    allow_learning: true
  });
  await api.userDataPolicySave("local", { allow_learning: true });
  await api.callTool("agent_tool_catalog", { user_id: "local", session_id: "sess_mock", token: "secret" });
}

describe("LocalUserWorkspace", () => {
  afterEach(() => {
    cleanup();
    resetMockApiState();
    vi.clearAllMocks();
  });

  it("renders user activity, policy, analytics, and learning panels", async () => {
    await seedUserAudit();

    render(<LocalUserWorkspace {...props} />);

    await waitFor(() => expect(screen.getAllByText("page_view").length).toBeGreaterThan(0));
    expect(screen.getByRole("heading", { name: "Activity Audit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tool Audit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Data Policy" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Feedback" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analytics Summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recommendations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Export And Delete" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Retention And Learning" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Privacy Aggregates" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Audit Posture" })).toBeInTheDocument();
    expect(screen.getAllByText("agent_tool_catalog").length).toBeGreaterThan(0);
    expect(screen.getAllByText("thumbs_up").length).toBeGreaterThan(0);
  });

  it("previews export/delete and aggregate governance without destructive actions", async () => {
    await seedUserAudit();
    render(<LocalUserWorkspace {...props} />);

    await waitFor(() => expect(screen.getAllByText("agent_tool_catalog").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Preview Export/Delete" }));
    await waitFor(() => expect(screen.getByText("USER_DATA_EXPORT_PREVIEWED")).toBeInTheDocument());
    expect(screen.getByText("Export/Delete JSON")).toBeInTheDocument();
    expect(screen.getByText("Retention/Learning JSON")).toBeInTheDocument();
    expect(screen.getAllByText("true").length).toBeGreaterThan(0);
    expect(screen.getAllByText("false").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Preview Aggregate Governance" }));
    await waitFor(() => expect(screen.getByText("AGGREGATE_GOVERNANCE_PREVIEWED")).toBeInTheDocument());
    expect(screen.getByText("Aggregate Governance JSON")).toBeInTheDocument();
    expect(screen.getAllByText("aggregate").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench").length).toBeGreaterThan(0);
  });

  it("updates policy and refreshes learning eligibility", async () => {
    await seedUserAudit();
    render(<LocalUserWorkspace {...props} />);

    const learningCheckbox = await screen.findByLabelText("Learning use");
    expect(learningCheckbox).toBeChecked();

    fireEvent.click(learningCheckbox);
    await waitFor(() => expect(screen.getByText("USER_DATA_POLICY_SAVED")).toBeInTheDocument());
    expect(learningCheckbox).not.toBeChecked();
  });
});
