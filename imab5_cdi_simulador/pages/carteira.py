"""
Página Simulador de Carteira — retorno ponderado IMA-B 5 + CDI
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta

from utils.session_state import init_session_state, get_ipca_cenario, get_selic_cenario, ipca_list_to_df, selic_list_to_reunioes
from utils.business_days import load_holidays, count_business_days
from utils.vna import (
    build_ipca_monthly_map,
    project_vna_daily,
    calcular_retorno_imab5,
    calcular_retorno_cdi,
    get_vna_at_date,
)


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">💼 Simulador de Carteira</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">'
        'Defina a alocação entre IMA-B 5 e CDI e veja o retorno ponderado esperado '
        'em diferentes cenários de abertura/fechamento de curva.'
        '</div>',
        unsafe_allow_html=True
    )

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real = st.session_state.get("taxa_real_aa", 7.75)
    duration_du = st.session_state.get("duration_du", 496)

    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))

    if not ipca_list or not selic_list:
        st.warning("⚠️ Carregue IPCA e Selic na aba **Parâmetros** antes de simular.")
        return

    vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))
    vna_ini = get_vna_at_date(data_inicio, vna_hist)
    if vna_ini is None:
        st.warning("⚠️ VNA não encontrado. Carregue o histórico na aba **Histórico VNA**.")
        return

    # ── Configuração da carteira ───────────────────────────────────────────────
    st.markdown("### ⚖️ Alocação da Carteira")

    col1, col2 = st.columns(2)
    with col1:
        peso_imab = st.slider(
            "IMA-B 5 (%)",
            min_value=0, max_value=100,
            value=int(st.session_state.get("peso_imab5", 50)),
            step=5, key="cart_imab"
        )
        st.session_state["peso_imab5"] = float(peso_imab)
    with col2:
        peso_cdi = 100 - peso_imab
        st.session_state["peso_cdi"] = float(peso_cdi)
        st.metric("CDI (%)", f"{peso_cdi}%", delta=f"IMA-B 5: {peso_imab}%", delta_color="off")

    # Gráfico de pizza
    _render_pizza(peso_imab, peso_cdi)

    # ── Cenários de marcação ───────────────────────────────────────────────────
    st.markdown("### 📐 Cenários de Abertura/Fechamento")

    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
    variacoes = {}
    cenarios_cfg = [
        ("c1", "🟢 Fechamento Forte", -1.0),
        ("c2", "🟩 Fechamento Suave", -0.50),
        ("c3", "🟡 Estabilidade", 0.0),
        ("c4", "🟧 Abertura Suave", 0.50),
        ("c5", "🔴 Abertura Forte", 1.0),
    ]
    cols = [col_c1, col_c2, col_c3, col_c4, col_c5]

    for (key, label, default), col in zip(cenarios_cfg, cols):
        with col:
            v = st.number_input(
                label,
                min_value=-10.0, max_value=10.0,
                value=float(st.session_state.get(f"cart_{key}", default)),
                step=0.10, format="%.2f",
                key=f"cart_{key}_input"
            )
            st.session_state[f"cart_{key}"] = v
            variacoes[label] = v

    # ── Cálculo ────────────────────────────────────────────────────────────────
    ipca_df = ipca_list_to_df(ipca_list)
    ipca_monthly = build_ipca_monthly_map(ipca_df, data_inicio, data_fim)
    selic_reunioes = selic_list_to_reunioes(selic_list)

    with st.spinner("Calculando..."):
        df_vna_proj = project_vna_daily(data_inicio, data_fim, vna_ini, ipca_monthly, holidays)

    if df_vna_proj.empty:
        st.error("Erro ao projetar VNA.")
        return

    vna_fim = float(df_vna_proj.iloc[-1]["VNA"])
    res_cdi = calcular_retorno_cdi(data_inicio, data_fim, selic_reunioes, holidays)
    du_total = count_business_days(data_inicio, data_fim, holidays)

    # Calcular para cada cenário
    resultados = []
    for label, variacao in variacoes.items():
        res_imab = calcular_retorno_imab5(
            data_inicio, data_fim, taxa_real, duration_du,
            vna_ini, vna_fim, variacao, holidays
        )
        ret_imab = res_imab["retorno_total"]
        ret_cdi = res_cdi["retorno_cdi"]

        # Retorno ponderado
        ret_carteira = (peso_imab / 100) * ret_imab + (peso_cdi / 100) * ret_cdi

        resultados.append({
            "Cenário": label,
            "Δ Taxa (p.p.)": variacao,
            "Retorno IMA-B5 (%)": round(ret_imab * 100, 4),
            "Retorno CDI (%)": round(ret_cdi * 100, 4),
            "Retorno Carteira (%)": round(ret_carteira * 100, 4),
            "vs CDI Puro (p.p.)": round((ret_carteira - ret_cdi) * 100, 4),
            "vs IMA-B5 Puro (p.p.)": round((ret_carteira - ret_imab) * 100, 4),
        })

    df_res = pd.DataFrame(resultados)

    # ── Exibição ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### 📊 Resultados | {data_inicio.strftime('%d/%m/%Y')} → {data_fim.strftime('%d/%m/%Y')} | {du_total} DU")

    # Cards principais
    _render_cards_carteira(df_res, peso_imab, peso_cdi)

    # Gráfico
    _render_grafico_carteira(df_res)

    # Tabela detalhada
    st.markdown("### 📋 Tabela Detalhada")
    st.dataframe(
        df_res.style.format({
            "Δ Taxa (p.p.)": "{:+.2f}",
            "Retorno IMA-B5 (%)": "{:.4f}",
            "Retorno CDI (%)": "{:.4f}",
            "Retorno Carteira (%)": "{:.4f}",
            "vs CDI Puro (p.p.)": "{:+.4f}",
            "vs IMA-B5 Puro (p.p.)": "{:+.4f}",
        }).background_gradient(subset=["Retorno Carteira (%)"], cmap="RdYlGn"),
        use_container_width=True, hide_index=True
    )

    # ── Análise de sensibilidade por alocação ──────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Sensibilidade por Alocação")
    _render_sensibilidade(
        data_inicio, data_fim, taxa_real, duration_du,
        vna_ini, vna_fim, selic_reunioes, holidays,
        variacoes, res_cdi
    )


def _render_pizza(peso_imab: int, peso_cdi: int):
    if peso_imab == 0 or peso_cdi == 0:
        return
    fig = go.Figure(go.Pie(
        labels=["IMA-B 5", "CDI"],
        values=[peso_imab, peso_cdi],
        marker_colors=["#1B4F72", "#2E86C1"],
        textinfo="label+percent",
        hole=0.45,
    ))
    fig.update_layout(
        height=220,
        margin=dict(t=10, b=10, l=0, r=0),
        showlegend=False,
    )
    col_center, _, _ = st.columns([1, 2, 2])
    with col_center:
        st.plotly_chart(fig, use_container_width=True)


def _render_cards_carteira(df: pd.DataFrame, peso_imab: float, peso_cdi: float):
    estab = df[df["Δ Taxa (p.p.)"] == 0.0]
    ret_cdi_puro = df.iloc[0]["Retorno CDI (%)"]

    cols = st.columns(len(df))
    emojis = ["🟢", "🟩", "🟡", "🟧", "🔴"]
    for i, (col, (_, row)) in enumerate(zip(cols, df.iterrows())):
        with col:
            ret = row["Retorno Carteira (%)"]
            vs_cdi = row["vs CDI Puro (p.p.)"]
            cor = "#1E8449" if vs_cdi >= 0 else "#C0392B"
            sinal = "+" if vs_cdi >= 0 else ""
            st.markdown(f"""
            <div style="background:white; border-radius:10px; padding:14px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.08);
                        border-top:4px solid {cor}; text-align:center;">
                <div style="font-size:0.75rem; color:#7F8C8D; font-weight:600;">{row['Cenário']}</div>
                <div style="font-size:1.35rem; font-weight:700; color:#1B4F72; margin:6px 0;">{ret:.4f}%</div>
                <div style="font-size:0.72rem; color:{cor};">{sinal}{vs_cdi:.4f} p.p. vs CDI</div>
            </div>
            """, unsafe_allow_html=True)


def _render_grafico_carteira(df: pd.DataFrame):
    fig = go.Figure()

    # IMA-B 5 (linha de referência)
    fig.add_trace(go.Scatter(
        name="IMA-B 5 (100%)",
        x=df["Δ Taxa (p.p.)"], y=df["Retorno IMA-B5 (%)"],
        mode="lines+markers",
        line=dict(color="#1B4F72", width=2, dash="dot"),
        marker=dict(size=8),
    ))

    # CDI (linha de referência)
    fig.add_hline(
        y=df["Retorno CDI (%)"].mean(),
        line_dash="dash", line_color="#2E86C1",
        annotation_text="CDI (100%)",
        annotation_position="top right",
    )

    # Carteira
    fig.add_trace(go.Scatter(
        name="Carteira Mista",
        x=df["Δ Taxa (p.p.)"], y=df["Retorno Carteira (%)"],
        mode="lines+markers",
        line=dict(color="#E67E22", width=3),
        marker=dict(size=10, symbol="diamond"),
    ))

    fig.update_layout(
        title="Retorno da Carteira por Cenário de Taxa",
        xaxis_title="Variação da Taxa IMA-B 5 (p.p.)",
        yaxis_title="Retorno (%)",
        height=380,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=12),
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_sensibilidade(
    data_inicio, data_fim, taxa_real, duration_du,
    vna_ini, vna_fim, selic_reunioes, holidays,
    variacoes, res_cdi
):
    """Heatmap: eixo X = variação taxa, eixo Y = % IMA-B 5, valor = retorno carteira."""
    pesos = list(range(0, 105, 10))  # 0% a 100%
    vars_vals = list(variacoes.values())
    vars_labels = [f"{v:+.1f}p.p." for v in vars_vals]

    # Pré-calcular retorno IMA-B5 por variação
    ret_imab_por_var = {}
    for var in vars_vals:
        res = calcular_retorno_imab5(
            data_inicio, data_fim, taxa_real, duration_du,
            vna_ini, vna_fim, var, holidays
        )
        ret_imab_por_var[var] = res["retorno_total"] * 100

    ret_cdi_val = res_cdi["retorno_cdi"] * 100

    # Montar matriz
    z = []
    for peso in pesos:
        row = []
        for var in vars_vals:
            ret_cart = (peso / 100) * ret_imab_por_var[var] + ((100 - peso) / 100) * ret_cdi_val
            row.append(round(ret_cart, 4))
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=vars_labels,
        y=[f"{p}% IMA-B5" for p in pesos],
        colorscale="RdYlGn",
        text=[[f"{v:.2f}%" for v in row] for row in z],
        texttemplate="%{text}",
        colorbar=dict(title="Retorno (%)"),
        hoverongaps=False,
    ))

    fig.update_layout(
        title="Retorno da Carteira (%) — Sensibilidade Alocação × Cenário de Taxa",
        xaxis_title="Cenário de Taxa IMA-B 5",
        yaxis_title="Alocação IMA-B 5",
        height=500,
        font=dict(family="Arial", size=11),
        margin=dict(t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Verde = maior retorno | Vermelho = menor retorno")
