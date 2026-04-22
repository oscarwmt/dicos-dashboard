import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURACIÓN Y RUTAS (Tu Servidor)
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

# ==========================================
# 2. SISTEMA DE EXTRACCIÓN (Caché Inteligente)
# ==========================================
# La Bóveda: Caché casi permanente (7 días) porque no cambia.
@st.cache_data(ttl=604800, show_spinner="Abriendo Bóveda Histórica...")
def cargar_historico():
    try:
        c1 = pd.read_csv(f"{BASE_URL}hist_cab_1.csv")
        d1 = pd.read_csv(f"{BASE_URL}hist_det_1.csv")
        c2 = pd.read_csv(f"{BASE_URL}hist_cab_2.csv")
        d2 = pd.read_csv(f"{BASE_URL}hist_det_2.csv")
        df_cab_hist = pd.concat([c1, c2], ignore_index=True)
        df_det_hist = pd.concat([d1, d2], ignore_index=True)
        return df_cab_hist, df_det_hist
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# El Motor Vivo: Caché que limpiaremos manualmente con el botón.
@st.cache_data(show_spinner="Descargando datos del año en curso...")
def cargar_actual():
    try:
        c_act = pd.read_csv(f"{BASE_URL}actual_cab.csv")
        d_act = pd.read_csv(f"{BASE_URL}actual_det.csv")
        prod = pd.read_csv(f"{BASE_URL}productos.csv")
        return c_act, d_act, prod
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_cab_hist, df_det_hist = cargar_historico()
df_cab_act, df_det_act, df_prod = cargar_actual()

if df_prod.empty:
    st.error("⚠️ No se han encontrado los archivos de datos. Verifica tu servidor.")
    st.stop()

# ==========================================
# 3. ENSAMBLAJE (Fusión Pasado + Presente)
# ==========================================
with st.spinner("🧠 Procesando Data Warehouse (10 Años)..."):
    # 1. Unir tablas
    df_cab_full = pd.concat([df_cab_hist, df_cab_act], ignore_index=True)
    df_det_full = pd.concat([df_det_hist, df_det_act], ignore_index=True)
    
    # 2. Cruces (JOINs en RAM)
    df_temp = pd.merge(df_det_full, df_prod, left_on='sku', right_on='PRCODIGO', how='inner')
    df_final = pd.merge(df_cab_full, df_temp, left_on=['FANUMERO', 'FATDOCTO'], right_on=['DENUMFAC', 'DETDOCTO'], how='inner')
    
    # 3. Formateo y Matemáticas
    df_final['fecha_dt'] = pd.to_datetime(df_final['fecha'], errors='coerce')
    df_final.dropna(subset=['fecha_dt'], inplace=True)
    df_final['año'] = df_final['fecha_dt'].dt.year
    df_final['mes'] = df_final['fecha_dt'].dt.month
    
    cols_num = ['cant', 'PREC1', 'PRECOM']
    df_final[cols_num] = df_final[cols_num].apply(pd.to_numeric, errors='coerce').fillna(0)
    
    df_final['neto'] = df_final['cant'] * df_final['PREC1']
    df_final['costo'] = df_final['cant'] * df_final['PRECOM']
    df_final['margen'] = df_final['neto'] - df_final['costo']
    
    for col in ['vendedor', 'comuna', 'descripcion']:
        df_final[col] = df_final[col].fillna('Sin Registro').astype(str)

# ==========================================
# 4. INTERFAZ GERENCIAL Y PANEL DE CONTROL
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

# -- BOTÓN DE SINCRONIZACIÓN (LA MAGIA) --
st.sidebar.markdown("### ⚙️ Centro de Datos")
if st.sidebar.button("🔄 Sincronizar Datos Hoy", use_container_width=True):
    with st.spinner("Conectando con Servidor DICOS... extrayendo ventas recientes..."):
        try:
            # 1. Disparamos el script PHP en tu servidor para generar el nuevo CSV
            requests.get(f"{BASE_URL}fabrica_datos.php?bloque=actual", timeout=15)
            # 2. Borramos SOLO la caché del año actual
            cargar_actual.clear()
            st.sidebar.success("✅ ¡Datos actualizados al minuto!")
            # 3. Recargamos la pantalla
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error de conexión: {e}")

st.sidebar.divider()

# -- FILTROS DE NAVEGACIÓN --
st.sidebar.markdown("### 🎛️ Navegación Temporal")
periodos = sorted(df_final['año'].unique())
anio_sel = st.sidebar.selectbox("Año Principal", periodos, index=len(periodos)-1 if periodos else 0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

df_anio = df_final[df_final['año'] == anio_sel]
df_mes = df_anio[df_anio['mes'] == mes_sel]

# -- MACRO KPIs --
venta_neta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia_anio = (margen_anio / venta_neta_anio * 100) if venta_neta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Anual Consolidado ({anio_sel})")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas Anuales", f"${venta_neta_anio:,.0f}")
m2.metric("Margen Real Anual", f"${margen_anio:,.0f}")
m3.metric("Eficiencia Promedio", f"{eficiencia_anio:.1f}%")

st.divider()

# -- PESTAÑAS --
tabs = st.tabs(["🌐 Desempeño Comercial", "🛒 Inteligencia de Portafolio", "📍 Zonas y Segmentos"])

with tabs[0]:
    st.markdown(f"### Detalle del Mes: {mes_sel}/{anio_sel}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Venta Neta del Mes", f"${df_mes['neto'].sum():,.0f}")
    c2.metric("Margen del Mes", f"${df_mes['margen'].sum():,.0f}")
    c3.metric("Documentos", f"{df_mes['FANUMERO'].nunique():,}")
    
    st.markdown("#### 🏆 Ranking Fuerza de Ventas")
    if not df_mes.empty:
        vend_stats = df_mes.groupby('vendedor', as_index=False)['neto'].sum().sort_values('neto', ascending=True)
        st.plotly_chart(px.bar(vend_stats, x='neto', y='vendedor', orientation='h'), use_container_width=True)

with tabs[1]:
    st.markdown("#### 🧠 Rentabilidad por Producto (Top 50)")
    if not df_mes.empty:
        prod_stats = df_mes.groupby(['sku', 'descripcion']).agg(
            Venta=('neto', 'sum'), Costo=('costo', 'sum'), Utilidad=('margen', 'sum')
        ).reset_index()
        prod_stats['%_Margen'] = (prod_stats['Utilidad'] / prod_stats['Venta'] * 100).fillna(0)
        prod_top = prod_stats.sort_values('Venta', ascending=False).head(50)
        st.dataframe(prod_top.style.format({'Venta': '${:,.0f}', 'Costo': '${:,.0f}', 'Utilidad': '${:,.0f}', '%_Margen': '{:.1f}%'}), use_container_width=True, hide_index=True)

with tabs[2]:
    st.markdown("#### 📍 Penetración por Comuna")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        st.plotly_chart(px.pie(zona_stats[zona_stats['neto']>0], values='neto', names='comuna', hole=0.4), use_container_width=True)