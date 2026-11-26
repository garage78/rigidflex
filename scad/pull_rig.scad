// rigidflex pull-test rig v2: motorised, with a load cell and force-extension logging
// rigidflex by garage78 · CC BY 4.0
//
// Load path (left to right):
//   anchor wall -> M8 bolt -> 50 kg S-type load cell -> M8 stud -> free fork -> coupon
//   -> fork on the carriage -> carriage -> brass nut -> T8x2 lead screw
//   -> 608 bearing in the motor end -> 60T GT2 pulley <- belt <- 20T pulley <- NEMA17
//
// Sizing (see docs/pull_rig.md):
//   max load   ≈ 300–360 N (coupon 10 x 3 mm; test stops at 100 % TPU strain) -> 50 kg (490 N) S cell
//   drive      T8 lead 2 mm, 3:1 belt reduction, 1/8 microstepping -> 2400 steps/mm; 2 mm/s = 4.8 kHz
//   torque     ≈ 0.13 N·m at the motor at 360 N (screw efficiency ≈ 0.3) vs ≈ 0.35 N·m available at 180 rpm
//   stroke     ≈ 80 mm (needed ≈ 40–45 mm)
//
// Printed parts: ebox, ebox_lid, cell_anchor, fork_a, carriage, motor_end. PETG or ASA, 5 walls, 40 % infill.
// Measure your load cell and set the [Load cell] values before printing the anchor and the fork.

part = "assembly"; // ["assembly", "ebox", "ebox_lid", "cell_anchor", "fork_a", "carriage", "motor_end"]
component = "";    // used by scripts/render_rig.py to export one assembly component at a time

/* [Base board] */
board = [650, 120, 18];
rail  = [12, 6];      // guide strips (width, height): 6 mm plywood, laser-cut, screwed along both board edges
/* [Load cell (S-type, measure yours)] */
lc_len    = 63.5;     // along the pull axis, between the two threaded faces
lc_w      = 51;       // across
lc_t      = 19;       // thickness (vertical as mounted)
lc_thread = 8;        // M8 on most 50 kg cells (some are M6 or M10)
/* [Coupon] */
c_len = 124; c_grip = 25; c_t = 3; c_w = 20;
/* [Drive] */
belt_c = 58.6;        // 20T-60T centre distance for a 200 mm closed GT2 belt
p60 = 38.2; p20 = 12.73;   // pulley pitch diameters
/* [Mechanics] */
gap     = c_t + 0.6;  // slot for the coupon between fork ears
ear_t   = 7;
pin_d   = 6.4;        // M6 bolt
screw_d = 8;          // T8
brg     = [22.2, 7.2];// 608 bearing (OD, width) + 0.2 clearance
deck    = 6;
plate_t = 10;         // motor-end plate
$fn = 48;

H = 26;                                   // pull axis height above the board
// key positions along X
box      = [104, 72, 34];
x_box    = 6;
x_anchor = 136; anchor_t = 14;
x_cell0  = x_anchor + anchor_t + 6.5;     // jam nut between wall and cell
x_cell1  = x_cell0 + lc_len;
x_forkA  = x_cell1 + 6.5;                 // jam nut between cell and fork
x_pinA   = x_forkA + 35;
x_coupon = x_pinA - c_grip/2;
x_pinB   = x_coupon + c_len - c_grip/2;
x_car    = x_pinB - 14;
car_len  = 140;
x_end    = board[0] - 40;                 // inner face of the motor-end plate
x_rail_end = x_end - 42;
stroke   = x_rail_end - (x_car + car_len);
echo(stroke_mm = stroke);
zm = H + belt_c;                          // motor axis height

module teardrop_x(d, h) {                 // horizontal hole along X that prints without support
    rotate([0, 90, 0]) linear_extrude(h) rotate(90) hull() { circle(d=d); translate([d/2*0.72, 0]) rotate(45) square(d/2*0.72*1.0, center=true); }
}
module rbox(s, r) { hull() for (x = [r, s[0]-r], y = [r, s[1]-r]) translate([x, y, 0]) cylinder(r=r, h=s[2]); }

