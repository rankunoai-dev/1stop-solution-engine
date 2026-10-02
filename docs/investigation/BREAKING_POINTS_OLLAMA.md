# 1Stop Ollama Adapter: Breaking Points & Edge Cases Registry

**Last Updated:** 2026-10-02
**Phase:** S-15 Investigation
**Status:** Active — Issues identified during Phase 1

---

## Critical Breaking Points (MUST FIX Before R1.0)

### BP-01: Ollama Server Unreachable

**Location:** `src/integrations/llm/ollama_adapter.py:92–123`

**Issue:** If Ollama server is unreachable (DNS failure, network down, process crashed), the stream hangs indefinitely because `httpx.AsyncClient.stream()` has no default timeout.

**Scenario:**
```python
# Ollama offline at http://localhost:11434
adapter = OllamaAdapter("qwen2.5:32b")
async for delta in adapter.stream([Message(role="user", content="Hello")]):
    # This hangs forever or times out at OS level (~60s)
    text += delta.text
```

**Impact:**
- User request blocks indefinitely
- FastAPI thread pool exhausted after ~10 concurrent hangs
- No error logged until timeout fires

**Fix:**
- Add explicit `timeout=httpx.Timeout(30.0, connect=10.0)` to `AsyncClient`
- Wrap stream init in timeout context: `asyncio.timeout(35s)`
- Re-raise as `IntegrationError("ollama", "connection_timeout")`

**Severity:** CRITICAL — Affects availability

**Tests Needed:**
- Mock Ollama endpoint that never responds
- Mock Ollama endpoint that closes connection mid-stream
- Mock timeout at different phases (connection, first token, mid-stream)

---

### BP-02: Partial UTF-8 Sequences in NDJSON Lines

**Location:** `src/integrations/llm/ollama_adapter.py:99–118`

**Issue:** `response.aiter_lines()` may yield partial UTF-8 sequences if a multibyte character (e.g., emoji, Chinese char) straddles a TCP packet boundary. `json.loads()` then fails with `JSONDecodeError`.

**Scenario:**
```
# Ollama response stream contains:
{"message":{"content":"Hello 世"}
{"message":{"content":"界"}}

# httpx splits on TCP boundaries:
Line 1: '{"message":{"content":"Hello 世界"}}'  # May arrive as two partial lines
Line 2: Partial UTF-8 byte sequence
```

**Impact:**
- Stream stops unexpectedly mid-answer
- User sees incomplete response ("Hello 世")
- Error not logged as `IntegrationError`, exception bubbles up

**Fix:**
- Use `response.aiter_bytes()` + manual UTF-8 decoder instead of `aiter_lines()`
- Accumulate bytes until a complete line (ending with `\n`) is formed
- Handle incomplete UTF-8 gracefully (buffer partial sequences)

**Severity:** HIGH — Affects answer quality

**Tests Needed:**
- Generate responses with multibyte characters
- Mock TCP stream that splits multibyte sequences
- Verify no exception on partial UTF-8

---

### BP-03: Model Not Found (404) Only Detected Mid-Stream

**Location:** `src/integrations/llm/ollama_adapter.py:92–97`

**Issue:** If model doesn't exist locally (e.g., typo in `LLM_MODEL`), Ollama returns HTTP 404 only after reading the first streamed chunk. The `response.raise_for_status()` check happens AFTER opening the stream, so it's inside the `async with response.aiter_lines()` block. If the 404 header arrives late, the error propagates into the consumer's iteration.

**Scenario:**
```python
adapter = OllamaAdapter("nonexistent-model-xyz")
async for delta in adapter.stream([...]):
    # First iteration: 404 IntegrationError
    text += delta.text
# User sees error mid-iteration, not before stream starts
```

**Impact:**
- Spend guard has already reserved cost (calls before stream starts)
- Answer generation starts, then fails partway through
- User sees partial/broken response
- Cost recorded as "error" but still charged

