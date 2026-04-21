import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import json
import calendar
from datetime import datetime

# --- CONEXIÓN AL BRIDGE ---
BRIDGE_URL = 'https://dicos.cl/db_bridge.php'
TOKEN_SECRETO = 'Oscar2026!'

@st.cache_data(ttl=600, show_spinner=False)
def extraer_tabla_simple(query, nombre_tabla):
    """Extrae datos con paginación pero SIN JOINs para no ahogar a MySQL"""
    offset = 0
    chunk_size = 2000
    df_completo = pd.DataFrame()
    status = st.empty()
    
    while True:
        status.info(f"📥 Descargando {nombre_tabla} (Bloque {offset} a {offset + chunk_size})...")
        q_paginada = f"{query} LIMIT {chunk_size} OFFSET {offset}"
        payload = {"token": TOKEN_SECRETO, "accion": "query_dashboard", "query": q_paginada}
        
        try:
            paquete_hex = json.dumps(payload).encode('utf-8').hex()
            response = requests.post(BRIDGE_URL, data={'paquete': paquete_hex}, timeout=60)
            
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
            st.error(f"Caída descargando {nombre_tabla}: {e}")
            break
            
    status.empty()
    return df_completo

# --- INTERFAZ ---
st.set_page_config(page_title="DICOS BI", page_icon="📊", layout="wide")
st.title("📊 DICOS SpA - Panel de Gestión (Motor Nube)")

# --- FILTROS ---
st.sidebar.header("⚙️ Filtros")
anio_sel = st.sidebar.selectbox("Año", [2024, 2025, 2026], index=1)
mes_sel = st.sidebar.selectbox("Mes", list(range(1, 13)), index=datetime.now().month - 1)

ultimo_dia = calendar.monthrange(anio_sel, mes_sel)[1]
f_ini, f_fin = f"{anio_sel}-{mes_sel:02d}-01", f"{anio_sel}-{mes_sel:02d}-{ultimo_dia}"

# --- EXTRACCIÓN DIVIDIDA (LA MAGIA OCURRE AQUÍ) ---
# Pedimos a MySQL cosas muy simples, sin cruces pesados.
q_cab = f"SELECT FANUMERO, FATDOCTO, FAFECHA as fecha, FACOMCLI as comuna, FACODVEND as vendedor FROM v_cabecera WHERE FAFECHA BETWEEN '{f_ini}' AND '{f_fin}'"
q_det = f"SELECT DENUMFAC, DETDOCTO, DECODPRO as sku, DECANTIDAD as cant FROM v_detalle WHERE FECDOCU BETWEEN '{f_ini}' AND '{f_fin}'"
q_prod = "SELECT PRCODIGO, PRDESCRIP as descripcion, PREC1, PRECOM FROM producto"

# Descargamos
df_cab = extraer_tabla_simple(q_cab, "Cabeceras")
df_det = extraer_tabla_simple(q_det, "Detalles")
df_prod = extraer_tabla_simple(q_prod, "Catálogo")

# --- PROCESAMIENTO EN LA NUBE (PANDAS) ---
if not df_cab.empty and not df_det.empty and not df_prod.empty:
    with st.spinner("🧠 Ensamblando Data Warehouse en la Nube..."):
        # Cruzamos Detalle con Catálogo
        df_temp = pd.merge(df_det, df_prod, left_on='sku', right_on='PRCODIGO', how='inner')
        # Cruzamos con Cabecera
        df_final = pd.merge(df_cab, df_temp, left_on=['FANUMERO', 'FATDOCTO'], right_on=['DENUMFAC', 'DETDOCTO'], how='inner')
        
        # Matemáticas
        df_final[['cant', 'PREC1', 'PRECOM']] = df_final[['cant', 'PREC1', 'PRECOM']].apply(pd.to_numeric, errors='coerce').fillna(0)
        df_final['neto'] = df_final['cant'] * df_final['PREC1']
        df_final['costo'] = df_final['cant'] * df_final['PRECOM']
        df_final['margen'] = df_final['neto'] - df_final['costo']
        
        # Limpieza de nulos para gráficos
        for col in ['vendedor', 'comuna', 'descripcion']:
            df_final[col] = df_final[col].fillna('Sin Registro').astype(str)

    # --- DASHBOARD ---
    st.success("✅ Extracción y cruce exitoso.")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Venta Neta", f"${df_final['neto'].sum():,.0f}")
    k2.metric("Margen Real", f"${df_final['margen'].sum():,.0f}")
    k3.metric("Documentos", f"{df_final['FANUMERO'].nunique():,}")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏆 Vendedores")
        st.plotly_chart(px.bar(df_final.groupby('vendedor', as_index=False)['neto'].sum().sort_values('neto'), x='neto', y='vendedor', orientation='h'), use_container_width=True)
    with c2:
        st.subheader("📍 Comunas")
        st.plotly_chart(px.pie(df_final, values='neto', names='comuna'), use_container_width=True)
else:
    st.warning("⚠️ Faltan datos en una de las tablas para este mes.")