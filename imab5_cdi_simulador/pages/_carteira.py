"""
Simulador de Carteira — retorno ponderado IMA-B 5 + CDI.
Os 3 cenários vêm da aba Cenários Principais.
"""
import sys, os
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.session_state import (
    init_session_state, get_ipca_cenario, get_selic_cenario,
    ipca_list_to_df, selic_list_to_reunioes,
)
from utils.business_days import load_holidays, count_business_days
from utils.vna import (
    build_ipca_monthly_map, project_vna_daily,
    calcular_retorno_imab5, calcular_retorno_cdi, get_vna_at_date,
)


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">💼 Simulador de Carteira</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">Defina a alocação entre IMA-B 5 e CDI. '
        'Os três cenários de abertura/fechamento são os mesmos da aba '
        '<b>Cenários Principais</b>.</div>', unsafe_allow_html=True
    )

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim    = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real   = st.session_state.get("taxa_real_aa", 7.75)
    duration_du = st.session_state.get("duration_du", 496)

    # Lê variações da aba Cenários Principais
    v1 = float(st.session_state.get("cenario1_variacao", -0.50))
    v2 = float(st.session_state.get("cenario2_variacao",  0.00))
    v3 = float(st.session_state.get("cenario3_variacao",  0.50))

    cenarios_cfg = [
        {"label": "🟢 Cenário 1 — Fechamento",  "var": v1, "cor": "#1E8449"},
        {"label": "🟡 Cenário 2 — Estabilidade", "var": v2, "cor": "#D4AC0D"},
        {"label": "🔴 Cenário 3 — Abertura",     "var": v3, "cor": "#C0392B"},
    ]

    ipca_list  = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))

    if not ipca_list or not selic_list:
        st.warning("⚠️ Carregue IPCA e Selic na aba **Parâmetros**.")
        return

    vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data","VNA","Ref"]))
    vna_ini  = get_vna_at_date(data_inicio, vna_hist)
    if vna_ini is None:
        st.warning("⚠️ VNA não encontrado. Carregue o histórico na aba **Histórico VNA**.")
        return

    # ── Alocação ──────────────────────────────────────────────────────────────
    st.markdown("### ⚖️ Alocação da Carteira")
    col1, col2 = st.columns(2)
    with col1:
        peso_imab = st.slider("IMA-B 5 (%)", 0, 100,
                              value=int(st.session_state.get("peso_imab5", 50)),
                              step=5, key="cart_imab")
        st.session_state["peso_imab5"] = float(peso_imab)
    with col2:
        peso_cdi = 100 - peso_imab
        st.session_state["peso_cdi"] = float(peso_cdi)
        st.metric("CDI (%)", f"{peso_cdi}%", delta=f"IMA-B 5: {peso_imab}%", delta_color="off")

    _render_pizza(peso_imab, peso_cdi)

    st.markdown(f"""
    <div class="info-box" style="display:flex;gap:32px;flex-wrap:wrap;">
        <span>🟢 <b>Fechamento:</b> {v1:+.2f} p.p.</span>
        <span>🟡 <b>Estabilidade:</b> {v2:+.2f} p.p.</span>
        <span>🔴 <b>Abertura:</b> {v3:+.2f} p.p.</span>
        <span style="color:#95A5A6;font-size:0.8rem;">← definidos na aba Cenários Principais</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Cálculo ───────────────────────────────────────────────────────────────
    ipca_monthly   = build_ipca_monthly_map(ipca_list_to_df(ipca_list), data_inicio, data_fim)
    selic_reunioes = selic_list_to_reunioes(selic_list)

    with st.spinner("Calculando..."):
        df_proj = project_vna_daily(data_inicio, data_fim, vna_ini, ipca_monthly, holidays)

    if df_proj.empty:
        st.error("Erro ao projetar VNA.")
        return

    vna_fim  = float(df_proj.iloc[-1]["VNA"])
    res_cdi  = calcular_retorno_cdi(data_inicio, data_fim, selic_reunioes, holidays)
    ret_cdi  = res_cdi["retorno_cdi"]
    du_total = count_business_days(data_inicio, data_fim, holidays)

    resultados = []
    for c in cenarios_cfg:
        res_imab = calcular_retorno_imab5(
            data_inicio, data_fim, taxa_real, duration_du,
            vna_ini, vna_fim, c["var"], holidays
        )
        ret_imab = res_imab["retorno_total"]
        ret_cart = (peso_imab / 100) * ret_imab + (peso_cdi / 100) * ret_cdi
        resultados.append({**c, "ret_imab": ret_imab, "ret_cdi": ret_cdi, "ret_cart": ret_cart})

    # ── Resultados ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f"### 📊 Resultados | {data_inicio.strftime('%d/%m/%Y')} → "
        f"{data_fim.strftime('%d/%m/%Y')} | {du_total} DU"
    )

    _render_cards(resultados)
    _render_grafico(resultados)

    st.markdown("### 📋 Tabela Detalhada")
    rows_tab = [
        {
            "Cenário":               r["label"],
            "Δ Taxa (p.p.)":         f"{r['var']:+.2f}",
            "Retorno IMA-B5 (%)":    round(r["ret_imab"] * 100, 4),
            "Retorno CDI (%)":       round(r["ret_cdi"]  * 100, 4),
            "Retorno Carteira (%)":  round(r["ret_cart"] * 100, 4),
            "vs CDI Puro (p.p.)":    round((r["ret_cart"] - r["ret_cdi"])  * 100, 4),
            "vs IMA-B5 Puro (p.p.)": round((r["ret_cart"] - r["ret_imab"]) * 100, 4),
        }
        for r in resultados
    ]
    df_tab = pd.DataFrame(rows_tab)
    st.dataframe(
        df_tab.style.format({
            "Retorno IMA-B5 (%)":    "{:.4f}",
            "Retorno CDI (%)":       "{:.4f}",
            "Retorno Carteira (%)":  "{:.4f}",
            "vs CDI Puro (p.p.)":    "{:+.4f}",
            "vs IMA-B5 Puro (p.p.)": "{:+.4f}",
        }),
        use_container_width=True, hide_index=True,
    )

    st.markdown("---")
    st.markdown("### 🎯 Sensibilidade por Alocação")
    _render_heatmap(data_inicio, data_fim, taxa_real, duration_du,
                    vna_ini, vna_fim, selic_reunioes, holidays,
                    cenarios_cfg, ret_cdi)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_pizza(peso_imab, peso_cdi):
    if peso_imab in (0, 100):
        return
    fig = go.Figure(go.Pie(
        labels=["IMA-B 5", "CDI"], values=[peso_imab, peso_cdi],
        marker_colors=["#1B4F72", "#2E86C1"],
        textinfo="label+percent", hole=0.45,
    ))
    fig.update_layout(height=200, margin=dict(t=10,b=10,l=0,r=0), showlegend=False)
    col, _, _ = st.columns([1, 2, 2])
    with col:
        st.plotly_chart(fig, use_container_width=True)


def _render_cards(resultados):
    cols = st.columns(3)
    for col, r in zip(cols, resultados):
        with col:
            ret  = r["ret_cart"] * 100
            vs   = (r["ret_cart"] - r["ret_cdi"]) * 100
            cor  = "#1E8449" if vs >= 0 else "#C0392B"
            sinal = "+" if vs >= 0 else ""
            st.markdown(f"""
            <div style="background:white;border-radius:12px;padding:18px;
                        box-shadow:0 2px 10px rgba(0,0,0,0.08);
                        border-top:5px solid {r['cor']};text-align:center;">
                <div style="font-size:0.78rem;color:#7F8C8D;font-weight:600;margin-bottom:6px;">
                    {r['label']}<br><span style="font-weight:400;">{r['var']:+.2f} p.p.</span>
                </div>
                <div style="font-size:1.6rem;font-weight:700;color:#1B4F72;">{ret:.4f}%</div>
                <div style="font-size:0.75rem;color:{cor};margin-top:4px;font-weight:600;">
                    {sinal}{vs:.4f} p.p. vs CDI
                </div>
                <div style="font-size:0.7rem;color:#95A5A6;margin-top:4px;">
                    IMA-B5: {r['ret_imab']*100:.2f}% | CDI: {r['ret_cdi']*100:.2f}%
                </div>
            </div>
            """, unsafe_allow_html=True)


def _render_grafico(resultados):
    labels   = [r["label"] for r in resultados]
    ret_imab = [r["ret_imab"] * 100 for r in resultados]
    ret_cdi  = [r["ret_cdi"]  * 100 for r in resultados]
    ret_cart = [r["ret_cart"] * 100 for r in resultados]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="IMA-B 5", x=labels, y=ret_imab,
        marker_color=["#1E8449","#D4AC0D","#C0392B"],
        text=[f"{v:.2f}%" for v in ret_imab], textposition="outside", opacity=0.7,
    ))
    fig.add_trace(go.Bar(
        name="CDI", x=labels, y=ret_cdi,
        marker_color="#2E86C1",
        text=[f"{v:.2f}%" for v in ret_cdi], textposition="outside", opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        name="Carteira", x=labels, y=ret_cart,
        mode="markers+text", marker=dict(size=14, color="#E67E22", symbol="diamond"),
        text=[f"{v:.2f}%" for v in ret_cart], textposition="top center",
    ))
    fig.update_layout(
        barmode="group", title="Retorno por Cenário (%)", height=420,
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Arial", size=12),
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=60,b=20), yaxis=dict(ticksuffix="%"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_heatmap(data_inicio, data_fim, taxa_real, duration_du,
                    vna_ini, vna_fim, selic_reunioes, holidays,
                    cenarios_cfg, ret_cdi_val):
    pesos = list(range(0, 105, 10))
    ret_imab_map = {}
    for c in cenarios_cfg:
        res = calcular_retorno_imab5(
            data_inicio, data_fim, taxa_real, duration_du,
            vna_ini, vna_fim, c["var"], holidays
        )
        ret_imab_map[c["var"]] = res["retorno_total"] * 100

    ret_cdi = ret_cdi_val * 100
    z = []
    for peso in pesos:
        row = [round((peso/100)*ret_imab_map[c["var"]] + ((100-peso)/100)*ret_cdi, 4)
               for c in cenarios_cfg]
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[c["label"] for c in cenarios_cfg],
        y=[f"{p}% IMA-B5" for p in pesos],
        colorscale="RdYlGn",
        text=[[f"{v:.2f}%" for v in row] for row in z],
        texttemplate="%{text}",
        colorbar=dict(title="Retorno (%)"),
    ))
    fig.update_layout(
        title="Retorno da Carteira (%) — Alocação × Cenário",
        height=480, font=dict(family="Arial", size=11),
        margin=dict(t=60,b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Verde = maior retorno | Vermelho = menor retorno")
