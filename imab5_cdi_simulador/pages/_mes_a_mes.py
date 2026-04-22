"""
Página Mês a Mês — retorno mensal IMA-B 5 vs CDI, somente carrego.
Retorno IMA-B5 = (1 + taxa_real_du) × (VNA_fim / VNA_ini) - 1
IPCA / VNA = VNA_fim / VNA_ini - 1
"""
import sys, os
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.session_state import init_session_state, get_selic_cenario, selic_list_to_reunioes, get_ipca_cenario, ipca_list_to_df
from utils.business_days import load_holidays, count_business_days, business_days_range
from utils.vna import (
    load_vna_historico,
    get_vna_exact_or_nearest,
    calcular_retorno_cdi,
    project_vna_daily,
    build_ipca_monthly_map,
    get_vna_at_date,
)


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">📅 Retorno Mês a Mês — Carrego Puro</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">Comparativo mensal sem abertura/fechamento de curva. '
        'Retorno IMA-B5 = (1 + taxa_real_du) × (VNA_fim/VNA_ini) − 1. '
        'IPCA = variação do VNA no período.</div>',
        unsafe_allow_html=True
    )

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real_aa = st.session_state.get("taxa_real_aa", 7.75)

    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))
    if not selic_list:
        st.warning("⚠️ Carregue Selic na aba **Parâmetros**.")
        return
    selic_reunioes = selic_list_to_reunioes(selic_list)

    # Tabela VNA completa (histórico + projeção)
    df_vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data", "VNA", "Ref"]))
    if not df_vna_hist.empty:
        df_vna_hist = df_vna_hist.copy()
        df_vna_hist["Data"] = pd.to_datetime(df_vna_hist["Data"]).dt.date

    df_vna_proj = _build_vna_proj(df_vna_hist, data_inicio, data_fim, holidays)

    # Períodos mensais
    periodos = _build_monthly_periods(data_inicio, data_fim, holidays)
    if not periodos:
        st.info("Período muito curto para análise mensal.")
        return

    rows = []
    idx_imab = 100.0
    idx_cdi = 100.0

    for ini, fim in periodos:
        du = count_business_days(ini, fim, holidays)

        vna_ini = _lookup_vna(ini, df_vna_hist, df_vna_proj)
        vna_fim = _lookup_vna(fim, df_vna_hist, df_vna_proj)

        if not vna_ini or not vna_fim or vna_ini <= 0:
            continue

        # IPCA / Variação VNA
        var_vna = vna_fim / vna_ini - 1.0  # decimal

        # Retorno IMA-B5: (1 + taxa_real proporcional ao DU) × (VNA_fim/VNA_ini) - 1
        taxa_real_du = (1 + taxa_real_aa / 100.0) ** (du / 252.0) - 1.0
        ret_imab = (1 + taxa_real_du) * (vna_fim / vna_ini) - 1.0

        # Retorno CDI
        res_cdi = calcular_retorno_cdi(ini, fim, selic_reunioes, holidays)
        ret_cdi = res_cdi["retorno_cdi"]

        idx_imab *= (1 + ret_imab)
        idx_cdi  *= (1 + ret_cdi)

        rows.append({
            "Período":              ini.strftime("%b/%Y"),
            "Início":               ini.strftime("%d/%m/%Y"),
            "Fim":                  fim.strftime("%d/%m/%Y"),
            "DU":                   du,
            "VNA Início":           round(vna_ini, 4),
            "VNA Fim":              round(vna_fim, 4),
            "IPCA / Var.VNA (%)":   round(var_vna * 100, 4),
            "Retorno IMA-B5 (%)":   round(ret_imab * 100, 4),
            "Retorno CDI (%)":      round(ret_cdi * 100, 4),
            "Dif. IMA-CDI (p.p.)":  round((ret_imab - ret_cdi) * 100, 4),
        })

    if not rows:
        st.warning("Não foi possível calcular. Verifique se o VNA histórico está carregado.")
        return

    df = pd.DataFrame(rows)

    # Totais acumulados
    ret_imab_total = (idx_imab / 100 - 1) * 100
    ret_cdi_total  = (idx_cdi  / 100 - 1) * 100
    dif_total = ret_imab_total - ret_cdi_total

    st.markdown("### 📊 Resumo do Período")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Retorno Total IMA-B5", f"{ret_imab_total:.4f}%")
    m2.metric("Retorno Total CDI",    f"{ret_cdi_total:.4f}%")
    m3.metric("Diferença Total",      f"{dif_total:+.4f} p.p.")
    m4.metric("Melhor Carrego", "IMA-B 5 🏆" if dif_total >= 0 else "CDI 🏆")

    # Tabela
    st.markdown("### 📋 Retorno Mensal Detalhado")

    def highlight(row):
        d = row["Dif. IMA-CDI (p.p.)"]
        c = "#EAFAF1" if d > 0 else ("#FDEDEC" if d < 0 else "")
        return [f"background-color: {c}"] * len(row)

    fmt = {
        "VNA Início":          "{:.4f}",
        "VNA Fim":             "{:.4f}",
        "IPCA / Var.VNA (%)":  "{:.4f}",
        "Retorno IMA-B5 (%)":  "{:.4f}",
        "Retorno CDI (%)":     "{:.4f}",
        "Dif. IMA-CDI (p.p.)": "{:+.4f}",
    }
    st.dataframe(
        df.style.apply(highlight, axis=1).format(fmt),
        use_container_width=True, hide_index=True
    )

    # Gráficos
    st.markdown("### 📈 Visualizações")
    t1, t2, t3 = st.tabs(["Barras Mensais", "Acumulado", "Diferença"])
    with t1: _plot_barras(df)
    with t2: _plot_acumulado(df, idx_imab, idx_cdi)
    with t3: _plot_diferenca(df)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_vna_proj(df_hist, data_inicio, data_fim, holidays):
    """Projeta VNA para datas futuras além do histórico disponível."""
    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    if not ipca_list or df_hist.empty:
        return pd.DataFrame(columns=["Data", "VNA"])

    ultima_hist = df_hist["Data"].max()
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


