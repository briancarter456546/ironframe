# ============================================================================
# ironframe/sae/judge_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# LLM-as-judge verification via MAL.
#
# Evaluates LLM output per-claim for:
#   - Factual consistency with provided context
#   - Logical coherence (conclusions follow from premises)
#   - Task alignment (output addresses what was asked)
#
# Uses a fast/cheap model by default to minimize cost at Tier 1.
#
# Usage:
#   from ironframe.sae.judge_v1_0 import Judge
#   from ironframe.mal import get_client
#
#   client = get_client()
#   judge = Judge(client)
#   verdict = judge.evaluate(
#       original_prompt='What causes inflation?',
#       output_text='Inflation is caused by increased money supply...',
#   )
#   print(verdict)
#   # {'approved': True, 'claims': [...], 'issues': [], 'summary': '...'}
# ============================================================================

import json
from typing import Any, Dict, List, Optional

_JUDGE_SYSTEM_PROMPT = """You are a factual verification judge. Your job is to evaluate an AI-generated response for accuracy and logical soundness.

Given the ORIGINAL PROMPT and the AI OUTPUT, evaluate:

1. CLAIMS: Extract each factual claim made in the output.
2. For each claim, assess:
   - SUPPORTED: Is this claim well-established or logically derived from stated premises?
   - UNSUPPORTED: Is this claim stated without evidence or justification?
   - CONTRADICTORY: Does this claim contradict other claims in the output or known facts?
3. LOGIC: Does the conclusion follow from the stated reasoning?
4. TASK_ALIGNMENT: Does the output actually address what was asked?

Respond in this exact JSON format (no markdown, no code fences):
{
  "approved": true/false,
  "claims": [
    {"text": "claim text", "status": "supported/unsupported/contradictory", "reason": "..."}
  ],
  "logic_sound": true/false,
  "task_aligned": true/false,
  "issues": ["issue 1", "issue 2"],
  "summary": "one-line verdict"
}

Set approved=true only if: no contradictory claims, logic is sound, task is aligned, and unsupported claims are minor."""


class Judge:
    """LLM-as-judge for per-claim factual verification.

    Uses MAL client with 'fast' preference by default (Tier 1 = cheap).
    """

    def __init__(self, client, preference: str = "fast"):
        self._client = client
        self._preference = preference

    def evaluate(
        self,
        original_prompt: str,
        output_text: str,
        context: str = "",
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Evaluate output_text against original_prompt.

        Returns structured verdict dict with:
          approved, claims, logic_sound, task_aligned, issues, summary
        """
        user_prompt = f"ORIGINAL PROMPT:\n{original_prompt}\n\n"
        if context:
            user_prompt += f"CONTEXT PROVIDED:\n{context}\n\n"
        user_prompt += f"AI OUTPUT:\n{output_text}"

        result = self._client.complete(
            prompt=user_prompt,
            system=_JUDGE_SYSTEM_PROMPT,
            preference=self._preference,
            max_tokens=max_tokens,
            temperature=0.0,
        )

        raw_text = result.get("text", "")
        verdict = self._parse_verdict(raw_text)
        verdict["model_used"] = result.get("model", "")
        verdict["cost_usd"] = result.get("cost_usd", 0.0)
        return verdict

    def _parse_verdict(self, text: str) -> Dict[str, Any]:
        """Parse judge response into structured verdict."""
        # Strip markdown fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            parsed = json.loads(cleaned)
            return {
                "approved": bool(parsed.get("approved", False)),
                "claims": parsed.get("claims", []),
                "logic_sound": bool(parsed.get("logic_sound", False)),
                "task_aligned": bool(parsed.get("task_aligned", True)),
                "issues": parsed.get("issues", []),
                "summary": parsed.get("summary", ""),
            }
        except (json.JSONDecodeError, KeyError):
            return {
                "approved": False,
                "claims": [],
                "logic_sound": False,
                "task_aligned": False,
                "issues": ["Judge response was not valid JSON"],
                "summary": f"Parse error. Raw: {text[:200]}",
                "raw_response": text,
            }
