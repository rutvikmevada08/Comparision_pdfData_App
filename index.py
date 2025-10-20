import streamlit as st
import pdfplumber
import pandas as pd
import tempfile
import re
import os

st.set_page_config(page_title="PDF Compare Tool", layout="wide")

st.title("📊 PDF Comparison Tool (Given / Received Data)")
st.markdown("Upload **two Party Statement PDFs** (like Ambuja NEFT) and compare by Date & Amount.")

# ========== DATA EXTRACTION FUNCTION ==========
def extract_data(pdf_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_file.read())
        tmp_path = tmp.name
    try:
        full_text = ""
        tables_found = []
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"

                # Try table extraction first
                page_tables = page.extract_tables()
                for table in page_tables:
                    if not table or len(table) <= 1:
                        continue
                    header = [h.strip() if h else "" for h in table[0]]
                    if any("Date" in h for h in header):
                        date_col = given_col = received_col = None
                        for i, col in enumerate(header):
                            if "Date" in col:
                                date_col = i
                            if "Given" in col:
                                given_col = i
                            if "Received" in col:
                                received_col = i

                        rows = []
                        for row in table[1:]:
                            if len(row) > 1:
                                date_val = (
                                    row[date_col].strip() if date_col is not None and row[date_col] else None
                                )
                                given_val = (
                                    row[given_col].replace("₹", "").replace(",", "").strip()
                                    if given_col is not None and len(row) > given_col and row[given_col]
                                    else None
                                )
                                rec_val = (
                                    row[received_col].replace("₹", "").replace(",", "").strip()
                                    if received_col is not None and len(row) > received_col and row[received_col]
                                    else None
                                )
                                rows.append((date_val, given_val, rec_val))

                        if rows:
                            df = pd.DataFrame(rows, columns=["Date", "Given", "Received"])
                            df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
                            df["Given"] = pd.to_numeric(df["Given"], errors="coerce")
                            df["Received"] = pd.to_numeric(df["Received"], errors="coerce")
                            tables_found.append(df)
                            break
                if tables_found:
                    break

        # ---------- Regex fallback ----------
        if not tables_found:
            matches = re.findall(r"(\d{2}/\d{2}/\d{4}).*?(Given|Received).*?₹\s*([\d,]+)", full_text)
            if matches:
                rows = []
                for date, label, amount in matches:
                    if "Given" in label:
                        rows.append((date, amount.replace(",", ""), None))
                    elif "Received" in label:
                        rows.append((date, None, amount.replace(",", "")))
                df = pd.DataFrame(rows, columns=["Date", "Given", "Received"])
                df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
                df["Given"] = pd.to_numeric(df["Given"], errors="coerce")
                df["Received"] = pd.to_numeric(df["Received"], errors="coerce")
                return df
            else:
                st.warning("⚠️ No recognizable Given/Received data found in this PDF.")
                return None

        return tables_found[0]

    except Exception as e:
        st.error(f"Error extracting data: {str(e)}")
        return None
    finally:
        os.unlink(tmp_path)

# ========== FILE UPLOAD SECTION ==========
col1, col2 = st.columns(2)
with col1:
    pdf1 = st.file_uploader("📂 Upload PDF 1", type=["pdf"])
with col2:
    pdf2 = st.file_uploader("📂 Upload PDF 2", type=["pdf"])

compare_type = st.radio("🔍 Compare by Column", ["Given", "Received"], horizontal=True)

# ========== PROCESS & COMPARE ==========
if pdf1 and pdf2:
    df1 = extract_data(pdf1)
    df2 = extract_data(pdf2)

    if df1 is not None and df2 is not None:
        st.success("✅ Both PDFs parsed successfully!")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📄 PDF 1 Data")
            st.dataframe(df1)
        with col2:
            st.subheader("📄 PDF 2 Data")
            st.dataframe(df2)

        # Select relevant column
        key_col = compare_type

        df1_compare = df1[["Date", key_col]].dropna()
        df2_compare = df2[["Date", key_col]].dropna()

        merged = pd.merge(df1_compare, df2_compare, on="Date", how="outer", suffixes=("_PDF1", "_PDF2"))

        # Detect mismatches
        merged["Match"] = merged.apply(
            lambda row: "✅ Match"
            if pd.notna(row[f"{key_col}_PDF1"])
            and pd.notna(row[f"{key_col}_PDF2"])
            and abs(row[f"{key_col}_PDF1"] - row[f"{key_col}_PDF2"]) < 1
            else "❌ Mismatch",
            axis=1,
        )

        st.subheader("📊 Comparison Result")
        def highlight_mismatch(row):
            color = "background-color: #ffcccc" if row["Match"] == "❌ Mismatch" else "background-color: #ccffcc"
            return [color] * len(row)

        st.subheader("📊 Comparison Result")
        st.dataframe(merged.style.apply(highlight_mismatch, axis=1))


        mismatches = merged[merged["Match"] == "❌ Mismatch"]
        if not mismatches.empty:
            st.error(f"⚠️ Found {len(mismatches)} mismatched rows.")
        else:
            st.success("🎯 All entries match perfectly!")

else:
    st.info("⬆️ Please upload two PDF files to start comparison.")
