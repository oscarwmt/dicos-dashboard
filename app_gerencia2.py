import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import warnings
import gc  # Librería para limpiar la memoria RAM manualmente
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

# ==========================================
# 1. SISTEMA DE EXTRACCIÓN (Modo Ultra-Ligero)
# ==========================================
# Forzamos a Pandas a usar la menor cantidad de bytes posibles por columna
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

@st.cache_data(ttl=604800, show_spinner="Abriendo Bóveda Histórica...")
def cargar_historico():
    dfs = []
    for anio in range(2016, 2026): 
        try:
            # Solo leemos las columnas que realmente usamos para no gastar RAM
            cols_necesarias = ['numero', 'tipo_doc', 'fecha', 'comuna', 'vendedor', 'patente', 'repartidor', 'sku', 'descripcion', 'cant', 'costo_unitario', 'venta_neta_linea']
            df = pd.read_csv(f"{BASE_URL}maestro_{anio}.csv", dtype=dtypes_optimos, usecols=cols_necesarias)
            dfs.append(df)
        except Exception:
            continue 
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

@st.cache_data(show_spinner="Descargando datos 2026...")
def cargar_actual():
    try:
        cols_necesarias = ['numero', 'tipo_doc', 'fecha', 'comuna', 'vendedor', 'patente', 'repartidor', 'sku', 'descripcion', 'cant', 'costo_unitario', 'venta_neta_linea']
        return pd.read_csv(f"{BASE_URL}actual_maestro.csv", dtype=dtypes_optimos, usecols=cols_necesarias)
    except Exception:
        return pd.DataFrame()

df_hist = cargar_historico()
df_act = cargar_actual()

if df_act.empty:
    st.error("⚠️ No se encontró la tabla del año actual.")
    st.stop()

# ==========================================
# 2. PROCESAMIENTO Y REGLAS DE NEGOCIO
# ==========================================
with st.spinner("🧠 Ensamblando datos y limpiando memoria..."):
    # 1. Unimos la historia con el año actual
    df_final = pd.concat([df_hist, df_act], ignore_index=True)
    
    # 2. TÉCNICA CLAVE: Borramos las tablas originales de la RAM para evitar el colapso
    del df_hist
    del df_act
    gc.collect() 
    
    # Manejo de fechas optimizado (le decimos el formato exacto para que no gaste CPU adivinando)
    df_final['fecha_dt'] = pd.to_datetime(df_final['fecha'], format='%Y-%m-%d', errors='coerce')
    df_final.dropna(subset=['fecha_dt'], inplace=True)
    df_final['año'] = df_final['fecha_dt'].dt.year
    df_final['mes'] = df_final['fecha_dt'].dt.month
    
    # Limpieza del tipo de documento para evitar errores de espacios invisibles
    df_final['tipo_doc'] = df_final['tipo_doc'].astype(str).str.strip().str.upper()
    
    # Asignación financiera (Directo de Sisgen)
    df_final['neto'] = df_final['venta_neta_linea'].fillna(0)
    df_final['costo_total'] = df_final['cant'].fillna(0) * df_final['costo_unitario'].fillna(0)
    
    # Reglas Tributarias de Sisgen
    CODIGOS_NOTA_CREDITO = ['NE']  
    CODIGOS_VENTA_INTERNA = ['OV'] 
    CODIGOS_COMPRA = ['FC', 'CR']  
    
    # Filtro de exclusión
    excluir = CODIGOS_VENTA_INTERNA + CODIGOS_COMPRA
    df_final = df_final[~df_final['tipo_doc'].isin(excluir)]
        
    # Notas de Crédito restan
    mask_nc = df_final['tipo_doc'].isin(CODIGOS_NOTA_CREDITO)
    df_final.loc[mask_nc, 'neto'] = -df_final.loc[mask_nc, 'neto'].abs()
    df_final.loc[mask_nc, 'costo_total'] = -df_final.loc[mask_nc, 'costo_total'].abs()
    
    df_final['margen'] = df_final['neto'] - df_final['costo_total']
    
    # Llenado de nulos
    cols_texto = ['vendedor', 'comuna', 'descripcion', 'patente', 'repartidor']
    for col in cols_texto:
        df_final[col] = df_final[col].fillna('Sin Registro')

# ==========================================
# 3. INTERFAZ GERENCIAL
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

st.sidebar.markdown("### ⚙️ Centro de Datos")
if st.sidebar.button("🔄 Sincronizar Datos Hoy", use_container_width=True):
    with st.spinner("Actualizando 2026 desde el servidor..."):
        try:
            requests.get(f"{BASE_URL}fabrica_datos_real.php?anio=2026", timeout=20)
            cargar_actual.clear()
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error de red al sincronizar: {e}")

st.sidebar.divider()

periodos = sorted(df_final['año'].unique())
anio_sel = st.sidebar.selectbox("Año Principal", periodos, index=len(periodos)-1 if periodos else 0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

df_anio = df_final[df_final['año'] == anio_sel]
df_mes = df_anio[df_anio['mes'] == mes_sel]

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
        st.plotly_chart(px.bar(vend_stats, x='neto', y='vendedor_lbl', orientation='h'), use_container_width=True)

with tabs[1]:
    st.markdown("#### 🧠 Rentabilidad por Producto (Top 50)")
    if not df_mes.empty:
        prod_stats = df_mes.groupby(['sku', 'descripcion']).agg(
            Venta=('neto', 'sum'), Costo=('costo_total', 'sum'), Utilidad=('margen', 'sum')
        ).reset_index()
        prod_stats['%_Margen'] = (prod_stats['Utilidad'] / prod_stats['Venta'] * 100).fillna(0)
        prod_top = prod_stats.sort_values('Venta', ascending=False).head(50)
        st.dataframe(prod_top.style.format({'Venta': '${:,.0f}', 'Costo': '${:,.0f}', 'Utilidad': '${:,.0f}', '%_Margen': '{:.1f}%'}), use_container_width=True, hide_index=True)

with tabs[2]:
    st.markdown("#### 📍 Penetración por Comuna")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        st.plotly_chart(px.pie(zona_stats[zona_stats['neto']>0], values='neto', names='comuna', hole=0.4), use_container_width=True)