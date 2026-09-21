# Estudo de qualidade de malha — varredura perfil × ângulo

Frente de trabalho da branch `mesh-quality-study`. Complementa o
[MESH_INVESTIGATION.md](MESH_INVESTIGATION.md): aquele documento persegue o erro
de Cl/Cd contra dados experimentais; este mede a **malha isoladamente**, sem
resolver escoamento nenhum, para decidir se o gerador atual limita o escopo do
app ou se dá para ampliá-lo.

## Método

147 malhas geradas e avaliadas com `blockMesh` + `checkMesh`, sem solver
(~9 s por malha, contra ~30-40 min de uma simulação completa):

| Varredura | Casos | O que varia |
|---|---|---|
| `studies/mesh_quality/factorial` | 120 | 12 perfis × 10 ângulos (0° a 20°) |
| `studies/mesh_quality/envelope_profiles` | 18 | perfis extremos (0003 a 0040, curvatura até 8%) |
| `studies/mesh_quality/envelope_angles` | 9 | ângulos de 25° a 80° |

Condição de escoamento fixa em todas: U=60 m/s, ν=1e-5 (Re=6·10⁶), para isolar
o efeito de geometria. Ferramentas em `tools/` (ver "Como reproduzir").

Limiares de referência: não-ortogonalidade < 70° é confortável, 70-85° exige
`nNonOrthogonalCorrectors`, acima de 85° a recomendação usual é refazer a malha;
assimetria (skewness) < 4.

## Resultado 1 — o perfil aerodinâmico quase não afeta a qualidade

Não-ortogonalidade máxima e razão de aspecto máxima deram **valores idênticos
nos 12 perfis**, para cada ângulo — e seguem idênticos nos perfis extremos
(0003, 0030, 0040, 6406, 6409, 8412):

| Ângulo | 0° | 2° | 6° | 10° | 15° | 20° |
|---|---|---|---|---|---|---|
| Não-ortogonalidade máx. | 84,48 | 88,16 | 89,09 | 89,57 | 89,67 | 89,79 |
| Razão de aspecto máx. | 17258 | 661 | 661 | 661 | 661 | 661 |
| Reprovações no checkMesh | 1 | 0 | 0 | 0 | 0 | 0 |

A única métrica sensível ao perfil é a assimetria, e ela tem mínimo em torno de
6-9% de espessura, piorando nas duas direções:

| Perfil | 0003 | 0006 | 0012 | 0018 | 0024 | 0030 | 0040 |
|---|---|---|---|---|---|---|---|
| Assimetria máx. | 1,96 | 0,98 | 1,11 | 1,58 | 2,12 | 2,77 | 3,99 |

Curvatura tem efeito menor (a 12% de espessura: 0012 → 1,11; 4412 → 1,31).
Nenhum perfil testado causou falha topológica: a topologia foi calibrada para
~12% de espessura, mas cobre de 3% a 40% sem quebrar. **O perfil não é o que
limita o escopo.**

## Resultado 2 — o ângulo entra na malha por um único inteiro

O `blockMeshDirect` **não rotaciona o perfil nem a malha**. A única dependência
com o ângulo é a coordenada y dos vértices 8 e 10 (o canto de saída do domínio):

```python
round(np.sin(np.radians(C2)) * (B2 + 1))    # B2 = 20 cordas
```

Consequências, todas verificadas nos 120 casos:

- Os `blockMeshDict` de 2° e 4° são **idênticos byte a byte** (só muda o
  comentário do cabeçalho), assim como 10° e 12° — ambos os pares caem no mesmo
  `k` arredondado. A malha é constante por faixas de ângulo.
- A malha em volta do perfil é a mesma em todos os ângulos. Logo, **qualidade de
  malha não pode explicar erro que varia com o ângulo**.
