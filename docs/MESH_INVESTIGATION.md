# Investigação de malha — NACA 0012, Re=6.000.000

Contexto de trabalho para a frente específica de **qualidade de malha**, separada da sessão principal do app. Se você está começando uma conversa nova só pra isso, leia este arquivo inteiro antes de mexer em qualquer coisa — ele existe pra não precisar reconstruir o histórico do zero.

## Objetivo desta frente

Validar o app contra dados experimentais da literatura (NACA 0012, Ladson/NASA TM 4074, Re=6.000.000, M=0.15) rodando os mesmos ângulos que a referência e comparando Cl/Cd. Faltam 2 de 4 ângulos (5° e 15°) para validar dentro de uma margem razoável (~<30% de erro, como já conseguimos em 0° e 10°).

## Onde estamos (rodada real pós-fix do liftDir, 2026-09-18, tarde)

**Validação rodada de novo com os três fixes juntos (malha + nut/nuTilda + liftDir). Resultado: os 4 ângulos validam dentro de margem de engenharia razoável — o `liftDir` era mesmo a explicação dominante do erro de Cd.**

| Ângulo | Cl erro | Cd erro | Situação |
|---|---|---|---|
| 0° | 102%* | 18% | ✅ bom (Cl% inflado por denominador perto de zero — Cl simulado 0,00012 vs ref -0,00724, diferença absoluta pequena) |
| 5° | 7,5% | 27% | ✅ bom (era 522%) |
| 10° | 7,5% | 28% | ✅ bom |
| 15° | 9% | 47% | ⚠️ o pior dos quatro, mas já em faixa razoável (era 575%); `Converged=0` ainda — ver abaixo |

Polar de arrasto agora é fisicamente sensata e monotônica: Cd = 0,0096 → 0,0108 → 0,0152 → 0,0269 (antes tinha um pico em 5° e caía em 10°, sinal claro de erro numérico). y+ médio 31-34 em todos os ângulos, dentro da faixa validada.

**Em aberto:** 15° segue com `Converged=0` no critério de estabilidade (últimos 20% da série ainda variando >2%) mesmo validando razoavelmente bem no valor médio — vale olhar se é convergência lenta genuína (perto de condições de carga mais alta) ou se ainda sobra alguma imprecisão de malha residual (a não-ortogonalidade crescente com o ângulo, documentada abaixo, não toca a superfície então não deveria afetar força — mas vale descartar de vez rodando mais iterações em 15° isoladamente antes de declarar fechado).

Referência (Ladson, tripped/80-grit, dados exatos): ver `core/reference_data/naca0012_ladson_re6e6.csv` e a fonte primária em `https://tmbwg.github.io/turbmodels/NACA0012_validation/CLCD_Ladson_expdata.dat`.

## O que já foi corrigido (não repetir)

1. **Malha não escalava com Reynolds** — `First_layer_thickness` (E8), apesar do nome, **não controla** a altura da célula na parede; só alimenta a grade do bloco *longe* da parede (via `O13`/farfield). Quem controla o y+ de verdade é `Expansion_ratio` (F8) combinado com `Boundary_layer_thickness` (D8) e `Number_of_mesh_on_boundary_layer_1` (N10) — ver `O10 = F8**N10`, o bloco escrito em `core/functions.py` linhas ~274-354. Corrigido com `functions.expansion_ratio_for_flow(velocity, nu)` (busca binária pela razão de expansão que dá a altura de 1ª célula alvo, calibrada contra o ponto conhecido-bom: y+≈37-48 em 15 m/s). y+ medido caiu de ~100-130 para ~30-37 depois disso — confirmado com simulação real, não só teoria.
2. **`nut`/`nuTilda` (viscosidade turbulenta de referência) fixos em 0,14, independente de `nu`** — com `nu=1e-5` isso dava uma razão `nut/nu=14.000` (o padrão pro modelo SA em aero externa é ~3-5). Inundava o domínio inteiro de viscosidade turbulenta artificial. Corrigido: `DEFAULT_NUT_NUTILDA = 5 * 1e-5` em `Run.py` (linha ~28). Confirmado contra o próprio NASA Turbulence Modeling Resource: uma simulação SA bem resolvida desse caso dá Cd≈0,0081-0,0083 em 0°, quase igual ao experimento — então nem é limitação do modelo SA, era erro nosso mesmo. **Esse foi o fix de maior impacto** — sozinho já tirou 0° e 10° de erro de centenas de % pra <30%.