// ======================= printed parts =======================

module ebox() {
    // ESP32 + TMC2209 + HX711 soldered on a 70 x 50 mm perfboard; 12 V jack and USB on the left, cables on the right
    w = 2.4; L = box[0]; W = box[1]; Hb = box[2];
    difference() {
        union() {
            translate([0, -W/2, 0]) rbox([L, W, Hb], 4);
            for (s = [-1, 1]) translate([L/2 - 12, s > 0 ? W/2 - 1 : -W/2 - 9, 0]) cube([24, 10, 4]);   // screw tabs
        }
        translate([w, -W/2 + w, w]) rbox([L - 2*w, W - 2*w, Hb], 2);
        translate([-1, -12, w + 9]) cube([w + 2, 12, 7]);                                     // USB
        translate([-1, 20, 17]) rotate([0, 90, 0]) cylinder(d=8, h=w + 2);                     // 12 V jack
        for (y = [10, 26]) translate([L - w - 1, y, 14]) rotate([0, 90, 0]) cylinder(d=6, h=w + 2); // cable glands
        for (s = [-1, 1]) translate([L/2, s*(W/2 + 4), -1]) cylinder(d=4.5, h=6);              // wood screws
    }
    for (x = [L/2 - 33, L/2 + 33], y = [-23, 23])                                              // perfboard standoffs
        translate([x, y, 0]) difference() { cylinder(d=6, h=w + 6); cylinder(d=2.2, h=w + 7); }
    for (x = [w + 3.5, L - w - 3.5], y = [-W/2 + w + 3.5, W/2 - w - 3.5])                     // lid bosses
        translate([x, y, 0]) difference() { cylinder(d=7, h=Hb); translate([0, 0, Hb - 10]) cylinder(d=2.6, h=11); }
}

module ebox_lid() {
    w = 2.4; L = box[0]; W = box[1];
    difference() {
        union() {
            translate([0, -W/2, 0]) rbox([L, W, 3], 4);
            translate([w + 0.3, -W/2 + w + 0.3, -2]) difference() {
                rbox([L - 2*w - 0.6, W - 2*w - 0.6, 2], 2);
                translate([1.6, 1.6, -1]) rbox([L - 2*w - 3.8, W - 2*w - 3.8, 4], 1);
            }
        }
        for (x = [w + 3.5, L - w - 3.5], y = [-W/2 + w + 3.5, W/2 - w - 3.5]) {
            translate([x, y, -3]) cylinder(d=3.4, h=10);
            translate([x, y, -3]) cylinder(d=8, h=1 + 2);   // clear the bosses under the lip
        }
        translate([L*0.72, 0, -3]) cylinder(d=24.2, h=10);                       // 24 mm stop / start button
        translate([L*0.32, 0, 2.4]) linear_extrude(1) text("rigidflex", size=7, font="Liberation Sans:style=Bold", halign="center", valign="center");
    }
}

module cell_anchor() {
    // stiff wall the load cell hangs from; gussets on the pull side, clear of the cell
    W = 70; Hw = H + 20;
    difference() {
        union() {
            translate([0, -W/2, 0]) cube([anchor_t, W, Hw]);
            translate([-22, -W/2, 0]) cube([anchor_t + 22 + 40, W, 8]);
            for (s = [-1, 1]) translate([0, s > 0 ? W/2 : -W/2 + 8, 0]) rotate([90, 0, 0])
                linear_extrude(8) polygon([[anchor_t - 0.1, 0], [anchor_t + 40, 0], [anchor_t + 40, 8], [anchor_t - 0.1, Hw - 4]]);
        }
        translate([-1, 0, H]) rotate([0, 90, 0]) cylinder(d=lc_thread + 0.4, h=anchor_t + 2);
        for (p = [[-12, 24], [-12, -24], [anchor_t + 30, 18], [anchor_t + 30, -18]]) translate([p[0], p[1], -1]) cylinder(d=4.5, h=10);
    }
}

