---
description: Have the examiner grade a report section, the docs, the demo script or the whole submission against the module's requirements
argument-hint: "[scope: docs/report/approach.md, the demo script, or empty for the whole submission]"
---

Examine: $ARGUMENTS (if empty, the whole submission).

1. Run the `examiner` agent on that scope only. Give it the date and point it at `.project-context/course-content/` for the requirements and rubric.
2. Check each of its factual claims about the repository yourself (a figure, a missing file, a claim it says is unsupported) before passing it on; drop what doesn't hold and say so.
3. Write the result to `docs/review/examiner-assessment-<YYYY-MM-DD>.md` (add `-<scope>` if scoped), in the style of the earlier assessments there: grade by criterion, the evidence for each, the questions an examiner would ask, and the fixes that would raise the grade most, each with a measurable "done when".
4. Add the fixes the team must make to the to-do (scratchpad source, `docs/briefs/` copy, republish). Don't commit unless asked.
