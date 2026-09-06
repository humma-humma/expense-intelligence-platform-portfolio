# ADR 0003: Use a bounded assistant, not an autonomous agent

- Status: accepted
- Date: 2026-08-29

## Context

Expense questions require exact arithmetic, traceable evidence, privacy, and controlled mutations. A general agent or arbitrary text-to-SQL interface would add risk without increasing personal utility.

## Decision

Use deterministic routing where possible, allow-listed typed query plans, read-only SQL execution, bounded tool calls, evidence verification, and explicit approval for every mutation or sensitive export. Add an LLM only after retrieval and SQL tools have fixed evaluation cases.

## Consequences

- Financial calculations remain in SQL or application code.
- Receipt text is evidence and is always treated as untrusted input.
- Every future action tool needs a permission rule, idempotency behavior, and audit record.

