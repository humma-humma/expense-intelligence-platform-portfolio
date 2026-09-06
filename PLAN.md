# Expense Intelligence Platform — Plan of Action

Status: Phase 2 (real German receipt ingestion) in progress
Last updated: 2026-09-06
Primary objective: build one coherent personal-use system that demonstrates Artifact C (production ML service) and Artifact E (RAG + controlled agentic workflows) without training or fine-tuning an OCR model.

## 1. Product outcome

A user photographs a German shopping or expense receipt in a mobile browser. The system processes it asynchronously, extracts receipt and line-item data, asks for confirmation when confidence or validation is insufficient, records the expense, and updates interactive expenditure views. A grounded assistant can later answer questions, create charts, find supporting receipts, and perform approved actions such as recategorization or export.

The intended path is:

```text
mobile capture
    -> upload and validate
    -> asynchronous OCR/extraction
    -> normalize and validate
    -> review uncertain fields
    -> persist confirmed expenditure
    -> dashboards and search
    -> grounded assistant and approved actions
```

## 2. Assumptions and constraints

These assumptions make the plan executable without inventing enterprise requirements:

- One user initially; multi-tenancy is out of scope.
- Receipts are primarily German and denominated in EUR.
- Typical volume is tens to a few hundred single-page receipts per month, not thousands per day.
- No OCR model training or fine-tuning. Low-confidence cases go to user review.
- Amazon Textract is the first production OCR provider. It supports German text detection, receipt/invoice analysis, line items, confidence values, and geometry. Its performance on the actual receipt corpus must still be measured before relying on its normalized fields.
- Development and automated tests do not repeatedly call paid OCR or LLM APIs. Raw provider responses are stored and replayed.
- AWS is the only cloud learned and deployed for this project.
- Video-MLOps already covers the model-lifecycle project. This repository does not add MLflow, DVC, training pipelines, or model registration.
- The dashboard requires a small frontend, but a native Android/iOS application and a separate SPA are not required.
- Planning budget assumption: target at most EUR 15/month for the normal personal deployment and alert before EUR 25/month. Adjust these two numbers before the first cloud deployment.
- Accuracy means “safe with review,” not “silently perfect.” The system never invents a missing price or alters a financial record without confirmation.

## 3. Explicit non-goals

- Training or fine-tuning OCR, embedding, or language models
- Tax preparation, bookkeeping compliance, or financial advice
- Payment initiation or bank-account integration
- Multi-user organizations, roles, subscriptions, or billing
- Native mobile applications
- Microservices for each processing step
- Managed Kubernetes
- Arbitrary LLM-generated SQL
- A general-purpose autonomous agent
- Five OCR, vector database, or agent frameworks for comparison

## 4. Architecture decisions

### 4.1 Keep one modular application

Use one Python repository and one shared domain model. Run it as separate process types where necessary:

- `web`: FastAPI, HTML/PWA routes, JSON API, health endpoints
- `worker`: asynchronous receipt processing and retryable actions
- `scheduler`: optional periodic housekeeping; add only when a real scheduled task exists

This preserves production separation without paying the complexity cost of microservices.

### 4.2 Recommended stack

| Concern | Initial choice | Reason |
|---|---|---|
| Language | Python 3.12+ | Strong OCR/data ecosystem and one-language backend |
| API | FastAPI + Pydantic | Validation, async endpoints, generated OpenAPI |
| Persistence | PostgreSQL 16+ | Financial records, analytics, full-text search, pgvector |
| ORM/migrations | SQLAlchemy 2 + Alembic | Explicit schema evolution |
| Queue | Redis + Celery | Common production job/retry model; sufficient at personal scale |
| Object storage | Local filesystem in unit tests, MinIO locally, S3 in AWS | Cheap binary storage with a common interface |
| OCR | Amazon Textract behind one narrow adapter | No model training; pay per document; German text support |
| Embeddings | One small multilingual SentenceTransformers model on CPU | German semantic search without per-query API cost |
| Agent orchestration | Plain Python typed state machine | Observable and deterministic; add LangGraph only if state complexity proves it necessary |
| LLM | Bedrock model selected by an evaluation/cost check in Phase 6 | Stays within AWS; no model commitment before evidence |
| Web UI | Jinja2 + HTMX + Chart.js + minimal PWA manifest | Mobile capture and interactive charts without a separate frontend stack |
| Tests | pytest, Hypothesis where valuable, Playwright for critical UI flows | Unit, property, integration, and browser coverage |
| Observability | JSON logs, Prometheus metrics, OpenTelemetry traces | Covers logs, metrics, and traces with local open-source tooling |
| Packaging | `pyproject.toml`, uv, Ruff, mypy | Fast reproducible environment and compact CI |

