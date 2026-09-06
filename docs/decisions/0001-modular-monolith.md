# ADR 0001: Start with a modular monolith

- Status: accepted
- Date: 2026-08-29

## Context

The system needs an API, background worker, receipt processing, analytics, and an assistant, but initially serves one person. Independent microservices would multiply deployment, networking, tracing, and data-consistency work before any user value exists.

## Decision

Keep one Python package and one domain model. Run the API and worker as separate process types when Phase 1 introduces asynchronous jobs. Split a component only when measured scaling, security, or release-independence requirements demand it.

## Consequences

- Local development and low-cost deployment remain simple.
- Module boundaries still separate API, jobs, OCR, analytics, retrieval, and assistant code.
- Process-level scaling remains possible without distributed service ownership.

