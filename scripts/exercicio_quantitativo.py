"""Exercício quantitativo do TCC (Capítulo 9).

Etapa 1 - modelo horário de clima e refrigeração para um campus hipotético
          de 100 MW de TI no Pecém e em Campinas (ERA5, 2016-2025).
Etapa 2 - correspondência horária entre a carga do campus e contratos eólicos
          e solares com o perfil verificado do Nordeste (ONS, 2025).
Etapa 3 - energia eólica e solar não realizada por constrained-off no
          Nordeste (ONS, 2025) e quanto dela o campus poderia absorver.

Saídas:
  ../figuras/grafico2..5-*.pdf   gráficos
  ../tabelas/*.tex               tabelas e macros com os números citados
  resultados.json                todos os resultados, para conferência

Uso:  python baixar_dados.py   (uma vez)
      python exercicio_quantitativo.py
"""
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from gerar_figuras import (AZUL, AZUL_MEDIO, AZUL_CLARO, CINZA, CINZA_CLARO,  # noqa: E402
                           LARGURA, SAIDA as FIGURAS)

DADOS = AQUI / "dados"
TABELAS = AQUI.parent / "tabelas"
TABELAS.mkdir(exist_ok=True)

LARANJA = "#C55A11"
CORES = {"A": AZUL, "B": AZUL_MEDIO, "C": LARANJA, "D": "#7F7F7F"}
NOMES = {
    "A": "A -- \\textit{chiller} e torre evaporativa",
    "B": "B -- \\textit{chiller} a ar com pré-resfriamento adiabático",
    "C": "C -- \\textit{chiller} a ar (seco)",
    "D": "D -- líquido no chip (W32) e \\textit{dry cooler}",
}
NOMES_CURTOS = {"A": "A: evaporativo", "B": "B: adiabático", "C": "C: seco",
                "D": "D: líquido W32"}
LOCAIS = {"pecem": "Pecém", "campinas": "Campinas"}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
H_FG = 2430.0  # calor latente de vaporização da água a ~30 °C, kJ/kg


# ---------------------------------------------------------------------------
# Premissas
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Premissas:
    p_nominal: float = 100.0   # MW de TI nominais
    utilizacao: float = 0.80   # carga média de TI / nominal
    f_elet: float = 0.07       # perdas de UPS, transformação e distribuição (fração da TI)
    f_aux: float = 0.01        # iluminação, segurança e automação (fração da TI)
    f_ar: float = 0.04         # ventiladores do ar interno (fração do calor no ar)
    t_agua_gelada: float = 18.0  # °C, água gelada de alimentação
    dt_evap: float = 4.0       # K, água gelada -> temperatura de evaporação
    eta_carnot: float = 0.55   # fração do COP de Carnot atingida pelo chiller
    cop_max: float = 12.0
    ap_torre: float = 4.0      # K, aproximação da torre ao bulbo úmido
    faixa_cond: float = 5.0    # K, elevação da água de condensação
    ap_cond: float = 2.0       # K, condensador -> temperatura de condensação
    itd_ar: float = 15.0       # K, ar externo -> condensação em chiller a ar
    ap_troca: float = 2.0      # K, trocador do resfriamento gratuito
    ap_dry: float = 5.0        # K, aproximação do dry cooler ao bulbo seco
    f_torre: float = 0.02      # ventiladores da torre e bombas de condensação (fração do calor rejeitado)
    f_bomba: float = 0.015     # bombas de água gelada (fração do calor no ar)
    f_dry: float = 0.03        # ventiladores de condensadores a ar / dry coolers
    f_latente: float = 0.85    # parcela do calor da torre rejeitada por evaporação
    ciclos: float = 4.0        # ciclos de concentração da torre
    eps_adiab: float = 0.70    # efetividade do pré-resfriamento adiabático
    t_liga_adiab: float = 24.0  # °C, acionamento do pré-resfriamento
    dt_ar_cond: float = 10.0   # K, aquecimento do ar no condensador
    perda_adiab: float = 1.2   # água pulverizada / água evaporada útil
    frac_liquido: float = 0.75  # parcela da TI removida pelo circuito líquido
    t_classe_w: float = 32.0   # °C, classe ASHRAE do circuito líquido
    f_cdu: float = 0.015       # bombas das CDUs (fração do calor no líquido)
    fator_emissao: float = 0.0385  # tCO2/MWh, fator médio do SIN em 2023 (MCTI)


BASE = Premissas()


# ---------------------------------------------------------------------------
# Clima e psicrometria
# ---------------------------------------------------------------------------
def p_sat(t):
    """Pressão de saturação do vapor, kPa (equação de Buck)."""
    return 0.61121 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def bulbo_umido(t, td, p):
    """Temperatura de bulbo úmido (°C) por bisseção da equação psicrométrica
    (ASHRAE Fundamentals). t, td em °C; p em kPa."""
    w = 0.622 * p_sat(td) / (p - p_sat(td))
    lo, hi = td.copy(), t.copy()
    for _ in range(40):
        m = (lo + hi) / 2
        ws = 0.622 * p_sat(m) / (p - p_sat(m))
        wm = ((2501 - 2.326 * m) * ws - 1.006 * (t - m)) / (2501 + 1.86 * t - 4.186 * m)
        lo = np.where(wm < w, m, lo)
        hi = np.where(wm < w, hi, m)
    return (lo + hi) / 2


def carregar_clima(local):
    h = json.load(open(DADOS / f"era5_{local}.json"))["hourly"]
    d = pd.DataFrame({"tbs": h["temperature_2m"], "td": h["dew_point_2m"],
                      "p": np.array(h["surface_pressure"]) / 10},
                     index=pd.to_datetime(h["time"]))
    d["tbu"] = bulbo_umido(d.tbs.values, d.td.values, d.p.values)
    return d


