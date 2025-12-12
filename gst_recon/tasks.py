from django.core.files import File
from .models import ReconciliationJob
from .recon_engine.parser import parse_file
from .recon_engine.matcher import reconcile_records
from .recon_engine.reporter import build_report_excel
import os

def run_reconciliation_async(job_id):
    try:
        job = ReconciliationJob.objects.get(id=job_id)
        job.status = "PROCESSING"
        job.save()

        # validate files exist
        if not job.gstr1 or not job.gstr1.file:
            raise ValueError("GSTR1 file not found")
        if not job.gstr3b or not job.gstr3b.file:
            raise ValueError("GSTR3B file not found")

        gstr1_path = job.gstr1.file.path
        gstr3b_path = job.gstr3b.file.path

        if not os.path.exists(gstr1_path):
            raise FileNotFoundError(f"GSTR1 file does not exist: {gstr1_path}")
        if not os.path.exists(gstr3b_path):
            raise FileNotFoundError(f"GSTR3B file does not exist: {gstr3b_path}")

        # parse to canonical rows & summaries
        g1_rows, g1_summary = parse_file(gstr1_path, source="GSTR1")
        g3_rows, g3_summary = parse_file(gstr3b_path, source="GSTR3B")
        
        print(f"DEBUG: GSTR1 rows: {len(g1_rows)}, summary: {g1_summary}")
        print(f"DEBUG: GSTR3B rows: {len(g3_rows)}, summary: {g3_summary}")
        if g1_rows:
            print(f"DEBUG: Sample GSTR1 row: {g1_rows[0]}")
        if g3_rows:
            print(f"DEBUG: Sample GSTR3B row: {g3_rows[0]}")

        # reconcile
        recon_result = reconcile_records(g1_rows, g3_rows, g1_summary, g3_summary)

        # build excel
        out_path = build_report_excel(recon_result, job_id=job.id)

        if not os.path.exists(out_path):
            raise FileNotFoundError(f"Report file was not generated: {out_path}")

        # attach report
        with open(out_path, 'rb') as f:
            job.report_file.save(f"recon_report_{job.id}.xlsx", File(f))
        job.result = recon_result
        job.status = "COMPLETED"
        job.save()
        return True

    except ReconciliationJob.DoesNotExist:
        return False
    except Exception as e:
        if 'job' in locals():
            job.status = "FAILED"
            job.error_message = str(e)
            job.save()
        return False
