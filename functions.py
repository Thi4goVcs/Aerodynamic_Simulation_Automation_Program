import numpy as np
import math
import os
import pandas as pd
import matplotlib.pyplot as plt
import shutil
from openpyxl import Workbook

# Obter o diretório do script em execução
script_dir = os.path.dirname(__file__)

# Alterar o diretório atual para o diretório do script
os.chdir(script_dir)

def naca4digit(m, p, t, c, num_points=102):
        """
        Generates points for a NACA 4-digit airfoil.

        Parameters:
            m (float): Maximum camber as a fraction of chord.
            p (float): Location of maximum camber as a fraction of chord.
            t (float): Maximum thickness as a fraction of chord.
            c (float): Chord length.
            num_points (int): Number of points to generate.

        Returns:
            tuple: Arrays of x and y coordinates of the airfoil points.
        """

        # Criar distribuição logarítmica
        # Gere valores de beta uniformemente espaçados de 0 a pi
        beta = np.linspace(0, np.pi, num_points)
        num_points = num_points*2
        # Calcule x usando a expressão dada
        x = (1 - np.cos(beta)) / 2
        # Inverter a distribuição para ter mais pontos no início
        yt = 5*t*c*(0.2969*np.sqrt(x/c) -
                    0.1260*(x/c) -
                    0.3516*(x/c)**2 +
                    0.2843*(x/c)**3 -
                    0.1015*(x/c)**4)

        if p == 0:
            yc = np.zeros_like(x)
            dyc_dx = np.zeros_like(x)
        else:
            yc = np.piecewise(x,
                              [x <= c*p, x > c*p],
                              [lambda x: m/p**2 * (2*p*x/c - (x/c)**2),
                               lambda x: m/(1 - p)**2 * ((1 - 2*p) + 2*p*x/c - (x/c)**2)])
            dyc_dx = np.piecewise(x,
                                  [x <= c*p, x > c*p],
                                  [lambda x: 2*m/p**2 * (p - x/c),
                                   lambda x: 2*m/(1 - p)**2 * (p - x/c)])

        xu = x - yt * np.sin(np.arctan(dyc_dx))
        xl = x + yt * np.sin(np.arctan(dyc_dx))
        yu = yc + yt * np.cos(np.arctan(dyc_dx))
        yl = yc - yt * np.cos(np.arctan(dyc_dx))

        # Concatenar coordenadas para simular o perfil completo, ajustando a ordem e evitando duplicação do ponto central
        xu = np.concatenate((np.flip(xu), xu[1:]))
        xl = np.concatenate((np.flip(xl), xl[1:]))
        yu = np.concatenate((np.flip(yu), -np.flip(yu)[1:]))
        yl = np.concatenate((np.flip(yl), -np.flip(yl)[1:]))
        # Remover o ponto duplicado (0, 0)


        return xu, yu, xl, yl


         