**Fix:**
- Validate model exists via `GET /api/tags` before streaming
- Call `response.raise_for_status()` BEFORE iterating lines
- Fail fast in a sync check during `__init__`

**Severity:** HIGH — Affects reliability & spend tracking

**Tests Needed:**
- Test with nonexistent model; verify error fires before `stream()` returns
- Test with model that exists but is not loaded; verify preload check

---

### BP-04: Token Count Heuristic is 20–40% Inaccurate

**Location:** `src/integrations/llm/ollama_adapter.py:125–139`

**Issue:** `count_tokens()` uses word-count heuristic (words × 4 // 3) but actual token counts vary wildly by content type:
- Plain text: 1.2–1.4 tokens/word (heuristic works)
- Code blocks: 0.8–1.0 tokens/word (heuristic overestimates)
- JSON: 0.6–0.8 tokens/word (heuristic way off)
- CJK (Chinese/Japanese/Korean): 0.3–0.5 tokens/word (heuristic fails)

**Scenario:**
```python
# Estimating cost for a code-heavy RAG prompt
code_prompt = "```python\nfor i in range(1000):\n    print(i)\n```"
estimated = await adapter.count_tokens([Message(role="user", content=code_prompt)])
# Returns ~400 tokens (words × 4 // 3)
# Actual tokens: ~180 (code compresses with tokenizer)

# Spend guard reserves cost for 400 tokens
# Actual cost is 45% less → underspend

# If estimate is LOW for CJK content:
cjk_prompt = "这是一个很长的中文提示"  # 8 words
estimated = await adapter.count_tokens([...])
# Returns ~11 tokens (8 × 4 // 3)
# Actual tokens: ~25 (CJK is more expensive)
# Spend guard under-reserves → may exceed cap
```

**Impact:**
- Spend cap enforcement is unreliable (off by 20–40%)
- May allow queries that exceed budget (integrity issue)
- May block queries under budget (availability issue)
- Golden-set evaluation on code/JSON docs will show wrong cost projections

**Fix:**
- Implement exact token counting via Ollama's generate endpoint (no cost, just tokenization)
- Or use Hugging Face tokenizer library for the specific model
- Or accept heuristic but add 50% buffer for safety

**Severity:** CRITICAL — Affects spend guard reliability (core mission)

**Tests Needed:**
- Test token counting on prompts with code, JSON, CJK content
- Compare against actual streaming token counts from `eval_count`
- Measure error margins by content type
- Determine safety buffer for estimation

---

### BP-05: State Not Isolated Between Concurrent Calls

**Location:** `src/integrations/llm/ollama_adapter.py:44–54, 109–118, 141–155`

**Issue:** Instance variables `_input_tokens` and `_output_tokens` are shared across all `stream()` calls on the same adapter instance. If two concurrent calls stream, their token counts corrupt each other.

**Scenario:**
```python
adapter = OllamaAdapter("qwen2.5:32b")

# Call 1 and Call 2 start concurrently
async def call1():
    async for delta in adapter.stream([Message(..., "Query 1")]):
        # At same time as call2, both writing to adapter._input_tokens
        pass
    usage = await adapter.get_usage()
    # usage may show tokens from Call 2!

async def call2():
    async for delta in adapter.stream([Message(..., "Query 2")]):
        pass
    usage = await adapter.get_usage()
    # usage may show tokens from Call 1 or mixed!

await asyncio.gather(call1(), call2())
```

**Impact:**
- Concurrency corrupts token counts
- Spend recording is wrong (llm_calls.input_tokens / output_tokens are garbage)
- Golden-set evaluation will show wrong costs

**Fix:**
- Return `Usage` object from `stream()` directly (don't store state in instance)
- Or create a new adapter per call (but this is inefficient)
- Or use `contextvars` to isolate state per async task

**Severity:** CRITICAL — Affects spend tracking integrity

**Tests Needed:**
- Spawn 5–10 concurrent streams on same adapter
- Verify each call's usage is isolated and correct
- Check that llm_calls table records show correct per-call tokens

---

### BP-06: No Timeout on Stream Consumption

**Location:** `src/integrations/llm/ollama_adapter.py:59–123`

**Issue:** Once streaming starts, there's no timeout on individual token consumption. If Ollama hangs mid-response (e.g., GPU memory exhaustion), the stream waits indefinitely. The outer `asyncio.timeout()` at the API layer may not be tight enough.

**Scenario:**
```python
# Ollama is generating, but GPU memory runs out after 50 tokens
async for delta in adapter.stream([...], max_tokens=2048):
    text += delta.text  # Last delta received 50 tokens ago
    # Ollama is hung trying to allocate memory
    # This loop will wait forever
```

**Impact:**
- User request hangs
- FastAPI task slot exhausted
- No observability (no log about which token number hung)

**Fix:**
- Add per-token timeout: if no token received within `read_timeout=10s`, fail
- Or catch `httpx.ReadTimeout` and re-raise as `IntegrationError`

**Severity:** HIGH — Affects availability

**Tests Needed:**
- Mock Ollama that sends N tokens then hangs
- Verify stream times out and raises IntegrationError

---

## High-Priority Edge Cases (Should Fix Before R1.0)

### EC-01: Ollama Returns Empty Response

**Issue:** Ollama may return a valid response with `message.content=""` (e.g., model refused, or rate-limited at provider level). Stream yields no deltas. `_output_tokens` may be 0 or missing.

**Fix:** Check for empty output, log a warning, return empty string gracefully (don't fail).

**Test:** Mock Ollama endpoint returning `{"done":true, "message":{"content":""}, "eval_count":0}`

---

### EC-02: Base URL with Path Prefix (Behind Proxy)

**Issue:** Line 89 hardcodes `/api/chat`. If Ollama is behind a proxy at `/ollama/api/chat`, the request fails silently.

**Fix:** Allow configurable endpoint path, or use service discovery to detect it.

**Test:** Mock Ollama at `http://localhost:8080/ollama/`, verify adapter finds `/api/chat` path.

---

### EC-03: Very Long Responses (>100K tokens)

**Issue:** If model generates >100K tokens, memory usage explodes (storing all deltas in `text += delta.text`). No backpressure.

**Fix:** Document recommendation to set `max_tokens` to 8K for safety. Consider truncation in adapter.

**Test:** Generate 50K token response, measure memory, latency.

---

### EC-04: Rapid Adapter Restart

**Issue:** Creating 10 new `OllamaAdapter` instances in a loop (e.g., during re-initialization). Each opens a new `httpx.AsyncClient`. Connection pool may exhaust.

**Fix:** Use a singleton or shared client pool. Or document connection reuse.

**Test:** Spawn 50 adapters in rapid succession, verify no connection pool exhaustion.

---

### EC-05: Network Flakiness (Intermittent Packet Loss)

**Issue:** TCP retransmission delays can cause token arrival to be very irregular (100ms pause, then 10 tokens, then 2s pause). Consumer may appear hung.

**Fix:** Add per-line timeout (not just per-stream), or implement backoff + retry logic.

**Test:** Mock TCP stream with artificial delays between packets.

---

## Low-Priority Edge Cases (Track for Future)

### EC-06: Model Preloading Overhead

**Note:** First call to a model takes 10–30s (VRAM loading). Subsequent calls are fast. S-15 should measure cold-start vs. warm latency.

---

### EC-07: Ollama Version Compatibility

**Note:** Ollama API changed between v0.1 and v0.3 (added `eval_count` field). Adapter assumes v0.3+. Document min version.

---

## Investigation Tasks for Phase 1 (S-15)

### Task: S-15a — Unit Tests for Edge Cases

Build `tests/integrations/llm/test_ollama_adapter.py`:
- [ ] Test unreachable server (timeout)
- [ ] Test 404 model not found
- [ ] Test model validation (`GET /api/tags`)
- [ ] Test concurrent calls (state isolation)
- [ ] Test empty response
- [ ] Test token count accuracy (code, JSON, CJK content)
- [ ] Test connection pool reuse

**Target:** All tests pass with mock Ollama (respx library)

---

### Task: S-15b — Golden-Set Evaluation on Real Ollama

Deploy `qwen2.5:32b-instruct-q4_k_m` to your development machine. Run on 20 real RankUno tool READMEs:

**Metrics to collect:**
1. Citation accuracy (> 85% required)
2. Hallucination rate (< 5% required)
3. Average response latency (target: <2s)
4. Average token count per answer
5. Cold-start latency (first model load)
6. Warm latency (subsequent calls)
7. Memory usage (GPU + system RAM)
8. Token estimate accuracy (compare `count_tokens()` vs. actual)

**Success criteria:**
- Citation accuracy ≥ 85%
- Hallucination rate ≤ 5%
- Latency p99 < 3s
- Token estimate error < 30%

**If any metric fails:** Escalate to Tier B (70B model) or hybrid mode (fallback to Haiku).

---

### Task: S-15c — Fix Critical Breaking Points

Prioritize fixes:

1. **BP-03 (Model validation)** — 2 hours
   - Add `validate_model()` method calling `/api/tags`
   - Call in `__init__`, fail fast if model missing

2. **BP-01 (Connection timeout)** — 1 hour
   - Add httpx timeout config
   - Add asyncio timeout around stream

3. **BP-04 (Token counting)** — 4 hours
   - Implement exact counting via Ollama tokenizer endpoint
   - Or use Hugging Face tokenizer for `qwen2.5`
   - Or add 50% safety buffer to heuristic

4. **BP-05 (State isolation)** — 2 hours
   - Refactor to return Usage from stream (don't store in instance)
   - Or use contextvars to isolate per async task

5. **BP-06 (Stream timeout)** — 1 hour
   - Add per-line timeout in `aiter_lines()` loop

**Total effort:** ~10 hours (1.25 days)

---

## Breaking Point Status Tracker

| ID | Severity | Issue | Status | Assign | ETA |
|---|---|---|---|---|---|
| BP-01 | CRITICAL | Unreachable server | Identified | Phase 1 | Oct 3 |
| BP-02 | HIGH | Partial UTF-8 | Identified | Phase 1 | Oct 3 |
| BP-03 | CRITICAL | Model validation | Identified | Phase 1 | Oct 2 |
| BP-04 | CRITICAL | Token counting | Identified | Phase 1 | Oct 3–4 |
| BP-05 | CRITICAL | State isolation | Identified | Phase 1 | Oct 3 |
| BP-06 | HIGH | Stream timeout | Identified | Phase 1 | Oct 3 |
| EC-01 | MEDIUM | Empty response | Identified | Phase 1 | Oct 4 |
| EC-02 | MEDIUM | Proxy path | Identified | Phase 2 | Oct 10 |
| EC-03 | LOW | Large responses | Identified | Phase 2 | Oct 15 |
| EC-04 | LOW | Connection pool | Identified | Phase 2 | Oct 15 |
| EC-05 | LOW | Network flakiness | Identified | Phase 2 | Oct 15 |

---

## Recommendations

1. **Phase 1 must fix all CRITICAL breaking points** before evaluating golden set. Otherwise, S-15 results are unreliable.

2. **Add 50% token estimate buffer** to spend guard as temporary safety net while token counting is being improved.

3. **Golden-set evaluation should run on a _stable_ Ollama** (not during first-time model load, not during system resource contention).

4. **Consider hybrid mode as fallback** if BP-03 or BP-04 cannot be fixed in time for R1.0.

5. **Document per-call timeout expectations** for API consumers (e.g., "answers take 1–3 seconds").
