"""
Production-Ready Streamlit Dashboard for Indian APMC Mandi Prices
Enhanced with caching, error handling, performance optimization, and advanced visualizations
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import logging
from datetime import datetime

# ============================================================================
# CONFIGURATION & LOGGING
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Indian APMC Market Prices Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Agricultural market price analysis dashboard for Indian APMC markets"
    }
)

# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA LOADING WITH CACHING
# ============================================================================

@st.cache_data
def load_data(file_path: str) -> pd.DataFrame:
    """
    Load market data CSV with caching to avoid reloading on every interaction
    
    Args:
        file_path: Path to the CSV file
    
    Returns:
        DataFrame with market data, or empty DataFrame if file not found
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"Data file not found: {file_path}")
            return pd.DataFrame()
        
        df = pd.read_csv(file_path)
        logger.info(f"Data loaded successfully: {len(df)} rows, {len(df.columns)} columns")
        return df
    
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")
        st.error(f"❌ Error loading data: {str(e)}")
        return pd.DataFrame()


@st.cache_data
def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare and transform data for analysis
    
    Args:
        df: Raw DataFrame
    
    Returns:
        Processed DataFrame with additional columns
    """
    if df.empty:
        return df
    
    df = df.copy()
    
    # Convert date column
    df['arrival_date'] = pd.to_datetime(df['arrival_date'], errors='coerce')
    
    # Extract date components
    df['year'] = df['arrival_date'].dt.year
    df['month'] = df['arrival_date'].dt.month
    df['month_name'] = df['arrival_date'].dt.strftime('%B')
    df['week'] = df['arrival_date'].dt.isocalendar().week
    df['day_of_week'] = df['arrival_date'].dt.day_name()
    
    # Calculate price metrics
    df['price_range'] = df['max_price'] - df['min_price']
    df['price_variance_pct'] = ((df['max_price'] - df['min_price']) / df['min_price'] * 100).round(2)
    
    return df


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    # Load and prepare data
    FILE_PATH = os.path.join("data", "market_data_master.csv")
    df = load_data(FILE_PATH)
    
    if df.empty:
        st.error("📊 No data available. Please check if the data file exists and is properly formatted.")
        st.info("Expected file path: data/market_data_master.csv")
        return
    
    # Prepare data
    df = prepare_data(df)
    
    # ========================================================================
    # TITLE & DESCRIPTION
    # ========================================================================
    
    st.title("📊 Indian APMC Market Prices Dashboard")
    st.markdown("""
    Real-time analysis of agricultural commodity prices across Indian APMC (Agricultural Produce Market Committee) markets.
    The data is updated automatically and provides insights into market trends, price variations, and regional comparisons.
    """)
    
    # Display last updated time
    col_info = st.columns(3)
    with col_info[0]:
        st.metric("📈 Total Records", f"{len(df):,}")
    with col_info[1]:
        st.metric("🗓️ Date Range", f"{df['arrival_date'].min().date()} to {df['arrival_date'].max().date()}")
    with col_info[2]:
        st.metric("📍 Unique Markets", df['market'].nunique())
    
    # ========================================================================
    # SIDEBAR FILTERS
    # ========================================================================
    
    st.sidebar.header("🔍 Filters")
    
    # Dynamic filter options
    states = st.sidebar.multiselect(
        "Select States",
        options=sorted(df['state'].unique()),
        default=sorted(df['state'].unique())[:3]  # Default to first 3 states for performance
    )
    
    # Districts conditional on states
    available_districts = df[df['state'].isin(states)]['district'].unique()
    districts = st.sidebar.multiselect(
        "Select Districts",
        options=sorted(available_districts),
        default=sorted(available_districts)[:5] if len(available_districts) > 0 else []
    )
    
    # Commodities
    commodities = st.sidebar.multiselect(
        "Select Commodities",
        options=sorted(df['commodity'].unique()),
        default=sorted(df['commodity'].unique())[:5]  # Default to first 5 for performance
    )
    
    # Advanced filters in expandable section
    with st.sidebar.expander("⚙️ Advanced Filters"):
        varieties = st.multiselect(
            "Varieties",
            options=sorted(df['variety'].unique()),
            default=sorted(df['variety'].unique())[:5]
        )
        
        grades = st.multiselect(
            "Grades",
            options=sorted(df['grade'].unique()),
            default=sorted(df['grade'].unique())[:3]
        )
        
        years = st.multiselect(
            "Years",
            options=sorted(df['year'].dropna().unique(), reverse=True),
            default=sorted(df['year'].dropna().unique(), reverse=True)[:2]
        )
    
    # Apply filters
    filtered_df = df[
        (df['state'].isin(states)) &
        (df['district'].isin(districts)) &
        (df['commodity'].isin(commodities)) &
        (df['variety'].isin(varieties)) &
        (df['grade'].isin(grades)) &
        (df['year'].isin(years))
    ].sort_values(by=['arrival_date', 'state', 'commodity'], ascending=[False, True, True])
    
    if filtered_df.empty:
        st.warning("⚠️ No data matches the selected filters. Please adjust your selection.")
        return
    
    # ========================================================================
    # KEY METRICS
    # ========================================================================
    
    st.subheader("📌 Key Metrics (₹)")
    
    metric_cols = st.columns(4)
    
    with metric_cols[0]:
        st.metric(
            "Avg Modal Price",
            f"₹{filtered_df['modal_price'].mean():.0f}",
            f"{(filtered_df['modal_price'].std()):.0f} σ"
        )
    
    with metric_cols[1]:
        st.metric(
            "Price Range",
            f"₹{filtered_df['price_range'].mean():.0f}",
            f"Avg per transaction"
        )
    
    with metric_cols[2]:
        st.metric(
            "Highest Price",
            f"₹{filtered_df['max_price'].max():.0f}",
            f"{filtered_df[filtered_df['max_price'] == filtered_df['max_price'].max()]['commodity'].values[0]}"
        )
    
    with metric_cols[3]:
        st.metric(
            "Lowest Price",
            f"₹{filtered_df['min_price'].min():.0f}",
            f"{filtered_df[filtered_df['min_price'] == filtered_df['min_price'].min()]['commodity'].values[0]}"
        )
    
    # ========================================================================
    # TABS FOR ORGANIZED CONTENT
    # ========================================================================
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 Overview", "📈 Trends", "🔍 Analysis", "📋 Data", "⚙️ Details"]
    )
    
    # ========================================================================
    # TAB 1: OVERVIEW
    # ========================================================================
    
    with tab1:
        st.subheader("Market Overview")
        
        col_overview = st.columns(2)
        
        with col_overview[0]:
            # Year-wise trend
            yearly_data = filtered_df.groupby('year').agg({
                'modal_price': 'mean',
                'min_price': 'mean',
                'max_price': 'mean'
            }).reset_index()
            
            fig_year = px.line(
                yearly_data,
                x='year',
                y=['min_price', 'max_price', 'modal_price'],
                markers=True,
                title="Year-wise Average Price Trends",
                labels={'value': 'Price (₹)', 'variable': 'Price Type'},
                hover_data={'year': ':.0f', 'value': ':.2f'}
            )
            fig_year.update_layout(hovermode='x unified')
            st.plotly_chart(fig_year, use_container_width=True)
        
        with col_overview[1]:
            # State-wise modal prices
            state_data = filtered_df.groupby('state')['modal_price'].mean().sort_values(ascending=False).head(10)
            
            fig_state = px.bar(
                x=state_data.values,
                y=state_data.index,
                orientation='h',
                title="Top 10 States by Average Modal Price",
                labels={'x': 'Average Modal Price (₹)', 'y': 'State'},
                color=state_data.values,
                color_continuous_scale='Viridis'
            )
            st.plotly_chart(fig_state, use_container_width=True)
        
        # Commodity price distribution
        st.subheader("Commodity Price Distribution")
        
        commodity_data = filtered_df.groupby('commodity').agg({
            'modal_price': ['mean', 'min', 'max'],
            'commodity': 'count'
        }).round(2)
        commodity_data.columns = ['Avg Price', 'Min Price', 'Max Price', 'Records']
        commodity_data = commodity_data.sort_values('Avg Price', ascending=False).head(15)
        
        fig_commodity = px.bar(
            x=commodity_data.index,
            y=commodity_data['Avg Price'],
            title="Top 15 Commodities by Average Price",
            labels={'x': 'Commodity', 'y': 'Price (₹)'},
            color=commodity_data['Avg Price'],
            color_continuous_scale='RdYlGn'
        )
        fig_commodity.update_xaxes(tickangle=45)
        st.plotly_chart(fig_commodity, use_container_width=True)
    
    # ========================================================================
    # TAB 2: TRENDS
    # ========================================================================
    
    with tab2:
        st.subheader("Price Trends Over Time")
        
        # Monthly trend
        col_trend = st.columns(1)
        
        with col_trend[0]:
            monthly_data = filtered_df.groupby(
                filtered_df['arrival_date'].dt.to_period('M')
            ).agg({
                'modal_price': 'mean',
                'min_price': 'mean',
                'max_price': 'mean',
                'price_range': 'mean'
            }).reset_index()
            monthly_data['arrival_date'] = monthly_data['arrival_date'].astype(str)
            
            fig_monthly = px.line(
                monthly_data,
                x='arrival_date',
                y=['min_price', 'modal_price', 'max_price'],
                title="Monthly Average Price Trends",
                labels={'value': 'Price (₹)', 'arrival_date': 'Month'},
                markers=True
            )
            fig_monthly.update_layout(hovermode='x unified')
            st.plotly_chart(fig_monthly, use_container_width=True)
        
        # Commodity comparison
        col_commodity = st.columns(1)
        
        with col_commodity[0]:
            selected_commodities = st.multiselect(
                "Select commodities to compare trends",
                options=sorted(filtered_df['commodity'].unique()),
                default=sorted(filtered_df['commodity'].unique())[:3]
            )
            
            if selected_commodities:
                commodity_trend = filtered_df[
                    filtered_df['commodity'].isin(selected_commodities)
                ].groupby(['arrival_date', 'commodity'])['modal_price'].mean().reset_index()
                
                fig_commodity_trend = px.line(
                    commodity_trend,
                    x='arrival_date',
                    y='modal_price',
                    color='commodity',
                    title="Commodity Price Trends Comparison",
                    labels={'modal_price': 'Price (₹)', 'arrival_date': 'Date'},
                    markers=True
                )
                fig_commodity_trend.update_layout(hovermode='x unified')
                st.plotly_chart(fig_commodity_trend, use_container_width=True)
    
    # ========================================================================
    # TAB 3: DETAILED ANALYSIS
    # ========================================================================
    
    with tab3:
        st.subheader("Advanced Analytics")
        
        col_analysis = st.columns(2)
        
        with col_analysis[0]:
            # Price distribution box plot
            fig_box = px.box(
                filtered_df,
                x='commodity',
                y='modal_price',
                color='state',
                title="Price Distribution by Commodity",
                labels={'modal_price': 'Modal Price (₹)'},
            )
            fig_box.update_xaxes(tickangle=45)
            st.plotly_chart(fig_box, use_container_width=True)
        
        with col_analysis[1]:
            # Min vs Max prices scatter
            fig_scatter = px.scatter(
                filtered_df.sample(min(1000, len(filtered_df))),  # Sample for performance
                x='min_price',
                y='max_price',
                color='commodity',
                size='price_range',
                hover_data=['state', 'market', 'arrival_date'],
                title="Min vs Max Price Correlation",
                labels={'min_price': 'Min Price (₹)', 'max_price': 'Max Price (₹)'},
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
        
        # State vs Commodity Heatmap
        st.subheader("State-Commodity Price Heatmap")
        
        heatmap_data = filtered_df.groupby(['state', 'commodity'])['modal_price'].mean().reset_index()
        
        fig_heatmap = px.density_heatmap(
            heatmap_data,
            x='commodity',
            y='state',
            nbinsx=40,
            nbinsy=15,
            color_continuous_scale='YlOrRd',
            title="Average Price Heatmap: State × Commodity"
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)
        
        # Price variance analysis
        st.subheader("Price Variance Analysis")
        
        col_variance = st.columns(2)
        
        with col_variance[0]:
            variance_commodity = filtered_df.groupby('commodity')['price_variance_pct'].mean().sort_values(ascending=False).head(10)
            
            fig_variance = px.bar(
                x=variance_commodity.values,
                y=variance_commodity.index,
                orientation='h',
                title="Top 10 Commodities by Price Variance %",
                labels={'x': 'Price Variance %'},
                color=variance_commodity.values,
                color_continuous_scale='Reds'
            )
            st.plotly_chart(fig_variance, use_container_width=True)
        
        with col_variance[1]:
            variance_state = filtered_df.groupby('state')['price_variance_pct'].mean().sort_values(ascending=False).head(10)
            
            fig_variance_state = px.bar(
                x=variance_state.values,
                y=variance_state.index,
                orientation='h',
                title="States by Average Price Variance %",
                labels={'x': 'Price Variance %'},
                color=variance_state.values,
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig_variance_state, use_container_width=True)
    
    # ========================================================================
    # TAB 4: DATA TABLE
    # ========================================================================
    
    with tab4:
        st.subheader("Detailed Market Data")
        
        # Data summary
        col_summary = st.columns(3)
        
        with col_summary[0]:
            st.metric("Filtered Records", f"{len(filtered_df):,}")
        with col_summary[1]:
            st.metric("States in Selection", filtered_df['state'].nunique())
        with col_summary[2]:
            st.metric("Commodities in Selection", filtered_df['commodity'].nunique())
        
        # Table display with limited rows
        st.write(f"Showing {min(1000, len(filtered_df)):,} of {len(filtered_df):,} records")
        
        display_columns = [
            'arrival_date', 'state', 'district', 'market', 'commodity',
            'variety', 'min_price', 'max_price', 'modal_price', 'price_range'
        ]
        
        display_df = filtered_df[display_columns].head(1000).copy()
        display_df['arrival_date'] = display_df['arrival_date'].dt.strftime('%Y-%m-%d')
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=500,
            hide_index=True
        )
        
        # Download data
        csv_data = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Filtered Data as CSV",
            data=csv_data,
            file_name=f"mandi_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # ========================================================================
    # TAB 5: AGGREGATED STATISTICS
    # ========================================================================
    
    with tab5:
        st.subheader("Aggregated Statistics")
        
        col_agg = st.columns(1)
        
        with col_agg[0]:
            # State-Commodity aggregation
            st.write("**State & Commodity Aggregation:**")
            agg_state_commodity = filtered_df.groupby(['state', 'commodity']).agg({
                'min_price': 'min',
                'max_price': 'max',
                'modal_price': 'mean',
                'price_range': 'mean',
                'market': 'count'
            }).round(2).reset_index()
            agg_state_commodity.columns = ['State', 'Commodity', 'Min Price', 'Max Price', 'Avg Modal', 'Avg Range', 'Records']
            agg_state_commodity = agg_state_commodity.sort_values('Avg Modal', ascending=False).head(50)
            
            st.dataframe(agg_state_commodity, use_container_width=True, hide_index=True)
            
            # Price statistics by state
            st.write("**Price Statistics by State:**")
            state_stats = filtered_df.groupby('state').agg({
                'modal_price': ['count', 'mean', 'median', 'std', 'min', 'max']
            }).round(2)
            state_stats.columns = ['Records', 'Mean Price', 'Median Price', 'Std Dev', 'Min Price', 'Max Price']
            
            st.dataframe(state_stats.sort_values('Mean Price', ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
