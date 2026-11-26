// Host test of the rig firmware logic (firmware/rigidflex_rig/rig_core.h). Built and run by tests/test_rigidflex.py.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>

#include "../firmware/rigidflex_rig/rig_core.h"

static int failures = 0;
#define CHECK(cond)                                                \
  do {                                                             \
    if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); failures++; } \
  } while (0)

int main() {
  using namespace rig;
  CHECK(STEPS_PER_MM == 2400);

  // odometer: 2 mm/s for 1.5 s = 3 mm, then reverse at 1 mm/s for 1 s = 2 mm
  Odometer o;
  o.zero(1000);
  o.change(1000, steps_per_s(2), 1);
  CHECK(std::fabs(o.mm(1501000) - 3.0) < 1e-9);
  o.change(1501000, steps_per_s(1), -1);
  CHECK(std::fabs(o.mm(2501000) - 2.0) < 1e-9);
  // micros() wraps every 71.6 min; positions must survive it
  Odometer w;
  w.zero(0xFFFFFF00u);
  w.change(0xFFFFFF00u, steps_per_s(2), 1);
  CHECK(std::fabs(w.mm(0xFFFFFF00u + 1000000u) - 2.0) < 1e-6);

  // a bond failure: force rises to ~250 N with noise, then drops to ~3 N
  std::mt19937 rng(7);
  std::normal_distribution<float> noise(0, 0.4f);
  Monitor m;
  Stop s = Stop::None;
  float x = 0, x_stop = -1;
  for (int i = 0; i < 4000 && s == Stop::None; i++) {
    x = i * 0.025f;  // 2 mm/s at 80 Hz
    float f = x < 0.3f ? 0 : x < 18 ? 250 * std::tanh((x - 0.3f) / 6) : 3;
    s = m.update(x, f + noise(rng), 40);
    if (s != Stop::None) x_stop = x;
  }
  CHECK(s == Stop::Break);
  CHECK(x_stop > 18 && x_stop < 18.2f);
  CHECK(m.peak() > 230 && m.peak() < 252);
  CHECK(m.peak_x() > 15 && m.peak_x() < 18.1f);

  // noise around zero never counts as a break; travel limit ends the test
  Monitor q;
  s = Stop::None;
  for (int i = 0; i < 4000 && s == Stop::None; i++) s = q.update(i * 0.025f, noise(rng), 40);
  CHECK(s == Stop::MaxTravel);

  // TPU that just stretches (no break) reaches the travel limit
  Monitor t;
  s = Stop::None;
  for (int i = 0; i < 4000 && s == Stop::None; i++) { x = i * 0.025f; s = t.update(x, 8 * x + noise(rng), 37); }
  CHECK(s == Stop::MaxTravel);
  CHECK(x >= 37 && x < 37.1f);

  // overload protection
  Monitor ov;
  CHECK(ov.update(1, 100, 40) == Stop::None);
  CHECK(ov.update(2, 471, 40) == Stop::Overload);

  // a single noisy low sample after the peak is not a break
  Monitor n1;
  n1.update(1, 100, 40);
  CHECK(n1.update(1.1f, 10, 40) == Stop::None);
  CHECK(n1.update(1.2f, 100, 40) == Stop::None);

  // load-cell scale
  Scale sc;
  CHECK(!sc.calibrated() && sc.force(1234) == 0);
  sc.offset = 1000;
  sc.counts_per_n = -210.5f;  // a cell wired "backwards" calibrates to a negative scale and still reads positive
  CHECK(std::fabs(sc.force(1000 - 21050) - 100) < 1e-3);

  // command parser
  Command c;
  CHECK(parse("RUN 40 2\r\n", c) && !std::strcmp(c.name, "run") && c.argc == 2 && c.args[0] == 40 && c.args[1] == 2);
  CHECK(parse("tare", c) && c.argc == 0);
  CHECK(parse("jog -12.5", c) && c.args[0] == -12.5f);
  CHECK(!parse("   ", c));
  CHECK(!parse("cal ten", c));
  CHECK(arg_or(c, 1, 7) == 7);

  if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
  std::printf("firmware core: all checks passed\n");
  return 0;
}
