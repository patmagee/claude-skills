import { describe, it, expect } from "vitest";
import {
  pluginSkillPaths,
  renderReadmeTable,
  replaceBetweenMarkers,
  checkVersionSync,
  README_START,
  README_END,
} from "./aggregates.js";
import type { Skill } from "./schema.js";

function skill(slug: string, harnesses: Skill["frontmatter"]["harnesses"], invocation: "model" | "user" = "model"): Skill {
  return {
    slug,
    dir: `/tmp/${slug}`,
    body: "b",
    frontmatter: {
      name: slug,
      description: `${slug} does things. Detail.`,
      invocation,
      harnesses,
      displayName: slug,
      shortDescription: `${slug} does things.`,
      disableModelInvocation: invocation === "user",
    },
  };
}

describe("pluginSkillPaths", () => {
  it("includes only claude-targeted skills, sorted", () => {
    const skills = [
      skill("b-skill", ["claude", "codex"]),
      skill("a-skill", ["claude"]),
      skill("codex-only", ["codex"]),
    ];
    expect(pluginSkillPaths(skills)).toEqual(["./skills/a-skill", "./skills/b-skill"]);
  });
});

describe("renderReadmeTable", () => {
  it("renders a row per skill with invocation", () => {
    const table = renderReadmeTable([skill("a-skill", ["claude"], "user")]);
    expect(table).toContain("| Skill | Description | Invocation |");
    expect(table).toContain("a-skill");
    expect(table).toContain("user");
  });
});

describe("replaceBetweenMarkers", () => {
  it("replaces content between markers", () => {
    const text = `pre\n${README_START}\nOLD\n${README_END}\npost`;
    const out = replaceBetweenMarkers(text, README_START, README_END, "NEW");
    expect(out).toBe(`pre\n${README_START}\nNEW\n${README_END}\npost`);
  });
  it("throws when a marker is missing", () => {
    expect(() => replaceBetweenMarkers("no markers", README_START, README_END, "x")).toThrow(/marker/i);
  });
});

describe("checkVersionSync", () => {
  it("passes when all versions match", () => {
    expect(checkVersionSync({ pkg: "1.0.0", plugin: "1.0.0" }).ok).toBe(true);
  });
  it("fails and reports when versions differ", () => {
    const r = checkVersionSync({ pkg: "1.0.0", plugin: "1.2.0" });
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/1\.2\.0/);
  });
});
