import io
import math

import altair as alt
import pandas as pd
import streamlit as st
import ollama

from scraper import coletar_avaliacoes_maps

MODELO_OLLAMA = "gemma3:4b"
VERDE = "#6FCF97"
OPCOES_OLLAMA = {"num_ctx": 16384}  # janela de contexto maior para caber as avaliações
MAX_AVALIACOES_IA = 150             # a IA lê só as 150 mais recentes
MAX_CARACTERES_COMENTARIO = 300

PERIODOS = {
    "Desde o início": None,
    "Últimos 2 anos": 730,
    "Último ano": 365,
    "Últimos 6 meses": 182,
    "Últimos 3 meses": 91,
    "Último mês": 30,
}

PERGUNTAS_SUGERIDAS = [
    "Qual é a principal reclamação dos clientes?",
    "O que os clientes mais elogiam?",
    "O atendimento está melhorando ou piorando?",
]

st.set_page_config(page_title="Raio-X de Reputação com IA", layout="wide")

st.title("Raio-X de Reputação de Comércios (Google Maps + IA)")
st.markdown("Cole o link de qualquer estabelecimento no Google Maps para extrair as avaliações mais recentes, gerar um plano de melhoria e tirar dúvidas com a IA.")

col_input, col_qtd = st.columns([4, 1])
with col_input:
    url_maps = st.text_input("Link do estabelecimento no Google Maps:", placeholder="https://www.google.com/maps/place/...")
with col_qtd:
    qtd_reviews = st.number_input("Últimas avaliações (máx. 500)", min_value=5, max_value=500, value=50, step=5)


def gerar_excel(df: pd.DataFrame, diagnostico: str) -> bytes:
    export = pd.DataFrame({
        "Nome": df["nome"],
        "Data (aprox.)": df["data"],
        "Nota": df["nota"],
        "Comentário": df["comentario"],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd/mm/yyyy", date_format="dd/mm/yyyy") as writer:
        export.to_excel(writer, sheet_name="Avaliações", index=False, header=False, startrow=1)
        wb = writer.book
        ws = writer.sheets["Avaliações"]

        f_head = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white",
                                "align": "center", "valign": "vcenter", "border": 1})
        f_txt = wb.add_format({"text_wrap": True, "valign": "top"})
        f_center = wb.add_format({"align": "center", "valign": "top"})
        f_data = wb.add_format({"num_format": "dd/mm/yyyy", "align": "center", "valign": "top"})

        for i, col in enumerate(export.columns):
            ws.write(0, i, col, f_head)

        ws.set_column("A:A", 28, f_txt)
        ws.set_column("B:B", 14, f_data)
        ws.set_column("C:C", 8, f_center)
        ws.set_column("D:D", 100, f_txt)
        ws.set_row(0, 22)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(export), len(export.columns) - 1)

        if diagnostico:
            ws2 = wb.add_worksheet("Diagnóstico IA")
            ws2.set_column("A:A", 130, f_txt)
            ws2.write(0, 0, "Diagnóstico Executivo & Plano de Ação", f_head)
            for i, linha in enumerate(diagnostico.split("\n"), start=1):
                ws2.write(i, 0, linha, f_txt)
    return buf.getvalue()


def serie_diaria(df: pd.DataFrame):
    """Média acumulada da nota, com um ponto para CADA dia (permite hover contínuo)."""
    d = df.dropna(subset=["data"]).sort_values("data").copy()
    if len(d) < 2:
        return None

    d["media"] = d["nota"].expanding().mean()
    d["total"] = range(1, len(d) + 1)
    s = d.groupby("data").agg(media=("media", "last"), total=("total", "last"))

    hoje = pd.Timestamp.today().normalize()
    idx = pd.date_range(s.index.min().normalize(), max(s.index.max().normalize(), hoje), freq="D")
    s = s.reindex(idx)
    s["total"] = s["total"].ffill()
    s["media"] = s["media"].interpolate(method="time")
    s = s.rename_axis("data").reset_index()
    s["media"] = s["media"].round(3)
    return s


