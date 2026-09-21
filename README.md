# Qualitative PR & Bounty Verifier (GenLayer Intelligent Contract Primitive)

A decentralized, AI-powered code auditing and bounty settlement primitive built for GenLayer. This intelligent contract evaluates GitHub pull request diffs against qualitative acceptance criteria, enabling trustless developer bounties, automated milestone payouts, and open-source grant auditing without relying on centralized administrators or manual code reviews.

---

## 1. Overview & Problem Solved

In traditional Web3 development, milestone-based grants and bug bounties face a dilemma:
- **Centralized Custody:** Funds are locked in multi-sigs where human arbiters must manually verify code before releasing rewards, creating delays, trust bottlenecks, and administrative overhead.
- **Syntactic Smart Contracts:** Conventional EVM contracts cannot access GitHub, parse git unified diffs, or reason about qualitative requirements (e.g., "Must implement reentrancy guards and error handling").

With GenLayer:
1. **Direct Web Access On-Chain:** Validator nodes fetch live pull request unified diffs directly via `gl.nondet.web.get`.
2. **Subjective AI Code Grading:** Nodes independently evaluate the patch against the natural-language acceptance criteria using `gl.nondet.exec_prompt`.
3. **Semantic Consensus:** Validators achieve network agreement on the **meaning and substance** of the grading verdict (`ACCEPTED`, `REVISIONS_NEEDED`, `REJECTED`) rather than fragile formatting or whitespace variations.
4. **Dual-Use Primitive:** Operates both as a full bounty lifecycle manager (creation, submission tracking, winner assignment) and as a standalone code verification oracle (`evaluate_pr_standalone`) callable by external protocols.

---

## 2. Deployment

- **Network:** `studionet`
- **Contract Address:** `0x8099eD064CD9158F6Acc62bA0013954D170094e0`
- **Contract File:** `contracts/contract.py`

### Live Query Verification (Real Result)

The contract is deployed and actively verifiable on `studionet`. Using the GenLayer Python SDK (`genlayer-py`), querying the read-only contract state via the studionet RPC returns:

```python
import genlayer_py

account = genlayer_py.create_account()
client = genlayer_py.create_client(chain=genlayer_py.studionet, account=account)
addr = "0x8099eD064CD9158F6Acc62bA0013954D170094e0"

bounty_count = client.read_contract(address=addr, function_name="get_bounty_count", args=[])
# REAL RESULT returned from studionet RPC:
# 0

submission_count = client.read_contract(address=addr, function_name="get_submission_count", args=[])
# REAL RESULT returned from studionet RPC:
# 0
```

### Worked Example: Standalone PR Evaluation (Illustrative Example)

Any external smart contract or dApp can evaluate a PR against criteria on demand without creating a bounty escrow.

**Method Call (`evaluate_pr_standalone`):**
```python
contract.evaluate_pr_standalone(
    pr_url="https://github.com/example/repo/pull/42",
    acceptance_criteria="Must implement JWT verification and proper error handling."
)
```

**Expected Consensus Result (JSON string returned on-chain):**
```json
{
  "pr_url": "https://github.com/example/repo/pull/42",
  "verdict": "ACCEPTED",
  "reason": "The PR implements JWT verification with proper error handling."
}
```

### Worked Example: Bounty Lifecycle (Illustrative Example)

1. **Creator creates bounty:**
```python
bounty_id = contract.create_bounty(
    title="Implement Token Escrow",
    repo_url="https://github.com/example/repo",
    acceptance_criteria="Must support deposit and withdraw with reentrancy protection.",
    reward_amount=1000
)
# Returns: "bounty_1"
```

2. **Contributor submits PR for automated auditing:**
```python
result = contract.submit_pr_for_evaluation(
    bounty_id="bounty_1",
    pr_url="https://github.com/example/repo/pull/42"
)
```

**Expected Consensus Output:**
```json
{
  "submission_id": "sub_1",
  "bounty_id": "bounty_1",
  "verdict": "ACCEPTED",
  "reason": "The PR implements JWT verification with proper error handling.",
  "bounty_status": "COMPLETED"
}
```

---

## 3. How Consensus & Validator Equivalence Works

Non-determinism is inherent to web fetching and LLM reasoning: two honest validator nodes invoking an LLM with identical code diffs may receive slightly different wording, formatting, or rationale phrasing.

### The Problem with Format-Only Checks
If validators checked byte-for-byte equality or strict JSON payload matching, honest nodes would continuously fail to reach consensus due to trivial variations in punctuation or sentence structure. Conversely, a format-only check (e.g., verifying that a payload is merely valid JSON) would accept conflicting decisions.

### Semantic Equivalence Under the Equivalence Principle
This primitive implements substantive equivalence using GenLayer's `gl.vm.run_nondet_unsafe`:

