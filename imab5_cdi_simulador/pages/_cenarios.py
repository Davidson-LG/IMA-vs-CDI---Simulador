"""
Página Principal — Três Cenários de Retorno (IMA-B 5 vs CDI)
"""
import sys, os
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.session_state import init_session_state, get_ipca_cenario, get_selic_cenario, ipca_list_to_df, selic_list_to_reunioes
from utils.business_days import load_holidays, count_business_days, business_days_range
from utils.vna import (
    load_vna_historico,
    build_ipca_monthly_map,
    project_vna_daily,
    calcular_retorno_imab5,
    calcular_retorno_cdi,
    get_vna_at_date,
)


def render():
    init_session_state()
    holidays = load_holidays()
    vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real = st.session_state.get("taxa_real_aa", 7.75)
    duration_du = st.session_state.get("duration_du", 496)

    st.markdown('<div class="section-title">🏠 Cenários Principais — IMA-B 5 vs CDI</div>', unsafe_allow_html=True)

    # Parâmetros rápidos
    with st.expander("📐 Ajuste Rápido de Parâmetros", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            taxa_real = st.number_input("Taxa Real IMA-B 5 (%a.a.)", 0.0, 30.0,
                                        value=float(taxa_real), step=0.01, format="%.4f", key="qp_taxa")
            st.session_state["taxa_real_aa"] = taxa_real
        with c2:
            duration_du = st.number_input("Duration (DU)", 1, 2000,
                                          value=int(duration_du), step=1, key="qp_dur")
            st.session_state["duration_du"] = duration_du
            st.caption(f"≈ {duration_du/252:.2f} anos")
        with c3:
            data_inicio = st.date_input("Data Início", value=data_inicio,
                                        format="DD/MM/YYYY", key="qp_ini")
            st.session_state["data_inicio"] = data_inicio
        with c4:
            data_fim = st.date_input("Data Fim", value=data_fim,
                                     format="DD/MM/YYYY", key="qp_fim")
            st.session_state["data_fim"] = data_fim

    if data_fim <= data_inicio:
        st.error("⚠️ Data final deve ser posterior à data de início.")
        return

    # Variações dos cenários
    st.markdown("### ⚙️ Variação de Curva por Cenário")
    st.markdown('<div class="info-box">Negativo = fechamento (ganho de marcação). Positivo = abertura (perda).</div>',
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### 🟢 Cenário 1 — Fechamento")
        v1 = st.number_input("Variação (p.p.)", -10.0, 10.0,
                             value=float(st.session_state.get("cenario1_variacao", -0.50)),
                             step=0.05, format="%.2f", key="v1")
        st.session_state["cenario1_variacao"] = v1
    with col2:
        st.markdown("#### 🟡 Cenário 2 — Estabilidade")
        v2 = st.number_input("Variação (p.p.)", -10.0, 10.0,
                             value=float(st.session_state.get("cenario2_variacao", 0.0)),
                             step=0.05, format="%.2f", key="v2")
        st.session_state["cenario2_variacao"] = v2
    with col3:
        st.markdown("#### 🔴 Cenário 3 — Abertura")
        v3 = st.number_input("Variação (p.p.)", -10.0, 10.0,
                             value=float(st.session_state.get("cenario3_variacao", 0.50)),
                             step=0.05, format="%.2f", key="v3")
        st.session_state["cenario3_variacao"] = v3

    # Dados
    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))

    if not ipca_list:
        st.warning("⚠️ Carregue IPCA na aba **Parâmetros**.")
        return
    if not selic_list:
        st.warning("⚠️ Carregue Selic na aba **Parâmetros**.")
        return

    ipca_df = ipca_list_to_df(ipca_list)
    ipca_monthly = build_ipca_monthly_map(ipca_df, data_inicio, data_fim)
    selic_reunioes = selic_list_to_reunioes(selic_list)

    # VNA
    if vna_hist.empty:
        st.warning("⚠️ Carregue o VNA histórico na aba **Histórico VNA**.")
        return

    vna_hist_c = vna_hist.copy()
    vna_hist_c["Data"] = pd.to_datetime(vna_hist_c["Data"]).dt.date
    vna_ini = get_vna_at_date(data_inicio, vna_hist_c)
    if vna_ini is None:
        st.warning("⚠️ VNA não encontrado para a data de início.")
        return

    with st.spinner("Calculando VNA projetado..."):
        df_vna_proj = project_vna_daily(data_inicio, data_fim, vna_ini, ipca_monthly, holidays)

    if df_vna_proj.empty:
        st.error("Erro ao calcular VNA.")
        return

    vna_fim = float(df_vna_proj.iloc[-1]["VNA"])

    # IPCA acumulado = variação do VNA (fim/início - 1)
    ipca_acum = (vna_fim / vna_ini - 1) * 100

    # Calcula três cenários
    cenarios = [
        {"label": "Cenário 1", "sub": "Fechamento de Curva", "var": v1, "cor": "#1E8449", "emoji": "🟢"},
        {"label": "Cenário 2", "sub": "Estabilidade",         "var": v2, "cor": "#D4AC0D", "emoji": "🟡"},
        {"label": "Cenário 3", "sub": "Abertura de Curva",    "var": v3, "cor": "#C0392B", "emoji": "🔴"},
    ]
    resultados = []
    for c in cenarios:
        res_imab = calcular_retorno_imab5(
            data_inicio, data_fim, taxa_real, duration_du,
            vna_ini, vna_fim, c["var"], holidays
        )
        res_cdi = calcular_retorno_cdi(data_inicio, data_fim, selic_reunioes, holidays)
        resultados.append({**c, "imab": res_imab, "cdi": res_cdi})

    # Info bar
    du_total = count_business_days(data_inicio, data_fim, holidays)
    st.markdown("---")
    st.markdown(f"### 📊 Resultados | {data_inicio.strftime('%d/%m/%Y')} → {data_fim.strftime('%d/%m/%Y')}")
    st.markdown(f"""
    <div class="info-box" style="display:flex;gap:40px;flex-wrap:wrap;">
        <span>📅 <b>DU:</b> {du_total}</span>
        <span>📉 <b>VNA Início:</b> R$ {vna_ini:.4f}</span>
        <span>📈 <b>VNA Fim:</b> R$ {vna_fim:.4f}</span>
        <span>🔢 <b>IPCA/VNA Acum.:</b> {ipca_acum:.4f}%</span>
        <span>⏱ <b>Duration:</b> {duration_du/252:.2f} anos</span>
    </div>
    """, unsafe_allow_html=True)

    # Cards
    st.markdown("<br>", unsafe_allow_html=True)
    cols = st.columns(3)
    for col, res in zip(cols, resultados):
        with col:
            _render_card(res)

    # Gráficos
    st.markdown("---")
    st.markdown("### 📈 Comparativo Visual")
    _render_graficos(resultados)

    with st.expander("📋 Tabela Detalhada", expanded=True):
        _render_tabela(resultados)


