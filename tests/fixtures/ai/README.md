# AI reviewer fixtures

A trimmed real output of an AI reviewer on one paper, used by `tests/test_ai_mappers.py`.

| File | What it is |
|---|---|
| `openaireview_paper.json` | OpenAIReview's `paper.json`, with 3 of its 24 merged comments, 1 unmerged comment and 2 paragraphs |
| `paper_blocks.json` | Paragraphs, abstract and references of the paper, as plain text, for matching quotes |

The review ran on 2026-10-03 with Claude Opus 5.5 (`us.anthropic.claude-opus-5-5`), OpenAIReview at commit `27740f8434cf` (v0.3.0).

The quotes and paragraphs come from Makan Farhoodimoghadam, Avery Louis, Joshua S. Bloom and Karthik Ram, "Beyond Document Relevance: Evaluating Citation-Set Structure in Citation Recommendation", licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Only short excerpts are included.
