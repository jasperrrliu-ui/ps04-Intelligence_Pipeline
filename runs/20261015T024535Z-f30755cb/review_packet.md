# Editorial review packet — run 20261015T024535Z-f30755cb

As-of date: **2026-10-15 UTC** (the run started on the evening of October 14 in New York). Status: **ready for production**. The English revision passed the deterministic check with review ID `d6059088001ca2b8e912bdb891642e60`; that check verifies file presence, source versions, locators, dates, and coverage. It does not establish that the generated interpretations are factually sound or ready to publish.

## What this run actually produced

- 78 candidate observations extracted in this run; the persistent corpus has 80 eligible records because it also retains two previously collected YouTube videos. The twelve-item topical focus has 2 RSS articles, 2 YouTube videos, 2 podcast episodes, and 6 labeled direct-web articles from 12 independent publishers.
- AI editorial decisions after policy revision: 12 accept, 67 reject, 1 defer. Three connected briefs, three article drafts, and three video-script drafts exist.
- [Summary](summary.json), [mechanical review](review.json), [focused materials](material_shortlist.jsonl), [decisions](decisions.jsonl), [briefs](briefs.jsonl).
- Article drafts: [01](articles/01.md), [02](articles/02.md), [03](articles/03.md). Video scripts: [01](video_scripts/01.md), [02](video_scripts/02.md), [03](video_scripts/03.md).

## Six-decision sample and policy rerun

| Source | AI decision after revision | Editorial audit |
| --- | --- | --- |
| [National Theatre: Bacchae Schools Tour set design](https://www.youtube.com/watch?v=mYCm3Hv8vOU) | Accept | On-topic first-person account of adapting a scenic concept to school spaces. YouTube captions still need checking against the video before direct quotation. |
| [LIGHT TALK: Cory Pattak](https://lighttalk.libsyn.com/light-talk-episode-495-two-steps-ahead-our-conversation-with-lighting-designer-cory-pattak) | Accept | Substantive lighting-design process. Its Whisper transcript is unverified; five cited passages need audio review below. |
| [AuraLuxMuse preprint](https://arxiv.org/html/2610.11792) | Accept | Relevant research prototype. Attribute capabilities and evaluation results to the authors; do not present them as proven production-wide effects. |
| [ABT: Behind the Ballet](https://www.youtube.com/watch?v=IxylEPM9YE8) | Reject | The talk briefly discusses set changes, but the bulk is ballet history and choreography. Its rejection from this narrow editorial scope is defensible; it is not in the twelve-item focus. |
| [WICKED: Production Stage Manager](https://www.youtube.com/watch?v=FEVb6tgzJ40) | Reject | Useful for show-operation context but not substantive scenic/lighting design process. It is not in the twelve-item focus. |
| [Space Hamlet interview](https://www.beyondthecurtain.co.uk/2026/09/dan-sturman-space-hamlet-interview.html) | Accept after policy revision | The first model pass wrongly deferred this full-text web article as an unverified transcript. The revision permits its concrete process account as an attributed, promotional interview; it does not independently verify audience or production outcomes. |

The original policy and decisions, policy-v2 rationale, raw revised decisions, and two metadata-consistency reason corrections are preserved under [revisions](revisions/). The rerun changed two labels: Space Hamlet `defer→accept`, and a separate immersive-art RSS item `reject→defer`. Every source cited in the existing briefs remains accepted.

## Corrections and remaining review

Before this packet, seven brief claims and corresponding draft passages were edited to narrow statements that overstated the AI preprint or implied that a podcast interview proved a general limit on automation. Original briefs and drafts are preserved under [revisions/before_editorial_corrections](revisions/before_editorial_corrections/). The current English drafts keep the evidence markers and citations, and the three pieces now have distinct angles: professional process, beginner learning, and app boundaries. The deterministic review was rerun after the revision and passed.

The mechanical review still flags the following LIGHT TALK ASR segments used by claim `01-c7`. Listen to the [retained audio](../../data/media/podcast_audio/7ad06d181a38262a3297597b/episode-audio) or publisher episode and check the surrounding conversation before publication:

| Segment | Approximate timestamp | ASR excerpt |
| --- | --- | --- |
| `s00041` | 00:02:14 | “Corey has been a working lighting designer for 20 years.” |
| `s01161` | 00:46:57 | “Or a feeling that you need to have to be a light designer.” |
| `s01173` | 00:47:25 | “you better be just as musical as that lighting designer” |
| `s01595` | 01:03:26 | “that I can't see the actors, that's bad lighting design.” |
| `s01597` | 01:03:32 | “If it's overpowering the performers as a lighting designer,” |

The new YouTube subtitles should likewise be checked against the recordings when used for a precise statement. The English article bodies fall within the course's 600–900 word target; video scripts are in English and include feasible visual suggestions. The student reviewed and approved the editorial set. The source index still marks the podcast transcript as automatic, so its five excerpts remain attributed cautiously and should be checked against the retained recording before direct quotation. Review promotional source incentives and the preprint's limited evidence when producing the videos.

## Cost and handoff

The saved Responses API usage records contain 30 completed model calls for this run. Using the listed GPT-4.1 mini standard rates, the **estimated model API cost is USD 0.149546**. This is an estimate, not an invoice; it excludes earlier failed runs, local transcription compute, and network use. See the [model pricing reference](https://developers.openai.com/api/docs/models/gpt-4.1-mini) and the usage details in `summary.json`.

The student's `approve` decision is recorded in `approval.json` against the current `review_id`. The package contains the English article/video-script pairs and source notes. No video has been produced or published, no Substack article has been published, and the separate technical demo is still pending. A second complete live run must occur on another UTC date.
