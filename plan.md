# Plan: Local AI Agents with Claude as Orchestrator

## Overview

Two-phase approach based on the research in `research.md`:

- **Phase 1–3**: Prerequisites and validation with Bash + curl (zero infra, proves the concept works)
- **Phase 4–6**: Build and configure the MCP server (production integration)
- **Phase 7–8**: Write the delegation rules in CLAUDE.md
- **Phase 9–10**: End-to-end validation
- **Phase 10b**: Token usage calculator (measure real savings vs. baseline)
- **Phase 11**: Pause for review
- **Phase 12**: Commit

Do not start Phase 4 until Phase 1–3 confirm the delegation pattern actually produces useful output.

---

## TODO

### Phase index

| Label | Description | Group |
|-------|-------------|-------|
| `PHASE-0` | ✅ Initialize git repository | Prerequisites |
| `PHASE-1` | ⚠️ Install Ollama + autostart + disable cloud | Prerequisites |
| `PHASE-2` | ✅ Pull and verify the primary model | Prerequisites |
| `PHASE-3` | Validate delegation via Bash + curl | Validation |
| `PHASE-4` | Set up the Python MCP server project | MCP server |
| `PHASE-5` | Write the MCP server | MCP server |
| `PHASE-6` | Register the MCP server with Claude Code | MCP server |
| `PHASE-7` | Update CLAUDE.md to use the MCP tool | Configuration |
| `PHASE-8` | Configure Ollama context window | Configuration |
| `PHASE-9` | End-to-end validation with MCP | Validation |
| `PHASE-10` | Validate the cost-saving assumption | Validation |
| `PHASE-10b` | Build token usage calculator | Tooling |
| `PHASE-11` | ⏸️ Pause for review | Review |
| `PHASE-12` | Commit and document | Commit |

> To execute a specific phase say: **"ejecuta PHASE-3"**
> To execute a range say: **"ejecuta desde PHASE-4 hasta PHASE-6"**
> To execute all say: **"ejecuta el plan"**

---

<!-- PHASE-0 -->
### [PHASE-0] Initialize git repository ✅

- [x] Initialize the repo in the project root
- [x] Create a `.gitignore` appropriate for Python + macOS
- [x] Add an initial commit with the existing documents
- [x] Verify the repo is clean

<!-- PHASE-1 -->
### [PHASE-1] Install Ollama ⚠️ partial

- [x] Check if Ollama is already installed — was not installed
- [x] Install ARM native from official `.app` (Homebrew install discarded — was x86_64/Rosetta, 0.8 tok/sec; replaced with `/Applications/Ollama.app`, 13 tok/sec)
- [x] Start the Ollama daemon — running via `ollama serve`
- [x] Verify the daemon is running and the API is reachable — `curl localhost:11434/api/tags` ✅
- [x] Configure Ollama to start automatically on login via the menu bar app:
  - Open Ollama from `/Applications/Ollama.app`
  - Click the Ollama icon in the macOS menu bar
  - Go to **Settings → General → Start at Login** and enable it
  - Verify: log out and back in, confirm `curl http://localhost:11434/api/tags` responds without manually starting the daemon
- [x] Disable cloud features (violates project constraint — only Claude is an allowed external service):
  - In Ollama Settings, find **"Cloud: enable cloud models and web search"** and **turn it OFF**

<!-- PHASE-2 -->
### [PHASE-2] Pull and verify the primary model ✅

- [x] Pull `qwen2.5-coder:14b` — 9.0 GB, Q4_K_M
- [x] Verify the model is available — `ollama list` confirms
- [x] Run a quick smoke test — palindrome function generated correctly
- [x] Note actual response time — cold start 5 tok/sec, warm **13 tok/sec** (within expected range)
- [x] 7B fallback not needed — 14B performs well on 18 GB unified memory

<!-- PHASE-3 -->
### [PHASE-3] Validate delegation via Bash + curl (Phase 1 of the two-phase strategy)