# ---------------------------------------------------------------------------
# Etapa 1 - modelo horário
# ---------------------------------------------------------------------------
def cop(pr, t_evap, t_cond):
    lift = np.maximum(t_cond - t_evap, 5.0)
    return np.minimum(pr.cop_max, pr.eta_carnot * (t_evap + 273.15) / lift)


def simular(clima, cenario, pr=BASE):
    """Potências horárias (MW) e água (L/h) de um cenário de refrigeração."""
    tbs, tbu = clima.tbs.values, clima.tbu.values
    n = len(tbs)
    p_ti = np.full(n, pr.p_nominal * pr.utilizacao)
    q_int = p_ti * (1 + pr.f_elet + pr.f_aux)          # todo o consumo interno vira calor
    t_evap = pr.t_agua_gelada - pr.dt_evap
    agua = np.zeros(n)

    if cenario == "D":
        q_liq = pr.frac_liquido * p_ti
        q_ar = q_int - q_liq
    else:
        q_liq = np.zeros(n)
        q_ar = q_int
    p_vent = pr.f_ar * q_ar
    q_mec = q_ar + p_vent                               # calor no circuito de água gelada

    if cenario == "A":
        t_torre = tbu + pr.ap_torre
        livre = t_torre + pr.ap_troca <= pr.t_agua_gelada
        t_cond = t_torre + pr.faixa_cond + pr.ap_cond
        p_ch = np.where(livre, 0.0, q_mec / cop(pr, t_evap, t_cond))
        q_rej = q_mec + p_ch
        p_rej = pr.f_torre * q_rej
        evap = pr.f_latente * q_rej * 1000 * 3600 / H_FG          # kg/h = L/h
        agua = evap * pr.ciclos / (pr.ciclos - 1)                  # evaporação + purga
    else:
        if cenario == "B":
            ativo = tbs > pr.t_liga_adiab
            t_ar = np.where(ativo, tbs - pr.eps_adiab * (tbs - tbu), tbs)
        else:
            ativo = np.zeros(n, bool)
            t_ar = tbs
        livre = t_ar + pr.ap_dry + pr.ap_troca <= pr.t_agua_gelada
        t_cond = t_ar + pr.itd_ar
        p_ch = np.where(livre, 0.0, q_mec / cop(pr, t_evap, t_cond))
        q_rej = q_mec + p_ch
        p_rej = pr.f_dry * q_rej
        if cenario == "B":
            agua = np.where(ativo, q_rej * 1000 * 3600 / H_FG
                            * (tbs - t_ar) / pr.dt_ar_cond * pr.perda_adiab, 0.0)
    p_bomba = pr.f_bomba * q_mec

    p_liq = np.zeros(n)
    livre_liq = np.zeros(n, bool)
    if cenario == "D":
        livre_liq = tbs + pr.ap_dry <= pr.t_classe_w
        t_evap_l = pr.t_classe_w - pr.dt_evap
        p_ch_l = np.where(livre_liq, 0.0, q_liq / cop(pr, t_evap_l, tbs + pr.itd_ar))
        p_liq = p_ch_l + pr.f_dry * (q_liq + p_ch_l) + pr.f_cdu * q_liq

    p_total = q_int + p_vent + p_ch + p_rej + p_bomba + p_liq
    return pd.DataFrame({"p_ti": p_ti, "p_total": p_total, "agua": agua,
                         "livre": livre, "livre_liq": livre_liq}, index=clima.index)


def indicadores(s, pr=BASE):
    e_ti = s.p_ti.sum()                                 # MWh
    e_tot = s.p_total.sum()
    horas = len(s)
    return {
        "pue": e_tot / e_ti,
        "pue_max": (s.p_total / s.p_ti).max(),
        "p_max": s.p_total.max(),
        "mw_medios": e_tot / horas,
        "fc": s.p_total.mean() / s.p_total.max(),
        "e_total_gwh": e_tot / 1e3 * 8760 / horas,
        "wue": s.agua.sum() / (e_ti * 1000),
        "agua_m3_ano": s.agua.sum() / 1000 * 8760 / horas,
        "agua_ls": s.agua.mean() / 3600,
        "agua_max_mes_m3_dia": s.agua.resample("MS").mean().max() * 24 / 1000,
        "horas_livres": float(s.livre.mean()),
        "horas_livres_liq": float(s.livre_liq.mean()),
        "co2_t_ano": e_tot * 8760 / horas * pr.fator_emissao,
    }


def etapa1(climas):
    res, mensal = {}, {}
    for local, clima in climas.items():
        for c in "ABCD":
            s = simular(clima, c)
            anos = [indicadores(g) for _, g in s.groupby(s.index.year)]
            media = {k: float(np.mean([a[k] for a in anos])) for k in anos[0]}
            media["pue_min_ano"] = min(a["pue"] for a in anos)
            media["pue_max_ano"] = max(a["pue"] for a in anos)
            media["wue_min_ano"] = min(a["wue"] for a in anos)
            media["wue_max_ano"] = max(a["wue"] for a in anos)
            res[(local, c)] = media
            m = s.groupby(s.index.month)
            mensal[(local, c)] = pd.DataFrame({
                "pue": m.p_total.sum() / m.p_ti.sum(),
                "agua_m3_dia": m.agua.mean() * 24 / 1000})
        # variante W40 do cenário D, citada no texto
        s40 = simular(clima, "D", replace(BASE, t_classe_w=40.0))
        res[(local, "D40")] = indicadores(s40)
    return res, mensal


