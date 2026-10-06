# Example reviews

Each file is a complete OCRS review, and the tests validate every one.

| File | What it shows |
|---|---|
| `human-review.json` | A single-blind journal review by a person: scores, a recommendation, and findings that point to sections and figures |
| `ai-review.json` | An AI review: OpenAIReview's output on a preprint, mapped by `map_with_record`, with the reviewer's commit, the model and the run times, and the reviewer's unmapped fields in `extensions.openaireview` |
| `hybrid-review.json` | A review an AI system drafted and a person checked, edited and approved, with what each contributed |

`human-review.json` and `hybrid-review.json` are made up. `ai-review.json` is a real OpenAIReview run on Makan Farhoodimoghadam, Avery Louis, Joshua S. Bloom and Karthik Ram, "Beyond Document Relevance: Evaluating Citation-Set Structure in Citation Recommendation", licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); it quotes short excerpts of the paper.
