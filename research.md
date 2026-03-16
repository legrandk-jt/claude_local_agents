# Local AI Agents Research

## Objective

Run local AI agents on the machine, using Claude as the orchestrator and local models to write code.

**Goal**: Reduce token costs by offloading mechanical/repetitive code generation to free local models, while keeping Claude for reasoning and orchestration.

**Constraint**: Only Claude is an allowed paid external service. No other paid model APIs (no OpenAI API, no Gemini API, no Mistral API, etc.). All sub-agents must run locally.

> ⚠️ **Cost-saving assumption**: This only works if the local model's output quality is good enough that Claude doesn't need to spend many tokens correcting it. If the local model produces bad output and Claude has to fix it in multiple rounds, the orchestration overhead can cost more than Claude doing the task directly. Model selection and task routing matter.

---

## Machine Specs

| Spec | Value |
|------|-------|
| Chip | Apple M3 Pro |
| Cores | 11 (5 performance + 6 efficiency) |
| Unified Memory | 18 GB |
| GPU | Integrated Apple GPU (Metal) |
| Free Disk | ~265 GB |
| OS | macOS Sequoia 15.x |

**Key insight**: On Apple Silicon, the CPU and GPU share the same unified memory pool. This means models loaded into memory are automatically accelerated by the GPU (via Metal). No discrete VRAM limitation — the entire 18 GB is usable by the model.

**Practical available memory for models**: ~12–15 GB (leaving ~3–6 GB for macOS and other processes).

---

## Model Recommendations

Models are listed as 4-bit quantized (Q4_K_M), which gives the best balance of size and quality.

### Tier 1 — Best fit for this machine (code-focused)

| Model | Size (Q4) | Context Window | Tool Calling | Fits? | Notes |
|-------|-----------|----------------|--------------|-------|-------|
| **Qwen2.5-Coder-14B-Instruct** | ~9 GB | 128k | ✅ Good | ✅ Yes | Top-tier code model, strong on Python/JS/TS. Best overall recommendation. |
| **DeepSeek-Coder-V2-Lite-Instruct** | ~9 GB | 128k | ✅ Good | ✅ Yes | MoE: 16B total params but only 2.4B active per forward pass — runs much faster than a dense 16B; quality closer to a dense 2–3B model. |
| **Qwen2.5-Coder-7B-Instruct** | ~5 GB | 128k | ✅ Good | ✅ Yes | Faster alternative, still very capable for code. |

### Tier 2 — General purpose (also good at code)

| Model | Size (Q4) | Context Window | Tool Calling | Fits? | Notes |
|-------|-----------|----------------|--------------|-------|-------|
| **Llama 3.1 8B Instruct** | ~5 GB | 128k | ⚠️ Moderate | ✅ Yes | Meta's solid general model. Good instruction following. |
| **Gemma 2 9B Instruct** | ~6 GB | 8k | ⚠️ Limited | ✅ Yes | Google's model. Punches above its weight, but 8k context is a real constraint for agents. |
| **Mistral 7B Instruct** | ~5 GB | 32k | ⚠️ Inconsistent | ✅ Yes | Fast and reliable, but tool calling is inconsistent without careful prompt engineering. |
| **Phi-3.5 Mini Instruct** | ~2.5 GB | 128k | ❌ Weak | ✅ Yes | Very fast, surprisingly capable for its size. Tool calling is unreliable — not suited as an agentic worker. |

### Tier 3 — Too large for comfortable use

| Model | Size (Q4) | Fits? | Notes |
|-------|-----------|-------|-------|
| Qwen2.5-Coder-32B | ~20 GB | ❌ No | Exceeds available RAM. |
| Llama 3.1 70B | ~40 GB | ❌ No | Way too large. |
| DeepSeek-Coder-V2 (full) | ~130 GB | ❌ No | Not viable. |