def sensibilidade(clima):
    """Variação de PUE (cenário C) e WUE (cenário A) no Pecém."""
    faixas = [
        ("eta_carnot", "Eficiência do \\textit{chiller} (fração de Carnot)", 0.45, 0.65),
        ("t_agua_gelada", "Temperatura da água gelada (°C)", 14.0, 22.0),
        ("f_elet", "Perdas elétricas (UPS e distribuição)", 0.04, 0.10),
        ("itd_ar", "Diferença ar–condensação, \\textit{chiller} a ar (K)", 12.0, 18.0),
        ("ap_torre", "Aproximação da torre (K)", 3.0, 6.0),
        ("f_latente", "Parcela latente na torre", 0.75, 1.0),
        ("ciclos", "Ciclos de concentração", 3.0, 6.0),
        ("f_ar", "Ventilação interna", 0.02, 0.06),
    ]
    base_pue = indicadores(simular(clima, "C"))["pue"]
    base_wue = indicadores(simular(clima, "A"))["wue"]
    linhas = []
    for campo, rotulo, lo, hi in faixas:
        r = {"campo": campo, "rotulo": rotulo, "lo": lo, "hi": hi}
        for nome, valor in (("baixo", lo), ("alto", hi)):
            pr = replace(BASE, **{campo: valor})
            r[f"pue_{nome}"] = indicadores(simular(clima, "C", pr), pr)["pue"]
            r[f"wue_{nome}"] = indicadores(simular(clima, "A", pr), pr)["wue"]
        linhas.append(r)
    return base_pue, base_wue, linhas


# ---------------------------------------------------------------------------
# Etapa 2 - correspondência horária
# ---------------------------------------------------------------------------
def perfis_ne():
    b = pd.read_csv(DADOS / "ons_balanco_2025.csv", sep=";")
    b = b[b.id_subsistema == "NE"].copy()
    b.index = pd.to_datetime(b.din_instante)
    return b[["val_gereolica", "val_gersolar", "val_carga"]].astype(float)


def bateria(carga, geracao, energia, potencia, rend=0.88):
    """Despacho simples: carrega com excedente, descarrega no déficit.
    Retorna a energia atendida (MWh) por geração direta + bateria."""
    ec = ed = np.sqrt(rend)
    soc = 0.0
    atendida = 0.0
    for l, g in zip(carga, geracao):
        if g >= l:
            atendida += l
            soc = min(energia, soc + min(g - l, potencia) * ec)
        else:
            atendida += g
            d = min(l - g, potencia, soc * ed)
            atendida += d
            soc -= d / ed
    return atendida


def etapa2(carga):
    ne = perfis_ne().reindex(carga.index).interpolate()
    l = carga.values
    e_l = l.sum()
    eol = ne.val_gereolica.values / ne.val_gereolica.sum() * e_l
    sol = ne.val_gersolar.values / ne.val_gersolar.sum() * e_l

    def metricas(g):
        return {"cfe": np.minimum(l, g).sum() / e_l,
                "horas_plenas": float(np.mean(g >= l)),
                "deficit_max": float(np.max(l - g)),
                "excedente": float(np.maximum(g - l, 0).sum() / e_l)}

    mixes = np.round(np.arange(0, 1.0001, 0.01), 2)
    curva = [{"eolica": s, **metricas(s * eol + (1 - s) * sol)} for s in mixes]
    otimo = max(curva, key=lambda r: r["cfe"])
    g_ot = otimo["eolica"] * eol + (1 - otimo["eolica"]) * sol

    p_bat = float(l.max())
    energias = np.arange(0, 6001, 100.0)
    cfe_bat = [bateria(l, g_ot, e, p_bat) / e_l for e in energias]
    fatores = np.round(np.arange(1.0, 3.01, 0.05), 2)
    cfe_sobre = [np.minimum(l, k * g_ot).sum() / e_l for k in fatores]

    def precisa(xs, ys, alvo):
        for x, y in zip(xs, ys):
            if y >= alvo:
                return float(x)
        return None

    alvos = {}
    for a in (0.90, 0.95, 0.99):
        alvos[f"{a:.2f}"] = {"bateria_mwh": precisa(energias, cfe_bat, a),
                             "sobrecontratacao": precisa(fatores, cfe_sobre, a)}
    mes = carga.index.month
    razao_mensal = (pd.Series(g_ot, index=carga.index).groupby(mes).sum()
                    / carga.groupby(mes).sum())
    return {
        "razao_mensal": razao_mensal.to_dict(),
        "eolica": metricas(eol), "solar": metricas(sol), "otimo": otimo,
        "curva": curva, "energias": energias.tolist(), "cfe_bat": cfe_bat,
        "fatores": fatores.tolist(), "cfe_sobre": cfe_sobre, "p_bat": p_bat,
        "alvos": alvos, "e_carga_gwh": e_l / 1e3,
        "fc_eolica": float(ne.val_gereolica.mean() / ne.val_gereolica.max()),
    }


