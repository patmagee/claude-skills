import { stringify } from "yaml";
import type { Skill } from "../schema.js";

export function renderCodexYaml(skill: Skill): string {
  const fm = skill.frontmatter;
  const doc = {
    interface: {
      display_name: fm.displayName,
      short_description: fm.shortDescription,
    },
    policy: {
      allow_implicit_invocation: fm.invocation === "model",
    },
  };
  return stringify(doc);
}
