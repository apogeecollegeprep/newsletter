from __future__ import annotations

import argparse
import html
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .sync import AirtableClient, RetryingSession, required_env


MAILERLITE_API = "https://connect.mailerlite.com/api"
DEFAULT_ISSUES_TABLE_ID = "tblsnPXpizZA9SVfO"
UNSUBSCRIBE_URL = "{$unsubscribe}"


@dataclass(frozen=True)
class Story:
    headline: str
    url: str
    source: str
    published_at: datetime
    category: str
    summary: str
    applicant_impact: str
    relevance_score: int
    source_quality: int
    selected: bool = False


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def story_from_fields(fields: dict[str, Any]) -> Story | None:
    required = ("Headline", "URL", "Published At", "Category", "Neutral Summary")
    if any(not fields.get(name) for name in required) or fields.get("Status") == "Rejected":
        return None
    return Story(
        headline=str(fields["Headline"]).strip(),
        url=str(fields["URL"]).strip(),
        source=str(fields.get("Source", "")).strip(),
        published_at=_parse_datetime(str(fields["Published At"])),
        category=str(fields["Category"]).strip(),
        summary=str(fields["Neutral Summary"]).strip(),
        applicant_impact=str(fields.get("Applicant Impact", "")).strip(),
        relevance_score=int(fields.get("Relevance Score", 0) or 0),
        source_quality=int(fields.get("Source Quality", 0) or 0),
        selected=bool(fields.get("Selected", False)),
    )


def select_top_stories(stories: list[Story], limit: int = 5) -> list[Story]:
    """Rank stories while preserving category variety in a small digest."""
    ranked = sorted(
        stories,
        key=lambda story: (
            story.selected,
            story.relevance_score,
            story.source_quality,
            story.published_at,
        ),
        reverse=True,
    )
    chosen: list[Story] = []
    used_categories: set[str] = set()
    for story in ranked:
        if story.category not in used_categories:
            chosen.append(story)
            used_categories.add(story.category)
        if len(chosen) == limit:
            return chosen
    for story in ranked:
        if story not in chosen:
            chosen.append(story)
        if len(chosen) == limit:
            break
    return chosen


def _story_html(story: Story) -> str:
    impact = ""
    if story.applicant_impact:
        impact = (
            '<p style="margin:10px 0 0;color:#184542;font-size:14px;line-height:1.55">'
            f"<strong>Why it matters:</strong> {html.escape(story.applicant_impact)}</p>"
        )
    return f"""
      <article style="padding:20px 0;border-bottom:1px solid #e7e9ee">
        <p style="margin:0 0 6px;color:#1F6C87;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">{html.escape(story.category)}</p>
        <h2 style="margin:0 0 6px;color:#050F1F;font-size:20px;line-height:1.3"><a href="{html.escape(story.url, quote=True)}" style="color:#050F1F;text-decoration:none">{html.escape(story.headline)}</a></h2>
        <p style="margin:0 0 10px;color:#6b7280;font-size:13px">{html.escape(story.source)}</p>
        <p style="margin:0;color:#191919;font-size:15px;line-height:1.65">{html.escape(story.summary)}</p>
        {impact}
        <p style="margin:12px 0 0"><a href="{html.escape(story.url, quote=True)}" style="color:#1F6C87;font-size:14px;font-weight:700">Read the original story →</a></p>
      </article>
    """


