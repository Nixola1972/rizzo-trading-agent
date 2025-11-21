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
    page_title="Trading Agent Dashboard",
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
st.title("🤖 Trading Agent Dashboard")
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Performance", "💼 Operations", "📈 Open Positions", "🎯 AI Decisions", "⚙️ Settings"])

with tab1:
    st.subheader("Account Balance Over Time")

    # Selezione periodo ✅ NUOVO!
    col_period1, col_period2 = st.columns([1, 4])
    with col_period1:
        period = st.selectbox(
            "📅 Period",
            ["1 Day", "3 Days", "7 Days", "30 Days", "All Time"],
            index=2  # Default: 7 Days
        )

    # Calcola data inizio
    period_map = {
        "1 Day": 1,
        "3 Days": 3,
        "7 Days": 7,
        "30 Days": 30,
        "All Time": None
    }

    days = period_map[period]

    # Query balance con filtro periodo
    try:
        if days:
            balance_data = query_db(f"""
                SELECT created_at, balance_usd
                FROM account_snapshots
                WHERE created_at > NOW() - INTERVAL '{days} days'
                ORDER BY created_at ASC
            """)
        else:
            balance_data = query_db("""
                SELECT created_at, balance_usd
                FROM account_snapshots
                ORDER BY created_at ASC
            """)

        if not balance_data.empty:
            # Calcola P&L %
            initial_balance = balance_data['balance_usd'].iloc[0]
            final_balance = balance_data['balance_usd'].iloc[-1]
            pnl = final_balance - initial_balance
            pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else 0

            # Mostra P&L
            col_pnl1, col_pnl2 = st.columns(2)
            with col_pnl1:
                st.metric("💵 P&L (Period)", f"${pnl:,.2f}", f"{pnl_pct:+.2f}%")
            with col_pnl2:
                win_color = "green" if pnl >= 0 else "red"
                st.markdown(f"<h3 style='color: {win_color};'>{'📈 Profit' if pnl >= 0 else '📉 Loss'}</h3>", unsafe_allow_html=True)

            # Grafico
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=balance_data['created_at'],
                y=balance_data['balance_usd'],
                mode='lines+markers',
                name='Balance',
                line=dict(color='#00ff00' if pnl >= 0 else '#ff0000', width=2),
                marker=dict(size=6),
                fill='tozeroy',
                fillcolor='rgba(0,255,0,0.1)' if pnl >= 0 else 'rgba(255,0,0,0.1)'
            ))

            fig.update_layout(
                title=f"Account Balance History ({period})",
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
                    COUNT(*) as num_positions,
                    AVG(pnl_usd) as avg_pnl
                FROM open_positions op
                JOIN account_snapshots snap ON op.snapshot_id = snap.id
                WHERE pnl_usd IS NOT NULL
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
                    color_continuous_scale=['red', 'yellow', 'green'],
                    hover_data=['num_positions', 'avg_pnl']
                )
                st.plotly_chart(fig_pnl, use_container_width=True)

                # Tabella con dettagli
                pnl_by_symbol['avg_pnl'] = pnl_by_symbol['avg_pnl'].round(2)
                pnl_by_symbol['total_pnl'] = pnl_by_symbol['total_pnl'].round(2)
                st.dataframe(pnl_by_symbol, use_container_width=True)
            else:
                st.info("Nessuna posizione con P&L registrato")
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
                    title='Operations Distribution',
                    color_discrete_map={
                        'open': '#00ff00',
                        'close': '#ff0000',
                        'hold': '#808080'
                    }
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

    # Query operations ✅ FIXATO!
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
                raw_payload->>'reason' as reason
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
    st.subheader("📈 Open Positions with P&L")

    # Posizioni aperte correnti ✅ NUOVO!
    try:
        open_positions = query_db("""
            SELECT
                op.symbol,
                op.side,
                op.size,
                op.entry_price,
                op.mark_price,
                op.pnl_usd,
                op.leverage,
                snap.created_at as last_update
            FROM open_positions op
            JOIN account_snapshots snap ON op.snapshot_id = snap.id
            WHERE snap.id = (SELECT MAX(id) FROM account_snapshots)
            AND op.size > 0
            ORDER BY ABS(op.pnl_usd) DESC
        """)

        if not open_positions.empty:
            st.success(f"🎯 {len(open_positions)} posizioni aperte")

            for idx, pos in open_positions.iterrows():
                pnl = float(pos['pnl_usd']) if pd.notna(pos['pnl_usd']) else 0
                pnl_color = "green" if pnl >= 0 else "red"
                pnl_icon = "📈" if pnl >= 0 else "📉"

                with st.expander(
                    f"{pnl_icon} {pos['symbol']} {pos['side'].upper()} - P&L: ${pnl:,.2f}",
                    expanded=True
                ):
                    col_pos1, col_pos2, col_pos3, col_pos4 = st.columns(4)

                    with col_pos1:
                        st.metric("Size", f"{pos['size']:.4f}")
                        st.metric("Entry", f"${pos['entry_price']:,.2f}")

                    with col_pos2:
                        st.metric("Mark Price", f"${pos['mark_price']:,.2f}")
                        price_change = ((pos['mark_price'] - pos['entry_price']) / pos['entry_price'] * 100) if pos['entry_price'] > 0 else 0
                        st.metric("Price Change", f"{price_change:+.2f}%")

                    with col_pos3:
                        st.metric("P&L", f"${pnl:,.2f}", delta_color="normal")
                        st.metric("Leverage", pos['leverage'])

                    with col_pos4:
                        st.metric("Side", pos['side'].upper())
                        st.caption(f"Updated: {pos['last_update']}")

            # Grafico posizioni
            fig_pos = go.Figure()

            for _, pos in open_positions.iterrows():
                color = 'green' if pos['side'] == 'long' else 'red'
                fig_pos.add_trace(go.Bar(
                    x=[pos['symbol']],
                    y=[pos['pnl_usd']],
                    name=f"{pos['symbol']} {pos['side']}",
                    marker_color=color
                ))

            fig_pos.update_layout(
                title="P&L per Position",
                xaxis_title="Symbol",
                yaxis_title="P&L (USD)",
                showlegend=True,
                height=300
            )
            st.plotly_chart(fig_pos, use_container_width=True)

        else:
            st.info("📊 Nessuna posizione aperta al momento")
            st.caption("Il bot aprirà posizioni automaticamente quando identifica opportunità di trading")

    except Exception as e:
        st.error(f"Errore nel caricamento delle posizioni: {e}")