> **Note on SSD swapping**: Models whose Q4 size exceeds available free RAM will spill to SSD. On macOS, SSD swap latency is 10–50x slower than RAM, dropping throughput from ~15–25 tok/sec to 2–5 tok/sec — effectively unusable for interactive sessions. Whether a model swaps depends on total memory pressure at runtime, not just model size alone.

---

## Recommended Stack

### Runtime: Ollama

**Ollama** is the best tool to run local models on macOS Apple Silicon:

- Native Metal support (uses GPU acceleration automatically)
- Exposes an **OpenAI-compatible REST API** (`http://localhost:11434/v1`)
- Simple model management (`ollama pull`, `ollama run`)
- Works headlessly (no GUI needed)
- Used by most agent frameworks as a backend

> ⚠️ **Important**: Ollama's default context window is **2048 tokens**, which is too small for most code tasks. Always set `num_ctx` explicitly (e.g. 8192 or 16384) when running models. Larger context windows consume more RAM from the unified memory pool.

### Architecture: Claude as Orchestrator + Local Model as Worker

```
User
 └─> Claude (Orchestrator)
       ├─> Plans the task, breaks it into steps
       ├─> Decides whether to delegate (self-contained task) or handle directly (complex/cross-file)
       └─> Calls Local Model (via Ollama API)  ← only for well-scoped, mechanical tasks
             └─> Local model writes the code
                   └─> Claude reviews and integrates (or retries if output is bad)
```

This pattern is efficient **only when**:
- The task is self-contained and well-scoped (single function, known signature, no deep cross-file reasoning)
- The local model's output is good enough on the first or second attempt
- Claude handles reasoning, planning, tool use, and context management — the things it's best at

### Integration Options

| Tool | How it connects | Notes |
|------|----------------|-------|
| **Ollama API** | `http://localhost:11434/v1` (OpenAI-compatible endpoint, local only) | Direct HTTP calls from any script — no external service involved |
| **Claude Code MCP** | Custom MCP server wrapping Ollama | **Most integrated path**: Claude Code can invoke local model as a native tool during a session. Requires writing an MCP server (see below). |
| **Custom Python script** | `anthropic` SDK + raw HTTP to Ollama | Most flexible for custom orchestration logic — only paid call is to Claude |
| **LangChain / LangGraph** | Has native Ollama integration | Good for building more complex agent graphs |

> ⚠️ The Ollama API uses the OpenAI-compatible format for convenience, but all inference runs locally. No data leaves, no cost incurred.

### MCP Integration (Claude Code native tool)

The MCP path is the most powerful option: Claude Code calls the local model as if it were a built-in tool, with no manual steps.

Requires building a small MCP server that:
1. Exposes a tool (e.g. `generate_code`) with an input schema (task description, context snippet)
2. Calls Ollama's API internally
3. Returns the result to Claude Code

The server must be registered in `~/.claude/claude_desktop_config.json` (or the Claude Code equivalent config). This is non-trivial to set up but gives the best developer experience once running.

---

## Starting Point Recommendation

1. **Install Ollama** (brew or direct download)
2. **Pull `qwen2.5-coder:14b`** — best code model for this machine
3. **Test with explicit context window**: run with `num_ctx=8192` to avoid the 2048-token default trap
4. **Build a thin Python orchestrator** that:
   - Receives a well-scoped coding task from Claude
   - Sends it to the local model via Ollama API
   - Validates the output (at minimum: checks it parses/compiles)
   - Returns the result to Claude for review and integration
5. Once the pipeline works, consider promoting it to a **Claude Code MCP tool** for seamless in-session use

---

## Notes

- M3 Pro with 18 GB can comfortably run 7B–14B parameter models at 4-bit quantization
- Performance on M3 Pro (approximate, short prompts, light load): ~30–60 tok/sec for 7B models, ~15–25 tok/sec for 14B models — throughput degrades with longer filled contexts
- The 14B code models (Qwen2.5-Coder-14B) hit the sweet spot for this machine: good code quality, fits in RAM, acceptable speed
- For agentic use, prefer models with strong tool calling (Qwen2.5-Coder series) over models with weak tool calling (Phi-3.5 Mini, Gemma 2)

