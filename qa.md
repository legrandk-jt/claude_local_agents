# QA Log

Test results and observations from executing the local agents setup plan.

---

## [PHASE-1 / PHASE-2] Ollama Installation & Model Smoke Test

**Date**: 2026-03-17

### Ollama installation issue: Rosetta 2 vs ARM native

**What happened**: Installed Ollama via Homebrew (`brew install ollama`). The machine has only the Intel Homebrew installed at `/usr/local`, so the binary was x86_64 running under Rosetta 2 emulation — no Metal GPU acceleration.

**Symptom**: First generation returned **0.8 tok/sec** instead of the expected 15–25 tok/sec.

**Fix**: Uninstalled Homebrew Ollama, downloaded the official `.app` from ollama.com (universal binary, arm64 + x86_64), installed to `/Applications`, created a symlink at `/usr/local/bin/ollama`.

**Secondary issue**: macOS Gatekeeper blocked the binary with "Ollama is damaged and can't be opened" because it was downloaded via `curl` (quarantine attribute set). `xattr -dr com.apple.quarantine /Applications/Ollama.app` failed on `_CodeSignature` files (expected — macOS protects code signatures). Fix: opened the `.app` via Finder to trigger Gatekeeper approval dialog.

**Final result after fix**:
- Binary: ARM64 native (`/Applications/Ollama.app/Contents/Resources/ollama`)
- Cold start (first generation, model loading): **5 tok/sec**
- Warm (model already in memory): **13 tok/sec** ✅

**Lesson**: On Apple Silicon Macs, always install Ollama from the official `.app` or ensure Homebrew is the ARM native version at `/opt/homebrew`. The Intel Homebrew at `/usr/local` installs x86_64 binaries that run under Rosetta — no Metal acceleration.

---

### Model smoke test

**Model**: `qwen2.5-coder:14b` Q4_K_M (9.0 GB)

**Test prompt**: "Write a Python function that checks if a string is a palindrome. Only return the code."

**Result**:
```python
def is_palindrome(s):
    normalized_str = s.replace(" ", "").lower()
    return normalized_str == normalized_str[::-1]
```

**Metrics**: 58 tokens, 13 tok/sec warm, 6 seconds total. Output is correct and clean. ✅

---

## [Pre-PHASE-3] E2E Test: Local Model Writing the MCP Server

**Date**: 2026-03-17

**Goal**: Validate that the local model (`qwen2.5-coder:14b`) can write production-usable code when delegated a well-defined task. Used as a proxy for PHASE-3 validation before building the real MCP integration.

**Task given to the model**: Write a Python MCP server that wraps Ollama, exposes 3 tools (`ollama_generate`, `ollama_chat`, `ollama_list_models`), uses `httpx.AsyncClient`, handles errors gracefully, and runs via stdio transport.

**Output file**: `mcp_server.py`

### Round 1 — Initial generation

**What the model got right** (first attempt):
- Core Ollama API calls (`/api/generate`, `/api/chat`, `/api/tags`) — correct endpoints, correct JSON structure
- `stream: false` to get synchronous responses
- `httpx.AsyncClient` with timeout
- Error handling pattern (catch and return string, no raise)
- `ollama_list_models` response parsing (`response.json().get("models", [])`)

**Bugs in round 1**:
- Import wrong: `from mcp.server import Server, stdio_server` — `stdio_server` lives in `mcp.server.stdio`
- `Server(tools)` — passed a dict to the constructor instead of a name string
- Tool registration: used a class-based pattern (`class MyServer(Server)`) instead of module-level decorators
- `ollama_chat` response parsing wrong: tried to iterate over `response.json().get("messages", [])` as a list — Ollama returns a single `{"message": {"role": "assistant", "content": "..."}}` object
- `ollama_list_models`: iterated over `response.json()` root dict instead of `response.json().get("models", [])`

### Round 2 — Targeted bug fix

Sent the model a prompt listing all 5 bugs explicitly with the correct behavior described.

**What improved**: Fixed `stdio_server` import, fixed `ollama_list_models` parsing, attempted tool registration with decorators.

**Remaining bugs after round 2**:
- `Server` import still missing
- `ollama_chat` response parsing still wrong (introduced a new broken pattern)
- Decorator pattern attempted inside a class definition — references `server` before it's created, invalid Python

### Round 3 — Final targeted fix

Sent the model the remaining 3 bugs with exact descriptions of the correct MCP SDK pattern (`@server.list_tools()`, `@server.call_tool()` as module-level decorators, `Tool` with `inputSchema`, `TextContent` with `type="text"`).

**Result**: All bugs resolved. Final code is structurally correct:
- Correct imports
- `server = Server(name="OllamaServer")` at module level
- `@server.list_tools()` and `@server.call_tool()` as module-level decorators
- `Tool` objects with proper `inputSchema`
- `TextContent(text=response, type="text")` return format
- `ollama_chat` correctly extracts `response.json()["message"]["content"]`

### Summary

| Aspect | Result |
|--------|--------|
| Rounds needed | 3 |
| Generic Python / HTTP logic | ✅ Correct from round 1 |
| MCP SDK-specific patterns | ❌ Required 3 rounds of explicit guidance |
| Ollama API response structure | ⚠️ Partially correct (generate OK, chat wrong until round 3) |
| Error handling | ✅ Correct from round 1 |
| Final output usable? | ✅ Yes |

---

## [Pre-PHASE-3] Cost Estimate — E2E Token Usage Analysis

