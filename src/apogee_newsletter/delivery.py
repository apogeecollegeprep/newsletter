from __future__ import annotations

import argparse
import html
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .sync import AirtableClient, RetryingSession, required_env, southeast_school_priority


MAILERLITE_API = "https://connect.mailerlite.com/api"
DEFAULT_ISSUES_TABLE_ID = "tblsnPXpizZA9SVfO"
UNSUBSCRIBE_URL = "{$unsubscribe}"
DEFAULT_LOGO_URL = (
    "https://storage.mlcdn.com/account_image/2569796/"
    "lELOmgKaNTA7GQjqpYi6zSHWcJBEeQPCafagKFng.png"
)
DEFAULT_PHYSICAL_ADDRESS = "1439 Fairbanks Street SW\nAtlanta, GA 30310"


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
            southeast_school_priority(story.headline, story.source, story.url),
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


def select_issue_stories(stories: list[Story], *, limit: int, monthly: bool) -> list[Story]:
    """Require explicit editorial selection for the automated weekly brief."""
    eligible = stories if monthly else [story for story in stories if story.selected]
    return select_top_stories(eligible, limit=limit)


def _story_html(story: Story) -> str:
    impact = ""
    if story.applicant_impact:
        impact = (
            '<p style="margin:10px 0 0;color:#184542;font-size:14px;line-height:1.55">'
            f"<strong>Why it matters:</strong> {html.escape(story.applicant_impact)}</p>"
        )
    return f"""
      <article style="padding:20px 0;border-bottom:1px solid #e7e9ee">
        <h3 style="margin:0 0 6px;color:#050F1F;font-size:20px;line-height:1.3"><a href="{html.escape(story.url, quote=True)}" style="color:#050F1F;text-decoration:none">{html.escape(story.headline)}</a></h3>
        <p style="margin:0 0 10px;color:#6b7280;font-size:13px">{html.escape(story.source)}</p>
        <p style="margin:0;color:#191919;font-size:15px;line-height:1.65">{html.escape(story.summary)}</p>
        {impact}
        <p style="margin:12px 0 0"><a href="{html.escape(story.url, quote=True)}" style="color:#1F6C87;font-size:14px;font-weight:700">Read the original story →</a></p>
      </article>
    """


def _grouped_news_html(stories: list[Story]) -> str:
    grouped: dict[str, list[Story]] = {}
    for story in stories:
        grouped.setdefault(story.category, []).append(story)
    return "".join(
        f"""
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td height="20" style="height:20px;line-height:20px;font-size:1px">&nbsp;</td></tr></table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td>
            <h2 style="margin:0;padding:0 0 8px;border-bottom:3px solid #F1A70F;color:#1F6C87;font-size:15px;line-height:1.3;letter-spacing:.08em;text-transform:uppercase">{html.escape(category)}</h2>
            {''.join(_story_html(story) for story in category_stories)}
          </td></tr></table>
        """
        for category, category_stories in grouped.items()
    )