module fork_a() {
    // free fork: M8 stud from the load cell at the back (captive nut), pin through the coupon at the front
    w = 2*ear_t + gap; af = lc_thread == 8 ? 13 : lc_thread == 6 ? 10 : 17;
    difference() {
        hull() {
            translate([0, 0, H]) rotate([0, 90, 0]) cylinder(d=24, h=16);
            translate([22, -w/2, H - 11]) cube([24, w, 22]);
        }
        translate([-1, 0, H]) rotate([0, 90, 0]) cylinder(d=lc_thread + 0.3, h=30);
        hull() for (z = [H, H + 20]) translate([6, 0, z]) rotate([0, 90, 0]) rotate([0, 0, 30]) cylinder(d=(af + 0.3)/cos(30), h=7, $fn=6);
        translate([28, -gap/2, H - 13]) cube([30, gap, 26]);
        translate([35, 0, H]) rotate([90, 0, 0]) cylinder(d=pin_d, h=w + 2, center=true);
    }
}

module carriage() {
    // flat sled guided by the two plywood strips; fork at the front, open channel for the screw,
    // nut wall at the back. Prints flat as exported, no supports.
    W = board[1] - 2*rail[0] - 1; w = 2*ear_t + gap; ch = 16; wall = 7;
    difference() {
        union() {
            translate([0, -W/2, 0]) cube([car_len, W, deck]);
            translate([0, -w/2, 0]) cube([28, w, H + 12]);                              // fork
            for (s = [-1, 1]) translate([28, s > 0 ? ch/2 : -ch/2 - wall, 0]) cube([car_len - 28, wall, H + 12]); // channel walls
            translate([car_len - 14, -22, 0]) cube([14, 44, H + 16]);                  // nut wall
            translate([24, -w/2 - 4, 0]) cube([10, w + 8, H + 12]);                    // fork-to-channel web
        }
        translate([-1, -gap/2, deck + 2]) cube([24, gap, H + 12]);                     // coupon slot
        translate([12, 0, H]) rotate([90, 0, 0]) cylinder(d=pin_d, h=w + 2, center=true);
        translate([34, -ch/2, deck]) cube([car_len - 48 + 0.01, ch, H + 20]);          // screw channel
        translate([car_len - 15, 0, H]) rotate([0, 90, 0]) cylinder(d=10.6, h=16);     // brass nut body
        for (a = [45:90:315]) translate([car_len - 15, 8*cos(a), H + 8*sin(a)]) rotate([0, 90, 0]) cylinder(d=2.9, h=16);
    }
}

module motor_end() {
    // vertical plate: 608 bearing for the lead screw (shoulder on the inner side takes the pull),
    // NEMA17 bolted to the inner face in a pocket, slotted so the belt can be tensioned
    W = 64; Ht = zm + 21 + 8;
    difference() {
        union() {
            translate([0, -W/2, 0]) cube([plate_t, W, Ht]);
            translate([-40, -W/2, 0]) cube([40 + plate_t, W, 8]);
            for (s = [-1, 1]) translate([0, s > 0 ? W/2 : -W/2 + 5, 0]) rotate([90, 0, 0])
                linear_extrude(5) polygon([[0.1, 0], [-36, 0], [-36, 8], [0.1, Ht - 12]]);
        }
        translate([2.8, 0, H]) teardrop_x(brg[0], plate_t);                            // bearing pocket from the outside
        translate([-1, 0, H]) teardrop_x(16, plate_t + 2);
        translate([-1, -21.8, zm - 21.8 - 2.5]) cube([6, 43.6, 43.6 + 5]);            // motor pocket (5 mm deep)
        hull() for (dz = [-2.5, 2.5]) translate([-1, 0, zm + dz]) teardrop_x(23, plate_t + 2);  // boss + shaft, slotted
        for (y = [-15.5, 15.5], z = [-15.5, 15.5]) hull() for (dz = [-2.5, 2.5])
            translate([-1, y, zm + z + dz]) rotate([0, 90, 0]) cylinder(d=3.4, h=plate_t + 2);
        for (p = [[-30, 22], [-30, -22], [-12, 22], [-12, -22]]) translate([p[0], p[1], -1]) cylinder(d=4.5, h=10);
    }
}

// ======================= bought parts (for the render) =======================

