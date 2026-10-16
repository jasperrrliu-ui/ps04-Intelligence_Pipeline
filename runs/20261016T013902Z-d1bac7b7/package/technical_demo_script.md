# Technical Demonstration — Narration and Screen Plan

**Target runtime:** 4–6 minutes; about 600 spoken words at a measured pace.  
**Language:** English.  
**Purpose:** Explain the project, collection and orchestration, repeated runs, maintenance model, and published deliverables. This is separate from the three audience-facing videos.

## Screen plan and narration

### 0:00–0:40 — What the project is about

**Show:** `config/project.json` and the overview diagram `demo_visual.svg`.

**Narration:**

This project is a research-to-publication pipeline for people who enjoy theatre but do not have professional stage-design training. We want to understand three things: how scenic and lighting designers work, what helps a beginner learn to see those choices, and where an AI-assisted stage-design app could help without pretending to replace a designer. The project does not build that app. It collects recent evidence and turns it into a small, reviewed publication series.

### 0:40–1:45 — Sources and turning media into usable evidence

**Show:** `config/sources.json`, `config/supplemental_articles.json`, one record from each source type, then `items.jsonl` and a timestamped `segments.json` asset.

**Narration:**

We use three source types. The configuration has four RSS feed endpoints, two specific YouTube video URLs, and two podcast RSS feeds. We also configured six direct-web supplements as a clearly labeled source set. For RSS, the feed is a discovery index: it gives us titles, dates, identifiers, and article URLs. The extraction stage downloads and cleans the article body; the RSS record alone is not the full article.

For YouTube, `yt-dlp` reads metadata and comments for the configured video URL. The extractor tries English captions, including auto-captions. If usable captions are unavailable, it can retain the audio, convert it with FFmpeg, and use `whisper.cpp` to create timestamped segments. Podcasts follow a similar path: the RSS enclosure points to the audio, a publisher transcript is used when available, and otherwise the audio can be transcribed with FFmpeg and `whisper.cpp`.

The result is a common item record with a stable item ID, publisher ID, publication date, source URL, retained text, and—when the source is audio or video—timestamped transcript segments. A substantive change creates a new content version; simply fetching the same item again does not. Text, segments, and downloaded media are retained as assets so a claim can be checked against the exact material used.

### 1:45–2:45 — Orchestration, backfill, and the 30-day window

**Show:** `run.sh`, `workflows/collect_sources.sh`, `workflows/create_series.sh`, and the run folder.

**Narration:**

This is an orchestration pipeline, not an autonomous agent. `run.sh` creates a new run ID, records the UTC as-of date, and snapshots the source list, project brief, policy, and prompts. The collection workflow runs the collectors, extracts content, upserts versions into SQLite, exports the corpus, filters dates, and creates the focused shortlist. JSONL files are the visible handoffs between stages; SQLite keeps stable item identities and content versions.

The date filter uses the as-of date and includes that day plus the previous 29 days. Each feed run scans the recent entries still exposed by its configured RSS or podcast feed, so a missed few days can be backfilled on a later run. Re-seeing an unchanged item does not create a duplicate version. One current limitation is that the YouTube sources are configured individual videos, not a channel-wide new-upload feed; new videos need to be added to the source configuration.

After normalization, the series workflow has several explicit steps. First, the model makes an accept, reject, or defer decision for each eligible item and records a reason. Accepted evidence is then organized into three briefs, each with its own question, argument, claims, evidence references, and limitations. The three lenses are: professional scenic and lighting design process; beginner learning scaffolds; and implications and boundaries for a future AI stage-design app. The article writer turns each brief into an English article, while the video writer turns the same brief into a companion script. Both outputs keep claim references tied to source passages or timestamped transcript segments. Deterministic checks then verify required files, references, language, coverage, and consistency. A human reviews the drafts and approval record before packaging. `bash run.sh --package runs/RUN_ID` refreshes the package from approved outputs without recollecting sources or rewriting the articles.

### 2:45–3:35 — Why there were two live runs

**Show:** the two `run.json` files and `summary.json` files for `20261015T024535Z-f30755cb` and `20261016T013902Z-d1bac7b7`; briefly show the earlier failed collection and recovery summaries.

**Narration:**

The first full live run was anchored to October 15 UTC. After its drafts were reviewed and approved, we ran the pipeline again on October 16 UTC. The assignment calls for live runs on different dates, and the second run also shows that the rolling window and persistent store work across editions.

The second run discovered and extracted 78 records. Six were new, 23 had changed evidence versions, and 49 were unchanged. Combined with retained history, 86 records were eligible for the date filter. The focused edition used 12 materials from 12 independent publishers: two RSS articles, two YouTube videos, two podcast episodes, and six clearly labeled web supplements. The second run did not only process the 29 changed or new records; it re-ran the edition workflow over the current eligible corpus and produced a fresh set of three briefs, articles, and scripts. An earlier collection-only attempt missed podcast transcripts; it remains documented as incomplete, and a later collection-only run records recovery. Neither collection-only run is misrepresented as a full live editorial run.

### 3:35–4:25 — How it stays maintainable

**Show:** a run's `config/`, `prompts/`, `logs/`, `changes.jsonl`, and `data/evidence/index.sqlite3`.

**Narration:**

The repository does not contain an always-running loop. A person or an external scheduler starts `bash run.sh`; that command creates a timestamped run folder and saves the exact source list, project brief, editorial policy, prompts, logs, and outputs. New editions can be scheduled or started manually using the same command. Each run scans the recent entries still exposed by the feeds, so a missed few days can be backfilled if the items remain available and within the 30-day window. The SQLite store reuses unchanged transcripts and preserves earlier versions. If a source endpoint changes or a YouTube video is replaced, the source configuration is updated and a new run is created; old run snapshots stay intact. In this configuration, YouTube items are specific video URLs, so adding newly published channel videos still requires updating the source list.

### 4:25–5:10 — Deliverables

**Show:** the three article links and matching YouTube videos, then `SUBMISSION.md`.

**Narration:**

The final audience-facing deliverables are three English articles and three companion YouTube videos. The first introduces professional scenic and lighting design; the second focuses on how a beginner can understand the process and what AI research currently suggests; the third discusses what a beginner-facing AI stage-design app should teach and where its promises should stop. Each article and video is cross-linked, and the source notes preserve the evidence behind the articles.

The key result is not just six pieces of content. It is a repeatable path from configured sources, through retained and timestamped evidence and human-reviewed editorial choices, to public articles and videos. This separate demonstration makes that path visible.

## Recording checklist

- Keep narration and on-screen interface in English.
- Show the actual RSS, YouTube, and podcast records and at least one retained transcript segment.
- Show the two dated run summaries and explain the earlier incomplete collection separately.
- Do not imply the configured YouTube URLs automatically discover every new channel upload.
- Keep API keys and other credentials off screen.
- Add the final technical demonstration URL to `SUBMISSION.md` after publishing it.
