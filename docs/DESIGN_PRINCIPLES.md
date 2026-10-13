---
title: "Design principles"
weight: 91
---

When implementing numerical or scientific models, prioritize scientific traceability, reproducibility, numerical correctness, and maintainability.

## 1. Classify numerical values

Distinguish between:

- Physical and mathematical constants.
- Empirical coefficients derived from literature or experiments.
- Configurable model assumptions.
- Numerical tolerances and solver parameters.
- Applicability limits and validity ranges.
- Derived quantities calculated from other parameters.

Do not treat empirical model parameters as universal constants.

## 2. Separate parameters from equations

When empirical parameters may reasonably change, group them into immutable, validated configuration objects, preferably frozen dataclasses.

Keep mathematical relations as pure functions unless a class represents a meaningful domain concept or manages necessary state.

Avoid introducing unnecessary abstraction layers.

## 3. Preserve mathematical consistency

Derived quantities must remain consistent with their underlying parameters.

Avoid independently configurable values that should be mathematically linked.

Validate parameter combinations, physical units, and meaningful numerical ranges.

## 4. Make scientific assumptions explicit

Document:

- Mathematical equations and their interpretation.
- Units and dimensional consistency.
- Literature references and the origin of empirical coefficients.
- Applicability ranges and underlying assumptions.
- Extrapolations beyond validated conditions.
- Differences between published formulations and their implementation.

Never silently substitute one empirical relation for another.

## 5. Support reproducibility

Make parameter sets inspectable and serializable.

Ensure simulation results can be associated with the model formulation, parameter values, software version, and relevant numerical settings used to produce them.

Avoid hidden mutable global state.

## 6. Prefer simple numerical APIs

Use pure functions for mathematical relations.

Introduce classes only when they represent meaningful domain concepts or manage necessary state.

Do not introduce inheritance hierarchies, factories, or abstract interfaces without concrete requirements.

## 7. Design for scientific verification

Include appropriate:

- Analytical and limiting-case checks.
- Boundary-condition tests.
- Reference comparisons against published results.
- Regression tests.
- Sensitivity tests where relevant.

Distinguish verification of the implementation from validation of the scientific model.

## 8. Avoid speculative abstractions

Do not generalize for hypothetical requirements.

Identify concrete extension points and implement the smallest architecture that supports them.

Prefer transparent, readable scientific code over clever abstractions.

---

## 9. Mandatory design review before implementation

Before implementing or substantially modifying a scientific model, answer the following questions.

| Question | Expected consideration |
|---|---|
| **What is configurable?** | Which empirical coefficients, assumptions, or numerical settings may change between studies? |
| **What is derived?** | Which quantities must be computed from other parameters to preserve mathematical consistency? |
| **What is fixed?** | Which mathematical identities, physical constants, or unit conversions should remain invariant? |
| **What is the validity domain?** | Under which physical conditions, geometries, parameter ranges, and assumptions is the model applicable? |
| **What are the scientific sources?** | Which equations and coefficients come from which references? Are any implementation choices not directly supported by those references? |
| **How will we verify it?** | Which analytical solutions, limiting cases, published benchmarks, and regression tests can establish implementation correctness? |
| **How will we extend it?** | Which realistic alternative formulations or parameterizations should the architecture accommodate without unnecessary complexity? |
| **How will we reproduce results?** | Can another researcher reconstruct the exact model configuration and implementation version used? |
| **What are the architectural trade-offs?** | Why are module constants, dataclasses, pure functions, or classes appropriate for this implementation? |
| **What could go wrong?** | Which numerical, physical, or modeling errors might produce plausible but incorrect results? |

### Design review requirements

1. Answer these questions briefly before substantial implementation work.
2. Identify assumptions and uncertainties explicitly. Do not invent scientific justifications.
3. Distinguish decisions supported by literature from engineering choices.
4. Explain significant architectural decisions and their alternatives.
5. Identify any decisions requiring scientific judgment from the project owner.
6. For minor changes, provide only the relevant answers rather than repeating the full review.
7. Do not proceed with scientifically consequential assumptions when clarification is necessary.

The review should be concise, specific to the actual model, and actionable. Avoid generic architectural commentary.

---

## 10. Final implementation review

Before considering the work complete, verify that:

- The implementation matches the documented equations.
- Parameter values and units are consistent.
- Derived quantities cannot become inconsistent with their dependencies.
- Scientific assumptions and validity limits are documented.
- Tests cover meaningful numerical and physical edge cases.
- Default behavior remains unchanged unless a change was intentional.
- The implementation introduces no unnecessary complexity.

**Guiding principle:** Scientific software should make its assumptions as transparent and testable as its algorithms.

Do not automatically refactor toward dataclasses or classes. Choose the simplest design that supports the actual scientific requirements, and be prepared to justify that choice.
