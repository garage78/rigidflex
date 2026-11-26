// rigidflex rig firmware: hardware-independent logic.
// Compiled into the ESP32 sketch and into tests/firmware_sim.cpp on a normal computer.
// rigidflex by garage78 · MIT
#pragma once
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

namespace rig {

// Drive train: 200-step motor, 1/8 microstepping (TMC2209 with MS1 = MS2 = GND), 20T -> 60T belt, T8 lead 2 mm.
constexpr double MOTOR_STEPS = 200, MICROSTEPS = 8, BELT_RATIO = 3, LEAD_MM = 2;
constexpr double STEPS_PER_MM = MOTOR_STEPS * MICROSTEPS * BELT_RATIO / LEAD_MM;   // 2400
constexpr float MAX_SPEED_MM_S = 8.0f;

struct StopRule {
  float capacity_n = 470.0f;     // stop just below the 50 kg (490 N) cell's rating
  float min_peak_n = 5.0f;       // a break only counts once the force has passed this
  float drop_fraction = 0.25f;   // ... and then falls below 25 % of the peak
  int drop_samples = 3;          // ... for this many samples in a row (≈ 40 ms at 80 Hz)
};

enum class Stop { None, Break, MaxTravel, Overload, User, Endstop };

inline const char* stop_name(Stop s) {
  switch (s) {
    case Stop::Break: return "break";
    case Stop::MaxTravel: return "max";
    case Stop::Overload: return "overload";
    case Stop::User: return "user";
    case Stop::Endstop: return "endstop";
    default: return "none";
  }
}

// Watches each (extension, force) sample of a pull and says when to stop.
class Monitor {
 public:
  explicit Monitor(StopRule r = StopRule()) : r_(r) {}
  void reset() { peak_ = 0; peak_x_ = 0; low_ = 0; }
  Stop update(float x_mm, float f_n, float max_mm) {
    if (f_n > peak_) { peak_ = f_n; peak_x_ = x_mm; }
    if (f_n >= r_.capacity_n) return Stop::Overload;
    if (peak_ >= r_.min_peak_n && f_n < r_.drop_fraction * peak_) {
      if (++low_ >= r_.drop_samples) return Stop::Break;
    } else {
      low_ = 0;
    }
    if (x_mm >= max_mm) return Stop::MaxTravel;
    return Stop::None;
  }
  float peak() const { return peak_; }
  float peak_x() const { return peak_x_; }

 private:
  StopRule r_;
  float peak_ = 0, peak_x_ = 0;
  int low_ = 0;
};

// Carriage position from the step frequency actually generated, integrated over time.
// The STEP pulses come from a hardware PWM channel, so the frequency is exact and constant
// between changes; only the moments of change need recording.
class Odometer {
 public:
  void zero(uint32_t t_us) { mm0_ = 0; t0_ = t_us; hz_ = 0; dir_ = 1; }
  void change(uint32_t t_us, double hz, int dir) { mm0_ = mm(t_us); t0_ = t_us; hz_ = hz; dir_ = dir; }
  double mm(uint32_t t_us) const { return mm0_ + dir_ * hz_ * (double)(uint32_t)(t_us - t0_) * 1e-6 / STEPS_PER_MM; }

 private:
  double mm0_ = 0, hz_ = 0;
  uint32_t t0_ = 0;
  int dir_ = 1;
};

inline double steps_per_s(float mm_s) { return fabs(mm_s) * STEPS_PER_MM; }

// Load-cell conversion. counts_per_n comes from `cal`, offset from `tare`.
struct Scale {
  long offset = 0;
  float counts_per_n = 0;
  bool calibrated() const { return counts_per_n != 0 && !isnan(counts_per_n); }
  float force(long raw) const { return calibrated() ? (float)(raw - offset) / counts_per_n : 0.0f; }
};

// "run 40 2" -> name "run", args {40, 2}
struct Command {
  char name[12] = {0};
  int argc = 0;
  float args[3] = {0, 0, 0};
};

inline bool parse(const char* line, Command& c) {
  c = Command();
  char buf[64];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = 0;
  char* save = nullptr;
  char* tok = strtok_r(buf, " \t\r\n", &save);
  if (!tok) return false;
  strncpy(c.name, tok, sizeof(c.name) - 1);
  for (char* p = c.name; *p; ++p) if (*p >= 'A' && *p <= 'Z') *p += 32;
  while ((tok = strtok_r(nullptr, " \t\r\n", &save)) && c.argc < 3) {
    char* end = nullptr;
    float v = strtof(tok, &end);
    if (end == tok) return false;
    c.args[c.argc++] = v;
  }
  return true;
}

inline float arg_or(const Command& c, int i, float dflt) { return c.argc > i ? c.args[i] : dflt; }

}  // namespace rig
