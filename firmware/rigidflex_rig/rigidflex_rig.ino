// rigidflex pull-test rig firmware for an ESP32 DevKit (Arduino core 2.x or 3.x, no extra libraries)
// rigidflex by garage78 · MIT
//
// Hardware: 50 kg S-type load cell -> HX711 (RATE pin high = 80 samples/s)
//           NEMA17 -> TMC2209 in standalone mode (MS1 = MS2 = GND: 1/8 microstepping)
//           24 mm push button (stop), optional end-stop microswitch at the motor end
// Wiring: docs/pull_rig.md. Talk to it at 115200 baud, or let `rigidflex test` do it.
//
// Commands (one per line):            Replies:
//   info                               OK,info,...
//   tare                               OK,tare,<offset>
//   cal <newtons>                      OK,cal,<counts_per_n>     (after tare, with a known load applied)
//   scale <counts_per_n>               OK,scale,<counts_per_n>
//   read                               OK,read,<newtons>
//   watch <seconds>                    D lines without moving, then OK,watch
//   jog <mm> [mm/s]                    OK,jog,<mm moved>         (+ = pull direction)
//   run <max_mm> [mm/s]                START,..., D,<t_ms>,<x_mm>,<force_n> ... END,<reason>,<peak_n>,<x_at_peak>,<x_end>
//   en <0|1>                           motor driver on / off
// Any byte received during a move, or the button, stops it.

#include <Arduino.h>
#include <Preferences.h>

#include "rig_core.h"

#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

static const char* VERSION = "2.0";

// ---- pins ----
constexpr int PIN_HX_DOUT = 19, PIN_HX_SCK = 18;
constexpr int PIN_STEP = 25, PIN_DIR = 26, PIN_EN = 27;
constexpr int PIN_BUTTON = 33, PIN_ENDSTOP = 32, PIN_LED = 2;
constexpr int DIR_PULL = HIGH;   // if the carriage moves towards the load cell on `jog 5`, change to LOW

Preferences prefs;
rig::Scale scale;
rig::Monitor monitor;
rig::Odometer odo;
portMUX_TYPE hx_mux = portMUX_INITIALIZER_UNLOCKED;
bool motor_enabled = false;

// ---- HX711 ----
bool hx_wait(uint32_t timeout_ms) {
  uint32_t t0 = millis();
  while (digitalRead(PIN_HX_DOUT) == HIGH) {
    if (millis() - t0 > timeout_ms) return false;
    delayMicroseconds(100);
  }
  return true;
}

long hx_read_raw() {  // 24 data bits, then one more clock pulse = channel A, gain 128
  long v = 0;
  portENTER_CRITICAL(&hx_mux);
  for (int i = 0; i < 24; i++) {
    digitalWrite(PIN_HX_SCK, HIGH);
    delayMicroseconds(1);
    v = (v << 1) | digitalRead(PIN_HX_DOUT);
    digitalWrite(PIN_HX_SCK, LOW);
    delayMicroseconds(1);
  }
  digitalWrite(PIN_HX_SCK, HIGH);
  delayMicroseconds(1);
  digitalWrite(PIN_HX_SCK, LOW);
  portEXIT_CRITICAL(&hx_mux);
  if (v & 0x800000) v |= ~0xFFFFFFL;  // sign-extend 24 -> 32 bits
  return v;
}

bool hx_average(int n, double& out) {
  double sum = 0;
  for (int i = 0; i < n; i++) {
    if (!hx_wait(500)) return false;
    sum += hx_read_raw();
  }
  out = sum / n;
  return true;
}

