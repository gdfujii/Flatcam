# FlatCAM 8.5 — Python 3.14 update: change log and double-sided board guide

This version of FlatCAM 8.5 runs on Python 3.14 and current libraries. It
adds a cutting tool library and several G-code changes for desktop GRBL
machines such as the Genmitsu Cubiko.

- [Change log](#change-log)
- [Making a double-sided board](#making-a-double-sided-board)
- [Checking the G-code before cutting](#checking-the-g-code-before-cutting)

---

## Change log

### Running FlatCAM

- **Python 3.14**, with PyQt6, Shapely 2, NumPy 2, Matplotlib 3.8+ and
  svg.path 4+. PyQt4 and pywin32 are no longer needed, and SciPy has been
  dropped because nothing used it.
- Install the requirements with `pip install -r requirements.txt` and start
  the program with `python FlatCAM.py`.
- **Restart FlatCAM after updating its code.** A window that was already
  open keeps running the code it started with.
- Errors inside the program are printed to the console and FlatCAM keeps
  running. Before, they closed the program.

### New: the Tool tab is a cutting tool library

The **Tool** tab lists the end mills, V-bits and drill bits you have, and
assigns them to operations. All values are in millimetres and converted
automatically for inch projects.

| Column | Meaning |
|---|---|
| Dia. | Cutter diameter. For a V-bit, the **tip** diameter. |
| Angle | V-bit included angle (V-bits only). |
| Feed | Speed across the board (not used by drill bits). |
| Plunge | Speed moving down into the material. Drill bits drill at this speed. |
| Spindle | Spindle speed in RPM, written as `M03 S…`. **Set it.** A bare `M03` can leave a GRBL spindle stopped. |
| Depth/pass | Maximum depth per pass for cuts deeper than this (board outline). |

**Operations** section:

- **Isolation routing:** the end mill or V-bit used, and its cut depth.
  For a V-bit the cut width depends on depth, and is shown as "Cut width".
- **Board outline:** the end mill used, and its cut depth (board thickness
  plus a little).
- **Drilling:** when "Drill bits above" is ticked, each hole is drilled
  with the closest drill bit in the list, changing bits as needed. Hole
  sizes with no bit within 0.1 mm show in red on the Excellon object and
  produce a warning.
- Choosing **"(object settings)"** for an operation goes back to the old
  behaviour, where the tool is set on each Gerber or Excellon object.

**End of every job** section:

- **Lift to height** (default 15 mm, never lower than the travel height),
  then the spindle stops.
- **Then return to X0 Y0** (default on).

Depths and heights are typed in and take effect when you press Enter or
leave the field. Either `0.06` or `-0.06` means 0.06 mm below the copper.

**Objects you already created keep the settings they were made with.**
After changing the Tool tab, delete and regenerate the isolation geometry,
cutout and CNC jobs.

### New: G-code changes

- **Separate plunge feed.** Each plunge is now
  `F<plunge>` → `G01 Z<depth>` → `F<feed>`. Geometry objects have a new
  "Plunge rate" field; empty means plunge at the feed rate.
- **Safe job end.** Every job ends with `G00 Z<end height>` → `M05` →
  `G00 X0 Y0` (or no return). Before, jobs returned to X0 Y0 only 1–2 mm
  above the board.
- **Rapid drill retract.** Each hole is `G01 Z<depth>` → `G00 Z<travel>`.
  The slow `G01 Z0` climb out of every hole is gone.
- **Drilling with tool changes.** Each drill bit is a tool (`T1`, `T2`, …
  smallest first) with `M6` and an `M0` pause. Tool change is turned on
  automatically when a job needs more than one bit.

### New: drill files

- **Edit → Join Excellon** joins the drill files selected in the Project
  list (Ctrl+click) into one object, "Joined drills". Holes of the same
  size share one tool, tools are numbered by size, and a hole present in
  two files is kept once.
- **File → Export Excellon…** saves an Excellon object as a `.drl` file,
  holes grouped by tool.
- **File → Open G-Code** recognises an Excellon drill file and opens it as
  Excellon. Before, it produced an empty, invisible CNC job.

### New: screen

- **Scroll bars** on the plot pan across everything that is drawn.
- Tools from the **Tool** menu (Double-Sided PCB, Measurement) and
  **Edit → Object Transformation** open in their own tab, named after the
  tool.
- Editing the tool table keeps the row you edited in view.

### Fixes

- Toolpaths are offset by the tool radius (checked down to the G-code).
  Tests now cover isolation, multi-pass isolation, board cutout, hole
  milling and painting.
- Joining drill files used each file's own tool numbers, so a `T1` of
  0.016″ from one file and a `T1` of 0.015″ from another were mixed up.
- `geocutout` (shell) left bridges twice the requested gap size.
- An empty object stopped "zoom to fit" (key 1) from working.
- SVG import lost the closing edge of closed shapes.
- Checkboxes that enable optional fields (for example "Tool change Z")
  had no effect.
- Paths joined during toolpath optimisation could take a segment from the
  wrong side.

### Settings carried over

- Tools saved before this version get a Plunge equal to their Feed, so
  their G-code is unchanged until you edit them. **Lower the Plunge of
  end mills and V-bits** (around 60 mm/min).
- Your existing defaults (`%APPDATA%\FlatCAM\defaults.json`) are kept.

---

## Making a double-sided board

This example uses the Genmitsu Cubiko and DesignSpark exports, but the
process is the same for other machines.

### Before you start

**Export from your PCB program, all as seen from the top (not
mirrored):**

- top copper Gerber
- bottom copper Gerber
- the drill files (plated and unplated)

A bottom layer exported "as seen from the bottom" (mirrored) will not line
up with the drill files. If the holes don't sit on the bottom pads when
both are opened, export the bottom layer again without mirroring. Also
delete drill files from older exports.

**Have ready:**

- a blank larger than the board, with room for alignment pins along two
  opposite edges
- alignment pins (dowels) and a drill bit or end mill of the same size

### 1. Set up the Tool tab

1. Check every tool you will use: diameter, **Feed**, **Plunge** and
   **Spindle**.
2. Add a drill bit the size of your alignment pins, for example
   "Drill 3.0mm".
3. Under **Operations**:
   - Isolation routing: your V-bit, depth `0.06` (1 oz copper)
   - Board outline: your end mill, depth = board thickness + 0.2 mm,
     for example `1.8`
   - Drilling: tick "Drill bits above", depth `1.8`
4. Under **End of every job**: lift height `15`, return to X0 Y0 as
   preferred.
5. In **Options → Geometry**, set **Travel Z** to `2`. Do the same under
   **Options → Excellon**.

### 2. Open the files

1. **File → Open Gerber**: top copper and bottom copper.
2. **File → Open Excellon**: each drill file.
3. Select the drill files in the Project list (Ctrl+click), then choose
   **Edit → Join Excellon**. Use "Joined drills" for drilling. You can also
   save it with **File → Export Excellon…**.
4. Check that the drill holes (small red circles) sit on the pads. If they
   don't, see "Before you start".

### 3. Mark the flip line

The board is turned over **left to right** for the second side, around a
vertical line through the middle of the board. A bounding box of the board
marks that line for the Double-Sided tool.

1. Select the top copper Gerber. On its Selected tab, under **Bounding
   Box**, leave the margin at `0` and click **Generate Geometry**. This
   creates "…_bbox", a rectangle around the board.
2. Alternatively, use a point on the line: X = (left edge + right edge) /
   2. For "Axis - Bottom.gbr", X runs from 0 to 97.282 mm, so the point is
   **(48.641, 0)**.

### 4. Make the alignment holes

1. Choose **Tool → Double-Sided PCB Tool**.
2. Fill in the form:
   - Mirror Axis: **Y** (flips left to right)
   - Axis Location: **Box**, and choose the "…_bbox" object. (Or **Point**
     with the point from step 3.)
   - Alignment Holes: two holes **to the left of the board**, for example
     `(-5, 5), (-5, 28)`
   - Drill diam.: your pin diameter, for example `3.0`
3. Click **Create Alignment Drill**. "Alignment Drills" has your holes and
   their mirror images on the right of the board.

### 5. Side 1: top, copper facing up

1. Clamp the blank. Set **X0 Y0** at the board's origin and **Z0** on the
   copper.
2. **Alignment holes:** select "Alignment Drills", tick all tools, and
   click **Generate** under Create CNC Job. They must go through the board
   into the spoilboard so the pins can sit in them. If your drilling depth
   is only just through the board, deepen it for this job. Export the
   G-code and run it.
3. **Through holes:** select "Joined drills", tick all tools, generate,
   export and run. At each pause (`M0`), fit the bit the job asks for and
   **set Z0 on the copper again** before resuming.
4. **Top copper:** select the top Gerber and click **Generate Geometry**
   under Isolation Routing. Select the new "…_iso" object, click
   **Generate** for its CNC job, export and run.

**Leave X0 Y0 unchanged from here on.** The pins keep the second side in
register with it.

### 6. Side 2: bottom, board flipped left to right

1. Unclamp the board and turn it over left to right. Fit it onto pins in
   the alignment holes and clamp it.
2. In the Double-Sided PCB Tool (same Mirror Axis and Box or Point as above),
   choose the **bottom copper Gerber** as Bottom Layer and click **Mirror
   Object**. It flips in place on the plot.
3. **Set Z0 on the copper again**, since this is a new surface.
4. **Bottom copper:** isolate the mirrored bottom Gerber, generate its CNC
   job, export and run.

### 7. Board outline

1. On the mirrored bottom Gerber's Selected tab, under **Board cutout**,
   set the margin and gap size, then click **Generate Geometry**. The cutter
   and depth come from the Tool tab, and the cut is made in passes no
   deeper than the end mill's Depth/pass.
2. Select "…_cutout", generate its CNC job, export and run last. The gaps
   hold the board in the blank.

### Why mirror only the bottom

Gerber and drill files are drawn as seen from the top. Side 1 is cut as
seen from the top, so nothing is mirrored. Side 2 is cut with the board
upside down, so its copper must be flipped the same way the board was.
Holes drilled on side 1 go through the board, so they don't need drilling
again.

---

## Checking the G-code before cutting

Open the exported file in a text editor:

| Check | Expect |
|---|---|
| Units | `G21` (mm) near the top |
| Spindle | `M03 S10000` (your RPM), not a bare `M03` |
| Plunges (isolation, outline) | `F<plunge>` / `G01 Z-…` / `F<feed>` |
| Depth | `Z-0.0600` for isolation, `Z-1.8000` for drilling and outline |
| Travel height | `G00 Z2.0000` between cuts |
| Drill holes | `G01 Z-1.8000` followed by `G00 Z2.0000` |
| Drill bit changes | `T1`, `M6`, `M0` per bit, smallest bit first |
| End | `G00 Z15.0000`, then `M05`, then `G00 X0.0000Y0.0000` |

**Notes for GRBL (Cubiko):**

- `(MSG, …)` lines are Mach3 messages that GRBL ignores. A drill job
  pauses at each `M0` without saying which bit to fit, so note the order
  (smallest first).
- Tool changes lift to **Tool change Z** (default 20 mm). Make sure the
  machine has that much Z travel above your Z0, or lower it on the
  Excellon object.
- If cuts get shallower as a job runs, lower the **Plunge** rate: the Z
  motor may be skipping steps when plunging. Also check the board is
  flat.