def blockMeshDirect(Alpha):

        # Variáveis
        Distance_to_inlet = 20 # x chord length
        Distance_to_outlet = 20  # x chord length
        Angle_os_response = Alpha  # degree
        Depth_in_Z = 0.01
        Mesh_scale = 1
        Cell_size_at_leading_edge = 0.00000001
        Cell_size_at_trailing_edge = 0.00000002
        Cell_size_in_middle = 0.000000015
        Separating_point_position = 0.25 # from leading point
        Boundary_layer_thickness = 0.2
        First_layer_thickness = 0.00000000002
        Expansion_ratio = 1.01
        Max_cell_size_in_inlet = 0.000001
        Max_cell_size_in_outlet = 0.000004
        Max_cell_size_in_inlet_x_outlet = 0.00001

        Number_of_mesh_on_boundary_layer_1 = 100
        Number_of_mesh_on_boundary_layer_2 = 100
        Number_of_mesh_at_tail = 200
        Number_of_mesh_in_leading = 100
        Number_of_mesh_in_trailing = 200
        Inlet_Expansion_Rario = 0.25


        A2 = Distance_to_inlet
        B2 = Distance_to_outlet
        C2 = Angle_os_response
        D2 = Depth_in_Z
        E2 = Mesh_scale

        D5 = Cell_size_at_leading_edge
        E5 = Cell_size_at_trailing_edge
        F5 = Cell_size_in_middle
        G5 = Separating_point_position

        D8 = Boundary_layer_thickness
        E8 = First_layer_thickness
        F8 = Expansion_ratio

        D11 = Max_cell_size_in_inlet
        E11 = Max_cell_size_in_outlet
        F11 = Max_cell_size_in_inlet_x_outlet

        N10 = Number_of_mesh_on_boundary_layer_1
        N13 = Number_of_mesh_on_boundary_layer_2
        N16 = Number_of_mesh_at_tail
        M10 = D8

        H8 = E8 * F8 ** N10
        O10 = F8 ** N10
        O13 = D11 / H8
        O16 = E11 / E5
        O18 = F11 * O13 / E11 * (N13 + N10) / N13
        O20 = G5
        O21 = Number_of_mesh_in_leading
        O22 = F5 / D5
        O23 = Number_of_mesh_in_trailing
        O24 = F5 / E5
        O28 = E5 / D11
        O29 = Inlet_Expansion_Rario

        H11 = H8 / A2 * (O13 - 1) + 1
        H13 = E5 / B2 * (O16 - 1) + 1
        H15 = D5 / G5 * (O22 - 1) + 1
        H17 = E5 / (1 - F5) * (O24 - 1) + 1
        H21 = F11 ** (1 / (N10 + N13))

        import numpy as np

        Airfoil_Generator = np.loadtxt('coordenadas.dat')

    # Separar os dados em duas colunas
        colunaA = Airfoil_Generator[:, 0]  # primeira coluna
        colunaB = Airfoil_Generator[:, 1]  # segunda coluna

    # Obter o número de linhas
        n_linhas = Airfoil_Generator.shape[0]

    # Criar as variáveis An e Bn dinamicamente
        for n in range(n_linhas):
            globals()[f"A{n+9}"] = colunaA[n]  # Criar variável An
            globals()[f"B{n+9}"] = colunaB[n]

        # Carregar dados do arquivo coordenadas.dat
        beguin_airfoil_up=9
        and_airfoil_up=(n_linhas/2)+9
        beguin_airfoil_down=(n_linhas/2)+9
        and_airfoil_down=n_linhas+9

