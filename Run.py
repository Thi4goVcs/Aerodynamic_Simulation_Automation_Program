import os
import sys
import json
import subprocess
import shutil
import threading
import time
import uuid
import atexit
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

# Freestream turbulence intensity (percent) for the k-omega SST model: a low-turbulence wind
# tunnel / clean external flow. It sets k; omega follows from k and the eddy viscosity above.
DEFAULT_TURBULENCE_INTENSITY_PCT = 0.1

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Design tokens (warm neutral + amber accent), from the "Focus" redesign handoff.
BG = "#201f1d"          # window
CARD = "#2a2725"        # cards / panels
SUNKEN = "#1a1917"      # inputs, charts, footer bars
QUEUE_BG = "#232120"
TRACK = "#35322f"       # bar tracks and thin borders
BORDER_STRONG = "#4a4642"
INK = "#f8f4f4"
INK2 = "#d7d3d3"
INK3 = "#bab6b6"
MUTED = "#9b9797"       # never go darker than this for text on the grounds above
ACCENT = "#e7a86f"
ACCENT_HOVER = "#ffc896"
ACCENT_PRESSED = "#c8894c"
ALERT = "#e0724f"
ALERT_TEXT = "#f1c3b1"
ALERT_TINT = "#3b2b24"      # rgba(224,114,79,.14) flattened on BG (CTk has no alpha)
ALERT_BORDER = "#764434"    # rgba(224,114,79,.45) flattened on BG
ROW_HOVER = "#2f2c29"

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"
FONT_TITLE = (FONT_FAMILY, 22, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 13)
FONT_SECTION = (FONT_FAMILY, 15, "bold")
FONT_LABEL = (FONT_FAMILY, 13)
FONT_BUTTON = (FONT_FAMILY, 13, "bold")
FONT_HINT = (FONT_FAMILY, 11)
FONT_CAPS = (FONT_FAMILY, 10, "bold")
FONT_HERO = (FONT_FAMILY, 30, "bold")

# Kept under the old names: the rest of the file (and presets/tests) use these.
MUTED_TEXT = MUTED
RUN_COLOR = ACCENT
RUN_HOVER = ACCENT_HOVER
WARN_COLOR = ALERT
BACK_COLOR = TRACK
BACK_HOVER = BORDER_STRONG

WIZARD_STEPS = ["Setup", "Mesh", "Preview", "Type", "Flow", "Run", "Results"]

# What each mesh-quality metric means and which direction is better, shown as
# a hover tooltip next to its value -- otherwise the raw numbers (e.g. "Max
# non-orthogonality: 88.32") give no sense of whether that's fine or a
# problem.
TU_HELP = ("Freestream turbulence intensity of the k-omega SST model, in percent. 0.1 is a clean, "
           "low-turbulence flow (wind tunnel / free flight); it sets k, and omega follows from k and Nut.")

YPLUS_HELP = ("Average wall y+ the standard mesh is sized for. The default (33.41) is the value validated "
              "against wind-tunnel data. Use ~1 to resolve the boundary layer down to the wall: it runs "
              "slower and, in our tests, did not improve the drag.")

