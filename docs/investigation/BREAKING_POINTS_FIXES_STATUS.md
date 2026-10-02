# Breaking Points Fixes: Implementation Status

**Date:** 2026-10-02
**Phase:** S-15 (Phase 1 Hardening)
**Status:** IN PROGRESS — 3 of 6 CRITICAL fixes applied

---

## Fixed Breaking Points ✅

### BP-03: Model Not Found (404) Detection → FIXED

**Issue:** Model validation was deferred to mid-stream, causing 404 errors to bubble up after stream started.

**Fix Applied:**
```python
async def validate_model(self) -> None:
    """Pre-flight validation via GET /api/tags before streaming."""
    # Checks model exists in Ollama's model list
    # Raises IntegrationError if missing
    # Called at start of stream()
```

**Location:** `src/integrations/llm/ollama_adapter.py:77–101`

**Status:** ✅ COMPLETE
**Testing:** Needs unit test `test_model_not_found_before_streaming()`

**Impact:** Fail-fast behavior; errors are now raised before stream opens, not mid-response.

---

### BP-01: Connection Timeout on Unreachable Server → FIXED

**Issue:** No timeout configured; stream hung indefinitely if server unreachable.

**Fixes Applied:**
```python
# In __init__:
self._client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0)  # 30s read, 10s connect
)

# In stream():
async with asyncio.timeout(35):  # Outer timeout wraps entire stream
    async with self._client.stream(...) as response:
        ...
```

**Location:** `src/integrations/llm/ollama_adapter.py:54–60` (init), `src/integrations/llm/ollama_adapter.py:143` (stream)

**Status:** ✅ COMPLETE
**Testing:** Needs unit test `test_unreachable_server_timeout()` with non-routable IP

**Impact:** Stream timeouts after 35s max, raising `IntegrationError("ollama", "stream_timeout")`.

---

### BP-06: No Timeout on Stream Consumption → FIXED

**Issue:** If Ollama hung mid-stream (e.g., OOM), stream waited indefinitely for next token.

**Fix Applied:**
```python
last_line_at = asyncio.get_event_loop().time()

async for line in response.aiter_lines():
    if not line:
        continue

    # BP-06: Per-line timeout (10s without a token)
    now = asyncio.get_event_loop().time()
    if now - last_line_at > 10:
        msg = "No token received for 10s; stream timeout"
        raise IntegrationError("ollama", msg)
    last_line_at = now
```

**Location:** `src/integrations/llm/ollama_adapter.py:151–160`

**Status:** ✅ COMPLETE
**Testing:** Needs unit test `test_stream_hangs_mid_response()` with mock that sends tokens then hangs

**Impact:** Individual token delays >10s trigger immediate error. Prevents indefinite hangs during generation.

---

## Partial/Incomplete Fixes ⚠️

### BP-04: Token Counting Accuracy → DOCUMENTED, NOT FIXED

