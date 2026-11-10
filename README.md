# Data centers no Brasil: escala, maturidade e território

Programas e dados do exercício quantitativo (Capítulo 9) do Trabalho de Conclusão de Curso
**"Sustentabilidade e infraestruturas críticas de data centers no Brasil: energia, água,
telecomunicações e impactos territoriais no Nordeste e no Ceará"**, de Lucas Batista Dantas
(Engenharia Elétrica, FEEC/Unicamp, 2026), orientado pelo Prof. Dr. Luiz Carlos Pereira da Silva.

Vídeo de apresentação: https://youtu.be/1Yy8i5SzRIk

## O que o exercício faz

| Etapa | Pergunta | Dados |
|---|---|---|
| 1. Refrigeração | Como o clima do Pecém e de Campinas muda o PUE e a água de um *campus* de 100 MW de TI, com quatro tecnologias de refrigeração? | ERA5 horário, 2016–2025 (Open-Meteo) |
| 2. Correspondência horária | Quanto de um contrato eólico/solar com 100% de equivalência anual coincide, hora a hora, com o consumo? | Balanço de energia horário do subsistema Nordeste, ONS 2025 |
| 3. *Constrained-off* | Quanta geração eólica e solar deixou de ser realizada no Nordeste e quanto dela coincide com a carga do *campus*? | Restrição de operação semi-horária de usinas eólicas e fotovoltaicas, ONS 2025 |
| 4. Campinas/Pau D'Alho | Frequência do limiar de 29,4 °C e o *campus* na escala declarada (386 MW) | ERA5 de Campinas |

Nenhum número do capítulo é digitado à mão: o programa grava todos em `tabelas/numeros.tex`,
lido pelo LaTeX na compilação, e em `scripts/resultados.json`.

## Como reproduzir

```bash
pip install numpy pandas matplotlib
python scripts/baixar_dados.py          # opcional: os dados já estão em scripts/dados
python scripts/exercicio_quantitativo.py
```

Saídas: `figuras/grafico2..5-*.pdf`, `tabelas/*.tex` e `scripts/resultados.json`.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `scripts/baixar_dados.py` | Baixa o clima ERA5 (Pecém e Campinas) e os dados abertos do ONS; agrega a geração não realizada do Nordeste por hora e por motivo (ENE, REL, CNF). Horas sem restrição registrada correspondem a corte nulo. |
| `scripts/exercicio_quantitativo.py` | Modelo horário de refrigeração, sensibilidade, correspondência horária com baterias, *constrained-off* e aplicação a Campinas. |
| `scripts/gerar_figuras.py` | Estilo e paleta comuns das figuras. |
| `scripts/dados/` | Dados usados no trabalho, como baixados. |
| `tabelas/`, `figuras/` | Saídas incluídas no texto do TCC. |

## Fontes dos dados

- Hersbach, H. et al. (2020). The ERA5 global reanalysis. *Q. J. R. Meteorol. Soc.*, 146, 1999–2049, via Open-Meteo Historical Weather API.
- Operador Nacional do Sistema Elétrico (ONS). Portal de Dados Abertos: balanço de energia nos subsistemas (base horária, 2025) e restrição de operação por *constrained-off* de usinas eólicas e fotovoltaicas (base semi-horária, 2025).

Os dados pertencem às respectivas fontes e seguem os termos de uso delas. O código é distribuído sob a licença MIT.

## Limites

Modelo de refrigeração simplificado e calibrado por premissas típicas, não por medições; célula
de reanálise de ~30 km; um único ano de geração e perfil agregado do Nordeste; a análise de
*constrained-off* mede coincidência temporal (limite superior), não energia efetivamente
aproveitável, e não modela a rede de transmissão.
