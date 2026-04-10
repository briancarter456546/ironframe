# ============================================================================
# ironframe/logic/fallacy_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Fallacy taxonomy with stepwise binary classification.
#
# 30 fallacy types organized by category. Each has:
#   - name, category, description
#   - detection_questions: binary (yes/no) questions for stepwise classification
#   - example: illustrative instance
#
# IMPORTANT: Rhetorical devices (antithesis, repetition, anaphora) are
# oratorical techniques, NOT logic flaws. This taxonomy only covers
# actual logical fallacies. (Per feedback_scimode_rhetoric.md)
#
# Dual use:
#   1. SAE Tier 0: prompt addendum for self-audit against common fallacies
#   2. Programmatic: check text against the taxonomy via detection questions
#
# Usage:
#   from ironframe.logic.fallacy_v1_0 import (
#       FALLACY_TAXONOMY, get_fallacy, fallacy_check_prompt,
#       get_detection_questions, search_fallacies,
#   )
#   f = get_fallacy('straw_man')
#   print(f['detection_questions'])
# ============================================================================

from typing import Any, Dict, List, Optional


# ---- Fallacy Taxonomy ----
# 30 fallacies organized by category

FALLACY_TAXONOMY: Dict[str, Dict[str, Any]] = {

    # === RELEVANCE FALLACIES (argument misses the point) ===

    "ad_hominem": {
        "name": "Ad Hominem",
        "category": "relevance",
        "description": "Attacking the person making the argument rather than the argument itself.",
        "detection_questions": [
            "Is a person or group being criticized rather than their argument?",
            "Would the argument's validity change if someone else made it?",
        ],
        "example": "You can't trust his analysis of the market -- he lost money in 2020.",
    },
    "straw_man": {
        "name": "Straw Man",
        "category": "relevance",
        "description": "Misrepresenting someone's argument to make it easier to attack.",
        "detection_questions": [
            "Is the argument being responded to accurately represented?",
            "Would the original author recognize this as their position?",
        ],
        "example": "'We should diversify into bonds.' 'So you want to abandon equities entirely?'",
    },
    "red_herring": {
        "name": "Red Herring",
        "category": "relevance",
        "description": "Introducing an irrelevant topic to divert from the original argument.",
        "detection_questions": [
            "Does the response address the original question/claim?",
            "If you remove this point, does it affect the conclusion at all?",
        ],
        "example": "The backtest shows poor returns. 'But look at how elegant the code is.'",
    },
    "appeal_to_authority": {
        "name": "Appeal to Authority",
        "category": "relevance",
        "description": "Claiming something is true because an authority said so, without evidence.",
        "detection_questions": [
            "Is the authority cited actually an expert in the relevant domain?",
            "Is the claim supported by evidence beyond the authority's endorsement?",
        ],
        "example": "This strategy works because Warren Buffett uses something similar.",
    },
    "appeal_to_emotion": {
        "name": "Appeal to Emotion",
        "category": "relevance",
        "description": "Using emotional manipulation instead of evidence to support a claim.",
        "detection_questions": [
            "Is the argument relying on fear, pity, or excitement rather than data?",
            "Would the argument still stand if the emotional language were removed?",
        ],
        "example": "If you don't hedge now, you'll lose everything you've worked for.",
    },
    "appeal_to_nature": {
        "name": "Appeal to Nature",
        "category": "relevance",
        "description": "Arguing something is good/right because it is 'natural' or traditional.",
        "detection_questions": [
            "Is 'naturalness' or tradition being used as evidence of quality?",
            "Is there actual evidence that the natural/traditional approach is better?",
        ],
        "example": "Buy-and-hold is the natural way to invest. Active trading is unnatural.",
    },
    "tu_quoque": {
        "name": "Tu Quoque (You Too)",
        "category": "relevance",
        "description": "Deflecting criticism by pointing out the accuser does the same thing.",
        "detection_questions": [
            "Is the response 'you do it too' rather than addressing the argument?",
            "Does the accuser's behavior actually invalidate their argument?",
        ],
        "example": "You say I'm overtrading, but you made 50 trades last month too.",
    },
    "genetic_fallacy": {
        "name": "Genetic Fallacy",
        "category": "relevance",
        "description": "Judging something based on its origin rather than its current merit.",
        "detection_questions": [
            "Is the origin/source being used to evaluate the argument's validity?",
            "Would the argument be judged differently if it came from another source?",
        ],
        "example": "That strategy came from Reddit, so it can't be serious.",
    },

    # === PRESUMPTION FALLACIES (conclusion assumes what it needs to prove) ===

    "begging_the_question": {
        "name": "Begging the Question",
        "category": "presumption",
        "description": "The conclusion is assumed in the premises (circular reasoning).",
        "detection_questions": [
            "Does any premise restate the conclusion in different words?",
            "Could someone who doubts the conclusion accept all the premises?",
        ],
        "example": "This system is profitable because it makes money.",
    },
    "false_dilemma": {
        "name": "False Dilemma",
        "category": "presumption",
        "description": "Presenting only two options when more exist.",
        "detection_questions": [
            "Are only two options presented?",
            "Are there viable alternatives not being considered?",
        ],
        "example": "Either we go all-in on tech stocks or we accept mediocre returns.",
    },
    "loaded_question": {
        "name": "Loaded Question",
        "category": "presumption",
        "description": "A question that contains an unverified assumption.",
        "detection_questions": [
            "Does the question assume something that hasn't been established?",
            "Can the question be answered without accepting the assumption?",
        ],
        "example": "Why does your strategy always fail in bear markets?",
    },
    "false_cause": {
        "name": "False Cause (Post Hoc)",
        "category": "presumption",
        "description": "Assuming that because B followed A, A caused B.",
        "detection_questions": [
            "Is temporal sequence being treated as causation?",
            "Has an actual causal mechanism been identified?",
            "Could a third factor explain both events?",
        ],
        "example": "I changed my SMA period and the next trade was profitable. The SMA change worked.",
    },
    "slippery_slope": {
        "name": "Slippery Slope",
        "category": "presumption",
        "description": "Claiming one event will inevitably lead to extreme consequences without evidence.",
        "detection_questions": [
            "Is a chain of consequences claimed without evidence for each link?",
            "Are the intermediate steps actually inevitable?",
        ],
        "example": "If we add one more system, we'll end up with 100 systems and no one can manage them.",
    },
    "no_true_scotsman": {
        "name": "No True Scotsman",
        "category": "presumption",
        "description": "Redefining criteria to exclude counterexamples after the fact.",
        "detection_questions": [
            "Were the criteria changed after a counterexample was presented?",
            "Would the original definition include the counterexample?",
        ],
        "example": "'All momentum strategies work.' 'This one didn't.' 'That's not a real momentum strategy.'",
    },

    # === INDUCTION FALLACIES (bad generalization from evidence) ===

    "hasty_generalization": {
        "name": "Hasty Generalization",
        "category": "induction",
        "description": "Drawing a broad conclusion from too few examples.",
        "detection_questions": [
            "Is the sample size sufficient for the claim being made?",
            "Are there obvious counterexamples not addressed?",
        ],
        "example": "The strategy won 3 out of 3 trades. It always works.",
    },
    "cherry_picking": {
        "name": "Cherry Picking",
        "category": "induction",
        "description": "Selecting only data that supports the conclusion while ignoring contradictory data.",
        "detection_questions": [
            "Is all relevant data being considered, or only favorable data?",
            "Would the conclusion change if unfavorable data were included?",
        ],
        "example": "The system has PF 4.0 in bull markets. (Ignoring PF 0.5 in bear markets.)",
    },
    "survivorship_bias": {
        "name": "Survivorship Bias",
        "category": "induction",
        "description": "Drawing conclusions only from successes, ignoring failures that are no longer visible.",
        "detection_questions": [
            "Are failed/delisted/removed cases included in the analysis?",
            "Could the pattern disappear if non-survivors were included?",
        ],
        "example": "All companies in the S&P 500 have grown long-term. (The ones that didn't were removed.)",
    },
    "anecdotal_evidence": {
        "name": "Anecdotal Evidence",
        "category": "induction",
        "description": "Using personal experience or a single case as proof of a general pattern.",
        "detection_questions": [
            "Is a single example being used to support a general claim?",
            "Is there systematic data available that wasn't consulted?",
        ],
        "example": "My friend made 200% on meme stocks. Meme stocks are great investments.",
    },
    "composition_division": {
        "name": "Composition/Division",
        "category": "induction",
        "description": "Assuming what's true of parts is true of the whole, or vice versa.",
        "detection_questions": [
            "Is a property of individual items being attributed to the group?",
            "Is a property of the group being attributed to each individual?",
        ],
        "example": "Each system is profitable, so the portfolio of all systems will be profitable.",
    },

    # === FORMAL FALLACIES (invalid logical structure) ===

    "affirming_consequent": {
        "name": "Affirming the Consequent",
        "category": "formal",
        "description": "If A then B. B is true. Therefore A is true. (Invalid: B could have other causes.)",
        "detection_questions": [
            "Is the argument: 'If A then B, B therefore A'?",
            "Could B be true for reasons other than A?",
        ],
        "example": "If the VIX is high, stocks fall. Stocks fell. Therefore VIX must be high.",
    },
    "denying_antecedent": {
        "name": "Denying the Antecedent",
        "category": "formal",
        "description": "If A then B. A is false. Therefore B is false. (Invalid: B could still be true.)",
        "detection_questions": [
            "Is the argument: 'If A then B, not A therefore not B'?",
            "Could B be true even without A?",
        ],
        "example": "If RSI < 10, buy. RSI is not < 10. Therefore don't buy. (Ignores other entry signals.)",
    },
    "undistributed_middle": {
        "name": "Undistributed Middle",
        "category": "formal",
        "description": "All A are B. All C are B. Therefore A are C. (Invalid: B is too broad.)",
        "detection_questions": [
            "Do the two groups share a category that doesn't actually connect them?",
            "Is the shared property too broad to establish a relationship?",
        ],
        "example": "Profitable strategies use moving averages. My strategy uses moving averages. Therefore it's profitable.",
    },
    "equivocation": {
        "name": "Equivocation",
        "category": "formal",
        "description": "Using the same word with different meanings in the same argument.",
        "detection_questions": [
            "Is a key term used with consistent meaning throughout?",
            "Would substituting a synonym in one usage break the argument?",
        ],
        "example": "'Risk' meaning volatility in one sentence and 'risk' meaning probability of loss in the next.",
    },

    # === QUANTITATIVE FALLACIES (misuse of numbers/statistics) ===

    "base_rate_neglect": {
        "name": "Base Rate Neglect",
        "category": "quantitative",
        "description": "Ignoring the prior probability when evaluating evidence.",
        "detection_questions": [
            "Is the base rate (prior probability) considered?",
            "Would the conclusion change if the base rate were very different?",
        ],
        "example": "The signal has 90% accuracy! (But only 1% of signals are real, so most positives are false.)",
    },
    "gamblers_fallacy": {
        "name": "Gambler's Fallacy",
        "category": "quantitative",
        "description": "Believing past random events affect future probabilities in independent trials.",
        "detection_questions": [
            "Are the events actually independent?",
            "Is the argument that something is 'due' because it hasn't happened recently?",
        ],
        "example": "We've had 5 losing trades. We're due for a winner.",
    },
    "texas_sharpshooter": {
        "name": "Texas Sharpshooter",
        "category": "quantitative",
        "description": "Finding a pattern in random data after the fact and claiming it was predicted.",
        "detection_questions": [
            "Was the pattern predicted before looking at the data?",
            "How many patterns were tested before this one was found?",
        ],
        "example": "Look, if you use a 17-day lookback with a 0.73 threshold, it works perfectly!",
    },
    "regression_to_mean_fallacy": {
        "name": "Regression to Mean Fallacy",
        "category": "quantitative",
        "description": "Attributing regression to the mean to a specific cause rather than statistics.",
        "detection_questions": [
            "Is an extreme result being followed by a less extreme result?",
            "Is a specific cause being credited when regression to the mean could explain it?",
        ],
        "example": "After our worst month ever, I changed the parameters and returns improved. The change worked.",
    },
    "correlation_causation": {
        "name": "Correlation/Causation Confusion",
        "category": "quantitative",
        "description": "Treating statistical correlation as proof of causal relationship.",
        "detection_questions": [
            "Is correlation being presented as causation?",
            "Has a causal mechanism been identified and tested?",
            "Could a confounding variable explain the correlation?",
        ],
        "example": "Gold and VIX are correlated, so VIX drives gold prices.",
    },
    "p_hacking": {
        "name": "P-Hacking / Multiple Comparisons",
        "category": "quantitative",
        "description": "Testing many hypotheses and reporting only the significant ones.",
        "detection_questions": [
            "How many variations were tested before finding this result?",
            "Was a correction applied for multiple comparisons?",
            "Would this result survive out-of-sample testing?",
        ],
        "example": "We tested 200 parameter combinations and found one with p < 0.05.",
    },
    "simpsons_paradox": {
        "name": "Simpson's Paradox",
        "category": "quantitative",
        "description": "A trend that appears in subgroups reverses when groups are combined.",
        "detection_questions": [
            "Could the relationship reverse if the data were split by a confounding variable?",
            "Are subgroup sizes dramatically different?",
        ],
        "example": "Strategy A beats B overall, but B beats A in every individual regime.",
    },
}

