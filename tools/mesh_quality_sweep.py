"""
Varredura de qualidade de malha: gera uma malha para cada combinacao
(perfil x angulo), roda blockMesh + checkMesh no WSL e tabula as metricas de
qualidade em CSV. Nao resolve nada -- so malha, entao cada caso custa segundos
em vez dos ~30-40 min de uma simulacao completa.

Uso:
    py -3 tools/mesh_quality_sweep.py --profiles 0012 --angles 0,5,10,15
    py -3 tools/mesh_quality_sweep.py --profiles 0009,0012,0018 --angles 0:20:5

O app gera a malha em coordenadas.dat/mesh_standard na raiz; esta ferramenta
trabalha inteiramente num diretorio proprio (--workdir) para poder rodar em
paralelo com uma simulacao do app sem disputar esses arquivos.
"""

import argparse
import csv
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "core"))

import functions  # noqa: E402

FOAM_BASHRC = "/usr/lib/openfoam/openfoam2212/etc/bashrc"
WSL_ROOT = "/tmp/mesh_sweep"
TEMPLATE_REL = Path("core") / "Standard" / "Incompressible"


# --------------------------------------------------------------------------- #
# Geracao da malha (lado Windows)
# --------------------------------------------------------------------------- #

def write_airfoil_coordinates(path, naca_code, num_points=102):
    """
    Escreve coordenadas.dat no mesmo formato que o app (Run.py search_airfoil):
    num_points pontos do extradorso (bordo de fuga -> bordo de ataque) seguidos
    de num_points pontos do intradorso (bordo de ataque -> bordo de fuga).
    blockMeshDirect assume exatamente essa ordem ao fatiar o arquivo em duas
    splines.
    """
    m = int(naca_code[0]) / 100
    p = int(naca_code[1]) / 10
    t = int(naca_code[2:]) / 100
    xu, yu, xl, yl = functions.naca4digit(m, p, t, 1.0, num_points)
    with open(path, "w") as f:
        for i in range(num_points):
            f.write("{:.6f} {:.6f}\n".format(xu[i], yu[i]))
        for i in range(num_points - 1, -1, -1):
            f.write("{:.6f} {:.6f}\n".format(xl[i], yl[i]))
    return t


def trailing_edge_gap(naca_code):
    """
    Espessura do bordo de fuga do perfil NACA 4 digitos em x=c. A formula
    classica nao fecha o bordo de fuga (deixa ~1.05% da espessura maxima), e o
    blockMeshDict ancora a spline num vertice unico em (1,0,0) -- entao esse gap
    vira um degrau geometrico no bordo de fuga.
    """
    t = int(naca_code[2:]) / 100
    yt_at_1 = 5 * t * (0.2969 - 0.1260 - 0.3516 + 0.2843 - 0.1015)
    return 2 * yt_at_1


def generate_case_dict(case_dir, naca_code, angle, velocity, nu):
    """Gera coordenadas.dat + mesh_standard (blockMeshDict) dentro de case_dir."""
    case_dir.mkdir(parents=True, exist_ok=True)
    write_airfoil_coordinates(case_dir / "coordenadas.dat", naca_code)

    first_layer = functions.first_layer_thickness_for_flow(velocity, nu)
    expansion = functions.expansion_ratio_for_flow(velocity, nu)

    previous_cwd = os.getcwd()
    try:
        os.chdir(case_dir)
        functions.blockMeshDirect(angle, first_layer_thickness=first_layer,
                                  expansion_ratio=expansion)
    finally:
        os.chdir(previous_cwd)

    return {
        "first_layer_thickness": first_layer,
        "expansion_ratio": expansion,
        "first_cell_height": functions._boundary_layer_first_cell(
            functions._REFERENCE_BOUNDARY_LAYER_THICKNESS, expansion,
            functions._REFERENCE_N_BOUNDARY_LAYER_CELLS),
    }


def wake_corner_offset(angle, distance_to_outlet=20):
    """
    Deslocamento vertical (inteiro) do canto de saida do dominio, que e a UNICA
    dependencia com o angulo dentro do blockMeshDirect -- ver vertices 8 e 10.
    O round() deixa a malha constante por faixas de angulo.
    """
    return round(math.sin(math.radians(angle)) * (distance_to_outlet + 1))


