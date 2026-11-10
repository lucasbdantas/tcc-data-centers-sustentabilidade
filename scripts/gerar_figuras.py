"""Gera as figuras e o gráfico do TCC em PDF vetorial, na pasta ../figuras.

Uso:  python gerar_figuras.py
Requer: matplotlib. Usa a fonte Latin Modern (a mesma do texto LaTeX),
incluída na pasta fonts/.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, Circle

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI.parent / "figuras"
SAIDA.mkdir(exist_ok=True)

for f in (AQUI / "fonts").glob("*.otf"):
    fm.fontManager.addfont(str(f))

plt.rcParams.update({
    "font.family": "Latin Modern Roman",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "pdf.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
})

# Paleta única para todas as ilustrações
AZUL = "#1F4E79"
AZUL_MEDIO = "#5B8DB8"
AZUL_CLARO = "#DCE8F3"
CINZA = "#595959"
CINZA_CLARO = "#BFBFBF"
VERMELHO = "#B22222"

LARGURA = 6.3  # polegadas, largura útil da página A4 com margens ABNT


def milhar(v):
    return f"{v:,.0f}".replace(",", ".")


def caixa(ax, x, y, w, h, texto, fundo=AZUL_CLARO, borda=AZUL, cor_texto="black",
          tamanho=9, negrito=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle="round,pad=0.02,rounding_size=1.2",
                                fc=fundo, ec=borda, lw=1.0, zorder=2))
    ax.text(x, y, texto, ha="center", va="center", fontsize=tamanho,
            color=cor_texto, weight="bold" if negrito else "normal",
            linespacing=1.15, zorder=3)


def seta(ax, x0, y0, x1, y1, cor=CINZA, estilo="-|>", conexao="arc3", lw=1.0):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=estilo, color=cor, lw=lw,
                                shrinkA=0, shrinkB=0, connectionstyle=conexao),
                zorder=1)


def tela(largura, altura, xmax=100, ymax=None):
    fig, ax = plt.subplots(figsize=(largura, altura))
    ymax = ymax if ymax is not None else xmax * altura / largura
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


# ---------------------------------------------------------------------------
# Gráfico 1 - PLAN 2026-2030: previsão de carga de data centers na Rede Básica
# Fontes: Nota Técnica da 1ª RQ (Figura 7) e Workshop da 2ª RQ (p. 68).
# ---------------------------------------------------------------------------
def grafico_plan():
    anos = [2026, 2027, 2028, 2029, 2030]
    series = [
        ("PLAN 2026–2030", [321, 731, 1485, 1852, 2157], CINZA_CLARO),
        ("1ª revisão quadrimestral", [304, 790, 1817, 2582, 3457], AZUL_MEDIO),
        ("2ª revisão quadrimestral", [315, 942, 2390, 3934, 5653], AZUL),
    ]
    fig, ax = plt.subplots(figsize=(LARGURA, 3.3))
    largura = 0.26
    for i, (nome, valores, cor) in enumerate(series):
        xs = [a + (i - 1) * largura for a in anos]
        barras = ax.bar(xs, valores, largura * 0.92, color=cor, label=nome, zorder=2)
        for b, v in zip(barras, valores):
            ax.text(b.get_x() + b.get_width() / 2, v + 70, milhar(v),
                    ha="center", va="bottom", fontsize=7, color=CINZA)
    ax.set_xticks(anos)
    ax.set_xticklabels([str(a) for a in anos])
    ax.set_ylabel("Carga (MW médios)")
    ax.set_ylim(0, 6300)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: milhar(v)))
    ax.grid(axis="y", color="#E6E6E6", lw=0.6, zorder=0)
    ax.tick_params(length=0)
    ax.spines["left"].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.savefig(SAIDA / "grafico1-plan.pdf")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figura 1 - Estágios documentais e físicos
# ---------------------------------------------------------------------------
def figura_estagios():
    fig, ax = tela(LARGURA, 2.55, 100, 40)
    xs = [32, 51.5, 71, 90.5]
    w, h = 17, 11
    doc = ["Anúncio ou\nmanifestação\nde interesse", "Aprovação\ninstitucional",
           "Contrato ou\nfinanciamento", "Licenciamento"]
    fis = ["Implantação\nfísica", "Energização", "Operação", "Plena\nocupação"]
    y_doc, y_fis = 29, 11

    ax.text(0, y_doc, "Estágios\ndocumentais", ha="left", va="center", fontsize=9,
            weight="bold", color=AZUL)
    ax.text(0, y_fis, "Estágios\nfísicos", ha="left", va="center", fontsize=9,
            weight="bold", color=AZUL)

    for i, (x, t) in enumerate(zip(xs, doc)):
        caixa(ax, x, y_doc, w, h, t, tamanho=8.5)
        if i:
            seta(ax, xs[i - 1] + w / 2, y_doc, x - w / 2, y_doc)
    for i, (x, t) in enumerate(zip(xs, fis)):
        caixa(ax, x, y_fis, w, h, t, fundo=AZUL_MEDIO, borda=AZUL, cor_texto="white",
              tamanho=8.5)
        if i:
            seta(ax, xs[i - 1] + w / 2, y_fis, x - w / 2, y_fis)
    # Licenciamento -> Implantação física
    y_meio = (y_doc + y_fis) / 2
    ax.plot([xs[3], xs[3], xs[0]], [y_doc - h / 2, y_meio, y_meio],
            color=CINZA, lw=1.0, zorder=1)
    seta(ax, xs[0], y_meio, xs[0], y_fis + h / 2)

    ax.text(61, 1.2, "Cada etapa exige evidência própria; a existência de uma "
            "não antecipa as posteriores.", ha="center", va="center",
            fontsize=8.5, style="italic", color=CINZA)
    fig.savefig(SAIDA / "figura1-estagios.pdf")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figura 2 - Interdependência das dimensões
# ---------------------------------------------------------------------------
def figura_dimensoes():
    fig, ax = tela(LARGURA, 3.9, 100, 62)
    cx, cy = 50, 31
    nos = {
        "Energia": (18, 52),
        "Água": (82, 52),
        "Telecomunicações": (18, 10),
        "Recursos humanos e\nimpactos socioeconômicos": (82, 10),
    }
    w, h = 32, 10

    # arestas entre dimensões (lados do quadrado) com o tipo de relação
    arestas = [
        ("Energia", "Água", "refrigeração: evaporação\n× eletricidade", 0, 4.6, 0),
        ("Energia", "Telecomunicações", "alimentação de estações\ne redundância de rotas", -8, 0, 90),
        ("Água", "Recursos humanos e\nimpactos socioeconômicos", "competição entre usos\ne comunidades", 8, 0, -90),
        ("Telecomunicações", "Recursos humanos e\nimpactos socioeconômicos", "qualificação para\noperação de redes", 0, -4.6, 0),
    ]
    for a, b, rotulo, dx, dy, rot in arestas:
        (x0, y0), (x1, y1) = nos[a], nos[b]
        if y0 == y1:
            seta(ax, x0 + w / 2, y0, x1 - w / 2, y1, estilo="<|-|>", cor=AZUL_MEDIO)
        else:
            seta(ax, x0, y0 - h / 2, x1, y1 + h / 2, estilo="<|-|>", cor=AZUL_MEDIO)
        ax.text((x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy, rotulo, ha="center",
                va="center", fontsize=7.8, style="italic", color=CINZA, rotation=rot)

    # raios até o núcleo territorial
    for (x, y) in nos.values():
        seta(ax, x + (8 if x < cx else -8), y + (-h / 2 if y > cy else h / 2),
             cx + (-7.5 if x < cx else 7.5), cy + (4 if y > cy else -4),
             estilo="-", cor=CINZA_CLARO, lw=0.9)

    ax.add_patch(Circle((cx, cy), 11.5, fc=AZUL, ec=AZUL, zorder=2))
    ax.text(cx, cy + 1.2, "Território e\ngovernança", ha="center", va="center",
            color="white", fontsize=10, weight="bold", zorder=3)
    ax.text(cx, cy - 5.3, "integra e coordena", ha="center", va="center",
            color="white", fontsize=7.5, style="italic", zorder=3)
    for nome, (x, y) in nos.items():
        caixa(ax, x, y, w, h, nome, tamanho=8.5, negrito=True)
    fig.savefig(SAIDA / "figura2-dimensoes.pdf")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figura 3 - Cadeia física da conectividade
# ---------------------------------------------------------------------------
def figura_cadeia():
    fig, ax = tela(LARGURA, 3.0, 100, 48)
    h = 8
    # trecho internacional
    caixa(ax, 8, 27, 13, h, "Cabo\nsubmarino", fundo="white")
    caixa(ax, 25, 27, 14, h, "Estação de\naterragem")
    seta(ax, 14.5, 27, 18, 27)
    # duas rotas terrestres
    etapas = [(44.5, "Backbone"), (62.5, "Backhaul\nterrestre"), (80.5, "Enlace de\nacesso")]
    lw_etapa = 16
    for y, rota in [(38, "Rota A"), (16, "Rota B")]:
        ax.text(37, y + (5.4 if y > 27 else -7.6), rota, fontsize=8, color=AZUL,
                weight="bold")
        seta(ax, 32, 27, 37, y, conexao="arc3,rad=0")
        for i, (x, t) in enumerate(etapas):
            caixa(ax, x, y, lw_etapa, h, t, tamanho=8.5)
            if i:
                seta(ax, etapas[i - 1][0] + lw_etapa / 2, y, x - lw_etapa / 2, y)
        seta(ax, 80.5 + lw_etapa / 2, y, 91.2, 27 + (3 if y > 27 else -3))
    caixa(ax, 95.5, 27, 8.5, 14, "Data\ncenter", fundo=AZUL, borda=AZUL,
          cor_texto="white", negrito=True)
    # ponto de troca
    caixa(ax, 44.5, 27, 12, 6.5, "Ponto de\ntroca (IX)", fundo="white", tamanho=8)
    seta(ax, 44.5, 34, 44.5, 30.3, estilo="<|-|>", cor=CINZA_CLARO)
    seta(ax, 44.5, 20, 44.5, 23.7, estilo="<|-|>", cor=CINZA_CLARO)
    # ponto comum de falha
    ax.add_patch(FancyBboxPatch((53.5, 9.5), 18, 35,
                                boxstyle="round,pad=0,rounding_size=2",
                                fc="none", ec=VERMELHO, lw=1.1,
                                ls=(0, (4, 2.5)), zorder=4))
    ax.text(62.5, 4.2, "Duto, travessia ou estação compartilhados pelas duas rotas:\n"
            "ponto comum de falha que anula a diversidade", ha="center",
            va="center", fontsize=7.8, color=VERMELHO, style="italic")
    fig.savefig(SAIDA / "figura3-cadeia.pdf")
    plt.close(fig)


if __name__ == "__main__":
    grafico_plan()
    figura_estagios()
    figura_dimensoes()
    figura_cadeia()
    print("Figuras geradas em", SAIDA)
