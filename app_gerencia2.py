import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import calendar
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURACIÓN CORPORATIVA Y NÚCLEO
# ==========================================
st.set_page_config(page_title="DICOS BI - Test 2022+", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #f4f6f9; }
    h1, h2, h3 { color: #003366 !important; }
    [data-testid="stMetricValue"] { color: #004080; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

BRIDGE_URL = 'https://dicos.cl/db_bridge.php'
TOKEN_SECRETO = 'Oscar2026!'
FECHA_CORTE = '2022-01-01' # <-- EL FILTRO MAESTRO

@st.cache_data(ttl=1800, show_spinner=False)
def extraer_tabla_desde_2022(query, nombre_tabla, chunk_size=2500):
    """Extrae datos en bloques para no asfixiar el hosting."""
    offset = 0
    df_completo = pd.DataFrame()
    status = st.empty()
    
    while True:
        status.info(f"📥 Sincronizando {nombre_tabla} desde 2022... (Filas: {offset} a {offset + chunk_size})")
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
            else:
                st.error(f"Error {response.status_code} en {nombre_tabla}")
                break
        except Exception as e:
            st.error(f"Micro-corte de red descargando {nombre_tabla}: {e}")
            break
            
    status.empty()
    return df_completo

# ==========================================
# 2. EXTRACCIÓN EN VIVO (SIN JOINS EN MYSQL)
# ==========================================
st.sidebar.title("⚙️ Panel de Control")
st.sidebar.caption("Datos en Vivo (Desde 2022)")

# Consultas simples: MySQL solo lee, Python hace el resto.
q_cab = f"SELECT FANUMERO, FATDOCTO, FAFECHA as fecha, FACOMCLI as comuna, FACODVEND as vendedor FROM v_cabecera WHERE FAFECHA >= '{FECHA_CORTE}'"
q_det = f"SELECT DENUMFAC, DETDOCTO, FECDOCU, DECODPRO as sku, DECANTIDAD as cant FROM v_detalle WHERE FECDOCU >= '{FECHA_CORTE}'"
q_prod = "SELECT PRCODIGO, PRDESCRIP as descripcion, PREC1, PRECOM FROM producto"

with st.spinner("Conectando al Data Warehouse DICOS..."):
    df_cab = extraer_tabla_desde_2022(q_cab, "Cabeceras")
    df_det = extraer_tabla_desde_2022(q_det, "Detalles")
    df_prod = extraer_tabla_desde_2022(q_prod, "Catálogo")

# ==========================================
# 3. ENSAMBLAJE DEL DATA WAREHOUSE (PANDAS)
# ==========================================
if df_cab.empty or df_det.empty:
    st.error("No se pudieron cargar los datos base.")
    st.stop()

with st.spinner("🧠 Procesando Inteligencia de Negocios en la Nube..."):
    # Cruces
    df_temp = pd.merge(df_det, df_prod, left_on='sku', right_on='PRCODIGO', how='inner')
    df_final = pd.merge(df_cab, df_temp, left_on=['FANUMERO', 'FATDOCTO'], right_on=['DENUMFAC', 'DETDOCTO'], how='inner')
    
    # Limpieza y fechas
    df_final['fecha'] = pd.to_datetime(df_final['fecha'], errors='coerce')
    df_final['año'] = df_final['fecha'].dt.year
    df_final['mes'] = df_final['fecha'].dt.month
    
    # Matemáticas
    cols_num = ['cant', 'PREC1', 'PRECOM']
    df_final[cols_num] = df_final[cols_num].apply(pd.to_numeric, errors='coerce').fillna(0)
    df_final['neto'] = df_final['cant'] * df_final['PREC1']
    df_final['costo'] = df_final['cant'] * df_final['PRECOM']
    df_final['margen'] = df_final['neto'] - df_final['costo']
    
    for col in ['vendedor', 'comuna', 'descripcion']:
        df_final[col] = df_final[col].fillna('Sin Registro').astype(str)

# ==========================================
# 4. INTERFAZ GERENCIAL (LOS FILTROS DE ÓSCAR)
# ==========================================
st.title("📊 DICOS SpA - Panel de Dirección")

periodos = sorted(df_final['año'].dropna().unique())
anio_sel = st.sidebar.selectbox("Año Principal", periodos, index=len(periodos)-1 if periodos else 0)
mes_sel = st.sidebar.selectbox("Mes de Foco", list(range(1, 13)), index=datetime.now().month - 1)

# Filtrado dinámico
df_anio = df_final[df_final['año'] == anio_sel]
df_mes = df_anio[df_anio['mes'] == mes_sel]

venta_neta_anio = df_anio['neto'].sum()
margen_anio = df_anio['margen'].sum()
eficiencia_anio = (margen_anio / venta_neta_anio * 100) if venta_neta_anio > 0 else 0

st.markdown(f"### 📈 Resumen Anual Consolidado ({anio_sel})")
m1, m2, m3 = st.columns(3)
m1.metric("Ventas Netas Anuales", f"${venta_neta_anio:,.0f}")
m2.metric("Margen Bruto Anual", f"${margen_anio:,.0f}")
m3.metric("Eficiencia Promedio", f"{eficiencia_anio:.1f}%")

st.divider()

tabs = st.tabs(["🌐 Desempeño Comercial", "📍 Zonas y Segmentos"])

with tabs[0]:
    venta_neta_mes = df_mes['neto'].sum()
    st.markdown(f"### Detalle del Mes: {mes_sel}/{anio_sel}")
    st.metric("Venta Neta del Mes", f"${venta_neta_mes:,.0f}")
    
    st.markdown("#### 🏆 Desempeño por Vendedor")
    if not df_mes.empty:
        vend_stats = df_mes.groupby('vendedor', as_index=False)['neto'].sum().sort_values('neto', ascending=True)
        fig_vend = px.bar(vend_stats, x='neto', y='vendedor', orientation='h', title="Venta Neta por Vendedor")
        fig_vend.update_traces(marker_color='#2ecc71')
        st.plotly_chart(fig_vend, use_container_width=True)

with tabs[1]:
    st.markdown("#### 📍 Penetración por Zonas (Comuna)")
    if not df_mes.empty:
        zona_stats = df_mes.groupby('comuna', as_index=False)['neto'].sum()
        zona_stats = zona_stats[zona_stats['neto'] > 0]
        fig_zona = px.pie(zona_stats, values='neto', names='comuna', hole=0.4)
        st.plotly_chart(fig_zona, use_container_width=True)