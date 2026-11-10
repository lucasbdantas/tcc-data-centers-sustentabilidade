"""Baixa e prepara os dados públicos usados no exercício quantitativo.

Saídas em dados/:
  era5_pecem.json, era5_campinas.json   clima horário 2016-2025 (ERA5 via Open-Meteo)
  ons_balanco_2025.csv                   balanço horário por subsistema (ONS)
  ons_coff_ne_2025_horario.csv           geração eólica e solar não realizada por
                                         corte (constrained-off) no Nordeste,
                                         agregada por hora e por motivo (ONS)

Uso:  python baixar_dados.py
Requer: pandas. Os arquivos brutos de constrained-off (~680 MB) são
processados um a um e descartados.
"""
import json
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd

DADOS = Path(__file__).resolve().parent / "dados"
DADOS.mkdir(exist_ok=True)
ONS = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset"
LOCAIS = {"pecem": (-3.55, -38.87), "campinas": (-22.90, -47.06)}


def baixar(url, destino):
    with urllib.request.urlopen(url, timeout=300) as r, open(destino, "wb") as f:
        while bloco := r.read(1 << 20):
            f.write(bloco)


def clima():
    for nome, (lat, lon) in LOCAIS.items():
        destino = DADOS / f"era5_{nome}.json"
        if destino.exists():
            continue
        url = ("https://archive-api.open-meteo.com/v1/archive"
               f"?latitude={lat}&longitude={lon}&start_date=2016-01-01&end_date=2025-12-31"
               "&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,surface_pressure"
               "&timezone=America%2FFortaleza&models=era5")
        baixar(url, destino)
        json.load(open(destino))  # falha cedo se a resposta não for JSON


def balanco():
    destino = DADOS / "ons_balanco_2025.csv"
    if not destino.exists():
        baixar(f"{ONS}/balanco_energia_subsistema_ho/BALANCO_ENERGIA_SUBSISTEMA_2025.csv", destino)


def constrained_off():
    destino = DADOS / "ons_coff_ne_2025_horario.csv"
    if destino.exists():
        return
    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        for fonte, pasta, prefixo in [("eolica", "restricao_coff_eolica_tm", "RESTRICAO_COFF_EOLICA"),
                                      ("solar", "restricao_coff_fotovoltaica_tm", "RESTRICAO_COFF_FOTOVOLTAICA")]:
            for mes in range(1, 13):
                bruto = Path(tmp) / "mes.csv"
                baixar(f"{ONS}/{pasta}/{prefixo}_2025_{mes:02d}.csv", bruto)
                d = pd.read_csv(bruto, sep=";", usecols=["id_subsistema", "din_instante",
                                "cod_razaorestricao", "val_geracaonaorealizadaapurada"])
                d = d[(d.id_subsistema == "NE") & d.cod_razaorestricao.notna()]
                d["hora"] = pd.to_datetime(d.din_instante).dt.floor("h")
                # valores semi-horários em MW médios -> energia horária em MWh
                d["mwh"] = d.val_geracaonaorealizadaapurada.fillna(0) / 2
                g = d.groupby(["hora", "cod_razaorestricao"]).mwh.sum().unstack(fill_value=0)
                g.columns = [f"{fonte}_{c}" for c in g.columns]
                partes.append(g)
                print(fonte, mes, round(g.values.sum() / 1e3), "GWh")
    total = pd.concat(partes).groupby(level=0).sum().fillna(0)
    total.index.name = "hora"
    total.to_csv(destino)


if __name__ == "__main__":
    clima()
    balanco()
    constrained_off()
    print("Dados prontos em", DADOS)
