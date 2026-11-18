import os
import secrets
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import (
    get_devices_for_owner,
    create_device,
    get_latest_reading_for_device,
    get_readings_for_device,
    create_manure_sample,
    get_samples_for_farmer,
    get_delivered_crop_and_report_for_farmer,
    get_notifications_for_farmer,
    mark_notification_as_read
)
from auth import hash_password

SOIL_TYPES = ["Alluvial", "Red", "Black", "Forest"]
CROPS = ["Tomato", "Potato", "Banana", "Cotton", "Sugarcane", "Paddy", "Maize"]

# Reference NPK benchmarks by soil type (kg/ha) for comparison
SOIL_BENCHMARKS = {
    "Alluvial": {"N": 95.0, "P": 55.0, "K": 75.0},
    "Red":      {"N": 75.0, "P": 45.0, "K": 60.0},
    "Black":    {"N": 110.0, "P": 65.0, "K": 90.0},
    "Forest":   {"N": 85.0, "P": 60.0, "K": 80.0}
}

def format_reading_age(received_at_str: str) -> str:
    """Calculate human-readable age of a sensor reading."""
    try:
        try:
            dt = datetime.strptime(received_at_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.fromisoformat(received_at_str.replace("Z", ""))
        seconds = (datetime.utcnow() - dt).total_seconds()
        if seconds < 60:
            return f"{int(seconds)} seconds ago"
        elif seconds < 3600:
            return f"{int(seconds // 60)} minutes ago"
        elif seconds < 86400:
            return f"{int(seconds // 3600)} hours ago"
        else:
            return f"{int(seconds // 86400)} days ago"
    except Exception:
        return received_at_str

def farmer_pages(user: dict):
    farmer_id = user["id"]

    menu_option = st.sidebar.radio(
        "Farmer Operations",
        ["📝 Add Manure Details", "📊 Farmer Dashboard", "🌾 Most Suitable Crop"],
        key="farmer_nav_menu"
    )

    # ================= 1. ADD MANURE DETAILS =================
    if menu_option == "📝 Add Manure Details":
        st.header("📝 Add Organic Manure Details")
        st.markdown(
            "Submit laboratory nutrient measurements paired with live ESP32 sensor telemetry "
            "for agricultural authority review and crop suitability advisory."
        )

        devices = get_devices_for_owner(farmer_id)

        # Device Registration Sub-section
        with st.expander("➕ Register a New ESP32 Sensor Node", expanded=(len(devices) == 0)):
            st.markdown("Register an IoT telemetry device to transmit temperature and moisture.")
            with st.form("register_device_form"):
                new_dev_name = st.text_input("Device Name / Identifier (e.g., ESP32-Compost-01)").strip()
                reg_dev_submitted = st.form_submit_button("Generate Device API Key", type="primary")

                if reg_dev_submitted:
                    if not new_dev_name:
                        st.error("Please provide a device identifier.")
                    else:
                        try:
                            # Generate a high-entropy secret token
                            raw_token = secrets.token_hex(16)
                            # Create device record first to get ID
                            temp_hash = hash_password(secrets.token_hex(8))
                            new_dev_id = create_device(farmer_id, new_dev_name, temp_hash)
                            
                            # Final key with DEV_{id}_{token} prefix
                            final_raw_key = f"DEV_{new_dev_id}_{raw_token}"
                            final_hash = hash_password(final_raw_key)

                            # Update database with final hash
                            from db import get_connection
                            conn = get_connection()
                            conn.execute("UPDATE devices SET api_key_hash = ? WHERE id = ?", (final_hash, new_dev_id))
                            conn.commit()
                            conn.close()

                            st.session_state["just_registered_key"] = final_raw_key
                            st.session_state["just_registered_dev"] = new_dev_name
                            st.rerun()
                        except Exception as e:
                            st.error(f"Device registration failed: {e}")

        # Show key once banner if newly registered
        if "just_registered_key" in st.session_state:
            st.warning(
                f"⚠️ **Device API Key Generated for '{st.session_state['just_registered_dev']}':**\n\n"
                f"```text\n{st.session_state['just_registered_key']}\n```\n"
                "**IMPORTANT:** Copy and flash this key into your ESP32 firmware now. "
                "For security, this raw key will **never be shown again**."
            )
            if st.button("I have safely recorded my API key"):
                del st.session_state["just_registered_key"]
                del st.session_state["just_registered_dev"]
                st.rerun()

        if not devices:
            st.info("No registered devices found. Please register an ESP32 device above to proceed.")
            return

        # Device Selection & Real Sensor Reading
        st.subheader("1. Connect Live ESP32 Telemetry")
        dev_options = {d["id"]: f"{d['device_name']} (ID: {d['id']})" for d in devices}
        selected_dev_id = st.selectbox(
            "Select Your Registered ESP32 Device",
            options=list(dev_options.keys()),
            format_func=lambda x: dev_options[x]
        )

        col_ref, col_auto = st.columns([2, 4])
        with col_ref:
            if st.button("🔄 Refresh Sensor Telemetry"):
                st.rerun()

        latest_reading = get_latest_reading_for_device(selected_dev_id)

        if not latest_reading:
            st.error(
                f"❌ No telemetry readings received yet from device '{dev_options[selected_dev_id]}'.\n\n"
                "Ensure your ESP32 is powered, connected to Wi-Fi, and configured with this device's API key. "
                "The system operates with **REAL SENSOR DATA ONLY**."
            )
            return

        # Display Real Reading
        reading_age = format_reading_age(latest_reading["received_at"])
        col_t, col_m, col_ts, col_age = st.columns(4)
        with col_t:
            st.metric("Temperature", f"{latest_reading['temperature_c']:.1f} °C")
        with col_m:
            st.metric("Moisture", f"{latest_reading['moisture_percent']:.1f} %")
        with col_ts:
            st.metric("Timestamp", str(latest_reading["received_at"]))
        with col_age:
            st.metric("Reading Age", reading_age)

        st.subheader("2. Manure Nutrients & Sample Submission")
        with st.form("submit_manure_form"):
            st.markdown("##### Manual Laboratory NPK Inputs (kg/ha)")
            col_n, col_p, col_k = st.columns(3)
            with col_n:
                val_n = st.number_input("Nitrogen (N) [0 - 200]", min_value=0.0, max_value=200.0, value=75.0, step=0.5)
            with col_p:
                val_p = st.number_input("Phosphorus (P) [0 - 200]", min_value=0.0, max_value=200.0, value=50.0, step=0.5)
            with col_k:
                val_k = st.number_input("Potassium (K) [0 - 200]", min_value=0.0, max_value=200.0, value=65.0, step=0.5)

            col_soil, col_crop = st.columns(2)
            with col_soil:
                val_soil = st.selectbox("Soil Type", SOIL_TYPES)
            with col_crop:
                val_crop = st.selectbox("Farmer Preferred Crop", CROPS)

            st.markdown("---")
            confirm_check = st.checkbox(
                f"I verify that the sensor readings (Temp: {latest_reading['temperature_c']} °C, "
                f"Moisture: {latest_reading['moisture_percent']} %) and entered NPK values are accurate."
            )

            submit_btn = st.form_submit_button("Submit Manure Sample to Authority", type="primary")

            if submit_btn:
                if not confirm_check:
                    st.error("Please confirm the verification checkbox to submit the sample.")
                else:
                    try:
                        res = create_manure_sample(
                            farmer_id=farmer_id,
                            device_id=selected_dev_id,
                            reading_id=latest_reading["id"],
                            temperature_c=latest_reading["temperature_c"],
                            moisture_percent=latest_reading["moisture_percent"],
                            nitrogen=val_n,
                            phosphorus=val_p,
                            potassium=val_k,
                            soil_type=val_soil,
                            preferred_crop=val_crop
                        )
                        st.success(
                            f"✅ Sample successfully submitted! Assigned Sample Code: **{res['sample_code']}** "
                            f"(Status: **PENDING** review)."
                        )
                    except Exception as e:
                        st.error(f"Failed to submit manure sample: {e}")

    # ================= 2. FARMER DASHBOARD =================
    elif menu_option == "📊 Farmer Dashboard":
        st.header("📊 Farmer Analytics Dashboard")
        st.caption("Live monitoring and nutrient profile of your registered organic manure samples.")

        samples = get_samples_for_farmer(farmer_id)

        if not samples:
            st.info("No manure samples submitted yet. Use the 'Add Manure Details' page to submit your first sample.")
            return

        df_samples = pd.DataFrame([dict(s) for s in samples])

        # KPI Cards
        total_samples = len(df_samples)
        pending_count = len(df_samples[df_samples["status"] == "PENDING"])
        approved_count = len(df_samples[df_samples["status"] == "APPROVED"])
        latest_temp = df_samples["temperature_c"].iloc[0]
        latest_moist = df_samples["moisture_percent"].iloc[0]

        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total Submissions", total_samples)
        kpi2.metric("Pending Review", pending_count)
        kpi3.metric("Approved", approved_count)
        kpi4.metric("Latest Sensor Temp", f"{latest_temp:.1f} °C")
        kpi5.metric("Latest Sensor Moist", f"{latest_moist:.1f} %")

        st.markdown("---")

        # Filters
        with st.expander("🔍 Filter Analytics", expanded=False):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                dev_list = ["All Devices"] + sorted(list(df_samples["device_name"].dropna().unique()))
                chosen_dev = st.selectbox("Filter by Device", dev_list)
            with f_col2:
                soil_list = ["All Soils"] + sorted(list(df_samples["soil_type"].dropna().unique()))
                chosen_soil = st.selectbox("Filter by Soil Type", soil_list)

        filtered_df = df_samples.copy()
        if chosen_dev != "All Devices":
            filtered_df = filtered_df[filtered_df["device_name"] == chosen_dev]
        if chosen_soil != "All Soils":
            filtered_df = filtered_df[filtered_df["soil_type"] == chosen_soil]

        if filtered_df.empty:
            st.warning("No records match the selected filters.")
            return

        # Interactive Plotly Charts
        chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs([
            "🧪 NPK Profile & Composition",
            "🌱 Manure vs Soil & Radar Matrix",
            "📈 Sensor Dynamics & Correlation",
            "🌾 Crop & Soil Portfolio"
        ])

        with chart_tab1:
            st.subheader("Nitrogen, Phosphorus, and Potassium (NPK) Distribution")
            col_bar, col_donut = st.columns([3, 2])
            with col_bar:
                fig_npk = px.bar(
                    filtered_df,
                    x="sample_code",
                    y=["nitrogen", "phosphorus", "potassium"],
                    barmode="group",
                    title="Chemical Nutrient Levels per Sample (kg/ha)",
                    labels={"value": "Nutrient Level (kg/ha)", "sample_code": "Sample Code", "variable": "Nutrient"},
                    hover_data=["soil_type", "preferred_crop", "status"],
                    color_discrete_map={"nitrogen": "#2563EB", "phosphorus": "#10B981", "potassium": "#F59E0B"}
                )
                fig_npk.update_layout(template="plotly_white", legend_title_text="Nutrients", margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_npk, use_container_width=True)

            with col_donut:
                sample_choices = filtered_df["sample_code"].tolist()
                picked_sample = st.selectbox("Inspect Nutrient Share for Sample", sample_choices, key="farmer_pie_pick")
                p_row = filtered_df[filtered_df["sample_code"] == picked_sample].iloc[0]
                pie_data = pd.DataFrame({
                    "Nutrient": ["Nitrogen (N)", "Phosphorus (P)", "Potassium (K)"],
                    "Amount": [p_row["nitrogen"], p_row["phosphorus"], p_row["potassium"]]
                })
                fig_donut = px.pie(
                    pie_data,
                    names="Nutrient",
                    values="Amount",
                    hole=0.5,
                    title=f"NPK Share for {picked_sample}",
                    color="Nutrient",
                    color_discrete_map={
                        "Nitrogen (N)": "#2563EB",
                        "Phosphorus (P)": "#10B981",
                        "Potassium (K)": "#F59E0B"
                    }
                )
                fig_donut.update_traces(textinfo="percent+label", pull=[0.02, 0.02, 0.02])
                fig_donut.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_donut, use_container_width=True)

        with chart_tab2:
            st.subheader("Nutrient Comparison & Multi-Dimensional Radar Analysis")
            col_bench, col_radar = st.columns([3, 2])
            sample_choices = filtered_df["sample_code"].tolist()
            picked_sample_code = st.selectbox("Select Sample to Analyze", sample_choices, key="farmer_bench_pick")
            picked_row = filtered_df[filtered_df["sample_code"] == picked_sample_code].iloc[0]
            soil_ref = SOIL_BENCHMARKS.get(picked_row["soil_type"], {"N": 80, "P": 50, "K": 70})

            with col_bench:
                comp_df = pd.DataFrame({
                    "Nutrient": ["Nitrogen (N)", "Phosphorus (P)", "Potassium (K)"],
                    "Sample Measured": [picked_row["nitrogen"], picked_row["phosphorus"], picked_row["potassium"]],
                    "Soil Benchmark": [soil_ref["N"], soil_ref["P"], soil_ref["K"]]
                })

                fig_comp = go.Figure()
                fig_comp.add_trace(go.Bar(
                    x=comp_df["Nutrient"],
                    y=comp_df["Sample Measured"],
                    name="Measured in Manure",
                    marker_color="#3B82F6"
                ))
                fig_comp.add_trace(go.Bar(
                    x=comp_df["Nutrient"],
                    y=comp_df["Soil Benchmark"],
                    name=f"Standard Benchmark ({picked_row['soil_type']} Soil)",
                    marker_color="#94A3B8"
                ))
                fig_comp.update_layout(
                    barmode="group",
                    title=f"{picked_sample_code} vs {picked_row['soil_type']} Standard",
                    yaxis_title="kg/ha",
                    template="plotly_white",
                    margin=dict(t=40, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            with col_radar:
                # Radar Chart: Normalized parameters (N, P, K, Temp, Moisture)
                categories = ["Nitrogen", "Phosphorus", "Potassium", "Temperature", "Moisture"]
                # Normalizing roughly to 0-100 scale for intuitive radar comparison
                norm_n = min(100.0, (picked_row["nitrogen"] / 150.0) * 100.0)
                norm_p = min(100.0, (picked_row["phosphorus"] / 100.0) * 100.0)
                norm_k = min(100.0, (picked_row["potassium"] / 150.0) * 100.0)
                norm_t = min(100.0, (picked_row["temperature_c"] / 50.0) * 100.0)
                norm_m = float(picked_row["moisture_percent"])

                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=[norm_n, norm_p, norm_k, norm_t, norm_m, norm_n],
                    theta=categories + [categories[0]],
                    fill='toself',
                    name=picked_sample_code,
                    line_color='#8B5CF6',
                    fillcolor='rgba(139, 92, 246, 0.3)'
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    title="Agronomic Profile Balance (Radar)",
                    template="plotly_white",
                    margin=dict(t=40, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_radar, use_container_width=True)

        with chart_tab3:
            st.subheader("Physical Sensor Telemetry Dynamics")
            c_trend1, c_trend2 = st.columns([3, 2])
            with c_trend1:
                fig_trend = go.Figure()
                sorted_df = filtered_df.sort_values("submitted_at")
                fig_trend.add_trace(go.Scatter(
                    x=sorted_df["submitted_at"],
                    y=sorted_df["temperature_c"],
                    mode="lines+markers",
                    name="Temperature (°C)",
                    line=dict(color="#F43F5E", width=2.5),
                    marker=dict(size=6)
                ))
                fig_trend.add_trace(go.Scatter(
                    x=sorted_df["submitted_at"],
                    y=sorted_df["moisture_percent"],
                    mode="lines+markers",
                    name="Moisture (%)",
                    line=dict(color="#0EA5E9", width=2.5),
                    marker=dict(size=6)
                ))
                fig_trend.update_layout(
                    title="Sensor Temperature & Moisture Progression",
                    xaxis_title="Submission Date",
                    yaxis_title="Sensor Units (°C / %)",
                    template="plotly_white",
                    hovermode="x unified",
                    margin=dict(t=40, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_trend, use_container_width=True)

            with c_trend2:
                # Scatter correlation: Temperature vs Moisture colored by Nitrogen
                fig_corr = px.scatter(
                    filtered_df,
                    x="temperature_c",
                    y="moisture_percent",
                    color="nitrogen",
                    size="potassium",
                    hover_name="sample_code",
                    title="Temp vs Moisture Correlation",
                    labels={"temperature_c": "Temperature (°C)", "moisture_percent": "Moisture (%)", "nitrogen": "Nitrogen"},
                    color_continuous_scale="Turbo"
                )
                fig_corr.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_corr, use_container_width=True)

        with chart_tab4:
            st.subheader("Portfolio Distribution across Crops and Soils")
            col_crop_pie, col_soil_bar = st.columns(2)
            with col_crop_pie:
                crop_counts = filtered_df["preferred_crop"].value_counts().reset_index()
                crop_counts.columns = ["Crop", "Count"]
                fig_crop_donut = px.pie(
                    crop_counts,
                    names="Crop",
                    values="Count",
                    hole=0.45,
                    title="Farmer Preferred Crops Distribution",
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig_crop_donut.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_crop_donut, use_container_width=True)

            with col_soil_bar:
                soil_counts = filtered_df["soil_type"].value_counts().reset_index()
                soil_counts.columns = ["Soil Type", "Submissions"]
                fig_soil_bar = px.bar(
                    soil_counts,
                    x="Soil Type",
                    y="Submissions",
                    color="Soil Type",
                    title="Submissions by Soil Classification",
                    color_discrete_sequence=["#10B981", "#F59E0B", "#3B82F6", "#8B5CF6"]
                )
                fig_soil_bar.update_layout(template="plotly_white", showlegend=False, margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_soil_bar, use_container_width=True)

        # Samples Table
        st.subheader("Submitted Samples History")
        display_cols = [
            "sample_code", "device_name", "temperature_c", "moisture_percent",
            "nitrogen", "phosphorus", "potassium", "soil_type", "preferred_crop",
            "status", "submitted_at"
        ]
        st.dataframe(filtered_df[display_cols], use_container_width=True)

    # ================= 3. MOST SUITABLE CROP =================
    elif menu_option == "🌾 Most Suitable Crop":
        st.header("🌾 Crop Suitability Recommendations")
        st.caption("Official agronomic advisory and AI predictions for your verified organic manure samples.")

        # Notifications Header
        notifs = get_notifications_for_farmer(farmer_id, unread_only=True)
        if notifs:
            st.info(f"🔔 **You have {len(notifs)} new notification(s):**")
            for n in notifs:
                col_msg, col_read = st.columns([5, 1])
                with col_msg:
                    st.write(f"• **{n['message']}** ({format_reading_age(n['created_at'])})")
                with col_read:
                    if st.button("Mark Read", key=f"notif_{n['id']}"):
                        mark_notification_as_read(n["id"])
                        st.rerun()
            st.markdown("---")

        # Query all samples submitted by this farmer
        all_samples = get_samples_for_farmer(farmer_id)
        if not all_samples:
            st.info("No samples submitted yet. Once you submit samples and authorities review them, recommendations will appear here.")
            return

        # Query only DELIVERED samples with predictions (enforced at query level)
        delivered_records = get_delivered_crop_and_report_for_farmer(farmer_id)
        delivered_map = {r["id"]: r for r in delivered_records}

        st.subheader("Submissions Status & Advisory Access")

        for s in all_samples:
            s_id = s["id"]
            code = s["sample_code"]
            status_val = s["status"]

            with st.container():
                st.markdown(f"#### Sample **{code}** (Preferred Crop: *{s['preferred_crop']}* | Soil: *{s['soil_type']}*)")
                
                if status_val == "PENDING":
                    st.markdown(
                        "<span class='badge-pending'>⏳ PENDING</span> – Under review by agricultural authority. "
                        "Advisories are released only after laboratory and sensor approval.",
                        unsafe_allow_html=True
                    )
                elif status_val == "REJECTED":
                    note = s["review_note"] or "Did not meet required organic standards."
                    st.markdown(
                        f"<span class='badge-rejected'>❌ REJECTED</span> – **Reviewer Note:** {note}",
                        unsafe_allow_html=True
                    )
                elif status_val == "APPROVED":
                    if s_id not in delivered_map:
                        st.markdown(
                            "<span class='badge-success'>✅ APPROVED</span> – Sample approved by authority. "
                            "Advisory report is being compiled and prepared for in-app delivery.",
                            unsafe_allow_html=True
                        )
                    else:
                        deliv = delivered_map[s_id]
                        st.markdown(
                            "<span class='badge-success'>📬 DELIVERED IN-APP</span> – Official advisory report is ready.",
                            unsafe_allow_html=True
                        )

                        # Top 2 crops card
                        col_c1, col_c2, col_dl = st.columns([2, 2, 2])
                        with col_c1:
                            st.markdown(f"🥇 **Primary Crop (Top-1):**\n### `{deliv['top1_crop']}`")
                        with col_c2:
                            st.markdown(f"🥈 **Alternative Crop (Top-2):**\n### `{deliv['top2_crop']}`")
                        with col_dl:
                            if deliv["pdf_blob"]:
                                st.download_button(
                                    label="📄 Download Advisory Report (PDF)",
                                    data=deliv["pdf_blob"],
                                    file_name=f"GOBARdhan_Advisory_{code}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_{s_id}",
                                    type="primary"
                                )
                st.markdown("---")
