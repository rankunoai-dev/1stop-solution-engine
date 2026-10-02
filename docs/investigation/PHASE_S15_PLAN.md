# Phase 1 (S-15): Ollama Validation & Adapter Hardening Plan

**Start Date:** 2026-10-02
**Target Completion:** 2026-10-05 (3 days)
**Owner:** Claude Code + Manoj (manual eval on golden set)
**Status:** IN PROGRESS

---

## Objectives

1. **Fix all CRITICAL breaking points** in `OllamaAdapter` (BP-01, BP-03, BP-04, BP-05, BP-06)
2. **Build test suite** exposing edge cases (respx-mocked unit tests)
3. **Run S-15 golden-set evaluation** on real Ollama with Qwen2.5 32B
4. **Go/No-Go decision** on pure on-prem deployment

---

## Deliverables

### D1: Hardened OllamaAdapter (`src/integrations/llm/ollama_adapter.py`)

**Fixes Required:**

1. **BP-03 (Model Validation)** — Add pre-flight check
   ```python
   async def validate_model(self) -> None:
       """Check model exists via /api/tags before streaming."""
       # GET /api/tags, check model name in response
       # Raise ConfigurationError if missing
   ```

2. **BP-01 (Connection Timeout)** — Add httpx timeout
   ```python
   # In __init__:
   self._client = httpx.AsyncClient(
       timeout=httpx.Timeout(30.0, connect=10.0)
   )
   # Wrap stream in asyncio.timeout(35s)
   ```

3. **BP-04 (Token Counting)** — Implement exact counting or buffer
   ```python
   async def count_tokens_exact(self, messages) -> int:
       """Use Ollama /api/generate (no-op endpoint) for exact token count."""
       # Or: use huggingface_hub tokenizer for qwen2.5
       # Or: return heuristic + 50% safety buffer
   ```

4. **BP-05 (State Isolation)** — Refactor Usage return
   ```python
   # Instead of storing _input_tokens/_output_tokens on instance:
   # Return (text_generator, usage_awaitable) from stream()
   # Or: Use contextvars.ContextVar to isolate per task
   ```

5. **BP-06 (Stream Timeout)** — Add per-line timeout
   ```python
   async for line in response.aiter_lines():
       if not line and time_since_last_token > 10s:
           raise IntegrationError("stream_timeout")
   ```

**Estimated Effort:** 8 hours
**Complexity:** Medium (refactoring state handling)

---

### D2: Unit Test Suite (`tests/integrations/llm/test_ollama_adapter.py`)

**Test Coverage:**

- [ ] `test_model_not_found_before_streaming()` — BP-03
- [ ] `test_connection_timeout()` — BP-01
- [ ] `test_concurrent_state_isolation()` — BP-05
- [ ] `test_token_count_accuracy_text()` — BP-04
- [ ] `test_token_count_accuracy_code()` — BP-04 (documents inaccuracy)
- [ ] `test_stream_empty_response()` — EC-01
- [ ] `test_stream_happy_path_single_token()` — HappyPath
- [ ] `test_stream_happy_path_multi_token()` — HappyPath
- [ ] `test_temperature_parameter_passed()` — HappyPath
- [ ] `test_http_500_error()` — Error handling
- [ ] `test_json_decode_error_malformed_line()` — BP-02 (partial)

**Framework:** pytest + respx (mock HTTP)
**Target Coverage:** 90%+ on adapter module

**Estimated Effort:** 6 hours

---

### D3: S-15 Golden-Set Evaluation Report

**Metrics to Collect (20 real RankUno tool READMEs):**

| Metric | Target | Pass Criteria |
|---|---|---|
| Citation accuracy | > 85% | Answers cite correct sections |
| Hallucination rate | < 5% | Claims backed by README |
| Response latency (p99) | < 3s | Includes model warm-up (2nd call) |
| Token estimate error | < 30% | `count_tokens()` vs actual |
| Model warm-up time | < 30s | First call after boot |
| Subsequent latency | 1–2s | Average of 20 queries |
| Memory usage peak | < 24GB | GPU + system RAM |
| Cost projection error | < 20% | Estimated vs actual spend |

**Tools:**
- Manual evaluation on 20 tool READMEs
- Stopwatch latency measurements
- Token count comparison via `llm_calls` table