- O deslocamento desse canto é o que degrada a não-ortogonalidade de 84,48 para
  89,79 — sem nenhum ganho físico em troca, já que o ângulo de ataque real entra
  por `U_x`/`U_y` (em `0/initialConditions`) e pela projeção `liftDir`/`dragDir`
  (em `system/forces`).

As condições de contorno já suportam malha fixa com escoamento rotacionado:
`0.orig/U` usa `freestreamVelocity` no inlet **e** no outlet, que alterna entre
entrada e saída conforme o fluxo local.

## Resultado 3 — as células ruins estão na saída, não no perfil

Com `checkMesh -writeSets obj` e o centroide dos conjuntos marcados
(`tools/mesh_quality_sweep.py --write-sets`), para NACA 0012:

| Conjunto | Ângulo | Onde está | Perto do perfil? |
|---|---|---|---|
| `nonOrthoFaces` (62 faces) | 0° | centroide x ≈ 19,8 | não |
| `nonOrthoFaces` (86 faces) | 15° | centroide x ≈ 19,7 · y ≈ 4,68 | não |
| `highAspectRatioCells` (1170) | 0° | x ∈ [8,6; 21] · y ∈ [-0,0034; 0,0034] | não |

O perfil ocupa x ∈ [0, 1]; a saída fica em x = 21. **As piores células estão a
~19 cordas a jusante**, agrupadas no canto de saída (vértice 8). Elas não tocam
a superfície do perfil, então não têm como corromper a integração de forças —
o que descarta a hipótese registrada no MESH_INVESTIGATION.md de que a
não-ortogonalidade de 89-90° explicaria o erro de Cd.

### Mecanismo

A aresta de saída dos blocos da esteira usa razão de expansão

```
O18 = F11 * O13 / E11 * (N13 + N10) / N13 ≈ 46.276
```

Isso deixa a primeira célula da saída com 2,27·10⁻⁵ de altura e ~0,5 de
comprimento em x — razão de aspecto ~28.000, exatamente onde as faces ruins
aparecem. O crescimento célula a célula é suave (1,055); o problema é a malha
manter altura de camada limite a 20 cordas de distância, onde não serve para nada.

Em 0° essas células ficam alinhadas e a reprovação aparece como razão de aspecto
(17258); com ângulo, o canto cisalhado as engorda (AR cai para 661) e o defeito
reaparece como não-ortogonalidade. São dois sintomas do mesmo parâmetro.

## Envelope atual do gerador

| Eixo | Limite medido | Observação |
|---|---|---|
| Espessura | 3% a 40% sem falha | assimetria chega a 3,99 (limite 4) em 0040 a 20° |
| Curvatura | até 8% sem falha | efeito pequeno na qualidade |
| Ângulo | quebra em 70° | `k` atinge 20 e o vértice 8 colide com o 9: assimetria 5·10¹⁴⁹, 2 reprovações. Em 80° o `blockMesh` nem roda (bloco invertido) |
| Reynolds | trava abaixo de ~9·10⁵ | a busca binária de `expansion_ratio_for_flow` satura em 1,00001 e o controle de y+ para de funcionar, em silêncio |

Nota sobre a camada limite: o bloco de camada limite usa `D8 = 0,2` corda,
enquanto a camada limite turbulenta real no bordo de fuga é ~0,016 corda em
Re=6·10⁶ — o bloco é 12× mais espesso que o fenômeno que deveria resolver, então
boa parte das 100 células "de camada limite" cai fora dela.

## Conclusão: melhorar, não limitar o escopo

O teto de qualidade **não vem do perfil nem do ângulo de ataque** — vem de dois
parâmetros fixos da topologia do domínio, e os dois são independentes do caso:

1. **`O18 ≈ 46.276` na aresta de saída.** Desacoplar o refino da esteira distante
   do refino da camada limite resolve tanto a razão de aspecto de 17258 quanto a
   não-ortogonalidade no canto (medido abaixo). É a correção essencial.
2. **O arredondamento do vértice 8/10**, e não o deslocamento em si — ver a
   ressalva a seguir.