The goal here is to confirm that the planning/generation split is useful **before** building any infrastructure. Claude uses its Bash tool to call Ollama directly.

- [ ] Create a temporary `CLAUDE.md` at the project root (or use `~/.claude/CLAUDE.md` for global scope) with the Bash+curl delegation rule:
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
- [ ] Open a Claude Code session in this project directory
- [ ] Ask Claude to write a mechanical task (e.g. "write a Python dataclass for a User with name, email, and created_at fields")
- [ ] Confirm Claude invokes the Bash tool with the curl command instead of writing code directly
- [ ] Inspect the output quality — is it good enough to integrate without heavy correction?
- [ ] Try a second test: "generate pytest stubs for a function that validates an email address"
- [ ] Try a negative test: ask Claude to debug a complex multi-file issue — confirm it does NOT delegate to Ollama
- [ ] Document findings: does the delegation pattern produce useful output? How often does it need correction?

> ⚠️ If the output quality is consistently poor and requires multiple rounds of Claude correction, re-evaluate model choice before proceeding to Phase 4. The cost-saving assumption only holds if local model output is good on the first or second attempt.

<!-- PHASE-4 -->
### [PHASE-4] Set up the Python MCP server project

- [ ] Create the directory structure for the MCP server
  ```
  local_agents/
    mcp_server/
      server.py
      requirements.txt
  ```
- [ ] Create `requirements.txt` with the required dependencies
  ```
  mcp
  httpx
  ```
- [ ] Create a Python virtual environment for the server
  ```bash
  python3 -m venv local_agents/mcp_server/.venv
  ```
- [ ] Install dependencies
  ```bash
  local_agents/mcp_server/.venv/bin/pip install -r local_agents/mcp_server/requirements.txt
  ```

<!-- PHASE-5 -->
### [PHASE-5] Write the MCP server

- [ ] Write `mcp_server/server.py` implementing the following tools:
  - `ollama_generate(model: str, prompt: str, system: str = "") -> str`
    - Calls `POST http://localhost:11434/api/generate` with `stream: false`
    - Returns the `response` field from the JSON result
  - `ollama_chat(model: str, messages: list, system: str = "") -> str`
    - Calls `POST http://localhost:11434/api/chat` with `stream: false`
    - Returns the assistant message content
  - `ollama_list_models() -> str`
    - Calls `GET http://localhost:11434/api/tags`
    - Returns a newline-separated list of available model names
- [ ] Use `httpx.AsyncClient` with a timeout of at least 120 seconds (14B model can be slow)
- [ ] Add error handling: if Ollama is not running or returns an error, return a clear error message (do not raise — Claude needs to see the error as tool output)
- [ ] Test the server runs without errors
  ```bash
  local_agents/mcp_server/.venv/bin/python local_agents/mcp_server/server.py
  ```
  Expected: process starts and waits (stdio transport — no visible output is normal)

<!-- PHASE-6 -->
### [PHASE-6] Register the MCP server with Claude Code

- [ ] Check where Claude Code stores its MCP configuration on this machine
  ```bash
  cat ~/.claude/claude.json 2>/dev/null || echo "file not found"
  ```
- [ ] Add the Ollama MCP server entry to `~/.claude/claude.json`:
  ```json
  {
    "mcpServers": {
      "ollama": {
        "command": "/Users/alex/Projects/labs/local_agents/mcp_server/.venv/bin/python",
        "args": ["/Users/alex/Projects/labs/local_agents/mcp_server/server.py"]
      }
    }
  }
  ```
  Note: if `claude.json` already has content, merge — do not overwrite.
- [ ] Alternatively, use the CLI command if available:
  ```bash
  claude mcp add ollama -- /Users/alex/Projects/labs/local_agents/mcp_server/.venv/bin/python \
    /Users/alex/Projects/labs/local_agents/mcp_server/server.py
  ```
