import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PageShell, PageShellGrid, PageShellList } from "./PageShell";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PageShell", () => {
  it("renders page chrome with search and actions", () => {
    const onSearchChange = vi.fn();

    render(
      <PageShell
        title="集成"
        eyebrow="集成与运维"
        description="统一入口"
        searchValue=""
        searchPlaceholder="搜索页面"
        onSearchChange={onSearchChange}
        actions={<button type="button">刷新</button>}
      >
        <PageShellGrid>
          <article>Gateway</article>
        </PageShellGrid>
      </PageShell>
    );

    expect(screen.getByRole("heading", { name: "集成" })).toBeInTheDocument();
    expect(screen.getByText("集成与运维")).toBeInTheDocument();
    expect(screen.getByText("统一入口")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索页面"), { target: { value: "mcp" } });
    expect(onSearchChange).toHaveBeenCalledWith("mcp");
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(screen.getByText("Gateway")).toBeInTheDocument();
  });

  it("renders loading and empty states", () => {
    const { rerender } = render(
      <PageShell title="运行" loading loadingText="正在加载运行">
        <span>loaded</span>
      </PageShell>
    );

    expect(screen.getByRole("status")).toHaveTextContent("正在加载运行");
    expect(screen.queryByText("loaded")).not.toBeInTheDocument();

    rerender(
      <PageShell title="运行" empty emptyTitle="没有运行" emptyDescription="换个筛选条件试试">
        <PageShellList>
          <span>run</span>
        </PageShellList>
      </PageShell>
    );

    expect(screen.getByRole("heading", { name: "没有运行" })).toBeInTheDocument();
    expect(screen.getByText("换个筛选条件试试")).toBeInTheDocument();
    expect(screen.queryByText("run")).not.toBeInTheDocument();
  });
});