def _lookup_vna(target: date, df_hist, df_proj) -> float | None:
    """Prioriza histórico ANBIMA, depois projetado."""
    if not df_hist.empty:
        v = get_vna_exact_or_nearest(target, df_hist)
        if v: return v
    if not df_proj.empty:
        v = get_vna_exact_or_nearest(target, df_proj)
        if v: return v
    return None


def _build_monthly_periods(inicio: date, fim: date, holidays: set) -> list:
    def is_du(d): return d.weekday() < 5 and d not in holidays
    periods = []
    cur = inicio
    while cur < fim:
        last = (date(cur.year + 1, 1, 1) if cur.month == 12
                else date(cur.year, cur.month + 1, 1)) - timedelta(days=1)
        fim_per = min(last, fim)
        while not is_du(fim_per) and fim_per > cur:
            fim_per -= timedelta(days=1)
        if fim_per > cur:
            periods.append((cur, fim_per))
        nxt = (date(cur.year + 1, 1, 1) if cur.month == 12
               else date(cur.year, cur.month + 1, 1))
        while not is_du(nxt) and nxt <= fim:
            nxt += timedelta(days=1)
        if nxt >= fim: break
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


def _plot_acumulado(df, idx_imab_final, idx_cdi_final):
    # Reconstrói séries acumuladas
    imab_acum, cdi_acum = [100.0], [100.0]
    for _, row in df.iterrows():
        imab_acum.append(imab_acum[-1] * (1 + row["Retorno IMA-B5 (%)"] / 100))
        cdi_acum.append(cdi_acum[-1]  * (1 + row["Retorno CDI (%)"]     / 100))
    labels = ["Início"] + df["Período"].tolist()
    fig = go.Figure()
    fig.add_trace(go.Scatter(name="IMA-B 5", x=labels, y=imab_acum,
                             mode="lines+markers", line=dict(color="#1B4F72", width=2.5)))
    fig.add_trace(go.Scatter(name="CDI", x=labels, y=cdi_acum,
                             mode="lines+markers", line=dict(color="#2E86C1", width=2.5, dash="dash")))
    fig.update_layout(title="Número Índice Acumulado (base 100)", height=400,
                     plot_bgcolor="white", paper_bgcolor="white",
                     legend=dict(orientation="h", y=1.1), margin=dict(t=60, b=20))
    st.plotly_chart(fig, use_container_width=True)


def _plot_diferenca(df):
    cores = ["#1E8449" if v >= 0 else "#C0392B" for v in df["Dif. IMA-CDI (p.p.)"]]
    fig = go.Figure(go.Bar(
        x=df["Período"], y=df["Dif. IMA-CDI (p.p.)"],
        marker_color=cores,
        text=[f"{v:+.2f}" for v in df["Dif. IMA-CDI (p.p.)"]],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Diferença: IMA-B5 − CDI (p.p.)", height=350,
                     plot_bgcolor="white", paper_bgcolor="white",
                     yaxis=dict(ticksuffix=" p.p."), margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)