Do not create generalized provider frameworks. Define one small OCR protocol because tests need a fake and production needs Textract. Add another real provider only if the acceptance corpus shows Textract is inadequate.

### 4.3 Target component flow

```text
Mobile PWA / Swagger / CLI
            |
            v
         FastAPI
       /    |     \
      v     v      v
PostgreSQL Redis  S3/MinIO
             |
             v
          Worker
             |
             v
      Textract AnalyzeExpense
             |
             v
 normalize -> validate -> review/confirm
             |
             v
     analytics + pgvector index
             |
             v
  router -> SQL/search/receipt/action tools
             |
             v
  structured answer + evidence + trace
```

### 4.4 Deployment profiles

Maintain three profiles, introduced only when their phase arrives:

1. **Local development:** Docker Compose with API, worker, PostgreSQL, Redis, MinIO, and observability. Paid providers are mocked by default.
2. **Economical personal production:** one small Linux host running the containers, S3 for encrypted receipt artifacts/backups, and pay-per-use Textract/Bedrock. PostgreSQL and Redis run on the host with tested backups. This is the normal always-on profile.
3. **Managed AWS demonstration:** ECS/Fargate, RDS PostgreSQL, managed Redis/Valkey, S3, IAM, Secrets Manager, CloudWatch, and an application load balancer only while validating the cloud architecture. Tear it down after evidence and documentation are captured unless its recurring cost is explicitly accepted.

This split is deliberate. Keeping RDS, managed Redis, multiple Fargate tasks, NAT gateways, and a load balancer running continuously is poor economics for one user.

## 5. Domain and data design

### 5.1 Core entities

- `receipt_job`: lifecycle, attempts, timestamps, error classification, idempotency key
- `receipt`: merchant, date/time, totals, currency, payment method, status, source hash
- `receipt_item`: raw description, normalized description, quantity, unit price, total, category, confidence
- `tax_summary`: rate/group, net, tax, gross
- `artifact`: original image, preprocessed image if created, raw OCR JSON, normalized JSON, storage reference, checksum
- `ocr_observation`: raw text, page, bounding box/polygon, confidence, provider and provider version
- `category`: controlled personal taxonomy
- `correction`: old/new value, reason, timestamp, source observation
- `budget`: period, category, amount, notification threshold
- `assistant_run`: user task, selected route, tool calls, evidence IDs, latency, tokens/cost, result status
- `action_request`: proposed mutation, idempotency key, approval state, execution result

### 5.2 Job state machine

```text
RECEIVED
  -> QUEUED
  -> PROCESSING
  -> NEEDS_REVIEW -> CONFIRMED
  -> CONFIRMED

Any processing state -> RETRYING -> PROCESSING
Any processing state -> FAILED
```

Rules:

- State transitions are validated and recorded.
- Retry only transient provider/network failures.
- Corrupt files, unsupported types, and failed invariants are permanent failures until user action.
- A confirmed receipt can be reprocessed only as a new version; never overwrite its provenance.
- Duplicate upload detection uses a content hash. Idempotency keys protect submission and external actions.

### 5.3 German receipt normalization

Implement deterministic normalization and validation before any LLM is introduced:

- decimal comma and thousands separators
- German date formats
- EUR symbol and currency variants
- `MwSt`, `USt`, `Netto`, `Brutto`, and VAT groups
- `Pfand`, returned deposits, coupons, discounts, and negative rows
- quantity-times-unit-price relationships
- subtotal/tax/total arithmetic with explicit rounding tolerance
- payment lines that must not be counted as purchases
- merchant-specific abbreviations only after repeated real examples justify rules

