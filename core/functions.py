import numpy as np
import math
import os
import re
import io
import sys
import pandas as pd
import matplotlib
# Backend não-interativo: plot_data_from_txt só salva PNGs em disco e pode ser
# chamada a partir de uma thread em segundo plano (fora do event loop do Tkinter).
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import shutil
from openpyxl import Workbook

# Diretório base do app. Quando empacotado com PyInstaller (--onefile),
# __file__ aponta para dentro do diretório temporário _MEIPASS, não para o
# .exe real -- nesse caso os arquivos de runtime (Results/, Simulations/,
# plots/, etc.) devem ficar ao lado do .exe, não em uma pasta temporária.
script_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))

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
        fid = open('mesh_standard', 'w')

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
        fid = open('mesh_standard', 'w')

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

def parse_live_coefficients(raw_text):
    """Parses a forceCoeffs coefficient.dat snapshot (read mid-run, from a
    still-running WSL case) into iteration/Cd/Cl arrays for a live plot.
    Returns None if the text can't be parsed as coefficient data yet."""
    try:
        df = pd.read_csv(io.StringIO(raw_text), comment='#', sep=r'\s+', header=None)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return None
    if df.empty or df.shape[1] < 5:
        return None
    return {"time": df.iloc[:, 0].tolist(), "cd": df.iloc[:, 1].tolist(), "cl": df.iloc[:, 4].tolist()}


