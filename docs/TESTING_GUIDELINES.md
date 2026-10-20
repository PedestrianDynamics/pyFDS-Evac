# Testing guidelines

**A passing test is evidence of correctness only to the extent that its
expected behaviour is independently justified and its assertions can detect
a relevant defect.**

A green suite does not show that the software is scientifically right. A
snapshot of the software's own output shows that the output changed, not
that it is correct. An assertion can look meaningful and still never run,
rest on a mock that returns the expected value, or restate the calculation
it checks. These guidelines apply to everyone who writes or reviews tests,
human or AI, in the same way (see [AI_USAGE.md](../AI_USAGE.md)).

## 1. What a test can prove

Name the claim a test supports. The kinds of evidence are not
interchangeable.

| Kind | Question it answers | Typical evidence | It does not prove |
|---|---|---|---|
| Reliability | Do the interface and the error paths work? | Invalid input, exceptions, CLI contracts, cleanup | Scientific correctness |
| Regression | Has recorded output changed? | Goldens, saved runs, base-versus-head comparison | That the output is right |
| Presentation snapshot | Has the rendered text or screen changed? | TUI screens, CLI help | Anything about the model |
| Property or invariant | Does a relation hold across inputs? | Conservation, monotonicity, exact boundaries, metamorphic relations | That the model is valid |
| Independent verification | Does the code satisfy its documented equations? | Hand calculation, independently coded formula, analytic solution, published benchmark | That the equations describe reality |
| Validation | Does the model represent observed behaviour in its intended range? | Experimental data with uncertainty and applicability limits | Correctness outside that range |

One test file can hold several kinds. Classify at the level of the artifact
and the assertion, not the file name.

## 2. Oracles

Independent evidence needs an oracle: where the expected value comes from.
Acceptable sources are a hand calculation that a person checked, an
independently derived equation, a primary reference, an external FDS field
or a stated invariant. Write the source in the test docstring.

- Numbers an AI agent produced are not an oracle.
- The output of the code under test is not an oracle.
- A check that shares the production algorithm, for example two functions
  that call the same rate helper, is a **consistency check**. Label it so;
  it does not verify the helper.
- Do not describe numerical verification as scientific validation.
  Validation needs independent empirical observations, a defined
  applicability domain, a treatment of uncertainty and a comparison
  criterion. Agreement with published equations verifies the
  implementation, not the model, and a test must stay inside the model's
  documented range.

## 3. Writing a test

1. State the claim and its kind (section 1) in the docstring.
2. For an independent verification test, derive the expected value without
   calling the code under test or a production helper it shares. Write the
   arithmetic out:
   `expected = 0.12 * (30.0 / 60.0)  # rate per min, 30 s exposure`.
   For a regression test, document where the baseline came from and do not
   present it as independent evidence of correctness.
3. Assert the observable result, not internal calls or structures, unless
   the internal contract is the point.
4. Cover the boundaries the model defines: equality at a threshold, just
   above and just below, zero, empty, invalid, out of domain, unit
   conversions.
5. Justify every tolerance from units, discretisation or rounding. Do not
   use a broad tolerance to make a test pass.
6. Synthetic fields, deterministic fixtures and substitutes for external
   dependencies are fine when they feed controlled inputs to the real
   scientific code. Never replace the computation being verified with a
   mock that returns the expected result.
7. Make sure the assertion runs: no branch, early return, swallowed
   exception or skip condition may bypass it.
8. Prefer small deterministic tests for implementation verification. For
   a property of the stochastic simulation, use predefined independent
   seeds, repeated runs and a justified statistical acceptance criterion.
   A single fixed-seed result does not establish a statistical property.

## 4. Reviewing a pull request

Ask of each changed or added test what incorrect implementation would make
it fail. Look for these smells:

| Smell | Sign |
|---|---|
| Rotten green | The assertion does not run (conditional check, `try/except: pass`, early return, skip). |
| Self-fulfilling mock | A mock returns the value the test then asserts. |
| Weak oracle | Only existence, type, finiteness or "no error" is checked where a stronger contract exists. |
| Circular calculation | The expected value comes from the function under test or a shared helper. |
| Implementation lock-in | Internal calls or structures are asserted when only behaviour is contractual. |
| Missing boundary | No threshold equality, zero, empty or invalid case. |
| Tolerance camouflage | A broad or unexplained tolerance hides real error. |
| Silent external-data omission | An `external_data` test is deselected or skipped and the result is read as end-to-end success. |
| Unsound physics claim | The test encodes behaviour outside the documented range. |

For critical scientific computations (FED, heat, smoke speed, routing),
consider injecting a representative defect: a wrong unit conversion, a
reversed threshold comparison, a removed equation term. A relevant test
should fail. Restore the original code afterwards. This is a judgement per
change, not a required step on every pull request.
`scripts/mutation_check.py` runs a recorded set of such defects for an area;
the findings and results are in [tests/AUDIT.md](../tests/AUDIT.md).

Do not delete a regression test only because it has no independent oracle.
Keep it and label it. Do not read a coverage figure or a snapshot count as
correctness. State in the review which checks did not run (for example
`external_data`).

## 5. Goldens and snapshots

A golden whose values come from running the code can show change, never
correctness. Re-recording it proves the change was intended, not that it is
right.

Tag every golden artifact, not every file:

- `independent-truth`: the values were checked against something outside the
  code. Name the source.
- `regression-only`: a snapshot of the code's own output.
- `presentation-snapshot`: rendered text or screens.
- `mixed`: some assertions are truth-backed and some are not; list them
  separately.

A test that only reuses a golden deck or helper is not a consumer of golden
data. Record such tests apart from the artifacts.

Re-recording rules:

- A pull request that changes golden or snapshot data has a section headed
  `Golden re-record:` with the artifacts, why the output changed, the
  class of change and its evidence (table below), and the reason for any
  tolerance change.
- For an `independent-truth` golden, update the reference or explain why it
  still holds.
- Never regenerate a snapshot to make CI pass. `PYFDS_EVAC_REGEN_GOLDEN=1`
  produces a candidate, not a verified reference.

| Class of change | Required evidence |
|---|---|
| Scientific or numerical behaviour changes | Independent verification or an explicit scientific review of the new behaviour |
| Behaviour-preserving refactor | An explanation of the observed diff and a check that the relevant observable contracts still hold; an unexpected difference is investigated |
| Presentation only | Review of the visual or textual diff; no scientific oracle |

When a scientifically meaningful result changes and no independent oracle
exists, state the verification gap in the `Golden re-record:` section and
get the maintainer's approval. A snapshot diff or the words "intentional
change" do not establish correctness.

The golden inventory with these tags is
[tests/golden/README.md](../tests/golden/README.md).

## 6. Limits

- Do not change equations, coefficients, defaults or the reading of a
  standard to make a test pass. If a test exposes an ambiguity, open an
  issue with the competing readings.
- A presence check in CI shows that a section exists, not that its argument
  is sound. The model owner reviews scientific changes.
- Standard CI deselects `external_data` tests. The release check runs them
  and adds verification evidence for the FDS-coupled workflows they cover.
  Neither a green pull request nor a passing release check establishes
  general scientific validity.