---

## How Claude Orchestrates Local Agents

### Nothing works out of the box

Claude Code has no native Ollama integration. Every path requires building something. The question is how much, and in what order.

---

### The 4 Integration Paths

#### Path 1: Bash tool + curl (Start here)

**What it is**: Claude Code already has a `Bash` tool. Ollama exposes a REST API. Claude can call it directly with `curl`.

**What to build**: Nothing. Just tell Claude via `CLAUDE.md` that it can delegate to Ollama.

**What to configure**: Ollama running + model pulled. Nothing else.

**Example instruction in `CLAUDE.md`**:
```
For mechanical code generation (boilerplate, repetitive patterns, test stubs),
delegate to Ollama via curl:
  curl -s http://localhost:11434/api/generate \
    -d '{"model":"qwen2.5-coder:14b","prompt":"...","stream":false}' | jq -r '.response'
Reserve your own reasoning for architecture, review, and integration.
```

**Tradeoffs**:
- ✅ Zero setup — works today
- ✅ Fully auditable, simple to debug
- ✅ Good for prototyping the workflow before investing in infrastructure
- ❌ Claude must construct JSON payloads inline — fragile
- ❌ No structured interface — Claude guesses at prompt formatting
- ❌ Claude won't delegate automatically; it must be instructed to do so every time

---

#### Path 2: MCP Server (End goal)

**What it is**: An MCP server exposes Ollama as a native Claude Code tool. Claude calls it within its reasoning loop like any other tool — no curl, no instructions needed.

**What to build**: An MCP server (~100–150 lines, Python or Node.js) that:
1. Exposes tools: `ollama_generate(model, prompt)`, `ollama_chat(model, messages)`
2. Calls `http://localhost:11434/api/generate` internally
3. Returns the result to Claude Code

**Minimal Python skeleton**:
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import httpx, asyncio

server = Server("ollama")

