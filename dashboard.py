import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Configurazione pagina
st.set_page_config(
    page_title="Rizzo Trading Bot Dashboard",
    page_icon="🤖",
    layout="wide"
)

# Connessione database
@st.cache_resource
def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        st.error("DATABASE_URL non configurato nel file .env")
        st.stop()
    return psycopg2.connect(database_url)

def query_db(query, params=None):
    """Esegue una query e restituisce un DataFrame"""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Errore query database: {e}")
        return pd.DataFrame()

# Header
st.title("🤖 Rizzo Trading Bot Dashboard")
st.markdown("---")

# Metriche principali
col1, col2, col3, col4 = st.columns(4)

# Total Account Value
try:
    latest_snapshot = query_db("""
        SELECT balance_usd, created_at
        FROM account_snapshots
        ORDER BY created_at DESC
        LIMIT 1
    """)

    if not latest_snapshot.empty:
        current_balance = float(latest_snapshot['balance_usd'].iloc[0])
        col1.metric("💰 Account Value", f"${current_balance:,.2f}")
    else:
        col1.metric("💰 Account Value", "N/A")
except Exception as e:
    col1.metric("💰 Account Value", "Error")

# Total Operations
try:
    total_ops = query_db("SELECT COUNT(*) as count FROM bot_operations")
    if not total_ops.empty:
        col2.metric("📊 Total Operations", int(total_ops['count'].iloc[0]))
    else:
        col2.metric("📊 Total Operations", "0")
except:
    col2.metric("📊 Total Operations", "Error")

# Open Positions
try:
    open_positions_query = query_db("""
        SELECT COUNT(DISTINCT op.symbol) as count
        FROM open_positions op
        JOIN account_snapshots snap ON op.snapshot_id = snap.id
        WHERE snap.id = (SELECT MAX(id) FROM account_snapshots)
    """)
    if not open_positions_query.empty:
        col3.metric("📈 Open Positions", int(open_positions_query['count'].iloc[0]))
    else:
        col3.metric("📈 Open Positions", "0")
except:
    col3.metric("📈 Open Positions", "Error")

# Bot Status
try:
    last_operation = query_db("""
        SELECT created_at
        FROM bot_operations
        ORDER BY created_at DESC
        LIMIT 1
    """)

    if not last_operation.empty:
        last_time = pd.to_datetime(last_operation['created_at'].iloc[0])
        now = datetime.now(last_time.tzinfo)
        diff = (now - last_time).total_seconds() / 60

        if diff < 30:
            col4.metric("🟢 Status", "Active", f"{int(diff)}m ago")
        else:
            col4.metric("🟡 Status", "Idle", f"{int(diff)}m ago")
    else:
        col4.metric("⚪ Status", "No Data")
except:
    col4.metric("❌ Status", "Error")

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Performance", "💼 Operations", "🎯 AI Decisions", "⚙️ Settings"])