### Ressalva: o deslocamento do vértice 8/10 é alinhamento de esteira, não lixo

Uma leitura inicial deste estudo concluiu que mover o vértice 8/10 com o ângulo
"não comprava nada". **Isso estava errado.** A linha de interface entre os blocos
da esteira vai do bordo de fuga (1, 0) até o vértice 8 (21, k) — e é exatamente
onde fica a banda de células refinadas da esteira. Mover o vértice inclina essa
banda para acompanhar o escoamento:

| Ângulo | 2° | 5° | 10° | 15° | 20° |
|---|---|---|---|---|---|
| Inclinação da banda | 2,86° | 5,71° | 11,31° | 14,04° | 19,29° |
| Erro vs. escoamento | +0,86 | +0,71 | +1,31 | -0,96 | -0,71 |

Ou seja, é um mecanismo (grosseiro) de alinhamento de esteira, e removê-lo jogaria
a esteira em células muito mais grossas: sobre a banda as células têm 3,2·10⁻⁴ de
altura; em y=1 (onde a esteira passa a ~4 cordas do bordo de fuga, a 15°) elas já
têm 0,083 — **260× mais grossas**.

O que o experimento mostra é que, **depois** de corrigir o O18, manter a inclinação
custa praticamente nada: 77,1211 contra 77,1178 de não-ortogonalidade (diferença de
0,003°) e assimetria 1,385 contra 1,142 — ambas muito abaixo do limite de 4.

Então a correção 2 não é remover a inclinação, é **tirar o arredondamento**: hoje
`round(sin α · 21)` erra o alinhamento em até 1,3° e faz 10° e 12° caírem na mesma
malha. Escrever a coordenada como float resolve, e o limite duro de 70° passa a
precisar só de um limitador.

### Achado lateral: salto de 33× na emenda da graduação em y

A graduação em y é dividida em duas seções (`multiGrading`): y ∈ [0; 0,2] com 100
células e razão 19,3, e y ∈ [0,2; 20] com 100 células e razão 9255. Na emenda, a
altura da célula cai de 6,2·10⁻³ para 1,9·10⁻⁴ — uma **contração abrupta de 33×**
no meio do domínio. O `checkMesh` não reclama (não é não-ortogonalidade, assimetria
nem razão de aspecto), mas descontinuidade de tamanho de célula degrada a
interpolação. Vale investigar separadamente.

### Experimento controlado (executado)

`tools/mesh_variant_experiment.py` aplica cada mudança isoladamente sobre o dict
gerado, sem tocar no `core/functions.py`, e mede. NACA 0012:

| Variante | Ângulo | Não-ortog. | Razão asp. | Reprovações | Faces ruins perto do perfil |
|---|---|---|---|---|---|
| base | 0° | 84,48 | 17258 | 1 | 0% |
| base | 15° | 89,67 | 661 | 0 | 0% |
| `corner0` (vértice 8/10 fixo) | 15° | 84,48 | 17258 | 1 | 0% |
| `wake50` (O18 = 50) | 0° | **77,12** | **661** | **0** | 0% |
| `wake50` | 15° | **77,12** | **661** | **0** | 0% |
| `wake50` + `corner0` | 0° e 15° | **77,12** | **661** | **0** | 0% |

Leitura:

- **`corner0` sozinho** faz a malha de 15° virar exatamente a de 0° (mesmos
  84,48 / 17258 / 1 reprovação), confirmando que o canto é a única dependência
  com o ângulo. Sozinho, ele só troca não-ortogonalidade por razão de aspecto.
- **`wake50` sozinho já resolve os dois defeitos**: elimina a reprovação de
  razão de aspecto em 0° e derruba a não-ortogonalidade de 89,67 para 77,12,
  ficando praticamente igual em 0° e 15°.
