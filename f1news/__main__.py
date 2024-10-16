from pathlib import Path
from urllib.parse import parse_qs
from bs4 import BeautifulSoup
import click
import feedparser

import httpx
from lxml import etree


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
def main(feed_url: str, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8,cs;q=0.6,sk;q=0.4,es;q=0.2",
            "DNT": "1",
        },
    ) as client:
        click.echo("Fetching feed")
        response = client.get(feed_url)
        response.raise_for_status()

        click.echo("Parsing feed")
        xml_bytes = response.content
        feed = feedparser.parse(xml_bytes)

        url_mapping = {}
        for entry in feed.entries:
            click.echo(f"Fetching: {entry.link}")
            response = client.get(entry.link)
            response.raise_for_status()

            click.echo(f"Parsing: {entry.link}")
            soup = BeautifulSoup(response.content, "html.parser")
            flair_link = soup.select_one('a[href*="/r/formula1/?f=flair_name"]')
            _, query_string = flair_link["href"].split("?")
            f_param_value = parse_qs(query_string)["f"][0]
            if f_param_value != 'flair_name:":post-news: News"':
                click.echo(f"Not news: {entry.link}")
                continue
            article_link = soup.select_one(
                'a[aria-label][target="_blank"][rel*="nofollow"][rel*="noopener"]'
            )
            article_url = article_link["href"]
            click.echo(f"Recording: {entry.link}")
            url_mapping[entry.link] = article_url

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