with tab1:
    st.subheader("Account Balance Over Time")

    # Grafico balance nel tempo
    try:
        balance_data = query_db("""
            SELECT created_at, balance_usd
            FROM account_snapshots
            ORDER BY created_at ASC
        """)

        if not balance_data.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=balance_data['created_at'],
                y=balance_data['balance_usd'],
                mode='lines+markers',
                name='Balance',
                line=dict(color='#00ff00', width=2),
                marker=dict(size=6)
            ))

            fig.update_layout(
                title="Account Balance History",
                xaxis_title="Date",
                yaxis_title="Balance (USD)",
                hovermode='x unified',
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nessun dato disponibile ancora. Il bot deve eseguire almeno un ciclo.")
    except Exception as e:
        st.error(f"Errore nel caricamento dei dati: {e}")

    # P&L per symbol
    st.subheader("P&L by Symbol")

    col_left, col_right = st.columns(2)

    with col_left:
        try:
            pnl_by_symbol = query_db("""
                SELECT
                    symbol,
                    SUM(pnl_usd) as total_pnl,
                    COUNT(*) as num_positions
                FROM open_positions op
                JOIN account_snapshots snap ON op.snapshot_id = snap.id
                GROUP BY symbol
                ORDER BY total_pnl DESC
            """)

            if not pnl_by_symbol.empty:
                fig_pnl = px.bar(
                    pnl_by_symbol,
                    x='symbol',
                    y='total_pnl',
                    title='Total P&L by Symbol',
                    color='total_pnl',
                    color_continuous_scale=['red', 'yellow', 'green']
                )
                st.plotly_chart(fig_pnl, use_container_width=True)
            else:
                st.info("Nessuna posizione registrata")
        except Exception as e:
            st.error(f"Errore: {e}")

    with col_right:
        try:
            operations_by_type = query_db("""
                SELECT
                    operation,
                    COUNT(*) as count
                FROM bot_operations
                GROUP BY operation
            """)

            if not operations_by_type.empty:
                fig_ops = px.pie(
                    operations_by_type,
                    values='count',
                    names='operation',
                    title='Operations Distribution'
                )
                st.plotly_chart(fig_ops, use_container_width=True)
            else:
                st.info("Nessuna operazione registrata")
        except Exception as e:
            st.error(f"Errore: {e}")

with tab2:
    st.subheader("Recent Operations")

    # Filtri
    col_filter1, col_filter2, col_filter3 = st.columns(3)

    with col_filter1:
        operation_filter = st.selectbox(
            "Operation Type",
            ["All", "open", "close", "hold"]
        )

    with col_filter2:
        symbol_filter = st.selectbox(
            "Symbol",
            ["All", "BTC", "ETH", "SOL"]
        )

    with col_filter3:
        limit = st.number_input("Show Last N", min_value=10, max_value=1000, value=50)

    # Query operations
    try:
        where_clauses = []
        if operation_filter != "All":
            where_clauses.append(f"operation = '{operation_filter}'")
        if symbol_filter != "All":
            where_clauses.append(f"symbol = '{symbol_filter}'")

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        operations = query_db(f"""
            SELECT
                id,
                created_at,
                operation,
                symbol,
                direction,
                target_portion_of_balance,
                leverage,
                reason
            FROM bot_operations
            {where_sql}
            ORDER BY created_at DESC
            LIMIT {limit}
        """)

        if not operations.empty:
            # Formatta il dataframe
            operations['created_at'] = pd.to_datetime(operations['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
            operations['target_%'] = (operations['target_portion_of_balance'] * 100).round(2)

            # Colorizza operations
            def highlight_operation(row):
                if row['operation'] == 'open':
                    return ['background-color: rgba(0, 255, 0, 0.1)'] * len(row)
                elif row['operation'] == 'close':
                    return ['background-color: rgba(255, 0, 0, 0.1)'] * len(row)
                else:
                    return ['background-color: rgba(128, 128, 128, 0.05)'] * len(row)

            styled_ops = operations.style.apply(highlight_operation, axis=1)
            st.dataframe(styled_ops, use_container_width=True, height=600)

            # Download CSV
            csv = operations.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"trading_operations_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("Nessuna operazione trovata con i filtri selezionati")
    except Exception as e:
        st.error(f"Errore nel caricamento delle operazioni: {e}")

with tab3:
    st.subheader("AI Decision Analysis")

    # Ultime decisioni AI
    try:
        ai_decisions = query_db("""
            SELECT
                bo.created_at,
                bo.operation,
                bo.symbol,
                bo.direction,
                bo.leverage,
                bo.reason,
                ac.system_prompt
            FROM bot_operations bo
            LEFT JOIN ai_contexts ac ON bo.context_id = ac.id
            ORDER BY bo.created_at DESC
            LIMIT 20
        """)

        if not ai_decisions.empty:
            for idx, row in ai_decisions.iterrows():
                with st.expander(
                    f"🤖 {row['created_at']} - {row['operation'].upper()} {row['symbol']} ({row['direction']})",
                    expanded=(idx==0)
                ):
                    col_a, col_b = st.columns([2, 1])

                    with col_a:
                        st.markdown(f"**Reason:** {row['reason']}")
                        if pd.notna(row['leverage']):
                            st.markdown(f"**Leverage:** {row['leverage']}x")

                    with col_b:
                        if row['operation'] == 'open':
                            st.success("OPEN POSITION")
                        elif row['operation'] == 'close':
                            st.error("CLOSE POSITION")
                        else:
                            st.info("HOLD")

                    if pd.notna(row['system_prompt']):
                        with st.expander("📄 View Full System Prompt"):
                            st.text(row['system_prompt'][:2000] + "..." if len(str(row['system_prompt'])) > 2000 else row['system_prompt'])
        else:
            st.info("Nessuna decisione AI registrata")
    except Exception as e:
        st.error(f"Errore: {e}")

with tab4:
    st.subheader("Bot Configuration")

    # Mostra env vars (senza valori sensibili)
    st.markdown("### Environment Variables Status")

    env_vars = {
        "AI_PROVIDER": os.getenv("AI_PROVIDER", "Not Set"),
        "OPENROUTER_MODEL": os.getenv("OPENROUTER_MODEL", "Not Set"),
        "TESTNET": os.getenv("TESTNET", "Not Set"),
        "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else "Not Set",
        "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else "Not Set",
        "OPENROUTER_API_KEY": "***" if os.getenv("OPENROUTER_API_KEY") else "Not Set",
    }

    df_env = pd.DataFrame(list(env_vars.items()), columns=["Variable", "Value"])
    st.dataframe(df_env, use_container_width=True)

    st.markdown("### Database Tables")
    try:
        tables = query_db("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        if not tables.empty:
            st.dataframe(tables, use_container_width=True)
        else:
            st.warning("Nessuna tabella trovata")
    except Exception as e:
        st.error(f"Errore: {e}")

# Refresh button
st.markdown("---")
if st.button("🔄 Refresh Data"):
    st.cache_resource.clear()
    st.rerun()

# Footer
st.markdown("---")
st.caption(f"🤖 Rizzo Trading Bot Dashboard | Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