def wake_block_shear_deg(angle, distance_to_inlet=20, distance_to_outlet=20):
    """
    Angulo de cisalhamento do bloco da esteira no vertice do bordo de fuga:
    desvio da ortogonalidade entre a aresta (1->8) e a aresta (1->2).
    """
    k = wake_corner_offset(angle, distance_to_outlet)
    return math.degrees(math.atan2(k, distance_to_outlet))


# --------------------------------------------------------------------------- #
# Execucao no WSL
# --------------------------------------------------------------------------- #

def to_wsl_path(path):
    text = str(Path(path).resolve()).replace("\\", "/")
    if len(text) > 1 and text[1] == ":":
        drive = text[0].lower()
        text = "/mnt/" + drive + text[2:]
    return text


def build_wsl_script(dicts_dir, case_ids, write_sets=False, tag="default"):
    template_unix = to_wsl_path(APP_DIR / TEMPLATE_REL)
    dicts_unix = to_wsl_path(dicts_dir)
    sets_flag = " -writeSets obj" if write_sets else ""

    # sem `set -u`/`set -e`: o bashrc do OpenFOAM referencia variaveis nao
    # definidas e aborta o shell inteiro sob `set -u`
    lines = [
        "source %s >/dev/null 2>&1" % FOAM_BASHRC,
        'ROOT="%s_%s"' % (WSL_ROOT, tag),
        'rm -rf "$ROOT"; mkdir -p "$ROOT/_template"',
        'cp -r "%s/." "$ROOT/_template/"' % template_unix,
        'cp -r "%s" "$ROOT/dicts"' % dicts_unix,
        'cd "$ROOT/_template" && rm -rf 0 && cp -r 0.orig 0',
    ]
    for case_id in case_ids:
        lines += [
            'echo "===CASE %s BEGIN==="' % case_id,
            'rm -rf "$ROOT/case"; cp -r "$ROOT/_template" "$ROOT/case"',
            'cp "$ROOT/dicts/%s.blockMeshDict" "$ROOT/case/system/blockMeshDict"' % case_id,
            'cd "$ROOT/case"',
            'start=$(date +%s.%N)',
            'blockMesh 2>&1 | tail -25',
            'echo "---CHECKMESH---"',
            'checkMesh%s 2>&1' % sets_flag,
            'echo "---ELAPSED $(echo "$(date +%s.%N) - $start" | bc)---"',
        ]
        if write_sets:
            # os .obj dos conjuntos ruins sao pequenos (centenas de pontos);
            # vao inteiros para o log e sao reduzidos a estatisticas no Python
            lines += [
                'for f in $(find postProcessing -name "*.obj" 2>/dev/null); do',
                '  echo "===OBJ $(basename $f .obj) BEGIN==="',
                '  grep "^v " "$f"',
                '  echo "===OBJ END==="',
                'done',
            ]
        lines += [
            'cd "$ROOT"; rm -rf "$ROOT/case"',
            'echo "===CASE %s END==="' % case_id,
        ]
    lines.append('rm -rf "$ROOT"')
    return "\n".join(lines) + "\n"


def run_wsl_script(script, timeout, tag="default"):
    """
    O script vai para um arquivo no WSL antes de rodar: o bashrc do OpenFOAM
    referencia variaveis nao definidas e derruba o shell sob `set -u`, e o
    proprio arquivo evita depender de como o stdin e consumido.
    """
    script_path = "/tmp/mesh_sweep_batch_%s.sh" % tag
    subprocess.run(["wsl", "-e", "bash", "-c", "cat > %s" % script_path],
                   input=script.encode("utf-8"),
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   timeout=120, check=True)
    result = subprocess.run(["wsl", "-e", "bash", script_path],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=timeout)
    return result.stdout.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Parsing do checkMesh
# --------------------------------------------------------------------------- #

NUM = r"([-+]?[\d.]+(?:[eE][-+]?\d+)?)"

