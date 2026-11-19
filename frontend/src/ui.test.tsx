import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ago, ConfirmButton, money, statusBadge, Toggle } from "./ui";

describe("ui helpers", () => {
  it("formats money and relative time", () => {
    expect(money(3)).toBe("$3.00");
    expect(money(null)).toBe("—");
    expect(ago(null)).toBe("—");
    expect(ago(new Date(Date.now() - 120_000).toISOString())).toBe("2m ago");
    expect(ago(new Date(Date.now() + 3 * 3600_000).toISOString())).toBe("in 3h");
  });

  it("labels not_contactable fans as unreachable", () => {
    render(<>{statusBadge("not_contactable")}</>);
    expect(screen.getByText("unreachable")).toBeInTheDocument();
  });

  it("toggle reports the inverted value", () => {
    const fn = vi.fn();
    render(<Toggle checked={false} onChange={fn} label="t" />);
    fireEvent.click(screen.getByRole("switch"));
    expect(fn).toHaveBeenCalledWith(true);
  });

  it("confirm button needs a second click", () => {
    const fn = vi.fn();
    render(<ConfirmButton onConfirm={fn} confirmText="Really delete">Delete</ConfirmButton>);
    fireEvent.click(screen.getByText("Delete"));
    expect(fn).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Really delete"));
    expect(fn).toHaveBeenCalledOnce();
  });
});
