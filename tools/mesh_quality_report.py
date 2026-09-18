"""
Le o CSV produzido pelo mesh_quality_sweep.py e resume: tabelas por angulo e
por perfil, quais casos reprovam no checkMesh e graficos das metricas.

Uso:
    py -3 tools/mesh_quality_report.py studies/mesh_quality/factorial/mesh_quality.csv
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# limiares usuais de checkMesh / pratica de CFD externo
NON_ORTHO_CORRECTORS = 70.0   # acima disso, precisa de nNonOrthogonalCorrectors
NON_ORTHO_REBUILD = 85.0      # acima disso, a recomendacao e refazer a malha
SKEWNESS_LIMIT = 4.0


def as_markdown(frame, float_format="%.2f"):
    return frame.to_string(float_format=lambda v: float_format % v)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    outdir = Path(args.outdir) if args.outdir else csv_path.parent
    # "0012" viraria o inteiro 12 e perderia o codigo do perfil
    data = pd.read_csv(csv_path, dtype={"profile": str})

    numeric = ["max_non_ortho", "avg_non_ortho", "max_aspect_ratio", "max_skewness",
               "severe_non_ortho_faces", "high_ar_cells", "failed_checks", "cells"]
    for column in numeric:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    print("=" * 78)
    print("CASOS: %d  |  perfis: %d  |  angulos: %d"
          % (len(data), data["profile"].nunique(), data["angle"].nunique()))
    print("=" * 78)

    broken = data[data["cells"].isna() | (data["cells"] == 0)]
    if len(broken):
        print("\n## blockMesh FALHOU (%d casos)" % len(broken))
        print(as_markdown(broken[["profile", "angle"]]))

    print("\n## Nao-ortogonalidade maxima (perfil x angulo)")
    pivot_no = data.pivot_table(index="profile", columns="angle", values="max_non_ortho")
    print(as_markdown(pivot_no))

    print("\n## Razao de aspecto maxima (perfil x angulo)")
    pivot_ar = data.pivot_table(index="profile", columns="angle", values="max_aspect_ratio")
    print(as_markdown(pivot_ar, "%.0f"))

    print("\n## Checagens reprovadas do checkMesh (perfil x angulo)")
    pivot_fail = data.pivot_table(index="profile", columns="angle", values="failed_checks")
    print(as_markdown(pivot_fail, "%.0f"))

    print("\n## Efeito do angulo (media sobre todos os perfis)")
    by_angle = data.groupby("angle").agg(
        k_canto=("wake_corner_k", "first"),
        cisalhamento_deg=("wake_shear_deg", "first"),
        nonortho_max=("max_non_ortho", "max"),
        nonortho_medio=("avg_non_ortho", "mean"),
        faces_severas=("severe_non_ortho_faces", "mean"),
        AR_max=("max_aspect_ratio", "max"),
        reprovacoes=("failed_checks", "sum"),
    )
    print(as_markdown(by_angle))

    print("\n## Efeito do perfil (media sobre todos os angulos)")
    by_profile = data.groupby("profile").agg(
        espessura=("thickness", "first"),
        curvatura=("camber", "first"),
        gap_bordo_fuga=("te_gap", "first"),
        nonortho_max=("max_non_ortho", "max"),
        skew_max=("max_skewness", "max"),
        AR_max=("max_aspect_ratio", "max"),
        reprovacoes=("failed_checks", "sum"),
    )
    print(as_markdown(by_profile, "%.4f"))

    # a malha so depende do angulo atraves do canto arredondado da esteira:
    # angulos com o mesmo k deveriam gerar metricas identicas
    print("\n## Malhas agrupadas pelo canto da esteira (k = round(sin(a)*21))")
    by_k = data.groupby(["profile", "wake_corner_k"])["max_non_ortho"].agg(["nunique", "count"])
    inconsistent = by_k[by_k["nunique"] > 1]
    if len(inconsistent) == 0:
        print("Confirmado: mesmo k => mesma nao-ortogonalidade. O angulo entra na")
        print("malha SO por esse inteiro arredondado -- a malha e constante por faixas.")
    else:
        print("Ha variacao dentro do mesmo k (o angulo afeta a malha por outra via):")
        print(as_markdown(inconsistent))

    if "nonOrthoFaces_near_field_frac" in data:
        print("\n## Onde estao as faces nao-ortogonais")
        near = data[["profile", "angle", "nonOrthoFaces_centroid_x",
                     "nonOrthoFaces_centroid_y", "nonOrthoFaces_near_field_frac"]].dropna()
        print(as_markdown(near.head(30), "%.3f"))

    # ---------------------------------------------------------------- graficos
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for profile, group in data.groupby("profile"):
        group = group.sort_values("angle")
        axes[0].plot(group["angle"], group["max_non_ortho"], marker="o", ms=3, label=profile)
        axes[1].plot(group["angle"], group["max_aspect_ratio"], marker="o", ms=3, label=profile)
        axes[2].plot(group["angle"], group["severe_non_ortho_faces"], marker="o", ms=3, label=profile)

    axes[0].axhline(NON_ORTHO_REBUILD, color="red", ls="--", lw=1, label="refazer malha (85)")
    axes[0].axhline(NON_ORTHO_CORRECTORS, color="orange", ls="--", lw=1, label="correctors (70)")
    axes[0].set_ylabel("nao-ortogonalidade max [graus]")
    axes[1].set_ylabel("razao de aspecto max")
    axes[1].set_yscale("log")
    axes[2].set_ylabel("n. de faces severamente nao-ortogonais")
    for axis in axes:
        axis.set_xlabel("angulo de ataque [graus]")
        axis.grid(alpha=0.3)
    axes[0].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    plot_path = outdir / "mesh_quality_vs_angle.png"
    fig.savefig(plot_path, dpi=130)
    print("\nGrafico: %s" % plot_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