**Date**: 2026-03-17

Measured token usage by re-running the 3 Ollama rounds with full JSON capture. Claude tokens estimated from the observable conversation (prompts constructed, responses reviewed, framing text).

### Measured: Ollama token counts (exact)

| Round | Input tokens | Output tokens | Cost |
|-------|-------------|---------------|------|
| 1 — initial generation | 349 | 587 | $0.000 |
| 2 — bug fix | 712 | 591 | $0.000 |
| 3 — final fix | 743 | 752 | $0.000 |
| **TOTAL** | **1,804** | **1,930** | **$0.000** |

### Estimated: Claude token breakdown

| Component | Tokens | Notes |
|-----------|--------|-------|
| Claude output — prompts to Ollama | 1,804 | Exactly what Ollama received as input |
| Claude output — curl scaffolding | 150 | ~50 tokens × 3 rounds |
| Claude output — review text | 400 | Bug analysis between rounds 2 and 3 |
| Claude output — framing | 150 | Initial explanation + final message |
| **Claude output total** | **2,504** | |
| Claude input — user task | 50 | |
| Claude input — Ollama responses reviewed | 1,930 | Code Claude had to read and validate |
| Claude input — conversation context | 400 | Prior turns |
| **Claude input total** | **2,380** | |

Pricing used: Claude Sonnet 4.6 — $3.00/1M input, $15.00/1M output.

### Results

```
─────────────────────────────────────────────────────────────
Scenario: WITH local model, 3 correction rounds (Bash+curl)
─────────────────────────────────────────────────────────────
Claude   input:  2,380 tokens   $0.00714
Claude   output: 2,504 tokens   $0.03756
Ollama   total:  3,734 tokens   $0.000    (free)
─────────────────────────────────────────────────────────────
Actual cost:   $0.04470
─────────────────────────────────────────────────────────────

─────────────────────────────────────────────────────────────
Scenario: WITHOUT local model (Claude generates code directly)
─────────────────────────────────────────────────────────────
Claude   input:     50 tokens   $0.00015
Claude   output: 1,930 tokens   $0.02895
─────────────────────────────────────────────────────────────
Baseline cost: $0.02910
─────────────────────────────────────────────────────────────

Result: +$0.01560  (+54%)  ⚠️  MORE expensive than Claude alone
```

### Why the local model was more expensive here

The fundamental economics of delegating via Bash+curl:

- Claude still outputs a **prompt** to Ollama (similar token count to the code itself)
- Claude adds **curl scaffolding** overhead (~150 tokens/call)
- Claude must **read and validate** every Ollama response (adds input tokens)
- Each correction round multiplies the overhead

The local model only pays off economically if either:
1. The task completes in **1 round** with correct output, AND the prompt is much shorter than the generated code
2. The **MCP path** is used (reduces scaffolding overhead from ~150 to ~40 tokens/call)

### Projections

```
─────────────────────────────────────────────────────────────
Happy path: 1 round, Bash+curl
─────────────────────────────────────────────────────────────
Actual:   $0.01225   Baseline: $0.00896   Difference: +37%

Happy path: 1 round, MCP
─────────────────────────────────────────────────────────────
Actual:   $0.01060   Baseline: $0.00896   Difference: +18%
─────────────────────────────────────────────────────────────
```

Even in the happy path (1 round, no corrections), using the local model via Bash+curl costs ~37% more than Claude alone. With MCP the gap narrows to ~18%.

### Does MCP help? Yes, but not for token savings

MCP saves ~110 output tokens per call vs Bash+curl ($0.00165/call). The real value of MCP is **not** token savings per se — it's:
- Cleaner invocation (no curl JSON escaping overhead)
- Structured tool interface (Claude makes cleaner decisions about when to delegate)
- Reliability (less prompt fragility, no shell escaping issues)

### Revised understanding of the value proposition

| Benefit | Expected | Reality |
|---------|----------|---------|
| Token cost savings | High | Low to none for small tasks |
| Data privacy (code stays local) | ✅ | ✅ Confirmed |
| Offline capability | ✅ | ✅ Confirmed |
| Cost savings at high volume (1000s of calls) | TBD | Plausible with MCP + happy path |
| Avoiding niche SDK knowledge errors | ❌ Assumed OK | ❌ 3 rounds needed |

**Honest conclusion**: For individual tasks, the local model does NOT save tokens — it adds orchestration overhead. The real value case is: (1) keeping generated code private/local, and (2) high-volume repetitive tasks with well-known libraries where the model reliably completes in 1 round.

---

### Conclusions

1. **Good for well-known APIs and generic code**: HTTP calls, JSON parsing, asyncio patterns, error handling — the model produces correct code on the first attempt for these.

2. **Struggles with niche/specific SDKs**: The MCP Python SDK is likely underrepresented in training data. The model defaulted to plausible-but-wrong patterns (class inheritance, dict-based tool registration) that don't match the actual SDK API.

3. **Responds well to precise feedback**: When bugs are described with the exact correct behavior (not just "fix this"), the model corrects them reliably.

4. **Implication for task routing**: Delegate to the local model tasks involving well-known libraries (stdlib, requests, SQLAlchemy, pytest, etc.). For niche SDKs or internal APIs the model hasn't seen, either write the scaffolding yourself or provide the exact API signature in the prompt.

5. **3 rounds is acceptable for a one-time task** — for repetitive tasks (generating 20 similar classes), the model would likely need only 1 round once the pattern is established in the prompt.
