"""
Compara duas rodadas de validacao (antes/depois de uma mudanca) contra os dados
de referencia: erro de Cl e Cd por angulo, y+ e o sinalizador de convergencia.

Cada diretorio precisa conter o `data.txt` e o `validation_summary.csv` que o app
escreve em `plots/`.

Uso:
    py -3 tools/compare_validation.py \
        --antes studies/mesh_quality/baseline_pre_correcoes \
        --depois plots \
        --rotulos "antes,depois"
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def carregar(directory):
    directory = Path(directory)
    dados = pd.read_csv(directory / "data.txt", sep="\t")
    resumo = pd.read_csv(directory / "validation_summary.csv")
    return dados, resumo


def tabela_erros(resumo_antes, resumo_depois, rotulos):
    erros = resumo_antes.merge(resumo_depois, on=["alpha", "coeff"],
                               suffixes=("_antes", "_depois"))
    erros["delta_pp"] = erros["rel_error_pct_depois"] - erros["rel_error_pct_antes"]
    erros = erros[["alpha", "coeff", "reference_antes",
                   "simulated_antes", "simulated_depois",
                   "rel_error_pct_antes", "rel_error_pct_depois", "delta_pp"]]
    return erros.rename(columns={
        "reference_antes": "referencia",
        "simulated_antes": "sim_%s" % rotulos[0],
        "simulated_depois": "sim_%s" % rotulos[1],
        "rel_error_pct_antes": "erro%%_%s" % rotulos[0],
        "rel_error_pct_depois": "erro%%_%s" % rotulos[1],
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--antes", required=True)
    parser.add_argument("--depois", required=True)
    parser.add_argument("--rotulos", default="antes,depois")
    parser.add_argument("--outdir", default="studies/mesh_quality")
    args = parser.parse_args()

    rotulos = [r.strip() for r in args.rotulos.split(",")]
    dados_antes, resumo_antes = carregar(args.antes)
    dados_depois, resumo_depois = carregar(args.depois)

    erros = tabela_erros(resumo_antes, resumo_depois, rotulos)
    print("=" * 96)
    print("ERRO CONTRA A REFERENCIA (delta_pp negativo = melhorou)")
    print("=" * 96)
    for coeff in ("Cl", "Cd"):
        print("\n## %s" % coeff)
        print(erros[erros["coeff"] == coeff].to_string(
            index=False, float_format=lambda v: "%.4g" % v))

    colunas = ["alpha", "yPlus_avg", "yPlus_max", "Converged"]
    fusao = dados_antes[colunas].merge(dados_depois[colunas], on="alpha",
                                        suffixes=("_" + rotulos[0], "_" + rotulos[1]))
    print("\n" + "=" * 96)
    print("y+ E CONVERGENCIA")
    print("=" * 96)
    print(fusao.to_string(index=False, float_format=lambda v: "%.2f" % v))

    media = erros.groupby("coeff")[["erro%%_%s" % rotulos[0],
                                    "erro%%_%s" % rotulos[1]]].mean()
    print("\n## Erro medio por coeficiente")
    print(media.to_string(float_format=lambda v: "%.1f" % v))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for axis, coeff in zip(axes, ("Cl", "Cd")):
        subconjunto = erros[erros["coeff"] == coeff]
        largura = 1.6
        posicoes = subconjunto["alpha"]
        axis.bar(posicoes - largura / 2, subconjunto["erro%%_%s" % rotulos[0]],
                 largura, label=rotulos[0], color="#d62728", alpha=0.85)
        axis.bar(posicoes + largura / 2, subconjunto["erro%%_%s" % rotulos[1]],
                 largura, label=rotulos[1], color="#2ca02c", alpha=0.85)
        axis.set_title("Erro relativo de %s" % coeff)
        axis.set_xlabel("angulo de ataque [graus]")
        axis.set_ylabel("erro [%]")
        axis.set_xticks(posicoes)
        axis.legend()
        axis.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    caminho = Path(args.outdir) / "comparacao_validacao.png"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=135)
    print("\nGrafico: %s" % caminho)
    return 0


if __name__ == "__main__":
    sys.exit(main())