module hex(af, h) { cylinder(d=af/cos(30), h=h, $fn=6); }
module along_x(x, h) { translate([x, 0, H]) rotate([0, 90, 0]) children(); }
module m6_bolt(len) { hex(10, 4); translate([0, 0, 4]) cylinder(d=6, h=len); }

module load_cell() {
    // S-beam: two slots from opposite sides make the S; the gauged web is in the middle window
    translate([x_cell0, 0, H]) difference() {
        translate([0, -lc_w/2, -lc_t/2]) cube([lc_len, lc_w, lc_t]);
        translate([lc_len*0.22, -lc_w/2 - 1, -lc_t]) cube([3, lc_w - 9, 2*lc_t]);
        translate([lc_len*0.78 - 3, -lc_w/2 + 10, -lc_t]) cube([3, lc_w, 2*lc_t]);
        hull() for (x = [lc_len*0.38, lc_len*0.62]) translate([x, 0, -lc_t]) cylinder(d=lc_w*0.36, h=2*lc_t);
        for (x = [-1, lc_len - 13]) translate([x, 0, 0]) rotate([0, 90, 0]) cylinder(d=lc_thread, h=14);
    }
}
module cell_potting() {   // the sealed strain-gauge web seen through the window
    translate([x_cell0, 0, H - 3]) hull() for (x = [lc_len*0.38, lc_len*0.62]) translate([x, 0, 0]) cylinder(d=lc_w*0.36 - 0.4, h=6);
}
module cell_gland() { translate([x_cell0 + 10, lc_w/2, H]) rotate([-90, 0, 0]) { hex(12, 4); cylinder(d=8, h=10); } }

module anchor_hardware() {
    along_x(x_anchor - 5.5, 0) hex(13, 5.5);                                   // M8 bolt head
    along_x(x_anchor - 1, 0) cylinder(d=8, h=anchor_t + 12);
    along_x(x_anchor + anchor_t, 0) hex(13, 6.5);                              // jam nut
    along_x(x_cell1, 0) hex(13, 6.5);                                          // jam nut
    along_x(x_cell1 - 10, 0) cylinder(d=8, h=6.5 + 10 + 16);                   // stud into the fork
}
module pins() { w = 2*ear_t + gap; for (x = [x_pinA, x_pinB]) translate([x, w/2 + 0.5, H]) rotate([90, 0, 0]) m6_bolt(w + 6); }
module pin_nuts() { w = 2*ear_t + gap; for (x = [x_pinA, x_pinB]) translate([x, -w/2 - 5.5, H]) rotate([90, 0, 0]) hex(10, 5); }

module screw() { along_x(x_end + 28 - 200, 0) cylinder(d=screw_d, h=200); }
module brass_nut() { translate([x_car + car_len, 0, H]) rotate([0, 90, 0]) { cylinder(d=22, h=3.5); translate([0, 0, -12]) cylinder(d=10.2, h=12); } }
module collar()    { along_x(x_end - 8.5, 0) difference() { cylinder(d=14, h=8); translate([0, 0, -1]) cylinder(d=8, h=10); } }
module bearing()   { along_x(x_end + 2.8, 0) difference() { cylinder(d=22, h=7); translate([0, 0, -1]) cylinder(d=8, h=9); } }

