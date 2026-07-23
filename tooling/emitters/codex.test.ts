import { describe, it, expect } from "vitest";
import { parse } from "yaml";
import { renderCodexYaml } from "./codex.js";
import type { Skill } from "../schema.js";

function skill(overrides: Partial<Skill["frontmatter"]> = {}): Skill {
  return {
    slug: "x",
    dir: "/tmp/x",
    body: "body",
    frontmatter: {
      name: "x",
      description: "d.",
      invocation: "model",
      harnesses: ["claude", "codex", "cursor"],
      displayName: "Ex",
      shortDescription: "short",
      disableModelInvocation: false,
      ...overrides,
    },
  };
}

describe("renderCodexYaml", () => {
  it("emits interface metadata and implicit invocation allowed", () => {
    const doc = parse(renderCodexYaml(skill()));
    expect(doc.interface.display_name).toBe("Ex");
    expect(doc.interface.short_description).toBe("short");
    expect(doc.policy.allow_implicit_invocation).toBe(true);
  });

  it("disallows implicit invocation for user skills", () => {
    const doc = parse(
      renderCodexYaml(skill({ invocation: "user", disableModelInvocation: true })),
    );
    expect(doc.policy.allow_implicit_invocation).toBe(false);
  });
});
