# ============================================================================
# ironframe/logic/cqot_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Critical Questions of Thought (CQoT) battery.
#
# Based on December 2024 arXiv research operationalizing Toulmin for LLMs.
# Three-phase process:
#   1. DECOMPOSE: separate premises from conclusions (no final answer yet)
#   2. INTERROGATE: run critical questions against each argument element
#   3. SYNTHESIZE: produce final answer only after validity check
#
# Each Toulmin component has its own set of critical questions.
# Questions are binary (yes/no) for programmatic evaluation.
#
# Dual use:
#   1. SAE Tier 0: prompt addendum forcing critical self-examination
#   2. Structured validation: programmatic check of argument quality
#
# Usage:
#   from ironframe.logic.cqot_v1_0 import (
#       cqot_prompt, CRITICAL_QUESTIONS, evaluate_argument,
#   )
#   print(cqot_prompt())  # inject into system prompt
#
#   results = evaluate_argument(toulmin_arg)
#   print(results)  # per-component question results
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---- Critical Questions per Toulmin Component ----

CRITICAL_QUESTIONS: Dict[str, List[str]] = {
    "claim": [
        "Is the claim explicitly stated, not buried or implicit?",
        "Is the claim falsifiable (could evidence prove it wrong)?",
        "Is the claim scoped (not universal/absolute without justification)?",
    ],
    "grounds": [
        "Is each piece of evidence specific and verifiable?",
        "Are the grounds sufficient to support the claim (not just one anecdote)?",
        "Are the grounds current and relevant to the claim's domain?",
        "Could the same grounds support a contradictory claim?",
    ],
    "warrant": [
        "Does the warrant explain WHY the grounds support the claim (not just restate them)?",
        "Does the warrant hold in this specific domain context?",
        "Is the warrant a recognized principle, or an assumption being treated as one?",
        "Would the warrant survive a direct challenge to its strongest premise?",
    ],
    "qualifier": [
        "Is a confidence level stated (not presented as absolute certainty)?",
        "Are scope conditions specified (when/where does this apply)?",
        "Are known limitations acknowledged?",
    ],
    "rebuttal": [
        "Is the strongest counterargument identified (not a strawman)?",
        "Is the counterargument addressed with evidence (not just dismissed)?",
        "Are there obvious objections that were not considered?",
    ],
    "backing": [
        "If the warrant is non-obvious, is it itself supported?",
        "Is the backing from a credible source or established principle?",
    ],
}

# All questions flattened for quick reference
ALL_QUESTIONS = []
for component, questions in CRITICAL_QUESTIONS.items():
    for q in questions:
        ALL_QUESTIONS.append({"component": component, "question": q})


@dataclass
class QuestionResult:
    """Result of evaluating a single critical question."""
    component: str
    question: str
    answer: Optional[bool] = None   # True=pass, False=fail, None=not evaluated
    note: str = ""


@dataclass
class CQoTResult:
    """Result of running the full CQoT battery on an argument."""
    results: List[QuestionResult] = field(default_factory=list)

    @property
    def total_questions(self) -> int:
        return len(self.results)

    @property
    def evaluated(self) -> int:
        return sum(1 for r in self.results if r.answer is not None)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.answer is True)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.answer is False)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.evaluated if self.evaluated > 0 else 0.0

    @property
    def weak_components(self) -> List[str]:
        """Components where any question failed."""
        failed_components = set()
        for r in self.results:
            if r.answer is False:
                failed_components.add(r.component)
        return sorted(failed_components)

    def by_component(self) -> Dict[str, List[QuestionResult]]:
        """Group results by Toulmin component."""
        grouped: Dict[str, List[QuestionResult]] = {}
        for r in self.results:
            grouped.setdefault(r.component, []).append(r)
        return grouped

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total_questions,
            "evaluated": self.evaluated,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 3),
            "weak_components": self.weak_components,
        }

    def format(self) -> str:
        """Human-readable report."""
        lines = [f"CQoT Battery: {self.passed}/{self.evaluated} passed "
                 f"({self.pass_rate:.0%})"]
        for component, questions in self.by_component().items():
            lines.append(f"\n  {component.upper()}:")
            for q in questions:
                if q.answer is True:
                    mark = "[PASS]"
                elif q.answer is False:
                    mark = "[FAIL]"
                else:
                    mark = "[----]"
                lines.append(f"    {mark} {q.question}")
                if q.note:
                    lines.append(f"           {q.note}")
        if self.weak_components:
            lines.append(f"\n  Weak components: {', '.join(self.weak_components)}")
        return "\n".join(lines)