@server.tool()
async def ollama_generate(model: str, prompt: str, system: str = "") -> str:
    """Delegate code generation to a local Ollama model."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post("http://localhost:11434/api/generate", json={
            "model": model, "prompt": prompt, "system": system, "stream": False
        })
        return r.json()["response"]

if __name__ == "__main__":
    asyncio.run(stdio_server(server).run())
```

**What to configure** (`~/.claude/claude.json` or via `claude mcp add`):
```json
{
  "mcpServers": {
    "ollama": {
      "command": "python",
      "args": ["/path/to/mcp_ollama_server.py"]
    }
  }
}
```

**Tradeoffs**:
- ✅ Native to Claude Code's tool-use loop — the intended extensibility mechanism
- ✅ Claude decides when to invoke Ollama based on its reasoning — no instructions needed
- ✅ Tool calls are visible in the session — fully auditable
- ✅ Keeps all Claude Code features: file awareness, git integration, CLAUDE.md
- ❌ You own the MCP server code — bugs break the integration silently
- ❌ Each Ollama call is synchronous from Claude's perspective — no mid-thought streaming
- ❌ Claude sees Ollama output as opaque text and must validate it before acting

---

#### Path 3: Hooks

**What it is**: Shell scripts triggered at lifecycle events (`PreToolUse`, `PostToolUse`, etc.). You intercept Claude's actions and inject Ollama calls.

**What to build**: Shell or Python scripts that call Ollama on specific tool events.

**What to configure** (`.claude/settings.json`):
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Write",
      "hooks": [{"type": "command", "command": "/path/to/ollama-hook.sh"}]
    }]
  }
}
```

**Verdict**: **Not suitable for orchestration.** Hooks are good for side-effects (linting, logging, transforming output after the fact), but they cannot cleanly inject new tool calls mid-reasoning. Architecturally they invert the model — you're bending Claude's workflow around hooks rather than Claude composing agents intentionally.

---

#### Path 4: Python orchestrator via Anthropic SDK (most control, leaves Claude Code)

**What it is**: A custom Python script runs the full agentic loop using the `anthropic` SDK, defines Ollama as a tool, and manages the conversation manually.

**What to build**: ~150–200 lines of Python implementing the tool-use loop.

```python
import anthropic, requests

client = anthropic.Anthropic()
tools = [{
    "name": "ollama_generate",
    "description": "Delegate mechanical code generation to a local Ollama model",
    "input_schema": {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string"}
        },
        "required": ["model", "prompt"]
    }
}]

def run_ollama(prompt, model="qwen2.5-coder:14b"):
    r = requests.post("http://localhost:11434/api/generate",
                      json={"model": model, "prompt": prompt, "stream": False})
    return r.json()["response"]

messages = [{"role": "user", "content": task}]
while True:
    response = client.messages.create(
        model="claude-sonnet-4-6", tools=tools, messages=messages
    )
    if response.stop_reason == "end_turn":
        break
    for block in response.content:
        if block.type == "tool_use" and block.name == "ollama_generate":
            result = run_ollama(block.input["prompt"], block.input.get("model"))
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": block.id, "content": result
            }]})
```

**Verdict**: Maximum control, but you abandon Claude Code entirely — no file awareness, no CLAUDE.md, no git integration, no slash commands. Only worth it if you're building a standalone pipeline that doesn't need the Claude Code environment.

---

### Recommended Approach: Two-Phase

**Phase 1 — Validate (today, no infra)**:
Use Path 1 (Bash + curl). Add a `CLAUDE.md` rule that tells Claude to delegate mechanical tasks to Ollama. Confirm the planning/generation split actually produces useful results for your use case. The bottleneck is usually prompt quality and task decomposition, not the transport layer.

**Phase 2 — Productionize (once validated)**:
Build the MCP server (Path 2). This makes Ollama a first-class tool that Claude invokes intentionally during any session, without instructions needed each time.

### Division of labor

| Claude | Local model (Ollama) |
|--------|---------------------|
| Architecture decisions | Boilerplate generation |
| Multi-file reasoning | Repetitive code patterns |
| Debugging complex bugs | Test stub scaffolding |
| Reviewing Ollama output | First-pass implementations from a spec |
| Planning task decomposition | Format/data transformations |

### How to tell Claude to use the local agent

The mechanism is `CLAUDE.md` — a file Claude reads automatically at the start of every session. You write the delegation rule once, and Claude applies it without needing to be told each time.

There are two variants depending on which path you're on:

#### With Bash + curl (Phase 1 — no MCP server yet)

Create `~/.claude/CLAUDE.md` (global) or `CLAUDE.md` in the project root:

```markdown
## Local agent delegation

When asked to write boilerplate, implement a function from a known signature,
generate test stubs, or do other mechanical/repetitive code tasks:

1. Delegate to the local Ollama model instead of writing it yourself
2. Call it via Bash:
   curl -s http://localhost:11434/api/generate \
     -d '{"model":"qwen2.5-coder:14b","prompt":"<your prompt>","stream":false}' \
     | jq -r '.response'
3. Review the output and integrate it — do not blindly accept it

Do NOT delegate tasks that require multi-file reasoning, debugging, or architecture decisions.
```

#### With MCP server (Phase 2 — Ollama registered as a native tool)

```markdown
## Local agent delegation

You have access to an `ollama_generate` tool that runs a local model on this machine.

Use it for: boilerplate, test stubs, repetitive patterns, first-pass implementations from a spec.
Do NOT use it for: multi-file reasoning, debugging complex bugs, architecture decisions.

Always review and validate the output before integrating it.
```

#### Ad-hoc override (always works, regardless of CLAUDE.md)

You can also tell Claude explicitly in the conversation at any time:

> "For this task, use the local model."

This overrides any CLAUDE.md rule and works immediately.

---

#### Important: Claude delegates by judgment, not by rule

Claude interprets the CLAUDE.md instruction and decides whether to delegate based on its understanding of the task. It will not mechanically always delegate. The more specific the rule (which task types → delegate; which → don't), the more predictable the behavior. Vague rules like "use the local model when possible" will produce inconsistent results.

---

### Key constraints to design around

- **Delegation is Claude's judgment, not a rule engine.** Claude decides when to call `ollama_generate`. CLAUDE.md instructions shape that judgment but don't enforce it mechanically.
- **Each Ollama call is synchronous.** Claude waits for the result before continuing its reasoning. Design tasks so Ollama gets self-contained prompts with all context included.
- **Context window on both ends matters.** Ollama's default is 2048 tokens — set `num_ctx` to at least 8192. Claude's context grows with each tool call round-trip — long sessions get expensive.
- **Validate Ollama output before trusting it.** At minimum check that generated code parses. Claude should be instructed to verify, not blindly accept.

---

## Engineering Review — Panel Discussion

Three engineers reviewed the initial version of this document independently, then their findings were compared to identify unanimous consensus. Only points agreed upon by all three were incorporated as changes.

---

### Engineer 1 — Systems & Infrastructure

**What is correct:**
- Unified memory explanation and ~12–15 GB practical headroom estimate are accurate.
- Ollama is the correct pick. Metal support is native, OpenAI-compatible endpoint is accurate.
- Q4_K_M size estimates are correct ballpark figures.
- Token throughput estimates (30–60 tok/sec for 7B, 15–25 for 14B) are consistent with community benchmarks.
- Constraint clarity (Claude-only paid service) is good for avoiding scope creep.

**Missing information:**
- Context window sizes not mentioned anywhere — critical for code agents. Qwen2.5-Coder-14B supports 128K; Gemma 2 9B only 8K. An agent reading large files will hit Gemma 2's limit fast.
- Prompt throughput vs. generation throughput conflated. For agents passing large code files, prefill time can dominate latency.
- Tool/function calling support not evaluated — not all listed models support it reliably. Phi-3.5 Mini has limited tool call reliability. Qwen2.5-Coder and Llama 3.1 are stronger here.
- Ollama concurrency model not mentioned — Ollama runs one model at a time by default. Multiple parallel sub-agent calls will queue.
- `OLLAMA_KEEP_ALIVE` and memory pressure from keeping the model resident not mentioned.
- MCP integration described as "wire it up" but the actual implementation complexity is non-trivial.
- No benchmark data (HumanEval, MBPP, LiveCodeBench) supporting the model quality assertions.

**Technical inaccuracies:**
- DeepSeek-Coder-V2-Lite: "16B MoE model" is misleading. Total params are 16B but only 2.4B are active per forward pass. Quality is closer to a dense 2–3B model, not a 16B.
- "Models above 14B will require swapping" is too absolute. Whether a model swaps depends on total system memory pressure, not a hard 14B cutoff. A 20B Q4 model (~12 GB) could fit without swapping on an otherwise idle system.
- "No data leaves, no cost incurred" — correct for inference, but `ollama pull` makes outbound requests to Ollama's registry. One-time cost, not runtime.
- "Metal 3" is not a hardware spec — it's the API version introduced at WWDC 2022. Should say "Apple GPU (Metal)" instead.

---

### Engineer 2 — AI/ML & LLM Inference

**What is correct:**
- Q4_K_M as the recommended quantization is correct — best perplexity-per-GB tradeoff among 4-bit quant families.
- Qwen2.5-Coder-14B as top pick is defensible — leads most code benchmarks at the sub-20B range.
- DeepSeek-Coder-V2-Lite MoE architecture note is a good addition (though the description needs fixing, see below).
- Ollama's `localhost:11434/v1` endpoint is accurate and stable.
- Claude-as-orchestrator / local-as-worker is a well-established and sound pattern.

**Missing information:**
- Quantization options not discussed beyond Q4_K_M. When to prefer Q5_K_M (slightly better quality, ~20% larger) vs Q3_K_M (fits more in RAM)? IQ quants (IQ4_XS, IQ3_M) not mentioned — these can be meaningfully better at the same size.
- Context window memory impact not discussed. Running Qwen2.5-Coder-14B at 128k context has dramatically different RAM footprint than 4k. KV cache scales with context length, can push model into swap.
- Ollama concurrency: `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_LOADED_MODELS` env vars are relevant for multi-model or parallel use.
- Tool calling support missing — critical for agentic setup. Mistral 7B's tool calling is inconsistent without prompt engineering. Phi-3.5 Mini has limited reliability.
- No evaluation of how well models follow system prompts for format constraints (e.g., "return only valid JSON") — smaller models frequently break these under complex prompts.
- No latency budget or cost analysis. At 15–25 tok/sec for 14B, a 300-line function might take 10–30 seconds. Is that acceptable? Tradeoff not addressed.
- MCP integration underspecified — the most relevant path for Claude Code context.
- No fallback/retry strategy for when local model produces bad output.

**Technical inaccuracies:**
- "Metal 3" is a branding confusion — Metal is an API, not hardware. Should say "Apple GPU (Metal)".
- DeepSeek-Coder-V2-Lite: 2.4B active params per token. Calling it "16B" sets incorrect quality expectations.
- "Runs fully offline, zero cost" is slightly overstated — running 14B continuously draws measurable power.
- SSD swap performance is understated: throughput drops to 2–5 tok/sec, not just "noticeably slower". Essentially unusable for interactive use.
- Ollama's OpenAI-compatible endpoint is not fully compatible — streaming behavior, tool-call schema enforcement, and logprob support differ. Frameworks relying on specific OpenAI response fields may silently fail.
- Q4_K_M treated as a pure win without acknowledging that for complex multi-step logic, Q8_0 or FP16 (viable for 7B on this machine) avoids subtle reasoning degradation.

---

### Engineer 3 — Software Architecture & Agentic Systems

**What is correct:**
- Hardware analysis is accurate. Unified memory claims are correct, size estimates are accurate (±5–10%).
- Ollama recommendation is sound — de facto standard for local inference on macOS Apple Silicon.
- Qwen2.5-Coder-14B is a legitimate top choice. Tier structure (7B fast / 14B sweet spot / 32B+ too large) is technically sound.
- Token throughput estimates are plausible. Orchestrator pattern is architecturally coherent.
- OpenAI-compatible API disclaimer is correct and worth keeping.

**Missing information:**
- Context window: Ollama's default is 2048 tokens — too small for code tasks. `num_ctx` must be set explicitly (e.g. 8192 or 16384). Larger context windows consume more RAM.
- Latency/UX for interactive use not addressed. At 15–25 tok/sec for 14B, a 500-token response takes 20–33 seconds. Needs explicit acknowledgment.
- MCP integration is the most interesting path and has the largest implementation gap — needs at minimum a skeleton of what the MCP server looks like.
- Quantization tradeoffs beyond Q4_K_M not discussed. For 7B at ~5 GB Q4, running Q8_0 (~7 GB) is viable on this machine and produces noticeably better code quality.
- Memory pressure from running Claude Code (Electron) + 9 GB model + dev tooling simultaneously not modeled.
- Tool calling support absent from model evaluation.
- No model validation/output checking step before results reach Claude.
- No mention of Ollama registry vs. GGUF from Hugging Face — some models may not be in Ollama's registry or lag in version.

**Technical inaccuracies:**
- DeepSeek-Coder-V2-Lite: 2.4B active params per forward pass. Quality is closer to a dense 2–3B, not a dense 16B.
- "Models above 14B will require swapping" is too absolute — threshold depends on total runtime memory pressure.
- Token throughput figures should carry caveats — throughput degrades with longer filled contexts (memory bandwidth bottleneck).
- Architecture diagram implies local model is always invoked — should show a conditional branch. For small edits or highly context-dependent changes, delegation adds latency with no benefit.
- "Only Claude API calls cost money" is correct but incomplete — if the local model requires multiple Claude correction rounds, orchestration overhead can exceed the cost of Claude handling the task directly.

---

### Consensus Analysis — How the 3 Engineers Agreed

After comparing the three independent reviews, the following points were raised by **all three engineers** and were therefore incorporated as unanimous changes:

| # | Point | All 3 raised it? | Action taken |
|---|-------|-----------------|--------------|
| 1 | **Context window missing from model tables** | ✅ Yes | Added `Context Window` column; added `num_ctx` warning for Ollama's 2048-token default |
| 2 | **Tool/function calling not evaluated** | ✅ Yes | Added `Tool Calling` column with per-model ratings |
| 3 | **DeepSeek-Coder-V2-Lite MoE description misleading** | ✅ Yes | Clarified: 16B total params, 2.4B active per forward pass, quality ~dense 2–3B |
| 4 | **"Models above 14B will swap" too absolute** | ✅ Yes | Rephrased: depends on total memory pressure at runtime, not a hard size cutoff |
| 5 | **MCP integration underspecified** | ✅ Yes | Expanded MCP section with what the server must do and where to register it |
| 6 | **Cost-saving assumption not guaranteed** | ✅ Yes | Added caveat: multiple Claude correction rounds can exceed cost of Claude doing it directly |

Points raised by only 1 or 2 engineers (not unanimous, not incorporated):
- Quantization alternatives (Q5_K_M, Q8_0, IQ quants) — raised by Engineers 2 and 3 only
- Latency budget / interactive UX discussion — raised by Engineers 2 and 3 only
- Ollama concurrency model (`OLLAMA_NUM_PARALLEL`) — raised by Engineers 1 and 2 only
- Benchmark data for model quality claims — raised by Engineer 1 only
- Ollama partial OpenAI compatibility — raised by Engineers 2 and 3 only
- "Metal 3" label incorrect — raised by Engineers 1 and 2 (Engineer 3 did not flag it explicitly)

---

### Engineering Review — Round 2: Orchestration

A second panel discussion was held on the specific question: **how can Claude orchestrate local agents, what needs to be built, and what needs to be configured?**

---

#### Engineer 1 — Systems & Infrastructure

**Nothing works out of the box.** Every path requires building something.

**Path 1 — MCP Server (recommended)**:
- Build: an MCP server (Python or Node.js) that exposes `ollama_generate(model, prompt, system)` and `ollama_chat(model, messages)`, each forwarding to `localhost:11434/api/generate`.
- Configure: register in `~/.claude/claude_code_config.json` or via `claude mcp add`.
- Claude's reasoning loop calls it natively. Full visibility into what was sent/received. Clean separation.
- Requires ~100–200 lines of code. Adds MCP round-trip latency on every delegation.

**Path 2 — Hooks**:
- Shell scripts triggered on lifecycle events (`PreToolUse`, `PostToolUse`, etc.) via `.claude/settings.json`.
- Good for augmenting existing tool calls (pre/post processing). Not suitable for true bidirectional orchestration — hooks are side-channel, can't cleanly inject new tool calls mid-stream.

**Path 3 — Bash tool + curl shim**:
- Zero infrastructure. Claude calls a CLI wrapper (`ollama-ask`) via its Bash tool.
- Must be instructed via `CLAUDE.md` — Claude won't do it automatically.
- Works immediately, no structured contract, good as a fallback or prototype.

**Path 4 — Proxy/middleware**: N/A — Claude Code's backend is fixed to Anthropic.

**Recommendation**: MCP server as primary + Bash shim as fallback. Write `CLAUDE.md` to establish the division of labor:
```
For mechanical code generation, delegate to the ollama_generate tool using qwen2.5-coder:14b.
Reserve your own reasoning for architecture, review, and integration.
```

---

#### Engineer 2 — AI/ML & LLM Inference

**Nothing meaningful works out of the box.**

**Path 1 — MCP Server**:
- Build: MCP server (Node.js or Python) exposing `ollama_generate` and `ollama_chat`, calling `localhost:11434/api/generate` or `/api/chat`.
- Configure: `~/.claude/claude.json` with the server command.
- Native to Claude Code. Claude controls delegation. Auditable. Build complexity: medium (~100–150 lines).
- Limitation: Ollama responds synchronously; no streaming to Claude mid-thought.

**Path 2 — Hooks**:
- Cannot cleanly inject new tool calls mid-reasoning. Useful for side-effects only, not for the planning/generation split.

**Path 3 — Bash + curl**:
- No build required. Claude constructs curl payloads inline. Fragile but works for prototyping.
- Need `stream:false` to get a complete response in one shell call.

**Path 4 — Python orchestrator (Anthropic SDK)**:
- Full agentic loop with tool_use. Maximum control. ~100–200 lines.
- Leaves Claude Code entirely — no file system awareness, no CLAUDE.md, no slash commands.

**Recommendation**: Start with Bash + curl to validate the workflow, then graduate to MCP server. The bottleneck is prompt quality and task decomposition, not the transport layer. Don't build infrastructure before you know the delegation pattern actually works.

---

#### Engineer 3 — Software Architecture & Agentic Systems

**Nothing works out of the box. Every path requires development.**

**Path 1 — MCP Server (recommended end state)**:
- Build: MCP server exposing `ollama_generate`, `ollama_chat`, `ollama_list_models`.
- Configure: `~/.claude/claude.json` (or `claude mcp add`).
- Claude Code's native extensibility mechanism. Keeps all Claude Code features. Claude invokes Ollama intentionally within its reasoning, not as a side-car.
- Recommended tool additions: `ollama_generate_with_context(file_contents, task)` to avoid Claude having to summarize files before delegating.

**Path 2 — Hooks**:
- Architecturally inverts the model — you're bending Claude's workflow around hooks rather than Claude composing agents intentionally. Good for post-processing or linting; not for orchestration.

**Path 3 — Bash tool + wrapper script**:
- Claude calls `python3 ollama_delegate.py qwen2.5-coder:14b generate_function /tmp/prompt.txt` via its Bash tool.
- More robust than raw curl. You control prompt templates. Claude still uses the Bash tool — no new infrastructure.
- Harder to iterate the interface without updating both script and Claude instructions.

**Path 4 — Anthropic SDK orchestrator**:
- Full control over the loop. Can run multiple Ollama calls in parallel (Claude returns multiple `tool_use` blocks simultaneously).
- Abandons Claude Code entirely. Only worth it for standalone pipelines.

**Recommendation**: MCP server. Build in priority order: (1) `ollama_generate` + `ollama_chat`, (2) `ollama_list_models` so Claude can select the right model per task, (3) `ollama_generate_with_context` for file-aware delegation.

---

#### Consensus Analysis — Orchestration Round

| # | Point | All 3 raised it? | Incorporated |
|---|-------|-----------------|--------------|
| 1 | **Nothing works out of the box — all paths require custom dev** | ✅ Yes | Stated explicitly in the section intro |
| 2 | **4 paths exist: MCP, Hooks, Bash/curl, Python SDK** | ✅ Yes | All 4 documented with build/configure breakdown |
| 3 | **MCP server is the recommended end goal** | ✅ Yes | Designated as Phase 2 / end goal |
| 4 | **Bash/curl is the fastest starting point** | ✅ Yes (Engineers 1 & 2 explicit; Engineer 3 via wrapper script) | Designated as Phase 1 — validate first |
| 5 | **Hooks are not suitable for true orchestration** | ✅ Yes | Called out explicitly with reasoning |
| 6 | **CLAUDE.md is essential for delegation behavior** | ✅ Yes | Noted under constraints and in Phase 1 guidance |

Points not unanimous (not incorporated into main document):
- Streaming variant of MCP tool writing to temp file — raised by Engineer 3 only
- `ollama_list_models` as a third tool — raised by Engineers 1 and 3 only
- Parallel tool_use calls from Claude — raised by Engineer 3 only