################################################################################################      

        I11 = np.log(O13) / np.log(H11)
        I13 = np.log(O16) / np.log(H13)
        I15 = np.log(O22) / np.log(H15)
        I17 = np.log(O24) / np.log(H17)

        # Abrir o arquivo para escrita
        fid = open('mesh_padrao', 'w')

        # Verificar se o arquivo foi aberto com sucesso
        if fid == -1:
            raise IOError('Não foi possível abrir o arquivo para escrita.')

        # Escrever no arquivo
        fid.write('/*--------------------------------*Thien Phan*-------------------------------*\\\n\n\n')
        fid.write('| =========                 |                                                 |\n\n\n')
        fid.write('| \\\\      /  F ield         | OpenFOAM: phanquocthien.org                     |\n\n\n')
        fid.write('|  \\\\    /   O peration     | Files are generated by Thien Phan               |\n\n\n')
        fid.write('|   \\\\  /    A nd           | Web:      www.OpenFOAM.com                      |\n\n\n')
        fid.write('|    \\\\/     M anipulation  |         Angle: %.3f                            |\n\n\n'% Angle_os_response)
        fid.write('\\*---------------------------------------------------------------------------*/\n\n')
        fid.write('\nFoamFile\n\n')
        fid.write('{\n\n')
        fid.write('    version     2.0;\n\n')
        fid.write('    format      ascii;\n\n')
        fid.write('    class       dictionary;\n\n')
        fid.write('    object      blockMeshDict;\n\n')
        fid.write('}\n\n')
        fid.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n\n')
        fid.write('convertToMeters\t%i\t;\n\n\n' % E2)  # Aqui escrevemos a variável convertToMeters
        fid.write('\ngeometry\n\n{\n\n}\n\n\n\n')
        fid.write('vertices\n\n(\n\n')
        fid.write('\t(\t0\t0\t0\t)\t//\t0\n\n')
        fid.write('\t(\t1\t0\t0\t)\t//\t1\n\n')
        fid.write('\t(\t1\t%i\t0\t)\t//\t2\n\n' % A2)
        fid.write('\t(\t%i\t0\t0\t)\t//\t3\n\n' % (-A2 + 1))
        fid.write('\t(\t0\t0\t%.2f\t)\t//\t4\n\n' % D2)
        fid.write('\t(\t1\t0\t%.2f\t)\t//\t5\n\n' % D2)
        fid.write('\t(\t1\t%i\t%.2f\t)\t//\t6\n\n' % (A2, D2))
        fid.write('\t(\t%i\t0\t%.2f\t)\t//\t7\n\n' % (-A2 + 1, D2))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t8\n\n' % (B2 + 1, round(np.sin(np.radians(C2)) * (B2 + 1))))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t9\n\n' % (B2 + 1, A2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t10\n\n' % (B2 + 1, round(np.sin(np.radians(C2)) * (B2 + 1)), D2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t11\n\n' % (B2 + 1, A2, D2))
        fid.write('\t(\t1\t%i\t0\t)\t//\t12\n\n' % (-A2))
        fid.write('\t(\t1\t%i\t%.2f\t)\t//\t13\n\n' % (-A2, D2))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t14\n\n' % (B2 + 1, -A2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t15\n\n' % (B2 + 1, -A2, D2))
        fid.write('\t(\t1\t0\t0\t)\t//\t16\n\n')
        fid.write('\t(\t1\t0\t%.2f\t)\t//\t17\n\n\n\n' % D2)
        fid.write(');\n\n\n\n\n\n\n')
        fid.write('blocks\n\n(\n\n')
        fid.write('\thex\t(0\t1\t2\t3\t4\t5\t6\t7)\t(\t%i\t%i\t1\t)\t//block 1\n' % (O21 + O23, N10 + N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\t x-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21 / (O21 + O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - O20, 1 - (O21 / (O21 + O23)), 1 / O24))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (O28, O28))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21 / (O21 + O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - O20, 1 - (O21 / (O21 + O23)), 1 / O24))
        fid.write('\t)\n\n')
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n')
        fid.write('\thex\t(1\t8\t9\t2\t5\t10\t11\t6)\t(\t%i\t%i\t1)\t//block 2\n' % (N16, N10 + N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%i\t%i\t%i\t%i\n\n' % (O16, O16, O16, O16))
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (O18, O18))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n')
        fid.write('\thex\t(3\t12\t16\t0\t7\t13\t17\t4)\t(\t%i\t%i\t1\t)\t//block 3\n' % (O21+O23, N10+N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%0.9f\n\n' % O28)
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21/(O21+O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-O20, 1-(O21/(O21+O23)), 1/O24))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21/(O21+O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-O20, 1-(O21/(O21+O23)), 1/O24))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\n\n' % O28)
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n\n\n\n\n\n\n\n\n')
        fid.write('\thex\t(12\t14\t8\t16\t13\t15\t10\t17)\t(\t%i\t%i\t1)\t//block 4\n' % (N16, N10+N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%i\t%i\t%i\t%i\n\n' % (O16, O16, O16, O16))
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (1/O18, 1/O18))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n\t)\n\n')
        fid.write(');\n\n\n\n\n\nedges\n\n(\n\n')
        fid.write('\tarc\t3 2\t(\t%0.9f\t%0.9f\t0\t)\n\n' % (-A2*math.sin(math.pi/4)+1, A2*math.sin(math.pi/4)))
        fid.write('\tarc\t7 6\t(\t%0.9f\t%0.9f\t%0.9f\t)\n\n\n\n' % (-A2*math.sin(math.pi/4)+1, A2*math.sin(math.pi/4), D2))
        fid.write('\tspline\t1\t0\n\n\t(\n\n')
        for i in range(int(beguin_airfoil_up), int(and_airfoil_up)):
            fid.write('\t(\t%0.6f\t%0.6f\t0\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i]))
        fid.write('\t)\n\n\n\n\n\n\n')
        fid.write('\tspline\t5\t4\n\n\t(\n\n')
        for i in range(int(beguin_airfoil_up), int(and_airfoil_up)):
            fid.write('\t(\t%0.6f\t%0.6f\t%0.6f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], D2))
        fid.write('\t)\n\n\n\n\n\n\n')
        fid.write('\tarc\t3 12\t(')
        fid.write('\t%0.9f\t %0.9f\t %0.9f\t' % (-A2 * math.sin(math.pi / 4) + 1, -A2 * math.sin(math.pi / 4), 0))
        fid.write(')\n\n')
        fid.write('\tarc\t7 13\t(')
        fid.write('\t%0.9f\t%0.9f\t%0.9f\t' % (-A2 * math.sin(math.pi / 4) + 1, -A2 * math.sin(math.pi / 4), D2))
        fid.write(')\n\n\n\n')
        fid.write('\tspline\t0\t16\n\n\t(\n\n')

        for i in range(int(beguin_airfoil_down), int(and_airfoil_down)):
            fid.write('\t(\t%0.6f\t%0.6f\t%0.6f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], 0))

        fid.write(')\n\n\n\n\n\n')

        fid.write('\tspline\t4\t17\n\n\t(\n\n')

        for i in range(int(beguin_airfoil_down), int(and_airfoil_down)):
            fid.write('\t(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], D2))
        fid.write(')\n\n\n\n\n\n\n);\n\n\n\n\n')
        fid.write('faces\n\n(\n\n\n\n);\n\n\n\n')
        fid.write('faces\n\n(\n\n\n\n);\n\n\n\n\n\n')
        fid.write('defaultPatch\n\n{\n\n')
        fid.write('\tname frontAndBack;\n\n')
        fid.write('\ttype empty;\n\n')
        fid.write('}\n\n\n\n')
        fid.write('boundary\n\n(\n\n')
        fid.write('inlet\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\t\ttype patch;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(9 2 6 11)\n\n')
        fid.write('\t\t\t(2 3 7 6)\n\n')
        fid.write('\t\t\t(3 12 13 7)\n\n')
        fid.write('\t\t\t(12 15 14 13)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n\n\n')
        fid.write('outlet\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(8 9 10 11)\n\n')
        fid.write('\t\t\t(15 8 10 14)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n\n')
        fid.write('walls\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype wall;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(0 1 5 4)\n\n')
        fid.write('\t\t\t(0 4 17 16)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t\t}\n\n\n')
        fid.write('interface1\t\t// patch name	\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\t\tfaces\n\n')
        fid.write('\t\t(\n')
        fid.write('\t\t\t(1 8 10 5)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n')
        fid.write('interface2\t\t// patch name\n\n')
        fid.write('\t\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(16 17 10 8)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n')
        fid.write(');\n\n\n')
        fid.write('mergePatchPairs\n\n(\n\n')
        fid.write('\t(interface1 interface2)\n\n')
        fid.write(');\n\n')
        fid.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n')

         # Fechar o arquivo
        fid.close()


def blockMeshDirect_Custom(alpha, distance_to_inlet, distance_to_outlet,cell_size_at_leading_edge, cell_size_at_trailing_edge, cell_size_in_middle,separating_point_position, boundary_layer_thickness, first_layer_thickness,expansion_ratio, max_cell_size_in_inlet, max_cell_size_in_outlet,max_cell_size_in_inlet_and_outlet, num_mesh_on_boundary_layer_1,num_mesh_on_boundary_layer_2, num_mesh_at_tail, num_mesh_in_leading,num_mesh_in_trailing):
        # Variáveis agora são definidas pelos parâmetros
        Angle_os_response = alpha  # graus
        Distance_to_inlet = distance_to_inlet  # comprimento de corda x
        Distance_to_outlet = distance_to_outlet  # comprimento de corda x
        Depth_in_Z = 0.01
        Mesh_scale = 1
        Cell_size_at_leading_edge = cell_size_at_leading_edge
        Cell_size_at_trailing_edge = cell_size_at_trailing_edge
        Cell_size_in_middle = cell_size_in_middle
        Separating_point_position = separating_point_position  # a partir do ponto de ataque
        Boundary_layer_thickness = boundary_layer_thickness
        First_layer_thickness = first_layer_thickness
        Expansion_ratio = expansion_ratio
        Max_cell_size_in_inlet = max_cell_size_in_inlet
        Max_cell_size_in_outlet = max_cell_size_in_outlet
        Max_cell_size_in_inlet_x_outlet = max_cell_size_in_inlet_and_outlet
        Number_of_mesh_on_boundary_layer_1 = num_mesh_on_boundary_layer_1
        Number_of_mesh_on_boundary_layer_2 = num_mesh_on_boundary_layer_2
        Number_of_mesh_at_tail = num_mesh_at_tail
        Number_of_mesh_in_leading = num_mesh_in_leading
        Number_of_mesh_in_trailing = num_mesh_in_trailing
        Inlet_Expansion_Rario = 0.25


        A2 = Distance_to_inlet
        B2 = Distance_to_outlet
        C2 = Angle_os_response
        D2 = Depth_in_Z
        E2 = Mesh_scale

        D5 = Cell_size_at_leading_edge
        E5 = Cell_size_at_trailing_edge
        F5 = Cell_size_in_middle
        G5 = Separating_point_position

        D8 = Boundary_layer_thickness
        E8 = First_layer_thickness
        F8 = Expansion_ratio

        D11 = Max_cell_size_in_inlet
        E11 = Max_cell_size_in_outlet
        F11 = Max_cell_size_in_inlet_x_outlet

        N10 = Number_of_mesh_on_boundary_layer_1
        N13 = Number_of_mesh_on_boundary_layer_2
        N16 = Number_of_mesh_at_tail
        M10 = D8

        H8 = E8 * F8 ** N10
        O10 = F8 ** N10
        O13 = D11 / H8
        O16 = E11 / E5
        O18 = F11 * O13 / E11 * (N13 + N10) / N13
        O20 = G5
        O21 = Number_of_mesh_in_leading
        O22 = F5 / D5
        O23 = Number_of_mesh_in_trailing
        O24 = F5 / E5
        O28 = E5 / D11
        O29 = Inlet_Expansion_Rario

        H11 = H8 / A2 * (O13 - 1) + 1
        H13 = E5 / B2 * (O16 - 1) + 1
        H15 = D5 / G5 * (O22 - 1) + 1
        H17 = E5 / (1 - F5) * (O24 - 1) + 1
        H21 = F11 ** (1 / (N10 + N13))

        import numpy as np

        Airfoil_Generator = np.loadtxt('coordenadas.dat')

    # Separar os dados em duas colunas
        colunaA = Airfoil_Generator[:, 0]  # primeira coluna
        colunaB = Airfoil_Generator[:, 1]  # segunda coluna

    # Obter o número de linhas
        n_linhas = Airfoil_Generator.shape[0]

    # Criar as variáveis An e Bn dinamicamente
        for n in range(n_linhas):
            globals()[f"A{n+9}"] = colunaA[n]  # Criar variável An
            globals()[f"B{n+9}"] = colunaB[n]

         # Carregar dados do arquivo coordenadas.dat
        beguin_airfoil_up=9
        and_airfoil_up=(n_linhas/2)+9
        beguin_airfoil_down=(n_linhas/2)+9
        and_airfoil_down=n_linhas+9



################################################################################################      


        I11 = np.log(O13) / np.log(H11)
        I13 = np.log(O16) / np.log(H13)
        I15 = np.log(O22) / np.log(H15)
        I17 = np.log(O24) / np.log(H17)

        # Abrir o arquivo para escrita
        fid = open('mesh_padrao', 'w')

        # Verificar se o arquivo foi aberto com sucesso
        if fid == -1:
            raise IOError('Não foi possível abrir o arquivo para escrita.')

        # Escrever no arquivo
        fid.write('/*--------------------------------*Thien Phan*-------------------------------*\\\n\n\n')
        fid.write('| =========                 |                                                 |\n\n\n')
        fid.write('| \\\\      /  F ield         | OpenFOAM: phanquocthien.org                     |\n\n\n')
        fid.write('|  \\\\    /   O peration     | Files are generated by Thien Phan               |\n\n\n')
        fid.write('|   \\\\  /    A nd           | Web:      www.OpenFOAM.com                      |\n\n\n')
        fid.write('|    \\\\/     M anipulation  |         Angle: %.3f                            |\n\n\n'% Angle_os_response)
        fid.write('\\*---------------------------------------------------------------------------*/\n\n')
        fid.write('\nFoamFile\n\n')
        fid.write('{\n\n')
        fid.write('    version     2.0;\n\n')
        fid.write('    format      ascii;\n\n')
        fid.write('    class       dictionary;\n\n')
        fid.write('    object      blockMeshDict;\n\n')
        fid.write('}\n\n')
        fid.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n\n')
        fid.write('convertToMeters\t%i\t;\n\n\n' % E2)  # Aqui escrevemos a variável convertToMeters
        fid.write('\ngeometry\n\n{\n\n}\n\n\n\n')
        fid.write('vertices\n\n(\n\n')
        fid.write('\t(\t0\t0\t0\t)\t//\t0\n\n')
        fid.write('\t(\t1\t0\t0\t)\t//\t1\n\n')
        fid.write('\t(\t1\t%i\t0\t)\t//\t2\n\n' % A2)
        fid.write('\t(\t%i\t0\t0\t)\t//\t3\n\n' % (-A2 + 1))
        fid.write('\t(\t0\t0\t%.2f\t)\t//\t4\n\n' % D2)
        fid.write('\t(\t1\t0\t%.2f\t)\t//\t5\n\n' % D2)
        fid.write('\t(\t1\t%i\t%.2f\t)\t//\t6\n\n' % (A2, D2))
        fid.write('\t(\t%i\t0\t%.2f\t)\t//\t7\n\n' % (-A2 + 1, D2))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t8\n\n' % (B2 + 1, round(np.sin(np.radians(C2)) * (B2 + 1))))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t9\n\n' % (B2 + 1, A2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t10\n\n' % (B2 + 1, round(np.sin(np.radians(C2)) * (B2 + 1)), D2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t11\n\n' % (B2 + 1, A2, D2))
        fid.write('\t(\t1\t%i\t0\t)\t//\t12\n\n' % (-A2))
        fid.write('\t(\t1\t%i\t%.2f\t)\t//\t13\n\n' % (-A2, D2))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t14\n\n' % (B2 + 1, -A2))
        fid.write('\t(\t%i\t%i\t%.2f\t)\t//\t15\n\n' % (B2 + 1, -A2, D2))
        fid.write('\t(\t1\t0\t0\t)\t//\t16\n\n')
        fid.write('\t(\t1\t0\t%.2f\t)\t//\t17\n\n\n\n' % D2)
        fid.write(');\n\n\n\n\n\n\n')
        fid.write('blocks\n\n(\n\n')
        fid.write('\thex\t(0\t1\t2\t3\t4\t5\t6\t7)\t(\t%i\t%i\t1\t)\t//block 1\n' % (O21 + O23, N10 + N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\t x-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21 / (O21 + O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - O20, 1 - (O21 / (O21 + O23)), 1 / O24))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (O28, O28))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21 / (O21 + O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - O20, 1 - (O21 / (O21 + O23)), 1 / O24))
        fid.write('\t)\n\n')
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n')
        fid.write('\thex\t(1\t8\t9\t2\t5\t10\t11\t6)\t(\t%i\t%i\t1)\t//block 2\n' % (N16, N10 + N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%i\t%i\t%i\t%i\n\n' % (O16, O16, O16, O16))
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (O18, O18))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10 / A2, N10 / (N13 + N10), O10))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1 - (M10 / A2), 1 - (N10 / (N13 + N10)), O13))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n')
        fid.write('\thex\t(3\t12\t16\t0\t7\t13\t17\t4)\t(\t%i\t%i\t1\t)\t//block 3\n' % (O21+O23, N10+N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%0.9f\n\n' % O28)
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21/(O21+O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-O20, 1-(O21/(O21+O23)), 1/O24))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (O20, O21/(O21+O23), O22))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-O20, 1-(O21/(O21+O23)), 1/O24))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\n\n' % O28)
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n')
        fid.write('\t)\n\n\n\n\n\n\n\n\n\n\n\n')
        fid.write('\thex\t(12\t14\t8\t16\t13\t15\t10\t17)\t(\t%i\t%i\t1)\t//block 4\n' % (N16, N10+N13))
        fid.write('\tedgeGrading\n\n\t(\n\n')
        fid.write('\t//\tx-direction\texpansion\tratio\n\n')
        fid.write('\t%i\t%i\t%i\t%i\n\n' % (O16, O16, O16, O16))
        fid.write('\t//\ty-direction\texpansion\tratio\n\n')
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t%0.9f\t%0.9f\n\n' % (1/O18, 1/O18))
        fid.write('\t(\n\n')
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (1-(M10/A2), 1-(N10/(N13+N10)), 1/O13))
        fid.write('(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (M10/A2, N10/(N13+N10), 1/O10))
        fid.write('\t)\n\n')
        fid.write('\t//\tz-direction\texpansion\tratio\n\n')
        fid.write('\t1\t1\t1\t1\n\n\t)\n\n')
        fid.write(');\n\n\n\n\n\nedges\n\n(\n\n')
        fid.write('\tarc\t3 2\t(\t%0.9f\t%0.9f\t0\t)\n\n' % (-A2*math.sin(math.pi/4)+1, A2*math.sin(math.pi/4)))
        fid.write('\tarc\t7 6\t(\t%0.9f\t%0.9f\t%0.9f\t)\n\n\n\n' % (-A2*math.sin(math.pi/4)+1, A2*math.sin(math.pi/4), D2))
        fid.write('\tspline\t1\t0\n\n\t(\n\n')
        for i in range(int(beguin_airfoil_up), int(and_airfoil_up)):
            fid.write('\t(\t%0.6f\t%0.6f\t0\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i]))
        fid.write('\t)\n\n\n\n\n\n\n')
        fid.write('\tspline\t5\t4\n\n\t(\n\n')
        for i in range(int(beguin_airfoil_up), int(and_airfoil_up)):
            fid.write('\t(\t%0.6f\t%0.6f\t%0.6f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], D2))
        fid.write('\t)\n\n\n\n\n\n\n')
        fid.write('\tarc\t3 12\t(')
        fid.write('\t%0.9f\t %0.9f\t %0.9f\t' % (-A2 * math.sin(math.pi / 4) + 1, -A2 * math.sin(math.pi / 4), 0))
        fid.write(')\n\n')
        fid.write('\tarc\t7 13\t(')
        fid.write('\t%0.9f\t%0.9f\t%0.9f\t' % (-A2 * math.sin(math.pi / 4) + 1, -A2 * math.sin(math.pi / 4), D2))
        fid.write(')\n\n\n\n')
        fid.write('\tspline\t0\t16\n\n\t(\n\n')

        for i in range(int(beguin_airfoil_down), int(and_airfoil_down)):
            fid.write('\t(\t%0.6f\t%0.6f\t%0.6f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], 0))

        fid.write(')\n\n\n\n\n\n')

        fid.write('\tspline\t4\t17\n\n\t(\n\n')

        for i in range(int(beguin_airfoil_down), int(and_airfoil_down)):
            fid.write('\t(\t%0.9f\t%0.9f\t%0.9f\t)\n\n' % (globals()['A%d' % i], globals()['B%d' % i], D2))
        fid.write(')\n\n\n\n\n\n\n);\n\n\n\n\n')
        fid.write('faces\n\n(\n\n\n\n);\n\n\n\n')
        fid.write('faces\n\n(\n\n\n\n);\n\n\n\n\n\n')
        fid.write('defaultPatch\n\n{\n\n')
        fid.write('\tname frontAndBack;\n\n')
        fid.write('\ttype empty;\n\n')
        fid.write('}\n\n\n\n')
        fid.write('boundary\n\n(\n\n')
        fid.write('inlet\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\t\ttype patch;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(9 2 6 11)\n\n')
        fid.write('\t\t\t(2 3 7 6)\n\n')
        fid.write('\t\t\t(3 12 13 7)\n\n')
        fid.write('\t\t\t(12 15 14 13)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n\n\n')
        fid.write('outlet\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(8 9 10 11)\n\n')
        fid.write('\t\t\t(15 8 10 14)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n\n')
        fid.write('walls\t\t// patch name\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype wall;\n\n')
        fid.write('\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(0 1 5 4)\n\n')
        fid.write('\t\t\t(0 4 17 16)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t\t}\n\n\n')
        fid.write('interface1\t\t// patch name	\n\n')
        fid.write('\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\t\tfaces\n\n')
        fid.write('\t\t(\n')
        fid.write('\t\t\t(1 8 10 5)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n')
        fid.write('interface2\t\t// patch name\n\n')
        fid.write('\t\t{\n\n')
        fid.write('\t\ttype patch;\n\n')
        fid.write('\t\t\tfaces\n\n')
        fid.write('\t\t(\n\n')
        fid.write('\t\t\t(16 17 10 8)\n\n')
        fid.write('\t\t);\n\n')
        fid.write('\t}\n\n')
        fid.write(');\n\n\n')
        fid.write('mergePatchPairs\n\n(\n\n')
        fid.write('\t(interface1 interface2)\n\n')
        fid.write(');\n\n')
        fid.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n')

         # Fechar o arquivo
        fid.close()


import math

def variables_incompressible(directory, angle, num_mech,p,nut_value,nutilda_value,nu_value_I):
    # Converting the angle to radians
    angle_rad = math.radians(angle)
    # Calculating U based on the given number of mechanisms
    U = num_mech
    
    # Constructing the full path for the file
    filepath = f"{directory}/initialConditions"
    
    with open(filepath, 'w') as fid:
        # Writing the custom header
        fid.write("""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  2212                                  |
|   \\  /    A nd           | Website:  www.openfoam.com                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    arch        "LSB;label=32;scalar=64";
    class       IOobject;
    location    "0";
    object      initialConditions;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n""")

        # Writing velocity components
        fid.write(f'U_mag {U};\n\n')
        fid.write(f'angle {angle};\n\n')
        fid.write(f'U_x  {U*math.cos(angle_rad):.3f};\n\n')
        fid.write(f'U_y  {U*math.sin(angle_rad):.3f};\n\n')
        fid.write('U_z 0;\n\n')
        fid.write(f'sen_alpha {math.sin(angle_rad):.4f};\n\n')
        fid.write(f'cos_alpha {math.cos(angle_rad):.4f};\n\n')
        fid.write('rhoInf 1.225;\n\n')
        fid.write(f'nut {nut_value};\n\n')
        fid.write(f'nuTilda {nutilda_value};\n\n')
        fid.write(f'p {p};\n\n')
        fid.write(f'nu {nu_value_I};\n\n')
        fid.write('// ************************************************************************* //\n')

# You do not need to explicitly close the file when using 'with open'.

def variables_compressible(directory, angle, num_mech,p,nut_value,T,omega,k,alphat,nu_value_I):
    # Converting the angle to radians
    angle_rad = math.radians(angle)
    # Calculating U based on the given number of mechanisms
    U = num_mech
    
    # Constructing the full path for the file
    filepath = f"{directory}/initialConditions"
    
    with open(filepath, 'w') as fid:
        # Writing the custom header
        fid.write("""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  2212                                  |
|   \\  /    A nd           | Website:  www.openfoam.com                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    arch        "LSB;label=32;scalar=64";
    class       IOobject;
    location    "0";
    object      initialConditions;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n""")

        # Writing velocity components
        fid.write(f'U_mag {U};\n')
        fid.write(f'U_x  {U * math.cos(angle_rad):.3f};\n\n')
        fid.write(f'U_y  {U * math.sin(angle_rad):.3f};\n\n')
        fid.write('U_z 0;\n\n')
        fid.write(f'sen_alpha {math.sin(angle_rad)};\n\n')
        fid.write(f'cos_alpha {math.cos(angle_rad)};\n\n')
        fid.write('rhoInf 1.225;\n\n')
        fid.write(f'nut {nut_value};\n\n')
        fid.write(f'P {p};\n\n')
        fid.write(f'T {T};\n\n')
        fid.write(f'omega {omega};\n\n')
        fid.write(f'K {k};\n\n')   
        fid.write(f'alphat {alphat};\n\n')     
        fid.write(f'nu {nu_value_I};\n\n')
        
        fid.write('// ************************************************************************* //\n')

# You do not need to explicitly close the file when using 'with open'.


def append_last_line_to_file(source_path, target_file):
    try:
        # Open the source file to read
        with open(source_path, 'r') as source:
            lines = source.readlines()
        
        # Find the last line that is not a comment
        last_valid_line = None
        for line in reversed(lines):
            if line.strip() and not line.startswith('#'):
                last_valid_line = line.strip()
                break
        
        # Append the last valid line to the target file
        with open(target_file, 'a') as target:  # 'a' mode opens the file for appending
            target.write(last_valid_line + '\n')  # Write the line with a newline at the end
        
        print("Line appended successfully.")
        
    except FileNotFoundError:
        print(f"Error: The file {source_path} does not exist.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

def plot_data_from_txt(file_path, output_dir='graficos'):
    # Limpar a pasta de saída (se existir) antes de salvar novos gráficos
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # Ler os dados do arquivo
    data = pd.read_csv(file_path, delimiter='\t', index_col=0)

    # Limpar e converter o índice
    data.index = data.index.str.extract(r'(-?\d+\.\d+|\d+)')[0].astype(float)

    # Criar um arquivo Excel e adicionar os dados
    excel_file_path = os.path.join(output_dir, 'data.xlsx')
    data.to_excel(excel_file_path, sheet_name='Data')

    # Criar um arquivo de texto formatado para ser lido no Octave
    octave_file_path = os.path.join(output_dir, 'data.txt')
    with open(octave_file_path, 'w') as f:
        # Escrever os nomes das colunas
        f.write('alpha\t' + '\t'.join(data.columns) + '\n')
        # Escrever os dados
        for alpha, row in data.iterrows():
            f.write(f"{alpha}\t" + '\t'.join(map(str, row.values)) + '\n')


    
    # Plotar um gráfico para cada coluna de dados e salvar como imagem
    for column in data.columns:
        plt.figure(figsize=(10, 5))
        plt.plot(data.index, data[column], marker='o', linestyle='-')
        plt.title(f'Gráfico de {column} por Alpha')
        plt.xlabel('alpha (graus)')
        plt.ylabel(column)
        plt.grid(True)
        
        # Salvar o gráfico como um arquivo de imagem
        file_name = os.path.join(output_dir, f'{column.replace("(", "").replace(")", "").replace("/", "_")}.png')
        plt.savefig(file_name)
        plt.close()  # Fechar a figura após salvar para liberar memória