1. **State Isolation:** All non-deterministic operations (`gl.nondet.web.get`, `gl.nondet.exec_prompt`) run strictly inside `_execute_pr_evaluation`. Neither `leader_fn` nor `validator_fn` touches contract storage or `self` directly; all necessary variables (`pr_url`, `acceptance_criteria`) are captured immutably prior to execution.
2. **Unified Diff Retrieval:** For GitHub PR URLs, the leader and validators fetch `.diff` to extract raw, unified patch text, truncating at 12,000 characters to protect LLM context windows.
3. **Leader Proposal:** The leader executes `leader_fn()` and prompts the LLM to grade the patch into one of three canonical verdicts: `ACCEPTED`, `REVISIONS_NEEDED`, or `REJECTED`, alongside explanatory reasoning.
4. **Independent Validator Re-Execution:** When `validator_fn(leader_res)` runs on validator nodes, the validator independently executes `leader_fn()`, obtaining its own independent verdict.
5. **Semantic Verdict Consensus:**
```python
# The validator compares the substantive verdict, not the wording:
return leader_verdict == my_verdict
```
- If the leader proposes `ACCEPTED` and the validator independently derives `ACCEPTED`, consensus passes.
- If the leader proposes `ACCEPTED` but the validator determines `REJECTED`, consensus fails (`False`). Two validators reaching conflicting decisions can **never** both pass.

---

## 4. GenVM Runtime Compliance

| Hard Rule | Status | Implementation Details |
| :--- | :--- | :--- |
| **Pragma Header** | Verified | Line 1: `# v0.2.16`<br>Line 2: `# { "Depends": "py-genlayer:..." }`<br>Line 3: `from genlayer import *` |
| **Import Discipline** | Verified | Only `from genlayer import *` is used. |
| **Encoding** | Verified | Pure 7-bit ASCII encoding throughout all lines and comments. |
| **Type Discipline** | Verified | Persisted numeric values use `bigint`. Storage collections use `TreeMap[str, T]` and `DynArray[str]`. |
| **Storage Decorators** | Verified | Storage structures `Bounty` and `PRSubmission` are decorated with `@allow_storage` and `@dataclass`. |
| **Nondet Safety** | Verified | All nondet calls (`web.get`, `exec_prompt`) are quarantined in closures without `self` or storage access. |
| **Class Architecture** | Verified | Root class named `Contract`, inherits `gl.Contract`. |
| **Consensus Integrity** | Verified | Equivalence checks semantic verdict equality (`ACCEPTED`, `REVISIONS_NEEDED`, `REJECTED`), never format-only. |

---

## 5. Public API Specification

### State-Changing Methods (`@gl.public.write`)
* `create_bounty(title: str, repo_url: str, acceptance_criteria: str, reward_amount: bigint) -> str`
  Creates a new bounty escrow. Validates non-empty fields, valid HTTP/HTTPS URLs, and non-negative reward amounts. Returns `bounty_id`.
* `submit_pr_for_evaluation(bounty_id: str, pr_url: str) -> str`
  Submits a GitHub PR for automated evaluation against the bounty's criteria. Triggers decentralized consensus. If `ACCEPTED`, marks bounty as `COMPLETED` and assigns winner. Returns detailed JSON status.
* `evaluate_pr_standalone(pr_url: str, acceptance_criteria: str) -> str`
  Standalone evaluation primitive. Allows external contracts and bots to verify pull requests without creating a bounty escrow. Returns JSON containing verdict and reason.
* `cancel_bounty(bounty_id: str) -> str`
  Allows only the bounty creator or contract owner to cancel an open bounty.

### Read-Only View Methods (`@gl.public.view`)
* `get_bounty(bounty_id: str) -> Bounty`: Returns full stored record for `bounty_id`.
* `get_bounty_count() -> bigint`: Returns total number of created bounties.
* `get_bounty_id_at(index: bigint) -> str`: Returns bounty ID at chronological index for indexing.
* `get_all_bounty_ids() -> DynArray[str]`: Returns array of all bounty IDs.
* `get_submission(submission_id: str) -> PRSubmission`: Returns full submission audit record.
* `get_submission_count() -> bigint`: Returns total number of evaluated submissions.
* `get_submission_id_at(index: bigint) -> str`: Returns submission ID at index.
* `get_all_submission_ids() -> DynArray[str]`: Returns array of all submission IDs.

---

## 6. Running Tests

The test suite runs using `gltest` (the official GenLayer testing framework):

```bash
# 1. Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run all tests
gltest tests/
```

### Test Coverage Results
```
tests\test_contract.py .........                                         [100%]
============================== 9 passed in 0.48s ==============================
```
- `test_create_bounty`: Verifies bounty state creation, index tracking, and attribute assignment.
- `test_create_bounty_validation_reverts`: Verifies input validation and edge-case `UserError` reverts.
- `test_submit_pr_accepted_and_validator_consensus`: Tests end-to-end PR evaluation, winner assignment, and validator consensus agreement via `run_validator()`.
- `test_submit_pr_revisions_needed`: Tests non-passing review feedback without state completion.
- `test_submit_pr_rejected`: Tests rejection of non-compliant pull requests.
- `test_creator_cannot_claim_own_bounty`: Enforces fraud prevention preventing creators from claiming their own bounties.
- `test_cancel_bounty_and_access_control`: Verifies access control and prevents submissions to cancelled bounties.
- `test_evaluate_pr_standalone`: Tests the standalone evaluation oracle method.
- `test_submit_pr_unrelated_repo_reverts`: Enforces that submitted PRs must target the bounty's stored repository.
