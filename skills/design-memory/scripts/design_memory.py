#!/usr/bin/env python3
"""
design-memory: Local vector store for design docs and decision records.

Indexes design documents into a ChromaDB collection at ~/.design-memory/
and supports semantic search across all indexed docs regardless of source repo.

Usage:
    python design_memory.py index <file_or_dir> [--repo REPO] [--tags TAG1,TAG2] [--human-reviewed]
    python design_memory.py query <search_text> [--top-k N] [--repo REPO] [--tags TAG1,TAG2]
    python design_memory.py status
    python design_memory.py context <search_text> [--top-k N]
    python design_memory.py remove <doc_id>
    python design_memory.py list [--repo REPO]
    python design_memory.py patterns add "<text>" --name NAME --category CAT --evidence FILE1,FILE2
    python design_memory.py patterns extract [--tags TAGS] [--repo REPO] [--dry-run]
    python design_memory.py patterns query "<text>" [--top-k N]
    python design_memory.py patterns list [--category CAT] [--status STATUS]
    python design_memory.py patterns show <pattern_id>
    python design_memory.py patterns confirm <pattern_id>
    python design_memory.py patterns supersede <old_id> <new_id>
    python design_memory.py patterns refresh [<pattern_id>] [--all]
    python design_memory.py patterns remove <pattern_id> [--force]
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import textwrap
from collections import deque
from datetime import datetime
from pathlib import Path

import chromadb
import yaml

STORE_PATH = os.environ.get("DESIGN_MEMORY_STORE", os.path.expanduser("~/.design-memory"))
COLLECTION_NAME = "design_docs"
PATTERNS_COLLECTION_NAME = "design_patterns"
MAX_FILE_SIZE = 500 * 1024  # 500KB
V2_MARKER = "design_memory_v2_gemini"

TAG_VOCABULARY = [
    "data-modeling", "api-design", "infrastructure", "clinical", "workflow",
    "auth", "frontend", "testing", "devops", "performance", "security",
    "observability", "tenant-isolation", "data-pipeline", "event-driven",
]


def to_sentinel_string(items: list[str]) -> str:
    """Convert list to pipe-delimited sentinel format: |item1|item2|"""
    return "|" + "|".join(s.strip() for s in items if s.strip()) + "|"


def _sentinel_contains(field: str, value: str) -> dict:
    """Build a ChromaDB where clause that matches sentinel-formatted fields exactly."""
    return {field: {"$contains": f"|{value}|"}}


class GeminiEmbeddingFunction:
    """Embedding function using Gemini text-embedding-004 via Vertex AI + ADC.

    Uses Application Default Credentials with a GCP project.
    Set GOOGLE_CLOUD_PROJECT to override the default project (design-memory-store).
    Run `gcloud auth application-default login` to set up ADC.
    """

    DEFAULT_PROJECT = "design-memory-store"

    def __init__(self):
        self._client = None

    def name(self) -> str:
        return "gemini-text-embedding-004"

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai

                project = os.environ.get("GOOGLE_CLOUD_PROJECT", self.DEFAULT_PROJECT)
                location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

                self._client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                )
            except Exception as exc:
                print(
                    f"ERROR: Failed to initialize Gemini client: {exc}\n"
                    "\n"
                    "Setup:\n"
                    "  1. gcloud auth application-default login\n"
                    "  2. Ensure Vertex AI API is enabled in your project\n"
                    f"  3. Project: {os.environ.get('GOOGLE_CLOUD_PROJECT', self.DEFAULT_PROJECT)}\n",
                    file=sys.stderr,
                )
                sys.exit(1)
        return self._client

    def __call__(self, input: list[str]) -> list[list[float]]:
        try:
            result = self.client.models.embed_content(
                model="text-embedding-004", contents=input
            )
            return [e.values for e in result.embeddings]
        except Exception as exc:
            print(
                f"ERROR: Gemini embedding request failed: {exc}\n"
                "\n"
                "Check that:\n"
                "  - You have internet connectivity\n"
                "  - Your ADC credentials are valid:  gcloud auth application-default login\n"
                "  - Vertex AI API is enabled in your project",
                file=sys.stderr,
            )
            sys.exit(1)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)


def get_client():
    os.makedirs(STORE_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=STORE_PATH)


def check_migration(client):
    """Check if an existing collection needs v2 migration."""
    try:
        existing = client.get_collection(name=COLLECTION_NAME)
    except Exception:
        # Collection doesn't exist yet, no migration needed
        return

    meta = existing.metadata or {}
    if meta.get("version") == V2_MARKER:
        return  # Already v2

    if existing.count() > 0:
        print(
            "ERROR: Existing design-memory collection uses incompatible embeddings.\n"
            "\n"
            "The v2 format uses Gemini text-embedding-004 which is incompatible with\n"
            "the previous embedding model. You must delete the existing store and re-index.\n"
            "\n"
            f"  rm -rf {STORE_PATH}\n"
            "\n"
            "Then re-index your design documents.",
            file=sys.stderr,
        )
        sys.exit(1)


def get_collection(client):
    check_migration(client)
    ef = GeminiEmbeddingFunction()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "version": V2_MARKER},
        embedding_function=ef,
    )


def get_patterns_collection(client):
    """Get or create the design_patterns collection for pattern storage."""
    ef = GeminiEmbeddingFunction()
    return client.get_or_create_collection(
        name=PATTERNS_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "version": V2_MARKER},
        embedding_function=ef,
    )


def generate_pattern_id(text: str) -> str:
    """Generate a stable pattern ID from the pattern text."""
    content_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"pattern_{content_hash}"


def compute_pattern_confidence(evidence: list[dict]) -> str:
    """Derive pattern confidence from the highest-tier evidence.

    Returns 'human' if any evidence is from a HUMAN DECISION,
    'confirmed' if highest is CONFIRMED, else 'ai'.
    """
    tiers = {e.get("tier", "ai") for e in evidence}
    if "human" in tiers:
        return "human"
    if "confirmed" in tiers:
        return "confirmed"
    return "ai"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors (pure Python)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def find_connected_components(adjacency: dict[int, set[int]], n: int) -> list[list[int]]:
    """Find connected components in an undirected graph using BFS.

    adjacency: {node_index: set of neighbor indices}
    n: total number of nodes
    Returns list of components, each a list of node indices.
    """
    visited = set()
    components = []
    for node in range(n):
        if node in visited:
            continue
        component = []
        queue = deque([node])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)
    return components


def get_genai_client():
    """Get a Gemini generative AI client (reuses the same credentials as embeddings)."""
    try:
        from google import genai

        project = os.environ.get("GOOGLE_CLOUD_PROJECT", GeminiEmbeddingFunction.DEFAULT_PROJECT)
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        return genai.Client(vertexai=True, project=project, location=location)
    except Exception as exc:
        print(f"ERROR: Failed to initialize Gemini client: {exc}", file=sys.stderr)
        sys.exit(1)


def generate_doc_id(filepath: str, content: str) -> str:
    """Stable ID from filepath + content hash so re-indexing updates rather than duplicates."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    name = Path(filepath).stem
    return f"{name}_{content_hash}"


