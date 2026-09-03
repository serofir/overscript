#!/usr/bin/env python3
"""Re-check every entry in data.js and report what is still alive.

For each script the checker asks the hosting forge (GitHub, GitLab, Gitea/Codeberg or
Bitbucket) for the last commit/tag/release, and falls back to a plain HTTP request for
ordinary websites. Nothing is written back to data.js: turning the report into new
versions and statuses needs a human.

Usage:
    python3 tools/check_sources.py [--data data.js] [--out report.json]

GitHub calls go through the GitHub API. Run `gh auth login` first to get a 5000/hour
rate limit instead of the anonymous 60/hour.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

USER_AGENT = "overscript-linkchecker (+https://github.com/serofir/overscript)"

GITHUB_API = "https://api.github.com/"
GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/([^/]+)/([^/?#]+)")
BITBUCKET_RE = re.compile(r"https?://(?:www\.)?bitbucket\.org/([^/]+)/([^/?#]+)")
# gitgud.io and gitlab.com are GitLab, the rest are Gitea/Forgejo
GITEA_HOSTS = ("codeberg.org", "git.bienvenidoainternet.org", "git.kiwifarms.net",
               "git.kiwifarms.st", "git.tanami.org")
GITLAB_HOSTS = ("gitlab.com", "gitgud.io")
FORGE_RE = re.compile(r"https?://(?:www\.)?([^/]+)/(.+)")


def github_token():
    try:
        token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                               timeout=20).stdout.strip()
        return token or None
    except Exception:
        return None


TOKEN = github_token()


def request(url, timeout=30):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if TOKEN and url.startswith(GITHUB_API):
        headers["Authorization"] = "Bearer " + TOKEN
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=timeout) as response:
            return response.status, response.read(1 << 20)
    except urllib.error.HTTPError as err:
        return err.code, err.read(4096)
    except Exception as err:                                   # noqa: BLE001
        return 0, str(err).encode()


def days_since(stamp):
    if not stamp:
        return None
    try:
        date = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        return (datetime.now(timezone.utc).date() - date).days
    except ValueError:
        return None


def check_github(owner, repo, result):
    code, body = request("%srepos/%s/%s" % (GITHUB_API, owner, repo))
    try:
        meta = json.loads(body)
    except ValueError:
        meta = {}
    result["http"] = code
    result["kind"] = "github"
    if code != 200:
        result["alive"] = False
        result["error"] = meta.get("message", "HTTP %s" % code)
        return
    result["alive"] = True
    result["archived"] = meta.get("archived", False)
    result["last_commit"] = meta.get("pushed_at")
    result["idle_days"] = days_since(meta.get("pushed_at"))
    result["stars"] = meta.get("stargazers_count")
    full_name = meta.get("full_name", "%s/%s" % (owner, repo))
    result["home"] = meta.get("html_url")
    if full_name.lower() != ("%s/%s" % (owner, repo)).lower():
        result["moved_to"] = full_name
    for path in ("releases/latest", "tags?per_page=1", "commits?per_page=1"):
        code, body = request("%srepos/%s/%s" % (GITHUB_API, full_name, path))
        if code != 200:
            continue
        try:
            payload = json.loads(body)
        except ValueError:
            continue
        if path == "releases/latest" and payload.get("tag_name"):
            result["version"] = payload["tag_name"]
            result["version_date"] = (payload.get("published_at") or "")[:10]
            break
        if path.startswith("tags") and payload:
            result["version"] = payload[0].get("name")
            break
        if path.startswith("commits") and payload:
            commit = payload[0]
            result["version"] = commit.get("sha", "")[:7]
            result["version_date"] = ((commit.get("commit") or {}).get("author")
                                      or {}).get("date", "")[:10]


def check_gitea(host, path, result):
    base = "https://%s/api/v1/repos/%s" % (host, path)
    code, body = request(base)
    result["http"] = code
    result["kind"] = "gitea"
    if code == 200:
        meta = json.loads(body)
        result["alive"] = True
        result["archived"] = meta.get("archived", False)
        result["last_commit"] = meta.get("updated_at")
        result["idle_days"] = days_since(meta.get("updated_at"))
        result["home"] = meta.get("html_url")
    else:
        result["alive"] = False
    code, body = request(base + "/releases/latest")
    if code == 200:
        try:
            release = json.loads(body)
            result["version"] = release.get("tag_name") or release.get("name")
            result["version_date"] = (release.get("published_at") or "")[:10]
        except ValueError:
            pass


def check_gitlab(host, path, result):
    url = "https://%s/api/v4/projects/%s" % (host, urllib.parse.quote(path, safe=""))
    code, body = request(url)
    result["http"] = code
    result["kind"] = "gitlab"
    if code != 200:
        result["alive"] = False
        return
    meta = json.loads(body)
    result["alive"] = True
    result["archived"] = meta.get("archived", False)
    result["last_commit"] = meta.get("last_activity_at")
    result["idle_days"] = days_since(meta.get("last_activity_at"))
    result["home"] = meta.get("web_url")
    code, body = request(url + "/repository/tags")
    if code == 200:
        try:
            tags = json.loads(body)
            if tags:
                result["version"] = tags[0].get("name")
        except ValueError:
            pass


def check_bitbucket(owner, repo, result):
    url = "https://api.bitbucket.org/2.0/repositories/%s/%s" % (owner, repo)
    code, body = request(url)
    result["http"] = code
    result["kind"] = "bitbucket"
    if code != 200:
        result["alive"] = False
        return
    meta = json.loads(body)
    result["alive"] = True
    result["last_commit"] = meta.get("updated_on")
    result["idle_days"] = days_since(meta.get("updated_on"))
    result["home"] = (meta.get("links", {}).get("html", {}) or {}).get("href")


def check_website(url, result):
    code, _ = request(url)
    if code == 0:                       # some hosts reject HEAD/GET from scripts
        code, _ = request(url, timeout=45)
    result["http"] = code
    result["kind"] = "website"
    if code == 0:                       # could not connect at all: not proof of death
        result["error"] = "connection failed"
        return
    result["alive"] = 200 <= code < 400


def check(entry):
    url = (entry.get("download_url") or "").strip()
    result = {"name": entry.get("name"), "download_url": url, "alive": None,
              "http": None, "kind": "none", "version": None, "version_date": None,
              "last_commit": None, "idle_days": None, "archived": None,
              "moved_to": None, "error": ""}

    if not url or url.startswith("#"):
        result["kind"] = "no-source"
        return result
    if not url.startswith("http"):
        result["kind"] = "local-copy"
        return result

    match = GITHUB_RE.match(url)
    if match:
        check_github(match.group(1), match.group(2).removesuffix(".git"), result)
        return result

    match = BITBUCKET_RE.match(url)
    if match:
        check_bitbucket(match.group(1), match.group(2), result)
        return result

    match = FORGE_RE.match(url)
    if match:
        host, path = match.group(1), match.group(2).strip("/").removesuffix(".git")
        # only treat it as a forge when the URL looks like owner/repo
        if len(path.split("/")) == 2:
            if host in GITEA_HOSTS:
                check_gitea(host, path, result)
                return result
            if host in GITLAB_HOSTS:
                check_gitlab(host, path, result)
                return result

    check_website(url, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default="data.js", help="path to data.js")
    parser.add_argument("--out", default="", help="write the JSON report here as well")
    args = parser.parse_args()

    try:
        source = open(args.data, encoding="utf-8").read()
        data = json.loads(source[source.index("=") + 1:].strip())
    except (OSError, ValueError) as err:
        sys.exit("could not read %s: %s" % (args.data, err))

    with ThreadPoolExecutor(max_workers=8) as pool:
        report = list(pool.map(check, data))

    output = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
    print(output)


if __name__ == "__main__":
    main()
