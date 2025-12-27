import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st


DATA_PATH = os.path.join("data", "market_data_master.csv")


@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df


@st.cache_data(show_spinner=False)
def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    df = df.copy()

    # Basic cleaning
    if "arrivaldate" in df.columns:
        df.rename(columns={"arrivaldate": "arrival_date"}, inplace=True)

    df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")
    if "state" in df.columns:
        df["state"] = df["state"].astype(str).str.strip()
    if "district" in df.columns:
        df["district"] = df["district"].astype(str).str.strip()
    if "market" in df.columns:
        df["market"] = df["market"].astype(str).str.strip()
    if "commodity" in df.columns:
        df["commodity"] = df["commodity"].astype(str).str.strip()

    for col in ["minprice", "maxprice", "modalprice"]:
        if col in df.columns:
            df.rename(columns={col: col.replace("price", "_price")}, inplace=True)

    for col in ["min_price", "max_price", "modal_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop obviously invalid rows
    if {"min_price", "max_price"}.issubset(df.columns):
        df = df[df["min_price"] > 0]
        df = df[df["max_price"] >= df["min_price"]]

    if "arrival_date" in df.columns:
        df = df.dropna(subset=["arrival_date"])
        df["year"] = df["arrival_date"].dt.year
        df["month"] = df["arrival_date"].dt.month

    return df


def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    st.sidebar.header("Filters")

    # State filter
    states = sorted(df["state"].dropna().unique().tolist()) if "state" in df.columns else []
    selected_states = st.sidebar.multiselect(
        "State",
        options=states,
        default=states[:3] if states else [],
    )

    # District filter
    if selected_states and "district" in df.columns and "state" in df.columns:
        dist_options = (
            df[df["state"].isin(selected_states)]["district"]
            .dropna()
            .sort_values()
            .unique()
            .tolist()
        )
    else:
        dist_options = []

    selected_districts = st.sidebar.multiselect(
        "District",
        options=dist_options,
        default=dist_options[:5] if dist_options else [],
    )

    # Advanced filters
    with st.sidebar.expander("Advanced filters"):
        if "commodity" in df.columns:
            commodities = (
                df["commodity"].dropna().sort_values().unique().tolist()
            )
            selected_commodities = st.multiselect(
                "Commodity",
                options=commodities,
                default=commodities[:5] if commodities else [],
            )
        else:
            selected_commodities = []

        min_date, max_date = None, None
        if "arrival_date" in df.columns:
            min_date = df["arrival_date"].min()
            max_date = df["arrival_date"].max()
            date_range = st.date_input(
                "Arrival date range",
                value=(min_date.date(), max_date.date()) if min_date and max_date else None,
            )
        else:
            date_range = None

    mask = pd.Series(True, index=df.index)

    if selected_states and "state" in df.columns:
        mask &= df["state"].isin(selected_states)
    if selected_districts and "district" in df.columns:
        mask &= df["district"].isin(selected_districts)
    if selected_commodities and "commodity" in df.columns:
        mask &= df["commodity"].isin(selected_commodities)

    if (
        date_range
        and isinstance(date_range, (tuple, list))
        and len(date_range) == 2
        and "arrival_date" in df.columns
    ):
        start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        mask &= df["arrival_date"].between(start, end)

    return df[mask].copy()


def overview_tab(df: pd.DataFrame):
    st.subheader("Overview")

    if df.empty:
        st.info("No data to display for current filters.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Records", f"{len(df):,}")
    with col2:
        if "state" in df.columns:
            st.metric("States", df["state"].nunique())
    with col3:
        if "commodity" in df.columns:
            st.metric("Commodities", df["commodity"].nunique())

    if {"arrival_date", "modal_price"}.issubset(df.columns):
        daily = (
            df.groupby("arrival_date", as_index=False)["modal_price"]
            .mean()
        )
        fig = px.line(
            daily,
            x="arrival_date",
            y="modal_price",
            title="Average modal price over time",
        )
        st.plotly_chart(fig, use_container_width=True)


def trends_tab(df: pd.DataFrame):
    st.subheader("Trends")

    if df.empty or "year" not in df.columns or "modal_price" not in df.columns:
        st.info("Not enough data for trend analysis.")
        return

    # Year-wise
    yearly = (
        df.groupby("year", as_index=False)["modal_price"]
        .mean()
        .sort_values("year")
    )
    fig_year = px.line(
        yearly,
        x="year",
        y="modal_price",
        markers=True,
        title="Average modal price by year",
    )
    st.plotly_chart(fig_year, use_container_width=True)

    # Monthly (within year)
    if "month" in df.columns:
        monthly = (
            df.groupby(["year", "month"], as_index=False)["modal_price"]
            .mean()
            .sort_values(["year", "month"])
        )
        monthly["year_month"] = monthly["year"].astype(str) + "-" + monthly["month"].astype(str)
        fig_month = px.line(
            monthly,
            x="year_month",
            y="modal_price",
            title="Average modal price by month",
        )
        st.plotly_chart(fig_month, use_container_width=True)


def analysis_tab(df: pd.DataFrame):
    st.subheader("Price analysis")

    if df.empty or "modal_price" not in df.columns:
        st.info("Not enough data for analysis.")
        return

    # Top commodities by price
    if "commodity" in df.columns and "state" in df.columns:
        top_n = st.slider("Top N commodities", 5, 30, 10, 1)
        agg = (
            df.groupby("commodity", as_index=False)["modal_price"]
            .mean()
            .sort_values("modal_price", ascending=False)
            .head(top_n)
        )
        fig_top = px.bar(
            agg,
            x="commodity",
            y="modal_price",
            title=f"Top {top_n} commodities by average modal price",
        )
        fig_top.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_top, use_container_width=True)

    # Boxplot distribution
    if "commodity" in df.columns:
        top_for_box = (
            df["commodity"].value_counts()
            .head(10)
            .index.tolist()
        )
        sub_df = df[df["commodity"].isin(top_for_box)]
        fig_box = px.box(
            sub_df,
            x="commodity",
            y="modal_price",
            title="Price distribution for top 10 commodities",
        )
        fig_box.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_box, use_container_width=True)

    # Min vs Max scatter
    if {"min_price", "max_price"}.issubset(df.columns):
        fig_scatter = px.scatter(
            df.sample(min(len(df), 3000), random_state=42)
            if len(df) > 3000 else df,
            x="min_price",
            y="max_price",
            color="commodity" if "commodity" in df.columns else None,
            title="Min vs Max price (sampled)",
            opacity=0.6,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)