def chunk_document(content: str, max_chars: int = 2000, overlap_chars: int = 200) -> list[str]:
    """Split a document into overlapping chunks for better retrieval.

    For short docs (under max_chars), returns the whole doc as one chunk.
    For longer docs, splits on paragraph boundaries with character-based overlap.
    """
    if len(content) <= max_chars:
        return [content]

    chunks = []
    paragraphs = content.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            # Character-based overlap: take last overlap_chars characters,
            # then find nearest paragraph break to avoid mid-sentence splits
            tail = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else current_chunk
            para_break = tail.find("\n\n")
            if para_break != -1:
                tail = tail[para_break + 2:]
            current_chunk = tail + "\n\n" + para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter delimited by --- from document content.

    Returns (frontmatter_dict, body_without_frontmatter).
    If no frontmatter or malformed YAML, returns ({}, original_content)
    with a warning on stderr.
    """
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if end_match is None:
        print("Warning: Found opening --- but no closing --- for frontmatter", file=sys.stderr)
        return {}, content

    yaml_text = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]

    try:
        frontmatter = yaml.safe_load(yaml_text)
        if not isinstance(frontmatter, dict):
            print(
                f"Warning: Frontmatter parsed but is not a dict (got {type(frontmatter).__name__})",
                file=sys.stderr,
            )
            return {}, content
        return frontmatter, body
    except yaml.YAMLError as exc:
        print(f"Warning: Malformed YAML frontmatter: {exc}", file=sys.stderr)
        return {}, content


def extract_decision_blocks(content: str) -> list[dict]:
    """Extract decision blocks from document content.

    Looks for [HUMAN DECISION]...[/HUMAN DECISION],
    [CONFIRMED DECISION]...[/CONFIRMED DECISION], and
    [AI DECISION]...[/AI DECISION] blocks.

    Returns list of {"tier": "human"|"confirmed"|"ai", "content": "..."}.
    """
    blocks = []
    patterns = [
        ("human", r"\[HUMAN DECISION\](.*?)\[/HUMAN DECISION\]"),
        ("confirmed", r"\[CONFIRMED DECISION\](.*?)\[/CONFIRMED DECISION\]"),
        ("ai", r"\[AI DECISION\](.*?)\[/AI DECISION\]"),
    ]

    for tier, pattern in patterns:
        for match in re.finditer(pattern, content, re.DOTALL):
            blocks.append({"tier": tier, "content": match.group(1).strip()})

    return blocks


def cmd_index(args):
    """Index one or more design docs into the vector store."""
    client = get_client()
    collection = get_collection(client)

    target = Path(args.path)
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(
            p
            for p in target.rglob("*")
            if p.suffix in (".md", ".txt", ".rst", ".adoc") and not p.name.startswith(".")
        )
    else:
        print(f"Error: {args.path} is not a file or directory", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("No indexable files found (.md, .txt, .rst, .adoc)", file=sys.stderr)
        sys.exit(1)

    indexed_count = 0
    total_tiers = {"human": 0, "confirmed": 0, "ai": 0}

    for filepath in files:
        # File size guard
        file_size = filepath.stat().st_size
        if file_size > MAX_FILE_SIZE:
            print(f"  Skipping {filepath.name} (file size {file_size // 1024}KB exceeds {MAX_FILE_SIZE // 1024}KB limit)")
            continue

        content = filepath.read_text(encoding="utf-8", errors="replace")
        if len(content.strip()) < 50:
            print(f"  Skipping {filepath.name} (too short)")
            continue

        # Parse frontmatter and extract decision blocks
        frontmatter, body = parse_frontmatter(content)
        decision_blocks = extract_decision_blocks(body)

        # Resolve metadata: CLI flags > frontmatter > git auto-detect > defaults
        # Repo
        repo = args.repo or frontmatter.get("repo")
        if not repo:
            try:
                import subprocess

                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    cwd=str(target if target.is_dir() else target.parent),
                )
                if result.returncode == 0:
                    repo = Path(result.stdout.strip()).name
            except Exception:
                pass
        if not repo:
            repo = "unknown"

        # Services
        if args.services:
            services_list = [s.strip() for s in args.services.split(",") if s.strip()]
        elif frontmatter.get("services"):
            services_list = [s.strip() for s in frontmatter["services"]] if isinstance(frontmatter["services"], list) else [frontmatter["services"]]
        else:
            services_list = [repo]

        # Tags
        if args.tags:
            tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]
        elif frontmatter.get("tags"):
            tags_list = [t.strip() for t in frontmatter["tags"]] if isinstance(frontmatter["tags"], list) else [frontmatter["tags"]]
        else:
            tags_list = []

        # Human reviewed
        human_reviewed = args.human_reviewed or frontmatter.get("human_reviewed", False)

        # Title
        title = frontmatter.get("title", filepath.stem)

        # Status
        status = frontmatter.get("status", "active")

        # Doc type
        doc_type = "decision" if decision_blocks else "design"

        # Decisions summary
        fm_decisions = frontmatter.get("decisions", [])
        if args.human_decisions:
            decisions_str = args.human_decisions
        elif fm_decisions:
            decisions_str = " | ".join(str(d) for d in fm_decisions)
        else:
            decisions_str = ""

        # Sentinel strings for services and tags
        services_sentinel = to_sentinel_string(services_list)
        tags_sentinel = to_sentinel_string(tags_list) if tags_list else ""

        # Prepend human decision block content to body for embedding weight
        indexable_body = body
        human_blocks = [b for b in decision_blocks if b["tier"] == "human"]
        if human_blocks:
            prepend = "\n\n".join(b["content"] for b in human_blocks)
            indexable_body = prepend + "\n\n" + body

        # Count tiers for summary
        for block in decision_blocks:
            total_tiers[block["tier"]] = total_tiers.get(block["tier"], 0) + 1

        chunks = chunk_document(indexable_body)

        for i, chunk in enumerate(chunks):
            doc_id = generate_doc_id(str(filepath), content)
            if len(chunks) > 1:
                doc_id = f"{doc_id}_chunk{i}"

            metadata = {
                "repo": repo,
                "services": services_sentinel,
                "filename": filepath.name,
                "filepath": str(filepath.resolve()),
                "indexed_at": datetime.now().isoformat(),
                "human_reviewed": human_reviewed,
                "decisions": decisions_str,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "doc_type": doc_type,
                "title": title,
                "status": status,
            }
            if tags_sentinel:
                metadata["tags"] = tags_sentinel

            collection.upsert(ids=[doc_id], documents=[chunk], metadatas=[metadata])

        # Per-file summary
        tier_labels = []
        file_tiers = {"human": 0, "confirmed": 0, "ai": 0}
        for block in decision_blocks:
            file_tiers[block["tier"]] += 1
        for tier_name in ("human", "confirmed", "ai"):
            if file_tiers[tier_name] > 0:
                tier_labels.append(f"{file_tiers[tier_name]} {tier_name}")
        tier_str = f", decisions: {', '.join(tier_labels)}" if tier_labels else ""

        print(
            f"  Indexed: {filepath.name} ({len(chunks)} chunk(s), "
            f"type={doc_type}, "
            f"services={', '.join(services_list)}{tier_str})"
        )
        indexed_count += 1

    print(f"\nIndexed {indexed_count} document(s) into {STORE_PATH}")
    print(f"Collection now has {collection.count()} total chunks")
    if any(total_tiers.values()):
        tier_summary = ", ".join(f"{v} {k}" for k, v in total_tiers.items() if v > 0)
        print(f"Decision blocks found: {tier_summary}")

    # Post-index pattern relevance check
    if getattr(args, "check_patterns", False):
        try:
            patterns_collection = get_patterns_collection(client)
            if patterns_collection.count() > 0:
                print("\nChecking new decisions against existing patterns...")
                for filepath in files:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    _, body = parse_frontmatter(content)
                    blocks = extract_decision_blocks(body)
                    for block in blocks:
                        results = patterns_collection.query(
                            query_texts=[block["content"]],
                            n_results=1,
                            include=["metadatas", "distances"],
                        )
                        if results["ids"][0]:
                            sim = 1 - results["distances"][0][0]
                            pmeta = results["metadatas"][0][0]
                            if sim >= 0.6:
                                print(f"  {filepath.name}: decision aligns with pattern '{pmeta.get('name')}' (similarity={sim:.3f})")
                            elif sim >= 0.4:
                                print(f"  {filepath.name}: decision may relate to pattern '{pmeta.get('name')}' (similarity={sim:.3f}) — review for consistency")
        except Exception:
            pass


def _format_sentinel(sentinel: str) -> str:
    """Format a sentinel string for human display: |a|b| -> a, b"""
    if not sentinel:
        return "?"
    return ", ".join(s for s in sentinel.split("|") if s.strip())


def _matches_filters(meta: dict, repo: str = None, service: str = None,
                     tags: str = None, decisions_only: bool = False) -> bool:
    """Check if a chunk's metadata matches the given post-query filters."""
    if repo and meta.get("repo") != repo:
        return False
    if service and f"|{service}|" not in meta.get("services", ""):
        return False
    if tags:
        for tag in tags.split(","):
            tag = tag.strip()
            if tag and f"|{tag}|" not in meta.get("tags", ""):
                return False
    if decisions_only and meta.get("doc_type") != "decision":
        return False
    return True