Never silently coerce an ambiguous value. Mark it for review and retain the source observation.

## 6. API and UI surface

### 6.1 Core API

- `POST /api/v1/receipts` — validate upload, store artifact, create job
- `GET /api/v1/jobs/{job_id}` — job state and safe failure details
- `GET /api/v1/receipts/{receipt_id}` — normalized result and evidence links
- `PATCH /api/v1/receipts/{receipt_id}` — approved correction with optimistic concurrency
- `POST /api/v1/receipts/{receipt_id}/confirm` — finalize reviewed receipt
- `POST /api/v1/receipts/{receipt_id}/reprocess` — explicit versioned reprocessing
- `GET /api/v1/receipts` — filters and cursor pagination
- `GET /api/v1/analytics/*` — typed aggregate endpoints used by charts
- `POST /api/v1/assistant/runs` — submit a grounded query/action task
- `GET /api/v1/assistant/runs/{run_id}` — structured result, citations, trace summary
- `POST /api/v1/actions/{action_id}/approve` — approve a proposed mutation
- `GET /health/live` — process liveness only
- `GET /health/ready` — required dependency readiness

### 6.2 Minimal UI

- Mobile capture/upload using `accept="image/*"` and `capture="environment"`
- Upload progress and asynchronous processing status
- Receipt review with confidence warnings and image-region highlighting
- Receipt history, search, filters, and correction history
- Category, merchant, and time-series dashboards
- Assistant panel showing answer, evidence, tool trace summary, and approval prompts

The first UI remains server-rendered. Reconsider a separate SPA only if interactions become unmaintainable after the complete vertical slice.

## 7. Artifact E design

### 7.1 Retrieval routes

Use the least expensive and most deterministic tool that can answer the task:

1. **Typed SQL analytics:** exact dates, sums, averages, groupings, category and merchant filters.
2. **Receipt lookup:** direct access by receipt ID, merchant, date, or cited evidence.
3. **Semantic retrieval:** fuzzy concepts over German receipt-item descriptions, such as “cleaning supplies” or “thesis equipment.”
4. **Hybrid retrieval:** semantic candidates constrained by structured metadata.
5. **Action tools:** recategorize, set a budget, export, mark for review; mutations require approval.

Do not allow arbitrary SQL. The model may emit only a validated query-plan schema with allow-listed fields, operators, aggregation functions, row limits, and a read-only database role.

### 7.2 Router and workflow

Start with deterministic routing for obvious requests. Use an LLM only for ambiguous intent or evidence synthesis.

```text
task
  -> authenticate and assign trace ID
  -> classify as read, proposed mutation, or unsupported
  -> select typed route/tool
  -> validate arguments and permissions
  -> retrieve evidence
  -> calculate numeric results in code/SQL
  -> optionally synthesize explanation
  -> verify citations refer to returned evidence
  -> return structured result
  -> await approval before any mutation
```

The workflow must support timeouts, bounded retries, idempotency, cancellation, and a maximum tool-call count. A failed or uncertain route must ask for clarification or abstain, not improvise.

### 7.3 Citations

Every material claim must cite one or more of:

- receipt ID and date
- line-item ID
- original artifact reference
- page and OCR bounding box
- exact aggregate query identifier and contributing receipt IDs

Selecting a citation should open the receipt and highlight the evidence region when geometry is available.

### 7.4 Permission boundaries

| Operation | Policy |
|---|---|
| Search/read/aggregate | Execute automatically |
| Generate chart or local preview | Execute automatically |
| Suggest a category/budget change | Propose only |
| Modify a saved expense | Explicit approval |
| Bulk recategorize | Explicit approval plus affected-count preview |
| Export sensitive data | Explicit approval |
| Delete a receipt | Explicit approval and recoverable soft delete |
| Payments/reimbursements | Unsupported |

## 8. Optimized delivery sequence

Each phase ends with a working vertical slice and a go/no-go gate. Do not begin the next expensive layer while the prior one is unreliable.

