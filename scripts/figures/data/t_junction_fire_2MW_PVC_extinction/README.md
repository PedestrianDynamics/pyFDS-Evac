# t_junction, fire_2MW_PVC: extinction slices only

The soot extinction coefficient at z = 2.0 m from the FDS run of
`assets/t_junction/t_junction.fds` (FDS-6.10.1-0-g12efa16-release, with
the PVC set of #796), the
only part of the run that `scripts/figures/sign_legibility_steps.py` reads.
It is tracked so the docs workflow can regenerate that figure, and kept out
of `assets/` so the TUI and other tools do not take it for a full run of the
scenario; the full run is in sciebo `fds-evac-data/t_junction/fire_2MW_PVC_796/`.

The four `.sf` files and their `.sf.bnd` files (one per mesh) are copied
byte for byte from the run. `t_junction.smv` is the run's file with every
`SLCF` block other than `SOOT EXTINCTION COEFFICIENT` and every `SMOKF3D`
block removed, because fdsreader opens every file the `.smv` lists:

```python
lines = open("fire_2MW_PVC_796/t_junction.smv").read().split("\n")
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
733634a85214435ad4a5d2f662f6e47406969f26fc352c63098089a2beae9e06  t_junction.smv
b245e0545b8a5832ed0f6bc8238e960a05820979674817ca4bdb7273c84a0441  t_junction_1_1.sf
816fc7c745f40273336ffcc3f4e0cdcc3d70656f49c0d262c03954963a2faccb  t_junction_2_1.sf
e87c208eff32d2e0d12689c1356d5f4c7565812e61feceb2f72b2a5218619e69  t_junction_3_1.sf
8a3b32c964efd6a31c2090be518deab8c0570aef8922ad3d3631c49343be209e  t_junction_4_1.sf
25849f65c51bafc874866f90ce66583122f50aff2fd8b21def3605988d67001e  t_junction_1_1.sf.bnd
0bf0afa63619578adeca2f2386ac1b53642d5ad255500ae338db8d43b16d8d3b  t_junction_2_1.sf.bnd
d18e53c7c4c204163430effc75661ba30ebdb250806edd4ec61994bc566ccce9  t_junction_3_1.sf.bnd
9350f8d62ac1b7622158e4da7c7364b4cb61637c4ed92d5fe33dadfefb910a2f  t_junction_4_1.sf.bnd
```

SHA-256 of the trimmed `t_junction.smv` here:
`0f6bb8f4e5b5e38b67536d8dbaa08f3a95717eb9974b1c813a8833d546228570`.
