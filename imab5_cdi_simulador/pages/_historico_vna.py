"""
Página Histórico VNA — visualização, upload e projeção futura.
"""
import sys, os
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st
from utils.persistence import save_vna
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.session_state import init_session_state, get_ipca_cenario, ipca_list_to_df
from utils.business_days import load_holidays
from utils.vna import (
    load_vna_historico,
    build_ipca_monthly_map,
    project_vna_daily,
    get_vna_at_date,
)


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">📈 Histórico e Projeção do VNA</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">'
        'O VNA é atualizado pelo IPCA conforme metodologia ANBIMA. '
        'Faça upload do arquivo ANBIMA para atualizar os valores efetivos. '
        'Os valores projetados usam o IPCA do cenário ativo.'
        '</div>', unsafe_allow_html=True
    )

    # ── Upload ─────────────────────────────────────────────────────────────────
    st.markdown("### 📥 Atualização de Dados ANBIMA")
    col_up, col_info = st.columns([2, 3])
    with col_up:
        uploaded = st.file_uploader(
            "Arquivo VNA ANBIMA (xlsx)",
            type=["xlsx"],
            help="Baixe o arquivo 'VNA ANBIMA — Dados históricos.xlsx' em anbima.com.br",
            key="vna_uploader"
        )
    with col_info:
        st.markdown("""
        <div class="info-box">
        <b>Como obter:</b><br>
        1. Acesse <code>anbima.com.br</code><br>
        2. Mercados → Títulos Públicos → VNA<br>
        3. Baixe o histórico NTN-B e faça upload aqui
        </div>
        """, unsafe_allow_html=True)

    if uploaded is not None:
        with st.spinner("Carregando VNA..."):
            df_vna = load_vna_historico(uploaded)
        if not df_vna.empty:
            st.session_state["vna_historico"] = df_vna
            save_vna(df_vna)  # persiste no browser
            ultimo = df_vna.iloc[-1]
            st.success(f"✅ {len(df_vna)} registros carregados | Último: {ultimo['Data']} = {ultimo['VNA']:.6f}")
        else:
            st.error("Erro ao ler o arquivo.")
    else:
        if st.session_state.get("vna_historico", pd.DataFrame()).empty:
            df_vna = load_vna_historico(None)
            if not df_vna.empty:
                st.session_state["vna_historico"] = df_vna

    df_vna = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))
    if df_vna.empty:
        st.warning("Nenhum dado VNA disponível.")
        return

    df_vna = df_vna.copy()
    df_vna["Data"] = pd.to_datetime(df_vna["Data"]).dt.date

    # ── Parâmetros de projeção ─────────────────────────────────────────────────
    st.markdown("### 📊 VNA Histórico + Projeção")
    col1, col2, col3 = st.columns(3)
    with col1:
        data_proj_fim = st.date_input(
            "Fim da Projeção",
            value=date(date.today().year + 2, 12, 31),
            format="DD/MM/YYYY", key="vna_proj_fim"
        )
    with col2:
        meses_hist = st.slider("Histórico (meses)", 3, 36, 12, key="vna_hist_meses")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        mostrar_proj = st.checkbox("Mostrar projeção", value=True, key="vna_show_proj")

    # Projeção
    df_vna_proj = pd.DataFrame(columns=["Data", "VNA"])
    data_proj_ini = df_vna["Data"].max()

    if mostrar_proj:
        ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
        if not ipca_list:
            st.warning("⚠️ Carregue IPCA na aba Parâmetros.")
        else:
            ipca_df = ipca_list_to_df(ipca_list)
            # Ancoragem: usa o dia 15 mais recente para evitar erro de back-cálculo
            from datetime import timedelta as _td
            anchor_date = data_proj_ini
            for d_try in [data_proj_ini.replace(day=15),
                          (data_proj_ini.replace(day=1) - _td(days=1)).replace(day=15)]:
                sub = df_vna[df_vna["Data"] == d_try]
                if not sub.empty and d_try <= data_proj_ini:
                    anchor_date = d_try
                    break
            ipca_monthly = build_ipca_monthly_map(ipca_df, anchor_date, data_proj_fim)
            vna_ponto = get_vna_at_date(anchor_date, df_vna)
            if vna_ponto:
                with st.spinner("Projetando VNA..."):
                    df_vna_proj = project_vna_daily(
                        anchor_date, data_proj_fim, vna_ponto, ipca_monthly, holidays
                    )
                if not df_vna_proj.empty:
                    df_vna_proj["Data"] = pd.to_datetime(df_vna_proj["Data"]).dt.date

    # ── Gráfico ────────────────────────────────────────────────────────────────
    data_corte = date.today() - timedelta(days=meses_hist * 30)
    df_hist_plot = df_vna[df_vna["Data"] >= data_corte].copy()

    fig = go.Figure()

    df_f = df_hist_plot[df_hist_plot.get("Ref", pd.Series(dtype=str)) == "F"] if "Ref" in df_hist_plot.columns else df_hist_plot
    if not df_f.empty:
        fig.add_trace(go.Scatter(
            name="VNA Efetivo (ANBIMA)",
            x=df_f["Data"].astype(str), y=df_f["VNA"],
            mode="lines", line=dict(color="#1B4F72", width=2),
        ))

    if "Ref" in df_hist_plot.columns:
        df_p = df_hist_plot[df_hist_plot["Ref"] == "P"]
        if not df_p.empty:
            fig.add_trace(go.Scatter(
                name="VNA Provisório",
                x=df_p["Data"].astype(str), y=df_p["VNA"],
                mode="lines", line=dict(color="#5D6D7E", width=1.5, dash="dot"),
            ))

    if not df_vna_proj.empty:
        fig.add_trace(go.Scatter(
            name="VNA Projetado",
            x=df_vna_proj["Data"].astype(str), y=df_vna_proj["VNA"],
            mode="lines", line=dict(color="#E74C3C", width=2, dash="dash"),
        ))

    # Linha "hoje" como shape (evita bug do add_vline com datas)
    hoje_str = date.today().isoformat()
    fig.add_shape(
        type="line",
        x0=hoje_str, x1=hoje_str,
        y0=0, y1=1,
        xref="x", yref="paper",
        line=dict(color="#95A5A6", dash="dash", width=1),
    )
    fig.add_annotation(
        x=hoje_str, y=1, xref="x", yref="paper",
        text="Hoje", showarrow=False,
        font=dict(size=10, color="#95A5A6"),
        xanchor="left", yanchor="top",
    )

    fig.update_layout(
        title="VNA NTN-B (Histórico + Projeção)",
        xaxis_title="Data", yaxis_title="VNA (R$)",
        height=480, plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Arial", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Tabelas ────────────────────────────────────────────────────────────────
    tab_hist, tab_proj = st.tabs(["📋 Histórico Recente", "🔮 Projeção Futura"])

    with tab_hist:
        df_show = df_vna.sort_values("Data", ascending=False).head(60).copy()
        df_show["Data"] = pd.to_datetime(df_show["Data"]).dt.strftime("%d/%m/%Y")
        df_show["VNA"] = df_show["VNA"].round(6)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tab_proj:
        if not df_vna_proj.empty:
            df_ps = df_vna_proj.copy()
            df_ps["Data"] = pd.to_datetime(df_ps["Data"]).dt.strftime("%d/%m/%Y")
            df_ps["VNA"] = df_ps["VNA"].round(6)
            df_ps["Var. Diária (%)"] = (df_ps["VNA"].pct_change() * 100).round(6)
            st.dataframe(df_ps, use_container_width=True, hide_index=True)
            csv = df_ps.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Baixar CSV", data=csv,
                               file_name=f"vna_projetado_{data_proj_fim}.csv", mime="text/csv")

    # ── Estatísticas ───────────────────────────────────────────────────────────
    with st.expander("📊 Estatísticas"):
        vna_atual = float(df_vna.sort_values("Data").iloc[-1]["VNA"])
        df_ano = df_vna[pd.to_datetime(df_vna["Data"]).dt.year == date.today().year]
        vna_ini_ano = float(df_ano.sort_values("Data").iloc[0]["VNA"]) if not df_ano.empty else None
        ret_ytd = (vna_atual / vna_ini_ano - 1) * 100 if vna_ini_ano else None
        ultimo = df_vna.sort_values("Data").iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VNA Atual", f"R$ {vna_atual:.4f}")
        c2.metric("VNA Início do Ano", f"R$ {vna_ini_ano:.4f}" if vna_ini_ano else "N/D")
        c3.metric("IPCA Acumulado (ano)", f"{ret_ytd:.4f}%" if ret_ytd else "N/D")
        ref = ultimo.get("Ref", "F")
        c4.metric("Status", "✅ Fechado" if ref == "F" else "⏳ Provisório")