with tab4:
    st.subheader("🎯 AI Decision Analysis")

    # Ultime decisioni AI ✅ FIXATO!
    try:
        ai_decisions = query_db("""
            SELECT
                bo.id,
                bo.created_at,
                bo.operation,
                bo.symbol,
                bo.direction,
                bo.leverage,
                bo.target_portion_of_balance,
                bo.raw_payload->>'reason' as reason,
                bo.raw_payload as full_payload,
                ac.system_prompt
            FROM bot_operations bo
            LEFT JOIN ai_contexts ac ON bo.context_id = ac.id
            ORDER BY bo.created_at DESC
            LIMIT 50
        """)

        if not ai_decisions.empty:
            st.success(f"📊 {len(ai_decisions)} decisioni AI trovate")

            # Filtro per operazione
            decision_filter = st.selectbox(
                "Filter by Operation",
                ["All", "open", "close", "hold"]
            )

            filtered_decisions = ai_decisions if decision_filter == "All" else ai_decisions[ai_decisions['operation'] == decision_filter]

            for idx, row in filtered_decisions.iterrows():
                # Icon e colore per tipo operazione
                if row['operation'] == 'open':
                    icon = "🟢"
                    color = "green"
                elif row['operation'] == 'close':
                    icon = "🔴"
                    color = "red"
                else:
                    icon = "⚪"
                    color = "gray"

                with st.expander(
                    f"{icon} {row['created_at']} - {row['operation'].upper()} {row['symbol']} ({row['direction']})",
                    expanded=(idx==0)
                ):
                    col_a, col_b = st.columns([3, 1])

                    with col_a:
                        st.markdown(f"### 💭 AI Reasoning")
                        st.markdown(f"**{row['reason']}**")

                        if pd.notna(row['leverage']) and row['leverage'] > 0:
                            st.markdown(f"**Leverage:** {row['leverage']}x")

                        if pd.notna(row['target_portion_of_balance']):
                            st.markdown(f"**Target %:** {row['target_portion_of_balance'] * 100:.1f}%")

                    with col_b:
                        if row['operation'] == 'open':
                            st.success("✅ OPEN")
                        elif row['operation'] == 'close':
                            st.error("❌ CLOSE")
                        else:
                            st.info("⏸️ HOLD")

                        st.caption(f"ID: {row['id']}")

                    # Full payload JSON
                    if pd.notna(row['full_payload']):
                        with st.expander("📦 Full Decision Payload (JSON)"):
                            st.json(row['full_payload'])

                    # System prompt
                    if pd.notna(row['system_prompt']):
                        with st.expander("📄 System Prompt (Input AI)"):
                            prompt_text = str(row['system_prompt'])
                            if len(prompt_text) > 5000:
                                st.text_area("Prompt", prompt_text[:5000] + "\n... (truncated)", height=300)
                                st.caption(f"Total length: {len(prompt_text)} characters")
                            else:
                                st.text_area("Prompt", prompt_text, height=300)
        else:
            st.info("Nessuna decisione AI registrata")
    except Exception as e:
        st.error(f"Errore nel caricamento decisioni AI: {e}")