- [ ] Restart Claude Code to pick up the new MCP server
- [ ] Verify the tool is visible: in a Claude Code session, ask "what tools do you have available?" — `ollama_generate`, `ollama_chat`, and `ollama_list_models` should appear

<!-- PHASE-7 -->
### [PHASE-7] Update CLAUDE.md to use the MCP tool

- [ ] Replace the Phase 3 Bash+curl delegation rule in `CLAUDE.md` with the MCP version:
  ```markdown
  ## Local agent delegation

  You have access to three Ollama tools that run local models on this machine:
  - `ollama_generate(model, prompt)` — for single-turn generation
  - `ollama_chat(model, messages)` — for multi-turn conversations
  - `ollama_list_models()` — to check which models are available

  **Use the local model for**:
  - Boilerplate code (dataclasses, CRUD, config parsing, etc.)
  - Implementing a function or method from a known signature
  - Generating test stubs or fixtures
  - Repetitive patterns (serializers, validators, migrations)
  - First-pass implementations from a spec or pseudocode
  - Format/data transformations

  **Do NOT use the local model for**:
  - Tasks requiring multi-file reasoning or cross-file context
  - Debugging complex or non-obvious bugs
  - Architecture and design decisions
  - Tasks where the correct answer depends on understanding the full codebase

  Default model: `qwen2.5-coder:14b`.
  Always review and validate the local model's output before integrating it.
  If the output is wrong after two attempts, handle the task yourself.
  ```

<!-- PHASE-8 -->
### [PHASE-8] Configure Ollama context window

- [ ] Verify what context window Ollama is using by default
  ```bash
  curl -s http://localhost:11434/api/show \
    -d '{"name":"qwen2.5-coder:14b"}' | jq '.parameters'
  ```
- [ ] Create a custom Modelfile that sets `num_ctx` to 8192 (the default of 2048 is too small for code tasks)
  ```
  # local_agents/Modelfile
  FROM qwen2.5-coder:14b
  PARAMETER num_ctx 8192
  ```
- [ ] Build the custom model variant
  ```bash
  ollama create qwen2.5-coder:14b-ctx8k -f local_agents/Modelfile
  ```
- [ ] Update the default model in `CLAUDE.md` to `qwen2.5-coder:14b-ctx8k`
- [ ] Update the default model in `mcp_server/server.py` to match

<!-- PHASE-9 -->
### [PHASE-9] End-to-end validation with MCP

- [ ] Open a fresh Claude Code session in this project directory
- [ ] Run `ollama_list_models()` via Claude — confirm the tool works and models are listed
- [ ] Repeat the Phase 3 mechanical task tests, now using the MCP tool instead of curl:
  - Ask Claude to write a Python dataclass
  - Ask Claude to generate pytest stubs
  - Ask Claude to implement a function from a signature
- [ ] Confirm Claude uses `ollama_generate` (not writing code directly, not using curl)
- [ ] Check response quality: is it comparable to Phase 3 results?
- [ ] Measure latency: is it acceptable for interactive use? (~15–25 tok/sec for 14B = 10–30 sec for a typical function)
- [ ] Run a stress test: ask for a larger generation (a full class with 5+ methods) — observe if it fits within the 8192 context window
- [ ] Confirm the negative case: ask Claude to debug a complex bug — it should NOT invoke Ollama

<!-- PHASE-10 -->
### [PHASE-10] Validate the cost-saving assumption

