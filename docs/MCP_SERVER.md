# LawAI over MCP

`backend/mcp_server.py` exposes the same services the HTTP API exposes, to a client that
speaks Model Context Protocol. Every tool is a thin adapter over something already measured
and already tested; nothing here reimplements retrieval, classification or verification.

---

## The one design constraint

**Grounding travels with the tools.**

`ask` returns typed claims with their per-claim verdicts and the abstention — never retrieved
text. That is the whole point. A model on the other end of this protocol will turn a
retrieved paragraph into a confident sentence about someone's liberty, and it will do so
*outside* the verifier. So the boundary sits exactly where the HTTP API puts it: the caller
receives what survived checking, what was removed, and why.

The corollary is that **there is no `search_corpus` tool.** It would be the most convenient
thing to add here and the most dangerous, for that reason. A test asserts its absence,
because an absence is exactly what gets added back by someone who does not know why it is
missing.

---

## Running it

From `backend/` — imports are rooted there, as with everything else in this project.

```bash
python mcp_server.py                    # stdio (Claude Desktop)
python mcp_server.py --http             # streamable HTTP on 127.0.0.1:8765
python mcp_server.py --http --port 9000
```

`AIML_API_KEY` is needed for `ask` and `draft_document`. Every other tool is an exact lookup
over committed data and works without credentials.

Logging goes to **stderr**, deliberately: stdio transport speaks JSON-RPC on stdout, and a
log line written there corrupts the stream so the client sees a protocol error rather than a
log.

## Claude Desktop

`~/.config/Claude/claude_desktop_config.json` on Linux,
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS:

```json
{
  "mcpServers": {
    "lawai": {
      "command": "/absolute/path/to/LawAI/backend/venv/bin/python",
      "args": ["/absolute/path/to/LawAI/backend/mcp_server.py"],
      "cwd": "/absolute/path/to/LawAI/backend",
      "env": {
        "AIML_API_KEY": "sk-...",
        "ENABLE_LIVE_JUDICIARY": "true"
      }
    }
  }
}
```

`cwd` matters: `LegalDataLoader` resolves the corpus relative to `backend/`, and
`VectorService` defaults to a CWD-relative `./chroma_db`.

---

## The tools

| Tool | What it does | Model call? |
|---|---|---|
| **`ask`** | Answers a question as checked claims, with verdicts and abstention. **Use this for anything needing a statement of law.** | yes |
| `get_section` | Full text of one BNS/BNSS/BSA section by citation | no |
| `classify_offence` | Cognizable, bailable, trying court, custody timeline — from the First Schedule | no |
| `explain_doctrine` | Curated doctrine on a section, with lineage and contested flags | no |
| `what_replaced` | IPC/CrPC/Evidence Act section → its 2023 replacement | no |
| `search_case_law` | Live judiciary search. **Retrieved, not curated** | no |
| `fetch_judgment` | One judgement's text from a live source | no |
| `draft_document` | Generates a document, disclaimer attached | yes |
| `list_document_types` | What `draft_document` accepts | no |
| `corpus_info` | Counts and scope, so a client can tell what is out of scope before asking | no |

Seven of the ten make no model call at all: they are exact lookups over committed data, so
they are free, identical on every run, and cannot invent anything.

### What the tools refuse

Each refusal is the same one the HTTP API makes, for the same reason:

- **A section that does not exist** — `get_section("BNS", "999")` says the BNS runs to 358
  rather than returning nothing, so a client can tell "wrong number" from "lookup failed".
- **An unresolved classification** — 27 First Schedule rows defer to another offence and come
  back `null` with the Schedule's own wording beside them. A guessed "bailable" is the most
  dangerous value this system can emit.
- **A repealed number with no recorded mapping** — refused rather than assumed. The acts
  renumbered, so returning the same number turns a miss into a confident wrong answer.
- **An out-of-scope question** — `ask` abstains. Tax, GST, contract and civil matters are not
  in the corpus, and `corpus_info` says so up front.

### What travels with a live result

`search_case_law` and `fetch_judgment` return material that **nothing downstream checks**.
Each hit carries its court, date and source URL, and the tool description says so, because
the description is the only place a client is told. Do not blend these with corpus output.

---

## Server instructions

The server sends a client three things it cannot infer:

1. the corpus is the **2023 codes**, not the repealed IPC/CrPC/Evidence Act;
2. prefer `ask` over assembling an answer from the lookup tools;
3. **preserve the epistemic class.** Enacted text, a procedural classification, what a court
   held, and the model's own reasoning are different kinds of statement, and a client that
   flattens them back into prose undoes the whole pipeline at the last step.

## Related

- `docs/ARCHITECTURE.md` — what each service does
- `docs/ATTRIBUTION_GAP.md` — why `ask` never says a case is an authority on a section unless
  the graph records it
- `CLAUDE.md` — the operational guide
