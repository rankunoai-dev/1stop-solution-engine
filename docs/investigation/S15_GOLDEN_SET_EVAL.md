# S-15 Golden-Set Evaluation Guide

**Phase:** S-15 (Ollama Validation)
**Duration:** ~4 hours
**Owner:** You (manual evaluation) + Claude (data collection)
**Date Started:** 2026-10-02
**Target Completion:** 2026-10-04

---

## Prerequisites

### 1. Ollama Installation & Model Pull

**On your development machine:**

```bash
# Install Ollama (if not already done)
# macOS/Linux: curl -fsSL https://ollama.ai/install.sh | sh
# Windows: Download from ollama.ai/download

# Verify Ollama is running
curl http://localhost:11434/api/tags

# Pull the model (one-time, ~20 GB download)
ollama pull qwen2.5:32b-instruct-q4_k_m

# Verify model is loaded
ollama list
# Should show: qwen2.5:32b-instruct-q4_k_m  (or similar)

# Test endpoint
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:32b-instruct-q4_k_m",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

### 2. Configure .env for Testing

```bash
# Ensure these are set in .env:
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:32b-instruct-q4_k_m
OLLAMA_BASE_URL=http://localhost:11434
ENVIRONMENT=development
```

### 3. Database & Services Running

```bash
# Start Postgres (if local Docker)
docker-compose up -d db

# Verify migrations are up
alembic upgrade head

# Or use Supabase connection string if already set
```

---

## Evaluation Protocol

### Phase 1: Model Warm-Up (10 min)

**Purpose:** Measure cold-start vs. warm latency

**Steps:**
1. Restart Ollama: `ollama kill && sleep 5 && ollama serve`
2. Make first API call to load model into VRAM
3. Record time to first token (should be 10–30s)
4. Wait 30 seconds
5. Make second call, record latency (should be 1–2s)

**Metrics to collect:**
- Cold-start latency (first call after model load): _____ seconds
- Warm latency (second call): _____ seconds

---

### Phase 2: Golden-Set Selection (15 min)

**If real RankUno tool READMEs are available:**
- Pick 20 random tool README files from your repository
- Avoid duplicates; include variety (web tools, CLI, data pipeline, etc.)

**If real docs not available yet (use fixtures):**
- I'll provide 20 synthetic tool descriptions that cover:
  - Plain text descriptions (baseline)
  - Code snippets in READMEs (for accuracy test)
  - JSON-heavy API specs (for token counting test)
  - CJK or multilingual content (for tokenizer test)

**Golden-set location:** Create `docs/evaluation/golden_set_s15.jsonl`
```json
{"id": "tool-001", "name": "CLI-Tool", "readme": "...long readme text..."}
{"id": "tool-002", "name": "API-Service", "readme": "...long readme text..."}
...
```

---

### Phase 3: Query Generation & Evaluation (2.5 hours)

For each of the 20 tools:

#### Query Type 1: "What is this tool?"

```
Tool: {tool_name}
README: {readme_text}
Query: "What is the {tool_name} tool and what does it do?"
```

**Metrics to collect:**

| Metric | Description | How to measure | Pass threshold |
|--------|---|---|---|
| **Citation Accuracy** | Does answer cite actual README sections? | Read answer, verify claims are in README; 1-10 scale | ≥8/10 (85%) |
| **Hallucination Rate** | Does answer invent facts not in README? | Look for claims without README evidence; 0-10 scale (0=no hallucinations) | ≥7/10 (no hallucinations) |
| **Response Time** | Seconds from query to full response | Use `time curl ...` or Python `time.perf_counter()` | <3s (p99) |
| **Token Count** | Input + output tokens from API | From llm_calls table or Ollama response | N/A (informational) |

#### Evaluation Form (Per Tool)

```
Tool ID: ________
Tool Name: ________________
Query: "What is this tool?"

Response Generated:
[Paste full response here]

Evaluation:
1. Citation Accuracy (1–10): _____
   Notes: [Which claims are cited? Which are questionable?]

2. Hallucination (0–10, 0=perfect): _____
   Notes: [Any invented details?]

3. Response Latency (seconds): _____.___

4. Input Tokens (from stream): _____
   Output Tokens: _____

Overall Quality (1–10): _____
Comments: [Any issues observed?]
```

---

### Phase 4: Data Collection & Analysis (30 min)

**Automated data collection (via Python script):**

```python
import asyncio
from src.modules.platform.settings import get_onestop_settings
from src.integrations.llm.ollama_adapter import OllamaAdapter
from src.integrations.llm.base import Message

async def evaluate_tool(tool_id: str, tool_name: str, readme: str):
    settings = get_onestop_settings()
    adapter = OllamaAdapter(
        model=settings.llm_model,
        base_url=settings.ollama_base_url
    )

    query = f"What is the {tool_name} tool and what does it do?"
    messages = [
        Message(role="system", content="You are a helpful assistant. Answer based only on the provided README."),
        Message(role="user", content=f"README:\n{readme}\n\nQ: {query}")
    ]

    import time
    start = time.perf_counter()

    full_response = ""
    async for delta in adapter.stream(messages, max_tokens=512):
        full_response += delta.text

    elapsed = time.perf_counter() - start
    usage = await adapter.get_usage()

    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "response": full_response,
        "latency_sec": elapsed,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": float(usage.cost_usd),
    }