module pulley(teeth_d, bore, z) {   // hub towards the plate, toothed band + flanges outside
    translate([x_end + plate_t + 1, 0, z]) rotate([0, 90, 0]) difference() {
        union() {
            cylinder(d=teeth_d > 20 ? 28 : 13, h=7.5);
            translate([0, 0, 7.5]) cylinder(d=teeth_d + 4, h=1);
            translate([0, 0, 8.5]) cylinder(d=teeth_d - 0.8, h=6.5, $fn=teeth_d > 20 ? 60 : 20);
            translate([0, 0, 15]) cylinder(d=teeth_d + 4, h=1);
        }
        translate([0, 0, -1]) cylinder(d=bore, h=20);
    }
}
module belt() {
    translate([x_end + plate_t + 1 + 8.75, 0, 0]) rotate([0, 90, 0]) linear_extrude(6) difference() {
        hull() { translate([-H, 0]) circle(d=p60 + 1.4, $fn=90); translate([-zm, 0]) circle(d=p20 + 1.4, $fn=40); }
        hull() { translate([-H, 0]) circle(d=p60 - 0.8, $fn=90); translate([-zm, 0]) circle(d=p20 - 0.8, $fn=40); }
    }
}
module nema17_body()  { translate([x_end + 5 - 48 + 9, -21.15, zm - 21.15]) cube([30, 42.3, 42.3]); }
module nema17_caps()  {
    for (x = [x_end + 5 - 48, x_end + 5 - 9]) translate([x, 0, zm]) rotate([0, 90, 0]) rotate([0, 0, 45])
        cylinder(d1=58, d2=58, h=9, $fn=4);
}
module nema17_caps_clipped() { intersection() { nema17_caps(); translate([x_end - 60, -21.15, zm - 21.15]) cube([80, 42.3, 42.3]); } }
module nema17_shaft() { translate([x_end + 5, 0, zm]) rotate([0, 90, 0]) { cylinder(d=22, h=2); cylinder(d=5, h=24); } }

module cable(pts, d=5) { for (i = [0:len(pts) - 2]) hull() { translate(pts[i]) sphere(d=d, $fn=16); translate(pts[i + 1]) sphere(d=d, $fn=16); } }
module cables() {
    // load cell -> ebox
    cable([[x_cell0 + 10, lc_w/2 + 10, H], [x_cell0 + 10, 44, H - 6], [x_anchor - 2, 44, 13], [x_box + box[0] + 8, 14, 14], [x_box + box[0], 10, 14]], 4.5);
    // motor -> ebox, along the back strip
    cable([[x_end - 30, 21, zm - 8], [x_end - 36, 40, 40], [x_end - 46, 54, rail[1] + 2.5], [x_car - 8, 54, rail[1] + 2.5],
           [x_car - 24, 54, 2.5], [x_box + box[0] + 14, 54, 2.5], [x_box + box[0] + 6, 30, 12], [x_box + box[0], 26, 14]], 5);
}
module cell_label()      { translate([x_cell0 + lc_len*0.08, -lc_w/2 + 3, H + lc_t/2]) cube([lc_len*0.84, 9, 0.15]); }
module cell_label_text() {
    translate([x_cell0 + lc_len/2, -lc_w/2 + 7.5, H + lc_t/2 + 0.1])
        linear_extrude(0.12) text("S-TYPE  50 kg  2.0 mV/V", size=3.2, font="Liberation Sans:style=Bold", halign="center", valign="center");
}
module button_bezel() { translate([x_box + box[0]*0.72, 0, box[2] + 3]) difference() { cylinder(d=30, h=3); translate([0, 0, -1]) cylinder(d=22, h=5); } }
module button_cap()   { translate([x_box + box[0]*0.72, 0, box[2] + 3]) { cylinder(d=21.5, h=5); translate([0, 0, 5]) scale([1, 1, 0.25]) sphere(d=21.5); } }
module box_screws()   { for (x = [2.4 + 3.5, box[0] - 2.4 - 3.5], y = [-box[1]/2 + 2.4 + 3.5, box[1]/2 - 2.4 - 3.5]) translate([x_box + x, y, box[2] + 3]) cylinder(d=5.5, h=1.8); }

module rails() {
    x0 = x_car - 10;
    for (s = [-1, 1]) translate([x0, s > 0 ? board[1]/2 - rail[0] : -board[1]/2, 0]) cube([x_rail_end - x0, rail[0], rail[1]]);
}
module scale_ticks() {
    // laser-engraved scale on the front strip; the carriage's rear edge is the pointer (1 mm ticks)
    x0 = x_car + car_len;
    for (i = [0:floor(stroke)]) let(l = i % 10 == 0 ? 9 : i % 5 == 0 ? 6 : 3.5)
        translate([x0 + i, -board[1]/2 + 2, rail[1] - 0.2]) cube([0.35, l, 0.25]);
}