### Phase 0 — Foundation and cost controls (2–3 days)

Deliver:

- Repository skeleton, `pyproject.toml`, configuration model, formatting/type/test tools
- Architecture decision records for OCR provider, single-user deployment, and LLM boundaries
- `.env.example` without secrets
- GitHub Actions for lint, type check, and unit tests
- AWS Budget alert and cost-allocation tags before provisioning paid resources
- Receipt test-data policy: synthetic samples or personal receipts kept outside Git

Gate:

- `uv sync`, lint, type check, and tests run from a clean checkout.
- No cloud credential or receipt image can be committed.
- Monthly target and hard alert have explicit values.

### Phase 1 — Local Artifact C vertical slice (1–2 weeks)

Status: completed on 2026-08-30. The local stack and fake-OCR path passed the phase gate; Phase 2 remains intentionally unstarted.

Deliver:

- FastAPI submission/status/result endpoints
- PostgreSQL job/receipt tables and Alembic migration
- Redis/Celery worker
- MinIO object storage
- Fake OCR adapter returning a stored fixture
- Upload validation, content hash, idempotency, retries, and state transitions
- Dockerfiles using multi-stage builds and non-root runtime users
- `docker compose up` starts the complete local slice

Gate:

- A test image submitted through Swagger reaches `NEEDS_REVIEW` or `CONFIRMED` asynchronously.
- Restarting API or worker does not lose job metadata or artifacts.
- Duplicate submission and transient-worker failure tests pass.
- Live and ready endpoints behave differently when dependencies fail.

### Phase 2 — Real German receipt ingestion (2–3 weeks)

Status: in progress since 2026-09-02. Textract response parsing, German money/date normalization, provider selection, raw-response artifact storage, line-item persistence, and OCR evidence persistence are implemented without paid calls. Review/correction APIs and a private real-receipt acceptance corpus remain.

Deliver:

- Textract adapter and encrypted storage of raw response
- Deterministic German normalization and arithmetic validation
- Receipt/item/tax/observation schema
- Review and correction endpoints
- Small private acceptance corpus covering multiple merchants and difficult cases
- Provider calls disabled in ordinary CI; sanitized golden responses replayed instead

Gate:

- For the acceptance corpus, merchant, date, total, and every accepted line item are traceable to OCR evidence.
- Incorrect totals and low-confidence critical fields enter `NEEDS_REVIEW`.
- No field is fabricated when OCR evidence is missing.
- A new receipt consumes at most one normal OCR call unless the user explicitly requests reprocessing.

Decision point:

- If Textract plus deterministic post-processing is adequate, continue.
- If inadequate, first improve image capture guidance and review UX. Evaluate one off-the-shelf alternative only afterward. Training remains out of scope unless the user changes this constraint.

### Phase 3 — Personal product and analytics (2–3 weeks)

Deliver:

- Mobile PWA capture flow
- Review page with confidence and evidence highlighting
- Controlled category taxonomy and manual correction
- Receipt history and filters
- Typed analytics endpoints and Chart.js dashboard
- Category breakdown, monthly trend, merchant view, largest purchases, and uncategorized queue

Gate:

- The complete photograph-to-confirmed-dashboard flow works from a real phone.
- Dashboard totals reconcile exactly with confirmed receipt totals.
- Charts use typed backend aggregates, not calculations generated by an LLM.
- Core browser flow passes Playwright on mobile viewport.

MVP cut line: stop here temporarily if the product is not already useful for weekly personal expense tracking.

### Phase 4 — Production hardening and observability (1–2 weeks)

Deliver:

- Structured logs with request/job/receipt correlation IDs
- Prometheus service and job metrics
- OpenTelemetry trace from upload through worker/provider
- Error classification, retry budgets, dead-letter visibility
- Database and artifact backup/restore scripts and documented recovery exercise
- Rate limiting, size limits, CSRF/session protections, secret handling, retention policy
- SBOM/image scan and optimized container layers

Gate:

- A forced OCR timeout, worker crash, database outage, and malformed upload have expected states and logs.
- A restore test recovers a known receipt and its artifact.
- Logs do not contain receipt images, full OCR text, credentials, or unnecessary personal data.

