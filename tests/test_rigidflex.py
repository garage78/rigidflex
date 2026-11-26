"""Run with:  python3 -m unittest discover -s tests"""
import math
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.dom import minidom

from rigidflex.advise import recommend
from rigidflex.analyze import load, summarise
from rigidflex.rig import Curve, SimulatedRig, metrics, plot, read_curve, session, write_curve
from rigidflex.threemf import Object3MF, Volume, read_stl, write_3mf

HERE = Path(__file__).parent
FIXTURE = HERE / "fixture_synthetic.csv"  # made-up numbers, only for testing the maths

CUBE = [((0, 0, 0), (1, 0, 0), (1, 1, 0)), ((0, 0, 0), (1, 1, 0), (0, 1, 0))]


class ThreeMFTest(unittest.TestCase):
    def test_two_volumes_with_extruders(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = write_3mf(Path(tmp) / "t.3mf", [Object3MF("o", [Volume("rigid", CUBE, 1), Volume("tpu", CUBE, 2)])])
            z = zipfile.ZipFile(out)
            main_model = minidom.parseString(z.read("3D/3dmodel.model"))
            self.assertEqual(len(main_model.getElementsByTagName("component")), 2)
            parts_model = minidom.parseString(z.read("3D/Objects/object_1.model"))
            meshes = parts_model.getElementsByTagName("mesh")
            self.assertEqual(len(meshes), 2)
            # each part: 2 triangles, and shared corners are stored once
            self.assertEqual([len(m.getElementsByTagName("triangle")) for m in meshes], [2, 2])
            self.assertEqual([len(m.getElementsByTagName("vertex")) for m in meshes], [4, 4])
            cfg = minidom.parseString(z.read("Metadata/model_settings.config"))
            parts = cfg.getElementsByTagName("part")
            got = []
            for part in parts:
                meta = {m.getAttribute("key"): m.getAttribute("value") for m in part.getElementsByTagName("metadata")}
                got.append((meta["name"], meta["extruder"]))
            self.assertEqual(got, [("rigid", "1"), ("tpu", "2")])

    def test_ascii_stl(self):
        stl = "solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.stl"
            p.write_text(stl)
            self.assertEqual(read_stl(p), [((0, 0, 0), (1, 0, 0), (0, 1, 0))])


class AnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.conds = {c.key[3] + "/" + c.key[1]: c for c in summarise(load(FIXTURE))}

    def test_stats(self):
        flat = self.conds["flat/PETG"]
        self.assertEqual(flat.n, 3)
        self.assertAlmostEqual(flat.mean, 100.0)
        self.assertAlmostEqual(flat.sd, 10.0)
        self.assertAlmostEqual(flat.ci95, 4.303 * 10 / math.sqrt(3), places=3)
        self.assertAlmostEqual(flat.mean_per_width, 5.0)
        self.assertEqual(flat.modes["bond"], 3)

    def test_advise_prefers_fewer_bond_failures(self):
        best = recommend(list(self.conds.values()), "PETG")
        self.assertEqual(best[0].key[3], "dovetail")
        # PLA has only one coupon, below the default minimum of 3
        self.assertEqual(recommend(list(self.conds.values()), "PLA"), [])

    def test_rejects_bad_failure_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text(FIXTURE.read_text().replace(",bond,SYNTHETIC test", ",broke,SYNTHETIC test"))
            with self.assertRaises(ValueError):
                load(bad)


class PlanTest(unittest.TestCase):
    def test_campaign_matrix(self):
        from rigidflex.plan import build, write_checklist, write_sheet
        plates, conds = build()
        self.assertEqual(len(plates), 10)                    # 4 joints + 2 overlaps x 2 orders + 2 graded
        with tempfile.TemporaryDirectory() as tmp:
            n = write_sheet(conds, Path(tmp) / "results.csv")
            self.assertEqual(n, 180)                         # A 60 + B 60 + T 20 + H 20 + G 20
            write_checklist(conds, Path(tmp) / "checklist.md")
            # an untouched sheet has no tested coupons yet
            with self.assertRaises(ValueError):
                load(Path(tmp) / "results.csv")
            # fill in one condition and it analyses
            lines = (Path(tmp) / "results.csv").read_text().splitlines()
            filled = [lines[0]]
            for i, line in enumerate(lines[1:6]):
                cells = line.split(",")
                cells[9], cells[10], cells[11] = "10", str(150 + i), "bond"
                filled.append(",".join(cells))
            (Path(tmp) / "partial.csv").write_text("\n".join(filled + lines[6:]) + "\n")
            conds = summarise(load(Path(tmp) / "partial.csv"))
            self.assertEqual(len(conds), 1)
            self.assertEqual(conds[0].n, 5)


def _linear_curve(slack=1.0, k=50.0, peak=200.0):
    c = Curve()
    for i in range(1001):
        x = i * 0.01
        f = 0.0 if x < slack else k * (x - slack)
        if f > peak:
            f = 2.0                                   # broke
        c.add(i * 5, x, f)
    return c


class CurveTest(unittest.TestCase):
    def test_metrics_with_toe_compensation(self):
        m = metrics(_linear_curve())
        self.assertAlmostEqual(m["stiffness_n_mm"], 50, places=6)
        self.assertAlmostEqual(m["peak_force_n"], 200, places=6)
        self.assertAlmostEqual(m["extension_mm"], 4.0, places=6)        # the 1 mm of slack is removed
        self.assertAlmostEqual(m["energy_j"], 0.5 * 200 * 4 / 1000, places=4)

    def test_rig_compliance_correction(self):
        m = metrics(_linear_curve(), rig_stiffness=500)
        self.assertAlmostEqual(m["extension_mm"], 4.0 - 200 / 500, places=6)
        self.assertAlmostEqual(m["stiffness_n_mm"], 1 / (1 / 50 - 1 / 500), places=4)

    def test_curve_file_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _linear_curve()
            c.meta["condition"] = "A PETG dovetail"
            back = read_curve(write_curve(Path(tmp) / "c.csv", c))
            self.assertEqual(back.meta["condition"], "A PETG dovetail")
            self.assertEqual(len(back.f_n), len(c.f_n))
            self.assertAlmostEqual(metrics(back)["extension_mm"], 4.0, places=2)


class SessionTest(unittest.TestCase):
    def test_guided_session_with_simulated_rig(self):
        from rigidflex.plan import build, write_sheet
        _, conds = build()
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "results.csv"
            write_sheet(conds[:1], sheet)                   # one condition, 5 coupons
            answers = iter(["10.1", "", "b"] + ["", "", ""] * 3 + ["q"])
            out: list[str] = []
            done = session(sheet, SimulatedRig(seed=3), ask=lambda _: next(answers), say=out.append)
            self.assertEqual(done, 4)
            rows = load(sheet)                              # the untested 5th coupon is skipped by load()
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["width_mm"], "10.1")
            self.assertTrue(all(r["energy_j"] and r["curve"] for r in rows))
            curves = sorted((Path(tmp) / "curves").glob("*.csv"))
            self.assertEqual(len(curves), 4)
            svg = plot(curves, Path(tmp) / "c.svg")
            self.assertIn("<polyline", svg.read_text())
            c = summarise(rows)[0]
            self.assertIsNotNone(c.extra_mean("energy_j"))