PATTERNS = {
    "points": re.compile(r"^\s*points:\s+(\d+)", re.M),
    "faces": re.compile(r"^\s*faces:\s+(\d+)", re.M),
    "cells": re.compile(r"^\s*cells:\s+(\d+)", re.M),
    "max_non_ortho": re.compile(r"non-orthogonality Max:\s*" + NUM),
    "avg_non_ortho": re.compile(r"non-orthogonality Max:\s*[-+\d.eE]+\s*average:\s*" + NUM),
    "severe_non_ortho_faces": re.compile(r"severely non-orthogonal .*?faces:\s*(\d+)"),
    "max_skewness": re.compile(r"Max skewness\s*=\s*" + NUM),
    "skew_faces": re.compile(r"Max skewness\s*=\s*[-+\d.eE]+,\s*(\d+) highly skew"),
    # checkMesh imprime a razao de aspecto de duas formas: "Max aspect ratio =
    # 660.9 OK." quando passa, e "***High aspect ratio cells found, Max aspect
    # ratio: 17258.4, number of cells 1170" quando reprova
    "max_aspect_ratio": re.compile(r"Max aspect ratio\s*[=:]\s*" + NUM),
    "high_ar_cells": re.compile(r"High aspect ratio cells found.*?number of cells\s*(\d+)"),
    "min_face_area": re.compile(r"Minimum face area\s*=\s*" + NUM),
    "min_volume": re.compile(r"Min volume\s*=\s*" + NUM),
    "max_volume": re.compile(r"Max volume\s*=\s*" + NUM),
    "max_cell_openness": re.compile(r"Max cell openness\s*=\s*" + NUM),
    "failed_checks": re.compile(r"Failed (\d+) mesh check"),
    "elapsed_s": re.compile(r"---ELAPSED\s+([\d.]+)---"),
}


def parse_case_log(log):
    row = {}
    for key, pattern in PATTERNS.items():
        match = pattern.search(log)
        if match is None:
            row[key] = ""
            continue
        text = match.group(1)
        try:
            row[key] = int(text) if key in ("points", "faces", "cells",
                                            "severe_non_ortho_faces", "high_ar_cells",
                                            "skew_faces", "failed_checks") else float(text)
        except ValueError:
            row[key] = text

    if row["failed_checks"] == "":
        row["failed_checks"] = 0 if "Mesh OK" in log else ""
    row["mesh_ok"] = "Mesh OK" in log
    row["blockmesh_ok"] = "End" in log.split("---CHECKMESH---")[0]
    row["warnings"] = " | ".join(
        line.strip().lstrip("*").strip()
        for line in log.splitlines() if line.strip().startswith("*")
    )[:500]
    return row


OBJ_BLOCK = re.compile(r"===OBJ (\S+) BEGIN===(.*?)===OBJ END===", re.S)

# caixa que envolve o perfil e a esteira imediata: uma face ruim aqui dentro
# pode contaminar a integracao de forcas na superficie; fora dela, nao
NEAR_FIELD_X = (-0.5, 2.0)
NEAR_FIELD_Y = (-1.0, 1.0)


def parse_set_locations(log):
    """
    Reduz os .obj dos conjuntos ruins (nonOrthoFaces, highAspectRatioCells, ...)
    a estatisticas de posicao: centroide, caixa delimitadora e a fracao dos
    pontos que cai perto do perfil.
    """
    stats = {}
    for match in OBJ_BLOCK.finditer(log):
        name = match.group(1)
        xs, ys, near = [], [], 0
        for line in match.group(2).splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0] != "v":
                continue
            x, y = float(parts[1]), float(parts[2])
            xs.append(x)
            ys.append(y)
            if (NEAR_FIELD_X[0] <= x <= NEAR_FIELD_X[1]
                    and NEAR_FIELD_Y[0] <= y <= NEAR_FIELD_Y[1]):
                near += 1
        if not xs:
            continue
        stats["%s_n_points" % name] = len(xs)
        stats["%s_centroid_x" % name] = round(sum(xs) / len(xs), 4)
        stats["%s_centroid_y" % name] = round(sum(ys) / len(ys), 4)
        stats["%s_xmin" % name] = round(min(xs), 4)
        stats["%s_xmax" % name] = round(max(xs), 4)
        stats["%s_near_field_frac" % name] = round(near / len(xs), 4)
    return stats


