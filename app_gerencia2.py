import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import json
import calendar
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# --- CONFIGURACIÓN DE CONEXIÓN ---
BRIDGE_URL = 'https://dicos.cl/db_bridge.php'
TOKEN_SECRETO = 'Oscar2026!'

@st.cache_data(ttl=600, show_spinner=False)
def extraer_datos_v_tablas(query_base, chunk_size=1500):
    """Extrae datos en bloques de 1,500 filas para proteger la RAM del hosting."""
    offset = 0
    df_completo = pd.DataFrame()
    
    status_text = st.empty()
    
    while True:
        status_text.info(f"⏳ Sincronizando bloque de datos: {offset} a {offset + chunk_size}...")
        
        query_paginada = f"{query_base} LIMIT {chunk_size} OFFSET {offset}"
        payload = {"token": TOKEN_SECRETO, "accion": "query_dashboard", "query": query_paginada}
        
        try:
            paquete_hex = json.dumps(payload).encode('utf-8').hex()
            response = requests.post(BRIDGE_URL, data={'paquete': paquete_hex}, timeout=60)
            
            if response.status_code == 200:
                res_json = response.json()
                data = res_json.get("data", [])
                
                if not data:
                    break 
                
                df_completo = pd.concat([df_completo, pd.DataFrame(data)], ignore_index=True)
                if len(data) < chunk_size:
                    break
                offset += chunk_size
            else:
                st.error(f"Error Servidor: {response.status_code}")
                break
        except Exception as e:
            st.error(f"Error de red: {e}")
            break
            
    status_text.empty()
    return df_completo

# --- INTERFAZ DEL DASHBOARD ---
st.set_page_config(page_title="DICOS BI - Dirección", page_icon="📊", layout="wide")

st.title("📊 DICOS SpA - Dashboard de Gestión Histórica")

# Filtros en Barra Lateral
st.sidebar.header("⚙️ Filtros")
anio_sel = st.sidebar.selectbox("Año", [2024, 2025, 2026], index=1)
mes_sel = st.sidebar.selectbox("Mes", list(range(1, 13)), index=datetime.now().month - 1)

ultimo_dia = calendar.monthrange(anio_sel, mes_sel)[1]
f_ini, f_fin = f"{anio_sel}-{mes_sel:02d}-01", f"{anio_sel}-{mes_sel:02d}-{ultimo_dia}"

# Consulta SQL a las Tablas Maestras
query = f"""
    SELECT c.FAFECHA as fecha, c.FANUMERO as numero, c.FACOMCLI as comuna, 
           c.FACODVEND as vendedor, d.DECODPRO as sku, p.PRDESCRIP as descripcion,
           d.DECANTIDAD as cant, (d.DECANTIDAD * p.PREC1) as neto, 
           (d.DECANTIDAD * p.PRECOM) as costo
    FROM v_cabecera c
    INNER JOIN v_detalle d ON c.FANUMERO = d.DENUMFAC AND c.FATDOCTO = d.DETDOCTO
    INNER JOIN producto p ON d.DECODPRO = p.PRCODIGO
    WHERE c.FAFECHA BETWEEN '{f_ini}' AND '{f_fin}'
      AND d.FECDOCU BETWEEN '{f_ini}' AND '{f_fin}'
"""

# Ejecución
df = extraer_datos_v_tablas(query)

if not df.empty:
    # Limpieza de datos
    df[['neto', 'costo', 'cant']] = df[['neto', 'costo', 'cant']].apply(pd.to_numeric, errors='coerce').fillna(0)
    df['margen'] = df['neto'] - df['costo']
    
    # KPIs Rápidos
    k1, k2, k3 = st.columns(3)
    k1.metric("Venta Neta", f"${df['neto'].sum():,.0f}")
    k2.metric("Margen Real", f"${df['margen'].sum():,.0f}")
    k3.metric("Documentos", f"{df['numero'].nunique():,}")
    
    st.divider()
    
    # Visualización
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏆 Ranking de Vendedores")
        rank = df.groupby('vendedor')['neto'].sum().sort_values(ascending=True)
        st.bar_chart(rank)
    with col2:
        st.subheader("📍 Venta por Comuna")
        st.plotly_chart(px.pie(df, values='neto', names='comuna'), use_container_width=True)

    st.subheader("📋 Detalle de v_detalle (Consolidado)")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No hay datos para el periodo seleccionado.")