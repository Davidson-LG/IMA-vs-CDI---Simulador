"""
IMA-B 5 vs CDI — Simulador de Retornos
"""
import sys
import os

# ── sys.path fix ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st

# ── DEBUG: mostrar estado do ambiente (remover após resolver) ───────────────────
with st.expander("🔧 DEBUG — remover após resolver", expanded=True):
    st.write("**__file__:**", __file__)
    st.write("**os.getcwd():**", os.getcwd())
    st.write("**_here:**", _here)
    st.write("**utils/ existe em _here:**", os.path.isdir(os.path.join(_here, "utils")))
    st.write("**Conteúdo de _here:**", os.listdir(_here) if os.path.isdir(_here) else "N/A")
    st.write("**sys.path (primeiros 5):**", sys.path[:5])

    # Tenta importar e mostra erro real
    try:
        import utils.session_state as _ss
        st.success("✅ utils.session_state importado com sucesso!")
    except Exception as _e:
        st.error(f"❌ Erro real ao importar utils.session_state:\n\n```\n{type(_e).__name__}: {_e}\n```")
        import traceback
        st.code(traceback.format_exc())

    try:
        import utils.business_days as _bd
        st.success("✅ utils.business_days importado com sucesso!")
    except Exception as _e:
        st.error(f"❌ Erro real: {type(_e).__name__}: {_e}")
        import traceback
        st.code(traceback.format_exc())

    try:
        import utils.vna as _vna
        st.success("✅ utils.vna importado com sucesso!")
    except Exception as _e:
        st.error(f"❌ Erro real: {type(_e).__name__}: {_e}")
        import traceback
        st.code(traceback.format_exc())

st.stop()