### Phase 5 — Retrieval foundation (1–2 weeks)

Deliver:

- PostgreSQL `pgvector` extension
- CPU-generated multilingual embeddings for confirmed line items
- PostgreSQL full-text/lexical search and hybrid retrieval
- Metadata filters for dates, merchants, and categories
- Versioned Artifact E evaluation dataset with German queries and expected evidence
- Retrieval metrics: Recall@k, MRR, hit rate, latency

Gate:

- Exact financial filters remain SQL, not embeddings.
- Semantic retrieval materially beats lexical-only retrieval on predefined fuzzy queries.
- Missing-evidence cases return no result rather than an unrelated receipt.
- Re-indexing is deterministic, resumable, and does not call an external embedding API.

### Phase 6 — Grounded assistant (2–3 weeks)

Deliver:

- Typed router and query-plan schemas
- SQL analytics, receipt lookup, semantic search, and chart-spec tools
- Bedrock model chosen from a small evaluation on accuracy, latency, and cost
- Structured responses with verified citations
- Run/trajectory logging with tokens, provider cost, latency, route, and failure
- Cache only safe, immutable read results; invalidate on corrected evidence

Gate:

- Route selection and tool arguments pass the fixed evaluation set.
- Numerical answers equal independently computed SQL results.
- Every factual answer has valid evidence; missing evidence causes abstention.
- The model cannot issue arbitrary SQL or access artifacts outside the user scope.
- Per-run token/tool/time ceilings terminate runaway workflows.

### Phase 7 — Controlled actions and external tool (1–2 weeks)

Deliver:

- Preview/approve/execute state machine
- Recategorization, budget update, CSV export, and mark-for-review tools
- Idempotent action execution and audit history
- One mock downstream accounting/export endpoint for integration testing
- Adversarial tests for prompt injection inside OCR text and unauthorized mutations

Gate:

- No mutation or sensitive export occurs without an approval record.
- Replaying the same action key produces no duplicate effect.
- OCR text is always treated as untrusted evidence, never as instructions.
- Partial downstream failure is retryable and visible without losing local state.

Artifact E cut line: router, retrieval, safe SQL, an external tool, structured evidence, evaluation, trace, cost metrics, and approval boundaries are all demonstrated.

### Phase 8 — CI/CD and economical AWS production (1–2 weeks)

Deliver:

- GitHub Actions stages: lint/type, unit, integration with service containers, browser smoke, Docker build, vulnerability scan, registry push, staging deploy, smoke test, manual production approval
- Immutable image tags by commit SHA and rollback procedure
- One small-host personal deployment, S3, IAM least privilege, Secrets Manager/Parameter Store decision, CloudWatch export, TLS/private access decision
- Automated encrypted backups and lifecycle rules for artifacts/logs
- Deployment smoke test covering upload, worker, persistence, and read-only assistant query

Gate:

- A tagged commit deploys staging and only an approved workflow deploys production.
- Rollback restores the previous image without schema loss.
- Idle monthly estimate is within the chosen budget before launch.
- Billing alarms, S3 lifecycle rules, log retention, and backup retention are active.

### Phase 9 — Managed AWS skills deployment, then teardown (3–5 days)

Deliver temporarily:

- ECS/Fargate API and worker
- RDS PostgreSQL
- managed Redis/Valkey
- S3, IAM roles, Secrets Manager, CloudWatch, load balancing and networking
- Documented deployment, evidence, measured monthly estimate, and teardown checklist

Gate:

- Integration smoke tests pass in the managed topology.
- IAM roles are workload-specific and secrets are not in images or task definitions.
- The environment is destroyed or scaled down immediately after validation unless its recurring cost is approved.

### Phase 10 — Kubernetes P1, local only (3–5 days)

Deliver:

- kind deployment with `Deployment`, `Service`, `Ingress`, `ConfigMap`, `Secret`, readiness/liveness probes, resource requests/limits, worker autoscaling concept, Job, and rolling update
- One failure and one rolling-update exercise

Gate:

- Pods become ready only after dependencies are usable.
- A bad release fails readiness without taking down the prior revision.
- No managed Kubernetes cluster is created for this personal project.

### Phase 11 — Terraform P2 (after manual AWS deployment works)

Deliver:

- Reproducible AWS networking, compute, database, storage, IAM, secrets references, logs, budgets, and lifecycle policies
- Separate disposable staging state
- Plan review in CI; apply requires approval
- Destruction tested on staging

Gate:

- A clean staging environment can be created, smoke-tested, and destroyed from documented commands.
- `terraform plan` contains no unmanaged surprise replacements and no secrets.

## 9. Test and evaluation strategy

### 9.1 Test pyramid

- **Unit:** parsing, decimal/date normalization, totals, state transitions, query-plan validation, citation validation.
- **Property-based:** localized money strings, arithmetic invariants, idempotency, pagination boundaries.
- **Contract:** fake and captured Textract responses against the OCR adapter contract.
- **Integration:** FastAPI, worker, PostgreSQL, Redis, and MinIO through Docker Compose.
- **End-to-end:** phone-sized upload/review/dashboard and assistant read/action approval flows.
- **Resilience:** provider throttling, timeout, worker restart, duplicate delivery, database outage, corrupted artifacts.
- **Security:** malicious filenames, oversized images, decompression bombs, OCR prompt injection, tool argument injection, unauthorized action replay.

### 9.2 Fixed Artifact E evaluation set

Create versioned, privacy-safe cases for:

- exact aggregation
- fuzzy item retrieval
- hybrid date/category filtering
- comparison between periods
- missing evidence and abstention
- ambiguous user intent and clarification
- chart specification correctness
- citation-to-receipt correctness
- proposed mutation and approval
- injection text printed on a receipt
- tool timeout and retry

Track route accuracy, Recall@k, MRR, numerical correctness, citation correctness, unsupported-claim rate, task completion, tool count, latency, and estimated cost per run.

## 10. Cost-control policy

### 10.1 Build-time controls

- Develop against fake OCR/LLM adapters and stored sanitized responses.
- Run paid smoke tests manually or on protected branches, never on every commit.
- Store the raw OCR response permanently with its checksum; parse it repeatedly without paying again.
- Generate embeddings locally on CPU and only for confirmed/changed items.
- Use deterministic SQL and rules before calling an LLM.
- Send only the minimum evidence required to the LLM; never send the full receipt history.
- Cache immutable analytical results where correctness allows it.
- Set per-run token, tool-call, retry, and wall-clock limits.

### 10.2 Infrastructure controls

- Local Docker Compose is the default until Phase 8.
- Prefer one always-on host over several minimum-billed managed services for personal production.
- Avoid NAT gateways, managed Kubernetes, multi-AZ databases, and idle load balancers in the normal profile.
- Use S3 lifecycle policies and short log retention appropriate for personal use.
- Stop or destroy staging automatically after validation.
- Tag every cloud resource by project, environment, owner, and expiry.
- Review AWS Cost Explorer monthly and document cost per receipt and cost per assistant task.
- Treat free tiers as temporary discounts, not architecture assumptions.

### 10.3 Spend gates

Before enabling each paid component, record:

1. What user-visible capability it unlocks.
2. Expected calls/storage/compute per month.
3. Expected idle and variable cost.
4. A cheaper alternative and why it was rejected.
5. The alert and shutdown condition.

No phase should add a continuously billed service merely to satisfy a resume keyword. The temporary managed AWS phase exists to demonstrate the skill and is explicitly disposable.

## 11. Security and privacy baseline

Receipts reveal location, habits, payment details, and potentially health-related purchases. Minimum controls:

- Private repository; no personal receipt fixtures in Git or public CI artifacts
- HTTPS or private network access from the first remote deployment
- Single-user authentication with secure session cookies and CSRF protection
- S3 encryption, blocked public access, least-privilege IAM, and short-lived workload credentials
- Encrypted database and backups; restore procedure tested
- Redaction of payment-card fragments and unnecessary personal fields
- Logs contain identifiers and metrics, not raw OCR content
- Soft-delete grace period followed by artifact/database deletion
- OCR and LLM data-flow documentation, including provider retention settings
- Treat receipt text as untrusted data, especially when it reaches the assistant

