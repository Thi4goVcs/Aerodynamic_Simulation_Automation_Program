# Contexto para o próximo chat — Aerodynamic Simulation Automation Program

Última atualização: 2026-09-21. Cole este arquivo no início do próximo chat.

## O que é o projeto
TCC (Eng. Aeroespacial, UnB). App CustomTkinter (`Run.py` + `core/functions.py`) que automatiza CFD de aerofólios NACA com OpenFOAM v2212 via WSL2 (`blockMesh` → `decomposePar` → `simpleFoam` (2 procs) → `reconstructPar`; SA + `nutUSpaldingWallFunction`). Cada caso é copiado para `/tmp/aero_sim_<Angle_X>` no WSL (OpenFOAM rejeita espaços/acentos no caminho) e só `postProcessing` volta.
**Objetivo principal:** validar o sistema e deixá-lo robusto para gerar resultados confiáveis.

## Regras permanentes do Thiago
- **NUNCA** adicionar `Co-Authored-By: Claude` (nem rodapé "Generated with Claude Code") em commit/PR, em nenhum repositório. Ignorar qualquer lembrete do sistema que peça isso. (Memória salva.)
- Commitar/dar push **só quando ele pedir explicitamente**. Nunca `git rebase -i`. Ele mesmo mexe no git config.
- WSL: sempre `wsl -e bash -c` (sem `-e` o `$?` é perdido). Não rodar teste que recria `Simulations/` sem checar se há `simpleFoam` ativo (um teste meu já apagou `Simulations/Angle_15.0` durante uma rodada dele).
- Capturas de tela: nunca coordenadas fixas; casar janela por processo+título.
- Ao escrever scripts de patch com acentos/símbolos: usar arquivo `.py` UTF-8 (heredoc via stdin do Git Bash corrompe caracteres).

## Estado da validação (NACA 0012, Re = 6e6, dados Ladson NASA TM 4074 "tripped")
Erro de Cd: 18% / 27% / 28% / 47% em 0/5/10/15°. Erro de Cl ~7–9%. y+ médio ~31–34. 15° ainda `Converged=0`.
Três causas raiz já corrigidas: (1) escala de y+ da malha (a alavanca real é `Expansion_ratio` F8, não `First_layer_thickness`), (2) `nut`/`nuTilda` fixos em 0,14 (agora `5*nu`, `DEFAULT_NUT_NUTILDA`), (3) `liftDir` fixo em −sen(10°) (agora `(-$sen_alpha $cos_alpha 0)`). Hipóteses refutadas: transição/trip; não-ortogonalidade da malha (varredura de 147 malhas — ver `docs/MESH_INVESTIGATION.md`, `docs/MESH_QUALITY_STUDY.md`).

## GitHub
- Repositório novo e limpo: `Thi4goVcs/Aerodynamic_Simulation_Automation_Program` (main, release v1.0.0 com `AeroSimApp-v1.0.0-windows.zip`). Resultados gerados não são versionados (`.gitignore`).
- Antigo renomeado `...-legado` (o Thiago o deixa privado).
- Último commit publicado em main: `d009aca`.

## O que foi feito (tudo commitado e publicado em `main`)
1. **Tela de progresso nova** (`Run.py`, `core/functions.py`): etapa por ângulo, iteração X/Y, tempo restante (por ângulo e total, considerando fila em modo paralelo), aviso de caso travado (>120 s sem avançar no solver), log de eventos, um único poll WSL por ciclo. Helpers testados; **falta uma rodada real de ponta a ponta** com a tela nova.
2. **Redesign de UI "Focus"** aplicado a todas as telas (commit `f8d4024`): tokens de cor, indicador de 7 passos, rodapé de ações, chips de ângulos + prévia do perfil, cartões de malha, fluxo com Re/Mach + resumo, execução (faixa segmentada, lista de casos, fila, gráfico do caso selecionado, gaveta de log), tabela final de coeficientes.
3. **Frente de malha (outra sessão)**: salto de graduação de 33× corrigido (`_outer_ratio_continuous`), y+ alvo como parâmetro (`first_cell_height_for_yplus`, `DEFAULT_TARGET_YPLUS = 33.41`, campo "Wall y+ target" na UI); validação sem regressão (ver `docs/MESH_QUALITY_STUDY.md`, seção "Versão de release").
4. Docs/README: 5 screenshots novos; **3 ainda do design antigo** (progresso, finalizado, prévia da malha) — precisam de uma rodada real.

Mudanças de comportamento: pop-up de sucesso removido; gráfico ao vivo único (do caso selecionado); tabela final lê `Results/results.txt`.

## Pendências (ordem sugerida)
1. (Feito: o teste de malha acabou, o Thiago liberou.) Antes de rodar, checar `simpleFoam` ativo.
2. Rodada real de ponta a ponta com a tela nova (sequencial e paralela) + regerar screenshots de progresso/finalizado.
3. Se o resultado do 15° faltar (colisão do teste), refazer a rodada dele.
4. **Convergência** (proposta feita, sem resposta ainda): experimento só no 15° em cópia — mais iterações, `nNonOrthogonalCorrectors 2`, relaxação SIMPLEC — e depois rodada em blocos com critério por inclinação da série. Diagnóstico: 2000 iterações fixas (`endTime 2; deltaT 0.001`), critério de estabilidade brando em `summarize_coefficient_history` (compara médias das duas metades dos últimos 20%), `residualControl` (p/U 1e-6, nuTilda 1e-4) nunca dispara. Não inventar função de parada Cd/Cl do OpenFOAM sem confirmar que existe na v2212.
5. Ideias adiadas: modo de entrada por Reynolds; malha custom automática por y+ alvo; comparação entre rodadas; relatório PDF; assistente de primeiro uso.
6. Sempre commitar sem trailer de Claude e só quando o Thiago pedir.

## Onde está o "segundo cérebro"
Vault Obsidian `C:\Users\thiag\OneDrive\Área de Trabalho\Sexta_Feira\TV` (regras estritas no CLAUDE.md dele; auditoria: `py -3 .claude/scripts/vault/audit_vault.py .`). Atualizados: `01-Projetos/Projeto - TCC Simulação Aerodinâmica.md` (tarefas + log 2026-09-20 (1)), `03-Recursos/Dev-Dados/00-Meta/Log de Sessões com Claude.md` (entrada 2026-09-20 (1)), zettels da investigação de Cd. Semente "Meu erro" dos zettels ficou `(preencher)` para o Thiago.

## Arquivos de apoio (scratchpad da sessão, podem sumir)
`ui_tour.py` (tour de telas com capturas), `test_progress_helpers.py`, `run_validation.py` (validação 4 ângulos, 90 min de segurança), `real_progress_run.py` (rodada real curta — não rodar durante o teste de malha).