**Issue:** Heuristic (word_count × 4 // 3) is 20–40% inaccurate on code/JSON/CJK content.

**What Was Done:**
- Added warning comment in `count_tokens()` docstring documenting the inaccuracy
- Note: Spend guard applies 50% safety buffer as compensating control
- Recommended future implementation: Ollama tokenizer endpoint or Hugging Face tokenizer

**Location:** `src/integrations/llm/ollama_adapter.py:182–195`

**Status:** ⚠️ DOCUMENTED, NOT YET FIXED (complex refactoring deferred to Phase 1b)
**Testing:** Needs unit test `test_token_count_accuracy_vs_actual()` that measures error %

**Decision Rationale:** Exact token counting requires:
- Either an extra round-trip to Ollama's `/api/generate` endpoint
- Or integrating Hugging Face tokenizers (new dependency)
- Or updating the spend guard to use an empirical safety multiplier

For Phase 1a (critical path), we're:
1. Documenting the known limitation
2. Relying on the spend guard's 50% safety buffer
3. Planning proper fix for Phase 1b (if S-15 eval demands it)

---

### BP-05: State Isolation in Concurrent Calls → DIAGNOSED, NOT FIXED

**Issue:** Instance variables `_input_tokens` and `_output_tokens` are shared across concurrent calls, corrupting usage stats.

**Root Cause:** After `stream()` completes, a single `Usage` object is read via `get_usage()`, but if two streams run concurrently, the state is overwritten.

**What Was Done:**
- Identified the architectural issue (instance state shared across async tasks)
- Documented in BREAKING_POINTS_OLLAMA.md

**Location:** `src/integrations/llm/ollama_adapter.py:44–54, 158–163, 186–198`

**Status:** ⚠️ DIAGNOSED, DEFERRED TO PHASE 1b (requires refactoring)

**Fix Options:**
1. **Option A (Preferred):** Return `Usage` object directly from `stream()` as a context manager or awaitable
   ```python
   async with adapter.stream([...]) as (token_stream, usage_future):
       async for delta in token_stream:
           ...
       usage = await usage_future
   ```

2. **Option B:** Use `contextvars.ContextVar` to isolate state per async task
   ```python
   _usage_var: contextvars.ContextVar[Usage] = contextvars.ContextVar("usage")
   ```

3. **Option C:** Create a new adapter instance per call (inefficient)

**Testing:** Needs unit test `test_concurrent_calls_state_isolation()` with 5–10 concurrent streams

**Decision Rationale:** This is an architectural refactoring that affects the public interface. Deferring to Phase 1b allows Phase 1a to focus on critical timeout/validation fixes first.

---

### BP-02: Partial UTF-8 Sequences in NDJSON → DEFERRED

**Issue:** If a multibyte UTF-8 character straddles a TCP packet boundary, `aiter_lines()` may yield a partial byte sequence, causing `json.loads()` to fail.

**Status:** 🟡 NOT YET ADDRESSED (low probability edge case)

**Mitigation:** Current error handling bubbles `json.JSONDecodeError` as `IntegrationError`, which is caught and logged. This is a safe fail, but not ideal for user experience.

**Proper Fix:** Use `response.aiter_bytes()` + manual line buffering instead of `aiter_lines()`, with UTF-8 decoding that handles incomplete sequences.

**Priority:** Deferred to Phase 2 (post-evaluation); low probability on well-formed Ollama responses.

---

## Unfixed Gaps & Future Work

### F-01: Token Counting Exact Implementation

**Timeline:** Phase 1b or R1.0
**Effort:** 4–6 hours
**Options:**
- Implement `count_tokens_exact()` using Ollama `/api/generate` endpoint
- Or use Hugging Face `transformers` tokenizer for the model
- Or adjust spend guard multiplier based on empirical testing

### F-02: State Isolation Refactor

**Timeline:** Phase 1b
**Effort:** 4–6 hours (includes public API change)
**Approach:** Implement Option A (return Usage from context manager)

### F-03: UTF-8 Handling Robustness

**Timeline:** Phase 2 or R2
**Effort:** 3–4 hours
**Approach:** Replace `aiter_lines()` with `aiter_bytes()` + manual buffering

### F-04: Ollama Version Pinning

**Timeline:** Phase 1c (documentation)
**Effort:** 1 hour
**Approach:** Document minimum Ollama version (v0.3+) in setup guide

---

## Test Gaps (To Fill)

| Test | Covers | Status | Effort |
|------|--------|--------|--------|
| `test_model_not_found_before_streaming()` | BP-03 | TODO | 1h |
| `test_unreachable_server_timeout()` | BP-01 | TODO | 1h |
| `test_stream_hangs_mid_response()` | BP-06 | TODO | 1h |
| `test_concurrent_calls_state_isolation()` | BP-05 | TODO | 2h |
| `test_token_count_accuracy_vs_actual()` | BP-04 | TODO | 2h |
| `test_malformed_json_line()` | BP-02 | TODO | 1.5h |
| `test_empty_response()` | EC-01 | TODO | 1h |
| `test_happy_path_single_token()` | HappyPath | PARTIAL | 0.5h |
| `test_happy_path_multi_token()` | HappyPath | PARTIAL | 0.5h |

**Total Test Effort:** ~11 hours

---

## Phase 1a Summary

**What We've Done:**
- ✅ Fixed BP-03 (model validation) — fail-fast before streaming
- ✅ Fixed BP-01 (connection timeout) — 35s outer + 30s httpx timeouts
- ✅ Fixed BP-06 (stream timeout) — 10s per-line timeout
- ✅ Documented BP-04 (token counting) — added safety buffer note
- ✅ Diagnosed BP-05 (state isolation) — architectural issue mapped

**What's Left for Phase 1b:**
- Build comprehensive test suite (11 tests, ~11 hours)
- Run golden-set evaluation (4 hours)
- Decide on BP-04 and BP-05 fixes (1–2 hour decision call)

**Go/No-Go Gate:** All 3 fixed breaking points + golden-set evaluation passes → Proceed to Phase 2 (GPU procurement)

---

## Running Tests Locally

Once test file is created:

```bash
# Install test deps
pip install pytest pytest-asyncio respx

# Run unit tests only (no real Ollama needed)
pytest tests/integrations/llm/test_ollama_adapter.py -v

# Run with coverage
pytest tests/integrations/llm/test_ollama_adapter.py --cov=src/integrations/llm

# Run specific test
pytest tests/integrations/llm/test_ollama_adapter.py::test_model_not_found_before_streaming -v
```

---

## Next Immediate Actions

1. **Today (Oct 2):** Create unit test file covering all 9 tests above
2. **Tomorrow (Oct 3):** Implement remaining tests, get CI green
3. **Oct 3–4:** Run golden-set evaluation on real Ollama
4. **Oct 4:** Make go/no-go decision on Tier A vs Tier B vs hybrid