MESH_METRIC_HELP = {
    "Cells": "Total number of mesh cells. Just the mesh size, not a quality judgment "
             "by itself -- more cells means more resolution but longer solve times.",
    "Points": "Total number of mesh vertices. Informational only.",
    "Max non-orthogonality": "Lower is better. The standard mesh sits around 57-64°. Angle between the line joining two cell "
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

# blockMeshDirect_Custom still takes a first-layer size, but since the grading seam fix it
# no longer changes the mesh (checked: 4e-6, 1e-8 and 3e-3 give byte-identical files), so the
# GUI no longer asks for it. Old presets that carry the key simply have it ignored.
CUSTOM_MESH_FIRST_LAYER = 4e-6

CUSTOM_MESH_PARAM_NAMES = [
    "distance_to_inlet", "distance_to_outlet", "cell_size_at_leading_edge",
    "cell_size_at_trailing_edge", "cell_size_in_middle", "separating_point_position",
    "boundary_layer_thickness", "expansion_ratio",
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
        self._run_token = None
        atexit.register(self._release_run_lock)

        self.master.title("Aerodynamic Simulation Automation Program")
        self.master.geometry("1000x780")
        self.master.minsize(880, 620)
        self.master.configure(fg_color=BG)
        self._traces = []  # (StringVar, trace id) pairs to drop when the screen changes

        # Todas as telas são construídas dentro deste container
        self.container = ctk.CTkFrame(self.master, fg_color=BG, corner_radius=0)
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
                         font=FONT_HINT, text_color=MUTED).pack(anchor="w")
            return
        if status["wsl_ok"] and status["openfoam_ok"]:
            banner = ctk.CTkFrame(frame, fg_color=QUEUE_BG, corner_radius=9,
                                  border_width=1, border_color=TRACK)
            banner.pack(fill="x")
            ctk.CTkLabel(banner, text="✓  WSL + OpenFOAM detected", font=FONT_HINT,
                         text_color=INK2).pack(anchor="w", padx=14, pady=8)
        else:
            banner = ctk.CTkFrame(frame, fg_color=ALERT_TINT, corner_radius=9,
                                  border_width=1, border_color=ALERT_BORDER)
            banner.pack(fill="x")
            ctk.CTkLabel(banner, wraplength=780, justify="left", font=FONT_HINT, text_color=ALERT_TEXT,
                         text=f"▲  {status['detail'] or 'WSL/OpenFOAM not detected.'} "
                              "See README.md for setup steps — simulations will fail without it.") \
                .pack(anchor="w", padx=14, pady=8)

    # ------------------------------------------------------------------ #
    # Helpers de UI
    # ------------------------------------------------------------------ #
    def clear_frame(self):
        for var, trace_id in self._traces:
            try:
                var.trace_remove("write", trace_id)
            except Exception:
                pass
        self._traces = []
        for widget in self.container.winfo_children():
            widget.destroy()

    def _watch(self, var, callback):
        """Call `callback` whenever `var` changes, for as long as this screen is shown."""
        trace_id = var.trace_add("write", lambda *_: callback())
        self._traces.append((var, trace_id))

    def _header(self, parent, title, subtitle=None, step=None):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(22, 12))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text=title, font=FONT_TITLE, text_color=INK, anchor="w").pack(fill="x")
        if subtitle:
            ctk.CTkLabel(titles, text=subtitle, font=FONT_LABEL, anchor="w", text_color=MUTED,
                         justify="left").pack(fill="x", pady=(3, 0))
        if step is not None:
            self._step_indicator(header, step).pack(side="right", anchor="n", pady=(6, 0))
        return header

    def _step_indicator(self, parent, current):
        strip = ctk.CTkFrame(parent, fg_color="transparent")
        for idx, name in enumerate(WIZARD_STEPS):
            color = ACCENT if idx == current else (MUTED if idx < current else BORDER_STRONG)
            dot = ctk.CTkFrame(strip, width=9, height=9, corner_radius=5, fg_color=color)
            dot.pack(side="left", padx=(0 if idx == 0 else 5, 0))
            if idx == current:
                ctk.CTkLabel(strip, text=name, font=FONT_HINT, text_color=ACCENT) \
                    .pack(side="left", padx=(5, 0))
        return strip

    def _card(self, parent, **pack_kwargs):
        card = ctk.CTkFrame(parent, corner_radius=11, fg_color=CARD)
        defaults = dict(fill="x", expand=False, padx=26, pady=8)
        defaults.update(pack_kwargs)
        card.pack(**defaults)
        return card

    def _caps_label(self, parent, text, **kwargs):
        opts = dict(font=FONT_CAPS, text_color=MUTED, anchor="w")
        opts.update(kwargs)
        return ctk.CTkLabel(parent, text=text.upper(), **opts)

    def _entry(self, parent, variable, mono=True, **kwargs):
        opts = dict(textvariable=variable, height=34, corner_radius=7, fg_color=SUNKEN,
                    border_color=TRACK, border_width=1, text_color=INK,
                    font=(FONT_MONO, 13) if mono else FONT_LABEL)
        opts.update(kwargs)
        return ctk.CTkEntry(parent, **opts)

    def _labeled_entry(self, parent, label_text, variable, hint=None, help_text=None):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        if help_text:
            head = ctk.CTkFrame(wrap, fg_color="transparent")
            head.pack(fill="x")
            self._caps_label(head, label_text).pack(side="left")
            icon = ctk.CTkLabel(head, text=" ⓘ", font=FONT_HINT, text_color=MUTED, cursor="hand2")
            icon.pack(side="left")
            _Tooltip(icon, help_text)
        else:
            self._caps_label(wrap, label_text).pack(fill="x")
        entry = self._entry(wrap, variable)
        entry.pack(fill="x", pady=(4, 0))
        if hint:
            ctk.CTkLabel(wrap, text=hint, font=FONT_HINT, anchor="w",
                         text_color=MUTED).pack(fill="x", pady=(2, 0))
        return wrap, entry

    def _primary_button(self, parent, text, command, **kwargs):
        opts = dict(font=FONT_BUTTON, height=38, corner_radius=8, fg_color=ACCENT,
                    hover_color=ACCENT_HOVER, text_color=BG)
        opts.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _secondary_button(self, parent, text, command, **kwargs):
        # "Ghost" button: 1px outline, no fill.
        opts = dict(font=FONT_BUTTON, height=34, corner_radius=7, fg_color="transparent",
                    hover_color=TRACK, border_width=1, border_color=BORDER_STRONG,
                    text_color=INK2)
        opts.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _link_button(self, parent, text, command, **kwargs):
        opts = dict(font=(FONT_FAMILY, 12), height=30, corner_radius=7, fg_color="transparent",
                    hover_color=TRACK, text_color=INK3, width=80)
        opts.update(kwargs)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _chip(self, parent, text, fg=TRACK, text_color=INK2):
        return ctk.CTkLabel(parent, text=text, font=(FONT_FAMILY, 10, "bold"), fg_color=fg,
                            text_color=text_color, corner_radius=4, height=20)

    def _segmented(self, parent, values, command=None, **kwargs):
        opts = dict(values=values, command=command, font=FONT_LABEL, fg_color=SUNKEN,
                    selected_color=BORDER_STRONG, selected_hover_color=BORDER_STRONG,
                    unselected_color=SUNKEN, unselected_hover_color=TRACK,
                    text_color=INK, corner_radius=8)
        opts.update(kwargs)
        return ctk.CTkSegmentedButton(parent, **opts)

    def _switch(self, parent, text, **kwargs):
        opts = dict(text=text, font=FONT_LABEL, text_color=INK2, progress_color=ACCENT,
                    button_color=INK, button_hover_color=INK2, fg_color=BORDER_STRONG)
        opts.update(kwargs)
        return ctk.CTkSwitch(parent, **opts)

    def _add_save_preset_button(self, parent):
        self._secondary_button(parent, "Save Preset...", self.save_preset, width=150) \
            .pack(anchor="w", padx=26, pady=(0, 10))

    def _add_parallel_toggle(self, parent, padx=26):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=padx, pady=(4, 10))
        self._switch(wrap, "Run angles in parallel", variable=self.parallel_var,
                     onvalue=True, offvalue=False).pack(anchor="w")
        ctk.CTkLabel(wrap, font=FONT_HINT, text_color=MUTED, anchor="w", justify="left",
                     text="Faster with several angles, but each angle already runs its own 2-process\n"
                          "OpenFOAM solve, so this uses much more CPU/RAM. Leave it off on a modest machine.") \
            .pack(anchor="w", pady=(4, 0))
        return wrap

    def _nav_bar(self, parent, back_command, next_text, next_command,
                 next_color=None, next_hover=None, extra=None):
        """Footer action bar: back link left; ghost extras + the primary action right."""
        bar = ctk.CTkFrame(parent, fg_color=SUNKEN, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        ctk.CTkFrame(bar, height=1, fg_color=TRACK, corner_radius=0).pack(fill="x", side="top")
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=26, pady=12)
        if back_command:
            self._link_button(inner, "← Back", back_command).pack(side="left")
        if next_command:
            self._primary_button(inner, next_text, next_command, width=190).pack(side="right")
        for text, command in reversed(extra or []):
            self._secondary_button(inner, text, command).pack(side="right", padx=(0, 10))
        return bar

    def _choice_card(self, parent, selected):
        """A card whose border lights up when `selected` is true."""
        return ctk.CTkFrame(parent, corner_radius=11, fg_color=CARD, border_width=1,
                            border_color=ACCENT if selected else TRACK)

    def _bind_click(self, widget, command):
        widget.bind("<Button-1>", lambda _e: command())
        for child in widget.winfo_children():
            if not isinstance(child, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkSegmentedButton)):
                self._bind_click(child, command)

    # ------------------------------------------------------------------ #
    # Tela principal
    # ------------------------------------------------------------------ #
    def main_menu(self):
        self.clear_frame()
        extra = [("Load Preset...", self.load_preset)]
        plots_dir = os.path.join(APP_DIR, "plots")
        if os.path.isdir(plots_dir) and any(f.lower().endswith(".png") for f in os.listdir(plots_dir)):
            extra.append(("View Last Results", self.results_viewer_screen))
        self._nav_bar(self.container, None, "Continue →", self._continue_from_setup, extra=extra)

        self._header(self.container, "Aerodynamic Simulation Automation Program",
                     "Define the airfoil geometry and the angles of attack to study.", step=0)

        self._env_banner = ctk.CTkFrame(self.container, fg_color="transparent")
        self._env_banner.pack(fill="x", padx=26, pady=(0, 10))
        self._populate_env_banner(self._env_banner)

        body = ctk.CTkFrame(self.container, fg_color="transparent")
        body.pack(fill="x", padx=26, pady=(0, 6))
        body.grid_columnconfigure(0, weight=3, uniform="setup")
        body.grid_columnconfigure(1, weight=2, uniform="setup")

        # ---- airfoil card ------------------------------------------------
        card = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        self._caps_label(card, "Airfoil").pack(fill="x", padx=18, pady=(16, 6))
        mode_names = ["NACA 4-digit", "Custom .dat file"]
        self._airfoil_seg = self._segmented(card, mode_names, command=self._set_airfoil_mode)
        self._airfoil_seg.pack(anchor="w", padx=18)
        self._airfoil_seg.set(mode_names[1] if self.airfoil == "airfoil_custom" else mode_names[0])

        self._airfoil_inputs = ctk.CTkFrame(card, fg_color="transparent")
        self._airfoil_inputs.pack(fill="x", padx=18, pady=(12, 0))
        self._naca_box = ctk.CTkFrame(self._airfoil_inputs, fg_color="transparent")
        self.naca_entry = self._entry(self._naca_box, self.naca_var, height=40,
                                      font=(FONT_MONO, 16), placeholder_text="0012")
        self.naca_entry.pack(fill="x")
        ctk.CTkLabel(self._naca_box, text="Four digits, e.g. 0012 (symmetric) or 2412 (cambered).",
                     font=FONT_HINT, text_color=MUTED, anchor="w").pack(fill="x", pady=(3, 0))
        self._file_box = ctk.CTkFrame(self._airfoil_inputs, fg_color="transparent")
        file_row = ctk.CTkFrame(self._file_box, fg_color="transparent")
        file_row.pack(fill="x")
        self._entry(file_row, self.file1_path, mono=False, height=40).pack(side="left", fill="x", expand=True)
        self._secondary_button(file_row, "Browse...", self.browse_file1, width=100, height=40) \
            .pack(side="left", padx=(8, 0))
        ctk.CTkLabel(self._file_box, text="A .dat file with the airfoil's x/y coordinates.",
                     font=FONT_HINT, text_color=MUTED, anchor="w").pack(fill="x", pady=(3, 0))

        self._caps_label(card, "Angle(s) of attack").pack(fill="x", padx=18, pady=(16, 4))
        self.angle_entry = self._entry(card, self.angle_var, height=38, font=(FONT_MONO, 14),
                                       placeholder_text="0, 2.5, 5, 10")
        self.angle_entry.pack(fill="x", padx=18)
        self._chips_row = ctk.CTkFrame(card, fg_color="transparent")
        self._chips_row.pack(fill="x", padx=18, pady=(8, 4))
        self._angle_note = ctk.CTkLabel(card, text="", font=FONT_HINT, text_color=ALERT_TEXT, anchor="w",
                                        justify="left", wraplength=380)
        self._angle_note.pack(fill="x", padx=18, pady=(0, 12))

        # ---- profile preview card ---------------------------------------
        side = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        side.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        self._caps_label(side, "Profile preview").pack(fill="x", padx=18, pady=(16, 6))
        self._profile_canvas = tk.Canvas(side, height=150, bg=SUNKEN, highlightthickness=0)
        self._profile_canvas.pack(fill="both", expand=True, padx=18)
        self._profile_canvas.bind("<Configure>", lambda _e: self._draw_profile())
        stats = ctk.CTkFrame(side, fg_color="transparent")
        stats.pack(fill="x", padx=18, pady=(10, 16))
        stats.grid_columnconfigure((0, 1), weight=1)
        self._cases_stat = ctk.CTkLabel(stats, text="0", font=(FONT_FAMILY, 20, "bold"),
                                        text_color=ACCENT, anchor="w")
        self._caps_label(stats, "Cases").grid(row=0, column=0, sticky="w")
        self._cases_stat.grid(row=1, column=0, sticky="w")
        self._caps_label(stats, "Solver").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(stats, text="simpleFoam", font=(FONT_FAMILY, 16, "bold"), text_color=INK2,
                     anchor="w").grid(row=1, column=1, sticky="w")

        # ---- mesh type cards --------------------------------------------
        self._caps_label(self.container, "Mesh generation").pack(fill="x", padx=26, pady=(14, 6))
        self._mesh_pick = "custom" if self.mesh_choice == "custom_mesh" else "standard"
        self._mesh_cards_row = ctk.CTkFrame(self.container, fg_color="transparent")
        self._mesh_cards_row.pack(fill="x", padx=26, pady=(0, 10))
        self._mesh_cards_row.grid_columnconfigure((0, 1), weight=1, uniform="mesh")
        self._render_mesh_cards()

        self._watch(self.naca_var, self._on_setup_changed)
        self._watch(self.angle_var, self._on_setup_changed)
        self._watch(self.file1_path, self._on_setup_changed)
        self._set_airfoil_mode(self._airfoil_seg.get())
        self._on_setup_changed()

    def _render_mesh_cards(self):
        for w in self._mesh_cards_row.winfo_children():
            w.destroy()
        options = [
            ("standard", "Standard Mesh", "VALIDATED",
             "Pre-tuned mesh, validated against NACA 0012 wind-tunnel data. Sized automatically "
             "for the Reynolds number. Fastest way to start."),
            ("custom", "Custom Mesh", "17 PARAMETERS",
             "Fine-tune every mesh parameter yourself. Recommended for advanced or compressible cases."),
        ]
        for col, (key, title, tag, desc) in enumerate(options):
            card = self._choice_card(self._mesh_cards_row, self._mesh_pick == key)
            card.grid(row=0, column=col, sticky="nsew", padx=(0, 9) if col == 0 else (9, 0))
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(14, 4))
            ctk.CTkLabel(top, text=title, font=FONT_SECTION, text_color=INK).pack(side="left")
            self._chip(top, tag, fg=ACCENT if key == "standard" else TRACK,
                       text_color=BG if key == "standard" else INK2).pack(side="left", padx=(10, 0))
            ctk.CTkLabel(card, text=desc, font=FONT_HINT, text_color=INK3, justify="left",
                         anchor="w", wraplength=380).pack(fill="x", padx=16, pady=(0, 14))
            self._bind_click(card, lambda k=key: self._pick_mesh(k))

    def _pick_mesh(self, key):
        self._mesh_pick = key
        self._render_mesh_cards()

    def _continue_from_setup(self):
        if self._mesh_pick == "custom":
            self.select_custom_mesh()
        else:
            self.select_standard_mesh()

    def _set_airfoil_mode(self, value):
        custom = value.startswith("Custom")
        self.airfoil = "airfoil_custom" if custom else "airfoil_NACA"
        self._naca_box.pack_forget()
        self._file_box.pack_forget()
        (self._file_box if custom else self._naca_box).pack(fill="x")
        self._draw_profile()

    def _on_setup_changed(self):
        if not hasattr(self, "_chips_row") or not self._chips_row.winfo_exists():
            return
        angles = []
        for part in self.angle_var.get().split(","):
            try:
                angles.append(float(part.strip()))
            except ValueError:
                pass
        for w in self._chips_row.winfo_children():
            w.destroy()
        for angle in angles[:12]:
            self._chip(self._chips_row, f"{angle:g}°", fg=TRACK, text_color=INK2) \
                .pack(side="left", padx=(0, 5))
        if len(angles) > 12:
            ctk.CTkLabel(self._chips_row, text=f"+{len(angles) - 12}", font=FONT_HINT,
                         text_color=MUTED).pack(side="left")
        n = len(angles)
        note = f"{n} case{'s' if n != 1 else ''}"
        last = getattr(self, "_last_case_seconds", None)
        if n and last:
            note += f"  ·  ≈ {functions.format_duration(last * n)} sequentially (from the last run)"
        ctk.CTkLabel(self._chips_row, text=("   " if n else "") + note, font=FONT_HINT,
                     text_color=MUTED).pack(side="left")
        self._cases_stat.configure(text=str(n))
        high = [a for a in angles if abs(a) >= 12]
        self._angle_note.configure(text=(
            f"▲ {', '.join(f'{a:g}°' for a in high)}: close to stall. A steady-state solver may need many more "
            "iterations here (the 15° case took ~3,000) or not settle at all.") if high else "")
        self._draw_profile()

    def _profile_points(self):
        """Closed contour (x, y) of the selected airfoil, or None if it can't be drawn."""
        try:
            if self.airfoil == "airfoil_custom":
                pts = []
                with open(self.file1_path.get(), "r") as fh:
                    for line in fh:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pts.append((float(parts[0]), float(parts[1])))
                            except ValueError:
                                pass
                return pts or None
            code = self.naca_var.get()
            if len(code) != 4 or not code.isdigit():
                return None
            xu, yu, xl, yl = functions.naca4digit(int(code[0]) / 100, int(code[1]) / 10,
                                                   int(code[2:]) / 100, 1.0, 80)
            # naca4digit returns each surface mirrored around the leading edge
            # (2n-1 points); like search_airfoil, keep only the first n of each:
            # upper TE->LE, then lower LE->TE.
            n = 80
            return list(zip(xu[:n], yu[:n])) + list(zip(xl[:n], yl[:n]))[::-1]
        except Exception:
            return None

    def _draw_profile(self):
        canvas = getattr(self, "_profile_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 40 or h < 40:
            return
        pts = self._profile_points()
        if not pts:
            canvas.create_text(w / 2, h / 2, text="Enter a 4-digit NACA code\nor pick a .dat file",
                               fill=MUTED, font=FONT_HINT, justify="center")
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1 = min(xs), max(xs)
        span = max(x1 - x0, 1e-9)
        pad = 18
        scale = (w - 2 * pad) / span
        cy = h / 2 - (max(ys) + min(ys)) / 2 * scale
        cy = min(max(cy, pad), h - pad)
        to_canvas = lambda p: (pad + (p[0] - x0) * scale, cy - p[1] * scale)
        canvas.create_line(pad, cy, w - pad, cy, fill=BORDER_STRONG, dash=(3, 3))
        flat = [c for p in pts for c in to_canvas(p)]
        canvas.create_polygon(flat, fill=CARD, outline=ACCENT, width=1.5)

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
        self._nav_bar(self.container, self.main_menu, "Create Mesh →", self.mesh_preview_screen,
                      extra=[("Save Preset...", self.save_preset)])

        self._header(self.container, "Custom Mesh Parameters",
                     "Adjust the block-mesh generation settings, then create the mesh.", step=1)

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
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        scroll.grid_columnconfigure((0, 1, 2), weight=1, uniform="meshcol")

        for idx, (title, fields) in enumerate(groups):
            card = ctk.CTkFrame(scroll, corner_radius=11, fg_color=CARD)
            card.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=6, pady=6)
            self._caps_label(card, title, text_color=ACCENT).pack(fill="x", padx=14, pady=(12, 2))
            for label, var in fields:
                wrap, entry = self._labeled_entry(card, label, var)
                wrap.pack(fill="x", padx=14, pady=(6, 4))
                self.entries[label] = entry  # Armazenando referências das entradas no dicionário
            ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

        info = ctk.CTkFrame(scroll, corner_radius=9, fg_color=QUEUE_BG, border_width=1, border_color=TRACK)
        info.grid(row=(len(groups) + 2) // 3, column=0, columnspan=3, sticky="ew", padx=6, pady=(6, 10))
        ctk.CTkLabel(info, font=FONT_HINT, text_color=INK3, justify="left", anchor="w", wraplength=820,
                     text="ⓘ  The outlet corner is realigned automatically for each angle of attack you run.")             .pack(fill="x", padx=14, pady=10)

    # ------------------------------------------------------------------ #
    # Tipo de simulação
    # ------------------------------------------------------------------ #
    def choose_simulation_type(self):
        self.clear_frame()
        self._nav_bar(self.container, self.main_menu, None, None)
        self._header(self.container, "Choose the Simulation Type",
                     "Pick the flow regime that matches your case.", step=3)

        row = ctk.CTkFrame(self.container, fg_color="transparent")
        row.pack(fill="x", padx=26, pady=10)
        row.grid_columnconfigure((0, 1), weight=1, uniform="type")

        options = [
            ("Incompressible", "For flows where density changes are negligible — typical in most "
             "low-speed aerodynamics cases.", ["M < 0.3", "5 inputs"], self.Incompressive_flow_variables_page),
            ("Compressible", "For flows with significant density variation — typical in high-speed / "
             "transonic cases.", ["M > 0.3", "8 inputs"], self.Compressive_flow_variables_page),
        ]
        for col, (title, desc, tags, command) in enumerate(options):
            selected = self.simulation_tipo == title
            card = self._choice_card(row, selected)
            card.grid(row=0, column=col, sticky="nsew", padx=(0, 9) if col == 0 else (9, 0))
            ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 17, "bold"), text_color=INK,
                         anchor="w").pack(fill="x", padx=20, pady=(18, 4))
            ctk.CTkLabel(card, text=desc, font=FONT_LABEL, text_color=INK3, justify="left",
                         anchor="w", wraplength=360).pack(fill="x", padx=20)
            chips = ctk.CTkFrame(card, fg_color="transparent")
            chips.pack(fill="x", padx=20, pady=(12, 8))
            for tag in tags:
                self._chip(chips, tag).pack(side="left", padx=(0, 6))
            self._primary_button(card, f"Select {title}", command).pack(fill="x", padx=20, pady=(6, 20))

    # ------------------------------------------------------------------ #
    # Pré-visualização da malha (qualidade + wireframe) antes de simular
    # ------------------------------------------------------------------ #
    def mesh_preview_screen(self):
        self.clear_frame()
        self._mesh_qualities = {}
        self._nav_bar(self.container, self.mesh_preview_back, "Continue →", self._continue_from_preview)
        self._header(self.container, "Mesh Preview",
                     "Review the mesh quality before running the simulation.", step=2)

        self._mesh_preview_angle = self.angles[0] if self.angles else 0.0

        if len(self.angles) > 1:
            switcher = ctk.CTkFrame(self.container, fg_color="transparent")
            switcher.pack(fill="x", padx=26, pady=(0, 8))
            self._caps_label(switcher, "Preview angle").pack(side="left", padx=(0, 10))
            angle_switcher = self._segmented(switcher, [f"{a:g}°" for a in self.angles],
                                             command=self._on_mesh_preview_angle_change)
            angle_switcher.pack(side="left")
            angle_switcher.set(f"{self._mesh_preview_angle:g}°")

        self._mesh_preview_body = ctk.CTkFrame(self.container, fg_color="transparent")
        self._mesh_preview_body.pack(fill="both", expand=True, padx=26, pady=(0, 10))
        self._render_mesh_preview_loading()

        threading.Thread(target=self._generate_mesh_preview_worker,
                          args=(self._mesh_preview_angle,), daemon=True).start()

    def _continue_from_preview(self):
        problems = []
        for angle, quality in getattr(self, "_mesh_qualities", {}).items():
            if not quality.get("blockmesh_ok"):
                problems.append(f"{angle:g}°: the mesh could not be generated")
            elif not quality.get("mesh_ok"):
                problems.append(f"{angle:g}°: checkMesh reported failures")
            elif (quality.get("max_nonortho") or 0) > 70:
                problems.append(f"{angle:g}°: max non-orthogonality {quality['max_nonortho']:.1f}° (above 70°)")
        if problems and not messagebox.askyesno(
                "Mesh quality warning",
                "The previewed mesh has problems:\n\n" + "\n".join(problems) +
                "\n\nThe standard mesh normally stays around 57-64°, so this usually means a custom "
                "parameter needs a look. Continue to the simulation anyway?"):
            return
        self.choose_simulation_type()

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
                    self.boundary_layer_thickness.get(), CUSTOM_MESH_FIRST_LAYER,
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
        wsl_work_dir = f"/tmp/aero_mesh_preview_{uuid.uuid4().hex[:8]}"
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
        self._mesh_qualities[angle] = quality

        body = ctk.CTkFrame(self._mesh_preview_body, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1, minsize=250)
        body.grid_rowconfigure(0, weight=1)

        plot_frame = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._render_mesh_plot(plot_frame, polygons, quality)

        info_frame = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        info_frame.grid(row=0, column=1, sticky="nsew")
        self._render_mesh_quality_panel(info_frame, quality)

    def _render_mesh_plot(self, parent, polygons, quality):
        from matplotlib.figure import Figure
        from matplotlib.collections import PolyCollection
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        fig = Figure(figsize=(5, 4.3), dpi=100)
        fig.patch.set_facecolor(CARD)
        ax = fig.add_subplot(111)
        ax.set_facecolor(SUNKEN)

        if polygons:
            xs = [p[0] for poly in polygons for p in poly]
            ys = [p[1] for poly in polygons for p in poly]
            coll = PolyCollection(polygons, facecolors="none", edgecolors="#7d766f", linewidths=0.3)
            ax.add_collection(coll)
            ax.set_xlim(max(-0.3, min(xs)), min(1.3, max(xs)))
            ax.set_ylim(max(-0.6, min(ys)), min(0.6, max(ys)))
        else:
            ax.text(0.5, 0.5, "Mesh preview unavailable", color=INK2,
                    ha="center", va="center", transform=ax.transAxes)

        ax.set_aspect("equal")
        ax.tick_params(colors=MUTED, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(TRACK)

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        # Matplotlib's own toolbar is a light-grey strip with dark icons; drive
        # the same actions from buttons that match the rest of the app instead.
        toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        toolbar.update()
        tools = ctk.CTkFrame(parent, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=(10, 0))
        self._secondary_button(tools, "Pan", toolbar.pan, width=60, height=28, font=(FONT_FAMILY, 12)) \
            .pack(side="left", padx=(0, 6))
        self._secondary_button(tools, "Zoom", toolbar.zoom, width=60, height=28, font=(FONT_FAMILY, 12)) \
            .pack(side="left", padx=(0, 6))
        self._secondary_button(tools, "Reset", toolbar.home, width=60, height=28, font=(FONT_FAMILY, 12)) \
            .pack(side="left")
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(6, 0))

        if polygons:
            total_cells = quality.get("cells")
            caption = f"Showing {len(polygons):,} near-field cells" + \
                      (f" (of {total_cells:,} total)." if total_cells else ".")
            ctk.CTkLabel(parent, text=caption, font=FONT_HINT, text_color=MUTED_TEXT) \
                .pack(padx=8, pady=(2, 8))

    def _render_mesh_quality_panel(self, parent, quality):
        self._caps_label(parent, "Mesh quality").pack(fill="x", padx=16, pady=(16, 8))

        if not quality.get("blockmesh_ok"):
            ctk.CTkLabel(parent, text="✗ Mesh generation failed", font=FONT_LABEL,
                         text_color=WARN_COLOR, anchor="w").pack(fill="x", padx=16, pady=(0, 4))
            ctk.CTkLabel(parent, text=quality.get("error") or "Unknown error.", font=FONT_HINT,
                         text_color=MUTED_TEXT, wraplength=260, justify="left", anchor="w") \
                .pack(fill="x", padx=16, pady=(0, 16))
            return

        ok = quality.get("mesh_ok")
        status_color = ACCENT if ok else ALERT
        status_text = "✓  Mesh OK" if ok else "▲  Mesh has warnings"
        ctk.CTkLabel(parent, text=status_text, font=(FONT_FAMILY, 17, "bold"), text_color=status_color,
                     anchor="w").pack(fill="x", padx=16, pady=(0, 12))

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
            ctk.CTkLabel(row, text=display_value, font=(FONT_MONO, 13), text_color=INK, anchor="e").pack(side="right")

        if quality.get("warnings"):
            self._caps_label(parent, "Warnings").pack(fill="x", padx=16, pady=(16, 4))
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

    # ------------------------------------------------------------------ #
    # Uma rodada por vez + diretorios de trabalho unicos no WSL
    # ------------------------------------------------------------------ #
    RUN_LOCK_PATH = os.path.join(APP_DIR, ".aerosim_run.lock")

    def _acquire_run_lock(self):
        """Simulations/ e os diretorios do WSL sao apagados e recriados a cada
        rodada, entao duas rodadas ao mesmo tempo destroem uma a outra."""
        ok, info = functions.acquire_run_lock(self.RUN_LOCK_PATH)
        if not ok:
            messagebox.showwarning(
                "A simulation is already running",
                f"Another instance of this app (PID {info.get('pid')}, started at {info.get('started')}) "
                "is running simulations in this folder. Starting a second run now would delete its data.\n\n"
                "Wait for it to finish, or close it first.")
            return False
        self._run_token = f"{int(time.time())}_{os.getpid()}"
        return True

    def _release_run_lock(self):
        functions.release_run_lock(self.RUN_LOCK_PATH)

    def _wsl_case_id(self, angle):
        """Name of this run's working directory (under /tmp/aero_sim_) for an angle."""
        token = getattr(self, "_run_token", None)
        return f"{token}_Angle_{angle}" if token else f"Angle_{angle}"

    def Simulation_Incompressible(self):
        self.simulation_tipo = "Incompressible"
        if not self.process_angles():  # Processa os ângulos
            return
        if not self._acquire_run_lock():
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
        if not self._acquire_run_lock():
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
            self._release_run_lock()
            return
        source_file = "mesh_standard"
        base_directory = "Simulations"
        if self.simulation_tipo == "Incompressible":
            flow_speed = self.flow_speed_var_I.get()
            Pressure = self.p_var_I.get()
            nut_value = self.nut_var.get()
            nutilda_value = self.nutilda_var.get()
            turbulence_intensity = self.tu_var_I.get() / 100.0
            nu_value_I = self.nu_var_I.get()
            standard_first_layer = functions.first_layer_thickness_for_flow(flow_speed, nu_value_I)
            standard_expansion_ratio = functions.expansion_ratio_for_flow(
                flow_speed, nu_value_I, target_yplus=self.yplus_var_I.get())
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
            standard_expansion_ratio = functions.expansion_ratio_for_flow(
                flow_speed, nu_value_c, target_yplus=self.yplus_var_c.get())

        self._init_progress_state()
        self._log_event(f"Preparing {len(self.angles)} case(s): {', '.join(f'{a:g}°' for a in self.angles)}")
        nu_used = nu_value_I if self.simulation_tipo == "Incompressible" else nu_value_c
        if self.mesh_choice == "standard_mesh" and nu_used:
            self._log_event(f"Standard mesh sized for Re ~ {flow_speed / nu_used:,.0f} "
                            f"(boundary-layer expansion ratio {standard_expansion_ratio:.4f})")

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
                    first_layer_thickness_val = CUSTOM_MESH_FIRST_LAYER
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
                                                         nut_value, nutilda_value, nu_value_I,
                                                         turbulence_intensity=turbulence_intensity)
                    functions.verify_initial_conditions(orig_directory_path, flow_speed)
                elif self.simulation_tipo == "Compressible":
                    functions.variables_compressible(orig_directory_path, angle, flow_speed, Pressure,
                                                       nut_value, T_value, omega_value, k_value,
                                                       alphat_value, nu_value_c)
                    functions.verify_initial_conditions(orig_directory_path, flow_speed)
            except Exception as e:
                messagebox.showerror("Mesh Generation Error",
                    f"Failed to generate mesh for angle {angle}: {e}\n\n"
                    "Check the mesh parameters (e.g. avoid zero values) and try again.")
                self._release_run_lock()
                return

            print(f"File '{source_file}' copied and renamed to '{destination_file_path}' after running blockMeshDirect for angle {angle}")
            self._log_event(f"{angle:g}°: mesh definition and flow conditions written")

        self._log_event("Case files ready — starting OpenFOAM in WSL")
        self.show_progress_screen()
        threading.Thread(target=self._run_simulations_worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Execução das simulações no WSL (roda em thread separada)
    # ------------------------------------------------------------------ #
    STAGE_LABELS = {"queued": "Queued", "preparing": "Preparing case", "blockMesh": "Meshing (blockMesh)",
                    "decomposePar": "Splitting domain (decomposePar)", "simpleFoam": "Solving",
                    "reconstructPar": "Merging results (reconstructPar)", "done": "Done", "failed": "Failed"}
    # Seconds without any change before a running angle is flagged as possibly stuck.
    STALL_SECONDS = {"simpleFoam": 120, "default": 300}

    def _init_progress_state(self):
        self._progress_log_lines = []
        self._progress_status_override = None
        self._live_data = {}
        self._progress_slots = 1
        self._run_started_at = time.monotonic()
        self._progress = {}
        for angle in self.angles:
            settings = functions.read_case_iteration_settings(
                os.path.join(APP_DIR, "Simulations", f"Angle_{angle}", "system", "controlDict"))
            delta_t, max_iter = settings if settings else (None, None)
            self._progress[angle] = {
                "stage": "queued", "iter": 0, "max_iter": max_iter, "delta_t": delta_t,
                "samples": [], "changed_at": time.monotonic(), "started_at": None,
                "ended_at": None, "coeff_rows": 0, "warned": False}

    def _log_event(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        try:
            print(line)
        except UnicodeEncodeError:
            # Windows consoles (cp1252) can't print every symbol; the console
            # echo must never be able to break the run.
            print(line.encode("ascii", "replace").decode("ascii"))
        self.master.after(0, self._append_log, line)

    def _append_log(self, line):
        self._progress_log_lines.append(line)
        last = getattr(self, "_log_last", None)
        if last is not None and last.winfo_exists():
            last.configure(text=line)
        box = getattr(self, "_progress_log_box", None)
        if box is not None and box.winfo_exists():
            box.configure(state="normal")
            box.insert("end", line + "\n")
            box.see("end")
            box.configure(state="disabled")

    def show_progress_screen(self):
        if not hasattr(self, "_progress") or set(self._progress) != set(self.angles):
            self._init_progress_state()
        self.clear_frame()
        self._selected_angle = self.angles[0]
        self._user_selected = False
        self._chart_dirty = True
        self._expanded = False
        n = len(self.angles)

        # ---- log strip (packed first so it always keeps its space) --------
        self._log_strip = ctk.CTkFrame(self.container, fg_color=SUNKEN, corner_radius=0)
        self._log_strip.pack(side="bottom", fill="x")
        ctk.CTkFrame(self._log_strip, height=1, fg_color=TRACK, corner_radius=0).pack(fill="x")
        strip_row = ctk.CTkFrame(self._log_strip, fg_color="transparent")
        strip_row.pack(fill="x", padx=26, pady=10)
        self._caps_label(strip_row, "Log").pack(side="left", padx=(0, 12))
        self._log_toggle = ctk.CTkButton(strip_row, text="Open full log ▾", width=110, height=24,
                                         font=FONT_HINT, fg_color="transparent", hover_color=TRACK,
                                         text_color=ACCENT, command=self._toggle_log_drawer)
        self._log_toggle.pack(side="right")
        self._log_last = ctk.CTkLabel(strip_row, text="", font=(FONT_MONO, 12), text_color=INK3, anchor="w")
        self._log_last.pack(side="left", fill="x", expand=True)
        self._progress_log_box = ctk.CTkTextbox(self.container, height=120, font=(FONT_MONO, 11),
                                                fg_color=SUNKEN, text_color=INK3, corner_radius=0)
        self._progress_log_box.insert("end", "".join(line + "\n" for line in self._progress_log_lines))
        self._progress_log_box.see("end")
        self._progress_log_box.configure(state="disabled")
        self._log_drawer_open = False
        if self._progress_log_lines:
            self._log_last.configure(text=self._progress_log_lines[-1])

        # ---- header: title left, the numbers people came for right --------
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(20, 10))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text="Running Simulations", font=FONT_TITLE, text_color=INK, anchor="w") \
            .pack(fill="x")
        mesh_name = "custom" if self.mesh_choice == "custom_mesh" else "standard"
        mode = "parallel" if self.parallel_var.get() and n > 1 else "sequential"
        ctk.CTkLabel(titles, text=f"{n} angle{'s' if n != 1 else ''}  ·  {mesh_name} mesh  ·  simpleFoam  ·  {mode}",
                     font=FONT_LABEL, text_color=MUTED, anchor="w").pack(fill="x", pady=(3, 0))
        stats = ctk.CTkFrame(header, fg_color="transparent")
        stats.pack(side="right")
        elapsed_box = ctk.CTkFrame(stats, fg_color="transparent")
        elapsed_box.pack(side="left", padx=(0, 26), anchor="s")
        self._caps_label(elapsed_box, "Elapsed", anchor="e").pack(anchor="e")
        self.progress_elapsed_label = ctk.CTkLabel(elapsed_box, text="0 s", font=(FONT_FAMILY, 17),
                                                   text_color=INK2)
        self.progress_elapsed_label.pack(anchor="e")
        remaining_box = ctk.CTkFrame(stats, fg_color="transparent")
        remaining_box.pack(side="left", anchor="s")
        self._caps_label(remaining_box, "Remaining", anchor="e").pack(anchor="e")
        self.progress_eta_label = ctk.CTkLabel(remaining_box, text="estimating…", font=FONT_HERO,
                                               text_color=ACCENT)
        self.progress_eta_label.pack(anchor="e")

        # ---- one segment per case ----------------------------------------
        segments = ctk.CTkFrame(self.container, fg_color="transparent")
        segments.pack(fill="x", padx=26, pady=(0, 10))
        segments.grid_columnconfigure(tuple(range(n)), weight=1, uniform="seg")
        self._progress_segments = {}
        for col, angle in enumerate(self.angles):
            cell = ctk.CTkFrame(segments, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 2, 0 if col == n - 1 else 2))
            bar = ctk.CTkProgressBar(cell, height=6, corner_radius=3, fg_color=TRACK, progress_color=ACCENT)
            bar.set(0)
            bar.pack(fill="x")
            ctk.CTkLabel(cell, text=f"{angle:g}°", font=(FONT_FAMILY, 11), text_color=MUTED, anchor="w") \
                .pack(fill="x", pady=(3, 0))
            self._progress_segments[angle] = bar
        # kept for scripts/tests that read the overall status line
        self.progress_status_label = ctk.CTkLabel(segments, text="", font=FONT_HINT, text_color=MUTED)
        self.progress_bar = ctk.CTkProgressBar(segments)

        # ---- body: case list | detail ------------------------------------
        self._progress_body = ctk.CTkFrame(self.container, fg_color="transparent")
        self._progress_body.pack(fill="both", expand=True, padx=26, pady=(0, 10))
        body = self._progress_body
        body.grid_columnconfigure(0, weight=0, minsize=286)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._progress_left = ctk.CTkFrame(body, fg_color="transparent", width=286)
        self._progress_left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._progress_left.grid_propagate(False)
        self._progress_left.grid_rowconfigure(0, weight=1)
        self._progress_left.grid_columnconfigure(0, weight=1)
        rows_holder = ctk.CTkScrollableFrame(self._progress_left, fg_color="transparent")
        rows_holder.grid(row=0, column=0, sticky="nsew")
        self._progress_rows = {}
        for angle in self.angles:
            self._progress_rows[angle] = self._build_case_row(rows_holder, angle)

        queue = ctk.CTkFrame(self._progress_left, corner_radius=9, fg_color=QUEUE_BG,
                             border_width=1, border_color=TRACK)
        queue.grid(row=1, column=0, sticky="sew", pady=(8, 0))
        qtop = ctk.CTkFrame(queue, fg_color="transparent")
        qtop.pack(fill="x", padx=13, pady=(12, 6))
        self._caps_label(qtop, "Queue").pack(side="left")
        self._queue_slots_label = ctk.CTkLabel(qtop, text="", font=FONT_HINT, text_color=INK3)
        self._queue_slots_label.pack(side="right")
        self._queue_slot_row = ctk.CTkFrame(queue, fg_color="transparent")
        self._queue_slot_row.pack(fill="x", padx=13)
        self._queue_note = ctk.CTkLabel(queue, text="", font=FONT_HINT, text_color=MUTED, anchor="w")
        self._queue_note.pack(fill="x", padx=13, pady=(6, 12))

        # ---- detail panel -------------------------------------------------
        self._progress_detail = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        self._progress_detail.grid(row=0, column=1, sticky="nsew")
        detail = self._progress_detail
        top = ctk.CTkFrame(detail, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 0))
        self._detail_top = top
        titles = ctk.CTkFrame(top, fg_color="transparent")
        self._detail_title = ctk.CTkLabel(titles, text="", font=(FONT_FAMILY, 19, "bold"),
                                          text_color=INK, anchor="w")
        self._detail_title.pack(fill="x")
        self._detail_line = ctk.CTkLabel(titles, text="", font=(FONT_FAMILY, 12), text_color=MUTED, anchor="w",
                                          justify="left", wraplength=380)
        self._detail_line.pack(fill="x", pady=(2, 0))
        self._expand_btn = self._secondary_button(top, "Expand", self._toggle_expand, width=92, height=28,
                                                  font=(FONT_FAMILY, 12))
        self._expand_btn.pack(side="right")
        self._secondary_button(top, "Case log", self._toggle_log_drawer, width=92, height=28,
                               font=(FONT_FAMILY, 12)).pack(side="right", padx=(0, 8))
        titles.pack(side="left", fill="x", expand=True)  # after the buttons, so they keep their width

        self._stuck_strip = ctk.CTkFrame(detail, corner_radius=8, fg_color=ALERT_TINT,
                                         border_width=1, border_color=ALERT_BORDER)
        self._stuck_label = ctk.CTkLabel(self._stuck_strip, text="", font=(FONT_FAMILY, 12),
                                         text_color=ALERT_TEXT, anchor="w", justify="left", wraplength=520)
        self._stuck_label.pack(fill="x", padx=12, pady=8)
        self._stuck_visible = False

        foot = ctk.CTkFrame(detail, fg_color="transparent")
        foot.pack(side="bottom", fill="x", padx=20, pady=(6, 16))
        self._cd_value = ctk.CTkLabel(foot, text="Cd  —", font=(FONT_FAMILY, 20, "bold"), text_color=ACCENT)
        self._cd_value.pack(side="left")
        self._cl_value = ctk.CTkLabel(foot, text="Cl  —", font=(FONT_FAMILY, 20, "bold"), text_color=INK)
        self._cl_value.pack(side="left", padx=(22, 0))
        self._chart_note = ctk.CTkLabel(foot, text="", font=(FONT_FAMILY, 12), text_color=MUTED, anchor="e")
        self._chart_note.pack(side="right")

        self._build_live_plot(detail)

        self._progress_token = object()
        self._select_case(self.angles[0], user=False)
        self._progress_tick(self._progress_token)

    def _build_case_row(self, parent, angle):
        row = ctk.CTkFrame(parent, corner_radius=9, fg_color="transparent")
        row.pack(fill="x", pady=2)
        stripe = ctk.CTkFrame(row, width=3, height=30, corner_radius=2, fg_color=TRACK)
        stripe.pack(side="left", fill="y", padx=(0, 10), pady=6)
        angle_label = ctk.CTkLabel(row, text=f"{angle:g}°", width=44, anchor="w",
                                   font=(FONT_FAMILY, 16, "bold"), text_color=INK)
        angle_label.pack(side="left")
        text_box = ctk.CTkFrame(row, fg_color="transparent")
        text_box.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=9)
        line = ctk.CTkFrame(text_box, fg_color="transparent")
        line.pack(fill="x")
        status = ctk.CTkLabel(line, text="Queued", anchor="w", font=(FONT_FAMILY, 12), text_color=INK2)
        status.pack(side="left", fill="x", expand=True)
        chip = self._chip(line, "STUCK", fg=ALERT, text_color=BG)
        bar = ctk.CTkProgressBar(text_box, height=3, corner_radius=2, fg_color=TRACK, progress_color=ACCENT)
        bar.set(0)
        bar.pack(fill="x", pady=(5, 0))
        widgets = dict(row=row, stripe=stripe, status=status, bar=bar, chip=chip, chip_shown=False)

        def hover(on):
            if angle != self._selected_angle:
                row.configure(fg_color=ROW_HOVER if on else "transparent")

        row.bind("<Enter>", lambda _e: hover(True))
        row.bind("<Leave>", lambda _e: hover(False))
        self._bind_click(row, lambda a=angle: self._select_case(a, user=True))
        return widgets

    def _select_case(self, angle, user=True):
        if user:
            self._user_selected = True
        self._selected_angle = angle
        self._chart_dirty = True
        for a, widgets in self._progress_rows.items():
            widgets["row"].configure(fg_color=CARD if a == angle else "transparent")
        self._refresh_progress_view()

    def _toggle_log_drawer(self):
        if not self._log_toggle.winfo_exists():
            return
        if self._log_drawer_open:
            self._progress_log_box.pack_forget()
            self._log_toggle.configure(text="Open full log ▾")
        else:
            self._progress_log_box.pack(side="bottom", fill="x", before=self._progress_body)
            self._progress_log_box.see("end")
            self._log_toggle.configure(text="Hide log ▴")
        self._log_drawer_open = not self._log_drawer_open

    def _toggle_expand(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._progress_left.grid_remove()
            self._progress_detail.grid(row=0, column=0, columnspan=2, sticky="nsew")
        else:
            self._progress_detail.grid(row=0, column=1, columnspan=1, sticky="nsew")
            self._progress_left.grid()
        self._expand_btn.configure(text="Collapse" if self._expanded else "Expand")

    def _progress_view_alive(self):
        label = getattr(self, "progress_eta_label", None)
        return label is not None and label.winfo_exists() and hasattr(self, "_progress_rows") \
            and bool(getattr(self, "_progress_token", None))

    def _progress_tick(self, token):
        if token is not getattr(self, "_progress_token", None) or not self._progress_view_alive():
            return
        self._refresh_progress_view()
        self.master.after(1000, self._progress_tick, token)

    def _set_overall_status(self, text):
        self._progress_status_override = text
        if self._progress_view_alive():
            self._refresh_progress_view()
            self._detail_line.configure(text=text)

    def _progress_poller(self, stop_event):
        # One wsl call per cycle covers every angle, so parallel runs cost no
        # more polling than a sequential one.
        run_ids = [self._wsl_case_id(angle) for angle in self.angles]
        command = functions.build_progress_poll_command(run_ids)
        while not stop_event.wait(2.5):
            try:
                r = subprocess.run(["wsl", "-e", "bash", "-c", command],
                                    capture_output=True, text=True, timeout=20)
            except Exception:
                continue
            snapshot = functions.parse_progress_snapshot(r.stdout or "")
            if snapshot:
                self.master.after(0, self._apply_progress_snapshot, snapshot)

    def _apply_progress_snapshot(self, snapshot):
        now = time.monotonic()
        for angle in self.angles:
            st = self._progress[angle]
            if st["stage"] in ("done", "failed"):
                continue
            info = snapshot.get(self._wsl_case_id(angle))
            if info is None:
                continue
            stage = functions.stage_from_logs(info["stages"])
            if stage != st["stage"]:
                self._progress_stage_changed(angle, st, stage, now)
            if stage in ("simpleFoam", "reconstructPar") and info["time"] is not None and st["delta_t"]:
                iteration = int(round(info["time"] / st["delta_t"]))
                if iteration != st["iter"]:
                    st["iter"] = iteration
                    st["changed_at"] = now
                    st["warned"] = False
                    st["samples"].append((now, iteration))
                    del st["samples"][:-60]
            data = functions.parse_live_coefficients(info["coeff"]) if info["coeff"].strip() else None
            if data and len(data["time"]) != st["coeff_rows"]:
                st["coeff_rows"] = len(data["time"])
                self._update_live_plot(angle, data)
        self._refresh_progress_view()

    def _progress_stage_changed(self, angle, st, stage, now):
        st["stage"] = stage
        st["changed_at"] = now
        st["warned"] = False
        if stage == "simpleFoam":
            limit = f", up to {st['max_iter']} iterations" if st["max_iter"] else ""
            message = f"solver started (simpleFoam{limit})"
        else:
            message = {"preparing": "preparing case files",
                       "blockMesh": "generating mesh (blockMesh)",
                       "decomposePar": "splitting domain for the 2-process solve (decomposePar)",
                       "reconstructPar": self._solve_stop_message(st)}.get(stage, stage)
        self._log_event(f"{angle:g}°: {message}")

    def _solve_stop_message(self, st):
        n, limit = st["iter"], st["max_iter"]
        if limit and n < limit * 0.99:
            why = f"stopped at iteration {n} (Cd and Cl settled; limit was {limit})"
        elif limit:
            why = f"reached the iteration limit ({limit}) without the stop criterion firing"
        else:
            why = f"finished at iteration {n}"
        return f"solve {why}, merging results (reconstructPar)"

    def _progress_angle_started(self, angle):
        st = self._progress[angle]
        now = time.monotonic()
        st["started_at"] = now
        st["changed_at"] = now
        if st["stage"] == "queued":
            st["stage"] = "preparing"
        self._log_event(f"{angle:g}°: started")
        self._refresh_progress_view()

    def _progress_angle_finished(self, angle, success):
        st = self._progress[angle]
        now = time.monotonic()
        st["ended_at"] = now
        st["stage"] = "done" if success else "failed"
        took = functions.format_duration(now - st["started_at"]) if st["started_at"] else "?"
        self._log_event(f"{angle:g}°: {'finished' if success else 'FAILED'} after {took}"
                        + ("" if success else " — see the console output for details"))
        self._refresh_progress_view()

    def _refresh_progress_view(self):
        if not self._progress_view_alive():
            return
        now = time.monotonic()
        total = len(self.angles)
        finished = running = queued = 0
        stuck_angles = {}
        infos = {}
        for angle in self.angles:
            st = self._progress[angle]
            stage = st["stage"]
            fraction = functions.run_progress_fraction(stage, st["iter"], st["max_iter"])
            finished += stage in ("done", "failed")
            queued += stage == "queued"
            running += stage not in ("done", "failed", "queued")

            stage_name = self.STAGE_LABELS.get(stage, stage)
            if stage == "simpleFoam":
                status = f"Solving · {st['iter']}" + (f"/{st['max_iter']}" if st["max_iter"] else "")
            elif stage == "done":
                status = "Done" + (f" in {functions.format_duration(st['ended_at'] - st['started_at'])}"
                                   if st["started_at"] and st["ended_at"] else "")
            else:
                status = stage_name if stage in ("queued", "failed") else \
                    f"{stage_name} · {functions.format_duration(now - st['changed_at'])}"

            stuck_for = None
            if stage not in ("done", "failed", "queued"):
                limit = self.STALL_SECONDS.get(stage, self.STALL_SECONDS["default"])
                idle = now - st["changed_at"]
                if idle > limit:
                    stuck_for = idle
                    stuck_angles[angle] = idle
                    if not st["warned"]:
                        st["warned"] = True
                        self._log_event(f"{angle:g}°: WARNING no progress for {functions.format_duration(idle)} "
                                        f"in stage '{stage_name}'")

            if stuck_for is not None:
                color = ALERT
            elif stage == "done":
                color = INK2
            elif stage == "failed":
                color = ALERT
            else:
                color = ACCENT
            infos[angle] = dict(status=status, stage=stage, stuck_for=stuck_for, fraction=fraction, color=color)

            widgets = self._progress_rows[angle]
            widgets["status"].configure(text=status, text_color=ALERT_TEXT if stuck_for is not None else INK2)
            widgets["bar"].configure(progress_color=color)
            widgets["bar"].set(fraction)
            widgets["stripe"].configure(fg_color=color if stage != "queued" else TRACK)
            if stuck_for is not None and not widgets["chip_shown"]:
                widgets["chip"].pack(side="right", padx=(6, 0))
                widgets["chip_shown"] = True
            elif stuck_for is None and widgets["chip_shown"]:
                widgets["chip"].pack_forget()
                widgets["chip_shown"] = False
            seg = self._progress_segments[angle]
            seg.configure(progress_color=color)
            seg.set(fraction)

        # Until the user picks a case, follow whichever one is being solved.
        if not self._user_selected:
            active = next((a for a in self.angles if self._progress[a]["stage"] == "simpleFoam"), None)
            if active is not None and active != self._selected_angle:
                self._selected_angle = active
                self._chart_dirty = True
                for a, w in self._progress_rows.items():
                    w["row"].configure(fg_color=CARD if a == active else "transparent")

        self._refresh_detail_panel(infos, now)

        # ---- header numbers ----------------------------------------------
        self.progress_elapsed_label.configure(text=functions.format_duration(now - self._run_started_at))
        if self._progress_status_override is not None:
            self.progress_eta_label.configure(text="—", font=FONT_HERO)
        else:
            eta = self._estimate_overall_eta()
            if finished == total:
                self.progress_eta_label.configure(text="—")
            elif eta is None:
                self.progress_eta_label.configure(text="estimating…", font=(FONT_FAMILY, 20, "bold"))
            else:
                self.progress_eta_label.configure(text=f"up to {functions.format_duration(eta)}", font=FONT_HERO)
        overall = f"{finished}/{total} finished  ·  {running} running  ·  {queued} queued"
        self.progress_status_label.configure(text=self._progress_status_override or overall)

        # ---- queue card --------------------------------------------------
        slots = max(1, getattr(self, "_progress_slots", 1))
        used = min(running, slots)
        self._queue_slots_label.configure(text=f"{used} of {slots} solver slot{'s' if slots != 1 else ''} in use")
        for w in self._queue_slot_row.winfo_children():
            w.destroy()
        for i in range(slots):
            self._queue_slot_row.grid_columnconfigure(i, weight=1)
            ctk.CTkFrame(self._queue_slot_row, height=5, corner_radius=3,
                         fg_color=ACCENT if i < used else TRACK).grid(row=0, column=i, sticky="ew", padx=2)
        done_times = [s["ended_at"] - s["started_at"] for s in self._progress.values()
                      if s["stage"] == "done" and s["started_at"] and s["ended_at"]]
        note = f"{queued} waiting" if queued else "nothing waiting"
        if done_times:
            average = sum(done_times) / len(done_times)
            self._last_case_seconds = average
            note += f"  ·  avg {functions.format_duration(average)} per case"
        self._queue_note.configure(text=note)

    def _refresh_detail_panel(self, infos, now):
        angle = self._selected_angle
        info = infos.get(angle)
        st = self._progress.get(angle)
        if info is None or st is None:
            return
        stage = info["stage"]
        self._detail_title.configure(text=f"{angle:g}°  —  {info['status']}")

        if stage == "simpleFoam":
            rate = functions.iteration_rate(st["samples"])
            line = f"Iteration {st['iter']}" + (f" (limit {st['max_iter']}, stops earlier once Cd/Cl settle)" if st["max_iter"] else "")
            if rate and st["max_iter"]:
                line += (f"  ·  up to ~{functions.format_duration((st['max_iter'] - st['iter']) / rate)} left"
                         f"  ·  {rate:.1f} it/s")
            else:
                line += "  ·  estimating time left…"
        elif stage == "queued":
            line = "Waiting for a free solver slot."
        elif stage == "done":
            line = "Finished — results were copied back."
        elif stage == "failed":
            line = "This case did not finish; see the log for details."
        else:
            line = f"Stage: {self.STAGE_LABELS.get(stage, stage)}"
        self._detail_line.configure(text=line)

        if info["stuck_for"] is not None:
            self._stuck_label.configure(
                text=f"No progress for {functions.format_duration(info['stuck_for'])} in "
                     f"“{self.STAGE_LABELS.get(stage, stage)}”. The case may be stuck — check the log, "
                     "or stop and rerun this angle if it doesn't move.")
            if not self._stuck_visible:
                self._stuck_strip.pack(fill="x", padx=20, pady=(10, 0), after=self._detail_top)
                self._stuck_visible = True
        elif self._stuck_visible:
            self._stuck_strip.pack_forget()
            self._stuck_visible = False

        data = self._live_data.get(angle)
        if data:
            self._cd_value.configure(text=f"Cd  {data['cd'][-1]:.4f}")
            self._cl_value.configure(text=f"Cl  {data['cl'][-1]:.4f}")
            self._chart_note.configure(text=f"{len(data['time'])} samples")
        else:
            self._cd_value.configure(text="Cd  —")
            self._cl_value.configure(text="Cl  —")
            self._chart_note.configure(text="")
        if self._chart_dirty:
            self._draw_selected_chart()

    def _estimate_overall_eta(self):
        rates = {angle: functions.iteration_rate(st["samples"])
                 for angle, st in self._progress.items() if st["stage"] == "simpleFoam"}
        known = [r for r in rates.values() if r]
        if not known:
            return None
        avg_rate = sum(known) / len(known)
        running, queued, per_angle = [], 0, []
        for angle, st in self._progress.items():
            max_iter = st["max_iter"]
            if not max_iter or st["stage"] in ("done", "failed"):
                continue
            if st["stage"] == "queued":
                queued += 1
                per_angle.append(max_iter / avg_rate)
            elif st["stage"] == "simpleFoam":
                running.append((max_iter - st["iter"]) / (rates.get(angle) or avg_rate))
            elif st["stage"] == "reconstructPar":
                running.append(0.0)
            else:
                running.append(max_iter / avg_rate)
        each = sum(per_angle) / len(per_angle) if per_angle else 0.0
        return functions.estimate_total_eta(running, queued, each, self._progress_slots)

    def _build_live_plot(self, parent):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        # One chart for the selected case (click another row to switch); every
        # case keeps its own series in _live_data so switching is instant.
        self._live_fig = Figure(figsize=(6, 2.6), dpi=100, constrained_layout=True)
        self._live_fig.patch.set_facecolor(SUNKEN)
        self._live_plot_canvas = FigureCanvasTkAgg(self._live_fig, master=parent)
        widget = self._live_plot_canvas.get_tk_widget()
        widget.configure(bg=SUNKEN, highlightthickness=0)
        widget.pack(fill="both", expand=True, padx=20, pady=(12, 4))
        self._draw_selected_chart()

    def _draw_selected_chart(self):
        canvas = getattr(self, "_live_plot_canvas", None)
        if canvas is None or not canvas.get_tk_widget().winfo_exists():
            return
        self._chart_dirty = False
        fig = self._live_fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor(SUNKEN)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8, length=0)
        ax.grid(axis="y", color=TRACK, linewidth=0.8)
        ax.set_axisbelow(True)

        data = self._live_data.get(self._selected_angle)
        if data and len(data["time"]) < 2:
            data = None  # one point draws nothing useful; wait for a second sample
        if not data:
            stage = self._progress.get(self._selected_angle, {}).get("stage", "queued")
            hint = "Waiting for the first coefficients…" if stage == "simpleFoam" else \
                "Convergence appears once the solver starts."
            ax.text(0.5, 0.5, hint, color=MUTED, ha="center", va="center", fontsize=10,
                    transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            iters = [t / self._progress[self._selected_angle]["delta_t"]
                     if self._progress[self._selected_angle].get("delta_t") else t for t in data["time"]]
            ax.plot(iters, data["cd"], color=ACCENT, linewidth=1.6, label="Cd")
            ax2 = ax.twinx()
            ax2.plot(iters, data["cl"], color=INK2, linewidth=1.6, label="Cl")
            ax2.tick_params(colors=MUTED, labelsize=8, length=0)
            for spine in ax2.spines.values():
                spine.set_visible(False)
            ax.set_xlabel("iteration", color=MUTED, fontsize=8)
            # The first ~10% is start-up transient (Cl swings to -1 or worse); scale the axes
            # to what comes after it so the part that shows convergence stays readable.
            skip = max(2, len(iters) // 10)
            for axis, series in ((ax, data["cd"]), (ax2, data["cl"])):
                tail = list(series)[skip:] if len(series) > skip + 3 else list(series)
                lo, hi = min(tail), max(tail)
                pad = (hi - lo) * 0.15 or max(abs(hi) * 0.05, 1e-4)
                axis.set_ylim(lo - pad, hi + pad)
            handles = ax.get_lines() + ax2.get_lines()
            ax.legend(handles, [h.get_label() for h in handles], loc="upper right", fontsize=8,
                      frameon=False, labelcolor=INK3)
        canvas.draw_idle()

    def _update_live_plot(self, angle, data):
        self._live_data[angle] = data
        if angle == getattr(self, "_selected_angle", None):
            self._chart_dirty = True

    def _run_simulations_worker(self):
        try:
            self._run_simulations_worker_inner()
        finally:
            self._release_run_lock()

    def _run_simulations_worker_inner(self):
        base_directory = os.path.join(APP_DIR, "Simulations")
        total = len(self.angles)

        stop_poll = threading.Event()
        threading.Thread(target=self._progress_poller, args=(stop_poll,), daemon=True).start()
        try:
            if self.parallel_var.get() and total > 1:
                failed_angles = self._run_simulations_parallel(base_directory, total)
            else:
                failed_angles = self._run_simulations_sequential(base_directory, total)
        finally:
            stop_poll.set()

        self._log_event("All simulations finished — extracting results and generating plots...")
        self.master.after(0, self._set_overall_status, "Extracting results and generating plots...")
        try:
            self.extract_results(base_directory)
        except Exception as e:
            self._log_event(f"ERROR extracting results: {e}")
            self.master.after(0, self._set_overall_status, f"⚠ Result extraction failed: {e}")
            raise

        self._log_event("Results ready")
        self.master.after(0, self._on_simulation_complete, failed_angles)

    def _run_simulations_sequential(self, base_directory, total):
        self._progress_slots = 1
        failed_angles = []
        for angle in self.angles:
            angle_directory = os.path.join(base_directory, f"Angle_{angle}")
            os.makedirs(angle_directory, exist_ok=True)  # Cria o diretório se não existir
            self.master.after(0, self._progress_angle_started, angle)
            success = self.run_commands_in_wsl(angle_directory)
            self.master.after(0, self._progress_angle_finished, angle, success)
            if not success:
                failed_angles.append(angle)
        return failed_angles

    def _run_simulations_parallel(self, base_directory, total):
        # Each angle's own OpenFOAM solve is already 2-process (decomposePar +
        # simpleFoam -parallel), so running several angles at once multiplies
        # that -- cap concurrency instead of launching every angle at the same
        # time, to keep this usable on a modest machine.
        max_workers = min(total, max(1, (os.cpu_count() or 4) // 2), 4)
        self._progress_slots = max_workers
        self._log_event(f"Running {total} angles in parallel, up to {max_workers} at a time")
        failed_angles = []

        def run_one(angle):
            angle_directory = os.path.join(base_directory, f"Angle_{angle}")
            os.makedirs(angle_directory, exist_ok=True)
            self.master.after(0, self._progress_angle_started, angle)
            success = self.run_commands_in_wsl(angle_directory)
            self.master.after(0, self._progress_angle_finished, angle, success)
            return angle, success

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_one, angle) for angle in self.angles]
            for future in concurrent.futures.as_completed(futures):
                angle, success = future.result()
                if not success:
                    failed_angles.append(angle)
        return failed_angles

    def _on_simulation_complete(self, failed_angles):
        self.clear_frame()
        total = len(self.angles)
        solved = total - len(failed_angles)
        elapsed = time.monotonic() - getattr(self, "_run_started_at", time.monotonic())
        self._nav_bar(self.container, self.main_menu, "New Simulation", self.main_menu,
                      extra=[("Open Results Folder", self.open_results_folder)])
        self._header(self.container, "Simulation Finished", "Results and plots have been saved.", step=6)

        rows = self._read_results_table()
        not_converged = [r["angle"] for r in rows if not r["converged"]]

        hero = ctk.CTkFrame(self.container, fg_color="transparent")
        hero.pack(fill="x", padx=26, pady=(0, 10))
        ctk.CTkLabel(hero, text=f"{solved} / {total}", font=FONT_HERO,
                     text_color=ACCENT if not failed_angles else ALERT).pack(side="left")
        text = ctk.CTkFrame(hero, fg_color="transparent")
        text.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(text, text=f"angles solved in {functions.format_duration(elapsed)}",
                     font=(FONT_FAMILY, 15, "bold"), text_color=INK, anchor="w").pack(fill="x")
        notes = []
        if failed_angles:
            notes.append(f"{len(failed_angles)} failed: {', '.join(f'{a:g}°' for a in failed_angles)} — "
                         "check the log or console output.")
        if not_converged:
            notes.append("Not fully converged: " + ", ".join(f"{a}°" for a in not_converged) +
                         " — treat their averages with care.")
        if self.last_validation:
            mean_err, used, excluded = functions.mean_validation_error(self.last_validation["summary"])
            if mean_err is None:
                notes.append("No converged angle to compare with the reference dataset.")
            else:
                extra = (f"; {excluded} point(s) left out: not converged or reference ~0" if excluded else "")
                notes.append(f"Compared with a bundled reference dataset: {mean_err:.1f}% average difference over "
                             f"{used} point(s){extra}. ({self.last_validation['citation']})")
        target_var = getattr(self, "yplus_var_I" if self.simulation_tipo != "Compressible" else "yplus_var_c", None)
        measured = [r["yplus"] for r in rows if r.get("yplus") is not None]
        if target_var is not None and measured and self.mesh_choice == "standard_mesh":
            target = self._safe_get(target_var)
            if target:
                notes.append(f"Wall y+ target {target:g}; measured average {sum(measured) / len(measured):.1f}.")
        if notes:
            ctk.CTkLabel(text, text="\n".join(notes), font=(FONT_FAMILY, 12), text_color=MUTED,
                         justify="left", anchor="w", wraplength=700).pack(fill="x")

        self._build_results_body(self.container, rows)

        if failed_angles:
            messagebox.showwarning("Simulation Finished with Errors",
                f"Simulation failed for angle(s): {failed_angles}.\n"
                "Check the console output for details.")

    def open_results_folder(self):
        results_dir = os.path.join(APP_DIR, "Results")
        if os.path.isdir(results_dir):
            os.startfile(results_dir)
        else:
            messagebox.showinfo("Results Folder", "No results folder found yet.")

    def _stop_info(self, case_name, last_time):
        """(iterations run, iteration limit) for a case, from its controlDict."""
        for base in (os.path.join(APP_DIR, "Simulations", case_name, "system", "controlDict"),
                     os.path.join(APP_DIR, "core", "Standard", "Incompressible", "system", "controlDict")):
            settings = functions.read_case_iteration_settings(base)
            if settings:
                delta_t, limit = settings
                return int(round(last_time / delta_t)), limit
        return None, None

    @staticmethod
    def _stop_text(row):
        """Why the case ended, in words: the most useful column of the results table."""
        iters, limit = row.get("iters"), row.get("limit")
        if row["cd"] is None:
            return "no results"
        at_limit = bool(limit and iters is not None and iters >= limit * 0.99)
        if row["converged"] and not at_limit:
            return f"✓ converged · {iters} it"
        if row["converged"]:
            return f"✓ stable at limit · {iters} it"
        return f"✕ not converged · {iters} it" + (" (limit)" if at_limit else "")

    def _read_results_table(self):
        """Rows of Results/results.txt as dicts (angle label, Cd, Cl, y+ avg, converged)."""
        path = os.path.join(APP_DIR, "Results", "results.txt")
        rows = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return rows
        for line in lines:
            if not line.strip() or line.startswith("#") or ": " not in line:
                continue
            name, rest = line.split(": ", 1)
            vals = rest.split("\t")
            if len(vals) < 16:
                continue
            try:
                numbers = [float(v) for v in vals]
            except ValueError:
                continue
            cd, cl, yplus, conv = numbers[1], numbers[4], numbers[13], numbers[15]
            iters, limit = self._stop_info(name, numbers[0])
            if cd != cd:  # nan: no coefficients were produced for this angle
                rows.append(dict(angle=name.replace("Angle_", ""), cd=None, cl=None, ld=None,
                                 yplus=None, converged=False, iters=None, limit=None))
                continue
            rows.append(dict(angle=name.replace("Angle_", ""), cd=cd, cl=cl,
                             ld=(cl / cd if cd else None), yplus=yplus, converged=bool(conv),
                             iters=iters, limit=limit))
        return rows

    def _build_results_body(self, parent, rows=None):
        """Coefficient table (left) + plot picker and viewer (right)."""
        if rows is None:
            rows = self._read_results_table()
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=26, pady=(0, 10))
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ---- coefficients table -------------------------------------------
        if rows:
            table = ctk.CTkScrollableFrame(body, corner_radius=11, fg_color=CARD, width=520)
            table.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
            headers = ["Angle", "Cd", "Cl", "Cl/Cd", "y+ avg", "How it ended"]
            widths = [56, 70, 70, 56, 56, 176]
            for col, (h, w) in enumerate(zip(headers, widths)):
                self._caps_label(table, h, width=w).grid(row=0, column=col, sticky="w", padx=(8, 0), pady=(8, 6))
            for r, row in enumerate(rows, start=1):
                def fmt(v, spec):
                    return "—" if v is None else format(v, spec)
                cells = [f"{row['angle']}°", fmt(row["cd"], ".5f"), fmt(row["cl"], ".4f"),
                         fmt(row["ld"], ".1f"), fmt(row["yplus"], ".1f")]
                for col, text in enumerate(cells):
                    ctk.CTkLabel(table, text=text, width=widths[col], anchor="w",
                                 font=(FONT_MONO, 13), text_color=INK if col == 0 else INK2) \
                        .grid(row=r, column=col, sticky="w", padx=(8, 0), pady=3)
                ok = row["converged"]
                ctk.CTkLabel(table, text=self._stop_text(row), font=(FONT_MONO, 12), anchor="w",
                             text_color=INK2 if ok else ALERT_TEXT, width=widths[5]) \
                    .grid(row=r, column=5, sticky="w", padx=(8, 0))

        # ---- plots --------------------------------------------------------
        plots_dir = os.path.join(APP_DIR, "plots")
        files = os.listdir(plots_dir) if os.path.isdir(plots_dir) else []
        files = sorted((f for f in files if f.lower().endswith(".png")), key=self._plot_sort_key)
        right = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        right.grid(row=0, column=1, sticky="nsew")
        if not files:
            ctk.CTkLabel(right, text="No plots found yet — run a simulation first.",
                         font=FONT_LABEL, text_color=MUTED).pack(expand=True)
            return
        names = [os.path.splitext(f)[0] for f in files]
        chips = ctk.CTkScrollableFrame(right, orientation="horizontal", height=44, fg_color="transparent")
        chips.pack(fill="x", padx=10, pady=(8, 0))
        self._plot_chip_buttons = {}
        for name in names:
            btn = ctk.CTkButton(chips, text=name.replace("_", " "), height=26, width=20, corner_radius=13,
                                font=(FONT_FAMILY, 12), fg_color=TRACK, hover_color=BORDER_STRONG,
                                text_color=INK2, command=lambda n=name: self._on_result_plot_selected(n))
            btn.pack(side="left", padx=(0, 6))
            self._plot_chip_buttons[name] = btn
        self._result_image_frame = right
        self._result_image_label = ctk.CTkLabel(right, text="")
        self._result_image_label.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._on_result_plot_selected(names[0])

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
                "tu_pct": self.tu_var_I.get(),
                "yplus": self.yplus_var_I.get(),
            }
        if hasattr(self, "flow_speed_var_c"):
            preset["flow_compressible"] = {
                "velocity": self.flow_speed_var_c.get(), "p": self.p_var_c.get(), "t": self.t_var.get(),
                "alphat": self.alphat_var.get(), "k": self.k_var.get(), "nut": self.nut_var_c.get(),
                "omega": self.omega_var.get(), "nu": self.nu_var_c.get(),
                "yplus": self.yplus_var_c.get(),
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
                self.tu_var_I = tk.DoubleVar(value=flow_i.get("tu_pct", DEFAULT_TURBULENCE_INTENSITY_PCT))
                self.nu_var_I = tk.DoubleVar(value=flow_i.get("nu", 1e-5))
                self.yplus_var_I = tk.DoubleVar(value=flow_i.get("yplus", functions.DEFAULT_TARGET_YPLUS))

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
                self.yplus_var_c = tk.DoubleVar(value=flow_c.get("yplus", functions.DEFAULT_TARGET_YPLUS))
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
        self._nav_bar(self.container, self.main_menu, None, None,
                      extra=[("Open Results Folder", self.open_results_folder)])
        self._header(self.container, "Results", "Browse the results of the last simulation.", step=6)
        self._build_results_body(self.container)

    @staticmethod
    def _plot_sort_key(filename):
        name = os.path.splitext(filename)[0]
        return (RESULT_PLOT_ORDER.index(name) if name in RESULT_PLOT_ORDER else len(RESULT_PLOT_ORDER), name)

    def _on_result_plot_selected(self, name):
        for key, btn in getattr(self, "_plot_chip_buttons", {}).items():
            if btn.winfo_exists():
                btn.configure(fg_color=ACCENT if key == name else TRACK,
                              text_color=BG if key == name else INK2)
        path = os.path.join(APP_DIR, "plots", f"{name}.png")
        try:
            img = Image.open(path)
        except Exception as e:
            self._result_image_label.configure(image=None, text=f"Could not open {name}.png: {e}")
            return
        frame = self._result_image_frame
        frame.update_idletasks()
        max_w = max(frame.winfo_width() - 30, 360)
        max_h = max(frame.winfo_height() - 70, 260)
        scale = min(max_w / img.width, max_h / img.height, 1.0)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self._result_image_label.configure(image=ctk_img, text="")
        self._result_image_label.image = ctk_img  # manter referência (senão o GC apaga a imagem)

    def run_commands_in_wsl(self, directory):
        unix_path = directory.replace("\\", "/").replace("C:/", "/mnt/c/")
        run_id = os.path.basename(directory.rstrip("\\/"))
        if getattr(self, "_run_token", None):
            run_id = f"{self._run_token}_{run_id}"
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
    # Propriedades do escoamento (Incompressível / Compressível)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_get(var, default=None):
        try:
            return var.get()
        except (tk.TclError, ValueError):
            return default

    def _flow_screen(self, title, run_command, speed_var, nu_var, basic_fields, adv_fields,
                     adv_columns, reset_advanced, temperature_var=None):
        self.clear_frame()
        self._nav_bar(self.container, self.choose_simulation_type, "Run Simulation ▸", run_command,
                      extra=[("Save Preset...", self.save_preset)])
        self._header(self.container, title, "Set the flow properties for this run.", step=4)

        body = ctk.CTkFrame(self.container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=26, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=290)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        # ---- velocity: the one input that matters, so it leads ----------
        hero = ctk.CTkFrame(left, corner_radius=11, fg_color=CARD)
        hero.pack(fill="x", pady=(0, 10))
        self._caps_label(hero, "Flow velocity").pack(fill="x", padx=18, pady=(16, 4))
        speed_row = ctk.CTkFrame(hero, fg_color="transparent")
        speed_row.pack(fill="x", padx=18)
        self._entry(speed_row, speed_var, height=46, font=(FONT_MONO, 20), border_color=BORDER_STRONG) \
            .pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(speed_row, text="m/s", font=FONT_LABEL, text_color=MUTED).pack(side="left", padx=(10, 0))
        helper = ctk.CTkLabel(hero, text="", font=FONT_HINT, text_color=INK3, anchor="w")
        helper.pack(fill="x", padx=18, pady=(6, 0))

        def update_helper():
            if not helper.winfo_exists():
                return
            u, nu = self._safe_get(speed_var), self._safe_get(nu_var)
            if not u or not nu or nu <= 0:
                helper.configure(text="Reynolds and Mach numbers appear here once the velocity is set.")
                return
            temp = self._safe_get(temperature_var, 288.15) if temperature_var is not None else 288.15
            sound = (1.4 * 287.05 * max(temp, 1.0)) ** 0.5
            text = f"Re ≈ {u / nu:,.0f}  (chord = 1 m)   ·   Mach ≈ {abs(u) / sound:.2f}"
            if u / nu < 9e5:
                text += "\nLow Re: below ~9e5 the wall refinement stays fixed (uniform boundary-layer cells)."
            helper.configure(text=text, justify="left")

        for var in (speed_var, nu_var) + ((temperature_var,) if temperature_var is not None else ()):
            self._watch(var, update_helper)
        update_helper()

        if basic_fields:
            grid = ctk.CTkFrame(hero, fg_color="transparent")
            grid.pack(fill="x", padx=12, pady=(10, 0))
            grid.grid_columnconfigure(tuple(range(len(basic_fields))), weight=1)
            for idx, (label, var) in enumerate(basic_fields):
                w, _ = self._labeled_entry(grid, label, var)
                w.grid(row=0, column=idx, sticky="ew", padx=6)
        ctk.CTkFrame(hero, height=16, fg_color="transparent").pack()

        # ---- advanced parameters, hidden until asked for -----------------
        self._switch(left, "Show advanced parameters",
                     command=lambda: self._toggle_advanced(reset_advanced)).pack(anchor="w", pady=(4, 6))
        self._adv_frame = ctk.CTkFrame(left, corner_radius=11, fg_color=CARD)
        grid = ctk.CTkFrame(self._adv_frame, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=12)
        grid.grid_columnconfigure(tuple(range(adv_columns)), weight=1)
        for idx, field in enumerate(adv_fields):
            label, var = field[0], field[1]
            w, _ = self._labeled_entry(grid, label, var, help_text=field[2] if len(field) > 2 else None)
            w.grid(row=idx // adv_columns, column=idx % adv_columns, sticky="ew", padx=6, pady=6)
        self._adv_anchor = ctk.CTkFrame(left, height=1, fg_color="transparent")
        self._adv_anchor.pack(fill="x")

        self._add_parallel_toggle(left, padx=0)

        # ---- run summary rail --------------------------------------------
        rail = ctk.CTkFrame(body, corner_radius=11, fg_color=CARD)
        rail.grid(row=0, column=1, sticky="new")
        self._caps_label(rail, "Run summary").pack(fill="x", padx=18, pady=(16, 8))
        self._summary_values = {}
        for key in ("Airfoil", "Angles", "Mesh", "Solver", "Execution"):
            row = ctk.CTkFrame(rail, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=3)
            ctk.CTkLabel(row, text=key, font=FONT_HINT, text_color=MUTED, width=70, anchor="w").pack(side="left")
            value = ctk.CTkLabel(row, text="", font=FONT_LABEL, text_color=INK, anchor="e",
                                 justify="right", wraplength=180)
            value.pack(side="right", fill="x", expand=True)
            self._summary_values[key] = value
        ctk.CTkFrame(rail, height=12, fg_color="transparent").pack()
        self._watch(self.parallel_var, self._refresh_run_summary)
        self._refresh_run_summary()

    def _refresh_run_summary(self):
        values = getattr(self, "_summary_values", None)
        if not values or not values["Airfoil"].winfo_exists():
            return
        if self.airfoil == "airfoil_custom":
            airfoil = os.path.basename(self.file1_path.get()) or "custom file"
        else:
            airfoil = f"NACA {self.naca_var.get()}" if self.naca_var.get() else "NACA"
        angles = ", ".join(f"{a:g}°" for a in self.angles) or "—"
        parallel = self.parallel_var.get() and len(self.angles) > 1
        values["Airfoil"].configure(text=airfoil)
        values["Angles"].configure(text=f"{angles}\n({len(self.angles)} case{'s' if len(self.angles) != 1 else ''})")
        values["Mesh"].configure(text="Custom" if self.mesh_choice == "custom_mesh" else "Standard")
        values["Solver"].configure(text="simpleFoam · SA")
        values["Execution"].configure(text="Parallel" if parallel else "Sequential")

    def _toggle_advanced(self, reset_advanced):
        if self._adv_frame.winfo_ismapped():
            self._adv_frame.pack_forget()
            reset_advanced()  # hidden advanced values fall back to their defaults
        else:
            self._adv_frame.pack(fill="x", pady=(0, 10), before=self._adv_anchor)

    def Incompressive_flow_variables_page(self):
        # Só cria com valores padrão na primeira vez -- preserva edições do
        # usuário (ou um preset carregado) ao navegar de volta pra cá.
        if not hasattr(self, "flow_speed_var_I"):
            self.flow_speed_var_I = tk.DoubleVar()
            self.p_var_I = tk.DoubleVar(value=0.0)
            self.nut_var = tk.DoubleVar(value=DEFAULT_NUT_NUTILDA)
            self.nutilda_var = tk.DoubleVar(value=DEFAULT_NUT_NUTILDA)
            self.tu_var_I = tk.DoubleVar(value=DEFAULT_TURBULENCE_INTENSITY_PCT)
            self.nu_var_I = tk.DoubleVar(value=1e-5)
            self.yplus_var_I = tk.DoubleVar(value=functions.DEFAULT_TARGET_YPLUS)

        self._flow_screen(
            "Incompressible Simulation", self.Simulation_Incompressible,
            self.flow_speed_var_I, self.nu_var_I, [],
            [("nu", self.nu_var_I), ("P", self.p_var_I), ("Nut", self.nut_var),
             ("Turbulence intensity (%)", self.tu_var_I, TU_HELP),
             ("Wall y+ target", self.yplus_var_I, YPLUS_HELP)],
            adv_columns=4, reset_advanced=self.toggle_additional_fields_reset)

    def toggle_additional_fields_reset(self):
        self.nut_var.set(DEFAULT_NUT_NUTILDA)  # Define valores padrão caso escondido
        self.nutilda_var.set(DEFAULT_NUT_NUTILDA)
        self.tu_var_I.set(DEFAULT_TURBULENCE_INTENSITY_PCT)
        self.p_var_I.set(0.0)
        self.nu_var_I.set(1e-5)
        self.yplus_var_I.set(functions.DEFAULT_TARGET_YPLUS)

    def Compressive_flow_variables_page(self):
        if not hasattr(self, "flow_speed_var_c"):
            self.flow_speed_var_c = tk.DoubleVar()
            self.p_var_c = tk.DoubleVar(value=1e5)
            self.t_var = tk.DoubleVar(value=298)
            self.alphat_var = tk.DoubleVar(value=0.1)
            self.k_var = tk.DoubleVar(value=0.1)
            self.nut_var_c = tk.DoubleVar(value=0.1)
            self.omega_var = tk.DoubleVar(value=0.1)
            self.nu_var_c = tk.DoubleVar(value=1e-6)
            self.yplus_var_c = tk.DoubleVar(value=functions.DEFAULT_TARGET_YPLUS)

        self._flow_screen(
            "Compressible Simulation", self.simulation_Compressible,
            self.flow_speed_var_c, self.nu_var_c,
            [("P (pressure)", self.p_var_c), ("T (temperature K)", self.t_var)],
            [("Alphat", self.alphat_var), ("k", self.k_var), ("Nut", self.nut_var_c),
             ("Omega", self.omega_var), ("Nu", self.nu_var_c), ("Wall y+ target", self.yplus_var_c, YPLUS_HELP)],
            adv_columns=3, reset_advanced=self.toggle_additional_fields_compressive_reset,
            temperature_var=self.t_var)

    def toggle_additional_fields_compressive_reset(self):
        # Define valores padrão caso escondido
        self.alphat_var.set(0.1)
        self.k_var.set(0.1)
        self.nut_var_c.set(0.1)
        self.omega_var.set(0.1)
        self.nu_var_c.set(1e-6)
        self.yplus_var_c.set(functions.DEFAULT_TARGET_YPLUS)

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