- **As duas juntas** dão o melhor resultado e tornam a malha rigorosamente
  independente do ângulo — mesma malha, mesmas métricas, em qualquer ângulo.
- Depois do `wake50`, as piores faces migram para as fronteiras do domínio
  (entrada e saída); nenhuma fica perto do perfil em nenhuma variante.

O valor 50 foi escolhido como ordem de grandeza razoável, não otimizado — vale
varrer esse parâmetro antes de fixá-lo no gerador.

### Ajuste correlato no solver

`system/fvSolution` usa `nNonOrthogonalCorrectors 0` com a malha atual chegando a
89,7° de não-ortogonalidade. Os esquemas já são `corrected` (`Gauss linear
corrected` / `snGrad corrected`), mas a prática usual acima de 70° é usar 1-2
correctores. Isso é candidato a explicar o `Converged=0` em 15° registrado no
MESH_INVESTIGATION.md, e continua valendo mesmo depois do `wake50` (77 > 70).

## Correções aplicadas e o teste de validação (resultado negativo)

As duas correções foram aplicadas no `core/functions.py` (nas duas cópias) em
2026-09-18:

- `O18 = wake_outlet_expansion_ratio(A2, N10 + N13)` — resolve a razão a partir de
  uma altura-alvo de primeira célula na saída (0,008 corda) com a busca binária
  `_solve_expansion_ratio_for_first_cell` que já existia, em vez de derivá-la da
  altura da célula de parede.
- `_wake_corner_offset(C2, A2, B2)` com formatação `%0.6f` — mantém a inclinação da
  banda de esteira, remove o arredondamento para inteiro, e limita o deslocamento
  em 0,9·A2 para o vértice 8 nunca alcançar o 9.

Qualidade de malha, NACA 0012 (verificada com `checkMesh`):

| Ângulo | Não-ortog. antes → depois | AR antes → depois | Reprovações |
|---|---|---|---|
| 0° | 84,48 → **77,12** | 17258 → **661** | 1 → **0** |
| 5° | 89,09 → **77,12** | 661 → 661 | 0 → 0 |
| 10° | 89,57 → **77,12** | 661 → 661 | 0 → 0 |
| 15° | 89,67 → **77,12** | 661 → 661 | 0 → 0 |

**E o efeito nos coeficientes aerodinâmicos foi nulo.** Rodando a mesma validação
(NACA 0012, 0/5/10/15°, U=60, Re=6·10⁶, mesmo driver):

| Ângulo | Cl erro antes → depois | Cd erro antes → depois |
|---|---|---|
| 0° | 101,6% → 103,6% | 18,15% → 18,17% |
| 5° | 7,53% → 7,70% | 27,03% → 27,00% |
| 10° | 7,46% → 7,61% | 27,69% → 27,84% |
| 15° | 8,96% → 8,97% | 46,98% → 48,87% |

Erro médio: Cd 30,0% → 30,5%; Cl 31,4% → 32,0%. y+ praticamente idêntico, e 15°
continua com `Converged=0`.

**Isso confirma a previsão do estudo em vez de contrariá-la.** A localização das
células ruins já mostrava que elas ficavam a ~19 cordas a jusante, sem tocar a
superfície — então não havia por onde afetarem a integração de forças. A variação
observada (≤2 pontos percentuais, a maior delas em 15°, que é justamente o caso
não convergido com 9,7% de variação na janela de média) está dentro do ruído.

Que a malha de fato mudou está registrado nas diferenças pequenas mas não nulas de
y+ máximo (148,10 → 147,89 em 15°; 112,84 → 112,79 em 10°).

O que as correções compram, então, não é exatidão:

- `checkMesh` passa limpo (0 reprovações) — defensável numa banca e utilizável como
  portão de qualidade automático antes de gastar uma simulação.
- A malha deixa de depender do Reynolds na esteira distante sem motivo físico.
- A banda refinada passa a seguir o ângulo de verdade (erro de alinhamento de até
  1,3° foi a zero; 10° e 12° deixam de compartilhar a mesma malha).
