"""
Página de Parâmetros — configuração de IPCA, Selic e parâmetros IMA-B 5.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from utils.session_state import init_session_state
from utils.focus_api import (
    get_focus_ipca_mensal,
    get_focus_selic_copom,
    get_focus_data_publicacao,
)


def render():
    init_session_state()

    st.markdown('<div class="section-title">⚙️ Parâmetros de Simulação</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📐 IMA-B 5 e Datas", "📊 IPCA", "🏦 Selic / COPOM"])

    # ── Tab 1: IMA-B 5 e Datas ────────────────────────────────────────────────
    with tab1:
        st.markdown("### Parâmetros do IMA-B 5")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            taxa = st.number_input(
                "Taxa Real IMA-B 5 (%a.a.)",
                min_value=0.0, max_value=30.0,
                value=float(st.session_state.get("taxa_real_aa", 7.75)),
                step=0.01, format="%.4f",
                help="Redemption yield real atual do IMA-B 5"
            )
            st.session_state["taxa_real_aa"] = taxa

        with col2:
            dur = st.number_input(
                "Duration (dias úteis)",
                min_value=1, max_value=2000,
                value=int(st.session_state.get("duration_du", 496)),
                step=1,
                help="Duration do IMA-B 5 em dias úteis"
            )
            st.session_state["duration_du"] = dur
            dur_anos = dur / 252.0
            st.caption(f"≈ {dur_anos:.2f} anos")

        with col3:
            data_ini = st.date_input(
                "Data de Início",
                value=st.session_state.get("data_inicio", date.today()),
                format="DD/MM/YYYY"
            )
            st.session_state["data_inicio"] = data_ini

        with col4:
            data_fim = st.date_input(
                "Data Final",
                value=st.session_state.get("data_fim", date.today() + timedelta(days=252)),
                format="DD/MM/YYYY"
            )
            st.session_state["data_fim"] = data_fim

        st.markdown("---")
        st.markdown("### Cenário Ativo")
        st.markdown("Selecione qual cenário de IPCA e Selic será usado nos cálculos da aba principal.")

        col_a, col_b = st.columns(2)
        with col_a:
            cenario_ipca = st.selectbox(
                "Cenário IPCA",
                options=["base", "otimista", "alternativo"],
                index=["base", "otimista", "alternativo"].index(
                    st.session_state.get("cenario_ativo_ipca", "base")
                ),
                format_func=lambda x: {"base": "📌 Base (Focus)", "otimista": "✅ Otimista", "alternativo": "⚠️ Alternativo"}[x]
            )
            st.session_state["cenario_ativo_ipca"] = cenario_ipca

        with col_b:
            cenario_selic = st.selectbox(
                "Cenário Selic",
                options=["base", "otimista", "alternativo"],
                index=["base", "otimista", "alternativo"].index(
                    st.session_state.get("cenario_ativo_selic", "base")
                ),
                format_func=lambda x: {"base": "📌 Base (Focus)", "otimista": "✅ Otimista", "alternativo": "⚠️ Alternativo"}[x]
            )
            st.session_state["cenario_ativo_selic"] = cenario_selic

    # ── Tab 2: IPCA ───────────────────────────────────────────────────────────
    with tab2:
        _render_ipca_tab()

    # ── Tab 3: Selic ──────────────────────────────────────────────────────────
    with tab3:
        _render_selic_tab()


def _render_ipca_tab():
    st.markdown("### 📊 Projeções de IPCA")

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("🔄 Atualizar Focus", key="btn_atualizar_focus_ipca"):
            st.cache_data.clear()
            st.rerun()

    # Carrega dados Focus
    with st.spinner("Carregando projeções Focus..."):
        df_focus = get_focus_ipca_mensal()
        focus_pub = get_focus_data_publicacao()
        st.session_state["focus_data_publicacao"] = focus_pub

    if df_focus.empty:
        st.warning("Não foi possível carregar dados do Focus. Verifique conexão.")
    else:
        st.success(f"✅ Focus carregado — publicação: {focus_pub}")
        # Salva cenário base
        base_list = []
        for _, row in df_focus.iterrows():
            base_list.append({
                "DataReferencia": row["DataReferencia"],
                "Mediana": float(row["Mediana"])
            })
        st.session_state["ipca_base"] = base_list

    st.markdown("---")

    # Editor de três cenários
    subtab1, subtab2, subtab3 = st.tabs(["📌 Base (Focus)", "✅ Otimista", "⚠️ Alternativo"])

    with subtab1:
        st.markdown("**Cenário Base — Mediana Focus (somente leitura)**")
        if st.session_state.get("ipca_base"):
            df_base = pd.DataFrame(st.session_state["ipca_base"])
            df_base["Mês"] = pd.to_datetime(df_base["DataReferencia"]).dt.strftime("%m/%Y")
            df_base["IPCA Mensal (%)"] = df_base["Mediana"].round(4)
            df_base["IPCA Acumulado (%)"] = ((1 + df_base["Mediana"] / 100).cumprod() - 1).round(4) * 100
            st.dataframe(
                df_base[["Mês", "IPCA Mensal (%)", "IPCA Acumulado (%)"]],
                use_container_width=True, hide_index=True
            )
            _plot_ipca_bar(df_base["Mês"].tolist(), df_base["IPCA Mensal (%)"].tolist(), "Cenário Base — Focus")
        else:
            st.info("Clique em 'Atualizar Focus' para carregar.")

    with subtab2:
        st.markdown("**Cenário Otimista — edição manual**")
        df_ot = _get_or_init_manual_ipca("ipca_otimista", offset=-0.10)
        edited_ot = st.data_editor(
            df_ot,
            key="de_ipca_otimista",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Mês": st.column_config.TextColumn("Mês", disabled=True),
                "IPCA (%)": st.column_config.NumberColumn("IPCA (%)", min_value=-5.0, max_value=10.0, step=0.01, format="%.2f"),
            }
        )
        if st.button("💾 Salvar Otimista", key="save_ot"):
            _save_manual_ipca("ipca_otimista", edited_ot)
            st.success("Cenário Otimista salvo!")
        _plot_ipca_bar(edited_ot["Mês"].tolist(), edited_ot["IPCA (%)"].tolist(), "Cenário Otimista")

    with subtab3:
        st.markdown("**Cenário Alternativo — edição manual**")
        df_alt = _get_or_init_manual_ipca("ipca_alternativo", offset=0.10)
        edited_alt = st.data_editor(
            df_alt,
            key="de_ipca_alternativo",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Mês": st.column_config.TextColumn("Mês", disabled=True),
                "IPCA (%)": st.column_config.NumberColumn("IPCA (%)", min_value=-5.0, max_value=10.0, step=0.01, format="%.2f"),
            }
        )
        if st.button("💾 Salvar Alternativo", key="save_alt"):
            _save_manual_ipca("ipca_alternativo", edited_alt)
            st.success("Cenário Alternativo salvo!")
        _plot_ipca_bar(edited_alt["Mês"].tolist(), edited_alt["IPCA (%)"].tolist(), "Cenário Alternativo")


def _get_or_init_manual_ipca(key: str, offset: float = 0.0) -> pd.DataFrame:
    """Inicializa ou recupera cenário manual de IPCA."""
    if st.session_state.get(key):
        df = pd.DataFrame(st.session_state[key])
        df["Mês"] = pd.to_datetime(df["DataReferencia"]).dt.strftime("%m/%Y")
        df = df.rename(columns={"Mediana": "IPCA (%)"})
        return df[["Mês", "IPCA (%)"]].copy()

    # Inicializa a partir do base com offset
    base = st.session_state.get("ipca_base", [])
    if not base:
        # Gera 24 meses com valor padrão
        rows = []
        ref = date.today().replace(day=1)
        for _ in range(24):
            rows.append({"Mês": ref.strftime("%m/%Y"), "IPCA (%)": round(0.35 + offset, 4)})
            ref = (ref + relativedelta(months=1))
        return pd.DataFrame(rows)

    df = pd.DataFrame(base)
    df["Mês"] = pd.to_datetime(df["DataReferencia"]).dt.strftime("%m/%Y")
    df["IPCA (%)"] = (df["Mediana"] + offset).round(4)
    return df[["Mês", "IPCA (%)"]].copy()


def _save_manual_ipca(key: str, df_edited: pd.DataFrame):
    """Salva edições manuais de IPCA no session_state."""
    rows = []
    for _, row in df_edited.iterrows():
        try:
            mes_str = row["Mês"]
            dt = pd.to_datetime(mes_str, format="%m/%Y")
            rows.append({"DataReferencia": dt, "Mediana": float(row["IPCA (%)"])})
        except Exception:
            pass
    st.session_state[key] = rows


def _render_selic_tab():
    st.markdown("### 🏦 Projeções Selic / COPOM")

    col_btn1, _ = st.columns([1, 4])
    with col_btn1:
        if st.button("🔄 Atualizar Focus", key="btn_atualizar_focus_selic"):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Carregando projeções Selic Focus..."):
        df_selic_focus = get_focus_selic_copom()

    if df_selic_focus.empty:
        st.warning("Não foi possível carregar dados de Selic do Focus.")
    else:
        rows = []
        for _, row in df_selic_focus.iterrows():
            rows.append({
                "reuniao_label": str(row["Reuniao"]),
                "data_reuniao": row["data_reuniao"],
                "taxa_aa": float(row["taxa_aa"]),
            })
        rows.sort(key=lambda x: x["data_reuniao"])
        st.session_state["selic_base"] = rows
        st.success(f"✅ Selic Focus carregado — {len(rows)} reuniões")

    subtab1, subtab2, subtab3 = st.tabs(["📌 Base (Focus)", "✅ Otimista", "⚠️ Alternativo"])

    with subtab1:
        st.markdown("**Cenário Base — Mediana Focus**")
        st.markdown(
            "📅 **Datas das reuniões COPOM**: edite abaixo se necessário. "
            "As datas afetam o cálculo de CDI em todos os meses com COPOM. "
            "Use sempre o **último dia** da reunião (quarta-feira)."
        )

        if st.session_state.get("selic_base"):
            df_b = pd.DataFrame(st.session_state["selic_base"])
            df_b = df_b.sort_values("data_reuniao").reset_index(drop=True)

            # Editor editável com datas e taxas
            df_edit = df_b.copy()
            df_edit["Reunião COPOM"] = df_edit["reuniao_label"]
            df_edit["Data Reunião"] = pd.to_datetime(df_edit["data_reuniao"]).dt.date
            df_edit["Selic (%a.a.)"] = df_edit["taxa_aa"]
            df_edit = df_edit[["Reunião COPOM", "Data Reunião", "Selic (%a.a.)"]]

            edited_base = st.data_editor(
                df_edit,
                key="de_selic_base",
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "Reunião COPOM": st.column_config.TextColumn(disabled=True),
                    "Data Reunião": st.column_config.DateColumn(
                        "Data Reunião (último dia)",
                        format="DD/MM/YYYY",
                        help="Insira a data do último dia da reunião COPOM (quarta-feira)"
                    ),
                    "Selic (%a.a.)": st.column_config.NumberColumn(
                        min_value=0.0, max_value=30.0, step=0.25, format="%.2f"
                    ),
                }
            )

            if st.button("💾 Salvar Datas e Taxas COPOM", key="save_selic_base_manual"):
                rows_updated = []
                for _, row in edited_base.iterrows():
                    dt = row["Data Reunião"]
                    if hasattr(dt, "date"): dt = dt.date()
                    rows_updated.append({
                        "reuniao_label": str(row["Reunião COPOM"]),
                        "data_reuniao": dt,
                        "taxa_aa": float(row["Selic (%a.a.)"]),
                    })
                rows_updated.sort(key=lambda x: x["data_reuniao"])
                st.session_state["selic_base"] = rows_updated

                # Sempre propaga as DATAS para otimista e alternativo,
                # preservando as taxas que já foram editadas nesses cenários
                for key_cen in ["selic_otimista", "selic_alternativo"]:
                    existing = st.session_state.get(key_cen, [])
                    # Monta mapa reunião → taxa já salva
                    taxa_map = {r["reuniao_label"]: r["taxa_aa"] for r in existing}
                    # Aplica as novas datas, preservando taxas existentes
                    updated = []
                    for r in rows_updated:
                        lbl = r["reuniao_label"]
                        updated.append({
                            "reuniao_label": lbl,
                            "data_reuniao":  r["data_reuniao"],
                            "taxa_aa":       taxa_map.get(lbl, r["taxa_aa"]),
                        })
                    st.session_state[key_cen] = updated

                st.success("✅ Datas e taxas COPOM atualizadas em todos os cenários!")
                st.rerun()

            _plot_selic_step(edited_base.rename(columns={"Reunião COPOM": "Reunião COPOM"}), "Cenário Base — Focus")

    with subtab2:
        st.markdown("**Cenário Otimista — edição manual** (taxas menores)")
        df_ot_s = _get_or_init_manual_selic("selic_otimista", offset=-0.25)
        edited_ot_s = st.data_editor(
            df_ot_s,
            key="de_selic_otimista",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Reunião COPOM": st.column_config.TextColumn(disabled=True),
                "Selic (%a.a.)": st.column_config.NumberColumn(min_value=0.0, max_value=30.0, step=0.25, format="%.2f"),
            }
        )
        if st.button("💾 Salvar Selic Otimista", key="save_selic_ot"):
            _save_manual_selic("selic_otimista", edited_ot_s)
            st.success("Cenário Selic Otimista salvo!")
        _plot_selic_step(edited_ot_s, "Selic Otimista")

    with subtab3:
        st.markdown("**Cenário Alternativo — edição manual** (taxas maiores)")
        df_alt_s = _get_or_init_manual_selic("selic_alternativo", offset=0.25)
        edited_alt_s = st.data_editor(
            df_alt_s,
            key="de_selic_alternativo",
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Reunião COPOM": st.column_config.TextColumn(disabled=True),
                "Selic (%a.a.)": st.column_config.NumberColumn(min_value=0.0, max_value=30.0, step=0.25, format="%.2f"),
            }
        )
        if st.button("💾 Salvar Selic Alternativo", key="save_selic_alt"):
            _save_manual_selic("selic_alternativo", edited_alt_s)
            st.success("Cenário Selic Alternativo salvo!")
        _plot_selic_step(edited_alt_s, "Selic Alternativo")


def _save_selic_base_from_focus(df_focus: pd.DataFrame):
    """Salva Selic base a partir do Focus (ordenado por data)."""
    rows = []
    for _, row in df_focus.iterrows():
        reuniao = str(row.get("Reuniao", ""))
        taxa = float(row.get("taxa_aa", row.get("Mediana", 14.75)))
        data_reuniao = row.get("data_reuniao") or _parse_reuniao_date(reuniao)
        if isinstance(data_reuniao, str):
            from datetime import datetime
            try: data_reuniao = datetime.strptime(data_reuniao, "%Y-%m-%d").date()
            except: data_reuniao = _parse_reuniao_date(reuniao)
        rows.append({
            "reuniao_label": reuniao,
            "data_reuniao": data_reuniao,
            "taxa_aa": taxa,
        })
    # Ordena por data
    rows.sort(key=lambda x: x["data_reuniao"])
    st.session_state["selic_base"] = rows


def _parse_reuniao_date(reuniao: str) -> date:
    """Converte string de reunião COPOM (ex: '1/2026') para date aproximada."""
    try:
        parts = reuniao.split("/")
        num = int(parts[0])
        ano = int(parts[1])
        # Reuniões do COPOM: ~8 por ano, estimativa por bimestre
        mes = min(num * 2, 12)
        return date(ano, mes, 1)
    except Exception:
        return date.today()


def _get_or_init_manual_selic(key: str, offset: float = 0.0) -> pd.DataFrame:
    if st.session_state.get(key):
        df = pd.DataFrame(st.session_state[key])
        if "reuniao_label" in df.columns:
            return df.rename(columns={"reuniao_label": "Reunião COPOM", "taxa_aa": "Selic (%a.a.)"})[["Reunião COPOM", "Selic (%a.a.)"]].copy()

    base = st.session_state.get("selic_base", [])
    if not base:
        return pd.DataFrame({"Reunião COPOM": ["1/2026", "2/2026", "3/2026", "4/2026"],
                             "Selic (%a.a.)": [14.75 + offset, 15.0 + offset, 15.0 + offset, 14.75 + offset]})

    df = pd.DataFrame(base)
    df["Selic (%a.a.)"] = (df["taxa_aa"] + offset).round(2)
    df["Reunião COPOM"] = df["reuniao_label"]
    return df[["Reunião COPOM", "Selic (%a.a.)"]].copy()


def _save_manual_selic(key: str, df_edited: pd.DataFrame):
    rows = []
    for _, row in df_edited.iterrows():
        reuniao = str(row["Reunião COPOM"])
        taxa = float(row["Selic (%a.a.)"])
        data_reuniao = _parse_reuniao_date(reuniao)
        rows.append({
            "reuniao_label": reuniao,
            "data_reuniao": data_reuniao,
            "taxa_aa": taxa,
        })
    st.session_state[key] = rows


def _plot_ipca_bar(meses: list, valores: list, titulo: str):
    if not meses:
        return
    fig = go.Figure(go.Bar(
        x=meses, y=valores,
        marker_color=["#C0392B" if v > 0.5 else "#2E86C1" for v in valores],
        text=[f"{v:.2f}%" for v in valores],
        textposition="outside",
    ))
    fig.update_layout(
        title=titulo,
        xaxis_title="Mês",
        yaxis_title="IPCA (%)",
        height=320,
        margin=dict(t=40, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=11),
    )
    st.plotly_chart(fig, use_container_width=True)


def _plot_selic_step(df: pd.DataFrame, titulo: str):
    if df.empty:
        return
    col_taxa = "Selic (%a.a.)" if "Selic (%a.a.)" in df.columns else "taxa_aa"
    col_ref = "Reunião COPOM" if "Reunião COPOM" in df.columns else "reuniao_label"
    fig = go.Figure(go.Scatter(
        x=df[col_ref].tolist(),
        y=df[col_taxa].tolist(),
        mode="lines+markers",
        line=dict(shape="hv", color="#1B4F72", width=2),
        marker=dict(size=8, color="#2E86C1"),
        text=[f"{v:.2f}%" for v in df[col_taxa]],
        textposition="top center",
    ))
    fig.update_layout(
        title=titulo,
        xaxis_title="Reunião COPOM",
        yaxis_title="Selic (%a.a.)",
        height=300,
        margin=dict(t=40, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=11),
    )
    st.plotly_chart(fig, use_container_width=True)
