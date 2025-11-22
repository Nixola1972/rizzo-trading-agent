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
                        data_tab1, data_tab2, data_tab3, data_tab4 = st.tabs([
                            "📈 Indicatori", "😊 Sentiment", "🔮 Forecasts", "📰 News"
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
                                    # Mostra le news formattate
                                    st.text_area("📰 News analizzate dall'AI", news_text, height=300)
                                else:
                                    st.info("Nessuna news disponibile")
                            else:
                                st.info("Nessuna news disponibile")

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
