import html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import click
import praw
import prawcore
import stamina
from lxml import etree


ATOM_NS = "http://www.w3.org/2005/Atom"
MEDIA_NS = "http://search.yahoo.com/mrss/"
FEED_URL = "https://honzajavorek.github.io/f1news/f1news.xml"
NEWS_FLAIR = ":post-news: News"


def get_focus_url(url: str) -> str:
    return f"firefox-focus://open-url?url={quote(url, safe='')}"


def get_image_url(submission) -> str | None:
    preview = getattr(submission, "preview", None)
    if preview:
        try:
            return html.unescape(preview["images"][0]["source"]["url"])
        except (KeyError, IndexError):
            pass
    thumbnail = submission.thumbnail
    if thumbnail.startswith("http"):
        return thumbnail
    return None


@click.command()
@click.option("--subreddit", default="formula1", help="Subreddit to scrape for news")
@click.option(
    "--limit", default=100, help="How many recent submissions to check for news flair"
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default="feed.xml",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Output file path",
)
@click.option(
    "--client-user-agent", default="F1news (+https://github.com/honzajavorek/f1news/)"
)
@click.option("--client-id", envvar="REDDIT_CLIENT_ID", required=True)
@click.option("--client-secret", envvar="REDDIT_CLIENT_SECRET", required=True)
def main(
    subreddit: str,
    limit: int,
    output_path: Path,
    client_user_agent: str,
    client_id: str,
    client_secret: str,
):
    click.echo("Initializing file system")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Initializing Reddit API client")
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=client_user_agent,
    )
    reddit.read_only = True

    click.echo(f"Fetching r/{subreddit} submissions")
    for attempt in stamina.retry_context(on=prawcore.exceptions.ResponseException):
        with attempt:
            submissions = list(reddit.subreddit(subreddit).new(limit=limit))
    if not submissions:
        raise click.ClickException(
            f"Got 0 submissions from r/{subreddit}, Reddit API fetch likely failed"
        )
    click.echo(f"Fetched {len(submissions)} submissions")

    click.echo("Building feed")
    feed = etree.Element("feed", nsmap={None: ATOM_NS, "media": MEDIA_NS})
    now = datetime.now(timezone.utc).isoformat()
    etree.SubElement(feed, "title").text = "F1news"
    etree.SubElement(feed, "id").text = FEED_URL
    etree.SubElement(feed, "updated").text = now
    etree.SubElement(
        feed, "link", {"rel": "self", "href": FEED_URL, "type": "application/atom+xml"}
    )

    for submission in submissions:
        if submission.link_flair_text != NEWS_FLAIR:
            continue
        click.echo(f"Recording as {submission.url}")
        entry = etree.SubElement(feed, "entry")
        etree.SubElement(entry, "title").text = submission.title
        etree.SubElement(entry, "id").text = f"reddit:{submission.id}"
        etree.SubElement(entry, "link", {"href": submission.url})
        published = datetime.fromtimestamp(
            submission.created_utc, tz=timezone.utc
        ).isoformat()
        etree.SubElement(entry, "published").text = published
        etree.SubElement(entry, "updated").text = published
        focus_url = get_focus_url(submission.url)
        summary_html = f'<a href="{focus_url}">Open in Firefox Focus</a>'
        if submission.selftext:
            description = html.escape(submission.selftext).replace("\n", "<br>")
            summary_html += f"<hr>{description}"
        etree.SubElement(entry, "summary", {"type": "html"}).text = summary_html
        if image_url := get_image_url(submission):
            etree.SubElement(entry, f"{{{MEDIA_NS}}}thumbnail", {"url": image_url})

    click.echo(f"Writing feed to {output_path}")
    Path(output_path).write_bytes(
        etree.tostring(feed, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    )
