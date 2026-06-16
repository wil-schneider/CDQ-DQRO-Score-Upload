"""
CDGC Data Quality Rule Occurrence (DQRO) Demo

End-to-end demo that:
  1. Authenticates to Informatica Cloud
  2. Searches for the 'FirstName' Column asset in the catalog
  3. Creates a DQRO asset with measuring method = TechnicalScript
     (linked to the FirstName column as Primary Data Element)
  4. Monitors the import job until completion
  5. Looks up the newly created DQRO's internal ID
  6. Uploads DQ scores from dq_scores_sample.csv
  7. Monitors the score import job
  8. Retrieves and prints the uploaded scores
"""

import os
import sys
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from CDGCAPIClientV2 import CDGCAPIClientV2

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('DQRO-Demo')

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL     = 'https://dm-us.informaticacloud.com'
BASE_API_URL = 'https://idmc-api.dm-us.informaticacloud.com'
USERNAME     = 'wschneider@ieast4.informatica.com'
PASSWORD     = 'WakeupWakeup1!'

DQRO_NAME        = 'Demo - FirstName Not Null Check'
DQRO_DESCRIPTION = 'Checks that the FirstName column contains no null or empty values.'
MEASURING_METHOD = 'TechnicalScript'   # API enum: TechnicalScript | InformaticaCloudDataQuality
THRESHOLD        = 70
TARGET           = 95
COLUMN_QUERY     = 'firstname'

SCORES_CSV = os.path.join(os.path.dirname(__file__), 'dq_scores_sample.csv')

JOB_POLL_INTERVAL = 15
JOB_POLL_TIMEOUT  = 900   # score import jobs can take ~8 minutes


def wait_for_job(client, job_id, label='Job'):
    """Poll monitor_import_job until the job reaches a terminal state."""
    deadline = time.time() + JOB_POLL_TIMEOUT
    while time.time() < deadline:
        resp = client.monitor_import_job(job_id)
        status = resp.get('status', '').upper()
        log.info(f"  {label} {job_id} status: {status}")
        if status in ('COMPLETED', 'SUCCESS', 'FAILED', 'ERROR'):
            return resp
        time.sleep(JOB_POLL_INTERVAL)
    raise TimeoutError(f"{label} {job_id} did not finish within {JOB_POLL_TIMEOUT}s")