def _monthly_editor_sections_html() -> str:
    """Return modular, MailerLite-friendly placeholders for the monthly issue."""
    video_url = html.escape(os.getenv("MONTHLY_FEATURE_VIDEO_URL", "https://youtu.be/qtVeMiYMGbg"), quote=True)
    video_thumbnail = html.escape(
        os.getenv("MONTHLY_FEATURE_VIDEO_THUMBNAIL", "https://img.youtube.com/vi/qtVeMiYMGbg/hqdefault.jpg"),
        quote=True,
    )
    section_gap = '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td height="36" style="height:36px;line-height:36px;font-size:1px">&nbsp;</td></tr></table>'
    card_gap = '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td height="16" style="height:16px;line-height:16px;font-size:1px">&nbsp;</td></tr></table>'
    return f"""
      <!-- EDITOR: WATCH / READ -->
      {section_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td>
        <p style="margin:0 0 7px;color:#1F6C87;font-size:12px;font-weight:700;letter-spacing:.11em;text-transform:uppercase">CURATED BY APOGEE</p>
        <h2 style="margin:0;padding:0 0 10px;border-bottom:3px solid #F1A70F;color:#050F1F;font-size:24px;line-height:1.25">What We’re Watching &amp; Reading</h2>
      </td></tr></table>
      {card_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F5F7F8;border-left:4px solid #1F6C87;border-radius:8px">
          <tr><td style="padding:20px 22px">
            <p style="margin:0 0 5px;color:#7B8492;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">READ</p>
            <h3 style="margin:0 0 8px;color:#050F1F;font-size:19px">[Add the book, essay, report, or resource title]</h3>
            <p style="margin:0 0 12px;color:#333E4D;font-size:15px;line-height:1.6">[In two or three sentences, explain why this is worth a family’s time and what it adds to the admissions conversation.]</p>
            <a href="https://apogeecollegeprep.com" style="color:#1F6C87;font-size:14px;font-weight:700">Read the recommendation →</a>
          </td></tr>
      </table>

      <!-- EDITOR: MEDIA FEATURE -->
      {section_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td>
        <p style="margin:0 0 7px;color:#1F6C87;font-size:12px;font-weight:700;letter-spacing:.11em;text-transform:uppercase">ONE TO WATCH OR LISTEN TO</p>
        <h2 style="margin:0;padding:0 0 10px;border-bottom:3px solid #F1A70F;color:#050F1F;font-size:24px;line-height:1.25">Media Pick of the Month</h2>
      </td></tr></table>
      {card_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#050F1F;border-radius:10px;overflow:hidden">
        <tr><td>
          <a href="{video_url}" style="display:block;text-decoration:none"><img src="{video_thumbnail}" width="568" alt="Watch the featured Apogee video on YouTube" style="display:block;width:100%;max-width:568px;height:auto;border:0"></a>
        </td></tr>
        <tr><td style="padding:22px 24px 24px">
          <p style="margin:0 0 5px;color:#F1A70F;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">FEATURED VIDEO</p>
          <h3 style="margin:0 0 8px;color:#FFFFFF;font-size:20px">Plan Your College Visits Wisely</h3>
          <p style="margin:0 0 16px;color:#D6DEE3;font-size:15px;line-height:1.6">A practical conversation addressing frequently asked questions about planning college visits. [Add any additional context or takeaway for Apogee families.]</p>
          <a href="{video_url}" style="display:inline-block;padding:12px 18px;background:#F1A70F;border-radius:999px;color:#050F1F;font-size:14px;font-weight:700;text-decoration:none">▶ Watch on YouTube</a>
        </td></tr>
      </table>

      <!-- EDITOR: APOGEE NEWS -->
      {section_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td>
        <p style="margin:0 0 7px;color:#1F6C87;font-size:12px;font-weight:700;letter-spacing:.11em;text-transform:uppercase">FROM OUR COMMUNITY</p>
        <h2 style="margin:0;padding:0 0 10px;border-bottom:3px solid #F1A70F;color:#050F1F;font-size:24px;line-height:1.25">Apogee News</h2>
      </td></tr></table>
      {card_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#FFF9EA;border-radius:10px">
          <tr><td style="padding:22px 24px">
            <p style="margin:0 0 5px;color:#8A6411;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">BUSINESS OR PROGRAM UPDATE</p>
            <h3 style="margin:0 0 8px;color:#050F1F;font-size:20px">[Share what’s new at Apogee]</h3>
            <p style="margin:0 0 12px;color:#333E4D;font-size:15px;line-height:1.6">[Use this space for a new Apogee video, service, event, resource, partnership, or company announcement.]</p>
            <a href="https://apogeecollegeprep.com" style="color:#1F6C87;font-size:14px;font-weight:700">Learn more →</a>
          </td></tr>
      </table>
      {card_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#EEF4F5;border-radius:10px">
          <tr><td style="padding:22px 24px">
            <h3 style="margin:0 0 10px;color:#1F6C87;font-size:17px">Apogee by the Numbers</h3>
            <p style="margin:0 0 4px;color:#050F1F;font-size:34px;font-weight:700;line-height:1">[XX]</p>
            <p style="margin:0;color:#333E4D;font-size:15px;line-height:1.6">[Add one meaningful statistic—for example, acceptances, scholarship dollars, or the range of colleges welcoming Apogee students—and give it brief context.]</p>
          </td></tr>
      </table>

      <!-- EDITOR: COMMUNITY HIGHLIGHT -->
      {section_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F4F0E7;border-radius:10px"><tr><td style="padding:24px">
          <h2 style="margin:0 0 10px;color:#050F1F;font-size:23px">Coach or Student Highlight</h2>
          <h3 style="margin:0 0 8px;color:#7A5B1E;font-size:18px">[Add the person’s name and a short headline]</h3>
          <p style="margin:0 0 12px;color:#46505E;font-size:15px;line-height:1.65">[Tell a concise, human story. Include a photograph and quotation only after receiving permission, and avoid disclosing private admissions information.]</p>
          <p style="margin:0;color:#1F6C87;font-size:16px;font-style:italic;line-height:1.55">“[Optional approved quotation.]”</p>
      </td></tr></table>

      <!-- EDITOR: MENTAL HEALTH -->
      {section_gap}
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#EAF3EF;border-top:4px solid #4D8B78;border-radius:10px"><tr><td style="padding:24px">
          <p style="margin:0 0 6px;color:#356858;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">WHOLE-STUDENT SUPPORT</p>
          <h2 style="margin:0 0 10px;color:#050F1F;font-size:23px">Mental Health &amp; the College Process</h2>
          <h3 style="margin:0 0 8px;color:#173F36;font-size:18px">[Add this month’s practical theme]</h3>
          <p style="margin:0 0 12px;color:#334940;font-size:15px;line-height:1.65">[Offer one grounded, supportive idea for managing the emotional side of applications. Keep the tone practical and avoid diagnosis or individualized medical advice.]</p>
          <p style="margin:0;color:#334940;font-size:13px;line-height:1.55"><strong>Helpful resource:</strong> [Add a credible article, exercise, or professional resource and link it here.]</p>
      </td></tr></table>
    """


