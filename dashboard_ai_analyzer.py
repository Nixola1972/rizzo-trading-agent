"""
Dashboard per Analisi Prompt AI
Permette di visualizzare, esportare e analizzare i prompt e le risposte AI.
"""

import streamlit as st
import pandas as pd
import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configurazione pagina
st.set_page_config(
    page_title="AI Prompt Analyzer",
    page_icon="🧠",
    layout="wide"
)

# Connessione database
def get_db_connection():
    """Crea una nuova connessione al database"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        st.error("DATABASE_URL non configurato nel file .env")
        st.stop()
    return psycopg2.connect(database_url)

def query_db(query, params=None):
    """Esegue una query e restituisce un DataFrame"""
    conn = None
    try:
        conn = get_db_connection()
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Errore query database: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

# ===== HEADER =====
st.title("🧠 AI Prompt Analyzer")
st.markdown("Analizza i prompt e le risposte dell'AI per ottimizzare le decisioni di trading")
st.markdown("---")

# ===== FILTRI =====
col1, col2, col3 = st.columns(3)

with col1:
    symbol_filter = st.selectbox(
        "Simbolo",
        ["Tutti", "BTC", "ETH", "SOL"],
        index=0
    )

with col2:
    hours_filter = st.selectbox(
        "Periodo",
        [6, 12, 24, 48, 72, 168],
        index=2,
        format_func=lambda x: f"{x} ore" if x < 48 else f"{x//24} giorni"
    )

with col3:
    limit_filter = st.number_input("Max risultati", min_value=1, max_value=100, value=20)

# ===== QUERY PROMPT LOGS =====
where_clause = ""
if symbol_filter != "Tutti":
    where_clause = f"AND symbol = '{symbol_filter}'"

query = f"""
SELECT
    id,
    created_at,
    symbol,
    full_prompt,
    ai_raw_response,
    parsed_decision,
    model_used,
    duration_ms
FROM ai_prompt_logs
WHERE created_at > NOW() - INTERVAL '{hours_filter} hours'
{where_clause}
ORDER BY created_at DESC
LIMIT {limit_filter}
"""

df = query_db(query)

if df.empty:
    st.warning("Nessun log AI trovato. I log verranno creati dopo il prossimo ciclo AI.")
    st.info("La tabella ai_prompt_logs potrebbe non esistere ancora. Esegui la migrazione del database.")
    st.stop()

# ===== TABELLA RIASSUNTIVA =====
st.subheader("📋 Log AI Recenti")

# Prepara dati per tabella
df['time'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m %H:%M')
df['decision'] = df['parsed_decision'].apply(
    lambda x: f"{x.get('operation', '?')} {x.get('direction', '')}" if isinstance(x, dict) else "?"
)
df['duration'] = df['duration_ms'].apply(lambda x: f"{x}ms" if x else "?")

# Mostra tabella compatta
display_df = df[['time', 'symbol', 'decision', 'model_used', 'duration']].copy()
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.markdown("---")

# ===== DETTAGLIO SINGOLO LOG =====
st.subheader("🔍 Dettaglio Log")

selected_id = st.selectbox(
    "Seleziona log da analizzare",
    df['id'].tolist(),
    format_func=lambda x: f"#{x} - {df[df['id']==x]['time'].values[0]} - {df[df['id']==x]['symbol'].values[0]} - {df[df['id']==x]['decision'].values[0]}"
)

if selected_id:
    selected = df[df['id'] == selected_id].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Simbolo", selected['symbol'])
    with col2:
        st.metric("Durata API", f"{selected['duration_ms']}ms")

    # ===== PROMPT INPUT =====
    st.markdown("### 📝 Prompt Inviato all'AI")

    prompt_text = selected['full_prompt']

    # Box copiabile
    st.text_area(
        "Prompt (clicca e Ctrl+A per selezionare tutto)",
        prompt_text,
        height=300,
        key="prompt_input"
    )

    # ===== RISPOSTA AI =====
    st.markdown("### 🤖 Risposta AI")

    response_text = selected['ai_raw_response'] or "Nessuna risposta"

    st.text_area(
        "Risposta AI (clicca e Ctrl+A per selezionare tutto)",
        response_text,
        height=150,
        key="ai_response"
    )

    # ===== DECISIONE PARSATA =====
    st.markdown("### ✅ Decisione Parsata")
    st.json(selected['parsed_decision'])

st.markdown("---")

# ===== TEMPLATE PER ANALISI ESTERNA =====
st.subheader("📤 Template per Analisi Esterna")

st.markdown("""
Copia questi template per far analizzare il prompt da un'altra AI (es. ChatGPT, Claude).
""")

if selected_id:
    selected = df[df['id'] == selected_id].iloc[0]

    # Template 1: Analisi Prompt
    analysis_template_1 = f"""Questo è il prompt di ingresso di un bot AI specializzato in trading di criptovalute.

