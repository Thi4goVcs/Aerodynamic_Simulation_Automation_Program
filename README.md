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
- Compressible and incompressible flow simulation setups
- Runs simulations for multiple angles of attack in one go
- Extracts Cd, Cl, Cm and side-force coefficients and plots them automatically
- Simulations run in a background thread — the UI stays responsive

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
> `Padrão/Compressivel` and `Padrão/Incompressivel` accordingly.

## Installation

### 1. Install WSL2 and a Linux distro

Open PowerShell **as Administrator** and run:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart when prompted, then finish the Ubuntu first-run setup (create a
username/password inside WSL).

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

## Usage

1. Pick a custom airfoil coordinates file, **or** type a 4-digit NACA code
   (e.g. `0012`).
2. Enter one or more angles of attack, comma-separated (e.g. `0, 2.5, 5, 10`).
3. Choose **Standard Mesh** (pre-tuned for NACA 0012) or **Custom Mesh** (full
   control over every meshing parameter).

   ![Custom mesh parameters](docs/screenshot_custom_mesh.png)

4. Choose **Incompressible** or **Compressible** flow and set the flow
   properties. Toggle "Show advanced parameters" for `nu`, `nut`, etc.

   ![Flow properties, incompressible](docs/screenshot_incompressible.png)

5. Click **Run Simulation**. Progress is shown live; simulations run in the
   background so the window stays responsive.

   ![Simulation progress](docs/screenshot_progress.png)

6. Results are written to `Resultados/resultados.txt`, and plots + an Excel
   spreadsheet are saved to `graficos/`.

   ![Simulation finished](docs/screenshot_complete.png)

See [MANUAL.md](MANUAL.md) for a detailed walkthrough of every screen and
parameter, plus troubleshooting tips.

## Project structure

```
Run.py                  GUI application (entry point)
functions.py             Airfoil geometry, mesh generation, post-processing
Padrão/Incompressivel/   Base OpenFOAM case template (incompressible)
Padrão/Compressivel/     Base OpenFOAM case template (compressible)
Simulador/                Generated per-angle simulation cases (runtime)
Resultados/               Aggregated results (resultados.txt) (runtime)
graficos/                  Generated plots + data.xlsx (runtime)
requirements.txt           Python dependencies
run.bat                    Windows launcher
```

## Troubleshooting

- **"WSL executable not found"** — Install WSL2 (see step 1) and make sure
  `wsl` works from a plain Windows terminal.
- **Simulation fails for every angle** — Run `wsl bash -c "blockMesh -help"`
  manually to confirm OpenFOAM is on the `PATH` inside WSL (step 2).
- **`ZeroDivisionError` / mesh generation error on Custom Mesh** — one of the
  mesh parameters is zero or otherwise invalid; the app now shows which angle
  failed instead of crashing. Adjust the parameter and try again.
- **Excel file locked / results not updating** — close `graficos/data.xlsx`
  before re-running a simulation; the app rewrites it on every run.

## License

Distributed under the MIT License — see [LICENSE](LICENSE) for details, and
[3_LICENSE.txt](3_LICENSE.txt) for the academic-use citation note.

## Contact

For questions, open an issue on GitHub or contact the author at
180078330@aluno.unb.br.