// ---- STEP pulses from a hardware PWM channel ----
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void step_init() { ledcAttach(PIN_STEP, 1000, 8); ledcWrite(PIN_STEP, 0); }
double step_hz(double hz) {
  if (hz < 1) { ledcWrite(PIN_STEP, 0); return 0; }
  double f = ledcChangeFrequency(PIN_STEP, (uint32_t)lround(hz), 8);
  ledcWrite(PIN_STEP, 128);
  return f;
}
#else
constexpr int LEDC_CH = 0;
void step_init() { ledcSetup(LEDC_CH, 1000, 8); ledcAttachPin(PIN_STEP, LEDC_CH); ledcWrite(LEDC_CH, 0); }
double step_hz(double hz) {
  if (hz < 1) { ledcWrite(LEDC_CH, 0); return 0; }
  double f = ledcChangeFrequency(LEDC_CH, (uint32_t)lround(hz), 8);
  ledcWrite(LEDC_CH, 128);
  return f;
}
#endif

void motor_enable(bool on) {
  digitalWrite(PIN_EN, on ? LOW : HIGH);  // TMC2209 EN is active low
  motor_enabled = on;
  if (on) delay(5);
}

bool button() { return digitalRead(PIN_BUTTON) == LOW; }
bool endstop() { return digitalRead(PIN_ENDSTOP) == LOW; }

// Move `dist` mm at `speed` mm/s (+ = pull). With record = true, stream D lines and apply the stop rule.
rig::Stop move(float dist, float speed, bool record, float max_mm) {
  speed = constrain(fabsf(speed), 0.05f, rig::MAX_SPEED_MM_S);
  int dir = dist >= 0 ? 1 : -1;
  digitalWrite(PIN_DIR, dir > 0 ? DIR_PULL : !DIR_PULL);
  motor_enable(true);
  while (Serial.available()) Serial.read();

  uint32_t t0 = micros();
  odo.zero(t0);
  monitor.reset();
  const double target = rig::steps_per_s(speed);
  // short ramp (5 steps over 100 ms) so the motor never stalls on start
  int ramp_step = 0;
  uint32_t next_ramp = t0;
  rig::Stop why = rig::Stop::None;

  while (why == rig::Stop::None) {
    uint32_t now = micros();
    if (ramp_step <= 5 && (int32_t)(now - next_ramp) >= 0) {
      double hz = target * (ramp_step == 5 ? 1.0 : 0.2 * (ramp_step + 1));
      odo.change(now, step_hz(hz), dir);
      ramp_step++;
      next_ramp = now + 20000;
    }
    if (Serial.available() || button()) why = rig::Stop::User;
    if (dir > 0 && endstop()) why = rig::Stop::Endstop;

    if (record) {
      if (digitalRead(PIN_HX_DOUT) == LOW) {
        long raw = hx_read_raw();
        uint32_t t = micros();
        double x = odo.mm(t);
        float f = scale.force(raw);
        Serial.printf("D,%lu,%.3f,%.2f\n", (unsigned long)((t - t0) / 1000), x, f);
        if (why == rig::Stop::None) why = monitor.update((float)x, f, max_mm);
      }
    } else if (fabs(odo.mm(micros())) >= fabsf(dist)) {
      why = rig::Stop::MaxTravel;
    }
    if (!record) delayMicroseconds(200);
  }
  odo.change(micros(), step_hz(0), dir);
  digitalWrite(PIN_LED, LOW);
  return why;
}

// ---- commands ----
void cmd_info() {
  Serial.printf("OK,info,version=%s,steps_per_mm=%.0f,counts_per_n=%.3f,capacity_n=%.0f,calibrated=%d\n", VERSION,
                rig::STEPS_PER_MM, scale.counts_per_n, rig::StopRule().capacity_n, scale.calibrated() ? 1 : 0);
}

bool do_tare() {
  double avg;
  if (!hx_average(40, avg)) { Serial.println("ERR,no data from the HX711 (check wiring)"); return false; }
  scale.offset = lround(avg);
  return true;
}

