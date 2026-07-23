import { describe, it, expect } from "vitest";
import { renderCursorMdc } from "./cursor.js";
import type { Skill } from "../schema.js";

const skill: Skill = {
  slug: "x",
  dir: "/tmp/x",
  body: "# Heading\n\nBody text.\n",
  frontmatter: {
    name: "x",
    description: "Full description. More.",
    invocation: "model",
    harnesses: ["claude", "codex", "cursor"],
    displayName: "Ex",
    shortDescription: "Full description.",
    disableModelInvocation: false,
  },
};

describe("renderCursorMdc", () => {
  it("emits frontmatter with description and alwaysApply false", () => {
    const out = renderCursorMdc(skill);
    expect(out).toMatch(/^---\n/);
    expect(out).toContain("description: Full description. More.");
    expect(out).toContain("alwaysApply: false");
  });

  it("includes the skill body after the frontmatter", () => {
    const out = renderCursorMdc(skill);
    expect(out).toContain("# Heading");
    expect(out).toContain("Body text.");
  });
});
