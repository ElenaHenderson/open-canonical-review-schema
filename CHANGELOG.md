# Changelog

## 0.4.0

The first public version.

### Schema

- `$id` is `https://valency-oss.github.io/open-canonical-review-schema/v0.4.0/canonical-review.schema.json`, and each version is published at its own URL.
- A human review no longer needs a `human_referee` object.
- Findings and claim assessments take optional `probability` (how likely the statement is true, 0–1) and `credence` (how confident the reviewer is in that probability, 0–1). `credence` needs `probability`.

### Python package

- `map_from` keeps an AI reviewer's raw output in `provenance.raw_payload` when `keep_raw=True`.
- The OpenReview mapper leaves out `referee_id` and `source_review_id` when the note has no signature or `id`, instead of writing `null`.
- Removed the PAT mapper.
- `ocrs.mappers.ai` (was `ocrs.mappers._ai`) holds the helpers the AI reviewer mappers are built on.
