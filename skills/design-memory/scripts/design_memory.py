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
"""

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import time
import uuid
from datetime import datetime
from pathlib import Path

import chromadb
import yaml

STORE_PATH = os.environ.get("DESIGN_MEMORY_STORE", os.path.expanduser("~/.design-memory"))
COLLECTION_NAME = "design_docs"
MAX_FILE_SIZE = 500 * 1024  # 500KB
V2_MARKER = "design_memory_v2_gemini"
METRICS_FILE = os.path.join(STORE_PATH, "metrics.jsonl")


class MetricsLogger:
    """Append-only JSONL logger for design-memory usage metrics.

    Each event is a single JSON line written to ~/.design-memory/metrics.jsonl.
    The session_id is read from CLAUDE_SESSION_ID env var if available, otherwise
    a per-process fallback is generated.
    """

    def __init__(self):
        self._session_id = os.environ.get("CLAUDE_SESSION_ID", f"local-{uuid.uuid4().hex[:8]}")

    def log(self, event_type: str, **fields):
        """Write a single metrics event."""
        os.makedirs(STORE_PATH, exist_ok=True)
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "event": event_type,
            **fields,
        }
        try:
            with open(METRICS_FILE, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass  # Metrics are best-effort; never block the main operation


_metrics = MetricsLogger()


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
    t0 = time.monotonic()
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

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _metrics.log(
        "index",
        files_indexed=indexed_count,
        total_chunks=collection.count(),
        decisions_by_tier=total_tiers,
        repo=args.repo or "auto",
        latency_ms=elapsed_ms,
    )

    print(f"\nIndexed {indexed_count} document(s) into {STORE_PATH}")
    print(f"Collection now has {collection.count()} total chunks")
    if any(total_tiers.values()):
        tier_summary = ", ".join(f"{v} {k}" for k, v in total_tiers.items() if v > 0)
        print(f"Decision blocks found: {tier_summary}")


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
    t0 = time.monotonic()
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
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _metrics.log(
            "query",
            search_text=args.search_text,
            results_returned=0,
            zero_results=True,
            latency_ms=elapsed_ms,
        )
        print("No matching documents found.")
        return

    similarities = [e["similarity"] for e in deduped]
    cross_repo_sources = set(e["meta"].get("repo") for e in deduped)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _metrics.log(
        "query",
        search_text=args.search_text,
        results_returned=len(deduped),
        zero_results=False,
        avg_similarity=sum(similarities) / len(similarities),
        max_similarity=max(similarities),
        min_similarity=min(similarities),
        repos_in_results=list(cross_repo_sources),
        cross_repo_hits=len(cross_repo_sources) > 1,
        latency_ms=elapsed_ms,
    )

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
    t0 = time.monotonic()
    context_id = f"ctx-{uuid.uuid4().hex[:12]}"
    client = get_client()
    collection = get_collection(client)

    if collection.count() == 0:
        _metrics.log("context", context_id=context_id, search_text=args.search_text,
                     results_returned=0, latency_ms=int((time.monotonic() - t0) * 1000))
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
        _metrics.log("context", context_id=context_id, search_text=args.search_text,
                     results_returned=0, latency_ms=int((time.monotonic() - t0) * 1000))
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

    # Log metrics for context generation
    similarities = [e["similarity"] for e in deduped]
    total_decisions_surfaced = sum(len(tier_decisions[t]) for t in tier_decisions)
    human_decisions_surfaced = len(tier_decisions["human"])
    docs_surfaced = [e["meta"].get("filename", "?") for e in deduped]
    cross_repo_sources = set(e["meta"].get("repo") for e in deduped)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _metrics.log(
        "context",
        context_id=context_id,
        search_text=args.search_text,
        results_returned=len(deduped),
        decisions_surfaced=total_decisions_surfaced,
        human_decisions_surfaced=human_decisions_surfaced,
        confirmed_decisions_surfaced=len(tier_decisions["confirmed"]),
        ai_decisions_surfaced=len(tier_decisions["ai"]),
        avg_similarity=sum(similarities) / len(similarities),
        max_similarity=max(similarities),
        docs_surfaced=docs_surfaced,
        repos_in_results=list(cross_repo_sources),
        cross_repo_hits=len(cross_repo_sources) > 1,
        latency_ms=elapsed_ms,
    )

    # Output as structured context block for prompt injection
    print("<prior_design_decisions>")
    print(f"context_id: {context_id}")
    print(f"The following prior design decisions are relevant to: {args.search_text}")
    print(f"Found {len(deduped)} relevant document(s) from the team's design history.\n")

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
    print()
    print(f"<influence_tracking context_id=\"{context_id}\">")
    print("After completing this design session, report which surfaced decisions influenced your output.")
    print("Run: design_memory.py report-influence \\")
    print(f"  --context-id {context_id} \\")
    print("  --used \"Decision text 1|Decision text 2\" \\")
    print("  --outcome aligned|diverged|partial \\")
    print("  --notes \"Brief explanation of how decisions were used or why you diverged\"")
    print("</influence_tracking>")
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
    _metrics.log("remove", doc_id=args.doc_id, chunks_removed=len(ids_to_remove))
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


def cmd_report_influence(args):
    """Record which surfaced decisions actually influenced the calling agent's output.

    This is the callback API for closing the metrics loop. The calling agent
    (e.g. superpowers brainstorm) invokes this after completing a design session
    to report which decisions from the context output were used, ignored, or
    diverged from.
    """
    decisions_used = [d.strip() for d in args.used.split("|") if d.strip()] if args.used else []

    _metrics.log(
        "influence",
        context_id=args.context_id,
        outcome=args.outcome,
        decisions_used=decisions_used,
        decisions_used_count=len(decisions_used),
        notes=args.notes or "",
    )

    print(f"Influence report recorded for context {args.context_id}")
    print(f"  Outcome: {args.outcome}")
    print(f"  Decisions used: {len(decisions_used)}")
    if args.notes:
        print(f"  Notes: {args.notes}")


def cmd_metrics(args):
    """Summarize metrics from the JSONL log."""
    if not os.path.exists(METRICS_FILE):
        print("No metrics recorded yet.")
        return

    events = []
    with open(METRICS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not events:
        print("No metrics recorded yet.")
        return

    # Filter by --since if provided
    if args.since:
        events = [e for e in events if e.get("timestamp", "") >= args.since]
        if not events:
            print(f"No events since {args.since}.")
            return

    # Overall counts by event type
    event_counts = {}
    for e in events:
        t = e.get("event", "unknown")
        event_counts[t] = event_counts.get(t, 0) + 1

    unique_sessions = set(e.get("session_id") for e in events)
    first_event = events[0].get("timestamp", "?")
    last_event = events[-1].get("timestamp", "?")

    print(f"=== Design Memory Metrics ===")
    print(f"Period: {first_event[:10]} to {last_event[:10]}")
    print(f"Total events: {len(events)}")
    print(f"Unique sessions: {len(unique_sessions)}")
    print()

    print("Event counts:")
    for event_type, count in sorted(event_counts.items()):
        print(f"  {event_type}: {count}")
    print()

    # Query & context metrics
    query_events = [e for e in events if e["event"] in ("query", "context")]
    if query_events:
        print("--- Retrieval Metrics ---")
        total_queries = len(query_events)
        zero_result = sum(1 for e in query_events if e.get("zero_results") or e.get("results_returned", 0) == 0)
        avg_results = sum(e.get("results_returned", 0) for e in query_events) / total_queries
        sims = [e.get("avg_similarity") for e in query_events if e.get("avg_similarity") is not None]
        avg_sim = sum(sims) / len(sims) if sims else 0
        max_sims = [e.get("max_similarity") for e in query_events if e.get("max_similarity") is not None]
        avg_max_sim = sum(max_sims) / len(max_sims) if max_sims else 0
        cross_repo = sum(1 for e in query_events if e.get("cross_repo_hits"))
        latencies = [e.get("latency_ms") for e in query_events if e.get("latency_ms") is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        print(f"  Total queries (query+context): {total_queries}")
        print(f"  Zero-result queries: {zero_result} ({zero_result/total_queries*100:.0f}%)")
        print(f"  Avg results per query: {avg_results:.1f}")
        print(f"  Avg similarity score: {avg_sim:.3f}")
        print(f"  Avg top similarity: {avg_max_sim:.3f}")
        print(f"  Cross-repo hits: {cross_repo} ({cross_repo/total_queries*100:.0f}%)")
        print(f"  Avg latency: {avg_latency:.0f}ms")
        print()

    # Context-specific metrics
    context_events = [e for e in events if e["event"] == "context"]
    if context_events:
        print("--- Decision Surfacing ---")
        total_ctx = len(context_events)
        total_surfaced = sum(e.get("decisions_surfaced", 0) for e in context_events)
        human_surfaced = sum(e.get("human_decisions_surfaced", 0) for e in context_events)
        confirmed_surfaced = sum(e.get("confirmed_decisions_surfaced", 0) for e in context_events)
        ai_surfaced = sum(e.get("ai_decisions_surfaced", 0) for e in context_events)

        print(f"  Context calls: {total_ctx}")
        print(f"  Total decisions surfaced: {total_surfaced}")
        print(f"    Human: {human_surfaced}  Confirmed: {confirmed_surfaced}  AI: {ai_surfaced}")
        if total_ctx > 0:
            print(f"  Avg decisions per context call: {total_surfaced / total_ctx:.1f}")
        print()

    # Influence metrics
    influence_events = [e for e in events if e["event"] == "influence"]
    if influence_events:
        print("--- Influence Tracking ---")
        total_reports = len(influence_events)
        outcomes = {}
        for e in influence_events:
            o = e.get("outcome", "unknown")
            outcomes[o] = outcomes.get(o, 0) + 1
        total_used = sum(e.get("decisions_used_count", 0) for e in influence_events)

        # Match influence reports to their context calls
        context_ids_with_influence = set(e.get("context_id") for e in influence_events)
        context_ids_total = set(e.get("context_id") for e in context_events if e.get("context_id"))
        report_rate = len(context_ids_with_influence) / len(context_ids_total) * 100 if context_ids_total else 0

        print(f"  Influence reports: {total_reports}")
        print(f"  Report-back rate: {report_rate:.0f}% of context calls")
        print(f"  Outcomes:")
        for outcome, count in sorted(outcomes.items()):
            print(f"    {outcome}: {count}")
        print(f"  Total decisions marked as used: {total_used}")
        if total_reports > 0:
            print(f"  Avg decisions used per report: {total_used / total_reports:.1f}")
        print()

    # Index metrics
    index_events = [e for e in events if e["event"] == "index"]
    if index_events:
        print("--- Indexing ---")
        total_indexed = sum(e.get("files_indexed", 0) for e in index_events)
        all_tiers = {"human": 0, "confirmed": 0, "ai": 0}
        for e in index_events:
            tiers = e.get("decisions_by_tier", {})
            for t in all_tiers:
                all_tiers[t] += tiers.get(t, 0)
        latencies = [e.get("latency_ms") for e in index_events if e.get("latency_ms") is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        print(f"  Index operations: {len(index_events)}")
        print(f"  Files indexed: {total_indexed}")
        print(f"  Decisions indexed: human={all_tiers['human']}, confirmed={all_tiers['confirmed']}, ai={all_tiers['ai']}")
        print(f"  Avg index latency: {avg_latency:.0f}ms")
        print()

    # Knowledge base coverage (from latest status or collection)
    # Doc hit rate: which indexed docs have been returned in queries
    all_docs_surfaced = set()
    for e in query_events:
        for doc in e.get("docs_surfaced", []):
            all_docs_surfaced.add(doc)
    if all_docs_surfaced:
        try:
            client = get_client()
            collection = get_collection(client)
            all_data = collection.get(include=["metadatas"])
            all_indexed_docs = set(m.get("filename") for m in all_data["metadatas"])
            hit_rate = len(all_docs_surfaced & all_indexed_docs) / len(all_indexed_docs) * 100 if all_indexed_docs else 0
            print("--- Knowledge Base Coverage ---")
            print(f"  Indexed docs: {len(all_indexed_docs)}")
            print(f"  Docs hit by queries: {len(all_docs_surfaced & all_indexed_docs)}")
            print(f"  Hit rate: {hit_rate:.0f}%")
            never_hit = all_indexed_docs - all_docs_surfaced
            if never_hit and len(never_hit) <= 10:
                print(f"  Never queried: {', '.join(sorted(never_hit))}")
            elif never_hit:
                print(f"  Never queried: {len(never_hit)} docs")
        except Exception:
            pass  # Best-effort; don't fail metrics if store is unavailable


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

    # report-influence
    p_influence = subparsers.add_parser(
        "report-influence",
        help="Report which surfaced decisions influenced the calling agent's output",
    )
    p_influence.add_argument("--context-id", required=True, help="The context_id from the context command output")
    p_influence.add_argument(
        "--used",
        default="",
        help="Pipe-delimited list of decision texts that were used (e.g. 'Use Resilience4j|3 max retries')",
    )
    p_influence.add_argument(
        "--outcome",
        required=True,
        choices=["aligned", "diverged", "partial", "no-relevant-decisions"],
        help="How the surfaced decisions related to the final output",
    )
    p_influence.add_argument("--notes", default="", help="Brief explanation of how decisions were used or why you diverged")
    p_influence.set_defaults(func=cmd_report_influence)

    # metrics
    p_metrics = subparsers.add_parser("metrics", help="Show usage and impact metrics summary")
    p_metrics.add_argument("--since", help="Only show events since this ISO date (e.g. 2026-03-01)")
    p_metrics.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
