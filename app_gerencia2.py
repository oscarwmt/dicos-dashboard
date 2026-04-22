import streamlit as st
import pandas as pd
import plotly.express as px
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURACIÓN Y DESCARGA DIRECTA (ETL)
# ==========================================
st.set_page_config(page_title="DICOS BI - Panel Gerencial", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f4f6f9; }
    h1, h2, h3 { color: #003366 !important; }
    [data-testid="stMetricValue"] { color: #004080; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

# Rutas a los archivos estáticos generados por el PHP
URL_CAB = 'https://dicos.cl/etl_cabeceras.csv'
URL_DET = 'https://dicos.cl/etl_detalles.csv'
URL_PROD = 'https://dicos.cl/etl_productos.csv'

@st.cache_data(ttl=3600, show_spinner="Descargando Data Warehouse estático...")
def cargar_archivos_csv():
    try:
        df_c = pd.read_csv(URL_CAB)
        df_d = pd.read_csv(URL_DET)
        df_p = pd.read_csv(URL_PROD)
        return df_c, df_d, df_p
    except Exception as e:
        st.error(f"Error descargando CSVs: Verifica que ejecutaste generar_etl.php en el servidor. Detalle: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_cab, df_det, df_prod = cargar_archivos_csv()

if df_cab.empty:
    st.stop()

# ==========================================
# 2. PROCESAMIENTO PANDAS EN MEMORIA
# ==========================================
with st.spinner("🧠 Procesando Inteligencia de Negocios..."):
    # Cruces (JOINs) a la velocidad de la luz en RAM
    df_temp = pd.merge(df_det, df_prod, left_on='sku', right_on='PRCODIGO', how='inner')
    df_final = pd.merge(df_cab, df_temp, left_on=['FANUMERO', 'FATDOCTO'], right_on=['DENUMFAC', 'DETDOCTO'], how='inner')
    
    # Formateo de Fechas
    df_final['fecha_dt'] = pd.to_datetime(df_final['fecha'], errors='coerce')
    df_final.dropna(subset=['fecha_dt'], inplace=True)
    df_final['año'] = df_final['fecha_dt'].dt.year
    df_final['mes'] = df_final['fecha_dt'].dt.month
    
    # Cálculo de KPIs Financieros (Gross y Net de acuerdo a ley contable chilena)
    cols_num = ['cant', 'PREC1', 'PRECOM']
    df_final[cols_num] = df_final[cols_num].apply(pd.to_numeric, errors='coerce').fillna(0)
    df_final['neto'] = df_final['cant'] * df_final['PREC1']
    df_final['costo'] = df_final['cant'] * df_final['PRECOM']
    df_final['margen'] = df_final['neto'] - df_final['costo']
    
    # Blindaje contra nulos
    for col in ['vendedor', 'comuna', 'descripcion']:
        df_final[col] = df_final[col].fillna('Sin Registro').astype(str)

# ==========================================
# 3. INTERFAZ GERENCIAL
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

# Selectores
periodos = sorted(df_final['año'].unique())
anio_sel = st.sidebar.selectbox("Año Principal", periodos, index=len(periodos)-1 if periodos else 0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=pd.Timestamp.now().month - 1)

df_anio = df_final[df_final['año'] == anio_sel]
df_mes = df_anio[df_anio['mes'] == mes_sel]

# MACRO KPIs
venta_neta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia_anio = (margen_anio / venta_neta_anio * 100) if venta_neta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Anual Consolidado ({anio_sel})")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas Anuales", f"${venta_neta_anio:,.0f}")
m2.metric("Margen Real Anual ($)", f"${margen_anio:,.0f}")
m3.metric("Eficiencia Promedio", f"{eficiencia_anio:.1f}%")

st.divider()

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