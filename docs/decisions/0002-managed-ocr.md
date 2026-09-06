# ADR 0002: Use managed OCR without model training

- Status: accepted
- Date: 2026-08-29

## Context

The product needs German receipt extraction, but OCR training and lifecycle engineering are already covered elsewhere and would delay the usable expense tracker. Personal volume makes pay-per-document OCR economically plausible.

## Decision

Use Amazon Textract as the first production OCR provider behind a narrow adapter. Store each raw provider response and reparse it without another paid call. Use sanitized recorded responses and a fake adapter in tests. Send uncertain critical fields to review rather than training a model.

## Reconsideration trigger

Only evaluate one off-the-shelf alternative if a representative private receipt corpus shows unacceptable critical-field or line-item performance after capture guidance and deterministic post-processing are improved. Training remains out of scope unless explicitly authorized.

