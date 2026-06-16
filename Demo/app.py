"""
CDGC DQRO Manager — Streamlit UI

Two tabs:
  1. Create DQRO  — fill minimal fields, optional column search, submit
  2. Upload Scores — manual row entry or CSV upload
"""

import csv
import io
import os
import sys
import tempfile
import time

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from CDGCAPIClientV2 import CDGCAPIClientV2

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="External DQ Score Upload",
    page_icon="📊",
    layout="wide",
)

# ── Load default credentials (Streamlit Secrets → env file → blanks) ───────────
def _load_env_defaults():
    # When deployed on Streamlit Cloud, credentials live in st.secrets
    try:
        secrets = st.secrets.get("informatica", {})
        if secrets:
            return {
                'BASE_URL':      secrets.get('BASE_URL',      'https://dm-us.informaticacloud.com'),
                'BASE_API_URL':  secrets.get('BASE_API_URL',  'https://idmc-api.dm-us.informaticacloud.com'),
                'IICS_USERNAME': secrets.get('IICS_USERNAME', ''),
                'IICS_PASSWORD': secrets.get('IICS_PASSWORD', ''),
            }
    except Exception:
        pass

    # Local fallback: read the env file
    defaults = {
        'BASE_URL':      'https://dm-us.informaticacloud.com',
        'BASE_API_URL':  'https://idmc-api.dm-us.informaticacloud.com',
        'IICS_USERNAME': '',
        'IICS_PASSWORD': '',
    }
    env_path = os.path.join(os.path.dirname(__file__), '..', 'env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, _, val = line.partition('=')
                    defaults[key.strip()] = val.strip()
    return defaults

DEFAULTS = _load_env_defaults()

# ── Session state defaults ─────────────────────────────────────────────────────
_state_defaults = {
    'client':         None,
    'connected':      False,
    'last_ref_id':    '',
    'column_hits':    [],
    'selected_column': None,
    'score_rows': [
        {
            'Score': 95,
            'Total Rows': 10000,
            'Failed Rows': 500,
            'Scanned Time': '2026-06-16T08:00:00.000Z',
            'Exception File Path': '',
        }
    ],
}
for k, v in _state_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ────────────────────────────────────────────────────────────────────
def poll_job(client, job_id, label, placeholder, interval=15, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.monitor_import_job(job_id)
        status = resp.get('status', '').upper()
        placeholder.info(f"⏳ {label} `{job_id}` — status: **{status}**")
        if status in ('COMPLETED', 'SUCCESS', 'FAILED', 'ERROR'):
            return resp
        time.sleep(interval)
    raise TimeoutError(f"{label} did not complete within {timeout}s")


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar – Connection
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("Connection")

    base_url     = st.text_input("Base URL",     value=DEFAULTS['BASE_URL'])
    base_api_url = st.text_input("API Base URL", value=DEFAULTS['BASE_API_URL'])
    username     = st.text_input("Username",     value=DEFAULTS['IICS_USERNAME'])
    password     = st.text_input("Password",     value=DEFAULTS['IICS_PASSWORD'],
                                 type="password")

    if st.button("Connect", use_container_width=True, type="primary"):
        with st.spinner("Authenticating…"):
            try:
                c = CDGCAPIClientV2(base_url, base_api_url, username, password)
                c.user_login()
                c.get_token()
                st.session_state.client    = c
                st.session_state.connected = True
            except Exception as exc:
                st.session_state.connected = False
                st.error(f"Connection failed:\n{exc}")

    if st.session_state.connected and st.session_state.client:
        c = st.session_state.client
        st.success("Connected")
        st.caption(f"Org: `{c.org_id}`")
        st.caption(f"Session: `{c.session_id[:8]}…`")


# ══════════════════════════════════════════════════════════════════════════════
# Main area
# ══════════════════════════════════════════════════════════════════════════════
st.title("External DQ Score Upload")
st.caption("Create and score Data Quality Rule Occurrences driven by technical scripts or external DQ tooling running outside of Informatica.")

if not st.session_state.connected:
    st.info("Use the sidebar to connect to Informatica Cloud.")
    st.stop()

tab_create, tab_scores = st.tabs(["📋 Create DQRO", "📤 Upload Scores"])


# ── Tab 1: Create DQRO ────────────────────────────────────────────────────────
with tab_create:
    st.header("Create Data Quality Rule Occurrence")

    left, right = st.columns(2)

    with left:
        dqro_name = st.text_input(
            "Rule Name *",
            placeholder="e.g. FirstName Not Null Check",
        )
        dqro_desc = st.text_area(
            "Description",
            placeholder="Describe what this rule checks…",
            height=90,
        )
        measuring_method = "TechnicalScript"
        st.text_input(
            "Measuring Method",
            value="Technical Script (External)",
            disabled=True,
            help="This tool is for DQ scores produced outside of Informatica — e.g. custom scripts, third-party profiling tools, or pipeline-native checks.",
        )

    with right:
        threshold   = st.slider("Threshold (minimum acceptable score)", 0, 100, 70)
        target      = st.slider("Target score", 0, 100, 95)
        criticality = st.selectbox(
            "Criticality",
            ["Low", "Medium", "High", "Critical"],
            index=1,
        )

    # ── Column search ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Primary Data Element *")

    col_search, col_btn = st.columns([5, 1])
    with col_search:
        col_query = st.text_input(
            "Search for a Column asset",
            placeholder="e.g. firstname",
            label_visibility="collapsed",
        )
    with col_btn:
        search_clicked = st.button("Search", key="search_col")

    if search_clicked:
        if col_query:
            with st.spinner("Searching catalog…"):
                try:
                    results = st.session_state.client.search_assets_advanced(
                        knowledge_query=col_query,
                        filter_spec=[{
                            "type": "simple",
                            "attribute": "core.classType",
                            "values": ["com.infa.odin.models.relational.Column"],
                        }],
                        from_offset=0, size=10, segments="all",
                    )
                    st.session_state.column_hits    = results.get("hits", [])
                    st.session_state.selected_column = None
                except Exception as exc:
                    st.error(f"Search failed: {exc}")
        else:
            st.warning("Enter a column name to search.")

    if st.session_state.column_hits:
        options = {
            f"{h.get('summary', {}).get('core.name', '?')}  —  {h.get('core.externalId', '')}": h
            for h in st.session_state.column_hits
        }
        chosen = st.selectbox("Select column", list(options.keys()), key="col_select")
        st.session_state.selected_column = options[chosen]
        st.caption(f"External ID: `{st.session_state.selected_column.get('core.externalId')}`")
    elif search_clicked and col_query:
        st.warning("No Column assets found for that query.")

    # ── Submit ─────────────────────────────────────────────────────────────────
    st.divider()
    create_status = st.empty()

    ready = bool(dqro_name and st.session_state.selected_column)
    if not dqro_name:
        st.caption("⚠ Rule Name is required.")
    elif not st.session_state.selected_column:
        st.caption("⚠ Search for and select a Primary Data Element column above.")

    if st.button(
        "Create DQRO",
        type="primary",
        disabled=not ready,
    ):
        col_ext_id = st.session_state.selected_column.get("core.externalId")

        create_status.info("Submitting DQRO import job…")
        try:
            result = st.session_state.client.create_dq_rule_occurrence(
                name=dqro_name,
                description=dqro_desc,
                measuring_method=measuring_method,
                threshold=threshold,
                target=target,
                criticality=criticality,
                primary_data_element_external_id=col_ext_id,
            )
            job_id = result.get("jobId")
            ref_id = result.get("reference_id")

            final = poll_job(
                st.session_state.client, job_id, "Create job", create_status
            )
            job_status = final.get("status", "").upper()

            if job_status in ("COMPLETED", "SUCCESS"):
                st.session_state.last_ref_id = ref_id
                create_status.success(
                    f"**DQRO created!**\n\n"
                    f"Reference ID: `{ref_id}`\n\n"
                    f"Switch to the **Upload Scores** tab to add score runs."
                )
            else:
                err = final.get("errorMessage") or "No error message returned."
                create_status.error(
                    f"Job finished with status **{job_status}**:\n\n{err}"
                )

        except Exception as exc:
            create_status.error(f"Error: {exc}")


# ── Tab 2: Upload Scores ──────────────────────────────────────────────────────
with tab_scores:
    st.header("Upload DQ Scores")
    st.caption("Publish score runs from an external technical script or DQ tool into the CDGC catalog.")

    ref_id_input = st.text_input(
        "DQRO Reference ID *",
        value=st.session_state.last_ref_id,
        placeholder="e.g. DQO-DEMO-A1B2C3D4",
    )

    upload_mode = st.radio(
        "Score source",
        ["Enter manually", "Upload CSV"],
        horizontal=True,
    )

    # ── Manual entry ───────────────────────────────────────────────────────────
    if upload_mode == "Enter manually":
        st.subheader("Score Runs")

        hcols = st.columns([2, 2, 2, 3, 4, 1])
        for col, label in zip(
            hcols,
            ["Score (0–100)", "Total Rows", "Failed Rows",
             "Scanned Time (ISO 8601)", "Exception File Path", ""],
        ):
            col.markdown(f"**{label}**")

        delete_indices = []
        for i, row in enumerate(st.session_state.score_rows):
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 3, 4, 1])
            row["Score"]  = c1.number_input(
                "", min_value=0, max_value=100, value=int(row["Score"]),
                key=f"score_{i}", label_visibility="collapsed",
            )
            row["Total Rows"] = c2.number_input(
                "", min_value=0, value=int(row["Total Rows"]),
                key=f"total_{i}", label_visibility="collapsed",
            )
            row["Failed Rows"] = c3.number_input(
                "", min_value=0, value=int(row["Failed Rows"]),
                key=f"failed_{i}", label_visibility="collapsed",
            )
            row["Scanned Time"] = c4.text_input(
                "", value=row["Scanned Time"],
                key=f"time_{i}", label_visibility="collapsed",
            )
            row["Exception File Path"] = c5.text_input(
                "", value=row["Exception File Path"],
                key=f"epath_{i}", label_visibility="collapsed",
            )
            if c6.button("✕", key=f"del_{i}", help="Remove this row"):
                delete_indices.append(i)

        for i in reversed(delete_indices):
            st.session_state.score_rows.pop(i)
            st.rerun()

        if st.button("＋ Add row"):
            st.session_state.score_rows.append({
                "Score": 95,
                "Total Rows": 10000,
                "Failed Rows": 500,
                "Scanned Time": "2026-06-16T08:00:00.000Z",
                "Exception File Path": "",
            })
            st.rerun()

        csv_file = None

    # ── CSV upload ─────────────────────────────────────────────────────────────
    else:
        csv_file = st.file_uploader(
            "Upload CSV",
            type=["csv"],
            help="Required columns: Reference ID, Score, Total Rows, Failed Rows, Scanned Time, Exception File Path",
        )
        with st.expander("CSV format reference"):
            st.code(
                "Reference ID,Score,Total Rows,Failed Rows,Scanned Time,Exception File Path\n"
                "MY-DQRO-001,92,10000,800,2026-06-01T08:00:00.000Z,/exceptions/run1.csv",
                language="text",
            )

    # ── Submit ─────────────────────────────────────────────────────────────────
    st.divider()
    score_status = st.empty()

    upload_disabled = not ref_id_input or (
        upload_mode == "Upload CSV" and csv_file is None
    )
    if st.button(
        "Upload Scores",
        type="primary",
        disabled=upload_disabled,
        help=(
            "DQRO Reference ID is required"
            if not ref_id_input
            else "Select a CSV file to upload" if upload_disabled else ""
        ),
    ):
        client = st.session_state.client
        score_status.info("Re-authenticating…")
        try:
            client.user_login()
            client.get_token()
        except Exception as exc:
            score_status.error(f"Re-authentication failed: {exc}")
            st.stop()

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        os.close(tmp_fd)

        try:
            fieldnames = [
                "Reference ID", "Score", "Total Rows",
                "Failed Rows", "Scanned Time", "Exception File Path",
            ]

            if upload_mode == "Upload CSV" and csv_file is not None:
                content = csv_file.read().decode("utf-8")
                reader  = csv.DictReader(io.StringIO(content))
                rows_out = []
                for row in reader:
                    row["Reference ID"] = ref_id_input
                    rows_out.append(row)
                if not rows_out:
                    score_status.error("The uploaded CSV is empty.")
                    st.stop()
                with open(tmp_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=reader.fieldnames or fieldnames)
                    writer.writeheader()
                    writer.writerows(rows_out)
            else:
                with open(tmp_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in st.session_state.score_rows:
                        writer.writerow({
                            "Reference ID":       ref_id_input,
                            "Score":              row["Score"],
                            "Total Rows":         row["Total Rows"],
                            "Failed Rows":        row["Failed Rows"],
                            "Scanned Time":       row["Scanned Time"],
                            "Exception File Path": row["Exception File Path"],
                        })

            score_status.info("Uploading scores…")
            result   = client.import_dq_scores_from_csv(tmp_path)
            job_id   = result.get("jobId")

            final      = poll_job(client, job_id, "Score job", score_status)
            job_status = final.get("status", "").upper()

            if job_status in ("COMPLETED", "SUCCESS"):
                score_status.success(
                    f"**Scores uploaded!** Job `{job_id}` completed.\n\n"
                    f"Scores may take up to 1 hour to appear in the CDGC UI."
                )
            else:
                err = final.get("errorMessage") or "No error message returned."
                score_status.error(
                    f"Job finished with status **{job_status}**:\n\n{err}"
                )

        except Exception as exc:
            score_status.error(f"Error: {exc}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
