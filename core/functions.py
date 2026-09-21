import numpy as np
import math
import os
import re
import io
import pandas as pd
import matplotlib
# Backend não-interativo: plot_data_from_txt só salva PNGs em disco e pode ser
# chamada a partir de uma thread em segundo plano (fora do event loop do Tkinter).
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import shutil
from openpyxl import Workbook

# O diretório de trabalho (raiz do app, onde ficam coordenadas.dat, Results/,
# Simulations/, plots/, etc.) é definido pelo Run.py na inicialização -- este
# módulo só usa caminhos relativos, sem presumir sua própria localização em
# disco (que agora é core/functions.py, um nível abaixo da raiz do app).

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



# Ponto de referência: 2e-11 m de primeira célula foi validado empiricamente
# (rodada real) como dando y+ ~= 37-48 em velocity=15 m/s, nu=1e-5 (Re=1.5e6)
# -- o regime "conhecido bom" em que este app foi originalmente ajustado.
_REFERENCE_FIRST_LAYER = 0.00000000002
_REFERENCE_VELOCITY = 15.0
_REFERENCE_NU = 1e-5


def _wall_shear_scale(velocity, nu, chord=1.0):
    """
    u_tau/nu estimado por Schlichting (atrito de placa plana turbulenta,
    valido para ~1e6 < Re_c < 1e9). So a RAZAO entre duas condicoes de
    escoamento e usada (ver first_layer_thickness_for_flow), entao a relacao
    (desconhecida) entre altura de celula e y+ real embutida na geometria
    do blockMeshDirect se cancela.
    """
    re_c = max(velocity * chord / nu, 1e5)
    cf = (2 * math.log10(re_c) - 0.65) ** -2.3
    u_tau = velocity * math.sqrt(cf / 2)
    return u_tau / nu


def first_layer_thickness_for_flow(velocity, nu, chord=1.0):
    """
    Escala a altura da primeira celula da camada limite para manter,
    aproximadamente, o mesmo y+ do regime de referencia (validado
    empiricamente) em qualquer outra velocidade/numero de Reynolds.
    Cai de volta no valor historico se velocity/nu vierem invalidos.
    """
    if not velocity or not nu:
        return _REFERENCE_FIRST_LAYER
    ref_scale = _wall_shear_scale(_REFERENCE_VELOCITY, _REFERENCE_NU, chord)
    new_scale = _wall_shear_scale(velocity, nu, chord)
    return _REFERENCE_FIRST_LAYER * (ref_scale / new_scale)


# A malha padrao concentra os N10 primeiros elementos da camada limite numa
# grade geometrica (razao Expansion_ratio) que cobre Boundary_layer_thickness
# -- e' essa grade, nao First_layer_thickness, que de fato controla a altura
# da celula junto a parede (y+). Ver blockMeshDirect: o bloco escrito com
# razao O10 = Expansion_ratio**N10 cobre exatamente essa regiao.
_REFERENCE_EXPANSION_RATIO = 1.01
_REFERENCE_BOUNDARY_LAYER_THICKNESS = 0.2
_REFERENCE_N_BOUNDARY_LAYER_CELLS = 100


def _boundary_layer_first_cell(thickness, ratio, n_cells):
    """Altura da 1a celula de uma grade geometrica de n_cells cobrindo `thickness`."""
    return thickness * (ratio - 1) / (ratio ** n_cells - 1)


