# Changelog

## 0.5.0

- Renamed metric `uncertainty.confidence` to `uncertainty.credence`, retaining the
  0–1 bounds, interval, and rationale. Existing records must rename this nested key.

- Added shared structured evidence locations with section, one-based page, document
  version, and exact text anchors with surrounding context. Artifact assessments now
  support the same `evidence_links` as claims, findings, and metrics.

- Split acceptance recommendations from `decision.revision_requirement`, with `none`,
  `minor`, `major`, and `unspecified` options. Revision-only source decisions no longer
  imply an acceptance judgment. This replaces the revision values in the old enum.
- Updated decision mappers, examples, and migration guidance. Published v0.4.0 is unchanged.
- Removed duplicate `seed` and `seeds` fields from `ai_referee.execution`.
  Review-run seeds live in `referee.reproducibility`; explicit stage seeds override
  the whole-review seed. Existing records must move execution seeds to that location.
- `target.identifiers` takes every identifier type Crossref uses for related items:
  `handle`, `ark`, `isbn`, `issn`, `ecli`, `accession` (with an optional `database`),
  `purl` and `uuid`. All are optional, so existing records stay valid. `issn` names the
  journal or series, so it never becomes the primary identifier. `ocrs.identifiers`
  adds validators, resolver URLs and `build_work_identifiers` arguments for them.
- `target.work_id` has a format: `<type>:<value>`, where `<type>` is the primary
  identifier's key in `target.identifiers` (`doi:10.7554/eLife.112155.1`). An internal ID
  also names its field (`internal_id:openreview_forum:2dnO3LLiJ1`), and a work with no
  identifier is `unknown`. Existing records must rewrite `work_id`;
  `generate_canonical_work_id(identifiers)` builds it. Mappers now derive it from
  `identifiers`, so a DOI wins over a platform's paper ID, and `map_to` reads the platform
  ID back from `identifiers.internal_id`. `map_with_record`'s `work_id` still takes any
  identifier of the paper.
- `target` names the exact version reviewed. Its other versions and forms go in the new
  `target.relations`: each has a `type`, its `identifiers` and an optional `version`. The
  types are Crossref's intra-work relation types (`is_version_of`, `is_preprint_of`,
  `replaces`, `is_same_as`, …) and DataCite's `is_new_version_of` and
  `is_previous_version_of`, in snake_case. `target.revision_of` is deprecated: use a
  relation of type `is_new_version_of`.

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