3. **`liftDir` hardcoded errado em `system/forces` (Incompressible e Compressible)** — o arquivo `core/Standard/{Incompressible,Compressible}/system/forces` é um template estático, copiado sem alteração pra cada simulação (`Run.py` nunca reescreve esse arquivo, só o `initialConditions`). Ele tinha `liftDir (-0.173648  $cos_alpha 0);` com o primeiro componente **fixo** em `-sin(10°)`, enquanto `dragDir ($cos_alpha $sen_alpha 0)` é corretamente parametrizado por ângulo. `liftDir` deveria ser `(-sin(α), cos(α), 0)` — perpendicular a `dragDir` — e só batia por coincidência em α=10°. Em qualquer outro ângulo, `liftDir` não é unitário nem ortogonal a `dragDir`, então o `forceCoeffs` vaza parte da força de sustentação (Cl, grande) pra dentro da projeção de arrasto (Cd, pequeno) — um vazamento pequeno de uma força grande já domina um valor pequeno. Isso bate exatamente com o padrão observado: erro de Cd baixo em 0° (quase não há sustentação pra vazar) e em 10° (liftDir acidentalmente exato), e erro de Cd absurdo (500%+) em 5°/15° (sustentação real vazando). **Corrigido**: `liftDir (-$sen_alpha  $cos_alpha 0);` nos dois arquivos `system/forces` (2026-09-18). Isso é uma correção de pós-processamento (projeção de força), **independente da malha em si** — pode explicar a maior parte do erro de Cd sem precisar mexer em topologia de malha. Ainda não validado com uma rodada completa (ver "Rodar uma validação completa" abaixo) — próximo passo é rodar os 4 ângulos de novo e ver quanto do erro de Cd em 5°/15° sobra depois desse fix.

Os três fixes estão no código, não commitados ainda (ver `git status`).

## O problema atual: 5° e 15° especificamente

Não é falta de convergência numérica — o histórico de Cd em 5° converge **suave e monotonicamente** pra um valor errado (não oscila). O padrão de Cd entre ângulos não é físico: 0,0094 → 0,053 → 0,0152 → -0,087 (deveria subir suave com o ângulo, não ter um pico em 5° e cair em 10°).

**Pista já levantada:** rodei `checkMesh` nas malhas de 5° e 15° isoladamente (sem resolver, só malha) e a não-ortogonalidade máxima está em **89-90°** (praticamente células degeneradas) contra 84° em 0°/10° que deram certo. Hipótese líder na época: a rotação do perfil em certos ângulos empurraria algum canto do multi-bloco pra quase-degenerado, e essa célula ruim bem na superfície corromperia a integração de força ali.

**Essa hipótese foi REFUTADA** por uma varredura de 147 malhas (2026-09-18) — ver [MESH_QUALITY_STUDY.md](MESH_QUALITY_STUDY.md) para os dados completos:

- **A malha não é rotacionada.** O `blockMeshDirect` não gira o perfil nem o domínio: o ângulo entra só na coordenada y dos vértices 8/10 (canto de saída), arredondada pra inteiro. Os `blockMeshDict` de 2° e 4° saem idênticos byte a byte, assim como 10° e 12°. A malha em volta do perfil é a mesma em todos os ângulos — então qualidade de malha não pode explicar erro que varia com o ângulo.
- **A não-ortogonalidade cresce monotonicamente com o ângulo** (84,5 em 0° → 89,6 em 10° → 89,8 em 20°), ou seja, 10° é tão "ruim" quanto 15°. A medição anterior de "84° em 0°/10°" não se reproduz.
- **As células ruins ficam a ~19 cordas a jusante**, agrupadas no canto de saída (centroide em x≈19,8, com o perfil em x∈[0,1] e a saída em x=21), medido com `checkMesh -writeSets obj`. Elas não tocam a superfície, logo não afetam a integração de forças.
- A causa é a razão de expansão `O18 ≈ 46.276` na aresta de saída dos blocos da esteira, que mantém altura de célula de camada limite a 20 cordas de distância.

