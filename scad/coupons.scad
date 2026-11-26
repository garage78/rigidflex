// Rigid + TPU bond-test coupons for the Snapmaker U1
// rigidflex by garage78 · CC BY 4.0
//
// Dog-bone shape (wide grips, narrow gauge section) so the coupon fails at the
// joint, not at the pin hole. The 10 x 3 mm gauge section keeps peak forces
// within the range of a 50 kg load cell (see scad/pull_rig.scad).
//
// Export each body separately (part = "rigid" / "flex"); `rigidflex kit coupon`
// does this and packs both into one two-material 3MF.
//
// Coupon A: in-plane butt joint (rigid and TPU side by side in the same layers)
// Coupon B: lap joint (TPU printed on the rigid material, or the reverse)
// Graded A (buffer > 0): rigid | buffer band of a stiffer TPU | soft TPU, three materials in one part
// All print flat, with no supports.

/* [Which coupon] */
coupon = "A";            // ["A", "B"]
part   = "both";         // ["both", "rigid", "buffer", "flex"]

/* [Shape] */
width      = 10;         // mm, gauge-section width
grip_w     = 20;         // mm, grip width
thickness  = 3;          // mm
grip_len   = 25;         // mm
taper_len  = 12;         // mm, grip-to-gauge transition
gauge_len  = 50;         // mm, narrow section with the joint in the middle
hole_d     = 6.5;        // mm, M6 pin

/* [Coupon A: butt joint] */
joint       = "dovetail"; // ["flat", "sawtooth", "dovetail"]
tooth_pitch = 2.5;        // mm
tooth_depth = 2.5;        // mm
buffer      = 0;          // mm, graded joint: band of intermediate TPU between rigid and soft TPU (0 = none)

/* [Coupon B: lap joint] */
overlap     = 20;         // mm (must be shorter than gauge_len)
rigid_below = true;       // true: TPU printed on rigid; false: rigid printed on TPU

$fn = 48;
L  = 2*grip_len + 2*taper_len + gauge_len;
xm = L/2;                // joint centre
yc = grip_w/2;           // centre line

// ---------- outline ----------
module outline() {
    hull() { square([grip_len, grip_w]); translate([grip_len + taper_len, yc - width/2]) square([0.01, width]); }
    translate([grip_len + taper_len, yc - width/2]) square([gauge_len, width]);
    hull() { translate([L - grip_len, 0]) square([grip_len, grip_w]); translate([L - grip_len - taper_len - 0.01, yc - width/2]) square([0.01, width]); }
}
module holes() {
    for (x = [grip_len/2, L - grip_len/2]) translate([x, yc, -1]) cylinder(d=hole_d, h=thickness+2);
}

// ---------- coupon A: everything left of the joint line is rigid ----------
module rigid_side_2d() {
    y0 = yc - width/2;
    n  = round(width / tooth_pitch);
    union() {
        translate([-1, -1]) square([xm - tooth_depth/2 + 1, grip_w + 2]);
        if (joint == "sawtooth")
            for (i = [0:n-1]) translate([xm - tooth_depth/2, y0 + i*tooth_pitch])
                polygon([[0,0],[tooth_depth, tooth_pitch/2],[0, tooth_pitch]]);
        else if (joint == "dovetail")
            for (i = [0:2:n-1]) translate([xm - tooth_depth/2, y0 + i*tooth_pitch])
                polygon([[0, tooth_pitch*0.25],[tooth_depth, 0],[tooth_depth, tooth_pitch],[0, tooth_pitch*0.75]]);
        else // flat
            translate([xm - tooth_depth/2, -1]) square([tooth_depth/2, grip_w + 2]);
    }
}
module A_rigid()  { difference() { linear_extrude(thickness) intersection() { outline(); rigid_side_2d(); } holes(); } }
module A_buffer() { difference() { linear_extrude(thickness) difference() { intersection() { outline(); translate([buffer, 0]) rigid_side_2d(); } rigid_side_2d(); } holes(); } }
module A_flex()   { difference() { linear_extrude(thickness) difference()   { outline(); rigid_side_2d(); translate([buffer, 0]) rigid_side_2d(); } holes(); } }

// ---------- coupon B: lap joint centred on the gauge section ----------
x0 = xm - overlap/2;
h  = thickness/2;
module B_rigid() {
    difference() {
        intersection() {
            linear_extrude(thickness) outline();
            union() {
                translate([-1, -1, -1]) cube([x0 + 1, grip_w + 2, thickness + 2]);
                translate([x0, -1, rigid_below ? 0 : h]) cube([overlap, grip_w + 2, h]);
            }
        }
        holes();
    }
}
module B_flex() {
    difference() {
        intersection() {
            linear_extrude(thickness) outline();
            union() {
                translate([x0 + overlap, -1, -1]) cube([L, grip_w + 2, thickness + 2]);
                translate([x0, -1, rigid_below ? h : 0]) cube([overlap, grip_w + 2, h]);
            }
        }
        holes();
    }
}

if (coupon == "A") {
    if (part == "both" || part == "rigid")  color("SteelBlue") A_rigid();
    if ((part == "both" || part == "buffer") && buffer > 0) color("Gold") A_buffer();
    if (part == "both" || part == "flex")   color("Orange")    A_flex();
} else {
    if (part == "both" || part == "rigid") color("SteelBlue") B_rigid();
    if (part == "both" || part == "flex")  color("Orange")    B_flex();
}
