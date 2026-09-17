#!/bin/bash
# Este script inicializa o OpenFOAM e executa os comandos necessários

# Carrega o ambiente OpenFOAM
source /usr/lib/openfoam/openfoam2212/etc/bashrc

# Executa o comando de limpeza
./Allclean

# Executa a simulação
./Allrun