# ---------------------------------------------------------------------------
# Etapa 3 - constrained-off
# ---------------------------------------------------------------------------
def etapa3(carga):
    c = pd.read_csv(DADOS / "ons_coff_ne_2025_horario.csv", parse_dates=["hora"],
                    index_col="hora").reindex(carga.index, fill_value=0.0)
    ne = perfis_ne()
    ene = c.eolica_ENE + c.solar_ENE
    rede = c.eolica_REL + c.eolica_CNF + c.solar_REL + c.solar_CNF
    total = ene + rede
    l = carga
    mensal = pd.DataFrame({"ENE": ene, "REL+CNF": rede}).groupby(c.index.month).sum() / 1e3
    return {
        "total_twh": total.sum() / 1e6,
        "ene_twh": ene.sum() / 1e6,
        "rede_twh": rede.sum() / 1e6,
        "eolica_twh": (c.eolica_ENE + c.eolica_REL + c.eolica_CNF).sum() / 1e6,
        "solar_twh": (c.solar_ENE + c.solar_REL + c.solar_CNF).sum() / 1e6,
        "ger_eolica_twh": ne.val_gereolica.sum() / 1e6,
        "ger_solar_twh": ne.val_gersolar.sum() / 1e6,
        "horas_com_corte": float((total > 0).mean()),
        "horas_ene_maior_carga": float((ene >= l).mean()),
        "absorve_ene": float(np.minimum(l, ene).sum() / l.sum()),
        # concentracao temporal do corte energetico (horas sem registro = corte nulo)
        "mwmed_total": float(total.mean()),
        "mwmed_ene": float(ene.mean()),
        "frac_ene_total": float(ene.sum() / total.sum()),
        "horas_ene_pos": float((ene > 0).mean()),
        "ene_quando_ocorre": float(ene[ene > 0].mean()),
        "ene_diurno": float(ene[(ene.index.hour >= 8) & (ene.index.hour < 17)].sum() / ene.sum()),
        "absorve_total": float(np.minimum(l, total).sum() / l.sum()),
        "razao_corte_campus": float(total.sum() / l.sum()),
        "mensal": mensal,
    }


# ---------------------------------------------------------------------------
# Etapa 4 - Campinas/Pau D'Alho: limiar evaporativo e escala declarada
# ---------------------------------------------------------------------------
T_LIMIAR_DEC = 29.4      # °C, acionamento do resfriamento evaporativo direto
                         # declarado pela Microsoft (Portaria GAEMA, 2026)
P_TI_PAU_DALHO = 386.0   # MW de TI do conjunto de 10 prédios (RIT do EIV, 2026)
MUST_PAU_DALHO = 300.0   # MW contratados no Parecer de Acesso (ONS, 2025)
SANASA_LS = 1.014        # L/s, demanda de água do Informe Técnico SANASA 0096/2026


def etapa4(clima):
    """Frequência do limiar de 29,4 °C em Campinas e o campus Pau D'Alho
    completo (386 MW de TI) com as premissas do Capítulo 9."""
    tbs = clima.tbs
    acima = tbs > T_LIMIAR_DEC
    dias = tbs.resample("D").max() > T_LIMIAR_DEC
    por_ano_h = acima.groupby(acima.index.year).mean()
    por_ano_d = dias.groupby(dias.index.year).mean()
    mes_d = dias.groupby(dias.index.month).mean()

    pr = replace(BASE, p_nominal=P_TI_PAU_DALHO)
    cen = {}
    for c in "ACD":
        s = simular(clima, c, pr)
        anos = [indicadores(g, pr) for _, g in s.groupby(s.index.year)]
        cen[c] = {k: float(np.mean([a[k] for a in anos])) for k in anos[0]}
        cen[c]["pue_max_total"] = float((s.p_total / s.p_ti).max())
    # demanda máxima em ocupação plena (utilização de 100% da TI)
    for c in "CD":
        sp = simular(clima, c, replace(pr, utilizacao=1.0))
        cen[c]["p_max_pleno"] = float(sp.p_total.max())
    # maior potência nominal de TI cuja demanda máxima horária cabe no MUST
    ti_no_must = {c: MUST_PAU_DALHO / (cen[c]["pue_max_total"] * BASE.utilizacao) for c in "CD"}
    return {
        "horas_acima": float(acima.mean()),
        "dias_acima": float(dias.mean()),
        "dias_acima_min_ano": float(por_ano_d.min()),
        "dias_acima_max_ano": float(por_ano_d.max()),
        "horas_acima_max_ano": float(por_ano_h.max()),
        "mes_dias": {int(k): float(v) for k, v in mes_d.items()},
        "tbs_max": float(tbs.max()),
        "campus": cen,
        "ti_no_must": ti_no_must,
    }


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------
def br(x, casas=1):
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, casas=0):
    return br(100 * x, casas) + "\\%"


def macros(d):
    linhas = ["% Gerado por scripts/exercicio_quantitativo.py -- não editar à mão."]
    for k, v in d.items():
        linhas.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def grafico_mensal(mensal):
    fig, eixos = plt.subplots(2, 2, figsize=(LARGURA, 4.6), sharex=True)
    meses = range(1, 13)
    rot = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    for j, local in enumerate(LOCAIS):
        for c in "ABCD":
            m = mensal[(local, c)]
            eixos[0, j].plot(meses, m.pue, color=CORES[c], lw=1.4, marker="o", ms=2.5,
                             label=NOMES_CURTOS[c])
            if c in "AB":
                eixos[1, j].plot(meses, m.agua_m3_dia, color=CORES[c], lw=1.4,
                                 marker="o", ms=2.5)
        eixos[0, j].set_title(LOCAIS[local], fontsize=10)
        eixos[1, j].set_xticks(list(meses))
        eixos[1, j].set_xticklabels(rot)
        for e in eixos[:, j]:
            e.grid(axis="y", color="#E6E6E6", lw=0.6)
            e.tick_params(length=0)
    eixos[0, 0].set_ylabel("PUE mensal")
    eixos[1, 0].set_ylabel("Água (m³/dia)")
    lim_pue = (1.15, max(e.get_ylim()[1] for e in eixos[0]))
    lim_agua = (0, max(e.get_ylim()[1] for e in eixos[1]))
    for e in eixos[0]:
        e.set_ylim(*lim_pue)
    for e in eixos[1]:
        e.set_ylim(*lim_agua)
        e.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: br(v, 0)))
    for e in eixos[0]:
        e.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: br(v, 2)))
    fig.legend(*eixos[0, 0].get_legend_handles_labels(), loc="lower center",
               ncol=4, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURAS / "grafico2-pue-agua.pdf")
    plt.close(fig)


