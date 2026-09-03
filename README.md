# overscript

Updated 03.09.2026

A comprehensive list of anonymous bulletin-board (BBS) scripts. Hosted at https://overscript.net

If you want to contribute to this list, send me an email or make a pull request.

Thanks to the many anonymous contributors who have sent me information over the years.

## The list

Everything lives in [`data.js`](data.js) as a single `script_data` array, rendered by
[`index.html`](index.html) with Vue. One entry looks like this:

```js
{
   "author_name" : "oprel",
   "author_url" : "https://github.com/oprel",
   "download_url" : "https://github.com/oprel/emanon",
   "language" : "Perl",
   "name" : "emanon",
   "notes" : "...",
   "version" : "727486f",
   "status" : "unmaintained",
   "last_checked" : "2026-09-03",
   "created" : "2015"
}
```

### Fields

| field | meaning |
| --- | --- |
| `download_url` | where to get the source today; `#none` when no public source is known |
| `archive_url` | optional: a preserved copy (tanami.org mirror, Google Code Archive or the Wayback Machine) for entries whose upstream has disappeared |
| `version` | latest release, tag or commit |
| `status` | see below |
| `last_checked` | date the entry was last verified by hand or by script |
| `created` | year the project started, when known |

### Statuses

| status | meaning |
| --- | --- |
| `maintained` | commits or releases within the last two years |
| `stable` | finished software that still works and is still downloadable, but sees no active development |
| `unmaintained` | nothing has happened for years, though the source is still available |
| `discontinued` | development stopped for good: the repository is archived/gone or the author said so |
| `missing` | upstream is gone; an `archive_url` is provided wherever a copy could be found |
| `unknown` | could not be verified (usually closed-source scripts or lost hosting) |

## Re-checking the list

`tools/check_sources.py` walks every entry, asks each forge (GitHub via `gh`, plus GitLab,
Gitea/Codeberg and Bitbucket over plain HTTP) for its last activity, latest release or tag,
and falls back to a plain request for ordinary websites. It prints a JSON report you can
diff against `data.js`:

```sh
python3 tools/check_sources.py --out report.json
```

It does not rewrite `data.js` — deciding whether a stalled project is `stable` or
`unmaintained` still needs a human.
