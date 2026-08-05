# FIC vs FED: two rules, two timescales

**Does toxic dose slow an evacuating agent, or only the irritant does?**

FED and FIC are both tenability rules and they are easy to conflate. They are
not interchangeable:

| | what it is | when it acts |
|---|---|---|
| **FED** | cumulative dose with a threshold | nothing at all below the threshold, then a binary stop |
| **FIC** | instantaneous irritant response | from the first tick, recovers on leaving the gas |

## The prediction, stated before running

On a short egress, **FED alone changes nothing** — the dose never approaches
its threshold — while **FIC bites immediately**. A model carrying only FED is
therefore non-conservative for exactly this class of fire.

Falsifiable: if FED materially slows an agent over a minute of exposure, either
the model or this reasoning is wrong.

## Layout and gas

A 4 × 50 m sealed corridor, one exit at the north end, agents at the south end,
so every agent walks the full length through the gas. One exit, so routing
cannot vary between runs and walking speed is the only thing that differs.

The gas is **prescribed, not burned** — a single `&INIT` fills the corridor with
a fixed mixture, so there is no combustion transient and no spatial gradient.
Concentration is not a variable. The technique and its pitfall (a second
`&INIT` without `XB` silently resets the whole domain) follow
[`fed_incap_co_*`](../fed_incap_co_2000ppm).

| species | level | drives | effect |
|---|---|---|---|
| CO | 2000 ppm | FED | rate 0.079 /min → **13 min** to reach FED = 1 |
| acrolein | 10 ppm | FIC | `FIC = 10/20 = 0.5` → speed factor `max(0.3, 1 − 0.7·0.5)` = **0.65** |

Acrolein sits deliberately off the 0.3 floor: a saturated factor would hide any
error in `fic_alpha`. The builder asserts the factor is neither pinned at the
floor nor within 5 % of 1.

## The three runs

Distinguished by CLI flags alone — no config change, so nothing else can drift:

```bash
run.py --scenario assets/fic_vs_fed_speed --disable-tenability   # neither
run.py --scenario assets/fic_vs_fed_speed --fic-alpha 0          # FED only
run.py --scenario assets/fic_vs_fed_speed                        # FED + FIC
```

Over the ~44 m walk: **~33 s** for the first two, **~51 s** for the third.
The first two should be indistinguishable.

## A subtlety worth knowing

Acrolein is **not only an irritant**. It also appears in FED's Fractional Lethal
Dose sum, so removing it moves both quantities. The asymmetry is what makes the
two rules separable at all:

- removing acrolein removes **100 %** of the speed penalty
- but only **3 %** of the dose rate, because CO dominates it

A control test asserts exactly that, rather than the tidier and false claim that
acrolein touches FIC alone.

## O2 hypoxia reference

`TestO2HypoxiaReference` pins the O2 term against the **published** closed form
rather than against our own docs:

> `FI_O2 = 1 / exp{8.13 − 0.54 (20.9 − X_O2 [%])}`
> — *On the use of surrogate gases in fire toxicity calculations*, Fire Safety
> Journal, Eq. (9), which states this is the form implemented in FDS.

`FI_O2` is already a **rate per minute**, so there is no seconds conversion to
apply. The verification suite's reference carried a spurious 60× for seven weeks
before this was noticed; citing the literature directly is cheaper than
re-deriving it.