def cmd_query(args):
    """Semantic search across all indexed design docs."""
    client = get_client()
    collection = get_collection(client)

    if collection.count() == 0:
        print("No documents indexed yet. Use 'index' to add design docs.", file=sys.stderr)
        sys.exit(1)

    has_filters = args.repo or args.service or args.tags or args.decisions_only

    # Fetch extra results when filtering so we have enough after post-filtering
    fetch_k = args.top_k * 5 if has_filters else args.top_k

    results = collection.query(
        query_texts=[args.search_text],
        n_results=min(fetch_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        print("No matching documents found.")
        return

    # Deduplicate by source file: keep the highest similarity chunk per document
    seen_files = {}
    for doc_id, doc, meta, dist in zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        filepath = meta.get("filepath", doc_id)
        similarity = 1 - dist
        if filepath not in seen_files or similarity > seen_files[filepath]["similarity"]:
            seen_files[filepath] = {
                "doc_id": doc_id,
                "doc": doc,
                "meta": meta,
                "dist": dist,
                "similarity": similarity,
            }

    # Sort by similarity descending
    deduped = sorted(seen_files.values(), key=lambda x: x["similarity"], reverse=True)

    # Apply post-query filters
    if has_filters:
        deduped = [
            e for e in deduped
            if _matches_filters(e["meta"], args.repo, args.service, args.tags, args.decisions_only)
        ][:args.top_k]
    else:
        deduped = deduped[:args.top_k]

    if not deduped:
        print("No matching documents found.")
        return

    print(f"Found {len(deduped)} relevant document(s):\n")
    for i, entry in enumerate(deduped):
        meta = entry["meta"]
        similarity = entry["similarity"]
        doc = entry["doc"]
        print(f"--- Result {i+1} (similarity: {similarity:.3f}) ---")
        print(f"  Repo: {meta.get('repo', '?')}  |  Services: {_format_sentinel(meta.get('services', '?'))}  |  Type: {meta.get('doc_type', '?')}")
        print(f"  Title: {meta.get('title', '?')}  |  Human reviewed: {meta.get('human_reviewed', '?')}")
        if meta.get("tags"):
            print(f"  Tags: {_format_sentinel(meta['tags'])}")
        if meta.get("decisions"):
            print(f"  Decisions: {meta['decisions']}")
        print()
        # Print a truncated preview
        preview = doc[:500] + ("..." if len(doc) > 500 else "")
        print(textwrap.indent(preview, "  "))
        print()


def cmd_context(args):
    """Output query results in a format suitable for injection into a system prompt or skill context.

    This is the integration point for superpowers brainstorm.
    """
    client = get_client()
    collection = get_collection(client)

    if collection.count() == 0:
        print("<!-- No design memory indexed yet -->")
        return

    has_filters = args.service or (hasattr(args, "repo") and args.repo) or (hasattr(args, "tags") and args.tags)

    # Fetch extra results when filtering so we have enough after post-filtering
    fetch_k = args.top_k * 5 if has_filters else args.top_k

    results = collection.query(
        query_texts=[args.search_text],
        n_results=min(fetch_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        print("<!-- No sufficiently relevant decisions found for this query -->")
        return

    # Deduplicate by source file: keep the highest similarity chunk per document
    seen_files = {}
    for doc_id, doc, meta, dist in zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        filepath = meta.get("filepath", doc_id)
        similarity = 1 - dist
        if filepath not in seen_files or similarity > seen_files[filepath]["similarity"]:
            seen_files[filepath] = {
                "doc_id": doc_id,
                "doc": doc,
                "meta": meta,
                "dist": dist,
                "similarity": similarity,
            }

    # Sort by similarity, apply post-query filters, then min_similarity threshold
    sorted_results = sorted(seen_files.values(), key=lambda x: x["similarity"], reverse=True)

    if has_filters:
        repo_filter = args.repo if hasattr(args, "repo") else None
        tags_filter = args.tags if hasattr(args, "tags") else None
        sorted_results = [
            e for e in sorted_results
            if _matches_filters(e["meta"], repo_filter, args.service, tags_filter)
        ]

    deduped = [
        e for e in sorted_results
        if e["similarity"] >= args.min_similarity
    ][:args.top_k]

    if not deduped:
        print("<!-- No sufficiently relevant decisions found for this query -->")
        return

    # Group decisions by tier across all matched documents
    tier_decisions = {"human": [], "confirmed": [], "ai": []}
    for entry in deduped:
        doc_content = entry["doc"]
        blocks = extract_decision_blocks(doc_content)
        for block in blocks:
            tier_decisions[block["tier"]].append({
                "content": block["content"],
                "meta": entry["meta"],
                "similarity": entry["similarity"],
            })

    # Query patterns if available and not suppressed
    pattern_results = []
    if not getattr(args, "no_patterns", False):
        try:
            patterns_collection = get_patterns_collection(client)
            if patterns_collection.count() > 0:
                p_results = patterns_collection.query(
                    query_texts=[args.search_text],
                    n_results=min(3, patterns_collection.count()),
                    include=["documents", "metadatas", "distances"],
                )
                if p_results["ids"][0]:
                    for pid, pdoc, pmeta, pdist in zip(
                        p_results["ids"][0], p_results["documents"][0],
                        p_results["metadatas"][0], p_results["distances"][0],
                    ):
                        sim = 1 - pdist
                        if sim >= args.min_similarity and pmeta.get("status") == "active":
                            pattern_results.append({"doc": pdoc, "meta": pmeta, "similarity": sim})
        except Exception:
            pass  # patterns collection may not exist yet

    # Output as structured context block for prompt injection
    print("<prior_design_decisions>")
    print(f"The following prior design decisions are relevant to: {args.search_text}")
    print(f"Found {len(deduped)} relevant document(s) from the team's design history.\n")

    # Include patterns section if any matched
    if pattern_results:
        print("<design_patterns>")
        print("Relevant established patterns from the team's design history:\n")
        for p in pattern_results:
            pmeta = p["meta"]
            evidence_count = pmeta.get("evidence_count", 0)
            print(f'<pattern name="{pmeta.get("name", "?")}" confidence="{pmeta.get("confidence", "?")}" evidence="{evidence_count} decisions" category="{pmeta.get("category", "?")}">')
            print(p["doc"])
            # Show source files
            try:
                evidence = json.loads(pmeta.get("evidence", "[]"))
                sources = sorted({e.get("filename", "?") for e in evidence})
                if sources:
                    print(f"Sources: {', '.join(sources)}")
            except (json.JSONDecodeError, TypeError):
                pass
            print("</pattern>\n")
        print("Patterns represent established team conventions. Follow them unless there is a compelling reason to diverge.")
        print("</design_patterns>\n")

    # Print tier-grouped decisions if any exist
    has_decisions = any(tier_decisions[t] for t in tier_decisions)
    if has_decisions:
        for tier_name, label in [("human", "HUMAN DECISIONS (highest confidence)"),
                                  ("confirmed", "CONFIRMED DECISIONS (team-validated)"),
                                  ("ai", "AI DECISIONS (auto-extracted, verify before relying on)")]:
            if tier_decisions[tier_name]:
                print(f"## {label}")
                for d in tier_decisions[tier_name]:
                    meta = d["meta"]
                    print(f"  [{meta.get('filename', '?')} | similarity={d['similarity']:.3f}]")
                    print(f"  {d['content']}")
                    print()

    # Print full document context
    for i, entry in enumerate(deduped):
        meta = entry["meta"]
        similarity = entry["similarity"]
        doc = entry["doc"]
        attrs = (
            f'repo="{meta.get("repo", "?")}" '
            f'services="{_format_sentinel(meta.get("services", "?"))}" '
            f'file="{meta.get("filename", "?")}" '
            f'type="{meta.get("doc_type", "?")}" '
            f'similarity="{similarity:.3f}" '
            f'human_reviewed="{meta.get("human_reviewed", False)}"'
        )
        print(f"<decision {attrs}>")

        # Surface decisions metadata prominently
        if meta.get("decisions"):
            print("\n** Key decisions:")
            for d in meta["decisions"].split("|"):
                d = d.strip()
                if d:
                    print(f"  - {d}")
            print()

        print(doc)
        print("</decision>\n")

    print("When making new design decisions, consider whether these prior decisions are relevant.")
    print("Give extra weight to HUMAN DECISIONS — these were explicitly called out by a team member.")
    print("Prioritize consistency with prior human-reviewed decisions unless there is a clear reason to diverge.")
    print("If diverging, explicitly note the prior decision and explain the rationale for the change.")
    print("</prior_design_decisions>")


def cmd_status(args):
    """Show stats about the current vector store."""
    client = get_client()
    collection = get_collection(client)

    total = collection.count()
    if total == 0:
        print(f"Design memory at {STORE_PATH}")
        print("No documents indexed yet.")
        return

    # Get all metadata to compute stats
    all_data = collection.get(include=["metadatas"])
    repos = {}
    services = {}
    doc_types = {}
    human_reviewed_count = 0
    decisions_count = 0
    unique_files = set()

    for meta in all_data["metadatas"]:
        repo = meta.get("repo", "unknown")
        repos[repo] = repos.get(repo, 0) + 1
        # Parse sentinel-format services: split on |, strip empty strings
        svc_str = meta.get("services", "")
        for svc in svc_str.split("|"):
            svc = svc.strip()
            if svc:
                services[svc] = services.get(svc, 0) + 1
        doc_type = meta.get("doc_type", "unknown")
        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        if meta.get("human_reviewed"):
            human_reviewed_count += 1
        if meta.get("decisions"):
            decisions_count += 1
        unique_files.add(meta.get("filepath", ""))

    print(f"Design memory at {STORE_PATH}")
    print(f"Total chunks: {total}")
    print(f"Unique documents: {len(unique_files)}")
    print(f"Human-reviewed chunks: {human_reviewed_count}")
    print(f"Chunks with decisions: {decisions_count}")
    print()
    print("By source repo:")
    for repo, count in sorted(repos.items()):
        print(f"  {repo}: {count} chunks")
    print()
    print("By service (decisions that apply to):")
    for svc, count in sorted(services.items()):
        print(f"  {svc}: {count} chunks")
    print()
    print("By type:")
    for dt, count in sorted(doc_types.items()):
        print(f"  {dt}: {count} chunks")

    # Pattern stats
    try:
        patterns_collection = get_patterns_collection(client)
        p_count = patterns_collection.count()
        if p_count > 0:
            p_data = patterns_collection.get(include=["metadatas"])
            statuses = {}
            confidences = {}
            categories = {}
            for pmeta in p_data["metadatas"]:
                s = pmeta.get("status", "?")
                statuses[s] = statuses.get(s, 0) + 1
                c = pmeta.get("confidence", "?")
                confidences[c] = confidences.get(c, 0) + 1
                cat = pmeta.get("category", "?")
                categories[cat] = categories.get(cat, 0) + 1

            print()
            status_parts = ", ".join(f"{v} {k}" for k, v in sorted(statuses.items()))
            print(f"Patterns: {p_count} total ({status_parts})")
            conf_parts = ", ".join(f"{v} {k}" for k, v in sorted(confidences.items()))
            print(f"  By confidence: {conf_parts}")
            cat_parts = ", ".join(f"{v} {k}" for k, v in sorted(categories.items()))
            print(f"  By category: {cat_parts}")
    except Exception:
        pass  # patterns collection may not exist yet


def cmd_remove(args):
    """Remove a document by exact ID or filename match."""
    client = get_client()
    collection = get_collection(client)

    # Exact matching: doc_id must equal the chunk ID or the filename metadata
    all_data = collection.get(include=["metadatas"])
    ids_to_remove = []
    for doc_id, meta in zip(all_data["ids"], all_data["metadatas"]):
        if doc_id == args.doc_id or meta.get("filename") == args.doc_id:
            ids_to_remove.append((doc_id, meta))

    if not ids_to_remove:
        print(f"No documents matching '{args.doc_id}' found.", file=sys.stderr)
        print("Use 'design_memory.py list' to see indexed documents and their filenames.")
        sys.exit(1)

    # Display what would be removed
    print(f"Found {len(ids_to_remove)} chunk(s) matching '{args.doc_id}':")
    for doc_id, meta in ids_to_remove:
        print(f"  {doc_id} ({meta.get('filename', '?')}, repo={meta.get('repo', '?')})")

    if not args.force:
        print(f"\nRe-run with --force to delete.")
        return

    collection.delete(ids=[doc_id for doc_id, _ in ids_to_remove])
    print(f"\nRemoved {len(ids_to_remove)} chunk(s).")


def cmd_list(args):
    """List all indexed documents."""
    client = get_client()
    collection = get_collection(client)

    if collection.count() == 0:
        print("No documents indexed.")
        return

    all_data = collection.get(include=["metadatas"])

    # Group by unique file
    files = {}
    for meta in all_data["metadatas"]:
        key = meta.get("filepath", "unknown")
        if key not in files:
            files[key] = meta

    repo_filter = args.repo if hasattr(args, "repo") and args.repo else None

    for filepath, meta in sorted(files.items()):
        if repo_filter and meta.get("repo") != repo_filter:
            continue
        hr = " [human-reviewed]" if meta.get("human_reviewed") else ""
        # Display sentinel-format services and tags as human-readable comma-separated
        svcs = _format_sentinel(meta.get("services", meta.get("repo", "?")))
        tags_str = ""
        if meta.get("tags"):
            tags_str = f" tags={_format_sentinel(meta['tags'])}"
        decisions = ""
        if meta.get("decisions"):
            count = len([d for d in meta["decisions"].split("|") if d.strip()])
            decisions = f" [{count} decision(s)]"
        print(f"  [{svcs}] {meta.get('filename', '?')} ({meta.get('doc_type', '?')}){hr}{decisions}{tags_str}")


############################
# Pattern commands
############################


def cmd_patterns_add(args):
    """Manually add a pattern with evidence links to existing documents."""
    client = get_client()
    docs_collection = get_collection(client)
    patterns_collection = get_patterns_collection(client)

    # Validate evidence files exist in design_docs
    evidence_files = [f.strip() for f in args.evidence.split(",") if f.strip()]
    if len(evidence_files) < 1:
        print("Error: At least one evidence file is required.", file=sys.stderr)
        sys.exit(1)

    all_docs = docs_collection.get(include=["metadatas", "documents"])
    # Build lookup by filepath and filename
    docs_by_file = {}
    for doc_id, meta, doc in zip(all_docs["ids"], all_docs["metadatas"], all_docs["documents"]):
        filepath = meta.get("filepath", "")
        filename = meta.get("filename", "")
        if filepath not in docs_by_file:
            docs_by_file[filepath] = {"meta": meta, "doc": doc}
        if filename not in docs_by_file:
            docs_by_file[filename] = {"meta": meta, "doc": doc}

    evidence = []
    repos = set()
    services_all = set()
    for ef in evidence_files:
        match = docs_by_file.get(ef)
        if not match:
            # Try partial match on filename
            for key, val in docs_by_file.items():
                if key.endswith(ef) or val["meta"].get("filename") == ef:
                    match = val
                    break
        if not match:
            print(f"Warning: Evidence file '{ef}' not found in design_docs. Skipping.", file=sys.stderr)
            continue

        meta = match["meta"]
        doc_content = match["doc"]
        blocks = extract_decision_blocks(doc_content)

        # Use all decision blocks from this file as evidence, or the decisions summary
        if blocks:
            for block in blocks:
                evidence.append({
                    "filepath": meta.get("filepath", ef),
                    "filename": meta.get("filename", ef),
                    "title": meta.get("title", ""),
                    "decision_text": block["content"][:500],
                    "tier": block["tier"],
                })
        elif meta.get("decisions"):
            for d in meta["decisions"].split("|"):
                d = d.strip()
                if d:
                    evidence.append({
                        "filepath": meta.get("filepath", ef),
                        "filename": meta.get("filename", ef),
                        "title": meta.get("title", ""),
                        "decision_text": d,
                        "tier": "ai",
                    })
        else:
            evidence.append({
                "filepath": meta.get("filepath", ef),
                "filename": meta.get("filename", ef),
                "title": meta.get("title", ""),
                "decision_text": "(no specific decision block found)",
                "tier": "ai",
            })

        repos.add(meta.get("repo", "unknown"))
        for svc in meta.get("services", "").split("|"):
            if svc.strip():
                services_all.add(svc.strip())

    if not evidence:
        print("Error: No valid evidence found from the specified files.", file=sys.stderr)
        sys.exit(1)

    confidence = compute_pattern_confidence(evidence)
    pattern_id = generate_pattern_id(args.pattern_text)
    now = datetime.now().isoformat()

    # Build tags
    tags_list = [args.category]
    if args.tags:
        tags_list.extend(t.strip() for t in args.tags.split(",") if t.strip())

    metadata = {
        "pattern_id": pattern_id,
        "name": args.name,
        "category": args.category,
        "tags": to_sentinel_string(tags_list),
        "services": to_sentinel_string(list(services_all)) if services_all else to_sentinel_string(["unknown"]),
        "repos": to_sentinel_string(list(repos)),
        "confidence": confidence,
        "status": "active",
        "superseded_by": "",
        "evidence": json.dumps(evidence),
        "evidence_count": len(evidence),
        "created_by": "manual",
        "created_at": now,
        "updated_at": now,
    }

    patterns_collection.upsert(ids=[pattern_id], documents=[args.pattern_text], metadatas=[metadata])
    print(f"Pattern added: {args.name}")
    print(f"  ID: {pattern_id}")
    print(f"  Confidence: {confidence}")
    print(f"  Evidence: {len(evidence)} decision(s) from {len(evidence_files)} file(s)")
    print(f"  Status: active")


def cmd_patterns_list(args):
    """List all patterns with optional filters."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    if patterns_collection.count() == 0:
        print("No patterns defined yet.")
        return

    all_data = patterns_collection.get(include=["metadatas", "documents"])

    for pid, meta, doc in zip(all_data["ids"], all_data["metadatas"], all_data["documents"]):
        # Apply filters
        if args.category and meta.get("category") != args.category:
            continue
        if args.status and meta.get("status") != args.status:
            continue
        if args.confidence and meta.get("confidence") != args.confidence:
            continue

        status = meta.get("status", "?")
        confidence = meta.get("confidence", "?")
        evidence_count = meta.get("evidence_count", 0)
        name = meta.get("name", "Unnamed")
        category = meta.get("category", "?")

        status_marker = {"active": "+", "draft": "~", "superseded": "-"}.get(status, "?")
        print(f"  [{status_marker}] {name} ({category}, {confidence}, {evidence_count} evidence)")
        # Truncate pattern text for list view
        preview = doc[:120] + ("..." if len(doc) > 120 else "")
        print(f"      {preview}")
        print(f"      id={pid}")


def cmd_patterns_show(args):
    """Show detailed information about a specific pattern."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    if patterns_collection.count() == 0:
        print("No patterns defined yet.")
        return

    # Find by pattern_id or name (partial match)
    all_data = patterns_collection.get(include=["metadatas", "documents"])
    found = None
    for pid, meta, doc in zip(all_data["ids"], all_data["metadatas"], all_data["documents"]):
        if pid == args.pattern_id or meta.get("name", "").lower() == args.pattern_id.lower():
            found = (pid, meta, doc)
            break
        # Partial match on name
        if args.pattern_id.lower() in meta.get("name", "").lower():
            found = (pid, meta, doc)

    if not found:
        print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
        sys.exit(1)

    pid, meta, doc = found
    print(f"Pattern: {meta.get('name', 'Unnamed')}")
    print(f"  ID: {pid}")
    print(f"  Status: {meta.get('status', '?')}")
    print(f"  Confidence: {meta.get('confidence', '?')}")
    print(f"  Category: {meta.get('category', '?')}")
    print(f"  Tags: {_format_sentinel(meta.get('tags', ''))}")
    print(f"  Services: {_format_sentinel(meta.get('services', ''))}")
    print(f"  Repos: {_format_sentinel(meta.get('repos', ''))}")
    print(f"  Created: {meta.get('created_at', '?')} by {meta.get('created_by', '?')}")
    print(f"  Updated: {meta.get('updated_at', '?')}")
    if meta.get("superseded_by"):
        print(f"  Superseded by: {meta['superseded_by']}")
    print()
    print("Pattern statement:")
    print(textwrap.indent(doc, "  "))
    print()

    evidence = json.loads(meta.get("evidence", "[]"))
    print(f"Evidence ({len(evidence)} decisions):")
    for i, e in enumerate(evidence):
        tier_label = {"human": "HUMAN", "confirmed": "CONFIRMED", "ai": "AI"}.get(e.get("tier", "ai"), "?")
        print(f"  {i+1}. [{tier_label}] {e.get('filename', '?')} — {e.get('title', '?')}")
        text = e.get("decision_text", "")
        if text and text != "(no specific decision block found)":
            preview = text[:200] + ("..." if len(text) > 200 else "")
            print(f"     {preview}")


def cmd_patterns_remove(args):
    """Remove a pattern by ID."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    if patterns_collection.count() == 0:
        print("No patterns to remove.")
        return

    # Find by pattern_id or name
    all_data = patterns_collection.get(include=["metadatas"])
    found = []
    for pid, meta in zip(all_data["ids"], all_data["metadatas"]):
        if pid == args.pattern_id or meta.get("name", "").lower() == args.pattern_id.lower():
            found.append((pid, meta))

    if not found:
        print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(found)} pattern(s) matching '{args.pattern_id}':")
    for pid, meta in found:
        print(f"  {pid} ({meta.get('name', '?')}, status={meta.get('status', '?')})")

    if not args.force:
        print("\nRe-run with --force to delete.")
        return

    patterns_collection.delete(ids=[pid for pid, _ in found])
    print(f"\nRemoved {len(found)} pattern(s).")


def cmd_patterns_confirm(args):
    """Promote a draft pattern to active."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    all_data = patterns_collection.get(include=["metadatas", "documents"])
    found = None
    for pid, meta, doc in zip(all_data["ids"], all_data["metadatas"], all_data["documents"]):
        if pid == args.pattern_id or meta.get("name", "").lower() == args.pattern_id.lower():
            found = (pid, meta, doc)
            break

    if not found:
        print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
        sys.exit(1)

    pid, meta, doc = found
    if meta.get("status") == "active":
        print(f"Pattern '{meta.get('name')}' is already active.")
        return

    meta["status"] = "active"
    meta["updated_at"] = datetime.now().isoformat()
    patterns_collection.upsert(ids=[pid], documents=[doc], metadatas=[meta])
    print(f"Pattern '{meta.get('name')}' promoted to active.")


def cmd_patterns_supersede(args):
    """Mark an old pattern as superseded by a new one."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    all_data = patterns_collection.get(include=["metadatas", "documents"])
    old_entry = None
    new_entry = None
    for pid, meta, doc in zip(all_data["ids"], all_data["metadatas"], all_data["documents"]):
        if pid == args.old_id or meta.get("name", "").lower() == args.old_id.lower():
            old_entry = (pid, meta, doc)
        if pid == args.new_id or meta.get("name", "").lower() == args.new_id.lower():
            new_entry = (pid, meta, doc)

    if not old_entry:
        print(f"Old pattern '{args.old_id}' not found.", file=sys.stderr)
        sys.exit(1)
    if not new_entry:
        print(f"New pattern '{args.new_id}' not found.", file=sys.stderr)
        sys.exit(1)

    old_pid, old_meta, old_doc = old_entry
    new_pid = new_entry[0]
    old_meta["status"] = "superseded"
    old_meta["superseded_by"] = new_pid
    old_meta["updated_at"] = datetime.now().isoformat()
    patterns_collection.upsert(ids=[old_pid], documents=[old_doc], metadatas=[old_meta])
    print(f"Pattern '{old_meta.get('name')}' marked as superseded by '{new_entry[1].get('name')}'.")


def cmd_patterns_query(args):
    """Semantic search over patterns."""
    client = get_client()
    patterns_collection = get_patterns_collection(client)

    if patterns_collection.count() == 0:
        print("No patterns indexed yet.")
        return

    results = patterns_collection.query(
        query_texts=[args.search_text],
        n_results=min(args.top_k * 3, patterns_collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        print("No matching patterns found.")
        return

    filtered = []
    for pid, doc, meta, dist in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        similarity = 1 - dist
        # Apply filters
        if args.category and meta.get("category") != args.category:
            continue
        if args.status and meta.get("status") != args.status:
            continue
        if args.min_evidence and meta.get("evidence_count", 0) < args.min_evidence:
            continue
        filtered.append({"pid": pid, "doc": doc, "meta": meta, "similarity": similarity})

    filtered = filtered[:args.top_k]

    if not filtered:
        print("No matching patterns found.")
        return

    print(f"Found {len(filtered)} matching pattern(s):\n")
    for i, entry in enumerate(filtered):
        meta = entry["meta"]
        print(f"--- Pattern {i+1} (similarity: {entry['similarity']:.3f}) ---")
        print(f"  Name: {meta.get('name', '?')}")
        print(f"  Status: {meta.get('status', '?')}  |  Confidence: {meta.get('confidence', '?')}  |  Category: {meta.get('category', '?')}")
        print(f"  Evidence: {meta.get('evidence_count', 0)} decision(s)")
        print(f"  Services: {_format_sentinel(meta.get('services', ''))}")
        print()
        print(textwrap.indent(entry["doc"], "  "))
        print()


def cmd_patterns_extract(args):
    """AI-assisted pattern extraction from indexed decisions."""
    client = get_client()
    docs_collection = get_collection(client)
    patterns_collection = get_patterns_collection(client)

    if docs_collection.count() == 0:
        print("No documents indexed yet. Index design docs first.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Gather all decision blocks from indexed documents
    print("Gathering decisions from indexed documents...")
    all_docs = docs_collection.get(include=["metadatas", "documents"])

    decisions = []  # list of {"text": str, "tier": str, "meta": dict}
    seen_texts = set()  # deduplicate identical decision text

    for meta, doc in zip(all_docs["metadatas"], all_docs["documents"]):
        # Apply filters
        if meta.get("status") == "superseded":
            continue
        if args.repo and meta.get("repo") != args.repo:
            continue
        if args.tags:
            for tag in args.tags.split(","):
                tag = tag.strip()
                if tag and f"|{tag}|" not in meta.get("tags", ""):
                    continue

        blocks = extract_decision_blocks(doc)
        for block in blocks:
            text = block["content"].strip()
            if text and text not in seen_texts:
                seen_texts.add(text)
                decisions.append({
                    "text": text,
                    "tier": block["tier"],
                    "meta": meta,
                })

        # Also include frontmatter decisions
        if meta.get("decisions"):
            for d in meta["decisions"].split("|"):
                d = d.strip()
                if d and d not in seen_texts:
                    seen_texts.add(d)
                    decisions.append({
                        "text": d,
                        "tier": "ai",
                        "meta": meta,
                    })

    if len(decisions) < args.min_evidence:
        print(f"Only found {len(decisions)} decision(s). Need at least {args.min_evidence} to form patterns.")
        return

    print(f"Found {len(decisions)} unique decision(s).")

    # Step 2: Embed all decision texts
    print("Embedding decisions for clustering...")
    ef = GeminiEmbeddingFunction()
    decision_texts = [d["text"] for d in decisions]

    # Batch embed (the API handles batching internally)
    embeddings = ef(decision_texts)

    # Step 3: Cluster by cosine similarity
    print(f"Clustering with threshold={args.cluster_threshold:.2f}...")
    n = len(decisions)
    adjacency = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim >= args.cluster_threshold:
                adjacency.setdefault(i, set()).add(j)
                adjacency.setdefault(j, set()).add(i)

    components = find_connected_components(adjacency, n)
    clusters = [c for c in components if len(c) >= args.min_evidence]

    if not clusters:
        print(f"No clusters found with >= {args.min_evidence} decisions. Try lowering --cluster-threshold or --min-evidence.")
        return

    print(f"Found {len(clusters)} potential pattern cluster(s).")

    if args.dry_run:
        print("\n--- DRY RUN: Showing clusters without persisting ---\n")
        for i, cluster in enumerate(clusters):
            print(f"Cluster {i+1} ({len(cluster)} decisions):")
            for idx in cluster:
                d = decisions[idx]
                tier = d["tier"].upper()
                filename = d["meta"].get("filename", "?")
                text = d["text"][:150] + ("..." if len(d["text"]) > 150 else "")
                print(f"  [{tier}] {filename}: {text}")
            print()
        print(f"Run without --dry-run to synthesize patterns via LLM.")
        return

    # Step 4: Synthesize patterns via Gemini
    print("Synthesizing patterns via Gemini...")
    genai_client = get_genai_client()
    tag_list_str = ", ".join(TAG_VOCABULARY)

    new_patterns = 0
    merged_patterns = 0

    for cluster_idx, cluster in enumerate(clusters):
        # Build prompt with decisions in this cluster
        cluster_decisions = [decisions[idx] for idx in cluster]
        decision_lines = []
        for j, d in enumerate(cluster_decisions):
            tier = d["tier"].upper()
            filename = d["meta"].get("filename", "?")
            repo = d["meta"].get("repo", "?")
            decision_lines.append(f"{j+1}. [{tier}] (from {filename} in {repo}): {d['text']}")

        prompt = (
            "You are analyzing design decisions from a software team's decision records.\n"
            "The following decisions appear to follow a common pattern:\n\n"
            + "\n".join(decision_lines) + "\n\n"
            "Synthesize a single pattern statement that captures the common approach.\n"
            "Format your response EXACTLY as:\n"
            f"NAME: <3-5 word title>\n"
            f"CATEGORY: <one of: {tag_list_str}>\n"
            "PATTERN: When <situation>, we use <approach> because <rationale>."
        )

        try:
            response = genai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            response_text = response.text.strip()
        except Exception as exc:
            print(f"  Warning: LLM call failed for cluster {cluster_idx+1}: {exc}", file=sys.stderr)
            continue

        # Parse response
        name = "Unnamed Pattern"
        category = "workflow"
        pattern_text = response_text

        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith("NAME:"):
                name = line[5:].strip()
            elif line.startswith("CATEGORY:"):
                cat = line[9:].strip().lower()
                if cat in TAG_VOCABULARY:
                    category = cat
            elif line.startswith("PATTERN:"):
                pattern_text = line[8:].strip()

        # Build evidence list
        evidence = []
        repos = set()
        services_all = set()
        for d in cluster_decisions:
            evidence.append({
                "filepath": d["meta"].get("filepath", ""),
                "filename": d["meta"].get("filename", ""),
                "title": d["meta"].get("title", ""),
                "decision_text": d["text"][:500],
                "tier": d["tier"],
            })
            repos.add(d["meta"].get("repo", "unknown"))
            for svc in d["meta"].get("services", "").split("|"):
                if svc.strip():
                    services_all.add(svc.strip())

        # Step 5: Deduplicate against existing patterns
        pattern_id = generate_pattern_id(pattern_text)
        merged = False
        if patterns_collection.count() > 0:
            existing = patterns_collection.query(
                query_texts=[pattern_text],
                n_results=1,
                include=["metadatas", "documents", "distances"],
            )
            if existing["ids"][0]:
                existing_sim = 1 - existing["distances"][0][0]
                if existing_sim > 0.85:
                    # Merge evidence into existing pattern
                    existing_meta = existing["metadatas"][0][0]
                    existing_evidence = json.loads(existing_meta.get("evidence", "[]"))
                    existing_filepaths = {e.get("filepath") for e in existing_evidence}
                    for e in evidence:
                        if e.get("filepath") not in existing_filepaths:
                            existing_evidence.append(e)
                    existing_meta["evidence"] = json.dumps(existing_evidence)
                    existing_meta["evidence_count"] = len(existing_evidence)
                    existing_meta["confidence"] = compute_pattern_confidence(existing_evidence)
                    existing_meta["updated_at"] = datetime.now().isoformat()
                    patterns_collection.upsert(
                        ids=[existing["ids"][0][0]],
                        documents=[existing["documents"][0][0]],
                        metadatas=[existing_meta],
                    )
                    merged = True
                    merged_patterns += 1
                    print(f"  Merged into existing: {existing_meta.get('name')} (+{len(evidence)} evidence)")

        if not merged:
            # Step 6: Persist new pattern
            confidence = compute_pattern_confidence(evidence)
            now = datetime.now().isoformat()
            metadata = {
                "pattern_id": pattern_id,
                "name": name,
                "category": category,
                "tags": to_sentinel_string([category]),
                "services": to_sentinel_string(list(services_all)) if services_all else to_sentinel_string(["unknown"]),
                "repos": to_sentinel_string(list(repos)),
                "confidence": confidence,
                "status": "draft",
                "superseded_by": "",
                "evidence": json.dumps(evidence),
                "evidence_count": len(evidence),
                "created_by": "ai_extraction",
                "created_at": now,
                "updated_at": now,
            }
            patterns_collection.upsert(ids=[pattern_id], documents=[pattern_text], metadatas=[metadata])
            new_patterns += 1
            print(f"  New pattern (draft): {name}")
            print(f"    {pattern_text[:120]}...")

    print(f"\nExtraction complete: {new_patterns} new pattern(s), {merged_patterns} merged into existing.")
    if new_patterns > 0:
        print("New patterns are in 'draft' status. Use 'patterns confirm <id>' to promote to active.")


def cmd_patterns_refresh(args):
    """Re-evaluate a pattern's evidence against current indexed documents."""
    client = get_client()
    docs_collection = get_collection(client)
    patterns_collection = get_patterns_collection(client)

    if patterns_collection.count() == 0:
        print("No patterns to refresh.")
        return

    # Get patterns to refresh
    all_patterns = patterns_collection.get(include=["metadatas", "documents"])
    targets = []
    if args.pattern_id and not args.all:
        for pid, meta, doc in zip(all_patterns["ids"], all_patterns["metadatas"], all_patterns["documents"]):
            if pid == args.pattern_id or meta.get("name", "").lower() == args.pattern_id.lower():
                targets.append((pid, meta, doc))
                break
        if not targets:
            print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        targets = list(zip(all_patterns["ids"], all_patterns["metadatas"], all_patterns["documents"]))

    print(f"Refreshing {len(targets)} pattern(s)...")

    for pid, meta, doc in targets:
        # Query design_docs for semantically similar chunks
        results = docs_collection.query(
            query_texts=[doc],
            n_results=min(20, docs_collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        if not results["ids"][0]:
            continue

        # Extract decisions from similar documents
        new_evidence = []
        existing_evidence = json.loads(meta.get("evidence", "[]"))
        existing_filepaths_decisions = {
            (e.get("filepath", ""), e.get("decision_text", ""))
            for e in existing_evidence
        }

        for doc_content, doc_meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            similarity = 1 - dist
            if similarity < 0.5:
                continue
            if doc_meta.get("status") == "superseded":
                continue

            blocks = extract_decision_blocks(doc_content)
            for block in blocks:
                key = (doc_meta.get("filepath", ""), block["content"][:500])
                if key not in existing_filepaths_decisions:
                    new_evidence.append({
                        "filepath": doc_meta.get("filepath", ""),
                        "filename": doc_meta.get("filename", ""),
                        "title": doc_meta.get("title", ""),
                        "decision_text": block["content"][:500],
                        "tier": block["tier"],
                    })
                    existing_filepaths_decisions.add(key)

        if new_evidence:
            combined = existing_evidence + new_evidence
            meta["evidence"] = json.dumps(combined)
            meta["evidence_count"] = len(combined)
            meta["confidence"] = compute_pattern_confidence(combined)
            meta["updated_at"] = datetime.now().isoformat()
            patterns_collection.upsert(ids=[pid], documents=[doc], metadatas=[meta])
            print(f"  {meta.get('name')}: +{len(new_evidence)} new evidence (total {len(combined)})")
        else:
            print(f"  {meta.get('name')}: no new evidence found")


def main():
    parser = argparse.ArgumentParser(description="Design memory: local vector store for design docs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Index design doc(s)")
    p_index.add_argument("path", help="File or directory to index")
    p_index.add_argument("--repo", help="Repository name (auto-detected from git if omitted)")
    p_index.add_argument(
        "--services",
        help="Comma-separated services/repos this decision applies to (e.g. tertiary-analysis,workbench). "
        "Use this when a design decision spans multiple services.",
    )
    p_index.add_argument("--tags", help="Comma-separated tags (e.g. data-modeling,api-design)")
    p_index.add_argument("--human-reviewed", action="store_true", help="Mark as human-reviewed")
    p_index.add_argument(
        "--human-decisions",
        help="Pipe-delimited summary of specific human decisions, e.g. "
        "'Use Resilience4j at HTTP layer|Dead letter to Postgres not Kafka|3 max retries'. "
        "These are indexed as first-class searchable content.",
    )
    p_index.add_argument("--check-patterns", action="store_true",
                         help="After indexing, check new decisions against existing patterns for relevance")
    p_index.set_defaults(func=cmd_index)

    # query
    p_query = subparsers.add_parser("query", help="Search design docs")
    p_query.add_argument("search_text", help="What to search for")
    p_query.add_argument("--top-k", type=int, default=5, help="Number of results")
    p_query.add_argument("--repo", help="Filter by source repo")
    p_query.add_argument("--service", help="Filter by target service")
    p_query.add_argument("--tags", help="Filter by tags")
    p_query.add_argument("--decisions-only", action="store_true", help="Only return decision docs")
    p_query.set_defaults(func=cmd_query)

    # context (for superpowers integration)
    p_context = subparsers.add_parser("context", help="Output context block for prompt injection")
    p_context.add_argument("search_text", help="Topic to find relevant decisions for")
    p_context.add_argument("--top-k", type=int, default=5, help="Number of results")
    p_context.add_argument("--min-similarity", type=float, default=0.3, help="Minimum similarity threshold (default 0.3)")
    p_context.add_argument("--service", help="Filter to decisions relevant to a specific service")
    p_context.add_argument("--repo", help="Filter by source repo")
    p_context.add_argument("--tags", help="Comma-separated tags to filter by")
    p_context.add_argument("--no-patterns", action="store_true", help="Suppress pattern results in context output")
    p_context.set_defaults(func=cmd_context)

    # status
    p_status = subparsers.add_parser("status", help="Show store stats")
    p_status.set_defaults(func=cmd_status)

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove a document")
    p_remove.add_argument("doc_id", help="Document ID or filename to remove (exact match)")
    p_remove.add_argument("--force", action="store_true", help="Actually delete (without this flag, just shows what would be removed)")
    p_remove.set_defaults(func=cmd_remove)

    # list
    p_list = subparsers.add_parser("list", help="List all indexed documents")
    p_list.add_argument("--repo", help="Filter by repo")
    p_list.set_defaults(func=cmd_list)

    # patterns (with sub-subcommands)
    p_patterns = subparsers.add_parser("patterns", help="Manage design patterns")
    patterns_sub = p_patterns.add_subparsers(dest="patterns_command", required=True)

    # patterns add
    pp_add = patterns_sub.add_parser("add", help="Manually add a pattern")
    pp_add.add_argument("pattern_text", help="Pattern statement text")
    pp_add.add_argument("--name", required=True, help="Short pattern name (3-5 words)")
    pp_add.add_argument("--category", required=True, help=f"Category from: {', '.join(TAG_VOCABULARY)}")
    pp_add.add_argument("--evidence", required=True, help="Comma-separated filenames of evidence docs")
    pp_add.add_argument("--tags", help="Additional comma-separated tags")
    pp_add.set_defaults(func=cmd_patterns_add)

    # patterns extract
    pp_extract = patterns_sub.add_parser("extract", help="AI-extract patterns from indexed decisions")
    pp_extract.add_argument("--tags", help="Filter source docs by tags")
    pp_extract.add_argument("--repo", help="Filter source docs by repo")
    pp_extract.add_argument("--min-evidence", type=int, default=2, help="Minimum decisions per cluster (default 2)")
    pp_extract.add_argument("--cluster-threshold", type=float, default=0.70, help="Cosine similarity threshold for clustering (default 0.70)")
    pp_extract.add_argument("--dry-run", action="store_true", help="Show clusters without persisting")
    pp_extract.set_defaults(func=cmd_patterns_extract)

    # patterns query
    pp_query = patterns_sub.add_parser("query", help="Semantic search over patterns")
    pp_query.add_argument("search_text", help="What to search for")
    pp_query.add_argument("--top-k", type=int, default=5, help="Number of results")
    pp_query.add_argument("--category", help="Filter by category")
    pp_query.add_argument("--status", help="Filter by status (active/draft/superseded)")
    pp_query.add_argument("--min-evidence", type=int, default=0, help="Minimum evidence count")
    pp_query.set_defaults(func=cmd_patterns_query)

    # patterns list
    pp_list = patterns_sub.add_parser("list", help="List all patterns")
    pp_list.add_argument("--category", help="Filter by category")
    pp_list.add_argument("--status", help="Filter by status")
    pp_list.add_argument("--confidence", help="Filter by confidence (human/confirmed/ai)")
    pp_list.set_defaults(func=cmd_patterns_list)

    # patterns show
    pp_show = patterns_sub.add_parser("show", help="Show pattern details")
    pp_show.add_argument("pattern_id", help="Pattern ID or name")
    pp_show.set_defaults(func=cmd_patterns_show)

    # patterns confirm
    pp_confirm = patterns_sub.add_parser("confirm", help="Promote a draft pattern to active")
    pp_confirm.add_argument("pattern_id", help="Pattern ID or name")
    pp_confirm.set_defaults(func=cmd_patterns_confirm)

    # patterns supersede
    pp_supersede = patterns_sub.add_parser("supersede", help="Mark pattern as superseded")
    pp_supersede.add_argument("old_id", help="Pattern ID or name to supersede")
    pp_supersede.add_argument("new_id", help="Pattern ID or name of replacement")
    pp_supersede.set_defaults(func=cmd_patterns_supersede)

    # patterns refresh
    pp_refresh = patterns_sub.add_parser("refresh", help="Re-evaluate pattern evidence")
    pp_refresh.add_argument("pattern_id", nargs="?", help="Pattern ID or name (omit with --all)")
    pp_refresh.add_argument("--all", action="store_true", help="Refresh all patterns")
    pp_refresh.set_defaults(func=cmd_patterns_refresh)

    # patterns remove
    pp_remove = patterns_sub.add_parser("remove", help="Remove a pattern")
    pp_remove.add_argument("pattern_id", help="Pattern ID or name")
    pp_remove.add_argument("--force", action="store_true", help="Actually delete")
    pp_remove.set_defaults(func=cmd_patterns_remove)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
