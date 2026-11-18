import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import (
    get_all_samples_with_details,
    get_sample_by_id,
    update_sample_review,
    create_prediction,
    get_prediction_for_sample,
    save_report,
    deliver_report,
    get_report_for_sample,
    create_notification,
    get_all_devices,
    get_readings_for_device
)
from ml import predict_top2, get_model_metrics, MODEL_NOTE
from report import generate_pdf_report

def authority_pages(user: dict):
    officer_id = user["id"]

    menu_option = st.sidebar.radio(
        "Authority Review Menu",
        ["📋 Manure Details Review", "🤖 Crop Prediction & Advisory", "📈 Aggregate Manure Analysis"],
        key="auth_nav_menu"
    )

    # Info banner regarding synthetic ML model
    with st.sidebar.expander("ℹ️ ML Model Governance & Transparency"):
        st.markdown(f"**Version:** 1.0.0-rf (Random Forest)\n\n_{MODEL_NOTE}_")

    # ================= 1. MANURE DETAILS REVIEW =================
    if menu_option == "📋 Manure Details Review":
        st.header("📋 Manure Submissions Review")
        st.caption("Inspect laboratory tests and IoT sensor telemetry for registered farmer manure samples.")

        all_samples = get_all_samples_with_details()

        if not all_samples:
            st.info("No manure samples submitted yet across the portal.")
            return

        df_all = pd.DataFrame([dict(s) for s in all_samples])

        # Filters
        f1, f2, f3 = st.columns(3)
        with f1:
            status_filter = st.selectbox("Filter by Status", ["All Statuses", "PENDING", "APPROVED", "REJECTED"])
        with f2:
            soil_filter = st.selectbox("Filter by Soil Type", ["All Soils"] + sorted(list(df_all["soil_type"].unique())))
        with f3:
            farmer_filter = st.selectbox("Filter by Farmer", ["All Farmers"] + sorted(list(df_all["farmer_name"].unique())))

        filtered = df_all.copy()
        if status_filter != "All Statuses":
            filtered = filtered[filtered["status"] == status_filter]
        if soil_filter != "All Soils":
            filtered = filtered[filtered["soil_type"] == soil_filter]
        if farmer_filter != "All Farmers":
            filtered = filtered[filtered["farmer_name"] == farmer_filter]

        st.subheader("Submissions Table")
        st.dataframe(
            filtered[[
                "id", "sample_code", "farmer_name", "device_name",
                "temperature_c", "moisture_percent", "nitrogen", "phosphorus",
                "potassium", "soil_type", "preferred_crop", "status", "submitted_at"
            ]],
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("Decision & Verification Workflow")

        pending_samples = [s for s in all_samples if s["status"] == "PENDING"]
        if not pending_samples:
            st.success("🎉 All pending submissions have been reviewed.")
        else:
            pending_options = {s["id"]: f"{s['sample_code']} - {s['farmer_name']} ({s['soil_type']}, Crop: {s['preferred_crop']})" for s in pending_samples}
            chosen_sample_id = st.selectbox(
                "Select a Pending Sample to Review",
                options=list(pending_options.keys()),
                format_func=lambda x: pending_options[x]
            )

            chosen_sample = get_sample_by_id(chosen_sample_id)

            c_info1, c_info2, c_info3 = st.columns(3)
            with c_info1:
                st.write(f"**Farmer:** {chosen_sample['farmer_name']}")
                st.write(f"**Email:** {chosen_sample['farmer_email']}")
                st.write(f"**Device:** {chosen_sample['device_name']}")
            with c_info2:
                st.write(f"**Sensor Temp:** {chosen_sample['temperature_c']} °C")
                st.write(f"**Sensor Moisture:** {chosen_sample['moisture_percent']} %")
                st.write(f"**Soil Type:** {chosen_sample['soil_type']}")
            with c_info3:
                st.write(f"**Nitrogen (N):** {chosen_sample['nitrogen']} kg/ha")
                st.write(f"**Phosphorus (P):** {chosen_sample['phosphorus']} kg/ha")
                st.write(f"**Potassium (K):** {chosen_sample['potassium']} kg/ha")

            with st.form("review_action_form"):
                review_note = st.text_area("Review Remarks / Agronomic Notes", value="Quality criteria verified against standards.")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    approve_btn = st.form_submit_button("✅ Approve Sample", type="primary")
                with action_col2:
                    reject_btn = st.form_submit_button("❌ Reject Sample")

                if approve_btn:
                    success = update_sample_review(
                        sample_id=chosen_sample_id,
                        status="APPROVED",
                        reviewed_by=officer_id,
                        review_note=review_note
                    )
                    if success:
                        st.success(f"Sample {chosen_sample['sample_code']} APPROVED! Proceed to 'Crop Prediction & Advisory' to generate recommendation.")
                        st.rerun()
                    else:
                        st.error("Approval failed or sample was already processed.")

                if reject_btn:
                    success = update_sample_review(
                        sample_id=chosen_sample_id,
                        status="REJECTED",
                        reviewed_by=officer_id,
                        review_note=review_note
                    )
                    if success:
                        st.warning(f"Sample {chosen_sample['sample_code']} marked as REJECTED.")
                        st.rerun()
                    else:
                        st.error("Action failed or sample was already processed.")

    # ================= 2. CROP PREDICTION & ADVISORY =================
    elif menu_option == "🤖 Crop Prediction & Advisory":
        st.header("🤖 Crop Suitability Advisory Generator")
        st.caption("Execute ML inference on approved manure samples, generate official advisory reports, and deliver in-app.")

        all_samples = get_all_samples_with_details()
        approved_samples = [s for s in all_samples if s["status"] == "APPROVED"]

        if not approved_samples:
            st.info("No approved samples available for crop prediction. Please approve pending submissions in the Review tab.")
            return

        sample_options = {s["id"]: f"{s['sample_code']} - {s['farmer_name']} ({s['soil_type']}, Preferred: {s['preferred_crop']})" for s in approved_samples}
        selected_id = st.selectbox(
            "Select Approved Manure Sample",
            options=list(sample_options.keys()),
            format_func=lambda x: sample_options[x]
        )

        sample = get_sample_by_id(selected_id)

        # Display Stored Features
        st.subheader("1. Stored Agronomic & Telemetry Features")
        f_col1, f_col2, f_col3, f_col4, f_col5, f_col6 = st.columns(6)
        f_col1.metric("Nitrogen (N)", f"{sample['nitrogen']} kg/ha")
        f_col2.metric("Phosphorus (P)", f"{sample['phosphorus']} kg/ha")
        f_col3.metric("Potassium (K)", f"{sample['potassium']} kg/ha")
        f_col4.metric("Temperature", f"{sample['temperature_c']} °C")
        f_col5.metric("Moisture", f"{sample['moisture_percent']} %")
        f_col6.metric("Soil Type", sample["soil_type"])

        st.markdown("---")
        st.subheader("2. Machine Learning Inference")

        # Run inference using stored features
        features_dict = {
            "nitrogen": sample["nitrogen"],
            "phosphorus": sample["phosphorus"],
            "potassium": sample["potassium"],
            "temperature": sample["temperature_c"],
            "moisture": sample["moisture_percent"],
            "soil_type": sample["soil_type"]
        }

        top2 = predict_top2(features_dict)
        top1_crop, conf1 = top2[0]
        top2_crop, conf2 = top2[1]

        # Display Model Confidence Chart (labelled "model confidence (uncalibrated)")
        chart_df = pd.DataFrame([
            {"Crop": top1_crop, "Confidence": conf1, "Rank": "Primary (Top-1)"},
            {"Crop": top2_crop, "Confidence": conf2, "Rank": "Alternative (Top-2)"}
        ])

        fig_conf = px.bar(
            chart_df,
            x="Crop",
            y="Confidence",
            color="Rank",
            title="Recommended Crop Suitability – model confidence (uncalibrated)",
            labels={"Confidence": "model confidence (uncalibrated)", "Crop": "Crop Category"},
            color_discrete_map={"Primary (Top-1)": "#16A34A", "Alternative (Top-2)": "#2563EB"},
            text=chart_df["Confidence"].apply(lambda v: f"{v*100:.1f}%")
        )
        fig_conf.update_yaxes(range=[0, 1.0])
        fig_conf.update_layout(template="plotly_white")
        st.plotly_chart(fig_conf, use_container_width=True)

        st.caption(f"ℹ️ **Regulatory Notice:** {MODEL_NOTE}")

        # Check existing prediction and report
        existing_pred = get_prediction_for_sample(selected_id)
        existing_report = get_report_for_sample(selected_id)

        # Save Prediction and PDF Generation
        pdf_bytes = generate_pdf_report(
            sample=dict(sample),
            prediction={"top1_crop": top1_crop, "top2_crop": top2_crop, "model_version": "1.0.0-rf"},
            confidences=top2
        )

        st.markdown("---")
        st.subheader("3. Advisory Report Actions")

        col_dl, col_deliver = st.columns(2)

        with col_dl:
            st.download_button(
                label="📄 Preview / Download Report (PDF)",
                data=pdf_bytes,
                file_name=f"GOBARdhan_Advisory_{sample['sample_code']}.pdf",
                mime="application/pdf",
                key=f"auth_preview_pdf_{selected_id}"
            )

        with col_deliver:
            is_delivered = existing_report and existing_report["delivery_status"] == "DELIVERED_IN_APP"
            if is_delivered:
                st.success(f"✅ Report was delivered in-app on {existing_report['delivered_at']}.")
            else:
                if st.button("🚀 Send Advisory Report to Farmer (In-App)", type="primary"):
                    try:
                        # 1. Save prediction if not already saved
                        if not existing_pred:
                            pred_id = create_prediction(
                                sample_id=selected_id,
                                top1_crop=top1_crop,
                                top2_crop=top2_crop,
                                model_version="1.0.0-rf"
                            )
                        else:
                            pred_id = existing_pred["id"]

                        # 2. Save report PDF
                        if not existing_report:
                            report_id = save_report(
                                sample_id=selected_id,
                                prediction_id=pred_id,
                                farmer_id=sample["farmer_id"],
                                pdf_blob=pdf_bytes
                            )
                        else:
                            report_id = existing_report["id"]

                        # 3. Deliver in-app
                        deliver_report(report_id)

                        # 4. Create farmer notification
                        create_notification(
                            farmer_id=sample["farmer_id"],
                            report_id=report_id,
                            message=f"Official Advisory Report for sample {sample['sample_code']} is ready! Recommended crops: {top1_crop} & {top2_crop}."
                        )

                        st.success(f"Advisory report for {sample['sample_code']} delivered in-app to {sample['farmer_name']}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to deliver advisory report: {e}")

    # ================= 3. AGGREGATE MANURE ANALYSIS =================
    elif menu_option == "📈 Aggregate Manure Analysis":
        st.header("📈 Authority Manure Analytics & Intelligence")
        st.caption("Deep-dive into telemetry distributions, statistical nutrient spreads across soil types, and operational telemetry history.")

        all_samples = get_all_samples_with_details()
        devices = get_all_devices()

        if not devices and not all_samples:
            st.info("No registered devices or manure submissions in the system yet.")
            return

        df_samples = pd.DataFrame([dict(s) for s in all_samples]) if all_samples else pd.DataFrame()

        # Executive KPI Header
        if not df_samples.empty:
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Total Submissions", len(df_samples))
            approved_count = len(df_samples[df_samples["status"] == "APPROVED"])
            k2.metric("Approved Samples", approved_count)
            pending_count = len(df_samples[df_samples["status"] == "PENDING"])
            k3.metric("Pending Audits", pending_count)
            avg_n = df_samples["nitrogen"].mean()
            k4.metric("Avg Nitrogen (N)", f"{avg_n:.1f} kg/ha")
            avg_m = df_samples["moisture_percent"].mean()
            k5.metric("Avg Moisture", f"{avg_m:.1f} %")
            st.markdown("---")

        auth_tab1, auth_tab2, auth_tab3, auth_tab4 = st.tabs([
            "📡 IoT Telemetry & Thermal Dynamics",
            "🧪 Nutrient Statistical Spread (Boxplots)",
            "🗺️ Crop Demand & Governance Heatmap",
            "🌱 Soil Benchmarks & Nutrient Matrices"
        ])

        # ----------------- TAB 1: TELEMETRY -----------------
        with auth_tab1:
            st.subheader("Physical IoT Telemetry Dynamics")
            if devices:
                dev_map = {d["id"]: f"{d['device_name']} (ID: {d['id']})" for d in devices}
                selected_dev_id = st.selectbox("Select Registered Device to Inspect", list(dev_map.keys()), format_func=lambda x: dev_map[x], key="auth_dev_pick")
                readings = get_readings_for_device(selected_dev_id, limit=300)

                if readings:
                    df_readings = pd.DataFrame([dict(r) for r in readings]).sort_values("received_at")
                    col_t1, col_t2 = st.columns([3, 2])
                    with col_t1:
                        fig_readings = go.Figure()
                        fig_readings.add_trace(go.Scatter(
                            x=df_readings["received_at"],
                            y=df_readings["temperature_c"],
                            mode="lines+markers",
                            name="Temperature (°C)",
                            line=dict(color="#EF4444", width=2.5),
                            fill="tozeroy",
                            fillcolor="rgba(239, 68, 68, 0.08)"
                        ))
                        fig_readings.add_trace(go.Scatter(
                            x=df_readings["received_at"],
                            y=df_readings["moisture_percent"],
                            mode="lines+markers",
                            name="Moisture (%)",
                            line=dict(color="#0284C7", width=2.5),
                            fill="tozeroy",
                            fillcolor="rgba(2, 132, 199, 0.08)"
                        ))
                        fig_readings.update_layout(
                            template="plotly_white",
                            title=f"Telemetry Stream: {dev_map[selected_dev_id]}",
                            xaxis_title="Timestamp",
                            yaxis_title="Sensor Units",
                            hovermode="x unified",
                            margin=dict(t=40, b=20, l=20, r=20)
                        )
                        st.plotly_chart(fig_readings, use_container_width=True)

                    with col_t2:
                        # Distribution histogram of Temperature & Moisture
                        fig_hist = px.histogram(
                            df_readings,
                            x="moisture_percent",
                            nbins=20,
                            marginal="box",
                            title="Moisture Distribution Range",
                            labels={"moisture_percent": "Moisture (%)"},
                            color_discrete_sequence=["#06B6D4"]
                        )
                        fig_hist.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                        st.plotly_chart(fig_hist, use_container_width=True)
                else:
                    st.info("No historical readings recorded for this device yet.")
            else:
                st.info("No registered devices in the system.")

        # ----------------- TAB 2: BOXPLOTS & SPREAD -----------------
        with auth_tab2:
            st.subheader("Statistical Nutrient Spread Across Soil Classifications")
            if not df_samples.empty:
                col_box1, col_box2 = st.columns([3, 2])
                with col_box1:
                    nutrient_choice = st.radio("Select Nutrient to Analyze Spread", ["nitrogen", "phosphorus", "potassium"], horizontal=True)
                    labels_map = {"nitrogen": "Nitrogen (N) kg/ha", "phosphorus": "Phosphorus (P) kg/ha", "potassium": "Potassium (K) kg/ha"}
                    colors_map = {"nitrogen": "#3B82F6", "phosphorus": "#10B981", "potassium": "#F59E0B"}
                    
                    fig_box = px.box(
                        df_samples,
                        x="soil_type",
                        y=nutrient_choice,
                        color="soil_type",
                        points="all",
                        title=f"{labels_map[nutrient_choice]} Spread by Soil Type",
                        color_discrete_sequence=px.colors.qualitative.Prism
                    )
                    fig_box.update_layout(template="plotly_white", showlegend=False, margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_box, use_container_width=True)

                with col_box2:
                    # Global NPK Bubble Chart
                    fig_bubble = px.scatter(
                        df_samples,
                        x="nitrogen",
                        y="potassium",
                        size="phosphorus",
                        color="soil_type",
                        hover_data=["sample_code", "farmer_name", "preferred_crop", "status"],
                        title="Nitrogen vs Potassium (Bubble Size = Phosphorus)",
                        color_discrete_sequence=px.colors.qualitative.Vivid
                    )
                    fig_bubble.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_bubble, use_container_width=True)
            else:
                st.info("No manure submissions available for nutrient spread analysis.")

        # ----------------- TAB 3: HEATMAP & GOVERNANCE -----------------
        with auth_tab3:
            st.subheader("Governance & Demand Intelligence")
            if not df_samples.empty:
                col_hm, col_gov = st.columns([3, 2])
                with col_hm:
                    # 2D Heatmap: Preferred Crop vs Soil Type
                    ctab = pd.crosstab(df_samples["preferred_crop"], df_samples["soil_type"])
                    fig_hm = px.imshow(
                        ctab,
                        text_auto=True,
                        aspect="auto",
                        color_continuous_scale="Teal",
                        title="Crop Demand Heatmap by Soil Classification",
                        labels=dict(x="Soil Type", y="Preferred Crop", color="Submissions")
                    )
                    fig_hm.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_hm, use_container_width=True)

                with col_gov:
                    # Status Governance Donut
                    status_counts = df_samples["status"].value_counts().reset_index()
                    status_counts.columns = ["Status", "Count"]
                    fig_status = px.pie(
                        status_counts,
                        names="Status",
                        values="Count",
                        hole=0.5,
                        title="Submission Audit Status Distribution",
                        color="Status",
                        color_discrete_map={
                            "APPROVED": "#10B981",
                            "PENDING": "#F59E0B",
                            "REJECTED": "#EF4444"
                        }
                    )
                    fig_status.update_traces(textinfo="percent+label", pull=[0.03] * len(status_counts))
                    fig_status.update_layout(template="plotly_white", margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_status, use_container_width=True)
            else:
                st.info("No submissions data available.")

        # ----------------- TAB 4: SOIL BENCHMARKS -----------------
        with auth_tab4:
            st.subheader("Nutrient Comparison across Soil Types")
            if not df_samples.empty:
                soil_grp = df_samples.groupby("soil_type")[["nitrogen", "phosphorus", "potassium"]].mean().reset_index()
                fig_soil = px.bar(
                    soil_grp,
                    x="soil_type",
                    y=["nitrogen", "phosphorus", "potassium"],
                    barmode="group",
                    title="Average NPK by Soil Classification (kg/ha)",
                    labels={"value": "Mean Nutrient Level (kg/ha)", "soil_type": "Soil Type", "variable": "Nutrient"},
                    color_discrete_map={"nitrogen": "#2563EB", "phosphorus": "#10B981", "potassium": "#F59E0B"}
                )
                fig_soil.update_layout(template="plotly_white", legend_title_text="Nutrients", margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_soil, use_container_width=True)
            else:
                st.info("No manure submissions available for aggregate soil analysis.")