def grafico_sensibilidade(base_pue, base_wue, linhas):
    fig, eixos = plt.subplots(1, 2, figsize=(LARGURA, 3.2))
    for e, chave, base, titulo, casas in [
            (eixos[0], "pue", base_pue, "PUE -- cenário C (seco)", 2),
            (eixos[1], "wue", base_wue, "WUE (L/kWh) -- cenário A (evaporativo)", 2)]:
        dados = [r for r in linhas if abs(r[f"{chave}_alto"] - r[f"{chave}_baixo"]) > 1e-4]
        dados.sort(key=lambda r: abs(r[f"{chave}_alto"] - r[f"{chave}_baixo"]))
        for i, r in enumerate(dados):
            lo, hi = r[f"{chave}_baixo"], r[f"{chave}_alto"]
            e.barh(i, lo - base, left=base, color=AZUL_CLARO, ec=AZUL, lw=0.6, height=0.6)
            e.barh(i, hi - base, left=base, color=AZUL_MEDIO, ec=AZUL, lw=0.6, height=0.6)
        e.set_yticks(range(len(dados)))
        e.set_yticklabels([r["rotulo"].replace("\\textit{chiller}", "chiller")
                           for r in dados], fontsize=7.5)
        e.axvline(base, color=CINZA, lw=0.8)
        e.set_title(titulo, fontsize=9)
        e.tick_params(length=0, labelsize=7.5)
        e.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _, c=casas: br(v, c)))
        e.grid(axis="x", color="#E6E6E6", lw=0.6)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(fc=AZUL_CLARO, ec=AZUL, label="limite inferior da faixa"),
                        Patch(fc=AZUL_MEDIO, ec=AZUL, label="limite superior da faixa")],
               loc="lower center", ncol=2, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(FIGURAS / "grafico3-sensibilidade.pdf")
    plt.close(fig)


def grafico_correspondencia(r2):
    fig, eixos = plt.subplots(1, 2, figsize=(LARGURA, 2.9))
    xs = [100 * r["eolica"] for r in r2["curva"]]
    eixos[0].plot(xs, [100 * r["cfe"] for r in r2["curva"]], color=AZUL, lw=1.6)
    eixos[0].axvline(100 * r2["otimo"]["eolica"], color=CINZA_CLARO, lw=0.8, ls="--")
    eixos[0].set_xlabel("Participação eólica no contrato (%)")
    eixos[0].set_ylabel("Correspondência horária (%)")
    eixos[0].set_title("Contrato com 100% de equivalência anual", fontsize=9)
    eixos[1].plot(r2["energias"], [100 * v for v in r2["cfe_bat"]], color=AZUL, lw=1.6)
    eixos[1].set_xlabel("Energia da bateria (MWh)")
    eixos[1].set_title("Mistura ótima + armazenamento", fontsize=9)
    eixos[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: br(v, 0)))
    for e in eixos:
        e.set_ylim(50, 100)
        e.grid(color="#E6E6E6", lw=0.6)
        e.tick_params(length=0)
        for a in (90, 95):
            e.axhline(a, color=CINZA_CLARO, lw=0.6)
    fig.tight_layout()
    fig.savefig(FIGURAS / "grafico4-correspondencia.pdf")
    plt.close(fig)


def grafico_curtailment(r3):
    m = r3["mensal"]
    fig, ax = plt.subplots(figsize=(LARGURA, 2.8))
    rot = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    x = np.arange(12)
    ax.bar(x, m["ENE"], color=AZUL, label="Razão energética (ENE)", zorder=2)
    ax.bar(x, m["REL+CNF"], bottom=m["ENE"], color=AZUL_CLARO, ec=AZUL, lw=0.5,
           label="Razões elétricas (REL e CNF)", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(rot)
    ax.set_ylabel("GWh")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: br(v, 0)))
    ax.grid(axis="y", color="#E6E6E6", lw=0.6, zorder=0)
    ax.tick_params(length=0)
    ax.spines["left"].set_visible(False)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.savefig(FIGURAS / "grafico5-constrained-off.pdf")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Tabelas LaTeX
# ---------------------------------------------------------------------------
def tabela_premissas():
    p = BASE
    linhas = [
        ("Potência de TI nominal / utilização média", f"{br(p.p_nominal,0)} MW / {pct(p.utilizacao)}", "60\\%--90\\%"),
        ("Perdas elétricas (UPS, transformação, distribuição)", pct(p.f_elet), "4\\%--10\\%"),
        ("Serviços auxiliares (iluminação, segurança)", pct(p.f_aux), "--"),
        ("Ventilação interna (fração do calor no ar)", pct(p.f_ar), "2\\%--6\\%"),
        ("Água gelada de alimentação", f"{br(p.t_agua_gelada,0)} °C", "14--22 °C"),
        ("Eficiência do \\textit{chiller} (fração do COP de Carnot)", br(p.eta_carnot, 2), "0,45--0,65"),
        ("Aproximação da torre ao bulbo úmido", f"{br(p.ap_torre,0)} K", "3--6 K"),
        ("Diferença ar externo--condensação (\\textit{chiller} a ar)", f"{br(p.itd_ar,0)} K", "12--18 K"),
        ("Parcela do calor da torre rejeitada por evaporação", br(p.f_latente, 2), "0,75--1,00"),
        ("Ciclos de concentração da torre", br(p.ciclos, 0), "3--6"),
        ("Efetividade adiabática / acionamento", f"{br(p.eps_adiab,2)} / {br(p.t_liga_adiab,0)} °C", "--"),
        ("Parcela da TI no circuito líquido (cenário D)", pct(p.frac_liquido), "--"),
        ("Água do circuito líquido (classe ASHRAE)", f"W{p.t_classe_w:.0f}", "W40"),
        ("Fator de emissão médio do SIN", f"{br(p.fator_emissao,4)} tCO\\textsubscript{{2}}/MWh", "--"),
    ]
    corpo = "\n".join(f"\t\t{a} & {b} & {c} \\\\" for a, b, c in linhas)
    return ("\\begin{tabular}{@{}p{8.2cm}ll@{}}\n\t\t\\toprule\n"
            "\t\t\\textbf{Premissa} & \\textbf{Valor-base} & \\textbf{Faixa testada} \\\\\n"
            "\t\t\\midrule\n" + corpo + "\n\t\t\\bottomrule\n\t\\end{tabular}\n")