with tab5:
    st.subheader("⚙️ Bot Configuration")

    # Mostra env vars (senza valori sensibili)
    st.markdown("### Environment Variables Status")

    env_vars = {
        "AI_PROVIDER": os.getenv("AI_PROVIDER", "Not Set"),
        "OPENROUTER_MODEL": os.getenv("OPENROUTER_MODEL", "Not Set"),
        "TESTNET": os.getenv("TESTNET", "Not Set"),
        "DATABASE_URL": "✅ Configured" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "OPENAI_API_KEY": "✅ Configured" if os.getenv("OPENAI_API_KEY") else "❌ Not Set",
        "OPENROUTER_API_KEY": "✅ Configured" if os.getenv("OPENROUTER_API_KEY") else "❌ Not Set",
        "CMC_PRO_API_KEY": "✅ Configured" if os.getenv("CMC_PRO_API_KEY") else "❌ Not Set",
        "PRIVATE_KEY": "✅ Configured" if os.getenv("PRIVATE_KEY") else "❌ Not Set",
        "WALLET_ADDRESS": os.getenv("WALLET_ADDRESS", "Not Set") if os.getenv("WALLET_ADDRESS") else "❌ Not Set",
    }

    df_env = pd.DataFrame(list(env_vars.items()), columns=["Variable", "Value"])
    st.dataframe(df_env, use_container_width=True)

    st.markdown("### Database Tables")
    try:
        tables = query_db("""
            SELECT
                table_name,
                (SELECT COUNT(*)
                 FROM information_schema.columns
                 WHERE table_schema = 'public'
                 AND table_name = t.table_name) as num_columns
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        if not tables.empty:
            st.dataframe(tables, use_container_width=True)

            # Conta righe per ogni tabella
            st.markdown("### Table Row Counts")
            row_counts = []
            for table in tables['table_name']:
                try:
                    count_df = query_db(f"SELECT COUNT(*) as count FROM {table}")
                    if not count_df.empty:
                        row_counts.append({
                            'Table': table,
                            'Rows': int(count_df['count'].iloc[0])
                        })
                except:
                    pass

            if row_counts:
                df_counts = pd.DataFrame(row_counts)
                st.dataframe(df_counts, use_container_width=True)

        else:
            st.warning("Nessuna tabella trovata")
    except Exception as e:
        st.error(f"Errore: {e}")

# Refresh button
st.markdown("---")
col_refresh1, col_refresh2 = st.columns([1, 4])
with col_refresh1:
    if st.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.rerun()

with col_refresh2:
    st.caption("💡 La dashboard si aggiorna automaticamente quando ricarichi la pagina")

# Footer
st.markdown("---")
st.caption(f"🤖 Trading Agent Dashboard | Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
st.caption("📊 Data source: PostgreSQL | 🔄 Auto-refresh: Reload page")
