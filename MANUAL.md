# User Manual — Aerodynamic Simulation Automation Program

This manual walks through every screen of the app. For installation
instructions, see [README.md](README.md).

## Overview

The app interacts with OpenFOAM to run aerodynamic simulations of NACA
4-digit airfoils, without requiring you to hand-edit any OpenFOAM case files.
It is aimed at aeromodeling teams, airfoil studies, and anyone getting
started with OpenFOAM who wants a guided workflow.

## 1. Main screen

![Main screen](docs/screenshot_main_menu.png)

| Field | Description |
|---|---|
| Airfoil coordinates file | Optional. Browse to a `.dat` file with airfoil `x y` coordinate pairs, one per line. If set, this overrides the NACA code below. |
| NACA 4-digit profile | Used when no custom file is selected. Must be exactly 4 digits, e.g. `0012`. |
| Angle(s) of attack | One or more angles in degrees, comma-separated, e.g. `0, 2.5, 5, 10`. |

Then pick a mesh type:

- **Standard Mesh** — a pre-tuned mesh validated for the NACA 0012 profile.
  Fastest way to get a result.
- **Custom Mesh** — exposes every mesh-generation parameter (see below).
  Recommended for anything other than the standard case, especially
  compressible/high-speed flows.

## 2. Custom Mesh Parameters

![Custom mesh parameters](docs/screenshot_custom_mesh.png)

Only shown if you picked **Custom Mesh**. Parameters are grouped as:

- **Geometry** — distance to inlet/outlet (in chord lengths), and where the
  mesh's separating point sits relative to the leading edge.
- **Cell sizes** — target cell size at the leading edge, trailing edge, and
  in the middle of the airfoil.
- **Boundary layer** — boundary layer thickness, first-layer thickness, and
  the expansion ratio between layers.
- **Max cell sizes** — the largest allowed cell size at the inlet, outlet,
  and their junction.
- **Mesh density** — number of divisions along the boundary layer, the tail,
  the leading edge, and the trailing edge.

The tail angle is automatically adjusted to match the angle of attack so the
wake is captured correctly downstream of the airfoil.

Click **Create Mesh** to continue.

## 3. Simulation type

![Choose the simulation type](docs/screenshot_choose_type.png)

- **Incompressible** — for flows where density changes are negligible
  (most low-speed aerodynamics cases).
- **Compressible** — for flows with significant density variation
  (high-speed / transonic cases).

## 4. Flow properties

### Incompressible

![Incompressible flow properties](docs/screenshot_incompressible.png)

| Field | Default | Notes |
|---|---|---|
| Flow velocity (m/s) | — | Required |
| nu | `1e-5` | Kinematic viscosity |
| P | `0.0` | Reference pressure |
| Nut | `0.14` | Recommended: same order as `nu` |
| Nutilda | `0.14` | Recommended: ~4× `nu` |

### Compressible

![Compressible flow properties](docs/screenshot_compressible.png)

| Field | Default | Notes |
|---|---|---|
| Flow velocity (m/s) | — | Required |
| P (pressure) | `1e5` | Pa |
| T (temperature K) | `298` | Kelvin |
| Alphat | `0.1` | |
| k | `0.1` | Turbulent kinetic energy |
| Nut | `0.1` | |
| Omega | `0.1` | |
| Nu | `1e-6` | Kinematic viscosity |

Toggle **Show advanced parameters** to reveal the secondary fields; they
reset to their defaults automatically when hidden again.

Click **Run Simulation** to start. The app switches to a progress screen and
runs each angle sequentially inside WSL, in a background thread so the
window stays responsive.

![Simulation progress](docs/screenshot_progress.png)

When it finishes, you'll see a summary with a button to open the results
folder directly.

![Simulation finished](docs/screenshot_complete.png)

## 5. Results

- `Resultados/resultados.txt` — one row per angle with `Time, Cd, Cd(f),
  Cd(r), Cl, Cl(f), Cl(r), CmPitch, CmRoll, CmYaw, Cs, Cs(f), Cs(r)`. If a
  simulation failed for a given angle, its row is filled with `nan` instead
  of corrupting the file.
- `graficos/data.xlsx` — the same data as a spreadsheet.
- `graficos/*.png` — one plot per coefficient, coefficient vs. angle of
  attack.

## Error messages

- **"Please enter a valid 4-digit NACA code"** — the NACA field must contain
  exactly 4 digits.
- **"Please enter valid angles separated by commas"** — check for stray
  characters in the angle(s) field; only numbers and commas are allowed.
- **Mesh Generation Error** — usually means a custom mesh parameter is zero
  or otherwise invalid (e.g. division by zero in the grading calculation).
  Check the message for which angle failed and adjust the parameter.
- **"WSL executable not found"** — WSL isn't installed or not on `PATH`; see
  [README.md](README.md) for setup steps.
- **Simulation Finished with Errors** — one or more angles failed inside
  WSL. Check the console/terminal output the app was launched from for the
  underlying OpenFOAM error.

## Tips

- When specifying multiple angles, expect the total run time to scale with
  the number of angles — each is solved as an independent case.
- Close `graficos/data.xlsx` before starting a new simulation; the app
  rewrites it on every run and Excel keeps the file locked while open.
- To change the number of solver iterations, edit `endTime` or `deltaT` in
  the relevant case's `system/controlDict` under `Padrão/Incompressivel` or
  `Padrão/Compressivel`.

## Citation

This program was developed as part of the author's undergraduate thesis
(TCC) at the University of Brasília (UnB). If you use it in academic work,
please cite the original thesis — see [3_LICENSE.txt](3_LICENSE.txt) for the
citation requirement attached to academic use.