def data_tab(df: pd.DataFrame):
    st.subheader("Filtered data")

    if df.empty:
        st.info("No data for current filters.")
        return

    display_cols = [
        c for c in df.columns
        if c
        in [
            "state",
            "district",
            "market",
            "commodity",
            "variety",
            "grade",
            "arrival_date",
            "min_price",
            "max_price",
            "modal_price",
        ]
        or c in ["year", "month"]
    ]

    st.write(f"Showing {min(1000, len(df)):,} of {len(df):,} records")
    st.dataframe(
        df[display_cols].head(1000),
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    csv = df[display_cols].to_csv(index=False)
    st.download_button(
        "📥 Download full filtered data (CSV)",
        data=csv,
        file_name=f"mandi_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


def details_tab(df: pd.DataFrame):
    st.subheader("Dataset details")

    if df.empty:
        st.info("No data loaded.")
        return

    st.write("**Raw columns**:")
    st.code(", ".join(df.columns))

    if "arrival_date" in df.columns:
        st.write(
            f"Date range: {df['arrival_date'].min().date()} → {df['arrival_date'].max().date()}"
        )
    if "state" in df.columns:
        st.write(f"States: {df['state'].nunique()}")
    if "district" in df.columns:
        st.write(f"Districts: {df['district'].nunique()}")
    if "market" in df.columns:
        st.write(f"Markets: {df['market'].nunique()}")
    if "commodity" in df.columns:
        st.write(f"Commodities: {df['commodity'].nunique()}")


def main():
    st.set_page_config(
        page_title="APMC / Mandi Market Dashboard",
        layout="wide",
    )

    st.title("APMC / Mandi Market Dashboard")

    df_raw = load_data(DATA_PATH)
    if df_raw.empty:
        st.error("No data found. Please ensure `data/market_data_master.csv` exists.")
        st.stop()

    df = prepare_data(df_raw)

    filtered_df = sidebar_filters(df)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 Overview", "📈 Trends", "🔍 Analysis", "📋 Data", "ℹ️ Details"]
    )

    with tab1:
        overview_tab(filtered_df)
    with tab2:
        trends_tab(filtered_df)
    with tab3:
        analysis_tab(filtered_df)
    with tab4:
        data_tab(filtered_df)
    with tab5:
        details_tab(filtered_df)


if __name__ == "__main__":
    main()
