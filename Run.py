import os
import sys
import json
import subprocess
import shutil
import threading
import concurrent.futures
import tkinter as tk
from tkinter import messagebox, filedialog

import customtkinter as ctk
from PIL import Image

# When bundled by PyInstaller (--onefile), __file__ resolves inside the
# temporary _MEIPASS extraction dir, not next to the actual .exe -- runtime
# output (coordenadas.dat, Results/, Simulations/, plots/) and the app's own
# internals (core/) must be found next to the .exe instead, so this is the
# base directory the rest of the app should use for those paths.
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.realpath(__file__))

# functions.py and the OpenFOAM case templates live under core/, out of the
# way of what you actually interact with (Run.py, Results/, plots/, ...).
os.chdir(APP_DIR)
sys.path.insert(0, os.path.join(APP_DIR, "core"))
import functions  # type: ignore

# Freestream nut/nuTilda default for the SA turbulence model: turbulent-viscosity
# ratio (nut/nu) of 5, the standard "fully turbulent, low ambient turbulence"
# setting recommended for external-aero SA cases. The old hardcoded default
# (0.14, independent of nu) gave a ratio of ~14,000 at nu=1e-5 -- several
# orders of magnitude too high -- which flooded the whole domain with
# non-physical eddy viscosity and was the main cause of the ~2x-6x drag
# overprediction found during NACA 0012 literature validation.
DEFAULT_NUT_NUTILDA = 5 * 1e-5

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_SUBTITLE = ("Segoe UI", 13)
FONT_SECTION = ("Segoe UI", 15, "bold")
FONT_LABEL = ("Segoe UI", 13)
FONT_BUTTON = ("Segoe UI", 14, "bold")
FONT_HINT = ("Segoe UI", 11)

MUTED_TEXT = ("gray40", "gray60")
RUN_COLOR = "#2fa572"
RUN_HOVER = "#227a55"
WARN_COLOR = "#e0a030"
BACK_COLOR = "#3a3a3a"
BACK_HOVER = "#4a4a4a"

# What each mesh-quality metric means and which direction is better, shown as
# a hover tooltip next to its value -- otherwise the raw numbers (e.g. "Max
# non-orthogonality: 88.32") give no sense of whether that's fine or a
# problem.
MESH_METRIC_HELP = {
    "Cells": "Total number of mesh cells. Just the mesh size, not a quality judgment "
             "by itself -- more cells means more resolution but longer solve times.",
    "Points": "Total number of mesh vertices. Informational only.",
    "Max non-orthogonality": "Lower is better. Angle between the line joining two cell "
                              "centers and the face normal between them. OpenFOAM flags "
                              "faces above 70° as severely non-orthogonal -- keep the "
                              "max comfortably below that for reliable convergence.",
    "Avg non-orthogonality": "Lower is better. Average across the whole mesh; should sit "
                              "well below the max, ideally under ~15-20°.",
    "Max skewness": "Lower is better. How distorted a cell/face is from an ideal shape. "
                     "Roughly: under ~1 is excellent, checkMesh starts flagging cells "
                     "above ~4.",
    "Max aspect ratio": "Not simply lower-is-better: thin, elongated cells are normal and "
                         "expected right at the wall (boundary layer) -- that's intentional. "
                         "A high value is only a concern if it's not explained by the "
                         "boundary layer, or if the solver struggles to converge.",
}

# The two derived plots are the most useful at a glance, so they lead; the
# rest falls back to filename order.
RESULT_PLOT_ORDER = ["polar_Cl_Cd", "efficiency_Cl_Cd", "Cl", "Cd", "CmPitch", "CmRoll", "CmYaw", "Cs"]

CUSTOM_MESH_PARAM_NAMES = [
    "distance_to_inlet", "distance_to_outlet", "cell_size_at_leading_edge",
    "cell_size_at_trailing_edge", "cell_size_in_middle", "separating_point_position",
    "boundary_layer_thickness", "first_layer_thickness", "expansion_ratio",
    "max_cell_size_in_inlet", "max_cell_size_in_outlet", "max_cell_size_in_inlet_and_outlet",
    "num_mesh_on_boundary_layer_1", "num_mesh_on_boundary_layer_2", "num_mesh_at_tail",
    "num_mesh_in_leading", "num_mesh_in_trailing",
]