def evaluate_argument(
    toulmin_arg,
    answers: Optional[Dict[str, Dict[int, bool]]] = None,
) -> CQoTResult:
    """Run CQoT battery against a ToulminArgument.

    If `answers` is provided, use them (programmatic evaluation).
    Format: {component: {question_index: True/False}}

    If `answers` is None, auto-evaluate based on whether the Toulmin
    component is populated (basic structural check, not semantic).
    """
    results = []

    for component, questions in CRITICAL_QUESTIONS.items():
        for i, question in enumerate(questions):
            # Check if answer was provided
            if answers and component in answers and i in answers[component]:
                answer = answers[component][i]
                results.append(QuestionResult(
                    component=component, question=question, answer=answer
                ))
                continue

            # Auto-evaluate: structural check based on component presence
            if answers is None:
                has_content = _has_component(toulmin_arg, component)
                # First question for each component: "is it present?"
                if i == 0:
                    results.append(QuestionResult(
                        component=component, question=question,
                        answer=has_content,
                        note="" if has_content else f"No {component} provided",
                    ))
                else:
                    # Can't auto-evaluate semantic questions
                    results.append(QuestionResult(
                        component=component, question=question,
                        answer=None, note="Requires semantic evaluation",
                    ))
            else:
                results.append(QuestionResult(
                    component=component, question=question, answer=None,
                ))

    return CQoTResult(results=results)


def _has_component(arg, component: str) -> bool:
    """Check if a Toulmin argument has a given component populated."""
    val = getattr(arg, component, None)
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, list):
        return len(val) > 0 and any(v.strip() for v in val if isinstance(v, str))
    return bool(val)


def cqot_prompt() -> str:
    """Return a prompt addendum implementing the CQoT three-phase process.

    Inject into system prompt for SAE Tier 0 (free, no API call).
    """
    return """Before finalizing any analytical conclusion, follow this three-phase process:

PHASE 1 - DECOMPOSE:
Separate your reasoning into explicit premises and conclusions. For each step:
  P1: [premise]
  P2: [premise]
  -> C1: [conclusion, derived from P1 and P2]
Do NOT state your final answer yet.

PHASE 2 - INTERROGATE:
For each conclusion, answer these critical questions:
  - Does this conclusion follow necessarily from the premises, or only probably?
  - Is any premise unverified or assumed rather than established?
  - What contradictory evidence exists that I have not addressed?
  - Does my reasoning bridge (warrant) actually connect evidence to conclusion, or am I making a logical leap?
  - Would this conclusion survive a direct challenge to its strongest premise?
  - Am I confusing correlation with causation, or anecdote with pattern?

PHASE 3 - SYNTHESIZE:
Only after completing Phase 2, produce your final answer. Include:
  - Your conclusion with explicit confidence qualifier
  - The strongest counterargument you identified
  - Any premises that remain unverified

If Phase 2 reveals a broken reasoning chain, revise your conclusion rather than proceeding with a flawed one."""


def cqot_validation_prompt() -> str:
    """Return a prompt for running CQoT on an existing argument.

    Use as a follow-up evaluation prompt.
    """
    questions_text = []
    for component, questions in CRITICAL_QUESTIONS.items():
        questions_text.append(f"\n{component.upper()}:")
        for q in questions:
            questions_text.append(f"  - {q}")

    return f"""Evaluate the argument above by answering each critical question with YES or NO, plus a brief justification.

{"".join(questions_text)}

For each NO answer, explain specifically what is missing or weak.
At the end, list the weak components and suggest how to strengthen them."""