def split_case_logs(output):
    logs = {}
    pattern = re.compile(r"===CASE (\S+) BEGIN===(.*?)===CASE \1 END===", re.S)
    for match in pattern.finditer(output):
        logs[match.group(1)] = match.group(2)
    return logs


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_angles(text):
    angles = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if ":" in chunk:
            start, stop, step = (float(v) for v in chunk.split(":"))
            value = start
            while value <= stop + 1e-9:
                angles.append(round(value, 3))
                value += step
        else:
            angles.append(float(chunk))
    return angles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", default="0012",
                        help="codigos NACA de 4 digitos separados por virgula")
    parser.add_argument("--angles", default="0,5,10,15",
                        help="lista de angulos, ou faixas inicio:fim:passo")
    parser.add_argument("--velocity", type=float, default=60.0)
    parser.add_argument("--nu", type=float, default=1e-5)
    parser.add_argument("--outdir", default=None,
                        help="destino dos resultados (default: studies/mesh_quality/<timestamp>)")
    parser.add_argument("--workdir", default=None,
                        help="onde gerar os blockMeshDicts (default: dentro de outdir)")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="casos por invocacao do WSL")
    parser.add_argument("--timeout", type=int, default=3600,
                        help="timeout por lote, em segundos")
    parser.add_argument("--keep-dicts", action="store_true",
                        help="preserva os blockMeshDicts gerados")
    parser.add_argument("--write-sets", action="store_true",
                        help="pede ao checkMesh os conjuntos de faces ruins (mais lento)")
    parser.add_argument("--tag", default="default",
                        help="sufixo do diretorio de trabalho no WSL; use um valor "
                             "distinto para rodar varreduras simultaneas")
    args = parser.parse_args()

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    angles = parse_angles(args.angles)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else APP_DIR / "studies" / "mesh_quality" / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workdir) if args.workdir else outdir / "dicts"
    workdir.mkdir(parents=True, exist_ok=True)
    logdir = outdir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)

    cases = []
    print("Gerando %d blockMeshDicts (%d perfis x %d angulos)..."
          % (len(profiles) * len(angles), len(profiles), len(angles)))
    for profile in profiles:
        for angle in angles:
            case_id = "n%s_a%s" % (profile, str(angle).replace("-", "m").replace(".", "p"))
            case_dir = workdir / case_id
            info = generate_case_dict(case_dir, profile, angle, args.velocity, args.nu)
            shutil.move(str(case_dir / "mesh_standard"),
                        str(workdir / (case_id + ".blockMeshDict")))
            shutil.rmtree(case_dir)
            cases.append({
                "case_id": case_id,
                "profile": profile,
                "angle": angle,
                "velocity": args.velocity,
                "nu": args.nu,
                "thickness": int(profile[2:]) / 100,
                "camber": int(profile[0]) / 100,
                "te_gap": trailing_edge_gap(profile),
                "wake_corner_k": wake_corner_offset(angle),
                "wake_shear_deg": round(wake_block_shear_deg(angle), 4),
                **info,
            })

    rows = []
    total = len(cases)
    for start in range(0, total, args.batch_size):
        batch = cases[start:start + args.batch_size]
        print("Lote %d-%d de %d: blockMesh + checkMesh no WSL..."
              % (start + 1, start + len(batch), total))
        script = build_wsl_script(workdir, [c["case_id"] for c in batch],
                                  write_sets=args.write_sets, tag=args.tag)
        began = time.time()
        try:
            output = run_wsl_script(script, args.timeout, tag=args.tag)
        except subprocess.TimeoutExpired:
            print("  TIMEOUT no lote -- pulando")
            continue
        logs = split_case_logs(output)
        print("  lote concluido em %.1f s" % (time.time() - began))

        for case in batch:
            log = logs.get(case["case_id"], "")
            (logdir / (case["case_id"] + ".log")).write_text(log, encoding="utf-8")
            row = dict(case)
            row.update(parse_case_log(log) if log else {"mesh_ok": False})
            if args.write_sets and log:
                row.update(parse_set_locations(log))
            rows.append(row)
            print("    %-16s nonOrtho_max=%-8s skew_max=%-8s AR_max=%-10s falhas=%s"
                  % (case["case_id"], row.get("max_non_ortho", "?"),
                     row.get("max_skewness", "?"), row.get("max_aspect_ratio", "?"),
                     row.get("failed_checks", "?")))

    csv_path = outdir / "mesh_quality.csv"
    if rows:
        fieldnames = []
        for row in rows:  # casos sem conjuntos ruins nao tem as colunas de posicao
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(rows)
        print("\nCSV: %s" % csv_path)

    if not args.keep_dicts:
        for dict_file in workdir.glob("*.blockMeshDict"):
            dict_file.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
