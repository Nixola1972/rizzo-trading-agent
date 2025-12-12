import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURAZIONE DATA DI INIZIO =====
# Imposta la data da cui iniziare a contare i dati
# Formato: YYYY-MM-DD oppure "today" per oggi
START_DATE_STR = os.getenv('DASHBOARD_START_DATE', 'today')

if START_DATE_STR.lower() == 'today':
    START_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
else:
    try:
        START_DATE = datetime.strptime(START_DATE_STR, '%Y-%m-%d')
    except:
        START_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# Configurazione pagina
st.set_page_config(
    page_title="Fresh Trading Dashboard",
    page_icon="🚀",
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

# ===== HEADER =====
st.title("🚀 Fresh Trading Dashboard")
st.markdown(f"**Data inizio conteggio:** `{START_DATE.strftime('%Y-%m-%d %H:%M')}`")
st.markdown("---")

# ===== METRICHE PRINCIPALI =====
col1, col2, col3, col4 = st.columns(4)

# Account Value attuale
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
except:
    col1.metric("💰 Account Value", "Error")

# Balance iniziale (alla data di start)
try:
    initial_snapshot = query_db(f"""
        SELECT balance_usd
        FROM account_snapshots
        WHERE created_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
        ORDER BY created_at ASC
        LIMIT 1
    """)

    if not initial_snapshot.empty:
        initial_balance = float(initial_snapshot['balance_usd'].iloc[0])
        if 'current_balance' in dir():
            pnl = current_balance - initial_balance
            pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else 0
            col2.metric("📈 P&L (dal start)", f"${pnl:,.2f}", f"{pnl_pct:+.2f}%")
        else:
            col2.metric("📈 P&L (dal start)", "N/A")
    else:
        col2.metric("📈 P&L (dal start)", "No data yet")
except Exception as e:
    col2.metric("📈 P&L (dal start)", "Error")

# Trades chiusi dal start
try:
    trades_data = query_db(f"""
        SELECT
            COUNT(*) as total_trades,
            COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
            COUNT(*) FILTER (WHERE pnl_usd <= 0) as losses,
            COALESCE(SUM(pnl_usd), 0) as total_pnl
        FROM trade_journal
        WHERE closed_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
    """)

    if not trades_data.empty and trades_data['total_trades'].iloc[0] > 0:
        total = int(trades_data['total_trades'].iloc[0])
        wins = int(trades_data['wins'].iloc[0])
        win_rate = (wins / total * 100) if total > 0 else 0
        col3.metric("🎯 Win Rate", f"{win_rate:.1f}%", f"{wins}W / {total - wins}L")
    else:
        col3.metric("🎯 Win Rate", "0%", "No trades yet")
except:
    col3.metric("🎯 Win Rate", "Error")

# Bot Status
try:
    last_operation = query_db(f"""
        SELECT created_at
        FROM bot_operations
        WHERE created_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
        ORDER BY created_at DESC
        LIMIT 1
    """)

    if not last_operation.empty:
        last_time = pd.to_datetime(last_operation['created_at'].iloc[0])
        now = datetime.now(last_time.tzinfo) if last_time.tzinfo else datetime.now()
        diff = (now - last_time).total_seconds() / 60

        if diff < 30:
            col4.metric("🟢 Status", "Active", f"{int(diff)}m ago")
        else:
            col4.metric("🟡 Status", "Idle", f"{int(diff)}m ago")
    else:
        col4.metric("⚪ Status", "Waiting", "No ops yet")
except:
    col4.metric("❌ Status", "Error")

st.markdown("---")

# ===== TABS =====
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Performance", "💼 Trade Journal", "📈 Open Positions", "🎯 AI Decisions"
])