def main():
    client = CDGCAPIClientV2(BASE_URL, BASE_API_URL, USERNAME, PASSWORD)

    # ── Step 1: Authenticate ─────────────────────────────────────────────────
    log.info("=== Step 1: Authenticate ===")
    client.user_login()
    client.get_token()
    log.info(f"  Org ID     : {client.org_id}")
    log.info(f"  Session ID : {client.session_id[:8]}...")

    # ── Step 2: Find the 'FirstName' Column asset ────────────────────────────
    log.info(f"\n=== Step 2: Search for Column asset '{COLUMN_QUERY}' ===")
    column_asset = client.find_column_asset(COLUMN_QUERY)

    if column_asset:
        column_internal_id  = column_asset.get('core.identity')
        column_external_id  = column_asset.get('core.externalId')
        column_name         = column_asset.get('summary', {}).get('core.name', COLUMN_QUERY)
        log.info(f"  Found column  : '{column_name}'")
        log.info(f"  Internal ID   : {column_internal_id}")
        log.info(f"  External ID   : {column_external_id}")
    else:
        log.warning("  No 'FirstName' column found. DQRO will be created without a Primary Data Element.")
        column_external_id = None
        column_name = None

    # ── Step 3: Create DQRO via bulk import ──────────────────────────────────
    log.info(f"\n=== Step 3: Create DQRO '{DQRO_NAME}' ===")
    create_result = client.create_dq_rule_occurrence(
        name=DQRO_NAME,
        description=DQRO_DESCRIPTION,
        measuring_method=MEASURING_METHOD,
        threshold=THRESHOLD,
        target=TARGET,
        primary_data_element_external_id=column_external_id
    )
    create_job_id  = create_result.get('jobId')
    dqro_ref_id    = create_result.get('reference_id')
    log.info(f"  Import job started")
    log.info(f"  Job ID       : {create_job_id}")
    log.info(f"  Reference ID : {dqro_ref_id}")

    # ── Step 4: Monitor DQRO creation job ────────────────────────────────────
    log.info(f"\n=== Step 4: Monitor DQRO creation job ===")
    create_status = wait_for_job(client, create_job_id, label='Create job')
    log.info(f"  Final status : {create_status.get('status')}")
    if create_status.get('errorMessage'):
        log.error(f"  Error: {create_status['errorMessage']}")

    # ── Step 5: Look up the new DQRO's internal ID ───────────────────────────
    log.info(f"\n=== Step 5: Look up DQRO by reference ID '{dqro_ref_id}' ===")
    time.sleep(5)   # brief delay for indexing
    dqro_results = client.search_assets_advanced(
        knowledge_query=dqro_ref_id,
        filter_spec=[{
            'type': 'simple',
            'attribute': 'core.classType',
            'values': ['com.infa.ccgf.models.governance.RuleInstance']
        }],
        from_offset=0, size=5, segments='all'
    )
    dqro_hit = next(
        (h for h in dqro_results.get('hits', [])
         if h.get('core.externalId') == dqro_ref_id),
        None
    )
    # Fallback: search by name if reference ID not yet indexed
    if not dqro_hit:
        dqro_results2 = client.search_assets_advanced(
            knowledge_query=DQRO_NAME,
            filter_spec=[{
                'type': 'simple',
                'attribute': 'core.classType',
                'values': ['com.infa.ccgf.models.governance.RuleInstance']
            }],
            from_offset=0, size=10, segments='all'
        )
        dqro_hit = next(
            (h for h in dqro_results2.get('hits', [])
             if h.get('core.externalId') == dqro_ref_id),
            None
        )

    if dqro_hit:
        dqro_internal_id = dqro_hit.get('core.identity')
        log.info(f"  Found DQRO")
        log.info(f"  Internal ID  : {dqro_internal_id}")
        log.info(f"  External ID  : {dqro_hit.get('core.externalId')}")
        sa = dqro_hit.get('selfAttributes', {})
        log.info(f"  MeasuringMethod : {sa.get('com.infa.ccgf.models.governance.MeasuringMethod')}")
        log.info(f"  Threshold    : {sa.get('com.infa.ccgf.models.governance.Threshold')}")
        log.info(f"  Target       : {sa.get('com.infa.ccgf.models.governance.Target')}")
    else:
        log.warning("  DQRO not found in search yet — it may still be indexing.")
        dqro_internal_id = None

    # ── Step 6: Upload DQ scores ─────────────────────────────────────────────
    # Re-authenticate to ensure the token is still valid after the long import job
    log.info(f"\n=== Step 6: Upload DQ scores from {os.path.basename(SCORES_CSV)} ===")
    client.user_login()
    client.get_token()

    # Rewrite the CSV with the real reference ID before uploading
    import csv, tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.csv')
    os.close(tmp_fd)
    with open(SCORES_CSV, newline='') as src, open(tmp_path, 'w', newline='') as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            row['Reference ID'] = dqro_ref_id
            writer.writerow(row)

    try:
        score_result = client.import_dq_scores_from_csv(tmp_path)
        score_job_id  = score_result.get('jobId')
        log.info(f"  Score import job started")
        log.info(f"  Job ID  : {score_job_id}")
        log.info(f"  Job URI : {score_result.get('jobUri')}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # ── Step 7: Monitor score import job ─────────────────────────────────────
    log.info(f"\n=== Step 7: Monitor score import job ===")
    score_status = wait_for_job(client, score_job_id, label='Score job')
    log.info(f"  Final status : {score_status.get('status')}")
    if score_status.get('errorMessage'):
        log.error(f"  Error: {score_status['errorMessage']}")

    # ── Step 8: Retrieve uploaded scores ─────────────────────────────────────
    log.info(f"\n=== Step 8: Retrieve DQ scores ===")
    if dqro_internal_id:
        time.sleep(5)
        try:
            scores_resp = client.get_dq_scores(dqro_internal_id, scheme='INTERNAL', limit=10)
            runs = scores_resp.get('runs', [])
            log.info(f"  Runs returned: {len(runs)}")
            for i, run in enumerate(runs, 1):
                log.info(
                    f"  Run {i}: score={run.get('score')}  "
                    f"totalRows={run.get('totalRows')}  "
                    f"failedRows={run.get('failedRows')}  "
                    f"scannedTime={run.get('scannedTime')}"
                )
        except Exception as e:
            log.warning(f"  Could not retrieve scores (scores may take up to 1 hour to appear): {e}")
    else:
        log.info("  Skipped — DQRO internal ID not available.")

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("\n=== Demo complete ===")
    log.info(f"  DQRO Name        : {DQRO_NAME}")
    log.info(f"  Reference ID     : {dqro_ref_id}")
    log.info(f"  Internal ID      : {dqro_internal_id or 'still indexing'}")
    log.info(f"  Measuring Method : {MEASURING_METHOD}")
    if column_name:
        log.info(f"  Primary Data El  : {column_name} ({column_external_id})")


if __name__ == '__main__':
    main()
