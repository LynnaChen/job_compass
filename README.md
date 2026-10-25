# Job Compass

A private, local job-search and application tracker driven by your resume PDF.

[中文说明](README.zh-CN.md)

## What it does

- Parse a text-based resume PDF locally, without an API key.
- Suggest skills and target roles; let you edit the suggestions before searching.
- Search public sources using confirmed keywords, job types and country. Cities affect priority rather than excluding the rest of the country.
- Keep student jobs, theses, internships and other jobs in one workspace.
- Record an application directly from a job card, maintain a visible progress timeline, and move rejected applications to the bottom in grey.
- Optionally refresh daily while the local process runs. Automatic updates start disabled.
- Keep AI research opportunities in a separate, evidence-based view when relevant jobs are found.

## Quick start

Requires Python 3.11 or newer. The only third-party runtime dependency is pypdf.

Windows PowerShell, from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open [Job Compass](http://127.0.0.1:18866). On Windows, after installation, `start.cmd` opens the browser and starts the background process if needed.

1. Upload your resume in **简历与方向** (Resume and search profile), or enter your profile manually.
2. Review roles, skills, keywords, country, preferred cities and job types.
3. Select **保存并搜索** (Save and search).
4. Use **记录已投** to record an application after submitting it yourself. It does not submit applications to employers.
5. Enable daily updates under preferences if wanted. The schedule uses Europe/Berlin time, default 09:00; the computer and process must be running.

The interface is currently Chinese; search terms support English, German and Chinese. Initial matching uses a transparent keyword catalog, not a language model. Suggested roles are editable and are not a hiring assessment.

## Data and privacy

The project ships with no resumes, personal profile, jobs, applications, notes, screenshots, credentials, or database.

PDF bytes and extracted text are processed in memory, not stored. Only the skills and search preferences you confirm are saved to `data/profile.json`. Contact information is not extracted into that profile. Do not put personal details into keyword fields. The original PDF is never sent to a model or a search engine.

When you search, confirmed skill/role terms and country are sent to the selected public search services. Applications, notes and progress stay in `data/jobs.sqlite3`. Runtime state and local environments are ignored by Git and excluded by the release packager. If you edit or add files, review those changes before publishing; the bundled scanner cannot identify every possible personal detail.

Keep the entire `data/` folder when backing up; stop the application before copying a live database. Each person should run their own copy. There are no shared accounts or public registration.

## Discovery coverage and limitations

Germany: Arbeitnow public API, Fraunhofer official listings, and Bing RSS discovery. Austria and Switzerland: web discovery and generated external search links; automated coverage is more limited. The app does not claim to search the entire web. Search-engine empty responses are reported as unavailable, not a successful exhaustive search. Use the external search links if a source is blocked or empty. A source can return zero matching candidates without there being zero opportunities elsewhere.

Language requirements are displayed rather than used to exclude jobs. First discovery and publisher dates are distinct. A reachable vacancy page is not proof that recruitment is still open. A thesis is not necessarily paid or open to external students. Scanned PDFs, encrypted PDFs, files over 5 MB and resumes over 15 pages are not supported. Keywords can always be entered manually.

Optional research sources can be added to the private `data/research_sources.json` file as a list of objects with `url`, `title`, `company`, `location`, `description`, `organization_type`, `opportunity_type` (`topic`), `opportunity_note`, and `expected` text fragments. No personal or preselected university topic list is bundled.

## Configuration

- `JOB_COMPASS_OSS_PORT`: local port, default 18866. The server binds only to 127.0.0.1.
- `JOB_COMPASS_OSS_DATA`: private runtime directory, default `data/` in this project.
- `JOB_COMPASS_SYSTEM_PROXY=1`: opt into system proxy settings; otherwise requests connect directly.

On Windows, optional login startup is installed by `install-autostart.ps1` and removed by `remove-autostart.ps1`. It uses its own `JobCompassOpenSource` entry. It is not installed automatically.

## Development and release

```sh
python -m unittest discover -s tests -v
python scripts/package_release.py --check
python scripts/package_release.py
```

Tests use synthetic resumes and isolated databases. The release ZIP contains only allowlisted source files, documentation, tests and the MIT license. It excludes `data/`, PDF files, screenshots, environments and logs. Unzip it to get a clean project suitable for a new GitHub repository. No credentials are needed to run the tool. No GitHub publishing happens automatically.

## License

MIT. See [LICENSE](LICENSE).