def tabela_resultados(res):
    def linha(rotulo, f):
        cel = [f(res[(lo, c)]) for lo in LOCAIS for c in "ABCD"]
        return f"\t\t{rotulo} & " + " & ".join(cel) + " \\\\"
    linhas = [
        linha("PUE anual (média)", lambda r: br(r["pue"], 2)),
        linha("PUE horário máximo", lambda r: br(r["pue_max"], 2)),
        linha("Demanda máxima (MW)", lambda r: br(r["p_max"], 0)),
        linha("Carga média (MW médios)", lambda r: br(r["mw_medios"], 0)),
        linha("Fator de carga", lambda r: br(r["fc"], 2)),
        linha("Energia total (GWh/ano)", lambda r: br(r["e_total_gwh"], 0)),
        linha("WUE (L/kWh)", lambda r: br(r["wue"], 2)),
        linha("Água (mil m³/ano)", lambda r: br(r["agua_m3_ano"] / 1e3, 0)),
        linha("Água no mês crítico (m³/dia)", lambda r: br(r["agua_max_mes_m3_dia"], 0)),
        linha("Emissões (mil tCO\\textsubscript{2}/ano)", lambda r: br(r["co2_t_ano"] / 1e3, 1)),
    ]
    cab = " & ".join(f"\\textbf{{{c}}}" for _ in LOCAIS for c in "ABCD")
    return ("\\begin{tabular}{@{}l" + "r" * 8 + "@{}}\n\t\t\\toprule\n"
            "\t\t & \\multicolumn{4}{c}{\\textbf{Pecém}} & \\multicolumn{4}{c}{\\textbf{Campinas}} \\\\\n"
            "\t\t\\cmidrule(lr){2-5}\\cmidrule(l){6-9}\n"
            f"\t\t\\textbf{{Indicador}} & {cab} \\\\\n\t\t\\midrule\n"
            + "\n".join(linhas) + "\n\t\t\\bottomrule\n\t\\end{tabular}\n")


def tabela_correspondencia(r2):
    def linha(rotulo, m):
        return (f"\t\t{rotulo} & {pct(m['cfe'])} & {pct(m['horas_plenas'])} & "
                f"{br(m['deficit_max'],0)} & {pct(m['excedente'])} \\\\")
    ot = r2["otimo"]
    rot_ot = f"Mistura ótima ({br(100*ot['eolica'],0)}\\% eólica)"
    return ("\\begin{tabular}{@{}lrrrr@{}}\n\t\t\\toprule\n"
            "\t\t\\textbf{Contrato} & \\textbf{Correspondência} & \\textbf{Horas plenas} & "
            "\\textbf{Déficit máx. (MW)} & \\textbf{Excedente} \\\\\n\t\t\\midrule\n"
            + "\n".join([linha("Somente eólico", r2["eolica"]),
                         linha("Somente solar", r2["solar"]),
                         linha(rot_ot, ot)])
            + "\n\t\t\\bottomrule\n\t\\end{tabular}\n")


