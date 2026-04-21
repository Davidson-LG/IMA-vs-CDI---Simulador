"""
Página Histórico VNA — visualização, upload de dados ANBIMA e projeção futura.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import io

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
        'O VNA (Valor Nominal Atualizado) é atualizado pelo IPCA conforme metodologia ANBIMA. '
        'Faça upload do arquivo ANBIMA para atualizar os valores efetivos. '
        'Os valores projetados usam o IPCA do cenário ativo.'
        '</div>',
        unsafe_allow_html=True
    )

    # ── Upload do arquivo VNA ──────────────────────────────────────────────────
    st.markdown("### 📥 Atualização de Dados ANBIMA")
    col_up, col_info = st.columns([2, 3])

    with col_up:
        uploaded = st.file_uploader(
            "Arquivo VNA ANBIMA (xlsx)",
            type=["xlsx"],
            help="Faça upload do arquivo 'VNA ANBIMA — Dados históricos.xlsx' baixado do site da ANBIMA.",
            key="vna_uploader"
        )

    with col_info:
        st.markdown("""
        <div class="info-box">
        <b>Como obter o arquivo:</b><br>
        1. Acesse <code>www.anbima.com.br</code><br>
        2. Mercados → Títulos Públicos → VNA<br>
        3. Baixe o arquivo histórico NTN-B<br>
        4. Faça upload aqui para atualizar os dados
        </div>
        """, unsafe_allow_html=True)

    # Carrega VNA
    if uploaded is not None:
        with st.spinner("Carregando VNA do arquivo..."):
            df_vna = load_vna_historico(uploaded)
        if not df_vna.empty:
            st.session_state["vna_historico"] = df_vna
            st.success(f"✅ VNA carregado: {len(df_vna)} registros | Último: {df_vna.iloc[-1]['Data']} = {df_vna.iloc[-1]['VNA']:.6f}")
        else:
            st.error("Erro ao ler o arquivo. Verifique se é o arquivo ANBIMA correto.")
    else:
        # Carrega do arquivo padrão do projeto
        if st.session_state.get("vna_historico", pd.DataFrame()).empty:
            with st.spinner("Carregando VNA padrão..."):
                df_vna = load_vna_historico(None)
            if not df_vna.empty:
                st.session_state["vna_historico"] = df_vna

    df_vna = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))

    if df_vna.empty:
        st.warning("Nenhum dado VNA disponível.")
        return

    df_vna["Data"] = pd.to_datetime(df_vna["Data"]).dt.date

    # ── Projeção futura ────────────────────────────────────────────────────────
    st.markdown("### 📊 VNA Histórico + Projeção")

    # Parâmetros de projeção
    col1, col2, col3 = st.columns(3)
    with col1:
        data_proj_ini = st.date_input(
            "Início da Projeção",
            value=df_vna["Data"].max(),
            format="DD/MM/YYYY",
            key="vna_proj_ini"
        )
    with col2:
        data_proj_fim = st.date_input(
            "Fim da Projeção",
            value=date(date.today().year + 2, 12, 31),
            format="DD/MM/YYYY",
            key="vna_proj_fim"
        )
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        mostrar_historico_dias = st.slider(
            "Histórico (meses atrás)",
            min_value=3, max_value=36, value=12, step=1,
            key="vna_hist_meses"
        )

    # IPCA para projeção
    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    if not ipca_list:
        st.warning("⚠️ Carregue IPCA na aba Parâmetros para ver a projeção.")
        df_vna_proj = pd.DataFrame(columns=["Data", "VNA"])
    else:
        ipca_df = ipca_list_to_df(ipca_list)
        ipca_monthly = build_ipca_monthly_map(ipca_df, data_proj_ini, data_proj_fim)
        vna_ponto_partida = get_vna_at_date(data_proj_ini, df_vna)

        if vna_ponto_partida is None:
            st.error("VNA não encontrado para a data de início da projeção.")
            df_vna_proj = pd.DataFrame(columns=["Data", "VNA"])
        else:
            with st.spinner("Projetando VNA..."):
                df_vna_proj = project_vna_daily(
                    data_proj_ini, data_proj_fim, vna_ponto_partida, ipca_monthly, holidays
                )
            df_vna_proj["Data"] = pd.to_datetime(df_vna_proj["Data"]).dt.date

    # ── Gráfico combinado ──────────────────────────────────────────────────────
    data_corte = date.today() - timedelta(days=mostrar_historico_dias * 30)
    df_hist_plot = df_vna[df_vna["Data"] >= data_corte].copy()

    fig = go.Figure()

    # Histórico — valores fechados (F)
    df_f = df_hist_plot[df_hist_plot["Ref"] == "F"] if "Ref" in df_hist_plot.columns else df_hist_plot
    if not df_f.empty:
        fig.add_trace(go.Scatter(
            name="VNA Efetivo (ANBIMA)",
            x=df_f["Data"], y=df_f["VNA"],
            mode="lines",
            line=dict(color="#1B4F72", width=2),
        ))

    # Histórico — valores provisórios (P) recentes
    df_p = df_hist_plot[df_hist_plot["Ref"] == "P"] if "Ref" in df_hist_plot.columns else pd.DataFrame()
    if not df_p.empty:
        fig.add_trace(go.Scatter(
            name="VNA Provisório",
            x=df_p["Data"], y=df_p["VNA"],
            mode="lines",
            line=dict(color="#5D6D7E", width=1.5, dash="dot"),
        ))

    # Projeção
    if not df_vna_proj.empty:
        fig.add_trace(go.Scatter(
            name="VNA Projetado (Focus)",
            x=df_vna_proj["Data"], y=df_vna_proj["VNA"],
            mode="lines",
            line=dict(color="#E74C3C", width=2, dash="dash"),
        ))

    # Linha vertical "hoje"
    fig.add_vline(
        x=date.today().isoformat(),
        line_dash="dash", line_color="#95A5A6",
        annotation_text="Hoje",
        annotation_position="top right",
    )

    fig.update_layout(
        title="VNA NTN-B (Histórico + Projeção)",
        xaxis_title="Data",
        yaxis_title="VNA (R$)",
        height=480,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Tabelas ────────────────────────────────────────────────────────────────
    tab_hist, tab_proj = st.tabs(["📋 Histórico Recente", "🔮 Projeção Futura"])

    with tab_hist:
        st.markdown("**Últimos 60 registros históricos**")
        df_show = df_vna.sort_values("Data", ascending=False).head(60).copy()
        df_show["Data"] = pd.to_datetime(df_show["Data"]).dt.strftime("%d/%m/%Y")
        df_show["VNA"] = df_show["VNA"].round(6)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tab_proj:
        if not df_vna_proj.empty:
            st.markdown(f"**VNA Projetado: {data_proj_ini.strftime('%d/%m/%Y')} → {data_proj_fim.strftime('%d/%m/%Y')}**")
            df_proj_show = df_vna_proj.copy()
            df_proj_show["Data"] = pd.to_datetime(df_proj_show["Data"]).dt.strftime("%d/%m/%Y")
            df_proj_show["VNA"] = df_proj_show["VNA"].round(6)
            df_proj_show["Var. Diária (%)"] = df_proj_show["VNA"].pct_change() * 100
            df_proj_show["Var. Diária (%)"] = df_proj_show["Var. Diária (%)"].round(6)
            st.dataframe(df_proj_show, use_container_width=True, hide_index=True)

            # Download
            csv = df_proj_show.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Baixar Projeção VNA (CSV)",
                data=csv,
                file_name=f"vna_projetado_{data_proj_ini}_{data_proj_fim}.csv",
                mime="text/csv",
            )
        else:
            st.info("Sem projeção disponível.")

    # ── Estatísticas ───────────────────────────────────────────────────────────
    with st.expander("📊 Estatísticas VNA"):
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        vna_atual = float(df_vna.sort_values("Data").iloc[-1]["VNA"])
        vna_inicio_ano = _get_vna_inicio_ano(df_vna)
        ret_ytd = (vna_atual / vna_inicio_ano - 1) * 100 if vna_inicio_ano else None

        with col_s1:
            st.metric("VNA Atual", f"R$ {vna_atual:.4f}")
        with col_s2:
            st.metric("VNA Início do Ano", f"R$ {vna_inicio_ano:.4f}" if vna_inicio_ano else "N/D")
        with col_s3:
            st.metric("IPCA Acumulado (ano)", f"{ret_ytd:.4f}%" if ret_ytd else "N/D")
        with col_s4:
            ultimo_reg = df_vna.sort_values("Data").iloc[-1]
            ref_label = "✅ Fechado" if ultimo_reg.get("Ref") == "F" else "⏳ Provisório"
            st.metric("Status Último VNA", ref_label)


def _get_vna_inicio_ano(df: pd.DataFrame) -> float | None:
    ano_atual = date.today().year
    df_ano = df[pd.to_datetime(df["Data"]).dt.year == ano_atual].sort_values("Data")
    if df_ano.empty:
        return None
    return float(df_ano.iloc[0]["VNA"])
