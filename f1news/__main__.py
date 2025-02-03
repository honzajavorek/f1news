from pathlib import Path
import click
import feedparser

import httpx
from lxml import etree
import praw
import praw.exceptions
import stamina


@click.command()
@click.option(
    "--feed",
    "feed_url",
    default="https://www.reddit.com/r/formula1.rss",
    help="RSS feed URL",
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
    "--user-agent", default="F1news (+https://github.com/honzajavorek/f1news/)"
)
@click.option("--client-id", envvar="REDDIT_CLIENT_ID", required=True)
@click.option("--client-secret", envvar="REDDIT_CLIENT_SECRET", required=True)
def main(
    feed_url: str,
    output_path: Path,
    user_agent: str,
    client_id: str,
    client_secret: str,
):
    click.echo("Initializing file system")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Initializing Reddit API client")
    reddit = praw.Reddit(
        client_id=client_id, client_secret=client_secret, user_agent=user_agent
    )
    reddit.read_only = True

    click.echo("Fetching feed")
    response = httpx.get(
        feed_url,
        follow_redirects=True,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
        },
    )
    response.raise_for_status()

    click.echo("Parsing feed")
    xml_bytes = response.content
    feed = feedparser.parse(xml_bytes)

    url_mapping = {}
    for entry in feed.entries:
        for attempt in stamina.retry_context(on=praw.exceptions.PRAWException):
            with attempt:
                click.echo(f"Fetching: {entry.link} (attempt #{attempt.num})")
                submission = reddit.submission(url=entry.link)
        if submission.link_flair_text == ":post-news: News":
            click.echo(f"Recording as {submission.url}")
            url_mapping[entry.link] = submission.url
        else:
            click.echo("Not news")

    click.echo("Rewriting feed")
    xml = etree.fromstring(xml_bytes)
    namespaces = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in xml.xpath("//atom:entry", namespaces=namespaces):
        link = entry.find("./atom:link", namespaces=namespaces)
        try:
            link.set("href", url_mapping[link.get("href")])
            click.echo(f"Keeping {link.get('href')}")
        except KeyError:
            click.echo(f"Removing {link.get('href')}")
            entry.getparent().remove(entry)

    click.echo(f"Writing feed to {output_path}")
    Path(output_path).write_bytes(
        etree.tostring(xml, pretty_print=True, xml_declaration=True)
    )