def render_email(stories: list[Story], *, monthly: bool = False) -> str:
    title = "Apogee Admissions Monthly" if monthly else "Apogee Admissions Weekly Brief"
    eyebrow = "MONTHLY NEWSLETTER DRAFT" if monthly else "THIS WEEK IN COLLEGE ADMISSIONS"
    news = "".join(_story_html(story) for story in stories)
    human_sections = ""
    if monthly:
        human_sections = """
          <section style="margin:32px 0;padding:24px;background:#f4f0e7;border-radius:10px">
            <p style="margin:0 0 6px;color:#7a5b1e;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">EDITOR SECTION</p>
            <h2 style="margin:0 0 10px;color:#1e2a3a">Student Highlight</h2>
            <p style="margin:0;color:#596579">Replace this placeholder with the student story, photograph, and approved quotation.</p>
          </section>
          <section style="margin:32px 0;padding:24px;background:#eef3f6;border-radius:10px">
            <p style="margin:0 0 6px;color:#31596c;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">EDITOR SECTION</p>
            <h2 style="margin:0 0 10px;color:#1e2a3a">Video Feature</h2>
            <p style="margin:0;color:#596579">Add a video thumbnail or animated preview linked to the hosted video.</p>
          </section>
        """
    return f"""<!doctype html>
<html><body style="margin:0;background:#F2F2F0;font-family:'Proxima Nova',Arial,sans-serif;color:#191919">
  <div style="display:none;max-height:0;overflow:hidden">Five developments that matter to undergraduate applicants and families.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F2F2F0"><tr><td align="center">
    <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:100%;max-width:640px;background:#ffffff;margin:24px auto;border-radius:12px;overflow:hidden">
      <tr><td style="padding:36px 36px 30px;background:#050F1F;border-top:5px solid #F1A70F">
        <p style="margin:0 0 10px;color:#F1A70F;font-size:12px;font-weight:700;letter-spacing:.12em">{eyebrow}</p>
        <h1 style="margin:0;color:#ffffff;font-size:30px;line-height:1.2">{title}</h1>
        <p style="margin:12px 0 0;color:#dce2ea;font-size:15px;line-height:1.5">Neutral, practical updates for students, families, and the Apogee coaching team.</p>
      </td></tr>
      <tr><td style="padding:10px 36px 32px">
        {news}
        {human_sections}
        <p style="margin:30px 0 0;color:#7b8492;font-size:12px;line-height:1.5">You are receiving this update from Apogee College Prep. <a href="{UNSUBSCRIBE_URL}" style="color:#7b8492">Unsubscribe or update preferences</a>.</p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


class DeliveryAirtableClient(AirtableClient):
    def __init__(self, http: RetryingSession) -> None:
        super().__init__(http)
        self.issues_table = os.getenv("AIRTABLE_ISSUES_TABLE_ID", DEFAULT_ISSUES_TABLE_ID)

    def recent_stories(self, *, days: int, now: datetime | None = None) -> list[Story]:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=days)
        records = self.list_records(
            self.candidates_table,
            (
                "Headline", "URL", "Source", "Published At", "Category", "Status",
                "Neutral Summary", "Applicant Impact", "Relevance Score", "Source Quality", "Selected",
            ),
        )
        stories = []
        for record in records:
            story = story_from_fields(record.get("fields", {}))
            if story and story.published_at >= cutoff:
                stories.append(story)
        return stories

    def record_issue(self, *, issue: str, week_of: str, status: str, subject: str, html_body: str, provider_id: str) -> None:
        self.http.request(
            "POST",
            self._table_url(self.issues_table),
            headers=self.headers,
            json={
                "records": [{
                    "fields": {
                        "Issue": issue,
                        "Week Of": week_of,
                        "Status": status,
                        "Subject Line": subject,
                        "Email Draft": html_body,
                        "Provider Campaign ID": provider_id,
                    }
                }],
                "typecast": False,
            },
        )


class MailerLiteClient:
    def __init__(self, http: RetryingSession) -> None:
        self.http = http
        self.api_key = required_env("MAILERLITE_API_KEY")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def group_id(self, name: str) -> str:
        response = self.http.request(
            "GET",
            f"{MAILERLITE_API}/groups",
            headers=self.headers,
            params={"filter[name]": name, "limit": 100},
        )
        exact = [group for group in response.json().get("data", []) if group.get("name") == name]
        if len(exact) != 1:
            raise RuntimeError(f"Expected one MailerLite group named {name!r}; found {len(exact)}")
        return str(exact[0]["id"])

    def create_campaign(self, *, group_id: str, sender_email: str, sender_name: str, subject: str, name: str, html_body: str) -> str:
        response = self.http.request(
            "POST",
            f"{MAILERLITE_API}/campaigns",
            headers=self.headers,
            json={
                "name": name,
                "type": "regular",
                "groups": [group_id],
                "emails": [{
                    "subject": subject,
                    "from_name": sender_name,
                    "from": sender_email,
                    "content": html_body,
                }],
            },
        )
        return str(response.json()["data"]["id"])

    def send_campaign(self, campaign_id: str) -> None:
        self.http.request(
            "POST",
            f"{MAILERLITE_API}/campaigns/{campaign_id}/schedule",
            headers=self.headers,
            json={"delivery": "instant"},
        )


def deliver(*, monthly: bool, dry_run: bool) -> dict[str, Any]:
    http = RetryingSession()
    airtable = DeliveryAirtableClient(http)
    days = int(os.getenv("MONTHLY_LOOKBACK_DAYS" if monthly else "WEEKLY_LOOKBACK_DAYS", "31" if monthly else "7"))
    limit = int(os.getenv("MONTHLY_STORY_LIMIT" if monthly else "WEEKLY_STORY_LIMIT", "8" if monthly else "5"))
    stories = select_top_stories(airtable.recent_stories(days=days), limit=limit)
    if not stories:
        raise RuntimeError("No eligible, fully summarized Airtable stories are available for this issue")

    now = datetime.now(UTC)
    issue_type = "Monthly Newsletter" if monthly else "Weekly Brief"
    subject = (
        f"Apogee Admissions Monthly — {now:%B %Y}"
        if monthly else f"Apogee Admissions Weekly Brief — {now:%B} {now.day}, {now.year}"
    )
    html_body = render_email(stories, monthly=monthly)
    if dry_run:
        return {"stories": len(stories), "subject": subject, "campaign_id": "", "sent": False}

    group_name = os.getenv(
        "MAILERLITE_MONTHLY_GROUP_NAME" if monthly else "MAILERLITE_WEEKLY_GROUP_NAME",
        "Weekly Admissions Brief Test",
    )
    mailerlite = MailerLiteClient(http)
    group_id = mailerlite.group_id(group_name)
    campaign_id = mailerlite.create_campaign(
        group_id=group_id,
        sender_email=os.getenv("MAILERLITE_FROM_EMAIL", "adam@apogeecollegeprep.com"),
        sender_name=os.getenv("MAILERLITE_FROM_NAME", "Apogee College Prep"),
        subject=subject,
        name=f"{issue_type} {now.date().isoformat()}",
        html_body=html_body,
    )
    if not monthly:
        mailerlite.send_campaign(campaign_id)
    airtable.record_issue(
        issue=f"{issue_type} {now.date().isoformat()}",
        week_of=now.date().isoformat(),
        status="Draft" if monthly else "Sent",
        subject=subject,
        html_body=html_body,
        provider_id=campaign_id,
    )
    return {"stories": len(stories), "subject": subject, "campaign_id": campaign_id, "sent": not monthly}


def _main(*, monthly: bool) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = deliver(monthly=monthly, dry_run=args.dry_run)
    action = "Prepared" if args.dry_run else ("Created draft" if monthly else "Sent")
    print(f"{action}: {result['subject']} ({result['stories']} stories)")


def weekly_main() -> None:
    _main(monthly=False)


def monthly_main() -> None:
    _main(monthly=True)