def summarize_coefficient_history(coefficient_path, avg_fraction=0.2, min_avg_rows=5):
    """
    Read an OpenFOAM forceCoeffs time history (coefficient.dat) and average
    the last portion of it instead of just taking the final sample, which
    can still carry solver oscillation/noise even after a long run.

    Returns None if the file is missing/empty, otherwise a dict with:
        last_time   -- the final time/iteration value reached
        averaged    -- list of 12 floats (Cd, Cd(f), Cd(r), Cl, Cl(f), Cl(r),
                        CmPitch, CmRoll, CmYaw, Cs, Cs(f), Cs(r)) averaged
                        over the last `avg_fraction` of the run
        converged   -- True if Cd and Cl look flat over the averaging window
                        (first half vs second half differ by < 2%)
        rel_change  -- the relative change behind that convergence check
    """
    try:
        df = pd.read_csv(coefficient_path, comment='#', sep=r'\s+', header=None)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return None
    if df.empty:
        return None

    n = len(df)
    window = min(n, max(min_avg_rows, int(n * avg_fraction)))
    tail = df.tail(window)

    last_time = df.iloc[-1, 0]
    averaged = tail.iloc[:, 1:].mean().tolist()

    # Judge convergence on Cd (col 1) and Cl (col 4) only. The moment and
    # side-force coefficients are routinely near-zero for a symmetric 2D
    # case, where tiny absolute noise produces a huge, meaningless relative
    # swing that would otherwise dominate the check.
    half = max(1, window // 2)
    primary_cols = [1, 4]
    first_half_mean = tail.iloc[:half, primary_cols].mean()
    second_half_mean = tail.iloc[-half:, primary_cols].mean()
    # A coefficient counts as converged if it changed by < 2% relative, OR
    # by less than an absolute tolerance -- at some angles Cd/Cl sit so
    # close to zero that a tiny, physically negligible absolute wobble
    # would otherwise read as a huge (meaningless) relative percentage.
    # The reported rel_change is floored against that same tolerance so it
    # stays a legible number instead of blowing up near a zero crossing.
    abs_tolerance = 2e-3
    abs_change = (second_half_mean - first_half_mean).abs()
    rel_change = abs_change / second_half_mean.abs().clip(lower=abs_tolerance)
    converged = bool(((rel_change < 0.02) | (abs_change < abs_tolerance)).all())

    return {
        "last_time": last_time,
        "averaged": averaged,
        "converged": converged,
        "rel_change": float(rel_change.max()),
    }


def summarize_yplus(yplus_path, avg_fraction=0.2, min_avg_rows=5):
    """
    Read an OpenFOAM yPlus function-object output and average the last
    portion of the run. Returns None if the file is missing/empty, otherwise
    a dict with 'average' (mean of the 'average' column) and 'max' (peak of
    the 'max' column) over the averaging window -- useful to sanity-check
    that the boundary-layer mesh resolution matches the turbulence model's
    wall-function assumptions.
    """
    try:
        df = pd.read_csv(yplus_path, comment='#', sep=r'\s+', header=None,
                          names=['Time', 'patch', 'min', 'max', 'average'])
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return None
    if df.empty:
        return None

    n = len(df)
    window = min(n, max(min_avg_rows, int(n * avg_fraction)))
    tail = df.tail(window)

    return {
        "average": float(tail['average'].mean()),
        "max": float(tail['max'].max()),
    }


def plot_data_from_txt(file_path, output_dir='plots'):
    # Limpar a pasta de saída (se existir) antes de salvar novos gráficos
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # Ler os dados do arquivo
    data = pd.read_csv(file_path, delimiter='\t', index_col=0)

    # Limpar e converter o índice
    data.index = data.index.str.extract(r'(-?\d+\.\d+|\d+)')[0].astype(float)
    data = data.sort_index()

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

    # A coluna "Converged" é metadado de QA, não um coeficiente -- usada para
    # marcar visualmente pontos possivelmente não convergidos nos gráficos,
    # não plotada como uma variável própria.
    converged_mask = data.pop('Converged').fillna(0).astype(bool) if 'Converged' in data.columns else pd.Series(True, index=data.index)

    plt.rcParams.update({
        'figure.dpi': 130,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'axes.titlesize': 13,
        'axes.titleweight': 'bold',
        'axes.labelsize': 11,
        'font.size': 10,
    })
    line_color = '#1f6fb2'
    flag_color = '#d9534f'

    def plot_with_convergence_flags(x, y, xlabel, ylabel, title, annotate_alpha=False):
        plt.plot(x, y, marker='o', markersize=6, linewidth=1.8, color=line_color, zorder=2)
        unconverged = ~converged_mask
        if unconverged.any():
            plt.scatter(x[unconverged], y[unconverged], marker='x', s=90, linewidths=2.2,
                        color=flag_color, zorder=3, label='not fully converged')
            plt.legend(loc='best', fontsize=9)
        if annotate_alpha:
            for alpha, xi, yi in zip(data.index, x, y):
                plt.annotate(f'{alpha:g}°', (xi, yi), textcoords="offset points", xytext=(6, 4), fontsize=8)
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.tight_layout()

    # Plotar um gráfico para cada coluna de dados e salvar como imagem
    for column in data.columns:
        plt.figure(figsize=(8, 4.5))
        if data[column].min() < 0 < data[column].max():
            plt.axhline(0, color='gray', linewidth=0.8, linestyle='--', zorder=1)
        plot_with_convergence_flags(data.index, data[column], 'alpha (deg)', column,
                                     f'{column} vs. Angle of Attack')
        file_name = os.path.join(output_dir, f'{column.replace("(", "").replace(")", "").replace("/", "_")}.png')
        plt.savefig(file_name)
        plt.close()

    # Gráficos derivados: polar de arrasto e eficiência aerodinâmica (Cl/Cd),
    # os dois mais usados na análise de um perfil e que antes não existiam.
    if 'Cl' in data.columns and 'Cd' in data.columns:
        plt.figure(figsize=(6.5, 6))
        plot_with_convergence_flags(data['Cd'], data['Cl'], 'Cd', 'Cl',
                                     'Drag Polar (Cl vs. Cd)', annotate_alpha=True)
        plt.savefig(os.path.join(output_dir, 'polar_Cl_Cd.png'))
        plt.close()

        with np.errstate(divide='ignore', invalid='ignore'):
            efficiency = data['Cl'] / data['Cd']
        plt.figure(figsize=(8, 4.5))
        plt.axhline(0, color='gray', linewidth=0.8, linestyle='--', zorder=1)
        plot_with_convergence_flags(data.index, efficiency, 'alpha (deg)', 'Cl / Cd',
                                     'Aerodynamic Efficiency (Cl/Cd) vs. Angle of Attack')
        plt.savefig(os.path.join(output_dir, 'efficiency_Cl_Cd.png'))
        plt.close()


# ---------------------------------------------------------------------- #
# Mesh preview: parsing the raw text a disposable blockMesh/checkMesh run
# in WSL prints back, so the GUI can show mesh quality + a wireframe
# before the user commits to a full simulation.
# ---------------------------------------------------------------------- #

def split_mesh_preview_output(raw_output):
    """Splits the marker-delimited stdout of the mesh-preview WSL command
    into its log/points/faces/boundary sections."""

    def _between(text, start_marker, end_marker):
        start = text.find(start_marker)
        end = text.find(end_marker)
        if start == -1 or end == -1:
            return ""
        return text[start + len(start_marker):end].strip("\n")

    raw_output = raw_output or ""
    return {
        "log": _between(raw_output, "===MESH_LOG_START===", "===MESH_LOG_END==="),
        "points": _between(raw_output, "===POINTS_START===", "===POINTS_END==="),
        "faces": _between(raw_output, "===FACES_START===", "===FACES_END==="),
        "boundary": _between(raw_output, "===BOUNDARY_START===", "===BOUNDARY_END==="),
    }


def parse_checkmesh_log(log_text):
    """Extracts mesh-quality metrics from blockMesh/checkMesh console output."""
    result = {
        "blockmesh_ok": False,
        "mesh_ok": False,
        "cells": None,
        "points": None,
        "max_nonortho": None,
        "avg_nonortho": None,
        "max_skewness": None,
        "max_aspect_ratio": None,
        "warnings": [],
        "error": None,
    }
    if not log_text:
        result["error"] = "No output captured from blockMesh/checkMesh."
        return result

    # checkMesh only runs (and prints "Mesh stats") if blockMesh succeeded.
    result["blockmesh_ok"] = "Mesh stats" in log_text

    if not result["blockmesh_ok"]:
        fatal = re.search(r'FOAM FATAL ERROR.*', log_text, re.S)
        result["error"] = fatal.group(0).strip()[:800] if fatal else log_text.strip()[-800:]
        return result

    m = re.search(r'\bcells:\s*(\d+)', log_text)
    if m:
        result["cells"] = int(m.group(1))
    m = re.search(r'\bpoints:\s*(\d+)', log_text)
    if m:
        result["points"] = int(m.group(1))
    m = re.search(r'Mesh non-orthogonality Max:\s*([\d.]+)\s*average:\s*([\d.]+)', log_text)
    if m:
        result["max_nonortho"] = float(m.group(1))
        result["avg_nonortho"] = float(m.group(2))
    m = re.search(r'Max skewness\s*=\s*([\d.]+)', log_text)
    if m:
        result["max_skewness"] = float(m.group(1))
    # checkMesh writes "Max aspect ratio = X OK." when the check passes, but
    # "***...Max aspect ratio: X, ..." (colon, not "=") when it fails.
    m = re.search(r'Max aspect ratio\s*[:=]\s*([\d.]+)', log_text)
    if m:
        result["max_aspect_ratio"] = float(m.group(1))

    result["warnings"] = [line.strip() for line in log_text.splitlines() if line.strip().startswith("***")]

    m = re.search(r'Failed (\d+) mesh checks?', log_text)
    if m:
        result["mesh_ok"] = False
        result["failed_checks"] = int(m.group(1))
    else:
        result["mesh_ok"] = bool(re.search(r'\bMesh OK\b', log_text))

    return result


def _parse_openfoam_list(text, caster):
    """Reads a bare OpenFOAM ASCII list ('N\\n(\\n...\\n)') and casts each entry."""
    values = []
    in_list = False
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if not in_list:
            if s == "(":
                in_list = True
            continue
        if s == ")":
            break
        values.append(caster(s))
    return values


def parse_openfoam_points(points_text):
    def _cast(s):
        parts = s.strip("()").split()
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    return _parse_openfoam_list(points_text, _cast)


def parse_openfoam_faces(faces_text):
    def _cast(s):
        inside = s[s.index("(") + 1:s.rindex(")")]
        return [int(v) for v in inside.split()]
    return _parse_openfoam_list(faces_text, _cast)


def parse_boundary_patch(boundary_text, patch_name):
    """Returns (startFace, nFaces) for a named patch in a polyMesh/boundary file."""
    m = re.search(rf'\b{re.escape(patch_name)}\b\s*\{{(.*?)\}}', boundary_text or "", re.S)
    if not m:
        return None
    block = m.group(1)
    nfaces_m = re.search(r'nFaces\s+(\d+)', block)
    startface_m = re.search(r'startFace\s+(\d+)', block)
    if not nfaces_m or not startface_m:
        return None
    return int(startface_m.group(1)), int(nfaces_m.group(1))


def build_mesh_wireframe(points_text, faces_text, boundary_text, patch_name="frontAndBack",
                          near_field_box=((-2.0, 3.0), (-2.0, 2.0)), max_polygons=25000):
    """Builds a 2D wireframe (list of cell polygons) from the polyMesh 'frontAndBack'
    patch -- the mesh is extruded by a single cell in Z, so that patch's faces are
    exactly the 2D grid cells. Keeps only the near-field region around the airfoil
    (the domain otherwise stretches many chord lengths to the inlet/outlet) and
    caps the polygon count for render performance."""
    points = parse_openfoam_points(points_text)
    faces = parse_openfoam_faces(faces_text)
    patch = parse_boundary_patch(boundary_text, patch_name)
    if not points or not faces or not patch:
        return []

    start_face, n_faces = patch
    patch_faces = faces[start_face:start_face + n_faces]
    if not patch_faces:
        return []

    z_values = [points[idx][2] for face in patch_faces for idx in face]
    z_min = min(z_values)

    (x_lo, x_hi), (y_lo, y_hi) = near_field_box
    polygons = []
    for face in patch_faces:
        face_points = [points[idx] for idx in face]
        if any(abs(p[2] - z_min) > 1e-9 for p in face_points):
            continue  # the duplicate back-plane copy of the same 2D cell
        if any(not (x_lo <= p[0] <= x_hi and y_lo <= p[1] <= y_hi) for p in face_points):
            continue  # outside the near-field region we care about previewing
        polygons.append([(p[0], p[1]) for p in face_points])

    if len(polygons) > max_polygons:
        stride = max(1, math.ceil(len(polygons) / max_polygons))
        polygons = polygons[::stride]

    return polygons