class _Tooltip:
    """Small hover tooltip anchored under a widget (plain Tk has no built-in one)."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#2b2b2b",
                 foreground="white", relief="solid", borderwidth=1,
                 font=("Segoe UI", 10), wraplength=280, padx=8, pady=6).pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, master):
        self.master = master
        self.naca_var = tk.StringVar()
        self.angle_var = tk.StringVar()
        self.angles = []
        self.simulation_tipo = None
        self.airfoil = "airfoil_NACA"
        self.file1_path = tk.StringVar(value='coordenadas.dat')
        self.mesh_choice = None  # Variável para armazenar a escolha de malha
        self.entries = {}  # Inicializando o dicionário aqui
        self.parallel_var = tk.BooleanVar(value=False)  # sequencial por padrão
        self.env_status = {"checked": False, "wsl_ok": False, "openfoam_ok": False, "detail": ""}
        self.last_validation = None
        self._env_banner = None

        self.master.title("Aerodynamic Simulation Automation Program")
        self.master.geometry("920x720")
        self.master.minsize(780, 560)

        # Todas as telas são construídas dentro deste container
        self.container = ctk.CTkFrame(self.master, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.main_menu()
        threading.Thread(target=self._check_environment_worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Health check: WSL + OpenFOAM present? (runs once, in the background)
    # ------------------------------------------------------------------ #
    def _check_environment_worker(self):
        wsl_ok = False
        openfoam_ok = False
        detail = ""
        try:
            r = subprocess.run(
                ["wsl", "-e", "bash", "-c",
                 "source /usr/lib/openfoam/openfoam2212/etc/bashrc 2>/dev/null; command -v blockMesh"],
                capture_output=True, text=True, timeout=15)
            wsl_ok = True
            openfoam_ok = r.returncode == 0 and bool(r.stdout.strip())
            if not openfoam_ok:
                detail = "WSL is installed, but OpenFOAM (blockMesh) wasn't found in it."
        except FileNotFoundError:
            detail = "WSL executable not found."
        except subprocess.TimeoutExpired:
            detail = "Timed out checking WSL/OpenFOAM."
        except Exception as e:
            detail = f"Couldn't check WSL/OpenFOAM: {e}"
        self.env_status = {"checked": True, "wsl_ok": wsl_ok, "openfoam_ok": openfoam_ok, "detail": detail}
        self.master.after(0, self._refresh_env_banner)

    def _refresh_env_banner(self):
        if self._env_banner is None or not self._env_banner.winfo_exists():
            return
        for w in self._env_banner.winfo_children():
            w.destroy()
        self._populate_env_banner(self._env_banner)

    def _populate_env_banner(self, frame):
        status = self.env_status
        if not status["checked"]:
            ctk.CTkLabel(frame, text="Checking WSL/OpenFOAM installation...",
                         font=FONT_HINT, text_color=MUTED_TEXT).pack(anchor="w")
            return
        if status["wsl_ok"] and status["openfoam_ok"]:
            ctk.CTkLabel(frame, text="✓ WSL + OpenFOAM detected", font=FONT_HINT,
                         text_color=RUN_COLOR).pack(anchor="w")
        else:
            ctk.CTkLabel(frame, wraplength=800, justify="left", font=FONT_HINT, text_color=WARN_COLOR,
                         text=f"⚠ {status['detail'] or 'WSL/OpenFOAM not detected.'} "
                              "See README.md for setup steps -- simulations will fail without it.") \
                .pack(anchor="w")

    # ------------------------------------------------------------------ #
    # Helpers de UI
    # ------------------------------------------------------------------ #
    def clear_frame(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def _header(self, parent, title, subtitle=None):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(24, 10))
        ctk.CTkLabel(header, text=title, font=FONT_TITLE, anchor="w").pack(fill="x")
        if subtitle:
            ctk.CTkLabel(header, text=subtitle, font=FONT_SUBTITLE, anchor="w",
                         text_color=MUTED_TEXT, justify="left").pack(fill="x", pady=(4, 0))
        return header

    def _card(self, parent, **pack_kwargs):
        card = ctk.CTkFrame(parent, corner_radius=12)
        defaults = dict(fill="x", expand=False, padx=30, pady=10)
        defaults.update(pack_kwargs)
        card.pack(**defaults)
        return card

    def _labeled_entry(self, parent, label_text, variable, hint=None):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(wrap, text=label_text, font=FONT_LABEL, anchor="w").pack(fill="x")
        entry = ctk.CTkEntry(wrap, textvariable=variable, font=FONT_LABEL, height=34)
        entry.pack(fill="x", pady=(4, 0))
        if hint:
            ctk.CTkLabel(wrap, text=hint, font=FONT_HINT, anchor="w",
                         text_color=MUTED_TEXT).pack(fill="x", pady=(2, 0))
        return wrap, entry

    def _primary_button(self, parent, text, command, **kwargs):
        opts = dict(font=FONT_BUTTON, height=42, corner_radius=8)
        opts.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _secondary_button(self, parent, text, command, **kwargs):
        opts = dict(font=FONT_BUTTON, height=42, corner_radius=8,
                    fg_color=BACK_COLOR, hover_color=BACK_HOVER)
        opts.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _add_save_preset_button(self, parent):
        self._secondary_button(parent, "Save Preset...", self.save_preset, width=180) \
            .pack(anchor="w", padx=30, pady=(0, 10))

    def _add_parallel_toggle(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=30, pady=(4, 10))
        ctk.CTkSwitch(wrap, text="Run angles in parallel", font=FONT_LABEL,
                      variable=self.parallel_var, onvalue=True, offvalue=False).pack(anchor="w")
        ctk.CTkLabel(wrap, font=FONT_HINT, text_color=MUTED_TEXT, anchor="w", justify="left",
                     text="Faster with multiple angles, but each angle already runs its own 2-process\n"
                          "OpenFOAM solve, so running several at once uses much more CPU/RAM. Leave\n"
                          "this off on a modest machine.") \
            .pack(anchor="w", pady=(2, 0))
        return wrap

    def _nav_bar(self, parent, back_command, next_text, next_command,
                 next_color=None, next_hover=None):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=30, pady=20, side="bottom")
        self._secondary_button(bar, "← Back", back_command, width=140).pack(side="left")
        kwargs = {}
        if next_color:
            kwargs["fg_color"] = next_color
        if next_hover:
            kwargs["hover_color"] = next_hover
        self._primary_button(bar, next_text, next_command, width=200, **kwargs).pack(side="right")
        return bar

    # ------------------------------------------------------------------ #
    # Tela principal
    # ------------------------------------------------------------------ #
    def main_menu(self):
        self.clear_frame()
        self._header(self.container, "Aerodynamic Simulation Automation Program",
                     "Define the airfoil geometry and the angles of attack to study.")

        self._env_banner = ctk.CTkFrame(self.container, fg_color="transparent")
        self._env_banner.pack(fill="x", padx=30, pady=(0, 6))
        self._populate_env_banner(self._env_banner)

        shortcuts_row = ctk.CTkFrame(self.container, fg_color="transparent")
        shortcuts_row.pack(fill="x", padx=30, pady=(0, 10))
        self._secondary_button(shortcuts_row, "Load Preset...", self.load_preset, width=160) \
            .pack(side="left")
        plots_dir = os.path.join(APP_DIR, "plots")
        if os.path.isdir(plots_dir) and any(f.lower().endswith(".png") for f in os.listdir(plots_dir)):
            self._secondary_button(shortcuts_row, "View Last Results", self.results_viewer_screen, width=200) \
                .pack(side="right")

        card = self._card(self.container)

        ctk.CTkLabel(card, text="Airfoil coordinates file", font=FONT_SECTION, anchor="w") \
            .pack(fill="x", padx=20, pady=(20, 4))
        file_row = ctk.CTkFrame(card, fg_color="transparent")
        file_row.pack(fill="x", padx=20)
        ctk.CTkEntry(file_row, textvariable=self.file1_path, font=FONT_LABEL, height=34) \
            .pack(side="left", fill="x", expand=True)
        ctk.CTkButton(file_row, text="Browse...", width=110, height=34,
                      command=self.browse_file1).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(card, text="Optional: pick a custom .dat file with airfoil x/y coordinates.",
                     font=FONT_HINT, anchor="w", text_color=MUTED_TEXT) \
            .pack(fill="x", padx=20, pady=(4, 16))

        naca_wrap, self.naca_entry = self._labeled_entry(
            card, "NACA 4-digit profile (used if no file is selected)", self.naca_var,
            hint="e.g. 0012")
        naca_wrap.pack(fill="x", padx=20, pady=(0, 16))

        angle_wrap, self.angle_entry = self._labeled_entry(
            card, "Angle(s) of attack", self.angle_var,
            hint="Comma-separated, in degrees — e.g. 0, 2.5, 5, 10")
        angle_wrap.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(self.container, text="Mesh generation", font=FONT_SECTION, anchor="w") \
            .pack(fill="x", padx=30, pady=(10, 8))

        mesh_row = ctk.CTkFrame(self.container, fg_color="transparent")
        mesh_row.pack(fill="x", padx=30, pady=(0, 30))
        mesh_row.grid_columnconfigure((0, 1), weight=1)

        std_card = ctk.CTkFrame(mesh_row, corner_radius=12)
        std_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(std_card, text="Standard Mesh", font=FONT_SECTION).pack(pady=(16, 4))
        ctk.CTkLabel(std_card, justify="center", text_color=MUTED_TEXT, font=FONT_HINT,
                     text="Pre-tuned mesh, validated for the\nNACA 0012 profile. Fastest way to start.") \
            .pack(padx=16)
        self._primary_button(std_card, "Use Standard Mesh", self.select_standard_mesh) \
            .pack(pady=16, padx=16, fill="x")

        custom_card = ctk.CTkFrame(mesh_row, corner_radius=12)
        custom_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(custom_card, text="Custom Mesh", font=FONT_SECTION).pack(pady=(16, 4))
        ctk.CTkLabel(custom_card, justify="center", text_color=MUTED_TEXT, font=FONT_HINT,
                     text="Fine-tune every mesh parameter yourself.\nRecommended for advanced/compressible cases.") \
            .pack(padx=16)
        self._primary_button(custom_card, "Use Custom Mesh", self.select_custom_mesh) \
            .pack(pady=16, padx=16, fill="x")

    def browse_file1(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        self.file1_path.set(path)
        self.airfoil = 'airfoil_custom'

    def select_standard_mesh(self):
        self.mesh_choice = "standard_mesh"
        if not self.process_angles():
            return
        if not self.search_airfoil():
            return
        self.clear_frame()
        self.mesh_preview_screen()

    # ------------------------------------------------------------------ #
    # Tela de malha customizada
    # ------------------------------------------------------------------ #
    def select_custom_mesh(self):
        self.mesh_choice = "custom_mesh"
        if not self.process_angles():
            return
        if not self.search_airfoil():
            return
        self.clear_frame()

        self._header(self.container, "Custom Mesh Parameters",
                     "Adjust the block-mesh generation settings, then create the mesh.")

        self.entries = {}  # Garantindo que self.entries é um dicionário vazio antes de começar

        # Os DoubleVars só são (re)criados com valor padrão na primeira vez --
        # assim, se o usuário voltar aqui a partir da pré-visualização da
        # malha para ajustar um parâmetro, os valores já digitados persistem.
        if not hasattr(self, "distance_to_inlet"):
            self.distance_to_inlet = tk.DoubleVar(value=12)
            self.distance_to_outlet = tk.DoubleVar(value=12)
            self.cell_size_at_leading_edge = tk.DoubleVar(value=0.01)
            self.cell_size_at_trailing_edge = tk.DoubleVar(value=0.02)
            self.cell_size_in_middle = tk.DoubleVar(value=0.035)
            self.separating_point_position = tk.DoubleVar(value=0.4)
            self.boundary_layer_thickness = tk.DoubleVar(value=0.2)
            self.first_layer_thickness = tk.DoubleVar(value=0.000004)
            self.expansion_ratio = tk.DoubleVar(value=1.2)
            self.max_cell_size_in_inlet = tk.DoubleVar(value=1)
            self.max_cell_size_in_outlet = tk.DoubleVar(value=1)
            self.max_cell_size_in_inlet_and_outlet = tk.DoubleVar(value=1)
            self.num_mesh_on_boundary_layer_1 = tk.DoubleVar(value=80)
            self.num_mesh_on_boundary_layer_2 = tk.DoubleVar(value=100)
            self.num_mesh_at_tail = tk.DoubleVar(value=160)
            self.num_mesh_in_leading = tk.DoubleVar(value=160)
            self.num_mesh_in_trailing = tk.DoubleVar(value=160)

        groups = [
            ("Geometry", [
                ("Distance to inlet (x chord length)", self.distance_to_inlet),
                ("Distance to outlet (x chord length)", self.distance_to_outlet),
                ("Separating point position (from leading point)", self.separating_point_position),
            ]),
            ("Cell sizes", [
                ("Cell size at leading edge", self.cell_size_at_leading_edge),
                ("Cell size at trailing edge", self.cell_size_at_trailing_edge),
                ("Cell size in middle", self.cell_size_in_middle),
            ]),
            ("Boundary layer", [
                ("Boundary layer thickness", self.boundary_layer_thickness),
                ("First layer thickness", self.first_layer_thickness),
                ("Expansion ratio", self.expansion_ratio),
            ]),
            ("Max cell sizes", [
                ("Max cell size in inlet", self.max_cell_size_in_inlet),
                ("Max cell size in outlet", self.max_cell_size_in_outlet),
                ("Max cell size in inlet & outlet", self.max_cell_size_in_inlet_and_outlet),
            ]),
            ("Mesh density", [
                ("Number of mesh on boundary layer 1", self.num_mesh_on_boundary_layer_1),
                ("Number of mesh out boundary layer 2", self.num_mesh_on_boundary_layer_2),
                ("Number of mesh at tail", self.num_mesh_at_tail),
                ("Number of mesh in leading", self.num_mesh_in_leading),
                ("Number of mesh in trailing", self.num_mesh_in_trailing),
            ]),
        ]

        scroll = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        for title, fields in groups:
            card = ctk.CTkFrame(scroll, corner_radius=12)
            card.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(card, text=title, font=FONT_SECTION, anchor="w") \
                .pack(fill="x", padx=16, pady=(14, 6))
            grid = ctk.CTkFrame(card, fg_color="transparent")
            grid.pack(fill="x", padx=16, pady=(0, 16))
            grid.grid_columnconfigure((0, 1), weight=1)
            for idx, (label, var) in enumerate(fields):
                wrap, entry = self._labeled_entry(grid, label, var)
                wrap.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=6, pady=6)
                self.entries[label] = entry  # Armazenando referências das entradas no dicionário

        self._nav_bar(self.container, self.main_menu, "Create Mesh →", self.mesh_preview_screen)

    # ------------------------------------------------------------------ #
    # Tipo de simulação
    # ------------------------------------------------------------------ #
    def choose_simulation_type(self):
        self.clear_frame()
        self._header(self.container, "Choose the Simulation Type",
                     "Pick the flow regime that matches your case.")

        row = ctk.CTkFrame(self.container, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=30, pady=10)
        row.grid_columnconfigure((0, 1), weight=1)

        incomp_card = ctk.CTkFrame(row, corner_radius=12)
        incomp_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(incomp_card, text="Incompressible", font=FONT_SECTION).pack(pady=(20, 6))
        ctk.CTkLabel(incomp_card, justify="center", font=FONT_HINT, text_color=MUTED_TEXT,
                     text="For flows where density changes are negligible —\n"
                          "typical in most low-speed aerodynamics cases.") \
            .pack(padx=16)
        self._primary_button(incomp_card, "Select Incompressible",
                             self.Incompressive_flow_variables_page).pack(pady=20, padx=16, fill="x")

        comp_card = ctk.CTkFrame(row, corner_radius=12)
        comp_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(comp_card, text="Compressible", font=FONT_SECTION).pack(pady=(20, 6))
        ctk.CTkLabel(comp_card, justify="center", font=FONT_HINT, text_color=MUTED_TEXT,
                     text="For flows with significant density variation —\n"
                          "typical in high-speed / transonic cases.") \
            .pack(padx=16)
        self._primary_button(comp_card, "Select Compressible",
                             self.Compressive_flow_variables_page).pack(pady=20, padx=16, fill="x")

        bar = ctk.CTkFrame(self.container, fg_color="transparent")
        bar.pack(fill="x", padx=30, pady=(0, 20))
        self._secondary_button(bar, "← Back", self.main_menu, width=140).pack(side="left")

    # ------------------------------------------------------------------ #
    # Pré-visualização da malha (qualidade + wireframe) antes de simular
    # ------------------------------------------------------------------ #
    def mesh_preview_screen(self):
        self.clear_frame()
        self._header(self.container, "Mesh Preview",
                     "Review the mesh quality before running the simulation.")

        self._mesh_preview_angle = self.angles[0] if self.angles else 0.0

        if len(self.angles) > 1:
            switcher = ctk.CTkFrame(self.container, fg_color="transparent")
            switcher.pack(fill="x", padx=30, pady=(0, 6))
            ctk.CTkLabel(switcher, text="Preview angle:", font=FONT_HINT, text_color=MUTED_TEXT) \
                .pack(side="left", padx=(0, 10))
            angle_switcher = ctk.CTkSegmentedButton(switcher, values=[f"{a:g}°" for a in self.angles],
                                                     command=self._on_mesh_preview_angle_change)
            angle_switcher.pack(side="left")
            angle_switcher.set(f"{self._mesh_preview_angle:g}°")

        self._mesh_preview_body = ctk.CTkFrame(self.container, fg_color="transparent")
        self._mesh_preview_body.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self._render_mesh_preview_loading()

        self._nav_bar(self.container, self.mesh_preview_back, "Continue →", self.choose_simulation_type)

        threading.Thread(target=self._generate_mesh_preview_worker,
                          args=(self._mesh_preview_angle,), daemon=True).start()

    def mesh_preview_back(self):
        if self.mesh_choice == "custom_mesh":
            self.select_custom_mesh()
        else:
            self.main_menu()

    def _on_mesh_preview_angle_change(self, value):
        try:
            angle = float(value.rstrip("°"))
        except ValueError:
            return
        self._mesh_preview_angle = angle
        self._render_mesh_preview_loading()
        threading.Thread(target=self._generate_mesh_preview_worker, args=(angle,), daemon=True).start()

    def _render_mesh_preview_loading(self):
        for w in self._mesh_preview_body.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._mesh_preview_body,
                     text=f"Generating mesh preview for α = {self._mesh_preview_angle:g}°...\n"
                          "Running blockMesh + checkMesh in WSL, this takes a few seconds.",
                     font=FONT_LABEL, text_color=MUTED_TEXT, justify="center").pack(expand=True)

    def _generate_mesh_preview_worker(self, angle):
        try:
            if self.mesh_choice == "custom_mesh":
                functions.blockMeshDirect_Custom(
                    angle, self.distance_to_inlet.get(), self.distance_to_outlet.get(),
                    self.cell_size_at_leading_edge.get(), self.cell_size_at_trailing_edge.get(),
                    self.cell_size_in_middle.get(), self.separating_point_position.get(),
                    self.boundary_layer_thickness.get(), self.first_layer_thickness.get(),
                    self.expansion_ratio.get(), self.max_cell_size_in_inlet.get(),
                    self.max_cell_size_in_outlet.get(), self.max_cell_size_in_inlet_and_outlet.get(),
                    self.num_mesh_on_boundary_layer_1.get(), self.num_mesh_on_boundary_layer_2.get(),
                    self.num_mesh_at_tail.get(), self.num_mesh_in_leading.get(), self.num_mesh_in_trailing.get())
            else:
                functions.blockMeshDirect(angle)
        except Exception as e:
            self.master.after(0, self._on_mesh_preview_ready, angle,
                               {"error": f"Could not generate the mesh: {e}"})
            return

        raw_output = self.run_mesh_preview_in_wsl("mesh_standard")
        if raw_output is None:
            self.master.after(0, self._on_mesh_preview_ready, angle,
                               {"error": "WSL executable not found. Ensure WSL is installed and available in PATH."})
            return

        parts = functions.split_mesh_preview_output(raw_output)
        quality = functions.parse_checkmesh_log(parts["log"])
        polygons = []
        if quality.get("blockmesh_ok"):
            try:
                polygons = functions.build_mesh_wireframe(parts["points"], parts["faces"], parts["boundary"])
            except Exception:
                polygons = []
        self.master.after(0, self._on_mesh_preview_ready, angle, {"quality": quality, "polygons": polygons})

    def run_mesh_preview_in_wsl(self, mesh_file="mesh_standard"):
        project_root = APP_DIR
        mesh_unix_path = os.path.join(project_root, mesh_file).replace("\\", "/").replace("C:/", "/mnt/c/")
        template_unix = os.path.join(project_root, "core", "Standard", "Incompressible") \
            .replace("\\", "/").replace("C:/", "/mnt/c/")
        # Meshing (blockMesh/checkMesh) doesn't depend on the flow type, so the
        # Incompressible template is reused as a disposable meshing sandbox
        # regardless of which flow type the user picks on the next screen.
        wsl_work_dir = "/tmp/aero_mesh_preview"
        command = (
            f'rm -rf "{wsl_work_dir}"; mkdir -p "{wsl_work_dir}"; '
            f'cp -r "{template_unix}/." "{wsl_work_dir}/"; '
            f'cp "{mesh_unix_path}" "{wsl_work_dir}/system/blockMeshDict"; '
            f'source /usr/lib/openfoam/openfoam2212/etc/bashrc; '
            f'cd "{wsl_work_dir}"; '
            # controlDict's function objects (forces/forceCoeffs) include
            # 0/initialConditions at case-creation time, before blockMesh
            # even runs -- so 0.orig must be restored to 0/ first, just
            # like Allrun's restore0Dir, even though meshing itself never
            # reads field values.
            f'rm -rf 0; cp -r 0.orig 0; '
            f'blockMesh > mesh_preview.log 2>&1; bm_status=$?; '
            f'if [ $bm_status -eq 0 ]; then checkMesh >> mesh_preview.log 2>&1; fi; '
            f'echo "===MESH_LOG_START==="; cat mesh_preview.log; echo "===MESH_LOG_END==="; '
            f'echo "===POINTS_START==="; cat constant/polyMesh/points 2>/dev/null; echo "===POINTS_END==="; '
            f'echo "===FACES_START==="; cat constant/polyMesh/faces 2>/dev/null; echo "===FACES_END==="; '
            f'echo "===BOUNDARY_START==="; cat constant/polyMesh/boundary 2>/dev/null; echo "===BOUNDARY_END==="; '
            f'cd /; rm -rf "{wsl_work_dir}"'
        )
        try:
            result = subprocess.run(["wsl", "-e", "bash", "-c", command], capture_output=True, text=True)
            return result.stdout
        except FileNotFoundError:
            return None

    def _on_mesh_preview_ready(self, angle, result):
        if angle != self._mesh_preview_angle:
            return  # o usuário já trocou de ângulo antes deste resultado chegar
        if not self._mesh_preview_body.winfo_exists():
            return  # o usuário já saiu da tela de preview antes do WSL responder
        for w in self._mesh_preview_body.winfo_children():
            w.destroy()

        if result.get("error") and not result.get("quality"):
            ctk.CTkLabel(self._mesh_preview_body, text=f"⚠ {result['error']}", font=FONT_LABEL,
                         text_color=WARN_COLOR, wraplength=700, justify="left").pack(expand=True, padx=20, pady=20)
            return

        quality = result["quality"]
        polygons = result["polygons"]

        body = ctk.CTkFrame(self._mesh_preview_body, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        plot_frame = ctk.CTkFrame(body, corner_radius=12)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._render_mesh_plot(plot_frame, polygons, quality)

        info_frame = ctk.CTkFrame(body, corner_radius=12)
        info_frame.grid(row=0, column=1, sticky="nsew")
        self._render_mesh_quality_panel(info_frame, quality)

    def _render_mesh_plot(self, parent, polygons, quality):
        from matplotlib.figure import Figure
        from matplotlib.collections import PolyCollection
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        fig = Figure(figsize=(5, 4.3), dpi=100)
        fig.patch.set_facecolor("#2b2b2b")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1e1e1e")

        if polygons:
            xs = [p[0] for poly in polygons for p in poly]
            ys = [p[1] for poly in polygons for p in poly]
            coll = PolyCollection(polygons, facecolors="none", edgecolors="#4da3ff", linewidths=0.4)
            ax.add_collection(coll)
            ax.set_xlim(max(-0.3, min(xs)), min(1.3, max(xs)))
            ax.set_ylim(max(-0.6, min(ys)), min(0.6, max(ys)))
        else:
            ax.text(0.5, 0.5, "Mesh preview unavailable", color="white",
                    ha="center", va="center", transform=ax.transAxes)

        ax.set_aspect("equal")
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#555555")

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(8, 0))

        toolbar_frame = tk.Frame(parent, bg="#2b2b2b")
        toolbar_frame.pack(fill="x", padx=8)
        toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
        toolbar.update()

        if polygons:
            total_cells = quality.get("cells")
            caption = f"Showing {len(polygons):,} near-field cells" + \
                      (f" (of {total_cells:,} total)." if total_cells else ".")
            ctk.CTkLabel(parent, text=caption, font=FONT_HINT, text_color=MUTED_TEXT) \
                .pack(padx=8, pady=(2, 8))

    def _render_mesh_quality_panel(self, parent, quality):
        ctk.CTkLabel(parent, text="Mesh Quality", font=FONT_SECTION, anchor="w") \
            .pack(fill="x", padx=16, pady=(16, 8))

        if not quality.get("blockmesh_ok"):
            ctk.CTkLabel(parent, text="✗ Mesh generation failed", font=FONT_LABEL,
                         text_color=WARN_COLOR, anchor="w").pack(fill="x", padx=16, pady=(0, 4))
            ctk.CTkLabel(parent, text=quality.get("error") or "Unknown error.", font=FONT_HINT,
                         text_color=MUTED_TEXT, wraplength=260, justify="left", anchor="w") \
                .pack(fill="x", padx=16, pady=(0, 16))
            return

        ok = quality.get("mesh_ok")
        status_color = RUN_COLOR if ok else WARN_COLOR
        status_text = "✓ Mesh OK" if ok else "⚠ Mesh has warnings"
        ctk.CTkLabel(parent, text=status_text, font=FONT_LABEL, text_color=status_color, anchor="w") \
            .pack(fill="x", padx=16, pady=(0, 12))

        rows = [
            ("Cells", quality.get("cells")),
            ("Points", quality.get("points")),
            ("Max non-orthogonality", quality.get("max_nonortho")),
            ("Avg non-orthogonality", quality.get("avg_nonortho")),
            ("Max skewness", quality.get("max_skewness")),
            ("Max aspect ratio", quality.get("max_aspect_ratio")),
        ]
        for label, value in rows:
            if value is None:
                continue
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            label_row = ctk.CTkFrame(row, fg_color="transparent")
            label_row.pack(side="left")
            ctk.CTkLabel(label_row, text=label, font=FONT_HINT, text_color=MUTED_TEXT, anchor="w").pack(side="left")
            help_text = MESH_METRIC_HELP.get(label)
            if help_text:
                help_icon = ctk.CTkLabel(label_row, text=" ⓘ", font=FONT_HINT, text_color=MUTED_TEXT, cursor="hand2")
                help_icon.pack(side="left")
                _Tooltip(help_icon, help_text)
            display_value = f"{value:.2f}" if isinstance(value, float) else f"{value:,}"
            ctk.CTkLabel(row, text=display_value, font=FONT_LABEL, anchor="e").pack(side="right")

        if quality.get("warnings"):
            ctk.CTkLabel(parent, text="Warnings", font=FONT_SECTION, anchor="w") \
                .pack(fill="x", padx=16, pady=(16, 4))
            for w_text in quality["warnings"][:6]:
                ctk.CTkLabel(parent, text=w_text, font=FONT_HINT, text_color=WARN_COLOR,
                             wraplength=260, justify="left", anchor="w").pack(fill="x", padx=16, pady=2)

    # ------------------------------------------------------------------ #
    # Geração de malha / preparo de dados (lógica preservada)
    # ------------------------------------------------------------------ #
    def search_airfoil(self):
        naca_code = self.naca_var.get()
        if self.airfoil == "airfoil_NACA":
            if len(naca_code) != 4 or not naca_code.isdigit():
                messagebox.showerror("Error:", "Please enter a valid 4-digit NACA code.")
                self.main_menu()
                return False

            m = int(naca_code[0]) / 100
            p = int(naca_code[1]) / 10
            t = int(naca_code[2:]) / 100
            num_points = 102

            # Gerar pontos do perfil aerodinâmico
            xu, yu, xl, yl = functions.naca4digit(m, p, t, 1.0, num_points)

            with open('coordenadas.dat', 'w') as f:
                for i in range(num_points):
                    f.write("{:.6f} {:.6f}\n".format(xu[i], yu[i]))
                for i in range(num_points - 1, -1, -1):
                    f.write("{:.6f} {:.6f}\n".format(xl[i], yl[i]))

        elif self.airfoil == "airfoil_custom":
            file_path = self.file1_path.get()
            try:
                # Abrir o arquivo com as coordenadas, ignorando linhas em branco
                with open(file_path, 'r') as file:
                    coordinates = [line.strip().split() for line in file if line.strip()]

                # Separar as coordenadas em listas de x e y
                x = [float(coord[0]) for coord in coordinates]
                y = [float(coord[1]) for coord in coordinates]
            except (FileNotFoundError, ValueError, IndexError) as e:
                messagebox.showerror("Error:", f"Could not read coordinate file: {e}")
                self.main_menu()
                return False

            with open("coordenadas.dat", "w") as file:
                for i in range(len(x)):
                    file.write(f"{x[i]} {y[i]}\n")

        return True

    def process_angles(self):
        angle_text = self.angle_var.get()
        try:
            self.angles = [float(angle.strip()) for angle in angle_text.split(',')]
        except ValueError:
            messagebox.showerror("Error:", "Please enter valid angles separated by commas.")
            self.angles = []  # Limpa a lista de ângulos em caso de erro
            self.main_menu()
            return False
        return True

    def Simulation_Incompressible(self):
        self.simulation_tipo = "Incompressible"
        if not self.process_angles():  # Processa os ângulos
            return
        source_directory = "core\\Standard\\Incompressible"
        target_directory = "Simulations"
        self.clear_and_create_angle_directories(target_directory, source_directory)
        print(f"Starting simulation with angles: {self.angles}")
        self.execute_mesh_operations()

    def simulation_Compressible(self):
        self.simulation_tipo = "Compressible"
        if not self.process_angles():  # Processa os ângulos
            return
        source_directory = "core\\Standard\\Compressible"
        target_directory = "Simulations"
        self.clear_and_create_angle_directories(target_directory, source_directory)
        print(f"Starting simulation with angles: {self.angles}")
        self.execute_mesh_operations()

    def clear_and_create_angle_directories(self, target_path, source_path):
        if not os.path.exists(target_path):
            os.makedirs(target_path)
        # Limpar diretório existente
        for item in os.listdir(target_path):
            item_path = os.path.join(target_path, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        # Criar subdiretórios para cada ângulo e copiar conteúdos
        for angle in self.angles:
            angle_folder = os.path.join(target_path, f"Angle_{angle}")
            shutil.copytree(source_path, angle_folder)

    def execute_mesh_operations(self):
        if not self.process_angles():
            return
        source_file = "mesh_standard"
        base_directory = "Simulations"
        if self.simulation_tipo == "Incompressible":
            flow_speed = self.flow_speed_var_I.get()
            Pressure = self.p_var_I.get()
            nut_value = self.nut_var.get()
            nutilda_value = self.nutilda_var.get()
            nu_value_I = self.nu_var_I.get()
            standard_first_layer = functions.first_layer_thickness_for_flow(flow_speed, nu_value_I)
            standard_expansion_ratio = functions.expansion_ratio_for_flow(flow_speed, nu_value_I)
        elif self.simulation_tipo == "Compressible":
            flow_speed = self.flow_speed_var_c.get()
            Pressure = self.p_var_c.get()
            nut_value = self.nut_var_c.get()
            omega_value = self.omega_var.get()
            nu_value_c = self.nu_var_c.get()
            alphat_value = self.alphat_var.get()
            T_value = self.t_var.get()
            k_value = self.k_var.get()
            standard_first_layer = functions.first_layer_thickness_for_flow(flow_speed, nu_value_c)
            standard_expansion_ratio = functions.expansion_ratio_for_flow(flow_speed, nu_value_c)

        for angle in self.angles:
            angle_directory_path = os.path.join(base_directory, f"Angle_{angle}")
            system_directory_path = os.path.join(angle_directory_path, "system")
            orig_directory_path = os.path.join(angle_directory_path, "0.orig")
            os.makedirs(system_directory_path, exist_ok=True)

            try:
                if self.mesh_choice == "standard_mesh":
                    functions.blockMeshDirect(angle, first_layer_thickness=standard_first_layer,
                                               expansion_ratio=standard_expansion_ratio)
                elif self.mesh_choice == "custom_mesh":
                    distance_to_inlet_val = self.distance_to_inlet.get()
                    distance_to_outlet_val = self.distance_to_outlet.get()
                    cell_size_at_leading_edge_val = self.cell_size_at_leading_edge.get()
                    cell_size_at_trailing_edge_val = self.cell_size_at_trailing_edge.get()
                    cell_size_in_middle_val = self.cell_size_in_middle.get()
                    separating_point_position_val = self.separating_point_position.get()
                    boundary_layer_thickness_val = self.boundary_layer_thickness.get()
                    first_layer_thickness_val = self.first_layer_thickness.get()
                    expansion_ratio_val = self.expansion_ratio.get()
                    max_cell_size_in_inlet_val = self.max_cell_size_in_inlet.get()
                    max_cell_size_in_outlet_val = self.max_cell_size_in_outlet.get()
                    max_cell_size_in_inlet_and_outlet_val = self.max_cell_size_in_inlet_and_outlet.get()
                    num_mesh_on_boundary_layer_1_val = self.num_mesh_on_boundary_layer_1.get()
                    num_mesh_on_boundary_layer_2_val = self.num_mesh_on_boundary_layer_2.get()
                    num_mesh_at_tail_val = self.num_mesh_at_tail.get()
                    num_mesh_in_leading_val = self.num_mesh_in_leading.get()
                    num_mesh_in_trailing_val = self.num_mesh_in_trailing.get()

                    functions.blockMeshDirect_Custom(angle, distance_to_inlet_val, distance_to_outlet_val,
                                cell_size_at_leading_edge_val, cell_size_at_trailing_edge_val,
                                cell_size_in_middle_val, separating_point_position_val,
                                boundary_layer_thickness_val, first_layer_thickness_val,
                                expansion_ratio_val, max_cell_size_in_inlet_val,
                                max_cell_size_in_outlet_val, max_cell_size_in_inlet_and_outlet_val,
                                num_mesh_on_boundary_layer_1_val, num_mesh_on_boundary_layer_2_val,
                                num_mesh_at_tail_val, num_mesh_in_leading_val, num_mesh_in_trailing_val)

                destination_file_path = os.path.join(system_directory_path, "blockMeshDict")
                shutil.copy(source_file, destination_file_path)

                if self.simulation_tipo == "Incompressible":
                    functions.variables_incompressible(orig_directory_path, angle, flow_speed, Pressure,
                                                         nut_value, nutilda_value, nu_value_I)
                elif self.simulation_tipo == "Compressible":
                    functions.variables_compressible(orig_directory_path, angle, flow_speed, Pressure,
                                                       nut_value, T_value, omega_value, k_value,
                                                       alphat_value, nu_value_c)
            except Exception as e:
                messagebox.showerror("Mesh Generation Error",
                    f"Failed to generate mesh for angle {angle}: {e}\n\n"
                    "Check the mesh parameters (e.g. avoid zero values) and try again.")
                return

            print(f"File '{source_file}' copied and renamed to '{destination_file_path}' after running blockMeshDirect for angle {angle}")

        self.show_progress_screen()
        threading.Thread(target=self._run_simulations_worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Execução das simulações no WSL (roda em thread separada)
    # ------------------------------------------------------------------ #
    def show_progress_screen(self):
        self.clear_frame()
        self._header(self.container, "Running Simulations",
                     "This can take a while depending on the mesh size and number of angles.\n"
                     "Feel free to leave this window open in the background.")
        card = self._card(self.container)
        self.progress_status_label = ctk.CTkLabel(card, text="Starting...", font=FONT_LABEL)
        self.progress_status_label.pack(padx=20, pady=(24, 8))
        self.progress_bar = ctk.CTkProgressBar(card, width=420)
        self.progress_bar.set(0)
        self.progress_bar.pack(padx=20, pady=(0, 24))

        plot_frame = ctk.CTkFrame(self.container, corner_radius=12)
        plot_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        self._build_live_plot(plot_frame)

    def _build_live_plot(self, parent):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        # Parallel runs get one small subplot per angle (laid out in a grid)
        # instead of a single plot, since several angles converge at once.
        self._live_plot_grid_mode = self.parallel_var.get() and len(self.angles) > 1
        self._live_plot_axes = {}

        if self._live_plot_grid_mode:
            n = len(self.angles)
            cols = min(4, n)
            rows = -(-n // cols)  # ceil division
            fig = Figure(figsize=(3.1 * cols, 2.3 * rows), dpi=100)
            fig.patch.set_facecolor("#2b2b2b")
            for i, angle in enumerate(self.angles):
                ax = fig.add_subplot(rows, cols, i + 1)
                ax.set_facecolor("#1e1e1e")
                ax.set_title(f"{angle:g}° — waiting...", color="white", fontsize=8)
                ax.tick_params(colors="white", labelsize=6)
                for spine in ax.spines.values():
                    spine.set_color("#555555")
                self._live_plot_axes[angle] = ax
            fig.tight_layout(pad=1.4)
        else:
            fig = Figure(figsize=(6, 3), dpi=100)
            fig.patch.set_facecolor("#2b2b2b")
            ax = fig.add_subplot(111)
            ax.set_facecolor("#1e1e1e")
            ax.set_title("Waiting for solver output...", color="white", fontsize=9, wrap=True)
            ax.tick_params(colors="white", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#555555")
            self._live_plot_axes["single"] = ax

        self._live_plot_canvas = FigureCanvasTkAgg(fig, master=parent)
        self._live_plot_canvas.draw()
        self._live_plot_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

    def _update_live_plot(self, angle, data):
        canvas = getattr(self, "_live_plot_canvas", None)
        if canvas is None or not canvas.get_tk_widget().winfo_exists():
            return
        axes = getattr(self, "_live_plot_axes", {})
        grid_mode = getattr(self, "_live_plot_grid_mode", False)
        ax = axes.get(angle) if grid_mode else axes.get("single")
        if ax is None:
            return
        ax.clear()
        ax.plot(data["time"], data["cd"], color="#4da3ff", label="Cd", linewidth=1.2 if grid_mode else 1.6)
        ax.plot(data["time"], data["cl"], color="#e0a030", label="Cl", linewidth=1.2 if grid_mode else 1.6)
        ax.set_title(f"{angle:g}°" if grid_mode else f"Angle {angle:g}° — live convergence",
                     color="white", fontsize=8 if grid_mode else 10)
        if not grid_mode:
            ax.set_xlabel("Iteration", color="white", fontsize=8)
        ax.set_facecolor("#1e1e1e")
        ax.legend(fontsize=6 if grid_mode else 8, loc="upper right", facecolor="#2b2b2b", labelcolor="white")
        ax.tick_params(colors="white", labelsize=6 if grid_mode else 8)
        for spine in ax.spines.values():
            spine.set_color("#555555")
        canvas.draw_idle()

    def _poll_live_coefficients(self, angle_directory, angle, stop_event):
        # Mirrors run_commands_in_wsl's own wsl_work_dir naming so this reads
        # the SAME in-progress case while it's still running there.
        run_id = os.path.basename(angle_directory.rstrip("\\/"))
        coeff_path = f"/tmp/aero_sim_{run_id}/postProcessing/forceCoeffs/0/coefficient.dat"
        while not stop_event.wait(3):
            try:
                r = subprocess.run(["wsl", "-e", "bash", "-c", f'cat "{coeff_path}" 2>/dev/null'],
                                    capture_output=True, text=True, timeout=10)
            except Exception:
                continue
            if not r.stdout.strip():
                continue
            data = functions.parse_live_coefficients(r.stdout)
            if data:
                self.master.after(0, self._update_live_plot, angle, data)

    def _set_progress(self, done, total, angle):
        self.progress_bar.set(done / total if total else 0)
        self.progress_status_label.configure(
            text=f"Angle {angle}°  —  {done}/{total} simulation(s) completed")

    def _run_simulations_worker(self):
        base_directory = os.path.join(APP_DIR, "Simulations")
        total = len(self.angles)

        if self.parallel_var.get() and total > 1:
            failed_angles = self._run_simulations_parallel(base_directory, total)
        else:
            failed_angles = self._run_simulations_sequential(base_directory, total)

        base_directory = os.path.join(APP_DIR, "Simulations")
        self.extract_results(base_directory)

        self.master.after(0, self._on_simulation_complete, failed_angles)

    def _run_simulations_sequential(self, base_directory, total):
        failed_angles = []
        for i, angle in enumerate(self.angles, start=1):
            angle_directory = os.path.join(base_directory, f"Angle_{angle}")
            os.makedirs(angle_directory, exist_ok=True)  # Cria o diretório se não existir
            stop_poll = threading.Event()
            poll_thread = threading.Thread(target=self._poll_live_coefficients,
                                            args=(angle_directory, angle, stop_poll), daemon=True)
            poll_thread.start()
            success = self.run_commands_in_wsl(angle_directory)
            stop_poll.set()
            if not success:
                failed_angles.append(angle)
            self.master.after(0, self._set_progress, i, total, angle)
        return failed_angles

    def _run_simulations_parallel(self, base_directory, total):
        # Each angle's own OpenFOAM solve is already 2-process (decomposePar +
        # simpleFoam -parallel), so running several angles at once multiplies
        # that -- cap concurrency instead of launching every angle at the same
        # time, to keep this usable on a modest machine.
        max_workers = min(total, max(1, (os.cpu_count() or 4) // 2), 4)
        failed_angles = []
        done_lock = threading.Lock()
        done_count = 0

        def run_one(angle):
            angle_directory = os.path.join(base_directory, f"Angle_{angle}")
            os.makedirs(angle_directory, exist_ok=True)
            stop_poll = threading.Event()
            poll_thread = threading.Thread(target=self._poll_live_coefficients,
                                            args=(angle_directory, angle, stop_poll), daemon=True)
            poll_thread.start()
            success = self.run_commands_in_wsl(angle_directory)
            stop_poll.set()
            return angle, success

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_one, angle) for angle in self.angles]
            for future in concurrent.futures.as_completed(futures):
                angle, success = future.result()
                if not success:
                    failed_angles.append(angle)
                with done_lock:
                    done_count += 1
                    current_done = done_count
                self.master.after(0, self._set_progress, current_done, total, angle)
        return failed_angles

    def _on_simulation_complete(self, failed_angles):
        self.clear_frame()
        self._header(self.container, "Simulation Finished", "Results and plots have been saved.")

        card = self._card(self.container)
        if failed_angles:
            ctk.CTkLabel(card, justify="left", wraplength=600, font=FONT_LABEL, text_color=WARN_COLOR,
                         text=f"⚠ {len(failed_angles)} of {len(self.angles)} simulation(s) failed: {failed_angles}\n"
                              "Check the console output for details.") \
                .pack(padx=20, pady=20)
        else:
            ctk.CTkLabel(card, font=FONT_LABEL, text_color=RUN_COLOR,
                         text=f"✓ All {len(self.angles)} simulation(s) completed successfully.") \
                .pack(padx=20, pady=20)

        if self.last_validation:
            avg_err = self.last_validation["summary"]["rel_error_pct"].mean()
            ctk.CTkLabel(card, justify="left", wraplength=600, font=FONT_HINT, text_color=MUTED_TEXT,
                         text=f"Validated against a bundled reference dataset — average difference "
                              f"{avg_err:.1f}% across the matching angles. See the \"validation_*\" "
                              f"plots in View Results for details.\nSource: {self.last_validation['citation']}") \
                .pack(padx=20, pady=(0, 16))

        actions = ctk.CTkFrame(self.container, fg_color="transparent")
        actions.pack(fill="x", padx=30, pady=(10, 20), side="bottom")
        self._secondary_button(actions, "Open Results Folder", self.open_results_folder, width=200) \
            .pack(side="left")
        self._secondary_button(actions, "View Results", self.results_viewer_screen, width=180) \
            .pack(side="left", padx=(10, 0))
        self._primary_button(actions, "Back to Main Menu", self.main_menu, width=200).pack(side="right")

        if failed_angles:
            messagebox.showwarning("Simulation Finished with Errors",
                f"Simulation failed for angle(s): {failed_angles}.\n"
                "Check the console output for details.")
        else:
            messagebox.showinfo("Simulation Complete:", "All simulations have been successfully completed!")

    def open_results_folder(self):
        results_dir = os.path.join(APP_DIR, "Results")
        if os.path.isdir(results_dir):
            os.startfile(results_dir)
        else:
            messagebox.showinfo("Results Folder", "No results folder found yet.")

    # ------------------------------------------------------------------ #
    # Presets de configuração (salvar/carregar um JSON com o setup inteiro)
    # ------------------------------------------------------------------ #
    def _collect_preset(self):
        preset = {
            "preset_version": 1,
            "airfoil": {
                "mode": "custom_file" if self.airfoil == "airfoil_custom" else "naca",
                "naca_code": self.naca_var.get(),
                "custom_file_path": self.file1_path.get(),
            },
            "angles": self.angle_var.get(),
            "mesh": {"choice": self.mesh_choice},
            "parallel": self.parallel_var.get(),
            "simulation_type": self.simulation_tipo,
        }
        if self.mesh_choice == "custom_mesh" and hasattr(self, "distance_to_inlet"):
            preset["mesh"]["custom_params"] = {
                name: getattr(self, name).get() for name in CUSTOM_MESH_PARAM_NAMES
            }
        if hasattr(self, "flow_speed_var_I"):
            preset["flow_incompressible"] = {
                "velocity": self.flow_speed_var_I.get(), "p": self.p_var_I.get(),
                "nut": self.nut_var.get(), "nutilda": self.nutilda_var.get(), "nu": self.nu_var_I.get(),
            }
        if hasattr(self, "flow_speed_var_c"):
            preset["flow_compressible"] = {
                "velocity": self.flow_speed_var_c.get(), "p": self.p_var_c.get(), "t": self.t_var.get(),
                "alphat": self.alphat_var.get(), "k": self.k_var.get(), "nut": self.nut_var_c.get(),
                "omega": self.omega_var.get(), "nu": self.nu_var_c.get(),
            }
        return preset

    def save_preset(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON preset", "*.json")],
            initialfile="preset.json", title="Save configuration preset")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_preset(), f, indent=2)
        except OSError as e:
            messagebox.showerror("Error:", f"Could not save preset: {e}")
            return
        messagebox.showinfo("Preset Saved", f"Configuration saved to {os.path.basename(path)}.")

    def load_preset(self):
        path = filedialog.askopenfilename(filetypes=[("JSON preset", "*.json")],
                                           title="Load configuration preset")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                preset = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("Error:", f"Could not read preset: {e}")
            return

        try:
            airfoil = preset.get("airfoil") or {}
            if airfoil.get("mode") == "custom_file":
                self.airfoil = "airfoil_custom"
                self.file1_path.set(airfoil.get("custom_file_path") or "")
            else:
                self.airfoil = "airfoil_NACA"
                self.naca_var.set(airfoil.get("naca_code") or "")
            self.angle_var.set(preset.get("angles") or "")

            mesh = preset.get("mesh") or {}
            self.mesh_choice = mesh.get("choice")
            custom_params = mesh.get("custom_params")
            if custom_params:
                for name in CUSTOM_MESH_PARAM_NAMES:
                    if name in custom_params:
                        setattr(self, name, tk.DoubleVar(value=custom_params[name]))

            self.parallel_var.set(bool(preset.get("parallel", False)))
            self.simulation_tipo = preset.get("simulation_type")

            flow_i = preset.get("flow_incompressible")
            if flow_i:
                self.flow_speed_var_I = tk.DoubleVar(value=flow_i.get("velocity", 0.0))
                self.p_var_I = tk.DoubleVar(value=flow_i.get("p", 0.0))
                self.nut_var = tk.DoubleVar(value=flow_i.get("nut", DEFAULT_NUT_NUTILDA))
                self.nutilda_var = tk.DoubleVar(value=flow_i.get("nutilda", DEFAULT_NUT_NUTILDA))
                self.nu_var_I = tk.DoubleVar(value=flow_i.get("nu", 1e-5))

            flow_c = preset.get("flow_compressible")
            if flow_c:
                self.flow_speed_var_c = tk.DoubleVar(value=flow_c.get("velocity", 0.0))
                self.p_var_c = tk.DoubleVar(value=flow_c.get("p", 1e5))
                self.t_var = tk.DoubleVar(value=flow_c.get("t", 298))
                self.alphat_var = tk.DoubleVar(value=flow_c.get("alphat", 0.1))
                self.k_var = tk.DoubleVar(value=flow_c.get("k", 0.1))
                self.nut_var_c = tk.DoubleVar(value=flow_c.get("nut", 0.1))
                self.omega_var = tk.DoubleVar(value=flow_c.get("omega", 0.1))
                self.nu_var_c = tk.DoubleVar(value=flow_c.get("nu", 1e-6))
        except (TypeError, ValueError) as e:
            messagebox.showerror("Error:", f"Preset file is malformed: {e}")
            return

        messagebox.showinfo("Preset Loaded",
            "Configuration loaded. Continue through the normal screens (mesh, "
            "simulation type, flow properties) to review and run it.")
        self.main_menu()

    # ------------------------------------------------------------------ #
    # Visualizador de resultados/plots dentro do próprio app
    # ------------------------------------------------------------------ #
    def results_viewer_screen(self):
        self.clear_frame()
        self._header(self.container, "Results", "Browse the plots generated by the last simulation.")

        plots_dir = os.path.join(APP_DIR, "plots")
        files = os.listdir(plots_dir) if os.path.isdir(plots_dir) else []
        files = sorted((f for f in files if f.lower().endswith(".png")), key=self._plot_sort_key)

        if not files:
            ctk.CTkLabel(self.container, text="No plots found yet — run a simulation first.",
                         font=FONT_LABEL, text_color=MUTED_TEXT).pack(expand=True)
            self._secondary_button(self.container, "← Back to Main Menu", self.main_menu, width=200) \
                .pack(padx=30, pady=20, side="bottom", anchor="w")
            return

        names = [os.path.splitext(f)[0] for f in files]

        picker_row = ctk.CTkFrame(self.container, fg_color="transparent")
        picker_row.pack(fill="x", padx=30, pady=(0, 10))
        ctk.CTkLabel(picker_row, text="Plot:", font=FONT_LABEL).pack(side="left", padx=(0, 10))
        self._result_plot_menu = ctk.CTkOptionMenu(picker_row, values=names, width=220,
                                                     command=self._on_result_plot_selected)
        self._result_plot_menu.pack(side="left")
        self._secondary_button(picker_row, "Open Results Folder", self.open_results_folder, width=180) \
            .pack(side="right")

        self._result_image_frame = ctk.CTkFrame(self.container, corner_radius=12)
        self._result_image_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))
        self._result_image_label = ctk.CTkLabel(self._result_image_frame, text="")
        self._result_image_label.pack(fill="both", expand=True, padx=10, pady=10)

        self._secondary_button(self.container, "← Back to Main Menu", self.main_menu, width=200) \
            .pack(padx=30, pady=(0, 20), side="bottom", anchor="w")

        self._on_result_plot_selected(names[0])

    @staticmethod
    def _plot_sort_key(filename):
        name = os.path.splitext(filename)[0]
        return (RESULT_PLOT_ORDER.index(name) if name in RESULT_PLOT_ORDER else len(RESULT_PLOT_ORDER), name)

    def _on_result_plot_selected(self, name):
        path = os.path.join(APP_DIR, "plots", f"{name}.png")
        try:
            img = Image.open(path)
        except Exception as e:
            self._result_image_label.configure(image=None, text=f"Could not open {name}.png: {e}")
            return
        max_w, max_h = 820, 480
        scale = min(max_w / img.width, max_h / img.height, 1.0)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self._result_image_label.configure(image=ctk_img, text="")
        self._result_image_label.image = ctk_img  # manter referência (senão o GC apaga a imagem)

    def run_commands_in_wsl(self, directory):
        unix_path = directory.replace("\\", "/").replace("C:/", "/mnt/c/")
        run_id = os.path.basename(directory.rstrip("\\/"))
        # OpenFOAM rejects spaces (and other special characters) in a case's
        # resolved path (fileName::stripInvalid), which breaks any project
        # checked out under a path like ".../Área de Trabalho/...". Reading
        # and writing case files is also far slower on the /mnt/c (DrvFs)
        # mount than on the native filesystem. To avoid both problems, the
        # case is copied into a native WSL directory, run there, and only
        # the results are copied back to the Windows-side folder.
        wsl_work_dir = f"/tmp/aero_sim_{run_id}"
        command = (
            f'rm -rf "{wsl_work_dir}" && '
            f'cp -r "{unix_path}" "{wsl_work_dir}" && '
            f'cd "{wsl_work_dir}" && '
            f'./run_simulation.sh; '
            f'sim_exit=$?; '
            f'rm -rf "{unix_path}/postProcessing"; '
            f'cp -r "{wsl_work_dir}/postProcessing" "{unix_path}/" 2>/dev/null; '
            f'rm -rf "{wsl_work_dir}"; '
            f'exit $sim_exit'
        )
        try:
            # -e is required here: without it, "wsl bash -c '...'" runs the
            # script through an extra default-shell wrapping layer on this
            # machine's WSL setup that silently resets $? to empty/0 between
            # statements, so "sim_exit=$?; ...; exit $sim_exit" would always
            # report success even when run_simulation.sh actually failed.
            subprocess.run(["wsl", "-e", "bash", "-c", command], check=True)
            print(f"Simulation completed in the directory {directory}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error executing simulation in the directory {directory}: {e}")
            print("Please check that the path, permissions, and script are correct.")
            return False
        except FileNotFoundError:
            print("WSL executable not found. Ensure WSL is installed and available in PATH.")
            return False

    # ------------------------------------------------------------------ #
    # Incompressível
    # ------------------------------------------------------------------ #
    def Incompressive_flow_variables_page(self):
        self.clear_frame()
        self._header(self.container, "Incompressible Simulation", "Set the flow properties for this run.")

        # Só cria com valores padrão na primeira vez -- preserva edições do
        # usuário (ou um preset carregado) ao navegar de volta pra cá.
        if not hasattr(self, "flow_speed_var_I"):
            self.flow_speed_var_I = tk.DoubleVar()
            self.p_var_I = tk.DoubleVar(value=0.0)
            self.nut_var = tk.DoubleVar(value=DEFAULT_NUT_NUTILDA)
            self.nutilda_var = tk.DoubleVar(value=DEFAULT_NUT_NUTILDA)
            self.nu_var_I = tk.DoubleVar(value=1e-5)

        card = self._card(self.container)
        wrap, _ = self._labeled_entry(card, "Flow velocity (m/s)", self.flow_speed_var_I)
        wrap.pack(fill="x", padx=20, pady=20)

        self.additional_fields_frame = ctk.CTkFrame(self.container, corner_radius=12)
        adv_grid = ctk.CTkFrame(self.additional_fields_frame, fg_color="transparent")
        adv_grid.pack(fill="x", padx=16, pady=16)
        adv_grid.grid_columnconfigure((0, 1), weight=1)
        adv_fields = [
            ("nu", self.nu_var_I), ("P", self.p_var_I),
            ("Nut", self.nut_var), ("Nutilda", self.nutilda_var),
        ]
        for idx, (label, var) in enumerate(adv_fields):
            w, _ = self._labeled_entry(adv_grid, label, var)
            w.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=6, pady=6)

        ctk.CTkSwitch(self.container, text="Show advanced parameters", font=FONT_LABEL,
                      command=self.toggle_additional_fields).pack(anchor="w", padx=30, pady=(0, 4))
        self._add_parallel_toggle(self.container)
        self._add_save_preset_button(self.container)

        self.nav_bar_I = self._nav_bar(self.container, self.main_menu, "Run Simulation",
                                        self.Simulation_Incompressible,
                                        next_color=RUN_COLOR, next_hover=RUN_HOVER)

    def toggle_additional_fields(self):
        if self.additional_fields_frame.winfo_ismapped():
            self.additional_fields_frame.pack_forget()  # Esconde os campos
            self.nut_var.set(DEFAULT_NUT_NUTILDA)  # Define valores padrão caso escondido
            self.nutilda_var.set(DEFAULT_NUT_NUTILDA)
            self.p_var_I.set(0.0)
            self.nu_var_I.set(1e-5)
        else:
            self.additional_fields_frame.pack(fill="x", padx=30, pady=(0, 10), before=self.nav_bar_I)

    # ------------------------------------------------------------------ #
    # Compressível
    # ------------------------------------------------------------------ #
    def Compressive_flow_variables_page(self):
        self.clear_frame()
        self._header(self.container, "Compressible Simulation", "Set the flow properties for this run.")

        if not hasattr(self, "flow_speed_var_c"):
            self.flow_speed_var_c = tk.DoubleVar()
            self.p_var_c = tk.DoubleVar(value=1e5)
            self.t_var = tk.DoubleVar(value=298)
            self.alphat_var = tk.DoubleVar(value=0.1)
            self.k_var = tk.DoubleVar(value=0.1)
            self.nut_var_c = tk.DoubleVar(value=0.1)
            self.omega_var = tk.DoubleVar(value=0.1)
            self.nu_var_c = tk.DoubleVar(value=1e-6)

        card = self._card(self.container)
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=20)
        grid.grid_columnconfigure((0, 1, 2), weight=1)
        basic_fields = [
            ("Flow velocity (m/s)", self.flow_speed_var_c),
            ("P (pressure)", self.p_var_c),
            ("T (temperature K)", self.t_var),
        ]
        for idx, (label, var) in enumerate(basic_fields):
            w, _ = self._labeled_entry(grid, label, var)
            w.grid(row=0, column=idx, sticky="ew", padx=6)

        self.additional_fields_frame_compressive = ctk.CTkFrame(self.container, corner_radius=12)
        adv_grid = ctk.CTkFrame(self.additional_fields_frame_compressive, fg_color="transparent")
        adv_grid.pack(fill="x", padx=16, pady=16)
        adv_grid.grid_columnconfigure((0, 1), weight=1)
        adv_fields = [
            ("Alphat", self.alphat_var), ("k", self.k_var),
            ("Nut", self.nut_var_c), ("Omega", self.omega_var),
            ("Nu", self.nu_var_c),
        ]
        for idx, (label, var) in enumerate(adv_fields):
            w, _ = self._labeled_entry(adv_grid, label, var)
            w.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=6, pady=6)

        ctk.CTkSwitch(self.container, text="Show advanced parameters", font=FONT_LABEL,
                      command=self.toggle_additional_fields_compressive).pack(anchor="w", padx=30, pady=(0, 4))
        self._add_parallel_toggle(self.container)
        self._add_save_preset_button(self.container)

        self.nav_bar_c = self._nav_bar(self.container, self.main_menu, "Run Simulation",
                                        self.simulation_Compressible,
                                        next_color=RUN_COLOR, next_hover=RUN_HOVER)

    def toggle_additional_fields_compressive(self):
        if self.additional_fields_frame_compressive.winfo_ismapped():
            self.additional_fields_frame_compressive.pack_forget()  # Esconde os campos
            # Define valores padrão caso escondido
            self.alphat_var.set(0.1)
            self.k_var.set(0.1)
            self.nut_var_c.set(0.1)
            self.omega_var.set(0.1)
            self.nu_var_c.set(1e-6)
        else:
            self.additional_fields_frame_compressive.pack(fill="x", padx=30, pady=(0, 10), before=self.nav_bar_c)

    # ------------------------------------------------------------------ #
    # Pós-processamento (lógica preservada)
    # ------------------------------------------------------------------ #
    def extract_results(self, base_directory):
        results_dir = os.path.join(base_directory, "..", "Results")
        results_path = os.path.join(results_dir, "results.txt")

        if not os.path.exists(results_dir):
            os.makedirs(results_dir)

        with open(results_path, "w") as results_file:
            results_file.write(
                "# Angle_n: Time\tCd\tCd(f)\tCd(r)\tCl\tCl(f)\tCl(r)\tCmPitch\tCmRoll\tCmYaw\tCs\tCs(f)\tCs(r)\tyPlus_avg\tyPlus_max\tConverged\n"
            )

        # Número de colunas de dados esperadas (Time + 12 coeficientes + yPlus_avg + yPlus_max + Converged)
        num_result_columns = 16

        with open(results_path, "a") as results_file:
            for angle in self.angles:
                angle_folder = f"Angle_{angle}"
                angle_directory_path = os.path.join(base_directory, angle_folder)

                if not os.path.exists(angle_directory_path):
                    os.makedirs(angle_directory_path)

                results_file.write(f"{angle_folder}: ")

                coefficient_path = os.path.join(angle_directory_path, "postProcessing", "forceCoeffs", "0", "coefficient.dat")
                yplus_path = os.path.join(angle_directory_path, "postProcessing", "yPlus", "0", "yPlus.dat")

                summary = functions.summarize_coefficient_history(coefficient_path)
                if summary is None:
                    print(f"Warning: no results found for angle {angle} ({coefficient_path})")
                    results_file.write("\t".join(["nan"] * num_result_columns) + "\n")
                    continue

                if not summary["converged"]:
                    print(f"Warning: angle {angle} may not be fully converged "
                          f"({summary['rel_change'] * 100:.1f}% change over the averaging window)")

                yplus = functions.summarize_yplus(yplus_path)
                yplus_values = [yplus["average"], yplus["max"]] if yplus else [float("nan"), float("nan")]

                row_values = [summary["last_time"]] + summary["averaged"] + yplus_values + [int(summary["converged"])]
                results_file.write("\t".join(f"{v:.6e}" if isinstance(v, float) else str(v) for v in row_values) + "\n")

        naca_code = self.naca_var.get() if self.airfoil == "airfoil_NACA" else None
        self.last_validation = functions.plot_data_from_txt(results_path, naca_code=naca_code)


if __name__ == "__main__":
    root = ctk.CTk()
    app = App(root)
    root.mainloop()