# ===== TAB 1: PERFORMANCE =====
with tab1:
    st.subheader("📊 Account Balance Over Time")

    try:
        balance_data = query_db(f"""
            SELECT created_at, balance_usd
            FROM account_snapshots
            WHERE created_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY created_at ASC
        """)

        if not balance_data.empty and len(balance_data) > 1:
            initial = balance_data['balance_usd'].iloc[0]
            final = balance_data['balance_usd'].iloc[-1]
            pnl = final - initial

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=balance_data['created_at'],
                y=balance_data['balance_usd'],
                mode='lines+markers',
                name='Balance',
                line=dict(color='#00ff00' if pnl >= 0 else '#ff0000', width=2),
                marker=dict(size=4),
                fill='tozeroy',
                fillcolor='rgba(0,255,0,0.1)' if pnl >= 0 else 'rgba(255,0,0,0.1)'
            ))

            fig.update_layout(
                title=f"Balance dal {START_DATE.strftime('%Y-%m-%d')}",
                xaxis_title="Date",
                yaxis_title="Balance (USD)",
                hovermode='x unified',
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("In attesa di dati... Il bot deve completare almeno un ciclo.")
    except Exception as e:
        st.error(f"Errore: {e}")

    # P&L per Symbol
    st.subheader("💰 P&L by Symbol (dal start)")

    col_left, col_right = st.columns(2)

    with col_left:
        try:
            pnl_by_symbol = query_db(f"""
                SELECT
                    symbol,
                    SUM(pnl_usd) as total_pnl,
                    COUNT(*) as num_trades,
                    AVG(pnl_usd) as avg_pnl
                FROM trade_journal
                WHERE closed_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
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

                pnl_by_symbol['avg_pnl'] = pnl_by_symbol['avg_pnl'].round(2)
                pnl_by_symbol['total_pnl'] = pnl_by_symbol['total_pnl'].round(2)
                st.dataframe(pnl_by_symbol, use_container_width=True)
            else:
                st.info("Nessun trade chiuso ancora")
        except Exception as e:
            st.error(f"Errore: {e}")

    with col_right:
        try:
            operations = query_db(f"""
                SELECT
                    operation,
                    COUNT(*) as count
                FROM bot_operations
                WHERE created_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
                GROUP BY operation
            """)

            if not operations.empty:
                fig_ops = px.pie(
                    operations,
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

# ===== TAB 2: TRADE JOURNAL =====
with tab2:
    st.subheader("📒 Trade Journal (dal start)")

    try:
        trades = query_db(f"""
            SELECT
                symbol,
                direction,
                entry_price,
                exit_price,
                pnl_usd,
                pnl_percent,
                opened_at,
                closed_at,
                duration_minutes,
                close_reason
            FROM trade_journal
            WHERE closed_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY closed_at DESC
            LIMIT 50
        """)

        if not trades.empty:
            # Stats summary
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)

            total_pnl = trades['pnl_usd'].sum()
            avg_pnl = trades['pnl_usd'].mean()
            avg_duration = trades['duration_minutes'].mean()
            best_trade = trades['pnl_usd'].max()
            worst_trade = trades['pnl_usd'].min()

            col_s1.metric("Total P&L", f"${total_pnl:.2f}")
            col_s2.metric("Avg P&L/Trade", f"${avg_pnl:.2f}")
            col_s3.metric("Avg Duration", f"{avg_duration:.0f} min")
            col_s4.metric("Best / Worst", f"${best_trade:.2f} / ${worst_trade:.2f}")

            st.markdown("---")

            # Format display
            trades['pnl_usd'] = trades['pnl_usd'].apply(lambda x: f"${x:.2f}")
            trades['pnl_percent'] = trades['pnl_percent'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
            trades['entry_price'] = trades['entry_price'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
            trades['exit_price'] = trades['exit_price'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")

            st.dataframe(trades, use_container_width=True, height=400)
        else:
            st.info("Nessun trade chiuso dal start date")
    except Exception as e:
        st.error(f"Errore: {e}")

# ===== TAB 3: OPEN POSITIONS =====
with tab3:
    st.subheader("📈 Posizioni Attualmente Aperte")

    try:
        # Ultima snapshot
        latest_snap = query_db("""
            SELECT id FROM account_snapshots ORDER BY created_at DESC LIMIT 1
        """)

        if not latest_snap.empty:
            snap_id = latest_snap['id'].iloc[0]

            positions = query_db(f"""
                SELECT
                    symbol,
                    side,
                    entry_price,
                    mark_price,
                    size,
                    leverage,
                    pnl_usd,
                    created_at
                FROM open_positions
                WHERE snapshot_id = {snap_id}
                ORDER BY symbol
            """)

            if not positions.empty:
                # Summary
                total_unrealized = positions['pnl_usd'].sum() if 'pnl_usd' in positions.columns else 0

                st.metric("💵 Total Unrealized P&L", f"${total_unrealized:.2f}")
                st.markdown("---")

                # Format
                for col in ['entry_price', 'mark_price']:
                    if col in positions.columns:
                        positions[col] = positions[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")

                if 'pnl_usd' in positions.columns:
                    positions['pnl_usd'] = positions['pnl_usd'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")

                st.dataframe(positions, use_container_width=True)
            else:
                st.info("Nessuna posizione aperta al momento")
        else:
            st.info("Nessuna snapshot disponibile")
    except Exception as e:
        st.error(f"Errore: {e}")

# ===== TAB 4: AI DECISIONS =====
with tab4:
    st.subheader("🎯 Ultime Decisioni AI (dal start)")

    try:
        decisions = query_db(f"""
            SELECT
                symbol,
                operation,
                direction,
                confidence,
                reasoning,
                created_at
            FROM bot_operations
            WHERE created_at >= '{START_DATE.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY created_at DESC
            LIMIT 100
        """)

        if not decisions.empty:
            # Filtro per operation
            ops = ['All'] + list(decisions['operation'].unique())
            selected_op = st.selectbox("Filtra per operazione:", ops)

            if selected_op != 'All':
                decisions = decisions[decisions['operation'] == selected_op]

            # Stats
            col_d1, col_d2, col_d3 = st.columns(3)
            col_d1.metric("Total Decisions", len(decisions))
            col_d2.metric("Opens", len(decisions[decisions['operation'] == 'open']))
            col_d3.metric("Closes", len(decisions[decisions['operation'] == 'close']))

            st.markdown("---")

            # Show decisions
            for _, row in decisions.head(20).iterrows():
                op = row['operation']
                symbol = row['symbol']
                direction = row.get('direction', '')
                confidence = row.get('confidence', 'N/A')
                reasoning = row.get('reasoning', 'N/A')
                time = row['created_at']

                if op == 'open':
                    icon = "🟢"
                elif op == 'close':
                    icon = "🔴"
                else:
                    icon = "⚪"

                with st.expander(f"{icon} {time} - {symbol} {op.upper()} {direction}"):
                    st.write(f"**Confidence:** {confidence}")
                    st.write(f"**Reasoning:** {reasoning}")
        else:
            st.info("Nessuna decisione AI registrata dal start date")
    except Exception as e:
        st.error(f"Errore: {e}")

# ===== FOOTER =====
st.markdown("---")
st.markdown(f"""
<div style='text-align: center; color: gray;'>
    Fresh Dashboard | Data Start: {START_DATE.strftime('%Y-%m-%d %H:%M')} |
    Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>
""", unsafe_allow_html=True)

# Auto-refresh ogni 60 secondi
st.markdown("""
<script>
    setTimeout(function(){
        window.location.reload();
    }, 60000);
</script>
""", unsafe_allow_html=True)
