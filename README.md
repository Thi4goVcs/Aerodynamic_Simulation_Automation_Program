# Aerodynamic Simulation Automation Program

A desktop app that automates aerodynamic CFD simulations of NACA 4-digit airfoils
using [OpenFOAM](https://www.openfoam.com/), running inside WSL2 on Windows.

It walks you through generating the airfoil geometry, building a block mesh,
running the simulation for one or more angles of attack, and produces the
resulting force/moment coefficients as an Excel spreadsheet and a set of
plots — no manual OpenFOAM case setup required.

This program was developed as part of the author's undergraduate thesis (TCC)
at the University of Brasília (UnB).

![Main screen](docs/screenshot_main_menu.png)

## Features

- Generates NACA 4-digit airfoil coordinates, or imports a custom `.dat` file
- Automatic block mesh generation, with a validated standard mesh (NACA 0012)
  or full manual control over every meshing parameter
- Mesh preview before simulating: a wireframe of the near-field mesh plus
  `checkMesh` quality metrics (non-orthogonality, skewness, aspect ratio),
  with a way to go back and adjust the mesh before committing to a run
- Compressible and incompressible flow simulation setups
- Runs simulations for multiple angles of attack in one go, sequentially or
  in parallel (with a concurrency cap so it doesn't overload the machine)
- Live Cd/Cl convergence plot while a sequential run is in progress
- Extracts Cd, Cl, Cm and side-force coefficients and plots them automatically
- Browse the result plots right inside the app (no need to open the `plots/`
  folder separately)
- Save/load a full setup (airfoil, mesh, flow properties) as a `.json`
  preset, to repeat or share a configuration
- Simulations run in a background thread — the UI stays responsive
- Checks WSL/OpenFOAM are actually installed on startup and flags it on the
  main screen if not, instead of only failing later mid-run

## Requirements

| Component | Version |
|---|---|
| Windows | 10 or 11, with WSL2 enabled |
| WSL distro | Ubuntu 20.04/22.04 (or another distro OpenFOAM supports) |
| OpenFOAM | **v2212** (this exact version — see note below) |
| Python | 3.10+ (Windows side, not inside WSL) |

> **Why OpenFOAM v2212 specifically?** The generated case files declare
> `Version: 2212` and were validated against that release. A different
> OpenFOAM version may still work, but mesh/solver behavior isn't guaranteed
> to match — if you use another version, update the version references in
> `core/Standard/Compressible` and `core/Standard/Incompressible` accordingly.

## Installation

### 1. Install WSL2 and a Linux distro

Open PowerShell **as Administrator** and run:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart when prompted, then finish the Ubuntu first-run setup (create a
username/password inside WSL).

> **Shortcut:** `setup_openfoam.bat` in this repo automates steps 1 and 2 as
> much as they can be automated (it still needs your input for the Windows
> restart, the Ubuntu first-run username/password, and your `sudo` password).
> Run it, follow its prompts, and skip to step 3 once it says OpenFOAM is
> installed.

### 2. Install OpenFOAM v2212 inside WSL

Open your WSL/Ubuntu terminal and run:

```bash
sudo sh -c "wget -O - https://dl.openfoam.org/gpg.key | apt-key add -"
sudo add-apt-repository http://dl.openfoam.org/ubuntu
sudo apt-get update
sudo apt-get install openfoam2212-default
```

Make sure the OpenFOAM environment is sourced automatically in every new
shell (the app calls `wsl bash -c "..."`, which loads your `~/.bashrc`):

```bash
echo "source /opt/openfoam2212/etc/bashrc" >> ~/.bashrc
```

Verify the installation:

```bash
source ~/.bashrc
blockMesh -help
```

If that prints `blockMesh`'s usage instead of a "command not found" error,
OpenFOAM is correctly installed and on the `PATH`.

### 3. Clone this repository (on the Windows side)

```bash
git clone https://github.com/Thi4goVcs/Aerodynamic_Simulation_Automation_Program.git
cd Aerodynamic_Simulation_Automation_Program
```

Keep the project on your Windows filesystem (e.g. `C:\Users\you\...`), **not**
inside the WSL filesystem — the app builds Windows paths and translates them
to `/mnt/c/...` before calling WSL.

### 4. Install Python and dependencies (Windows side)

Install [Python 3.10+](https://www.python.org/downloads/) and make sure
"Add python.exe to PATH" is checked during setup. Then either:

- Double-click **`run.bat`** — it checks for Python/WSL and installs missing
  packages automatically before launching the app, or
- Install manually and run it yourself:

  ```bash
  pip install -r requirements.txt
  python Run.py
  ```

Prefer not to install Python at all? Run **`build_exe.bat`** once (needs
Python only for that one build step) to produce a standalone
**`AeroSimApp.exe`** in the project folder; after that, just double-click the
.exe. Keep it next to `Standard/` — it looks for the case templates and
writes its output relative to its own location, not the folder it's launched
from.

## Usage

1. Pick a custom airfoil coordinates file, **or** type a 4-digit NACA code
   (e.g. `0012`).
2. Enter one or more angles of attack, comma-separated (e.g. `0, 2.5, 5, 10`).
3. Choose **Standard Mesh** (pre-tuned for NACA 0012) or **Custom Mesh** (full
   control over every meshing parameter).

   ![Custom mesh parameters](docs/screenshot_custom_mesh.png)

4. Review the **mesh preview** — a wireframe of the mesh plus `checkMesh`
   quality metrics — before anything is simulated. Go back and adjust the
   mesh if needed, or continue.

   ![Mesh preview](docs/screenshot_mesh_preview.png)

5. Choose **Incompressible** or **Compressible** flow and set the flow
   properties. Toggle "Show advanced parameters" for `nu`, `nut`, etc.

   ![Flow properties, incompressible](docs/screenshot_incompressible.png)

6. Click **Run Simulation**. Progress is shown live; simulations run in the
   background so the window stays responsive.

   ![Simulation progress](docs/screenshot_progress.png)

7. Results are written to `Results/results.txt`, and plots + an Excel
   spreadsheet are saved to `plots/`.

   ![Simulation finished](docs/screenshot_complete.png)

See [MANUAL.md](MANUAL.md) for a detailed walkthrough of every screen and
parameter, plus troubleshooting tips.

## Project structure

```
Run.py                            GUI application (entry point)
run.bat                           Windows launcher
build_exe.bat                     Builds a standalone AeroSimApp.exe
core/                              App internals -- nothing here needs to be
  functions.py                    touched directly to use the app
  Standard/Incompressible/        Base OpenFOAM case template (incompressible)
  Standard/Compressible/          Base OpenFOAM case template (compressible)
Simulations/                      Generated per-angle simulation cases (runtime)
Results/                          Aggregated results (results.txt) (runtime)
plots/                            Generated plots + data.xlsx (runtime)
docs/                              Screenshots used by README.md/MANUAL.md
requirements.txt                  Python dependencies
```

## Troubleshooting

- **"WSL executable not found"** — Install WSL2 (see step 1) and make sure
  `wsl` works from a plain Windows terminal.
- **Simulation fails for every angle** — Run `wsl bash -c "blockMesh -help"`
  manually to confirm OpenFOAM is on the `PATH` inside WSL (step 2).
- **`ZeroDivisionError` / mesh generation error on Custom Mesh** — one of the
  mesh parameters is zero or otherwise invalid; the app now shows which angle
  failed instead of crashing. Adjust the parameter and try again.
- **Excel file locked / results not updating** — close `plots/data.xlsx`
  before re-running a simulation; the app rewrites it on every run.

## License

Distributed under the MIT License — see [LICENSE](LICENSE) for details,
including the academic-use citation requirement.

## Contact

For questions, open an issue on GitHub or contact the author at
180078330@aluno.unb.br.
