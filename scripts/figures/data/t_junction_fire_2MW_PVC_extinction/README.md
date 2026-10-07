# t_junction, fire_2MW_PVC: extinction slices only

The soot extinction coefficient at z = 2.0 m from the FDS run of
`assets/t_junction/t_junction.fds` (FDS-6.10.1-0-g12efa16-release), the
only part of the run that `scripts/figures/sign_legibility_steps.py` reads.
It is tracked so the docs workflow can regenerate that figure, and kept out
of `assets/` so the TUI and other tools do not take it for a full run of the
scenario; the full run is in sciebo `fds-evac-data/t_junction/fire_2MW_PVC/`.

The four `.sf` files and their `.sf.bnd` files (one per mesh) are copied
byte for byte from the run. `t_junction.smv` is the run's file with every
`SLCF` block other than `SOOT EXTINCTION COEFFICIENT` and every `SMOKF3D`
block removed, because fdsreader opens every file the `.smv` lists:

```python
lines = open("fire_2MW_PVC/t_junction.smv").read().split("\n")
out, i = [], 0
while i < len(lines):
    head = lines[i].split()
    if head and head[0] in ("SLCF", "SMOKF3D"):
        block = lines[i : i + 5]
        if head[0] == "SLCF" and block[2].strip() == "SOOT EXTINCTION COEFFICIENT":
            out += block
        i += 5
        continue
    out.append(lines[i])
    i += 1
open("t_junction.smv", "w").write("\n".join(out))
```

fdsreader still logs that the run's `_hrr.csv` and `_steps.csv` are
missing; the figure does not use them.

SHA-256 of the source files in sciebo; the `.sf` and `.sf.bnd` files here
are identical:

```
b1d37b64d6dac98884675f65567d733a0e7ea4da2d5c410f3173933c05b6c2ec  t_junction.smv
12423c239f2006fca04837b1b1ddec7015a64387f8901ef85b879eb93a8e7acb  t_junction_1_1.sf
eb40387a7b45be14f7d8c6c315e7abab45ab58d75336d8ec27d12cac4ae00fc1  t_junction_2_1.sf
48b3c8269ffcc9d8f796609704374a1673d730e96b822a7525433e8e93c51434  t_junction_3_1.sf
731da7fa87907c787b3eff9442df3e6a5169b3747fd4beecfc733301894a2bcf  t_junction_4_1.sf
2697d5e1ad34ebe64c7f1dc585c654cbe2efcdc970944987b56560deec4a5aa5  t_junction_1_1.sf.bnd
1777b89056221b1ef0e0b5076df6dda4607c48bb23f489e37e43ed7af99e022f  t_junction_2_1.sf.bnd
cb9a5444c1d77110eb1b1668d8194669a0c086b7d4c2998c2ed2b8d78fffdd2f  t_junction_3_1.sf.bnd
f040984d9be9a63da8a13bbe0b49ff61e8a0cf72540a5e19d6e9cd60c03599f5  t_junction_4_1.sf.bnd
```

SHA-256 of the trimmed `t_junction.smv` here:
`bbcbe86757ea9fffa2f3bf107dc525e15296e5934719a31cc16698fe4b0c7039`.
