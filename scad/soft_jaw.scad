// Magnetic soft jaw for a bench vise: rigid plate + TPU face, in one print
// rigidflex by garage78 · CC BY 4.0
//
// Holds painted, chromed or 3D-printed parts without marking them.
// Print it as modelled (back face on the plate): the TPU face is printed on top of the
// rigid plate, which is exactly the "TPU on rigid" lap bond measured in series B.
// The rigid face has keying grooves that the TPU fills, so it holds mechanically as well.
// Press 10 x 3 mm disc magnets into the pockets on the back after printing.

part = "both";          // ["both", "rigid", "flex"]
jaw_w   = 100;          // mm, vise jaw width
jaw_h   = 25;           // mm, jaw height
plate_t = 4;            // mm, rigid plate
pad_t   = 2.4;          // mm, TPU pad above the plate
face    = "ribbed";     // ["smooth", "ribbed"]
groove_pitch = 6;       // mm, keying grooves under the TPU
groove_w = 2;  groove_d = 1.4;
magnet_d = 10.2; magnet_t = 3.1; magnets = 3;
$fn = 48;

module grooves() {
    for (y = [groove_pitch/2 : groove_pitch : jaw_h - groove_pitch/2 + 0.01])
        translate([3, y - groove_w/2, plate_t - groove_d]) cube([jaw_w - 6, groove_w, groove_d + 0.01]);
}
module rigid() {
    difference() {
        cube([jaw_w, jaw_h, plate_t]);
        grooves();
        for (i = [0:magnets-1]) translate([jaw_w*(i + 0.5)/magnets, jaw_h/2, -0.01]) cylinder(d=magnet_d, h=magnet_t);
    }
}
module flex() {
    union() {
        translate([1, 1, plate_t]) cube([jaw_w - 2, jaw_h - 2, pad_t - (face == "ribbed" ? 0.8 : 0)]);
        if (face == "ribbed")
            for (y = [2.5 : 2.5 : jaw_h - 2.5]) translate([1, y - 0.6, plate_t + pad_t - 0.8 - 0.01]) cube([jaw_w - 2, 1.2, 0.81]);
        intersection() { grooves(); translate([0, 0, 0]) cube([jaw_w, jaw_h, plate_t + 0.01]); }  // TPU keys in the grooves
    }
}
if (part != "flex")  color("SteelBlue") rigid();
if (part != "rigid") color("Orange")    flex();