void handle(const rig::Command& c) {
  const char* n = c.name;
  if (!strcmp(n, "info") || !strcmp(n, "?")) { cmd_info(); return; }
  if (!strcmp(n, "tare")) { if (do_tare()) Serial.printf("OK,tare,%ld\n", scale.offset); return; }
  if (!strcmp(n, "cal")) {
    float load = rig::arg_or(c, 0, 0);
    double avg;
    if (load <= 0) { Serial.println("ERR,usage: cal <newtons> (tare first, unloaded)"); return; }
    if (!hx_average(80, avg)) { Serial.println("ERR,no data from the HX711"); return; }
    scale.counts_per_n = (float)((avg - scale.offset) / load);
    prefs.putFloat("cpn", scale.counts_per_n);
    Serial.printf("OK,cal,%.3f\n", scale.counts_per_n);
    return;
  }
  if (!strcmp(n, "scale")) {
    scale.counts_per_n = rig::arg_or(c, 0, 0);
    prefs.putFloat("cpn", scale.counts_per_n);
    Serial.printf("OK,scale,%.3f\n", scale.counts_per_n);
    return;
  }
  if (!strcmp(n, "read")) {
    double avg;
    if (!hx_average(16, avg)) { Serial.println("ERR,no data from the HX711"); return; }
    Serial.printf("OK,read,%.2f\n", scale.force(lround(avg)));
    return;
  }
  if (!strcmp(n, "watch")) {
    uint32_t t0 = millis(), dur = (uint32_t)(rig::arg_or(c, 0, 5) * 1000);
    while (millis() - t0 < dur && !Serial.available()) {
      if (hx_wait(200)) Serial.printf("D,%lu,0.000,%.2f\n", (unsigned long)(millis() - t0), scale.force(hx_read_raw()));
    }
    Serial.println("OK,watch");
    return;
  }
  if (!strcmp(n, "en")) { motor_enable(rig::arg_or(c, 0, 1) != 0); Serial.printf("OK,en,%d\n", motor_enabled); return; }
  if (!strcmp(n, "jog")) {
    float d = rig::arg_or(c, 0, 0);
    if (d == 0) { Serial.println("ERR,usage: jog <mm> [mm/s]"); return; }
    rig::Stop why = move(d, rig::arg_or(c, 1, 5), false, 0);
    Serial.printf("OK,jog,%.3f,%s\n", odo.mm(micros()), why == rig::Stop::MaxTravel ? "done" : rig::stop_name(why));
    return;
  }
  if (!strcmp(n, "run")) {
    float max_mm = rig::arg_or(c, 0, 40), speed = rig::arg_or(c, 1, 2);
    if (!scale.calibrated()) { Serial.println("ERR,not calibrated: tare, hang a known load, then cal <newtons>"); return; }
    if (max_mm <= 0) { Serial.println("ERR,usage: run <max_mm> [mm/s]"); return; }
    if (!do_tare()) return;
    digitalWrite(PIN_LED, HIGH);
    Serial.printf("START,%.3f,%.1f,%.0f\n", speed, max_mm, rig::STEPS_PER_MM);
    rig::Stop why = move(max_mm, speed, true, max_mm);
    Serial.printf("END,%s,%.2f,%.3f,%.3f\n", rig::stop_name(why), monitor.peak(), monitor.peak_x(), odo.mm(micros()));
    return;
  }
  Serial.printf("ERR,unknown command '%s' (try info)\n", n);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_HX_DOUT, INPUT);
  pinMode(PIN_HX_SCK, OUTPUT);
  digitalWrite(PIN_HX_SCK, LOW);
  pinMode(PIN_STEP, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_EN, OUTPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_ENDSTOP, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  motor_enable(false);
  step_init();
  prefs.begin("rigidflex", false);
  scale.counts_per_n = prefs.getFloat("cpn", 0);
  delay(300);
  Serial.printf("# rigidflex rig %s ready\n", VERSION);
  cmd_info();
}

void loop() {
  static char line[64];
  static int len = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      line[len] = 0;
      rig::Command c;
      if (len && rig::parse(line, c)) handle(c);
      else if (len) Serial.println("ERR,could not parse the command");
      len = 0;
    } else if (len < (int)sizeof(line) - 1) {
      line[len++] = ch;
    }
  }
  if (motor_enabled && button()) motor_enable(false);  // idle press releases the motor so the carriage can be pushed by hand
}
