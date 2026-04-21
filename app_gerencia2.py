import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import json
import time
import calendar
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURACIÓN Y CONEXIÓN
# ==========================================
st.set_page_config(page_title="DICOS BI - Panel Gerencial", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f4f6f9; }
    h1, h2, h3 { color: #003366 !important; }
    [data-testid="stMetricValue"] { color: #004080; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

BRIDGE_URL = 'https://dicos.cl/db_bridge.php'
TOKEN_SECRETO = 'Oscar2026!'
FECHA_CORTE = '2023-01-01' # Filtro maestro desde 2023

@st.cache_data(ttl=3600, show_spinner=False)
def extraer_datos_modo_ninja(query, nombre_tabla, chunk_size=2500):
    """
    Extrae datos en bloques aplicando un pequeño retraso (Rate Limiting) 
    para evadir el firewall del hosting compartido.
    """
    offset = 0
    df_completo = pd.DataFrame()
    alerta = st.empty()
    
    while True:
        alerta.info(f"📥 Descargando {nombre_tabla} desde 2023... (Filas: {offset} a {offset + chunk_size})")
        q_paginada = f"{query} LIMIT {chunk_size} OFFSET {offset}"
        payload = {"token": TOKEN_SECRETO, "accion": "query_dashboard", "query": q_paginada}
        
        try:
            paquete_hex = json.dumps(payload).encode('utf-8').hex()
            response = requests.post(BRIDGE_URL, data={'paquete': paquete_hex}, timeout=45)
            
            if response.status_code == 200:
                res_json = response.json()
                data = res_json.get("data", [])
                
                if not data: break
                
                df_completo = pd.concat([df_completo, pd.DataFrame(data)], ignore_index=True)
                
                if len(data) < chunk_size: break
                
                offset += chunk_size
                # EL SECRETO: Pausar 0.3 segundos para no activar el firewall
                time.sleep(0.3) 
            else:
                st.error(f"Bloqueo del servidor en {nombre_tabla} - Código HTTP: {response.status_code}")
                break
                
        except Exception as e:
            st.error(f"Fallo de red conectando con DICOS: {e}")
            break
            
    alerta.empty()
    return df_completo

# ==========================================
# 2. MOTOR DE EXTRACCIÓN (OLAP en Memoria)
# ==========================================
st.sidebar.title("⚙️ Filtros de Análisis")
st.sidebar.caption("Data Warehouse: 2023 - Actualidad")

# Pedimos datos planos a MySQL, Python hará los cruces pesados
q_cab = f"SELECT FANUMERO, FATDOCTO, FAFECHA as fecha, FACOMCLI as comuna, FACODVEND as vendedor FROM v_cabecera WHERE FAFECHA >= '{FECHA_CORTE}'"
q_det = f"SELECT DENUMFAC, DETDOCTO, DECODPRO as sku, DECANTIDAD as cant FROM v_detalle WHERE FECDOCU >= '{FECHA_CORTE}'"
q_prod = "SELECT PRCODIGO, PRDESCRIP as descripcion, PREC1, PRECOM FROM producto"

with st.spinner("Conectando con Servidor DICOS SpA..."):
    df_cab = extraer_datos_modo_ninja(q_cab, "Cabeceras (v_cabecera)")
    df_det = extraer_datos_modo_ninja(q_det, "Detalles (v_detalle)")
    df_prod = extraer_datos_modo_ninja(q_prod, "Catálogo (producto)")

if df_cab.empty or df_det.empty or df_prod.empty:
    st.error("⚠️ No se pudo construir el Data Warehouse. Verifica tu conexión a internet.")
    st.stop()

# ==========================================
# 3. PROCESAMIENTO PANDAS (Tu Ferrari)
# ==========================================
with st.spinner("🧠 Procesando Inteligencia de Negocios..."):
    # Cruces (JOINs) en memoria RAM (Python)
    df_temp = pd.merge(df_det, df_prod, left_on='sku', right_on='PRCODIGO', how='inner')
    df_final = pd.merge(df_cab, df_temp, left_on=['FANUMERO', 'FATDOCTO'], right_on=['DENUMFAC', 'DETDOCTO'], how='inner')
    
    # Formateo de Fechas
    df_final['fecha_dt'] = pd.to_datetime(df_final['fecha'], errors='coerce')
    df_final.dropna(subset=['fecha_dt'], inplace=True)
    df_final['año'] = df_final['fecha_dt'].dt.year
    df_final['mes'] = df_final['fecha_dt'].dt.month
    
    # Cálculo de KPIs Financieros
    cols_num = ['cant', 'PREC1', 'PRECOM']
    df_final[cols_num] = df_final[cols_num].apply(pd.to_numeric, errors='coerce').fillna(0)
    df_final['neto'] = df_final['cant'] * df_final['PREC1']
    df_final['costo'] = df_final['cant'] * df_final['PRECOM']
    df_final['margen'] = df_final['neto'] - df_final['costo']
    
    # Blindaje contra nulos en gráficos
    for col in ['vendedor', 'comuna', 'descripcion']:
        df_final[col] = df_final[col].fillna('Sin Registro').astype(str)

# ==========================================
# 4. INTERFAZ GERENCIAL
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

# Selectores dinámicos basados en la data real
periodos = sorted(df_final['año'].unique())
anio_sel = st.sidebar.selectbox("Año Principal", periodos, index=len(periodos)-1 if periodos else 0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

df_anio = df_final[df_final['año'] == anio_sel]
df_mes = df_anio[df_anio['mes'] == mes_sel]

# MACRO KPIs ANUALES
venta_neta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia_anio = (margen_anio / venta_neta_anio * 100) if venta_neta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Anual Consolidado ({anio_sel})")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas Anuales", f"${venta_neta_anio:,.0f}")
m2.metric("Margen Real Anual ($)", f"${margen_anio:,.0f}")
m3.metric("Eficiencia Promedio", f"{eficiencia_anio:.1f}%")

st.divider()

# PESTAÑAS (Reincorporando tu lógica modular)
tabs = st.tabs(["🌐 Desempeño Comercial", "🛒 Inteligencia de Portafolio", "📍 Zonas y Segmentos"])

with tabs[0]:
    venta_neta_mes = df_mes['neto'].sum()
    margen_mes = df_mes['margen'].sum()
    
    st.markdown(f"### Detalle del Mes: {mes_sel}/{anio_sel}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Venta Neta del Mes", f"${venta_neta_mes:,.0f}")
    c2.metric("Margen del Mes", f"${margen_mes:,.0f}")
    c3.metric("Documentos", f"{df_mes['FANUMERO'].nunique():,}")
    
    st.markdown("#### 🏆 Ranking Fuerza de Ventas")
    if not df_mes.empty:
        vend_stats = df_mes.groupby('vendedor', as_index=False)['neto'].sum().sort_values('neto', ascending=True)
        fig_vend = px.bar(vend_stats, x='neto', y='vendedor', orientation='h', text_auto='.2s')
        fig_vend.update_traces(marker_color='#2ecc71')
        st.plotly_chart(fig_vend, use_container_width=True)

with tabs[1]:
    st.markdown("#### 🧠 Rentabilidad por Producto (Top 50)")
    if not df_mes.empty:
        prod_stats = df_mes.groupby(['sku', 'descripcion']).agg(
            Venta=('neto', 'sum'), Costo=('costo', 'sum'), Utilidad=('margen', 'sum'), Unidades=('cant', 'sum')
        ).reset_index()
        prod_stats['%_Margen'] = (prod_stats['Utilidad'] / prod_stats['Venta'] * 100).fillna(0)
        
        prod_top = prod_stats.sort_values('Venta', ascending=False).head(50)
        st.dataframe(prod_top.style.format({
            'Venta': '${:,.0f}', 'Costo': '${:,.0f}', 'Utilidad': '${:,.0f}', '%_Margen': '{:.1f}%', 'Unidades': '{:,.0f}'
        }).background_gradient(subset=['%_Margen'], cmap='Blues'), use_container_width=True, hide_index=True)

with tabs[2]:
    st.markdown("#### 📍 Penetración por Comuna (Distribución Geográfica)")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        zona_stats = zona_stats[zona_stats['neto'] > 0]
        fig_zona = px.pie(zona_stats, values='neto', names='comuna', hole=0.4)
        st.plotly_chart(fig_zona, use_container_width=True)