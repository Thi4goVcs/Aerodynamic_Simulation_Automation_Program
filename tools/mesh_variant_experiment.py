"""
Testa variantes do blockMeshDict gerado, para separar CAUSA de CORRELACAO nas
metricas de qualidade. Nao altera o gerador (core/functions.py): parte do dict
que o app produz e aplica remendos textuais pontuais, de forma que cada variante
difere da linha de base em um unico parametro.

Variantes:
  base      -- exatamente o que o app gera hoje
  corner0   -- vertices 8/10 (canto de saida) fixos em y=0, ou seja, sem o
               deslocamento com o angulo de ataque
  wakeNN    -- razao de expansao da aresta de saida (O18) trocada por NN,
               desacoplando o refino da esteira distante do da camada limite
  wakeNN_corner0 -- as duas juntas

Uso:
    py -3 tools/mesh_variant_experiment.py --profile 0012 --angles 0,15 --wake-ratio 50
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "tools"))
sys.path.insert(0, str(APP_DIR / "core"))

import functions  # noqa: E402
import mesh_quality_sweep as sweep  # noqa: E402


def wake_outlet_ratio(velocity, nu):
    """Reproduz O18 do blockMeshDirect para a condicao de escoamento dada."""
    first_layer = functions.first_layer_thickness_for_flow(velocity, nu)
    expansion = functions.expansion_ratio_for_flow(velocity, nu)
    n_bl_1 = n_bl_2 = 100
    max_cell_inlet = 1e-6
    max_cell_outlet = 4e-6
    max_cell_inlet_outlet = 1e-5
    h8 = first_layer * expansion ** n_bl_1
    o13 = max_cell_inlet / h8
    return max_cell_inlet_outlet * o13 / max_cell_outlet * (n_bl_2 + n_bl_1) / n_bl_2


def patch_fixed_corner(text):
    text = re.sub(r"(\(\t\d+\t)(-?\d+)(\t0\t\)\t//\t8\b)", r"\g<1>0\g<3>", text)
    text = re.sub(r"(\(\t\d+\t)(-?\d+)(\t0\.01\t\)\t//\t10\b)", r"\g<1>0\g<3>", text)
    return text


def patch_wake_ratio(text, o18, new_ratio):
    original_direct = "\t%0.9f\t%0.9f\n" % (o18, o18)
    original_inverse = "\t%0.9f\t%0.9f\n" % (1 / o18, 1 / o18)
    if original_direct not in text or original_inverse not in text:
        raise RuntimeError("nao achei as linhas de grading O18 no dict gerado")
    text = text.replace(original_direct, "\t%0.9f\t%0.9f\n" % (new_ratio, new_ratio))
    text = text.replace(original_inverse, "\t%0.9f\t%0.9f\n" % (1 / new_ratio, 1 / new_ratio))
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="0012")
    parser.add_argument("--angles", default="0,15")
    parser.add_argument("--velocity", type=float, default=60.0)
    parser.add_argument("--nu", type=float, default=1e-5)
    parser.add_argument("--wake-ratio", type=float, default=50.0)
    parser.add_argument("--outdir", default="studies/mesh_quality/variants")
    args = parser.parse_args()

    outdir = APP_DIR / args.outdir
    dicts_dir = outdir / "dicts"
    logs_dir = outdir / "logs"
    for directory in (dicts_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    o18 = wake_outlet_ratio(args.velocity, args.nu)
    print("O18 atual (razao de expansao da aresta de saida) = %.1f" % o18)
    print("variante wake%g troca esse valor por %g\n" % (args.wake_ratio, args.wake_ratio))

    case_ids = []
    for angle in sweep.parse_angles(args.angles):
        scratch = dicts_dir / "_tmp"
        sweep.generate_case_dict(scratch, args.profile, angle, args.velocity, args.nu)
        base_text = (scratch / "mesh_standard").read_text()
        shutil.rmtree(scratch)

        tag = str(angle).replace("-", "m").replace(".", "p")
        variants = {
            "a%s_base" % tag: base_text,
            "a%s_corner0" % tag: patch_fixed_corner(base_text),
            "a%s_wake%g" % (tag, args.wake_ratio): patch_wake_ratio(base_text, o18, args.wake_ratio),
            "a%s_wake%g_corner0" % (tag, args.wake_ratio):
                patch_wake_ratio(patch_fixed_corner(base_text), o18, args.wake_ratio),
        }
        for name, text in variants.items():
            (dicts_dir / (name + ".blockMeshDict")).write_text(text)
            case_ids.append(name)

    print("Rodando %d variantes no WSL...\n" % len(case_ids))
    script = sweep.build_wsl_script(dicts_dir, case_ids, write_sets=True, tag="variants")
    output = sweep.run_wsl_script(script, timeout=3600, tag="variants")
    logs = sweep.split_case_logs(output)

    header = ("%-26s %-12s %-12s %-12s %-9s %s"
              % ("variante", "nonOrtho", "AR_max", "skew", "falhas", "centroide das faces ruins"))
    print(header)
    print("-" * len(header))
    for case_id in case_ids:
        log = logs.get(case_id, "")
        (logs_dir / (case_id + ".log")).write_text(log, encoding="utf-8")
        row = sweep.parse_case_log(log) if log else {}
        row.update(sweep.parse_set_locations(log) if log else {})
        location = ""
        if row.get("nonOrthoFaces_centroid_x") is not None:
            location = "x=%.1f y=%.2f (perto do perfil: %.0f%%)" % (
                row.get("nonOrthoFaces_centroid_x", float("nan")),
                row.get("nonOrthoFaces_centroid_y", float("nan")),
                100 * row.get("nonOrthoFaces_near_field_frac", 0))
        print("%-26s %-12s %-12s %-12s %-9s %s"
              % (case_id, row.get("max_non_ortho", "?"), row.get("max_aspect_ratio", "?"),
                 row.get("max_skewness", "?"), row.get("failed_checks", "?"), location))

    return 0


if __name__ == "__main__":
    sys.exit(main())