def _render_card(res):
    imab = res["imab"]
    cdi = res["cdi"]
    ret_imab = imab["retorno_total"] * 100
    ret_cdi = cdi["retorno_cdi"] * 100
    dif = ret_imab - ret_cdi
    cor_dif = "#1E8449" if dif >= 0 else "#C0392B"
    sinal = "+" if dif >= 0 else ""
    vencedor = "IMA-B 5" if dif >= 0 else "CDI"
    st.markdown(f"""
    <div style="background:white;border-radius:14px;padding:20px;
                box-shadow:0 2px 12px rgba(0,0,0,0.10);
                border-top:5px solid {res['cor']};margin-bottom:8px;">
        <div style="font-size:1.1rem;font-weight:700;color:{res['cor']};margin-bottom:4px;">
            {res['emoji']} {res['label']}
        </div>
        <div style="font-size:0.85rem;color:#7F8C8D;margin-bottom:14px;">
            {res['sub']} | Δtaxa: {res['var']:+.2f} p.p.
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
            <div style="text-align:center;">
                <div style="font-size:0.75rem;color:#95A5A6;font-weight:600;">IMA-B 5</div>
                <div style="font-size:1.6rem;font-weight:700;color:#1B4F72;">{ret_imab:.4f}%</div>
            </div>
            <div style="text-align:center;align-self:center;">
                <div style="font-size:1.2rem;color:#BDC3C7;">vs</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:0.75rem;color:#95A5A6;font-weight:600;">CDI</div>
                <div style="font-size:1.6rem;font-weight:700;color:#1B4F72;">{ret_cdi:.4f}%</div>
            </div>
        </div>
        <div style="background:#F8F9FA;border-radius:8px;padding:10px;text-align:center;">
            <div style="font-size:0.75rem;color:#7F8C8D;">Diferença (IMA-B5 − CDI)</div>
            <div style="font-size:1.3rem;font-weight:700;color:{cor_dif};">{sinal}{dif:.4f} p.p.</div>
            <div style="font-size:0.75rem;color:{cor_dif};font-weight:600;">✦ {vencedor} mais vantajoso</div>
        </div>
        <div style="margin-top:12px;font-size:0.78rem;color:#7F8C8D;border-top:1px solid #ECF0F1;padding-top:8px;">
            <div>• Carrego IMA-B5: {imab['retorno_carrego']*100:.4f}%</div>
            <div>• Marcação: {imab['impacto_mtm']*100:+.4f}%</div>
            <div>• VNA acum. (IPCA): {imab['ipca_periodo']*100:.4f}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_graficos(resultados):
    labels = [r["label"] for r in resultados]
    ret_imab = [r["imab"]["retorno_total"] * 100 for r in resultados]
    ret_cdi = [r["cdi"]["retorno_cdi"] * 100 for r in resultados]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="IMA-B 5", x=labels, y=ret_imab,
                         marker_color=["#1E8449", "#D4AC0D", "#C0392B"],
                         text=[f"{v:.4f}%" for v in ret_imab], textposition="outside"))
    fig.add_trace(go.Bar(name="CDI", x=labels, y=ret_cdi,
                         marker_color="#2E86C1",
                         text=[f"{v:.4f}%" for v in ret_cdi], textposition="outside", opacity=0.85))
    fig.update_layout(barmode="group", title="Retorno por Cenário (%)", height=420,
                     plot_bgcolor="white", paper_bgcolor="white",
                     font=dict(family="Arial", size=12),
                     legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                     margin=dict(t=60, b=20), yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig, use_container_width=True)

    # Decomposição
    st.markdown("#### Decomposição do Retorno IMA-B 5")
    carrego = [r["imab"]["retorno_carrego"] * 100 for r in resultados]
    mtm = [r["imab"]["impacto_mtm"] * 100 for r in resultados]
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name="Carrego (real + VNA)", x=labels, y=carrego,
                          marker_color="#2E86C1",
                          text=[f"{v:.4f}%" for v in carrego], textposition="inside"))
    fig2.add_trace(go.Bar(name="Marcação a Mercado", x=labels, y=mtm,
                          marker_color=["#1E8449" if v >= 0 else "#C0392B" for v in mtm],
                          text=[f"{v:+.4f}%" for v in mtm], textposition="inside"))
    fig2.update_layout(barmode="stack", height=350, plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=40, b=20),
                      yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig2, use_container_width=True)


def _render_tabela(resultados):
    rows = []
    for res in resultados:
        imab, cdi = res["imab"], res["cdi"]
        rows.append({
            "Cenário": f"{res['emoji']} {res['label']} — {res['sub']}",
            "Δ Taxa (p.p.)": f"{res['var']:+.2f}",
            "VNA Acum. / IPCA (%)": f"{imab['ipca_periodo']*100:.4f}",
            "Carrego IMA-B5 (%)": f"{imab['retorno_carrego']*100:.4f}",
            "Marcação (%)": f"{imab['impacto_mtm']*100:+.4f}",
            "Retorno IMA-B5 (%)": f"{imab['retorno_total']*100:.4f}",
            "Retorno CDI (%)": f"{cdi['retorno_cdi']*100:.4f}",
            "Diferença (p.p.)": f"{(imab['retorno_total']-cdi['retorno_cdi'])*100:+.4f}",
            "Vencedor": "✅ IMA-B 5" if imab["retorno_total"] >= cdi["retorno_cdi"] else "✅ CDI",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
