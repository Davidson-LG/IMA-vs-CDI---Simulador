"""
Retorno Mês a Mês — carrego puro.
CDI:    índice_fim / índice_inicio - 1  (número índice acumulado diário)
IMA-B5: ((1+taxa_real)^(DU/252)) * (VNA_fim/VNA_ini) - 1
IPCA:   VNA_fim / VNA_ini - 1
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
    init_session_state, get_selic_cenario, selic_list_to_reunioes,
    get_ipca_cenario, ipca_list_to_df,
)
from utils.business_days import load_holidays, count_business_days, business_days_range
from utils.vna import (
    load_vna_historico, project_vna_daily,
    build_ipca_monthly_map, get_vna_at_date,
    calcular_retorno_cdi,
)


def render():
    init_session_state()
    holidays = load_holidays()

    st.markdown('<div class="section-title">📅 Retorno Mês a Mês — Carrego Puro</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="info-box">'
        'CDI = índice_fim / índice_inicio − 1 (número índice diário acumulado). '
        'IMA-B5 = (1+taxa_real)^(DU/252) × (VNA_fim/VNA_ini) − 1. '
        'IPCA = VNA_fim / VNA_ini − 1.'
        '</div>', unsafe_allow_html=True
    )

    data_inicio = st.session_state.get("data_inicio", date.today())
    data_fim    = st.session_state.get("data_fim", date.today() + timedelta(days=252))
    taxa_real_aa = st.session_state.get("taxa_real_aa", 7.75)

    selic_list = get_selic_cenario(st.session_state.get("cenario_ativo_selic", "base"))
    if not selic_list:
        st.warning("⚠️ Carregue Selic na aba **Parâmetros**.")
        return
    selic_reunioes = selic_list_to_reunioes(selic_list)

    # Constrói tabela VNA completa (histórico + projeção)
    df_vna_hist = st.session_state.get("vna_historico", pd.DataFrame(columns=["Data","VNA","Ref"]))
    if not df_vna_hist.empty:
        df_vna_hist = df_vna_hist.copy()
        df_vna_hist["Data"] = pd.to_datetime(df_vna_hist["Data"]).dt.date

    df_vna_full = _build_vna_full(df_vna_hist, data_inicio, data_fim, holidays)

    # CDI calculado diretamente por período (metodologia correta)
    df_cdi = None  # não mais usado — CDI calculado por período abaixo

    # Períodos mensais
    periodos = _build_monthly_periods(data_inicio, data_fim, holidays)
    if not periodos:
        st.info("Período muito curto para análise mensal.")
        return

    rows = []
    idx_imab = 100.0
    idx_cdi  = 100.0

    for ini, fim in periodos:
        du = len(business_days_range(ini, fim, holidays))

        # VNA lookup (procv): pega o VNA exato do início e fim do mês
        vna_ini = _lookup_date(ini, df_vna_full)
        vna_fim = _lookup_date(fim, df_vna_full)

        if not vna_ini or not vna_fim or vna_ini <= 0:
            continue

        # CDI: calcula diretamente para o período (metodologia validada)
        res_cdi = calcular_retorno_cdi(ini, fim, selic_reunioes, holidays)
        ret_cdi = res_cdi["retorno_cdi"]

        # IPCA = variação do VNA
        var_vna = vna_fim / vna_ini - 1.0

        # Retorno IMA-B5 = (1+taxa_real)^(DU/252) * (VNA_fim/VNA_ini) - 1
        taxa_real_du = (1 + taxa_real_aa / 100.0) ** (du / 252.0) - 1.0
        ret_imab = (1 + taxa_real_du) * (vna_fim / vna_ini) - 1.0

        idx_imab *= (1 + ret_imab)
        idx_cdi  *= (1 + ret_cdi)

        rows.append({
            "Período":             ini.strftime("%b/%Y"),
            "Início":              ini.strftime("%d/%m/%Y"),
            "Fim":                 fim.strftime("%d/%m/%Y"),
            "DU":                  du,
            "VNA Início":          round(vna_ini, 4),
            "VNA Fim":             round(vna_fim, 4),
            "IPCA / Var.VNA (%)":  round(var_vna * 100, 4),
            "Retorno IMA-B5 (%)":  round(ret_imab * 100, 4),
            "Retorno CDI (%)":     round(ret_cdi * 100, 4),
            "Dif. IMA-CDI (p.p.)": round((ret_imab - ret_cdi) * 100, 4),
        })

    if not rows:
        st.warning("Não foi possível calcular. Verifique se o VNA histórico está carregado.")
        return

    df = pd.DataFrame(rows)
    ret_imab_total = (idx_imab / 100 - 1) * 100
    ret_cdi_total  = (idx_cdi  / 100 - 1) * 100
    dif_total = ret_imab_total - ret_cdi_total

    st.markdown("### 📊 Resumo do Período")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Retorno Total IMA-B5", f"{ret_imab_total:.4f}%")
    m2.metric("Retorno Total CDI",    f"{ret_cdi_total:.4f}%")
    m3.metric("Diferença Total",      f"{dif_total:+.4f} p.p.")
    m4.metric("Melhor Carrego", "IMA-B 5 🏆" if dif_total >= 0 else "CDI 🏆")

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

    st.markdown("### 📈 Visualizações")
    t1, t2, t3 = st.tabs(["Barras Mensais", "Acumulado", "Diferença"])
    with t1: _plot_barras(df)
    with t2: _plot_acumulado(df)
    with t3: _plot_diferenca(df)


# ── Funções de suporte ─────────────────────────────────────────────────────────

def _build_vna_full(df_hist, data_inicio, data_fim, holidays):
    """
    Retorna DataFrame {Data: date, Value: float} com VNA para cada DU do período.
    Usa histórico ANBIMA onde disponível, projeta o restante.

    IPCA do ciclo 15-a-15:
    - Para ciclos com dados na coluna 'Índice' do arquivo ANBIMA → usa esse valor
    - Para ciclos futuros → usa o cenário IPCA selecionado (base/otimista/alternativo)
    """
    result = {}

    # Histórico ANBIMA
    if not df_hist.empty:
        for _, row in df_hist.iterrows():
            result[row["Data"]] = float(row["VNA"])

    if not result:
        return pd.DataFrame(columns=["Data", "Value"])

    ultima_hist = max(result.keys())
    if ultima_hist >= data_fim:
        df = pd.DataFrame(list(result.items()), columns=["Data", "Value"])
        return df.sort_values("Data").reset_index(drop=True)

    # Monta mapa IPCA de ciclo: usa 'Índice' do VNA histórico para ciclos conhecidos
    # e o cenário IPCA para ciclos futuros
    ipca_cycle_map = _build_ipca_cycle_map(df_hist, data_fim)

    # Ponto de partida: último VNA do histórico
    vna_ponto = result[ultima_hist]

    if ipca_cycle_map:
        df_proj = project_vna_daily(ultima_hist, data_fim, vna_ponto, ipca_cycle_map, holidays)
        if not df_proj.empty:
            df_proj["Data"] = pd.to_datetime(df_proj["Data"]).dt.date
            for _, row in df_proj.iterrows():
                if row["Data"] not in result:
                    result[row["Data"]] = float(row["VNA"])

    df = pd.DataFrame(list(result.items()), columns=["Data", "Value"])
    return df.sort_values("Data").reset_index(drop=True)


def _build_ipca_cycle_map(df_hist: pd.DataFrame, data_fim) -> dict:
    """
    Monta mapa {(ano, mes): ipca_ciclo%} para projeção VNA 15-a-15.

    Prioridade:
    1. Coluna 'Índice' do arquivo ANBIMA histórico (ciclos já divulgados)
    2. Cenário IPCA selecionado (ciclos futuros)
    """
    from datetime import date as _date
    cycle_map = {}

    # 1. Valores do arquivo ANBIMA (campo 'Índice' = IPCA do ciclo)
    if "Índice" in df_hist.columns:
        for _, row in df_hist.iterrows():
            try:
                d = row["Data"]
                if isinstance(d, str):
                    d = pd.to_datetime(d).date()
                elif hasattr(d, "date"):
                    d = d.date()
                idx = row.get("Índice")
                if pd.notna(idx) and float(idx) > 0:
                    cycle_map[(d.year, d.month)] = float(idx)
            except Exception:
                pass

    # 2. Cenário IPCA para datas não cobertas pelo histórico
    ipca_list = get_ipca_cenario(st.session_state.get("cenario_ativo_ipca", "base"))
    if ipca_list:
        ipca_df = ipca_list_to_df(ipca_list)
        for _, row in ipca_df.iterrows():
            dt = row["DataReferencia"]
            if isinstance(dt, pd.Timestamp):
                dt = dt.date()
            key = (dt.year, dt.month)
            if key not in cycle_map:  # não sobrescreve o ANBIMA
                cycle_map[key] = float(row["Mediana"])

    return cycle_map


def _build_cdi_index(data_inicio, data_fim, selic_reunioes, holidays):
    """
    Constrói número índice CDI diário (base = 10000 no data_inicio).
    Retorna DataFrame {Data: date, Value: float}.
    """
    reunioes = sorted(selic_reunioes, key=lambda x: x["data_reuniao"])

    # Taxa vigente inicial
    taxa = reunioes[0]["taxa_aa"] if reunioes else 14.75
    for r in reunioes:
        if r["data_reuniao"] <= data_inicio:
            taxa = r["taxa_aa"]

    all_days = business_days_range(data_inicio, data_fim, holidays)
    rows = []
    indice = 10000.0
    rows.append({"Data": data_inicio, "Value": indice})

    for d in all_days:
        if d == data_inicio:
            continue
        # Atualiza taxa na data da reunião
        for r in reunioes:
            if r["data_reuniao"] <= d:
                taxa = r["taxa_aa"]
            else:
                break
        fator = (1 + taxa / 100.0) ** (1.0 / 252.0)
        indice *= fator
        rows.append({"Data": d, "Value": indice})

    return pd.DataFrame(rows).sort_values("Data").reset_index(drop=True)


def _lookup_date(target: date, df: pd.DataFrame) -> float | None:
    """Procv: retorna Value para a data exata, ou a anterior mais próxima."""
    if df.empty:
        return None
    sub = df[df["Data"] <= target]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["Value"])


def _build_monthly_periods(inicio, fim, holidays):
    def is_du(d): return d.weekday() < 5 and d not in holidays
    periods = []
    cur = inicio
    while cur < fim:
        last = (date(cur.year+1,1,1) if cur.month==12
                else date(cur.year,cur.month+1,1)) - timedelta(days=1)
        fim_per = min(last, fim)
        while not is_du(fim_per) and fim_per > cur:
            fim_per -= timedelta(days=1)
        if fim_per > cur:
            periods.append((cur, fim_per))
        nxt = (date(cur.year+1,1,1) if cur.month==12
               else date(cur.year,cur.month+1,1))
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
                     yaxis=dict(ticksuffix="%"), margin=dict(t=60,b=20))
    st.plotly_chart(fig, use_container_width=True)


def _plot_acumulado(df):
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
                     legend=dict(orientation="h", y=1.1), margin=dict(t=60,b=20))
    st.plotly_chart(fig, use_container_width=True)


def _plot_diferenca(df):
    cores = ["#1E8449" if v >= 0 else "#C0392B" for v in df["Dif. IMA-CDI (p.p.)"]]
    fig = go.Figure(go.Bar(
        x=df["Período"], y=df["Dif. IMA-CDI (p.p.)"], marker_color=cores,
        text=[f"{v:+.2f}" for v in df["Dif. IMA-CDI (p.p.)"]],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(title="Diferença: IMA-B5 − CDI (p.p.)", height=350,
                     plot_bgcolor="white", paper_bgcolor="white",
                     yaxis=dict(ticksuffix=" p.p."), margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)