Analizza il prompt e dimmi:
1. Se secondo te ha spazi di miglioramento
2. Se i dati contenuti sono sufficienti per un'attenta analisi
3. Se la struttura del prompt è chiara e ben organizzata
4. Eventuali informazioni mancanti che potrebbero migliorare le decisioni

=== PROMPT ===
{selected['full_prompt']}
=== FINE PROMPT ==="""

    st.markdown("#### 1️⃣ Template Analisi Prompt")
    st.text_area(
        "Copia questo per analizzare il prompt",
        analysis_template_1,
        height=200,
        key="template_1"
    )

    # Template 2: Analisi Risposta
    analysis_template_2 = f"""Questa è la risposta dell'AI specialista in trading di criptovalute al prompt precedente.

Analizza la risposta e dimmi:
1. Se le conclusioni raggiunte sono corrette e logiche
2. Se l'AI ha considerato tutti i fattori importanti
3. Se la decisione ({selected['parsed_decision'].get('operation', '?')} {selected['parsed_decision'].get('direction', '')}) è coerente con i dati forniti
4. Se si debba modificare il prompt per raggiungere migliori risultati

=== RISPOSTA AI ===
{selected['ai_raw_response']}
=== FINE RISPOSTA ===

=== DECISIONE FINALE ===
{selected['parsed_decision']}
=== FINE DECISIONE ==="""

    st.markdown("#### 2️⃣ Template Analisi Risposta")
    st.text_area(
        "Copia questo per analizzare la risposta",
        analysis_template_2,
        height=200,
        key="template_2"
    )

    # Template Completo
    full_template = f"""Sto analizzando un bot AI di trading criptovalute. Ti mostro sia il prompt che la risposta.

=== PARTE 1: PROMPT INVIATO ALL'AI ===
{selected['full_prompt']}
=== FINE PROMPT ===

=== PARTE 2: RISPOSTA DELL'AI ===
{selected['ai_raw_response']}
=== FINE RISPOSTA ===

=== PARTE 3: DECISIONE PARSATA ===
{selected['parsed_decision']}
=== FINE DECISIONE ===

Per favore analizza:
1. Il prompt è ben strutturato? Mancano informazioni importanti?
2. La risposta dell'AI è logica e coerente con i dati?
3. La decisione finale è corretta?
4. Come si potrebbe migliorare il sistema?"""

    st.markdown("#### 3️⃣ Template Completo (Prompt + Risposta)")
    st.text_area(
        "Copia questo per un'analisi completa",
        full_template,
        height=200,
        key="template_full"
    )

# ===== CONFRONTO TRA SIMBOLI =====
st.markdown("---")
st.subheader("📊 Confronto per Simbolo")

# Raggruppa per simbolo negli ultimi log
comparison_query = f"""
SELECT
    symbol,
    COUNT(*) as total_decisions,
    AVG(duration_ms) as avg_duration,
    COUNT(CASE WHEN parsed_decision->>'operation' = 'open' THEN 1 END) as opens,
    COUNT(CASE WHEN parsed_decision->>'operation' = 'close' THEN 1 END) as closes,
    COUNT(CASE WHEN parsed_decision->>'operation' = 'hold' THEN 1 END) as holds
FROM ai_prompt_logs
WHERE created_at > NOW() - INTERVAL '{hours_filter} hours'
GROUP BY symbol
ORDER BY symbol
"""

comparison_df = query_db(comparison_query)

if not comparison_df.empty:
    col1, col2, col3 = st.columns(3)

    for idx, row in comparison_df.iterrows():
        col = [col1, col2, col3][idx % 3]
        with col:
            st.markdown(f"### {row['symbol']}")
            st.metric("Decisioni", int(row['total_decisions']))
            st.metric("Avg Duration", f"{int(row['avg_duration'] or 0)}ms")
            st.write(f"Open: {int(row['opens'])} | Close: {int(row['closes'])} | Hold: {int(row['holds'])}")

st.markdown("---")
st.caption("Dashboard AI Prompt Analyzer - Per debug e ottimizzazione del sistema di trading")
