"""
Página Mês a Mês — retorno mensal IMA-B 5 vs CDI, somente carrego.
VNA calculado via lookup na tabela: VNA(fim_mês) / VNA(início_mês) - 1
"""
import sys, os
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.session_state import init_session_state, get_selic_cenario, selic_list_to_reunioes
from utils.business_days import load_holidays, count_business_days, business_days_range
from utils.vna import (
    load_vna_historico,
    get_vna_exact_or_nearest,
    calcular_retorno_imab5,
    calcular_retorno_cdi,
    project_vna_daily,
    build_ipca_monthly_map,
    get_vna_at_date,
)
from utils.session_state import get_ipca_cenario, ipca_list_to_df


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">📅 Retorno Mês a Mês — Carrego Puro</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">Comparativo mensal sem abertura/fechamento de curva. '
        'VNA calculado via tabela ANBIMA (VNA fim / VNA início − 1). '
        'Objetivo: avaliar qual alternativa é mais vantajosa pelo carrego.</div>',
        unsafe_allow_html=True
    )

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real = st.session_state.get("taxa_real_aa", 7.75)
    duration_du = st.session_state.get("duration_du", 496)

    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))
    if not selic_list:
        st.warning("⚠️ Carregue Selic na aba **Parâmetros**.")
        return
    selic_reunioes = selic_list_to_reunioes(selic_list)

    # Constrói tabela VNA completa (histórico + projeção)
    df_vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))
    if not df_vna_hist.empty:
        df_vna_hist = df_vna_hist.copy()
        df_vna_hist["Data"] = pd.to_datetime(df_vna_hist["Data"]).dt.date

    # Projeta VNA para datas futuras se necessário
    df_vna_proj = _build_vna_table(df_vna_hist, data_inicio, data_fim, holidays)

    # Monta períodos mensais
    periodos = _build_monthly_periods(data_inicio, data_fim, holidays)
    if not periodos:
        st.info("Período muito curto para análise mensal.")
        return

    # Calcula retornos
    rows = []
    idx_imab = 100.0
    idx_cdi = 100.0

    for ini, fim in periodos:
        du = count_business_days(ini, fim, holidays)

        # VNA lookup: pega VNA exato (ou mais próximo) no início e fim do período
        vna_ini = _lookup_vna(ini, df_vna_hist, df_vna_proj)
        vna_fim = _lookup_vna(fim, df_vna_hist, df_vna_proj)

        if not vna_ini or not vna_fim or vna_ini <= 0:
            continue

        # IPCA do período = variação do VNA
        ipca_mes = (vna_fim / vna_ini - 1) * 100

        res_imab = calcular_retorno_imab5(
            ini, fim, taxa_real, duration_du,
            vna_ini, vna_fim, 0.0, holidays
        )
        res_cdi = calcular_retorno_cdi(ini, fim, selic_reunioes, holidays)

        idx_imab *= (1 + res_imab["retorno_total"])
        idx_cdi *= (1 + res_cdi["retorno_cdi"])

        rows.append({
            "Período": ini.strftime("%b/%Y"),
            "Início": ini.strftime("%d/%m/%Y"),
            "Fim": fim.strftime("%d/%m/%Y"),
            "DU": du,
            "VNA Início": round(vna_ini, 4),
            "VNA Fim": round(vna_fim, 4),
            "IPCA / Var. VNA (%)": round(ipca_mes, 4),
            "Carrego Real (%)": round(res_imab["carrego_real"] * 100, 4),
            "Retorno IMA-B5 (%)": round(res_imab["retorno_total"] * 100, 4),
            "Retorno CDI (%)": round(res_cdi["retorno_cdi"] * 100, 4),
            "Dif. IMA-CDI (p.p.)": round((res_imab["retorno_total"] - res_cdi["retorno_cdi"]) * 100, 4),
            "Índice IMA-B5": round(idx_imab, 4),
            "Índice CDI": round(idx_cdi, 4),
        })

    if not rows:
        st.warning("Não foi possível calcular. Verifique se o VNA histórico está carregado.")
        return

    df = pd.DataFrame(rows)

    # Totais
    ret_imab_total = (idx_imab / 100 - 1) * 100
    ret_cdi_total = (idx_cdi / 100 - 1) * 100
    dif_total = ret_imab_total - ret_cdi_total

    st.markdown("### 📊 Resumo do Período")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Retorno Total IMA-B5", f"{ret_imab_total:.4f}%")
    m2.metric("Retorno Total CDI", f"{ret_cdi_total:.4f}%")
    m3.metric("Diferença Total", f"{dif_total:+.4f} p.p.")
    m4.metric("Melhor Carrego", "IMA-B 5 🏆" if dif_total >= 0 else "CDI 🏆")

    # Tabela
    st.markdown("### 📋 Retorno Mensal Detalhado")
    def highlight(row):
        d = row["Dif. IMA-CDI (p.p.)"]
        c = "#EAFAF1" if d > 0 else ("#FDEDEC" if d < 0 else "")
        return [f"background-color: {c}"] * len(row)

    cols_fmt = {
        "IPCA / Var. VNA (%)": "{:.4f}", "Carrego Real (%)": "{:.4f}",
        "Retorno IMA-B5 (%)": "{:.4f}", "Retorno CDI (%)": "{:.4f}",
        "Dif. IMA-CDI (p.p.)": "{:+.4f}", "VNA Início": "{:.4f}", "VNA Fim": "{:.4f}",
        "Índice IMA-B5": "{:.4f}", "Índice CDI": "{:.4f}",
    }
    st.dataframe(
        df.style.apply(highlight, axis=1).format(cols_fmt),
        use_container_width=True, hide_index=True
    )

    # Gráficos
    st.markdown("### 📈 Visualizações")
    t1, t2, t3 = st.tabs(["Barras Mensais", "Acumulado", "Diferença"])
    with t1: _plot_barras(df)
    with t2: _plot_acumulado(df)
    with t3: _plot_diferenca(df)

    with st.expander("📉 VNA e IPCA Mensal"):
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["Período"], y=df["IPCA / Var. VNA (%)"],
            marker_color=["#E74C3C" if v > 0.5 else "#2E86C1" for v in df["IPCA / Var. VNA (%)"]],
            text=[f"{v:.2f}%" for v in df["IPCA / Var. VNA (%)"]],
            textposition="outside",
        ))
        fig.update_layout(title="Variação VNA Mensal (%)", height=300,
                         plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)


