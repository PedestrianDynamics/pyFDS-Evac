---
title: "Extinction coefficient"
weight: 3
---

The extinction coefficient *K* [1/m] measures how strongly smoke attenuates
light per metre of path. It is the quantity from which visibility, walking
speed in smoke and most smoke tenability limits are computed.

Symbols follow the [notation table](/docs/concepts.md#notation); here *L* is
the length of a light path, not the route length \(L_k\) of the table.

## The equations as published

Light of intensity \(I_0\) that crosses a path of length *L* [m] through
smoke leaves with intensity *I*. The attenuation follows the
Bouguer–Lambert–Beer law, usually called the Beer–Lambert law (Bouguer 1729;
Lambert 1760; Beer 1852). For smoke measurement, Guillaume (2026, SFPE
Handbook, 6th ed., Ch. 33, pp. 980–981) writes it as \(I = I_0 \exp(-kL)\).
The Fire Dynamics Simulator (FDS) User's Guide (McGrattan et al. 2025,
FDS 6.10.1, §22.10.5) writes the law as

$$
\frac{I}{I_0} = e^{-KL} \qquad \text{(McGrattan et al. 2025, Eq. 22.21)}
$$

and *K* is the product of a mass-specific extinction coefficient
\(K_m\) [m²/kg] and the mass concentration of smoke particulate
\(\rho Y_S\) [kg/m³]:

$$
K = K_m\, \rho Y_S \qquad \text{(McGrattan et al. 2025, Eq. 22.22)}
$$

Along a path on which *K* varies, the exponent becomes the integral of *K*
along the path, which FDS evaluates as a sum over cells for its beam detector
(McGrattan et al. 2025, Eq. 18.5, §18.3.6). That dimensionless integral is the optical depth. The optical
density per metre *D* [1/m] uses base-10 logarithms instead of natural ones:

$$
D \equiv -\frac{1}{L}\log_{10}\frac{I}{I_0} = K \log_{10} e \approx K/2.3 \qquad \text{(McGrattan et al. 2025, Eq. 22.24)}
$$

The distinction matters when reading the literature. Tenability limits are
often quoted as OD/m (optical density per metre, *D*), and Purser and
McAllister (2026), in the Society of Fire Protection Engineers (SFPE)
Handbook, give both forms: for example OD/m = 0.2 corresponds to an
extinction coefficient of about 0.5 1/m (Ch. 70, Table 70.3 and p. 2285).

## The data behind \(K_m\)

FDS uses \(K_m\) = 8700 m²/kg by default (`MASS_EXTINCTION_COEFFICIENT`).
The User Guide describes it as a value suggested for flaming combustion of
wood and plastics, and gives 8700 ± 1100 m²/kg at a wavelength of 633 nm for
most flaming fuels (FDS User Guide §22.10.5, footnote 7), citing
Mulholland and Croarkin (2000).

## Known limits

*K* depends on wavelength, and the 8700 m²/kg figure is for red light at
633 nm. It is a property of flame-generated soot; other fire effluents can differ.
In a fire model *K* also inherits every uncertainty of the predicted soot
yield and soot transport. FDS writes the local *K* as the `EXTINCTION
COEFFICIENT` output quantity (§22.10.5); the unrelated quantity
`EXTINCTION` is a combustion-suppression flag (§22.10.29).

## Sources

- Bouguer, P. (1729). *Essai d'optique sur la gradation de la lumière*.
  Claude Jombert, Paris.
- Lambert, J. H. (1760). *Photometria, sive de mensura et gradibus
  luminis, colorum et umbrae*. Klett, Augsburg.
- Beer, A. (1852). *Bestimmung der Absorption des rothen Lichts in farbigen
  Flüssigkeiten*. Annalen der Physik, 162(5), 78–88.
  [doi:10.1002/andp.18521620505](https://doi.org/10.1002/andp.18521620505)
- Guillaume, E. (2026). *Smoke release rate data*. SFPE Handbook of Fire
  Protection Engineering, 6th ed., Ch. 33, 979–986, pp. 980–981.
  [doi:10.1007/978-3-031-59212-6_33](https://doi.org/10.1007/978-3-031-59212-6_33)
- McGrattan, K., Hostikka, S., Floyd, J., McDermott, R., Vanella, M.,
  Mueller, E., & Paul, C. (2025). *Fire Dynamics Simulator User's
  Guide*. NIST Special Publication 1019, 6th ed., revision
  FDS-6.10.1-0-g12efa16, §18.3.6 and §22.10.5.
  [github.com/firemodels/fds/releases/tag/FDS-6.10.1](https://github.com/firemodels/fds/releases/tag/FDS-6.10.1)
- Mulholland, G. W., & Croarkin, C. (2000). *Specific extinction
  coefficient of flame generated smoke*. Fire and Materials, 24(5),
  227–230.
  [doi:10.1002/1099-1018(200009/10)24:5<227::AID-FAM742>3.0.CO;2-9](https://doi.org/10.1002/1099-1018%28200009/10%2924:5%3C227::AID-FAM742%3E3.0.CO;2-9)
  (value quoted from the FDS User Guide).
- Purser, D. A., & McAllister, J. L. (2026). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 6th ed., Ch. 70, 2271–2352.
  [doi:10.1007/978-3-031-59212-6_70](https://doi.org/10.1007/978-3-031-59212-6_70)

How pyFDS-Evac uses this: see the [smoke-speed model](/models/smoke-speed.md)
and [route rerouting](/models/routing.md).

How it is verified: [ISO 20414 Test 18](/verification/iso-test-18.md) and the [S2 corridor](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s2_corridor_speed.py) test.