def render_email(stories: list[Story], *, monthly: bool = False) -> str:
    title = "Apogee Ascent"
    eyebrow = "MONTHLY NEWSLETTER DRAFT" if monthly else "THIS WEEK IN COLLEGE ADMISSIONS"
    news = _grouped_news_html(stories)
    human_sections = _monthly_editor_sections_html() if monthly else ""
    logo_url = html.escape(os.getenv("APOGEE_LOGO_URL", DEFAULT_LOGO_URL), quote=True)
    physical_address = html.escape(
        os.getenv("APOGEE_PHYSICAL_ADDRESS", DEFAULT_PHYSICAL_ADDRESS).strip()
    ).replace("\n", "<br>")
    news_heading = ""
    intro = ""
    if monthly:
        intro = """
          <p style="margin:0;padding:26px 0 0;color:#334155;font-size:16px;line-height:1.65">A monthly guide to the developments, ideas, and people shaping the college journey.</p>
        """
        news_heading = """
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td height="42" style="height:42px;line-height:42px;font-size:1px">&nbsp;</td></tr></table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td>
            <p style="margin:0 0 7px;color:#1F6C87;font-size:12px;font-weight:700;letter-spacing:.11em;text-transform:uppercase">THE MONTH IN ADMISSIONS</p>
            <h2 style="margin:0;padding:0 0 10px;border-bottom:3px solid #F1A70F;color:#050F1F;font-size:24px;line-height:1.25">What’s in the News</h2>
          </td></tr></table>
        """
    return f"""<!doctype html>
<html><body style="margin:0;background:#F2F2F0;font-family:'Proxima Nova',Arial,sans-serif;color:#191919">
  <div style="display:none;max-height:0;overflow:hidden">Five developments that matter to undergraduate applicants and families.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F2F2F0"><tr><td align="center">
    <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:100%;max-width:640px;background:#ffffff;margin:24px auto;border-radius:12px;overflow:hidden">
      <tr><td style="padding:36px 36px 30px;background:#050F1F;border-top:5px solid #F1A70F">
        <img src="{logo_url}" width="210" alt="Apogee College Prep" style="display:block;width:210px;max-width:68%;height:auto;margin:0 0 24px;border:0">
        <p style="margin:0 0 10px;color:#F1A70F;font-size:12px;font-weight:700;letter-spacing:.12em">{eyebrow}</p>
        <h1 style="margin:0;color:#ffffff;font-size:30px;line-height:1.2">{title}</h1>
      </td></tr>
      <tr><td style="padding:0 36px 32px">
        {intro}
        {human_sections}
        {news_heading}
        {news}
        <p style="margin:30px 0 0;color:#7b8492;font-size:12px;line-height:1.5">You are receiving this update from Apogee College Prep.<br>{physical_address}<br><a href="{UNSUBSCRIBE_URL}" style="color:#7b8492">Unsubscribe or update preferences</a>.</p>
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

    def ensure_group_subscribers(self, *, group_id: str, emails: list[str]) -> int:
        """Non-destructively add or update recipients in the weekly group."""
        unique_emails = list(dict.fromkeys(email.strip().casefold() for email in emails if email.strip()))
        for email in unique_emails:
            self.http.request(
                "POST",
                f"{MAILERLITE_API}/subscribers",
                headers=self.headers,
                json={"email": email, "groups": [group_id]},
            )
        return len(unique_emails)

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
    stories = select_issue_stories(
        airtable.recent_stories(days=days),
        limit=limit,
        monthly=monthly,
    )
    if not stories:
        raise RuntimeError("No eligible, fully summarized Airtable stories are available for this issue")

    now = datetime.now(UTC)
    issue_type = "Apogee Ascent Monthly" if monthly else "Apogee Ascent"
    subject = (
        f"Apogee Ascent — {now:%B %Y}"
        if monthly else f"Apogee Ascent — {now:%B} {now.day}, {now.year}"
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
    if not monthly:
        weekly_recipients = os.getenv("MAILERLITE_WEEKLY_RECIPIENTS", "").split(",")
        mailerlite.ensure_group_subscribers(group_id=group_id, emails=weekly_recipients)
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