# Run evaluation
async def run_evaluation():
    results = []
    for tool in golden_set:
        result = await evaluate_tool(tool["id"], tool["name"], tool["readme"])
        results.append(result)
        print(f"Evaluated {tool['name']}: {result['latency_sec']:.2f}s")

    return results
```

---

## Success Criteria (S-15 Gate)

✅ **ALL of these must be true to proceed to Phase 2:**

| Criterion | Target | Status |
|---|---|---|
| Citation accuracy (mean) | ≥85% | [ ] Pass |
| Hallucination rate (mean) | ≤5% | [ ] Pass |
| Response latency p99 | <3s | [ ] Pass |
| Token estimate error | <30% | [ ] Pass |
| No unhandled exceptions | 0 | [ ] Pass |
| Test suite passes | 12/12 | [✓] PASS |
| Model validation works | Pre-flight check | [ ] Pass |
| Timeouts enforced | All 3 working | [ ] Pass |

---

## Failure Mode & Escalation

**If ANY criterion fails:**

### Option A: Escalate to Tier B
- Upgrade to RTX 4090 × 2 or A100 (48–80 GB VRAM)
- Switch to `qwen2.5:70b-instruct-q4_k_m` or `deepseek-r1:70b`
- Expected improvement: +10–15% citation accuracy
- Re-run S-15 with 70B model

### Option B: Hybrid Mode
- Keep Tier A GPU for on-prem Ollama
- Add cloud fallback: retry query via Claude Haiku if Ollama response doesn't meet quality gate
- Cost: $50–100/month (only when Ollama fails)
- Trade-off: Adds 50 lines of adapter code + retry logic

### Option C: Delay On-Prem to R2
- Use cloud-only (Claude Haiku) for R1.0–R1.8
- Revisit on-prem deployment after golden-set proves quality
- Risk: Continue paying cloud costs while Ollama is being validated

---

## Reporting Results

### S-15 Evaluation Report Template

**Date:** 2026-10-04
**Model:** qwen2.5:32b-instruct-q4_k_m
**Hardware:** RTX 4090 / RTX 3090 / [specify]
**Test Set:** 20 real RankUno tools / 20 synthetic fixtures

#### Summary Metrics

| Metric | Result | Target | Status |
|---|---|---|---|
| Citation Accuracy (mean) | ____% | ≥85% | [ ] Pass / [ ] Fail |
| Hallucination Rate (mean) | ____% | ≤5% | [ ] Pass / [ ] Fail |
| Latency p99 | ____.__ s | <3s | [ ] Pass / [ ] Fail |
| Cold-Start Latency | ____.__ s | <30s | [✓] Baseline |
| Warm Latency (avg) | ____.__ s | 1–2s | [✓] Baseline |
| Token Est. Error | ____% | <30% | [ ] Pass / [ ] Fail |
| Cost/Query | $_______ | $0.00 | [✓] Pass |

#### Per-Tool Breakdown

| Tool | Citation | Hallucination | Latency | Status |
|---|---|---|---|---|
| Tool-001 | 9/10 | 0/10 | 1.2s | ✓ |
| Tool-002 | 7/10 | 2/10 | 2.1s | ✓ |
| ... | ... | ... | ... | ... |
| **Mean** | **8.2/10** | **1.1/10** | **1.8s** | **PASS** |

#### Recommendation

**Based on S-15 results:**

- [ ] **GO:** Approve Tier A GPU procurement (RTX 4090, ~$5K, proceed to Phase 2)
- [ ] **ESCALATE:** Recommend Tier B (70B model) for higher quality
- [ ] **HYBRID:** Recommend hybrid mode (Ollama + Haiku fallback)
- [ ] **NO-GO:** Recommend cloud-only for R1, revisit in R2

**Rationale:**
[Your assessment of why this path is chosen]

---

## Timeline

- **Oct 2:** Prerequisites complete, tests written ✅
- **Oct 3:** Warm-up phase + golden-set selection (1–2 hours)
- **Oct 3–4:** Evaluation loop (2–3 hours)
- **Oct 4:** Analysis + decision + report (1 hour)
- **Oct 5:** Decision gate; proceed to Phase 2 if GO

---

## Support & Debugging

### Common Issues

**Issue:** Ollama model not loading / "model not found"
- **Fix:** `ollama pull qwen2.5:32b-instruct-q4_k_m` and wait for completion
- **Verify:** `ollama list` should show model with ✓

**Issue:** Timeouts during evaluation
- **Fix:** Ollama may be low on VRAM; check `nvidia-smi` for GPU memory usage
- **Fix:** Increase timeout in adapter from 35s to 60s if needed for first-call delays

**Issue:** Token counts way off / spent cap exceeded during eval
- **Fix:** Spend guard has 50% safety buffer; evaluate on a fresh session with cap=999 temporarily
- **Config:** Set `SPEND_CAP_DAY_USD=999.00` in .env for eval, reset after

**Issue:** Real RankUno tool READMEs not available yet**
- **Fix:** I'll generate 20 synthetic fixtures covering various content types
- **Note:** Results will be re-validated on real docs in R1.5

---

## Next Steps

1. **Now (Oct 2):** Print this guide, gather golden-set READMEs
2. **Tomorrow (Oct 3):** Run warm-up phase and start evaluation
3. **Oct 4:** Complete evaluation, fill report, schedule decision call
4. **Oct 5:** Make go/no-go decision; order GPU if GO

**Questions?** Review `docs/investigation/BREAKING_POINTS_FIXES_STATUS.md` for context on the 3 fixes that enable this evaluation.
