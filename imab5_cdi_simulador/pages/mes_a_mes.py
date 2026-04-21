"""
Página Mês a Mês — Comparativo mensal IMA-B 5 vs CDI (somente carrego, sem abertura/fechamento)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from utils.session_state import init_session_state, get_ipca_cenario, get_selic_cenario, ipca_list_to_df, selic_list_to_reunioes
from utils.business_days import load_holidays, count_business_days, get_month_end_business_days, next_business_day
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

    st.markdown('<div class="section-title">📅 Retorno Mês a Mês — Carrego Puro</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">Comparativo mensal sem abertura/fechamento de curva. '
        'Objetivo: avaliar qual alternativa é mais vantajosa exclusivamente pelo carrego.</div>',
        unsafe_allow_html=True
    )

    holidays = load_holidays()
    vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real = st.session_state.get("taxa_real_aa", 7.75)
    duration_du = st.session_state.get("duration_du", 496)

    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))

    if not ipca_list or not selic_list:
        st.warning("⚠️ Carregue as projeções de IPCA e Selic na aba **Parâmetros**.")
        return

    ipca_df = ipca_list_to_df(ipca_list)
    ipca_monthly = build_ipca_monthly_map(ipca_df, data_inicio, data_fim)
    selic_reunioes = selic_list_to_reunioes(selic_list)

    vna_ini_global = get_vna_at_date(data_inicio, vna_hist)
    if vna_ini_global is None:
        st.warning("⚠️ VNA não encontrado. Carregue o histórico na aba **Histórico VNA**.")
        return

    # Projeta VNA para todo o período
    with st.spinner("Projetando VNA..."):
        df_vna_proj = project_vna_daily(data_inicio, data_fim, vna_ini_global, ipca_monthly, holidays)

    if df_vna_proj.empty:
        st.error("Erro ao calcular projeção VNA.")
        return

    df_vna_proj["Data"] = pd.to_datetime(df_vna_proj["Data"]).dt.date

    # Montar lista de meses (início e fim de cada mês no período)
    datas_mes = _build_monthly_periods(data_inicio, data_fim, holidays)

    if not datas_mes:
        st.info("Período muito curto para análise mensal.")
        return

    # Calcular retorno mensal
    rows = []
    numero_indice_imab = 100.0
    numero_indice_cdi = 100.0

    for inicio_mes, fim_mes in datas_mes:
        # VNA do início e fim do mês
        vna_ini_mes = _get_vna_from_proj(inicio_mes, df_vna_proj, vna_hist)
        vna_fim_mes = _get_vna_from_proj(fim_mes, df_vna_proj, vna_hist)

        if vna_ini_mes is None or vna_fim_mes is None:
            continue

        du_mes = count_business_days(inicio_mes, fim_mes, holidays)
        ipca_mes = (vna_fim_mes / vna_ini_mes - 1) * 100

        res_imab = calcular_retorno_imab5(
            inicio_mes, fim_mes, taxa_real, duration_du,
            vna_ini_mes, vna_fim_mes, 0.0, holidays
        )
        res_cdi = calcular_retorno_cdi(inicio_mes, fim_mes, selic_reunioes, holidays)

        numero_indice_imab *= (1 + res_imab["retorno_total"])
        numero_indice_cdi *= (1 + res_cdi["retorno_cdi"])

        rows.append({
            "Mês": inicio_mes.strftime("%b/%Y"),
            "Início": inicio_mes.strftime("%d/%m/%Y"),
            "Fim": fim_mes.strftime("%d/%m/%Y"),
            "DU": du_mes,
            "IPCA (%)": round(ipca_mes, 4),
            "Retorno IMA-B5 (%)": round(res_imab["retorno_total"] * 100, 4),
            "Retorno CDI (%)": round(res_cdi["retorno_cdi"] * 100, 4),
            "Dif. (IMA-CDI) p.p.": round((res_imab["retorno_total"] - res_cdi["retorno_cdi"]) * 100, 4),
            "Índice IMA-B5": round(numero_indice_imab, 4),
            "Índice CDI": round(numero_indice_cdi, 4),
        })

    if not rows:
        st.info("Não foi possível calcular retornos mensais para o período selecionado.")
        return

    df_result = pd.DataFrame(rows)

    # ── Totalizador ────────────────────────────────────────────────────────────
    ret_total_imab = (numero_indice_imab / 100 - 1) * 100
    ret_total_cdi = (numero_indice_cdi / 100 - 1) * 100
    dif_total = ret_total_imab - ret_total_cdi

    st.markdown("### 📊 Resumo do Período")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Retorno Total IMA-B5", f"{ret_total_imab:.4f}%")
    with m2:
        st.metric("Retorno Total CDI", f"{ret_total_cdi:.4f}%")
    with m3:
        st.metric("Diferença Total", f"{dif_total:+.4f} p.p.",
                  delta_color="normal" if dif_total >= 0 else "inverse")
    with m4:
        vencedor = "IMA-B 5 🏆" if dif_total >= 0 else "CDI 🏆"
        st.metric("Melhor Carrego", vencedor)

    # ── Tabela ─────────────────────────────────────────────────────────────────
    st.markdown("### 📋 Retorno Mensal Detalhado")

    # Formatação condicional simples via pandas styler
    def highlight_row(row):
        dif = row["Dif. (IMA-CDI) p.p."]
        if dif > 0:
            return ["background-color: #EAFAF1"] * len(row)
        elif dif < 0:
            return ["background-color: #FDEDEC"] * len(row)
        return [""] * len(row)

    styled = df_result.style.apply(highlight_row, axis=1).format({
        "IPCA (%)": "{:.4f}",
        "Retorno IMA-B5 (%)": "{:.4f}",
        "Retorno CDI (%)": "{:.4f}",
        "Dif. (IMA-CDI) p.p.": "{:+.4f}",
        "Índice IMA-B5": "{:.4f}",
        "Índice CDI": "{:.4f}",
    })
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Gráficos ───────────────────────────────────────────────────────────────
    st.markdown("### 📈 Visualizações")

    tab_bar, tab_acum, tab_dif = st.tabs(["Barras Mensais", "Acumulado", "Diferença Mensal"])

    with tab_bar:
        _plot_barras_mensais(df_result)

    with tab_acum:
        _plot_acumulado(df_result)

    with tab_dif:
        _plot_diferenca_mensal(df_result)

    # ── IPCA acumulado ─────────────────────────────────────────────────────────
    with st.expander("📉 IPCA Mensal Projetado"):
        fig_ipca = go.Figure(go.Bar(
            x=df_result["Mês"],
            y=df_result["IPCA (%)"],
            marker_color=["#E74C3C" if v > 0.5 else "#2E86C1" for v in df_result["IPCA (%)"]],
            text=[f"{v:.2f}%" for v in df_result["IPCA (%)"]],
            textposition="outside",
        ))
        fig_ipca.update_layout(
            title="IPCA Mensal Projetado (%)",
            height=300, plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_ipca, use_container_width=True)


def _build_monthly_periods(data_inicio: date, data_fim: date, holidays: set) -> list:
    """
    Cria lista de (início_mês, fim_mês) para cada mês no intervalo.
    O primeiro período começa em data_inicio e vai até o fim do mês.
    O último período vai do início do mês até data_fim.
    """
    periods = []
    current = data_inicio

    while current < data_fim:
        # Fim do mês corrente
        if current.month == 12:
            last_day_month = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day_month = date(current.year, current.month + 1, 1) - timedelta(days=1)

        fim_periodo = min(last_day_month, data_fim)

        # Recua fim_periodo para último DU se não for DU
        while not _is_du(fim_periodo, holidays):
            fim_periodo -= timedelta(days=1)

        if fim_periodo > current:
            periods.append((current, fim_periodo))

        # Próximo período: primeiro DU do próximo mês
        if current.month == 12:
            next_month_start = date(current.year + 1, 1, 1)
        else:
            next_month_start = date(current.year, current.month + 1, 1)

        # Avança para primeiro dia útil do próximo mês
        while not _is_du(next_month_start, holidays) and next_month_start <= data_fim:
            next_month_start += timedelta(days=1)

        if next_month_start >= data_fim:
            break
        current = next_month_start

    return periods


def _is_du(d: date, holidays: set) -> bool:
    return d.weekday() < 5 and d not in holidays


def _get_vna_from_proj(target: date, df_proj: pd.DataFrame, df_hist: pd.DataFrame) -> float | None:
    # Histórico
    if not df_hist.empty:
        df_h = df_hist.copy()
        df_h["Data"] = pd.to_datetime(df_h["Data"]).dt.date
        sub = df_h[df_h["Data"] == target]
        if not sub.empty:
            return float(sub.iloc[-1]["VNA"])

    # Projetado
    sub = df_proj[df_proj["Data"] == target]
    if not sub.empty:
        return float(sub.iloc[-1]["VNA"])

    # Mais próximo anterior
    sub = df_proj[df_proj["Data"] <= target]
    if not sub.empty:
        return float(sub.iloc[-1]["VNA"])

    return None


def _plot_barras_mensais(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="IMA-B 5",
        x=df["Mês"], y=df["Retorno IMA-B5 (%)"],
        marker_color="#1B4F72",
        text=[f"{v:.2f}%" for v in df["Retorno IMA-B5 (%)"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="CDI",
        x=df["Mês"], y=df["Retorno CDI (%)"],
        marker_color="#2E86C1",
        text=[f"{v:.2f}%" for v in df["Retorno CDI (%)"]],
        textposition="outside",
    ))
    fig.update_layout(
        barmode="group", title="Retorno Mensal (%)",
        height=400, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=1.1),
        yaxis=dict(ticksuffix="%"),
        margin=dict(t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def _plot_acumulado(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        name="IMA-B 5", x=df["Mês"], y=df["Índice IMA-B5"],
        mode="lines+markers", line=dict(color="#1B4F72", width=2.5),
        marker=dict(size=7),
    ))
    fig.add_trace(go.Scatter(
        name="CDI", x=df["Mês"], y=df["Índice CDI"],
        mode="lines+markers", line=dict(color="#2E86C1", width=2.5, dash="dash"),
        marker=dict(size=7),
    ))
    fig.update_layout(
        title="Número Índice Acumulado (base 100)",
        height=400, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def _plot_diferenca_mensal(df: pd.DataFrame):
    cores = ["#1E8449" if v >= 0 else "#C0392B" for v in df["Dif. (IMA-CDI) p.p."]]
    fig = go.Figure(go.Bar(
        x=df["Mês"], y=df["Dif. (IMA-CDI) p.p."],
        marker_color=cores,
        text=[f"{v:+.2f}" for v in df["Dif. (IMA-CDI) p.p."]],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="Diferença Mensal: IMA-B5 − CDI (p.p.)",
        height=350, plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(ticksuffix=" p.p."),
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
