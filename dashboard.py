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
        col1.metric("💰 Account Value", f"${current_balance:,.2f}",
                   help="Valore totale del tuo account su Hyperliquid in USD")
    else:
        col1.metric("💰 Account Value", "N/A",
                   help="Valore totale del tuo account in USD")
except Exception as e:
    col1.metric("💰 Account Value", "Error")

# Total Operations
try:
    total_ops = query_db("SELECT COUNT(*) as count FROM bot_operations")
    if not total_ops.empty:
        col2.metric("📊 Total Operations", int(total_ops['count'].iloc[0]),
                   help="Numero totale di operazioni eseguite dal bot (open, close, hold)")
    else:
        col2.metric("📊 Total Operations", "0",
                   help="Numero totale di operazioni eseguite")
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
        col3.metric("📈 Open Positions", int(open_positions_query['count'].iloc[0]),
                   help="Numero di posizioni attualmente aperte (BTC, ETH, SOL)")
    else:
        col3.metric("📈 Open Positions", "0",
                   help="Numero di posizioni attualmente aperte")
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
            col4.metric("🟢 Status", "Active", f"{int(diff)}m ago",
                       help="Il bot è attivo se ha eseguito operazioni negli ultimi 30 minuti")
        else:
            col4.metric("🟡 Status", "Idle", f"{int(diff)}m ago",
                       help="Il bot è inattivo da più di 30 minuti - potrebbe esserci un problema")
    else:
        col4.metric("⚪ Status", "No Data",
                   help="Nessuna operazione registrata ancora")