def grafico_evolucao(df: pd.DataFrame, dias):
    s = serie_diaria(df)
    if s is None:
        return None

    if dias:
        corte = pd.Timestamp.today().normalize() - pd.Timedelta(days=dias)
        s = s[s["data"] >= corte]
    if len(s) < 2:
        return None

    span = (s["data"].max() - s["data"].min()).days
    formato_x = "%d/%m" if span <= 200 else "%m/%Y"

    ymin = max(1.0, math.floor((s["media"].min() - 0.1) * 10) / 10)
    ymax = min(5.0, math.ceil((s["media"].max() + 0.1) * 10) / 10)
    if ymax - ymin < 0.3:
        meio = (ymax + ymin) / 2
        ymin, ymax = max(1.0, meio - 0.15), min(5.0, meio + 0.15)

    y = alt.Y("media:Q", scale=alt.Scale(domain=[ymin, ymax], clamp=True), title="Média acumulada")
    base = alt.Chart(s).encode(
        x=alt.X("data:T", title=None, axis=alt.Axis(format=formato_x, grid=False))
    )

    area = base.mark_area(
        interpolate="monotone",
        line={"color": VERDE, "strokeWidth": 2.5},
        color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color="rgba(111,207,151,0.35)", offset=0),
                   alt.GradientStop(color="rgba(111,207,151,0.0)", offset=1)],
            x1=1, x2=1, y1=0, y2=1,
        ),
    ).encode(y=y)

    hover = alt.selection_point(fields=["data"], nearest=True, on="mouseover",
                                empty=False, clear="mouseout")

    seletor = base.mark_point().encode(y=y, opacity=alt.value(0)).add_params(hover)

    ponto = base.mark_circle(size=90, color=VERDE).encode(
        y=y, opacity=alt.condition(hover, alt.value(1), alt.value(0))
    )

    regua = base.mark_rule(color="#999", strokeDash=[3, 3]).encode(
        tooltip=[
            alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
            alt.Tooltip("media:Q", title="Média até aqui", format=".2f"),
            alt.Tooltip("total:Q", title="Avaliações até aqui", format="d"),
        ]
    ).transform_filter(hover)

    return (area + seletor + ponto + regua).properties(height=350)


def montar_contexto(df: pd.DataFrame) -> str:
    """Texto com as avaliações mais recentes, usado como base para a IA."""
    linhas = []
    for _, r in df.head(MAX_AVALIACOES_IA).iterrows():
        quando = r["data_texto"] or "data desconhecida"
        comentario = str(r["comentario"])[:MAX_CARACTERES_COMENTARIO]
        linhas.append(f"- [{r['nota']} estrelas | {quando}]: {comentario}")
    return "\n".join(linhas)


def responder_pergunta(contexto: str, historico: list, pergunta: str):
    """Gera a resposta em streaming, com base apenas nas avaliações coletadas."""
    sistema = (
        "Você é um consultor especialista em gestão de comércios e negócios locais. "
        "Responda sempre em português, de forma direta e objetiva, baseando-se ESTRITAMENTE "
        "nas avaliações de clientes abaixo. Se a resposta não puder ser encontrada nelas, "
        "diga isso claramente em vez de inventar. Sempre que possível, cite exemplos "
        "curtos das avaliações e dê recomendações práticas.\n\n"
        f"AVALIAÇÕES DOS CLIENTES:\n{contexto}"
    )
    mensagens = [{"role": "system", "content": sistema}]
    mensagens += historico[-6:]
    mensagens.append({"role": "user", "content": pergunta})

    try:
        for parte in ollama.chat(model=MODELO_OLLAMA, messages=mensagens,
                                 options=OPCOES_OLLAMA, stream=True):
            yield parte["message"]["content"]
    except Exception as e:
        yield f"Erro ao conectar no Ollama. Verifique se ele está rodando. Detalhe: {e}"


# ---------------- Coleta ----------------
if st.button("Analisar Estabelecimento", type="primary"):
    if not url_maps:
        st.warning("Cole um link válido do Google Maps primeiro.")
    else:
        with st.spinner("Coletando as avaliações mais recentes do Google Maps... (pode levar alguns minutos)"):
            dados = coletar_avaliacoes_maps(url_maps, limite=qtd_reviews)

        if not dados:
            for chave in ("df", "diagnostico", "contexto", "chat"):
                st.session_state.pop(chave, None)
            st.error("Não foi possível extrair comentários desse link. Veja o terminal para detalhes do erro.")
        else:
            df = pd.DataFrame(dados)
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            contexto = montar_contexto(df)

            prompt = f"""
            Você é um consultor especialista em gestão de comércios e negócios locais
            (restaurantes, lojas, serviços, clínicas, academias etc.).
            Analise as seguintes avaliações reais de clientes coletadas do Google Maps:

            {contexto}

            Com base estritamente nesses relatos, entregue em português:
            1. **Principais Pontos Fortes** (o que os clientes mais elogiam).
            2. **Gargalos Operacionais** (reclamações recorrentes sobre demora, atendimento, qualidade, preço ou estrutura).
            3. **Plano de Ação Prático** (3 recomendações diretas para o dono do negócio aumentar sua nota e retenção de clientes).
            """
            with st.spinner(f"Gerando insights com Ollama ({MODELO_OLLAMA})..."):
                try:
                    resposta = ollama.chat(model=MODELO_OLLAMA,
                                           messages=[{"role": "user", "content": prompt}],
                                           options=OPCOES_OLLAMA)
                    diagnostico = resposta["message"]["content"]
                except Exception as e:
                    diagnostico = f"Erro ao conectar no Ollama. Verifique se ele está rodando. Detalhe: {e}"

            st.session_state["df"] = df
            st.session_state["diagnostico"] = diagnostico
            st.session_state["contexto"] = contexto
            st.session_state["chat"] = []