# Category descriptions
CATEGORIES = {
    "relevance": "Argument misses the point or uses irrelevant support",
    "presumption": "Conclusion assumes what it needs to prove",
    "induction": "Bad generalization from evidence",
    "formal": "Invalid logical structure",
    "quantitative": "Misuse of numbers, statistics, or probability",
}


def get_fallacy(key: str) -> Optional[Dict[str, Any]]:
    """Get a fallacy definition by key."""
    return FALLACY_TAXONOMY.get(key)


def get_detection_questions(key: str) -> List[str]:
    """Get detection questions for a specific fallacy."""
    f = FALLACY_TAXONOMY.get(key, {})
    return f.get("detection_questions", [])


def list_by_category(category: str) -> List[str]:
    """List fallacy keys in a category."""
    return [k for k, v in FALLACY_TAXONOMY.items() if v["category"] == category]


def search_fallacies(query: str) -> List[str]:
    """Search fallacies by keyword in name, description, or example."""
    query_lower = query.lower()
    matches = []
    for key, f in FALLACY_TAXONOMY.items():
        searchable = f"{f['name']} {f['description']} {f.get('example', '')}".lower()
        if query_lower in searchable:
            matches.append(key)
    return matches


def fallacy_check_prompt() -> str:
    """Return a prompt addendum for self-auditing against common fallacies.

    SAE Tier 0: inject into system prompt for analytical tasks.
    """
    return """Before finalizing your analysis, check for these common reasoning errors:

RELEVANCE: Am I attacking a person instead of their argument? Am I responding to what was actually said, or a distorted version? Am I introducing irrelevant points?

PRESUMPTION: Am I assuming my conclusion in my premises (circular)? Am I presenting a false either/or when more options exist? Am I confusing sequence with causation?

INDUCTION: Am I generalizing from too few examples? Am I only looking at data that supports my conclusion? Am I ignoring failures/non-survivors?

QUANTITATIVE: Am I ignoring the base rate? Am I treating correlation as causation? Am I finding patterns after the fact (Texas Sharpshooter)? Did I test many hypotheses and report only the significant one?

If you catch any of these in your reasoning, fix the reasoning rather than proceeding with a flawed argument."""


def full_audit_prompt() -> str:
    """Return a comprehensive prompt for auditing text against all 30 fallacies.

    More thorough than fallacy_check_prompt(). Use for high-stakes analysis.
    """
    lines = ["Audit the argument above for logical fallacies. For each category, "
             "check the listed fallacies:\n"]

    for cat_key, cat_desc in CATEGORIES.items():
        lines.append(f"\n{cat_key.upper()} ({cat_desc}):")
        for key in list_by_category(cat_key):
            f = FALLACY_TAXONOMY[key]
            lines.append(f"  - {f['name']}: {f['description']}")

    lines.append("\nFor each fallacy detected, quote the specific text that "
                 "commits the fallacy and explain why it qualifies.")
    lines.append("If no fallacies are found in a category, state 'Clean.'")
    return "\n".join(lines)
