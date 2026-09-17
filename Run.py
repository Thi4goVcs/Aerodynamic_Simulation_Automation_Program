import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
from tqdm import tqdm
import os
import subprocess
import functions # type: ignore
import shutil

class App:
    def __init__(self, master):
        self.master = master
        self.naca_var = tk.StringVar()
        self.angle_var = tk.StringVar()
        self.angles = []
        self.simulation_tipo = None
        self.airfoil = "airfoil_NACA"
        self.file1_path = tk.StringVar(value='coordenadas.dat')
        self.mesh_choice = None # Variável para armazenar a escolha de malha
        self.master.title("Aerodynamic Simulation Automation Program")
        self.entries = {}  # Inicializando o dicionário aqui
        self.main_menu()

    def clear_frame(self):
        for widget in self.master.winfo_children():
            widget.destroy()

    def main_menu(self):
        self.clear_frame()

        file_frame = tk.Frame(self.master)
        file_frame.pack(pady=10)
        tk.Label(file_frame, text="file:", font=('Arial', 14)).pack(side=tk.LEFT)
        tk.Entry(file_frame, textvariable=self.file1_path, font=('Arial', 14)).pack(side=tk.LEFT)
        tk.Button(file_frame, text="search", command=self.browse_file1).pack(side=tk.LEFT, padx=10)

        tk.Label(self.master, text="Naca:", font=('Arial', 14)).pack(pady=10)
        self.naca_entry = tk.Entry(self.master, textvariable=self.naca_var, font=('Arial', 14))
        self.naca_entry.pack(pady=10)

        tk.Label(self.master, text="Angle(s)", font=('Arial', 14)).pack(pady=10)
        self.angle_entry = tk.Entry(self.master, textvariable=self.angle_var, font=('Arial', 14))
        self.angle_entry.pack(pady=10)

        tk.Button(self.master, text="Standard Mesh", font=('Arial', 14), command=self.Mesh_Padrao).pack(side=tk.LEFT, padx=20, pady=20)
        tk.Button(self.master, text="Custom Mesh", font=('Arial', 14), command=self.Mesh_custom).pack(side=tk.RIGHT, padx=20, pady=20)

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

    def Mesh_custom(self):
        self.mesh_choice = "malha_custom"
        self.clear_frame()
        if not self.process_angles():
            return
        self.search_airfoil()
        left_frame = tk.Frame(self.master)
        right_frame = tk.Frame(self.master)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

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
        
        variables = [
                ("Distance to inlet (x chord length)", self.distance_to_inlet),
                ("Distance to outlet (x chord length)", self.distance_to_outlet),
                ("Cell size at leading edge", self.cell_size_at_leading_edge),
                ("Cell size at trailing edge", self.cell_size_at_trailing_edge),
                ("Cell size in middle", self.cell_size_in_middle),
                ("Separating point position (from leading point)", self.separating_point_position),
                ("Boundary layer thickness", self.boundary_layer_thickness),
                ("First layer thickness", self.first_layer_thickness),
                ("Expansion ratio", self.expansion_ratio),
                ("Max cell size in inlet", self.max_cell_size_in_inlet),
                ("Max cell size in outlet", self.max_cell_size_in_outlet),
                ("Max cell size in inlet & outlet", self.max_cell_size_in_inlet_and_outlet),
                ("Number of mesh on boundary layer 1", self.num_mesh_on_boundary_layer_1),
                ("Number of mesh out boundary layer 2", self.num_mesh_on_boundary_layer_2),
                ("Number of mesh at tail", self.num_mesh_at_tail),
                ("Number of mesh in leading", self.num_mesh_in_leading),
                ("Number of mesh in trailing", self.num_mesh_in_trailing),
            ]

        for index, (var, var_name) in enumerate(variables):
            target_frame = left_frame if index % 2 == 0 else right_frame
            frame = tk.Frame(target_frame)
            frame.pack(fill=tk.X, padx=5, pady=5)
            label = tk.Label(frame, text=var, font=('Arial', 12))
            label.pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=('Arial', 12), textvariable=var_name)
            entry.pack(side=tk.RIGHT, expand=True, fill=tk.X)
            self.entries[var] = entry  # Armazenando referências das entradas no dicionário

        button_frame = tk.Frame(self.master)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(button_frame, text="Back", font=('Arial', 14), command=self.main_menu).pack(side=tk.LEFT, padx=10, pady=20)
        tk.Button(button_frame, text="Create mesh", font=('Arial', 14), command=self.escolha_tipo_simulacao).pack(side=tk.RIGHT, padx=10, pady=20)

    def escolha_tipo_simulacao(self):
        self.clear_frame()

        # Descrição geral da escolha de tipo de simulação
        tk.Label(self.master, text="Choose the type of simulation you want to run:",
                font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=2, pady=20, sticky="w")

        # Descrição para Simulação Compressível
        tk.Label(self.master, text="Compressible Simulation: Use this option to simulate flows where density variations are significant, such as in high-speed flows around aerodynamic objects.",
                font=('Arial', 14), wraplength=500, justify="left").grid(row=1, column=0, columnspan=2, pady=10, sticky="w")
        tk.Button(self.master, text="Compressible Simulation", font=('Arial', 14),
                command=self.Compressive_flow_variables_page).grid(row=2, column=0, padx=20, pady=20, sticky="w")

        # Descrição para Simulação Incompressível
        tk.Label(self.master, text="Incompressible Simulation: Choose this option for simulations of flows where density changes are negligible, typical in many low-speed flows.",
                font=('Arial', 14), wraplength=500, justify="left").grid(row=3, column=0, columnspan=2, pady=10, sticky="w")
        tk.Button(self.master, text="Incompressible Simulation", font=('Arial', 14),
                command=self.Incompressive_flow_variables_page).grid(row=4, column=0, padx=20, pady=20, sticky="w")

        # Botão para voltar ao menu principal
        tk.Button(self.master, text="back", font=('Arial', 14), command=self.main_menu).grid(row=5, column=0, padx=10, pady=20, sticky="w")

        # Ajustar a coluna para expandir e ocupar espaço disponível
        self.master.grid_columnconfigure(0, weight=1)
        self.master.grid_columnconfigure(1, weight=1)

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
            # f.write("NACA {:04d} Airfoil M={:.1f}% P={:.1f}% T={:.1f}%\n".format(int(m*1000), m*100, p*100, t*100))
            # f.write("# x-coordinate y-coordinate\n")
                for i in range(num_points):
                   f.write("{:.6f} {:.6f}\n".format(xu[i], yu[i]))
                for i in range(num_points-1, -1, -1):
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

            # f.write("# x-coordinate y-coordinate\n")
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
        source_directory = "Padrão\\Incompressivel"  # Caminho para a pasta de onde os arquivos serão copiados
        target_directory = "Simulador"  # Caminho para a pasta que será limpa e onde serão criadas subpastas
        self.clear_and_create_angle_directories(target_directory, source_directory)
        print(f"Starting simulation with angles: {self.angles}")
        self.execute_mesh_operations()
        # Adicione aqui o código para iniciar a simulação usando esses valores

    def simulation_Compressible(self):
        self.simulation_tipo = "Compressible"
        if not self.process_angles():  # Processa os ângulos
            return
        source_directory = "Padrão\\Compressivel"  # Caminho para a pasta de onde os arquivos serão copiados
        target_directory = "Simulador"  # Caminho para a pasta que será limpa e onde serão criadas subpastas
        self.clear_and_create_angle_directories(target_directory, source_directory)
        print(f"Starting simulation with angles: {self.angles}")
        self.execute_mesh_operations()
        # Adicione aqui o código para iniciar a simulação usando esses valores

    
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
        source_file = "mesh_padrao"  # Caminho do arquivo a ser copiado
        base_directory = "Simulador"
        if self.simulation_tipo == "Incompressible":
            flow_speed = self.flow_speed_var_I.get()
            Pressure=self.p_var_I.get()
            nut_value=self.nut_var.get()
            nutilda_value=self.nutilda_var.get()
            nu_value_I=self.nu_var_I.get()
        elif self.simulation_tipo == "Compressible":
            flow_speed = self.flow_speed_var_c.get()
            Pressure=self.p_var_c.get()
            nut_value=self.nut_var_c.get()
            omega_value=self.omega_var.get()
            nu_value_c=self.nu_var_c.get()
            alphat_value=self.alphat_var.get()
            T_value=self.t_var.get()
            k_value=self.k_var.get()

        for angle in self.angles:
            # Caminho para o diretório do ângulo dentro da pasta "Simulador"
            angle_directory_path = os.path.join(base_directory, f"Angulo_{angle}")
            # Caminho para a subpasta "System" dentro do diretório do ângulo
            system_directory_path = os.path.join(angle_directory_path, "system")
            orig_directory_path = os.path.join(angle_directory_path, "0.orig")
            # Cria o diretório "System" se não existir
            os.makedirs(system_directory_path, exist_ok=True)

            try:
                # Executa a função blockMeshDirect para o ângulo atual
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


                # Define o caminho do arquivo de destino com o novo nome 'ovo' dentro da pasta "System"
                destination_file_path = os.path.join(system_directory_path, "blockMeshDict")

                # Copia o arquivo para o diretório "System" do ângulo com o novo nome
                shutil.copy(source_file, destination_file_path)
                            # Executa a função blockMeshDirect para o ângulo atual
                if self.simulation_tipo == "Incompressible":
                    functions.variables_incompressible(orig_directory_path, angle, flow_speed,Pressure,nut_value,nutilda_value,nu_value_I)
                elif self.simulation_tipo == "Compressible":

                    functions.variables_compressible(orig_directory_path, angle, flow_speed,Pressure,nut_value,T_value,omega_value,k_value,alphat_value,nu_value_c)
            except Exception as e:
                messagebox.showerror("Mesh Generation Error",
                    f"Failed to generate mesh for angle {angle}: {e}\n\n"
                    "Check the mesh parameters (e.g. avoid zero values) and try again.")
                return

            print(f"File '{source_file}' copied and renamed to '{destination_file_path}' after running blockMeshDirect for angle {angle}")

        self.run_simulations()


    def run_simulations(self):
        base_directory = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Simulador")
        failed_angles = []

        # Configurando a barra de progresso
        with tqdm(total=len(self.angles), desc="Simulações") as pbar:
            for angle in self.angles:
                angle_directory = os.path.join(base_directory, f"Angulo_{angle}")
                os.makedirs(angle_directory, exist_ok=True)  # Cria o diretório se não existir
                if not self.run_commands_in_wsl(angle_directory):
                    failed_angles.append(angle)
                pbar.update(1)  # Atualiza a barra de progresso a cada iteração

        # Caminho do diretório Simulador
        base_directory = os.path.join(os.path.dirname(__file__), "Simulador")
        # Chama a função passando o diretório base
        self.extrair_dados(base_directory)

        if failed_angles:
            messagebox.showwarning("Simulation Finished with Errors",
                f"Simulation failed for angle(s): {failed_angles}.\n"
                "Check the console output for details.")
        else:
            messagebox.showinfo("Simulation Complete:", "All simulations have been successfully completed!")


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
        # Substitua "alpha" por um valor adequado ou adicione uma entrada de usuário para ele
        functions.blockMeshDirect_Custom(alpha=5, **args)  # Substitua `alpha=5` pelo valor correto conforme necessário


    def Incompressive_flow_variables_page(self):
        self.clear_frame()

        # Definições de variáveis com StringVar para armazenar os valores
        self.flow_speed_var_I = tk.DoubleVar()
        self.p_var_I = tk.DoubleVar(value="0.0")
        self.nut_var = tk.DoubleVar(value="0.14")  # Valor padrão
        self.nutilda_var = tk.DoubleVar(value="0.14")  # Valor padrão
        self.nu_var_I = tk.DoubleVar(value="1e-5")  # Valor padrão

        # Criação dos campos de entrada
        tk.Label(self.master, text="Flow velocity (m/s):", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.master, textvariable=self.flow_speed_var_I, font=('Arial', 14)).pack(pady=5)

        # Criação dos campos adicionais escondidos para "nu" e "nutilda"
        self.additional_fields_frame = tk.Frame(self.master)
        self.additional_fields_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        self.additional_fields_frame.pack_forget()  # Esconde inicialmente

        tk.Label(self.additional_fields_frame, text="nu:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame, textvariable=self.nu_var_I, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame, text="P:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame, textvariable=self.p_var_I, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame, text="Nut:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame, textvariable=self.nut_var, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame, text="Nutilda:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame, textvariable=self.nutilda_var, font=('Arial', 14)).pack(pady=5)

        # Botão para revelar/esconder os campos adicionais
        tk.Button(self.master, text="+", font=('Arial', 14), command=self.toggle_additional_fields).pack(pady=20)

        # Botão de submissão para processar os dados
        tk.Button(self.master, text="Run simulation", font=('Arial', 14), command=self.Simulation_Incompressible).pack(pady=20)

        tk.Button(self.master, text="Back", font=('Arial', 14), command=self.main_menu).pack(side=tk.LEFT, padx=10, pady=20)

    def toggle_additional_fields(self):
        if self.additional_fields_frame.winfo_ismapped():
            self.additional_fields_frame.pack_forget()  # Esconde os campos
            self.nut_var.set("0.14")  # Define valores padrão caso escondido
            self.nutilda_var.set("0.14")
            self.p_var_I.set("0.0")
            self.nu_var_I.set("1e-5")
        else:
            self.additional_fields_frame.pack(pady=10, fill=tk.BOTH, expand=True)  # Mostra os campos



    def Compressive_flow_variables_page(self):
        self.clear_frame()

        # Definições de variáveis com StringVar para armazenar os valores
        self.flow_speed_var_c = tk.DoubleVar()
        self.p_var_c = tk.DoubleVar(value="1e5") 
        self.t_var = tk.DoubleVar(value="298") 
        self.alphat_var = tk.DoubleVar(value="0.1")  # Valor padrão
        self.k_var = tk.DoubleVar(value="0.1")       # Valor padrão
        self.nut_var_c = tk.DoubleVar(value="0.1")     # Valor padrão
        self.omega_var = tk.DoubleVar(value="0.1")   # Valor padrão
        self.nu_var_c = tk.DoubleVar(value="1e-6")

        # Criação dos campos de entrada básicos
        tk.Label(self.master, text="Flow velocity (m/s):", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.master, textvariable=self.flow_speed_var_c, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.master, text="P (pressure):", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.master, textvariable=self.p_var_c, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.master, text="T (temperature K):", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.master, textvariable=self.t_var, font=('Arial', 14)).pack(pady=5)

        # Campos adicionais escondidos inicialmente
        self.additional_fields_frame_compressive = tk.Frame(self.master)
        self.additional_fields_frame_compressive.pack(pady=10, fill=tk.BOTH, expand=True)
        self.additional_fields_frame_compressive.pack_forget()  # Esconde inicialmente

        tk.Label(self.additional_fields_frame_compressive, text="Alphat:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame_compressive, textvariable=self.alphat_var, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame_compressive, text="k:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame_compressive, textvariable=self.k_var, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame_compressive, text="Nut:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame_compressive, textvariable=self.nut_var_c, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame_compressive, text="Omega:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame_compressive, textvariable=self.omega_var, font=('Arial', 14)).pack(pady=5)

        tk.Label(self.additional_fields_frame_compressive, text="Nu:", font=('Arial', 14)).pack(pady=5)
        tk.Entry(self.additional_fields_frame_compressive, textvariable=self.nu_var_c, font=('Arial', 14)).pack(pady=5)


        # Botão para revelar/esconder os campos adicionais
        tk.Button(self.master, text="+", font=('Arial', 14), command=self.toggle_additional_fields_compressive).pack(pady=20)

        # Botão de submissão para processar os dados
        tk.Button(self.master, text="Run simulation", font=('Arial', 14), command=self.simulation_Compressible).pack(pady=20)

        tk.Button(self.master, text="Back", font=('Arial', 14), command=self.main_menu).pack(side=tk.LEFT, padx=10, pady=20)

    def toggle_additional_fields_compressive(self):
        if self.additional_fields_frame_compressive.winfo_ismapped():
            self.additional_fields_frame_compressive.pack_forget()  # Esconde os campos
            # Define valores padrão caso escondido
            self.alphat_var.set("0.1")
            self.k_var.set("0.1")
            self.nut_var.set("0.1")
            self.omega_var.set("0.1")
            self.nu_var_c.set("1e-6")
        else:
            self.additional_fields_frame_compressive.pack(pady=10, fill=tk.BOTH, expand=True)  # Mostra os campos

    def extrair_dados(self, base_directory):
        # Caminho para o diretório onde o arquivo de resultados será salvo
        vf_directory = os.path.join(base_directory, "..", "Resultados")
        resultados_path = os.path.join(vf_directory, "resultados.txt")

        # Verifica e cria o diretório VF se não existir
        if not os.path.exists(vf_directory):
            os.makedirs(vf_directory)

        # Abre o arquivo de resultados em modo de escrita para limpar o conteúdo
        with open(resultados_path, "w") as resultados_file:
            # Escreve o cabeçalho
            resultados_file.write("# Angulo_n: Time\tCd\tCd(f)\tCd(r)\tCl\tCl(f)\tCl(r)\tCmPitch\tCmRoll\tCmYaw\tCs\tCs(f)\tCs(r)\n")

        # Abre o arquivo de resultados em modo de anexação
        with open(resultados_path, "a") as resultados_file:
            # Itera sobre todos os ângulos na lista self.angles
            for angle in self.angles:
                angle_folder = f"Angulo_{angle}"
                angle_directory_path = os.path.join(base_directory, angle_folder)

                # Verifica se o diretório do ângulo existe, senão, cria
                if not os.path.exists(angle_directory_path):
                    os.makedirs(angle_directory_path)

                # Escreve o ângulo atual no arquivo de resultados
                resultados_file.write(f"{angle_folder}: ")


                # Caminho para o arquivo coefficient.dat
                coefficient_path = os.path.join(angle_directory_path, "postProcessing", "forceCoeffs", "0", "coefficient.dat")

                # Número de colunas de dados esperadas (Time, Cd, Cd(f), Cd(r), Cl, Cl(f), Cl(r), CmPitch, CmRoll, CmYaw, Cs, Cs(f), Cs(r))
                num_result_columns = 13
                missing_data_row = "\t".join(["nan"] * num_result_columns) + "\n"

                # Verifica se o arquivo coefficient.dat existe
                if os.path.isfile(coefficient_path):
                    with open(coefficient_path, "r") as coeff_file:
                        # Lê todas as linhas do arquivo
                        lines = coeff_file.readlines()
                        if lines:
                            # Pega a última linha de dados e escreve no arquivo de resultados
                            resultados_file.write(lines[-1])
                        else:
                            print(f"Warning: {coefficient_path} is empty, skipping angle {angle}")
                            resultados_file.write(missing_data_row)
                else:
                    print(f"Warning: no results found for angle {angle} ({coefficient_path})")
                    resultados_file.write(missing_data_row)

        functions.plot_data_from_txt(resultados_path)


root = tk.Tk()
app = App(root)
root.mainloop()
