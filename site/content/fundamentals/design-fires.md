---
title: "Design fires"
weight: 2
---

ASET depends on the fire, and a fire model needs its heat release rate
(HRR) over time as input. A **design fire** is that input chosen for an
engineering analysis: an idealised HRR curve, not a forecast of one real
fire. This page covers the published conventions: the t² growth law and
its four classes, how growth is capped, steady fires, fits to tests, and
what a design fire does not tell you. The last section lists the fires
used in the pyFDS-Evac studies.

{{< callout type="info" >}}
This page states published conventions only. pyFDS-Evac does not choose a
fire: the fire is part of the FDS case you supply. The study fires in the
[last section](#fires-used-in-pyfds-evac-studies) are study inputs, not
defaults.
{{< /callout >}}

![Left: heat release rate against time for the slow, medium, fast and ultra-fast t-squared classes, solid up to 1055 kW and dashed beyond. Right: the T-junction ramp reaching 2 MW at 90 s and the constant 60 kW fire of the Schröder et al. (2020) study, drawn against the fast and ultra-fast classes](/images/fundamentals/design_fires.png)

*(a) The four t² classes of vfdb Table 4.3 and SFPE Eqs. 14.49–14.52. Each
curve is solid up to its growth time, when it reaches 1055 kW, and dashed
beyond. (b) The two study fires, with the fast and ultra-fast classes for
reference. The T-junction ramp is read from its FDS deck; it passes
1055 kW at 46 s. Script: `scripts/figures/fundamentals_design_fires.py`.*

## Design fire scenario and design fire

The vfdb guide separates the two (vfdb 2020, §4.1, pp. 39–40):

- A **design fire scenario** describes a fire case in words: where the
  fire starts, what burns, and which fire protection works or fails.
- A **design fire** turns the scenario into numbers, mainly an HRR curve
  over time.

Design fires are chosen so that a real fire in that use exceeds them only
with a very low probability: "worst credible", not "worst case" (§4.1,
pp. 40–41). The guide calls a design fire a theoretical but possible curve
that covers many real fires on the safe side (§4.3.1.1, p. 53). The SFPE
Handbook likewise calls the assumed fire characteristics of a scenario the
"design fire" and describes them as a time-dependent HRR (Hadjisophocleous
and Mehaffey 2016, p. 1271).

The scenario is chosen for the goal of the analysis. For egress, a small
fire at the main exit can matter more than a large fire elsewhere (Nilsson
and Fahy 2016, p. 2048).

A design fire is not meant to simulate every fire that could occur. It
lets the engineer compare safety measures, and it is chosen by judgement
and checked by varying it (Karlsson and Quintiere 2000, §3.5.1).

## The t² law as published

In real fires the early growth is nearly always accelerating. The
simplest description takes the HRR as growing with the square of time
(Karlsson and Quintiere 2000, §3.4.4, Eq. 3.7; vfdb 2020, §4.3.2.1,
Eq. 4.1, p. 58):

$$
\dot Q = \alpha\, t^2
$$

\(\dot Q\) is the HRR in kW, \(\alpha\) the growth factor in kW/s², and
\(t\) the time in s. **The clock starts at established burning, not at
ignition.** vfdb counts \(t\) without the ignition and smouldering phase;
Karlsson and Quintiere count it from the time \(t_0\) when flaming starts
and significant energy is released, which depends on the fuel and the
ignition source. vfdb also writes the law with an offset
(Eq. 4.2, p. 58):

$$
\dot Q = \dot Q_S + \dot Q_0 \left(\frac{t}{t_g}\right)^2, \qquad \dot Q_0 = 1000\ \mathrm{kW}
$$

where \(\dot Q_S\) is the HRR at \(t_0\), when the incipient fire turns
into a spreading fire, and \(t_g\) is the characteristic growth time. vfdb
writes \(t_\alpha\) on p. 58 and \(t_g\) later in the chapter.

### The four growth classes

The **growth time** \(t_g\) is the time to reach 1000 Btu/s, about
1055 kW, so \(\alpha = 1055/t_g^2\) (Schifiliti et al. 2016, p. 1326,
after NFPA 72 Appendix B; Karlsson and Quintiere 2000, §3.4.4, after
NFPA 204M).

| Class | \(t_g\) [s] | \(\alpha\) [kW/s²] | Typical use (vfdb Table 4.2) | Typical fuels (SFPE Table 38.2) |
|---|---|---|---|---|
| Slow | 600 | 0.002931 | picture gallery | densely packed wood products |
| Medium | 300 | 0.01172 | dwelling, office, hotel reception and rooms | solid wood furniture such as desks; single items with little plastic |
| Fast | 150 | 0.04689 | shop | high-stacked wood pallets, cartons on pallets, some upholstered furniture |
| Ultra-fast | 75 | 0.1876 | industrial storage, production hall | upholstered furniture, high-stacked plastics, thin wood furniture such as wardrobes |

*\(\alpha\) as printed in vfdb Table 4.3 (p. 60), which takes \(\alpha\) from
Drysdale and \(t_g\) from NFPA 92B. SFPE Eqs. 14.49–14.52 (Alpert 2016,
p. 443) print 0.00293, 0.01172, 0.0469 and 0.1876. Karlsson and Quintiere
Table 3.5 rounds them to 0.003, 0.012, 0.047 and 0.19. The occupancy
column of vfdb Table 4.2 comes from BSI DD 240.*

vfdb calls these values guidance, not normative (p. 59, footnote 1). The
mapping from occupancy to class is not universal either: vfdb puts
offices at medium, while a Swedish proposal in Karlsson and Quintiere
(Table 3.7, "not approved yet") puts schools and offices at fast.

{{< details title="1000 kW or 1055 kW? The sources use both" closed="true" >}}

The class values of \(\alpha\) are normalised to 1000 Btu/s = 1055 kW:
vfdb Table 4.3 says so in its footnote (1 Btu/s ≈ 1055.056 W), and
SFPE Ch. 40 defines \(t_g\) as the time to 1055 kW (p. 1326). Check:
1055/600² = 0.00293, 1055/300² = 0.01172, 1055/150² = 0.04689 and
1055/75² = 0.18756 kW/s².

Other passages of the same sources use 1000 kW. vfdb Eq. 4.2 sets
\(\dot Q_0\) = 1000 kW, and its Table 4.3 heads the \(t_g\) column "time to
reach 1 MW". The SFPE Handbook defines its \(t_{1000}\) as the time to reach
1000 kW (Hadjisophocleous and Mehaffey 2016, Eq. 38.1 and Table 38.2,
pp. 1271–1272).

With 1000 kW, the same \(t_g\) gives an \(\alpha\) 5.5 % lower (1000/1055).
The four class names and growth times are the same in all sources; only
\(\alpha\) differs. When a report quotes a class, check which
normalisation it uses.

{{< /details >}}

## How growth ends

The t² curve describes growth only. A real fire stops growing, and the
design fire must say when and how.

- **Fuel or ventilation limit.** The maximum HRR is the lesser of the
  fuel-controlled and the ventilation-controlled maximum (vfdb 2020,
  §4.3.2.3, Eq. 4.4, p. 62; Hadjisophocleous and Mehaffey 2016,
  pp. 1272–1273). The curve follows t² up to that maximum and then levels
  off at a steady value.
- **Flashover.** In a room fire the t² curve holds only up to flashover
  and needs enough air. At flashover the curve is left and the HRR rises
  quickly to the room's maximum (vfdb 2020, p. 59). The SFPE Handbook
  usually ignores that short rise and jumps to the post-flashover level
  (p. 1273).
- **A local fire in a large hall** stops growing when it reaches the
  maximum HRR of its limited burning area (vfdb 2020, p. 59).
- **Decay.** The curve must be checked against the fire load that is
  present (vfdb 2020, p. 59). Decay starts after about 70 % of the releasable
  energy is spent, vfdb (§4.3.3.4, p. 70), or after 70–80 % of the design
  fire load, SFPE (p. 1273), and both allow a linear fall. For life safety
  the first 10–30 min matter, so the steady phase is often assumed to
  continue with no decay (Karlsson and Quintiere 2000, §3.5.4).
- **Sprinklers.** If the burning items may be shielded from the spray, the
  SFPE Handbook suggests assuming that sprinklers stop the growth but do
  not suppress the fire: the HRR stays at its value at activation. Often
  the HRR drops; for shielded fires it may keep rising (Hadjisophocleous
  and Mehaffey 2016, pp. 1272–1273). vfdb gives a simplified curve: t²
  growth up to activation, then constant for 5 min, then a linear fall to
  zero over 25 min (§7.3.3, Eqs. 7.1–7.3, p. 278). Any credit for
  sprinklers must allow for the chance that the system fails (vfdb 2020,
  §4.2, item 5, p. 47).

### Steady fires

A steady fire keeps a constant HRR, either from ignition or after a
ramp. It is the growth → steady shape above with the growth phase left out
or shortened. It is an idealised source: easy to reproduce and compare,
but it skips the early growth that often decides detection and the first
smoke.

### Fits to tests and real events

A growth factor can also be fitted to calorimeter data for one item.
Karlsson and Quintiere (Table 3.4) and the SFPE Handbook (Schifiliti et
al. 2016, Table 40.4, p. 1332) list such fits for the same furniture
calorimeter tests. The tests suggest growth times between 50 and 500 s
(p. 1331). A fit follows the test only from its "virtual time", when the
test starts to follow the t² curve, and it does not predict when growth
stops or when the fuel runs out (p. 1331). **A fitted \(\alpha\) is not a
class:** it describes one item under one ignition, and a value such as
0.1055 kW/s² sits between fast and ultra-fast.

## What a design fire is not

- **Not a prediction.** It is chosen to be exceeded rarely, not to match
  the fire that will occur.
- **Not a verdict on the building.** It is an input to an analysis; the
  verdict comes from comparing ASET with RSET under stated criteria.
- **Not the scenario.** The same curve can sit in different scenarios, at
  a different place or with different doors open.
- **Not a class when it is a fit or a custom ramp.** A piecewise-linear
  ramp has no \(\alpha\); compare it with the classes by the time it takes
  to reach 1055 kW.
- **Not a property of the building.** A growth class describes the fuel
  and its arrangement. Contents change over the life of a building.
- **Not a smoke source term.** The HRR does not fix the smoke. Soot and
  other product yields must be given separately (vfdb 2020, p. 60). For
  visibility this matters as much as the HRR.

## Known limits

- **The t² law comes from free-burning tests.** In a small enclosure the
  hot layer feeds heat back to the fuel, and in a closed one oxygen runs
  short; the free-burning rate must then be adjusted (Hadjisophocleous and
  Mehaffey 2016, p. 1272).
- **The incipient phase is left out.** Smouldering before \(t_0\) releases
  little heat but can produce smoke that triggers detectors before growth
  starts (Karlsson and Quintiere 2000, §3.5.2; the SFPE Handbook excludes
  smouldering from its pre-flashover curves, p. 1271).
- **Life safety and structure use different curves.** For escape the time
  frame is mostly under 30 min and the design fire is an HRR curve; for
  structural stability it is a temperature–time curve over 0.5–3 h
  (Karlsson and Quintiere 2000, §3.5.1). Standard temperature–time curves
  do not belong in an egress analysis.

## Fires used in pyFDS-Evac studies

These are the fires of the [Studies](/docs/studies/_index.md). They are
**study inputs**, chosen for each study's question. Neither was chosen by
the design-fire procedure above, so neither is a design fire, and neither
is a pyFDS-Evac default. Each new study adds a row here and one to the
[Studies index](/docs/studies/_index.md).

| Study | Curve type | Parameters | Stated or assumed |
|---|---|---|---|
| [ASET-RSET maps after Schröder et al. (2020)](/docs/study-schroeder2020.md) | Steady from ignition | 60 kW: HRRPUA 166.7 kW/m² on 0.6 × 0.6 m; flexible polyurethane foam | 60 kW from the authors' reference implementation ([doi:10.5281/zenodo.3875550](https://doi.org/10.5281/zenodo.3875550)); the paper's text does not state it. Burner size and fuel are ours |
| [With and without the fire](/docs/howto-with-without-fire.md) | Piecewise-linear ramp, then steady | 0, 100, 800, 1600, 2000 kW at 0, 20, 40, 60, 90 s; 2 MW to 300 s (HRRPUA 1000 kW/m² on 2 m²); fuel vinyl chloride (PVC), 16.4 MJ/kg | From the deck `assets/t_junction/t_junction.fds`. Not a t² class: it passes 1055 kW at 46 s, faster than ultra-fast (75 s). The deck comments and README disagree with the deck ([#280](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/280)) |

Both fires start at t = 0 with no incipient phase.

## Sources

- vfdb (2020). *Leitfaden Ingenieurmethoden des Brandschutzes*, TB 04-01,
  4th ed., March 2020, J. Zehfuß (ed.). Vereinigung zur Förderung des
  Deutschen Brandschutzes. §4.1 (pp. 39–40); §4.2, item 5 (p. 47);
  §4.3.1.1 (p. 53); §4.3.2.1, Eqs. 4.1–4.2 (p. 58), p. 59 and
  Tables 4.2–4.3 (p. 60); §4.3.2.3, Eq. 4.4 (p. 62); §4.3.3.4 (p. 70);
  §7.3.3, Eqs. 7.1–7.3 (pp. 276–278). NFPA 92B and BSI DD 240 are cited
  here through this guide.
- Hadjisophocleous, G. V., & Mehaffey, J. R. (2016). *Fire scenarios*. SFPE
  Handbook of Fire Protection Engineering, 5th ed., Ch. 38, pp. 1271–1273.
  [doi:10.1007/978-1-4939-2565-0_38](https://doi.org/10.1007/978-1-4939-2565-0_38)
- Alpert, R. L. (2016). *Ceiling jet flows*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 14, Eqs. 14.49–14.52, p. 443.
  [doi:10.1007/978-1-4939-2565-0_14](https://doi.org/10.1007/978-1-4939-2565-0_14)
- Schifiliti, R. P., Custer, R. L. P., & Meacham, B. J. (2016). *Design of
  detection systems*. SFPE Handbook of Fire Protection Engineering, 5th
  ed., Ch. 40, pp. 1326, 1331–1332. NFPA 72 Appendix B is cited here
  through this chapter and Ch. 14.
  [doi:10.1007/978-1-4939-2565-0_40](https://doi.org/10.1007/978-1-4939-2565-0_40)
- Nilsson, D., & Fahy, R. (2016). *Selecting scenarios for deterministic
  fire safety engineering analysis: life safety for occupants*. SFPE
  Handbook of Fire Protection Engineering, 5th ed., Ch. 57, pp. 2047–2048.
  [doi:10.1007/978-1-4939-2565-0_57](https://doi.org/10.1007/978-1-4939-2565-0_57)
- Karlsson, B., & Quintiere, J. G. (2000). *Enclosure Fire Dynamics*. CRC
  Press, Boca Raton. §3.4.4 (Eq. 3.7, Tables 3.4–3.5), §3.5.1–3.5.4
  (Table 3.7). NFPA 204M is cited here through this book.

How the fire reaches pyFDS-Evac: the FDS case supplies it, see
[Your FDS case](/docs/fds-case-requirements.md). How ASET follows from it:
[ASET, RSET and the egress timeline](/fundamentals/aset-rset.md).