Isso deixava o fix do `liftDir` (item 3 acima) como a explicação em aberto para o erro de Cd. **Confirmado**: rodei a validação completa depois do fix (ver tabela no topo) — os 4 ângulos foram de 500%+ de erro em Cd pra 18-47%. O `liftDir` era mesmo a causa dominante, não a malha.

## Como reproduzir rápido (sem gastar simulação completa)

`checkMesh` sozinho é rápido (segundos) e não precisa rodar o solver — use isso pra iterar antes de comprometer uma rodada completa (~30-40 min):

```bash
# gerar o blockMeshDict pro ângulo/condição desejada
py -3 -c "
import sys, os
sys.path.insert(0, r'CAMINHO\core')
os.chdir(r'CAMINHO')
import functions
fl = functions.first_layer_thickness_for_flow(60.0, 1e-5)
er = functions.expansion_ratio_for_flow(60.0, 1e-5)
functions.blockMeshDirect(5.0, first_layer_thickness=fl, expansion_ratio=er)
"

# copiar pro WSL, gerar e checar a malha
wsl -e bash -c "source /usr/lib/openfoam/openfoam2212/etc/bashrc 2>/dev/null; \
  rm -rf /tmp/cm_test; mkdir -p /tmp/cm_test; \
  cp -r 'CAMINHO/core/Standard/Incompressible/.' /tmp/cm_test/; \
  cp 'CAMINHO/mesh_standard' /tmp/cm_test/system/blockMeshDict; \
  cd /tmp/cm_test && cp -r 0.orig 0 && blockMesh > bm.log 2>&1 && checkMesh"
```

Troque `CAMINHO` pelo caminho do repo (tem espaço/acento no path real — sempre entre aspas).

## Regra importante deste projeto (lição já registrada)

Não confie no nome/posição de uma variável numa fórmula legada (essa malha é uma planilha Excel portada pra Python, cheia de variáveis tipo `H8`, `O13`, `N10`) sem rastrear pra onde ela realmente vai no arquivo gerado, e sem comparar contra medição real antes/depois. Foi assim que a primeira tentativa de corrigir o y+ (mexendo em `First_layer_thickness`) não teve efeito nenhum — só descobri rodando de verdade e comparando y+ medido. Registrado como zettel no segundo cérebro: "O nome do parâmetro não garante a causa".

## Rodar uma validação completa (quando fizer sentido gastar a simulação)

Script pronto em `C:\Users\thiag\AppData\Local\Temp\claude\...\scratchpad\run_validation.py` (caminho muda por sessão — se não existir mais, é fácil recriar: instancia `Run.App`, seta `naca_var="0012"`, `angle_var="0, 5, 10, 15"`, `parallel_var=True`, `flow_speed_var_I=60.0` — Re=6.000.000 com `nu=1e-5` — chama `Simulation_Incompressible()`). Timeout de segurança precisa ser generoso (90 min já usado) — rodadas passadas já bateram no timeout de 30 min e perderam o pós-processamento.

## Ver também
- [MESH_QUALITY_STUDY.md](MESH_QUALITY_STUDY.md) — varredura de qualidade de malha (perfil × ângulo), envelope do gerador e o harness em `tools/` que roda `blockMesh`+`checkMesh` em lote
- `core/functions.py` — `blockMeshDirect`, `expansion_ratio_for_flow`, `first_layer_thickness_for_flow`, `_boundary_layer_first_cell`, `_solve_expansion_ratio_for_first_cell`
- `core/reference_data/naca0012_ladson_re6e6.csv` — dataset de referência
- Segundo cérebro (Obsidian): `Sexta_Feira/TV/01-Projetos/Projeto - TCC Simulação Aerodinâmica.md` — acompanhamento do projeto como um todo, não só a malha
