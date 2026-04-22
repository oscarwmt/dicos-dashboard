import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
st.set_page_config(page_title="DICOS BI - Gestión 2023-2026", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f4f6f9; }
    h1, h2, h3 { color: #003366 !important; }
    [data-testid="stMetricValue"] { color: #004080; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

BASE_URL = 'https://dicos.cl/appcom/'

# Tipado para optimizar RAM
dtypes_optimos = {
    'numero': 'string',
    'tipo_doc': 'category',
    'comuna': 'category',
    'vendedor': 'category',
    'sku': 'string',
    'cant': 'float32',
    'costo_unitario': 'float32',
    'venta_neta_linea': 'float32'
}

# ==========================================
# 1. CARGA DE DATOS (RESTRINGIDA 2023-2026)
# ==========================================
@st.cache_data(show_spinner=False)
def cargar_datos_anio(anio):
    try:
        filename = "actual_maestro.csv" if anio == 2026 else f"maestro_{anio}.csv"
        url = f"{BASE_URL}{filename}"
        
        # Leemos solo columnas críticas para ahorrar memoria
        cols = ['numero', 'tipo_doc', 'fecha', 'comuna', 'vendedor', 'sku', 'descripcion', 'cant', 'costo_unitario', 'venta_neta_linea']
        df = pd.read_csv(url, dtype=dtypes_optimos, usecols=cols)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos del año {anio}: {e}")
        return pd.DataFrame()

# ==========================================
# INTERFAZ Y CONTROLES
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

st.sidebar.markdown("### ⚙️ Configuración de Análisis")

# Restricción explícita de años
anios_permitidos = [2026, 2025, 2024, 2023]
anio_sel = st.sidebar.selectbox("Seleccione Año de Análisis", anios_permitidos, index=0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

if st.sidebar.button("🔄 Sincronizar Datos Actuales", width='stretch'):
    with st.spinner("Actualizando 2026..."):
        try:
            requests.get(f"{BASE_URL}fabrica_datos_real.php?anio=2026", timeout=20)
            cargar_datos_anio.clear()
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# ==========================================
# 2. PROCESAMIENTO FINANCIERO
# ==========================================
with st.spinner(f"🧠 Analizando datos de {anio_sel}..."):
    df_anio = cargar_datos_anio(anio_sel)
    
    if df_anio.empty:
        st.warning(f"No se encontraron datos para el año {anio_sel}.")
        st.stop()
        
    # Conversión de fechas y métricas
    df_anio['fecha_dt'] = pd.to_datetime(df_anio['fecha'], format='%Y-%m-%d', errors='coerce')
    df_anio.dropna(subset=['fecha_dt'], inplace=True)
    df_anio['mes'] = df_anio['fecha_dt'].dt.month
    
    df_anio['neto'] = df_anio['venta_neta_linea'].fillna(0)
    df_anio['costo_total'] = df_anio['cant'].fillna(0) * df_anio['costo_unitario'].fillna(0)
    
    # Filtros de negocio
    excluir = ['OV', 'FC', 'CR'] # Órdenes de venta, facturas compra, etc.
    df_anio = df_anio[~df_anio['tipo_doc'].astype(str).str.upper().isin(excluir)]
        
    # Tratamiento de Notas de Crédito
    mask_nc = df_anio['tipo_doc'].astype(str).str.upper() == 'NE'
    df_anio.loc[mask_nc, 'neto'] = -df_anio.loc[mask_nc, 'neto'].abs()
    df_anio.loc[mask_nc, 'costo_total'] = -df_anio.loc[mask_nc, 'costo_total'].abs()
    
    df_anio['margen'] = df_anio['neto'] - df_anio['costo_total']

# Filtro por mes seleccionado
df_mes = df_anio[df_anio['mes'] == mes_sel]

# ==========================================
# 3. VISUALIZACIÓN GERENCIAL
# ==========================================
venta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia = (margen_anio / venta_anio * 100) if venta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Consolidado - Año {anio_sel}")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas", f"${venta_anio:,.0f}")
m2.metric("Margen Real", f"${margen_anio:,.0f}")
m3.metric("Eficiencia", f"{eficiencia:.1f}%")

st.divider()

tabs = st.tabs(["🌐 Ventas", "🛒 Productos", "📍 Geografía"])

with tabs[0]:
    st.markdown(f"#### Desempeño Mes {mes_sel}")
    if not df_mes.empty:
        vend_stats = df_mes.groupby('vendedor', as_index=False)['neto'].sum().sort_values('neto', ascending=True)
        st.plotly_chart(px.bar(vend_stats, x='neto', y='vendedor', orientation='h', title="Ventas por Vendedor"), use_container_width=True)

with tabs[1]:
    st.markdown("#### Top 50 Productos más Rentables (Mes)")
    if not df_mes.empty:
        prod_stats = df_mes.groupby(['sku', 'descripcion']).agg({'neto':'sum', 'margen':'sum'}).reset_index()
        prod_stats = prod_stats.sort_values('neto', ascending=False).head(50)
        st.dataframe(prod_stats.style.format({'neto': '${:,.0f}', 'margen': '${:,.0f}'}), hide_index=True, use_container_width=True)

with tabs[2]:
    st.markdown("#### Distribución por Comuna")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        st.plotly_chart(px.pie(zona_stats[zona_stats['neto']>0], values='neto', names='comuna', hole=0.4), use_container_width=True)