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
st.set_page_config(page_title="DICOS BI - Dirección", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f4f6f9; }
    h1, h2, h3 { color: #003366 !important; }
    [data-testid="stMetricValue"] { color: #004080; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

BASE_URL = 'https://dicos.cl/appcom/'

# Tipado estricto para ahorrar RAM
dtypes_optimos = {
    'numero': 'string',
    'tipo_doc': 'category',
    'comuna': 'category',
    'vendedor': 'category',
    'patente': 'category',
    'repartidor': 'category',
    'sku': 'string',
    'cant': 'float32',
    'costo_unitario': 'float32',
    'venta_neta_linea': 'float32'
}

# ==========================================
# 1. EXTRACCIÓN A DEMANDA (1 AÑO A LA VEZ)
# ==========================================
@st.cache_data(show_spinner=False)
def cargar_datos_anio(anio):
    try:
        # Definir nombre de archivo según selección
        filename = "actual_maestro.csv" if anio == 2026 else f"maestro_{anio}.csv"
        url = f"{BASE_URL}{filename}"
        
        # Solo leer columnas necesarias para maximizar eficiencia
        cols = ['numero', 'tipo_doc', 'fecha', 'comuna', 'vendedor', 'patente', 'repartidor', 'sku', 'descripcion', 'cant', 'costo_unitario', 'venta_neta_linea']
        df = pd.read_csv(url, dtype=dtypes_optimos, usecols=cols)
        return df
    except Exception as e:
        st.error(f"Error al cargar datos del año {anio}: {e}")
        return pd.DataFrame()

# ==========================================
# INTERFAZ Y CONTROLES (SE MUEVEN AL INICIO)
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

st.sidebar.markdown("### ⚙️ Centro de Datos")
if st.sidebar.button("🔄 Sincronizar Datos Hoy", width='stretch'):
    with st.spinner("Actualizando 2026 desde el servidor..."):
        try:
            requests.get(f"{BASE_URL}fabrica_datos_real.php?anio=2026", timeout=20)
            cargar_datos_anio.clear() # Limpiar caché para forzar lectura del nuevo archivo
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error de red: {e}")

st.sidebar.divider()

# Selector de Año (Esto ahora controla qué archivo se descarga)
anios_disponibles = list(range(2026, 2015, -1))
anio_sel = st.sidebar.selectbox("Año Principal", anios_disponibles, index=0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

# ==========================================
# 2. PROCESAMIENTO (SOLO EL AÑO SELECCIONADO)
# ==========================================
with st.spinner(f"🧠 Analizando {anio_sel}..."):
    df_anio = cargar_datos_anio(anio_sel)
    
    if df_anio.empty:
        st.warning(f"No hay datos o no se ha generado el archivo para el año {anio_sel}.")
        st.stop()
        
    # Procesamiento financiero
    df_anio['fecha_dt'] = pd.to_datetime(df_anio['fecha'], format='%Y-%m-%d', errors='coerce')
    df_anio.dropna(subset=['fecha_dt'], inplace=True)
    df_anio['mes'] = df_anio['fecha_dt'].dt.month
    
    df_anio['tipo_doc'] = df_anio['tipo_doc'].astype(str).str.strip().str.upper()
    df_anio['neto'] = df_anio['venta_neta_linea'].fillna(0)
    df_anio['costo_total'] = df_anio['cant'].fillna(0) * df_anio['costo_unitario'].fillna(0)
    
    # Reglas de Negocio
    excluir = ['OV', 'FC', 'CR']
    df_anio = df_anio[~df_anio['tipo_doc'].isin(excluir)]
        
    mask_nc = df_anio['tipo_doc'] == 'NE'
    df_anio.loc[mask_nc, 'neto'] = -df_anio.loc[mask_nc, 'neto'].abs()
    df_anio.loc[mask_nc, 'costo_total'] = -df_anio.loc[mask_nc, 'costo_total'].abs()
    
    df_anio['margen'] = df_anio['neto'] - df_anio['costo_total']
    
    # Limpieza de textos
    for col in ['vendedor', 'comuna', 'descripcion', 'patente', 'repartidor']:
        df_anio[col] = df_anio[col].fillna('Sin Registro')

# Filtro mensual
df_mes = df_anio[df_anio['mes'] == mes_sel]

# ==========================================
# 3. DASHBOARD
# ==========================================
venta_neta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia_anio = (margen_anio / venta_neta_anio * 100) if venta_neta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Anual Consolidado ({anio_sel})")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas Anuales", f"${venta_neta_anio:,.0f}")
m2.metric("Margen Real Anual", f"${margen_anio:,.0f}")
m3.metric("Eficiencia Promedio", f"{eficiencia_anio:.1f}%")

st.divider()

tabs = st.tabs(["🌐 Desempeño Comercial", "🛒 Inteligencia de Portafolio", "📍 Zonas y Segmentos"])

with tabs[0]:
    st.markdown(f"### Detalle del Mes: {mes_sel}/{anio_sel}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Venta Neta del Mes", f"${df_mes['neto'].sum():,.0f}")
    c2.metric("Margen del Mes", f"${df_mes['margen'].sum():,.0f}")
    c3.metric("Documentos", f"{df_mes['numero'].nunique():,}")
    
    st.markdown("#### 🏆 Ranking Fuerza de Ventas")
    if not df_mes.empty:
        df_mes['vendedor_lbl'] = 'Cód: ' + df_mes['vendedor'].astype(str)
        vend_stats = df_mes.groupby('vendedor_lbl', as_index=False)['neto'].sum().sort_values('neto', ascending=True)
        st.plotly_chart(px.bar(vend_stats, x='neto', y='vendedor_lbl', orientation='h'), width='stretch')

with tabs[1]:
    st.markdown("#### 🧠 Rentabilidad por Producto (Top 50)")
    if not df_mes.empty:
        prod_stats = df_mes.groupby(['sku', 'descripcion']).agg(
            Venta=('neto', 'sum'), Costo=('costo_total', 'sum'), Utilidad=('margen', 'sum')
        ).reset_index()
        prod_stats['%_Margen'] = (prod_stats['Utilidad'] / prod_stats['Venta'] * 100).fillna(0)
        prod_top = prod_stats.sort_values('Venta', ascending=False).head(50)
        st.dataframe(prod_top.style.format({'Venta': '${:,.0f}', 'Costo': '${:,.0f}', 'Utilidad': '${:,.0f}', '%_Margen': '{:.1f}%'}), hide_index=True)

with tabs[2]:
    st.markdown("#### 📍 Penetración por Comuna")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        st.plotly_chart(px.pie(zona_stats[zona_stats['neto']>0], values='neto', names='comuna', hole=0.4), width='stretch')