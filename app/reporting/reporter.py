"""
Execution Report Generator
Compiles ExecutionRun metrics, step latencies, acceptance criteria traceability,
and human approval records into a comprehensive Markdown/Text report.
"""
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List

from app.models.test_suite import TestSuite
from app.models.execution import ExecutionRun, ApprovalRecord, TestOutcome
from app.models.requirements import JiraRequirement


class ExecutionReportGenerator:
    """Generates audit-ready execution reports suitable for Jira attachments and CI/CD pipelines."""

    @staticmethod
    def generate_markdown_report(
        run: ExecutionRun,
        suite: Optional[TestSuite] = None,
        requirement: Optional[JiraRequirement] = None,
        approval: Optional[ApprovalRecord] = None,
    ) -> str:
        req_key = requirement.key if requirement else (suite.requirement_key if suite else "N/A")
        req_summary = requirement.summary if requirement else "Enterprise Automated Test Suite"
        approver = approval.reviewer if approval else "Unspecified"
        suite_hash = approval.suite_hash if approval else (suite.compute_hash() if suite else "N/A")

        total = run.total_tests
        passed = run.passed_tests
        failed = run.failed_tests
        pass_rate = f"{(passed / total * 100):.1f}%" if total > 0 else "0%"
        duration_s = f"{(run.finished_at - run.started_at).total_seconds():.2f}s" if run.finished_at else "N/A"

        md = [
            f"# 🎯 Automated Test Execution Report: Let me TEST it....!",
            f"",
            f"**Execution Run ID:** `{run.run_id}`  ",
            f"**Parent Requirement:** `{req_key}` — *{req_summary}*  ",
            f"**Target Application:** `{run.target_url}`  ",
            f"**Execution Timestamp:** `{run.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}`  ",
            f"**Cryptographic Suite Hash (SHA-256):** `{suite_hash}`  ",
            f"**Signed Approver:** `{approver}`  ",
            f"",
            f"---",
            f"",
            f"## 📊 Executive Summary",
            f"* **Total Test Scenarios:** {total}",
            f"* **Passed Scenarios:** {passed} ({pass_rate})",
            f"* **Failed Scenarios:** {failed}",
            f"* **Total Duration:** {duration_s}",
            f"",
            f"---",
            f"",
            f"## 📋 Acceptance Criteria Traceability",
        ]

        if requirement and requirement.acceptance_criteria:
            for ac in requirement.acceptance_criteria:
                # Find matching test case outcome
                matching_outcome = "NOT TESTED"
                if suite:
                    for tc in suite.test_cases:
                        if tc.source_ac_id == ac.id or ac.id in tc.title:
                            tc_res = next((r for r in run.results if r.test_case_id == tc.id), None)
                            if tc_res:
                                matching_outcome = "✅ PASSED" if tc_res.outcome == TestOutcome.PASS else "❌ FAILED"
                md.append(f"* **[{ac.id}]** {ac.text}: **{matching_outcome}**")
        else:
            md.append("*No explicit acceptance criteria metadata recorded.*")

        md.extend([
            f"",
            f"---",
            f"",
            f"## 🔍 Scenario & Step Execution Details",
        ])

        for res in run.results:
            icon = "✅" if res.outcome == TestOutcome.PASS else "❌"
            tc_title = res.test_case_id
            if suite:
                matched_tc = next((t for t in suite.test_cases if t.id == res.test_case_id), None)
                if matched_tc:
                    tc_title = f"{matched_tc.id}: {matched_tc.title}"

            md.append(f"### {icon} {tc_title} — {res.outcome.value} ({res.duration_seconds}s)")
            if res.failure_message:
                md.append(f"> **Failure Diagnosis:** {res.failure_message}")
                md.append(f"> **Classification:** `{res.classification.value}`")
                if res.screenshot_path:
                    md.append(f"> **Evidence Screenshot:** `{res.screenshot_path}`")

            md.append("")
            md.append("| Step # | Action | Target / Selector | Duration | Outcome |")
            md.append("| :--- | :--- | :--- | :--- | :--- |")

            for s in res.step_results:
                step_icon = "✅ PASS" if s.passed else "❌ FAIL"
                md.append(f"| {s.step_number} | `{s.action.value.upper()}` | `{s.error_message or 'OK'}` | {s.duration_ms} ms | {step_icon} |")
            md.append("")

        md.extend([
            f"---",
            f"_Generated automatically by [Let me TEST it....!](https://github.com/LetMeTestIt)._",
        ])

        return "\n".join(md)

    @classmethod
    def save_report_file(
        cls,
        run: ExecutionRun,
        suite: Optional[TestSuite] = None,
        requirement: Optional[JiraRequirement] = None,
        approval: Optional[ApprovalRecord] = None,
        output_dir: str = "artifacts/reports",
    ) -> Path:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"execution_report_{run.run_id}.md"

        content = cls.generate_markdown_report(run, suite, requirement, approval)
        report_path.write_text(content, encoding="utf-8")
        return report_path

    @classmethod
    def generate_html_report(
        cls,
        run: ExecutionRun,
        suite: Optional[TestSuite] = None,
        requirement: Optional[JiraRequirement] = None,
        approval: Optional[ApprovalRecord] = None,
    ) -> str:
        """Renders an executive HTML template for Playwright PDF compilation."""
        import base64

        def _img_base64(path_str):
            if not path_str:
                return None
            try:
                p = Path(path_str).resolve()
                if p.exists():
                    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode('utf-8')}"
            except Exception:
                pass
            return None

        req_key = requirement.key if requirement else (suite.requirement_key if suite else "N/A")
        req_summary = requirement.summary if requirement else "Enterprise Automated Test Suite"
        approver = approval.reviewer if approval else "Unspecified"
        suite_hash = approval.suite_hash if approval else (suite.compute_hash() if suite else "N/A")

        total = run.total_tests
        passed = run.passed_tests
        failed = run.failed_tests
        pass_rate = f"{(passed / total * 100):.1f}%" if total > 0 else "0%"
        duration_s = f"{(run.finished_at - run.started_at).total_seconds():.2f}s" if run.finished_at else "N/A"

        # Build Scenarios HTML
        scenarios_html = []
        for res in run.results:
            is_pass = res.outcome == TestOutcome.PASS
            badge_color = "#107e3e" if is_pass else "#bb0000"
            badge_bg = "#e8f5e9" if is_pass else "#ffebee"
            badge_text = "PASS" if is_pass else "FAIL"

            matched_tc = next((t for t in suite.test_cases if t.id == res.test_case_id), None) if suite else None
            title_text = f"{res.test_case_id}: {matched_tc.title if matched_tc else ''}"

            step_rows = []
            for s in res.step_results:
                s_status = '<span style="color:#107e3e;font-weight:600;">PASS</span>' if s.passed else '<span style="color:#bb0000;font-weight:600;">FAIL</span>'
                step_rows.append(f"""
                <tr>
                    <td style="padding:6px 10px;border-bottom:1px solid #eee;">{s.step_number}</td>
                    <td style="padding:6px 10px;border-bottom:1px solid #eee;"><code>{s.action.value.upper()}</code></td>
                    <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#555;">{s.error_message or 'OK'}</td>
                    <td style="padding:6px 10px;border-bottom:1px solid #eee;">{s.duration_ms} ms</td>
                    <td style="padding:6px 10px;border-bottom:1px solid #eee;">{s_status}</td>
                </tr>
                """)

            failure_html = ""
            if res.failure_message:
                b64_img = _img_base64(res.screenshot_path)
                img_tag = f'<div style="margin-top:8px;"><img src="{b64_img}" style="max-width:100%;border-radius:4px;border:1px solid #ddd;" /></div>' if b64_img else ""
                failure_html = f"""
                <div style="background:#fff3f3;border-left:4px solid #bb0000;padding:10px 14px;margin:10px 0;border-radius:4px;">
                    <div style="color:#bb0000;font-weight:600;">Failure Diagnosis:</div>
                    <div style="font-size:0.9rem;color:#333;margin-top:2px;">{res.failure_message}</div>
                    <div style="font-size:0.8rem;color:#666;margin-top:4px;">Classification: <code>{res.classification.value}</code></div>
                    {img_tag}
                </div>
                """

            scenarios_html.append(f"""
            <div style="margin-bottom:20px;border:1px solid #e0e6ed;border-radius:6px;overflow:hidden;">
                <div style="background:#f8fafc;padding:10px 14px;border-bottom:1px solid #e0e6ed;display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:600;color:#1e293b;">{title_text}</span>
                    <span style="background:{badge_bg};color:{badge_color};padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:700;">{badge_text} ({res.duration_seconds}s)</span>
                </div>
                <div style="padding:10px 14px;">
                    {failure_html}
                    <table style="width:100%;border-collapse:collapse;font-size:0.82rem;margin-top:6px;">
                        <thead>
                            <tr style="background:#f1f5f9;text-align:left;color:#475569;">
                                <th style="padding:6px 10px;">Step #</th>
                                <th style="padding:6px 10px;">Action</th>
                                <th style="padding:6px 10px;">Details / Diagnosis</th>
                                <th style="padding:6px 10px;">Latency</th>
                                <th style="padding:6px 10px;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(step_rows)}
                        </tbody>
                    </table>
                </div>
            </div>
            """)

        # AC Traceability rows
        ac_rows = []
        if requirement and requirement.acceptance_criteria:
            for ac in requirement.acceptance_criteria:
                matching_status = '<span style="color:#64748b;">Not Tested</span>'
                if suite:
                    for tc in suite.test_cases:
                        if tc.source_ac_id == ac.id or ac.id in tc.title:
                            tc_res = next((r for r in run.results if r.test_case_id == tc.id), None)
                            if tc_res:
                                matching_status = '<span style="color:#107e3e;font-weight:600;">✅ PASSED</span>' if tc_res.outcome == TestOutcome.PASS else '<span style="color:#bb0000;font-weight:600;">❌ FAILED</span>'
                ac_rows.append(f"""
                <tr style="border-bottom:1px solid #f1f5f9;">
                    <td style="padding:6px 10px;font-weight:600;color:#0369a1;width:15%;">[{ac.id}]</td>
                    <td style="padding:6px 10px;color:#334155;">{ac.text}</td>
                    <td style="padding:6px 10px;text-align:right;">{matching_status}</td>
                </tr>
                """)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Execution Report - {run.run_id}</title>
    <style>
        @page {{
            size: A4;
            margin: 12mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #1e293b;
            line-height: 1.4;
            margin: 0;
            padding: 0;
            font-size: 11pt;
        }}
        .header-bar {{
            background: linear-gradient(135deg, #0a6ed1, #0854a0);
            color: #ffffff;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 16px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 18px;
        }}
        .kpi-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 10px 14px;
            text-align: center;
        }}
        .kpi-val {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #0f172a;
        }}
        .kpi-lbl {{
            font-size: 0.75rem;
            color: #64748b;
            text-transform: uppercase;
            font-weight: 600;
            margin-top: 2px;
        }}
        .section-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: #0854a0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 4px;
            margin-top: 18px;
            margin-bottom: 10px;
        }}
        table.meta-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            margin-bottom: 14px;
        }}
        table.meta-table td {{
            padding: 4px 8px;
        }}
        table.meta-table td.lbl {{
            color: #64748b;
            font-weight: 600;
            width: 25%;
        }}
        code {{
            background: #f1f5f9;
            padding: 2px 5px;
            border-radius: 4px;
            font-size: 0.82rem;
            color: #0f172a;
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div style="font-size:1.4rem;font-weight:700;">Let me TEST it....!</div>
        <div style="font-size:0.9rem;opacity:0.9;margin-top:2px;">Agentic Quality Engineering Platform — Autonomous Execution Audit Report</div>
    </div>

    <table class="meta-table">
        <tr>
            <td class="lbl">Requirement:</td>
            <td><strong>{req_key}</strong> — {req_summary}</td>
            <td class="lbl">Run ID:</td>
            <td><code>{run.run_id}</code></td>
        </tr>
        <tr>
            <td class="lbl">Target URL:</td>
            <td><code>{run.target_url}</code></td>
            <td class="lbl">Execution Time:</td>
            <td>{run.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
        </tr>
        <tr>
            <td class="lbl">Signed Approver:</td>
            <td><code>{approver}</code></td>
            <td class="lbl">Suite Hash:</td>
            <td><code>{suite_hash[:18]}...</code></td>
        </tr>
    </table>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-val">{total}</div>
            <div class="kpi-lbl">Total Scenarios</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val" style="color:#107e3e;">{passed}</div>
            <div class="kpi-lbl">Passed ({pass_rate})</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val" style="color:{'#bb0000' if failed else '#107e3e'};">{failed}</div>
            <div class="kpi-lbl">Failed</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{duration_s}</div>
            <div class="kpi-lbl">Total Duration</div>
        </div>
    </div>

    <div class="section-title">Acceptance Criteria Verification Matrix</div>
    <table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-bottom:16px;">
        {''.join(ac_rows) if ac_rows else '<tr><td style="color:#64748b;padding:6px;">No explicit acceptance criteria specified.</td></tr>'}
    </table>

    <div class="section-title">Scenario &amp; Step Execution Breakdown</div>
    {''.join(scenarios_html)}

    <div style="margin-top:24px;border-top:1px solid #e2e8f0;padding-top:10px;font-size:0.75rem;color:#64748b;text-align:center;">
        Generated by Let me TEST it....! | Agentic Quality Engineering Platform | Verified Execution
    </div>
</body>
</html>
"""

    @classmethod
    def save_pdf_report(
        cls,
        run: ExecutionRun,
        suite: Optional[TestSuite] = None,
        requirement: Optional[JiraRequirement] = None,
        approval: Optional[ApprovalRecord] = None,
        output_dir: str = "artifacts/reports",
    ) -> Path:
        """Generates a professional PDF audit report with consistent running headers using Chromium."""
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"Execution_Report_{run.run_id}.pdf"

        html_content = cls.generate_html_report(run, suite, requirement, approval)

        req_key = requirement.key if requirement else (suite.requirement_key if suite else "QA-Audit")
        header_html = f"""
        <div style="font-size: 8pt; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #64748b; width: 100%; padding: 0 14mm; display: flex; justify-content: space-between; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; box-sizing: border-box;">
            <span><strong>Let me TEST it....!</strong> &bull; Agentic Quality Engineering Platform</span>
            <span>Requirement: {req_key} &bull; Run: {run.run_id}</span>
        </div>
        """
        footer_html = """
        <div style="font-size: 8pt; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #64748b; width: 100%; padding: 0 14mm; display: flex; justify-content: space-between; border-top: 1px solid #cbd5e1; padding-top: 4px; box-sizing: border-box;">
            <span>Autonomous Execution Audit &bull; Cryptographically Verified</span>
            <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
        </div>
        """

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_content, wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=header_html,
                footer_template=footer_html,
                margin={"top": "18mm", "bottom": "18mm", "left": "12mm", "right": "12mm"},
            )
            browser.close()

        return pdf_path