def _solve_expansion_ratio_for_first_cell(target_first_cell, thickness, n_cells,
                                           lo=1.00001, hi=5.0, iters=100):
    """
    Busca binaria pela razao de expansao que produz a altura de 1a celula
    desejada (thickness*(r-1)/(r**n-1) e monotonicamente decrescente em r).
    """
    def g(ratio):
        return _boundary_layer_first_cell(thickness, ratio, n_cells) - target_first_cell
    if g(lo) <= 0:
        return lo
    if g(hi) >= 0:
        return hi
    for _ in range(iters):
        mid = (lo + hi) / 2
        if g(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# A altura da primeira celula sai de  altura = y+ * nu / u_tau,  com u_tau
# estimado por Schlichting. Essa estimativa superestima o y+ real desta malha:
# numa rodada medida (10 graus, Re=6e6) a primeira celula de 3.283e-4 corda deu
# y+ medio 33.41, contra 73.52 previstos -- dai o fator de calibracao.
_YPLUS_CALIBRATION = 33.41 / 73.52

# Com este valor a malha e identica a validada contra Ladson/NASA TM 4074 em
# qualquer velocidade. y+ ~ 1 (malha resolvida ate a parede) funciona, mas nos
# testes de 2026-09 deu Cd pior -- ver docs/MESH_QUALITY_STUDY.md.
DEFAULT_TARGET_YPLUS = 33.41


def first_cell_height_for_yplus(target_yplus, velocity, nu, chord=1.0):
    """Altura da primeira celula na parede para um y+ alvo: y+ * nu / u_tau."""
    scale = _wall_shear_scale(velocity, nu, chord)  # u_tau / nu
    return target_yplus / (scale * _YPLUS_CALIBRATION)


def expansion_ratio_for_flow(velocity, nu, chord=1.0,
                              boundary_layer_thickness=_REFERENCE_BOUNDARY_LAYER_THICKNESS,
                              n_cells=_REFERENCE_N_BOUNDARY_LAYER_CELLS,
                              target_yplus=DEFAULT_TARGET_YPLUS):
    """
    Razao de expansao da camada limite que entrega o y+ alvo na parede, em
    qualquer velocidade/Reynolds. Abaixo de Re ~9e5 a celula pedida fica maior
    que o espacamento uniforme do bloco e a busca satura (malha uniforme).
    Cai no valor historico se velocity/nu vierem invalidos.
    """
    if not velocity or not nu:
        return _REFERENCE_EXPANSION_RATIO
    target_first_cell = first_cell_height_for_yplus(target_yplus, velocity, nu, chord)
    return _solve_expansion_ratio_for_first_cell(target_first_cell, boundary_layer_thickness, n_cells)


def _outer_ratio_continuous(inner_last_cell, outer_length, n_cells, growth=1.1):
    """
    Razao de expansao do trecho externo da graduacao em y, comecando de onde o
    trecho da camada limite termina. Antes ela vinha de `O13 = D11/H8`, um tamanho
    que ninguem escolhia: a celula encolhia 33x na emenda em y=0,2 corda, em volta
    do perfil inteiro, e a malha gastava 38 camadas so para voltar ao tamanho
    anterior.
    """
    ratio = _solve_expansion_ratio_for_first_cell(inner_last_cell * growth,
                                                  outer_length, n_cells)
    return ratio ** (n_cells - 1)


# A aresta de saida dos blocos da esteira tinha sua razao de expansao derivada da
# altura da primeira celula na parede (O18 = F11*O13/E11*...), o que propagava o
# refino da camada limite ate a saida, 20 cordas a jusante: a primeira celula la
# ficava com 2e-5 corda e razao de aspecto ~2e4 -- origem medida das celulas que o
# checkMesh reprovava. A 20 cordas a esteira tem ordem de 1 corda de largura, entao
# o que importa e a altura alvo abaixo, nao o y+ da parede.
_WAKE_OUTLET_FIRST_CELL = 0.008


def wake_outlet_expansion_ratio(edge_length, n_cells,
                                 target_first_cell=_WAKE_OUTLET_FIRST_CELL):
    """
    Razao de expansao (ultima/primeira celula) da aresta de saida dos blocos da
    esteira. Depende do tamanho do dominio e da contagem de celulas -- que e do
    que ela de fato depende -- e nao do Reynolds.
    """
    ratio = _solve_expansion_ratio_for_first_cell(target_first_cell, edge_length, n_cells)
    return ratio ** (n_cells - 1)


def _wake_corner_offset(angle, distance_to_inlet, distance_to_outlet):
    """
    Deslocamento vertical do canto de saida (vertices 8 e 10). Ele inclina a linha
    de interface que vai do bordo de fuga ate a saida -- onde fica a banda refinada
    da esteira -- para acompanhar a direcao do escoamento. Era arredondado para
    inteiro, o que fazia a banda andar em degraus (10 e 12 graus caiam na mesma
    malha) com ate 1,3 grau de desalinhamento. O limite impede que o vertice 8
    alcance o 9, o que degenera a malha a partir de ~72 graus.
    """
    offset = math.sin(math.radians(angle)) * (distance_to_outlet + 1)
    limit = 0.9 * distance_to_inlet
    return max(-limit, min(limit, offset))


def blockMeshDirect(Alpha, first_layer_thickness=None, expansion_ratio=None):

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
        First_layer_thickness = (first_layer_thickness if first_layer_thickness is not None
                                  else _REFERENCE_FIRST_LAYER)
        Expansion_ratio = (expansion_ratio if expansion_ratio is not None
                            else _REFERENCE_EXPANSION_RATIO)
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
        O13 = _outer_ratio_continuous(_boundary_layer_first_cell(D8, F8, N10) * F8 ** (N10 - 1),
                                      A2 - D8, N13)
        O16 = E11 / E5
        O18 = wake_outlet_expansion_ratio(A2, N10 + N13)
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
        fid.write('\t(\t%i\t%0.6f\t0\t)\t//\t8\n\n' % (B2 + 1, _wake_corner_offset(C2, A2, B2)))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t9\n\n' % (B2 + 1, A2))
        fid.write('\t(\t%i\t%0.6f\t%.2f\t)\t//\t10\n\n' % (B2 + 1, _wake_corner_offset(C2, A2, B2), D2))
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
        O13 = _outer_ratio_continuous(_boundary_layer_first_cell(D8, F8, N10) * F8 ** (N10 - 1),
                                      A2 - D8, N13)
        O16 = E11 / E5
        O18 = wake_outlet_expansion_ratio(A2, N10 + N13)
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
        fid.write('\t(\t%i\t%0.6f\t0\t)\t//\t8\n\n' % (B2 + 1, _wake_corner_offset(C2, A2, B2)))
        fid.write('\t(\t%i\t%i\t0\t)\t//\t9\n\n' % (B2 + 1, A2))
        fid.write('\t(\t%i\t%0.6f\t%.2f\t)\t//\t10\n\n' % (B2 + 1, _wake_corner_offset(C2, A2, B2), D2))
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

# ---------------------------------------------------------------------------
# Protecao contra rodadas simultaneas e contra escrita no template
# ---------------------------------------------------------------------------
def pid_alive(pid):
    """True se existe um processo com esse PID. Nao usa os.kill(pid, 0): no
    Windows qualquer sinal diferente de CTRL_* termina o processo."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_run_lock(lock_path, pid=None, started=None):
    """Reserva a pasta Simulations/ para esta execucao do app.

    Retorna (True, None) se conseguiu, ou (False, info) se OUTRA instancia viva
    ja esta rodando (info = {"pid": ..., "started": ...}). Uma trava deixada por
    um processo que ja morreu e ignorada e sobrescrita."""
    import json
    import time as _time
    pid = os.getpid() if pid is None else pid
    started = _time.strftime("%H:%M:%S") if started is None else started
    try:
        with open(lock_path, "r", encoding="utf-8") as fh:
            info = json.load(fh)
        if info.get("pid") != pid and pid_alive(info.get("pid")):
            return False, info
    except (OSError, ValueError):
        pass
    with open(lock_path, "w", encoding="utf-8") as fh:
        json.dump({"pid": pid, "started": started}, fh)
    return True, None


def release_run_lock(lock_path, pid=None):
    """Remove a trava, mas so se ela pertence a este processo."""
    import json
    pid = os.getpid() if pid is None else pid
    try:
        with open(lock_path, "r", encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return
    if info.get("pid") == pid:
        try:
            os.remove(lock_path)
        except OSError:
            pass


def _refuse_template_dir(directory):
    """As funcoes que escrevem initialConditions so podem escrever na pasta de
    um caso (Simulations/Angle_X/0.orig), nunca em core/Standard/, senao a
    saida de uma rodada vira o "template" de todas as seguintes."""
    parts = [p.lower() for p in re.split(r"[\\/]+", os.path.abspath(str(directory)))]
    for i in range(len(parts) - 1):
        if parts[i] == "core" and parts[i + 1] == "standard":
            raise ValueError(f"Refusing to write case values into the template directory: {directory}")


def verify_initial_conditions(directory, expected_speed):
    """Confere, lendo o arquivo de volta, que U_mag e o pedido nesta rodada
    (e nao um valor herdado de uma rodada antiga)."""
    with open(f"{directory}/initialConditions", "r") as fh:
        match = re.search(r"^U_mag\s+([^;\s]+)\s*;", fh.read(), flags=re.M)
    if not match or abs(float(match.group(1)) - float(expected_speed)) > 1e-9 * max(1.0, abs(float(expected_speed))):
        found = match.group(1) if match else "missing"
        raise ValueError(f"{directory}/initialConditions has U_mag {found}, expected {expected_speed}")


def variables_incompressible(directory, angle, num_mech,p,nut_value,nutilda_value,nu_value_I):
    _refuse_template_dir(directory)
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
    _refuse_template_dir(directory)
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


PROGRESS_STAGE_ORDER = ("blockMesh", "decomposePar", "simpleFoam", "reconstructPar")

# Where each pipeline stage sits on the 0..1 progress bar of one angle. The
# solver dominates the wall time, so it gets most of the range and moves with
# the iteration count; the other stages are short fixed slices.
_STAGE_FRACTION = {"queued": 0.0, "preparing": 0.01, "blockMesh": 0.03, "decomposePar": 0.07,
                   "reconstructPar": 0.96, "done": 1.0, "failed": 1.0}
_SOLVER_START, _SOLVER_SPAN = 0.08, 0.87


def build_progress_poll_command(run_ids):
    """Single bash command reporting, for every run, which OpenFOAM stage logs
    exist, the last solver 'Time =' line and the forceCoeffs file. One wsl call
    for all runs keeps the polling cost flat however many angles run at once."""
    ids = " ".join(f'"{run_id}"' for run_id in run_ids)
    return (
        f'for id in {ids}; do d="/tmp/aero_sim_$id"; [ -d "$d" ] || continue; '
        'echo "@@ID $id"; '
        'for l in blockMesh decomposePar simpleFoam reconstructPar; do '
        '[ -f "$d/log.$l" ] && echo "@@LOG $l"; done; '
        't=$(tail -c 30000 "$d/log.simpleFoam" 2>/dev/null | grep -a "^Time = " | tail -n 1); '
        'echo "@@TIME ${t#Time = }"; '
        'echo "@@COEFF"; cat "$d/postProcessing/forceCoeffs/0/coefficient.dat" 2>/dev/null; '
        'echo "@@END"; done'
    )


def parse_progress_snapshot(raw_text):
    """Parses the output of build_progress_poll_command into
    {run_id: {"stages": [...], "time": float | None, "coeff": str}}."""
    runs = {}
    current = None
    coeff_lines = None
    for line in raw_text.splitlines():
        line = line.rstrip("\r")
        if line.startswith("@@ID "):
            current = {"stages": [], "time": None, "coeff": ""}
            runs[line[5:].strip()] = current
            coeff_lines = None
        elif current is None:
            continue
        elif line.startswith("@@LOG "):
            current["stages"].append(line[6:].strip())
        elif line.startswith("@@TIME"):
            try:
                current["time"] = float(line[6:].strip())
            except ValueError:
                current["time"] = None
        elif line == "@@COEFF":
            coeff_lines = []
        elif line == "@@END":
            if coeff_lines is not None:
                current["coeff"] = "\n".join(coeff_lines)
            coeff_lines = None
        elif coeff_lines is not None:
            coeff_lines.append(line)
    return runs


def stage_from_logs(stages):
    """Latest pipeline stage whose log file exists ('preparing' if none yet)."""
    for name in reversed(PROGRESS_STAGE_ORDER):
        if name in stages:
            return name
    return "preparing"


def read_case_iteration_settings(control_dict_path):
    """(delta_t, max_iterations) from a case's controlDict, or None. For a
    steady simpleFoam case the 'time' is just iteration * deltaT."""
    try:
        with open(control_dict_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    number = r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
    end_match = re.search(r'^\s*endTime\s+' + number + r'\s*;', text, re.M)
    step_match = re.search(r'^\s*deltaT\s+' + number + r'\s*;', text, re.M)
    if not end_match or not step_match:
        return None
    end_time, delta_t = float(end_match.group(1)), float(step_match.group(1))
    if delta_t <= 0:
        return None
    return delta_t, max(1, round(end_time / delta_t))


def run_progress_fraction(stage, iteration, max_iterations):
    """0..1 progress of one angle from its pipeline stage and solver iteration."""
    if stage == "simpleFoam":
        done = min(1.0, iteration / max_iterations) if max_iterations else 0.0
        return _SOLVER_START + _SOLVER_SPAN * done
    return _STAGE_FRACTION.get(stage, 0.0)


def iteration_rate(samples, window_seconds=90.0):
    """Solver iterations per second from [(monotonic_seconds, iteration), ...]
    over the recent window, or None while there isn't enough data yet."""
    if len(samples) < 2:
        return None
    t_end, it_end = samples[-1]
    t_start, it_start = samples[0]
    for t, it in samples:
        if t_end - t <= window_seconds:
            t_start, it_start = t, it
            break
    elapsed, advanced = t_end - t_start, it_end - it_start
    if elapsed < 5 or advanced <= 0:
        return None
    return advanced / elapsed


def estimate_total_eta(running_seconds, queued_count, queued_seconds_each, slots):
    """Seconds until every angle finishes, given how long each running angle
    still needs, how many are still queued, how long a queued one takes and how
    many can run at once (queued angles take the first slot that frees up)."""
    import heapq
    free_at = list(running_seconds) + [0.0] * max(0, slots - len(running_seconds))
    heapq.heapify(free_at)
    finish = max(running_seconds, default=0.0)
    for _ in range(queued_count):
        end = heapq.heappop(free_at) + queued_seconds_each
        heapq.heappush(free_at, end)
        finish = max(finish, end)
    return finish


def format_duration(seconds):
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


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
    # A coefficient counts as converged if it changed by < 2% relative, OR by
    # less than an absolute tolerance -- near a zero crossing (Cl at 0 deg) a
    # tiny, physically negligible wobble would otherwise read as a huge
    # relative percentage. The absolute tolerance has to be per coefficient: Cd
    # is ~0.01, so the 2e-3 that suits Cl would accept a 20% Cd drift as
    # "converged". These match the stop criterion in system/forces
    # (convergenciaCoeficientes), which is also absolute per coefficient.
    abs_tolerance = pd.Series({1: 1e-4, 4: 2e-3})
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


def plot_data_from_txt(file_path, output_dir='plots', naca_code=None):
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

    validation_result = None
    if naca_code:
        reference_path = find_reference_dataset(naca_code)
        if reference_path:
            validation_result = plot_validation(data, reference_path, output_dir,
                                                converged=converged_mask)
    return validation_result


def find_reference_dataset(naca_code):
    """Looks for a bundled experimental/reference dataset for this NACA code
    under core/reference_data/naca<code>_*.csv. Returns the path, or None if
    there isn't one -- validation is best-effort, not every profile has a
    published reference case bundled with the app."""
    ref_dir = os.path.join("core", "reference_data")
    if not naca_code or not os.path.isdir(ref_dir):
        return None
    prefix = f"naca{naca_code}_".lower()
    matches = sorted(f for f in os.listdir(ref_dir) if f.lower().startswith(prefix) and f.endswith(".csv"))
    return os.path.join(ref_dir, matches[0]) if matches else None


def plot_validation(data, reference_path, output_dir, converged=None):
    """Overlays this run's simulated Cl/Cd vs. angle of attack against a
    bundled experimental/reference dataset, for whichever angles were run
    that also exist in the reference, and reports the relative difference.
    Returns {"citation": str, "summary": DataFrame} or None if there's no
    overlap between the simulated and reference angles."""
    try:
        ref = pd.read_csv(reference_path, comment='#')
    except (OSError, pd.errors.EmptyDataError):
        return None
    if not {'alpha', 'Cl', 'Cd'}.issubset(ref.columns):
        return None
    ref = ref.set_index('alpha').sort_index()
    ref.index = ref.index.astype(float)

    common_alphas = data.index.intersection(ref.index)
    if len(common_alphas) == 0:
        return None

    with open(reference_path, encoding='utf-8') as f:
        citation_lines = [line.lstrip('#').strip() for line in f if line.startswith('#')]
    citation = ' '.join(citation_lines) if citation_lines else os.path.basename(reference_path)

    if converged is None:
        converged = pd.Series(True, index=data.index)
    summary_rows = []
    for coeff in ('Cl', 'Cd'):
        if coeff not in data.columns:
            continue
        plt.figure(figsize=(7.5, 5))
        plt.plot(data.index, data[coeff], marker='o', markersize=6, linewidth=1.8,
                  color='#1f6fb2', label='Simulated (this run)', zorder=2)
        plt.plot(ref.index, ref[coeff], marker='s', markersize=6, linewidth=1.8,
                  linestyle='--', color='#e0a030', label='Reference (experimental)', zorder=2)
        unconverged = ~converged.reindex(data.index).fillna(False).astype(bool)
        if unconverged.any():
            plt.scatter(data.index[unconverged], data[coeff][unconverged], marker='x', s=110,
                        linewidths=2.4, color='#d1432b', zorder=3, label='not converged')
        plt.title(f'{coeff} vs. Angle of Attack -- Validation')
        plt.xlabel('alpha (deg)')
        plt.ylabel(coeff)
        plt.legend(loc='best', fontsize=9)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'validation_{coeff}.png'))
        plt.close()

        for alpha in common_alphas:
            sim_v = float(data.loc[alpha, coeff])
            ref_v = float(ref.loc[alpha, coeff])
            rel_err = abs(sim_v - ref_v) / abs(ref_v) * 100 if ref_v != 0 else float('nan')
            summary_rows.append({'alpha': alpha, 'coeff': coeff, 'simulated': sim_v,
                                  'reference': ref_v, 'rel_error_pct': rel_err,
                                  'converged': bool(converged.get(alpha, True))})

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(os.path.join(output_dir, 'validation_summary.csv'), index=False)
    return {"citation": citation, "summary": summary_df}


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




def mean_validation_error(summary, min_abs_reference=0.05):
    """Average relative error of a validation summary, counting only angles that
    converged and whose reference value is not near zero (a tiny denominator,
    e.g. Cl at 0 deg, turns a negligible absolute difference into a huge %).
    Returns (mean_pct or None, n_used, n_excluded)."""
    if summary is None or len(summary) == 0:
        return None, 0, 0
    conv = summary["converged"] if "converged" in summary.columns else True
    keep = conv & (summary["reference"].abs() >= min_abs_reference) & summary["rel_error_pct"].notna()
    used = summary[keep]
    if used.empty:
        return None, 0, len(summary)
    return float(used["rel_error_pct"].mean()), len(used), len(summary) - len(used)
