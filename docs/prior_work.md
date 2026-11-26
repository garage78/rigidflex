# Prior work: what is already known about rigid + TPU bonds in FFF

rigidflex does not start from zero. This page lists the published work closest to it, what each study
found (as stated in its abstract), and what is still missing. Every DOI below was checked against Crossref
or Europe PMC. If you know a paper that belongs here, open an issue.

## Studies

| Study | Materials | What it tested | Main finding |
|---|---|---|---|
| Lopes, Silva & Carneiro, *Additive Manufacturing* 23 (2018) 45–52. [doi:10.1016/j.addma.2018.06.027](https://doi.org/10.1016/j.addma.2018.06.027) | PLA, TPU, PET | "Zebra-crossing" specimens with many material transitions | Material affinity governs the interface; boundary design matters in multi-material printing |
| Tamburrino, Graziosi & Bordegoni, *Virtual and Physical Prototyping* 14(4) (2019) 316–332. [doi:10.1080/17452759.2019.1607758](https://doi.org/10.1080/17452759.2019.1607758) | TPU–PLA, PLA–CPE, CPE–TPU | Butt-joined tensile bars; print order, interface slicing pattern, infill below the interface | Mechanical interlocking raised adhesion even where chemical bonding was weak; thermal history matters |
| Brancewicz-Steinmetz et al., *Materials* 14 (2021) 6464. [doi:10.3390/ma14216464](https://doi.org/10.3390/ma14216464) | PLA, TPU | Adhesion vs printing parameters and material order | Order matters: for several infill-pattern pairs, TPU printed onto PLA did as well as, or better than, the reverse |
| Kuipers, Su, Wu & Wang, *Additive Manufacturing* 50 (2022) 102495. [doi:10.1016/j.addma.2021.102495](https://doi.org/10.1016/j.addma.2021.102495) | Dual-material extrusion | Interlaced, topologically interlocking lattice at the interface | Interlocks all three axes while keeping extrusion continuous; the idea behind the slicers' beam interlocking |
| Frenkel, Ginsbury & Sharabi, *Biomimetics* 7(4) (2022) 170. [doi:10.3390/biomimetics7040170](https://doi.org/10.3390/biomimetics7040170) | **PETG + TPU** | Simple vs bio-inspired stiff-to-compliant interfaces, tensile | Bio-inspired (graded/interdigitated) interfaces increased strain, toughness and modulus over a simple joint |
| Tarrés et al., *Int. J. Advanced Manufacturing Technology* (2025). [doi:10.1007/s00170-025-17099-x](https://doi.org/10.1007/s00170-025-17099-x) | PLA, TPU | Modified lap-shear test of interlaminar bonding | Layer height, line width and temperature gradients change PLA–TPU interlaminar adhesion |

## What these studies agree on

1. **Geometry beats chemistry** when the pair does not bond well: interlocking joints help most (Tamburrino; Kuipers; Frenkel).
2. **Print order and temperature history matter** at the interface (Tamburrino; Brancewicz-Steinmetz; Tarrés).
3. **PLA and TPU have low affinity** (Lopes), so PLA is the hard case.
4. **A graded or bio-inspired transition** from stiff to compliant helps (Frenkel, with PETG and TPU).

## What is still missing, and what rigidflex adds

| Gap | rigidflex |
|---|---|
| No study we found used a toolchanger | On the U1 each material keeps its own hotend and temperature, and print order is set freely (series B and T) |
| Almost no data for **ASA** + TPU, and little for PETG + TPU in butt and lap joints | PLA, PETG and ASA, each with TPU 95A and 85A |
| No heat exposure after printing | Series H: 24 h at 80 °C, for parts in cars or near engines |
| Graded joints only as bio-inspired geometry with two materials | Series G: three materials (rigid → TPU 95A → TPU 85A), only practical on a toolchanger |
| Slicer interlocking (beam interlocking) not measured against simple CAD joints on real hardware | Series A compares flat, sawtooth, dovetail and Orca beam interlocking on the same coupon |
| Raw curves rarely published | Every force–extension curve published under CC BY 4.0, with the code that reads it |

## Predictions to test

From the studies above, before any U1 data:

- Interlocking joints (dovetail, beam) will beat flat butt joints for every pair, and by most for PLA.
- TPU printed on rigid will hold at least as well as rigid printed on TPU.
- PLA–TPU will be the weakest pair, and PLA will lose most after the heat soak.
- The graded three-material joint will raise extension and energy at failure more than peak force.

If the data disagrees, that is published too.