# ---------------------------------------------------------------------------
def main():
    climas = {lo: carregar_clima(lo) for lo in LOCAIS}
    res, mensal = etapa1(climas)
    base_pue, base_wue, sens = sensibilidade(climas["pecem"])

    pecem25 = climas["pecem"][climas["pecem"].index.year == 2025]
    carga = simular(pecem25, "D").p_total
    r2 = etapa2(carga)
    r3 = etapa3(carga)
    r4 = etapa4(climas["campinas"])

    # verificações de consistência
    for (lo, c), r in res.items():
        assert r["pue"] > 1 and r["wue"] >= 0, (lo, c)
    assert res[("pecem", "C")]["wue"] == 0 and res[("pecem", "D")]["wue"] == 0
    assert 0 < r2["otimo"]["cfe"] < 1

    grafico_mensal(mensal)
    grafico_sensibilidade(base_pue, base_wue, sens)
    grafico_correspondencia(r2)
    grafico_curtailment(r3)

    (TABELAS / "tab-premissas.tex").write_text(tabela_premissas(), encoding="utf-8")
    (TABELAS / "tab-resultados.tex").write_text(tabela_resultados(res), encoding="utf-8")
    (TABELAS / "tab-correspondencia.tex").write_text(tabela_correspondencia(r2), encoding="utf-8")

    pa, pb, pc, pd_ = (res[("pecem", c)] for c in "ABCD")
    ca, cc = res[("campinas", "A")], res[("campinas", "C")]
    dessal_ls = 1000.0
    n = {
        "nPUEApecem": br(pa["pue"], 2), "nPUEBpecem": br(pb["pue"], 2),
        "nPUECpecem": br(pc["pue"], 2), "nPUEDpecem": br(pd_["pue"], 2),
        "nPUEAcampinas": br(ca["pue"], 2), "nPUECcampinas": br(cc["pue"], 2),
        "nPUEDcampinas": br(res[("campinas", "D")]["pue"], 2),
        "nVarPUEAnos": br(max(r["pue_max_ano"] - r["pue_min_ano"]
                              for k, r in res.items() if k[1] in "ABCD"), 2),
        "nWUEApecem": br(pa["wue"], 2), "nWUEBpecem": br(pb["wue"], 2),
        "nWUEAcampinas": br(ca["wue"], 2), "nWUEBcampinas": br(res[("campinas", "B")]["wue"], 2),
        "nAguaApecem": br(pa["agua_m3_ano"] / 1e6, 2),
        "nAguaApecemLs": br(pa["agua_ls"], 0),
        "nAguaApecemDia": br(pa["agua_m3_ano"] / 365, 0),
        "nAguaApecemDessal": pct(pa["agua_ls"] / dessal_ls, 1),
        "nAguaApecemPop": br(pa["agua_ls"] / dessal_ls * 720, 0),
        "nAguaBpecem": br(pb["agua_m3_ano"] / 1e3, 0),
        "nEnergiaApecem": br(pa["e_total_gwh"], 0), "nEnergiaCpecem": br(pc["e_total_gwh"], 0),
        "nEnergiaDpecem": br(pd_["e_total_gwh"], 0),
        "nDeltaEnergiaCA": br(pc["e_total_gwh"] - pa["e_total_gwh"], 0),
        "nDeltaMWCA": br(pc["mw_medios"] - pa["mw_medios"], 1),
        "nTrocaAguaEnergia": br(pa["agua_m3_ano"] / ((pc["e_total_gwh"] - pa["e_total_gwh"]) * 1e3), 1),
        "nPmaxApecem": br(pa["p_max"], 0), "nPmaxCpecem": br(pc["p_max"], 0),
        "nPmaxDpecem": br(pd_["p_max"], 0),
        "nFCCpecem": br(pc["fc"], 2), "nFCApecem": br(pa["fc"], 2),
        "nMWmedCpecem": br(pc["mw_medios"], 0), "nMWmedApecem": br(pa["mw_medios"], 0),
        "nCampiNordeste": br(2098 / pc["mw_medios"], 0),
        "nPconexaoCpecem": br(pc["pue_max"] * BASE.p_nominal, 0),
        "nPconexaoDpecem": br(pd_["pue_max"] * BASE.p_nominal, 0),
        "nDeltaConexao": br((pc["pue_max"] - pd_["pue_max"]) * BASE.p_nominal, 0),
        "nFracEPE": pct(pc["pue_max"] * BASE.p_nominal / 4000, 1),
        "nLivreLiqPecem": pct(pd_["horas_livres_liq"], 0),
        "nLivreLiqPecemQuarenta": pct(res[("pecem", "D40")]["horas_livres_liq"], 0),
        "nPUEDpecemQuarenta": br(res[("pecem", "D40")]["pue"], 2),
        "nLivreAcampinas": pct(ca["horas_livres"], 0), "nLivreApecem": pct(pa["horas_livres"], 0),
        "nLivreCcampinas": pct(cc["horas_livres"], 0),
        "nCOtwoCpecem": br(pc["co2_t_ano"] / 1e3, 1),
        "nAguaMaxApecem": br(pa["agua_max_mes_m3_dia"], 0),
        "nSensPUEmin": br(min(min(r["pue_baixo"], r["pue_alto"]) for r in sens), 2),
        "nSensPUEmax": br(max(max(r["pue_baixo"], r["pue_alto"]) for r in sens), 2),
        "nSensWUEmin": br(min(min(r["wue_baixo"], r["wue_alto"]) for r in sens), 2),
        "nSensWUEmax": br(max(max(r["wue_baixo"], r["wue_alto"]) for r in sens), 2),
        "nCFEeolica": pct(r2["eolica"]["cfe"]), "nCFEsolar": pct(r2["solar"]["cfe"]),
        "nCFEotimo": pct(r2["otimo"]["cfe"]), "nMixOtimo": pct(r2["otimo"]["eolica"]),
        "nHorasPlenasOtimo": pct(r2["otimo"]["horas_plenas"]),
        "nDeficitMaxOtimo": br(r2["otimo"]["deficit_max"], 0),
        "nExcedenteOtimo": pct(r2["otimo"]["excedente"]),
        "nPotBateria": br(r2["p_bat"], 0),
        "nCFEbatUmaHora": pct(r2["cfe_bat"][r2["energias"].index(round(r2["p_bat"], -2))]),
        "nCFEbatMax": pct(r2["cfe_bat"][-1]),
        "nBatMax": br(r2["energias"][-1], 0),
        "nRazaoMin": pct(min(r2["razao_mensal"].values())),
        "nRazaoMax": pct(max(r2["razao_mensal"].values())),
        "nMesRazaoMin": MESES[min(r2["razao_mensal"], key=r2["razao_mensal"].get) - 1],
        "nMesRazaoMax": MESES[max(r2["razao_mensal"], key=r2["razao_mensal"].get) - 1],
        "nTbsPecem": br(climas["pecem"].tbs.mean(), 1),
        "nTbuPecem": br(climas["pecem"].tbu.mean(), 1),
        "nTbsMaxPecem": br(climas["pecem"].tbs.max(), 1),
        "nTbsCampinas": br(climas["campinas"].tbs.mean(), 1),
        "nTbuCampinas": br(climas["campinas"].tbu.mean(), 1),
        "nCargaGWh": br(r2["e_carga_gwh"], 0),
        "nCoffTotal": br(r3["total_twh"], 1), "nCoffENE": br(r3["ene_twh"], 1),
        "nCoffRede": br(r3["rede_twh"], 1),
        "nCoffEolica": br(r3["eolica_twh"], 1), "nCoffSolar": br(r3["solar_twh"], 1),
        "nCoffFracEolica": pct(r3["eolica_twh"] / (r3["ger_eolica_twh"] + r3["eolica_twh"]), 0),
        "nCoffHoras": pct(r3["horas_com_corte"], 0),
        "nCoffHorasENE": pct(r3["horas_ene_maior_carga"], 0),
        "nCoffAbsorveENE": pct(r3["absorve_ene"], 0),
        "nCoffAbsorveTotal": pct(r3["absorve_total"], 0),
        "nCoffVezes": br(r3["razao_corte_campus"], 0),
        "nCoffMWmedTotal": br(round(r3["mwmed_total"], -1), 0),
        "nCoffMWmedENE": br(round(r3["mwmed_ene"], -1), 0),
        "nCoffFracENE": pct(r3["frac_ene_total"], 0),
        "nCoffHorasENEpos": pct(r3["horas_ene_pos"], 0),
        "nCoffENEquando": br(round(r3["ene_quando_ocorre"], -2), 0),
        "nCoffDiurno": pct(r3["ene_diurno"], 0),
    }
    for alvo, nome in (("0.90", "Noventa"), ("0.95", "NoventaCinco"), ("0.99", "NoventaNove")):
        a = r2["alvos"][alvo]
        n[f"nBat{nome}"] = br(a["bateria_mwh"], 0) if a["bateria_mwh"] is not None else "mais de 6.000"
        n[f"nBatHoras{nome}"] = (br(a["bateria_mwh"] / r2["p_bat"], 0)
                                 if a["bateria_mwh"] is not None else "mais de 60")
        n[f"nSobre{nome}"] = (br(a["sobrecontratacao"], 2) if a["sobrecontratacao"] is not None
                              else "mais de 3")
    # Etapa 4 - Campinas/Pau D'Alho
    pdA, pdC, pdD = (r4["campus"][c] for c in "ACD")
    assert 0 <= r4["dias_acima"] <= 1 and pdC["wue"] == 0 and pdD["wue"] == 0
    meses_ord = sorted(r4["mes_dias"], key=r4["mes_dias"].get, reverse=True)
    n.update({
        "nLimiarDEC": br(T_LIMIAR_DEC, 1),
        "nHorasAcimaLimiar": pct(r4["horas_acima"], 0),
        "nDiasAcimaLimiar": pct(r4["dias_acima"], 0),
        "nDiasAcimaLimiarMin": pct(r4["dias_acima_min_ano"], 0),
        "nDiasAcimaLimiarMax": pct(r4["dias_acima_max_ano"], 0),
        "nMesMaisLimiar": MESES[meses_ord[0] - 1],
        "nMesMaisLimiarDias": pct(r4["mes_dias"][meses_ord[0]], 0),
        "nMesSegundoLimiar": MESES[meses_ord[1] - 1],
        "nTbsMaxCampinas": br(r4["tbs_max"], 1),
        "nPauDalhoTI": br(P_TI_PAU_DALHO, 0),
        "nPauDalhoMUST": br(MUST_PAU_DALHO, 0),
        "nPauDalhoMUSTTWh": br(MUST_PAU_DALHO * 8760 / 1e6, 2),
        "nPauDalhoAguaALs": br(pdA["agua_ls"], 0),
        "nPauDalhoAguaAm": br(pdA["agua_m3_ano"] / 1e6, 1),
        "nSanasaLs": br(SANASA_LS, 1),
        "nPauDalhoRazaoSanasa": br(pdA["agua_ls"] / SANASA_LS, 0),
        "nPauDalhoEnergiaC": br(pdC["e_total_gwh"] / 1e3, 2),
        "nPauDalhoEnergiaD": br(pdD["e_total_gwh"] / 1e3, 2),
        "nPauDalhoDeltaCA": br(pdC["e_total_gwh"] - pdA["e_total_gwh"], 0),
        "nPauDalhoPmaxC": br(pdC["p_max"], 0),
        "nPauDalhoPmaxD": br(pdD["p_max"], 0),
        "nPauDalhoPmaxDPleno": br(pdD["p_max_pleno"], 0),
        "nPauDalhoPmaxCPleno": br(pdC["p_max_pleno"], 0),
        "nPauDalhoMWmedD": br(pdD["mw_medios"], 0),
        "nPauDalhoTInoMUSTD": br(r4["ti_no_must"]["D"], 0),
        "nPauDalhoTInoMUSTC": br(r4["ti_no_must"]["C"], 0),
    })
    (TABELAS / "numeros.tex").write_text(macros(n), encoding="utf-8")

    saida = {"etapa1": {f"{lo}_{c}": r for (lo, c), r in res.items()},
             "sensibilidade": {"base_pue_C": base_pue, "base_wue_A": base_wue, "linhas": sens},
             "etapa2": {k: v for k, v in r2.items() if k not in ("curva", "cfe_bat", "cfe_sobre")},
             "etapa3": {k: v for k, v in r3.items() if k != "mensal"},
             "etapa4": r4,
             "numeros": n}
    (AQUI / "resultados.json").write_text(json.dumps(saida, indent=1, ensure_ascii=False,
                                                     default=float), encoding="utf-8")
    print(json.dumps(n, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
