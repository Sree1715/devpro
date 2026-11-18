import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def generate_pdf_report(sample: dict, prediction: dict, confidences: list = None) -> bytes:
    """
    Generates a structured PDF Advisory Report for an approved manure sample using ReportLab.
    Returns bytes of the compiled PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1E3A8A"),
        alignment=1  # Centered
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        alignment=1
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#0F172A")
    )
    bold_body = ParagraphStyle(
        "BoldBodyDark",
        parent=body_style,
        fontName="Helvetica-Bold"
    )
    note_style = ParagraphStyle(
        "LegalNote",
        parent=styles["Italic"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748B")
    )

    elements = []

    # Header
    elements.append(Paragraph("Smart Manure Advisory Report", title_style))
    elements.append(Paragraph("GOBARdhan System (SIH1767)", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=12))

    # Sample Identification Table
    elements.append(Paragraph("1. Sample Identification & Origin", section_heading))
    meta_data = [
        [
            Paragraph("<b>Sample Code:</b>", body_style), Paragraph(str(sample.get("sample_code", "N/A")), bold_body),
            Paragraph("<b>Submission Date:</b>", body_style), Paragraph(str(sample.get("submitted_at", "N/A")), body_style)
        ],
        [
            Paragraph("<b>Farmer Name:</b>", body_style), Paragraph(str(sample.get("farmer_name", "N/A")), body_style),
            Paragraph("<b>Farmer Email:</b>", body_style), Paragraph(str(sample.get("farmer_email", "N/A")), body_style)
        ],
        [
            Paragraph("<b>Registered Device:</b>", body_style), Paragraph(str(sample.get("device_name", "N/A")), body_style),
            Paragraph("<b>Review Status:</b>", body_style), Paragraph(f"<font color='#16A34A'><b>{sample.get('status', 'APPROVED')}</b></font>", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 110, 160])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 10))

    # Laboratory & Sensor Analysis Table
    elements.append(Paragraph("2. Physical Telemetry & Chemical Nutrient Profile", section_heading))
    chem_data = [
        [
            Paragraph("<b>Parameter</b>", bold_body),
            Paragraph("<b>Measured Value</b>", bold_body),
            Paragraph("<b>Parameter</b>", bold_body),
            Paragraph("<b>Measured Value</b>", bold_body)
        ],
        [
            Paragraph("Temperature (Sensor)", body_style), Paragraph(f"{sample.get('temperature_c', 0.0)} °C", body_style),
            Paragraph("Available Nitrogen (N)", body_style), Paragraph(f"{sample.get('nitrogen', 0.0)} kg/ha", body_style)
        ],
        [
            Paragraph("Moisture (Sensor)", body_style), Paragraph(f"{sample.get('moisture_percent', 0.0)} %", body_style),
            Paragraph("Phosphorus (P)", body_style), Paragraph(f"{sample.get('phosphorus', 0.0)} kg/ha", body_style)
        ],
        [
            Paragraph("Soil Classification", body_style), Paragraph(str(sample.get("soil_type", "N/A")), body_style),
            Paragraph("Potassium (K)", body_style), Paragraph(f"{sample.get('potassium', 0.0)} kg/ha", body_style)
        ],
        [
            Paragraph("Farmer Preferred Crop", body_style), Paragraph(str(sample.get("preferred_crop", "N/A")), body_style),
            Paragraph("Reviewer Remarks", body_style), Paragraph(str(sample.get("review_note", "Standard agronomic verification passed.")), body_style)
        ]
    ]
    chem_table = Table(chem_data, colWidths=[135, 135, 135, 135])
    chem_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(chem_table)
    elements.append(Spacer(1, 10))

    # Crop Advisory Section
    elements.append(Paragraph("3. Crop Suitability Advisory & Model Prediction", section_heading))
    conf_str1 = f" (Confidence: {confidences[0][1]*100:.1f}%)" if confidences and len(confidences) > 0 else ""
    conf_str2 = f" (Confidence: {confidences[1][1]*100:.1f}%)" if confidences and len(confidences) > 1 else ""

    pred_data = [
        [
            Paragraph("<b>Recommended Priority</b>", bold_body),
            Paragraph("<b>Suitable Crop</b>", bold_body),
            Paragraph("<b>Model Confidence (uncalibrated)</b>", bold_body)
        ],
        [
            Paragraph("<b>Top-1 Choice (Primary)</b>", body_style),
            Paragraph(f"<font size='11' color='#16A34A'><b>{prediction.get('top1_crop', 'N/A')}</b></font>", body_style),
            Paragraph(conf_str1 or "Calculated via Random Forest", body_style)
        ],
        [
            Paragraph("<b>Top-2 Choice (Alternative)</b>", body_style),
            Paragraph(f"<font size='11' color='#2563EB'><b>{prediction.get('top2_crop', 'N/A')}</b></font>", body_style),
            Paragraph(conf_str2 or "Calculated via Random Forest", body_style)
        ]
    ]
    pred_table = Table(pred_data, colWidths=[150, 190, 200])
    pred_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#93C5FD")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFDBFE")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(pred_table)
    elements.append(Spacer(1, 12))

    # Advisory Notice
    elements.append(Paragraph("<b>Model Version:</b> " + str(prediction.get("model_version", "1.0.0-rf")), body_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        "<b>Notice:</b> This suitability advisory is generated using machine learning trained on rule-derived "
        "synthetic data under the GOBARdhan initiative. Confidence figures reflect agreement with heuristic agro-climatic "
        "decision matrices and must be validated against regional agro-meteorological advisories.",
        note_style
    ))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Report Delivery: In-App Direct Advisory Delivery (GOBARdhan System).", note_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
