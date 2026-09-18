"""
Figuras explicativas do estudo de malha: desenha o dominio real (vertices e
arcos como o blockMeshDirect os escreve) e a distribuicao de celulas que as
formulas de graduacao produzem. Nada aqui e esquematico -- as posicoes e
alturas de celula vem das mesmas contas do gerador.

Uso:
    py -3 tools/mesh_quality_figures.py --outdir studies/mesh_quality
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "core"))
import functions  # noqa: E402

A2 = B2 = 20.0          # distancias ate entrada e saida, em cordas
N_BL = 100              # celulas por secao da graduacao em y
D8 = 0.2                # espessura do bloco de camada limite

AZUL = "#1f77b4"
LARANJA = "#ff7f0e"
VERMELHO = "#d62728"
VERDE = "#2ca02c"
CINZA = "#888888"


def wake_corner(angle):
    return round(math.sin(math.radians(angle)) * (B2 + 1))


def cell_boundaries(length, total_ratio, n_cells, start=0.0):
    """Posicoes das faces de uma grade geometrica (total_ratio = ultima/primeira)."""
    r = total_ratio ** (1.0 / (n_cells - 1))
    h1 = length * (r - 1) / (r ** n_cells - 1)
    positions = [start]
    for j in range(n_cells):
        positions.append(positions[-1] + h1 * r ** j)
    return np.array(positions)


def painel_dominio(ax, angle):
    k = wake_corner(angle)
    theta = np.linspace(np.pi / 2, 3 * np.pi / 2, 200)
    ax.plot(1 + A2 * np.cos(theta), A2 * np.sin(theta), color=CINZA, lw=1.5)
    for y in (A2, -A2):
        ax.plot([1, B2 + 1], [y, y], color=CINZA, lw=1.5)
    ax.plot([B2 + 1, B2 + 1], [-A2, A2], color=CINZA, lw=1.5)

    # linha de interface: onde fica a banda refinada da esteira
    ax.plot([1, B2 + 1], [0, k], color=VERMELHO, lw=2.5, zorder=5,
            label="banda refinada da esteira")
    ax.plot([1, B2 + 1], [0, math.tan(math.radians(angle)) * B2],
            color=VERDE, lw=1.6, ls="--", zorder=4,
            label="direcao real do escoamento (%g graus)" % angle)

    ax.plot([0, 1], [0, 0], color="black", lw=4, solid_capstyle="butt", zorder=6)
    ax.annotate("perfil", (0.5, 0), (-6, 5), textcoords="offset points", fontsize=8)
    ax.scatter([B2 + 1], [k], s=60, color=VERMELHO, zorder=7)
    ax.annotate("vertice 8\n(y = %d)" % k, (B2 + 1, k), (-52, 14),
                textcoords="offset points", fontsize=8, color=VERMELHO)
    ax.scatter([19.8], [k * 19.8 / 20], s=180, facecolor="none",
               edgecolor=VERMELHO, lw=2, zorder=7)
    ax.annotate("piores celulas\nmedidas aqui", (19.8, k * 19.8 / 20), (-30, -38),
                textcoords="offset points", fontsize=8, color=VERMELHO)

    ax.set_title("Dominio a %g graus: a banda refinada segue o escoamento" % angle,
                 fontsize=10)
    ax.set_xlabel("x [cordas]")
    ax.set_ylabel("y [cordas]")
    ax.set_aspect("equal")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.2)


def painel_saida(ax, o18_atual, o18_novo):
    janela = 0.35
    for coluna, (o18, cor, rotulo) in enumerate([
            (o18_atual, VERMELHO, "hoje: O18 = %.0f" % o18_atual),
            (o18_novo, VERDE, "proposto: O18 = %.0f" % o18_novo)]):
        faces = cell_boundaries(A2, o18, 2 * N_BL)
        visiveis = faces[faces <= janela]
        for y in visiveis:
            ax.plot([coluna, coluna + 0.8], [y, y], color=cor, lw=0.7)
        ax.plot([coluna, coluna], [0, janela], color=cor, lw=1.2)
        ax.plot([coluna + 0.8, coluna + 0.8], [0, janela], color=cor, lw=1.2)
        primeira = faces[1] - faces[0]
        ax.text(coluna + 0.4, janela * 1.04,
                "%s\n%d celulas nesta janela\n1a celula = %.5f corda"
                % (rotulo, len(visiveis) - 1, primeira),
                ha="center", va="bottom", fontsize=8, color=cor)

    ax.set_xlim(-0.3, 2.1)
    ax.set_ylim(0, janela * 1.35)
    ax.set_xticks([])
    ax.set_ylabel("y a partir da linha da esteira [cordas]")
    ax.set_title("Correcao 1: altura das celulas na saida (x = 21)", fontsize=10)


def painel_degraus(ax):
    angulos = np.linspace(0, 20, 400)
    exato = np.degrees(np.arctan2(np.sin(np.radians(angulos)) * (B2 + 1), B2))
    arredondado = [math.degrees(math.atan2(wake_corner(a), B2)) for a in angulos]

    ax.plot(angulos, angulos, color=CINZA, lw=1.2, ls=":", label="escoamento (referencia)")
    ax.plot(angulos, arredondado, color=VERMELHO, lw=2,
            label="hoje: round(sin a * 21) -- degraus")
    ax.plot(angulos, exato, color=VERDE, lw=1.8, ls="--",
            label="sem arredondar -- segue o angulo")
    ax.fill_between(angulos, angulos, arredondado, color=VERMELHO, alpha=0.12)

    ax.set_xlabel("angulo de ataque [graus]")
    ax.set_ylabel("inclinacao da banda refinada [graus]")
    ax.set_title("Correcao 2 revisada: manter a inclinacao, tirar o degrau", fontsize=10)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.25)


def painel_perfil_y(ax):
    secao1 = cell_boundaries(D8, functions.expansion_ratio_for_flow(60.0, 1e-5) ** N_BL,
                             N_BL, start=0.0)
    secao2 = cell_boundaries(A2 - D8, 9255.22, N_BL, start=D8)
    y1, h1 = secao1[:-1], np.diff(secao1)
    y2, h2 = secao2[:-1], np.diff(secao2)

    ax.semilogy(y1, h1, color=AZUL, lw=2, label="secao 1 (y = 0 a 0,2)")
    ax.semilogy(y2, h2, color=LARANJA, lw=2, label="secao 2 (y = 0,2 a 20)")
    ax.axvline(D8, color=VERMELHO, ls="--", lw=1.2)
    ax.annotate("salto de 33x para baixo\nna emenda das duas secoes",
                (D8, h2[0]), (28, -6), textcoords="offset points",
                fontsize=8, color=VERMELHO,
                arrowprops=dict(arrowstyle="->", color=VERMELHO, lw=1.2))
    ax.set_xlim(0, 2.5)
    ax.set_xlabel("distancia da linha da esteira, y [cordas]")
    ax.set_ylabel("altura da celula [cordas]")
    ax.set_title("Quao rapido a malha engrossa saindo da banda", fontsize=10)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.25, which="both")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="studies/mesh_quality")
    parser.add_argument("--angle", type=float, default=15.0)
    parser.add_argument("--wake-ratio", type=float, default=50.0)
    args = parser.parse_args()

    first_layer = functions.first_layer_thickness_for_flow(60.0, 1e-5)
    expansion = functions.expansion_ratio_for_flow(60.0, 1e-5)
    h8 = first_layer * expansion ** N_BL
    o18_atual = 1e-5 * (1e-6 / h8) / 4e-6 * (2 * N_BL) / N_BL

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10))
    painel_dominio(axes[0][0], args.angle)
    painel_saida(axes[0][1], o18_atual, args.wake_ratio)
    painel_degraus(axes[1][0])
    painel_perfil_y(axes[1][1])
    fig.tight_layout()

    outdir = APP_DIR / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "mesh_corrections_explained.png"
    fig.savefig(path, dpi=135)
    print("figura: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
