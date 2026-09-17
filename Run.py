import os
import subprocess
import shutil
import threading
import tkinter as tk
from tkinter import messagebox, filedialog

import customtkinter as ctk

import functions  # type: ignore

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

        self.master.title("Aerodynamic Simulation Automation Program")
        self.master.geometry("920x720")
        self.master.minsize(780, 560)

        # Todas as telas são construídas dentro deste container
        self.container = ctk.CTkFrame(self.master, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.main_menu()

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
        self._primary_button(std_card, "Use Standard Mesh", self.Mesh_Padrao) \
            .pack(pady=16, padx=16, fill="x")

        custom_card = ctk.CTkFrame(mesh_row, corner_radius=12)
        custom_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(custom_card, text="Custom Mesh", font=FONT_SECTION).pack(pady=(16, 4))
        ctk.CTkLabel(custom_card, justify="center", text_color=MUTED_TEXT, font=FONT_HINT,
                     text="Fine-tune every mesh parameter yourself.\nRecommended for advanced/compressible cases.") \
            .pack(padx=16)
        self._primary_button(custom_card, "Use Custom Mesh", self.Mesh_custom) \
            .pack(pady=16, padx=16, fill="x")

    def browse_file1(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        self.file1_path.set(path)
        self.airfoil = 'airfoil_custom'

    def Mesh_Padrao(self):
        self.mesh_choice = "malha_padrão"
        self.search_airfoil()
        self.clear_frame()
        self.escolha_tipo_simulacao()

    # ------------------------------------------------------------------ #
    # Tela de malha customizada
    # ------------------------------------------------------------------ #
    def Mesh_custom(self):
        self.mesh_choice = "malha_custom"
        self.clear_frame()
        if not self.process_angles():
            return
        self.search_airfoil()

        self._header(self.container, "Custom Mesh Parameters",
                     "Adjust the block-mesh generation settings, then create the mesh.")

        self.entries = {}  # Garantindo que self.entries é um dicionário vazio antes de começar

        # Definindo os atributos da instância DoubleVar com valores padrão
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

        self._nav_bar(self.container, self.main_menu, "Create Mesh →", self.escolha_tipo_simulacao)

    # ------------------------------------------------------------------ #
    # Tipo de simulação
    # ------------------------------------------------------------------ #
    def escolha_tipo_simulacao(self):
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
    # Geração de malha / preparo de dados (lógica preservada)
    # ------------------------------------------------------------------ #
    def search_airfoil(self):
        naca_code = self.naca_var.get()
        if self.airfoil == "airfoil_NACA":
            if len(naca_code) != 4 or not naca_code.isdigit():
                messagebox.showerror("Error:", "Please enter a valid 4-digit NACA code.")
                self.main_menu()
                return

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
                return

            with open("coordenadas.dat", "w") as file:
                for i in range(len(x)):
                    file.write(f"{x[i]} {y[i]}\n")

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
        source_directory = "Padrão\\Incompressivel"
        target_directory = "Simulador"
        self.clear_and_create_angle_directories(target_directory, source_directory)
        print(f"Starting simulation with angles: {self.angles}")
        self.execute_mesh_operations()

    def simulation_Compressible(self):
        self.simulation_tipo = "Compressible"
        if not self.process_angles():  # Processa os ângulos
            return
        source_directory = "Padrão\\Compressivel"
        target_directory = "Simulador"
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
            angle_folder = os.path.join(target_path, f"Angulo_{angle}")
            shutil.copytree(source_path, angle_folder)

    def execute_mesh_operations(self):
        if not self.process_angles():
            return
        source_file = "mesh_padrao"
        base_directory = "Simulador"
        if self.simulation_tipo == "Incompressible":
            flow_speed = self.flow_speed_var_I.get()
            Pressure = self.p_var_I.get()
            nut_value = self.nut_var.get()
            nutilda_value = self.nutilda_var.get()
            nu_value_I = self.nu_var_I.get()
        elif self.simulation_tipo == "Compressible":
            flow_speed = self.flow_speed_var_c.get()
            Pressure = self.p_var_c.get()
            nut_value = self.nut_var_c.get()
            omega_value = self.omega_var.get()
            nu_value_c = self.nu_var_c.get()
            alphat_value = self.alphat_var.get()
            T_value = self.t_var.get()
            k_value = self.k_var.get()

        for angle in self.angles:
            angle_directory_path = os.path.join(base_directory, f"Angulo_{angle}")
            system_directory_path = os.path.join(angle_directory_path, "system")
            orig_directory_path = os.path.join(angle_directory_path, "0.orig")
            os.makedirs(system_directory_path, exist_ok=True)

            try:
                if self.mesh_choice == "malha_padrão":
                    functions.blockMeshDirect(angle)
                elif self.mesh_choice == "malha_custom":
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

    def _set_progress(self, done, total, angle):
        self.progress_bar.set(done / total if total else 0)
        self.progress_status_label.configure(
            text=f"Angle {angle}°  —  {done}/{total} simulation(s) completed")

    def _run_simulations_worker(self):
        base_directory = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Simulador")
        failed_angles = []
        total = len(self.angles)

        for i, angle in enumerate(self.angles, start=1):
            angle_directory = os.path.join(base_directory, f"Angulo_{angle}")
            os.makedirs(angle_directory, exist_ok=True)  # Cria o diretório se não existir
            success = self.run_commands_in_wsl(angle_directory)
            if not success:
                failed_angles.append(angle)
            self.master.after(0, self._set_progress, i, total, angle)

        base_directory = os.path.join(os.path.dirname(__file__), "Simulador")
        self.extrair_dados(base_directory)

        self.master.after(0, self._on_simulation_complete, failed_angles)

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

        actions = ctk.CTkFrame(self.container, fg_color="transparent")
        actions.pack(fill="x", padx=30, pady=(10, 20), side="bottom")
        self._secondary_button(actions, "Open Results Folder", self.open_results_folder, width=220) \
            .pack(side="left")
        self._primary_button(actions, "Back to Main Menu", self.main_menu, width=200).pack(side="right")

        if failed_angles:
            messagebox.showwarning("Simulation Finished with Errors",
                f"Simulation failed for angle(s): {failed_angles}.\n"
                "Check the console output for details.")
        else:
            messagebox.showinfo("Simulation Complete:", "All simulations have been successfully completed!")

    def open_results_folder(self):
        results_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Resultados")
        if os.path.isdir(results_dir):
            os.startfile(results_dir)
        else:
            messagebox.showinfo("Results Folder", "No results folder found yet.")

    def run_commands_in_wsl(self, directory):
        unix_path = directory.replace("\\", "/").replace("C:/", "/mnt/c/")
        command = f"cd {unix_path} && ./run_simulation.sh"  # Chama o script que você criou
        try:
            subprocess.run(["wsl", "bash", "-c", command], check=True)
            print(f"Simulation completed in the directory {directory}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error executing simulation in the directory {directory}: {e}")
            print("Please check that the path, permissions, and script are correct.")
            return False
        except FileNotFoundError:
            print("WSL executable not found. Ensure WSL is installed and available in PATH.")
            return False

    def arquivo(self):
        args = {key: float(self.entries[key].get()) for key in self.entries}
        functions.blockMeshDirect_Custom(alpha=5, **args)

    # ------------------------------------------------------------------ #
    # Incompressível
    # ------------------------------------------------------------------ #
    def Incompressive_flow_variables_page(self):
        self.clear_frame()
        self._header(self.container, "Incompressible Simulation", "Set the flow properties for this run.")

        self.flow_speed_var_I = tk.DoubleVar()
        self.p_var_I = tk.DoubleVar(value=0.0)
        self.nut_var = tk.DoubleVar(value=0.14)
        self.nutilda_var = tk.DoubleVar(value=0.14)
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

        self.nav_bar_I = self._nav_bar(self.container, self.main_menu, "Run Simulation",
                                        self.Simulation_Incompressible,
                                        next_color=RUN_COLOR, next_hover=RUN_HOVER)

    def toggle_additional_fields(self):
        if self.additional_fields_frame.winfo_ismapped():
            self.additional_fields_frame.pack_forget()  # Esconde os campos
            self.nut_var.set(0.14)  # Define valores padrão caso escondido
            self.nutilda_var.set(0.14)
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
    def extrair_dados(self, base_directory):
        vf_directory = os.path.join(base_directory, "..", "Resultados")
        resultados_path = os.path.join(vf_directory, "resultados.txt")

        if not os.path.exists(vf_directory):
            os.makedirs(vf_directory)

        with open(resultados_path, "w") as resultados_file:
            resultados_file.write("# Angulo_n: Time\tCd\tCd(f)\tCd(r)\tCl\tCl(f)\tCl(r)\tCmPitch\tCmRoll\tCmYaw\tCs\tCs(f)\tCs(r)\n")

        with open(resultados_path, "a") as resultados_file:
            for angle in self.angles:
                angle_folder = f"Angulo_{angle}"
                angle_directory_path = os.path.join(base_directory, angle_folder)

                if not os.path.exists(angle_directory_path):
                    os.makedirs(angle_directory_path)

                resultados_file.write(f"{angle_folder}: ")

                coefficient_path = os.path.join(angle_directory_path, "postProcessing", "forceCoeffs", "0", "coefficient.dat")

                # Número de colunas de dados esperadas (Time, Cd, Cd(f), Cd(r), Cl, Cl(f), Cl(r), CmPitch, CmRoll, CmYaw, Cs, Cs(f), Cs(r))
                num_result_columns = 13
                missing_data_row = "\t".join(["nan"] * num_result_columns) + "\n"

                if os.path.isfile(coefficient_path):
                    with open(coefficient_path, "r") as coeff_file:
                        lines = coeff_file.readlines()
                        if lines:
                            resultados_file.write(lines[-1])
                        else:
                            print(f"Warning: {coefficient_path} is empty, skipping angle {angle}")
                            resultados_file.write(missing_data_row)
                else:
                    print(f"Warning: no results found for angle {angle} ({coefficient_path})")
                    resultados_file.write(missing_data_row)

        functions.plot_data_from_txt(resultados_path)


if __name__ == "__main__":
    root = ctk.CTk()
    app = App(root)
    root.mainloop()