module coupon_part(which) { translate([x_coupon, c_t/2, H - c_w/2]) rotate([90, 0, 0]) coupon_geom(which); }
module coupon_geom(which) {
    // simplified dog-bone for the render (the real one is scad/coupons.scad)
    L = c_len; gw = 10; tl = 12; xm = L/2;
    module outline() {
        hull() { square([c_grip, c_w]); translate([c_grip + tl, c_w/2 - gw/2]) square([0.01, gw]); }
        translate([c_grip + tl, c_w/2 - gw/2]) square([L - 2*(c_grip + tl), gw]);
        hull() { translate([L - c_grip, 0]) square([c_grip, c_w]); translate([L - c_grip - tl - 0.01, c_w/2 - gw/2]) square([0.01, gw]); }
    }
    difference() {
        linear_extrude(c_t) intersection() { outline(); if (which == "rigid") square([xm, c_w]); else translate([xm, 0]) square([xm, c_w]); }
        for (x = [c_grip/2, L - c_grip/2]) translate([x, c_w/2, -1]) cylinder(d=6.5, h=c_t + 2);
    }
}

module assembly_component(name) {
    if (name == "board")        translate([0, -board[1]/2, -board[2]]) cube(board);
    if (name == "rails")        rails();
    if (name == "ticks")        scale_ticks();
    if (name == "ebox")         translate([x_box, 0, 0]) ebox();
    if (name == "ebox_lid")     translate([x_box, 0, box[2]]) ebox_lid();
    if (name == "box_screws")   box_screws();
    if (name == "button_bezel") button_bezel();
    if (name == "button_cap")   button_cap();
    if (name == "cell_anchor")  translate([x_anchor, 0, 0]) cell_anchor();
    if (name == "anchor_hw")    anchor_hardware();
    if (name == "load_cell")    load_cell();
    if (name == "cell_potting") cell_potting();
    if (name == "cell_gland")   cell_gland();
    if (name == "cell_label")   cell_label();
    if (name == "cell_label_text") cell_label_text();
    if (name == "cables")       cables();
    if (name == "fork_a")       translate([x_forkA, 0, 0]) fork_a();
    if (name == "coupon_rigid") coupon_part("rigid");
    if (name == "coupon_tpu")   coupon_part("tpu");
    if (name == "pins")         pins();
    if (name == "pin_nuts")     pin_nuts();
    if (name == "carriage")     translate([x_car, 0, 0]) carriage();
    if (name == "brass_nut")    brass_nut();
    if (name == "screw")        screw();
    if (name == "collar")       collar();
    if (name == "bearing")      bearing();
    if (name == "motor_end")    translate([x_end, 0, 0]) motor_end();
    if (name == "pulley60")     pulley(p60, 8, H);
    if (name == "pulley20")     pulley(p20, 5, zm);
    if (name == "belt")         belt();
    if (name == "motor_body")   nema17_body();
    if (name == "motor_caps")   nema17_caps_clipped();
    if (name == "motor_shaft")  nema17_shaft();
}

COMPONENTS = ["board", "rails", "ticks", "ebox", "ebox_lid", "box_screws", "button_bezel", "button_cap",
              "cell_anchor", "anchor_hw", "load_cell", "cell_potting", "cell_gland", "cell_label", "cell_label_text", "cables", "fork_a",
              "coupon_rigid", "coupon_tpu", "pins", "pin_nuts", "carriage", "brass_nut", "screw", "collar",
              "bearing", "motor_end", "pulley60", "pulley20", "belt", "motor_body", "motor_caps", "motor_shaft"];

// printable parts are exported in their print orientation
if (component != "") assembly_component(component);
else if (part == "assembly") for (c = COMPONENTS) assembly_component(c);
else if (part == "ebox") ebox();
else if (part == "ebox_lid") translate([0, 0, 3]) rotate([180, 0, 0]) ebox_lid();
else if (part == "cell_anchor") cell_anchor();
else if (part == "fork_a") translate([0, 0, 12]) rotate([90, 0, 0]) translate([0, 0, -H]) fork_a();
else if (part == "carriage") carriage();
else if (part == "motor_end") motor_end();
