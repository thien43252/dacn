# Teacher assistant evaluation data

Run from `backend`:

```sh
uv run python ../eval/run_lms_assist.py
uv run python ../eval/run_lms_assist.py --provider openai
uv run ruff check ../eval/run_lms_assist.py
```

`reference.jsonl` links two original Vietnamese grade 8 lessons to five facts
each. The lessons contain 478 and 518 whitespace-delimited words respectively.
The science lesson uses the application's `ly` subject code.
`essays.jsonl` contains 30 original, synthetic student answers: ten maths,
ten science and ten literature responses, from incorrect to complete.
Each record includes a 10-point analytic rubric and a model answer.

`teacher_score` values are authored reference labels, not scores collected from
independent teachers. Review these labels with teachers before using this small
dataset as empirical evidence of SC-010. Answers are deliberately short; this
does not establish performance on full-length essays or other grade levels.

Fake mode uses fixed, structurally valid questions and a constant grade of 5,
independent of reference scores. Its metrics are not model quality measurements.
It always exits 0, while reporting pipeline failures explicitly. Real runs use
the selected chat provider for generation, grading and judging, with model names
from `.env`; embeddings use the configured provider (fake embeddings in fake mode).
Shared generator/judge biases limit the interpretation of SC-009 results.

Missing questions count against the five requested questions per lesson. Failed
grading suggestions count against agreement; MAE covers successful suggestions
only and reports its sample count. Real runs exit 1 for missed 80% targets or
pipeline/judge errors. Full question judgments, grades and errors are saved to
`eval/results/lms_assist-*.json`. Uploads use a temporary directory and databases
are fresh in-memory SQLite instances.