**Report Contents:**
- Pass/fail on each criterion
- Recommendations (upgrade to 70B? Use Haiku fallback? Accept 32B?)
- Cost/benefit analysis

**Estimated Effort:** 4 hours (manual evaluation)

---

## Task Breakdown

### Phase 1a: Adapter Fixes (Oct 2–3)

**Hour 1–2: BP-03 Model Validation**
- Add `validate_model()` method calling `GET /api/tags`
- Call in `__init__` or before `stream()`
- Test with respx mock

**Hour 3–4: BP-01 Connection Timeout**
- Configure httpx timeout on AsyncClient
- Wrap stream in `asyncio.timeout(35s)`
- Test timeout handling

**Hour 5–6: BP-04 Token Counting**
- Research Ollama tokenizer endpoint
- Implement `count_tokens_exact()` or use safety buffer
- Compare heuristic vs exact on 10 test prompts

**Hour 7–8: BP-05 State Isolation**
- Refactor Usage return (complex refactoring)
- Or use contextvars for isolation
- Test concurrent calls

**Hour 9–10: BP-06 Stream Timeout**
- Add per-line timeout in stream loop
- Test hang scenario

---

### Phase 1b: Test Suite (Oct 3–4)

**Write 10 test functions:**
- Mock Ollama via respx
- Verify adapter handles errors, concurrency, edge cases
- Use parametrized tests for different content types

---

### Phase 1c: Golden-Set Eval (Oct 4–5)

**Prerequisites:**
1. Pull `qwen2.5:32b-instruct-q4_k_m` to your dev machine (~20 GB download)
   - Time: ~30 min (depends on internet speed)
2. Start Ollama: `ollama pull qwen2.5:32b-instruct-q4_k_m`
3. Verify endpoint: `curl http://localhost:11434/api/tags`

**Evaluation Steps:**
1. Pick 20 RankUno tool READMEs (or use fixtures if not available yet)
2. For each README:
   - Generate a "What is this tool?" query
   - Run adapter, time response
   - Rate citation accuracy (1–10 scale)
   - Check for hallucinations (facts not in README)
   - Record token counts from llm_calls table
3. Aggregate metrics
4. Write report with go/no-go recommendation

---

## Exit Criteria (S-15 Pass)

**ALL of the following must be true:**

- ✅ All CRITICAL breaking points fixed and tests passing
- ✅ Citation accuracy ≥ 85% on golden set
- ✅ Hallucination rate ≤ 5%
- ✅ Latency p99 < 3s (after warm-up)
- ✅ Token estimate error < 30%
- ✅ No unhandled exceptions during evaluation
- ✅ Spend guard cap enforcement remains intact

**If ANY criterion fails:**
- Escalate to Tier B hardware (70B model)
- OR switch to hybrid mode (Ollama + Haiku fallback)
- OR delay on-prem deployment to R2 (use cloud in R1)

---

## Risks & Mitigations

### Risk 1: Token Counting Takes Too Long to Fix

**Mitigation:** Use 50% safety buffer on heuristic immediately. Accept that spend may be 20% under-estimated during R1. Plan exact counting for R2.

### Risk 2: Qwen2.5 32B Quality Doesn't Meet 85% Threshold

**Mitigation:** Have 70B model download ready as backup. Can upgrade hardware mid-eval.

### Risk 3: No Real RankUno Tool READMEs Available Yet

**Mitigation:** Use fixture docs (generated or synthetic) that test code, JSON, and edge cases. Results will be validated when real docs are available in R1.5.

### Risk 4: Ollama Installation Fails on Dev Machine

**Mitigation:** Use Docker-based Ollama: `docker run -d -p 11434:11434 ollama/ollama`. Or use a remote GPU server if local install doesn't work.

---

## Success Criteria

**This phase is successful if:**
1. OllamaAdapter passes all unit tests
2. S-15 evaluation achieves pass on all metrics
3. No critical issues discovered during testing
4. Team confidence in on-prem deployment is HIGH

**If successful:** Proceed to Phase 2 (GPU procurement) with high confidence.

**If unsuccessful:** Pivot to hybrid or cloud-only mode for R1; revisit on-prem in R2.
