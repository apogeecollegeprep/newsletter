# Apogee Ascent

This first phase collects prospective-student admissions news from Inoreader and writes qualified, deduplicated candidates to Airtable. The scheduled review then reads each selected article and enriches its Airtable record. It does not send email yet.

## Editorial workflow

1. Inoreader gathers articles from selected sources.
2. The daily automation reads the previous 28 hours of items.
3. Only sources marked **Active** in Airtable's `Sources` table are accepted.
4. Post-enrollment campus-life topics and international-student-only topics are rejected.
5. The classifier evaluates the headline first and then a cleaned version of the article's first three feed paragraphs using stricter body-level signals. This captures indirect but important stories—such as admissions fraud, application verification, and changed requirements—without treating navigation or related-story links as article content. Up to the ten most relevant new candidates are ranked, categorized, and added to Airtable with status **New**; admissions-integrity investigations receive an extra priority point. When stories are otherwise comparable, the ranking gives a modest preference to Southeastern schools in Apogee's application data, led by the University of Georgia, South Carolina, Alabama, and Georgia Tech.
6. Each candidate article is opened and its full accessible body is reviewed. Airtable receives a neutral 2–4 sentence summary plus a 1–2 sentence explanation of the practical impact for undergraduate applicants and families. If a publisher blocks the full article, the limitation is disclosed in **Editorial Notes**.
7. Graduate/professional-school-only stories, historical pieces without a current applicant takeaway, and stories without a material undergraduate admissions connection are marked **Rejected**.
8. Apogee editors review, approve, reject, and select stories in Airtable.

The Airtable base is `Apogee Admissions Newsletter` (`appjM2J9lAfpLyfd7`).

## Required GitHub secrets

- `AIRTABLE_TOKEN`: an Airtable personal access token with record read/write access to the Apogee base.
- `INOREADER_CLIENT_ID`: the App ID from an Inoreader registered application.
- `INOREADER_CLIENT_SECRET`: the App key from that application.
- `INOREADER_REFRESH_TOKEN`: an OAuth refresh token with `read` scope.

Never commit these values. Add them under repository **Settings → Secrets and variables → Actions**.

## Inoreader OAuth setup

1. In Inoreader preferences, register an application and set a redirect URI you control.
2. Locally set `INOREADER_CLIENT_ID`, `INOREADER_CLIENT_SECRET`, and `INOREADER_REDIRECT_URI`.
3. Install the project with `python -m pip install -e .`.
4. Run `python scripts/inoreader_oauth.py` and open the displayed authorization URL.
5. Copy the returned authorization code and run `python scripts/inoreader_oauth.py --code CODE`.
6. Store the resulting refresh token in GitHub Actions as `INOREADER_REFRESH_TOKEN`.

The automation reads only the Inoreader folder `Apogee Newsletter`, using the stream ID `user/-/label/Apogee Newsletter`.

## Airtable token

Create a personal access token at <https://airtable.com/create/tokens> with these scopes:

- `data.records:read`
- `data.records:write`

Restrict its resource access to the `Apogee Admissions Newsletter` base.

## Local validation

```text
python -m pip install -e '.[dev]'
pytest
sync-newsletter --dry-run
```

The scheduled task runs daily at 8:00 a.m. Eastern and creates and enriches Airtable candidate records.

## MailerLite delivery

The weekly workflow sends a five-story **Apogee Ascent** brief to the MailerLite group `Weekly Admissions Brief Test` every Monday at 8:30 a.m. Eastern. It only uses Airtable candidates that have a full **Neutral Summary**, are not rejected, and have the **Selected** checkbox turned on. Among those editor-approved records, it preserves category variety and uses the same Southeastern-school preference as a tie-breaker. Before each send, it non-destructively ensures the configured weekly recipients belong to the MailerLite group. It records the sent campaign in Airtable's `Issues` table.

The email footer uses Apogee's physical mailing address: `1439 Fairbanks Street SW, Atlanta, GA 30310`.

The monthly workflow creates an editable MailerLite draft. It pre-populates the news section and branded layout, while leaving clearly marked **Student Highlight** and **Video Feature** sections for a human editor. It never sends the monthly issue automatically.

Add these GitHub Actions values:

- Secret `MAILERLITE_API_KEY`
- Secret `AIRTABLE` (the Airtable personal access token already used by this repository)

The test sender is `Apogee College Prep <adam@apogeecollegeprep.com>`. MailerLite may substitute its temporary sending domain until an Apogee domain is authenticated.

MailerLite currently documents API-supplied HTML campaign content as a Power-plan feature. The manual workflow intentionally provides a controlled live test: if the account rejects custom HTML, the action fails before scheduling or sending the campaign and its log contains MailerLite's validation response.