- Some a falha dura em 70°.

### Onde o erro restante provavelmente está

O padrão é sistemático e não veio das células ruins: **Cl baixo em 7-9% e Cd alto
em 18-49%, em todos os ângulos**. Candidatos, em ordem de suspeita:

1. **Domínio de 20 cordas.** Para validação de perfil a prática é 50-100 cordas;
   20 cordas subestima sustentação. É a hipótese mais alinhada com um déficit de
   Cl sistemático. Testável: `blockMeshDirect_Custom` já aceita
   `distance_to_inlet`/`distance_to_outlet` como parâmetros.
2. **y+ mal distribuído.** Média 34 mas máximo 148 a 15° — a primeira célula é
   grossa demais perto do bordo de ataque, onde o cisalhamento é maior.
3. **O bloco de camada limite com 0,2 corda** contra ~0,016 corda de camada limite
   real: a resolução está no lugar errado.
4. **O salto de 33×** na emenda da graduação em y.

## Domínio maior, salto de graduação e y+ (medições de 2026-09-19)

### Custo de aumentar o domínio

Medido com `blockMeshDirect_Custom` (que já aceita `distance_to_inlet`/`outlet`),
NACA 0012 a 10°. O solver roda 2000 iterações fixas (`endTime 2`, `deltaT 0.001`),
então o custo por rodada é proporcional ao número de células:

| Opção | Células | Custo | Não-ortog. | Salto em y | Célula da esteira no bordo de fuga |
|---|---|---|---|---|---|
| 20 cordas (hoje) | 200.000 | 1,00× | 77,1 | 33× | 0,0026 |
| 50 cordas, esticando | 200.000 | 1,00× | 76,6 | 13× | 0,0066 (2,5× mais grossa) |
| 100 cordas, esticando | 200.000 | 1,00× | 76,4 | 6,5× | 0,0132 (5× mais grossa) |
| 50 cordas + células | 224.700 | 1,12× | 74,9 | 14× | 0,0056 |
| 100 cordas + células | 244.160 | 1,22× | 73,2 | 7,6× | 0,0102 |

Como a graduação é geométrica, distância extra sai barata: esticar não custa nada
e não piora nenhuma métrica do `checkMesh`, mas engrossa a esteira logo atrás do
bordo de fuga, porque a razão total `O16 = 200` da esteira é fixa. Ressalva: com
iterações fixas, um domínio maior pode convergir menos no mesmo número de passos.

### O salto de 33×

A graduação em y tem duas seções independentes. A seção 1 (parede até 0,2 corda)
termina com células de 6,15·10⁻³; a seção 2 começa com 1,89·10⁻⁴, um tamanho que
ninguém escolheu (sai de `O13 = D11/H8`). A malha precisa de **38 células** (19% das
200 na direção normal) só para voltar ao tamanho de antes do salto, numa faixa de
0,2 a 0,263 corda **ao redor do perfil inteiro** (blocos 1 e 3) e ao longo da
esteira. É o único defeito medido que fica perto do perfil.

Começando a seção 2 onde a 1 termina (crescimento de 1,1), a resolução a partir de
~0,4 corda fica praticamente igual (0,076 vs 0,081 em y=1; 0,174 vs 0,173 em y=2),
com **160 células em vez de 200** — e só 177 para um domínio de 100 cordas. Ou seja,
corrigir o salto paga o domínio maior.

### y+

SA com `nutUSpaldingWallFunction` (válida para qualquer y+). Medido: média 31-34,
mas máximo 41 (0°) → 148 (15°): a primeira célula tem a mesma altura ao longo de
toda a corda, e o cisalhamento se concentra no bordo de ataque conforme o ângulo
sobe. A referência NASA TMR para este caso usa y+ < 1 e obtém Cd ≈ 0,0081 — o
experimento de Ladson —, o que torna a estratégia de parede o suspeito principal
do Cd alto.

