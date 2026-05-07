# final_hint_policy_v1 Notes

## 2026-04-28 Hard Rules Sync

This note documents the strict rules synchronized from the xuanheng skill and user confirmation.

1. Front-6 hints plus known category must not form a strong-anchor combo.
2. All hints must be natural semantics, no meta-descriptor/template wording.
3. Dimension rule is strict 7-of-7 unique dimensions.
4. After any edit, rerun full checks until zero violations.
5. Never claim checks were done unless checks were actually run.
6. No speculative self-invented hint wording without common-usage grounding.
7. No forced four-character or uniform-length formatting.
8. No hint reuse across different answers.
9. No same-hint reuse within the same category.
10. No generic placeholder terms.

## Policy Mapping

- Main source: data/final_hint_policy_v1.json
- Rule block: hard_rules_2026_04_28
- Universal fields aligned:
  - universal_constraints.forbid_global_hint_reuse_across_answers
  - universal_constraints.forbid_same_hint_reuse_within_category
  - universal_constraints.answer_conditioned_diversity_guard.default_min_unique_dimensions = 7
  - universal_constraints.answer_conditioned_diversity_guard.require_all_slots_unique_dimensions = true
  - universal_constraints.natural_language_guard.forbidden_generic_terms
  - universal_constraints.per_hint_mandatory_check.checks includes:
    - no_generic_placeholder_term
    - no_cross_answer_hint_reuse
    - no_same_category_hint_reuse
    - dimension_unique_7of7

## Execution Honesty

No run, no pass.
If any check reports violations, continue edits and rerun checks until zero errors.