def _build_vna_table(df_hist: pd.DataFrame, data_inicio: date, data_fim: date, holidays: set) -> pd.DataFrame:
    """Combina VNA histórico com projeção para o período completo."""
    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    if not ipca_list or df_hist.empty:
        return pd.DataFrame(columns=["Data", "VNA"])

    ultima_hist = df_hist["Data"].max() if not df_hist.empty else data_inicio
    if ultima_hist >= data_fim:
        return pd.DataFrame(columns=["Data", "VNA"])

    ipca_df = ipca_list_to_df(ipca_list)
    ipca_monthly = build_ipca_monthly_map(ipca_df, ultima_hist, data_fim)
    vna_ponto = get_vna_at_date(ultima_hist, df_hist)
    if not vna_ponto:
        return pd.DataFrame(columns=["Data", "VNA"])

    df_proj = project_vna_daily(ultima_hist, data_fim, vna_ponto, ipca_monthly, holidays)
    if not df_proj.empty:
        df_proj["Data"] = pd.to_datetime(df_proj["Data"]).dt.date
    return df_proj


def _lookup_vna(target: date, df_hist: pd.DataFrame, df_proj: pd.DataFrame) -> float | None:
    """Busca VNA: prioriza histórico ANBIMA, depois projetado."""
    if not df_hist.empty:
        v = get_vna_exact_or_nearest(target, df_hist)
        if v:
            return v
    if not df_proj.empty:
        v = get_vna_exact_or_nearest(target, df_proj)
        if v:
            return v
    return None


def _build_monthly_periods(inicio: date, fim: date, holidays: set) -> list:
    """Cria lista de (início, fim) para cada mês no intervalo."""
    def is_du(d):
        return d.weekday() < 5 and d not in holidays

    periods = []
    cur = inicio
    while cur < fim:
        if cur.month == 12:
            last = date(cur.year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(cur.year, cur.month + 1, 1) - timedelta(days=1)
        fim_per = min(last, fim)
        while not is_du(fim_per) and fim_per > cur:
            fim_per -= timedelta(days=1)
        if fim_per > cur:
            periods.append((cur, fim_per))
        if cur.month == 12:
            nxt = date(cur.year + 1, 1, 1)
        else:
            nxt = date(cur.year, cur.month + 1, 1)
        while not is_du(nxt) and nxt <= fim:
            nxt += timedelta(days=1)
        if nxt >= fim:
            break
        cur = nxt
    return periods


def _plot_barras(df):
    fig = go.Figure()
    fig.add_trace(go.Bar(name="IMA-B 5", x=df["Período"], y=df["Retorno IMA-B5 (%)"],
                         marker_color="#1B4F72",
                         text=[f"{v:.2f}%" for v in df["Retorno IMA-B5 (%)"]],
                         textposition="outside"))
    fig.add_trace(go.Bar(name="CDI", x=df["Período"], y=df["Retorno CDI (%)"],
                         marker_color="#2E86C1",
                         text=[f"{v:.2f}%" for v in df["Retorno CDI (%)"]],
                         textposition="outside"))
    fig.update_layout(barmode="group", title="Retorno Mensal (%)", height=400,
                     plot_bgcolor="white", paper_bgcolor="white",
                     legend=dict(orientation="h", y=1.1),
                     yaxis=dict(ticksuffix="%"), margin=dict(t=60, b=20))
    st.plotly_chart(fig, use_container_width=True)


def _plot_acumulado(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(name="IMA-B 5", x=df["Período"], y=df["Índice IMA-B5"],
                             mode="lines+markers", line=dict(color="#1B4F72", width=2.5)))
    fig.add_trace(go.Scatter(name="CDI", x=df["Período"], y=df["Índice CDI"],
                             mode="lines+markers", line=dict(color="#2E86C1", width=2.5, dash="dash")))
    fig.update_layout(title="Número Índice Acumulado (base 100)", height=400,
                     plot_bgcolor="white", paper_bgcolor="white",
                     legend=dict(orientation="h", y=1.1), margin=dict(t=60, b=20))
    st.plotly_chart(fig, use_container_width=True)


def _plot_diferenca(df):
    cores = ["#1E8449" if v >= 0 else "#C0392B" for v in df["Dif. IMA-CDI (p.p.)"]]
    fig = go.Figure(go.Bar(x=df["Período"], y=df["Dif. IMA-CDI (p.p.)"],
                           marker_color=cores,
                           text=[f"{v:+.2f}" for v in df["Dif. IMA-CDI (p.p.)"]],
                           textposition="outside"))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Diferença: IMA-B5 − CDI (p.p.)", height=350,
                     plot_bgcolor="white", paper_bgcolor="white",
                     yaxis=dict(ticksuffix=" p.p."), margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)