## Versão de release (2026-09-21): salto corrigido + y+ como parâmetro

Portado para o projeto original: `_outer_ratio_continuous` (salto de 32,6× → 0,91×)
e `first_cell_height_for_yplus` com `DEFAULT_TARGET_YPLUS = 33.41`, que reproduz a
malha validada com diferença ≤ 7,5·10⁻⁷ entre 10 e 340 m/s. Exposto na UI como
"Wall y+ target". Não portados: domínio de 100 cordas (piorou Cl) e graduação da
esteira por alvo (neutra em 20 cordas).

`checkMesh` (NACA 0012, 0-15°, 200 mil células): não-ortogonalidade 77,1 → 57,4;
razão de aspecto 661 → 370; assimetria máx. 1,40 → 1,08; 0 reprovações.

Validação, mesmo driver e solver da v1 (iterações 1777/2000/2000/2000, iguais à v1):

| Ângulo | Cl erro v1 → release | Cd erro v1 → release |
|---|---|---|
| 0° | 103,6 → 103,7 | 18,17 → 18,13 |
| 5° | 7,70 → 7,69 | 27,00 → 26,82 |
| 10° | 7,61 → 7,61 | 27,84 → 27,26 |
| 15° (não convergido) | 8,97 → 9,24 | 48,87 → 50,66 |

Sem regressão: 0/5/10° iguais ou levemente melhores; a variação em 15° está dentro
da deriva desse caso (−6% no último quarto). Malha mais limpa, resultado preservado.

## Melhorias estruturais no gerador (não são de qualidade de malha, mas travam a evolução)

- `blockMeshDirect` e `blockMeshDirect_Custom` têm 309 linhas de corpo cada, das
  quais **301 são idênticas**. Toda correção precisa ser feita duas vezes.
- As coordenadas do perfil viram variáveis globais do módulo (`A9`..`A212`, via
  `globals()[f"A{n+9}"]`) e são lidas de volta por nome — impede gerar duas
  malhas simultaneamente, que é o que um sistema de lote precisa fazer.
- Caminhos relativos fixos (`'coordenadas.dat'`, `'mesh_standard'`) dependem do
  diretório corrente; já causaram um bug (commit `14c4de7`).
- Parâmetros expostos na tela "Custom" não são grandezas físicas
  (`Cell_size_at_leading_edge = 1e-8`): só as razões entre eles importam.
- Nenhuma validação: uma razão de expansão de 46.276 passa sem aviso, e a
  saturação da busca binária em Re baixo também.
- Sem testes. Um golden-file (gerar o dict de um caso conhecido e comparar com
  referência) pegaria regressões em segundos.

## Como reproduzir

```bash
# varredura perfil x angulo (cada malha ~9 s)
py -3 tools/mesh_quality_sweep.py --profiles 0012,0018 --angles 0:20:5 --outdir studies/mesh_quality/nova

# com localizacao das celulas ruins
py -3 tools/mesh_quality_sweep.py --profiles 0012 --angles 0,15 --write-sets --tag loc --outdir studies/mesh_quality/loc

# tabelas e graficos a partir do CSV
py -3 tools/mesh_quality_report.py studies/mesh_quality/nova/mesh_quality.csv

# experimento controlado de variantes do dict
py -3 tools/mesh_variant_experiment.py --profile 0012 --angles 0,15 --wake-ratio 50
```

Use `--tag` distinto para rodar varreduras simultâneas (cada uma usa seu próprio
diretório de trabalho no WSL).

## Ver também

- `tools/mesh_quality_sweep.py` — geração + `checkMesh` + parsing das métricas
- `tools/mesh_quality_report.py` — tabelas e gráficos a partir do CSV
- `tools/mesh_variant_experiment.py` — variantes controladas do dict gerado
- `studies/mesh_quality/*/report.txt` e `mesh_quality.csv` — dados brutos