## 12. Principal risks and mitigations

| Risk | Early signal | Mitigation |
|---|---|---|
| Textract performs poorly on German supermarket receipts | Acceptance corpus has low critical-field/line-item accuracy | Improve capture quality and review UX; test one off-the-shelf provider before reconsidering scope |
| Line-item categorization is ambiguous | High correction rate | Small personal taxonomy, merchant/item aliases learned from confirmed corrections, confidence threshold |
| LLM is used where SQL should be used | Numeric errors or unnecessary cost | Typed router, deterministic aggregates, independent result verification |
| “Agent” becomes an unsafe general executor | Arbitrary SQL/tools or invisible mutations | Allow-listed schemas, bounded workflow, approval state machine, audit log |
| Frontend expands into a second project | Time spent on framework plumbing | Server-rendered PWA, five core screens, Chart.js only |
| Personal AWS topology is too expensive | Idle cost dominates per-receipt cost | Single-host production; managed stack time-boxed and torn down |
| Receipt fixtures leak private data | Real images appear in Git/CI | Synthetic fixtures and sanitized provider JSON; private corpus outside repository |
| Scope reaches Kubernetes/Terraform before product value | Infrastructure exists but scanning is unused | Hard phase gates and MVP cut line after Phase 3 |

## 13. Definitions of done

### Artifact C is done when

- `docker compose up` starts API, worker, PostgreSQL, Redis, storage, and required observability.
- A mobile upload is validated, processed asynchronously, persisted, reviewed, and retrieved.
- Metadata, raw output, normalized output, and source artifacts retain provenance.
- Duplicate delivery, retries, permanent failure, cancellation/reprocessing policy, and idempotency are tested.
- Logs, metrics, traces, live/readiness endpoints, backups, restore, and CI/CD are demonstrated.
- The service has run in AWS and can roll back safely.

### Artifact E is done when

- The router selects among typed SQL, receipt lookup, semantic/hybrid retrieval, chart, and action tools.
- Responses are structured, numerically verified, and grounded in clickable receipt/line-item evidence.
- Retrieval and agent behavior are evaluated on a fixed German dataset.
- Runs record route, tools, evidence, failures, latency, tokens, and cost.
- Timeouts, retries, fallbacks, idempotency, injection defense, and approval boundaries are tested.
- At least one read-only multi-step query and one approval-controlled external action work end to end.

## 14. Planned repository shape

Create this structure incrementally; do not generate empty modules before their phase:

```text
expense-intelligence-platform/
├── PLAN.md
├── README.md
├── pyproject.toml
├── compose.yaml
├── Dockerfile
├── .env.example
├── migrations/
├── src/expense_intelligence/
│   ├── api/
│   ├── domain/
│   ├── persistence/
│   ├── jobs/
│   ├── ocr/
│   ├── analytics/
│   ├── retrieval/
│   ├── assistant/
│   └── web/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
├── deploy/
│   ├── aws/
│   ├── kubernetes/
│   └── terraform/
└── docs/
    ├── decisions/
    ├── operations/
    └── evaluations/
```

## 15. Immediate next action

Implement Phase 0 only, then Phase 1 as a complete fake-OCR vertical slice. Do not begin Textract integration, dashboards, RAG, LLM routing, Kubernetes, or Terraform until the asynchronous local job flow passes its gate.

Useful official references verified for this plan:

- Textract receipt/invoice processing: https://docs.aws.amazon.com/textract/latest/dg/analyzing-document-expense.html
- Textract supported document languages and limits: https://docs.aws.amazon.com/textract/latest/dg/limits-document.html
- Textract expense fields, confidence, and geometry: https://docs.aws.amazon.com/textract/latest/dg/invoices-receipts.html
- AWS Fargate cost model: https://aws.amazon.com/fargate/pricing/
- Amazon RDS for PostgreSQL pricing model: https://aws.amazon.com/rds/postgresql/pricing/
