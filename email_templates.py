"""HTML email bodies for the lead-capture widget flow. Simple inline-styled
HTML (no external CSS — email clients need inline styles) kept separate
from routes.py for readability.
"""


def lead_report_email(branding: dict, lead_first_name: str, business_name: str, website_url: str,
                       overall_score: float, overall_grade: str, snapshot_url: str) -> tuple[str, str]:
    """Email sent to the lead who ran the widget. Returns (subject, html)."""
    subject = f"Your Website Score: {overall_score}/100 ({overall_grade})"
    greeting = f"Hi {lead_first_name}," if lead_first_name else "Hi there,"
    html = f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a;">
      <p>{greeting}</p>
      <p>Thanks for requesting a free Website Visibility Audit for <strong>{website_url}</strong>.</p>
      <div style="background:#f5f7fa; border-radius:12px; padding:24px; text-align:center; margin:24px 0;">
        <div style="font-size:14px; color:#555; text-transform:uppercase; letter-spacing:1px;">Website Score</div>
        <div style="font-size:48px; font-weight:700; color:#0f62fe; margin:8px 0;">{overall_score}/100</div>
        <div style="font-size:20px; font-weight:600; color:#333;">Grade: {overall_grade}</div>
      </div>
      <p>We found several opportunities that may be limiting {business_name or 'your business'}'s visibility in search and AI-powered results.</p>
      <p style="text-align:center; margin:32px 0;">
        <a href="{snapshot_url}" style="background:#0f62fe; color:#fff; padding:14px 28px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block;">View Your Full Snapshot</a>
      </p>
      <p>Want a deeper walkthrough of what's holding your website back? Reach out and we'll be happy to help.</p>
      <p style="margin-top:32px; color:#555;">
        {branding.get('company_name','')}<br>
        {branding.get('phone','')}<br>
        <a href="mailto:{branding.get('email','')}">{branding.get('email','')}</a><br>
        <a href="{branding.get('website','')}">{branding.get('website','')}</a>
      </p>
    </div>
    """
    return subject, html


def full_audit_email(branding: dict, lead_first_name: str, business_name: str, website_url: str,
                      full_report_url: str, wants_help: bool) -> tuple[str, str]:
    """Email sent to the lead after they click "Request Your Full Audit" on
    their prospect snapshot (widget results or public share link) and answer
    the "want help fixing these?" prompt. Sent either way -- the answer only
    changes the message copy, not whether they get the report."""
    subject = "Your Full Website Audit Is Ready"
    greeting = f"Hi {lead_first_name}," if lead_first_name else "Hi there,"
    help_para = (
        "We'll be in touch shortly to talk through the fixes and how we can help."
        if wants_help else
        "If you'd like a hand with any of it down the road, just reply to this email."
    )
    html = f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a;">
      <p>{greeting}</p>
      <p>As requested, here's the complete website audit for <strong>{website_url}</strong> — every issue found, why it matters, and exactly how to fix it.</p>
      <p style="text-align:center; margin:32px 0;">
        <a href="{full_report_url}" style="background:#0f62fe; color:#fff; padding:14px 28px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block;">View Your Full Audit</a>
      </p>
      <p>{help_para}</p>
      <p style="margin-top:32px; color:#555;">
        {branding.get('company_name','')}<br>
        {branding.get('phone','')}<br>
        <a href="mailto:{branding.get('email','')}">{branding.get('email','')}</a><br>
        <a href="{branding.get('website','')}">{branding.get('website','')}</a>
      </p>
    </div>
    """
    return subject, html


def lead_notification_email(branding: dict, lead: dict, business_name: str, website_url: str,
                             overall_score: float, overall_grade: str, full_report_url: str) -> tuple[str, str]:
    """Email sent to the agency notifying them of a new widget lead."""
    subject = f"New Website Audit Lead: {business_name or website_url} ({overall_score}/100)"
    html = f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a;">
      <h2 style="margin-bottom:4px;">New Website Audit Lead</h2>
      <p style="color:#555;">Someone just ran a website audit through your embedded widget.</p>
      <table style="width:100%; border-collapse: collapse; margin: 16px 0;">
        <tr><td style="padding:6px 0; color:#888;">Name</td><td style="padding:6px 0; font-weight:600;">{lead.get('first_name','')} {lead.get('last_name','')}</td></tr>
        <tr><td style="padding:6px 0; color:#888;">Email</td><td style="padding:6px 0; font-weight:600;">{lead.get('email','')}</td></tr>
        <tr><td style="padding:6px 0; color:#888;">Phone</td><td style="padding:6px 0; font-weight:600;">{lead.get('phone') or '—'}</td></tr>
        <tr><td style="padding:6px 0; color:#888;">Website</td><td style="padding:6px 0; font-weight:600;">{website_url}</td></tr>
        <tr><td style="padding:6px 0; color:#888;">Website Score</td><td style="padding:6px 0; font-weight:600;">{overall_score}/100 ({overall_grade})</td></tr>
      </table>
      <p style="text-align:center; margin:24px 0;">
        <a href="{full_report_url}" style="background:#0f62fe; color:#fff; padding:12px 24px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block;">View Full Audit Report</a>
      </p>
      <p style="color:#888; font-size:13px;">This lead was captured via the embeddable audit widget.</p>
    </div>
    """
    return subject, html
