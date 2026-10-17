import { describe, expect, it } from "vitest";
import { createShelfServer } from "./server.js";

describe("createShelfServer", () => {
  it("builds", () => {
    expect(createShelfServer({})).toBeDefined();
  });
});
