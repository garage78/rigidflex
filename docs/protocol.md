# Test protocol: rigid + TPU bond on the Snapmaker U1

Version 0.3, written before the hardware arrives. Anyone should be able to repeat this and get comparable numbers.

## 1. Materials

- **TPU 95A:** one brand and one spool lot for the whole study.
- **Soft TPU 85A:** for series G and the three-material grommet, also one brand and one lot. If 85A won't feed reliably, use 90A and note it.
- Dry all TPU for 6 h at 50 °C before use.
- **Rigid:** PLA, PETG and ASA, one brand each. ASA is always printed with the U1 top cover installed.
- Record the brand, colour and lot of every spool in `notes`.

## 2. Printing

- **Spool layout** for the whole campaign: extruder 1 rigid, extruder 2 TPU 95A, extruder 3 TPU 85A, extruder 4 free. Every generated 3MF already assigns its parts to these extruders.
- Generate every plate with `rigidflex plan`, or a single one with `rigidflex kit coupon ...`. Each plate holds 5 coupons of one condition.
- **Settings:** keep the defaults unless the series varies the setting: 0.4 mm nozzles, 0.2 mm layers, 100 % infill, 3 walls. A solid coupon measures the bond, not the infill pattern.
- Print orientation is flat on the plate, as generated.
- **Records:** note the slicer version and keep the sliced 3MF that produced every plate. It is published with the data.
- **Print log:** for each plate, fill in a row of `print_log.csv`:
  - print time and the weight of the coupons;
  - the **weight of everything that is not a coupon** (prime tower, purge, skirt), weighed on a 0.1 g scale;
  - the number of toolchanges, as the slicer reports it.
  
  Then slice the same 3MF once for a single-nozzle printer with a filament changer, with that slicer's default flush volumes, and note its flush estimate in `single_nozzle_flush_g`. That shows how much material the toolchanger saves on real multi-material parts.
- Do not test any coupon with visible defects at the interface. Record them as excluded, with a photo.

## 3. Conditioning

- **Standard (`48h-RT`):** 48 h at room temperature, with the room temperature and humidity noted.
- **Heat soak (`heat-80C-24h`):** 24 h at 80 °C in an oven, then 24 h at room temperature before testing.

## 4. Pull test

- **Rig:** the motorised rig in [pull_rig.md](pull_rig.md): a 50 kg load cell, the coupon pinned at both ends with M6 bolts, and the carriage driven by a stepper at a constant speed.
- **Before the first test, and every 50 tests:**
  - Calibrate the force with known masses.
  - Measure the rig's own stiffness once with the steel dummy coupon.
  
  Both are described in [pull_rig.md](pull_rig.md#calibration).
- **Speed:** 2 mm/s (120 mm/min), set by the firmware.
- **Stop when** the joint separates, or the TPU tears, or the TPU section reaches **100 % strain**, whichever comes first.
  - 100 % strain is about 37 mm of carriage travel. `rigidflex test --max-mm 40` stops there, including slack.
  - The firmware stops by itself when the force falls below 25 % of the peak, which is a break.
  - If the TPU reaches 100 % strain without failing, record `failure_mode = tpu`. The bond held beyond the point where the TPU yields, which is the best possible result.
- **How to run it:** `rigidflex test results.csv --port … --rig-stiffness …` walks through every untested coupon in order:
  1. Type the gauge-section width at the joint, measured with calipers.
  2. Pin the coupon in so it hangs straight with no slack, then press Enter.
  3. The rig pulls and stops.
  4. Classify the **failure mode**:
     - `bond`: separates at the interface
     - `tpu`: the TPU tears, or reaches 100 % strain with the bond intact
     - `rigid`: the rigid part breaks
     - `grip`: failure at a pin hole, so the coupon is invalid and gets re-tested
- **What gets saved:** the full curve goes to `curves/`, and the sheet gets the peak force, extension at peak, energy to peak and initial stiffness. The sheet is saved after every coupon.
  - Extension is toe-compensated: pin slack is removed by extending the 10–40 % line to zero force.
  - With `--rig-stiffness`, the rig's own deflection is removed as well.
- Take one photo per coupon after failure, named like its curve file.

## 5. Recording

`rigidflex plan` writes `results.csv` with one row per coupon and every condition column already filled in. `rigidflex test` fills in the rest. Without the rig you can also type the values by hand, starting from `data/results_template.csv` for a single pair:

| column | meaning |
|---|---|
| `series` | A, B, T, H, G |
| `rigid`, `tpu` | materials (e.g. `PETG`, `TPU95A`; G: `TPU85A` or `TPU95A+TPU85A`) |
| `joint` | A: `flat` / `sawtooth` / `dovetail` / `orca-beam`; B: `lap`; G: `direct` / `graded` |
| `overlap_mm` | B only |
| `tpu_temp_c` | TPU nozzle temperature |
| `toolchange_order` | B only: `tpu-on-rigid` / `rigid-on-tpu` |
| `conditioning` | `48h-RT` or `heat-80C-24h` |
| `specimen` | 1..5 |
| `width_mm` | measured width at the joint (calipers) |
| `peak_force_n` | peak force, N |
| `failure_mode` | `bond` / `tpu` / `rigid` / `grip` |
| `extension_mm` | extension at peak, mm (toe-compensated) |
| `energy_j` | energy to peak, J |
| `stiffness_n_mm` | initial stiffness, N/mm (10–40 % of peak) |
| `curve` | the curve file, relative to the sheet |
| `notes` | anything unusual |

Then run:

```bash
rigidflex analyze results.csv --plates print_log.csv
rigidflex plot curves/A_PETG*.csv -o A_PETG.svg
```

## 6. Series G: graded joint

- `G_direct`: rigid butt-jointed straight to TPU 85A.
- `G_graded`: the same joint with a 6 mm band of TPU 95A between the rigid part and the 85A. That makes three materials in one part, printed with three extruders.
- **The question:** does a stiffness step in between make a soft part hold better than the direct joint? On a single-nozzle printer this costs two purges per layer. On the U1 it is one more toolchange.

## 7. Function test (series F)

- Fit each grommet in a 1.2 mm steel test panel with an 8 mm cable through it. Test both the two-material version and the three-material version (95A membrane + 85A lip).
- Put a 100 mm water column above it for 1 h, then check for leaks with paper towel underneath.
- Repeat after 20 insertions and removals of the cable.
- Grommets that pass are fitted on a vehicle and checked again after one month of use.
