# Question eval

Fifteen business questions with expectations, run against a live agent server on the synthetic
fixtures and graded against ground truth computed from the same fixtures. Not part of `pytest`;
it needs a model.

```bash
uv run langgraph dev --no-browser --port 2025          # or any server exposing the graph
uv run python tests/eval/run_questions.py http://127.0.0.1:2025 results.jsonl
uv run python tests/eval/grade.py results.jsonl        # numeric checks + a review table
```

`grade.py` verifies the figures that have a deterministic answer (spend, CPA per window) and
prints every answer's tools, timing, and the expectation to judge by hand. Add a question by
appending to `questions.json` with an `expect` line; add a numeric check in `grade.py` when the
answer has one.

The grader shifts its windows by the same fixture anchor the server uses (`PAID_MEDIA_FIXTURE_ANCHOR`,
default two days ago), so figures line up on any day.