- [ ] Run 5 representative real tasks (tasks you'd actually ask Claude in your workflow)
- [ ] For each task, note:
  - Did Claude delegate to Ollama or handle it itself?
  - Was the Ollama output usable as-is, needed minor fixes, or was it wrong?
  - How many Claude tokens were spent on orchestration vs. the output itself?
- [ ] Decide: does the local model save tokens in practice, or does correction overhead cancel it out?
- [ ] If the model quality is insufficient, consider switching to `qwen2.5-coder:7b` for speed or staying on 14B but narrowing the task types that are delegated

<!-- PHASE-10b -->
### [PHASE-10b] Build token usage calculator

The goal is a lightweight Python script that instruments both Claude API calls and Ollama calls, logs token usage per task, and prints a session summary showing real vs. baseline cost — so we can verify the project's core objective is being met.

- [ ] Create `token_calculator.py` in the project root
- [ ] Implement a `Session` class that tracks:
  - `claude_input_tokens` — tokens Claude received as input (orchestration overhead)
  - `claude_output_tokens` — tokens Claude generated (orchestration overhead)
  - `ollama_input_tokens` — tokens the local model received (free)
  - `ollama_output_tokens` — tokens the local model generated (free)
  - `task_name` — label for the task being measured
- [ ] Add a `record_claude_usage(input_tokens, output_tokens)` method that reads from the Claude API response `usage` field
- [ ] Add a `record_ollama_usage(response_json)` method that reads `prompt_eval_count` and `eval_count` from the Ollama API response
- [ ] Add a `baseline_estimate()` method that estimates what Claude would have spent doing the task alone:
  ```
  baseline_input  = claude_input_tokens
  baseline_output = claude_output_tokens + ollama_output_tokens
  # Rationale: without local model, Claude would generate the same output itself
  ```
- [ ] Add a `cost(input_tokens, output_tokens, model="sonnet")` helper using current pricing:
  - Sonnet 4.6: $3.00 / 1M input, $15.00 / 1M output
  - Opus 4.6:   $15.00 / 1M input, $75.00 / 1M output
- [ ] Add a `print_report()` method that outputs:
  ```
  ─────────────────────────────────────────
  Task: <task_name>
  ─────────────────────────────────────────
  Claude tokens   input: X    output: Y    cost: $Z
  Ollama tokens   input: X    output: Y    cost: $0.00  (local)
  ─────────────────────────────────────────
  Actual cost:    $A
  Baseline cost:  $B  (Claude doing it alone)
  Savings:        $C  (D%)
  ─────────────────────────────────────────
  ```
- [ ] Add a `SessionLog` class that persists results to `token_log.jsonl` (one JSON line per task) so savings accumulate over time
- [ ] Add a `summary()` function that reads `token_log.jsonl` and prints cumulative stats:
  - Total tasks measured
  - Total Claude tokens spent
  - Total estimated savings
  - Average savings per task
- [ ] Write a usage example at the bottom of the file under `if __name__ == "__main__":` showing how to wrap a real task

<!-- PHASE-11 -->
### [PHASE-11] ⏸️ Pause for review

- [ ] Review the full setup: Ollama running, MCP server registered, CLAUDE.md rules in place
- [ ] Review `mcp_server/server.py` for any issues
- [ ] Review the Modelfile and context window configuration
- [ ] Confirm the delegation behavior is working as expected based on Phase 9–10 findings
- [ ] Decide if any CLAUDE.md rules need to be tightened or loosened

**Stop here and wait for explicit approval before proceeding to Phase 12.**

<!-- PHASE-12 -->
### [PHASE-12] Commit and document

- [ ] Stage the new files:
  - `mcp_server/server.py`
  - `mcp_server/requirements.txt`
  - `Modelfile`
  - `CLAUDE.md`
  - `plan.md`
  - `research.md`
- [ ] Commit with a descriptive message:
  ```
  Add local agent setup: Ollama + MCP server + Claude Code integration

  - MCP server wrapping Ollama with ollama_generate, ollama_chat, ollama_list_models tools
  - Custom Modelfile setting num_ctx=8192 for qwen2.5-coder:14b
  - CLAUDE.md delegation rules for mechanical code generation tasks
  ```
- [ ] Update `research.md` with any findings from Phase 9–10 that changed the recommendations
