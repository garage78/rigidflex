// Parametric rigid + TPU grommet / cable pass-through for the Snapmaker U1
// Rigid ring (clips into the panel hole) + TPU membrane (seals around the cable).
// three = true: the sealing lip is printed in a softer TPU (e.g. 85A) on a 95A membrane: three materials, one part.
// garage78 · CC BY 4.0

part = "both";          // ["both", "rigid", "flex", "soft"]
three         = false;  // soft sealing lip in a third material
panel_hole_d  = 25;     // mm, hole in the panel
panel_thick   = 1.2;    // mm, sheet thickness (classic-car bulkhead steel ≈ 1.2)
cable_d       = 8;      // mm, cable or rod to seal around (0 = blanking plug)
flange        = 4;      // mm, flange width beyond the hole
wall          = 1.6;    // mm, rigid ring wall
membrane      = 1.2;    // mm, TPU membrane thickness
cone          = 3;      // mm, how far the membrane lip rises around the cable
$fn = 96;

R  = panel_hole_d/2;
module rigid() {
    difference() {
        union() {
            cylinder(r=R+flange, h=1.6);                         // outer flange
            cylinder(r=R-0.15, h=1.6+panel_thick);               // barrel through the hole
            translate([0,0,1.6+panel_thick]) cylinder(r1=R+0.6, r2=R-0.15, h=1.2); // snap lip
        }
        translate([0,0,-1]) cylinder(r=R-0.15-wall, h=10);
        for (a=[0:90:270]) rotate(a) translate([-0.6, 0, 1.6]) cube([1.2, R+2, 5]); // slots so the lip flexes
    }
}
module lip() { cylinder(r1=cable_d/2+1.4, r2=cable_d/2+0.6, h=membrane+cone); }
module seal_hole() { if (cable_d > 0) translate([0,0,-1]) cylinder(r=cable_d/2*0.85, h=20); } // 15 % interference
module flex() {
    difference() {
        union() {
            cylinder(r=R-0.15-wall+0.01, h=membrane);            // membrane fused to the ring's inner wall
            if (cable_d > 0 && !three) lip();
        }
        seal_hole();
    }
}
module soft() {   // three-material version: the lip, printed on top of the membrane
    if (cable_d > 0) difference() { lip(); translate([0,0,-1]) cylinder(r=R, h=membrane+1); seal_hole(); }
}
if (part == "both" || part == "rigid") color("SteelBlue") rigid();
if (part == "both" || part == "flex")  color("Orange")    flex();
if ((part == "both" || part == "soft") && three) color("Gold") soft();
