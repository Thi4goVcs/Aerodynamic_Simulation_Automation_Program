# Passagem: mudanças no app vindas do estudo de malha

Para o chat responsável pelo app. Detalhes técnicos e números em
[MESH_QUALITY_STUDY.md](MESH_QUALITY_STUDY.md).

## Já feito — não refazer

Validado em 2026-09-21 (NACA 0012, 0/5/10/15°, Re=6·10⁶): sem regressão em Cl/Cd,
malha bem mais limpa (não-ortogonalidade 77 → 57°, razão de aspecto 661 → 370,
0 reprovações no `checkMesh`, mesmas 200 mil células).

- `core/functions.py`: `wake_outlet_expansion_ratio` (O18), `_wake_corner_offset`,
  `_outer_ratio_continuous` (correção do salto de 33× na graduação),
  `first_cell_height_for_yplus` + `DEFAULT_TARGET_YPLUS = 33.41`.
- `Run.py`: campo **Wall y+ target** nas opções avançadas das duas telas de fluxo,
  incluído no reset das opções avançadas e no salvar/carregar preset (chave `yplus`).

Decisões tomadas, com teste: **manter o domínio em 20 cordas** (100 cordas derrubou
o Cl em ~6%) e **manter o y+ padrão em 33,41** (y+ ≈ 1 funciona, mas piorou o Cd).

---

## 1. Critério de parada pela estabilidade do coeficiente — prioridade alta

**Problema:** o `simpleFoam` para por resíduo (`residualControl` p/U 1e-6), e resíduo
depende da malha. Trocando só a malha, a mesma configuração parou em 800 iterações
em vez de 2000, com o Cd ainda derivando — e o usuário não fica sabendo.

**Solução nativa do OpenFOAM v2212** (sem código novo; é o que o tutorial oficial
`simpleFoam/simpleCar` faz). Em `core/Standard/Incompressible/system/forces` e
`core/Standard/Compressible/system/forces`, junto dos outros function objects:

```
convergenciaCoeficientes
{
    type            runTimeControl;
    libs            (utilityFunctionObjects);
    conditions
    {
        coeficientesEstaveis
        {
            type            average;
            functionObject  forceCoeffs;
            fields          (Cd Cl);
            tolerance       1e-3;
            window          200;
            windowType      exact;
        }
    }
    satisfiedAction end;
}
```

Junto:

- `system/fvSolution` (nos dois templates): desligar o `residualControl` (remover o
  bloco ou pôr 1e-12).
- `system/controlDict`: `endTime` vira teto de segurança — `endTime 4;` (= 4000
  iterações com `deltaT 0.001`).
- `forceCoeffs` em `system/forces`: trocar `writeControl outputTime;` por
  `writeControl timeStep;`. Hoje o `coefficient.dat` tem só 20 amostras em 2000
  iterações.

**Verificar ao implementar:**

- Se o `runTimeControl` lê o coeficiente a cada iteração, e não só nos passos de
  escrita.
- Rodar os 4 ângulos: 0/5/10° devem ficar a ~0,5% dos resultados da release, e é
  bom registrar em quantas iterações cada um parou. O 15° deve ir até o teto sem
  convergir — é o esperado.

**Alinhar o critério pós-rodada** (`summarize_coefficient_history`,
`core/functions.py` ~linha 1176), senão os dois critérios discordam:

- Com 20 amostras, a janela de 20% vira **5 pontos** (últimas 500 iterações). Com
  `writeControl timeStep` isso se resolve sozinho.
- `abs_tolerance = 2e-3` vale para Cd e Cl, mas o Cd é ~0,01: uma variação de 19% no
  Cd passa como "convergido". A tolerância absoluta só faz sentido para o Cl perto de
  zero (0°). Sugestão: 2e-3 para Cl e ~1e-4 para Cd.

## 2. UI/UX

**a. Mostrar por que cada ângulo parou (tela de progresso/resultados).** Hoje o aviso
de não-convergência é só um `print` no console (`Run.py` ~2344) e o usuário da GUI
não vê. Mostrar por ângulo: "convergiu em 1.240 iterações" ou "atingiu o limite de
4.000 sem convergir (variação 14%) — resultado incerto".

**b. Marcar ângulos não convergidos nos resultados** — ponto vazado nos gráficos e
na tabela de validação, e fora da média de erro (ou com aviso). Hoje o 15° entra na
média do erro mesmo não convergido.

**c. Aviso de envelope na tela de ângulos:** para ângulos a partir de ~12-15°,
algo como "perto do estol; o solver de regime permanente pode não convergir". Em
nenhum teste o 15° convergiu (derivas de 6% a 69%).

**d. Tooltip no campo Wall y+ target**, no padrão do `MESH_METRIC_HELP`. Texto
sugerido: "y+ médio desejado na parede. O padrão (33,41) é o valor validado contra
dados experimentais. Use ~1 para resolver a camada limite até a parede — roda mais
devagar e, nos nossos testes, não melhorou o arrasto." E nos resultados, mostrar o
y+ obtido ao lado do alvo (o `yPlus_avg` já está no `data.txt`).

**e. Aviso de Reynolds baixo** no texto que mostra o Re na tela de fluxo (`Run.py`
~2177): abaixo de Re ≈ 900.000 o controle de y+ satura e a camada limite fica com
malha uniforme. Algo como "Re baixo: o refinamento de parede fica fixo".

**f. Tela de malha customizada — remover "First layer thickness"**
(`Run.py` ~632 e ~656, `CUSTOM_MESH_PARAM_NAMES` ~112, e o argumento repassado em
~782). Depois da correção do salto ele não altera nada na malha. Presets antigos que
tenham a chave devem só ignorá-la. Menor prioridade: os campos de "cell size"
(valores como 1e-8) não são tamanhos físicos, só as razões entre eles importam —
vale explicar ou esconder.

**g. Prévia de malha como portão de qualidade:** se o `checkMesh` reprovar ou a
não-ortogonalidade passar de 70°, avisar antes de iniciar a simulação (avisar, não
bloquear). A malha padrão agora dá 57°, então qualquer reprovação indica uma malha
customizada problemática. Dá para citar a referência no `MESH_METRIC_HELP`
("malha padrão: ~57°").

## 3. Robustez — falhas que a UI deveria impedir

**a. Rodadas simultâneas se destroem.** Os diretórios no WSL são fixos:
`/tmp/aero_sim_{run_id}` (`Run.py` ~2105, onde `run_id` é o ângulo) e
`/tmp/aero_mesh_preview` (~818). Em 2026-09-20 uma segunda rodada apagou os dados
brutos de outra em andamento, sem aviso. Correção: incluir um identificador único da
execução no caminho (ex.: timestamp + pid), procurando **todas** as ocorrências de
`aero_sim_`. Na UI: impedir iniciar uma segunda rodada com outra ativa, ou avisar.

**b. Template sendo sobrescrito.** `core/Standard/Incompressible/0.orig/initialConditions`
foi encontrado com valores de uma rodada antiga (`U_mag 51.48`, `nu 8.58e-6`). O app
deve escrever só na pasta do caso (`Simulations/Angle_X/0.orig`), nunca no template —
achar qual caminho de código grava lá.