class WasteTest(unittest.TestCase):
    def test_waste_report(self):
        from rigidflex.analyze import waste_report
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "print_log.csv"
            p.write_text("series,rigid,plate,tpu_temp_c,print_time_min,parts_g,u1_waste_g,single_nozzle_flush_g,toolchanges,notes\n"
                         "A,PLA,A_flat.3mf,230,60,20,2,30,40,\nA,PLA,A_dovetail.3mf,230,60,20,2,,40,\nB,PLA,x,230,,,,,,\n")
            r = waste_report(p)
            self.assertIn("2 plate(s) logged: 40 g", r)
            self.assertIn("30 g of flush", r)


@unittest.skipUnless(shutil.which("c++"), "no C++ compiler")
class FirmwareTest(unittest.TestCase):
    def test_firmware_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "fwsim"
            subprocess.run(["c++", "-std=c++17", "-O1", "-o", str(exe), str(HERE / "firmware_sim.cpp")], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout)


@unittest.skipUnless(shutil.which("openscad"), "OpenSCAD not installed")
class KitTest(unittest.TestCase):
    def test_coupon_and_grommet(self):
        from rigidflex.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            for args in (["kit", "coupon", "--type", "A", "--joint", "sawtooth", "--copies", "2"],
                         ["kit", "coupon", "--type", "B"],
                         ["kit", "grommet", "--hole", "20", "--cable", "6"],
                         ["kit", "softjaw", "--width", "80", "--height", "20"]):
                self.assertEqual(self._extruders(main, args, tmp), {"1", "2"})
            for args in (["kit", "coupon", "--type", "G", "--joint", "graded", "--copies", "1"],
                         ["kit", "grommet", "--hole", "25", "--cable", "8", "--three"]):
                self.assertEqual(self._extruders(main, args, tmp), {"1", "2", "3"})
            self.assertEqual(self._extruders(main, ["kit", "coupon", "--type", "G", "--joint", "direct", "--copies", "1"], tmp), {"1", "3"})

    @staticmethod
    def _extruders(main, args, tmp):
        out = Path(tmp) / "k.3mf"
        main(args + ["-o", str(out)])
        cfg = minidom.parseString(zipfile.ZipFile(out).read("Metadata/model_settings.config"))
        return {m.getAttribute("value") for part in cfg.getElementsByTagName("part")
                for m in part.getElementsByTagName("metadata") if m.getAttribute("key") == "extruder"}

    def test_rig_parts(self):
        from rigidflex.cli import RIG_PARTS, main
        with tempfile.TemporaryDirectory() as tmp:
            main(["kit", "rig", "-o", tmp])
            for p in RIG_PARTS:
                self.assertGreater(len(read_stl(Path(tmp) / f"rig_{p}.stl")), 12)


if __name__ == "__main__":
    unittest.main()
