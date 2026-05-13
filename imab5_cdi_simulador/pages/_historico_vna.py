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




def _project_with_anbima_cycle(
    df_vna: pd.DataFrame,
    anchor_date,
    vna_anchor: float,
    ipca_monthly: dict,
    data_fim,
    holidays: set,
) -> pd.DataFrame:
    """
    Projeta VNA a partir de anchor_date usando:
    1. Para dias restantes do ciclo atual (até DataMes):
       interpolação proporcional entre VNA(anchor) e VNAAtual usando DU
       VNA(d) = VNA_anchor × (VNAAtual/VNA_anchor)^(DU_anchor→d / DU_anchor→DataMes)
    2. Para ciclos futuros: project_vna_daily com ipca_monthly
    """
    from utils.business_days import business_days_range as _bdr
    rows = []

    # Verifica se o arquivo ANBIMA tem DataMes e VNAAtual
    has_cycle_info = (
        "DataMes" in df_vna.columns and
        "VNAAtual" in df_vna.columns and
        not df_vna[df_vna["Data"] == anchor_date].empty
    )

    cycle_end = None
    vna_cycle_end = None

    if has_cycle_info:
        last_row = df_vna[df_vna["Data"] == anchor_date].iloc[0]
        try:
            cycle_end    = pd.to_datetime(last_row["DataMes"]).date()
            vna_cycle_end = float(last_row["VNAAtual"])
            if cycle_end <= anchor_date or vna_cycle_end <= 0:
                cycle_end = None
        except Exception:
            cycle_end = None

    if cycle_end and vna_cycle_end:
        # Interpola dias restantes do ciclo atual
        dias_ciclo = _bdr(anchor_date, cycle_end, holidays)
        du_total = len(dias_ciclo) - 1  # excl anchor, incl cycle_end
        if du_total > 0:
            for i, d in enumerate(dias_ciclo[1:], 1):  # skip anchor_date
                ratio = i / du_total
                vna_d = vna_anchor * (vna_cycle_end / vna_anchor) ** ratio
                rows.append({"Data": d, "VNA": round(vna_d, 6)})

        # Projeta ciclos futuros a partir de cycle_end
        if cycle_end < data_fim:
            vna_at_end = vna_cycle_end
            df_fut = project_vna_daily(
                cycle_end, data_fim, vna_at_end, ipca_monthly, holidays
            )
            if not df_fut.empty:
                df_fut["Data"] = pd.to_datetime(df_fut["Data"]).dt.date
                # Evita duplicar cycle_end
                df_fut = df_fut[df_fut["Data"] > cycle_end]
                rows.extend(df_fut.to_dict("records"))
    else:
        # Sem DataMes/VNAAtual: usa project_vna_daily diretamente
        df_p = project_vna_daily(anchor_date, data_fim, vna_anchor, ipca_monthly, holidays)
        if not df_p.empty:
            df_p["Data"] = pd.to_datetime(df_p["Data"]).dt.date
            rows.extend(df_p.to_dict("records"))

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Data", "VNA"])

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
            # Ancoragem: usa o último dia disponível no histórico
            # (evita recuar para mês anterior quando o dia 15 do mês atual não existe)
            anchor_date = data_proj_ini
            if not df_vna.empty:
                ultima_hist = df_vna["Data"].max()
                if ultima_hist <= data_proj_ini:
                    anchor_date = ultima_hist
            # Inclui todos os meses do ipca_df no mapa
            ipca_monthly = build_ipca_monthly_map(ipca_df, date(2020,1,1), data_proj_fim)

            # Injeta IPCA dos ciclos ativos a partir do campo 'Índice' do arquivo ANBIMA
            # Necessário para projetar dias antes do dia 15 do mês atual
            if "Índice" in df_vna.columns:
                for _, row in df_vna[df_vna["Data"] <= anchor_date].iterrows():
                    try:
                        idx_val = float(row["Índice"])
                        if idx_val > 0:
                            d = row["Data"]
                            # O Índice do dia d pertence ao ciclo que começa no 15 anterior
                            # Para d entre 01-14 do mês: ciclo = mês anterior
                            # Para d entre 15-31 do mês: ciclo = mês atual
                            if d.day < 15:
                                ciclo_mes = d.month - 1 if d.month > 1 else 12
                                ciclo_ano = d.year if d.month > 1 else d.year - 1
                            else:
                                ciclo_mes = d.month
                                ciclo_ano = d.year
                            key = (ciclo_ano, ciclo_mes)
                            if key not in ipca_monthly or ipca_monthly[key] == 0.0:
                                ipca_monthly[key] = idx_val
                    except Exception:
                        pass

            vna_ponto = get_vna_at_date(anchor_date, df_vna)
            if vna_ponto:
                with st.spinner("Projetando VNA..."):
                    df_vna_proj = _project_with_anbima_cycle(
                        df_vna, anchor_date, vna_ponto,
                        ipca_monthly, data_proj_fim, holidays
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