# ---------------- Exibição (persiste após cada interação) ----------------
if "df" in st.session_state:
    df = st.session_state["df"]
    diagnostico = st.session_state["diagnostico"]

    st.divider()
    k1, k2, k3 = st.columns(3)
    k1.metric("Avaliações Analisadas", len(df))
    k2.metric("Nota Média (Amostra)", f"{df['nota'].mean():.1f} / 5.0")
    positivos = len(df[df["nota"] >= 4])
    k3.metric("Taxa de Satisfação (4-5 ★)", f"{(positivos / len(df)) * 100:.0f}%")

    if len(df) > MAX_AVALIACOES_IA:
        st.caption(f"Gráficos e Excel usam as {len(df)} avaliações. A IA analisa as {MAX_AVALIACOES_IA} mais recentes.")

    col_graf, col_tab = st.columns(2)

    with col_graf:
        st.subheader("Distribuição de Notas")
        dist = (df["nota"].value_counts()
                .reindex([1, 2, 3, 4, 5], fill_value=0)
                .rename_axis("nota").reset_index(name="qtd"))
        graf_dist = (
            alt.Chart(dist)
            .mark_bar(color="#1F77B4")
            .encode(
                x=alt.X("nota:O", title="Nota (estrelas)", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("qtd:Q", title="Quantidade", axis=alt.Axis(tickMinStep=1, format="d")),
                tooltip=[alt.Tooltip("nota:O", title="Nota"), alt.Tooltip("qtd:Q", title="Qtd")],
            )
            .properties(height=300)
        )
        st.altair_chart(graf_dist, use_container_width=True)

    with col_tab:
        st.subheader("Amostra de Comentários")
        tabela = pd.DataFrame({
            "Nome": df["nome"],
            "Data (aprox.)": df["data"].dt.strftime("%d/%m/%Y").fillna("—"),
            "Nota": df["nota"],
            "Comentário": df["comentario"],
        })
        st.dataframe(tabela, use_container_width=True, height=300, hide_index=True)

    st.subheader("Evolução da Nota ao Longo do Tempo")
    escolha = st.radio("Período", list(PERIODOS.keys()), horizontal=True, key="periodo_grafico")
    graf_evo = grafico_evolucao(df, PERIODOS[escolha])
    if graf_evo is not None:
        st.altair_chart(graf_evo, use_container_width=True)
        st.caption("A linha mostra a média das notas acumulada até cada data. Passe o mouse em qualquer "
                   "ponto do gráfico para ver o valor. O Google informa datas relativas ('há 2 meses'), "
                   "então as datas são aproximadas.")
    else:
        st.info("Não há avaliações suficientes nesse período para montar o gráfico. Tente um período maior.")

    st.divider()
    st.subheader("Diagnóstico Executivo & Plano de Ação (IA)")
    st.markdown(diagnostico)

    # ---------------- Pergunte à IA ----------------
    st.divider()
    st.subheader("Pergunte à IA sobre este negócio")
    st.caption("Faça qualquer pergunta sobre as avaliações coletadas. A IA responde apenas com base nelas.")

    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    cols_sug = st.columns(len(PERGUNTAS_SUGERIDAS))
    for i, texto in enumerate(PERGUNTAS_SUGERIDAS):
        if cols_sug[i].button(texto, key=f"sug_{i}", use_container_width=True):
            st.session_state["pergunta_pendente"] = texto

    for msg in st.session_state["chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    pergunta = st.chat_input("Ex.: O que os clientes reclamam sobre o atendimento?")
    if not pergunta:
        pergunta = st.session_state.pop("pergunta_pendente", None)

    if pergunta:
        with st.chat_message("user"):
            st.markdown(pergunta)
        with st.chat_message("assistant"):
            resposta = st.write_stream(
                responder_pergunta(st.session_state["contexto"], st.session_state["chat"], pergunta)
            )
        st.session_state["chat"].append({"role": "user", "content": pergunta})
        st.session_state["chat"].append({"role": "assistant", "content": resposta})

    if st.session_state["chat"]:
        if st.button("Limpar conversa"):
            st.session_state["chat"] = []
            st.rerun()

    st.divider()
    st.download_button(
        "Baixar planilha (Excel)",
        data=gerar_excel(df, diagnostico),
        file_name="avaliacoes_maps.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )