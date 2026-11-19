import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("sends the CSRF header and JSON body", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response('{"ok":true}', { status: 200 }));
    await expect(api.post("/api/x", { a: 1 })).resolves.toEqual({ ok: true });
    const init = f.mock.calls[0][1]!;
    expect((init.headers as Record<string, string>)["X-Requested-With"]).toBe("wakeful");
    expect(init.body).toBe('{"a":1}');
  });

  it("turns validation errors into readable messages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ["body", "price"], msg: "too low" }] }), { status: 422 }));
    await expect(api.get("/api/y")).rejects.toEqual(new ApiError(422, "price: too low"));
  });

  it("signals unauthorized responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response('{"detail":"Not signed in"}', { status: 401 }));
    const spy = vi.fn();
    window.addEventListener("wakeful:unauthorized", spy);
    await expect(api.get("/api/z")).rejects.toThrow("Not signed in");
    expect(spy).toHaveBeenCalled();
  });
});