except:
    col4.metric("❌ Status", "Error")

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Performance", "💼 Operations", "📈 Open Positions", "🎯 AI Decisions", "🧠 AI Strategy Analysis", "⚙️ Settings"])

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

    # ========================================
    # TRADING ANALYTICS SECTION (NEW)
    # ========================================
    st.markdown("---")
    st.subheader("📈 Trading Analytics")

    # Info box con spiegazione generale
    with st.expander("ℹ️ Cosa significano queste metriche?", expanded=False):
        st.markdown("""
        **Metriche di Performance del Trading Bot:**

        | Metrica | Significato | Valori Ideali |
        |---------|-------------|---------------|
        | **Win Rate** | Percentuale di trade chiusi in profitto | >50% è buono, >60% è ottimo |
        | **Avg P&L/Trade** | Guadagno/perdita media per ogni trade | Positivo = bot profittevole |
        | **Max Drawdown** | Massima perdita dal picco più alto | <20% è accettabile, <10% è ottimo |
        | **Profit Factor** | Rapporto tra profitti totali e perdite totali | >1.5 è buono, >2 è ottimo |

        **Come leggere i grafici:**
        - **Long vs Short**: Confronta le performance tra posizioni rialziste (Long) e ribassiste (Short)
        - **Performance by Symbol**: Mostra quali criptovalute stanno performando meglio
        - **Equity Curve**: Andamento del capitale nel tempo - la linea verde tratteggiata è il "picco" massimo raggiunto
        - **Drawdown %**: Mostra quanto sei "sotto" rispetto al massimo - più è basso meglio è
        """)

    # Row 1: Key Metrics
    col_an1, col_an2, col_an3, col_an4 = st.columns(4)

    # WIN RATE
    try:
        win_rate_data = query_db("""
            SELECT
                COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                COUNT(*) FILTER (WHERE pnl_usd < 0) as losses,
                COUNT(*) FILTER (WHERE pnl_usd = 0) as breakeven,
                COUNT(*) as total
            FROM open_positions
            WHERE pnl_usd IS NOT NULL
        """)

        if not win_rate_data.empty and win_rate_data['total'].iloc[0] > 0:
            wins = int(win_rate_data['wins'].iloc[0])
            losses = int(win_rate_data['losses'].iloc[0])
            total = int(win_rate_data['total'].iloc[0])
            win_rate = (wins / total * 100) if total > 0 else 0

            with col_an1:
                st.metric("🎯 Win Rate", f"{win_rate:.1f}%", f"{wins}W / {losses}L",
                         help="Percentuale di trade chiusi in profitto. >50% buono, >60% ottimo")
        else:
            with col_an1:
                st.metric("🎯 Win Rate", "N/A", "No closed trades",
                         help="Percentuale di trade chiusi in profitto")
    except Exception as e:
        with col_an1:
            st.metric("🎯 Win Rate", "Error", help="Errore nel calcolo")

    # AVG P&L PER TRADE
    try:
        avg_pnl_data = query_db("""
            SELECT
                AVG(pnl_usd) as avg_pnl,
                AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END) as avg_win,
                AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END) as avg_loss
            FROM open_positions
            WHERE pnl_usd IS NOT NULL
        """)

        if not avg_pnl_data.empty and pd.notna(avg_pnl_data['avg_pnl'].iloc[0]):
            avg_pnl = float(avg_pnl_data['avg_pnl'].iloc[0])
            avg_win = float(avg_pnl_data['avg_win'].iloc[0]) if pd.notna(avg_pnl_data['avg_win'].iloc[0]) else 0
            avg_loss = float(avg_pnl_data['avg_loss'].iloc[0]) if pd.notna(avg_pnl_data['avg_loss'].iloc[0]) else 0

            with col_an2:
                delta_color = "normal" if avg_pnl >= 0 else "inverse"
                st.metric("💰 Avg P&L/Trade", f"${avg_pnl:.2f}",
                         help="Guadagno/perdita media per trade. Se positivo, il bot è profittevole in media")
                st.caption(f"Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
        else:
            with col_an2:
                st.metric("💰 Avg P&L/Trade", "N/A",
                         help="Guadagno/perdita media per trade")
    except Exception as e:
        with col_an2:
            st.metric("💰 Avg P&L/Trade", "Error", help="Errore nel calcolo")

    # MAX DRAWDOWN
    try:
        drawdown_data = query_db("""
            SELECT balance_usd, created_at
            FROM account_snapshots
            ORDER BY created_at ASC
        """)

        if not drawdown_data.empty and len(drawdown_data) > 1:
            balances = drawdown_data['balance_usd'].astype(float).values

            # Calculate running max and drawdown
            running_max = balances[0]
            max_drawdown = 0
            max_drawdown_pct = 0

            for balance in balances:
                if balance > running_max:
                    running_max = balance
                drawdown = running_max - balance
                drawdown_pct = (drawdown / running_max * 100) if running_max > 0 else 0
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown = drawdown
                    max_drawdown_pct = drawdown_pct

            with col_an3:
                st.metric("📉 Max Drawdown", f"{max_drawdown_pct:.2f}%", f"-${max_drawdown:.2f}",
                         help="Massima perdita dal picco più alto. <10% ottimo, <20% accettabile, >30% rischioso")
        else:
            with col_an3:
                st.metric("📉 Max Drawdown", "N/A",
                         help="Massima perdita dal picco più alto")
    except Exception as e:
        with col_an3:
            st.metric("📉 Max Drawdown", "Error", help="Errore nel calcolo")

    # PROFIT FACTOR
    try:
        pf_data = query_db("""
            SELECT
                COALESCE(SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd END), 0) as gross_profit,
                COALESCE(ABS(SUM(CASE WHEN pnl_usd < 0 THEN pnl_usd END)), 0.01) as gross_loss
            FROM open_positions
            WHERE pnl_usd IS NOT NULL
        """)

        if not pf_data.empty:
            gross_profit = float(pf_data['gross_profit'].iloc[0])
            gross_loss = float(pf_data['gross_loss'].iloc[0])
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

            with col_an4:
                pf_status = "Good" if profit_factor > 1.5 else ("Ok" if profit_factor > 1 else "Poor")
                st.metric("⚖️ Profit Factor", f"{profit_factor:.2f}", pf_status,
                         help="Profitti totali / Perdite totali. >1 = profittevole, >1.5 buono, >2 ottimo")
        else:
            with col_an4:
                st.metric("⚖️ Profit Factor", "N/A",
                         help="Profitti totali / Perdite totali")
    except Exception as e:
        with col_an4:
            st.metric("⚖️ Profit Factor", "Error", help="Errore nel calcolo")

    # Row 2: Performance by Direction (Long vs Short)
    col_dir1, col_dir2 = st.columns(2)

    with col_dir1:
        st.markdown("#### 📊 Performance by Direction")
        try:
            direction_perf = query_db("""
                SELECT
                    side as direction,
                    COUNT(*) as trades,
                    SUM(pnl_usd) as total_pnl,
                    AVG(pnl_usd) as avg_pnl,
                    COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                    COUNT(*) FILTER (WHERE pnl_usd < 0) as losses
                FROM open_positions
                WHERE pnl_usd IS NOT NULL AND side IS NOT NULL
                GROUP BY side
            """)

            if not direction_perf.empty:
                for _, row in direction_perf.iterrows():
                    direction = row['direction'].upper() if row['direction'] else "N/A"
                    total_pnl = float(row['total_pnl']) if pd.notna(row['total_pnl']) else 0
                    avg_pnl = float(row['avg_pnl']) if pd.notna(row['avg_pnl']) else 0
                    wins = int(row['wins']) if pd.notna(row['wins']) else 0
                    losses = int(row['losses']) if pd.notna(row['losses']) else 0
                    trades = int(row['trades'])
                    win_rate = (wins / trades * 100) if trades > 0 else 0

                    icon = "🟢" if direction == "LONG" else "🔴"
                    pnl_color = "green" if total_pnl >= 0 else "red"

                    st.markdown(f"""
                    <div style="background: {'#28a74522' if direction == 'LONG' else '#dc354522'};
                                padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                        <h4 style="margin: 0;">{icon} {direction}</h4>
                        <p style="margin: 5px 0;">
                            <b>Trades:</b> {trades} |
                            <b>Win Rate:</b> {win_rate:.1f}% |
                            <b>Total P&L:</b> <span style="color: {pnl_color};">${total_pnl:+,.2f}</span>
                        </p>
                        <p style="margin: 0; color: #666;">Avg P&L: ${avg_pnl:+,.2f}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Nessun dato di direzione disponibile")
        except Exception as e:
            st.error(f"Errore: {e}")

    with col_dir2:
        st.markdown("#### 🪙 Performance by Symbol (Detailed)")
        try:
            symbol_perf = query_db("""
                SELECT
                    symbol,
                    COUNT(*) as trades,
                    SUM(pnl_usd) as total_pnl,
                    AVG(pnl_usd) as avg_pnl,
                    COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                    MAX(pnl_usd) as best_trade,
                    MIN(pnl_usd) as worst_trade
                FROM open_positions
                WHERE pnl_usd IS NOT NULL
                GROUP BY symbol
                ORDER BY total_pnl DESC
            """)

            if not symbol_perf.empty:
                for _, row in symbol_perf.iterrows():
                    symbol = row['symbol']
                    total_pnl = float(row['total_pnl']) if pd.notna(row['total_pnl']) else 0
                    avg_pnl = float(row['avg_pnl']) if pd.notna(row['avg_pnl']) else 0
                    trades = int(row['trades'])
                    wins = int(row['wins']) if pd.notna(row['wins']) else 0
                    win_rate = (wins / trades * 100) if trades > 0 else 0
                    best = float(row['best_trade']) if pd.notna(row['best_trade']) else 0
                    worst = float(row['worst_trade']) if pd.notna(row['worst_trade']) else 0

                    pnl_color = "green" if total_pnl >= 0 else "red"

                    st.markdown(f"""
                    <div style="background: #f8f9fa; padding: 12px; border-radius: 8px;
                                margin-bottom: 8px; border-left: 4px solid {pnl_color};">
                        <b>{symbol}</b>
                        <span style="float: right; color: {pnl_color}; font-weight: bold;">${total_pnl:+,.2f}</span>
                        <br/>
                        <small style="color: #666;">
                            {trades} trades | {win_rate:.0f}% WR |
                            Best: ${best:+,.2f} | Worst: ${worst:+,.2f}
                        </small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Nessun dato per symbol disponibile")
        except Exception as e:
            st.error(f"Errore: {e}")

    # Row 3: Equity Curve with Drawdown
    st.markdown("#### 📈 Equity Curve with Drawdown")
    try:
        equity_data = query_db("""
            SELECT balance_usd, created_at
            FROM account_snapshots
            ORDER BY created_at ASC
        """)

        if not equity_data.empty and len(equity_data) > 1:
            equity_data['created_at'] = pd.to_datetime(equity_data['created_at'])
            equity_data['balance_usd'] = equity_data['balance_usd'].astype(float)

            # Calculate running max and drawdown for each point
            equity_data['running_max'] = equity_data['balance_usd'].cummax()
            equity_data['drawdown'] = equity_data['running_max'] - equity_data['balance_usd']
            equity_data['drawdown_pct'] = (equity_data['drawdown'] / equity_data['running_max'] * 100)

            # Create figure with secondary y-axis
            from plotly.subplots import make_subplots

            fig_equity = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.7, 0.3],
                subplot_titles=('Equity Curve', 'Drawdown %')
            )

            # Equity curve
            fig_equity.add_trace(
                go.Scatter(
                    x=equity_data['created_at'],
                    y=equity_data['balance_usd'],
                    mode='lines',
                    name='Balance',
                    line=dict(color='#2196F3', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(33, 150, 243, 0.1)'
                ),
                row=1, col=1
            )

            # Running max (peak)
            fig_equity.add_trace(
                go.Scatter(
                    x=equity_data['created_at'],
                    y=equity_data['running_max'],
                    mode='lines',
                    name='Peak',
                    line=dict(color='#4CAF50', width=1, dash='dot')
                ),
                row=1, col=1
            )

            # Drawdown
            fig_equity.add_trace(
                go.Scatter(
                    x=equity_data['created_at'],
                    y=equity_data['drawdown_pct'],
                    mode='lines',
                    name='Drawdown %',
                    line=dict(color='#f44336', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(244, 67, 54, 0.3)'
                ),
                row=2, col=1
            )

            fig_equity.update_layout(
                height=500,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            fig_equity.update_yaxes(title_text="Balance (USD)", row=1, col=1)
            fig_equity.update_yaxes(title_text="Drawdown %", row=2, col=1, autorange="reversed")
            fig_equity.update_xaxes(title_text="Date", row=2, col=1)

            st.plotly_chart(fig_equity, use_container_width=True)
        else:
            st.info("Non ci sono abbastanza dati per l'equity curve. Attendi almeno 2 snapshot.")
    except Exception as e:
        st.error(f"Errore equity curve: {e}")

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

    # === SENTINEL STATUS BOX ===
    st.markdown("### 🛡️ Sentinel Monitor")

    try:
        # Stato sentinel
        sentinel_status = query_db("""
            SELECT
                MAX(created_at) as last_check,
                COUNT(*) as checks_24h,
                COUNT(action_taken) as actions_24h,
                COUNT(CASE WHEN action_taken = 'CLOSE_STOP_LOSS' THEN 1 END) as stop_loss_count,
                COUNT(CASE WHEN action_taken = 'CLOSE_TRAILING_STOP' THEN 1 END) as trailing_stop_count
            FROM sentinel_logs
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)

        # Config da .env (valori di default se non letti)
        trailing_pct = os.getenv('TRAILING_STOP_PERCENT', '7')
        activation_pct = os.getenv('TRAILING_STOP_ACTIVATION_PERCENT', '3')
        stop_loss_pct = os.getenv('INITIAL_STOP_LOSS_PERCENT', '10')
        sentinel_enabled = os.getenv('SENTINEL_ENABLED', 'true').lower() == 'true'

        col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)

        with col_s1:
            status_icon = "🟢" if sentinel_enabled else "🔴"
            st.metric("Stato", f"{status_icon} {'ATTIVO' if sentinel_enabled else 'OFF'}")

        with col_s2:
            last_check = sentinel_status['last_check'].iloc[0] if not sentinel_status.empty and pd.notna(sentinel_status['last_check'].iloc[0]) else None
            if last_check:
                # Formatta timestamp
                last_check_str = pd.to_datetime(last_check).strftime('%H:%M:%S')
                st.metric("Ultimo Check", last_check_str)
            else:
                st.metric("Ultimo Check", "N/A")

        with col_s3:
            checks = int(sentinel_status['checks_24h'].iloc[0]) if not sentinel_status.empty else 0
            st.metric("Check 24h", checks)

        with col_s4:
            actions = int(sentinel_status['actions_24h'].iloc[0]) if not sentinel_status.empty else 0
            st.metric("Azioni 24h", actions)

        with col_s5:
            st.caption(f"**Config:**")
            st.caption(f"Trailing: {trailing_pct}%")
            st.caption(f"Activation: {activation_pct}%")
            st.caption(f"Stop Loss: {stop_loss_pct}%")

    except Exception as e:
        st.warning(f"⚠️ Sentinel status non disponibile: {e}")

    st.markdown("---")

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

            # Carica tracking per tutte le posizioni
            tracking_data = query_db("""
                SELECT symbol, direction, entry_price, peak_price, trailing_active, last_checked_price, updated_at
                FROM position_tracking
            """)
            tracking_dict = {row['symbol']: row for _, row in tracking_data.iterrows()} if not tracking_data.empty else {}

            for idx, pos in open_positions.iterrows():
                pnl = float(pos['pnl_usd']) if pd.notna(pos['pnl_usd']) else 0
                pnl_color = "green" if pnl >= 0 else "red"
                pnl_icon = "📈" if pnl >= 0 else "📉"

                # Ottieni tracking per questa posizione
                symbol_tracking = tracking_dict.get(pos['symbol'])

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

                    # === TRAILING STOP MONITOR ===
                    if symbol_tracking is not None:
                        st.markdown("---")
                        st.markdown("**🛡️ Trailing Stop Monitor**")

                        col_t1, col_t2, col_t3, col_t4 = st.columns(4)

                        peak_price = float(symbol_tracking['peak_price'])
                        trailing_active = symbol_tracking['trailing_active']
                        current_price = float(pos['mark_price'])

                        # Calcola distanza dal peak
                        if pos['side'].lower() == 'long':
                            peak_dist = ((current_price - peak_price) / peak_price) * 100
                        else:
                            peak_dist = ((peak_price - current_price) / peak_price) * 100

                        with col_t1:
                            st.metric("Peak Price", f"${peak_price:,.2f}")

                        with col_t2:
                            # Colore per distanza dal peak
                            dist_color = "green" if peak_dist >= 0 else ("red" if peak_dist < -5 else "orange")
                            st.metric("Dist. dal Peak", f"{peak_dist:+.2f}%")

                        with col_t3:
                            trailing_icon = "🟢 ATTIVO" if trailing_active else "⚪ Inattivo"
                            st.metric("Trailing", trailing_icon)

                        with col_t4:
                            # Calcola soglia stop
                            if trailing_active:
                                stop_trigger = f"-{trailing_pct}% dal peak"
                            else:
                                stop_trigger = f"-{stop_loss_pct}% da entry"
                            st.metric("Stop Trigger", stop_trigger)

                        # Barra progresso verso stop
                        if trailing_active:
                            # Trailing attivo: mostra quanto manca allo stop
                            progress = min(100, max(0, (float(trailing_pct) + peak_dist) / float(trailing_pct) * 100))
                            st.progress(progress / 100, text=f"Margine trailing: {float(trailing_pct) + peak_dist:.2f}%")
                        else:
                            # Stop loss: mostra quanto manca
                            profit_pct = price_change if pos['side'].lower() == 'long' else -price_change
                            progress = min(100, max(0, (float(stop_loss_pct) + profit_pct) / float(stop_loss_pct) * 100))
                            st.progress(progress / 100, text=f"Margine stop loss: {float(stop_loss_pct) + profit_pct:.2f}%")
                    else:
                        st.caption("⚠️ Tracking non ancora inizializzato per questa posizione")

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

    # === SENTINEL HISTORY ===
    st.markdown("---")
    st.markdown("### 📜 Sentinel Price History")

    try:
        sentinel_logs = query_db("""
            SELECT
                created_at,
                symbol,
                direction,
                entry_price,
                current_price,
                peak_price,
                profit_pct,
                profit_from_peak_pct,
                trailing_active,
                action_taken,
                action_reason
            FROM sentinel_logs
            ORDER BY created_at DESC
            LIMIT 30
        """)

        if not sentinel_logs.empty:
            # Filtri
            col_f1, col_f2 = st.columns([1, 3])
            with col_f1:
                symbols = ['Tutti'] + sorted(sentinel_logs['symbol'].unique().tolist())
                selected_symbol = st.selectbox("Filtra Symbol", symbols, key="sentinel_filter")

            if selected_symbol != 'Tutti':
                sentinel_logs = sentinel_logs[sentinel_logs['symbol'] == selected_symbol]

            # Formatta la tabella
            display_df = sentinel_logs.copy()
            display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%H:%M:%S')
            display_df['profit_pct'] = display_df['profit_pct'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
            display_df['profit_from_peak_pct'] = display_df['profit_from_peak_pct'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
            display_df['entry_price'] = display_df['entry_price'].apply(lambda x: f"${x:,.2f}")
            display_df['current_price'] = display_df['current_price'].apply(lambda x: f"${x:,.2f}")
            display_df['peak_price'] = display_df['peak_price'].apply(lambda x: f"${x:,.2f}")
            display_df['trailing_active'] = display_df['trailing_active'].apply(lambda x: "🟢" if x else "⚪")
            display_df['action_taken'] = display_df['action_taken'].fillna("-")

            # Rinomina colonne
            display_df = display_df.rename(columns={
                'created_at': 'Time',
                'symbol': 'Symbol',
                'direction': 'Dir',
                'entry_price': 'Entry',
                'current_price': 'Price',
                'peak_price': 'Peak',
                'profit_pct': 'P/L%',
                'profit_from_peak_pct': 'Peak%',
                'trailing_active': 'Trail',
                'action_taken': 'Action',
                'action_reason': 'Reason'
            })

            # Mostra solo colonne rilevanti
            columns_to_show = ['Time', 'Symbol', 'Dir', 'Entry', 'Price', 'Peak', 'P/L%', 'Peak%', 'Trail', 'Action']
            st.dataframe(display_df[columns_to_show], use_container_width=True, hide_index=True)

            # Mostra azioni recenti se ci sono
            actions = sentinel_logs[sentinel_logs['action_taken'].notna() & (sentinel_logs['action_taken'] != '')]
            if not actions.empty:
                st.markdown("#### ⚡ Azioni Recenti")
                for _, action in actions.iterrows():
                    action_icon = "🛑" if action['action_taken'] else "ℹ️"
                    st.warning(f"{action_icon} **{action['action_taken']}** - {action['symbol']} {action['direction'].upper()}: {action['action_reason']}")
        else:
            st.info("📊 Nessun log sentinel disponibile. Il sentinel registrerà i dati quando ci sono posizioni aperte.")

    except Exception as e:
        st.warning(f"⚠️ Sentinel history non disponibile: {e}")

with tab4:
    st.subheader("🎯 AI Decision Analysis")

    # === SIGNAL SCORES SECTION (NEW) ===
    st.markdown("### 📊 Signal Scoring (Latest)")

    try:
        latest_scores = query_db("""
            SELECT
                symbol,
                score_bullish,
                score_bearish,
                net_score,
                direction,
                confidence,
                signals,
                created_at
            FROM signal_scores
            WHERE created_at = (SELECT MAX(created_at) FROM signal_scores)
            ORDER BY symbol
        """)

        if not latest_scores.empty:
            # Mostra metriche per ogni symbol
            score_cols = st.columns(len(latest_scores))

            for idx, (_, row) in enumerate(latest_scores.iterrows()):
                with score_cols[idx]:
                    symbol = row['symbol']
                    direction = row['direction']
                    net_score = float(row['net_score'])
                    confidence = row['confidence']

                    # Colore e icona basati sulla direzione
                    if direction == 'LONG':
                        icon = "🟢"
                        bg_color = "#28a74522"
                    elif direction == 'SHORT':
                        icon = "🔴"
                        bg_color = "#dc354522"
                    else:
                        icon = "⚪"
                        bg_color = "#6c757d22"

                    st.markdown(f"""
                    <div style="background: {bg_color}; padding: 15px; border-radius: 10px; text-align: center;">
                        <h3 style="margin: 0;">{icon} {symbol}</h3>
                        <h2 style="margin: 5px 0; color: {'green' if net_score > 0 else 'red' if net_score < 0 else 'gray'};">
                            {net_score:+.1f}
                        </h2>
                        <p style="margin: 0;"><b>{direction}</b> ({confidence})</p>
                        <small style="color: #666;">
                            Bull: {float(row['score_bullish']):.1f} | Bear: {float(row['score_bearish']):.1f}
                        </small>
                    </div>
                    """, unsafe_allow_html=True)

            # Dettagli segnali in expander
            with st.expander("📈 Dettaglio Segnali", expanded=False):
                for _, row in latest_scores.iterrows():
                    st.markdown(f"**{row['symbol']}**")
                    signals = row['signals']
                    if signals:
                        for sig in signals:
                            if sig.get('contribution', 0) > 0:
                                dir_icon = "🟢" if sig.get('direction') == 'BULLISH' else "🔴"
                                st.markdown(f"  {dir_icon} {sig.get('indicator')}: {sig.get('reason')} (+{sig.get('contribution', 0):.1f})")
                    st.markdown("---")

            st.caption(f"Ultimo aggiornamento: {latest_scores['created_at'].iloc[0]}")
        else:
            st.info("📊 Nessun dato di scoring disponibile. Il bot deve eseguire almeno un ciclo con il sistema di scoring attivo.")

    except Exception as e:
        st.warning(f"Signal Scores non disponibili: {e}")
        st.caption("La tabella signal_scores potrebbe non esistere ancora. Eseguire il bot per crearla.")

    st.markdown("---")

    # Ultime decisioni AI con dati di contesto completi
    try:
        ai_decisions = query_db("""
            SELECT
                bo.id,
                bo.created_at,
                bo.context_id,
                bo.operation,
                bo.symbol,
                bo.direction,
                bo.leverage,
                bo.target_portion_of_balance,
                bo.raw_payload->>'reason' as reason,
                bo.raw_payload as full_payload
            FROM bot_operations bo
            ORDER BY bo.created_at DESC
            LIMIT 50
        """)

        if not ai_decisions.empty:
            st.success(f"📊 {len(ai_decisions)} decisioni AI trovate")

            # Filtri
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                decision_filter = st.selectbox(
                    "🔍 Filtra per Operazione",
                    ["Tutte", "open", "close", "hold"]
                )
            with col_f2:
                symbol_filter_ai = st.selectbox(
                    "🪙 Filtra per Symbol",
                    ["Tutti", "BTC", "ETH", "SOL"],
                    key="ai_symbol_filter"
                )

            filtered_decisions = ai_decisions
            if decision_filter != "Tutte":
                filtered_decisions = filtered_decisions[filtered_decisions['operation'] == decision_filter]
            if symbol_filter_ai != "Tutti":
                filtered_decisions = filtered_decisions[filtered_decisions['symbol'] == symbol_filter_ai]

            for idx, row in filtered_decisions.iterrows():
                # Icon e colore per tipo operazione
                if row['operation'] == 'open':
                    icon = "🟢"
                    badge_color = "#28a745"
                elif row['operation'] == 'close':
                    icon = "🔴"
                    badge_color = "#dc3545"
                else:
                    icon = "⚪"
                    badge_color = "#6c757d"

                with st.expander(
                    f"{icon} {row['created_at']} - {row['operation'].upper()} {row['symbol']} ({row['direction']})",
                    expanded=(idx==0)
                ):
                    # Header con decisione
                    st.markdown(f"""
                    <div style="background: linear-gradient(90deg, {badge_color}22, transparent);
                                padding: 15px; border-radius: 10px; border-left: 4px solid {badge_color}; margin-bottom: 15px;">
                        <h3 style="margin: 0; color: {badge_color};">{icon} {row['operation'].upper()} {row['symbol']}</h3>
                        <p style="margin: 5px 0 0 0; color: #666;">Direction: {row['direction']} | Leverage: {row['leverage']}x | Target: {(row['target_portion_of_balance'] or 0) * 100:.1f}%</p>
                    </div>
                    """, unsafe_allow_html=True)

                    # === REASONING PRINCIPALE ===
                    st.markdown("### 💭 Ragionamento AI")
                    reason_text = row['reason'] or "Nessun reasoning disponibile"
                    st.info(reason_text)

                    # === DATI INPUT - Carica solo se context_id esiste ===
                    context_id = row.get('context_id')
                    if pd.notna(context_id):
                        st.markdown("---")
                        st.markdown("### 📊 Dati Input Analizzati dall'AI")

                        # Tab interni per i dati
                        data_tab1, data_tab2, data_tab3, data_tab4, data_tab5, data_tab6 = st.tabs([
                            "📈 Indicatori", "😊 Sentiment", "🔮 Forecasts", "📰 News", "📊 Signal Scores", "📝 Prompt AI"
                        ])

                        # --- INDICATORI ---
                        with data_tab1:
                            indicators_data = query_db(f"""
                                SELECT
                                    ticker,
                                    price,
                                    ema20,
                                    macd,
                                    rsi_7,
                                    pp, s1, s2, r1, r2,
                                    funding_rate,
                                    open_interest_latest,
                                    volume_bid,
                                    volume_ask
                                FROM indicators_contexts
                                WHERE context_id = {context_id}
                            """)

                            if not indicators_data.empty:
                                for _, ind in indicators_data.iterrows():
                                    ticker = ind['ticker']

                                    # Calcola segnali
                                    price = float(ind['price']) if pd.notna(ind['price']) else 0
                                    ema20 = float(ind['ema20']) if pd.notna(ind['ema20']) else 0
                                    macd = float(ind['macd']) if pd.notna(ind['macd']) else 0
                                    rsi = float(ind['rsi_7']) if pd.notna(ind['rsi_7']) else 50

                                    # Segnali visivi
                                    trend_signal = "🟢 BULLISH" if price > ema20 else "🔴 BEARISH"
                                    macd_signal = "🟢 Positivo" if macd > 0 else "🔴 Negativo"
                                    if rsi > 70:
                                        rsi_signal = "🔴 Overbought"
                                    elif rsi < 30:
                                        rsi_signal = "🟢 Oversold"
                                    else:
                                        rsi_signal = "⚪ Neutro"

                                    st.markdown(f"#### {ticker}")

                                    col_i1, col_i2, col_i3, col_i4 = st.columns(4)
                                    with col_i1:
                                        st.metric("💰 Price", f"${price:,.2f}")
                                        st.caption(f"EMA20: ${ema20:,.2f}")
                                    with col_i2:
                                        st.metric("📊 RSI(7)", f"{rsi:.1f}")
                                        st.caption(rsi_signal)
                                    with col_i3:
                                        st.metric("📈 MACD", f"{macd:.4f}")
                                        st.caption(macd_signal)
                                    with col_i4:
                                        st.metric("🎯 Trend", trend_signal.split()[1])
                                        st.caption(trend_signal)

                                    # Pivot points
                                    if pd.notna(ind['pp']):
                                        with st.expander(f"📍 Pivot Points {ticker}"):
                                            pp_col1, pp_col2 = st.columns(2)
                                            with pp_col1:
                                                st.write(f"**PP:** ${float(ind['pp']):,.2f}")
                                                st.write(f"**S1:** ${float(ind['s1']):,.2f}" if pd.notna(ind['s1']) else "S1: N/A")
                                                st.write(f"**S2:** ${float(ind['s2']):,.2f}" if pd.notna(ind['s2']) else "S2: N/A")
                                            with pp_col2:
                                                st.write(f"**R1:** ${float(ind['r1']):,.2f}" if pd.notna(ind['r1']) else "R1: N/A")
                                                st.write(f"**R2:** ${float(ind['r2']):,.2f}" if pd.notna(ind['r2']) else "R2: N/A")
                                                if pd.notna(ind['funding_rate']):
                                                    st.write(f"**Funding:** {float(ind['funding_rate'])*100:.4f}%")

                                    st.markdown("---")
                            else:
                                st.info("Nessun dato indicatori disponibile per questa decisione")

                        # --- SENTIMENT ---
                        with data_tab2:
                            sentiment_data = query_db(f"""
                                SELECT value, classification, raw
                                FROM sentiment_contexts
                                WHERE context_id = {context_id}
                            """)

                            if not sentiment_data.empty:
                                sent = sentiment_data.iloc[0]
                                value = int(sent['value']) if pd.notna(sent['value']) else 50
                                classification = sent['classification'] or "Unknown"

                                # Colore basato su valore
                                if value <= 25:
                                    sent_color = "#dc3545"  # Extreme Fear - Red
                                    sent_icon = "😱"
                                elif value <= 45:
                                    sent_color = "#fd7e14"  # Fear - Orange
                                    sent_icon = "😰"
                                elif value <= 55:
                                    sent_color = "#ffc107"  # Neutral - Yellow
                                    sent_icon = "😐"
                                elif value <= 75:
                                    sent_color = "#28a745"  # Greed - Green
                                    sent_icon = "😊"
                                else:
                                    sent_color = "#20c997"  # Extreme Greed - Teal
                                    sent_icon = "🤑"

                                st.markdown(f"""
                                <div style="text-align: center; padding: 20px; background: {sent_color}22; border-radius: 15px;">
                                    <h1 style="font-size: 64px; margin: 0;">{sent_icon}</h1>
                                    <h2 style="color: {sent_color}; margin: 10px 0;">{value}/100</h2>
                                    <p style="font-size: 18px; margin: 0;"><strong>{classification}</strong></p>
                                </div>
                                """, unsafe_allow_html=True)

                                # Barra visiva del sentiment
                                st.progress(value / 100)
                                st.caption("0 = Extreme Fear | 50 = Neutral | 100 = Extreme Greed")
                            else:
                                st.info("Nessun dato sentiment disponibile")

                        # --- FORECASTS ---
                        with data_tab3:
                            forecasts_data = query_db(f"""
                                SELECT ticker, timeframe, last_price, prediction,
                                       lower_bound, upper_bound, change_pct
                                FROM forecasts_contexts
                                WHERE context_id = {context_id}
                                ORDER BY ticker, timeframe
                            """)

                            if not forecasts_data.empty:
                                for _, fc in forecasts_data.iterrows():
                                    change = float(fc['change_pct']) if pd.notna(fc['change_pct']) else 0
                                    change_color = "green" if change >= 0 else "red"
                                    change_icon = "📈" if change >= 0 else "📉"

                                    st.markdown(f"#### {fc['ticker']} - {fc['timeframe']}")

                                    fc_col1, fc_col2, fc_col3 = st.columns(3)
                                    with fc_col1:
                                        last_p = float(fc['last_price']) if pd.notna(fc['last_price']) else 0
                                        st.metric("Prezzo Attuale", f"${last_p:,.2f}")
                                    with fc_col2:
                                        pred = float(fc['prediction']) if pd.notna(fc['prediction']) else 0
                                        st.metric("Previsione", f"${pred:,.2f}", f"{change:+.2f}%")
                                    with fc_col3:
                                        lower = float(fc['lower_bound']) if pd.notna(fc['lower_bound']) else 0
                                        upper = float(fc['upper_bound']) if pd.notna(fc['upper_bound']) else 0
                                        st.metric("Range", f"${lower:,.0f} - ${upper:,.0f}")

                                    st.markdown("---")
                            else:
                                st.info("Nessun forecast disponibile")

                        # --- NEWS ---
                        with data_tab4:
                            news_data = query_db(f"""
                                SELECT news_text
                                FROM news_contexts
                                WHERE context_id = {context_id}
                            """)

                            if not news_data.empty:
                                news_text = news_data.iloc[0]['news_text']
                                if news_text:
                                    # Mostra le news formattate (key unica per evitare duplicati)
                                    st.text_area("📰 News analizzate dall'AI", news_text, height=300, key=f"news_{row['id']}")
                                else:
                                    st.info("Nessuna news disponibile")
                            else:
                                st.info("Nessuna news disponibile")

                        # --- SIGNAL SCORES ---
                        with data_tab5:
                            # Cerca scores salvati vicino al timestamp della decisione
                            scores_data = query_db(f"""
                                SELECT
                                    symbol,
                                    score_bullish,
                                    score_bearish,
                                    net_score,
                                    direction,
                                    confidence,
                                    signals,
                                    thresholds,
                                    created_at
                                FROM signal_scores
                                WHERE created_at BETWEEN
                                    '{row['created_at']}'::timestamp - interval '5 minutes'
                                    AND '{row['created_at']}'::timestamp + interval '5 minutes'
                                ORDER BY created_at DESC
                            """)

                            if not scores_data.empty:
                                st.success(f"📊 {len(scores_data)} signal scores trovati")

                                for _, score in scores_data.iterrows():
                                    symbol = score['symbol']
                                    net = float(score['net_score'])
                                    bull = float(score['score_bullish'])
                                    bear = float(score['score_bearish'])
                                    direction = score['direction']
                                    confidence = score['confidence']

                                    # Colore basato sulla direzione
                                    if direction == 'LONG':
                                        dir_color = "#28a745"
                                        dir_icon = "🟢"
                                    elif direction == 'SHORT':
                                        dir_color = "#dc3545"
                                        dir_icon = "🔴"
                                    else:
                                        dir_color = "#6c757d"
                                        dir_icon = "⚪"

                                    st.markdown(f"""
                                    <div style="background: {dir_color}22; padding: 15px; border-radius: 10px;
                                                border-left: 4px solid {dir_color}; margin-bottom: 10px;">
                                        <h4 style="margin: 0;">{dir_icon} {symbol} → {direction} ({confidence})</h4>
                                        <p style="margin: 5px 0;">
                                            <b>Net Score:</b> <span style="color: {'green' if net > 0 else 'red' if net < 0 else 'gray'}; font-size: 1.2em;">{net:+.1f}</span> |
                                            <b>Bull:</b> {bull:.1f} |
                                            <b>Bear:</b> {bear:.1f}
                                        </p>
                                    </div>
                                    """, unsafe_allow_html=True)

                                    # Mostra segnali individuali
                                    signals = score['signals']
                                    if signals:
                                        with st.expander(f"📈 Dettaglio segnali {symbol}"):
                                            for sig in signals:
                                                contrib = sig.get('contribution', 0)
                                                if contrib > 0:
                                                    sig_dir = sig.get('direction', 'NEUTRAL')
                                                    sig_icon = "🟢" if sig_dir == 'BULLISH' else "🔴" if sig_dir == 'BEARISH' else "⚪"
                                                    st.markdown(f"""
                                                    {sig_icon} **{sig.get('indicator')}**: {sig.get('reason')}
                                                    *Contributo: +{contrib:.1f} (peso: {sig.get('weight', 0)}, intensità: {sig.get('intensity', 0):.1%})*
                                                    """)
                            else:
                                st.info("Nessun signal score disponibile per questa decisione")

                        # --- PROMPT AI COMPLETO ---
                        with data_tab6:
                            # Carica il prompt dalla tabella ai_contexts
                            prompt_data = query_db(f"""
                                SELECT system_prompt, created_at
                                FROM ai_contexts
                                WHERE id = {context_id}
                            """)

                            if not prompt_data.empty:
                                prompt = prompt_data.iloc[0]['system_prompt']
                                if prompt:
                                    st.markdown("#### 📝 Prompt inviato all'AI")
                                    st.text_area(
                                        "System Prompt completo",
                                        prompt,
                                        height=500,
                                        key=f"prompt_{row['id']}"
                                    )

                                    # Statistiche prompt
                                    st.caption(f"Lunghezza: {len(prompt)} caratteri | ~{len(prompt.split())} parole")
                                else:
                                    st.info("Prompt non disponibile")
                            else:
                                st.info("Prompt non disponibile per questa decisione")

                            # Mostra anche la risposta AI
                            st.markdown("#### 🤖 Risposta AI")
                            if pd.notna(row['full_payload']):
                                st.json(row['full_payload'])
                            else:
                                st.info("Risposta AI non disponibile")

                    # === DETTAGLI TECNICI (collassati) ===
                    with st.expander("🔧 Dettagli Tecnici"):
                        st.caption(f"Operation ID: {row['id']} | Context ID: {context_id}")

                        if pd.notna(row['full_payload']):
                            st.markdown("**Raw Decision Payload:**")
                            st.json(row['full_payload'])

        else:
            st.info("Nessuna decisione AI registrata. Il bot deve eseguire almeno un ciclo.")
    except Exception as e:
        st.error(f"Errore nel caricamento decisioni AI: {e}")
        st.exception(e)

with tab5:
    st.subheader("🧠 AI Strategy Analysis")

    st.markdown("""
    ### Performance Analytics & AI-Powered Optimization

    This module analyzes your historical trading performance and uses AI to suggest concrete improvements.
    """)

    # Import analytics modules
    try:
        import analytics
        import strategy_controller

        col_days, col_analyze = st.columns([1, 3])

        with col_days:
            analysis_days = st.selectbox(
                "📅 Analysis Period",
                [7, 14, 30, 60],
                index=2,  # Default: 30 days
                help="Days of historical data to analyze"
            )

        with col_analyze:
            st.write("")  # Spacer
            st.write("")  # Spacer
            if st.button("🚀 Run AI Analysis", type="primary", use_container_width=True):
                st.session_state['run_analysis'] = True

        if st.session_state.get('run_analysis', False):
            with st.spinner(f"🔍 Analyzing last {analysis_days} days of trading data..."):
                # Run analytics
                performance = analytics.get_performance_summary(days=analysis_days)

                if performance.get('error'):
                    st.error(f"❌ Error: {performance['error']}")
                else:
                    # Display Performance Summary
                    st.markdown("---")
                    st.subheader("📊 Performance Summary")

                    col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)

                    col_metric1.metric(
                        "Total Trades",
                        performance['total_trades'],
                        help="Total number of completed trades"
                    )

                    col_metric2.metric(
                        "Win Rate",
                        f"{performance['win_rate']*100:.1f}%",
                        delta=f"{performance['winning_trades']}W / {performance['losing_trades']}L",
                        help="Percentage of winning trades"
                    )

                    col_metric3.metric(
                        "Profit Factor",
                        f"{performance['profit_factor']:.2f}",
                        delta="Good" if performance['profit_factor'] > 1.5 else "Needs Improvement",
                        delta_color="normal" if performance['profit_factor'] > 1.5 else "inverse",
                        help="Profit to loss ratio"
                    )

                    col_metric4.metric(
                        "Net Profit",
                        f"${performance['net_profit_usd']:.2f}",
                        delta=f"Avg: ${performance['net_profit_usd']/performance['total_trades']:.2f}/trade" if performance['total_trades'] > 0 else "N/A",
                        help="Total net profit"
                    )

                    # Trade Metrics
                    st.markdown("---")
                    st.subheader("📈 Trade Metrics")

                    col_trade1, col_trade2 = st.columns(2)

                    with col_trade1:
                        st.metric("Avg Win", f"+{performance['avg_win_pct']:.2f}%", help="Average winning trade")
                        st.metric("Max Win", f"+{performance['max_win_pct']:.2f}%", help="Best trade")

                    with col_trade2:
                        st.metric("Avg Loss", f"{performance['avg_loss_pct']:.2f}%", help="Average losing trade")
                        st.metric("Max Loss", f"{performance['max_loss_pct']:.2f}%", help="Worst trade")

                    st.metric("Avg Duration", f"{performance['avg_duration_minutes']:.0f} minutes", help="Average trade duration")

                    # Close Quality Analysis
                    st.markdown("---")
                    st.subheader("🎯 Close Quality Analysis")

                    st.markdown("""
                    Hindsight analysis: how well you closed your positions relative to subsequent price movements.
                    """)

                    close_quality = performance['close_quality_distribution']

                    col_quality1, col_quality2 = st.columns(2)

                    with col_quality1:
                        # Close quality distribution
                        quality_df = pd.DataFrame([
                            {"Quality": k, "Count": v} for k, v in close_quality.items()
                        ])

                        if not quality_df.empty:
                            fig = px.pie(
                                quality_df,
                                values='Count',
                                names='Quality',
                                title="Close Quality Distribution",
                                color_discrete_sequence=px.colors.qualitative.Set3
                            )
                            st.plotly_chart(fig, use_container_width=True)

                    with col_quality2:
                        st.metric(
                            "Total Missed Profit",
                            f"{performance['total_missed_profit_pct']:.1f}%",
                            delta=f"Avg: {performance['avg_missed_per_trade_pct']:.2f}% per trade",
                            delta_color="inverse",
                            help="Profit left on the table by closing too early"
                        )

                        st.info(f"""
                        **Interpretation:**
                        - EXCELLENT: Closed near peak (<1% missed)
                        - GOOD: Price dropped after close
                        - TOO_EARLY: Left >5% on table
                        - TOO_LATE: Held too long, gave back profit
                        """)

                    # Per-Symbol Breakdown
                    st.markdown("---")
                    st.subheader("📊 Per-Symbol Performance")

                    per_symbol_data = []
                    for symbol, stats in performance['per_symbol'].items():
                        per_symbol_data.append({
                            "Symbol": symbol,
                            "Trades": stats['total_trades'],
                            "Win Rate": f"{stats['win_rate']*100:.1f}%",
                            "Profit Factor": f"{stats['profit_factor']:.2f}",
                            "Net Profit": f"${stats['net_profit_usd']:.2f}",
                            "Avg Win": f"+{stats['avg_win_pct']:.2f}%",
                            "Avg Loss": f"{stats['avg_loss_pct']:.2f}%"
                        })

                    if per_symbol_data:
                        df_symbols = pd.DataFrame(per_symbol_data)
                        st.dataframe(df_symbols, use_container_width=True)

                    # AI Analysis
                    st.markdown("---")
                    st.subheader("🤖 AI-Powered Strategy Recommendations")

                    with st.spinner("🧠 Running AI analysis..."):
                        try:
                            ai_result = strategy_controller.analyze_with_ai(days=analysis_days, verbose=False)

                            if ai_result.get('error'):
                                st.error(f"❌ AI Analysis Error: {ai_result['error']}")
                            else:
                                st.success("✅ AI Analysis Complete!")

                                # Display AI Analysis
                                st.markdown(ai_result['analysis'])

                                # Download Report Button
                                if 'report_path' in ai_result:
                                    st.markdown("---")
                                    st.success(f"📄 Report saved: {ai_result['report_path']}")

                                    try:
                                        with open(ai_result['report_path'], 'r') as f:
                                            report_content = f.read()

                                        st.download_button(
                                            label="📥 Download Full Report",
                                            data=report_content,
                                            file_name=f"strategy_analysis_{datetime.now().strftime('%Y%m%d')}.md",
                                            mime="text/markdown"
                                        )
                                    except:
                                        pass

                        except Exception as e:
                            st.error(f"❌ Error running AI analysis: {e}")
                            st.exception(e)

                    # Reset button
                    if st.button("🔄 Run New Analysis"):
                        st.session_state['run_analysis'] = False
                        st.rerun()

        else:
            st.info("👆 Select analysis period and click 'Run AI Analysis' to start")

            st.markdown("""
            ### 📋 What This Analysis Provides:

            1. **Performance Metrics**: Win rate, profit factor, average trade duration
            2. **Close Quality Analysis**: How well you timed your exits using hindsight data
            3. **Per-Symbol Breakdown**: Performance for each crypto (BTC/ETH/SOL)
            4. **Missed Opportunities**: Profit left on the table from early exits
            5. **AI Recommendations**: Concrete suggestions to improve profitability
            6. **Parameter Optimization**: Suggested changes to .env configuration

            ### 🆕 Advanced Features:

            - **Per-symbol inactivity analysis**: Identifies when bot was inactive on specific symbols
            - **Portfolio opportunity cost**: Finds suboptimal position choices
            - **Threshold optimization**: Calculates optimal SCORE_THRESHOLD_OPEN per symbol

            See [README_ANALYTICS.md](/README_ANALYTICS.md) for full documentation.
            """)

    except ImportError as e:
        st.error(f"❌ Analytics modules not found: {e}")
        st.info("Make sure analytics.py and strategy_controller.py are in the same directory as dashboard.py")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
        st.exception(e)

with tab6:
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
