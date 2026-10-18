# Changelog

## 0.6.2

All additions are optional, so every 0.6.1 review is valid under 0.6.2.

### Schema

- `target.identifiers.valency_id` gives the work's Valency Hub ID: `W_` and at least 8
  characters from a-z and 2-9 without `i`, `l` and `o` (`W_6r533gdt`), or one version's ID,
  with `_v` and the version number (`W_6r533gdt_v2`). Its page is
  `https://hub.valency.io/works/<id>`. `target.work_id` takes `valency_id:<id>`, which comes
  after OpenAlex in the resolution priority.
- `referee.human_referee.valency_id` gives the reviewer's Valency Hub author ID (`A_7zdytxzb`),
  whose page is `https://hub.valency.io/authors/<id>`.

### Python package

- `validate_valency_work` and `validate_valency_author` check the two ID formats, and
  `build_work_identifiers` takes `valency_id`, adding its Hub link.
- A `work_id` given as a Hub work page (`https://hub.valency.io/works/W_…`) or as a Hub
  citation (`vlnc:W_…`) becomes `identifiers.valency_id`, not a `permalink` or an
  `internal_id`.

- New mapper `reviewer3` for Reviewer3's Markdown report: `map_with_record` takes the
  report's text as `output`. The Overview becomes `opinion.contributions`; AI Text
  Detection, Fatal Flaws and Reference Check become `checks`, with an `outcome` only for
  Fatal Flaws, which states one; Reviewer Comments become `findings.comments`, with no
  severity, and each comment's page and excerpt become an evidence link. The schema is
  unchanged.

## 0.6.1

All additions are optional, so every 0.6.0 review is valid under 0.6.1.

### Schema

- `checks` records systematic checks run on the work, including those that found nothing:
  AI-text detection, reference verification, fatal-flaw screens, similarity, image
  integrity, statistics and retractions. Each check has a `kind`, the tool that ran it
  (`performed_by`; absent means the referee), an `outcome` only when the source states one,
  the source's `summary`, `measurements` (a proportion is a 0–1 `fraction`) and per-item
  results (`items`: what was checked, the source's `status`, and whether it was `flagged`).
  `finding_ids` links a check to the findings that report its problems.
- `opinion.contributions` lists what the work contributes, as the reviewer reads it, with an
  optional `title` and a `claim_id` in `claim_assessments`. Contributions are neither
  strengths nor assessed claims.
- `findings.comments` holds points the source does not classify as strengths, weaknesses or
  questions. A review whose only points are comments is valid.
- `text_format` says how the review's free text is written: `markup` (`plain`, `markdown`
  or `html`) and `math` (`none` or `tex`).
- Evidence links' `work` takes `citation`, the reference as printed.
- `target.title` gives the work's title, as the review gives it.
- `validate_canonical` also checks that check ids are unique among checks, findings and
  action items, that `checks[].finding_ids` name findings, and that
  `opinion.contributions[].claim_id` names a claim in `claim_assessments`.

## 0.6.0

All additions are optional, so every 0.5.0 review is valid under 0.6.0.

### Schema

- Findings take an `id`, unique among the review's findings and action items, a `group`
  (the review's headings the point sits under, outermost first) and `suggested_edits`
  (rewrites the reviewer proposes: a `replacement` and, optionally, the `original` text).
- A finding that restates others in brief lists their ids in `summarizes`, so it can be
  left out when counting points. `summarizes: []` marks an overview whose source does not
  say which points it covers.
- Action items (`findings.changes` and `ethics_and_risk.required_mitigations`) take an
  `id`, `title`, `evidence_links`, `suggested_edits` and `group`, as findings do, and
  `applies_to.finding_id` names the finding they address.
- Evidence locations take `page_end` for a page range. Evidence links take the type
  `bibliography`, for the work's own reference list, and a `work` (title, authors, year,
  identifiers) for another work, such as a citation the reviewer says is missing.
- `review_context.review_type` takes `pre_submission`: feedback the authors asked for
  before submitting.
- `validate_canonical` also checks what JSON Schema cannot: ids are unique, `summarizes`
  and `applies_to.finding_id` name findings that exist, and `page_end` is not before `page`.

### Python package

- New mapper `deepreview` for Google DeepReview's Markdown report: `map_with_record`
  takes the report's text as `output`.
- `map_with_record` no longer requires `reviewer_commit` or `model_id`. It takes
  `reviewer_version` for a reviewer with releases rather than commits; what is not given
  is `unspecified`. `map_from(..., keep_raw=True)` keeps a Markdown report as
  `raw_payload.text`.
- Mapping records have a `parsed` rule for values a mapper reads out of the reviewer's
  text by a pattern, and `Recorder.parse` to record them.

## 0.5.0

- Added `review_context.stage`, `pre_publication` or `post_publication`, after Crossref's
  peer-review `stage`. Removed `post_publication` from `review_context.review_type`, which
  now only says what kind of review it is. Existing records must move that value to
  `stage` and set `review_type` to the kind of review, for example `initial` or
  `community_comment`.
- Added the Crossref peer-review types OCRS could not express to
  `review_context.review_type`: `author_comment`, `community_comment`, `aggregate` and
  `recommendation`. Of Crossref's other types, `referee-report` is `initial`, `revision`
  or `rebuttal_response` depending on the round, `editor-report` is `meta_review`, and
  `manuscript` is the reviewed manuscript itself rather than a review, so it has no value.

- Added optional `provenance.review_doi`, the DOI registered for the review itself
  (e.g., a Crossref peer review DOI). The reviewed work's DOI stays in
  `target.identifiers.doi`.
- Added `proceedings_article` to `target.work_type`, for papers published in
  conference proceedings.

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
- Replaced `findings.required_changes` and `findings.optional_suggestions` with one
  `findings.changes` list. A change's `priority` is now `critical`, `major`, `minor`, or
  `trivial` (was `low`, `medium`, `high`, or `blocking`) and says how serious the problem
  is, not whether the reviewer requires the change; `decision.revision_requirement` still
  records that. The new values also apply to `ethics_and_risk.required_mitigations`.
  Existing records must move both lists into `changes` and map each priority to a new value.

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
